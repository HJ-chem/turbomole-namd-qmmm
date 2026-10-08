#!/usr/bin/env python3
# Copyright (c) 2026 Hao Jiang
# SPDX-License-Identifier: MIT
"""NAMD custom-QM adapter for TURBOMOLE ridft/rdgrad.

The adapter preserves NAMD result ordering and restores compacted point-charge
forces. Prepare matching control, basis, and orbital files before running it.
Coordinate order is part of that setup, not a cosmetic option. See docs/tutorial.md.
The supported public workflow uses one fixed QM region and electrostatic embedding.
"""

import os
import sys
import shutil
import subprocess as sp
import re
import errno
import argparse
import math

# ===========================================================================
# COMMAND-LINE PARAMETER OVERVIEW (see build_arg_parser() below for full
# help text on each — this is just a quick-reference list)
# ===========================================================================
# Every flag below falls back to a QM_* environment variable when omitted
# (e.g. via NAMD's `set env(QM_PDB_FILE) "qm-sel.pdb"` in the .conf), then
# to the hardcoded default shown — an explicit flag on QMExecPath always
# wins over its environment variable.
#
#   input_file          (positional, required) NAMD appends this automatically
#   --scf-cmd             TURBOMOLE SCF executable       $QM_SCF_CMD       (default: ridft)
#   --grad-cmd            TURBOMOLE gradient executable  $QM_GRAD_CMD      (default: rdgrad)
#   --scf-log             SCF log filename                $QM_SCF_LOG      (default: ridft.log)
#   --grad-log            Gradient log filename           $QM_GRAD_LOG     (default: rdgrad.log)
#   --run-dir             Base dir for --pdb-file          $QM_RUN_DIR      (default: none)
#   --pdb-file            Path to qm-sel.pdb               $QM_PDB_FILE     (default: none)
#                         (for --coord-order auto/pdb)
#   --charge-mode         'none' | 'mulliken'              $QM_CHARGE_MODE  (default: mulliken)
#   / --QMChargeMode      (case-insensitive; 'chelpg' rejected — ORCA-only in NAMD)
#   --coord-order         'auto' | 'namd' | 'pdb'          $QM_COORD_ORDER  (default: auto)
#                         (case-insensitive)
#   --input-dir-tmpl      Staging dir template, {n}=region $QM_INPUT_DIR_TMPL   (default: input_{n})
#   --output-dir-tmpl     Restart-file archive dir template $QM_OUTPUT_DIR_TMPL  (default: output_{n})
#   --results-dir-tmpl    Per-step results archive dir tmpl $QM_RESULTS_DIR_TMPL (default: results_{n})
#
# TURBOMOLE core count / parallelization (e.g. PARNODES, SMPCPUS, OMP_NUM_THREADS)
# is INTENTIONALLY not a flag here — this script never sets or overrides any
# environment variable; it simply inherits whatever the calling process (e.g.
# a SLURM job script) already has exported. Configure that outside this file.
# ===========================================================================

# ===========================================================================
# Fixed TURBOMOLE I/O file names
# ===========================================================================
# These are dictated by TURBOMOLE itself (its executables always read/write
# files with these exact names in the working directory) — do NOT change
# unless you are also renaming files inside TURBOMOLE's own control file.
# Centralized here purely so the rest of the script has no bare string
# literals scattered through the logic. Not exposed as CLI flags since
# they are never meant to vary between runs.
COORD_FILE        = 'coord'
POINT_CHARGE_FILE = 'point_charges'
GRADIENT_FILE      = 'gradient'
ENERGY_FILE        = 'energy'
PC_GRADIENT_FILE   = 'pc_gradient'
STEP_FILE          = 'step'

# --- Files copied to output_N/ (wavefunction restart files) -----------------
# These are read back by TURBOMOLE at the start of the next step.
OUTPUT_FILES = ['alpha', 'beta', 'mos', 'basis', 'auxbasis', 'control']

# --- Initialization sentinel files ------------------------------------------
# For each QM region the script maps turbo-exec/N-1/ to input_N/, output_N/, results_N/
# Example with 3 QM regions:
#   turbo-exec/0  <->  input_1 / output_1 / results_1
#   turbo-exec/1  <->  input_2 / output_2 / results_2
#   turbo-exec/2  <->  input_3 / output_3 / results_3
#
# Each region is initialized from its own input_N/ ONLY when NONE of the
# files below are present in turbo-exec/N-1/.  Add/remove names as needed.
INIT_SENTINEL_FILES = ['control', 'basis', 'alpha', 'beta', 'mos']

# ===========================================================================
# PHYSICAL CONSTANTS (do not change unless you know what you are doing)
# ===========================================================================
BOHR_TO_ANG       = 0.529177210903
ANG_TO_BOHR       = 1.0 / BOHR_TO_ANG
HARTREE_TO_KCALMOL = 627.509469
GRAD_TO_NAMD_FORCE = -HARTREE_TO_KCALMOL / BOHR_TO_ANG   # gradient -> kcal/mol/Å force

# --- Link-Atom <-> boundary-atom matching validation (--coord-order pdb) ---
# The NAMD QM/MM input file carries only element + xyz for QM/link atoms (no
# atom serial numbers), so a Link Atom is matched to its PDB-identified
# parent boundary atom by nearest Cartesian distance. This is the maximum
# acceptable distance (Å) for that match; NAMD places Link Atoms along the
# cut bond (~1.0-1.1 Å for a capping C-H), so this gives headroom for
# stretched bonds while still catching a genuine mis-assignment.
LINK_ATOM_MAX_PARENT_DIST = 1.15  # Angstrom


