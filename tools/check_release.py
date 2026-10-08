#!/usr/bin/env python3
"""Audit the explicit public file set. This is a guard, not a proof of privacy."""
# Copyright (c) 2026 Hao Jiang
# SPDX-License-Identifier: MIT
import argparse
from pathlib import Path, PurePosixPath
import re

MANIFEST = "RELEASE_FILES.txt"
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".cff", ".tcl", ".conf", ".sh", ".yml", ".yaml"}
TEXT_NAMES = {"LICENSE", ".gitignore", ".gitattributes"}
PRIVATE_NAMES = {"coord", "control", "basis", "auxbasis", "alpha", "beta", "mos",
                 "gradient", "pc_gradient", "point_charges", "energy", "statistics", "step", "qm.list"}
IGNORED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist"}
PATTERNS = {
    "personal absolute path": re.compile(r"(?<![\w:])/(?:Users|home)/[A-Za-z0-9._-]+/"),
    "structure record": re.compile(r"^(?:ATOM  |HETATM)\s*\d", re.MULTILINE),
    "private key": re.compile(r"^-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----", re.MULTILINE),
    "access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "access token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
}
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PUBLIC_EMAILS = {"hao.jiang@dbb.su.se"}


def manifest_paths(root):
    """Return canonical relative paths; reject traversal and duplicate entries."""
    manifest = root / MANIFEST
    if manifest.is_symlink():
        raise ValueError("The manifest must not be a symlink.")
    names = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or str(path) != name or "\\" in name:
            raise ValueError("Manifest contains a noncanonical or unsafe relative path.")
        if name in names:
            raise ValueError("Manifest contains duplicate entries.")
        names.append(name)
    if MANIFEST not in names:
        raise ValueError("The manifest must include itself.")
    return names


def ignored(path):
    return any(part in IGNORED_PARTS or part.endswith(".egg-info") for part in path.parts)


def audit(root, deny_terms=()):
    """Return diagnostics without printing matched private content."""
    root = Path(root).resolve()
    try:
        names = manifest_paths(root)
    except (OSError, UnicodeError, ValueError) as error:
        return [f"Cannot read safe release manifest: {type(error).__name__}"]
    errors = []
    for name in names:
        relative = Path(name)
        path = root / relative
        if ignored(relative):
            errors.append(f"{name}: build/cache/history paths cannot be exported")
            continue
        if any((root / parent).is_symlink() for parent in [relative, *relative.parents]):
            errors.append(f"{name}: symlinks cannot be exported")
            continue
        if not path.is_file():
            errors.append(f"{name}: listed file is missing")
            continue
        if (path.name in PRIVATE_NAMES or path.name.startswith("ref-") or
                (path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES)):
            errors.append(f"{name}: file type is outside the public source policy")
            continue
        if path.stat().st_size > 256 * 1024:
            errors.append(f"{name}: file exceeds the source-file size limit")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{name}: cannot read UTF-8 source text")
            continue
        if "\x00" in content:
            errors.append(f"{name}: binary content")
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                errors.append(f"{name}: possible {label}")
        if any(email.lower() not in PUBLIC_EMAILS for email in EMAIL.findall(content)):
            errors.append(f"{name}: email address outside the declared public contacts")
        for number, term in enumerate(deny_terms, 1):
            if term and term.casefold() in (name + "\n" + content).casefold():
                errors.append(f"{name}: private-term rule {number} matched")
    allowed = set(names)
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if not ignored(relative) and (path.is_file() or path.is_symlink()):
            if relative.as_posix() not in allowed:
                errors.append(f"{relative.as_posix()}: file is not in the release manifest")
    return errors


def read_private_terms(path, root):
    if path is None:
        return []
    path = Path(path).resolve()
    if path.is_relative_to(Path(root).resolve()):
        raise ValueError("Keep the private-term file outside the public checkout.")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--deny-term-file", type=Path, help="Private terms, one per line, kept outside the checkout")
    args = parser.parse_args()
    errors = audit(args.root, read_private_terms(args.deny_term_file, args.root))
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print(f"Release audit passed: {len(manifest_paths(args.root))} explicitly listed text files.")


if __name__ == "__main__":
    main()
