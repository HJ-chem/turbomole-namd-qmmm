# Changelog

## Unreleased — 0.1.0.dev0

- Package the interface with an installable `turbomole-namd` command and a source
  launcher. The source launcher requires the adjacent `src` directory.
- Provide an English tutorial, single-region preparation templates, author and
  citation metadata, and an MIT license for the distributed framework.
- Stop with an error when requested Mulliken charge output is missing or
  incomplete. Do not silently replace a failed population analysis with zeroes.
- Remove the previous NAMD result before evaluating a new input, so an SCF
  failure cannot leave the previous geometry's result at the expected pathname.
- Choose `QM_COORD_ORDER=namd` explicitly in the NAMD template. The adapter's
  legacy `auto` default is retained for existing callers; see the tutorial for
  its fallback and geometry assumptions.
- Add synthetic protocol tests, template checks, and an explicit public-file
  manifest with an audited source-export tool.

No real NAMD/TURBOMOLE calculation or scientific benchmark is included in the
automated test results. No stable release or DOI has been assigned.
