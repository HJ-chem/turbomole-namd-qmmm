#!/usr/bin/env python3
"""Export only the audited public file manifest, without any Git history."""
# Copyright (c) 2026 Hao Jiang
# SPDX-License-Identifier: MIT
import argparse
from pathlib import Path
import zipfile

from check_release import audit, manifest_paths, read_private_terms


def build_archive(root, output, deny_terms=()):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.is_relative_to(root):
        raise ValueError("Write the archive outside the source checkout.")
    errors = audit(root, deny_terms)
    if errors:
        raise ValueError("Release audit failed:\n" + "\n".join(errors))
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(manifest_paths(root)):
            path = root / name
            info = zipfile.ZipInfo("turbomole-namd-qmmm/" + name)
            info.create_system = 3
            mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deny-term-file", type=Path)
    args = parser.parse_args()
    build_archive(args.root, args.output, read_private_terms(args.deny_term_file, args.root))
    print(f"Wrote source archive: {args.output.name}")


if __name__ == "__main__":
    main()
