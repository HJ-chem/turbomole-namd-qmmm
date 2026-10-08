# Private calculation setup

These are templates, not a bundled molecular calculation. They contain no
structure, force field, orbital file, or scientific result.

Install the Python package first. In a **new directory outside the checkout**:

```text
calculation/
  Input/
    input.psf             supplied privately
    input.pdb             supplied privately
    selection.tcl         copy and edit this template
    prepare.tcl           copy this script
  mm.conf                 your validated NAMD settings
  qmmm.conf               copy and edit this template
  submit.sh               optional; adapt to the cluster
  turbo-exec/input_1/     prepared electronic input and orbital files
```

`mm.conf` must define the structure, coordinates, force-field parameter files,
nonbonded interactions, boundary conditions, and outputs. It must not execute
`run` or `minimize`. All paths are resolved from the calculation directory.
Set `outputName qmmm` there if using the output names in the tutorial.

1. Replace the `none` selection in `selection.tcl`; define every QM-MM boundary.
2. Run `vmd -dispdev text -e prepare.tcl` from the private `Input` directory.
3. Inspect the generated selections and QM boundary geometry.
4. Build the matching capped QM calculation with TURBOMOLE. The provided NAMD
   template explicitly uses `QM_COORD_ORDER=namd`.
5. Set charge and multiplicity in `qmmm.conf` to match TURBOMOLE occupations.
6. Run the one-step execution check in an appropriate allocation, then inspect
   convergence, forces, charges, and atom mapping before extending the run.

The templates are parsed and their configuration guards are checked in local
tests. Real VMD preparation and NAMD/TURBOMOLE execution require your local
software and inputs; they are not performed by the synthetic test suite.
