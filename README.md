# TURBOMOLE–NAMD QM/MM Interface

A Python interface that connects NAMD's custom QM driver to TURBOMOLE `ridft`
and `rdgrad`. It converts coordinates, energies, gradients, and atomic charges
while preserving the order expected by NAMD.

**Status:** development release candidate (`0.1.0.dev0`). The supported workflow
uses one fixed QM region with electrostatic embedding. Synthetic protocol tests
exercise the adapter; they do not establish scientific accuracy or constitute a
real NAMD/TURBOMOLE benchmark.

## Install and try it

Python 3.11 or newer is required. The adapter has no runtime Python dependencies.
From a downloaded or cloned source checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
turbomole-namd --help
python -m unittest discover -s tests -v
```

You can also inspect the command without installing the package:

```bash
python3 turbomole-namd.py --help
```

Keep the source launcher next to `src/`; copying the launcher alone will not work.
For actual calculations, install NAMD, TURBOMOLE, VMD/TopoTools, and the required
force fields separately under their respective terms.

## Set up your own calculation

1. Create a new calculation directory **outside this repository**.
2. Copy the files from [examples/templates](examples/templates) into the layout
   described in [the setup guide](examples/templates/README.md).
3. Edit `selection.tcl`, then run `prepare.tcl` in VMD to generate region flags.
4. Prepare the capped QM model, basis assignments, occupations, and initial
   orbitals in `turbo-exec/input_1`, with the same atom order used by the adapter.
5. Supply a validated `mm.conf`, set the QM charge and multiplicity, and run a
   short validation calculation before a longer simulation.

The template chooses `QM_COORD_ORDER=namd` explicitly. Build the TURBOMOLE input
for that order. Changing atom order requires a matching electronic setup.

See the [full tutorial](docs/tutorial.md) for units, file formats, boundary
handling, restart behavior, and validation. See [validation](docs/validation.md)
for what has and has not been tested.

## Features and scope

- NAMD custom-input parsing and result writing.
- Å/Bohr and Hartree/kcal/mol conversion, including the gradient-to-force sign.
- QM/link-atom force and charge mapping back to NAMD order.
- Zero-charge filtering and coincident-charge force reconstruction.
- SCF/gradient execution, file checks, and restart-file archiving.
- Generic VMD/NAMD/batch templates and tests containing invented data only.

Missing or incomplete Mulliken output is a fatal error when charge feedback is
requested. Pure-QM input without point-charge entries is not supported. Multiple
QM regions, adaptive partitions, arbitrary QM methods, and automatic electronic
state preparation are not validated features.

## Data boundaries

No research structures, trajectories, calculation logs, force-field distributions,
orbital files, credentials, or computational results are distributed. The tests
construct tiny protocol examples independently in temporary directories.

`.gitignore` is a convenience, not a confidentiality guarantee. The source-export
tool uses an explicit [file manifest](RELEASE_FILES.txt). Read the
[release guide](docs/releasing.md) before creating a repository or release.

## Citation

Please cite this interface when it contributes to a publication, and identify the
release or commit used. [CITATION.cff](CITATION.cff) supplies software metadata for
GitHub's citation feature. A repository URL, release version, and DOI should be
added when they actually exist; none is fabricated here.

Also cite the scientific software and methods used in your calculation. See
[REFERENCES.md](REFERENCES.md). Citation is a scholarly request, not an extra
restriction added to the MIT license.

## Author

**Hao Jiang**, Postdoctoral Researcher  
Department of Biochemistry and Biophysics (DBB), Stockholm University, Sweden  
[hao.jiang@dbb.su.se](mailto:hao.jiang@dbb.su.se)

## License and contributions

The interface code, documentation, and original synthetic tests are covered by
the [MIT License](LICENSE). External programs and force fields retain their own
terms; see [THIRD_PARTY.md](THIRD_PARTY.md).

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), and report
sensitive issues privately as described in [SECURITY.md](SECURITY.md).
