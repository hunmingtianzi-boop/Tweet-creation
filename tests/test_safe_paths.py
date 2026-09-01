from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.safe_paths import (
    SafePathError,
    existing_regular_file,
    new_directory_path,
    new_file_path,
    write_text_create_once,
)


class SafePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_create_once_preserves_existing_file_and_direct_symlink(self) -> None:
        existing = self.root / "evidence.json"
        existing.write_text("sentinel", encoding="utf-8")
        with self.assertRaises(SafePathError):
            write_text_create_once(existing, "replacement", label="evidence")
        self.assertEqual(existing.read_text(encoding="utf-8"), "sentinel")

        target = self.root / "target.json"
        target.write_text("target-sentinel", encoding="utf-8")
        link = self.root / "linked.json"
        link.symlink_to(target)
        with self.assertRaises(SafePathError):
            write_text_create_once(link, "replacement", label="evidence")
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "target-sentinel")

    def test_every_existing_ancestor_is_checked_before_read_or_write(self) -> None:
        real = self.root / "real"
        nested = real / "nested"
        nested.mkdir(parents=True)
        source = nested / "source.txt"
        source.write_text("source", encoding="utf-8")
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)

        with self.assertRaisesRegex(SafePathError, r"symlink"):
            existing_regular_file(alias / "nested" / "source.txt", label="source")
        with self.assertRaisesRegex(SafePathError, r"symlink"):
            new_file_path(alias / "nested" / "report.json", label="report")
        with self.assertRaisesRegex(SafePathError, r"symlink"):
            new_directory_path(alias / "nested" / "bundle", label="bundle")
        self.assertFalse((nested / "report.json").exists())
        self.assertFalse((nested / "bundle").exists())

    def test_new_paths_require_preexisting_real_parent(self) -> None:
        missing_parent = self.root / "missing" / "report.json"
        with self.assertRaises(SafePathError):
            new_file_path(missing_parent, label="report")
        self.assertFalse((self.root / "missing").exists())

        existing_dir = self.root / "existing-bundle"
        existing_dir.mkdir()
        sentinel = existing_dir / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(SafePathError):
            new_directory_path(existing_dir, label="bundle")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_create_once_file_can_be_kept_outside_runtime_root(self) -> None:
        runtime = self.root / "installed-runtime"
        runtime.mkdir()
        with self.assertRaisesRegex(SafePathError, r"outside the installed runtime"):
            write_text_create_once(
                runtime / "report.json",
                "blocked",
                label="report",
                forbidden_root=runtime,
            )
        self.assertFalse((runtime / "report.json").exists())

        external = self.root / "project"
        external.mkdir()
        created = write_text_create_once(
            external / "report.json",
            "accepted",
            label="report",
            forbidden_root=runtime,
        )
        self.assertEqual(created.read_text(encoding="utf-8"), "accepted")


if __name__ == "__main__":
    unittest.main()
