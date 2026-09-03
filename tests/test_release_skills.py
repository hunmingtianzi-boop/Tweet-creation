from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from scripts.release_skills import (
    PACKAGE_SOURCES,
    ReleaseError,
    build_manifest,
    clone_readiness,
    collect_package_files,
    install_packages,
    stage_packages,
    validate_skill_structure,
    validate_skill_structures,
    verify_installed_packages,
    verify_manifest,
    write_manifest,
)


ROOT = Path(__file__).resolve().parent.parent


def _locked_runtime_available() -> bool:
    key = "-".join(
        (
            platform.system().lower(),
            platform.machine().lower(),
            sys.implementation.cache_tag or "unknown-python",
        )
    )
    support = json.loads(
        (ROOT / "runtime" / "platform-support.json").read_text(encoding="utf-8")
    )
    return any(
        isinstance(row, dict)
        and row.get("platform_key") == key
        and row.get("status") == "locked"
        for row in support.get("supported", [])
    )


requires_locked_runtime = unittest.skipUnless(
    _locked_runtime_available(),
    "requires the reviewed locked Codex Desktop runtime; portable CI verifies fail-closed behavior instead",
)


class ReleaseSkillTests(unittest.TestCase):
    def test_stdlib_skill_structure_gate_rejects_invalid_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "SKILL.md"
            skill.write_text(
                "---\nname: wrong-package\ndescription: TODO\nextra: unsafe\n---\n# Body\n",
                encoding="utf-8",
            )
            with self.assertRaises(ReleaseError):
                validate_skill_structure("org-wechat-studio", skill)
        self.assertTrue(validate_skill_structures(ROOT)["ok"])

    def test_clone_readiness_fails_closed_when_distribution_audit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "scripts.release_skills._platform_audit_snapshot",
            return_value={"ok": False, "error": "synthetic locked wheel mismatch"},
        ):
            result = clone_readiness(
                Path(directory),
                phase="migration",
                workspace_root=ROOT,
                mcp_inventory={"ok": True, "routes": []},
            )
        checks = {item["id"]: item for item in result["checks"]}
        self.assertEqual(checks["locked-python-distributions"]["status"], "missing")
        self.assertIn("locked-python-distributions", result["local_blockers"])
        self.assertFalse(result["local_prerequisites_ready"])

    def test_clone_readiness_distinguishes_ardot_config_from_task_injection(self) -> None:
        inventory = {
            "ok": True,
            "routes": [
                {
                    "name": "ardot-remote",
                    "enabled": True,
                    "auth_mechanism": "o_auth",
                    "transport_type": "streamable_http",
                    "url": "https://ardot.tencent.com/mcp",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "scripts.release_skills._platform_audit_snapshot",
            return_value={
                "ok": True,
                "verified_distributions": ["Pillow", "cryptography"],
            },
        ):
            missing = clone_readiness(
                Path(directory),
                phase="bootstrap",
                workspace_root=ROOT,
                visible_tool_ids=[],
                mcp_inventory=inventory,
            )
            visible = clone_readiness(
                Path(directory),
                phase="bootstrap",
                workspace_root=ROOT,
                visible_tool_ids=[
                    "mcp__ardot_remote__create_design",
                    "mcp__ardot_remote__create_new_page",
                ],
                mcp_inventory=inventory,
            )
        missing_checks = {item["id"]: item for item in missing["checks"]}
        visible_checks = {item["id"]: item for item in visible["checks"]}
        self.assertEqual(
            missing_checks["ardot-remote-local-configuration"]["status"], "passed"
        )
        self.assertEqual(
            missing_checks["ardot-current-task-registry"]["status"],
            "requires-task-reload",
        )
        self.assertTrue(missing["current_task_reload_required"])
        self.assertEqual(
            visible_checks["ardot-current-task-registry"]["status"], "passed"
        )
        self.assertFalse(visible["current_task_reload_required"])

    def test_clone_readiness_declares_codex_only_and_live_login_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = clone_readiness(Path(directory), phase="full", workspace_root=ROOT)
        self.assertEqual(result["schema"], "org-wechat-clone-readiness-v1")
        self.assertEqual(result["support"]["execution_host"], "codex-desktop")
        self.assertEqual(
            result["support"]["other_harnesses"],
            "unsupported-until-a-reviewed-adapter-and-full-forward-test-are-released",
        )
        self.assertFalse(
            result["support"]["semantic_contract_portability_is_execution_support"]
        )
        checks = {item["id"]: item for item in result["checks"]}
        self.assertTrue(checks["codex-with-chatgpt"]["required"])
        self.assertEqual(
            checks["codex-desktop-session"]["status"], "requires-live-probe"
        )
        self.assertEqual(
            checks["chatgpt-connection-and-login"]["status"],
            "requires-live-probe",
        )
        self.assertEqual(
            checks["ardot-login-and-target-access"]["status"],
            "requires-live-probe",
        )
        self.assertEqual(
            checks["wechat-account-session"]["status"], "requires-live-probe"
        )
        self.assertFalse(result["live_session_ready"])
        self.assertFalse(result["ready_to_read_source_material"])

    def test_clone_readiness_is_phase_specific(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            delivery = clone_readiness(
                Path(directory), phase="delivery", workspace_root=ROOT
            )
            bootstrap = clone_readiness(
                Path(directory), phase="bootstrap", workspace_root=ROOT
            )
        delivery_checks = {item["id"]: item for item in delivery["checks"]}
        self.assertFalse(delivery_checks["codex-with-chatgpt"]["required"])
        self.assertEqual(delivery_checks["codex-with-chatgpt"]["status"], "not-required")
        self.assertTrue(delivery_checks["ardot-login-and-target-access"]["required"])
        self.assertTrue(delivery_checks["wechat-account-session"]["required"])
        bootstrap_checks = {item["id"]: item for item in bootstrap["checks"]}
        self.assertTrue(bootstrap_checks["ardot-login-and-target-access"]["required"])
        self.assertFalse(bootstrap_checks["wechat-account-session"]["required"])

    def test_release_cli_requires_isolation_and_ignores_hostile_pythonpath(self) -> None:
        script = ROOT / "scripts" / "release_skills.py"
        unisolated = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(unisolated.returncode, 2)
        self.assertIn("requires python3 -I -S", unisolated.stdout)

        with tempfile.TemporaryDirectory() as directory:
            hostile = Path(directory)
            marker = hostile / "sitecustomize-ran"
            (hostile / "sitecustomize.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
                encoding="utf-8",
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(hostile)
            isolated = subprocess.run(
                [sys.executable, "-I", "-S", str(script), "--help"],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(isolated.returncode, 0, isolated.stdout + isolated.stderr)
            self.assertFalse(marker.exists())

    def test_release_cli_json_is_safe_on_ascii_only_stdout(self) -> None:
        script = ROOT / "scripts" / "release_skills.py"
        manifest = ROOT / "release" / "org-wechat-skills-v1.json"
        command = (
            "import runpy,sys;"
            "sys.stdout.reconfigure(encoding='ascii');"
            f"sys.argv={[str(script), 'verify', str(manifest)]!r};"
            f"runpy.run_path({str(script)!r},run_name='__main__')"
        )
        completed = subprocess.run(
            [sys.executable, "-I", "-S", "-c", command],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("\\u4f7f", completed.stdout)

    def test_org_package_excludes_visual_and_organization_history(self) -> None:
        relative = {
            item.as_posix()
            for _, item in collect_package_files("org-wechat-studio", ROOT)
        }
        self.assertIn("SKILL.md", relative)
        self.assertIn("scripts/runtime_preflight.py", relative)
        self.assertIn("references/host-prerequisites.md", relative)
        self.assertFalse(any(path.startswith("examples/") for path in relative))
        self.assertFalse(any(path.startswith("organizations/") for path in relative))
        self.assertFalse(any(path.startswith("output/") for path in relative))
        self.assertFalse(any(path.startswith("experiments/") for path in relative))
        self.assertFalse(any(path.startswith("skills/") for path in relative))

    def test_release_has_one_discoverable_entrypoint_per_skill_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "stage"
            stage_packages(destination, ROOT)
            entrypoints = sorted(destination.glob("*/SKILL.md"))
            self.assertEqual(
                [item.parent.name for item in entrypoints],
                sorted(PACKAGE_SOURCES),
            )
            self.assertEqual(
                list(
                    (destination / "org-wechat-studio").glob(
                        "skills/**/SKILL.md"
                    )
                ),
                [],
            )

    def test_every_packaged_local_markdown_link_resolves_inside_its_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "stage"
            stage_packages(destination, ROOT)
            markdown_link = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
            for package in sorted(PACKAGE_SOURCES):
                package_root = (destination / package).resolve()
                for markdown in package_root.rglob("*.md"):
                    for match in markdown_link.finditer(
                        markdown.read_text(encoding="utf-8")
                    ):
                        raw = match.group(1).strip()
                        if raw.startswith(("https://", "http://", "mailto:", "#")):
                            continue
                        without_fragment = raw.split("#", 1)[0]
                        if not without_fragment:
                            continue
                        target = (
                            markdown.parent
                            / urllib.parse.unquote(without_fragment)
                        ).resolve()
                        with self.subTest(
                            package=package,
                            markdown=markdown.relative_to(package_root),
                            target=raw,
                        ):
                            target.relative_to(package_root)
                            self.assertTrue(target.exists(), target)

    def test_packaged_markdown_has_no_executable_relative_script_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "stage"
            stage_packages(destination, ROOT)
            command = re.compile(r"python3(?:\s+-I\s+-S)?\s+scripts/")
            explanatory = ("Direct ", "Never ", "refus", "forbid", "拒绝", "禁止")
            for markdown in destination.glob("*/**/*.md"):
                for line_number, line in enumerate(
                    markdown.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if command.search(line) and not any(
                        marker in line for marker in explanatory
                    ):
                        self.fail(
                            f"relative packaged command at {markdown}:{line_number}: {line}"
                        )

    def test_manifest_round_trip_and_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "release.json"
            expected = write_manifest(manifest_path, ROOT)
            self.assertEqual(expected, verify_manifest(manifest_path, ROOT))
            tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
            tampered["release_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(ReleaseError):
                verify_manifest(manifest_path, ROOT)

    def test_stage_matches_repository_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "stage"
            manifest = stage_packages(destination, ROOT)
            self.assertEqual(manifest, build_manifest(ROOT))
            for package in PACKAGE_SOURCES:
                self.assertTrue((destination / package / "SKILL.md").is_file())

    def test_verified_manifest_installs_all_packages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest_path = root / "release.json"
            write_manifest(manifest_path, ROOT)
            skills_root = root / "skills"
            result = install_packages(skills_root, manifest_path, ROOT)
            self.assertTrue(result["ok"])
            installed_manifest = Path(result["installed_manifest"])
            self.assertTrue(installed_manifest.is_file())
            self.assertEqual(installed_manifest.read_bytes(), manifest_path.read_bytes())
            self.assertTrue(
                verify_installed_packages(skills_root, manifest_path, ROOT)["ok"]
            )
            self.assertTrue(
                verify_installed_packages(
                    skills_root,
                    installed_manifest,
                    ROOT,
                    verify_workspace_source=False,
                )["ok"]
            )
            for package in PACKAGE_SOURCES:
                self.assertTrue((root / "skills" / package / "SKILL.md").is_file())

    def test_installed_verify_rejects_external_matching_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            external_manifest = root / "externally-supplied-matching.json"
            write_manifest(external_manifest, ROOT)
            skills_root = root / "skills"
            install_packages(skills_root, external_manifest, ROOT)

            with self.assertRaisesRegex(
                ReleaseError,
                "must be located directly",
            ):
                verify_installed_packages(
                    skills_root,
                    external_manifest,
                    ROOT,
                    verify_workspace_source=False,
                )

    def test_installed_verify_rejects_wrong_manifest_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source_manifest = root / "release.json"
            write_manifest(source_manifest, ROOT)
            skills_root = root / "skills"
            installed = install_packages(skills_root, source_manifest, ROOT)
            canonical_manifest = Path(installed["installed_manifest"])
            wrong_name = canonical_manifest.parent / "wrong-name.json"
            wrong_name.write_bytes(canonical_manifest.read_bytes())

            with self.assertRaisesRegex(
                ReleaseError,
                "filename must equal its internal release_sha256",
            ):
                verify_installed_packages(
                    skills_root,
                    wrong_name,
                    ROOT,
                    verify_workspace_source=False,
                )

    def test_installed_verify_rejects_symlinked_manifest_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source_manifest = root / "release.json"
            write_manifest(source_manifest, ROOT)
            skills_root = root / "skills"
            installed = install_packages(skills_root, source_manifest, ROOT)
            installed_manifest = Path(installed["installed_manifest"])
            manifest_store = installed_manifest.parent
            real_store = root / "detached-manifest-store"
            manifest_store.rename(real_store)
            manifest_store.symlink_to(real_store, target_is_directory=True)

            with self.assertRaisesRegex(
                ReleaseError,
                "installed manifest store must not use symlinks",
            ):
                verify_installed_packages(
                    skills_root,
                    manifest_store / installed_manifest.name,
                    ROOT,
                    verify_workspace_source=False,
                )

    @requires_locked_runtime
    def test_installed_runtime_runs_census_and_profile_from_external_cwd(self) -> None:
        private_tmp = Path("/private/tmp")
        if not private_tmp.is_dir():
            private_tmp = Path(tempfile.gettempdir()).resolve()
        with tempfile.TemporaryDirectory(
            prefix="org-wechat-installed-smoke-", dir=private_tmp
        ) as directory:
            root = Path(directory).resolve()
            source_manifest = root / "release.json"
            write_manifest(source_manifest, ROOT)
            skills_root = root / "skills"
            installed = install_packages(skills_root, source_manifest, ROOT)
            installed_manifest = Path(installed["installed_manifest"])
            runtime_root = skills_root / "org-wechat-studio"
            runner = runtime_root / "scripts" / "secure_runner.py"
            preflight = runtime_root / "scripts" / "runtime_preflight.py"

            project = root / "user-project"
            project.mkdir()
            subprocess.run(
                ["git", "init", "-q"], cwd=project, check=True, capture_output=True
            )
            (project / ".gitignore").write_text(
                "output/runtime/\n", encoding="utf-8"
            )
            session_root = project / "output" / "runtime"
            session_root.mkdir(parents=True)

            verify = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(runtime_root / "scripts" / "release_skills.py"),
                    "verify-installed",
                    str(installed_manifest),
                    "--skills-root",
                    str(skills_root),
                ],
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)

            census_path = session_root / "census.json"
            census = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(runner),
                    str(preflight),
                    "init-current-session-census",
                    "--phase",
                    "migration",
                    "--session-id",
                    "installed-smoke-session",
                    "--workspace-root",
                    str(runtime_root),
                    "--skills-root",
                    str(skills_root),
                    "--release-manifest",
                    str(installed_manifest),
                    "--output",
                    str(census_path),
                    "--visible-tool-id",
                    "image_gen__imagegen",
                    "--visible-tool-id",
                    "codex-with-chatgpt",
                    "--visible-tool-id",
                    "browser:control-in-app-browser",
                    "--visible-tool-id",
                    "mcp__node_repl__js",
                    "--visible-tool-id",
                    "view_image",
                ],
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(census.returncode, 0, census.stdout + census.stderr)

            target_path = project / "runtime-target.json"
            target_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "org-wechat-runtime-target-v1",
                        "links": {},
                        "targets": {},
                    }
                ),
                encoding="utf-8",
            )
            profile_path = session_root / "profile.json"
            profile = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(runner),
                    str(preflight),
                    "init-profile",
                    str(census_path),
                    str(target_path),
                    "--phase",
                    "migration",
                    "--workspace-root",
                    str(runtime_root),
                    "--output",
                    str(profile_path),
                ],
                cwd=project,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(profile.returncode, 0, profile.stdout + profile.stderr)
            generated = json.loads(profile_path.read_text(encoding="utf-8"))
            census_payload = json.loads(census_path.read_text(encoding="utf-8"))
            census_skills = {
                item["id"]: item for item in census_payload["skills"]
            }
            self.assertEqual(
                {item["id"] for item in generated["skills"]},
                set(PACKAGE_SOURCES),
            )
            for item in generated["skills"]:
                entrypoint = Path(item["entrypoint"])
                self.assertTrue(entrypoint.is_absolute())
                self.assertEqual(entrypoint, skills_root / item["id"] / "SKILL.md")
                self.assertTrue(entrypoint.is_file())
                self.assertEqual(
                    item["sha256"],
                    census_skills[item["id"]]["entrypoint_sha256"],
                )
            self.assertFalse((runtime_root / "skills").exists())

            report_path = session_root / "binding-report.json"
            runtime_mode = runtime_root.stat().st_mode
            os.chmod(runtime_root, runtime_mode & ~0o222)
            try:
                binding = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-S",
                        str(runner),
                        str(preflight),
                        str(profile_path),
                        "--phase",
                        "migration",
                        "--workspace-root",
                        str(runtime_root),
                        "--session-root",
                        str(session_root),
                        "--output",
                        str(report_path),
                        "--binding-only",
                    ],
                    cwd=project,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            finally:
                os.chmod(runtime_root, runtime_mode)
            self.assertEqual(binding.returncode, 0, binding.stdout + binding.stderr)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["binding_ready"], report["errors"])
            probe = next(
                item
                for item in report["host_setup_actions"]
                if item["id"] == "run-migration-rgba-route-probe"
            )
            self.assertEqual(Path(probe["session_root"]), session_root)
            self.assertEqual(
                Path(probe["artifact_root"]).parent,
                session_root / "migration-probes",
            )
            self.assertFalse(runtime_root in Path(probe["artifact_root"]).parents)
            for command_field in (
                "processor_command",
                "ingestion_command_template",
            ):
                for case in probe["probe_cases"]:
                    command = case[command_field]
                    self.assertEqual(Path(command[3]).parent.parent, runtime_root)

    def test_install_rejects_symlink_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "release.json"
            write_manifest(manifest_path, ROOT)
            alias = root / "release-link.json"
            alias.symlink_to(manifest_path)
            with self.assertRaises(ReleaseError):
                install_packages(root / "skills", alias, ROOT)

    def test_release_paths_reject_symlink_ancestors_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real = root / "real-release-parent"
            nested = real / "nested"
            nested.mkdir(parents=True)
            alias = root / "release-parent-alias"
            alias.symlink_to(real, target_is_directory=True)

            linked_manifest = alias / "nested" / "release.json"
            with self.assertRaisesRegex(ReleaseError, r"symlink"):
                write_manifest(linked_manifest, ROOT)
            self.assertFalse((nested / "release.json").exists())

            linked_stage = alias / "nested" / "stage"
            with self.assertRaisesRegex(ReleaseError, r"symlink"):
                stage_packages(linked_stage, ROOT)
            self.assertFalse((nested / "stage").exists())

            manifest = root / "release.json"
            write_manifest(manifest, ROOT)
            linked_skills = alias / "nested" / "skills"
            with self.assertRaisesRegex(ReleaseError, r"symlink"):
                install_packages(linked_skills, manifest, ROOT)
            self.assertFalse((nested / "skills").exists())

    @requires_locked_runtime
    def test_installed_external_census_is_phase_scoped_for_bootstrap_and_api_delivery(self) -> None:
        private_tmp = Path("/private/tmp")
        if not private_tmp.is_dir():
            private_tmp = Path(tempfile.gettempdir()).resolve()
        with tempfile.TemporaryDirectory(
            prefix="org-wechat-phase-census-", dir=private_tmp
        ) as directory:
            root = Path(directory).resolve()
            source_manifest = root / "release.json"
            write_manifest(source_manifest, ROOT)
            skills_root = root / "skills"
            installed = install_packages(skills_root, source_manifest, ROOT)
            installed_manifest = Path(installed["installed_manifest"])
            runtime_root = skills_root / "org-wechat-studio"
            runner = runtime_root / "scripts" / "secure_runner.py"
            preflight = runtime_root / "scripts" / "runtime_preflight.py"
            project = root / "external-project"
            project.mkdir()
            adapter = json.loads(
                (runtime_root / "runtime" / "adapters" / "codex-desktop.json").read_text(
                    encoding="utf-8"
                )
            )

            def run_census(phase: str, visible: list[str]) -> dict:
                output = root / f"{phase}-census.json"
                command = [
                    sys.executable,
                    "-I",
                    "-S",
                    str(runner),
                    str(preflight),
                    "init-current-session-census",
                    "--phase",
                    phase,
                    "--session-id",
                    f"{phase}-external-session",
                    "--workspace-root",
                    str(runtime_root),
                    "--skills-root",
                    str(skills_root),
                    "--release-manifest",
                    str(installed_manifest),
                    "--output",
                    str(output),
                ] + [
                    argument
                    for tool_id in visible
                    for argument in ("--visible-tool-id", tool_id)
                ]
                completed = subprocess.run(
                    command,
                    cwd=project,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    completed.returncode, 0, completed.stdout + completed.stderr
                )
                return json.loads(output.read_text(encoding="utf-8"))

            bootstrap_ids = adapter["capabilities"]["ardot.create"]["requires"]
            bootstrap = run_census("bootstrap", bootstrap_ids)
            self.assertEqual(
                {item["id"] for item in bootstrap["tools"]}, set(bootstrap_ids)
            )
            self.assertNotIn(
                "scripts/ingest_browser_download.py",
                {item["id"] for item in bootstrap["tools"]},
            )

            delivery_kinds = (
                "image.inspect",
                "ardot.read",
                "ardot.write",
                "ardot.export",
                "wechat.current-session-readback",
            )
            delivery_ids = sorted(
                {
                    tool_id
                    for kind in delivery_kinds
                    for tool_id in adapter["capabilities"][kind]["requires"]
                }
            )
            delivery = run_census("delivery", delivery_ids)
            delivered_ids = {item["id"] for item in delivery["tools"]}
            self.assertIn("scripts/wechat_publisher.py", delivered_ids)
            self.assertNotIn("scripts/ingest_browser_download.py", delivered_ids)
            self.assertIn(
                "scripts/ingest_wechat_readback_capture.py", delivered_ids
            )
            self.assertIn("browser:control-in-app-browser", delivered_ids)
            self.assertTrue(
                delivery["publication_routes"]["current_session_readback"][
                    "available"
                ]
            )
            self.assertTrue(
                delivery["publication_routes"]["draft"]["api"]["available"]
            )

    def test_install_rolls_back_all_packages_when_one_swap_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root = root / "skills"
            skills_root.mkdir()
            for package in PACKAGE_SOURCES:
                target = skills_root / package
                target.mkdir()
                (target / "old-marker.txt").write_text(package, encoding="utf-8")
            manifest_path = root / "release.json"
            write_manifest(manifest_path, ROOT)

            real_replace = __import__("os").replace
            failed = False

            def fail_last_incoming(source: object, destination: object) -> None:
                nonlocal failed
                source_path = Path(source)
                destination_path = Path(destination)
                if (
                    not failed
                    and ".org-wechat-studio.incoming-" in source_path.name
                    and destination_path.name == "org-wechat-studio"
                ):
                    failed = True
                    raise OSError("synthetic final package swap failure")
                real_replace(source, destination)

            with mock.patch("scripts.release_skills.os.replace", side_effect=fail_last_incoming):
                with self.assertRaises(OSError):
                    install_packages(skills_root, manifest_path, ROOT)

            for package in PACKAGE_SOURCES:
                self.assertEqual(
                    (skills_root / package / "old-marker.txt").read_text(
                        encoding="utf-8"
                    ),
                    package,
                )
            self.assertEqual(
                list(
                    (skills_root / ".org-wechat-release-manifests").glob(
                        "*.json"
                    )
                ),
                [],
            )


if __name__ == "__main__":
    unittest.main()
