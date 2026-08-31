from __future__ import annotations

import base64
import ast
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_preflight import (  # noqa: E402
    EXPECTED_SEMANTIC_CAPABILITIES,
    REQUIRED_PATHS,
    TRUSTED_BUNDLE_PATHS,
    _build_host_setup_actions,
    _validate_local_paths,
    validate_runtime_profile,
)


NOW = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)
VALID_KEY = "base64:" + base64.b64encode(b"runtime-preflight-test-key-material-32b").decode("ascii")
SECURE_RUNNER = [
    sys.executable,
    "-I",
    "-S",
    str(ROOT / "scripts" / "secure_runner.py"),
]
def sha256_uri(path: Path) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def probe(method: str, evidence: str, *, checked_at: datetime = NOW) -> dict[str, str]:
    return {
        "status": "passed",
        "method": method,
        "checked_at": checked_at.isoformat(),
        "evidence": evidence,
    }


def runtime_tool(
    tool_id: str,
    kind: str,
    provider: str = "test-provider",
    source: str = "runtime-registry",
) -> dict[str, str]:
    return {
        "id": tool_id,
        "kind": kind,
        "status": "available",
        "source": source,
        "provider": provider,
        "session_id": "test-session-20260831",
    }


def valid_profile() -> dict:
    return {
        "schema_version": 2,
        "kind": "org-wechat-runtime-profile",
        "harness": {
            "name": "test-host",
            "adapter_path": "tests/fixtures/host-enabled-adapter.json",
            "adapter_sha256": sha256_uri(ROOT / "tests" / "fixtures" / "host-enabled-adapter.json"),
        },
        "skills": [
            {
                "id": "org-wechat-studio",
                "entrypoint": "SKILL.md",
                "status": "loaded",
                "sha256": sha256_uri(ROOT / "SKILL.md"),
            },
            {
                "id": "ardot-wechat-publisher",
                "entrypoint": "skills/ardot-wechat-publisher/SKILL.md",
                "status": "available",
                "sha256": sha256_uri(ROOT / "skills" / "ardot-wechat-publisher" / "SKILL.md"),
            },
        ],
        "tools": [
            runtime_tool(
                "image_gen__imagegen", "image.generate.opaque", "codex-image-provider"
            ),
            runtime_tool(
                "test__rgba_generate", "image.generate.rgba", "test-rgba-provider"
            ),
            runtime_tool("view_image", "image.inspect", "codex-image-provider"),
            runtime_tool(
                "mcp__ardot_remote__fetch_file_info", "ardot.read", "ardot-remote"
            ),
            runtime_tool(
                "mcp__ardot_remote__fetch_editor_state", "ardot.read", "ardot-remote"
            ),
            runtime_tool("mcp__ardot_remote__batch_read", "ardot.read", "ardot-remote"),
            runtime_tool("mcp__ardot_remote__batch_edit", "ardot.write", "ardot-remote"),
            runtime_tool(
                "mcp__ardot_remote__capture_screenshot", "ardot.export", "ardot-remote"
            ),
            runtime_tool("mcp__ardot_remote__export_nodes", "ardot.export", "ardot-remote"),
            runtime_tool(
                "browser:control-in-app-browser",
                "browser.control",
                "codex-browser",
                "skill-registry",
            ),
            runtime_tool("mcp__node_repl__js", "browser.control", "codex-browser"),
            runtime_tool(
                "host.receipt.attest",
                "host.receipt.attest",
                "test-host-attestor",
                "runtime-registry",
            ),
        ],
        "links": {
            "ardot_current_workspace": {
                "url": "https://ardot.tencent.com/file/123456789?web_only=1&node_id=1%3A2",
                "purpose": "current test workspace",
                "probe": probe("read-only-live", "ardot-file-id-and-access-matched"),
            },
            "wechat_current_account": {
                "url": "https://mp.weixin.qq.com/",
                "purpose": "current visible target account",
                "probe": probe("read-only-live", "wechat-visible-account-matched"),
            },
        },
        "capabilities": {
            "opaque_image_generation": {
                "mode": "tool",
                "status": "bound_unprobed",
                "tool_ids": ["image_gen__imagegen"],
                "probe": probe("runtime-registry", "opaque-imagegen-schema-bound"),
            },
            "rgba_cutout_generation": {
                "mode": "tool",
                "status": "bound_unprobed",
                "tool_ids": ["test__rgba_generate"],
                "output_contract": "subject-cutout-rgba8-v1",
                "processor": "scripts/prepare_micro_cutout.py",
                "probe": probe("runtime-registry", "rgba-imagegen-schema-bound"),
            },
            "visual_inspection": {
                "mode": "tool",
                "status": "passed",
                "tool_ids": ["view_image"],
                "probe": probe("read-only-live", "neutral-local-image-read"),
            },
            "ardot_authoring": {
                "mode": "mcp",
                "status": "passed",
                "tool_ids": [
                    "mcp__ardot_remote__fetch_file_info",
                    "mcp__ardot_remote__fetch_editor_state",
                    "mcp__ardot_remote__batch_read",
                    "mcp__ardot_remote__batch_edit",
                    "mcp__ardot_remote__capture_screenshot",
                    "mcp__ardot_remote__export_nodes",
                ],
                "workspace_link": "ardot_current_workspace",
                "expected_file_id": "123456789",
                "expected_root_id": "1:2",
                "observed_file_id": "123456789",
                "observed_root_id": "1:2",
                "observed_access": "read-write-export",
                "probe": probe("read-only-live", "ardot-root-and-permission-matched"),
            },
            "wechat_delivery": {
                "mode": "ui",
                "status": "passed",
                "tool_ids": ["browser:control-in-app-browser", "mcp__node_repl__js"],
                "account_link": "wechat_current_account",
                "target_account_ref": "test-visible-account",
                "observed_account_ref": "test-visible-account",
                "observed_access": "draft-read-write",
                "probe": probe("read-only-live", "wechat-editor-account-matched"),
            },
            "host_receipt_attestation": {
                "mode": "host",
                "status": "passed",
                "tool_ids": ["host.receipt.attest"],
                "trust_boundary": "host-owned-private-key-and-protected-trust-store",
                "observed_access": "sign-live-read-and-saved-draft",
                "probe": probe("host-attested-live", "host-attestor-and-trust-store-bound"),
            },
            "secret_store": {
                "mode": "environment",
                "status": "passed",
                "secret_refs": [
                    "PROVENANCE_WATERMARK_KEY",
                ],
                "path_refs": ["PROVENANCE_WATERMARK_PRIVATE_ROOT"],
                "probe": probe("environment-reference", "watermark-key-shape-valid"),
            },
        },
    }


