"""Tcl syntax and early configuration guards; no VMD/NAMD emulation."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "examples" / "templates"
TCLSH = shutil.which("tclsh")


@unittest.skipUnless(TCLSH, "tclsh is required for template syntax checks")
class TemplateTests(unittest.TestCase):
    def run_tcl(self, code, cwd=None):
        return subprocess.run([TCLSH], input=code, text=True,
                              capture_output=True, cwd=cwd)

    def test_tcl_scripts_are_complete(self):
        for name in ("selection.tcl", "prepare.tcl", "qmmm.conf"):
            with self.subTest(name=name):
                code = f"set f [open {{{TEMPLATES / name}}} r]\nset s [read $f]\nclose $f\nputs [info complete $s]\n"
                result = self.run_tcl(code)
                self.assertEqual(result.stdout.strip(), "1", result.stderr)

    def test_preparation_requires_explicit_qm_selection(self):
        code = f"catch {{source {{{TEMPLATES / 'prepare.tcl'}}}}} reason\nputs $reason\n"
        result = self.run_tcl(code)
        self.assertIn("Set qmRegion1Selection", result.stdout)

    def test_namd_template_requires_electronic_state(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "mm.conf").write_text("# Empty synthetic configuration\n")
            code = f"catch {{source {{{TEMPLATES / 'qmmm.conf'}}}}} reason\nputs $reason\n"
            result = self.run_tcl(code, cwd=directory)
        self.assertIn("Set qmTotalCharge and qmMultiplicity", result.stdout)
