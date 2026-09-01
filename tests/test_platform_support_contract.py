from __future__ import annotations

import json
import platform
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "scripts" / "secure_runner.py"
LOCK = ROOT / "runtime" / "python-dependency-lock.json"
MATRIX = ROOT / "runtime" / "platform-support.json"


class PlatformSupportContractTests(unittest.TestCase):
    def test_platform_audit_matches_reviewed_lock_without_auto_promotion(self) -> None:
        key = "-".join(
            (
                platform.system().lower(),
                platform.machine().lower(),
                sys.implementation.cache_tag or "unknown-python",
            )
        )
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        support = json.loads(MATRIX.read_text(encoding="utf-8"))
        locked = key in lock.get("platforms", {})
        completed = subprocess.run(
            [sys.executable, "-I", "-S", str(RUNNER), "--platform-audit"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0 if locked else 2, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["platform_key"], key)
        self.assertEqual(report["supported"], locked)
        self.assertEqual(report["target_execution_allowed"], locked)
        if not locked:
            self.assertFalse(report["distribution_lock_verified"])
            self.assertIn("review", report["next_step"])
            self.assertNotIn(
                key,
                {
                    item["platform_key"]
                    for item in support.get("supported", [])
                    if isinstance(item, dict) and "platform_key" in item
                },
            )


if __name__ == "__main__":
    unittest.main()
