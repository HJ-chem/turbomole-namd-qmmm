# Preparing a public release

Maintain this source checkout separately from every research calculation. Never
initialize or publish a repository by copying an entire calculation directory.
Coordinates can appear in extensionless flags, topology, restart files, logs,
QM input/output, plots, and orbital files as well as in PDB files.

## Build the public file set

Review `RELEASE_FILES.txt`. It explicitly lists every exported file. The audit
rejects unlisted source files, symlinks, traversal paths, unsupported file types,
binary/large files, selected credentials, personal absolute paths, and undeclared
email contacts. Git history, virtual environments, caches, and build directories
are ignored by the audit and are never exported.

Keep a local list of confidential project names, identifiers, account names,
hostnames, and unusual selection labels **outside the public checkout**. Put one
term per line. Do not commit that list or upload it to CI.

From this checkout:

```bash
python -m unittest discover -s tests -v
python tools/check_release.py --deny-term-file /path/outside/checkout/private-terms.txt
python tools/build_release.py \
    --deny-term-file /path/outside/checkout/private-terms.txt \
    --output ../turbomole-namd-qmmm-source.zip
```

The exporter refuses to overwrite an existing archive. It includes only manifest
entries and strips Git history and original file timestamps. Do not modify the
checkout while exporting. Pattern checks cannot establish that a manuscript,
selection, image, or numerical result is nonconfidential; review the actual files.

`.gitignore` does not remove files already tracked in Git. Deleting a file in a
later commit does not remove its earlier versions. If private content ever
entered a published repository, follow
[GitHub's sensitive-data removal guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
For this framework, start from the clean export instead of reusing research history.

## Create the repository

Extract the audited archive in a separate location. Review its contents and
initialize a fresh Git repository there. A suitable name is
`turbomole-namd-qmmm`. The extracted source includes no repository remote.

Before public publication, confirm the author list and your right to distribute
the contributed code under the chosen license. This candidate includes MIT; the
external programs and force fields retain their own terms. Retain author notices
and distinguish a scholarly citation request from license conditions.

Create an empty GitHub repository and push only this reviewed source repository.
Avoid attaching private logs or structures in issues, pull requests, screenshots,
releases, or CI artifacts. Inspect the first CI run and record any platform
limitations; do not add passing badges before there is a corresponding result.

## Make a citable version

Add the actual repository URL to `CITATION.cff` and the package project URLs after
the repository exists. When a release is ready, synchronize the version in
`pyproject.toml` and `src/turbomole_namd/__init__.py`, update the changelog, and
add the real release version/date to `CITATION.cff`.

Use a release tag such as `v0.1.0` only when that release is actually made.
GitHub supports preserving releases through Zenodo; the archived release can
then receive a DOI. Use the assigned DOI and inspect the archive's author and
license metadata. Cite a version-specific DOI for reproducibility when available.
See [GitHub's archive and citation guide](https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content).

Keep absent ORCIDs, paper references, DOIs, and repository URLs absent until they
are supplied or assigned. `CITATION.cff` can describe the software itself without
a companion paper; see [GitHub's citation-file guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files).
