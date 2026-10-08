# Validation status

This development candidate provides automated checks of the interface contract.
It does not include a real molecular benchmark or establish numerical accuracy
for any scientific application.

## Automated checks

Run `python -m unittest discover -s tests -v` from the repository root.

| Area | Evidence supplied by the tests |
|---|---|
| Input and output | Header/row parsing, result shape, truncated input rejection |
| Units and signs | Å/Bohr conversion; Hartree/kcal/mol conversion; forces as negative gradients |
| Ordering | Link-atom permutation and inverse force/charge mapping |
| Embedding | Zero and coincident charges, force expansion, cancellation and count errors |
| Charge feedback | Complete Mulliken parsing; missing/incomplete analysis fails |
| Execution | Full command-line call using artificial SCF/gradient executables; failed SCF leaves no previous result |
| Templates | Tcl completeness and early selection/electronic-state guards |
| Export | Manifest traversal, symlinks, unlisted files, research-file types, private terms, and binary content |

The mock executables write predetermined numbers. They do not evaluate a
Hamiltonian, run an SCF cycle, or check the physical validity of the model.
Tcl checks do not execute VMD selection or NAMD simulation commands.

The initial local protocol checks use macOS and Python 3.14. A wheel was also
built and installed in a clean Python 3.13 environment, where both installed
entry points were checked with `--help`. The configured GitHub Actions
matrix targets Linux with Python 3.11, 3.13, and 3.14; a workflow definition is not
evidence that these jobs have run. Real-engine compatibility is not certified
for a particular version, operating system, accelerator, or cluster.

## Validation with real software

Before using a new model for production work:

1. Inspect the PSF/PDB alignment, selections, cut bonds, capped geometry, and
   correspondence between NAMD and TURBOMOLE atom order.
2. Confirm method/basis assignments, electron occupations, charge, multiplicity,
   point-charge derivatives, and converged SCF output.
3. Run a short evaluation and compare the energy, QM/link forces, MM point-charge
   forces, and total charge with an independent calculation of the same model.
4. Where appropriate, compare analytic forces with finite differences using the
   same boundary and embedding conventions.
5. Check continuation behavior and, for dynamics, integration stability and
   timestep sensitivity before assessing sampling or scientific conclusions.

Record exact versions, commands, tolerances, and observations. Public validation
should use an independently constructed or suitably licensed public model,
with a script that reproduces it. Permission to use a structure does not
automatically permit redistribution of its force-field parameters.

The current release deliberately supplies configuration templates and synthetic
tests. A fully runnable, real-engine example remains future validation work.
