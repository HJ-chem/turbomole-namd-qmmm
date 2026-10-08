# Citing the interface and its dependencies

Please cite the interface as software, identify the release or commit used, and
use the author information in [CITATION.cff](CITATION.cff). This development
candidate has no assigned DOI or published paper. Add a real repository URL and
release DOI after publication; do not use placeholder identifiers in a manuscript.

Software citation is independent of licensing. The request to cite this work
does not add a condition to the [MIT License](LICENSE).

For a calculation, also cite the programs and methods actually used:

| Component | Reference |
|---|---|
| NAMD | Phillips, J. C., et al. **Scalable molecular dynamics on CPU and GPU architectures with NAMD.** *Journal of Chemical Physics* **153**, 044130 (2020). [DOI: 10.1063/5.0014475](https://doi.org/10.1063/5.0014475) |
| NAMD QM/MM | Melo, M. C. R., et al. **NAMD goes quantum: an integrative suite for hybrid simulations.** *Nature Methods* **15**, 351–354 (2018). [DOI: 10.1038/nmeth.4638](https://doi.org/10.1038/nmeth.4638) |
| TURBOMOLE | Franzke, Y. J., et al. **TURBOMOLE: Today and Tomorrow.** *Journal of Chemical Theory and Computation* **19**, 6859–6890 (2023). [DOI: 10.1021/acs.jctc.3c00347](https://doi.org/10.1021/acs.jctc.3c00347) |
| VMD, when used for preparation or visualization | Humphrey, W., Dalke, A., and Schulten, K. **VMD: Visual molecular dynamics.** *Journal of Molecular Graphics* **14**, 33–38 (1996). [DOI: 10.1016/0263-7855(96)00018-5](https://doi.org/10.1016/0263-7855(96)00018-5) |

Record the exact NAMD, TURBOMOLE, VMD, and interface versions. Check the current
[NAMD citation guidance](https://www.ks.uiuc.edu/Research/namd/),
[NAMD QM/MM page](https://www.ks.uiuc.edu/Research/qmmm/), and
[TURBOMOLE citation guidance](https://www.turbomole.org/publications/).
TURBOMOLE requests its version and relevant review/method references.

The table does not cover all method citations. Add the functionals, basis sets,
dispersion corrections, boundary methods, force fields, sampling methods, and
other tools used in the work. Follow any separate attribution requirements of
those resources. A citation to the interface does not replace them.

GitHub can display a citation entry from the root `CITATION.cff`; see
[GitHub's citation-file documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files).