# ---------------------------------------------------------------------------
# Command-line interface — every per-run tunable, all with defaults that
# reproduce this script's original fixed-constant behavior if nothing is
# overridden. Pass overrides on NAMD's QMExecPath line (see module
# docstring) instead of editing this file.
# ---------------------------------------------------------------------------

def build_arg_parser():
    p = argparse.ArgumentParser(
        description="TURBOMOLE-NAMD QM/MM interface. All settings below "
                     "are optional flags with working defaults — override "
                     "them from NAMD's QMExecPath line, not by editing "
                     "this file. Every flag also has a QM_* environment "
                     "variable fallback (see each flag's help) so it can be "
                     "omitted from QMExecPath entirely and set once via "
                     "Tcl's `env` array instead — an explicit flag always "
                     "wins over its environment variable."
    )
    p.add_argument('input_file',
                    help="NAMD QM/MM input file (NAMD appends this automatically)")
    p.add_argument('--scf-cmd', default=os.environ.get('QM_SCF_CMD', 'ridft'),
                    help="TURBOMOLE SCF executable, e.g. ridft or dscf. Falls back "
                         "to $QM_SCF_CMD, then 'ridft'.")
    p.add_argument('--grad-cmd', default=os.environ.get('QM_GRAD_CMD', 'rdgrad'),
                    help="TURBOMOLE gradient executable, e.g. rdgrad or ricc2. Falls "
                         "back to $QM_GRAD_CMD, then 'rdgrad'.")
    p.add_argument('--scf-log', default=os.environ.get('QM_SCF_LOG', 'ridft.log'),
                    help="SCF log filename, used for archiving & Mulliken parsing. "
                         "Falls back to $QM_SCF_LOG, then 'ridft.log'.")
    p.add_argument('--grad-log', default=os.environ.get('QM_GRAD_LOG', 'rdgrad.log'),
                    help="Gradient log filename. Falls back to $QM_GRAD_LOG, then "
                         "'rdgrad.log'.")
    p.add_argument('--run-dir', default=os.environ.get('QM_RUN_DIR'),
                    help="Base directory for resolving --pdb-file when given as "
                         "a relative path (e.g. pass NAMD's own "
                         "$rundir/$env(RUNDIR) Tcl variable here so --pdb-file "
                         "can be a bare filename instead of a full path). An "
                         "absolute --pdb-file value ignores this. Falls back to "
                         "$QM_RUN_DIR if not given explicitly.")
    p.add_argument('--pdb-file', default=os.environ.get('QM_PDB_FILE'),
                    help="Path to qm-sel.pdb (the same file given as NAMD's own "
                         "qmParamPDB), used only for --coord-order auto/pdb to "
                         "identify Link Atom parents. Falls back to the "
                         "QM_PDB_FILE environment variable if not given "
                         "explicitly — Tcl's `env` array propagates to child "
                         "processes, so `set env(QM_PDB_FILE) \"qm-sel.pdb\"` in "
                         "the .conf means this flag can be left off the "
                         "QMExecPath line entirely (an explicit --pdb-file still "
                         "overrides it). A relative path (from either source) is "
                         "resolved against --run-dir if given, else this "
                         "script's working directory at invocation time — an "
                         "absolute path is safest.")
    p.add_argument('--charge-mode', '--QMChargeMode', dest='charge_mode',
                    default=os.environ.get('QM_CHARGE_MODE', 'mulliken'),
                    help="QM/link atom charge column in .result — mirrors NAMD's own "
                         "QMChargeMode parameter (same accepted values, same default): "
                         "'none' writes 0.0 for every atom (original force-field charges "
                         "kept on NAMD's side); 'mulliken' (default, matches NAMD's own "
                         "default) parses TURBOMOLE's Mulliken charges from the SCF log — "
                         "NAMD's docs specify MULLIKEN as the correct choice for any "
                         "custom QM software interface, regardless of the level of theory "
                         "actually used. 'chelpg' is an ORCA-only option in NAMD and is "
                         "NOT supported here — passing it raises a hard error rather than "
                         "silently substituting something else. Matched case-insensitively, "
                         "so you can pass NAMD's own QMChargeMode Tcl variable as-is. Falls "
                         "back to $QM_CHARGE_MODE, then 'mulliken', if not given explicitly.")
    p.add_argument('--coord-order', default=os.environ.get('QM_COORD_ORDER', 'auto'),
                    help="Atom order used when writing TURBOMOLE's coord file "
                         "(must match the prepared TURBOMOLE input). Accepts "
                         "'auto'/'namd'/'pdb', matched case-insensitively. 'auto' "
                         "(default, no flag needed in normal use) uses PDB-based "
                         "Link Atom placement whenever --pdb-file is resolvable, "
                         "and silently falls back to NAMD's original order "
                         "otherwise. 'namd' "
                         "forces the original order even if a PDB IS available. "
                         "'pdb' forces PDB-based placement and prints a WARNING "
                         "(falling back to namd order) if the PDB can't be "
                         "resolved/parsed, instead of silently accepting that. "
                         "The .result file is always written back in NAMD's "
                         "original order regardless of this setting. Falls back "
                         "to $QM_COORD_ORDER, then 'auto', if not given explicitly.")
    p.add_argument('--input-dir-tmpl',
                    default=os.environ.get('QM_INPUT_DIR_TMPL', 'input_{n}'),
                    help="Staging dir name template for initial TURBOMOLE files, "
                         "{n} = 1-based QM region index. Falls back to "
                         "$QM_INPUT_DIR_TMPL, then 'input_{n}'.")
    p.add_argument('--output-dir-tmpl',
                    default=os.environ.get('QM_OUTPUT_DIR_TMPL', 'output_{n}'),
                    help="Wavefunction-restart archive dir template. Falls back to "
                         "$QM_OUTPUT_DIR_TMPL, then 'output_{n}'.")
    p.add_argument('--results-dir-tmpl',
                    default=os.environ.get('QM_RESULTS_DIR_TMPL', 'results_{n}'),
                    help="Per-step results archive dir template. Falls back to "
                         "$QM_RESULTS_DIR_TMPL, then 'results_{n}'.")
    return p


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def resolve_path(path, base_dir):
    """Resolve `path` to an absolute path. If `path` is already absolute,
    it's returned as-is. If relative and `base_dir` is given, it's resolved
    against `base_dir` (e.g. --run-dir). If relative and no base_dir is
    given, it's resolved against the current working directory."""
    if not path:
        return None
    if os.path.isabs(path):
        return path
    if base_dir:
        return os.path.join(base_dir, path)
    return os.path.abspath(path)


