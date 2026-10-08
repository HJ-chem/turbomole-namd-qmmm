# External software and data

The MIT license in this repository applies to the interface, documentation,
templates, and original synthetic tests distributed here. It does not grant
rights to NAMD, TURBOMOLE, VMD, TopoTools, force fields, or user-supplied data.

| Dependency | How it is used | Distribution boundary |
|---|---|---|
| [NAMD](https://www.ks.uiuc.edu/Research/namd/) | Calls the custom QM driver and runs the classical calculation | Obtain separately under the applicable NAMD terms |
| [TURBOMOLE](https://www.turbomole.org/) | Evaluates the embedded QM energy and gradients | Obtain a suitable installation and license separately |
| [VMD](https://www.ks.uiuc.edu/Research/vmd/) and [TopoTools](https://www.ks.uiuc.edu/Research/vmd/plugins/topotools/) | Prepare and inspect selections | Obtain separately under their respective terms |
| Force fields and molecular inputs | Define each user's calculation | Supply independently with the necessary permissions |

No executables, external source distributions, force-field libraries, molecular
datasets, orbitals, license files for external programs, or real calculation
outputs are bundled. Generated files can still contain unpublished coordinates
or model information and should stay in the user's calculation directory.

Tests construct artificial text and mock executables in temporary directories.
These files are original protocol fixtures; they are not extracts from a
research calculation and do not represent a validated chemical model.

If third-party source code or data is added later, preserve its notices, document
its origin and license here, and check compatibility before redistributing it.
See [REFERENCES.md](REFERENCES.md) for scholarly citations.
