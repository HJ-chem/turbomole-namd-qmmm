# Contributing

Use a small branch for each change and explain the behavior it changes. Include
a focused regression test for changes to input parsing, units, force mapping,
charge feedback, or execution failures.

From a source checkout:

```bash
python -m pip install .
python -m unittest discover -s tests -v
python tools/check_release.py
turbomole-namd --help
```

The template checks use `tclsh`; install Tcl to run them locally. Real VMD,
NAMD, and TURBOMOLE calculations are separate validation and require suitable
installations. Do not report a mock-executable test as a scientific benchmark.

Use invented, minimal inputs in tests and reports. Do not submit unpublished
coordinates, topology, atom selections, trajectories, raw calculation logs,
orbital files, personal paths, access tokens, or licensed software distributions.
If an issue needs private discussion, use [SECURITY.md](SECURITY.md).

Update the relevant documentation and `CHANGELOG.md` when behavior changes.
Add each intentionally public file to `RELEASE_FILES.txt`; inspect its content
before doing so. Never add private terms or data to the public audit rules.

Contributions should be compatible with the repository's MIT license and include
appropriate author and third-party credit. Do not add code or data you lack
permission to distribute.