def load_step(exec_dir):
    step_file = os.path.join(exec_dir, STEP_FILE)
    try:
        with open(step_file, 'r') as f:
            return int(f.read().strip())
    except IOError as e:
        if e.errno == errno.ENOENT:
            return 0
        raise


def save_step(exec_dir, step):
    step_file = os.path.join(exec_dir, STEP_FILE)
    with open(step_file, 'w') as f:
        f.write(str(step))


# ---------------------------------------------------------------------------
# NAMD input parsing
# ---------------------------------------------------------------------------

def parse_namd_input(input_filepath):
    """
    Parse NAMD QM/MM input file.

    NAMD format:
        first line:
            <num_qm> <num_pc>

        followed by:
            num_qm QM/link atoms
            num_pc MM point charges

    IMPORTANT:
        Do NOT merge point charges at identical coordinates.

        Every point charge supplied by NAMD is preserved as an
        independent point charge. This is important for reproducing
        the exact NAMD QM/MM electrostatic environment.

    NOTE ON ORDER: the QM/link atoms are kept in exactly the order NAMD
    delivered them. TURBOMOLE preserves atom order in its $grad output, so
    this same order is used throughout (writing coord, then reading the
    gradient back) with no reordering step in between.
    """

    qm_atoms = []
    point_charges = []

    with open(input_filepath, 'r') as f:

        first_line = f.readline().split()

        if len(first_line) < 2:
            raise ValueError(
                f"Invalid first line in NAMD input file: {first_line}"
            )

        num_qm = int(first_line[0])
        num_pc = int(first_line[1])

        line_count = 0

        for line in f:

            toks = line.split()

            if not toks:
                continue

            if len(toks) < 4:
                continue

            x = float(toks[0])
            y = float(toks[1])
            z = float(toks[2])
            val = toks[3]

            line_count += 1

            # ------------------------------------------------------
            # QM + link atoms
            # ------------------------------------------------------

            if line_count <= num_qm:

                qm_atoms.append({
                    'element': val.lower(),
                    'x':       x,
                    'y':       y,
                    'z':       z
                })

            # ------------------------------------------------------
            # MM point charges
            # ------------------------------------------------------

            else:

                charge = float(val)

                # IMPORTANT:
                # Preserve EVERY point charge independently.
                point_charges.append({
                    'q': charge,
                    'x': x,
                    'y': y,
                    'z': z
                })

    # --------------------------------------------------------------
    # Sanity checks
    # --------------------------------------------------------------

    expected_lines = num_qm + num_pc

    if line_count != expected_lines:
        raise RuntimeError(
            f"NAMD input atom count mismatch:\n"
            f"  Header says: {expected_lines} "
            f"({num_qm} QM + {num_pc} PC)\n"
            f"  Actually read: {line_count}"
        )

    if len(qm_atoms) != num_qm:
        raise RuntimeError(
            f"QM atom count mismatch:\n"
            f"  Expected: {num_qm}\n"
            f"  Read:     {len(qm_atoms)}"
        )

    if len(point_charges) != num_pc:
        raise RuntimeError(
            f"Point-charge count mismatch:\n"
            f"  Expected: {num_pc}\n"
            f"  Read:     {len(point_charges)}"
        )

    print(
        f"NAMD QM/MM input parsed successfully:\n"
        f"  QM/link atoms    = {len(qm_atoms)}\n"
        f"  Point charges    = {len(point_charges)}\n"
        f"  Total atoms/PCs  = {line_count}"
    )

    return qm_atoms, point_charges, num_qm, num_pc


# ---------------------------------------------------------------------------
# TURBOMOLE file I/O
# ---------------------------------------------------------------------------

def parse_qm_sel_pdb(pdb_filepath):
    """
    Parse qm-sel.pdb for Beta/Occ flags identifying QM boundary atoms.

    PDB flag convention (fixed-width columns, 1-indexed):
        Beta == 1.00 & Occ == 0.00 : normal QM atom
        Beta == 1.00 & Occ == 1.00 : QM boundary atom (bonded to a Link Atom)
        (anything else)            : MM atom, not part of the QM region

    Returns:
        num_qm_pdb : count of atoms with Beta == 1.00 (real QM atoms,
                     including boundary atoms — excludes Link Atoms, which
                     are not in the PDB at all since NAMD appends them).
        num_link   : count of atoms with Beta == 1.00 & Occ == 1.00
                     (one boundary atom per Link Atom NAMD will append).
    """
    num_qm_pdb = 0
    num_link = 0
    with open(pdb_filepath, 'r') as f:
        for line in f:
            if not (line.startswith('ATOM') or line.startswith('HETATM')):
                continue
            try:
                occupancy = float(line[54:60])
                beta      = float(line[60:66])
            except (ValueError, IndexError):
                continue
            if abs(beta - 1.00) < 1e-3:
                num_qm_pdb += 1
                if abs(occupancy - 1.00) < 1e-3:
                    num_link += 1
    return num_qm_pdb, num_link


