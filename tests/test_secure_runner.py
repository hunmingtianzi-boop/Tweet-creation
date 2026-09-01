from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "secure_runner.py"
AUTHORING_ENTRYPOINT_HELP = (
    ("scripts/orgs.py", "register-asset"),
    ("scripts/build_visual_directions.py", "--output"),
    ("scripts/build_storyboard.py", "--output"),
    ("scripts/build_visual_kit.py", "--org"),
    ("scripts/build_ardot_manifest.py", "--org"),
    ("scripts/inspect_asset.py", "--role"),
)


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
    def test_platform_audit_verifies_current_lock_before_target(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-I", "-S", str(RUNNER), "--platform-audit"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["supported"])
        self.assertTrue(report["distribution_lock_verified"])
        self.assertTrue(report["target_execution_allowed"])

    def test_unknown_platform_audit_fails_before_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            prepare_workspace(workspace, "raise SystemExit('target must not run')\n")
            lock_path = workspace / "runtime" / "python-dependency-lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["platforms"] = {}
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(workspace / "scripts" / "secure_runner.py"),
                    "--platform-audit",
                ],
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
            report = json.loads(completed.stdout)
            self.assertFalse(report["supported"])
            self.assertFalse(report["target_execution_allowed"])
            self.assertIn("absent", report["blocking_reason"])

    def test_dependency_candidate_is_create_once_review_material_only(self) -> None:
        lock_before = (ROOT / "runtime" / "python-dependency-lock.json").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.json"
            command = [
                sys.executable,
                "-I",
                "-S",
                str(RUNNER),
                "--dependency-candidate",
                str(candidate),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            self.assertFalse(payload["trusted"])
            self.assertTrue(payload["review_required"])
            self.assertFalse(payload["automatic_lock_upgrade_allowed"])
            replay = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(replay.returncode, 0)
            self.assertIn("must be a new", replay.stderr)
        self.assertEqual(
            lock_before,
            (ROOT / "runtime" / "python-dependency-lock.json").read_bytes(),
        )

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

    def test_authoring_entrypoints_ignore_hostile_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            hostile = Path(directory)
            marker = hostile / "sitecustomize-ran.txt"
            (hostile / "sitecustomize.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('unsafe')\n",
                encoding="utf-8",
            )
            (hostile / "PIL.py").write_text(
                "raise RuntimeError('hostile Pillow imported')\n", encoding="utf-8"
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(hostile)
            for target, expected in AUTHORING_ENTRYPOINT_HELP:
                with self.subTest(target=target):
                    completed = subprocess.run(
                        secure_command(target, "--help"),
                        cwd=ROOT,
                        check=False,
                        capture_output=True,
                        text=True,
                        env=environment,
                    )
                    self.assertEqual(
                        completed.returncode, 0, completed.stdout + completed.stderr
                    )
                    self.assertIn(expected, completed.stdout)
            self.assertFalse(marker.exists())

    def test_authoring_entrypoints_are_allowed_locked_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for target, expected in AUTHORING_ENTRYPOINT_HELP:
                with self.subTest(target=target):
                    completed = subprocess.run(
                        secure_command(str(ROOT / target), "--help"),
                        cwd=directory,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(
                        completed.returncode, 0, completed.stdout + completed.stderr
                    )
                    self.assertIn(expected, completed.stdout)

    def test_authoring_entrypoints_reject_direct_cli_execution(self) -> None:
        for target, _ in AUTHORING_ENTRYPOINT_HELP:
            with self.subTest(target=target):
                completed = subprocess.run(
                    [sys.executable, str(ROOT / target), "--help"],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(
                    "python3 -I -S scripts/secure_runner.py", completed.stderr
                )

    def test_authoring_entrypoints_reject_outputs_inside_installed_runtime(self) -> None:
        """Authoring CLIs must not turn the installed Skill into project storage."""

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            article = project / "article.json"
            article.write_text("{}\n", encoding="utf-8")
            organization = project / "organization"
            organization.mkdir()
            token = uuid.uuid4().hex
            cases = (
                (
                    "scripts/build_storyboard.py",
                    (str(article), "--output", str(ROOT / f".{token}-storyboard.json")),
                ),
                (
                    "scripts/build_visual_directions.py",
                    (
                        str(organization),
                        "recruitment",
                        "--output",
                        str(ROOT / f".{token}-directions.json"),
                    ),
                ),
                (
                    "scripts/build_visual_kit.py",
                    (
                        str(article),
                        "--org",
                        str(organization),
                        "--output",
                        str(ROOT / f".{token}-kit.json"),
                    ),
                ),
                (
                    "scripts/build_ardot_manifest.py",
                    (
                        str(article),
                        "--org",
                        str(organization),
                        "--output",
                        str(ROOT / f".{token}-ardot.json"),
                    ),
                ),
                (
                    "scripts/orgs.py",
                    (
                        "asset-plan",
                        str(organization),
                        "recruitment",
                        "--output",
                        str(ROOT / f".{token}-asset-plan.json"),
                    ),
                ),
                (
                    "scripts/compile_wechat.py",
                    (
                        str(article),
                        "--authoring-preview",
                        "--org",
                        str(organization),
                        "--output",
                        str(ROOT / f".{token}-preview"),
                    ),
                ),
            )
            for target, arguments in cases:
                with self.subTest(target=target):
                    completed = subprocess.run(
                        secure_command(target, *arguments),
                        cwd=project,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(
                        completed.returncode, 0, completed.stdout + completed.stderr
                    )
                    self.assertIn("outside the installed runtime", completed.stderr)

    def test_final_evidence_entrypoints_reject_outputs_inside_installed_runtime(self) -> None:
        # canonical_pack_root deliberately rejects lexical symlink ancestors;
        # macOS's default /var/folders alias would mask the output-boundary gate.
        with tempfile.TemporaryDirectory(dir="/private/tmp") as directory:
            project = Path(directory)
            first = project / "first.json"
            second = project / "second.json"
            first.write_text("{}\n", encoding="utf-8")
            second.write_text("{}\n", encoding="utf-8")
            image = project / "carrier.png"
            image.write_bytes(b"not-decoded-before-output-preflight")
            token = uuid.uuid4().hex
            cases = (
                (
                    "scripts/build_visual_review.py",
                    (
                        str(first),
                        "--article",
                        str(second),
                        "--output",
                        str(ROOT / f".{token}-visual-review.json"),
                    ),
                ),
                (
                    "scripts/validate_transport_fidelity.py",
                    (
                        str(first),
                        "--report",
                        str(ROOT / f".{token}-transport.json"),
                    ),
                ),
                (
                    "scripts/validate_workflow_attribution.py",
                    (
                        str(first),
                        "--report",
                        str(ROOT / f".{token}-attribution.json"),
                    ),
                ),
                (
                    "scripts/provenance_watermark.py",
                    (
                        "detect",
                        str(image),
                        "--report",
                        str(ROOT / f".{token}-watermark.json"),
                    ),
                ),
            )
            for target, arguments in cases:
                with self.subTest(target=target):
                    completed = subprocess.run(
                        secure_command(target, *arguments),
                        cwd=project,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(
                        completed.returncode, 0, completed.stdout + completed.stderr
                    )
                    self.assertIn(
                        "outside the installed runtime",
                        completed.stdout + completed.stderr,
                    )

    def test_authoring_docs_do_not_recommend_direct_cli_execution(self) -> None:
        documents = [ROOT / "SKILL.md", ROOT / "README.md"]
        documents.extend(sorted((ROOT / "references").glob("*.md")))
        for document in documents:
            text = document.read_text(encoding="utf-8")
            for target, _ in AUTHORING_ENTRYPOINT_HELP:
                name = Path(target).name
                with self.subTest(document=document.name, target=target):
                    self.assertNotIn(
                        f'python3 "$ORG_WECHAT_RUNTIME_ROOT/scripts/{name}"', text
                    )
                    self.assertNotIn(f"python3 scripts/{name}", text)

    def test_interaction_policy_is_an_allowed_locked_entrypoint(self) -> None:
        completed = subprocess.run(
            secure_command("scripts/wechat_interaction_policy.py", "--help"),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("--fallback", completed.stdout)

    def test_final_evidence_clis_are_allowed_locked_entrypoints(self) -> None:
        for target, expected in (
            ("scripts/validate_workflow_attribution.py", "--require-readback"),
            ("scripts/build_visual_review.py", "--article"),
        ):
            with self.subTest(target=target):
                completed = subprocess.run(
                    secure_command(target, "--help"),
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    completed.returncode, 0, completed.stdout + completed.stderr
                )
                self.assertIn(expected, completed.stdout)

    def test_publisher_runtime_location_uses_runner_platform_audit(self) -> None:
        document = (
            ROOT
            / "skills"
            / "ardot-wechat-publisher"
            / "references"
            / "runtime-location.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" --platform-audit',
            document,
        )
        self.assertNotIn(
            '"$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" \\\n+  --platform-audit',
            document,
        )

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