def select_codex_chatgpt_rgba_route(profile: dict) -> dict:
    """Bind the current Codex adapter's composite ChatGPT/IAB RGBA route."""

    profile["harness"] = {
        "name": "codex-desktop",
        "adapter_path": "runtime/adapters/codex-desktop.json",
        "adapter_sha256": sha256_uri(ROOT / "runtime" / "adapters" / "codex-desktop.json"),
    }
    profile["tools"] = [
        item for item in profile["tools"] if item["kind"] != "image.generate.rgba"
    ]
    for item in profile["tools"]:
        if item["kind"] == "browser.control":
            item["provider"] = "codex-chatgpt-browser"
            item["session_id"] = "codex-chatgpt-session-20260831"
    profile["tools"].append(
        runtime_tool(
            "codex-with-chatgpt",
            "chatgpt.session",
            "codex-chatgpt-browser",
            "skill-registry",
        )
    )
    profile["tools"][-1]["session_id"] = "codex-chatgpt-session-20260831"
    profile["capabilities"]["rgba_cutout_generation"] = {
        "mode": "chatgpt-web",
        "status": "bound_unprobed",
        "tool_ids": [
            "codex-with-chatgpt",
            "browser:control-in-app-browser",
            "mcp__node_repl__js",
        ],
        "provider_skill": {
            "id": "chatgpt-web-image-route",
            "status": "loaded",
            "contract": "chatgpt-web-image-route-v1",
        },
        "output_contract": "subject-cutout-rgba8-v1",
        "processor": "scripts/prepare_micro_cutout.py",
        "probe": probe("runtime-registry", "chatgpt-web-route-bound-no-live-image-proof"),
    }
    return profile


def error_codes(report: dict) -> set[str]:
    return {item["code"] for item in report["errors"]}


class RuntimePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.private_root_context = tempfile.TemporaryDirectory(prefix="runtime-private-")
        self.private_root = self.private_root_context.name

    def tearDown(self) -> None:
        self.private_root_context.cleanup()

    def run_check(
        self,
        profile: dict,
        phase: str = "full",
        *,
        binding_only: bool = False,
        environment: dict[str, str] | None = None,
    ) -> dict:
        return validate_runtime_profile(
            profile,
            ROOT,
            phase,
            now=NOW,
            environment=(
                {
                    "PROVENANCE_WATERMARK_KEY": VALID_KEY,
                    "PROVENANCE_WATERMARK_PRIVATE_ROOT": self.private_root,
                }
                if environment is None
                else environment
            ),
            binding_only=binding_only,
        )

    def build_minimal_workspace(self, root: Path) -> None:
        for relative in REQUIRED_PATHS:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("\n", encoding="utf-8")
        (root / "references" / "qa.md").write_text("\n", encoding="utf-8")
        (root / "runtime" / "setup-links.json").write_text(
            (ROOT / "runtime" / "setup-links.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (root / "runtime" / "adapters" / "codex-desktop.json").write_text(
            (ROOT / "runtime" / "adapters" / "codex-desktop.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def test_unattested_live_profile_cannot_claim_phase_ready(self) -> None:
        report = self.run_check(valid_profile())
        self.assertFalse(report["ok"])
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertFalse(report["phase_ready"])
        self.assertEqual(report["check_level"], "unattested")
        self.assertIn("runtime.probe.unattested", error_codes(report))
        self.assertIn(
            "runtime.capability.rgba_live_probe_deferred",
            {item["code"] for item in report["warnings"]},
        )

    def test_binding_only_checks_bindings_without_claiming_readiness(self) -> None:
        profile = valid_profile()
        for item in profile["links"].values():
            item.pop("probe")
        for item in profile["capabilities"].values():
            item.pop("probe")
            item["status"] = "declared"
        report = self.run_check(profile, binding_only=True, environment={})
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(report["binding_ready"])
        self.assertFalse(report["phase_ready"])
        self.assertEqual(report["check_level"], "binding")
        self.assertRegex(report["binding_nonce"], r"^[A-Za-z0-9_-]{32,}$")
        self.assertRegex(report["binding_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            report["resolved_capabilities"]["rgba_cutout_generation"]["live_proof"],
            "deferred-until-first-generated-asset",
        )
        self.assertRegex(
            report["python"]["cryptography_version"], r"^(?:4[3-9]|50)\."
        )
        actions = {item["id"]: item for item in report["host_setup_actions"]}
        self.assertEqual(actions["open-wechat-account"]["url"], "https://mp.weixin.qq.com/")
        self.assertIn("/file/123456789", actions["open-ardot-target"]["url"])
        self.assertEqual(
            actions["open-wechat-account"]["user_step_if_needed"],
            "scan-or-complete-wechat-login",
        )
        self.assertNotIn("token=", json.dumps(actions, ensure_ascii=False))
        self.assertTrue(actions["bind-image-inspection"]["blocking"])
        self.assertTrue(actions["bind-opaque-image-generation"]["blocking"])
        self.assertTrue(actions["bind-rgba-cutout-generation"]["blocking"])
        self.assertTrue(actions["bind-host-receipt-attestation"]["blocking"])

    def test_host_setup_actions_follow_selected_ardot_and_wechat_routes(self) -> None:
        ui_profile = valid_profile()
        ui_profile["capabilities"]["ardot_authoring"]["mode"] = "ui"
        ui_profile["capabilities"]["ardot_authoring"]["tool_ids"] = [
            "browser:control-in-app-browser",
            "mcp__node_repl__js",
        ]
        ui_profile["tools"] = [
            item for item in ui_profile["tools"] if not item["kind"].startswith("ardot.")
        ]
        ui_report = self.run_check(ui_profile, binding_only=True, environment={})
        self.assertTrue(ui_report["binding_ready"], ui_report["errors"])
        ui_actions = {
            item["id"]: item
            for item in _build_host_setup_actions(
                ui_profile,
                "full",
                {
                    "ardot_current_workspace": ui_profile["links"]["ardot_current_workspace"]["url"],
                    "wechat_current_account": "https://mp.weixin.qq.com/",
                },
            )
        }
        self.assertNotIn("connect-ardot-mcp", ui_actions)
        self.assertIn("prepare-ardot-ui-route", ui_actions)

        api_profile = valid_profile()
        api_profile["capabilities"]["wechat_delivery"]["mode"] = "api"
        api_profile["links"]["wechat_current_account"]["url"] = "https://api.weixin.qq.com/"
        api_actions = {
            item["id"]: item
            for item in _build_host_setup_actions(
                api_profile,
                "full",
                {
                    "ardot_current_workspace": api_profile["links"]["ardot_current_workspace"]["url"],
                    "wechat_current_account": "https://api.weixin.qq.com/",
                },
            )
        }
        self.assertNotIn("open-wechat-account", api_actions)
        self.assertEqual(
            api_actions["connect-wechat-api-provider"]["user_step_if_needed"],
            "authorize-wechat-api-provider",
        )

    def test_codex_chatgpt_rgba_route_is_prepared_before_ardot(self) -> None:
        profile = select_codex_chatgpt_rgba_route(valid_profile())
        profile["capabilities"].pop("wechat_delivery")
        profile["capabilities"].pop("host_receipt_attestation")
        profile["links"].pop("wechat_current_account")
        profile["tools"] = [
            item for item in profile["tools"] if item["kind"] != "host.receipt.attest"
        ]
        report = self.run_check(
            profile, phase="authoring", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        action_ids = [item["id"] for item in report["host_setup_actions"]]
        for expected in (
            "load-chatgpt-image-route-skill",
            "load-codex-with-chatgpt-skill",
            "prepare-codex-with-chatgpt",
            "open-chatgpt-image-session",
            "bind-rgba-download-processing",
        ):
            self.assertIn(expected, action_ids)
            self.assertLess(action_ids.index(expected), action_ids.index("connect-ardot-mcp"))
        actions = {item["id"]: item for item in report["host_setup_actions"]}
        self.assertEqual(
            actions["prepare-codex-with-chatgpt"]["steps"],
            ["update-check", "sandbox-allow", "doctor"],
        )
        self.assertEqual(
            actions["open-chatgpt-image-session"]["user_step_if_needed"],
            "complete-chatgpt-login-only",
        )
        self.assertNotIn("url", actions["open-chatgpt-image-session"])
        self.assertEqual(
            actions["open-chatgpt-image-session"]["target"],
            "current-c2c-session-chat-or-project-conversation",
        )
        self.assertIn(
            "first-real-generated-file",
            actions["bind-rgba-download-processing"]["expected_result"],
        )

    def test_codex_chatgpt_rgba_route_requires_skill_contract_and_one_session(self) -> None:
        profile = select_codex_chatgpt_rgba_route(valid_profile())
        profile["capabilities"].pop("wechat_delivery")
        profile["capabilities"].pop("host_receipt_attestation")
        profile["links"].pop("wechat_current_account")
        profile["tools"] = [
            item for item in profile["tools"] if item["kind"] != "host.receipt.attest"
        ]

        missing_skill = copy.deepcopy(profile)
        missing_skill["capabilities"]["rgba_cutout_generation"]["provider_skill"][
            "status"
        ] = "available"
        report = self.run_check(
            missing_skill, phase="authoring", binding_only=True, environment={}
        )
        self.assertIn("runtime.skills.provider_skill_not_loaded", error_codes(report))

        mismatched_session = copy.deepcopy(profile)
        for item in mismatched_session["tools"]:
            if item["id"] == "codex-with-chatgpt":
                item["session_id"] = "different-chatgpt-session"
        report = self.run_check(
            mismatched_session, phase="authoring", binding_only=True, environment={}
        )
        self.assertIn("runtime.capability.tool_context_mismatch", error_codes(report))

    def test_chatgpt_doctor_is_not_live_rgba_image_proof(self) -> None:
        profile = select_codex_chatgpt_rgba_route(valid_profile())
        rgba = profile["capabilities"]["rgba_cutout_generation"]
        rgba["status"] = "passed"
        rgba["probe"] = probe("c2c-doctor", "doctor-green-but-no-generated-file")
        report = self.run_check(profile)
        self.assertIn(
            "runtime.capability.rgba_session_not_live_image_proof",
            error_codes(report),
        )
        self.assertIn("runtime.probe.method_invalid", error_codes(report))

    def test_chatgpt_login_wall_blocks_live_rgba_readiness(self) -> None:
        profile = select_codex_chatgpt_rgba_route(valid_profile())
        profile["capabilities"]["rgba_cutout_generation"]["status"] = (
            "needs_user_login"
        )
        report = self.run_check(profile)
        self.assertIn(
            "runtime.capability.rgba_provider_needs_user_login",
            error_codes(report),
        )

    def test_delivery_actions_keep_image_inspection_blocking_without_generation(self) -> None:
        profile = valid_profile()
        actions = {
            item["id"]: item
            for item in _build_host_setup_actions(
                profile,
                "delivery",
                {
                    "ardot_current_workspace": profile["links"]["ardot_current_workspace"]["url"],
                    "wechat_current_account": "https://mp.weixin.qq.com/",
                },
            )
        }
        self.assertTrue(actions["bind-image-inspection"]["blocking"])
        self.assertNotIn("bind-opaque-image-generation", actions)
        self.assertNotIn("bind-rgba-cutout-generation", actions)
        self.assertNotIn("open-chatgpt-image-session", actions)

    def test_missing_opaque_image_generation_tool_is_blocking(self) -> None:
        profile = valid_profile()
        profile["tools"] = [
            item for item in profile["tools"] if item["kind"] != "image.generate.opaque"
        ]
        report = self.run_check(profile)
        self.assertFalse(report["ok"])
        self.assertIn("runtime.capability.tool_unresolved", error_codes(report))

    def test_rgba_tool_route_requires_cutout_contract_and_processor(self) -> None:
        profile = valid_profile()
        profile["capabilities"]["rgba_cutout_generation"]["output_contract"] = (
            "generic-png"
        )
        profile["capabilities"]["rgba_cutout_generation"]["processor"] = (
            "scripts/inspect_asset.py"
        )
        report = self.run_check(profile, binding_only=True, environment={})
        codes = error_codes(report)
        self.assertIn("runtime.capability.rgba_output_contract_mismatch", codes)
        self.assertIn("runtime.capability.rgba_processor_mismatch", codes)

    def test_ardot_mcp_requires_read_write_and_export(self) -> None:
        profile = valid_profile()
        profile["capabilities"]["ardot_authoring"]["tool_ids"] = [
            "mcp__ardot_remote__fetch_file_info"
        ]
        report = self.run_check(profile)
        self.assertIn("runtime.capability.tool_kind_mismatch", error_codes(report))

    def test_ardot_similar_host_and_nonstandard_port_are_rejected(self) -> None:
        for url, expected in (
            ("https://ardot.tencent.com.evil.example/file/123", "runtime.link.ardot_host_untrusted"),
            ("https://ardot.tencent.com:8443/file/123", "runtime.link.port_forbidden"),
            ("https://ardot.tencent.com:not-a-port/file/123", "runtime.link.port_invalid"),
        ):
            with self.subTest(url=url):
                profile = valid_profile()
                profile["links"]["ardot_current_workspace"]["url"] = url
                report = self.run_check(profile)
                self.assertIn(expected, error_codes(report))

    def test_ardot_path_query_and_fragment_are_rejected(self) -> None:
        for url, expected in (
            ("https://ardot.tencent.com/other/123", "runtime.link.ardot_path_invalid"),
            ("https://ardot.tencent.com/file/123?token=abc", "runtime.link.secret_query_forbidden"),
            ("https://ardot.tencent.com/file/123?auth=opaque", "runtime.link.query_forbidden"),
            ("https://ardot.tencent.com/file/123#private", "runtime.link.ardot_fragment_forbidden"),
        ):
            with self.subTest(url=url):
                profile = valid_profile()
                profile["links"]["ardot_current_workspace"]["url"] = url
                report = self.run_check(profile)
                self.assertIn(expected, error_codes(report))

    def test_wechat_session_query_is_never_persisted(self) -> None:
        profile = valid_profile()
        profile["links"]["wechat_current_account"]["url"] = (
            "https://mp.weixin.qq.com/cgi-bin/home?lang=zh_CN&token=123456"
        )
        report = self.run_check(profile)
        codes = error_codes(report)
        self.assertIn("runtime.link.secret_query_forbidden", codes)
        self.assertNotIn("token=123456", json.dumps(report, ensure_ascii=False))

    def test_inline_secret_fields_and_values_are_rejected_and_redacted(self) -> None:
        profile = valid_profile()
        profile["app_secret"] = "base64:" + "A" * 64
        profile["client_secret"] = "plain-secret-must-not-survive"
        report = self.run_check(profile)
        codes = error_codes(report)
        self.assertIn("runtime.secret.inline_field_forbidden", codes)
        self.assertIn("runtime.secret.inline_value_forbidden", codes)
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("A" * 64, serialized)
        self.assertNotIn("plain-secret-must-not-survive", serialized)

    def test_secret_token_shapes_and_unbound_urls_never_reach_report(self) -> None:
        profile = valid_profile()
        profile["raw_watermark_id"] = "wm-private-record"
        profile["opaque_value"] = "sk-proj-this-is-a-secret-token-value"
        profile["links"]["unbound_external"] = {
            "url": "https://evil.example/private/path",
            "purpose": "must be rejected",
        }
        report = self.run_check(profile, binding_only=True, environment={})
        codes = error_codes(report)
        self.assertIn("runtime.secret.inline_field_forbidden", codes)
        self.assertIn("runtime.secret.inline_value_forbidden", codes)
        self.assertIn("runtime.link.unbound", codes)
        self.assertIn("runtime.link.host_untrusted", codes)
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("sk-proj-this-is-a-secret-token-value", serialized)
        self.assertNotIn("evil.example", serialized)

    def test_secret_shaped_tool_identifier_is_redacted_from_failure_report(self) -> None:
        profile = valid_profile()
        secret_shaped_id = "sk-proj-FAKESECRET1234567890"
        profile["tools"][0]["id"] = secret_shaped_id
        profile["capabilities"]["opaque_image_generation"]["tool_ids"] = [secret_shaped_id]
        report = self.run_check(profile, binding_only=True, environment={})
        self.assertFalse(report["ok"])
        self.assertIn("runtime.secret.inline_value_forbidden", error_codes(report))
        self.assertNotIn(secret_shaped_id, json.dumps(report, ensure_ascii=False))

    def test_fake_tool_id_is_not_in_selected_adapter(self) -> None:
        profile = valid_profile()
        profile["tools"][0]["id"] = "fake.image.generator"
        profile["capabilities"]["opaque_image_generation"]["tool_ids"] = [
            "fake.image.generator"
        ]
        report = self.run_check(profile, binding_only=True, environment={})
        self.assertIn("runtime.tools.adapter_route_unresolved", error_codes(report))

    def test_harness_identity_and_adapter_sha_are_bound(self) -> None:
        profile = valid_profile()
        profile["harness"]["name"] = "different-harness"
        profile["harness"]["adapter_sha256"] = "sha256:" + "0" * 64
        report = self.run_check(profile, binding_only=True, environment={})
        codes = error_codes(report)
        self.assertIn("runtime.profile.adapter_sha256_mismatch", codes)
        self.assertIn("runtime.profile.adapter_contract_mismatch", codes)

    def test_stale_live_probe_is_blocking(self) -> None:
        profile = valid_profile()
        profile["capabilities"]["ardot_authoring"]["probe"] = probe(
            "read-only-live",
            "stale-probe",
            checked_at=NOW - timedelta(hours=2),
        )
        report = self.run_check(profile)
        self.assertIn("runtime.probe.stale", error_codes(report))

    def test_live_ardot_file_and_wechat_account_must_match_expected_identity(self) -> None:
        profile = valid_profile()
        profile["capabilities"]["ardot_authoring"]["observed_file_id"] = "999999999"
        profile["capabilities"]["ardot_authoring"]["observed_root_id"] = "9:9"
        profile["capabilities"]["wechat_delivery"]["observed_account_ref"] = "other-account"
        report = self.run_check(profile)
        codes = error_codes(report)
        self.assertIn("runtime.capability.ardot_observed_file_mismatch", codes)
        self.assertIn("runtime.capability.ardot_observed_root_mismatch", codes)
        self.assertIn("runtime.capability.wechat_account_mismatch", codes)

    def test_login_page_cannot_be_reported_as_wechat_ready(self) -> None:
        profile = valid_profile()
        profile["capabilities"]["wechat_delivery"]["status"] = "needs_user_login"
        profile["capabilities"]["wechat_delivery"].pop("observed_account_ref")
        profile["capabilities"]["wechat_delivery"].pop("observed_access")
        report = self.run_check(profile)
        self.assertIn("runtime.capability.wechat_needs_user_login", error_codes(report))

    def test_missing_or_short_watermark_key_is_blocking(self) -> None:
        missing = self.run_check(valid_profile(), environment={})
        self.assertIn("runtime.secret.ref_unresolved", error_codes(missing))
        short = self.run_check(
            valid_profile(),
            environment={
                "PROVENANCE_WATERMARK_KEY": "base64:YWJj",
                "PROVENANCE_WATERMARK_PRIVATE_ROOT": self.private_root,
            },
        )
        self.assertIn("runtime.secret.watermark_key_invalid", error_codes(short))
        self.assertNotIn("base64:YWJj", json.dumps(short, ensure_ascii=False))

    def test_delivery_requires_host_receipt_attestation_tool_and_trust_boundary(self) -> None:
        missing_tool = valid_profile()
        missing_tool["tools"] = [
            item for item in missing_tool["tools"] if item["kind"] != "host.receipt.attest"
        ]
        report = self.run_check(missing_tool, binding_only=True, environment={})
        self.assertIn("runtime.capability.tool_unresolved", error_codes(report))

        repository_key = valid_profile()
        repository_key["capabilities"]["host_receipt_attestation"]["trust_boundary"] = (
            "repository-environment-key"
        )
        report = self.run_check(repository_key, binding_only=True, environment={})
        self.assertIn(
            "runtime.capability.host_receipt_trust_boundary_invalid",
            error_codes(report),
        )

    def test_private_registry_root_must_be_git_external_and_not_a_symlink(self) -> None:
        inside_git = self.run_check(
            valid_profile(),
            environment={
                "PROVENANCE_WATERMARK_KEY": VALID_KEY,
                "PROVENANCE_WATERMARK_PRIVATE_ROOT": str(ROOT),
            },
        )
        self.assertIn("runtime.private_root.inside_git", error_codes(inside_git))

        private_base = Path(self.private_root)
        target = private_base / "target"
        target.mkdir()
        link = private_base / "link"
        link.symlink_to(target, target_is_directory=True)
        symlinked = self.run_check(
            valid_profile(),
            environment={
                "PROVENANCE_WATERMARK_KEY": VALID_KEY,
                "PROVENANCE_WATERMARK_PRIVATE_ROOT": str(link),
            },
        )
        self.assertIn("runtime.private_root.symlink_forbidden", error_codes(symlinked))

    def test_skill_hash_drift_is_blocking(self) -> None:
        profile = valid_profile()
        profile["skills"][1]["sha256"] = "sha256:" + "0" * 64
        report = self.run_check(profile)
        self.assertIn("runtime.skills.sha256_mismatch", error_codes(report))

    def test_phase_specific_skill_must_be_loaded(self) -> None:
        profile = valid_profile()
        profile["capabilities"].pop("opaque_image_generation")
        profile["capabilities"].pop("rgba_cutout_generation")
        profile["tools"] = [
            item
            for item in profile["tools"]
            if item["kind"] not in {"image.generate.opaque", "image.generate.rgba"}
        ]
        profile["skills"][0]["status"] = "available"
        profile["skills"][1]["status"] = "loaded"
        report = self.run_check(profile, phase="delivery", binding_only=True, environment={})
        self.assertTrue(report["binding_ready"], report["errors"])

        profile["skills"][1]["status"] = "available"
        report = self.run_check(profile, phase="delivery", binding_only=True, environment={})
        self.assertIn("runtime.skills.phase_skill_not_loaded", error_codes(report))

    def test_capability_tools_cannot_mix_provider_sessions(self) -> None:
        profile = valid_profile()
        for item in profile["tools"]:
            if item["id"] == "mcp__ardot_remote__export_nodes":
                item["session_id"] = "different-session"
        report = self.run_check(profile, binding_only=True, environment={})
        self.assertIn("runtime.capability.tool_context_mismatch", error_codes(report))

    def test_setup_registry_and_codex_adapter_cover_exact_capabilities(self) -> None:
        setup = json.loads((ROOT / "runtime" / "setup-links.json").read_text(encoding="utf-8"))
        adapter = json.loads(
            (ROOT / "runtime" / "adapters" / "codex-desktop.json").read_text(encoding="utf-8")
        )
        self.assertEqual(setup["schema_version"], 2)
        self.assertEqual(adapter["schema_version"], 2)
        self.assertEqual(setup["semantic_capabilities"], list(EXPECTED_SEMANTIC_CAPABILITIES))
        self.assertEqual(set(adapter["capabilities"]), set(EXPECTED_SEMANTIC_CAPABILITIES))
        self.assertIn("routing-only", adapter["truth_boundary"])
        host_route = adapter["capabilities"]["host.receipt.attest"]
        self.assertEqual(host_route["availability"], "unavailable")
        self.assertEqual(host_route["requires"], [])
        self.assertIn("no callable", host_route["reason"])
        self.assertTrue(setup["startup_policy"]["wait_for_user_login"])
        self.assertFalse(setup["startup_policy"]["persist_session_query"])
        self.assertEqual(setup["external"]["chatgpt_web"]["url"], "https://chatgpt.com/")
        rgba_route = adapter["capabilities"]["image.generate.rgba"]
        self.assertEqual(rgba_route["route"], "chatgpt-web")
        self.assertEqual(rgba_route["output_contract"], "subject-cutout-rgba8-v1")
        self.assertEqual(rgba_route["processor"], "scripts/prepare_micro_cutout.py")
        self.assertEqual(
            rgba_route["provider_skill"]["contract"], "chatgpt-web-image-route-v1"
        )

    def test_current_codex_adapter_blocks_delivery_but_keeps_authoring_available(self) -> None:
        delivery = select_codex_chatgpt_rgba_route(valid_profile())
        delivery["tools"] = [
            item for item in delivery["tools"] if item["kind"] != "host.receipt.attest"
        ]
        report = self.run_check(delivery, binding_only=True, environment={})
        self.assertFalse(report["binding_ready"])
        self.assertIn(
            "runtime.capability.host_receipt_attestation_unavailable",
            error_codes(report),
        )

        authoring = copy.deepcopy(delivery)
        authoring["capabilities"].pop("wechat_delivery")
        authoring["capabilities"].pop("host_receipt_attestation")
        authoring["links"].pop("wechat_current_account")
        report = self.run_check(
            authoring, phase="authoring", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])

    def test_delivery_transport_chain_is_required_and_digest_bound(self) -> None:
        critical = {
            "requirements.txt",
            "runtime/python-dependency-lock.json",
            "skills/chatgpt-web-image-route/SKILL.md",
            "skills/chatgpt-web-image-route/references/image-generation-contract.md",
            "references/使用说明.md",
            "references/organization-pack-migration.md",
            "references/source-zero-audit.md",
            "references/style-options.md",
            "references/onboarding.md",
            "references/org-pack-schema.md",
            "references/visual-calibration.md",
            "references/article-schema.md",
            "references/storyboard.md",
            "references/interaction-composition.md",
            "references/expressive-typography.md",
            "references/ardot-workflow.md",
            "references/organic-layout.md",
            "references/visual-review.md",
            "references/information-density.md",
            "references/qa.md",
            "references/provenance-watermark.md",
            "references/ardot-transport-fidelity.md",
            "scripts/asset_quality.py",
            "scripts/build_visual_directions.py",
            "scripts/build_storyboard.py",
            "scripts/build_visual_kit.py",
            "scripts/inspect_asset.py",
            "scripts/prepare_micro_cutout.py",
            "scripts/build_ardot_manifest.py",
            "scripts/build_visual_review.py",
            "scripts/compile_wechat.py",
            "scripts/orgs.py",
            "scripts/provenance_watermark.py",
            "scripts/secure_runner.py",
            "scripts/secure_runtime.py",
            "scripts/transport_fidelity.py",
            "scripts/validate_transport_fidelity.py",
            "scripts/validate_workflow_attribution.py",
            "scripts/wechat_interaction_policy.py",
            "scripts/workflow_quality.py",
            "style-presets/prismatic-paper-editorial.json",
            "skills/ardot-wechat-publisher/references/handoff-contract.md",
            "skills/ardot-wechat-publisher/references/wechat-api-delivery.md",
            "skills/ardot-wechat-publisher/references/wechat-interaction-capability.md",
        }
        self.assertTrue(critical.issubset(set(REQUIRED_PATHS)))
        self.assertTrue(critical.issubset(set(TRUSTED_BUNDLE_PATHS)))

        pending = ["compile_wechat", "transport_fidelity", "validate_transport_fidelity"]
        imported_scripts: set[str] = set()
        while pending:
            module = pending.pop()
            relative = f"scripts/{module}.py"
            if relative in imported_scripts or not (ROOT / relative).is_file():
                continue
            imported_scripts.add(relative)
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names.add(node.module.split(".", 1)[0])
                elif isinstance(node, ast.Import):
                    names.update(alias.name.split(".", 1)[0] for alias in node.names)
            pending.extend(
                name for name in names if (ROOT / "scripts" / f"{name}.py").is_file()
            )
        self.assertTrue(imported_scripts.issubset(set(TRUSTED_BUNDLE_PATHS)))

    def test_transitive_validator_change_alters_trusted_bundle_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            self.build_minimal_workspace(workspace)
            errors: list[dict[str, str]] = []
            baseline = _validate_local_paths(workspace, errors)["trusted_bundle_sha256"]
            dependency = workspace / "scripts" / "asset_quality.py"
            dependency.write_text("# changed validator\n", encoding="utf-8")
            changed = _validate_local_paths(workspace, [])["trusted_bundle_sha256"]
            self.assertNotEqual(baseline, changed)

    def test_wechat_ui_can_use_computer_use_without_browser_route(self) -> None:
        profile = valid_profile()
        profile["tools"] = [
            item
            for item in profile["tools"]
            if item["id"] != "browser:control-in-app-browser"
        ]
        for item in profile["tools"]:
            if item["id"] == "mcp__node_repl__js":
                item.update(
                    {
                        "kind": "computer.use",
                        "provider": "codex-computer",
                        "source": "runtime-registry",
                    }
                )
        profile["tools"].append(
            runtime_tool(
                "computer-use:computer-use",
                "computer.use",
                "codex-computer",
                "skill-registry",
            )
        )
        profile["capabilities"]["wechat_delivery"]["tool_ids"] = [
            "computer-use:computer-use",
            "mcp__node_repl__js",
        ]
        report = self.run_check(profile, binding_only=True, environment={})
        self.assertTrue(report["binding_ready"], report["errors"])

    def test_local_gate_rejects_symlinked_required_files_and_non_object_registries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            self.build_minimal_workspace(workspace)
            required = workspace / "scripts" / "orgs.py"
            required.unlink()
            required.symlink_to(ROOT / "scripts" / "orgs.py")
            (workspace / "runtime" / "setup-links.json").write_text("[]\n", encoding="utf-8")
            errors: list[dict[str, str]] = []
            _validate_local_paths(workspace, errors)
            codes = {item["code"] for item in errors}
            self.assertIn("runtime.local.required_file_missing_or_untrusted", codes)
            self.assertIn("runtime.local.setup_links_schema_invalid", codes)

    def test_tracked_runtime_registries_are_secret_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            self.build_minimal_workspace(workspace)
            setup = json.loads((workspace / "runtime" / "setup-links.json").read_text(encoding="utf-8"))
            setup["client_secret"] = "must-not-be-accepted"
            (workspace / "runtime" / "setup-links.json").write_text(
                json.dumps(setup), encoding="utf-8"
            )
            errors: list[dict[str, str]] = []
            _validate_local_paths(workspace, errors)
            self.assertIn(
                "runtime.secret.inline_field_forbidden",
                {item["code"] for item in errors},
            )

    def test_active_agent_mcp_endpoint_is_semantically_locked_and_hashed(self) -> None:
        baseline_errors: list[dict[str, str]] = []
        baseline = _validate_local_paths(ROOT, baseline_errors)
        self.assertNotIn("runtime.local.agent_mcp_url_invalid", {item["code"] for item in baseline_errors})
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            self.build_minimal_workspace(workspace)
            for relative in (
                "agents/openai.yaml",
                "skills/ardot-wechat-publisher/agents/openai.yaml",
            ):
                source = ROOT / relative
                destination = workspace / relative
                destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            clean_errors: list[dict[str, str]] = []
            clean = _validate_local_paths(workspace, clean_errors)
            self.assertNotIn(
                "runtime.local.agent_mcp_url_invalid",
                {item["code"] for item in clean_errors},
            )
            manifest = workspace / "agents" / "openai.yaml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "https://ardot.tencent.com/mcp",
                    "https://evil.example/mcp",
                ),
                encoding="utf-8",
            )
            drift_errors: list[dict[str, str]] = []
            drift = _validate_local_paths(workspace, drift_errors)
            self.assertIn(
                "runtime.local.agent_mcp_url_invalid",
                {item["code"] for item in drift_errors},
            )
            self.assertNotEqual(
                clean["trusted_bundle_sha256"],
                drift["trusted_bundle_sha256"],
            )

    def test_probe_age_cannot_be_relaxed_past_policy_maximum(self) -> None:
        with self.assertRaises(ValueError):
            validate_runtime_profile(
                valid_profile(),
                ROOT,
                "full",
                now=NOW,
                max_age_minutes=61,
                environment={},
                binding_only=True,
            )

    def test_authoring_phase_can_omit_wechat_but_reports_full_gap(self) -> None:
        profile = valid_profile()
        profile["capabilities"].pop("wechat_delivery")
        profile["capabilities"].pop("host_receipt_attestation")
        profile["links"].pop("wechat_current_account")
        profile["tools"] = [
            item
            for item in profile["tools"]
            if item["kind"] not in {"browser.control", "host.receipt.attest"}
        ]
        report = self.run_check(profile, phase="authoring", binding_only=True, environment={})
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertFalse(report["phase_ready"])
        self.assertIn(
            "runtime.capability.out_of_phase_missing",
            {item["code"] for item in report["warnings"]},
        )

    def test_bootstrap_phase_does_not_require_an_existing_ardot_file(self) -> None:
        profile = valid_profile()
        profile["links"].pop("ardot_current_workspace")
        profile["links"].pop("wechat_current_account")
        profile["capabilities"].pop("ardot_authoring")
        profile["capabilities"].pop("wechat_delivery")
        profile["capabilities"].pop("host_receipt_attestation")
        profile["capabilities"].pop("opaque_image_generation")
        profile["capabilities"].pop("rgba_cutout_generation")
        profile["capabilities"].pop("visual_inspection")
        profile["capabilities"].pop("secret_store")
        profile["tools"] = []
        profile["tools"].append(
            runtime_tool(
                "mcp__ardot_remote__create_design", "ardot.create", "ardot-remote"
            )
        )
        profile["tools"].append(
            runtime_tool(
                "mcp__ardot_remote__create_new_page", "ardot.create", "ardot-remote"
            )
        )
        profile["capabilities"]["ardot_bootstrap"] = {
            "mode": "mcp",
            "status": "declared",
            "tool_ids": [
                "mcp__ardot_remote__create_design",
                "mcp__ardot_remote__create_new_page",
            ],
        }
        report = self.run_check(profile, phase="bootstrap", binding_only=True, environment={})
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertNotIn("runtime.capability.ardot_link_unresolved", error_codes(report))
        actions = {item["id"]: item for item in report["host_setup_actions"]}
        self.assertEqual(actions["open-ardot-target"]["url"], "https://ardot.tencent.com/")
        self.assertEqual(
            actions["open-ardot-target"]["expected_result"],
            "blank-design-create-route-ready",
        )
        self.assertNotIn("open-wechat-account", actions)
        self.assertNotIn("open-chatgpt-image-session", actions)
        self.assertNotIn("bind-image-inspection", actions)
        self.assertNotIn("resolve-watermark-runtime", actions)

    def test_cli_writes_binding_report_and_returns_success(self) -> None:
        profile = valid_profile()
        current = datetime.now(timezone.utc)
        for item in profile["links"].values():
            item["probe"]["checked_at"] = current.isoformat()
        for item in profile["capabilities"].values():
            item["probe"]["checked_at"] = current.isoformat()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "profile.json"
            output_path = root / "report.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            env = dict(os.environ)
            env["PROVENANCE_WATERMARK_KEY"] = VALID_KEY
            private_root = root / "private-watermark-registry"
            private_root.mkdir()
            env["PROVENANCE_WATERMARK_PRIVATE_ROOT"] = str(private_root)
            completed = subprocess.run(
                [
                    *SECURE_RUNNER,
                    str(ROOT / "scripts" / "runtime_preflight.py"),
                    str(profile_path),
                    "--phase",
                    "full",
                    "--workspace-root",
                    str(ROOT),
                    "--output",
                    str(output_path),
                    "--binding-only",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(report["binding_ready"])
            self.assertFalse(report["phase_ready"])

    def test_cli_rejects_unattested_live_claims(self) -> None:
        profile = valid_profile()
        current = datetime.now(timezone.utc)
        for item in profile["links"].values():
            item["probe"]["checked_at"] = current.isoformat()
        for item in profile["capabilities"].values():
            item["probe"]["checked_at"] = current.isoformat()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "profile.json"
            output_path = root / "report.json"
            private_root = root / "private-watermark-registry"
            private_root.mkdir()
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            env = dict(os.environ)
            env["PROVENANCE_WATERMARK_KEY"] = VALID_KEY
            env["PROVENANCE_WATERMARK_PRIVATE_ROOT"] = str(private_root)
            completed = subprocess.run(
                [
                    *SECURE_RUNNER,
                    str(ROOT / "scripts" / "runtime_preflight.py"),
                    str(profile_path),
                    "--workspace-root",
                    str(ROOT),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 1)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("runtime.probe.unattested", error_codes(report))
            self.assertFalse(report["phase_ready"])

    def test_cli_never_overwrites_an_existing_report(self) -> None:
        profile = valid_profile()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "profile.json"
            output_path = root / "report.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            output_path.write_text("preserve-me\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    *SECURE_RUNNER,
                    str(ROOT / "scripts" / "runtime_preflight.py"),
                    str(profile_path),
                    "--workspace-root",
                    str(ROOT),
                    "--output",
                    str(output_path),
                    "--binding-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "preserve-me\n")

    def test_cli_rejects_artifacts_inside_another_git_repository(self) -> None:
        profile = valid_profile()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            profile_path = root / "profile.json"
            output_path = root / "report.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            completed = subprocess.run(
                [
                    *SECURE_RUNNER,
                    str(ROOT / "scripts" / "runtime_preflight.py"),
                    str(profile_path),
                    "--workspace-root",
                    str(ROOT),
                    "--output",
                    str(output_path),
                    "--binding-only",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