def dist3(a, b):
    return math.sqrt((a['x'] - b['x'])**2 + (a['y'] - b['y'])**2 + (a['z'] - b['z'])**2)


def reorder_qm_atoms_by_pdb(qm_atoms, num_link):
    """
    Reorder QM/link atoms to match a prepared coord convention: each Link
    Atom (which NAMD always appends at the very end of the QM/link list) is
    moved to sit right after the real QM atom it's bonded to. Every OTHER
    atom keeps its exact original relative order from NAMD — nothing else
    is touched, so e.g. a metal cluster's already-sensible order (as
    delivered by NAMD) is never disturbed.

    Matching method: the NAMD QM/MM input file carries only element + xyz
    for each QM/link atom (no atom serial numbers), so a Link Atom is
    matched to its parent by nearest Cartesian distance among the real QM
    atoms. This is validated before being trusted:
        - the distance must be <= LINK_ATOM_MAX_PARENT_DIST, and
        - each real QM atom may be the parent of at most one Link Atom.
    Either violation raises, so a bad match can never silently produce a
    corrupted (but not visibly wrong) coord file.

    Returns `order`: a list of length len(qm_atoms) where order[i] is the
    index into the ORIGINAL qm_atoms list (NAMD's order) of the atom
    placed at position i of the reordered list. Use restore_original_order
    with this same list to map TURBOMOLE's results back to NAMD's order.
    """
    n = len(qm_atoms)
    if num_link == 0 or n == 0:
        return list(range(n))

    if num_link >= n:
        raise RuntimeError(
            f"Number of expected Link Atoms from the PDB ({num_link}) is >= "
            f"the total QM/link atoms delivered by NAMD ({n}). Check that "
            f"qmParamPDB matches the QM selection in the .conf file."
        )

    real_qm_idx  = list(range(n - num_link))
    link_idx     = list(range(n - num_link, n))

    parent_of_link = {}
    for li in link_idx:
        la = qm_atoms[li]
        best_ri, best_d = None, float('inf')
        for ri in real_qm_idx:
            d = dist3(la, qm_atoms[ri])
            if d < best_d:
                best_d, best_ri = d, ri
        if best_d > LINK_ATOM_MAX_PARENT_DIST:
            raise RuntimeError(
                f"Link Atom at ({la['x']:.3f}, {la['y']:.3f}, {la['z']:.3f}) has "
                f"no real QM atom within {LINK_ATOM_MAX_PARENT_DIST:.2f} A "
                f"(closest = {best_d:.3f} A). Nearest-neighbor Link Atom <-> "
                f"parent matching is unreliable here; aborting --coord-order "
                f"pdb rather than risk a misleading coord file."
            )
        parent_of_link[li] = best_ri

    if len(set(parent_of_link.values())) != len(parent_of_link):
        raise RuntimeError(
            "Two or more Link Atoms were matched to the same QM boundary atom "
            "by nearest-neighbor distance (ambiguous/overlapping boundary "
            "geometry); aborting --coord-order pdb rather than risk a "
            "misleading coord file."
        )

    links_by_parent = {}
    for li, ri in parent_of_link.items():
        links_by_parent.setdefault(ri, []).append(li)

    order = []
    for ri in real_qm_idx:
        order.append(ri)
        order.extend(links_by_parent.get(ri, []))

    return order


def validate_order_permutation(order, expected_n):
    """Verify `order` (however it was produced — identity or
    reorder_qm_atoms_by_pdb) is a genuine permutation of range(expected_n):
    right length, every index 0..expected_n-1 present exactly once. This is
    what BOTH write_turbomole_coord and restore_original_order silently
    depend on being true; checking it explicitly here means a bug in the
    reordering logic is caught immediately with a clear message, instead of
    surfacing later as a subtly wrong or missing atom in the .result file."""
    if len(order) != expected_n:
        raise RuntimeError(
            f"Internal error: atom reorder produced {len(order)} positions, "
            f"expected {expected_n}. Refusing to write a coord file or map "
            f"results back with a corrupted ordering."
        )
    if sorted(order) != list(range(expected_n)):
        raise RuntimeError(
            f"Internal error: atom reorder is not a valid permutation of "
            f"0..{expected_n - 1} (duplicate and/or missing indices). "
            f"Refusing to write a coord file or map results back with a "
            f"corrupted ordering."
        )


def verify_coord_atom_count(coord_filepath, expected_n):
    """Re-read the just-written coord file and verify it actually contains
    exactly expected_n atom lines — a self-check on our own write, so a
    mismatch between the declared and written atom counts is caught immediately with a
    clear reason, rather than surfacing later as a confusing TURBOMOLE
    error or, worse, a silently wrong result."""
    with open(coord_filepath, 'r') as f:
        atom_lines = [
            line for line in f
            if line.strip() and not line.strip().startswith('$')
        ]
    if len(atom_lines) != expected_n:
        raise RuntimeError(
            f"Coord file atom count mismatch: NAMD declared {expected_n} "
            f"QM/link atoms, but {coord_filepath} actually contains "
            f"{len(atom_lines)} atom lines. Refusing to run TURBOMOLE "
            f"against a coord file that doesn't match what NAMD sent."
        )


