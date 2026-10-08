# Copyright (c) 2026 Hao Jiang
# SPDX-License-Identifier: MIT
# Edit this file in a private calculation directory.
set inputPSF "input.psf"
set inputPDB "input.pdb"
set qmRegion1Selection "none"
# Each entry is {label {QM endpoint selection} {MM endpoint selection}}.
# Leave the list empty only when there are no covalent QM-MM boundary bonds.
set qmMmLinkBonds [list]
set activeRadius 10.0
set activeSelection "same residue as within $activeRadius of ($qmRegion1Selection)"
