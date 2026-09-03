from __future__ import annotations

import ast
import base64
import copy
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_preflight import (  # noqa: E402
    EXPECTED_SEMANTIC_CAPABILITIES,
    EXPECTED_LOCAL_SETUP_LINKS,
    MIGRATION_RGBA_PROBE_CONTRACT,
    REQUIRED_PATHS,
    TRUSTED_BUNDLE_PATHS,
    _artifact_location_is_private,
    _build_host_setup_actions,
    _private_create_once_output,
    _validate_local_paths,
    build_current_session_registry_census,
    build_host_registry_census,
    build_runtime_profile_from_census,
    finalize_current_session_migration,
    finalize_migration_binding_report,
    validate_runtime_profile,
)
from ingest_browser_download import ingest_download  # noqa: E402
from prepare_migration_probe import prepare_migration_probe  # noqa: E402
from release_skills import (  # noqa: E402
    build_manifest,
    install_packages,
    write_manifest,
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


def source_zero_policy(phase: str) -> tuple[dict, str]:
    roles = {
        "migration": ["current-runtime-output"],
        "bootstrap": ["current-runtime-output"],
        "authoring": ["current-source-input", "current-pack", "current-runtime-output"],
        "delivery": ["current-pack", "current-article", "current-runtime-output"],
        "full": ["current-source-input", "current-pack", "current-runtime-output"],
    }[phase]
    policy = {
        "schema_version": 1,
        "kind": "org-wechat-source-zero-filesystem-policy-v1",
        "phase": phase,
        "scope_id": "test-current-organization",
        "deny_by_default": True,
        "deny_legacy_ardot_references": True,
        "allow": [
            {"role": role, "path": f"/private/test/{role}"}
            for role in roles
        ],
        "deny": [
            {"role": "examples", "path": "examples/**"},
            {"role": "other-organizations", "path": "organizations/*-except-current"},
            {"role": "legacy-output", "path": "output/*-except-current"},
            {"role": "legacy-ardot-references", "path": "ardot/*-except-current"},
        ],
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return policy, digest


def installed_registry_for(profile: dict) -> dict:
    return {
        "verified": True,
        "release_sha256": "test-release-sha256",
        "registry_digest": "sha256:" + "1" * 64,
        "census_sha256": "sha256:" + "2" * 64,
        "skills": {
            item["id"]: {
                "id": item["id"],
                "installed_entrypoint": str((ROOT / item["entrypoint"]).resolve()),
                "entrypoint_sha256": item["sha256"],
                "registry_status": item["status"],
            }
            for item in profile.get("skills", [])
        },
        "tools": {
            item["id"]: copy.deepcopy(item) for item in profile.get("tools", [])
        },
    }


def valid_profile() -> dict:
    policy, policy_sha = source_zero_policy("full")
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
            runtime_tool(
                "host.image.provider.acquire.authority",
                "image.provider.acquire.authority",
                "test-host-authority",
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
            runtime_tool(
                "host.filesystem.lease",
                "filesystem.access.lease",
                "test-host-policy",
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
            "filesystem_access_lease": {
                "mode": "host",
                "status": "passed",
                "tool_ids": ["host.filesystem.lease"],
                "policy": policy,
                "policy_sha256": policy_sha,
                "lease": {
                    "lease_id": "test-filesystem-lease-20260831",
                    "policy_sha256": policy_sha,
                    "host_enforced": True,
                    "deny_by_default": True,
                },
                "probe": probe("host-enforced-live", "source-zero-lease-active"),
            },
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
                "generation_route_id": "test-rgba-provider-v1",
                "probe": probe("runtime-registry", "rgba-imagegen-schema-bound"),
            },
            "provider_acquisition_authority": {
                "mode": "host",
                "status": "passed",
                "tool_ids": ["host.image.provider.acquire.authority"],
                "trust_boundary": "trusted-harness-policy-hook-no-assurance-upgrade",
                "authority_mode": "policy-hook-only",
                "observed_access": (
                    "evaluate-exact-provider-acquisition-challenge-as-policy-hook"
                ),
                "probe": probe(
                    "host-policy-hook",
                    "exact-provider-acquisition-challenge-policy-evaluated",
                ),
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
        item
        for item in profile["tools"]
        if item["kind"]
        not in {
            "image.generate.rgba",
            "image.provider.acquire.authority",
            "filesystem.access.lease",
        }
    ]
    profile["capabilities"].pop("filesystem_access_lease", None)
    profile["capabilities"].pop("provider_acquisition_authority", None)
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
    profile["tools"].append(
        runtime_tool(
            "scripts/ingest_browser_download.py",
            "browser.download.ingest",
            "codex-chatgpt-browser",
            "runtime-registry",
        )
    )
    profile["tools"][-1]["session_id"] = "codex-chatgpt-session-20260831"
    profile["skills"].append(
        {
            "id": "chatgpt-web-image-route",
            "entrypoint": "skills/chatgpt-web-image-route/SKILL.md",
            "status": "loaded",
            "sha256": sha256_uri(ROOT / "skills" / "chatgpt-web-image-route" / "SKILL.md"),
        }
    )
    profile["capabilities"]["rgba_cutout_generation"] = {
        "mode": "chatgpt-web",
        "status": "bound_unprobed",
        "tool_ids": [
            "codex-with-chatgpt",
            "browser:control-in-app-browser",
            "mcp__node_repl__js",
        ],
        "download_ingest_tool_ids": [
            "browser:control-in-app-browser",
            "mcp__node_repl__js",
            "scripts/ingest_browser_download.py",
        ],
        "provider_skill": {
            "id": "chatgpt-web-image-route",
            "status": "loaded",
            "contract": "chatgpt-web-image-route-v1",
        },
        "output_contract": "subject-cutout-rgba8-v1",
        "processor": "scripts/prepare_micro_cutout.py",
        "generation_route_id": "chatgpt-web-image-route-v1",
        "probe": probe("runtime-registry", "chatgpt-web-route-bound-no-live-image-proof"),
    }
    return profile


def select_migration_profile(profile: dict) -> dict:
    """Keep only the image-route capabilities used by migration stage zero."""

    profile["links"] = {}
    profile["capabilities"] = {
        name: item
        for name, item in profile["capabilities"].items()
        if name
        in {
            "filesystem_access_lease",
            "opaque_image_generation",
            "rgba_cutout_generation",
            "visual_inspection",
        }
    }
    profile["capabilities"]["rgba_cutout_generation"][
        "migration_probe_contract"
    ] = MIGRATION_RGBA_PROBE_CONTRACT
    profile["capabilities"]["rgba_cutout_generation"]["generation_route_id"] = (
        "chatgpt-web-image-route-v1"
        if profile["capabilities"]["rgba_cutout_generation"]["mode"]
        == "chatgpt-web"
        else "test-rgba-provider-v1"
    )
    policy, policy_sha = source_zero_policy("migration")
    filesystem = profile["capabilities"].get("filesystem_access_lease")
    if isinstance(filesystem, dict):
        filesystem["policy"] = policy
        filesystem["policy_sha256"] = policy_sha
        filesystem["lease"]["policy_sha256"] = policy_sha
    if profile.get("harness", {}).get("name") == "test-host":
        profile["capabilities"]["migration_probe_finalization"] = {
            "mode": "host",
            "status": "passed",
            "tool_ids": ["host.migration.finalize"],
            "trust_boundary": "host-owned-private-key-protected-trust-store-and-replay-ledger",
            "probe": probe("host-attested-live", "migration-finalizer-and-ledger-active"),
        }
        profile["tools"].append(
            runtime_tool(
                "host.migration.finalize",
                "host.migration.finalize",
                "test-host-policy",
                "runtime-registry",
            )
        )
    used_tool_ids = {
        tool_id
        for capability in profile["capabilities"].values()
        for field in ("tool_ids", "download_ingest_tool_ids")
        for tool_id in capability.get(field, [])
    }
    profile["tools"] = [
        item for item in profile["tools"] if item["id"] in used_tool_ids
    ]
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
        installed_registry_override: dict | None = None,
    ) -> dict:
        profile = copy.deepcopy(profile)
        filesystem = profile.get("capabilities", {}).get("filesystem_access_lease")
        if isinstance(filesystem, dict):
            policy, policy_sha = source_zero_policy(phase)
            filesystem["policy"] = policy
            filesystem["policy_sha256"] = policy_sha
            if isinstance(filesystem.get("lease"), dict):
                filesystem["lease"]["policy_sha256"] = policy_sha
        if installed_registry_override is None:
            installed_registry_override = installed_registry_for(profile)
        return validate_runtime_profile(
            profile,
            ROOT,
            phase,
            session_root=Path(self.private_root).resolve(),
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
            installed_registry_override=installed_registry_override,
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

    def attach_real_registry_census(
        self, profile: dict, root: Path
    ) -> tuple[Path, Path, Path]:
        source_manifest = root / "source-release-manifest.json"
        skills_root = root / "installed-skills"
        write_manifest(source_manifest, ROOT)
        installed = install_packages(skills_root, source_manifest, ROOT)
        manifest_path = Path(installed["installed_manifest"])
        raw_registry = {
            "schema_version": 1,
            "kind": "org-wechat-host-registry-export-v1",
            "harness": profile["harness"]["name"],
            "session_id": "test-session-20260831",
            "registry_export": {
                "capability": "host.registry.export",
                "tool_id": "host.registry.export",
                "provider": "test-host-registry",
                "session_id": "test-session-20260831",
                "request_id": "registry-export-request-20260831",
            },
            "tools": copy.deepcopy(profile["tools"])
            + [
                runtime_tool(
                    "host.registry.export",
                    "host.registry.export",
                    "test-host-registry",
                )
            ],
            "skills": [
                {
                    "id": item["id"],
                    "status": item["status"],
                    "installed_entrypoint": str(
                        (skills_root / item["id"] / "SKILL.md").resolve()
                    ),
                }
                for item in profile["skills"]
            ]
            + (
                []
                if any(
                    item["id"] == "chatgpt-web-image-route"
                    for item in profile["skills"]
                )
                else [
                    {
                        "id": "chatgpt-web-image-route",
                        "status": "available",
                        "installed_entrypoint": str(
                            (
                                skills_root
                                / "chatgpt-web-image-route"
                                / "SKILL.md"
                            ).resolve()
                        ),
                    }
                ]
            ),
        }
        census = build_host_registry_census(
            raw_registry,
            ROOT,
            adapter_path=ROOT / profile["harness"]["adapter_path"],
            skills_root=skills_root,
            release_manifest_path=manifest_path,
        )
        census_path = root / "registry-census.json"
        census_path.write_text(
            json.dumps(census, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        profile["registry_census"] = {
            "path": str(census_path),
            "sha256": sha256_uri(census_path),
        }
        installed_skills = {
            item["id"]: item for item in census["skills"]
        }
        for item in profile["skills"]:
            installed = installed_skills[item["id"]]
            item["entrypoint"] = installed["installed_entrypoint"]
            item["sha256"] = installed["entrypoint_sha256"]
            item["status"] = installed["registry_status"]
        return census_path, manifest_path, skills_root

    def create_probe_artifacts(
        self, binding_report: dict, source_root: Path
    ) -> dict:
        action = next(
            item
            for item in binding_report["host_setup_actions"]
            if item["id"] == "run-migration-rgba-route-probe"
        )
        case = action["probe_cases"][0]
        artifact_root_relative = action["artifact_root"]
        artifact_root = ROOT / artifact_root_relative
        artifact_root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(lambda: shutil.rmtree(artifact_root, ignore_errors=True))

        source = source_root.resolve() / "browser-download.png"
        image = Image.new("RGBA", (440, 400), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        points = [
            (35, 180),
            (65, 70),
            (145, 45),
            (210, 85),
            (285, 35),
            (400, 95),
            (370, 180),
            (410, 280),
            (300, 350),
            (220, 315),
            (135, 365),
            (55, 310),
            (90, 240),
        ]
        draw.polygon(points, fill=(90, 120, 160, 255))
        draw.ellipse((80, 85, 250, 260), fill=(180, 100, 110, 255))
        draw.polygon(
            [(180, 60), (390, 100), (330, 330), (210, 250)],
            fill=(100, 170, 140, 255),
        )
        image.save(source)

        def relative_path(template: str) -> str:
            return template.replace("{artifact_root}", artifact_root_relative)

        raw_relative = relative_path(case["raw_path"])
        ingestion_relative = relative_path(case["ingestion_report_path"])
        derivative_relative = relative_path(case["derived_path"])
        derivation_relative = relative_path(case["derivation_report_path"])
        raw_path = ROOT / raw_relative
        ingestion_path = ROOT / ingestion_relative
        derivative_path = ROOT / derivative_relative
        derivation_path = ROOT / derivation_relative
        binding_path = source_root.resolve() / "migration-binding-report.json"
        binding_path.write_text(
            json.dumps(binding_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        ingest_download(
            source,
            raw_path,
            ingestion_path,
            artifact_root,
            binding_nonce=binding_report["binding_nonce"],
            binding_digest=binding_report["binding_digest"],
            provider_session_id="provider-session-current",
            provider_request_id="provider-request-current",
            observed_download_id="browser-download-current",
            request_metadata_sha256=case["host_request_metadata_sha256"],
        )
        result = prepare_migration_probe(
            raw_path,
            derivative_path,
            derivation_path,
            binding_report_path=binding_path,
            ingestion_report_path=ingestion_path,
            attempt=1,
            role="floating-spot",
            article_id="migration-route-probe",
            asset_slot_id="migration.rgba-route-probe",
            prompt_sha256=case["prompt_sha256"],
            generation_route=case["generation_route"],
            failure_report_path=Path(
                case["failure_report_path"].replace(
                    "{artifact_root}", artifact_root_relative
                )
            ),
            require_native_alpha=True,
        )
        derivative_sha = sha256_uri(derivative_path)
        config_sha = result["processor"]["config_sha256"]
        with Image.open(derivative_path) as opened:
            opened.load()
            pixel_sha = "sha256:" + hashlib.sha256(
                f"{opened.mode}:{opened.width}x{opened.height}:".encode("ascii")
                + opened.tobytes()
            ).hexdigest()
        inspection = {
            name: {
                "status": "passed",
                "derivative_sha256": derivative_sha,
                "observation_id": f"inspection-{name}-current",
            }
            for name in ("transparent", "light", "dark")
        }
        return {
            "action": action,
            "case": case,
            "raw_relative": raw_relative,
            "raw_path": raw_path,
            "ingestion_relative": ingestion_relative,
            "ingestion_path": ingestion_path,
            "derivative_relative": derivative_relative,
            "derivative_path": derivative_path,
            "derivative_sha": derivative_sha,
            "pixel_sha": pixel_sha,
            "derivation_relative": derivation_relative,
            "derivation_path": derivation_path,
            "config_sha": config_sha,
            "inspection": inspection,
            "binding_path": binding_path,
            "binding_sha": sha256_uri(binding_path),
        }

    def create_unprocessed_probe_case(
        self,
        binding_report: dict,
        source_root: Path,
        *,
        attempt: int = 1,
        native_opaque: bool = False,
    ) -> dict:
        action = next(
            item
            for item in binding_report["host_setup_actions"]
            if item["id"] == "run-migration-rgba-route-probe"
        )
        case = next(
            item for item in action["probe_cases"] if item["attempt"] == attempt
        )
        artifact_root = Path(action["artifact_root"])
        artifact_root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(lambda: shutil.rmtree(artifact_root, ignore_errors=True))
        binding_path = source_root.resolve() / f"binding-attempt-{attempt}.json"
        binding_path.write_text(
            json.dumps(binding_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        observed = source_root.resolve() / f"observed-attempt-{attempt}.png"
        if attempt == 1:
            image = (
                Image.new("RGB", (440, 400), (246, 246, 246))
                if native_opaque
                else Image.new("RGBA", (440, 400), (0, 0, 0, 0))
            )
            draw = ImageDraw.Draw(image)
            draw.polygon(
                [
                    (35, 180),
                    (65, 70),
                    (145, 45),
                    (210, 85),
                    (285, 35),
                    (400, 95),
                    (370, 180),
                    (410, 280),
                    (300, 350),
                    (220, 315),
                    (135, 365),
                    (55, 310),
                    (90, 240),
                ],
                fill=(119, 119, 119, 255),
            )
            draw.ellipse((80, 85, 250, 260), fill=(150, 110, 110, 255))
            draw.polygon(
                [(180, 60), (390, 100), (330, 330), (210, 250)],
                fill=(100, 150, 130, 255),
            )
        else:
            image = Image.new("RGB", (440, 400), (0, 255, 60))
            draw = ImageDraw.Draw(image)
            draw.polygon(
                [(40, 180), (80, 60), (210, 90), (390, 50), (360, 320), (120, 350)],
                fill=(119, 119, 119),
            )
        image.save(observed)

        def rendered(name: str) -> Path:
            return Path(
                str(case[name]).replace("{artifact_root}", str(artifact_root))
            )

        raw_path = rendered("raw_path")
        ingestion_path = rendered("ingestion_report_path")
        ingest_download(
            observed,
            raw_path,
            ingestion_path,
            artifact_root,
            binding_nonce=binding_report["binding_nonce"],
            binding_digest=binding_report["binding_digest"],
            provider_session_id=f"provider-session-attempt-{attempt}",
            provider_request_id=f"provider-request-attempt-{attempt}",
            observed_download_id=f"browser-download-attempt-{attempt}",
            request_metadata_sha256=case["host_request_metadata_sha256"],
        )
        return {
            "action": action,
            "case": case,
            "artifact_root": artifact_root,
            "binding_path": binding_path,
            "raw_path": raw_path,
            "ingestion_path": ingestion_path,
            "output_path": rendered("derived_path"),
            "report_path": rendered("derivation_report_path"),
        }

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
        self.assertEqual(
            api_actions["connect-wechat-api-provider"]["read_only_endpoints"],
            ["draft/count", "material/get_materialcount"],
        )
        self.assertIn(
            "preflight-account",
            api_actions["connect-wechat-api-provider"][
                "preflight_command_template"
            ],
        )
        self.assertIn(
            "ui-readback",
            api_actions["connect-wechat-api-provider"]["does_not_prove"],
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
        self.assertFalse(report["operational_ready"])
        self.assertEqual(
            report["provider_acquisition_assurance"]["current_session"][
                "authority_mode"
            ],
            "current-session-operator-harness-trusted",
        )
        self.assertFalse(
            report["provider_acquisition_assurance"]["current_session"][
                "host_attested"
            ]
        )
        self.assertFalse(
            report["provider_acquisition_assurance"]["current_session"]["portable"]
        )
        self.assertFalse(
            report["provider_acquisition_assurance"]["portable"][
                "binding_available"
            ]
        )
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
        self.assertIn("validate-current-session-provider-acquisition-chain", action_ids)
        self.assertNotIn("bind-provider-acquisition-policy-hook", action_ids)
        actions = {item["id"]: item for item in report["host_setup_actions"]}
        self.assertFalse(
            actions["open-chatgpt-image-session"]["request_recovery"][
                "duplicate_submission_while_unknown"
            ]
        )
        self.assertEqual(
            actions["connect-ardot-mcp"]["configured_but_not_model_visible"],
            "reload-or-open-new-codex-task;repository-cannot-hot-inject-tools",
        )
        self.assertIn(
            "remote-mutation-success",
            actions["connect-ardot-mcp"]["configuration_or-oauth-does-not-prove"],
        )
        migration_gate = actions["enforce-migration-rgba-route-gate"]
        self.assertTrue(migration_gate["blocking"])
        self.assertFalse(
            migration_gate["local-profile-report-or-model-claim-can-satisfy"]
        )
        self.assertEqual(
            migration_gate["scope"]["generation_route_id"],
            "chatgpt-web-image-route-v1",
        )
        self.assertRegex(
            migration_gate["scope"]["trusted_bundle_sha256"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            actions["prepare-codex-with-chatgpt"]["steps"],
            [
                "update-check",
                "sandbox-allow",
                "session-for-exact-workspace-root",
                "tunnel-status",
                "if-needs-choice-stop-for-connection-choice",
                "if-new-workspace-run-setup",
                "verify-project-and-exact-connector",
                "verify-workspace-info-matches-current-worktree",
                "doctor",
            ],
        )
        self.assertEqual(
            actions["open-chatgpt-image-session"]["user_step_if_needed"],
            "complete-chatgpt-login-captcha-2fa-or-consent-after-workspace-setup",
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
        self.assertNotIn("run-migration-rgba-route-probe", actions)

    def test_host_provider_policy_hook_is_optional_and_cannot_upgrade_assurance(self) -> None:
        profile = valid_profile()
        profile["capabilities"].pop("wechat_delivery")
        profile["capabilities"].pop("host_receipt_attestation")
        profile["links"].pop("wechat_current_account")
        used = {
            tool_id
            for capability in profile["capabilities"].values()
            for field in ("tool_ids", "download_ingest_tool_ids")
            for tool_id in capability.get(field, [])
        }
        profile["tools"] = [item for item in profile["tools"] if item["id"] in used]
        report = self.run_check(
            profile, phase="authoring", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        assurance = report["provider_acquisition_assurance"]
        self.assertTrue(assurance["current_session"]["binding_available"])
        self.assertEqual(
            assurance["current_session"]["authority_mode"],
            "current-session-operator-harness-trusted",
        )
        self.assertFalse(assurance["current_session"]["host_attested"])
        self.assertFalse(assurance["current_session"]["portable"])
        self.assertFalse(
            assurance["current_session"]["policy_hook"]["can_upgrade_assurance"]
        )
        self.assertFalse(assurance["formal_micro_operational_ready"])
        self.assertIn(
            "bind-provider-acquisition-policy-hook",
            {item["id"] for item in report["host_setup_actions"]},
        )

    def test_migration_phase_requires_neutral_rgba_route_probe_before_sources(self) -> None:
        profile = select_migration_profile(valid_profile())
        report = self.run_check(
            profile, phase="migration", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertFalse(report["phase_ready"])
        self.assertEqual(
            report["external_probe_required"],
            [
                "opaque_image_generation",
                "rgba_cutout_generation",
                "visual_inspection",
                "filesystem_access_lease",
                "migration_probe_finalization",
            ],
        )
        self.assertEqual(
            report["resolved_capabilities"]["rgba_cutout_generation"][
                "live_proof"
            ],
            "required-neutral-migration-probe-in-current-host-trace",
        )
        self.assertEqual(
            report["migration_selftest"]["contract"],
            MIGRATION_RGBA_PROBE_CONTRACT,
        )
        self.assertTrue(report["migration_selftest"]["before_source_material"])
        self.assertEqual(
            report["migration_selftest"]["truth_columns"],
            {
                "local_pixel_chain_verified": "host-trace-required",
                "host_route_verified": "host-trace-required",
            },
        )
        self.assertFalse(
            report["migration_selftest"]["article_asset_registration_allowed"]
        )
        actions = {item["id"]: item for item in report["host_setup_actions"]}
        probe_action = actions["run-migration-rgba-route-probe"]
        self.assertTrue(probe_action["blocking"])
        self.assertIn("read-source-material", probe_action["must_complete_before"])
        self.assertEqual(
            probe_action["artifact_root_template"],
            "{session_root}/migration-probes/{binding_nonce}",
        )
        self.assertEqual(
            Path(probe_action["session_root"]), Path(self.private_root).resolve()
        )
        self.assertTrue(Path(probe_action["artifact_root"]).is_absolute())
        self.assertFalse(
            Path(probe_action["artifact_root"]).is_relative_to(ROOT)
            if hasattr(Path(), "is_relative_to")
            else str(Path(probe_action["artifact_root"])).startswith(str(ROOT) + os.sep)
        )
        self.assertIn("never-register", probe_action["artifact_policy"])
        self.assertEqual(probe_action["attempt_policy"]["maximum_attempts"], 2)
        self.assertEqual(
            probe_action["attempt_policy"]["preference"],
            "native-alpha-first-controlled-key-fallback-only",
        )
        self.assertTrue(
            probe_action["attempt_policy"][
                "run_attempt_2_only_after_attempt_1_processing_failure"
            ]
        )
        self.assertFalse(
            probe_action["attempt_policy"][
                "attempt_2_requires_new_user_confirmation"
            ]
        )
        self.assertTrue(
            probe_action["attempt_policy"][
                "request_recovery_is_separate_from_source_attempt"
            ]
        )
        self.assertEqual(len(probe_action["probe_cases"]), 2)
        for case in probe_action["probe_cases"]:
            self.assertEqual(
                case["prompt_sha256"],
                "sha256:"
                + hashlib.sha256(case["prompt"].encode("utf-8")).hexdigest(),
            )
            self.assertIn("No text", case["prompt"])
            self.assertNotIn("organization", case["prompt"].lower())
            metadata = case["host_request_metadata"]
            self.assertEqual(metadata["prompt_sha256"], case["prompt_sha256"])
            self.assertEqual(
                case["host_request_metadata_sha256"],
                "sha256:"
                + hashlib.sha256(
                    json.dumps(
                        metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            )
        native, fallback = probe_action["probe_cases"]
        self.assertEqual(native["acquisition_mode"], "native-alpha")
        self.assertIsNone(native["key_color"])
        self.assertIn("genuinely transparent background", native["prompt"])
        self.assertIn("nonsemantic calibration mark", native["prompt"])
        self.assertIn("stroke thickness about 8 percent", native["prompt"])
        self.assertIn("span 60 to 70 percent", native["prompt"])
        self.assertIn("large open negative spaces", native["prompt"])
        self.assertNotIn("leaf-like ovals", native["prompt"].lower())
        self.assertNotIn("coral", native["prompt"].lower())
        self.assertNotIn("golden yellow", native["prompt"].lower())
        self.assertIn("--require-native-alpha", native["processor_command"])
        self.assertNotIn("--key-color", native["processor_command"])
        self.assertEqual(fallback["acquisition_mode"], "controlled-key-fallback")
        self.assertEqual(fallback["key_color"], "#00FF3C")
        self.assertIn("--key-color", fallback["processor_command"])
        self.assertIn("#00FF3C", fallback["processor_command"])
        self.assertNotIn("connect-ardot-mcp", actions)
        self.assertNotIn("open-ardot-target", actions)
        self.assertNotIn("open-wechat-account", actions)
        self.assertEqual(
            probe_action["proof_boundary"]["local_pixel_chain"],
            "processor-and-pixel-inspection-required-but-insufficient",
        )
        self.assertFalse(
            probe_action["proof_boundary"]["profile_or_model_authored_receipt_can_pass"]
        )
        self.assertEqual(
            probe_action["pixel_inspection_command_template"][:5],
            [
                "python3",
                "-I",
                "-S",
                str(ROOT / "scripts" / "secure_runner.py"),
                str(ROOT / "scripts" / "inspect_asset.py"),
            ],
        )
        self.assertTrue(probe_action["visual_context_policy"]["probe_is_style_reference"] is False)
        self.assertEqual(
            probe_action["visual_context_policy"]["probe_semantics"],
            "nonsemantic-monochrome-open-stroke-calibration-only",
        )
        self.assertTrue(
            probe_action["visual_context_policy"][
                "same_c2c_managed_conversation_required"
            ]
        )
        self.assertFalse(
            probe_action["visual_context_policy"][
                "throwaway_chat_inside_current_c2c_task_allowed"
            ]
        )
        self.assertTrue(
            _artifact_location_is_private(Path(probe_action["artifact_root"]), ROOT)
        )

    def test_migration_requires_external_session_root(self) -> None:
        profile = select_migration_profile(valid_profile())
        common = {
            "now": NOW,
            "environment": {},
            "binding_only": True,
            "installed_registry_override": installed_registry_for(profile),
        }
        with self.assertRaisesRegex(ValueError, "explicit absolute --session-root"):
            validate_runtime_profile(profile, ROOT, "migration", **common)
        with self.assertRaisesRegex(ValueError, "outside the installed runtime"):
            validate_runtime_profile(
                profile,
                ROOT,
                "migration",
                session_root=ROOT / "runtime",
                **common,
            )

    def test_codex_migration_probe_runs_after_chatgpt_and_pixel_routes_bind(self) -> None:
        profile = select_migration_profile(
            select_codex_chatgpt_rgba_route(valid_profile())
        )
        report = self.run_check(
            profile, phase="migration", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        action_ids = [item["id"] for item in report["host_setup_actions"]]
        actions = {item["id"]: item for item in report["host_setup_actions"]}
        self.assertEqual(
            actions["open-chatgpt-image-session"]["target"],
            "current-c2c-session-chat-or-project-conversation",
        )
        self.assertNotIn("seal-migration-gate-and-end-setup-task", actions)
        probe_index = action_ids.index("run-migration-rgba-route-probe")
        for prerequisite in (
            "prepare-codex-with-chatgpt",
            "open-chatgpt-image-session",
            "bind-rgba-download-processing",
            "bind-image-inspection",
            "bind-opaque-image-generation",
        ):
            self.assertLess(action_ids.index(prerequisite), probe_index)
        action = report["host_setup_actions"][probe_index]
        self.assertEqual(
            action["probe_cases"][0]["generation_route"],
            "chatgpt-web-image-route-v1",
        )
        self.assertIn(
            "browser-observed-provider-original-download-event",
            action["host_evidence_required"],
        )
        self.assertIn(
            "same-current-provider-session-for-request-generation-and-download",
            action["host_evidence_required"],
        )
        self.assertIn(
            "local-original-png-magic-mime-byte-length-download-time-and-sha256",
            action["host_evidence_required"],
        )
        self.assertIn(
            "host-image-inspection-of-the-exact-derived-file-on-transparent-light-and-dark-surfaces",
            action["host_evidence_required"],
        )

    def test_migration_phase_rejects_missing_probe_contract(self) -> None:
        profile = select_migration_profile(valid_profile())
        profile["capabilities"]["rgba_cutout_generation"].pop(
            "migration_probe_contract"
        )
        report = self.run_check(
            profile, phase="migration", binding_only=True, environment={}
        )
        self.assertIn(
            "runtime.capability.rgba_migration_probe_contract_missing",
            error_codes(report),
        )

        wrong_route = select_migration_profile(valid_profile())
        wrong_route["capabilities"]["rgba_cutout_generation"][
            "generation_route_id"
        ] = "invented-generic-route-v1"
        report = self.run_check(
            wrong_route, phase="migration", binding_only=True, environment={}
        )
        self.assertIn(
            "runtime.capability.rgba_adapter_generation_route_mismatch",
            error_codes(report),
        )

    def test_authoring_requires_adapter_matched_rgba_generation_route(self) -> None:
        missing = valid_profile()
        missing["capabilities"]["rgba_cutout_generation"].pop("generation_route_id")
        report = self.run_check(
            missing, phase="authoring", binding_only=True, environment={}
        )
        self.assertIn(
            "runtime.capability.rgba_generation_route_id_invalid",
            error_codes(report),
        )

        mismatched = valid_profile()
        mismatched["capabilities"]["rgba_cutout_generation"][
            "generation_route_id"
        ] = "invented-route-v1"
        report = self.run_check(
            mismatched, phase="authoring", binding_only=True, environment={}
        )
        self.assertIn(
            "runtime.capability.rgba_adapter_generation_route_mismatch",
            error_codes(report),
        )

    def test_migration_probe_is_nonce_bound_and_rejects_unsafe_nonce(self) -> None:
        profile = select_migration_profile(valid_profile())
        first = validate_runtime_profile(
            profile,
            ROOT,
            "migration",
            session_root=Path(self.private_root).resolve(),
            now=NOW,
            environment={},
            binding_only=True,
            challenge_nonce="A" * 32,
            installed_registry_override=installed_registry_for(profile),
        )
        second = validate_runtime_profile(
            profile,
            ROOT,
            "migration",
            session_root=Path(self.private_root).resolve(),
            now=NOW,
            environment={},
            binding_only=True,
            challenge_nonce="B" * 32,
            installed_registry_override=installed_registry_for(profile),
        )
        first_action = next(
            item
            for item in first["host_setup_actions"]
            if item["id"] == "run-migration-rgba-route-probe"
        )
        second_action = next(
            item
            for item in second["host_setup_actions"]
            if item["id"] == "run-migration-rgba-route-probe"
        )
        self.assertEqual(
            first_action["probe_cases"][0]["prompt_sha256"],
            second_action["probe_cases"][0]["prompt_sha256"],
        )
        self.assertNotEqual(
            first_action["probe_cases"][0]["host_request_metadata_sha256"],
            second_action["probe_cases"][0]["host_request_metadata_sha256"],
        )
        self.assertNotEqual(first_action["artifact_root"], second_action["artifact_root"])
        self.assertNotIn("A" * 32, first_action["probe_cases"][0]["prompt"])
        self.assertEqual(
            first_action["probe_cases"][0]["host_request_metadata"]["binding_nonce"],
            "A" * 32,
        )
        with self.assertRaises(ValueError):
            validate_runtime_profile(
                profile,
                ROOT,
                "migration",
                session_root=Path(self.private_root).resolve(),
                now=NOW,
                environment={},
                binding_only=True,
                challenge_nonce="../unsafe/path" + "x" * 32,
                installed_registry_override=installed_registry_for(profile),
            )

    def test_migration_profile_claims_cannot_self_attest_host_route(self) -> None:
        profile = select_migration_profile(valid_profile())
        rgba = profile["capabilities"]["rgba_cutout_generation"]
        rgba["status"] = "passed"
        rgba["probe"] = probe(
            "generated-asset-live", "model-authored-old-local-report"
        )
        report = self.run_check(profile, phase="migration", environment={})
        self.assertFalse(report["ok"])
        self.assertFalse(report["phase_ready"])
        self.assertEqual(
            report["migration_selftest"]["status"], "host-trace-required"
        )
        self.assertIn("runtime.probe.unattested", error_codes(report))

    def test_current_session_migration_closes_operationally_without_signed_claim(self) -> None:
        profile = select_migration_profile(
            select_codex_chatgpt_rgba_route(valid_profile())
        )
        nonce = secrets.token_urlsafe(32)
        binding = validate_runtime_profile(
            profile,
            ROOT,
            "migration",
            session_root=Path(self.private_root).resolve(),
            now=NOW,
            environment={},
            binding_only=True,
            challenge_nonce=nonce,
            installed_registry_override=installed_registry_for(profile),
        )
        self.assertTrue(binding["binding_ready"], binding["errors"])
        self.assertEqual(
            binding["migration_selftest"]["portable_signed_upgrade"],
            "unavailable-on-selected-adapter",
        )
        with tempfile.TemporaryDirectory() as directory:
            artifacts = self.create_probe_artifacts(binding, Path(directory))
            source_sha = artifacts["binding_sha"]
            case = artifacts["case"]
            evidence = {
                "schema_version": 1,
                "kind": "org-wechat-migration-session-evidence-v1",
                "created_at": NOW.isoformat(),
                "binding": {
                    "binding_nonce": binding["binding_nonce"],
                    "binding_digest": binding["binding_digest"],
                    "source_binding_report_sha256": source_sha,
                    "trusted_bundle_sha256": binding["local"]["trusted_bundle_sha256"],
                    "installed_release_sha256": binding["local"]["installed_release_sha256"],
                    "registry_digest": binding["local"]["registry_digest"],
                    "adapter_sha256": binding["resolved_harness"]["adapter_sha256"],
                    "generation_route_id": binding["resolved_capabilities"][
                        "rgba_cutout_generation"
                    ]["generation_route_id"],
                },
                "probe": {
                    "attempt": 1,
                    "prompt_sha256": case["prompt_sha256"],
                    "host_request_metadata_sha256": case[
                        "host_request_metadata_sha256"
                    ],
                    "provider_session_id": "provider-session-current",
                    "provider_request_id": "provider-request-current",
                    "observed_download_id": "browser-download-current",
                    "download_ingestion": {
                        "path": artifacts["ingestion_relative"],
                        "sha256": sha256_uri(artifacts["ingestion_path"]),
                    },
                    "derivative_png": {
                        "path": artifacts["derivative_relative"],
                        "sha256": artifacts["derivative_sha"],
                        "pixel_sha256": artifacts["pixel_sha"],
                        "mode": "RGBA8",
                    },
                    "derivation_report": {
                        "path": artifacts["derivation_relative"],
                        "sha256": sha256_uri(artifacts["derivation_path"]),
                        "config_sha256": artifacts["config_sha"],
                    },
                    "inspection": artifacts["inspection"],
                },
            }
            final = finalize_current_session_migration(
                binding,
                evidence,
                ROOT,
                source_binding_report_sha256=source_sha,
                now=NOW,
            )
            self.assertTrue(final["operational_ready"])
            self.assertFalse(final["phase_ready"])
            self.assertFalse(final["portable_signed_audit"])
            self.assertEqual(
                final["continuation"]["scope"], "same-host-session-only"
            )
            forged = copy.deepcopy(evidence)
            forged["binding"]["registry_digest"] = "sha256:" + "0" * 64
            with self.assertRaises(ValueError):
                finalize_current_session_migration(
                    binding,
                    forged,
                    ROOT,
                    source_binding_report_sha256=source_sha,
                    now=NOW,
                )

    def test_migration_probe_processor_cli_runs_from_external_cwd_and_is_nonregisterable(self) -> None:
        profile = select_migration_profile(
            select_codex_chatgpt_rgba_route(valid_profile())
        )
        binding = self.run_check(
            profile, phase="migration", binding_only=True, environment={}
        )
        self.assertTrue(binding["binding_ready"], binding["errors"])
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory).resolve()
            inputs = self.create_unprocessed_probe_case(binding, external)
            command = [
                str(item)
                .replace("{artifact_root}", str(inputs["artifact_root"]))
                .replace("{binding_report}", str(inputs["binding_path"]))
                for item in inputs["case"]["processor_command"]
            ]
            self.assertTrue(Path(command[4]).is_absolute())
            self.assertEqual(
                Path(command[4]).resolve(),
                (ROOT / "scripts" / "prepare_migration_probe.py").resolve(),
            )
            cwd = external / "unrelated-project"
            cwd.mkdir()
            completed = subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
            lineage = json.loads(inputs["report_path"].read_text(encoding="utf-8"))
            self.assertEqual(
                lineage["kind"],
                "org-wechat-migration-probe-cutout-derivation-v1",
            )
            self.assertEqual(lineage["status"], "migration-probe-only")
            authority = lineage["migration_probe"]
            self.assertTrue(authority["migration_only"])
            self.assertFalse(authority["article_asset_authority"])
            self.assertFalse(authority["registerable"])
            self.assertFalse(authority["portable"])
            self.assertFalse(authority["carry_forward"])

    def test_migration_probe_processor_rejects_missing_fake_wrong_and_article_scope(self) -> None:
        profile = select_migration_profile(
            select_codex_chatgpt_rgba_route(valid_profile())
        )
        binding = self.run_check(
            profile, phase="migration", binding_only=True, environment={}
        )
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory).resolve()
            inputs = self.create_unprocessed_probe_case(binding, external)
            base = [
                str(item)
                .replace("{artifact_root}", str(inputs["artifact_root"]))
                .replace("{binding_report}", str(inputs["binding_path"]))
                for item in inputs["case"]["processor_command"]
            ]
            cwd = external / "unrelated-project"
            cwd.mkdir()

            missing = list(base)
            index = missing.index("--ingestion-report")
            del missing[index : index + 2]
            result = subprocess.run(
                missing, cwd=cwd, check=False, capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(inputs["output_path"].exists())
            self.assertFalse(inputs["report_path"].exists())

            forged_binding = copy.deepcopy(binding)
            forged_binding["binding_ready"] = False
            forged_path = external / "forged-binding.json"
            forged_path.write_text(json.dumps(forged_binding), encoding="utf-8")
            forged = [
                str(forged_path) if item == str(inputs["binding_path"]) else item
                for item in base
            ]
            result = subprocess.run(
                forged, cwd=cwd, check=False, capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(inputs["output_path"].exists())

            wrong_ingestion = external / "wrong-ingestion.json"
            wrong_ingestion.write_bytes(inputs["ingestion_path"].read_bytes())
            wrong = [
                str(wrong_ingestion)
                if item == str(inputs["ingestion_path"])
                else item
                for item in base
            ]
            result = subprocess.run(
                wrong, cwd=cwd, check=False, capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(inputs["output_path"].exists())

            article = list(base)
            article[article.index("migration-route-probe")] = "real-article"
            result = subprocess.run(
                article, cwd=cwd, check=False, capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(inputs["output_path"].exists())
            self.assertFalse(inputs["report_path"].exists())

    def test_migration_probe_attempt_two_requires_real_attempt_one_failure(self) -> None:
        profile = select_migration_profile(
            select_codex_chatgpt_rgba_route(valid_profile())
        )
        binding = self.run_check(
            profile, phase="migration", binding_only=True, environment={}
        )
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory).resolve()
            inputs = self.create_unprocessed_probe_case(
                binding, external, attempt=2
            )
            command = [
                str(item)
                .replace("{artifact_root}", str(inputs["artifact_root"]))
                .replace("{binding_report}", str(inputs["binding_path"]))
                for item in inputs["case"]["processor_command"]
            ]
            cwd = external / "unrelated-project"
            cwd.mkdir()
            result = subprocess.run(
                command, cwd=cwd, check=False, capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("attempt 1 failure report", result.stdout + result.stderr)
            self.assertFalse(inputs["output_path"].exists())
            self.assertFalse(inputs["report_path"].exists())

    def test_migration_probe_native_failure_emits_bound_fallback_action(self) -> None:
        profile = select_migration_profile(
            select_codex_chatgpt_rgba_route(valid_profile())
        )
        binding = self.run_check(
            profile, phase="migration", binding_only=True, environment={}
        )
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory).resolve()
            inputs = self.create_unprocessed_probe_case(
                binding, external, native_opaque=True
            )
            command = [
                str(item)
                .replace("{artifact_root}", str(inputs["artifact_root"]))
                .replace("{binding_report}", str(inputs["binding_path"]))
                for item in inputs["case"]["processor_command"]
            ]
            cwd = external / "unrelated-project"
            cwd.mkdir()
            result = subprocess.run(
                command, cwd=cwd, check=False, capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            response = json.loads(result.stdout)
            failure_path = Path(
                inputs["case"]["failure_report_path"].replace(
                    "{artifact_root}", str(inputs["artifact_root"])
                )
            )
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            fallback = next(
                item
                for item in inputs["action"]["probe_cases"]
                if item["attempt"] == 2
            )
            self.assertTrue(response["fallback_eligible"])
            self.assertFalse(response["requires_new_user_confirmation"])
            self.assertEqual(response["next_action"], failure["next_action"])
            self.assertEqual(response["next_action"]["attempt"], 2)
            self.assertEqual(
                response["next_action"]["prompt_sha256"],
                fallback["prompt_sha256"],
            )
            self.assertEqual(
                response["next_action"]["acquisition_mode"],
                "controlled-key-fallback",
            )
            self.assertFalse(inputs["output_path"].exists())
            self.assertFalse(inputs["report_path"].exists())

    def test_signed_migration_receipt_closes_phase_ready_and_rejects_forgery(self) -> None:
        profile = select_migration_profile(valid_profile())
        binding = validate_runtime_profile(
            profile,
            ROOT,
            "migration",
            session_root=Path(self.private_root).resolve(),
            now=NOW,
            environment={},
            binding_only=True,
            challenge_nonce=secrets.token_urlsafe(32),
            installed_registry_override=installed_registry_for(profile),
        )
        self.assertTrue(binding["binding_ready"], binding["errors"])
        with tempfile.TemporaryDirectory() as directory:
            artifacts = self.create_probe_artifacts(binding, Path(directory))
            source_sha = artifacts["binding_sha"]
            case = artifacts["case"]
            private_key = Ed25519PrivateKey.generate()
            public_key = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            receipt = {
                "schema_version": 1,
                "kind": "org-wechat-migration-probe-host-receipt-v1",
                "receipt_id": "migration-receipt-current",
                "issued_at": NOW.isoformat(),
                "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
                "continuation_expires_at": (NOW + timedelta(hours=1)).isoformat(),
                "binding": {
                    "binding_nonce": binding["binding_nonce"],
                    "binding_digest": binding["binding_digest"],
                    "trusted_bundle_sha256": binding["local"]["trusted_bundle_sha256"],
                    "installed_release_sha256": binding["local"][
                        "installed_release_sha256"
                    ],
                    "registry_digest": binding["local"]["registry_digest"],
                    "registry_census_sha256": binding["local"][
                        "registry_census_sha256"
                    ],
                    "adapter_sha256": binding["resolved_harness"]["adapter_sha256"],
                    "generation_route_id": binding["resolved_capabilities"][
                        "rgba_cutout_generation"
                    ]["generation_route_id"],
                    "migration_probe_contract": MIGRATION_RGBA_PROBE_CONTRACT,
                    "filesystem_policy_sha256": binding["resolved_capabilities"][
                        "filesystem_access_lease"
                    ]["policy_sha256"],
                    "source_binding_report_sha256": source_sha,
                },
                "replay_protection": {
                    "single_use": True,
                    "host_nonce_consumed": True,
                    "host_ledger_id": "migration-ledger-current",
                },
                "host": {
                    "capability": "host.migration.finalize",
                    "provider": "test-host",
                    "session_id": "test-session-current",
                    "request_id": "migration-finalize-request",
                    "filesystem_lease_id": binding["resolved_capabilities"][
                        "filesystem_access_lease"
                    ]["lease_id"],
                },
                "probe": {
                    "attempt": 1,
                    "prompt_sha256": case["prompt_sha256"],
                    "host_request_metadata_sha256": case[
                        "host_request_metadata_sha256"
                    ],
                    "generation_route_id": binding["resolved_capabilities"][
                        "rgba_cutout_generation"
                    ]["generation_route_id"],
                    "provider_request_id": "provider-request-current",
                    "provider_session_id": "provider-session-current",
                    "observed_download_id": "browser-download-current",
                    "download_ingestion": {
                        "path": artifacts["ingestion_relative"],
                        "sha256": sha256_uri(artifacts["ingestion_path"]),
                    },
                    "host_route_verified": True,
                    "local_pixel_chain_verified": True,
                    "raw_png": {
                        "path": artifacts["raw_relative"],
                        "sha256": sha256_uri(artifacts["raw_path"]),
                        "byte_length": artifacts["raw_path"].stat().st_size,
                        "mime": "image/png",
                        "downloaded_at": NOW.isoformat(),
                    },
                    "derivative_png": {
                        "path": artifacts["derivative_relative"],
                        "sha256": artifacts["derivative_sha"],
                        "pixel_sha256": artifacts["pixel_sha"],
                        "mode": "RGBA8",
                    },
                    "derivation_report": {
                        "path": artifacts["derivation_relative"],
                        "sha256": sha256_uri(artifacts["derivation_path"]),
                        "config_sha256": artifacts["config_sha"],
                    },
                    "inspection": artifacts["inspection"],
                },
            }

            def sign(value: dict) -> dict:
                signed = copy.deepcopy(value)
                unsigned_bytes = json.dumps(
                    signed,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                signed["signature"] = {
                    "algorithm": "ed25519",
                    "key_id": "migration-key-current",
                    "value_base64": base64.b64encode(
                        private_key.sign(unsigned_bytes)
                    ).decode("ascii"),
                }
                return signed

            signed = sign(receipt)
            final = finalize_migration_binding_report(
                binding,
                signed,
                ROOT,
                source_binding_report_sha256=source_sha,
                trusted_public_keys={"migration-key-current": public_key},
                now=NOW,
            )
            self.assertTrue(final["phase_ready"])
            self.assertEqual(final["check_level"], "host-finalized")
            missing_ingestion = copy.deepcopy(receipt)
            missing_ingestion["probe"].pop("download_ingestion")
            with self.assertRaisesRegex(ValueError, "download ingestion evidence"):
                finalize_migration_binding_report(
                    binding,
                    sign(missing_ingestion),
                    ROOT,
                    source_binding_report_sha256=source_sha,
                    trusted_public_keys={"migration-key-current": public_key},
                    now=NOW,
                )
            unsigned = copy.deepcopy(receipt)
            with self.assertRaises(ValueError):
                finalize_migration_binding_report(
                    binding,
                    unsigned,
                    ROOT,
                    source_binding_report_sha256=source_sha,
                    trusted_public_keys={"migration-key-current": public_key},
                    now=NOW,
                )
            replay_forgery = copy.deepcopy(receipt)
            replay_forgery["replay_protection"]["host_nonce_consumed"] = False
            with self.assertRaises(ValueError):
                finalize_migration_binding_report(
                    binding,
                    sign(replay_forgery),
                    ROOT,
                    source_binding_report_sha256=source_sha,
                    trusted_public_keys={"migration-key-current": public_key},
                    now=NOW,
                )

    def test_native_migration_route_does_not_load_chatgpt(self) -> None:
        profile = select_migration_profile(valid_profile())
        report = self.run_check(
            profile, phase="migration", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        actions = {item["id"]: item for item in report["host_setup_actions"]}
        self.assertNotIn("prepare-codex-with-chatgpt", actions)
        self.assertNotIn("open-chatgpt-image-session", actions)
        self.assertEqual(
            actions["run-migration-rgba-route-probe"]["probe_cases"][0][
                "generation_route"
            ],
            "test-rgba-provider-v1",
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
        self.assertNotIn("run-migration-rgba-route-probe", actions)

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

    def test_watermark_secret_is_required_only_for_eligible_carriers(self) -> None:
        no_carrier = valid_profile()
        no_carrier["artifact_inventory"] = {
            "census_complete": True,
            "source_sha256": "sha256:" + "7" * 64,
            "eligible_watermark_carriers": [],
        }
        no_carrier["capabilities"].pop("secret_store")
        report = self.run_check(
            no_carrier, phase="full", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertNotIn("secret_store", report["resolved_capabilities"])

        carrier = copy.deepcopy(no_carrier)
        carrier["artifact_inventory"]["eligible_watermark_carriers"] = [
            {"asset_id": "generated-background-1", "sha256": "sha256:" + "8" * 64}
        ]
        blocked = self.run_check(
            carrier, phase="full", binding_only=True, environment={}
        )
        self.assertIn("runtime.capability.missing", error_codes(blocked))

    def test_optional_delivery_audit_requires_real_attestor_and_trust_boundary(self) -> None:
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
        profile["capabilities"].pop("provider_acquisition_authority")
        profile["tools"] = [
            item
            for item in profile["tools"]
            if item["kind"]
            not in {
                "image.generate.opaque",
                "image.generate.rgba",
                "image.provider.acquire.authority",
            }
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
        self.assertEqual(adapter["harness"], "codex-desktop")
        self.assertEqual(
            adapter["support_status"], "only-supported-execution-adapter"
        )
        self.assertEqual(
            setup["support"],
            {
                "execution_host": "codex-desktop",
                "status": "supported-only-on-codex-desktop",
                "other_harnesses": "unsupported-until-a-reviewed-adapter-and-full-forward-test-are-released",
                "semantic_contract_portability_is_execution_support": False,
            },
        )
        self.assertEqual(setup["semantic_capabilities"], list(EXPECTED_SEMANTIC_CAPABILITIES))
        self.assertEqual(set(adapter["capabilities"]), set(EXPECTED_SEMANTIC_CAPABILITIES))
        self.assertEqual(set(setup["local"]), set(EXPECTED_LOCAL_SETUP_LINKS))
        for link_id, (package, path) in EXPECTED_LOCAL_SETUP_LINKS.items():
            self.assertEqual(setup["local"][link_id]["package"], package)
            self.assertEqual(setup["local"][link_id]["path"], path)
        self.assertEqual(setup["local"]["publisher_skill"]["path"], "SKILL.md")
        self.assertEqual(
            setup["local"]["chatgpt_image_route_skill"]["path"], "SKILL.md"
        )
        self.assertIn("routing-only", adapter["truth_boundary"])
        host_route = adapter["capabilities"]["host.receipt.attest"]
        self.assertEqual(host_route["availability"], "unavailable")
        self.assertEqual(host_route["requires"], [])
        self.assertIn("no callable", host_route["reason"])
        provider_authority = adapter["capabilities"][
            "image.provider.acquire.authority"
        ]
        self.assertEqual(provider_authority["availability"], "unavailable")
        self.assertEqual(provider_authority["requires"], [])
        self.assertFalse(provider_authority["can_upgrade_assurance"])
        self.assertIn("does not block current-session", provider_authority["reason"])
        self.assertTrue(setup["startup_policy"]["wait_for_user_login"])
        self.assertTrue(
            setup["startup_policy"]["declare_execution_conditions_first"]
        )
        self.assertTrue(
            setup["startup_policy"]["clone_check_before_source_material"]
        )
        self.assertFalse(setup["startup_policy"]["persist_session_query"])
        self.assertEqual(setup["external"]["chatgpt_web"]["url"], "https://chatgpt.com/")
        self.assertEqual(
            setup["external"]["codex_with_chatgpt_repository"]["url"],
            "https://github.com/XiaoDuoYa/codex-with-chatgpt",
        )
        self.assertEqual(
            setup["local"]["host_prerequisites"]["path"],
            "references/host-prerequisites.md",
        )
        rgba_route = adapter["capabilities"]["image.generate.rgba"]
        self.assertEqual(rgba_route["route"], "chatgpt-web")
        self.assertEqual(rgba_route["output_contract"], "subject-cutout-rgba8-v1")
        self.assertEqual(rgba_route["processor"], "scripts/prepare_micro_cutout.py")
        self.assertEqual(
            rgba_route["acquisition_preference"],
            "native-alpha-first-controlled-key-fallback-only",
        )
        self.assertEqual(rgba_route["preferred_processor_arg"], "--require-native-alpha")
        self.assertEqual(rgba_route["fallback_processor_arg"], "--key-color")
        self.assertEqual(
            rgba_route["migration_probe_contract"],
            MIGRATION_RGBA_PROBE_CONTRACT,
        )
        self.assertEqual(
            rgba_route["generation_route_id"], "chatgpt-web-image-route-v1"
        )
        self.assertEqual(
            rgba_route["provider_skill"]["contract"], "chatgpt-web-image-route-v1"
        )

    def test_current_codex_adapter_allows_session_draft_but_not_optional_signed_audit(self) -> None:
        current = select_codex_chatgpt_rgba_route(valid_profile())
        current["capabilities"].pop("host_receipt_attestation")
        current["tools"] = [
            item for item in current["tools"] if item["kind"] != "host.receipt.attest"
        ]
        report = self.run_check(current, binding_only=True, environment={})
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertNotIn(
            "runtime.provider_acquisition.no_formal_authority_route",
            error_codes(report),
        )
        self.assertEqual(
            report["provider_acquisition_assurance"]["current_session"]["assurance"],
            "operator-harness-trusted-current-session",
        )

        audited = select_codex_chatgpt_rgba_route(valid_profile())
        report = self.run_check(audited, binding_only=True, environment={})
        self.assertFalse(report["binding_ready"])
        self.assertIn(
            "runtime.capability.host_receipt_attestation_unavailable",
            error_codes(report),
        )
        self.assertNotIn(
            "runtime.provider_acquisition.no_formal_authority_route",
            error_codes(report),
        )

        delivery = copy.deepcopy(audited)
        delivery["capabilities"].pop("host_receipt_attestation")
        delivery["capabilities"].pop("opaque_image_generation")
        delivery["capabilities"].pop("rgba_cutout_generation")
        for skill in delivery["skills"]:
            if skill["id"] == "ardot-wechat-publisher":
                skill["status"] = "loaded"
            elif skill["id"] == "org-wechat-studio":
                skill["status"] = "available"
        used_tool_ids = {
            tool_id
            for capability in delivery["capabilities"].values()
            for tool_id in capability.get("tool_ids", [])
        }
        delivery["tools"] = [
            item for item in delivery["tools"] if item["id"] in used_tool_ids
        ]
        report = self.run_check(
            delivery, phase="delivery", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertEqual(
            report["host_attestation"], "optional-portable-audit-upgrade"
        )
        self.assertEqual(report["delivery_assurance"]["mode"], "current-session-draft")
        self.assertFalse(
            report["delivery_assurance"]["host_receipt_absence_blocks_draft_write"]
        )
        action_ids = {item["id"] for item in report["host_setup_actions"]}
        self.assertNotIn("bind-host-receipt-attestation", action_ids)

    def test_current_codex_adapter_supports_verified_local_wechat_api_tool(self) -> None:
        profile = select_codex_chatgpt_rgba_route(valid_profile())
        for name in (
            "opaque_image_generation",
            "rgba_cutout_generation",
            "host_receipt_attestation",
        ):
            profile["capabilities"].pop(name, None)
        profile["artifact_inventory"] = {
            "census_complete": True,
            "source_sha256": "sha256:" + "9" * 64,
            "eligible_watermark_carriers": [],
        }
        profile["links"]["wechat_current_account"]["url"] = (
            "https://api.weixin.qq.com/"
        )
        profile["capabilities"]["wechat_delivery"] = {
            "mode": "api",
            "status": "declared",
            "tool_ids": ["scripts/wechat_publisher.py"],
            "account_link": "wechat_current_account",
            "target_account_ref": "test-visible-account",
        }
        profile["capabilities"]["wechat_current_session_readback"] = {
            "mode": "host-ui",
            "status": "declared",
            "tool_ids": [
                "browser:control-in-app-browser",
                "mcp__node_repl__js",
                "scripts/ingest_wechat_readback_capture.py",
            ],
            "target_account_ref": "test-visible-account",
            "truth_boundary": (
                "browser-computer-use-exact-draft-capture-current-session-only-"
                "nonportable-no-publication-authority"
            ),
            "processor": "scripts/ingest_wechat_readback_capture.py",
        }
        profile["tools"].append(
            runtime_tool(
                "scripts/wechat_publisher.py",
                "wechat.draft",
                "codex-desktop",
                "runtime-registry",
            )
        )
        readback_tool = runtime_tool(
            "scripts/ingest_wechat_readback_capture.py",
            "wechat.current-session-readback",
            "codex-chatgpt-browser",
            "runtime-registry",
        )
        readback_tool["session_id"] = "codex-chatgpt-session-20260831"
        profile["tools"].append(readback_tool)
        for skill in profile["skills"]:
            skill["status"] = (
                "loaded"
                if skill["id"] == "ardot-wechat-publisher"
                else "available"
            )
        used = {
            tool_id
            for capability in profile["capabilities"].values()
            for field in ("tool_ids", "download_ingest_tool_ids")
            for tool_id in capability.get(field, [])
        }
        profile["tools"] = [item for item in profile["tools"] if item["id"] in used]
        report = self.run_check(
            profile, phase="delivery", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertTrue(report["publication_routes"]["draft"]["api"]["available"])
        self.assertFalse(
            report["publication_routes"]["draft"]["api"][
                "implies_publication_authority"
            ]
        )
        self.assertFalse(
            report["publication_routes"]["current_session_publish"]["api"][
                "available"
            ]
        )
        self.assertTrue(report["publication_routes"]["selected"]["binding_ready"])
        self.assertTrue(
            report["publication_routes"]["current_session_readback"]["available"]
        )
        self.assertIn(
            "connect-wechat-api-provider",
            {item["id"] for item in report["host_setup_actions"]},
        )
        self.assertIn(
            "capture-wechat-current-session-readback",
            {item["id"] for item in report["host_setup_actions"]},
        )
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("WECHAT_APP_SECRET", serialized)
        self.assertNotIn("access_token", serialized)

        profile["capabilities"]["wechat_delivery"]["terminal_state"] = "publish"
        live_report = self.run_check(
            profile, phase="delivery", binding_only=True, environment={}
        )
        self.assertFalse(live_report["binding_ready"])
        self.assertIn(
            "runtime.publication.api_authority_unavailable",
            error_codes(live_report),
        )
        self.assertFalse(
            live_report["publication_routes"]["current_session_publish"]["api"][
                "available"
            ]
        )
        self.assertFalse(
            live_report["publication_routes"]["selected"]["binding_ready"]
        )
        self.assertIn(
            "resolve-wechat-api-publication-route",
            {item["id"] for item in live_report["host_setup_actions"]},
        )

    def test_independent_host_authority_enables_api_publish_binding(self) -> None:
        profile = valid_profile()
        for name in (
            "opaque_image_generation",
            "rgba_cutout_generation",
            "provider_acquisition_authority",
            "host_receipt_attestation",
            "secret_store",
        ):
            profile["capabilities"].pop(name, None)
        profile["artifact_inventory"] = {
            "census_complete": True,
            "source_sha256": "sha256:" + "8" * 64,
            "eligible_watermark_carriers": [],
        }
        profile["links"]["wechat_current_account"]["url"] = (
            "https://api.weixin.qq.com/"
        )
        profile["capabilities"]["wechat_delivery"] = {
            "mode": "api",
            "status": "declared",
            "tool_ids": ["scripts/wechat_publisher.py"],
            "account_link": "wechat_current_account",
            "target_account_ref": "test-visible-account",
            "terminal_state": "publish",
        }
        profile["capabilities"]["wechat_publication_authority"] = {
            "mode": "host",
            "status": "declared",
            "tool_ids": ["host.wechat.current-session-authority"],
            "trust_boundary": (
                "host-in-process-fresh-confirmation-and-authoritative-readback"
            ),
        }
        profile["tools"].extend(
            [
                runtime_tool(
                    "scripts/wechat_publisher.py",
                    "wechat.draft",
                    "test-host",
                ),
                runtime_tool(
                    "host.wechat.current-session-authority",
                    "wechat.current-session-authority",
                    "test-host-authority",
                ),
            ]
        )
        for skill in profile["skills"]:
            skill["status"] = (
                "loaded"
                if skill["id"] == "ardot-wechat-publisher"
                else "available"
            )
        used = {
            tool_id
            for capability in profile["capabilities"].values()
            for field in ("tool_ids", "download_ingest_tool_ids")
            for tool_id in capability.get(field, [])
        }
        profile["tools"] = [item for item in profile["tools"] if item["id"] in used]
        report = self.run_check(
            profile, phase="delivery", binding_only=True, environment={}
        )
        self.assertTrue(report["binding_ready"], report["errors"])
        self.assertTrue(
            report["publication_routes"]["current_session_publish"]["api"][
                "available"
            ]
        )
        self.assertTrue(report["publication_routes"]["selected"]["binding_ready"])
        self.assertIn(
            "bind-wechat-current-session-publication-authority",
            {item["id"] for item in report["host_setup_actions"]},
        )

    def test_build_census_and_init_profile_cli_avoid_manual_registry_fields(self) -> None:
        source_profile = select_codex_chatgpt_rgba_route(valid_profile())
        source_profile["capabilities"].pop("host_receipt_attestation", None)
        source_profile["tools"] = [
            item
            for item in source_profile["tools"]
            if item["kind"] != "host.receipt.attest"
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source_manifest = root / "source-release-manifest.json"
            skills_root = root / "installed-skills"
            write_manifest(source_manifest, ROOT)
            installed = install_packages(skills_root, source_manifest, ROOT)
            manifest = Path(installed["installed_manifest"])
            census_path = root / "census.json"
            visible_tool_ids = [
                item["id"]
                for item in source_profile["tools"]
                if not item["id"].startswith("scripts/")
            ]
            census_command = subprocess.run(
                [
                    *SECURE_RUNNER,
                    str(ROOT / "scripts" / "runtime_preflight.py"),
                    "init-current-session-census",
                    "--phase",
                    "authoring",
                    "--session-id",
                    "codex-session-current",
                    "--workspace-root",
                    str(ROOT),
                    "--skills-root",
                    str(skills_root),
                    "--release-manifest",
                    str(manifest),
                    "--output",
                    str(census_path),
                ]
                + [
                    argument
                    for tool_id in visible_tool_ids
                    for argument in ("--visible-tool-id", tool_id)
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                census_command.returncode,
                0,
                census_command.stdout + census_command.stderr,
            )
            census = json.loads(census_path.read_text(encoding="utf-8"))
            self.assertEqual(
                census["registry_assurance"]["mode"],
                "current-session-model-visible-intent",
            )
            self.assertFalse(census["registry_assurance"]["host_attested_registry"])
            self.assertTrue(census["registry_assurance"]["requires_later_live_probes"])
            self.assertFalse(census["publication_routes"]["draft"]["api"]["available"])
            self.assertFalse(
                census["publication_routes"]["current_session_publish"]["api"][
                    "available"
                ]
            )
            self.assertTrue(
                census["provider_acquisition_routes"]["current_session"][
                    "available"
                ]
            )
            self.assertFalse(
                census["provider_acquisition_routes"]["current_session"][
                    "host_attested"
                ]
            )
            self.assertFalse(
                census["provider_acquisition_routes"]["portable"]["available"]
            )
            target = root / "target.json"
            target.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "org-wechat-runtime-target-v1",
                        "links": {
                            "ardot_current_workspace": {
                                "url": "https://ardot.tencent.com/file/123456789?web_only=1&node_id=1%3A2",
                                "purpose": "current target",
                            }
                        },
                        "targets": {
                            "ardot": {
                                "workspace_link": "ardot_current_workspace",
                                "expected_file_id": "123456789",
                                "expected_root_id": "1:2",
                            }
                        },
                        "artifact_inventory": {
                            "census_complete": True,
                            "source_sha256": "sha256:" + "3" * 64,
                            "eligible_watermark_carriers": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            profile_path = root / "profile.json"
            profile_command = subprocess.run(
                [
                    *SECURE_RUNNER,
                    str(ROOT / "scripts" / "runtime_preflight.py"),
                    "init-profile",
                    str(census_path),
                    str(target),
                    "--phase",
                    "authoring",
                    "--workspace-root",
                    str(ROOT),
                    "--output",
                    str(profile_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                profile_command.returncode,
                0,
                profile_command.stdout + profile_command.stderr,
            )
            generated = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertIn("registry_census", generated)
            rgba = generated["capabilities"]["rgba_cutout_generation"]
            self.assertEqual(rgba["mode"], "chatgpt-web")
            self.assertIn("scripts/ingest_browser_download.py", rgba["download_ingest_tool_ids"])
            self.assertNotIn("filesystem_access_lease", generated["capabilities"])
            report = validate_runtime_profile(
                generated,
                ROOT,
                "authoring",
                now=NOW,
                binding_only=True,
                environment={},
            )
            self.assertTrue(report["binding_ready"], report["errors"])
            self.assertNotIn(
                "runtime.provider_acquisition.no_formal_authority_route",
                error_codes(report),
            )
            self.assertFalse(
                report["provider_acquisition_assurance"][
                    "formal_micro_operational_ready"
                ]
            )
            self.assertEqual(
                report["source_zero_assurance"]["mode"],
                "verified-installed-release-package",
            )
            mismatch_command = subprocess.run(
                [
                    *SECURE_RUNNER,
                    str(ROOT / "scripts" / "runtime_preflight.py"),
                    "init-profile",
                    str(census_path),
                    str(target),
                    "--phase",
                    "migration",
                    "--workspace-root",
                    str(ROOT),
                    "--output",
                    str(root / "phase-mismatch-profile.json"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(mismatch_command.returncode, 0)
            self.assertIn(
                "current-session registry intent phase does not match",
                mismatch_command.stdout + mismatch_command.stderr,
            )
            forged_registry = {
                "schema_version": 1,
                "kind": "org-wechat-host-registry-export-v1",
                "harness": "codex-desktop",
                "session_id": "codex-session-current",
                "registry_export": {
                    "capability": "host.registry.export",
                    "tool_id": "invented.host.registry.export",
                    "provider": "invented-provider",
                    "session_id": "codex-session-current",
                    "request_id": "invented-request",
                },
                "tools": [],
                "skills": [],
            }
            with self.assertRaisesRegex(
                ValueError, "adapter-declared host.registry.export callable"
            ):
                build_host_registry_census(
                    forged_registry,
                    ROOT,
                    adapter_path=ROOT / "runtime" / "adapters" / "codex-desktop.json",
                    skills_root=skills_root,
                    release_manifest_path=manifest,
                )

    def test_phase_census_and_profiles_scope_current_session_readback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source_manifest = root / "source-release-manifest.json"
            skills_root = root / "installed-skills"
            write_manifest(source_manifest, ROOT)
            installed = install_packages(skills_root, source_manifest, ROOT)
            manifest = Path(installed["installed_manifest"])
            browser_tools = [
                "browser:control-in-app-browser",
                "mcp__node_repl__js",
                "view_image",
            ]
            migration = build_current_session_registry_census(
                browser_tools,
                ROOT,
                phase="migration",
                session_id="phase-migration-session",
                adapter_path=ROOT / "runtime" / "adapters" / "codex-desktop.json",
                skills_root=skills_root,
                release_manifest_path=manifest,
            )
            migration_ids = {item["id"] for item in migration["tools"]}
            self.assertIn("scripts/ingest_browser_download.py", migration_ids)
            self.assertNotIn(
                "scripts/ingest_wechat_readback_capture.py",
                migration_ids,
            )

            delivery = build_current_session_registry_census(
                browser_tools,
                ROOT,
                phase="delivery",
                session_id="phase-delivery-session",
                adapter_path=ROOT / "runtime" / "adapters" / "codex-desktop.json",
                skills_root=skills_root,
                release_manifest_path=manifest,
            )
            delivery_ids = {item["id"] for item in delivery["tools"]}
            self.assertIn(
                "scripts/ingest_wechat_readback_capture.py",
                delivery_ids,
            )
            self.assertNotIn("scripts/ingest_browser_download.py", delivery_ids)
            self.assertTrue(
                delivery["publication_routes"]["current_session_readback"][
                    "available"
                ]
            )
            self.assertFalse(
                delivery["publication_routes"]["current_session_readback"][
                    "implies_publication_authority"
                ]
            )

            target = {
                "schema_version": 1,
                "kind": "org-wechat-runtime-target-v1",
                "links": {
                    "ardot_current_workspace": {
                        "url": (
                            "https://ardot.tencent.com/file/123456789?"
                            "web_only=1&node_id=1%3A2"
                        ),
                        "purpose": "current target",
                    },
                    "wechat_current_account": {
                        "url": "https://api.weixin.qq.com/",
                        "purpose": "current API target",
                    },
                },
                "targets": {
                    "ardot": {
                        "workspace_link": "ardot_current_workspace",
                        "expected_file_id": "123456789",
                        "expected_root_id": "1:2",
                    },
                    "wechat": {
                        "mode": "api",
                        "terminal_state": "draft",
                        "account_link": "wechat_current_account",
                        "target_account_ref": "test-visible-account",
                    },
                },
                "artifact_inventory": {
                    "census_complete": True,
                    "source_sha256": "sha256:" + "9" * 64,
                    "eligible_watermark_carriers": [],
                },
            }
            delivery_path = root / "delivery-census.json"
            delivery_path.write_text(
                json.dumps(delivery, ensure_ascii=False),
                encoding="utf-8",
            )
            current_profile = build_runtime_profile_from_census(
                delivery,
                delivery_path,
                target,
                ROOT,
                "delivery",
            )
            current_profile["capabilities"].pop(
                "wechat_current_session_readback"
            )
            current_report = validate_runtime_profile(
                current_profile,
                ROOT,
                "delivery",
                now=NOW,
                environment={},
                binding_only=True,
            )
            self.assertIn(
                "runtime.readback.current_session_route_missing",
                error_codes(current_report),
            )

            ardot_tools = [
                "view_image",
                "mcp__ardot_remote__fetch_file_info",
                "mcp__ardot_remote__fetch_editor_state",
                "mcp__ardot_remote__batch_read",
                "mcp__ardot_remote__batch_edit",
                "mcp__ardot_remote__capture_screenshot",
                "mcp__ardot_remote__export_nodes",
            ]
            missing_browser = build_current_session_registry_census(
                ardot_tools,
                ROOT,
                phase="delivery",
                session_id="missing-browser-session",
                adapter_path=ROOT / "runtime" / "adapters" / "codex-desktop.json",
                skills_root=skills_root,
                release_manifest_path=manifest,
            )
            self.assertFalse(
                missing_browser["publication_routes"][
                    "current_session_readback"
                ]["available"]
            )
            missing_path = root / "missing-browser-census.json"
            missing_path.write_text(
                json.dumps(missing_browser, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "complete WeChat UI readback capture route",
            ):
                build_runtime_profile_from_census(
                    missing_browser,
                    missing_path,
                    target,
                    ROOT,
                    "delivery",
                )

            portable_tools = [*ardot_tools, "host.receipt.attest"]
            portable_census = build_current_session_registry_census(
                portable_tools,
                ROOT,
                phase="delivery",
                session_id="portable-api-session",
                adapter_path=ROOT / "tests" / "fixtures" / "host-enabled-adapter.json",
                skills_root=skills_root,
                release_manifest_path=manifest,
            )
            self.assertFalse(
                portable_census["publication_routes"][
                    "current_session_readback"
                ]["available"]
            )
            portable_path = root / "portable-census.json"
            portable_path.write_text(
                json.dumps(portable_census, ensure_ascii=False),
                encoding="utf-8",
            )
            portable_target = copy.deepcopy(target)
            portable_target["assurance"] = {
                "host_receipt_attestation": {
                    "trust_boundary": (
                        "host-owned-private-key-and-protected-trust-store"
                    )
                }
            }
            portable_profile = build_runtime_profile_from_census(
                portable_census,
                portable_path,
                portable_target,
                ROOT,
                "delivery",
            )
            self.assertNotIn(
                "wechat_current_session_readback",
                portable_profile["capabilities"],
            )
            portable_report = validate_runtime_profile(
                portable_profile,
                ROOT,
                "delivery",
                now=NOW,
                environment={},
                binding_only=True,
            )
            self.assertTrue(portable_report["binding_ready"], portable_report["errors"])
            self.assertFalse(
                portable_report["publication_routes"][
                    "current_session_readback"
                ]["selected"]
            )

    def test_delivery_transport_chain_is_required_and_digest_bound(self) -> None:
        critical = {
            "requirements.txt",
            "runtime/python-dependency-lock.json",
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
            "scripts/pack_assets.py",
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

    def test_runtime_docs_expose_codex_census_and_future_adapter_boundary(self) -> None:
        runtime_docs = (ROOT / "references" / "runtime-preflight.md").read_text(
            encoding="utf-8"
        )
        for relative in ("README.md", "SKILL.md", "references/使用说明.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("init-current-session-census", text, relative)
            self.assertIn("Codex Desktop", text, relative)
            self.assertIn('--session-root "$ORG_WECHAT_SESSION_ROOT"', text, relative)
            self.assertNotIn(
                '"$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" build-census',
                text,
                relative,
            )
        self.assertIn("build-census", runtime_docs)
        self.assertIn("未来 adapter", runtime_docs)
        self.assertIn("host.registry.export", runtime_docs)
        self.assertIn('--session-root "$ORG_WECHAT_SESSION_ROOT"', runtime_docs)
        self.assertIn(
            '"$ORG_WECHAT_RUNTIME_ROOT/scripts/ingest_browser_download.py" \\',
            runtime_docs,
        )
        self.assertIn("/ABSOLUTE/PATH/RETURNED/BY/HOST.png \\", runtime_docs)
        self.assertIn("--allowed-target-root", runtime_docs)
        self.assertNotIn("--source /ABSOLUTE/PATH/RETURNED/BY/HOST.png", runtime_docs)
        self.assertNotIn("--target-root", runtime_docs)
        self.assertNotIn("--generation-route-id", runtime_docs)

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

    def test_external_session_output_respects_owning_git_ignore_and_symlinks(self) -> None:
        private_tmp = Path("/private/tmp")
        if not private_tmp.is_dir():
            private_tmp = Path(tempfile.gettempdir()).resolve()
        with tempfile.TemporaryDirectory(
            prefix="org-wechat-private-output-", dir=private_tmp
        ) as directory:
            root = Path(directory).resolve()
            installed_runtime = root / "skills" / "org-wechat-studio"
            installed_runtime.mkdir(parents=True)

            user_project = root / "user-project"
            user_project.mkdir()
            subprocess.run(
                ["git", "init", "-q"],
                cwd=user_project,
                check=True,
                capture_output=True,
            )
            (user_project / ".gitignore").write_text(
                "output/runtime/\n", encoding="utf-8"
            )
            ignored = user_project / "output" / "runtime" / "census.json"
            unignored = user_project / "census.json"
            self.assertTrue(
                _artifact_location_is_private(ignored, installed_runtime)
            )
            self.assertFalse(
                _artifact_location_is_private(unignored, installed_runtime)
            )

            external_non_git = root / "private-session" / "census.json"
            self.assertTrue(
                _artifact_location_is_private(external_non_git, installed_runtime)
            )
            self.assertFalse(
                _artifact_location_is_private(
                    installed_runtime / "output" / "census.json",
                    installed_runtime,
                )
            )

            real_parent = root / "real-session"
            real_parent.mkdir()
            linked_parent = root / "linked-session"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(SystemExit, "symbolic links"):
                _private_create_once_output(
                    linked_parent / "census.json",
                    installed_runtime,
                    "census output",
                )
            (real_parent / "census.json").write_text("{}\n", encoding="utf-8")
            (real_parent / "target.json").write_text("{}\n", encoding="utf-8")
            external_input = subprocess.run(
                [
                    *SECURE_RUNNER,
                    str(ROOT / "scripts" / "runtime_preflight.py"),
                    "init-profile",
                    str(linked_parent / "census.json"),
                    str(linked_parent / "target.json"),
                    "--phase",
                    "migration",
                    "--workspace-root",
                    str(ROOT),
                    "--output",
                    str(root / "private-session" / "profile.json"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(external_input.returncode, 0)
            self.assertIn(
                "path must not contain symbolic links",
                external_input.stdout + external_input.stderr,
            )

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
            relative = "agents/openai.yaml"
            source = ROOT / relative
            destination = workspace / relative
            destination.write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8"
            )
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
        profile["capabilities"].pop("filesystem_access_lease")
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
        create_contract = actions["open-ardot-target"]["create_design_contract"]
        self.assertEqual(create_contract["mutation_class"], "non-idempotent")
        self.assertEqual(
            create_contract["on_timeout_5xx_or_truncated_response"],
            "create-unknown",
        )
        self.assertFalse(create_contract["automatic_retry"])
        self.assertNotIn("open-wechat-account", actions)
        self.assertNotIn("open-chatgpt-image-session", actions)
        self.assertNotIn("run-migration-rgba-route-probe", actions)
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
            root = Path(directory).resolve()
            profile_path = root / "profile.json"
            output_path = root / "report.json"
            self.attach_real_registry_census(profile, root)
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
            root = Path(directory).resolve()
            profile_path = root / "profile.json"
            output_path = root / "report.json"
            private_root = root / "private-watermark-registry"
            private_root.mkdir()
            self.attach_real_registry_census(profile, root)
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
            root = Path(directory).resolve()
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
            root = Path(directory).resolve()
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
