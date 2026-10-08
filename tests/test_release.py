"""Release-boundary tests using temporary, artificial repositories."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_release import audit
from build_release import build_archive


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "source"
        self.root.mkdir()
        (self.root / "README.md").write_text("A synthetic public example.\n")
        self.manifest = self.root / "RELEASE_FILES.txt"
        self.manifest.write_text("README.md\nRELEASE_FILES.txt\n")

    def test_clean_fixture_and_export_exclude_git_history(self):
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text("private metadata")
        self.assertEqual(audit(self.root), [])
        output = self.base / "source.zip"
        build_archive(self.root, output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {
                "turbomole-namd-qmmm/README.md",
                "turbomole-namd-qmmm/RELEASE_FILES.txt",
            })
        with self.assertRaises(FileExistsError):
            build_archive(self.root, output)

    def test_manifest_cannot_escape_checkout(self):
        (self.base / "outside.md").write_text("outside")
        self.manifest.write_text("../outside.md\nRELEASE_FILES.txt\n")
        self.assertTrue(audit(self.root))

    def test_symlink_cannot_export_external_file(self):
        external = self.base / "outside.md"
        external.write_text("outside")
        (self.root / "README.md").unlink()
        (self.root / "README.md").symlink_to(external)
        self.assertTrue(audit(self.root))

    def test_unlisted_file_prevents_release(self):
        (self.root / "unexpected.md").write_text("unexpected")
        self.assertTrue(audit(self.root))
        with self.assertRaises(ValueError):
            build_archive(self.root, self.base / "bad.zip")
        self.assertFalse((self.base / "bad.zip").exists())

    def test_research_file_is_rejected_even_when_listed(self):
        (self.root / "model.pdb").write_text("invented data")
        self.manifest.write_text(self.manifest.read_text() + "model.pdb\n")
        self.assertTrue(audit(self.root))

    def test_local_path_and_private_terms_are_rejected(self):
        (self.root / "README.md").write_text("/" + "Users/" + "example/private/run")
        self.assertTrue(audit(self.root))
        marker = "invented" + "_private_marker"
        (self.root / "README.md").write_text(marker)
        errors = audit(self.root, deny_terms=[marker])
        self.assertTrue(errors)
        self.assertNotIn(marker, "\n".join(errors))

    def test_binary_content_is_rejected(self):
        (self.root / "README.md").write_bytes(b"binary\x00payload")
        self.assertTrue(audit(self.root))


if __name__ == "__main__":
    unittest.main()