def restore_original_order(values_in_coord_order, order):
    """Scatter a per-atom list that's in 'coord order' (aligned with
    `order`, as returned by reorder_qm_atoms_by_pdb or the identity order)
    back into NAMD's original QM/link atom order. order[i] is the
    original NAMD index of the atom that was written at position i of
    coord — so this works identically (as a no-op) when order is the
    identity permutation, i.e. when --coord-order namd was used."""
    if len(values_in_coord_order) != len(order):
        raise RuntimeError(
            f"Internal error: {len(values_in_coord_order)} per-atom values "
            f"to restore, but the atom order has {len(order)} entries. "
            f"Refusing to write a .result file with a mismatched mapping."
        )
    result = [None] * len(order)
    for pos, orig_idx in enumerate(order):
        result[orig_idx] = values_in_coord_order[pos]
    return result


def write_turbomole_coord(coord_filepath, qm_atoms):
    """Write QM/link atoms to TURBOMOLE's $coord format, in the exact order
    given (see parse_namd_input's note on order, and reorder_qm_atoms_by_pdb
    for the optional atom reordering)."""
    lines = ["$coord\n"]
    for atom in qm_atoms:
        x_bohr = atom['x'] * ANG_TO_BOHR
        y_bohr = atom['y'] * ANG_TO_BOHR
        z_bohr = atom['z'] * ANG_TO_BOHR
        lines.append(f"{x_bohr:20.14f}  {y_bohr:20.14f}  {z_bohr:20.14f}  {atom['element']}\n")
    lines.append("$end\n")
    with open(coord_filepath, 'w') as f:
        f.writelines(lines)


def _turbomole_charge(charge):
    """Return the charge exactly as it will be represented in point_charges."""
    return float(f"{charge:.8f}")


def prepare_turbomole_point_charges(point_charges):
    """Filter zero charges and merge co-located charges for TURBOMOLE.

    TURBOMOLE omits exact-zero charges and coalesces coincident charges in its
    pc_gradient output.  Keep a mapping so its gradients can be expanded back
    to NAMD's original point-charge order.
    """
    groups = {}
    force_mapping = [None] * len(point_charges)

    for index, pc in enumerate(point_charges):
        charge = _turbomole_charge(pc['q'])
        if charge == 0.0:
            continue

        key = (pc['x'], pc['y'], pc['z'])
        groups.setdefault(key, []).append((index, charge))

    turbomole_charges = []
    for key, members in groups.items():
        total_charge = _turbomole_charge(sum(charge for _, charge in members))
        if total_charge == 0.0:
            raise RuntimeError(
                "Coincident non-zero point charges cancel after TURBOMOLE "
                "formatting; cannot recover their individual forces."
            )

        tm_index = len(turbomole_charges)
        turbomole_charges.append({
            'x': key[0], 'y': key[1], 'z': key[2], 'q': total_charge
        })
        for original_index, charge in members:
            force_mapping[original_index] = (tm_index, charge / total_charge)

    return turbomole_charges, force_mapping


def write_turbomole_point_charges(pc_filepath, point_charges):
    """Write TURBOMOLE-compatible point charges and return the force mapping."""
    turbomole_charges, force_mapping = prepare_turbomole_point_charges(point_charges)
    lines = ["$point_charges\n"]
    for pc in turbomole_charges:
        x_bohr = pc['x'] * ANG_TO_BOHR
        y_bohr = pc['y'] * ANG_TO_BOHR
        z_bohr = pc['z'] * ANG_TO_BOHR
        lines.append(f"{x_bohr:20.14f}  {y_bohr:20.14f}  {z_bohr:20.14f}  {pc['q']:16.8f}\n")
    lines.append("$end\n")
    with open(pc_filepath, 'w') as f:
        f.writelines(lines)
    return turbomole_charges, force_mapping


# ---------------------------------------------------------------------------
# Parsing Turbomole output
# ---------------------------------------------------------------------------

