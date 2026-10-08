#!/usr/bin/env python3
"""Source-checkout launcher; no package installation required."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from turbomole_namd.adapter import cli

if __name__ == "__main__":
    cli()
