from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "secure_runner.py"


def secure_command(target: str, *arguments: str) -> list[str]:
    return [sys.executable, "-I", "-S", str(RUNNER), target, *arguments]


def prepare_workspace(workspace: Path, target_source: str) -> Path:
    shutil.copytree(ROOT / "scripts", workspace / "scripts")
    (workspace / "runtime").mkdir()
    shutil.copy2(
        ROOT / "runtime" / "python-dependency-lock.json",
        workspace / "runtime" / "python-dependency-lock.json",
    )
    target = workspace / "scripts" / "runtime_preflight.py"
    target.write_text(target_source, encoding="utf-8")
    return workspace / "scripts" / "secure_runner.py"


def run_workspace(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(workspace / "scripts" / "secure_runner.py"),
            "scripts/runtime_preflight.py",
        ],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )


class SecureRunnerTests(unittest.TestCase):
    def test_security_sensitive_cli_rejects_direct_python(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "runtime_preflight.py"), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("python3 -I -S scripts/secure_runner.py", completed.stderr)

    def test_locked_snapshot_runs_compiler_with_hostile_pythonpath_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            hostile = Path(directory)
            marker = hostile / "sitecustomize-ran.txt"
            (hostile / "sitecustomize.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('unsafe')\n",
                encoding="utf-8",
            )
            (hostile / "cryptography.py").write_text(
                "raise RuntimeError('hostile cryptography imported')\n", encoding="utf-8"
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(hostile)
            completed = subprocess.run(
                secure_command("scripts/compile_wechat.py", "--help"),
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertFalse(marker.exists())
            self.assertIn("--transport-fidelity", completed.stdout)

    def test_multi_entrypoint_guard_returns_actual_locked_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prepare_workspace(
                workspace,
                "from secure_runtime import require_secure_runtime_any\n"
                "actual = require_secure_runtime_any({\n"
                "    'scripts/runtime_preflight.py',\n"
                "    'scripts/validate_transport_fidelity.py',\n"
                "})\n"
                "print(actual)\n",
            )
            completed = run_workspace(workspace)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(completed.stdout.strip(), "scripts/runtime_preflight.py")

    def test_runner_rejects_missing_isolation_flags(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(RUNNER), "scripts/runtime_preflight.py", "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("invoke with both -I and -S", completed.stderr)

    def test_tampered_dependency_lock_cannot_start_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prepare_workspace(workspace, "raise SystemExit('target must not run')\n")
            lock = json.loads(
                (ROOT / "runtime" / "python-dependency-lock.json").read_text(
                    encoding="utf-8"
                )
            )
            key = "-".join(
                (
                    platform.system().lower(),
                    platform.machine().lower(),
                    sys.implementation.cache_tag or "unknown-python",
                )
            )
            lock["platforms"][key]["distributions"]["Pillow"][
                "aggregate_sha256"
            ] = "sha256:" + "0" * 64
            (workspace / "runtime" / "python-dependency-lock.json").write_text(
                json.dumps(lock), encoding="utf-8"
            )
            completed = run_workspace(workspace)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("exactly one locked distribution", completed.stderr)
            self.assertNotIn("target must not run", completed.stderr)

    def test_workspace_package_shadow_fails_closed_before_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prepare_workspace(workspace, "raise SystemExit('target must not run')\n")
            shadow = workspace / "scripts" / "cryptography"
            shadow.mkdir()
            (shadow / "__init__.py").write_text(
                "raise RuntimeError('workspace shadow imported')\n", encoding="utf-8"
            )
            completed = run_workspace(workspace)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("scripts importable census mismatch", completed.stderr)
            self.assertIn("directory:cryptography", completed.stderr)
            self.assertNotIn("target must not run", completed.stderr)

    def test_unexpected_importable_script_fails_closed_before_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prepare_workspace(workspace, "raise SystemExit('target must not run')\n")
            (workspace / "scripts" / "unexpected_helper.py").write_text(
                "raise RuntimeError('unexpected helper imported')\n", encoding="utf-8"
            )
            completed = run_workspace(workspace)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("scripts importable census mismatch", completed.stderr)
            self.assertIn("source:unexpected_helper.py", completed.stderr)
            self.assertNotIn("target must not run", completed.stderr)

    def test_snapshot_byte_tamper_is_rechecked_by_sensitive_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prepare_workspace(
                workspace,
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "marker = getattr(sys, '_org_wechat_secure_runtime_v1')\n"
                "snapshot = Path(marker['dependency_snapshot'])\n"
                "manifest = json.loads((snapshot / '.org-wechat-dependency-snapshot-v1.json').read_text())\n"
                "distribution = manifest['distributions'][sorted(manifest['distributions'])[0]]\n"
                "victim = snapshot / distribution['files'][0]['path']\n"
                "os.chmod(victim, 0o600)\n"
                "victim.write_bytes(victim.read_bytes() + b'tampered')\n"
                "from secure_runtime import require_secure_runtime\n"
                "require_secure_runtime('scripts/runtime_preflight.py')\n"
                "raise SystemExit('target must not pass verification')\n",
            )
            completed = run_workspace(workspace)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("snapshot file digest mismatch", completed.stderr)
            self.assertNotIn("target must not pass verification", completed.stderr)

    def test_forged_snapshot_manifest_cannot_replace_release_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prepare_workspace(
                workspace,
                "import hashlib, json, os, sys\n"
                "from pathlib import Path\n"
                "marker = getattr(sys, '_org_wechat_secure_runtime_v1')\n"
                "snapshot = Path(marker['dependency_snapshot'])\n"
                "manifest_path = snapshot / '.org-wechat-dependency-snapshot-v1.json'\n"
                "manifest = json.loads(manifest_path.read_text())\n"
                "distribution = manifest['distributions'][sorted(manifest['distributions'])[0]]\n"
                "row = distribution['files'][0]\n"
                "victim = snapshot / row['path']\n"
                "os.chmod(victim, 0o600)\n"
                "forged = victim.read_bytes() + b'forged'\n"
                "victim.write_bytes(forged)\n"
                "row['size'] = len(forged)\n"
                "row['sha256'] = 'sha256:' + hashlib.sha256(forged).hexdigest()\n"
                "manifest_bytes = (json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + '\\n').encode()\n"
                "os.chmod(manifest_path, 0o600)\n"
                "manifest_path.write_bytes(manifest_bytes)\n"
                "marker['snapshot_manifest_sha256'] = 'sha256:' + hashlib.sha256(manifest_bytes).hexdigest()\n"
                "from secure_runtime import require_secure_runtime\n"
                "require_secure_runtime('scripts/runtime_preflight.py')\n"
                "raise SystemExit('target must not pass verification')\n",
            )
            completed = run_workspace(workspace)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("snapshot aggregate digest is invalid", completed.stderr)
            self.assertNotIn("target must not pass verification", completed.stderr)

    def test_snapshot_extra_file_is_rejected_even_with_valid_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prepare_workspace(
                workspace,
                "import sys\n"
                "from pathlib import Path\n"
                "marker = getattr(sys, '_org_wechat_secure_runtime_v1')\n"
                "snapshot = Path(marker['dependency_snapshot'])\n"
                "(snapshot / 'cryptography.py').write_text('raise RuntimeError()')\n"
                "from secure_runtime import require_secure_runtime\n"
                "require_secure_runtime('scripts/runtime_preflight.py')\n"
                "raise SystemExit('target must not pass verification')\n",
            )
            completed = run_workspace(workspace)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("snapshot file census", completed.stderr)
            self.assertNotIn("target must not pass verification", completed.stderr)


if __name__ == "__main__":
    unittest.main()