def parse_turbomole_gradient(gradient_filepath, num_qm_atoms):
    """
    Parse TURBOMOLE's $grad file for the final ('cycle =') block.

    IMPORTANT — actual TURBOMOLE $grad layout (verified against real output):
        $grad          cartesian gradients
          cycle =   1   SCF energy = ...
          <x y z element>      <- coordinate line, atom 1
          <x y z element>      <- coordinate line, atom 2
          ...                     (num_qm_atoms coordinate lines total)
          <dE/dx dE/dy dE/dz>  <- gradient line, atom 1
          <dE/dx dE/dy dE/dz>  <- gradient line, atom 2
          ...                     (num_qm_atoms gradient lines total)
        $end

    The coordinate lines and gradient lines are each a single contiguous
    block of num_qm_atoms lines — they are NOT interleaved atom-by-atom.

    Returned forces are in the SAME order atoms were written to `coord`
    (i.e. `order` from main(), not necessarily NAMD's original order) —
    the caller is responsible for mapping back to NAMD's order via
    restore_original_order when --coord-order reordered anything.
    """
    if not os.path.exists(gradient_filepath):
        raise FileNotFoundError(f"Turbomole gradient file not found: {gradient_filepath}")

    with open(gradient_filepath, 'r') as f:
        lines = f.readlines()

    cycle_indices = [i for i, l in enumerate(lines) if 'cycle =' in l]
    if not cycle_indices:
        raise RuntimeError("No 'cycle =' block found in Turbomole gradient file.")

    last_cycle_line = lines[cycle_indices[-1]]
    m = re.search(r'energy\s*=\s*([+-]?\d+\.\d+(?:[DdEe][+-]?\d+)?)', last_cycle_line)
    if not m:
        raise RuntimeError(f"Could not parse energy from: {last_cycle_line}")

    energy_hartree = float(m.group(1).replace('D', 'E').replace('d', 'e'))

    coord_block_start = cycle_indices[-1] + 1
    grad_block_start  = coord_block_start + num_qm_atoms
    grad_block_end    = grad_block_start + num_qm_atoms

    if grad_block_end > len(lines):
        raise RuntimeError(
            f"Truncated Turbomole gradient file: expected {num_qm_atoms} "
            f"coordinate lines followed by {num_qm_atoms} gradient lines "
            f"after the 'cycle =' line, but the file has only "
            f"{len(lines) - coord_block_start} lines remaining."
        )

    forces = []
    for line in lines[grad_block_start:grad_block_end]:
        grad_toks = line.strip().split()
        if len(grad_toks) < 3:
            raise RuntimeError(f"Malformed Turbomole gradient line: {line!r}")
        gx = float(grad_toks[0].replace('D', 'E').replace('d', 'e'))
        gy = float(grad_toks[1].replace('D', 'E').replace('d', 'e'))
        gz = float(grad_toks[2].replace('D', 'E').replace('d', 'e'))
        forces.append([gx * GRAD_TO_NAMD_FORCE,
                       gy * GRAD_TO_NAMD_FORCE,
                       gz * GRAD_TO_NAMD_FORCE])

    if len(forces) != num_qm_atoms:
        raise RuntimeError(f"Expected {num_qm_atoms} gradients, got {len(forces)}.")

    return energy_hartree, forces


def parse_turbomole_pc_gradient(gradient_filepath, num_point_charges):
    """Read TURBOMOLE pc_gradient and convert gradients to NAMD forces."""
    if num_point_charges == 0:
        return []
    if not os.path.exists(gradient_filepath):
        raise FileNotFoundError(f"Turbomole point-charge gradient file not found: {gradient_filepath}")

    gradients = []
    in_block = False
    with open(gradient_filepath, 'r') as f:
        for line in f:
            stripped = line.strip()
            if stripped == '$point_charge_gradients':
                in_block = True
                continue
            if in_block and stripped == '$end':
                break
            if not in_block or not stripped:
                continue

            toks = stripped.split()
            if len(toks) != 3:
                raise RuntimeError(f"Invalid point-charge gradient line: {line.rstrip()}")
            gradients.append([
                float(toks[0].replace('D', 'E').replace('d', 'e')) * GRAD_TO_NAMD_FORCE,
                float(toks[1].replace('D', 'E').replace('d', 'e')) * GRAD_TO_NAMD_FORCE,
                float(toks[2].replace('D', 'E').replace('d', 'e')) * GRAD_TO_NAMD_FORCE,
            ])

    if len(gradients) != num_point_charges:
        raise RuntimeError(
            f"Expected {num_point_charges} TURBOMOLE point-charge gradients, "
            f"got {len(gradients)}."
        )
    return gradients


def expand_point_charge_forces(turbomole_forces, force_mapping):
    """Restore NAMD's original point-charge order, including zero-charge rows."""
    forces = [[0.0, 0.0, 0.0] for _ in force_mapping]
    for index, mapping in enumerate(force_mapping):
        if mapping is None:
            continue
        tm_index, weight = mapping
        forces[index] = [component * weight for component in turbomole_forces[tm_index]]
    return forces


def write_namd_result(result_filepath, energy_kcalmol, qm_forces, qm_charges, pc_forces):
    """Write the complete result contract required by NAMD's custom QM API."""
    if len(qm_forces) != len(qm_charges):
        raise ValueError("QM force and charge counts do not match.")

    with open(result_filepath, 'w') as f:
        f.write(f"{energy_kcalmol:.10f} {len(pc_forces)}\n")
        for force, charge in zip(qm_forces, qm_charges):
            fx, fy, fz = force
            f.write(f"{fx:18.10f} {fy:18.10f} {fz:18.10f} {charge:12.6f}\n")
        for fx, fy, fz in pc_forces:
            f.write(f"{fx:18.10f} {fy:18.10f} {fz:18.10f}\n")


def parse_turbomole_charges(log_filepath, num_qm_atoms):
    """Parse Mulliken atomic charges from a TURBOMOLE SCF log. Returned in
    the SAME order atoms were written to `coord` (i.e. `order` from
    main()) — the caller is responsible for mapping back to NAMD's order
    via restore_original_order when --coord-order reordered anything."""
    if not os.path.exists(log_filepath):
        raise FileNotFoundError(f"SCF log required for Mulliken charges: {log_filepath}")

    with open(log_filepath, 'r') as f:
        lines = f.readlines()

    header_found = False
    parsed = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^atom\s+charge\b', stripped, re.IGNORECASE):
            header_found = True
            continue
        if not header_found:
            continue
        if not stripped or stripped.lower().startswith('moments'):
            if parsed:
                break
            continue

        match = re.match(
            r'^\s*\d+[A-Za-z]+\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?)\b',
            line,
        )
        if match:
            parsed.append(float(match.group(1).replace('D', 'E').replace('d', 'e')))

    if len(parsed) == num_qm_atoms:
        return parsed

    raise RuntimeError(
        f"Could not parse all Mulliken charges from {log_filepath} "
        f"(found {len(parsed)}, expected {num_qm_atoms}). "
        "Enable population analysis ($pop) and check the SCF log. "
        "Refusing to substitute zero charges."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = build_arg_parser().parse_args()

    charge_mode = args.charge_mode.strip().lower()
    if charge_mode == 'chelpg':
        raise RuntimeError(
            "--charge-mode/--QMChargeMode 'CHELPG' is an ORCA-only option in "
            "NAMD; it has no meaning for this TURBOMOLE interface. NAMD's own "
            "docs specify MULLIKEN as the correct choice for any custom QM "
            "software interface. Use --charge-mode mulliken or --charge-mode "
            "none instead."
        )
    if charge_mode not in ('none', 'mulliken'):
        raise RuntimeError(
            f"Unrecognized --charge-mode/--QMChargeMode value "
            f"{args.charge_mode!r} (expected 'none' or 'MULLIKEN', matched "
            f"case-insensitively). Refusing to guess — this setting changes "
            f"real data written back to NAMD, so a misspelled value is not "
            f"silently treated as 'none'."
        )

    coord_order = args.coord_order.strip().lower()
    if coord_order not in ('auto', 'namd', 'pdb'):
        raise RuntimeError(
            f"Unrecognized --coord-order value {args.coord_order!r} "
            f"(expected 'auto', 'namd', or 'pdb', matched case-insensitively)."
        )

    # pdb_filepath: only source now is --pdb-file (resolved against
    # --run-dir if relative). Only ever used for --coord-order auto/pdb below.
    pdb_filepath = resolve_path(args.pdb_file, args.run_dir) if args.pdb_file else None

    input_filepath   = args.input_file
    exec_dir         = os.path.dirname(os.path.abspath(input_filepath))  # turbo-exec/0
    parent_exec_dir  = os.path.dirname(exec_dir)                          # turbo-exec

    exec_folder_name = os.path.basename(exec_dir)
    try:
        region_idx = int(exec_folder_name) + 1
    except ValueError:
        region_idx = 1

    input_n_dir   = os.path.join(parent_exec_dir, args.input_dir_tmpl.format(n=region_idx))
    output_n_dir  = os.path.join(parent_exec_dir, args.output_dir_tmpl.format(n=region_idx))
    results_n_dir = os.path.join(parent_exec_dir, args.results_dir_tmpl.format(n=region_idx))

    os.makedirs(output_n_dir,  exist_ok=True)
    os.makedirs(results_n_dir, exist_ok=True)

    # Files to archive into results_n_dir/ after each step.
    # Tuple format: (filename_in_exec_dir, archive_name_template); {a} -> step number.
    files_to_save = [
        (args.scf_log,      'ridft{a}'),
        #(args.grad_log,     'rdgrad{a}'),
        #(GRADIENT_FILE,     'gradient{a}'),
        #(PC_GRADIENT_FILE,  'pc_gradient{a}'),
        #(ENERGY_FILE,       'energy{a}'),
        #(COORD_FILE,        'coord{a}'),
        #(POINT_CHARGE_FILE, 'point_charges{a}'),
        #('alpha',           'alpha{a}'),
        #('beta',            'beta{a}'),
        #('control',         'control{a}'),
    ]

    step = load_step(exec_dir)

    # ------------------------------------------------------------------
    # Parse NAMD input & check point charges
    # ------------------------------------------------------------------
    qm_atoms, point_charges, num_qm, num_pc = parse_namd_input(input_filepath)

    if len(point_charges) == 0:
        print(
            f"ERROR: No MM point charges received from NAMD (num_pc = {num_pc}).\n"
            f"QM/MM electrostatic embedding requires point charges.\n"
            f"Check QMElecEmbed and QMPointChargeScheme in your NAMD configuration.",
            file=sys.stderr
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Initialize exec_dir from input_N only when key files are missing
    # (regardless of step number — applies independently to each QM region)
    # ------------------------------------------------------------------
    needs_init = (
        os.path.exists(input_n_dir) and
        not any(os.path.exists(os.path.join(exec_dir, f)) for f in INIT_SENTINEL_FILES)
    )
    if needs_init:
        print(f"[Region {region_idx}] No TURBOMOLE files found in {exec_dir}, "
              f"initializing from {input_n_dir}")
        for fname in os.listdir(input_n_dir):
            src = os.path.join(input_n_dir, fname)
            dst = os.path.join(exec_dir, fname)
            if os.path.isfile(src):
                shutil.copyfile(src, dst)

    # Always write coord from NAMD coordinates (never use the template coord).
    # `order[i]` = original NAMD index of the atom placed at coord position i
    # (identity permutation when no reorder happens). Reused below to map
    # TURBOMOLE's per-atom results back to NAMD's original order.
    order = list(range(num_qm))
    if coord_order == 'namd':
        pass  # explicit: never reorder, even if a PDB is available
    elif coord_order in ('auto', 'pdb'):  # the only remaining choices
        # 'pdb' warns loudly if it can't do what was explicitly asked for;
        # 'auto' just falls back silently since no PDB was ever promised.
        loud = (coord_order == 'pdb')
        if not pdb_filepath:
            if loud:
                print(
                    "WARNING: --coord-order pdb requires --pdb-file to be "
                    "given; falling back to NAMD's original order.",
                    file=sys.stderr
                )
        elif not os.path.exists(pdb_filepath):
            if loud:
                print(
                    f"WARNING: PDB file not found ({pdb_filepath!r}); "
                    f"falling back to NAMD's original order.",
                    file=sys.stderr
                )
        else:
            num_qm_pdb, num_link = parse_qm_sel_pdb(pdb_filepath)
            expected_real_qm = num_qm - num_link
            if num_qm_pdb != expected_real_qm:
                if loud:
                    print(
                        f"WARNING: qm-sel.pdb reports {num_qm_pdb} real QM atoms "
                        f"(Beta=1.00), but NAMD's {num_qm} QM/link atoms minus "
                        f"{num_link} expected Link Atoms gives {expected_real_qm}. "
                        f"Falling back to NAMD's original order rather than risk "
                        f"a wrong reorder.",
                        file=sys.stderr
                    )
            else:
                try:
                    order = reorder_qm_atoms_by_pdb(qm_atoms, num_link)
                except RuntimeError as exc:
                    if loud:
                        print(
                            f"WARNING: {exc} Falling back to NAMD's original order.",
                            file=sys.stderr
                        )
                    order = list(range(num_qm))
    # Sanity-check the reorder itself before trusting it for anything: must
    # be a genuine permutation of every QM/link atom NAMD sent, whether it
    # came from reorder_qm_atoms_by_pdb or is just the identity order.
    validate_order_permutation(order, num_qm)
    ordered_qm_atoms = [qm_atoms[i] for i in order]

    coord_file = os.path.join(exec_dir, COORD_FILE)
    write_turbomole_coord(coord_file, ordered_qm_atoms)
    # Re-read what was actually written and confirm the atom count matches
    # what NAMD declared (num_qm) — catches a write-time inconsistency
    # before TURBOMOLE ever runs on it.
    verify_coord_atom_count(coord_file, num_qm)

    # Write point_charges.  The mapping restores TURBOMOLE's compacted
    # pc_gradient output to NAMD's original point-charge order.
    pc_file = os.path.join(exec_dir, POINT_CHARGE_FILE)
    turbomole_charges, pc_force_mapping = write_turbomole_point_charges(
        pc_file, point_charges
    )

    # Remove stale outputs so a failed/aborted TURBOMOLE run can never leave
    # behind results from a previous geometry for the parser to pick up.
    for old_file in [GRADIENT_FILE, ENERGY_FILE, PC_GRADIENT_FILE]:
        p = os.path.join(exec_dir, old_file)
        if os.path.exists(p):
            os.remove(p)

    # ------------------------------------------------------------------
    # Run TURBOMOLE
    # ------------------------------------------------------------------
    dscf_log_path = os.path.join(exec_dir, args.scf_log)
    grad_log_path = os.path.join(exec_dir, args.grad_log)

    def run_turbomole(cmd, log_path):
        """Run a TURBOMOLE executable, aborting loudly on a non-zero exit
        code instead of silently letting a failed step reach the results
        parser (which would otherwise fail later with a confusing,
        unrelated-looking error, or in the worst case parse a leftover file
        from a previous step). Inherits the calling environment as-is
        (e.g. PARNODES/SMPCPUS set by a SLURM job script for SMP-enabled
        TURBOMOLE builds, or any TURBOMOLE core-count/parallelization
        configuration) — this script never sets or overrides any of that
        itself."""
        try:
            with open(log_path, 'w') as log:
                result = sp.run([cmd], cwd=exec_dir, stdout=log, stderr=sp.STDOUT)
        except FileNotFoundError:
            raise RuntimeError(
                f"TURBOMOLE executable '{cmd}' not found. Check that "
                f"TURBOMOLE is on PATH, or pass a full path via "
                f"--scf-cmd/--grad-cmd on the QMExecPath line."
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"TURBOMOLE executable '{cmd}' exited with code "
                f"{result.returncode}. See {log_path} for details."
            )

    run_turbomole(args.scf_cmd,  dscf_log_path)
    run_turbomole(args.grad_cmd, grad_log_path)

    # ------------------------------------------------------------------
    # Parse results & write NAMD .result
    # ------------------------------------------------------------------
    gradient_file = os.path.join(exec_dir, GRADIENT_FILE)
    energy_hartree, forces_coord_order = parse_turbomole_gradient(gradient_file, num_qm)
    energy_kcalmol = energy_hartree * HARTREE_TO_KCALMOL
    # forces_coord_order[i] is the force on the atom written at coord position
    # i; scatter back to NAMD's original atom order (no-op when order is
    # identity, i.e. --coord-order namd).
    forces = restore_original_order(forces_coord_order, order)

    if charge_mode == 'mulliken':
        qm_charges_coord_order = parse_turbomole_charges(dscf_log_path, num_qm)
        qm_charges = restore_original_order(qm_charges_coord_order, order)
    else:
        qm_charges = [0.0] * num_qm

    pc_gradient_file = os.path.join(exec_dir, PC_GRADIENT_FILE)
    turbomole_pc_forces = parse_turbomole_pc_gradient(
        pc_gradient_file, len(turbomole_charges)
    )
    pc_forces = expand_point_charge_forces(turbomole_pc_forces, pc_force_mapping)

    result_filepath = input_filepath + ".result"
    write_namd_result(result_filepath, energy_kcalmol, forces, qm_charges, pc_forces)

    # ------------------------------------------------------------------
    # Archive outputs
    # ------------------------------------------------------------------
    for fname in OUTPUT_FILES:
        src = os.path.join(exec_dir, fname)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(output_n_dir, fname))

    for src_name, dst_template in files_to_save:
        src = os.path.join(exec_dir, src_name)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(results_n_dir, dst_template.format(a=str(step))))

    save_step(exec_dir, step + 1)
    print(f"[Region {region_idx}] Step {step} complete. Energy: {energy_kcalmol:.6f} kcal/mol")


def cli():
    """Console entry point with a nonzero exit status on failed evaluations."""
    try:
        main()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)



if __name__ == "__main__":
    cli()
