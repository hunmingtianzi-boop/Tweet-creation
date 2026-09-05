#!/usr/bin/env python3
"""Validate startup bindings and refuse unattested live-readiness claims."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/runtime_preflight.py")


PROFILE_KIND = "org-wechat-runtime-profile"
REPORT_KIND = "org-wechat-runtime-preflight-report"
SCHEMA_VERSION = 2
PHASES = {"migration", "bootstrap", "authoring", "delivery", "full"}
DEFAULT_PROBE_MAX_AGE_MINUTES = 60
MIGRATION_RGBA_PROBE_CONTRACT = "neutral-rgba-route-probe-v1"
MIGRATION_RGBA_PROBE_ARTIFACT_ROOT = (
    "{session_root}/migration-probes/{binding_nonce}"
)
MIGRATION_RGBA_PROBE_FALLBACK_KEY = "#00FF3C"
MIGRATION_RECEIPT_KIND = "org-wechat-migration-probe-host-receipt-v1"
MIGRATION_FINAL_REPORT_KIND = "org-wechat-migration-final-report-v1"
MIGRATION_SESSION_EVIDENCE_KIND = "org-wechat-migration-session-evidence-v1"
RUNTIME_SESSION_EVIDENCE_KIND = "org-wechat-runtime-session-evidence-v1"
MIGRATION_SESSION_REPORT_KIND = "org-wechat-migration-current-session-report-v1"
MIGRATION_CONSUMPTION_KIND = "org-wechat-migration-receipt-consumption-v1"
MIGRATION_TRUST_STORE_KIND = "org-wechat-migration-host-trust-store-v1"
MIGRATION_RECEIPT_MAX_TTL_SECONDS = 600
HOST_REGISTRY_CENSUS_KIND = "org-wechat-host-registry-census-v1"
HOST_REGISTRY_EXPORT_KIND = "org-wechat-host-registry-export-v1"
CURRENT_SESSION_REGISTRY_INTENT_KIND = (
    "org-wechat-current-session-registry-intent-v1"
)
FILESYSTEM_POLICY_KIND = "org-wechat-source-zero-filesystem-policy-v1"

REQUIRED_PATHS = (
    "README.md",
    "SKILL.md",
    "agents/openai.yaml",
    "requirements.txt",
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
    "references/ardot-transport-fidelity.md",
    "references/qa.md",
    "references/provenance-watermark.md",
    "references/runtime-preflight.md",
    "references/host-prerequisites.md",
    "runtime/setup-links.json",
    "runtime/adapters/codex-desktop.json",
    "runtime/python-dependency-lock.json",
    "runtime/platform-support.json",
    "runtime/non-mcp-dependencies.json",
    "runtime/host-registry-census-contract.json",
    "runtime/migration-host-receipt-contract.json",
    "style-presets/prismatic-paper-editorial.json",
    "scripts/orgs.py",
    "scripts/secure_runner.py",
    "scripts/secure_runtime.py",
    "scripts/asset_quality.py",
    "scripts/asset_role_policy.py",
    "scripts/pack_assets.py",
    "scripts/ingest_browser_download.py",
    "scripts/ingest_wechat_readback_capture.py",
    "scripts/prepare_migration_probe.py",
    "scripts/workflow_quality.py",
    "scripts/build_visual_directions.py",
    "scripts/build_storyboard.py",
    "scripts/build_visual_kit.py",
    "scripts/inspect_asset.py",
    "scripts/prepare_micro_cutout.py",
    "scripts/provider_acquisition_authority.py",
    "scripts/build_ardot_manifest.py",
    "scripts/build_visual_review.py",
    "scripts/compile_wechat.py",
    "scripts/export_ardot_handoff.py",
    "scripts/transport_fidelity.py",
    "scripts/validate_transport_fidelity.py",
    "scripts/provenance_watermark.py",
    "scripts/release_skills.py",
    "scripts/wechat_interaction_policy.py",
    "scripts/wechat_publisher.py",
    "scripts/validate_workflow_attribution.py",
)

LINK_SCAN_FILES = (
    "SKILL.md",
    "README.md",
    "references/使用说明.md",
    "references/organization-pack-migration.md",
    "references/ardot-workflow.md",
)

EXPECTED_SETUP_LINKS = {
    "ardot_mcp": "https://ardot.tencent.com/mcp",
    "ardot_web": "https://ardot.tencent.com/",
    "wechat_web": "https://mp.weixin.qq.com/",
    "wechat_api": "https://api.weixin.qq.com/",
    "chatgpt_web": "https://chatgpt.com/",
    "codex_with_chatgpt_repository": "https://github.com/XiaoDuoYa/codex-with-chatgpt",
}

EXPECTED_SEMANTIC_CAPABILITIES = (
    "host.registry.export",
    "image.generate.opaque",
    "image.generate.rgba",
    "image.provider.acquire.authority",
    "image.inspect",
    "chatgpt.session",
    "ardot.create",
    "ardot.read",
    "ardot.write",
    "ardot.export",
    "browser.control",
    "computer.use",
    "browser.download.ingest",
    "wechat.draft",
    "wechat.current-session-readback",
    "wechat.current-session-authority",
    "host.receipt.attest",
    "host.migration.finalize",
    "filesystem.access.lease",
    "secret.resolve",
)

REQUIRED_SKILLS = {"org-wechat-studio", "ardot-wechat-publisher"}

EXPECTED_LOCAL_SETUP_LINKS = {
    "host_prerequisites": (
        "org-wechat-studio",
        "references/host-prerequisites.md",
    ),
    "authoring_skill": ("org-wechat-studio", "SKILL.md"),
    "publisher_skill": ("ardot-wechat-publisher", "SKILL.md"),
    "runtime_contract": ("org-wechat-studio", "references/runtime-preflight.md"),
    "secure_runner": ("org-wechat-studio", "scripts/secure_runner.py"),
    "browser_download_ingestor": (
        "org-wechat-studio",
        "scripts/ingest_browser_download.py",
    ),
    "wechat_readback_ingestor": (
        "org-wechat-studio",
        "scripts/ingest_wechat_readback_capture.py",
    ),
    "migration_probe_processor": (
        "org-wechat-studio",
        "scripts/prepare_migration_probe.py",
    ),
    "ardot_handoff_exporter": (
        "org-wechat-studio",
        "scripts/export_ardot_handoff.py",
    ),
    "wechat_publisher": ("org-wechat-studio", "scripts/wechat_publisher.py"),
    "python_dependency_lock": (
        "org-wechat-studio",
        "runtime/python-dependency-lock.json",
    ),
    "platform_support": ("org-wechat-studio", "runtime/platform-support.json"),
    "non_mcp_dependencies": (
        "org-wechat-studio",
        "runtime/non-mcp-dependencies.json",
    ),
    "host_registry_census_contract": (
        "org-wechat-studio",
        "runtime/host-registry-census-contract.json",
    ),
    "migration_host_receipt_contract": (
        "org-wechat-studio",
        "runtime/migration-host-receipt-contract.json",
    ),
    "codex_adapter": (
        "org-wechat-studio",
        "runtime/adapters/codex-desktop.json",
    ),
    "chatgpt_image_route_skill": ("chatgpt-web-image-route", "SKILL.md"),
    "chatgpt_image_route_contract": (
        "chatgpt-web-image-route",
        "references/image-generation-contract.md",
    ),
    "cutout_processor": ("org-wechat-studio", "scripts/prepare_micro_cutout.py"),
    "cutout_inspector": ("org-wechat-studio", "scripts/inspect_asset.py"),
    "usage": ("org-wechat-studio", "references/使用说明.md"),
    "qa": ("org-wechat-studio", "references/qa.md"),
}

PHASE_LOADED_SKILL = {
    "migration": "org-wechat-studio",
    "bootstrap": "org-wechat-studio",
    "authoring": "org-wechat-studio",
    "delivery": "ardot-wechat-publisher",
    "full": "org-wechat-studio",
}

def phase_capabilities(phase, document):
    from production_intent import generation_selection
    selection = generation_selection(document)
    return tuple(name for name in PHASE_CAPABILITIES[phase]
                 if not (name == "opaque_image_generation" and not selection["opaque"])
                 and not (name == "rgba_cutout_generation" and not selection["rgba"]))


PHASE_CAPABILITIES = {
    "migration": (
        "opaque_image_generation",
        "rgba_cutout_generation",
        "visual_inspection",
    ),
    "bootstrap": ("ardot_bootstrap",),
    "authoring": (
        "opaque_image_generation",
        "rgba_cutout_generation",
        "visual_inspection",
        "ardot_authoring",
    ),
    "delivery": (
        "visual_inspection",
        "ardot_authoring",
        "wechat_delivery",
    ),
    "full": (
        "opaque_image_generation",
        "rgba_cutout_generation",
        "visual_inspection",
        "ardot_authoring",
        "wechat_delivery",
    ),
}

OPTIONAL_PHASE_CAPABILITIES = {
    "migration": ("filesystem_access_lease", "migration_probe_finalization"),
    "bootstrap": ("filesystem_access_lease",),
    "authoring": (
        "filesystem_access_lease",
        "provider_acquisition_authority",
        "secret_store",
    ),
    "delivery": (
        "filesystem_access_lease",
        "host_receipt_attestation",
        "wechat_current_session_readback",
        "wechat_publication_authority",
        "secret_store",
    ),
    "full": (
        "filesystem_access_lease",
        "host_receipt_attestation",
        "wechat_current_session_readback",
        "wechat_publication_authority",
        "provider_acquisition_authority",
        "secret_store",
    ),
}

# Tool census is phase-scoped.  In particular, bootstrap must not acquire a
# Browser dependency and API delivery must not inherit the authoring image
# route or its download-ingestion processor.
PHASE_REGISTRY_SEMANTIC_KINDS = {
    "migration": {
        "image.generate.opaque",
        "image.generate.rgba",
        "image.inspect",
        "chatgpt.session",
        "browser.control",
        "browser.download.ingest",
        "host.migration.finalize",
        "filesystem.access.lease",
    },
    "bootstrap": {"ardot.create"},
    "authoring": {
        "image.generate.opaque",
        "image.generate.rgba",
        "image.inspect",
        "chatgpt.session",
        "browser.control",
        "browser.download.ingest",
        "ardot.read",
        "ardot.write",
        "ardot.export",
        "image.provider.acquire.authority",
        "host.receipt.attest",
        "filesystem.access.lease",
    },
    "delivery": {
        "image.inspect",
        "ardot.read",
        "ardot.write",
        "ardot.export",
        "wechat.draft",
        "wechat.current-session-readback",
        "wechat.current-session-authority",
        "host.receipt.attest",
        "browser.control",
        "computer.use",
        "filesystem.access.lease",
    },
    "full": set(EXPECTED_SEMANTIC_CAPABILITIES),
}

CAPABILITY_MODES = {
    "opaque_image_generation": {"tool"},
    "rgba_cutout_generation": {"chatgpt-web", "tool"},
    "visual_inspection": {"tool"},
    "ardot_bootstrap": {"mcp", "ui"},
    "ardot_authoring": {"mcp", "ui"},
    "wechat_delivery": {"api", "ui"},
    "wechat_current_session_readback": {"host-ui"},
    "wechat_publication_authority": {"host"},
    "provider_acquisition_authority": {"host"},
    "host_receipt_attestation": {"host"},
    "migration_probe_finalization": {"host"},
    "filesystem_access_lease": {"host"},
    "secret_store": {"environment", "tool"},
}

SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:access_?token|refresh_?token|authorization|cookie|password|app_?secret|"
    r"client_?secret|api_?key|secret_?value|token_?value|key_?value|private_?key|wm_?id|"
    r"raw_?watermark_?id|watermark_?id)(?:$|_)",
    re.IGNORECASE,
)
SENSITIVE_QUERY_KEY = re.compile(
    r"^(?:token|access_token|authorization|cookie|password|secret|appsecret|key)$",
    re.IGNORECASE,
)
SENSITIVE_VALUE = re.compile(
    r"(?:access[_-]?token|refresh[_-]?token|authorization|bearer\s+|cookie|appsecret|token=|"
    r"\bsk-[A-Za-z0-9_-]{12,}|"
    r"(?:hex|base64):[A-Za-z0-9+/=]{20,})",
    re.IGNORECASE,
)
TOOL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{1,159}$")
ENV_REF = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
ARDOT_NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_;.-]{0,255}$")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
GENERATION_ROUTE_ID = re.compile(r"^[a-z0-9][a-z0-9._:/-]{1,127}$")
BINDING_NONCE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")

TRUSTED_BUNDLE_PATHS = (
    "scripts/ardot_capture_adapter.py",
    "scripts/production_intent.py",
    "scripts/render_quality.py",
    "SKILL.md",
    "requirements.txt",
    "agents/openai.yaml",
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
    "references/runtime-preflight.md",
    "references/ardot-transport-fidelity.md",
    "runtime/setup-links.json",
    "runtime/adapters/codex-desktop.json",
    "runtime/python-dependency-lock.json",
    "runtime/platform-support.json",
    "runtime/non-mcp-dependencies.json",
    "runtime/host-registry-census-contract.json",
    "runtime/migration-host-receipt-contract.json",
    "style-presets/prismatic-paper-editorial.json",
    "scripts/runtime_preflight.py",
    "scripts/safe_paths.py",
    "scripts/secure_runner.py",
    "scripts/secure_runtime.py",
    "scripts/asset_quality.py",
    "scripts/asset_role_policy.py",
    "scripts/pack_assets.py",
    "scripts/ingest_browser_download.py",
    "scripts/ingest_wechat_readback_capture.py",
    "scripts/prepare_migration_probe.py",
    "scripts/build_visual_directions.py",
    "scripts/build_storyboard.py",
    "scripts/build_visual_kit.py",
    "scripts/inspect_asset.py",
    "scripts/prepare_micro_cutout.py",
    "scripts/provider_acquisition_authority.py",
    "scripts/build_ardot_manifest.py",
    "scripts/build_visual_review.py",
    "scripts/compile_wechat.py",
    "scripts/export_ardot_handoff.py",
    "scripts/orgs.py",
    "scripts/provenance_watermark.py",
    "scripts/release_skills.py",
    "scripts/transport_fidelity.py",
    "scripts/validate_transport_fidelity.py",
    "scripts/validate_workflow_attribution.py",
    "scripts/wechat_interaction_policy.py",
    "scripts/wechat_publisher.py",
    "scripts/workflow_quality.py",
)


def _error(errors: list[dict[str, str]], code: str, path: str, message: str) -> None:
    errors.append({"code": code, "path": path, "message": message})


def _warning(warnings: list[dict[str, str]], code: str, path: str, message: str) -> None:
    warnings.append({"code": code, "path": path, "message": message})


def _redact_report(value: Any) -> Any:
    """Remove secret-shaped strings from every report field, including identifiers."""

    if isinstance(value, dict):
        return {key: _redact_report(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_report(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_report(item) for item in value]
    if isinstance(value, str) and SENSITIVE_VALUE.search(value):
        return "[REDACTED]"
    return value


def _trusted_bundle_digest(workspace_root: Path) -> str:
    members = []
    for relative in TRUSTED_BUNDLE_PATHS:
        path = workspace_root / relative
        digest = _sha256(path) if path.is_file() and not path.is_symlink() else "missing"
        members.append({"path": relative, "sha256": digest})
    encoded = json.dumps(members, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _skill_package_root(workspace_root: Path, package: str) -> Path:
    """Resolve one package in either source or top-level installed layout."""

    if package == "org-wechat-studio":
        return workspace_root
    source_wrapper = workspace_root / "skills" / package
    if source_wrapper.is_dir():
        return source_wrapper
    return workspace_root.parent / package


def _validate_agent_mcp_contract(
    workspace_root: Path,
    relative: str,
    errors: list[dict[str, str]],
) -> None:
    """Fail closed if an active Skill manifest points anywhere but the canonical MCP."""

    path = workspace_root / relative
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _error(
            errors,
            "runtime.local.agent_manifest_invalid",
            relative,
            f"agent manifest cannot be read: {exc}",
        )
        return
    _validate_no_secrets(text, errors, relative)
    url_values = re.findall(r'^\s*url:\s*["\']?([^"\'\s#]+)', text, flags=re.MULTILINE)
    all_urls = re.findall(r"https?://[^\s\"']+", text)
    expected_url = EXPECTED_SETUP_LINKS["ardot_mcp"]
    if url_values != [expected_url] or all_urls != [expected_url]:
        _error(
            errors,
            "runtime.local.agent_mcp_url_invalid",
            relative,
            f"agent manifest must contain exactly one credential-free MCP URL: {expected_url}",
        )
    for field, expected in (
        ("type", "mcp"),
        ("value", "ardot-remote"),
        ("transport", "streamable_http"),
    ):
        values = re.findall(
            rf'^\s*(?:-\s*)?{re.escape(field)}:\s*["\']?([^"\'\s#]+)',
            text,
            flags=re.MULTILINE,
        )
        if values != [expected]:
            _error(
                errors,
                "runtime.local.agent_mcp_contract_invalid",
                relative,
                f"agent manifest must bind exactly one {field}={expected}",
            )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read runtime profile {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("runtime profile root must be a JSON object")
    return value


def _canonical_absolute_path(path: Path) -> Path:
    """Normalize ``~``/dot traversal without resolving symbolic links."""

    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _canonical_existing_input(path: Path, label: str) -> Path:
    """Return a canonical existing input after rejecting every symlink hop."""

    canonical = _canonical_absolute_path(path)
    if canonical.is_symlink() or _has_any_symlink_component(canonical):
        raise ValueError(f"{label} path must not contain symbolic links")
    try:
        return canonical.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} path is unavailable") from exc


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _prefixed_file_sha256(path: Path) -> str:
    return "sha256:" + _sha256(path)


def _load_migration_trust_store(path: Path, workspace_root: Path) -> dict[str, bytes]:
    raw = _canonical_absolute_path(path)
    if not raw.is_absolute() or raw.is_symlink():
        raise ValueError("migration trust store must be an absolute non-symlink file")
    try:
        resolved = raw.resolve(strict=True)
        resolved.relative_to(workspace_root.resolve())
    except ValueError:
        pass
    except OSError as exc:
        raise ValueError("migration trust store is unavailable") from exc
    else:
        raise ValueError("migration trust store must remain outside the repository")
    if not resolved.is_file():
        raise ValueError("migration trust store must be a regular file")
    if os.name == "posix":
        for member in (resolved, *resolved.parents):
            metadata = member.lstat()
            if stat.S_ISLNK(metadata.st_mode) or metadata.st_uid != 0:
                raise ValueError("migration trust store and every parent must be root-owned and non-symlink")
            if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise ValueError("migration trust store path must not be group/other writable")
            if os.access(member, os.W_OK):
                raise ValueError("repository process must not be able to modify the migration trust store")
    else:
        raise ValueError(
            "this OS requires an adapter-provided protected trust-store verifier; POSIX ownership rules cannot be substituted"
        )
    payload = _read_json(resolved)
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != MIGRATION_TRUST_STORE_KIND
        or not isinstance(payload.get("keys"), list)
    ):
        raise ValueError("migration trust store schema is invalid")
    keys: dict[str, bytes] = {}
    for item in payload["keys"]:
        if not isinstance(item, dict) or item.get("algorithm") != "ed25519":
            raise ValueError("migration trust store key entry is invalid")
        key_id = item.get("key_id")
        encoded = item.get("public_key_base64")
        if not isinstance(key_id, str) or not TOOL_ID.fullmatch(key_id) or not isinstance(encoded, str):
            raise ValueError("migration trust store key id/bytes are invalid")
        try:
            raw_key = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("migration trust store public key is not canonical base64") from exc
        if len(raw_key) != 32 or key_id in keys:
            raise ValueError("migration trust store Ed25519 key length/id is invalid")
        keys[key_id] = raw_key
    if not keys:
        raise ValueError("migration trust store contains no trusted keys")
    return keys


def _receipt_artifact_path(
    workspace_root: Path,
    artifact_root: Path,
    claimed: Any,
    expected: str,
) -> Path:
    if claimed != expected or not isinstance(claimed, str):
        raise ValueError(f"migration receipt artifact path must equal {expected}")
    claimed_path = Path(claimed)
    if not claimed_path.is_absolute():
        raise ValueError("migration receipt artifact path must be absolute")
    candidate = _canonical_absolute_path(claimed_path)
    canonical_root = _canonical_absolute_path(artifact_root)
    try:
        candidate.relative_to(canonical_root)
    except ValueError as exc:
        raise ValueError("migration receipt artifact escapes its bound session root") from exc
    if _has_any_symlink_component(candidate):
        raise ValueError("migration receipt artifact path contains a symlink")
    resolved = candidate.resolve(strict=True)
    resolved.relative_to(canonical_root.resolve(strict=True))
    if not resolved.is_file():
        raise ValueError("migration receipt artifact must be a regular file")
    if not _artifact_location_is_private(resolved, workspace_root):
        raise ValueError(
            "migration receipt artifact must remain outside Git or in a Git-ignored path"
        )
    return resolved


def _bound_migration_artifact_root(
    binding_report: dict[str, Any],
    probe_action: dict[str, Any],
    workspace_root: Path,
) -> Path:
    """Revalidate the external session root bound into a migration report."""

    session_value = probe_action.get("session_root")
    artifact_value = probe_action.get("artifact_root")
    nonce = binding_report.get("binding_nonce")
    if (
        not isinstance(session_value, str)
        or not isinstance(artifact_value, str)
        or not isinstance(nonce, str)
        or not Path(session_value).is_absolute()
        or not Path(artifact_value).is_absolute()
    ):
        raise ValueError("migration binding report lacks absolute external session paths")
    session_root = _canonical_absolute_path(Path(session_value))
    if str(session_root) != session_value or _has_any_symlink_component(session_root):
        raise ValueError("migration session root is noncanonical or contains a symlink")
    try:
        session_root = session_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("migration session root is unavailable") from exc
    if not session_root.is_dir():
        raise ValueError("migration session root must be an existing directory")
    runtime_root = workspace_root.resolve(strict=True)
    try:
        session_root.relative_to(runtime_root)
    except ValueError:
        pass
    else:
        raise ValueError("migration session root must be outside the installed runtime")
    if not _artifact_location_is_private(session_root, runtime_root):
        raise ValueError("migration session root must be outside Git or Git-ignored")
    expected = session_root / "migration-probes" / nonce
    artifact_root = _canonical_absolute_path(Path(artifact_value))
    if artifact_root != expected or _has_any_symlink_component(artifact_root):
        raise ValueError("migration artifact root does not match its bound external session root")
    if artifact_root.exists() and (
        not artifact_root.is_dir() or artifact_root.is_symlink()
    ):
        raise ValueError("migration artifact root must be a real directory")
    return artifact_root


def _validate_previous_migration_attempt_failure(
    *,
    binding_report: dict[str, Any],
    probe_action: dict[str, Any],
    artifact_root_path: Path,
    failure_entry: dict[str, Any],
) -> dict[str, str]:
    """Reopen attempt 1 and prove it really failed an allowed native gate."""

    cases = probe_action.get("probe_cases")
    first = next(
        (item for item in cases if isinstance(item, dict) and item.get("attempt") == 1),
        None,
    ) if isinstance(cases, list) else None
    if not isinstance(first, dict):
        raise ValueError("migration attempt 1 case is missing")
    artifact_root = str(artifact_root_path)
    failure_expected = str(first.get("failure_report_path", "")).replace(
        "{artifact_root}", artifact_root
    )
    failure_path = _receipt_artifact_path(
        workspace_root=Path(__file__).resolve().parent.parent,
        artifact_root=artifact_root_path,
        claimed=failure_entry.get("path"),
        expected=failure_expected,
    )
    if failure_entry.get("sha256") != _prefixed_file_sha256(failure_path):
        raise ValueError("migration attempt 1 failure report digest is invalid")
    failure = _read_json(failure_path)
    raw_expected = str(first.get("raw_path", "")).replace(
        "{artifact_root}", artifact_root
    )
    ingestion_expected = str(first.get("ingestion_report_path", "")).replace(
        "{artifact_root}", artifact_root
    )
    raw_path = _receipt_artifact_path(
        Path(__file__).resolve().parent.parent,
        artifact_root_path,
        raw_expected,
        raw_expected,
    )
    ingestion_path = _receipt_artifact_path(
        Path(__file__).resolve().parent.parent,
        artifact_root_path,
        ingestion_expected,
        ingestion_expected,
    )
    ingestion = _read_json(ingestion_path)
    ingestion_binding = ingestion.get("binding")
    ingestion_source = ingestion.get("source")
    ingestion_target = ingestion.get("target")
    if (
        ingestion.get("kind") != "org-wechat-browser-download-ingestion-v1"
        or not isinstance(ingestion_binding, dict)
        or ingestion_binding.get("binding_nonce") != binding_report.get("binding_nonce")
        or ingestion_binding.get("binding_digest") != binding_report.get("binding_digest")
        or ingestion_binding.get("request_metadata_sha256")
        != first.get("host_request_metadata_sha256")
        or not isinstance(ingestion_source, dict)
        or not isinstance(ingestion_target, dict)
        or ingestion_target.get("path") != str(raw_path)
        or ingestion_target.get("create_once") is not True
        or ingestion_target.get("sha256") != _prefixed_file_sha256(raw_path)
        or ingestion_target.get("byte_length") != raw_path.stat().st_size
        or ingestion_source.get("sha256") != ingestion_target.get("sha256")
        or ingestion_source.get("byte_length") != ingestion_target.get("byte_length")
    ):
        raise ValueError("migration attempt 1 ingestion evidence is invalid")
    from prepare_migration_probe import (
        FAILURE_KIND,
        _recompute_native_failure,
    )

    error = failure.get("error")
    recomputed = _recompute_native_failure(raw_path)
    if (
        failure.get("schema_version") != 1
        or failure.get("kind") != FAILURE_KIND
        or failure.get("status") != "allowed-native-gate-failure"
        or failure.get("attempt") != 1
        or failure.get("article_id") != "migration-route-probe"
        or failure.get("asset_slot_id") != "migration.rgba-route-probe"
        or failure.get("role") != "floating-spot"
        or failure.get("binding_nonce") != binding_report.get("binding_nonce")
        or failure.get("binding_digest") != binding_report.get("binding_digest")
        or failure.get("prompt_sha256") != first.get("prompt_sha256")
        or failure.get("host_request_metadata_sha256")
        != first.get("host_request_metadata_sha256")
        or failure.get("generation_route") != first.get("generation_route")
        or failure.get("source_sha256") != _prefixed_file_sha256(raw_path)
        or failure.get("ingestion_report_sha256")
        != _prefixed_file_sha256(ingestion_path)
        or failure.get("processor_script")
        != "scripts/prepare_migration_probe.py"
        or failure.get("processor_script_sha256")
        != _prefixed_file_sha256(
            Path(__file__).resolve().parent / "prepare_migration_probe.py"
        )
        or not isinstance(error, dict)
        or error.get("code") != recomputed
        or recomputed
        not in {
            "cutout.source.native_alpha_required",
            "cutout.source.invalid_native_rgba",
        }
        or failure.get("create_once") is not True
        or failure.get("migration_only") is not True
        or failure.get("article_asset_authority") is not False
        or failure.get("registerable") is not False
        or failure.get("portable") is not False
        or failure.get("carry_forward") is not False
    ):
        raise ValueError("attempt 2 lacks real allowed create-once attempt 1 failure evidence")
    return {
        "path": str(failure_path),
        "sha256": _prefixed_file_sha256(failure_path),
        "error_code": str(recomputed),
    }


def _validate_migration_derivation_report(
    *,
    binding_report: dict[str, Any],
    source_binding_report_sha256: str,
    probe_action: dict[str, Any],
    case: dict[str, Any],
    artifact_root_path: Path,
    ingestion_path: Path,
    raw_path: Path,
    derivative_path: Path,
    derivation_path: Path,
) -> dict[str, Any]:
    """Validate the migration-only lineage and deny article asset authority."""

    payload = _read_json(derivation_path)
    generation = payload.get("generation")
    authority = payload.get("migration_probe")
    processor = payload.get("processor")
    output = payload.get("output")
    final_validation = payload.get("final_validation")
    if not all(
        isinstance(item, dict)
        for item in (generation, authority, processor, output, final_validation)
    ):
        raise ValueError("migration derivation report lacks isolated lineage")
    binding_entry = authority.get("binding_report")
    ingestion_entry = authority.get("download_ingestion")
    if not isinstance(binding_entry, dict) or not isinstance(ingestion_entry, dict):
        raise ValueError("migration derivation authority lacks binding/ingestion evidence")
    binding_path = _canonical_existing_input(
        Path(str(binding_entry.get("path"))), "migration derivation binding report"
    )
    if (
        binding_entry.get("sha256") != source_binding_report_sha256
        or _prefixed_file_sha256(binding_path) != source_binding_report_sha256
    ):
        raise ValueError("migration derivation is not bound to the exact source report bytes")
    expected_flags = {
        "validated": True,
        "migration_only": True,
        "article_asset_authority": False,
        "registerable": False,
        "portable": False,
        "carry_forward": False,
    }
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != "org-wechat-migration-probe-cutout-derivation-v1"
        or payload.get("status") != "migration-probe-only"
        or payload.get("article_id") != "migration-route-probe"
        or payload.get("asset_slot_id") != "migration.rgba-route-probe"
        or payload.get("role") != "floating-spot"
        or generation.get("route") != case.get("generation_route")
        or generation.get("prompt_sha256") != case.get("prompt_sha256")
        or generation.get("authority_scope_at_creation") != "migration-probe-only"
        or generation.get("operationally_accepted") is not False
        or generation.get("host_attested") is not False
        or generation.get("portable") is not False
        or authority.get("kind")
        != "org-wechat-migration-probe-processor-authority-v1"
        or any(authority.get(key) != value for key, value in expected_flags.items())
        or authority.get("binding_nonce") != binding_report.get("binding_nonce")
        or authority.get("binding_digest") != binding_report.get("binding_digest")
        or authority.get("contract") != MIGRATION_RGBA_PROBE_CONTRACT
        or authority.get("attempt") != case.get("attempt")
        or authority.get("acquisition_mode") != case.get("acquisition_mode")
        or authority.get("prompt_sha256") != case.get("prompt_sha256")
        or authority.get("host_request_metadata_sha256")
        != case.get("host_request_metadata_sha256")
        or authority.get("generation_route") != case.get("generation_route")
        or authority.get("source_sha256") != _prefixed_file_sha256(raw_path)
        or authority.get("source_byte_length") != raw_path.stat().st_size
        or ingestion_entry.get("path") != str(ingestion_path)
        or ingestion_entry.get("sha256") != _prefixed_file_sha256(ingestion_path)
        or ingestion_entry.get("source_sha256") != _prefixed_file_sha256(raw_path)
        or output.get("file_sha256") != _prefixed_file_sha256(derivative_path)
        or output.get("mode") != "RGBA8"
        or final_validation.get("ok") is not True
    ):
        raise ValueError("migration derivation lineage is invalid or article-capable")
    runtime_root = Path(__file__).resolve().parent.parent
    if (
        authority.get("processor_script") != "scripts/prepare_migration_probe.py"
        or authority.get("processor_script_sha256")
        != _prefixed_file_sha256(runtime_root / "scripts" / "prepare_migration_probe.py")
        or authority.get("pixel_processor_script") != "scripts/prepare_micro_cutout.py"
        or authority.get("pixel_processor_script_sha256")
        != _prefixed_file_sha256(runtime_root / "scripts" / "prepare_micro_cutout.py")
        or processor.get("script") != "scripts/prepare_micro_cutout.py"
        or processor.get("script_sha256")
        != _prefixed_file_sha256(runtime_root / "scripts" / "prepare_micro_cutout.py")
    ):
        raise ValueError("migration derivation processor bytes do not match the installed runtime")
    attempt = case.get("attempt")
    previous = authority.get("previous_attempt_failure")
    if attempt == 1 and previous is not None:
        raise ValueError("migration attempt 1 cannot carry fallback failure evidence")
    if attempt == 2:
        if not isinstance(previous, dict):
            raise ValueError("migration attempt 2 lacks attempt 1 failure evidence")
        verified = _validate_previous_migration_attempt_failure(
            binding_report=binding_report,
            probe_action=probe_action,
            artifact_root_path=artifact_root_path,
            failure_entry=previous,
        )
        if previous != verified:
            raise ValueError("migration attempt 2 failure reference is noncanonical")
    return payload


def finalize_migration_binding_report(
    binding_report: dict[str, Any],
    receipt: dict[str, Any],
    workspace_root: Path,
    *,
    source_binding_report_sha256: str,
    trusted_public_keys: dict[str, bytes],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify one host-owned migration receipt and close ``phase_ready``.

    The signed receipt is the only input that can upgrade readiness.  A local
    derivation report, screenshots or profile fields remain insufficient.
    """

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if (
        binding_report.get("kind") != REPORT_KIND
        or binding_report.get("phase") != "migration"
        or binding_report.get("binding_ready") is not True
        or binding_report.get("phase_ready") is not False
        or binding_report.get("check_level") != "binding"
    ):
        raise ValueError("source report is not a valid unfinalized migration binding report")
    if receipt.get("schema_version") != 1 or receipt.get("kind") != MIGRATION_RECEIPT_KIND:
        raise ValueError("migration host receipt schema/kind is invalid")
    signature = receipt.get("signature")
    if not isinstance(signature, dict) or signature.get("algorithm") != "ed25519":
        raise ValueError("migration host receipt signature object is invalid")
    key_id = signature.get("key_id")
    encoded_signature = signature.get("value_base64")
    if not isinstance(key_id, str) or key_id not in trusted_public_keys or not isinstance(encoded_signature, str):
        raise ValueError("migration host receipt signing key is not trusted")
    unsigned = dict(receipt)
    unsigned.pop("signature", None)
    try:
        signature_bytes = base64.b64decode(encoded_signature, validate=True)
        Ed25519PublicKey.from_public_bytes(trusted_public_keys[key_id]).verify(
            signature_bytes,
            _canonical_bytes(unsigned),
        )
    except (ValueError, binascii.Error, InvalidSignature) as exc:
        raise ValueError("migration host receipt signature verification failed") from exc

    issued_at = _parse_timestamp(receipt.get("issued_at"))
    expires_at = _parse_timestamp(receipt.get("expires_at"))
    if issued_at is None or expires_at is None or expires_at <= issued_at:
        raise ValueError("migration host receipt timestamps are invalid")
    if (expires_at - issued_at).total_seconds() > MIGRATION_RECEIPT_MAX_TTL_SECONDS:
        raise ValueError("migration host receipt TTL exceeds policy")
    if current_time < issued_at - timedelta(seconds=300) or current_time > expires_at:
        raise ValueError("migration host receipt is not currently valid")
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not TOOL_ID.fullmatch(receipt_id):
        raise ValueError("migration host receipt id is invalid")

    binding = receipt.get("binding")
    if not isinstance(binding, dict):
        raise ValueError("migration host receipt binding is missing")
    harness = binding_report.get("resolved_harness")
    capabilities = binding_report.get("resolved_capabilities")
    local = binding_report.get("local")
    if not isinstance(harness, dict) or not isinstance(capabilities, dict) or not isinstance(local, dict):
        raise ValueError("migration binding report lacks resolved host bindings")
    if local.get("installed_registry_verified") is not True:
        raise ValueError("migration binding report lacks a verified installed release census")
    rgba = capabilities.get("rgba_cutout_generation")
    filesystem = capabilities.get("filesystem_access_lease")
    if not isinstance(rgba, dict) or not isinstance(filesystem, dict):
        raise ValueError("migration binding report lacks RGBA/filesystem bindings")
    expected_binding = {
        "binding_nonce": binding_report.get("binding_nonce"),
        "binding_digest": binding_report.get("binding_digest"),
        "trusted_bundle_sha256": local.get("trusted_bundle_sha256"),
        "installed_release_sha256": local.get("installed_release_sha256"),
        "registry_digest": local.get("registry_digest"),
        "registry_census_sha256": local.get("registry_census_sha256"),
        "adapter_sha256": harness.get("adapter_sha256"),
        "generation_route_id": rgba.get("generation_route_id"),
        "migration_probe_contract": MIGRATION_RGBA_PROBE_CONTRACT,
        "filesystem_policy_sha256": filesystem.get("policy_sha256"),
        "source_binding_report_sha256": source_binding_report_sha256,
    }
    if binding != expected_binding:
        raise ValueError("migration host receipt binding does not match the exact source report")

    replay = receipt.get("replay_protection")
    if (
        not isinstance(replay, dict)
        or replay.get("single_use") is not True
        or replay.get("host_nonce_consumed") is not True
        or not isinstance(replay.get("host_ledger_id"), str)
        or not TOOL_ID.fullmatch(replay["host_ledger_id"])
    ):
        raise ValueError("migration host receipt lacks host-enforced atomic replay protection")
    host = receipt.get("host")
    if (
        not isinstance(host, dict)
        or host.get("capability") != "host.migration.finalize"
        or not isinstance(host.get("provider"), str)
        or not isinstance(host.get("session_id"), str)
        or not isinstance(host.get("request_id"), str)
        or host.get("filesystem_lease_id") != filesystem.get("lease_id")
    ):
        raise ValueError("migration host identity/session/filesystem lease binding is invalid")

    probe = receipt.get("probe")
    if not isinstance(probe, dict):
        raise ValueError("migration host receipt probe evidence is missing")
    attempt = probe.get("attempt")
    actions = binding_report.get("host_setup_actions")
    probe_action = next(
        (
            item
            for item in actions
            if isinstance(item, dict) and item.get("id") == "run-migration-rgba-route-probe"
        ),
        None,
    ) if isinstance(actions, list) else None
    cases = probe_action.get("probe_cases") if isinstance(probe_action, dict) else None
    case = next(
        (item for item in cases if isinstance(item, dict) and item.get("attempt") == attempt),
        None,
    ) if isinstance(cases, list) else None
    if case is None:
        raise ValueError("migration host receipt attempt is not one of the bound probe cases")
    if (
        probe.get("prompt_sha256") != case.get("prompt_sha256")
        or probe.get("host_request_metadata_sha256") != case.get("host_request_metadata_sha256")
        or probe.get("generation_route_id") != rgba.get("generation_route_id")
        or not isinstance(probe.get("provider_request_id"), str)
        or not isinstance(probe.get("provider_session_id"), str)
        or not isinstance(probe.get("observed_download_id"), str)
        or probe.get("host_route_verified") is not True
        or probe.get("local_pixel_chain_verified") is not True
    ):
        raise ValueError("migration host receipt request/download truth boundary is incomplete")

    artifact_root_path = _bound_migration_artifact_root(
        binding_report, probe_action, workspace_root
    )
    artifact_root = str(artifact_root_path)
    raw_entry = probe.get("raw_png")
    derivative_entry = probe.get("derivative_png")
    derivation_entry = probe.get("derivation_report")
    if not all(isinstance(item, dict) for item in (raw_entry, derivative_entry, derivation_entry)):
        raise ValueError("migration host receipt artifact evidence is incomplete")
    raw_expected = str(case["raw_path"]).replace("{artifact_root}", artifact_root)
    derivative_expected = str(case["derived_path"]).replace("{artifact_root}", artifact_root)
    derivation_expected = str(case["derivation_report_path"]).replace("{artifact_root}", artifact_root)
    raw_path = _receipt_artifact_path(
        workspace_root, artifact_root_path, raw_entry.get("path"), raw_expected
    )
    derivative_path = _receipt_artifact_path(
        workspace_root,
        artifact_root_path,
        derivative_entry.get("path"),
        derivative_expected,
    )
    derivation_path = _receipt_artifact_path(
        workspace_root,
        artifact_root_path,
        derivation_entry.get("path"),
        derivation_expected,
    )
    if True:  # every migration route uses create-once ingestion, not only Browser routes
        ingestion_entry = probe.get("download_ingestion")
        if not isinstance(ingestion_entry, dict):
            raise ValueError(
                "migration host receipt lacks Browser download ingestion evidence"
            )
        ingestion_expected = str(case["ingestion_report_path"]).replace(
            "{artifact_root}", artifact_root
        )
        ingestion_path = _receipt_artifact_path(
            workspace_root,
            artifact_root_path,
            ingestion_entry.get("path"),
            ingestion_expected,
        )
        ingestion_payload = _read_json(ingestion_path)
        ingestion_binding = ingestion_payload.get("binding")
        ingestion_trace = ingestion_payload.get("host_trace")
        ingestion_source = ingestion_payload.get("source")
        ingestion_target = ingestion_payload.get("target")
        if (
            ingestion_entry.get("sha256") != _prefixed_file_sha256(ingestion_path)
            or ingestion_payload.get("kind")
            != "org-wechat-browser-download-ingestion-v1"
            or ingestion_payload.get("assurance")
            != "current-session-observed-path"
            or ingestion_payload.get("browser_event_attested") is not False
            or not isinstance(ingestion_binding, dict)
            or ingestion_binding.get("binding_nonce")
            != binding_report.get("binding_nonce")
            or ingestion_binding.get("binding_digest")
            != binding_report.get("binding_digest")
            or ingestion_binding.get("request_metadata_sha256")
            != case.get("host_request_metadata_sha256")
            or not isinstance(ingestion_trace, dict)
            or ingestion_trace.get("provider_session_id")
            != probe.get("provider_session_id")
            or ingestion_trace.get("provider_request_id")
            != probe.get("provider_request_id")
            or ingestion_trace.get("observed_download_id")
            != probe.get("observed_download_id")
            or not isinstance(ingestion_source, dict)
            or not isinstance(ingestion_target, dict)
            or Path(str(ingestion_target.get("path"))).resolve() != raw_path
            or ingestion_source.get("sha256") != ingestion_target.get("sha256")
            or ingestion_source.get("byte_length")
            != ingestion_target.get("byte_length")
            or ingestion_target.get("sha256") != _prefixed_file_sha256(raw_path)
            or ingestion_target.get("byte_length") != raw_path.stat().st_size
            or ingestion_target.get("create_once") is not True
        ):
            raise ValueError(
                "migration host receipt Browser ingestion does not bind the exact raw bytes"
            )
    raw_bytes = raw_path.read_bytes()
    if (
        not raw_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        or raw_entry.get("mime") != "image/png"
        or raw_entry.get("byte_length") != len(raw_bytes)
        or raw_entry.get("sha256") != _prefixed_file_sha256(raw_path)
        or _parse_timestamp(raw_entry.get("downloaded_at")) is None
    ):
        raise ValueError("migration provider-original PNG facts do not match local bytes")
    from asset_quality import inspect_png, validate_micro_asset
    from PIL import Image

    derivative_inspection = inspect_png(derivative_path)
    derivative_sha = _prefixed_file_sha256(derivative_path)
    with Image.open(derivative_path) as opened:
        opened.load()
        derivative_pixel_sha = "sha256:" + hashlib.sha256(
            f"{opened.mode}:{opened.width}x{opened.height}:".encode("ascii")
            + opened.tobytes()
        ).hexdigest()
    if (
        derivative_entry.get("sha256") != derivative_sha
        or derivative_entry.get("pixel_sha256") != derivative_pixel_sha
        or derivative_entry.get("mode") != "RGBA8"
        or derivative_inspection.get("bit_depth") != 8
        or derivative_inspection.get("color_type") != 6
        or not validate_micro_asset(derivative_path, "floating-spot").get("ok")
    ):
        raise ValueError("migration derivative is not the exact approved RGBA8 pixel artifact")
    derivation_payload = _validate_migration_derivation_report(
        binding_report=binding_report,
        source_binding_report_sha256=source_binding_report_sha256,
        probe_action=probe_action,
        case=case,
        artifact_root_path=artifact_root_path,
        ingestion_path=ingestion_path,
        raw_path=raw_path,
        derivative_path=derivative_path,
        derivation_path=derivation_path,
    )
    if (
        derivation_entry.get("sha256") != _prefixed_file_sha256(derivation_path)
        or derivation_entry.get("config_sha256")
        != (derivation_payload.get("processor") or {}).get("config_sha256")
        or (derivation_payload.get("output") or {}).get("file_sha256") != derivative_sha
        or (derivation_payload.get("final_validation") or {}).get("ok") is not True
    ):
        raise ValueError("migration derivation report does not bind the exact approved output")
    surfaces = probe.get("inspection")
    if not isinstance(surfaces, dict) or set(surfaces) != {"transparent", "light", "dark"}:
        raise ValueError("migration host receipt must contain exact transparent/light/dark inspections")
    for name, surface in surfaces.items():
        if (
            not isinstance(surface, dict)
            or surface.get("status") != "passed"
            or surface.get("derivative_sha256") != derivative_sha
            or not isinstance(surface.get("observation_id"), str)
        ):
            raise ValueError(f"migration {name} surface inspection is incomplete")

    finalized = dict(binding_report)
    finalized.update(
        {
            "kind": MIGRATION_FINAL_REPORT_KIND,
            "check_level": "host-finalized",
            "ok": True,
            "phase_ready": True,
            "host_attestation": "migration-host-receipt-verified",
            "migration_selftest": {
                **dict(binding_report.get("migration_selftest") or {}),
                "status": "passed",
                "truth_columns": {
                    "local_pixel_chain_verified": True,
                    "host_route_verified": True,
                },
                "receipt_id": receipt_id,
            },
            "migration_host_receipt": receipt,
            "continuation": {
                "contract": "org-wechat-migration-continuation-v1",
                "receipt_id": receipt_id,
                "trusted_bundle_sha256": expected_binding["trusted_bundle_sha256"],
                "installed_release_sha256": expected_binding[
                    "installed_release_sha256"
                ],
                "registry_digest": expected_binding["registry_digest"],
                "adapter_sha256": expected_binding["adapter_sha256"],
                "generation_route_id": expected_binding["generation_route_id"],
                "filesystem_policy_sha256": expected_binding["filesystem_policy_sha256"],
                "allowed_next_phases": ["bootstrap", "authoring", "full"],
                "expires_at": receipt.get("continuation_expires_at"),
            },
            "errors": [],
        }
    )
    continuation_expiry = _parse_timestamp(receipt.get("continuation_expires_at"))
    if continuation_expiry is None or continuation_expiry <= expires_at:
        raise ValueError("migration continuation expiry must be later than receipt expiry")
    return _redact_report(finalized)


def finalize_current_session_migration(
    binding_report: dict[str, Any],
    evidence: dict[str, Any],
    workspace_root: Path,
    *,
    source_binding_report_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Issue a non-portable session continuation.

    New callers use a lightweight runtime-session binding that does not create
    or inspect an RGBA calibration image.  The older probe evidence kind stays
    readable for compatibility with already-created session artifacts.
    """

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if (
        binding_report.get("kind") != REPORT_KIND
        or binding_report.get("phase") != "migration"
        or binding_report.get("binding_ready") is not True
        or binding_report.get("phase_ready") is not False
        or binding_report.get("check_level") != "binding"
    ):
        raise ValueError("source report is not a valid migration binding report")
    local = binding_report.get("local")
    capabilities = binding_report.get("resolved_capabilities")
    if (
        not isinstance(local, dict)
        or local.get("installed_registry_verified") is not True
        or not isinstance(capabilities, dict)
    ):
        raise ValueError("current-session migration requires a verified installed release census")
    rgba = capabilities.get("rgba_cutout_generation")
    if not isinstance(rgba, dict):
        raise ValueError("migration binding report lacks the RGBA route")
    evidence_kind = evidence.get("kind")
    if (
        evidence.get("schema_version") != 1
        or evidence_kind
        not in {RUNTIME_SESSION_EVIDENCE_KIND, MIGRATION_SESSION_EVIDENCE_KIND}
    ):
        raise ValueError("current-session runtime evidence schema/kind is invalid")
    created_at = _parse_timestamp(evidence.get("created_at"))
    if (
        created_at is None
        or created_at > current_time + timedelta(minutes=5)
        or current_time - created_at > timedelta(minutes=DEFAULT_PROBE_MAX_AGE_MINUTES)
    ):
        raise ValueError("current-session migration evidence is stale or future-dated")
    expected_binding = {
        "binding_nonce": binding_report.get("binding_nonce"),
        "binding_digest": binding_report.get("binding_digest"),
        "source_binding_report_sha256": source_binding_report_sha256,
        "trusted_bundle_sha256": local.get("trusted_bundle_sha256"),
        "installed_release_sha256": local.get("installed_release_sha256"),
        "registry_digest": local.get("registry_digest"),
        "adapter_sha256": (binding_report.get("resolved_harness") or {}).get(
            "adapter_sha256"
        ),
        "generation_route_id": rgba.get("generation_route_id"),
    }
    if evidence.get("binding") != expected_binding:
        raise ValueError("current-session runtime evidence binding is not exact")

    if evidence_kind == RUNTIME_SESSION_EVIDENCE_KIND:
        provider_session_id = evidence.get("provider_session_id")
        if (
            not isinstance(provider_session_id, str)
            or not TOOL_ID.fullmatch(provider_session_id)
        ):
            raise ValueError("current-session provider session id is invalid")
        finalized = dict(binding_report)
        finalized.update(
            {
                "kind": MIGRATION_SESSION_REPORT_KIND,
                "check_level": "current-session-bound",
                "ok": True,
                "phase_ready": False,
                "operational_ready": True,
                "assurance": "current-session-observed-path-not-portable-signed",
                "portable_signed_audit": False,
                "migration_selftest": {
                    "required": False,
                    "status": "not-requested",
                    "reason": "rgba-migration-probe-is-explicit-diagnostics-only",
                    "before_source_material": False,
                    "article_asset_registration_allowed": False,
                    "article_asset_registration_policy": (
                        "conditional-on-each-real-asset-passing-provider-acquisition-"
                        "raw-byte-derivation-and-final-quality-gates"
                    ),
                },
                "current_session_evidence": evidence,
                "continuation": {
                    "contract": "org-wechat-runtime-current-session-continuation-v1",
                    "binding_digest": binding_report.get("binding_digest"),
                    "trusted_bundle_sha256": local.get("trusted_bundle_sha256"),
                    "installed_release_sha256": local.get(
                        "installed_release_sha256"
                    ),
                    "registry_digest": local.get("registry_digest"),
                    "adapter_sha256": expected_binding["adapter_sha256"],
                    "generation_route_id": expected_binding[
                        "generation_route_id"
                    ],
                    "provider_session_id": provider_session_id,
                    "allowed_next_phases": ["bootstrap", "authoring", "full"],
                    "scope": "same-host-session-only",
                },
                "errors": [],
            }
        )
        return _redact_report(finalized)

    probe = evidence.get("probe")
    if not isinstance(probe, dict):
        raise ValueError("current-session migration probe evidence is missing")
    actions = binding_report.get("host_setup_actions")
    probe_action = next(
        (
            item
            for item in actions
            if isinstance(item, dict) and item.get("id") == "run-migration-rgba-route-probe"
        ),
        None,
    ) if isinstance(actions, list) else None
    cases = probe_action.get("probe_cases") if isinstance(probe_action, dict) else None
    case = next(
        (
            item
            for item in cases
            if isinstance(item, dict) and item.get("attempt") == probe.get("attempt")
        ),
        None,
    ) if isinstance(cases, list) else None
    if not isinstance(case, dict):
        raise ValueError("current-session migration attempt is not a bound probe case")
    trace_fields = ("provider_session_id", "provider_request_id", "observed_download_id")
    if (
        probe.get("prompt_sha256") != case.get("prompt_sha256")
        or probe.get("host_request_metadata_sha256")
        != case.get("host_request_metadata_sha256")
        or any(
            not isinstance(probe.get(field), str)
            or not TOOL_ID.fullmatch(str(probe.get(field)))
            for field in trace_fields
        )
    ):
        raise ValueError("current-session provider trace identifiers are incomplete")
    artifact_root_path = _bound_migration_artifact_root(
        binding_report, probe_action, workspace_root
    )
    artifact_root = str(artifact_root_path)

    ingestion_entry = probe.get("download_ingestion")
    derivative_entry = probe.get("derivative_png")
    derivation_entry = probe.get("derivation_report")
    if not all(
        isinstance(item, dict)
        for item in (ingestion_entry, derivative_entry, derivation_entry)
    ):
        raise ValueError("current-session migration artifact evidence is incomplete")
    ingestion_expected = str(case["ingestion_report_path"]).replace(
        "{artifact_root}", artifact_root
    )
    raw_expected = str(case["raw_path"]).replace("{artifact_root}", artifact_root)
    derivative_expected = str(case["derived_path"]).replace(
        "{artifact_root}", artifact_root
    )
    derivation_expected = str(case["derivation_report_path"]).replace(
        "{artifact_root}", artifact_root
    )
    ingestion_path = _receipt_artifact_path(
        workspace_root,
        artifact_root_path,
        ingestion_entry.get("path"),
        ingestion_expected,
    )
    raw_path = _receipt_artifact_path(
        workspace_root, artifact_root_path, raw_expected, raw_expected
    )
    derivative_path = _receipt_artifact_path(
        workspace_root,
        artifact_root_path,
        derivative_entry.get("path"),
        derivative_expected,
    )
    derivation_path = _receipt_artifact_path(
        workspace_root,
        artifact_root_path,
        derivation_entry.get("path"),
        derivation_expected,
    )
    ingestion_payload = _read_json(ingestion_path)
    ingestion_binding = ingestion_payload.get("binding")
    ingestion_trace = ingestion_payload.get("host_trace")
    ingestion_source = ingestion_payload.get("source")
    ingestion_target = ingestion_payload.get("target")
    if (
        ingestion_entry.get("sha256") != _prefixed_file_sha256(ingestion_path)
        or ingestion_payload.get("kind") != "org-wechat-browser-download-ingestion-v1"
        or ingestion_payload.get("assurance") != "current-session-observed-path"
        or ingestion_payload.get("browser_event_attested") is not False
        or not isinstance(ingestion_binding, dict)
        or ingestion_binding.get("binding_nonce") != binding_report.get("binding_nonce")
        or ingestion_binding.get("binding_digest") != binding_report.get("binding_digest")
        or ingestion_binding.get("request_metadata_sha256")
        != case.get("host_request_metadata_sha256")
        or not isinstance(ingestion_trace, dict)
        or any(
            ingestion_trace.get(field) != probe.get(field) for field in trace_fields
        )
        or not isinstance(ingestion_source, dict)
        or not isinstance(ingestion_target, dict)
        or Path(str(ingestion_target.get("path"))).resolve() != raw_path
        or ingestion_source.get("sha256") != ingestion_target.get("sha256")
        or ingestion_source.get("byte_length") != ingestion_target.get("byte_length")
        or ingestion_target.get("sha256") != _prefixed_file_sha256(raw_path)
        or ingestion_target.get("byte_length") != raw_path.stat().st_size
        or ingestion_target.get("create_once") is not True
    ):
        raise ValueError("download ingestion report does not bind the exact current-session bytes")
    raw_bytes = raw_path.read_bytes()
    if not raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("ingested provider original is not a PNG")

    from asset_quality import inspect_png, validate_micro_asset
    from PIL import Image

    derivative_sha = _prefixed_file_sha256(derivative_path)
    derivative_inspection = inspect_png(derivative_path)
    with Image.open(derivative_path) as opened:
        opened.load()
        derivative_pixel_sha = "sha256:" + hashlib.sha256(
            f"{opened.mode}:{opened.width}x{opened.height}:".encode("ascii")
            + opened.tobytes()
        ).hexdigest()
    if (
        derivative_entry.get("sha256") != derivative_sha
        or derivative_entry.get("pixel_sha256") != derivative_pixel_sha
        or derivative_entry.get("mode") != "RGBA8"
        or derivative_inspection.get("bit_depth") != 8
        or derivative_inspection.get("color_type") != 6
        or not validate_micro_asset(derivative_path, "floating-spot").get("ok")
    ):
        raise ValueError("current-session derivative fails the exact RGBA8 pixel gate")
    derivation_payload = _validate_migration_derivation_report(
        binding_report=binding_report,
        source_binding_report_sha256=source_binding_report_sha256,
        probe_action=probe_action,
        case=case,
        artifact_root_path=artifact_root_path,
        ingestion_path=ingestion_path,
        raw_path=raw_path,
        derivative_path=derivative_path,
        derivation_path=derivation_path,
    )
    if (
        derivation_entry.get("sha256") != _prefixed_file_sha256(derivation_path)
        or derivation_entry.get("config_sha256")
        != (derivation_payload.get("processor") or {}).get("config_sha256")
        or (derivation_payload.get("output") or {}).get("file_sha256") != derivative_sha
        or (derivation_payload.get("final_validation") or {}).get("ok") is not True
    ):
        raise ValueError("current-session derivation report does not bind the approved output")
    surfaces = probe.get("inspection")
    if not isinstance(surfaces, dict) or set(surfaces) != {"transparent", "light", "dark"}:
        raise ValueError("transparent/light/dark exact-file inspections are required")
    for name, surface in surfaces.items():
        if (
            not isinstance(surface, dict)
            or surface.get("status") != "passed"
            or surface.get("derivative_sha256") != derivative_sha
            or not isinstance(surface.get("observation_id"), str)
        ):
            raise ValueError(f"current-session {name} inspection is incomplete")

    finalized = dict(binding_report)
    finalized.update(
        {
            "kind": MIGRATION_SESSION_REPORT_KIND,
            "check_level": "current-session-finalized",
            "ok": True,
            "phase_ready": False,
            "operational_ready": True,
            "assurance": "current-session-observed-path-not-portable-signed",
            "portable_signed_audit": False,
            "migration_selftest": {
                **dict(binding_report.get("migration_selftest") or {}),
                "status": "passed-current-session",
                "truth_columns": {
                    "local_pixel_chain_verified": True,
                    "host_trace_identifiers_bound": True,
                    "browser_event_cryptographically_attested": False,
                },
            },
            "current_session_evidence": evidence,
            "continuation": {
                "contract": "org-wechat-migration-current-session-continuation-v1",
                "binding_digest": binding_report.get("binding_digest"),
                "trusted_bundle_sha256": local.get("trusted_bundle_sha256"),
                "installed_release_sha256": local.get("installed_release_sha256"),
                "registry_digest": local.get("registry_digest"),
                "adapter_sha256": expected_binding["adapter_sha256"],
                "generation_route_id": expected_binding["generation_route_id"],
                "provider_session_id": probe.get("provider_session_id"),
                "allowed_next_phases": ["bootstrap", "authoring", "full"],
                "scope": "same-host-session-only",
            },
            "errors": [],
        }
    )
    return _redact_report(finalized)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_git_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _safe_url(value: Any, path: str, errors: list[dict[str, str]]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        _error(errors, "runtime.link.url_missing", path, "link URL is required")
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        _error(errors, "runtime.link.url_invalid", path, "link URL is invalid")
        return None
    if parsed.scheme != "https" or not parsed.hostname:
        _error(errors, "runtime.link.https_required", path, "link must be an https URL")
        return None
    try:
        port = parsed.port
    except ValueError:
        _error(errors, "runtime.link.port_invalid", path, "URL port is invalid")
        return None
    if port is not None:
        _error(errors, "runtime.link.port_forbidden", path, "explicit URL ports are forbidden")
    if parsed.username or parsed.password:
        _error(errors, "runtime.link.credentials_forbidden", path, "URL user info is forbidden")
        return None
    safe_pairs: list[tuple[str, str]] = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if SENSITIVE_QUERY_KEY.fullmatch(key):
            _error(
                errors,
                "runtime.link.secret_query_forbidden",
                path,
                f"URL query parameter {key!r} must not be stored",
            )
            continue
        if key not in {"node_id", "web_only"}:
            _error(
                errors,
                "runtime.link.query_forbidden",
                path,
                f"URL query parameter {key!r} is not in the credential-free allowlist",
            )
            continue
        safe_pairs.append((key, item))
    if parsed.fragment and SENSITIVE_VALUE.search(parsed.fragment):
        _error(errors, "runtime.link.secret_fragment_forbidden", path, "URL fragment contains secret material")
    safe_query = urlencode(safe_pairs)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, ""))


def _validate_ardot_url(value: str, path: str, errors: list[dict[str, str]]) -> None:
    parsed = urlsplit(value)
    if parsed.hostname != "ardot.tencent.com":
        _error(
            errors,
            "runtime.link.ardot_host_untrusted",
            path,
            "Ardot workspace host must be exactly ardot.tencent.com",
        )
    if not re.fullmatch(r"/file/[0-9]+", parsed.path):
        _error(
            errors,
            "runtime.link.ardot_path_invalid",
            path,
            "Ardot workspace path must be /file/<numeric-id>",
        )
    allowed_query = {"node_id", "web_only"}
    seen_query_keys: set[str] = set()
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if key in seen_query_keys:
            _error(
                errors,
                "runtime.link.ardot_query_duplicate",
                path,
                f"Ardot query parameter {key!r} must appear at most once",
            )
        seen_query_keys.add(key)
        if key not in allowed_query:
            _error(
                errors,
                "runtime.link.ardot_query_forbidden",
                path,
                f"Ardot query parameter {key!r} is not allowed",
            )
        if key == "web_only" and item != "1":
            _error(
                errors,
                "runtime.link.ardot_web_only_invalid",
                path,
                "Ardot web_only must equal 1 when present",
            )
    if parsed.fragment:
        _error(errors, "runtime.link.ardot_fragment_forbidden", path, "Ardot URL fragments are forbidden")


def _validate_wechat_url(
    value: str,
    mode: str,
    path: str,
    errors: list[dict[str, str]],
) -> None:
    parsed = urlsplit(value)
    expected_host = "api.weixin.qq.com" if mode == "api" else "mp.weixin.qq.com"
    if parsed.hostname != expected_host:
        _error(
            errors,
            "runtime.link.wechat_host_untrusted",
            path,
            f"WeChat {mode} host must be exactly {expected_host}",
        )
    if mode == "api":
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            _error(
                errors,
                "runtime.link.wechat_api_base_invalid",
                path,
                "WeChat API link must be the credential-free API base URL",
            )
    else:
        if parsed.path not in {"", "/"} and not parsed.path.startswith("/cgi-bin/"):
            _error(
                errors,
                "runtime.link.wechat_ui_path_invalid",
                path,
                "WeChat UI link must stay under mp.weixin.qq.com or /cgi-bin/",
            )
        if parsed.query:
            _error(
                errors,
                "runtime.link.wechat_session_query_forbidden",
                path,
                "store a credential-free WeChat base/editor path; session query parameters are forbidden",
            )
        if parsed.fragment:
            _error(errors, "runtime.link.wechat_fragment_forbidden", path, "WeChat URL fragments are forbidden")


def _validate_no_secrets(value: Any, errors: list[dict[str, str]], path: str = "profile") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if isinstance(key, str) and SENSITIVE_KEY.search(key):
                _error(
                    errors,
                    "runtime.secret.inline_field_forbidden",
                    child,
                    "store only a secret reference, never secret material",
                )
            _validate_no_secrets(item, errors, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_secrets(item, errors, f"{path}[{index}]")
    elif isinstance(value, str) and SENSITIVE_VALUE.search(value):
        _error(
            errors,
            "runtime.secret.inline_value_forbidden",
            path,
            "possible token, cookie, or encoded secret material is forbidden",
        )


def _validate_probe(
    probe: Any,
    path: str,
    errors: list[dict[str, str]],
    *,
    now: datetime,
    max_age_minutes: int,
    required_methods: set[str] | None = None,
) -> None:
    if not isinstance(probe, dict):
        _error(errors, "runtime.probe.missing", path, "a current probe object is required")
        return
    if probe.get("status") != "passed":
        _error(errors, "runtime.probe.not_passed", f"{path}.status", "probe status must be passed")
    method = probe.get("method")
    if not isinstance(method, str) or not method:
        _error(errors, "runtime.probe.method_missing", f"{path}.method", "probe method is required")
    elif required_methods is not None and method not in required_methods:
        _error(
            errors,
            "runtime.probe.method_invalid",
            f"{path}.method",
            f"probe method must be one of {sorted(required_methods)}",
        )
    checked_at = _parse_timestamp(probe.get("checked_at"))
    if checked_at is None:
        _error(
            errors,
            "runtime.probe.timestamp_invalid",
            f"{path}.checked_at",
            "probe timestamp must be timezone-aware ISO 8601",
        )
    else:
        age_seconds = (now - checked_at).total_seconds()
        if age_seconds < -300:
            _error(errors, "runtime.probe.timestamp_future", f"{path}.checked_at", "probe timestamp is in the future")
        elif age_seconds > max_age_minutes * 60:
            _error(
                errors,
                "runtime.probe.stale",
                f"{path}.checked_at",
                f"probe is older than {max_age_minutes} minutes",
            )
    evidence = probe.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        _error(errors, "runtime.probe.evidence_missing", f"{path}.evidence", "probe evidence is required")
    elif len(evidence) > 240 or SENSITIVE_VALUE.search(evidence):
        _error(
            errors,
            "runtime.probe.evidence_unsafe",
            f"{path}.evidence",
            "probe evidence must be a short, redacted identifier",
        )


def _validate_local_paths(workspace_root: Path, errors: list[dict[str, str]]) -> dict[str, Any]:
    missing: list[str] = []
    for relative in REQUIRED_PATHS:
        required_path = workspace_root / relative
        trusted_file = required_path.is_file() and not required_path.is_symlink()
        if trusted_file:
            try:
                required_path.resolve(strict=True).relative_to(workspace_root)
            except (OSError, ValueError):
                trusted_file = False
        if not trusted_file:
            missing.append(relative)
            _error(
                errors,
                "runtime.local.required_file_missing_or_untrusted",
                relative,
                "required workflow file is missing, a symlink, or outside the workspace",
            )

    scan_files = set(LINK_SCAN_FILES)
    scan_files.update(
        path.relative_to(workspace_root).as_posix()
        for path in (workspace_root / "references").glob("*.md")
        if path.is_file()
    )
    broken_links: list[dict[str, str]] = []
    for relative in sorted(scan_files):
        source = workspace_root / relative
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local_target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = (source.parent / local_target).resolve()
            try:
                resolved.relative_to(workspace_root)
            except ValueError:
                broken_links.append({"source": relative, "target": target})
                _error(
                    errors,
                    "runtime.local.link_outside_workspace",
                    relative,
                    f"local Markdown link escapes workspace: {target}",
                )
                continue
            if not resolved.exists():
                broken_links.append({"source": relative, "target": target})
                _error(
                    errors,
                    "runtime.local.link_broken",
                    relative,
                    f"local Markdown link does not resolve: {target}",
                )

    setup_links_status = "passed"
    setup_links_path = workspace_root / "runtime" / "setup-links.json"
    try:
        setup_links = json.loads(setup_links_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        setup_links_status = "failed"
        _error(
            errors,
            "runtime.local.setup_links_invalid",
            "runtime/setup-links.json",
            f"setup link registry cannot be read: {exc}",
        )
        setup_links = {}
    if not isinstance(setup_links, dict):
        setup_links_status = "failed"
        _error(
            errors,
            "runtime.local.setup_links_schema_invalid",
            "runtime/setup-links.json",
            "setup link registry root must be an object",
        )
        setup_links = {}
    else:
        _validate_no_secrets(setup_links, errors, "runtime.setup_links")
    if isinstance(setup_links, dict):
        if (
            setup_links.get("schema_version") != SCHEMA_VERSION
            or setup_links.get("kind") != "org-wechat-setup-links"
        ):
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.setup_links_schema_invalid",
                "runtime/setup-links.json",
                "setup link registry schema/kind is invalid",
            )
        if setup_links.get("support") != {
            "execution_host": "codex-desktop",
            "status": "supported-only-on-codex-desktop",
            "other_harnesses": "unsupported-until-a-reviewed-adapter-and-full-forward-test-are-released",
            "semantic_contract_portability_is_execution_support": False,
        }:
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.execution_host_support_invalid",
                "runtime/setup-links.json.support",
                "this release must declare Codex Desktop as its only supported execution host",
            )
        if setup_links.get("startup_policy") != {
            "declare_execution_conditions_first": True,
            "clone_check_before_source_material": True,
            "open_after_binding": True,
            "prepare_before_source_material": True,
            "migration_rgba_probe_before_source_material": False,
            "wait_for_user_login": True,
            "reprobe_after_login": True,
            "persist_session_query": False,
        }:
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.startup_policy_invalid",
                "runtime/setup-links.json.startup_policy",
                "startup policy must declare Codex-only conditions first, require clone check, open safe targets early, wait for login, and never persist session queries",
            )
        external = setup_links.get("external")
        if not isinstance(external, dict):
            external = {}
        for link_id, expected_url in EXPECTED_SETUP_LINKS.items():
            item = external.get(link_id)
            actual_url = item.get("url") if isinstance(item, dict) else None
            if actual_url != expected_url:
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.setup_link_missing",
                    f"runtime/setup-links.json.external.{link_id}",
                    f"setup link must equal {expected_url}",
                )
        local = setup_links.get("local")
        if not isinstance(local, dict):
            local = {}
        if set(local) != set(EXPECTED_LOCAL_SETUP_LINKS):
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.setup_link_set_invalid",
                "runtime/setup-links.json.local",
                "local setup links must cover the exact package-scoped runtime contract",
            )
        for link_id, (expected_package, expected_path) in (
            EXPECTED_LOCAL_SETUP_LINKS.items()
        ):
            item = local.get(link_id)
            actual_path = item.get("path") if isinstance(item, dict) else None
            actual_package = item.get("package") if isinstance(item, dict) else None
            package_root = _skill_package_root(workspace_root, expected_package)
            candidate = package_root / expected_path
            trusted_file = candidate.is_file() and not candidate.is_symlink()
            if trusted_file:
                try:
                    candidate.resolve(strict=True).relative_to(
                        package_root.resolve(strict=True)
                    )
                except (OSError, ValueError):
                    trusted_file = False
            if (
                actual_package != expected_package
                or actual_path != expected_path
                or not trusted_file
            ):
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.setup_link_missing",
                    f"runtime/setup-links.json.local.{link_id}",
                    "local setup link must resolve to "
                    f"{expected_package}/{expected_path} in the active source or sibling layout",
                )
        semantic_capabilities = setup_links.get("semantic_capabilities")
        if (
            not isinstance(semantic_capabilities, list)
            or semantic_capabilities != list(EXPECTED_SEMANTIC_CAPABILITIES)
            or len(set(semantic_capabilities)) != len(semantic_capabilities)
        ):
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.semantic_capabilities_invalid",
                "runtime/setup-links.json.semantic_capabilities",
                "semantic capability registry must match the canonical ordered capability contract",
            )

    adapter_path = workspace_root / "runtime" / "adapters" / "codex-desktop.json"
    try:
        adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        setup_links_status = "failed"
        _error(
            errors,
            "runtime.local.adapter_invalid",
            "runtime/adapters/codex-desktop.json",
            f"Codex adapter cannot be read: {exc}",
        )
        adapter = {}
    if not isinstance(adapter, dict):
        setup_links_status = "failed"
        _error(
            errors,
            "runtime.local.adapter_schema_invalid",
            "runtime/adapters/codex-desktop.json",
            "Codex adapter root must be an object",
        )
        adapter = {}
    else:
        _validate_no_secrets(adapter, errors, "runtime.codex_adapter")
    if isinstance(adapter, dict):
        adapter_capabilities = adapter.get("capabilities")
        if (
            adapter.get("schema_version") != SCHEMA_VERSION
            or adapter.get("kind") != "org-wechat-runtime-adapter"
            or adapter.get("harness") != "codex-desktop"
            or adapter.get("support_status")
            != "only-supported-execution-adapter"
            or not isinstance(adapter_capabilities, dict)
            or set(adapter_capabilities) != set(EXPECTED_SEMANTIC_CAPABILITIES)
        ):
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.adapter_schema_invalid",
                "runtime/adapters/codex-desktop.json",
                "Codex adapter must cover every canonical semantic capability exactly once",
            )
        elif any(
            not isinstance(adapter_capabilities[name], dict)
            or not isinstance(adapter_capabilities[name].get("requires"), list)
            or (
                adapter_capabilities[name].get("availability") == "unavailable"
                and (
                    adapter_capabilities[name]["requires"]
                    or not isinstance(adapter_capabilities[name].get("reason"), str)
                    or not adapter_capabilities[name]["reason"].strip()
                )
            )
            or (
                adapter_capabilities[name].get("availability") != "unavailable"
                and not adapter_capabilities[name]["requires"]
            )
            for name in EXPECTED_SEMANTIC_CAPABILITIES
        ):
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.adapter_route_invalid",
                "runtime/adapters/codex-desktop.json.capabilities",
                "every Codex adapter capability must declare a route, or an explicit unavailable reason with no phantom callable",
            )
        else:
            opaque_route = adapter_capabilities.get("image.generate.opaque")
            rgba_route = adapter_capabilities.get("image.generate.rgba")
            chatgpt_route = adapter_capabilities.get("chatgpt.session")
            if (
                not isinstance(opaque_route, dict)
                or opaque_route.get("route") != "tool"
                or opaque_route.get("requires") != ["image_gen__imagegen"]
            ):
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.adapter_visual_route_invalid",
                    "runtime/adapters/codex-desktop.json.capabilities.image.generate.opaque",
                    "Codex Desktop opaque generation must use the native image_gen route",
                )
            if (
                not isinstance(rgba_route, dict)
                or rgba_route.get("route") != "chatgpt-web"
                or rgba_route.get("requires")
                != [
                    "codex-with-chatgpt",
                    "browser:control-in-app-browser",
                    "mcp__node_repl__js",
                ]
                or rgba_route.get("output_contract") != "subject-cutout-rgba8-v1"
                or rgba_route.get("processor") != "scripts/prepare_micro_cutout.py"
                or rgba_route.get("provider_skill")
                != {
                    "id": "chatgpt-web-image-route",
                    "required_status": "loaded",
                    "contract": "chatgpt-web-image-route-v1",
                }
            ):
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.adapter_visual_route_invalid",
                    "runtime/adapters/codex-desktop.json.capabilities.image.generate.rgba",
                    "Codex Desktop RGBA generation must use the reviewed ChatGPT web route and cutout contract",
                )
            if (
                not isinstance(chatgpt_route, dict)
                or chatgpt_route.get("route") != "skill+browser"
                or chatgpt_route.get("requires") != ["codex-with-chatgpt"]
            ):
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.adapter_visual_route_invalid",
                    "runtime/adapters/codex-desktop.json.capabilities.chatgpt.session",
                    "Codex Desktop ChatGPT sessions must be bound through the codex-with-chatgpt Skill",
                )
            ingestion_route = adapter_capabilities.get("browser.download.ingest")
            if (
                not isinstance(ingestion_route, dict)
                or ingestion_route.get("route")
                != "browser-observed-path+local-create-once"
                or ingestion_route.get("requires")
                != [
                    "browser:control-in-app-browser",
                    "mcp__node_repl__js",
                    "scripts/ingest_browser_download.py",
                ]
                or ingestion_route.get("processor")
                != "scripts/ingest_browser_download.py"
            ):
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.adapter_download_route_invalid",
                    "runtime/adapters/codex-desktop.json.capabilities.browser.download.ingest",
                    "Codex Browser downloads must use the reviewed current-session create-once processor",
                )
            readback_route = adapter_capabilities.get(
                "wechat.current-session-readback"
            )
            if (
                not isinstance(readback_route, dict)
                or readback_route.get("route")
                != "browser-current-session-capture+local-create-once-ingestion"
                or readback_route.get("requires")
                != [
                    "browser:control-in-app-browser",
                    "mcp__node_repl__js",
                    "scripts/ingest_wechat_readback_capture.py",
                ]
                or readback_route.get("processor")
                != "scripts/ingest_wechat_readback_capture.py"
                or readback_route.get("assurance")
                != "current-session-only-nonportable"
            ):
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.adapter_wechat_readback_route_invalid",
                    "runtime/adapters/codex-desktop.json.capabilities.wechat.current-session-readback",
                    "Codex API draft readback must use the reviewed current-session UI capture ingestor",
                )
            wechat_api_route = adapter_capabilities.get("wechat.draft")
            if (
                not isinstance(wechat_api_route, dict)
                or wechat_api_route.get("route") != "verified-local-api-client"
                or wechat_api_route.get("requires") != ["scripts/wechat_publisher.py"]
                or wechat_api_route.get("processor") != "scripts/wechat_publisher.py"
            ):
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.adapter_wechat_api_route_invalid",
                    "runtime/adapters/codex-desktop.json.capabilities.wechat.draft",
                    "Codex WeChat API delivery must use the reviewed local publisher without persisting credentials",
                )

    try:
        dependency_lock = _read_json(
            workspace_root / "runtime" / "python-dependency-lock.json"
        )
        platform_support = _read_json(
            workspace_root / "runtime" / "platform-support.json"
        )
        non_mcp = _read_json(workspace_root / "runtime" / "non-mcp-dependencies.json")
    except ValueError as exc:
        setup_links_status = "failed"
        _error(
            errors,
            "runtime.local.dependency_contract_invalid",
            "runtime",
            str(exc),
        )
    else:
        locked_platforms = dependency_lock.get("platforms")
        supported_rows = platform_support.get("supported")
        supported_keys = {
            item.get("platform_key")
            for item in supported_rows
            if isinstance(item, dict) and item.get("status") == "locked"
        } if isinstance(supported_rows, list) else set()
        if (
            dependency_lock.get("support_policy", {}).get("unknown_platform")
            != "fail-before-target"
            or dependency_lock.get("support_policy", {}).get("candidate_is_trusted")
            is not False
            or not isinstance(locked_platforms, dict)
            or supported_keys != set(locked_platforms)
            or platform_support.get("supported_execution_hosts")
            != ["codex-desktop"]
        ):
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.platform_support_mismatch",
                "runtime/platform-support.json",
                "reviewed platform matrix must name only Codex Desktop, exactly match the dependency lock, and fail unknown platforms before target execution",
            )
        required_entrypoints = {
            "scripts/runtime_preflight.py",
            "scripts/ingest_browser_download.py",
            "scripts/ingest_wechat_readback_capture.py",
            "scripts/prepare_migration_probe.py",
            "scripts/export_ardot_handoff.py",
            "scripts/wechat_publisher.py",
        }
        if not required_entrypoints <= set(
            dependency_lock.get("allowed_entrypoints") or []
        ):
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.secure_entrypoints_incomplete",
                "runtime/python-dependency-lock.json.allowed_entrypoints",
                "runtime profile, migration probe, ingestion, Ardot handoff and WeChat publisher must be frozen secure-runner entrypoints",
            )
        dependency_ids = {
            item.get("id")
            for item in non_mcp.get("dependencies", [])
            if isinstance(item, dict)
        }
        if (
            non_mcp.get("kind") != "org-wechat-non-mcp-dependency-contract"
            or not {
                "python-locked-runtime",
                "codex-desktop-host",
                "codex-with-chatgpt",
                "browser-control-in-app-browser",
                "browser-download-ingestion",
                "source-zero-filesystem-lease",
                "migration-probe-finalizer",
            }
            <= dependency_ids
        ):
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.non_mcp_census_incomplete",
                "runtime/non-mcp-dependencies.json",
                "non-MCP dependency census is incomplete",
            )

    agent_error_count = len(errors)
    _validate_agent_mcp_contract(workspace_root, "agents/openai.yaml", errors)
    agent_manifest_status = "passed" if len(errors) == agent_error_count else "failed"

    return {
        "required_file_count": len(REQUIRED_PATHS),
        "missing_files": missing,
        "scanned_markdown_files": sorted(scan_files),
        "broken_links": broken_links,
        "setup_links": setup_links_status,
        "codex_adapter": "passed" if setup_links_status == "passed" else "failed",
        "agent_manifests": agent_manifest_status,
        "trusted_bundle_sha256": _trusted_bundle_digest(workspace_root),
    }


def _validate_python(
    workspace_root: Path,
    errors: list[dict[str, str]],
    *,
    external_write_root: Path | None = None,
) -> dict[str, Any]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 9):
        _error(errors, "runtime.python.version_unsupported", "python.version", "Python 3.9 or newer is required")
    pillow_version: str | None = None
    try:
        import PIL  # type: ignore

        pillow_version = str(PIL.__version__)
        if pillow_version != "11.3.0":
            _error(
                errors,
                "runtime.python.pillow_version_mismatch",
                "python.pillow",
                "Pillow must exactly match requirements.txt: 11.3.0",
            )
    except (ImportError, ValueError, AttributeError) as exc:
        _error(errors, "runtime.python.pillow_missing", "python.pillow", f"Pillow is unavailable: {exc}")

    cryptography_version: str | None = None
    try:
        import cryptography  # type: ignore

        cryptography_version = str(cryptography.__version__)
        if cryptography_version != "50.0.0":
            _error(
                errors,
                "runtime.python.cryptography_version_mismatch",
                "python.cryptography",
                "cryptography must exactly match requirements.txt: 50.0.0",
            )
    except (ImportError, ValueError, AttributeError) as exc:
        _error(
            errors,
            "runtime.python.cryptography_missing",
            "python.cryptography",
            f"cryptography is unavailable: {exc}",
        )

    write_probe = "not-required-read-only-installed-runtime"
    if external_write_root is not None:
        try:
            with tempfile.TemporaryDirectory(
                prefix=".runtime-preflight-", dir=external_write_root
            ) as directory:
                marker = Path(directory) / "probe.txt"
                marker.write_text("runtime-preflight\n", encoding="utf-8")
                if marker.read_text(encoding="utf-8") != "runtime-preflight\n":
                    raise OSError("external session readback mismatch")
            write_probe = "passed-external-session-root"
        except OSError as exc:
            write_probe = "failed-external-session-root"
            _error(
                errors,
                "runtime.local.external_session_not_writable",
                "session_root",
                f"external session write/read probe failed: {exc}",
            )

    git_revision: str | None = None
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace_root,
            env=_clean_git_environment(),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        candidate = completed.stdout.strip()
        if re.fullmatch(r"[0-9a-f]{40}", candidate):
            git_revision = candidate
    except (OSError, subprocess.SubprocessError):
        pass

    return {
        "python_version": version,
        "pillow_version": pillow_version,
        "cryptography_version": cryptography_version,
        "workspace_write_read": "not-attempted-read-only-runtime",
        "external_session_write_read": write_probe,
        "git_revision": git_revision,
    }


def _valid_watermark_key(value: str) -> bool:
    try:
        if value.startswith("hex:"):
            raw = bytes.fromhex(value[4:])
        elif value.startswith("base64:"):
            raw = base64.b64decode(value[7:], validate=True)
        else:
            return False
    except (ValueError, binascii.Error):
        return False
    return len(raw) >= 32


def _validate_private_root(
    value: str | None,
    errors: list[dict[str, str]],
    path: str,
) -> None:
    if not value:
        _error(
            errors,
            "runtime.private_root.ref_unresolved",
            path,
            "private watermark registry root is unavailable",
        )
        return
    candidate = Path(value).expanduser()
    if candidate.is_symlink():
        _error(
            errors,
            "runtime.private_root.symlink_forbidden",
            path,
            "private watermark registry root must not be a symlink",
        )
        return
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        _error(
            errors,
            "runtime.private_root.invalid",
            path,
            "private watermark registry root must be an existing directory",
        )
        return
    if not resolved.is_dir():
        _error(
            errors,
            "runtime.private_root.invalid",
            path,
            "private watermark registry root must be an existing directory",
        )
        return
    if not os.access(resolved, os.W_OK):
        _error(
            errors,
            "runtime.private_root.not_writable",
            path,
            "private watermark registry root is not writable",
        )
    try:
        completed = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--git-dir"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=_clean_git_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    if completed is not None and completed.returncode == 0:
        _error(
            errors,
            "runtime.private_root.inside_git",
            path,
            "private watermark registry root must be outside every Git repository",
        )


def _validate_harness_adapter(
    profile: dict[str, Any],
    workspace_root: Path,
    errors: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    harness = profile.get("harness")
    if not isinstance(harness, dict):
        _error(errors, "runtime.profile.harness_missing", "profile.harness", "harness object is required")
        return {}, {}
    name = harness.get("name")
    if not isinstance(name, str) or not TOOL_ID.fullmatch(name):
        _error(errors, "runtime.profile.harness_missing", "profile.harness.name", "harness name is required")
        return {}, {}
    adapter_path_value = harness.get("adapter_path")
    if not isinstance(adapter_path_value, str) or not adapter_path_value:
        _error(
            errors,
            "runtime.profile.adapter_path_missing",
            "profile.harness.adapter_path",
            "harness adapter path is required",
        )
        return {}, {}
    relative_adapter_path = Path(adapter_path_value)
    if relative_adapter_path.is_absolute():
        _error(
            errors,
            "runtime.profile.adapter_path_untrusted",
            "profile.harness.adapter_path",
            "harness adapter path must be workspace-relative",
        )
        return {}, {}
    raw_adapter_path = workspace_root / relative_adapter_path
    if raw_adapter_path.is_symlink():
        _error(
            errors,
            "runtime.profile.adapter_path_untrusted",
            "profile.harness.adapter_path",
            "harness adapter must not be a symlink",
        )
        return {}, {}
    adapter_path = raw_adapter_path.resolve()
    try:
        adapter_path.relative_to(workspace_root)
    except ValueError:
        _error(
            errors,
            "runtime.profile.adapter_path_untrusted",
            "profile.harness.adapter_path",
            "harness adapter must stay inside the workspace",
        )
        return {}, {}
    if not adapter_path.is_file():
        _error(
            errors,
            "runtime.profile.adapter_path_untrusted",
            "profile.harness.adapter_path",
            "harness adapter must be a regular non-symlink file",
        )
        return {}, {}
    declared_sha = harness.get("adapter_sha256")
    actual_sha = f"sha256:{_sha256(adapter_path)}"
    if declared_sha != actual_sha:
        _error(
            errors,
            "runtime.profile.adapter_sha256_mismatch",
            "profile.harness.adapter_sha256",
            "harness adapter SHA does not match the selected file",
        )
    try:
        adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        adapter = None
    if not isinstance(adapter, dict):
        _error(
            errors,
            "runtime.profile.adapter_invalid",
            "profile.harness.adapter_path",
            "harness adapter must be a JSON object",
        )
        return {}, {}
    _validate_no_secrets(adapter, errors, "profile.harness.adapter")
    adapter_capabilities = adapter.get("capabilities")
    if (
        adapter.get("schema_version") != SCHEMA_VERSION
        or adapter.get("kind") != "org-wechat-runtime-adapter"
        or adapter.get("harness") != name
        or not isinstance(adapter_capabilities, dict)
        or set(adapter_capabilities) != set(EXPECTED_SEMANTIC_CAPABILITIES)
    ):
        _error(
            errors,
            "runtime.profile.adapter_contract_mismatch",
            "profile.harness.adapter_path",
            "adapter identity and semantic capability set must match the selected harness",
        )
        adapter_capabilities = {}
    return {
        "name": name,
        "adapter_path": adapter_path_value,
        "adapter_sha256": actual_sha,
    }, adapter_capabilities


def _tool_map(
    profile: dict[str, Any],
    adapter_capabilities: dict[str, Any],
    errors: list[dict[str, str]],
    installed_registry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    tools = profile.get("tools")
    if not isinstance(tools, list):
        _error(errors, "runtime.tools.inventory_missing", "profile.tools", "tool inventory must be a list")
        return {}
    resolved: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(tools):
        path = f"profile.tools[{index}]"
        if not isinstance(item, dict):
            _error(errors, "runtime.tools.item_invalid", path, "tool inventory item must be an object")
            continue
        tool_id = item.get("id")
        kind = item.get("kind")
        if not isinstance(tool_id, str) or not TOOL_ID.fullmatch(tool_id):
            _error(errors, "runtime.tools.id_invalid", f"{path}.id", "tool id is invalid")
            continue
        if tool_id in resolved:
            _error(errors, "runtime.tools.id_duplicate", f"{path}.id", "tool id must be unique")
            continue
        if not isinstance(kind, str) or not TOOL_ID.fullmatch(kind):
            _error(errors, "runtime.tools.kind_invalid", f"{path}.kind", "tool kind is invalid")
        if item.get("status") != "available":
            _error(errors, "runtime.tools.not_available", f"{path}.status", "tool must be available")
        if item.get("source") not in {
            "runtime-registry",
            "skill-registry",
            "model-visible-current-session-intent",
        }:
            _error(
                errors,
                "runtime.tools.source_invalid",
                f"{path}.source",
                "tool route must come from the current runtime, Skill registry, or the explicit non-attested current-session intent initializer",
            )
        adapter_route = adapter_capabilities.get(kind)
        adapter_requires = adapter_route.get("requires") if isinstance(adapter_route, dict) else None
        if not isinstance(adapter_requires, list) or tool_id not in adapter_requires:
            _error(
                errors,
                "runtime.tools.adapter_route_unresolved",
                f"{path}.id",
                "tool id/kind is absent from the selected harness adapter",
            )
        provider = item.get("provider")
        session_id = item.get("session_id")
        if not isinstance(provider, str) or not TOOL_ID.fullmatch(provider):
            _error(errors, "runtime.tools.provider_invalid", f"{path}.provider", "tool provider is required")
        if not isinstance(session_id, str) or not TOOL_ID.fullmatch(session_id):
            _error(
                errors,
                "runtime.tools.session_invalid",
                f"{path}.session_id",
                "current host session id is required",
            )
        registry_item = (installed_registry.get("tools") or {}).get(tool_id)
        compared_fields = ("id", "kind", "status", "source", "provider", "session_id")
        if not isinstance(registry_item, dict):
            _error(
                errors,
                "runtime.tools.registry_missing",
                path,
                "tool is absent from the machine-generated current host registry census",
            )
        elif any(item.get(field) != registry_item.get(field) for field in compared_fields):
            _error(
                errors,
                "runtime.tools.profile_not_registry",
                path,
                "tool identity/status/provider/session does not match the current host registry census",
            )
        resolved[tool_id] = item
    return resolved


def _require_tool_kinds(
    tool_ids: Any,
    path: str,
    tool_map: dict[str, dict[str, Any]],
    errors: list[dict[str, str]],
    accepted_kind_sets: Iterable[set[str]],
) -> list[str]:
    if not isinstance(tool_ids, list) or not tool_ids:
        _error(errors, "runtime.capability.tool_ids_missing", path, "capability requires tool_ids")
        return []
    resolved_ids: list[str] = []
    kinds: set[str] = set()
    contexts: set[tuple[str, str]] = set()
    for index, value in enumerate(tool_ids):
        item_path = f"{path}[{index}]"
        if not isinstance(value, str) or value not in tool_map:
            _error(
                errors,
                "runtime.capability.tool_unresolved",
                item_path,
                "tool id is absent from the available runtime inventory",
            )
            continue
        resolved_ids.append(value)
        kind = tool_map[value].get("kind")
        if isinstance(kind, str):
            kinds.add(kind)
        provider = tool_map[value].get("provider")
        session_id = tool_map[value].get("session_id")
        if isinstance(provider, str) and isinstance(session_id, str):
            contexts.add((provider, session_id))
    if resolved_ids and not any(required <= kinds for required in accepted_kind_sets):
        expected = [sorted(item) for item in accepted_kind_sets]
        _error(
            errors,
            "runtime.capability.tool_kind_mismatch",
            path,
            f"tool kinds {sorted(kinds)} do not satisfy any required set {expected}",
        )
    if len(contexts) > 1:
        _error(
            errors,
            "runtime.capability.tool_context_mismatch",
            path,
            "all tools for one capability must come from the same provider and current host session",
        )
    return resolved_ids


def _require_adapter_routes(
    route_kinds: Iterable[str],
    tool_ids: list[str],
    adapter_capabilities: dict[str, Any],
    errors: list[dict[str, str]],
    path: str,
) -> None:
    supplied = set(tool_ids)
    for route_kind in route_kinds:
        route = adapter_capabilities.get(route_kind)
        required = route.get("requires") if isinstance(route, dict) else None
        if not isinstance(required, list) or not required:
            _error(
                errors,
                "runtime.capability.adapter_route_missing",
                path,
                f"selected adapter has no complete route for {route_kind}",
            )
            continue
        missing = sorted(set(required) - supplied)
        if missing:
            _error(
                errors,
                "runtime.capability.adapter_dependencies_missing",
                path,
                f"selected {route_kind} route is missing adapter dependencies: {missing}",
            )


def _git_value(workspace_root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=workspace_root,
            env=_clean_git_environment(),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _has_any_symlink_component(path: Path) -> bool:
    """Return true when an absolute path traverses any symbolic link."""

    absolute = _canonical_absolute_path(path)
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


_INTENT_KIND_PRIORITY = (
    "host.registry.export",
    "wechat.current-session-authority",
    "host.receipt.attest",
    "host.migration.finalize",
    "filesystem.access.lease",
    "chatgpt.session",
    "browser.control",
    "computer.use",
    "ardot.create",
    "ardot.read",
    "ardot.write",
    "ardot.export",
    "image.provider.acquire.authority",
    "image.generate.opaque",
    "image.generate.rgba",
    "image.inspect",
    "wechat.draft",
)


def _intent_provider_for_kind(kind: str) -> str:
    if kind.startswith("ardot."):
        return "ardot-remote"
    if kind in {"browser.control", "chatgpt.session"}:
        return "codex-browser"
    if kind == "computer.use":
        return "codex-computer-use"
    if kind.startswith("image."):
        return "codex-image-provider"
    if kind.startswith("wechat."):
        return "codex-wechat-host"
    return "codex-host"


def build_current_session_registry_census(
    visible_tool_ids: list[str],
    workspace_root: Path,
    *,
    phase: str,
    session_id: str,
    adapter_path: Path,
    skills_root: Path,
    release_manifest_path: Path,
) -> dict[str, Any]:
    """Build a non-attested census from the model-visible tool identifier set.

    Status, semantic kind, provider grouping and installed Skill paths are
    derived from the reviewed adapter/release.  The result is binding intent
    for this host session and never an authoritative host registry export.
    """

    if phase not in PHASES:
        raise ValueError("current-session registry intent phase is invalid")
    if not isinstance(session_id, str) or not TOOL_ID.fullmatch(session_id):
        raise ValueError("current-session registry intent session id is invalid")
    if not isinstance(visible_tool_ids, list) or not visible_tool_ids:
        raise ValueError("at least one model-visible tool id is required")
    if any(
        not isinstance(tool_id, str) or not TOOL_ID.fullmatch(tool_id)
        for tool_id in visible_tool_ids
    ):
        raise ValueError("model-visible tool identifiers are invalid")
    if len(visible_tool_ids) != len(set(visible_tool_ids)):
        raise ValueError("model-visible tool identifiers must be unique")

    workspace_root = _canonical_existing_input(workspace_root, "workspace root")
    adapter_resolved = _canonical_existing_input(adapter_path, "adapter")
    _canonical_existing_input(skills_root, "skills root")
    _canonical_existing_input(release_manifest_path, "release manifest")
    adapter = _read_json(adapter_resolved)
    capabilities = adapter.get("capabilities")
    if (
        adapter.get("schema_version") != SCHEMA_VERSION
        or adapter.get("kind") != "org-wechat-runtime-adapter"
        or not isinstance(adapter.get("harness"), str)
        or not isinstance(capabilities, dict)
    ):
        raise ValueError("selected adapter is invalid")

    allowed_kinds_by_tool: dict[str, set[str]] = {}
    for kind, route in capabilities.items():
        if not isinstance(route, dict) or route.get("availability") == "unavailable":
            continue
        for tool_id in route.get("requires", []):
            if (
                isinstance(tool_id, str)
                and not ENV_REF.fullmatch(tool_id)
                and not tool_id.startswith("scripts/")
            ):
                allowed_kinds_by_tool.setdefault(tool_id, set()).add(kind)

    tool_rows: list[dict[str, str]] = []
    ignored: list[str] = []
    for tool_id in sorted(visible_tool_ids):
        kinds = allowed_kinds_by_tool.get(tool_id)
        if not kinds:
            ignored.append(tool_id)
            continue
        kind = next(
            (candidate for candidate in _INTENT_KIND_PRIORITY if candidate in kinds),
            sorted(kinds)[0],
        )
        tool_rows.append(
            {
                "id": tool_id,
                "kind": kind,
                "status": "available",
                "source": "model-visible-current-session-intent",
                "provider": _intent_provider_for_kind(kind),
                "session_id": session_id,
            }
        )

    from release_skills import verify_installed_packages

    try:
        release = verify_installed_packages(
            skills_root.expanduser(),
            release_manifest_path.expanduser().resolve(strict=True),
            workspace_root,
            verify_workspace_source=False,
        )
    except Exception as exc:
        raise ValueError(
            f"verified installed Skill release is unavailable: {exc}"
        ) from exc
    installed = {
        item.get("package"): Path(str(item.get("path")))
        for item in release.get("verified", [])
        if isinstance(item, dict) and isinstance(item.get("package"), str)
    }
    expected_skill_ids = {
        "org-wechat-studio",
        "chatgpt-web-image-route",
        "ardot-wechat-publisher",
    }
    if release.get("ok") is not True or set(installed) != expected_skill_ids:
        raise ValueError("verified installed Skill release is incomplete")
    loaded_skill_ids = {PHASE_LOADED_SKILL[phase]}
    rgba_route = capabilities.get("image.generate.rgba")
    if (
        phase in {"migration", "authoring", "full"}
        and isinstance(rgba_route, dict)
        and rgba_route.get("route") == "chatgpt-web"
    ):
        loaded_skill_ids.add("chatgpt-web-image-route")
    skill_rows = [
        {
            "id": skill_id,
            "status": "loaded" if skill_id in loaded_skill_ids else "available",
            "installed_entrypoint": str(
                (installed[skill_id] / "SKILL.md").resolve(strict=True)
            ),
        }
        for skill_id in sorted(expected_skill_ids)
    ]
    raw_intent = {
        "schema_version": 1,
        "kind": CURRENT_SESSION_REGISTRY_INTENT_KIND,
        "harness": adapter["harness"],
        "session_id": session_id,
        "intent_phase": phase,
        "tools": tool_rows,
        "skills": skill_rows,
        "ignored_model_visible_tool_ids": ignored,
    }
    return build_host_registry_census(
        raw_intent,
        workspace_root,
        adapter_path=adapter_resolved,
        skills_root=skills_root,
        release_manifest_path=release_manifest_path,
        allow_current_session_intent=True,
        phase=phase,
    )


def build_host_registry_census(
    raw_registry: dict[str, Any],
    workspace_root: Path,
    *,
    adapter_path: Path,
    skills_root: Path,
    release_manifest_path: Path,
    allow_current_session_intent: bool = False,
    phase: str | None = None,
) -> dict[str, Any]:
    """Normalize a host registry export and verify installed release bytes.

    The host export supplies live registry identity/status.  Local processor
    entries are added only when their exact bytes are part of this trusted
    workspace; installed Skill bytes are independently checked by
    ``release_skills.verify_installed_packages``.
    """

    workspace_root = _canonical_existing_input(workspace_root, "workspace root")
    registry_kind = raw_registry.get("kind")
    if (
        raw_registry.get("schema_version") != 1
        or registry_kind
        not in {
            HOST_REGISTRY_EXPORT_KIND,
            CURRENT_SESSION_REGISTRY_INTENT_KIND,
        }
        or (
            registry_kind == CURRENT_SESSION_REGISTRY_INTENT_KIND
            and not allow_current_session_intent
        )
        or not isinstance(raw_registry.get("harness"), str)
        or not isinstance(raw_registry.get("session_id"), str)
        or not TOOL_ID.fullmatch(raw_registry["harness"])
        or not TOOL_ID.fullmatch(raw_registry["session_id"])
    ):
        raise ValueError("host registry export schema/identity is invalid")
    adapter_resolved = _canonical_existing_input(adapter_path, "adapter")
    _canonical_existing_input(skills_root, "skills root")
    _canonical_existing_input(release_manifest_path, "release manifest")
    try:
        adapter_relative = adapter_resolved.relative_to(workspace_root).as_posix()
    except ValueError as exc:
        raise ValueError("adapter must be a reviewed file inside the workspace") from exc
    if adapter_resolved.is_symlink() or not adapter_resolved.is_file():
        raise ValueError("adapter must be a regular non-symlink file")
    adapter = _read_json(adapter_resolved)
    if (
        adapter.get("schema_version") != SCHEMA_VERSION
        or adapter.get("kind") != "org-wechat-runtime-adapter"
        or adapter.get("harness") != raw_registry["harness"]
        or not isinstance(adapter.get("capabilities"), dict)
    ):
        raise ValueError("host registry export does not match the selected adapter")
    adapter_capabilities = adapter["capabilities"]
    if registry_kind == HOST_REGISTRY_EXPORT_KIND:
        export_route = adapter_capabilities.get("host.registry.export")
        export_trace = raw_registry.get("registry_export")
        if (
            not isinstance(export_route, dict)
            or export_route.get("availability") == "unavailable"
            or not isinstance(export_trace, dict)
            or export_trace.get("capability") != "host.registry.export"
            or export_trace.get("tool_id") not in export_route.get("requires", [])
            or export_trace.get("session_id") != raw_registry.get("session_id")
            or not isinstance(export_trace.get("provider"), str)
            or not TOOL_ID.fullmatch(str(export_trace.get("provider")))
            or not isinstance(export_trace.get("request_id"), str)
            or not TOOL_ID.fullmatch(str(export_trace.get("request_id")))
        ):
            raise ValueError(
                "host registry export must come from the adapter-declared host.registry.export callable"
            )
    else:
        if raw_registry.get("intent_phase") not in PHASES:
            raise ValueError("current-session registry intent phase is invalid")

    selected_phase = phase or (
        str(raw_registry.get("intent_phase"))
        if registry_kind == CURRENT_SESSION_REGISTRY_INTENT_KIND
        else str(raw_registry.get("census_phase") or "full")
    )
    if selected_phase not in PHASES:
        raise ValueError("host registry census phase is invalid")
    if (
        registry_kind == CURRENT_SESSION_REGISTRY_INTENT_KIND
        and raw_registry.get("intent_phase") != selected_phase
    ):
        raise ValueError("current-session registry intent phase is inconsistent")

    from release_skills import FORBIDDEN_PARTS, verify_installed_packages

    try:
        release_result = verify_installed_packages(
            skills_root.expanduser(),
            release_manifest_path.expanduser().resolve(strict=True),
            workspace_root,
            verify_workspace_source=False,
        )
    except Exception as exc:
        raise ValueError(f"installed Skill release verification failed: {exc}") from exc
    if release_result.get("ok") is not True:
        raise ValueError("installed Skill release verification failed")
    installed_by_name = {
        item.get("package"): item
        for item in release_result.get("verified", [])
        if isinstance(item, dict) and isinstance(item.get("package"), str)
    }
    registry_skills = raw_registry.get("skills")
    if not isinstance(registry_skills, list):
        raise ValueError("host registry export skills must be a list")
    skill_status: dict[str, str] = {}
    skill_registry_entrypoints: dict[str, Path] = {}
    for item in registry_skills:
        if not isinstance(item, dict):
            raise ValueError("host registry Skill entry is invalid")
        skill_id = item.get("id")
        status = item.get("status")
        installed_entrypoint = item.get("installed_entrypoint")
        if (
            not isinstance(skill_id, str)
            or not TOOL_ID.fullmatch(skill_id)
            or status not in {"loaded", "available"}
            or not isinstance(installed_entrypoint, str)
            or not installed_entrypoint
            or skill_id in skill_status
        ):
            raise ValueError(
                "host registry Skill identity/status/installed entrypoint is invalid or duplicated"
            )
        raw_entrypoint = _canonical_absolute_path(Path(installed_entrypoint))
        if _has_any_symlink_component(raw_entrypoint):
            raise ValueError(
                f"host registry Skill entrypoint contains a symlink: {skill_id}"
            )
        try:
            resolved_entrypoint = raw_entrypoint.resolve(strict=True)
        except OSError as exc:
            raise ValueError(
                f"host registry Skill entrypoint is unavailable: {skill_id}"
            ) from exc
        if not resolved_entrypoint.is_file():
            raise ValueError(
                f"host registry Skill entrypoint is not a regular file: {skill_id}"
            )
        skill_status[skill_id] = status
        skill_registry_entrypoints[skill_id] = resolved_entrypoint
    expected_packages = {
        "org-wechat-studio",
        "chatgpt-web-image-route",
        "ardot-wechat-publisher",
    }
    if set(installed_by_name) != expected_packages or not expected_packages <= set(skill_status):
        raise ValueError("host registry does not cover all verified installed Skill packages")
    skills: list[dict[str, Any]] = []
    for skill_id in sorted(expected_packages):
        entrypoint = Path(str(installed_by_name[skill_id]["path"])) / "SKILL.md"
        if entrypoint.is_symlink() or not entrypoint.is_file():
            raise ValueError(f"installed Skill entrypoint is unsafe: {skill_id}")
        expected_entrypoint = entrypoint.resolve(strict=True)
        if skill_registry_entrypoints[skill_id] != expected_entrypoint:
            raise ValueError(
                f"host registry Skill path does not match the verified installed release: {skill_id}"
            )
        skills.append(
            {
                "id": skill_id,
                "installed_entrypoint": str(expected_entrypoint),
                "host_registry_entrypoint": str(skill_registry_entrypoints[skill_id]),
                "entrypoint_sha256": _prefixed_file_sha256(entrypoint),
                "registry_status": skill_status[skill_id],
                "package_bundle_sha256": installed_by_name[skill_id].get(
                    "bundle_sha256"
                ),
            }
        )

    raw_tools = raw_registry.get("tools")
    if not isinstance(raw_tools, list):
        raise ValueError("host registry export tools must be a list")
    selected_semantic_kinds = PHASE_REGISTRY_SEMANTIC_KINDS[selected_phase]
    if registry_kind == HOST_REGISTRY_EXPORT_KIND:
        selected_semantic_kinds = {*selected_semantic_kinds, "host.registry.export"}
    required_ids = {
        tool_id
        for semantic_kind, route in adapter["capabilities"].items()
        if semantic_kind in selected_semantic_kinds
        if isinstance(route, dict) and isinstance(route.get("requires"), list)
        for tool_id in route["requires"]
        if isinstance(tool_id, str) and not ENV_REF.fullmatch(tool_id)
    }
    tool_rows: dict[str, dict[str, str]] = {}
    for item in raw_tools:
        if not isinstance(item, dict):
            raise ValueError("host registry tool entry is invalid")
        tool_id = item.get("id")
        if tool_id not in required_ids:
            continue
        kind = item.get("kind")
        provider = item.get("provider")
        session_id = item.get("session_id")
        if (
            not isinstance(tool_id, str)
            or not isinstance(kind, str)
            or not isinstance(provider, str)
            or not isinstance(session_id, str)
            or not TOOL_ID.fullmatch(tool_id)
            or not TOOL_ID.fullmatch(kind)
            or not TOOL_ID.fullmatch(provider)
            or not TOOL_ID.fullmatch(session_id)
            or item.get("status") != "available"
            or tool_id in tool_rows
        ):
            raise ValueError("host registry tool identity/status is invalid or duplicated")
        route = adapter["capabilities"].get(kind)
        if not isinstance(route, dict) or tool_id not in route.get("requires", []):
            raise ValueError(f"host registry tool is not mapped by the adapter: {tool_id}")
        tool_rows[tool_id] = {
            "id": tool_id,
            "kind": kind,
            "status": "available",
            "source": str(item.get("source") or "runtime-registry"),
            "provider": provider,
            "session_id": session_id,
        }
    if registry_kind == HOST_REGISTRY_EXPORT_KIND:
        export_trace = raw_registry["registry_export"]
        export_tool = tool_rows.get(str(export_trace.get("tool_id")))
        if (
            not isinstance(export_tool, dict)
            or export_tool.get("kind") != "host.registry.export"
            or export_tool.get("provider") != export_trace.get("provider")
            or export_tool.get("session_id") != export_trace.get("session_id")
        ):
            raise ValueError(
                "host registry export trace does not match its model-visible host tool row"
            )
    for local_tool_id, local_kind in (
        ("scripts/ingest_browser_download.py", "browser.download.ingest"),
        (
            "scripts/ingest_wechat_readback_capture.py",
            "wechat.current-session-readback",
        ),
        ("scripts/wechat_publisher.py", "wechat.draft"),
    ):
        if local_tool_id not in required_ids:
            continue
        local_tool = workspace_root / local_tool_id
        if local_tool.is_symlink() or not local_tool.is_file():
            raise ValueError(f"reviewed local runtime tool is unavailable: {local_tool_id}")
        provider = raw_registry["harness"]
        session_id = raw_registry["session_id"]
        if local_kind == "browser.download.ingest":
            ui_context = tool_rows.get("browser:control-in-app-browser")
            if not isinstance(ui_context, dict):
                raise ValueError(
                    "local Browser ingestion/capture requires the current Browser registry context"
                )
            provider = ui_context["provider"]
            session_id = ui_context["session_id"]
        elif local_kind == "wechat.current-session-readback":
            ui_context = tool_rows.get("browser:control-in-app-browser")
            if not isinstance(ui_context, dict):
                ui_context = next(
                    (
                        item
                        for item in tool_rows.values()
                        if item.get("kind") == "computer.use"
                    ),
                    None,
                )
            if not isinstance(ui_context, dict):
                # A portable signed API delivery does not need the
                # current-session UI readback route. Leave this optional route
                # absent from the census when Browser/Computer Use is unavailable;
                # profile construction/validation will still reject a
                # nonportable API draft that selects it.
                continue
            provider = ui_context["provider"]
            session_id = ui_context["session_id"]
        tool_rows[local_tool_id] = {
            "id": local_tool_id,
            "kind": local_kind,
            "status": "available",
            "source": "runtime-registry",
            "provider": provider,
            "session_id": session_id,
        }

    def route_complete(semantic_kind: str) -> bool:
        route = adapter_capabilities.get(semantic_kind)
        required = route.get("requires") if isinstance(route, dict) else None
        return bool(
            isinstance(required, list)
            and required
            and all(tool_id in tool_rows for tool_id in required)
        )

    publication_routes = {
        "draft": {
            "api": {
                "available": route_complete("wechat.draft")
                and any(
                    item.get("kind") == "wechat.draft"
                    for item in tool_rows.values()
                ),
                "implies_publication_authority": False,
            },
            "ui": {
                "available": route_complete("browser.control")
                or route_complete("computer.use")
            },
        },
        "current_session_publish": {
            "api": {
                "available": route_complete("wechat.current-session-authority"),
                "independent_capability": "wechat.current-session-authority",
                "inferred_from_wechat_draft": False,
            },
            "ui": {
                "available": route_complete("browser.control")
                or route_complete("computer.use"),
                "requires_live_confirmation_and_authoritative_readback": True,
            },
        },
        "current_session_readback": {
            "available": route_complete("wechat.current-session-readback"),
            "assurance": "current-session-only-nonportable",
            "implies_publication_authority": False,
        },
        "portable_signed_publish": {
            "available": route_complete("host.receipt.attest"),
            "independent_capability": "host.receipt.attest",
        },
    }
    provider_acquisition_routes = {
        "current_session": {
            "available": True,
            "operational_ready": False,
            "authority_mode": "current-session-operator-harness-trusted",
            "assurance": "operator-harness-trusted-current-session",
            "host_attested": False,
            "portable": False,
            "required_asset_gates": [
                "current-session-runtime-binding",
                "canonical-provider-request",
                "create-once-download-ingestion",
                "exact-raw-byte-binding",
                "rgba8-alpha-pixel-validation",
            ],
            "optional_policy_hook": {
                "capability": "image.provider.acquire.authority",
                "available": route_complete("image.provider.acquire.authority"),
                "can_veto": True,
                "can_upgrade_assurance": False,
            },
        },
        "portable": {
            "available": route_complete("host.receipt.attest"),
            "receipt_kind": "org-wechat-provider-image-host-receipt-v1",
            "authority_mode": "portable-signed",
        },
        "without_complete_chain": {
            "authority_mode": "structural-only",
            "formal_micro_ready": False,
        },
    }

    git_common_dir = _git_value(workspace_root, "rev-parse", "--git-common-dir")
    if git_common_dir and not Path(git_common_dir).is_absolute():
        git_common_dir = str((workspace_root / git_common_dir).resolve())
    manifest_resolved = release_manifest_path.expanduser().resolve(strict=True)
    try:
        manifest_reference = manifest_resolved.relative_to(workspace_root).as_posix()
    except ValueError:
        manifest_reference = str(manifest_resolved)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": HOST_REGISTRY_CENSUS_KIND,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "harness": {
            "name": raw_registry["harness"],
            "session_id": raw_registry["session_id"],
            "adapter_path": adapter_relative,
            "adapter_sha256": _prefixed_file_sha256(adapter_resolved),
        },
        "workspace_identity": {
            "workspace_root": str(workspace_root),
            "workspace_root_sha256": "sha256:"
            + hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest(),
            "git_common_dir": git_common_dir,
            "git_head": _git_value(workspace_root, "rev-parse", "HEAD"),
        },
        "installed_release": {
            "skills_root": str(skills_root.expanduser().resolve(strict=True)),
            "manifest_path": manifest_reference,
            "manifest_sha256": _prefixed_file_sha256(manifest_resolved),
            "release_sha256": release_result.get("release_sha256"),
            "source_zero_forbidden_parts_absent": sorted(FORBIDDEN_PARTS),
        },
        "registry_assurance": {
            "mode": (
                "host-callable-current-session-export"
                if registry_kind == HOST_REGISTRY_EXPORT_KIND
                else "current-session-model-visible-intent"
            ),
            "host_registry_export_callable": registry_kind
            == HOST_REGISTRY_EXPORT_KIND,
            "host_attested_registry": False,
            "portable": False,
            "requires_later_live_probes": True,
            "intent_phase": raw_registry.get("intent_phase"),
            "census_phase": selected_phase,
            "ignored_model_visible_tool_ids": raw_registry.get(
                "ignored_model_visible_tool_ids", []
            ),
        },
        "publication_routes": publication_routes,
        "provider_acquisition_routes": provider_acquisition_routes,
        "tools": sorted(tool_rows.values(), key=lambda item: item["id"]),
        "skills": skills,
        "truth_boundary": (
            "Registry identity and installed bytes only; login, browser events, generation, "
            "filesystem isolation and phase readiness require separate current-session evidence."
        ),
    }
    payload["registry_digest"] = _canonical_sha256(payload)
    return payload


def _validate_registry_census(
    profile: dict[str, Any],
    workspace_root: Path,
    errors: list[dict[str, str]],
    *,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify installed Skill package bytes through the release manifest API."""

    if override is not None:
        if override.get("verified") is not True or not isinstance(override.get("skills"), dict):
            _error(errors, "runtime.registry.override_invalid", "registry", "test registry override is invalid")
            return {}
        return override
    reference = profile.get("registry_census")
    if not isinstance(reference, dict):
        _error(
            errors,
            "runtime.registry.census_missing",
            "profile.registry_census",
            "a machine-generated current host registry census is required; profile Skill status is not trusted",
        )
        return {}
    census_path_value = reference.get("path")
    if not isinstance(census_path_value, str) or not census_path_value:
        _error(errors, "runtime.registry.census_path_invalid", "profile.registry_census.path", "registry census path is required")
        return {}
    census_path = _canonical_absolute_path(Path(census_path_value))
    if census_path.is_symlink() or _has_any_symlink_component(census_path):
        _error(errors, "runtime.registry.census_path_unsafe", "profile.registry_census.path", "registry census path must not contain symlinks")
        return {}
    try:
        resolved = census_path.resolve(strict=True)
        census = _read_json(resolved)
    except (OSError, ValueError) as exc:
        _error(errors, "runtime.registry.census_unavailable", "profile.registry_census.path", str(exc))
        return {}
    actual_sha = _prefixed_file_sha256(resolved)
    if reference.get("sha256") != actual_sha:
        _error(errors, "runtime.registry.census_sha_mismatch", "profile.registry_census.sha256", "registry census bytes changed")
    if (
        census.get("schema_version") != 1
        or census.get("kind") != HOST_REGISTRY_CENSUS_KIND
        or census.get("registry_digest")
        != _canonical_sha256({key: value for key, value in census.items() if key != "registry_digest"})
    ):
        _error(errors, "runtime.registry.census_contract_invalid", "profile.registry_census", "registry census schema/digest is invalid")
        return {}
    identity = census.get("workspace_identity")
    expected_root_sha = "sha256:" + hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest()
    if not isinstance(identity, dict) or identity.get("workspace_root_sha256") != expected_root_sha:
        _error(errors, "runtime.registry.workspace_identity_mismatch", "profile.registry_census.workspace_identity", "registry census belongs to a different workspace/worktree")
    census_harness = census.get("harness")
    profile_harness = profile.get("harness")
    if (
        not isinstance(census_harness, dict)
        or not isinstance(profile_harness, dict)
        or census_harness.get("name") != profile_harness.get("name")
        or census_harness.get("adapter_path") != profile_harness.get("adapter_path")
        or census_harness.get("adapter_sha256") != profile_harness.get("adapter_sha256")
    ):
        _error(
            errors,
            "runtime.registry.harness_identity_mismatch",
            "profile.registry_census.harness",
            "registry census harness/session adapter identity does not match the profile",
        )
    release = census.get("installed_release")
    if not isinstance(release, dict):
        _error(errors, "runtime.registry.release_missing", "profile.registry_census.installed_release", "installed release verification is missing")
        return {}
    try:
        from release_skills import verify_installed_packages

        result = verify_installed_packages(
            Path(str(release.get("skills_root"))),
            (
                Path(str(release.get("manifest_path")))
                if Path(str(release.get("manifest_path"))).is_absolute()
                else workspace_root / str(release.get("manifest_path"))
            ).resolve(strict=True),
            workspace_root,
            verify_workspace_source=False,
        )
    except Exception as exc:
        _error(errors, "runtime.registry.installed_release_invalid", "profile.registry_census.installed_release", f"installed Skill packages do not match the release manifest: {exc}")
        return {}
    if (
        result.get("ok") is not True
        or result.get("release_sha256") != release.get("release_sha256")
    ):
        _error(errors, "runtime.registry.installed_release_digest_mismatch", "profile.registry_census.installed_release", "installed release digest does not match the census")
    manifest_value = release.get("manifest_path")
    manifest_path = Path(str(manifest_value))
    if not manifest_path.is_absolute():
        manifest_path = workspace_root / manifest_path
    try:
        actual_manifest_sha = _prefixed_file_sha256(manifest_path.resolve(strict=True))
    except OSError:
        actual_manifest_sha = None
    if actual_manifest_sha != release.get("manifest_sha256"):
        _error(
            errors,
            "runtime.registry.release_manifest_sha_mismatch",
            "profile.registry_census.installed_release.manifest_sha256",
            "release manifest bytes changed after the census",
        )
    expected_forbidden_parts = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        "examples",
        "experiments",
        "organizations",
        "output",
    }
    if set(release.get("source_zero_forbidden_parts_absent") or []) != expected_forbidden_parts:
        _error(
            errors,
            "runtime.registry.source_zero_release_unproven",
            "profile.registry_census.installed_release.source_zero_forbidden_parts_absent",
            "installed release census does not prove the canonical forbidden trees absent",
        )
    registry_assurance = census.get("registry_assurance")
    if (
        not isinstance(registry_assurance, dict)
        or registry_assurance.get("mode")
        not in {
            "host-callable-current-session-export",
            "current-session-model-visible-intent",
        }
        or registry_assurance.get("host_attested_registry") is not False
        or registry_assurance.get("portable") is not False
        or registry_assurance.get("requires_later_live_probes") is not True
    ):
        _error(
            errors,
            "runtime.registry.assurance_invalid",
            "profile.registry_census.registry_assurance",
            "registry assurance must preserve its current-session and non-portable truth boundary",
        )
    publication_routes = census.get("publication_routes")
    if not isinstance(publication_routes, dict):
        _error(
            errors,
            "runtime.registry.publication_routes_missing",
            "profile.registry_census.publication_routes",
            "registry census must report independent draft and publication routes",
        )
    else:
        draft_routes = publication_routes.get("draft")
        current_routes = publication_routes.get("current_session_publish")
        readback_route = publication_routes.get("current_session_readback")
        draft_api = draft_routes.get("api") if isinstance(draft_routes, dict) else None
        current_api = (
            current_routes.get("api") if isinstance(current_routes, dict) else None
        )
        portable_publish = publication_routes.get("portable_signed_publish")
        route_contract_valid = (
            isinstance(draft_api, dict)
            and isinstance(draft_api.get("available"), bool)
            and draft_api.get("implies_publication_authority") is False
            and isinstance(current_api, dict)
            and isinstance(current_api.get("available"), bool)
            and current_api.get("independent_capability")
            == "wechat.current-session-authority"
            and current_api.get("inferred_from_wechat_draft") is False
            and isinstance(readback_route, dict)
            and isinstance(readback_route.get("available"), bool)
            and readback_route.get("assurance")
            == "current-session-only-nonportable"
            and readback_route.get("implies_publication_authority") is False
            and isinstance(portable_publish, dict)
            and isinstance(portable_publish.get("available"), bool)
            and portable_publish.get("independent_capability")
            == "host.receipt.attest"
        )
        if not route_contract_valid:
            _error(
                errors,
                "runtime.registry.publication_routes_invalid",
                "profile.registry_census.publication_routes",
                "draft API, nonportable current-session readback, independent publication authority, and portable receipt routes must remain separate",
            )
    provider_acquisition_routes = census.get("provider_acquisition_routes")
    provider_current = (
        provider_acquisition_routes.get("current_session")
        if isinstance(provider_acquisition_routes, dict)
        else None
    )
    provider_without = (
        provider_acquisition_routes.get("without_complete_chain")
        if isinstance(provider_acquisition_routes, dict)
        else None
    )
    provider_policy = (
        provider_current.get("optional_policy_hook")
        if isinstance(provider_current, dict)
        else None
    )
    if (
        not isinstance(provider_current, dict)
        or provider_current.get("available") is not True
        or provider_current.get("operational_ready") is not False
        or provider_current.get("authority_mode")
        != "current-session-operator-harness-trusted"
        or provider_current.get("assurance")
        != "operator-harness-trusted-current-session"
        or provider_current.get("host_attested") is not False
        or provider_current.get("portable") is not False
        or not isinstance(provider_current.get("required_asset_gates"), list)
        or not isinstance(provider_policy, dict)
        or provider_policy.get("capability")
        != "image.provider.acquire.authority"
        or not isinstance(provider_policy.get("available"), bool)
        or provider_policy.get("can_veto") is not True
        or provider_policy.get("can_upgrade_assurance") is not False
        or not isinstance(provider_without, dict)
        or provider_without.get("authority_mode") != "structural-only"
        or provider_without.get("formal_micro_ready") is not False
    ):
        _error(
            errors,
            "runtime.registry.provider_acquisition_routes_invalid",
            "profile.registry_census.provider_acquisition_routes",
            "provider acquisition must distinguish current-session operator trust, optional veto policy, and portable signed assurance",
        )
    skills = census.get("skills")
    skill_map = {
        item.get("id"): item
        for item in skills
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(skills, list) else {}
    census_tools = census.get("tools")
    tool_map = {
        item.get("id"): item
        for item in census_tools
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(census_tools, list) else {}
    return {
        "verified": not any(item["code"].startswith("runtime.registry.") for item in errors),
        "release_sha256": result.get("release_sha256"),
        "skills": skill_map,
        "tools": tool_map,
        "harness": census_harness,
        "source_zero_release_verified": set(
            release.get("source_zero_forbidden_parts_absent") or []
        )
        == expected_forbidden_parts,
        "registry_digest": census.get("registry_digest"),
        "census_sha256": actual_sha,
        "registry_assurance": registry_assurance,
        "publication_routes": publication_routes,
        "provider_acquisition_routes": provider_acquisition_routes,
    }


def build_runtime_profile_from_census(
    census: dict[str, Any],
    census_path: Path,
    target: dict[str, Any],
    workspace_root: Path,
    phase: str,
) -> dict[str, Any]:
    """Generate a profile without hand-copying tool/provider/session status."""

    if phase not in PHASES:
        raise ValueError(f"unsupported phase: {phase}")
    if (
        census.get("schema_version") != 1
        or census.get("kind") != HOST_REGISTRY_CENSUS_KIND
        or census.get("registry_digest")
        != _canonical_sha256(
            {key: value for key, value in census.items() if key != "registry_digest"}
        )
    ):
        raise ValueError("registry census is invalid")
    if (
        target.get("schema_version") != 1
        or target.get("kind") != "org-wechat-runtime-target-v1"
    ):
        raise ValueError("runtime target configuration is invalid")
    workspace_root = workspace_root.resolve(strict=True)
    registry_assurance = census.get("registry_assurance")
    if (
        isinstance(registry_assurance, dict)
        and registry_assurance.get("mode")
        == "current-session-model-visible-intent"
        and registry_assurance.get("intent_phase") != phase
    ):
        raise ValueError(
            "current-session registry intent phase does not match the requested profile phase"
        )
    harness = census.get("harness")
    if not isinstance(harness, dict):
        raise ValueError("registry census harness is missing")
    adapter_relative = harness.get("adapter_path")
    if not isinstance(adapter_relative, str):
        raise ValueError("registry census adapter path is invalid")
    adapter_path = (workspace_root / adapter_relative).resolve(strict=True)
    adapter = _read_json(adapter_path)
    adapter_capabilities = adapter.get("capabilities")
    if not isinstance(adapter_capabilities, dict):
        raise ValueError("selected adapter capability registry is invalid")

    census_skills = {
        item.get("id"): item
        for item in census.get("skills", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    required_capabilities = phase_capabilities(phase, target)
    selected_skill_ids = {"org-wechat-studio", "ardot-wechat-publisher"}
    rgba_route = adapter_capabilities.get("image.generate.rgba")
    if (
        "rgba_cutout_generation" in required_capabilities
        and isinstance(rgba_route, dict)
        and rgba_route.get("route") == "chatgpt-web"
    ):
        selected_skill_ids.add("chatgpt-web-image-route")
    skills: list[dict[str, Any]] = []
    for skill_id in sorted(selected_skill_ids):
        registry_item = census_skills.get(skill_id)
        if not isinstance(registry_item, dict):
            raise ValueError(f"registry census is missing installed Skill: {skill_id}")
        installed_entrypoint = registry_item.get("installed_entrypoint")
        entrypoint_sha256 = registry_item.get("entrypoint_sha256")
        if (
            not isinstance(installed_entrypoint, str)
            or not Path(installed_entrypoint).is_absolute()
            or not isinstance(entrypoint_sha256, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", entrypoint_sha256)
        ):
            raise ValueError(
                f"registry census has no verified installed entrypoint: {skill_id}"
            )
        entrypoint = Path(installed_entrypoint).resolve(strict=True)
        if (
            entrypoint.is_symlink()
            or not entrypoint.is_file()
            or _prefixed_file_sha256(entrypoint) != entrypoint_sha256
        ):
            raise ValueError(
                f"registry census installed entrypoint bytes changed: {skill_id}"
            )
        skills.append(
            {
                "id": skill_id,
                "entrypoint": str(entrypoint),
                "status": registry_item.get("registry_status"),
                "sha256": entrypoint_sha256,
            }
        )

    census_tools = {
        item.get("id"): item
        for item in census.get("tools", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    selected_tools: dict[str, dict[str, Any]] = {}

    def route_ids(*semantic_kinds: str) -> list[str]:
        resolved: list[str] = []
        for semantic_kind in semantic_kinds:
            route = adapter_capabilities.get(semantic_kind)
            required = route.get("requires") if isinstance(route, dict) else None
            if not isinstance(required, list) or not required:
                raise ValueError(f"adapter route is unavailable: {semantic_kind}")
            for tool_id in required:
                item = census_tools.get(tool_id)
                if not isinstance(item, dict):
                    raise ValueError(
                        f"current host registry is missing {semantic_kind} dependency: {tool_id}"
                    )
                selected_tools[tool_id] = dict(item)
                if tool_id not in resolved:
                    resolved.append(tool_id)
        return resolved

    capabilities: dict[str, Any] = {}
    if "opaque_image_generation" in required_capabilities:
        capabilities["opaque_image_generation"] = {
            "mode": "tool",
            "status": "bound_unprobed",
            "tool_ids": route_ids("image.generate.opaque"),
        }
    if "rgba_cutout_generation" in required_capabilities:
        if not isinstance(rgba_route, dict):
            raise ValueError("adapter has no RGBA route")
        rgba_mode = rgba_route.get("route")
        if rgba_mode not in CAPABILITY_MODES["rgba_cutout_generation"]:
            raise ValueError("adapter RGBA route is unsupported")
        rgba: dict[str, Any] = {
            "mode": rgba_mode,
            "status": "bound_unprobed",
            "tool_ids": route_ids("image.generate.rgba"),
            "output_contract": rgba_route.get("output_contract"),
            "processor": rgba_route.get("processor"),
            "generation_route_id": rgba_route.get("generation_route_id"),
        }
        if phase == "migration":
            rgba["migration_probe_contract"] = rgba_route.get(
                "migration_probe_contract"
            )
        if rgba_mode == "chatgpt-web":
            provider_contract = rgba_route.get("provider_skill")
            if not isinstance(provider_contract, dict):
                raise ValueError("ChatGPT RGBA adapter provider Skill is missing")
            provider_registry = census_skills.get(str(provider_contract.get("id")))
            if not isinstance(provider_registry, dict):
                raise ValueError("ChatGPT RGBA provider Skill is absent from the census")
            rgba["provider_skill"] = {
                "id": provider_contract.get("id"),
                "status": provider_registry.get("registry_status"),
                "contract": provider_contract.get("contract"),
            }
            rgba["download_ingest_tool_ids"] = route_ids(
                "browser.download.ingest"
            )
        capabilities["rgba_cutout_generation"] = rgba
    if "visual_inspection" in PHASE_CAPABILITIES[phase]:
        capabilities["visual_inspection"] = {
            "mode": "tool",
            "status": "declared",
            "tool_ids": route_ids("image.inspect"),
        }
    if phase in {"authoring", "full"}:
        provider_authority_route = adapter_capabilities.get(
            "image.provider.acquire.authority"
        )
        provider_authority_requires = (
            provider_authority_route.get("requires")
            if isinstance(provider_authority_route, dict)
            else None
        )
        if (
            isinstance(provider_authority_route, dict)
            and provider_authority_route.get("availability") != "unavailable"
            and isinstance(provider_authority_requires, list)
            and provider_authority_requires
            and all(
                tool_id in census_tools for tool_id in provider_authority_requires
            )
        ):
            capabilities["provider_acquisition_authority"] = {
                "mode": "host",
                "status": "declared",
                "tool_ids": route_ids("image.provider.acquire.authority"),
                "trust_boundary": "trusted-harness-policy-hook-no-assurance-upgrade",
                "authority_mode": "policy-hook-only",
            }

    links = target.get("links")
    if not isinstance(links, dict):
        links = {}
    targets = target.get("targets")
    if not isinstance(targets, dict):
        targets = {}

    def ui_route_ids() -> tuple[str, list[str]]:
        for semantic_kind in ("browser.control", "computer.use"):
            route = adapter_capabilities.get(semantic_kind)
            required = route.get("requires") if isinstance(route, dict) else None
            if isinstance(required, list) and required and all(
                tool_id in census_tools for tool_id in required
            ):
                return semantic_kind, route_ids(semantic_kind)
        raise ValueError("current host has no complete Browser or Computer Use route")

    if "ardot_bootstrap" in PHASE_CAPABILITIES[phase]:
        create_route = adapter_capabilities.get("ardot.create")
        if (
            isinstance(create_route, dict)
            and isinstance(create_route.get("requires"), list)
            and all(tool_id in census_tools for tool_id in create_route["requires"])
        ):
            ardot_mode, ardot_tools = "mcp", route_ids("ardot.create")
        else:
            _, ardot_tools = ui_route_ids()
            ardot_mode = "ui"
        capabilities["ardot_bootstrap"] = {
            "mode": ardot_mode,
            "status": "declared",
            "tool_ids": ardot_tools,
        }
    if "ardot_authoring" in PHASE_CAPABILITIES[phase]:
        ardot_target = targets.get("ardot")
        if not isinstance(ardot_target, dict):
            raise ValueError("Ardot target identity is required for this phase")
        mcp_kinds = ("ardot.read", "ardot.write", "ardot.export")
        if all(
            isinstance(adapter_capabilities.get(kind), dict)
            and all(
                tool_id in census_tools
                for tool_id in adapter_capabilities[kind].get("requires", [])
            )
            for kind in mcp_kinds
        ):
            ardot_mode, ardot_tools = "mcp", route_ids(*mcp_kinds)
        else:
            _, ardot_tools = ui_route_ids()
            ardot_mode = "ui"
        capabilities["ardot_authoring"] = {
            "mode": ardot_mode,
            "status": "declared",
            "tool_ids": ardot_tools,
            "workspace_link": ardot_target.get("workspace_link"),
            "expected_file_id": ardot_target.get("expected_file_id"),
            "expected_root_id": ardot_target.get("expected_root_id"),
        }
    if "wechat_delivery" in PHASE_CAPABILITIES[phase]:
        wechat_target = targets.get("wechat")
        if not isinstance(wechat_target, dict):
            raise ValueError("WeChat target identity is required for this phase")
        requested_mode = wechat_target.get("mode", "ui")
        terminal_state = wechat_target.get("terminal_state", "draft")
        if terminal_state not in {"draft", "publish"}:
            raise ValueError("WeChat terminal_state must be draft or publish")
        if requested_mode == "api":
            wechat_tools = route_ids("wechat.draft")
        elif requested_mode == "ui":
            _, wechat_tools = ui_route_ids()
        else:
            raise ValueError("WeChat target mode must be api or ui")
        capabilities["wechat_delivery"] = {
            "mode": requested_mode,
            "status": "declared",
            "tool_ids": wechat_tools,
            "account_link": wechat_target.get("account_link"),
            "target_account_ref": wechat_target.get("target_account_ref"),
            "terminal_state": terminal_state,
        }
        target_assurance = target.get("assurance")
        portable_readback_selected = bool(
            isinstance(target_assurance, dict)
            and isinstance(
                target_assurance.get("host_receipt_attestation"), dict
            )
        )
        if (
            requested_mode == "api"
            and terminal_state == "draft"
            and not portable_readback_selected
        ):
            readback_route = adapter_capabilities.get(
                "wechat.current-session-readback"
            )
            readback_requires = (
                readback_route.get("requires")
                if isinstance(readback_route, dict)
                else None
            )
            if (
                not isinstance(readback_route, dict)
                or readback_route.get("availability") == "unavailable"
                or not isinstance(readback_requires, list)
                or not readback_requires
                or not all(tool_id in census_tools for tool_id in readback_requires)
            ):
                raise ValueError(
                    "current-session API draft requires the complete WeChat UI readback capture route"
                )
            capabilities["wechat_current_session_readback"] = {
                "mode": "host-ui",
                "status": "declared",
                "tool_ids": route_ids("wechat.current-session-readback"),
                "target_account_ref": wechat_target.get("target_account_ref"),
                "truth_boundary": (
                    "browser-computer-use-exact-draft-capture-current-session-only-"
                    "nonportable-no-publication-authority"
                ),
                "processor": "scripts/ingest_wechat_readback_capture.py",
            }
        if terminal_state == "publish" and requested_mode == "api":
            authority_route = adapter_capabilities.get(
                "wechat.current-session-authority"
            )
            authority_requires = (
                authority_route.get("requires")
                if isinstance(authority_route, dict)
                else None
            )
            if (
                isinstance(authority_route, dict)
                and authority_route.get("availability") != "unavailable"
                and isinstance(authority_requires, list)
                and authority_requires
                and all(tool_id in census_tools for tool_id in authority_requires)
            ):
                capabilities["wechat_publication_authority"] = {
                    "mode": "host",
                    "status": "declared",
                    "tool_ids": route_ids("wechat.current-session-authority"),
                    "trust_boundary": (
                        "host-in-process-fresh-confirmation-and-authoritative-readback"
                    ),
                }

    assurance = target.get("assurance")
    if isinstance(assurance, dict):
        filesystem_config = assurance.get("filesystem_access_lease")
        filesystem_route = adapter_capabilities.get("filesystem.access.lease")
        if isinstance(filesystem_config, dict):
            if (
                not isinstance(filesystem_route, dict)
                or filesystem_route.get("availability") == "unavailable"
            ):
                raise ValueError("requested host filesystem assurance is unavailable")
            capabilities["filesystem_access_lease"] = {
                "mode": "host",
                "status": "declared",
                "tool_ids": route_ids("filesystem.access.lease"),
                **filesystem_config,
            }
        migration_config = assurance.get("migration_probe_finalization")
        migration_route = adapter_capabilities.get("host.migration.finalize")
        if isinstance(migration_config, dict):
            if (
                phase != "migration"
                or not isinstance(migration_route, dict)
                or migration_route.get("availability") == "unavailable"
            ):
                raise ValueError("requested portable migration assurance is unavailable")
            capabilities["migration_probe_finalization"] = {
                "mode": "host",
                "status": "declared",
                "tool_ids": route_ids("host.migration.finalize"),
                **migration_config,
            }
        receipt_config = assurance.get("host_receipt_attestation")
        receipt_route = adapter_capabilities.get("host.receipt.attest")
        if isinstance(receipt_config, dict):
            if (
                phase not in {"delivery", "full"}
                or not isinstance(receipt_route, dict)
                or receipt_route.get("availability") == "unavailable"
            ):
                raise ValueError("requested portable delivery assurance is unavailable")
            capabilities["host_receipt_attestation"] = {
                "mode": "host",
                "status": "declared",
                "tool_ids": route_ids("host.receipt.attest"),
                **receipt_config,
            }

    artifact_inventory = target.get("artifact_inventory")
    if phase in {"authoring", "delivery", "full"} and not isinstance(
        artifact_inventory, dict
    ):
        raise ValueError(
            "current artifact inventory is required to decide whether watermark secrets are needed"
        )
    carrier_ids = _watermark_carrier_ids(
        {"artifact_inventory": artifact_inventory}, []
    )
    if carrier_ids:
        capabilities["secret_store"] = {
            "mode": "environment",
            "status": "declared",
            "secret_refs": ["PROVENANCE_WATERMARK_KEY"],
            "path_refs": ["PROVENANCE_WATERMARK_PRIVATE_ROOT"],
        }

    profile: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": PROFILE_KIND,
        "harness": {
            "name": harness.get("name"),
            "adapter_path": adapter_relative,
            "adapter_sha256": harness.get("adapter_sha256"),
        },
        "registry_census": {
            "path": str(census_path.expanduser().resolve(strict=True)),
            "sha256": _prefixed_file_sha256(census_path.expanduser().resolve(strict=True)),
        },
        "skills": skills,
        "tools": sorted(selected_tools.values(), key=lambda item: item["id"]),
        "links": links,
        "capabilities": capabilities,
    }
    if isinstance(artifact_inventory, dict):
        profile["artifact_inventory"] = artifact_inventory
    if "generation" in target:
        profile["generation"] = target["generation"]
    return profile


def _validate_skills(
    profile: dict[str, Any],
    workspace_root: Path,
    phase: str,
    errors: list[dict[str, str]],
    installed_registry: dict[str, Any],
) -> dict[str, dict[str, str]]:
    skills = profile.get("skills")
    if not isinstance(skills, list):
        _error(errors, "runtime.skills.inventory_missing", "profile.skills", "skill inventory must be a list")
        return {}
    resolved: dict[str, dict[str, str]] = {}
    for index, item in enumerate(skills):
        path = f"profile.skills[{index}]"
        if not isinstance(item, dict):
            _error(errors, "runtime.skills.item_invalid", path, "skill inventory item must be an object")
            continue
        skill_id = item.get("id")
        entrypoint = item.get("entrypoint")
        if not isinstance(skill_id, str) or not skill_id:
            _error(errors, "runtime.skills.id_missing", f"{path}.id", "skill id is required")
            continue
        if skill_id in resolved:
            _error(errors, "runtime.skills.id_duplicate", f"{path}.id", "skill id must be unique")
            continue
        if item.get("status") not in {"loaded", "available"}:
            _error(errors, "runtime.skills.not_available", f"{path}.status", "skill must be loaded or available")
        if not isinstance(entrypoint, str) or not entrypoint:
            _error(errors, "runtime.skills.entrypoint_missing", f"{path}.entrypoint", "skill entrypoint is required")
            continue
        else:
            raw_entrypoint = Path(entrypoint).expanduser()
            if not raw_entrypoint.is_absolute():
                raw_entrypoint = workspace_root / raw_entrypoint
            raw_entrypoint = raw_entrypoint.absolute()
            if _has_any_symlink_component(raw_entrypoint):
                entrypoint_path = None
                _error(
                    errors,
                    "runtime.skills.entrypoint_unsafe",
                    f"{path}.entrypoint",
                    "skill entrypoint path must not contain symbolic links",
                )
            else:
                try:
                    entrypoint_path = raw_entrypoint.resolve(strict=True)
                except OSError:
                    entrypoint_path = None
                    _error(
                        errors,
                        "runtime.skills.entrypoint_unavailable",
                        f"{path}.entrypoint",
                        "skill entrypoint is unavailable",
                    )
            declared_sha = item.get("sha256")
            if not isinstance(declared_sha, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", declared_sha):
                _error(
                    errors,
                    "runtime.skills.sha256_invalid",
                    f"{path}.sha256",
                    "skill sha256 must be sha256:<64 lowercase hex>",
                )
            elif entrypoint_path is not None and entrypoint_path.is_file():
                actual_sha = f"sha256:{_sha256(entrypoint_path)}"
                if declared_sha != actual_sha:
                    _error(
                        errors,
                        "runtime.skills.sha256_mismatch",
                        f"{path}.sha256",
                        "loaded skill hash does not match the current project entrypoint",
                    )
            resolved[skill_id] = {
                "entrypoint": str(entrypoint_path or raw_entrypoint),
                "sha256": str(declared_sha),
                "status": str(item.get("status")),
            }
        installed = (installed_registry.get("skills") or {}).get(skill_id)
        if not isinstance(installed, dict):
            _error(
                errors,
                "runtime.skills.installed_registry_missing",
                path,
                "Skill is absent from the verified installed registry census",
            )
        else:
            registry_status = installed.get("registry_status")
            installed_sha = installed.get("entrypoint_sha256")
            installed_path_value = installed.get("installed_entrypoint")
            if registry_status not in {"loaded", "available"}:
                _error(errors, "runtime.skills.installed_status_invalid", path, "installed registry status is invalid")
            if item.get("status") != registry_status:
                _error(errors, "runtime.skills.profile_status_not_registry", f"{path}.status", "profile Skill status does not match the current host registry")
            if not isinstance(installed_path_value, str) or not isinstance(installed_sha, str):
                _error(errors, "runtime.skills.installed_path_invalid", path, "installed Skill path/digest is missing")
            else:
                installed_path = _canonical_absolute_path(Path(installed_path_value))
                try:
                    installed_resolved = installed_path.resolve(strict=True)
                except OSError:
                    installed_resolved = None
                if (
                    installed_path.is_symlink()
                    or installed_resolved is None
                    or not installed_resolved.is_file()
                    or _prefixed_file_sha256(installed_resolved) != installed_sha
                    or entrypoint_path != installed_resolved
                    or installed_sha != item.get("sha256")
                ):
                    _error(
                        errors,
                        "runtime.skills.installed_bytes_mismatch",
                        path,
                        "installed Skill entrypoint bytes do not match the reviewed repository entrypoint",
                    )
    for skill_id in REQUIRED_SKILLS:
        if skill_id not in resolved:
            _error(
                errors,
                "runtime.skills.required_missing",
                f"profile.skills.{skill_id}",
                "required Skill must bind its exact verified installed entrypoint",
            )
    loaded_skill = PHASE_LOADED_SKILL[phase]
    installed_loaded = (installed_registry.get("skills") or {}).get(loaded_skill)
    if not isinstance(installed_loaded, dict) or installed_loaded.get("registry_status") != "loaded":
        _error(
            errors,
            "runtime.skills.phase_skill_not_loaded",
            f"profile.skills.{loaded_skill}.status",
            f"{loaded_skill} must be loaded for phase {phase}; available is not equivalent to loaded",
        )
    return resolved


def _validate_links(
    profile: dict[str, Any],
    phase: str,
    errors: list[dict[str, str]],
    *,
    now: datetime,
    max_age_minutes: int,
    binding_only: bool,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    links = profile.get("links")
    if not isinstance(links, dict):
        _error(errors, "runtime.links.inventory_missing", "profile.links", "link inventory must be an object")
        return {}, {}
    resolved: dict[str, dict[str, Any]] = {}
    safe_links: dict[str, str] = {}
    referenced_links: set[str] = set()
    capabilities = profile.get("capabilities")
    if isinstance(capabilities, dict):
        for capability_name in PHASE_CAPABILITIES[phase]:
            capability = capabilities.get(capability_name)
            if not isinstance(capability, dict):
                continue
            for field in ("workspace_link", "account_link"):
                value = capability.get(field)
                if isinstance(value, str):
                    referenced_links.add(value)
    for name, item in links.items():
        path = f"profile.links.{name}"
        if not isinstance(name, str) or not TOOL_ID.fullmatch(name):
            _error(errors, "runtime.link.name_invalid", path, "link name is invalid")
            continue
        if not isinstance(item, dict):
            _error(errors, "runtime.link.item_invalid", path, "link entry must be an object")
            continue
        if name not in referenced_links:
            _error(
                errors,
                "runtime.link.unbound",
                path,
                "every runtime link must be referenced by a capability required in the selected phase",
            )
        safe = _safe_url(item.get("url"), f"{path}.url", errors)
        if safe is not None:
            host = urlsplit(safe).hostname
            if host not in {"ardot.tencent.com", "mp.weixin.qq.com", "api.weixin.qq.com"}:
                _error(
                    errors,
                    "runtime.link.host_untrusted",
                    f"{path}.url",
                    "runtime links must use the exact Ardot or WeChat allowlisted host",
                )
            elif name in referenced_links:
                safe_links[name] = safe
        purpose = item.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            _error(errors, "runtime.link.purpose_missing", f"{path}.purpose", "link purpose is required")
        resolved[name] = item
    return resolved, safe_links


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _watermark_carrier_ids(profile: dict[str, Any], errors: list[dict[str, str]]) -> list[str]:
    inventory = profile.get("artifact_inventory")
    if inventory is None:
        return []
    if not isinstance(inventory, dict):
        _error(
            errors,
            "runtime.artifacts.inventory_invalid",
            "profile.artifact_inventory",
            "artifact inventory must be an object",
        )
        return []
    if inventory.get("census_complete") is not True:
        _error(
            errors,
            "runtime.artifacts.census_incomplete",
            "profile.artifact_inventory.census_complete",
            "watermark secret gating requires a complete current artifact census",
        )
    source_sha = inventory.get("source_sha256")
    if not isinstance(source_sha, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", source_sha):
        _error(
            errors,
            "runtime.artifacts.source_sha_invalid",
            "profile.artifact_inventory.source_sha256",
            "artifact census must bind its current handoff/asset inventory SHA-256",
        )
    carriers = inventory.get("eligible_watermark_carriers")
    if not isinstance(carriers, list):
        _error(
            errors,
            "runtime.artifacts.carriers_invalid",
            "profile.artifact_inventory.eligible_watermark_carriers",
            "eligible carrier inventory must be a list",
        )
        return []
    ids: list[str] = []
    for index, item in enumerate(carriers):
        path = f"profile.artifact_inventory.eligible_watermark_carriers[{index}]"
        if not isinstance(item, dict):
            _error(errors, "runtime.artifacts.carrier_invalid", path, "carrier must be an object")
            continue
        asset_id = item.get("asset_id")
        sha = item.get("sha256")
        if not isinstance(asset_id, str) or not TOOL_ID.fullmatch(asset_id):
            _error(errors, "runtime.artifacts.carrier_id_invalid", f"{path}.asset_id", "carrier asset id is invalid")
            continue
        if not isinstance(sha, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", sha):
            _error(errors, "runtime.artifacts.carrier_sha_invalid", f"{path}.sha256", "carrier SHA-256 is invalid")
            continue
        ids.append(asset_id)
    if len(ids) != len(set(ids)):
        _error(
            errors,
            "runtime.artifacts.carrier_duplicate",
            "profile.artifact_inventory.eligible_watermark_carriers",
            "carrier asset ids must be unique",
        )
    return sorted(set(ids))


def _validate_filesystem_policy(
    item: dict[str, Any],
    phase: str,
    path: str,
    errors: list[dict[str, str]],
) -> tuple[str | None, str | None]:
    policy = item.get("policy")
    if not isinstance(policy, dict):
        _error(errors, "runtime.filesystem.policy_missing", f"{path}.policy", "source-zero filesystem policy is required")
        return None, None
    if (
        policy.get("schema_version") != 1
        or policy.get("kind") != FILESYSTEM_POLICY_KIND
        or policy.get("phase") != phase
        or policy.get("deny_by_default") is not True
        or policy.get("deny_legacy_ardot_references") is not True
    ):
        _error(
            errors,
            "runtime.filesystem.policy_contract_invalid",
            f"{path}.policy",
            "filesystem policy must be phase-bound, deny-by-default and deny legacy Ardot references",
        )
    allow = policy.get("allow")
    allow_roles: set[str] = set()
    if not isinstance(allow, list):
        _error(errors, "runtime.filesystem.allowlist_missing", f"{path}.policy.allow", "filesystem allowlist is required")
        allow = []
    for index, entry in enumerate(allow):
        entry_path = f"{path}.policy.allow[{index}]"
        if not isinstance(entry, dict):
            _error(errors, "runtime.filesystem.allow_invalid", entry_path, "allow entry must be an object")
            continue
        role = entry.get("role")
        value = entry.get("path")
        if not isinstance(role, str) or not TOOL_ID.fullmatch(role):
            _error(errors, "runtime.filesystem.allow_role_invalid", f"{entry_path}.role", "allow role is invalid")
            continue
        if not isinstance(value, str) or not value.strip() or any(token in value for token in ("*", "..")):
            _error(errors, "runtime.filesystem.allow_path_invalid", f"{entry_path}.path", "allow path must be explicit and non-globbed")
            continue
        allow_roles.add(role)
    expected_roles = {
        "migration": {"current-runtime-output"},
        "bootstrap": {"current-runtime-output"},
        "authoring": {"current-source-input", "current-pack", "current-runtime-output"},
        "delivery": {"current-pack", "current-article", "current-runtime-output"},
        "full": {"current-source-input", "current-pack", "current-runtime-output"},
    }[phase]
    if allow_roles != expected_roles:
        _error(
            errors,
            "runtime.filesystem.allow_roles_invalid",
            f"{path}.policy.allow",
            f"phase {phase} requires exact allow roles {sorted(expected_roles)}",
        )
    deny = policy.get("deny")
    deny_roles = {
        entry.get("role")
        for entry in deny
        if isinstance(entry, dict) and isinstance(entry.get("role"), str)
    } if isinstance(deny, list) else set()
    expected_denies = {
        "examples",
        "other-organizations",
        "legacy-output",
        "legacy-ardot-references",
    }
    if deny_roles != expected_denies:
        _error(
            errors,
            "runtime.filesystem.deny_rules_incomplete",
            f"{path}.policy.deny",
            f"filesystem policy must explicitly deny {sorted(expected_denies)}",
        )
    policy_sha = _canonical_sha256(policy)
    if item.get("policy_sha256") != policy_sha:
        _error(
            errors,
            "runtime.filesystem.policy_sha_mismatch",
            f"{path}.policy_sha256",
            "filesystem policy SHA-256 does not match canonical policy bytes",
        )
    lease = item.get("lease")
    lease_id: str | None = None
    if not isinstance(lease, dict):
        _error(errors, "runtime.filesystem.lease_missing", f"{path}.lease", "host filesystem lease is required")
    else:
        lease_id = lease.get("lease_id") if isinstance(lease.get("lease_id"), str) else None
        if (
            not lease_id
            or not TOOL_ID.fullmatch(lease_id)
            or lease.get("policy_sha256") != policy_sha
            or lease.get("host_enforced") is not True
            or lease.get("deny_by_default") is not True
        ):
            _error(
                errors,
                "runtime.filesystem.lease_contract_invalid",
                f"{path}.lease",
                "lease must be host-enforced, deny-by-default and bind the exact policy SHA",
            )
    return policy_sha, lease_id


def _validate_capabilities(
    profile: dict[str, Any],
    phase: str,
    tool_map: dict[str, dict[str, Any]],
    links: dict[str, dict[str, Any]],
    safe_links: dict[str, str],
    adapter_capabilities: dict[str, Any],
    installed_registry: dict[str, Any],
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
    *,
    now: datetime,
    max_age_minutes: int,
    environment: dict[str, str],
    binding_only: bool,
) -> dict[str, Any]:
    capabilities = profile.get("capabilities")
    if not isinstance(capabilities, dict):
        _error(
            errors,
            "runtime.capabilities.inventory_missing",
            "profile.capabilities",
            "capability inventory must be an object",
        )
        return {}
    resolved: dict[str, Any] = {}
    required = phase_capabilities(phase, profile)
    selected = list(required)
    carrier_ids = _watermark_carrier_ids(profile, errors)
    inventory_present = isinstance(profile.get("artifact_inventory"), dict)
    secret_present = isinstance(capabilities.get("secret_store"), dict)
    if phase in {"authoring", "delivery", "full"}:
        if carrier_ids and "secret_store" not in selected:
            selected.append("secret_store")
        elif not inventory_present and secret_present and "secret_store" not in selected:
            selected.append("secret_store")
        elif not inventory_present and not secret_present:
            _error(
                errors,
                "runtime.artifacts.inventory_required_for_secret_gating",
                "profile.artifact_inventory",
                "omit secret_store only after a complete current census proves there are no eligible carriers",
            )
    selected.extend(
        name
        for name in OPTIONAL_PHASE_CAPABILITIES[phase]
        if name != "secret_store"
        and isinstance(capabilities.get(name), dict)
        and name not in selected
    )
    if (
        inventory_present
        and not carrier_ids
        and isinstance(capabilities.get("secret_store"), dict)
    ):
        _warning(
            warnings,
            "runtime.secret.not_required_without_eligible_carriers",
            "profile.capabilities.secret_store",
            "secret store is not selected because the complete artifact census contains no eligible watermark carrier",
        )
    if (
        "migration_probe_finalization" in selected
        and "filesystem_access_lease" not in selected
    ):
        _error(
            errors,
            "runtime.capability.portable_migration_requires_filesystem_lease",
            "profile.capabilities.migration_probe_finalization",
            "portable signed migration assurance requires the host-enforced source-zero filesystem lease",
        )
    for name in selected:
        path = f"profile.capabilities.{name}"
        item = capabilities.get(name)
        if not isinstance(item, dict):
            _error(errors, "runtime.capability.missing", path, "required capability is missing")
            continue
        mode = item.get("mode")
        if mode not in CAPABILITY_MODES[name]:
            _error(
                errors,
                "runtime.capability.mode_invalid",
                f"{path}.mode",
                f"mode must be one of {sorted(CAPABILITY_MODES[name])}",
            )
            continue
        status = item.get("status")
        if not binding_only:
            if name == "rgba_cutout_generation" and status == "needs_user_login":
                _error(
                    errors,
                    "runtime.capability.rgba_provider_needs_user_login",
                    f"{path}.status",
                    "the selected image provider requires login before visual generation",
                )
            accepted_statuses = {"passed"}
            if name in {"opaque_image_generation", "rgba_cutout_generation"}:
                accepted_statuses.add("bound_unprobed")
            if status not in accepted_statuses:
                _error(
                    errors,
                    "runtime.capability.not_passed",
                    f"{path}.status",
                    f"capability status must be one of {sorted(accepted_statuses)}",
                )
            elif status == "bound_unprobed":
                warning_code = (
                    "runtime.capability.rgba_live_probe_deferred"
                    if name == "rgba_cutout_generation"
                    else "runtime.capability.opaque_live_probe_deferred"
                )
                warning_message = (
                    "image generation is bound but unprobed; inspect the first real asset "
                    "without blocking source reading on a synthetic calibration image"
                )
                _warning(
                    warnings,
                    warning_code,
                    f"{path}.status",
                    warning_message,
                )

        if name == "provider_acquisition_authority":
            adapter_route = adapter_capabilities.get(
                "image.provider.acquire.authority"
            )
            if (
                not isinstance(adapter_route, dict)
                or adapter_route.get("availability") == "unavailable"
            ):
                _error(
                    errors,
                    "runtime.capability.provider_acquisition_authority_unavailable",
                    path,
                    (
                        "the profile selected an optional provider-acquisition policy hook, "
                        "but this harness exposes no such callable"
                    ),
                )
                tool_ids = []
            else:
                tool_ids = _require_tool_kinds(
                    item.get("tool_ids"),
                    f"{path}.tool_ids",
                    tool_map,
                    errors,
                    ({"image.provider.acquire.authority"},),
                )
                _require_adapter_routes(
                    ("image.provider.acquire.authority",),
                    tool_ids,
                    adapter_capabilities,
                    errors,
                    f"{path}.tool_ids",
                )
            if (
                item.get("trust_boundary")
                != "trusted-harness-policy-hook-no-assurance-upgrade"
                or item.get("authority_mode") != "policy-hook-only"
            ):
                _error(
                    errors,
                    "runtime.capability.provider_acquisition_authority_boundary_invalid",
                    path,
                    (
                        "provider acquisition callback is only a trusted-harness veto "
                        "policy hook and cannot upgrade current-session assurance"
                    ),
                )
            if (
                not binding_only
                and item.get("observed_access")
                != "evaluate-exact-provider-acquisition-challenge-as-policy-hook"
            ):
                _error(
                    errors,
                    "runtime.capability.provider_acquisition_authority_probe_incomplete",
                    f"{path}.observed_access",
                    (
                        "configured policy hook must evaluate the exact article acquisition "
                        "challenge; allow does not constitute attestation"
                    ),
                )
            probe_methods = {"host-policy-hook"}
        elif name == "filesystem_access_lease":
            adapter_route = adapter_capabilities.get("filesystem.access.lease")
            if (
                not isinstance(adapter_route, dict)
                or adapter_route.get("availability") == "unavailable"
            ):
                _error(
                    errors,
                    "runtime.capability.filesystem_lease_unavailable",
                    path,
                    "selected harness cannot enforce the source-zero filesystem allowlist; a profile declaration cannot replace a host lease",
                )
                tool_ids = []
            else:
                tool_ids = _require_tool_kinds(
                    item.get("tool_ids"),
                    f"{path}.tool_ids",
                    tool_map,
                    errors,
                    ({"filesystem.access.lease"},),
                )
                _require_adapter_routes(
                    ("filesystem.access.lease",),
                    tool_ids,
                    adapter_capabilities,
                    errors,
                    f"{path}.tool_ids",
                )
            policy_sha, lease_id = _validate_filesystem_policy(item, phase, path, errors)
            probe_methods = {"host-enforced-live"}
        elif name == "migration_probe_finalization":
            adapter_route = adapter_capabilities.get("host.migration.finalize")
            if (
                not isinstance(adapter_route, dict)
                or adapter_route.get("availability") == "unavailable"
            ):
                _error(
                    errors,
                    "runtime.capability.migration_finalizer_unavailable",
                    path,
                    "selected harness has no host-owned migration finalizer/signing callable and replay ledger",
                )
                tool_ids = []
            else:
                tool_ids = _require_tool_kinds(
                    item.get("tool_ids"),
                    f"{path}.tool_ids",
                    tool_map,
                    errors,
                    ({"host.migration.finalize"},),
                )
                _require_adapter_routes(
                    ("host.migration.finalize",),
                    tool_ids,
                    adapter_capabilities,
                    errors,
                    f"{path}.tool_ids",
                )
            if (
                item.get("trust_boundary")
                != "host-owned-private-key-protected-trust-store-and-replay-ledger"
            ):
                _error(
                    errors,
                    "runtime.capability.migration_finalizer_trust_boundary_invalid",
                    f"{path}.trust_boundary",
                    "migration finalization requires a host-owned signing key, protected public trust store and atomic replay ledger",
                )
            probe_methods = {"host-attested-live"}
        elif name == "opaque_image_generation":
            tool_ids = _require_tool_kinds(
                item.get("tool_ids"),
                f"{path}.tool_ids",
                tool_map,
                errors,
                ({"image.generate.opaque"},),
            )
            _require_adapter_routes(
                ("image.generate.opaque",),
                tool_ids,
                adapter_capabilities,
                errors,
                f"{path}.tool_ids",
            )
            adapter_route = adapter_capabilities.get("image.generate.opaque")
            if not isinstance(adapter_route, dict) or adapter_route.get("route") != "tool":
                _error(
                    errors,
                    "runtime.capability.opaque_route_unresolved",
                    path,
                    "selected adapter must expose a direct opaque-image generation route",
                )
            probe_methods = (
                {"runtime-registry"}
                if status == "bound_unprobed"
                else {"generated-asset-live"}
            )
        elif name == "rgba_cutout_generation":
            output_contract = item.get("output_contract")
            if output_contract != "subject-cutout-rgba8-v1":
                _error(
                    errors,
                    "runtime.capability.rgba_output_contract_mismatch",
                    f"{path}.output_contract",
                    "RGBA cutout generation must bind subject-cutout-rgba8-v1",
                )
            processor = item.get("processor")
            if processor != "scripts/prepare_micro_cutout.py":
                _error(
                    errors,
                    "runtime.capability.rgba_processor_mismatch",
                    f"{path}.processor",
                    "RGBA cutouts must pass through scripts/prepare_micro_cutout.py",
                )
            adapter_route = adapter_capabilities.get("image.generate.rgba")
            adapter_mode = adapter_route.get("route") if isinstance(adapter_route, dict) else None
            if adapter_mode != mode:
                _error(
                    errors,
                    "runtime.capability.rgba_route_unresolved",
                    f"{path}.mode",
                    "selected RGBA mode does not match the current harness adapter route",
                )
            if (
                not isinstance(adapter_route, dict)
                or adapter_route.get("output_contract") != output_contract
                or adapter_route.get("processor") != processor
            ):
                _error(
                    errors,
                    "runtime.capability.rgba_adapter_contract_mismatch",
                    path,
                    "selected adapter must preserve the RGBA output contract and cutout processor",
                )
            generation_route_id = item.get("generation_route_id")
            if (
                not isinstance(generation_route_id, str)
                or not GENERATION_ROUTE_ID.fullmatch(generation_route_id)
            ):
                _error(
                    errors,
                    "runtime.capability.rgba_generation_route_id_invalid",
                    f"{path}.generation_route_id",
                    "RGBA generation must bind the selected provider's stable route ID",
                )
            if (
                not isinstance(adapter_route, dict)
                or adapter_route.get("generation_route_id") != generation_route_id
            ):
                _error(
                    errors,
                    "runtime.capability.rgba_adapter_generation_route_mismatch",
                    path,
                    "profile generation route ID must match the selected adapter route",
                )
            if mode == "tool":
                tool_ids = _require_tool_kinds(
                    item.get("tool_ids"),
                    f"{path}.tool_ids",
                    tool_map,
                    errors,
                    ({"image.generate.rgba"},),
                )
                _require_adapter_routes(
                    ("image.generate.rgba",),
                    tool_ids,
                    adapter_capabilities,
                    errors,
                    f"{path}.tool_ids",
                )
            else:
                tool_ids = _require_tool_kinds(
                    item.get("tool_ids"),
                    f"{path}.tool_ids",
                    tool_map,
                    errors,
                    ({"chatgpt.session", "browser.control"},),
                )
                _require_adapter_routes(
                    ("image.generate.rgba", "chatgpt.session", "browser.control"),
                    tool_ids,
                    adapter_capabilities,
                    errors,
                    f"{path}.tool_ids",
                )
                ingest_route = adapter_capabilities.get("browser.download.ingest")
                if (
                    not isinstance(ingest_route, dict)
                    or ingest_route.get("availability") == "unavailable"
                ):
                    _error(
                        errors,
                        "runtime.capability.browser_download_ingest_unavailable",
                        f"{path}.download_ingest_tool_ids",
                        "ChatGPT-web RGBA requires a current-session Browser download ingestion route",
                    )
                    ingest_tool_ids = []
                else:
                    ingest_tool_ids = _require_tool_kinds(
                        item.get("download_ingest_tool_ids"),
                        f"{path}.download_ingest_tool_ids",
                        tool_map,
                        errors,
                        ({"browser.download.ingest"},),
                    )
                    _require_adapter_routes(
                        ("browser.download.ingest",),
                        ingest_tool_ids,
                        adapter_capabilities,
                        errors,
                        f"{path}.download_ingest_tool_ids",
                    )
                provider_skill = item.get("provider_skill")
                if not isinstance(provider_skill, dict):
                    _error(
                        errors,
                        "runtime.skills.provider_skill_missing",
                        f"{path}.provider_skill",
                        "ChatGPT web generation requires the reviewed wrapper Skill",
                    )
                else:
                    if provider_skill.get("id") != "chatgpt-web-image-route":
                        _error(
                            errors,
                            "runtime.skills.provider_skill_missing",
                            f"{path}.provider_skill.id",
                            "provider Skill id must be chatgpt-web-image-route",
                        )
                    if provider_skill.get("status") != "loaded":
                        _error(
                            errors,
                            "runtime.skills.provider_skill_not_loaded",
                            f"{path}.provider_skill.status",
                            "the ChatGPT image-route wrapper Skill must be loaded before authoring",
                        )
                    installed_provider = (installed_registry.get("skills") or {}).get(
                        "chatgpt-web-image-route"
                    )
                    if (
                        not isinstance(installed_provider, dict)
                        or installed_provider.get("registry_status") != "loaded"
                    ):
                        _error(
                            errors,
                            "runtime.skills.provider_skill_registry_not_loaded",
                            f"{path}.provider_skill.status",
                            "the verified current host registry must report chatgpt-web-image-route as loaded",
                        )
                    elif provider_skill.get("status") != installed_provider.get(
                        "registry_status"
                    ):
                        _error(
                            errors,
                            "runtime.skills.provider_skill_profile_not_registry",
                            f"{path}.provider_skill.status",
                            "provider Skill status does not match the verified current host registry",
                        )
                    if provider_skill.get("contract") != "chatgpt-web-image-route-v1":
                        _error(
                            errors,
                            "runtime.skills.provider_skill_contract_mismatch",
                            f"{path}.provider_skill.contract",
                            "provider Skill must implement chatgpt-web-image-route-v1",
                        )
                adapter_provider_skill = (
                    adapter_route.get("provider_skill")
                    if isinstance(adapter_route, dict)
                    else None
                )
                if (
                    not isinstance(adapter_route, dict)
                    or not isinstance(adapter_provider_skill, dict)
                    or not isinstance(provider_skill, dict)
                    or adapter_provider_skill.get("id") != provider_skill.get("id")
                    or adapter_provider_skill.get("contract")
                    != provider_skill.get("contract")
                    or adapter_provider_skill.get("required_status")
                    != provider_skill.get("status")
                ):
                    _error(
                        errors,
                        "runtime.capability.rgba_adapter_contract_mismatch",
                        path,
                        "profile provider Skill, output contract, and processor must match the adapter",
                    )
                if not binding_only and isinstance(item.get("probe"), dict):
                    if item["probe"].get("method") in {
                        "c2c-doctor",
                        "chatgpt-session",
                        "provider-session",
                    }:
                        _error(
                            errors,
                            "runtime.capability.rgba_session_not_live_image_proof",
                            f"{path}.probe.method",
                            "C2C doctor/session readiness is not proof of a generated RGBA asset",
                        )
            probe_methods = (
                {"runtime-registry"}
                if status == "bound_unprobed"
                else {"generated-asset-live"}
            )
        elif name == "visual_inspection":
            tool_ids = _require_tool_kinds(
                item.get("tool_ids"),
                f"{path}.tool_ids",
                tool_map,
                errors,
                ({"image.inspect"},),
            )
            _require_adapter_routes(
                ("image.inspect",), tool_ids, adapter_capabilities, errors, f"{path}.tool_ids"
            )
            probe_methods = {"read-only-live"}
        elif name == "ardot_bootstrap":
            accepted = ({"ardot.create"},) if mode == "mcp" else ({"browser.control"}, {"computer.use"})
            tool_ids = _require_tool_kinds(
                item.get("tool_ids"), f"{path}.tool_ids", tool_map, errors, accepted
            )
            selected_routes = ("ardot.create",) if mode == "mcp" else tuple(
                kind
                for kind in ("browser.control", "computer.use")
                if any(tool_map[tool_id].get("kind") == kind for tool_id in tool_ids)
            )
            _require_adapter_routes(
                selected_routes, tool_ids, adapter_capabilities, errors, f"{path}.tool_ids"
            )
            probe_methods = {"runtime-registry", "read-only-live"}
        elif name == "ardot_authoring":
            accepted = (
                ({"ardot.read", "ardot.write", "ardot.export"},)
                if mode == "mcp"
                else ({"browser.control"}, {"computer.use"})
            )
            tool_ids = _require_tool_kinds(
                item.get("tool_ids"), f"{path}.tool_ids", tool_map, errors, accepted
            )
            selected_routes = ("ardot.read", "ardot.write", "ardot.export") if mode == "mcp" else tuple(
                kind
                for kind in ("browser.control", "computer.use")
                if any(tool_map[tool_id].get("kind") == kind for tool_id in tool_ids)
            )
            _require_adapter_routes(
                selected_routes, tool_ids, adapter_capabilities, errors, f"{path}.tool_ids"
            )
            link_name = item.get("workspace_link")
            if not isinstance(link_name, str) or link_name not in links:
                _error(
                    errors,
                    "runtime.capability.ardot_link_unresolved",
                    f"{path}.workspace_link",
                    "Ardot workspace link must resolve in profile.links",
                )
            elif link_name in links:
                raw_url = links[link_name].get("url")
                _validate_ardot_url(
                    raw_url if isinstance(raw_url, str) else "",
                    f"profile.links.{link_name}.url",
                    errors,
                )
                match = re.search(r"/file/([0-9]+)", raw_url if isinstance(raw_url, str) else "")
                link_file_id = match.group(1) if match else None
                expected_file_id = item.get("expected_file_id")
                if not isinstance(expected_file_id, str) or not expected_file_id:
                    _error(
                        errors,
                        "runtime.capability.ardot_expected_file_missing",
                        f"{path}.expected_file_id",
                        "expected Ardot file id is required",
                    )
                elif link_file_id is not None and expected_file_id != link_file_id:
                    _error(
                        errors,
                        "runtime.capability.ardot_link_file_mismatch",
                        f"{path}.expected_file_id",
                        "expected Ardot file id does not match workspace URL",
                    )
                expected_root_id = item.get("expected_root_id")
                if not isinstance(expected_root_id, str) or not ARDOT_NODE_ID.fullmatch(expected_root_id):
                    _error(
                        errors,
                        "runtime.capability.ardot_expected_root_invalid",
                        f"{path}.expected_root_id",
                        "expected Ardot root/node id is required and must use the canonical node-id shape",
                    )
                query_node_id = dict(parse_qsl(urlsplit(raw_url).query)).get("node_id") if isinstance(raw_url, str) else None
                if query_node_id is not None and query_node_id != expected_root_id:
                    _error(
                        errors,
                        "runtime.capability.ardot_link_root_mismatch",
                        f"{path}.expected_root_id",
                        "expected Ardot root/node id does not match the workspace URL node_id",
                    )
                if not binding_only:
                    _validate_probe(
                        links[link_name].get("probe"),
                        f"profile.links.{link_name}.probe",
                        errors,
                        now=now,
                        max_age_minutes=max_age_minutes,
                        required_methods={"read-only-live"},
                    )
                    if item.get("observed_file_id") != expected_file_id:
                        _error(
                            errors,
                            "runtime.capability.ardot_observed_file_mismatch",
                            f"{path}.observed_file_id",
                            "live Ardot probe returned a different file id",
                        )
                    if item.get("observed_root_id") != expected_root_id:
                        _error(
                            errors,
                            "runtime.capability.ardot_observed_root_mismatch",
                            f"{path}.observed_root_id",
                            "live Ardot probe returned a different article root/node id",
                        )
                    if item.get("observed_access") != "read-write-export":
                        _error(
                            errors,
                            "runtime.capability.ardot_access_incomplete",
                            f"{path}.observed_access",
                            "live Ardot probe must confirm read, write, and export access",
                        )
            probe_methods = {"read-only-live"}
        elif name == "wechat_delivery":
            accepted = ({"wechat.draft"},) if mode == "api" else ({"browser.control"}, {"computer.use"})
            tool_ids = _require_tool_kinds(
                item.get("tool_ids"), f"{path}.tool_ids", tool_map, errors, accepted
            )
            selected_routes = ("wechat.draft",) if mode == "api" else tuple(
                kind
                for kind in ("browser.control", "computer.use")
                if any(tool_map[tool_id].get("kind") == kind for tool_id in tool_ids)
            )
            _require_adapter_routes(
                selected_routes, tool_ids, adapter_capabilities, errors, f"{path}.tool_ids"
            )
            link_name = item.get("account_link")
            if not isinstance(link_name, str) or link_name not in links:
                _error(
                    errors,
                    "runtime.capability.wechat_link_unresolved",
                    f"{path}.account_link",
                    "WeChat account/API link must resolve in profile.links",
                )
            elif link_name in links:
                raw_url = links[link_name].get("url")
                _validate_wechat_url(
                    raw_url if isinstance(raw_url, str) else "",
                    mode,
                    f"profile.links.{link_name}.url",
                    errors,
                )
            account_ref = item.get("target_account_ref")
            terminal_state = item.get("terminal_state", "draft")
            if terminal_state not in {"draft", "publish"}:
                _error(
                    errors,
                    "runtime.capability.wechat_terminal_state_invalid",
                    f"{path}.terminal_state",
                    "WeChat terminal_state must be draft or publish",
                )
            if not isinstance(account_ref, str) or not account_ref.strip():
                _error(
                    errors,
                    "runtime.capability.wechat_account_missing",
                    f"{path}.target_account_ref",
                    "target account reference is required",
                )
            if not binding_only:
                if isinstance(link_name, str) and link_name in links:
                    _validate_probe(
                        links[link_name].get("probe"),
                        f"profile.links.{link_name}.probe",
                        errors,
                        now=now,
                        max_age_minutes=max_age_minutes,
                        required_methods={"read-only-live"},
                    )
                if status == "needs_user_login":
                    _error(
                        errors,
                        "runtime.capability.wechat_needs_user_login",
                        f"{path}.status",
                        "target WeChat route requires user login before delivery",
                    )
                if item.get("observed_account_ref") != account_ref:
                    _error(
                        errors,
                        "runtime.capability.wechat_account_mismatch",
                        f"{path}.observed_account_ref",
                        "live WeChat probe returned a different visible account",
                    )
                if item.get("observed_access") != "draft-read-write":
                    _error(
                        errors,
                        "runtime.capability.wechat_access_incomplete",
                        f"{path}.observed_access",
                        "live WeChat probe must confirm draft read/write access",
                    )
            probe_methods = {"read-only-live"}
        elif name == "wechat_current_session_readback":
            tool_ids = _require_tool_kinds(
                item.get("tool_ids"),
                f"{path}.tool_ids",
                tool_map,
                errors,
                (
                    {"browser.control", "wechat.current-session-readback"},
                    {"computer.use", "wechat.current-session-readback"},
                ),
            )
            _require_adapter_routes(
                ("wechat.current-session-readback",),
                tool_ids,
                adapter_capabilities,
                errors,
                f"{path}.tool_ids",
            )
            if (
                item.get("truth_boundary")
                != "browser-computer-use-exact-draft-capture-current-session-only-nonportable-no-publication-authority"
                or item.get("processor")
                != "scripts/ingest_wechat_readback_capture.py"
            ):
                _error(
                    errors,
                    "runtime.capability.wechat_readback_boundary_invalid",
                    path,
                    "current-session readback must remain exact-draft UI capture, nonportable and non-authorizing",
                )
            account_ref = item.get("target_account_ref")
            if not isinstance(account_ref, str) or not account_ref:
                _error(
                    errors,
                    "runtime.capability.wechat_readback_account_missing",
                    f"{path}.target_account_ref",
                    "current-session readback requires the exact target account",
                )
            probe_methods = {"read-only-live"}
        elif name == "wechat_publication_authority":
            adapter_route = adapter_capabilities.get(
                "wechat.current-session-authority"
            )
            if (
                not isinstance(adapter_route, dict)
                or adapter_route.get("availability") == "unavailable"
            ):
                _error(
                    errors,
                    "runtime.capability.wechat_publication_authority_unavailable",
                    path,
                    "the selected harness has no independent current-session publication authority",
                )
                tool_ids = []
            else:
                tool_ids = _require_tool_kinds(
                    item.get("tool_ids"),
                    f"{path}.tool_ids",
                    tool_map,
                    errors,
                    ({"wechat.current-session-authority"},),
                )
                _require_adapter_routes(
                    ("wechat.current-session-authority",),
                    tool_ids,
                    adapter_capabilities,
                    errors,
                    f"{path}.tool_ids",
                )
            if (
                item.get("trust_boundary")
                != "host-in-process-fresh-confirmation-and-authoritative-readback"
            ):
                _error(
                    errors,
                    "runtime.capability.wechat_publication_authority_boundary_invalid",
                    f"{path}.trust_boundary",
                    "publication authority must remain inside the host and consume a fresh confirmation plus authoritative readback",
                )
            if (
                not binding_only
                and item.get("observed_access")
                != "consume-confirmation-and-publish-exact-readback-draft"
            ):
                _error(
                    errors,
                    "runtime.capability.wechat_publication_authority_probe_incomplete",
                    f"{path}.observed_access",
                    "host probe must confirm fresh confirmation consumption and exact draft publication",
                )
            probe_methods = {"host-live-authority"}
        elif name == "host_receipt_attestation":
            adapter_route = adapter_capabilities.get("host.receipt.attest")
            if (
                not isinstance(adapter_route, dict)
                or adapter_route.get("availability") == "unavailable"
            ):
                _error(
                    errors,
                    "runtime.capability.host_receipt_attestation_unavailable",
                    path,
                    "selected harness has no real host receipt signer; portable signed audit is unavailable",
                )
                tool_ids = []
                probe_methods = {"host-attested-live"}
                resolved[name] = {"mode": mode, "tool_ids": tool_ids}
                continue
            tool_ids = _require_tool_kinds(
                item.get("tool_ids"),
                f"{path}.tool_ids",
                tool_map,
                errors,
                ({"host.receipt.attest"},),
            )
            _require_adapter_routes(
                ("host.receipt.attest",),
                tool_ids,
                adapter_capabilities,
                errors,
                f"{path}.tool_ids",
            )
            trust_boundary = item.get("trust_boundary")
            if trust_boundary != "host-owned-private-key-and-protected-trust-store":
                _error(
                    errors,
                    "runtime.capability.host_receipt_trust_boundary_invalid",
                    f"{path}.trust_boundary",
                    (
                        "host receipt attestation must use a host-owned private key and a "
                        "protected read-only trust store; repository or environment-owned keys are forbidden"
                    ),
                )
            if not binding_only and item.get("observed_access") != "sign-live-read-and-saved-draft":
                _error(
                    errors,
                    "runtime.capability.host_receipt_access_incomplete",
                    f"{path}.observed_access",
                    "host probe must confirm both live-root and saved-draft receipt signing",
                )
            probe_methods = {"host-attested-live"}
        else:
            secret_refs = item.get("secret_refs")
            if not isinstance(secret_refs, list):
                secret_refs = []
            if "PROVENANCE_WATERMARK_KEY" not in secret_refs:
                _error(
                    errors,
                    "runtime.secret.watermark_ref_missing",
                    f"{path}.secret_refs",
                    "PROVENANCE_WATERMARK_KEY reference is required",
                )
            path_refs = item.get("path_refs")
            if not isinstance(path_refs, list) or "PROVENANCE_WATERMARK_PRIVATE_ROOT" not in path_refs:
                _error(
                    errors,
                    "runtime.private_root.ref_missing",
                    f"{path}.path_refs",
                    "PROVENANCE_WATERMARK_PRIVATE_ROOT reference is required",
                )
                path_refs = []
            for index, secret_ref in enumerate(secret_refs):
                if not isinstance(secret_ref, str) or not ENV_REF.fullmatch(secret_ref):
                    _error(
                        errors,
                        "runtime.secret.ref_invalid",
                        f"{path}.secret_refs[{index}]",
                        "secret reference must be an uppercase identifier",
                    )
            for index, path_ref in enumerate(path_refs):
                if not isinstance(path_ref, str) or not ENV_REF.fullmatch(path_ref):
                    _error(
                        errors,
                        "runtime.private_root.ref_invalid",
                        f"{path}.path_refs[{index}]",
                        "private path reference must be an uppercase identifier",
                    )
            if mode == "environment":
                tool_ids = []
                for secret_ref in secret_refs:
                    secret_value = environment.get(secret_ref)
                    if binding_only:
                        continue
                    if not secret_value:
                        _error(
                            errors,
                            "runtime.secret.ref_unresolved",
                            f"{path}.secret_refs.{secret_ref}",
                            "secret reference is not available in the current environment",
                        )
                    elif secret_ref == "PROVENANCE_WATERMARK_KEY" and not _valid_watermark_key(
                        secret_value
                    ):
                        _error(
                            errors,
                            "runtime.secret.watermark_key_invalid",
                            f"{path}.secret_refs.{secret_ref}",
                            "watermark key must be hex:/base64: encoded and at least 32 bytes",
                        )
                if not binding_only and "PROVENANCE_WATERMARK_PRIVATE_ROOT" in path_refs:
                    _validate_private_root(
                        environment.get("PROVENANCE_WATERMARK_PRIVATE_ROOT"),
                        errors,
                        f"{path}.path_refs.PROVENANCE_WATERMARK_PRIVATE_ROOT",
                    )
                probe_methods = {"environment-reference"}
            else:
                tool_ids = _require_tool_kinds(
                    item.get("tool_ids"),
                    f"{path}.tool_ids",
                    tool_map,
                    errors,
                    ({"secret.resolve"},),
                )
                _require_adapter_routes(
                    ("secret.resolve",), tool_ids, adapter_capabilities, errors, f"{path}.tool_ids"
                )
                probe_methods = {"secret-reference", "read-only-live"}

        if not binding_only:
            _validate_probe(
                item.get("probe"),
                f"{path}.probe",
                errors,
                now=now,
                max_age_minutes=max_age_minutes,
                required_methods=probe_methods,
            )
        resolved_item: dict[str, Any] = {"mode": mode, "tool_ids": tool_ids}
        if name in {"opaque_image_generation", "rgba_cutout_generation"}:
            resolved_item["live_proof"] = (
                "deferred-until-first-generated-asset-nonblocking-for-source-reading"
                if binding_only or status == "bound_unprobed"
                else "profile-claim-unattested"
            )
        if name == "rgba_cutout_generation":
            resolved_item["output_contract"] = item.get("output_contract")
            resolved_item["processor"] = item.get("processor")
            if phase == "migration":
                resolved_item["migration_probe_contract"] = item.get(
                    "migration_probe_contract"
                )
                resolved_item["generation_route_id"] = item.get(
                    "generation_route_id"
                )
            if mode == "chatgpt-web":
                resolved_item["provider_skill"] = item.get("provider_skill")
                resolved_item["session_readiness_is_image_proof"] = False
                resolved_item["download_ingest_tool_ids"] = ingest_tool_ids
        if name == "filesystem_access_lease":
            resolved_item["policy_sha256"] = policy_sha
            resolved_item["lease_id"] = lease_id
        if name == "wechat_delivery":
            resolved_item["terminal_state"] = item.get("terminal_state", "draft")
            resolved_item["target_account_ref"] = item.get("target_account_ref")
        if name == "wechat_current_session_readback":
            resolved_item["target_account_ref"] = item.get("target_account_ref")
            resolved_item["truth_boundary"] = item.get("truth_boundary")
            resolved_item["processor"] = item.get("processor")
        if name == "provider_acquisition_authority":
            resolved_item["authority_mode"] = item.get("authority_mode")
        resolved[name] = resolved_item

    wechat_resolved = resolved.get("wechat_delivery")
    readback_resolved = resolved.get("wechat_current_session_readback")
    portable_selected = "host_receipt_attestation" in resolved
    requires_current_readback = bool(
        isinstance(wechat_resolved, dict)
        and wechat_resolved.get("mode") == "api"
        and wechat_resolved.get("terminal_state", "draft") == "draft"
        and not portable_selected
    )
    if requires_current_readback and (
        not isinstance(readback_resolved, dict)
        or readback_resolved.get("target_account_ref")
        != wechat_resolved.get("target_account_ref")
    ):
        _error(
            errors,
            "runtime.readback.current_session_route_missing",
            "profile.capabilities.wechat_current_session_readback",
            "current-session API draft delivery requires the exact-account Browser/Computer Use readback capture route",
        )
    if not requires_current_readback and isinstance(readback_resolved, dict):
        _error(
            errors,
            "runtime.readback.route_out_of_scope",
            "profile.capabilities.wechat_current_session_readback",
            "the current-session readback ingestion route is only selected for nonportable API draft delivery",
        )
    if (
        isinstance(wechat_resolved, dict)
        and wechat_resolved.get("terminal_state") == "publish"
        and wechat_resolved.get("mode") == "api"
        and "wechat_publication_authority" not in resolved
        and "host_receipt_attestation" not in resolved
    ):
        _error(
            errors,
            "runtime.publication.api_authority_unavailable",
            "profile.capabilities.wechat_delivery.terminal_state",
            (
                "API draft access is available but file-only wechat.draft cannot publish; "
                "bind wechat.current-session-authority, select portable receipts, or change "
                "the target to a declared live UI route"
            ),
        )

    for optional in sorted(set(PHASE_CAPABILITIES["full"]) - set(required)):
        if optional not in capabilities:
            _warning(
                warnings,
                "runtime.capability.out_of_phase_missing",
                f"profile.capabilities.{optional}",
                f"{optional} is not required for phase {phase}, but the full workflow is not ready",
            )
    return resolved


def _binding_digest(
    profile: dict[str, Any],
    phase: str,
    safe_links: dict[str, str],
    trusted_bundle_sha256: str,
) -> str:
    """Bind a future host receipt to intent without retaining probes or secrets."""

    skill_intent = []
    for item in profile.get("skills", []):
        if isinstance(item, dict):
            skill_intent.append(
                {
                    key: item.get(key)
                    for key in ("id", "entrypoint", "status", "sha256")
                }
            )
    tool_intent = []
    for item in profile.get("tools", []):
        if isinstance(item, dict):
            tool_intent.append(
                {
                    key: item.get(key)
                    for key in ("id", "kind", "status", "source", "provider", "session_id")
                }
            )
    capability_keys = {
        "mode",
        "authority_mode",
        "terminal_state",
        "trust_boundary",
        "truth_boundary",
        "tool_ids",
        "download_ingest_tool_ids",
        "provider_skill",
        "output_contract",
        "processor",
        "migration_probe_contract",
        "generation_route_id",
        "workspace_link",
        "expected_file_id",
        "expected_root_id",
        "account_link",
        "target_account_ref",
        "secret_refs",
        "path_refs",
        "policy_sha256",
        "lease",
    }
    capability_intent: dict[str, Any] = {}
    capabilities = profile.get("capabilities")
    if isinstance(capabilities, dict):
        for name, item in capabilities.items():
            if isinstance(name, str) and isinstance(item, dict):
                capability_intent[name] = {
                    key: item.get(key) for key in sorted(capability_keys) if key in item
                }
    intent = {
        "schema_version": SCHEMA_VERSION,
        "kind": PROFILE_KIND,
        "phase": phase,
        "trusted_bundle_sha256": trusted_bundle_sha256,
        "harness": profile.get("harness"),
        "registry_census": profile.get("registry_census"),
        "artifact_inventory": profile.get("artifact_inventory"),
        "skills": sorted(skill_intent, key=lambda item: str(item.get("id"))),
        "tools": sorted(tool_intent, key=lambda item: str(item.get("id"))),
        "links": dict(sorted(safe_links.items())),
        "capabilities": dict(sorted(capability_intent.items())),
    }
    encoded = json.dumps(intent, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _migration_rgba_probe_cases(
    *,
    binding_nonce: str,
    binding_digest: str,
    generation_route_id: str,
    runtime_root: Path,
) -> list[dict[str, Any]]:
    """Return a native-alpha probe followed by one controlled-key fallback."""

    common = (
        "Create one plain, nonsemantic calibration mark: a single connected open test "
        "stroke in uniform neutral mid-gray #777777. Make the stroke thickness about 8 "
        "percent of the canvas width; this describes thickness, not the overall mark size. "
        "Make the complete visible path bounding box span 60 to 70 percent of both the canvas "
        "width and height. Trace an asymmetric near-square path with at least three deep "
        "inward turns and large open negative spaces; do not close or fill a large region. "
        "It must not resemble any real object, icon, logo, letter, leaf, flower, animal, "
        "robot, device, or brand motif. Use no artistic style, material language, palette, "
        "lighting, or decoration. No text, letters, digits, logo, QR code, signature, "
        "frame, card, panel, pedestal, ground plane, scenery, texture, gradient, "
        "checkerboard, or backdrop shadow. Keep the silhouette fully inside the canvas "
        "with a clear 12 percent safety margin on every edge. "
    )
    specifications = (
        {
            "attempt": 1,
            "acquisition_mode": "native-alpha",
            "key_color": None,
            "prompt": (
                common
                + "Return the provider-original PNG with a genuinely transparent background "
                "and real pixel alpha. Background pixels must have alpha 0. Do not simulate "
                "transparency with white, black, a colored plane, checkerboard pixels, haze, "
                "or a rectangular matte."
            ),
            "processor_extra_args": ["--require-native-alpha"],
        },
        {
            "attempt": 2,
            "acquisition_mode": "controlled-key-fallback",
            "key_color": MIGRATION_RGBA_PROBE_FALLBACK_KEY,
            "prompt": (
                common
                + f"Return the provider-original PNG on a perfectly uniform "
                f"{MIGRATION_RGBA_PROBE_FALLBACK_KEY} background. Keep that key color out "
                "of the subject, keep it connected across the full canvas border, and do "
                "not add any shadow or semi-transparent effect onto the background."
            ),
            "processor_extra_args": [
                "--key-color",
                MIGRATION_RGBA_PROBE_FALLBACK_KEY,
            ],
        },
    )

    cases: list[dict[str, Any]] = []
    for specification in specifications:
        attempt = int(specification["attempt"])
        prompt = str(specification["prompt"])
        prompt_sha256 = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        request_metadata = {
            "schema": "org-wechat-migration-rgba-request-v1",
            "contract": MIGRATION_RGBA_PROBE_CONTRACT,
            "binding_nonce": binding_nonce,
            "binding_digest": binding_digest,
            "attempt": attempt,
            "acquisition_mode": specification["acquisition_mode"],
            "generation_route": generation_route_id,
            "prompt_sha256": prompt_sha256,
        }
        request_metadata_sha256 = "sha256:" + hashlib.sha256(
            json.dumps(
                request_metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        raw_path = f"{{artifact_root}}/provider-original-attempt-{attempt}.png"
        ingestion_report_path = (
            f"{{artifact_root}}/download-ingestion-attempt-{attempt}.json"
        )
        derived_path = f"{{artifact_root}}/cutout-rgba-attempt-{attempt}.png"
        report_path = f"{{artifact_root}}/cutout-report-attempt-{attempt}.json"
        failure_path = f"{{artifact_root}}/cutout-failure-attempt-{attempt}.json"
        processor_command = [
            "python3",
            "-I",
            "-S",
            str(runtime_root / "scripts" / "secure_runner.py"),
            str(runtime_root / "scripts" / "prepare_migration_probe.py"),
            raw_path,
            derived_path,
            "--binding-report",
            "{binding_report}",
            "--ingestion-report",
            ingestion_report_path,
            "--attempt",
            str(attempt),
            "--role",
            "floating-spot",
            "--article-id",
            "migration-route-probe",
            "--asset-slot-id",
            "migration.rgba-route-probe",
            "--prompt-sha256",
            prompt_sha256,
            "--generation-route",
            generation_route_id,
            *(
                ["--failure-report", failure_path]
                if attempt == 1
                else [
                    "--previous-failure-report",
                    "{artifact_root}/cutout-failure-attempt-1.json",
                ]
            ),
            *list(specification["processor_extra_args"]),
            "--report",
            report_path,
        ]
        cases.append(
            {
                "attempt": attempt,
                "acquisition_mode": specification["acquisition_mode"],
                "key_color": specification["key_color"],
                "prompt": prompt,
                "prompt_sha256": prompt_sha256,
                "generation_route": generation_route_id,
                "host_request_metadata": request_metadata,
                "host_request_metadata_sha256": request_metadata_sha256,
                "raw_path": raw_path,
                "ingestion_report_path": ingestion_report_path,
                "ingestion_command_template": [
                    "python3",
                    "-I",
                    "-S",
                    str(runtime_root / "scripts" / "secure_runner.py"),
                    str(runtime_root / "scripts" / "ingest_browser_download.py"),
                    "{browser_observed_absolute_download_path}",
                    raw_path,
                    "--report",
                    ingestion_report_path,
                    "--allowed-target-root",
                    "{artifact_root}",
                    "--binding-nonce",
                    binding_nonce,
                    "--binding-digest",
                    binding_digest,
                    "--provider-session-id",
                    "{provider_session_id}",
                    "--provider-request-id",
                    "{provider_request_id}",
                    "--observed-download-id",
                    "{observed_download_id}",
                    "--request-metadata-sha256",
                    request_metadata_sha256,
                ],
                "derived_path": derived_path,
                "derivation_report_path": report_path,
                "failure_report_path": failure_path if attempt == 1 else None,
                "processor_command": processor_command,
            }
        )
    return cases


def _migration_rgba_probe_action(
    *,
    binding_nonce: str,
    binding_digest: str,
    generation_route_id: str,
    runtime_root: Path,
    session_root: Path,
) -> dict[str, Any]:
    cases = _migration_rgba_probe_cases(
        binding_nonce=binding_nonce,
        binding_digest=binding_digest,
        generation_route_id=generation_route_id,
        runtime_root=runtime_root,
    )
    artifact_root = session_root / "migration-probes" / binding_nonce
    return {
        "id": "run-migration-rgba-route-probe",
        "action": "generate-download-derive-and-inspect-neutral-rgba-probe",
        "contract": MIGRATION_RGBA_PROBE_CONTRACT,
        "blocking": True,
        "must_complete_before": [
            "read-source-material",
            "create-organization-pack",
            "open-ardot-target",
            "open-wechat-account",
        ],
        "binding_nonce_ref": "report.binding_nonce",
        "binding_digest_ref": "report.binding_digest",
        "artifact_root_template": MIGRATION_RGBA_PROBE_ARTIFACT_ROOT,
        "session_root": str(session_root),
        "artifact_root": str(artifact_root),
        "artifact_policy": (
            "create-once-current-binding-only;git-ignored;never-register;"
            "never-copy-to-organization-assets;never-upload-to-ardot"
        ),
        "path_preconditions": [
            "session-root-is-external-to-installed-runtime",
            "session-root-is-outside-git-or-git-ignored",
            "raw-derived-and-report-paths-do-not-exist",
            "artifact-root-and-path-components-are-not-symlinks",
            "no-artifact-from-another-binding-nonce-is-reused",
        ],
        "attempt_policy": {
            "preference": "native-alpha-first-controlled-key-fallback-only",
            "maximum_attempts": 2,
            "run_attempt_2_only_after_attempt_1_processing_failure": True,
            "attempt_2_trigger": (
                "attempt-1-provider-original-lacks-valid-native-alpha-or-fails-pixel-gate-only"
            ),
            "attempt_2_trigger_codes": sorted(
                (
                    "cutout.source.invalid_native_rgba",
                    "cutout.source.native_alpha_required",
                )
            ),
            "attempt_2_requires_processor_failure_report": True,
            "attempt_2_requires_new_user_confirmation": False,
            "attempt_2_next_action_is_bound_in_failure_report": True,
            "login_captcha_download_repair_consumes_attempt": False,
            "source_attempt_counts_only_after_original_download": True,
            "request_recovery_is_separate_from_source_attempt": True,
            "provider_timeout_recovery": {
                "states": [
                    "provider-pending",
                    "completed-await-download",
                    "provider-terminal-failed",
                    "browser-control-unavailable",
                ],
                "first_action": "read-only-resume-same-c2c-session-and-request",
                "duplicate_submission_allowed": False,
                "terminal_provider_failure_may_retry_same_bound_prompt": True,
                "browser_transport_failure_requires_host-reload": True,
            },
            "never_lower_cutout_thresholds": True,
        },
        "visual_context_policy": {
            "probe_is_style_reference": False,
            "official_prompt_may_reference_probe": False,
            "probe_semantics": "nonsemantic-monochrome-open-stroke-calibration-only",
            "probe_contains_organization_or_article_style_cues": False,
            "official_generation_must_exclude_calibration_mark": True,
            "follow_active_provider_session_rules": True,
            "same_c2c_managed_conversation_required": True,
            "throwaway_chat_inside_current_c2c_task_allowed": False,
        },
        "probe_cases": cases,
        "pixel_inspection_command_template": [
            "python3",
            "-I",
            "-S",
            str(runtime_root / "scripts" / "secure_runner.py"),
            str(runtime_root / "scripts" / "inspect_asset.py"),
            "{derived_path}",
            "--role",
            "floating-spot",
        ],
        "host_evidence_required": [
            "current-provider-request-and-completed-generation",
            "same-current-provider-session-for-request-generation-and-download",
            "browser-observed-provider-original-download-event",
            "local-original-png-magic-mime-byte-length-download-time-and-sha256",
            "secure-processor-zero-exit-and-create-once-derivation-report",
            "current-derived-rgba8-pixel-gate-pass",
            "host-image-inspection-of-the-exact-derived-file-on-transparent-light-and-dark-surfaces",
            "binding-nonce-and-binding-digest-associated-with-the-host-trace",
            "host-request-metadata-sha256-associated-with-provider-request-generation-and-download",
        ],
        "proof_boundary": {
            "local_pixel_chain": "processor-and-pixel-inspection-required-but-insufficient",
            "host_route": "current-host-request-generation-and-original-download-trace-required",
            "profile_or_model_authored_receipt_can_pass": False,
            "completion_requires_both": [
                "local_pixel_chain_verified",
                "host_route_verified",
            ],
        },
        "forbidden_acquisition": [
            "screenshot",
            "preview-canvas",
            "clipboard",
            "copied-remote-url",
            "model-authored-download-receipt",
        ],
        "expected_result": (
            "neutral-rgba-route-probe-passed-in-current-host-trace;"
            "probe-is-not-an-article-asset-and-does-not-replace-first-official-asset-lineage"
        ),
    }


def _build_host_setup_actions(
    profile: dict[str, Any],
    phase: str,
    safe_links: dict[str, str],
    *,
    runtime_root: Path | None = None,
    migration_session_root: Path | None = None,
    binding_nonce: str | None = None,
    binding_digest: str | None = None,
    trusted_bundle_sha256: str | None = None,
    portable_provider_signer_available: bool = False,
    include_legacy_rgba_probe: bool = False,
) -> list[dict[str, Any]]:
    """Return credential-free actions the host must prepare before authoring."""

    capabilities = profile.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
    filesystem = capabilities.get("filesystem_access_lease")
    filesystem_policy_sha = (
        filesystem.get("policy_sha256") if isinstance(filesystem, dict) else None
    )
    filesystem_lease = filesystem.get("lease") if isinstance(filesystem, dict) else None
    actions: list[dict[str, Any]] = []
    if isinstance(filesystem, dict):
        actions.append(
            {
                "id": "acquire-source-zero-filesystem-lease",
                "action": "acquire-host-filesystem-access-lease",
                "target": "filesystem.access.lease",
                "blocking": True,
                "must_complete_before": "load-phase-skill-or-read-any-source",
                "policy_sha256": filesystem_policy_sha,
                "lease_id": filesystem_lease.get("lease_id") if isinstance(filesystem_lease, dict) else None,
                "required_denies": [
                    "examples",
                    "other-organizations",
                    "legacy-output",
                    "legacy-ardot-references",
                ],
                "profile-or-model-claim-can-satisfy": False,
                "expected_result": "host-enforced-deny-by-default-lease-visible-in-current-session",
            }
        )
    else:
        actions.append(
            {
                "id": "enforce-source-zero-release-boundary",
                "action": "assert-verified-installed-release-census",
                "blocking": True,
                "must_complete_before": "load-phase-skill-or-read-any-source",
                "forbidden_package_trees": [
                    "examples",
                    "experiments",
                    "organizations",
                    "output",
                ],
                "assurance": "verified-release-package-not-host-filesystem-isolation",
                "expected_result": "installed-release-byte-census-verified-and-forbidden-trees-absent",
            }
        )
    actions.append(
        {
            "id": "load-phase-skill",
            "action": "load-skill",
            "target": PHASE_LOADED_SKILL[phase],
            "blocking": True,
            "expected_result": "repository-resource-and-sha-match",
        }
    )
    rgba_capability = capabilities.get("rgba_cutout_generation")
    rgba_mode = rgba_capability.get("mode") if isinstance(rgba_capability, dict) else None
    if "rgba_cutout_generation" in phase_capabilities(phase, profile) and rgba_mode == "chatgpt-web":
        actions.extend(
            [
                {
                    "id": "load-chatgpt-image-route-skill",
                    "action": "load-skill",
                    "target": "chatgpt-web-image-route",
                    "blocking": True,
                    "expected_result": "repository-wrapper-and-chatgpt-web-image-route-v1-contract-loaded",
                },
                {
                    "id": "load-codex-with-chatgpt-skill",
                    "action": "load-skill",
                    "target": "codex-with-chatgpt",
                    "blocking": True,
                    "expected_result": "current-skill-registry-resource-loaded",
                },
                {
                    "id": "prepare-codex-with-chatgpt",
                    "action": "run-provider-preflight",
                    "target": "codex-with-chatgpt",
                    "steps": [
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
                    "blocking": True,
                    "non_login_user_steps": [
                        "choose-temporary-or-fixed-address",
                        "authorize-cloudflare-only-if-fixed-address-selected",
                        "create-or-replace-exact-workspace-connector",
                        "create-or-bind-chatgpt-project",
                    ],
                    "expected_result": "exact-worktree-project-connector-and-workspace-identity-green-no-image-proof-claimed",
                },
                {
                    "id": "open-chatgpt-image-session",
                    "action": "claim-or-reuse-c2c-managed-iab-chat",
                    "target": "current-c2c-session-chat-or-project-conversation",
                    "credential_free_login_entry": EXPECTED_SETUP_LINKS["chatgpt_web"],
                    "blocking": True,
                    "user_step_if_needed": "complete-chatgpt-login-captcha-2fa-or-consent-after-workspace-setup",
                    "request_recovery": {
                        "states": [
                            "provider-pending",
                            "completed-await-download",
                            "provider-terminal-failed",
                            "browser-control-unavailable",
                        ],
                        "unknown_or_timeout_first_action": "read-only-resume-same-c2c-session-and-request",
                        "duplicate_submission_while_unknown": False,
                        "browser_failure_consumes_source_attempt": False,
                        "browser_failure_recovery": "reload-host-task-then-reread-same-request",
                        "provider_terminal_failure_recovery": "resubmit-same-mode-and-exact-bound-prompt-with-new-request-id",
                    },
                    "expected_result": (
                        "same-provider-session-visible-and-ready-for-image-request;"
                        "base-entry-used-only-for-login-or-c2c-approved-new-long-chat"
                    ),
                },
                {
                    "id": "bind-rgba-download-processing",
                    "action": "bind-observed-download-create-once-ingestion-and-processor",
                    "targets": [
                        "provider-original-png-download",
                        "browser.download.ingest",
                        "scripts/ingest_browser_download.py",
                        "scripts/prepare_migration_probe.py",
                        "scripts/prepare_micro_cutout.py",
                        "image.inspect",
                    ],
                    "blocking": True,
                    "expected_result": (
                        "browser-observed-path-create-once-ingestion-and-cutout-processor-visible;"
                        "first-real-generated-file-remains-the-quality-evidence"
                    ),
                },
            ]
        )
    if phase in {"authoring", "full"} and "rgba_cutout_generation" in phase_capabilities(phase, profile):
        provider_authority = capabilities.get("provider_acquisition_authority")
        actions.append(
            {
                "id": "validate-current-session-provider-acquisition-chain",
                "action": "validate-complete-current-session-acquisition-and-pixel-chain",
                "target": "scripts/provider_acquisition_authority.py",
                "blocking": True,
                "must_complete_before": "register-first-formal-article-micro-asset",
                "acquisition_kind": "org-wechat-provider-image-acquisition-v2",
                "authority_mode": "current-session-operator-harness-trusted",
                "host_attested": False,
                "portable": False,
                "required_evidence": [
                    "current-session-runtime-binding",
                    "canonical-provider-request",
                    "create-once-download-ingestion",
                    "exact-raw-byte-binding",
                    "rgba8-alpha-pixel-validation",
                ],
                "expected_result": (
                    "operator-harness-trusted current-session operational acceptance; "
                    "never a host-attested or portable claim"
                ),
            }
        )
        if isinstance(provider_authority, dict):
            actions.append(
                {
                    "id": "bind-provider-acquisition-policy-hook",
                    "action": "bind-optional-trusted-harness-veto-policy-hook",
                    "target": "image.provider.acquire.authority",
                    "blocking": False,
                    "must_complete_before": "prepare-first-formal-article-micro-asset",
                    "challenge_kind": (
                        "org-wechat-provider-image-authority-challenge-v1"
                    ),
                    "authority_mode": "policy-hook-only",
                    "can_veto": True,
                    "can_upgrade_assurance": False,
                    "expected_result": (
                        "allow leaves assurance unchanged; deny or exception blocks the asset"
                    ),
                }
            )
        if portable_provider_signer_available:
            actions.append(
                {
                    "id": "prepare-portable-provider-receipt-route",
                    "action": "bind-host-signer-and-protected-provider-trust-store",
                    "target": "host.receipt.attest",
                    "blocking": False,
                    "must_complete_before": "prepare-first-formal-article-micro-asset",
                    "receipt_kind": "org-wechat-provider-image-host-receipt-v1",
                    "authority_mode": "portable-signed",
                    "file-json-can-satisfy": False,
                    "expected_result": (
                        "host-signed-exact-provider-acquisition-challenge-verified-against-"
                        "protected-external-trust-store"
                    ),
                }
            )
    ardot_capability_name = "ardot_bootstrap" if phase == "bootstrap" else "ardot_authoring"
    ardot_capability = capabilities.get(ardot_capability_name)
    ardot_mode = ardot_capability.get("mode") if isinstance(ardot_capability, dict) else None
    if ardot_mode == "mcp":
        actions.append(
            {
                "id": "connect-ardot-mcp",
                "action": "diagnose-config-injection-auth-and-target-separately",
                "url": EXPECTED_SETUP_LINKS["ardot_mcp"],
                "blocking": True,
                "user_step_if_needed": "complete-ardot-oauth",
                "state_model": {
                    "configured": "codex-mcp-list-get-local-evidence-only",
                    "model_visible": "required-tool-ids-in-current-task-registry",
                    "live_authenticated": "same-session-provider-read-only-response",
                    "target_access_verified": "exact-file-and-root-read",
                    "last_mutation_outcome": "operation-specific-provider-response",
                },
                "configured_but_not_model_visible": "reload-or-open-new-codex-task;repository-cannot-hot-inject-tools",
                "configuration_or-oauth-does-not-prove": [
                    "current-task-injection",
                    "exact-target-access",
                    "remote-mutation-success",
                ],
                "expected_result": "provider-session-callables-visible-before-live-target-probe",
            }
        )
    elif ardot_mode == "ui":
        actions.append(
            {
                "id": "prepare-ardot-ui-route",
                "action": "load-ui-route",
                "target": "browser.control-or-computer.use",
                "blocking": True,
                "expected_result": "selected-ui-callables-visible",
            }
        )
    if phase == "bootstrap":
        ardot_url = EXPECTED_SETUP_LINKS["ardot_web"]
        ardot_result = "blank-design-create-route-ready"
    else:
        workspace_link = (
            ardot_capability.get("workspace_link") if isinstance(ardot_capability, dict) else None
        )
        ardot_url = safe_links.get(workspace_link) if isinstance(workspace_link, str) else None
        ardot_result = "exact-file-and-root-visible"
    if ardot_url:
        ardot_action = {
                "id": "open-ardot-target",
                "action": "open-or-read",
                "url": ardot_url,
                "blocking": True,
                "user_step_if_needed": "complete-ardot-web-login",
                "expected_result": ardot_result,
            }
        if phase == "bootstrap":
            ardot_action["create_design_contract"] = {
                "mutation_class": "non-idempotent",
                "bind_unique_nonce_and_title_before_call": True,
                "on_timeout_5xx_or_truncated_response": "create-unknown",
                "automatic_retry": False,
                "reconcile_before_retry": [
                    "reload-provider-task-if-needed",
                    "read-only-search-for-bound-nonce-or-title",
                    "ask-user-to-check-ardot-ui-only-if-provider-discovery-is-unavailable",
                    "create-again-only-after-absence-is-explicitly-established",
                ],
            }
        actions.append(ardot_action)
    if "wechat_delivery" in PHASE_CAPABILITIES[phase]:
        wechat = capabilities.get("wechat_delivery")
        wechat_mode = wechat.get("mode") if isinstance(wechat, dict) else None
        terminal_state = (
            wechat.get("terminal_state", "draft")
            if isinstance(wechat, dict)
            else "draft"
        )
        account_link = wechat.get("account_link") if isinstance(wechat, dict) else None
        account_url = safe_links.get(account_link) if isinstance(account_link, str) else None
        if wechat_mode == "api":
            publisher_root = runtime_root or Path(__file__).resolve().parent.parent
            actions.append(
                {
                    "id": "connect-wechat-api-provider",
                    "action": "run-read-only-account-preflight",
                    "url": account_url or EXPECTED_SETUP_LINKS["wechat_api"],
                    "blocking": True,
                    "user_step_if_needed": "authorize-wechat-api-provider",
                    "local_client": "scripts/wechat_publisher.py",
                    "preflight_command_template": [
                        "python3",
                        "-I",
                        "-S",
                        str(publisher_root / "scripts" / "secure_runner.py"),
                        str(publisher_root / "scripts" / "wechat_publisher.py"),
                        "--store",
                        "{external_session_root}/publisher.sqlite3",
                        "preflight-account",
                        "--target-account",
                        "{exact_account_ref}",
                        "--output",
                        "{external_session_root}/wechat-account-preflight.json",
                    ],
                    "read_only_endpoints": [
                        "draft/count",
                        "material/get_materialcount",
                    ],
                    "failure_classes": [
                        "credentials-missing",
                        "account-mismatch",
                        "api-unreachable",
                        "permission-denied",
                        "ui-readback-route-missing",
                    ],
                    "does_not_prove": [
                        "upload-permission",
                        "draft-write-permission",
                        "ui-readback",
                        "publication-permission",
                    ],
                    "expected_result": "exact-target-account-draft-and-material-read-access-visible-with-zero-mutations",
                }
            )
            if isinstance(
                capabilities.get("wechat_current_session_readback"), dict
            ):
                actions.append(
                    {
                        "id": "capture-wechat-current-session-readback",
                        "action": "open-exact-api-saved-draft-and-capture-chapters",
                        "target": "wechat.current-session-readback",
                        "blocking": True,
                        "must_complete_after": "capture-raw-api-draft-get",
                        "must_complete_before": "validate-saved-draft-readback",
                        "processor": "scripts/ingest_wechat_readback_capture.py",
                        "required_capture": "one actual 390px PNG per frozen chapter",
                        "assurance": "current-session-only-nonportable",
                        "host_attested": False,
                        "portable": False,
                        "publication_authority": False,
                        "expected_result": (
                            "exact-account-draft-revision-api-reread-runtime-session-"
                            "and-create-once-screenshot-bundle-bound"
                        ),
                    }
                )
            if terminal_state == "publish":
                if isinstance(
                    capabilities.get("wechat_publication_authority"), dict
                ):
                    actions.append(
                        {
                            "id": "bind-wechat-current-session-publication-authority",
                            "action": "bind-host-live-publication-authority",
                            "target": "wechat.current-session-authority",
                            "blocking": True,
                            "must_complete_before": "publish-exact-draft",
                            "expected_result": (
                                "fresh-user-confirmation-consumed-in-process-and-exact-"
                                "account-draft-authoritatively-read-back-before-publish"
                            ),
                        }
                    )
                elif not isinstance(
                    capabilities.get("host_receipt_attestation"), dict
                ):
                    actions.append(
                        {
                            "id": "resolve-wechat-api-publication-route",
                            "action": "stop-before-api-live-publish",
                            "target": "wechat.current-session-authority",
                            "blocking": True,
                            "current_route_status": "unavailable",
                            "available_alternatives": [
                                "change-target-mode-to-ui-and-use-a-declared-live-ui-route",
                                "select-portable-host-receipt-attestation",
                                "keep-terminal-state-draft",
                            ],
                            "expected_result": (
                                "independent-publication-authority-or-explicit-alternative-"
                                "selected;wechat-draft-api-alone-is-insufficient"
                            ),
                        }
                    )
        elif wechat_mode == "ui":
            actions.extend(
                [
                    {
                        "id": "prepare-wechat-ui-route",
                        "action": "load-ui-route",
                        "target": "browser.control-or-computer.use",
                        "blocking": True,
                        "expected_result": "selected-ui-skill-runtime-and-current-session-callables-visible",
                    },
                    {
                    "id": "open-wechat-account",
                    "action": "open-or-read",
                    "url": account_url or EXPECTED_SETUP_LINKS["wechat_web"],
                    "blocking": True,
                    "user_step_if_needed": "scan-or-complete-wechat-login",
                    "expected_result": "target-account-and-draft-access-visible",
                    },
                ]
            )
            if terminal_state == "publish":
                actions.append(
                    {
                        "id": "confirm-wechat-ui-live-publish",
                        "action": "consume-fresh-confirmation-and-publish-through-live-ui",
                        "target": "exact-current-wechat-draft",
                        "blocking": True,
                        "must_complete_before": "publish-or-group-send-click",
                        "expected_result": (
                            "fresh-confirmation-bound-to-visible-account-and-exact-draft;"
                            "authoritative-post-action-status-read-back"
                        ),
                    }
                )
    if isinstance(capabilities.get("host_receipt_attestation"), dict):
        actions.append(
            {
                "id": "bind-host-receipt-attestation",
                "action": "bind-host-callable-and-protected-trust-store",
                "targets": ["host.receipt.attest"],
                "blocking": True,
                "expected_result": (
                    "host-only-private-key-live-root-and-saved-draft-signing-visible;"
                    "root-owned-read-only-public-trust-store-readable"
                ),
            }
        )
    carrier_ids = _watermark_carrier_ids(profile, [])
    if carrier_ids and isinstance(capabilities.get("secret_store"), dict):
        actions.append(
            {
                "id": "resolve-watermark-runtime",
                "action": "resolve-secret-references",
                "targets": [
                    "PROVENANCE_WATERMARK_KEY",
                    "PROVENANCE_WATERMARK_PRIVATE_ROOT",
                ],
                "blocking": True,
                "eligible_carrier_ids": carrier_ids,
                "expected_result": "boolean-checks-only-no-values",
            }
        )
    if "visual_inspection" in PHASE_CAPABILITIES[phase]:
        actions.append(
            {
                "id": "bind-image-inspection",
                "action": "bind-callables",
                "targets": ["image.inspect"],
                "blocking": True,
                "expected_result": "inspection-callable-visible-neutral-read-required",
            }
        )
    if "opaque_image_generation" in phase_capabilities(phase, profile):
        actions.append(
            {
                "id": "bind-opaque-image-generation",
                "action": "bind-callables",
                "targets": ["image.generate.opaque"],
                "blocking": True,
                "expected_result": "opaque-callable-visible-first-real-asset-is-live-proof",
            }
        )
    if "rgba_cutout_generation" in phase_capabilities(phase, profile) and rgba_mode == "tool":
        actions.append(
            {
                "id": "bind-rgba-cutout-generation",
                "action": "bind-callables-and-processor",
                "targets": [
                    "image.generate.rgba",
                    "scripts/prepare_micro_cutout.py",
                    "image.inspect",
                ],
                "blocking": True,
                "expected_result": (
                    "rgba-callable-and-processor-visible-first-real-asset-is-quality-evidence"
                ),
            }
        )
    if phase == "migration":
        if binding_nonce is None or binding_digest is None:
            raise ValueError(
                "migration host actions require the current binding nonce and digest"
            )
        if runtime_root is None or migration_session_root is None:
            raise ValueError(
                "migration host actions require the installed runtime root and external session root"
            )
        generation_route_id = (
            rgba_capability.get("generation_route_id")
            if isinstance(rgba_capability, dict)
            else None
        )
        if not isinstance(generation_route_id, str):
            generation_route_id = "unresolved-generation-route"
        actions.append(
            {
                "id": "finalize-current-session-runtime-binding",
                "action": "create-session-continuation-without-rgba-probe",
                "target": "scripts/runtime_preflight.py finalize-current-session-migration",
                "blocking": True,
                "must_complete_before": "register-first-formal-article-micro-asset",
                "evidence_kind": RUNTIME_SESSION_EVIDENCE_KIND,
                "bindings": {
                    "binding_nonce": binding_nonce,
                    "binding_digest": binding_digest,
                    "trusted_bundle_sha256": trusted_bundle_sha256,
                },
                "assurance": "current-session-observed-path-not-portable-signed",
                "phase_ready_claim_allowed": False,
                "expected_result": "current-session-runtime-binding-without-rgba-calibration-gate",
            }
        )
        if include_legacy_rgba_probe:
            optional_probe = _migration_rgba_probe_action(
                binding_nonce=binding_nonce,
                binding_digest=binding_digest,
                generation_route_id=generation_route_id,
                runtime_root=runtime_root,
                session_root=migration_session_root,
            )
            optional_probe["blocking"] = False
            optional_probe["must_complete_before"] = []
            optional_probe["explicit_legacy_diagnostic"] = True
            optional_probe["expected_result"] = (
                "optional-rgba-route-diagnostic-only;never-block-source-reading-or-authoring"
            )
            actions.append(optional_probe)
            if isinstance(capabilities.get("migration_probe_finalization"), dict):
                actions.append(
                    {
                        "id": "finalize-migration-rgba-route-probe",
                        "action": "host-sign-and-atomically-consume-migration-probe",
                        "target": "host.migration.finalize",
                        "blocking": False,
                        "must_complete_before": "portable-signed-audit-only",
                        "bindings": {
                            "binding_nonce": binding_nonce,
                            "binding_digest": binding_digest,
                            "trusted_bundle_sha256": trusted_bundle_sha256,
                            "filesystem_policy_sha256": filesystem_policy_sha,
                        },
                        "receipt_contract": "runtime/migration-host-receipt-contract.json",
                        "replay_policy": "host-ledger-atomic-single-use-plus-local-create-once-consumption-record",
                        "profile-or-model-authored-receipt-can-satisfy": False,
                        "expected_result": "verified-final-report-with-phase-ready-true-and-reusable-scope-bound-continuation",
                    }
                )
            else:
                actions.append(
                    {
                        "id": "finalize-current-session-migration-probe",
                        "action": "verify-local-probe-chain-and-create-session-continuation",
                        "target": "scripts/runtime_preflight.py finalize-current-session-migration",
                        "blocking": False,
                        "must_complete_before": "legacy-probe-compatibility-only",
                        "bindings": {
                            "binding_nonce": binding_nonce,
                            "binding_digest": binding_digest,
                            "trusted_bundle_sha256": trusted_bundle_sha256,
                        },
                        "assurance": "current-session-observed-path-not-portable-signed",
                        "phase_ready_claim_allowed": False,
                        "expected_result": "current-session-operational-continuation-with-phase-ready-false",
                    }
                )
    return actions


def validate_runtime_profile(
    profile: dict[str, Any],
    workspace_root: Path,
    phase: str,
    *,
    session_root: Path | None = None,
    now: datetime | None = None,
    max_age_minutes: int = DEFAULT_PROBE_MAX_AGE_MINUTES,
    environment: dict[str, str] | None = None,
    binding_only: bool = False,
    challenge_nonce: str | None = None,
    installed_registry_override: dict[str, Any] | None = None,
    include_legacy_rgba_probe: bool = False,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"unsupported phase: {phase}")
    if max_age_minutes < 1 or max_age_minutes > DEFAULT_PROBE_MAX_AGE_MINUTES:
        raise ValueError(
            f"max probe age must be between 1 and {DEFAULT_PROBE_MAX_AGE_MINUTES} minutes"
        )
    workspace_root = workspace_root.resolve()
    migration_session_root = (
        _canonical_migration_session_root(session_root, workspace_root)
        if phase == "migration"
        else None
    )
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    env = dict(os.environ if environment is None else environment)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    _validate_no_secrets(profile, errors)
    if profile.get("schema_version") != SCHEMA_VERSION:
        _error(
            errors,
            "runtime.profile.schema_version_invalid",
            "profile.schema_version",
            f"schema_version must be {SCHEMA_VERSION}",
        )
    if profile.get("kind") != PROFILE_KIND:
        _error(
            errors,
            "runtime.profile.kind_invalid",
            "profile.kind",
            f"kind must be {PROFILE_KIND}",
        )
    local = _validate_local_paths(workspace_root, errors)
    python = _validate_python(
        workspace_root,
        errors,
        external_write_root=migration_session_root,
    )
    harness, adapter_capabilities = _validate_harness_adapter(profile, workspace_root, errors)
    installed_registry = _validate_registry_census(
        profile,
        workspace_root,
        errors,
        override=installed_registry_override,
    )
    skills = _validate_skills(
        profile,
        workspace_root,
        phase,
        errors,
        installed_registry,
    )
    tools = _tool_map(profile, adapter_capabilities, errors, installed_registry)
    links, safe_links = _validate_links(
        profile,
        phase,
        errors,
        now=current_time,
        max_age_minutes=max_age_minutes,
        binding_only=binding_only,
    )
    capabilities = _validate_capabilities(
        profile,
        phase,
        tools,
        links,
        safe_links,
        adapter_capabilities,
        installed_registry,
        errors,
        warnings,
        now=current_time,
        max_age_minutes=max_age_minutes,
        environment=env,
        binding_only=binding_only,
    )
    used_tool_ids = {
        tool_id
        for capability in capabilities.values()
        if isinstance(capability, dict)
        for field in ("tool_ids", "download_ingest_tool_ids")
        for tool_id in capability.get(field, [])
        if isinstance(tool_id, str)
    }
    for unused_tool_id in sorted(set(tools) - used_tool_ids):
        _error(
            errors,
            "runtime.tools.unbound",
            f"profile.tools.{unused_tool_id}",
            "every declared tool must be used by a capability required in the selected phase",
        )

    binding_ready = not errors
    if not binding_only:
        _error(
            errors,
            "runtime.probe.unattested",
            "profile",
            (
                "profile probe fields are untrusted declarations; phase readiness requires a current "
                "host-side tool trace or a host-signed adapter receipt"
            ),
        )
    nonce = challenge_nonce or secrets.token_urlsafe(32)
    if not BINDING_NONCE.fullmatch(nonce):
        raise ValueError(
            "binding challenge nonce must contain 32-128 URL-safe letters, digits, underscore, or hyphen"
        )
    binding_digest = _binding_digest(
        profile,
        phase,
        safe_links,
        str(local.get("trusted_bundle_sha256", "missing")),
    )

    registry_publication = installed_registry.get("publication_routes")
    if not isinstance(registry_publication, dict):
        registry_publication = {}
    registry_draft = registry_publication.get("draft")
    registry_current = registry_publication.get("current_session_publish")
    registry_readback = registry_publication.get("current_session_readback")
    registry_portable = registry_publication.get("portable_signed_publish")
    registry_draft = registry_draft if isinstance(registry_draft, dict) else {}
    registry_current = registry_current if isinstance(registry_current, dict) else {}
    registry_readback = (
        registry_readback if isinstance(registry_readback, dict) else {}
    )
    registry_portable = (
        registry_portable if isinstance(registry_portable, dict) else {}
    )
    installed_tools = installed_registry.get("tools")
    installed_tools = installed_tools if isinstance(installed_tools, dict) else {}

    def _registry_route_available(container: dict[str, Any], name: str) -> bool:
        route = container.get(name)
        return isinstance(route, dict) and route.get("available") is True

    wechat_binding = capabilities.get("wechat_delivery")
    selected_wechat_mode = (
        wechat_binding.get("mode") if isinstance(wechat_binding, dict) else None
    )
    selected_terminal_state = (
        wechat_binding.get("terminal_state", "draft")
        if isinstance(wechat_binding, dict)
        else None
    )
    draft_api_available = _registry_route_available(registry_draft, "api") or any(
        item.get("kind") == "wechat.draft"
        for item in installed_tools.values()
        if isinstance(item, dict)
    )
    draft_ui_available = _registry_route_available(registry_draft, "ui") or any(
        item.get("kind") in {"browser.control", "computer.use"}
        for item in installed_tools.values()
        if isinstance(item, dict)
    )
    current_api_publish_available = (
        _registry_route_available(registry_current, "api")
        and "wechat_publication_authority" in capabilities
    ) or "wechat_publication_authority" in capabilities
    current_ui_publish_available = _registry_route_available(
        registry_current, "ui"
    ) or draft_ui_available
    current_session_readback_available = bool(
        (
            registry_readback.get("available") is True
            or any(
                item.get("kind") == "wechat.current-session-readback"
                for item in installed_tools.values()
                if isinstance(item, dict)
            )
        )
        and "wechat_current_session_readback" in capabilities
    )
    portable_publish_available = (
        registry_portable.get("available") is True
        and "host_receipt_attestation" in capabilities
    ) or "host_receipt_attestation" in capabilities
    if selected_terminal_state == "draft":
        selected_route = f"draft.{selected_wechat_mode}"
        selected_publication_ready = bool(
            selected_wechat_mode == "api" and draft_api_available
            or selected_wechat_mode == "ui" and draft_ui_available
        )
    elif selected_terminal_state == "publish" and selected_wechat_mode == "api":
        selected_route = "current_session_publish.api"
        selected_publication_ready = (
            current_api_publish_available or portable_publish_available
        )
    elif selected_terminal_state == "publish" and selected_wechat_mode == "ui":
        selected_route = "current_session_publish.ui"
        selected_publication_ready = current_ui_publish_available
    else:
        selected_route = None
        selected_publication_ready = False
    publication_routes = {
        "target": {
            "terminal_state": selected_terminal_state,
            "mode": selected_wechat_mode,
        },
        "draft": {
            "api": {
                "available": draft_api_available,
                "implies_publication_authority": False,
            },
            "ui": {"available": draft_ui_available},
        },
        "current_session_publish": {
            "api": {
                "available": current_api_publish_available,
                "independent_capability": "wechat.current-session-authority",
                "inferred_from_wechat_draft": False,
            },
            "ui": {
                "available": current_ui_publish_available,
                "requires_fresh_confirmation_and_authoritative_readback": True,
            },
        },
        "current_session_readback": {
            "available": current_session_readback_available,
            "selected": "wechat_current_session_readback" in capabilities,
            "assurance": "current-session-only-nonportable",
            "implies_publication_authority": False,
        },
        "portable_signed_publish": {
            "available": portable_publish_available,
            "independent_capability": "host.receipt.attest",
        },
        "selected": {
            "route": selected_route,
            "binding_ready": bool(selected_publication_ready and binding_ready),
        },
    }
    provider_authority_route = adapter_capabilities.get(
        "image.provider.acquire.authority"
    )
    provider_authority_selected = "provider_acquisition_authority" in capabilities
    provider_receipt_route = adapter_capabilities.get("host.receipt.attest")
    provider_receipt_requires = (
        provider_receipt_route.get("requires")
        if isinstance(provider_receipt_route, dict)
        else None
    )
    portable_provider_signer_available = bool(
        isinstance(provider_receipt_route, dict)
        and provider_receipt_route.get("availability") != "unavailable"
        and isinstance(provider_receipt_requires, list)
        and provider_receipt_requires
        and all(
            tool_id in installed_tools
            and isinstance(installed_tools[tool_id], dict)
            and installed_tools[tool_id].get("kind") == "host.receipt.attest"
            for tool_id in provider_receipt_requires
        )
    )
    provider_acquisition_assurance = (
        {
            "required_for_formal_micro_assets": True,
            "current_session": {
                "binding_available": True,
                "authority_mode": "current-session-operator-harness-trusted",
                "assurance": "operator-harness-trusted-current-session",
                "operational_ready": False,
                "host_attested": False,
                "portable": False,
                "required_asset_gates": [
                    "current-session-runtime-binding",
                    "canonical-provider-request",
                    "create-once-download-ingestion",
                    "exact-raw-byte-binding",
                    "rgba8-alpha-pixel-validation",
                ],
                "policy_hook": {
                    "capability": "image.provider.acquire.authority",
                    "binding_available": provider_authority_selected,
                    "adapter_status": (
                    "unavailable"
                    if not isinstance(provider_authority_route, dict)
                    or provider_authority_route.get("availability") == "unavailable"
                    else "available"
                    ),
                    "can_veto": True,
                    "can_upgrade_assurance": False,
                },
            },
            "portable": {
                "authority_mode": "portable-signed",
                "receipt_kind": "org-wechat-provider-image-host-receipt-v1",
                "host_capability": "host.receipt.attest",
                "binding_available": portable_provider_signer_available,
                "verified": False,
                "per_asset_verification_required": True,
                "file_json_can_satisfy": False,
            },
            "formal_micro_operational_ready": False,
            "reason": (
                "binding report only; every formal asset must later pass the complete "
                "current-session migration/request/ingestion/raw/RGBA chain, or the "
                "stronger protected portable double-signature route"
            ),
        }
        if phase in {"authoring", "full"} and "rgba_cutout_generation" in phase_capabilities(phase, profile)
        else {
            "required_for_formal_micro_assets": False,
            "reason": "selected phase does not create formal generated micro assets",
        }
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "phase": phase,
        "check_level": "binding" if binding_only else "unattested",
        "ok": not errors,
        "binding_ready": binding_ready,
        "phase_ready": False,
        "operational_ready": False,
        "binding_nonce": nonce if binding_only else None,
        "binding_digest": binding_digest,
        "registry_assurance": installed_registry.get("registry_assurance"),
        "publication_routes": publication_routes,
        "provider_acquisition_assurance": provider_acquisition_assurance,
        "host_attestation": (
            "selected-for-portable-signed-audit"
            if phase in {"delivery", "full"}
            and "host_receipt_attestation" in capabilities
            else "optional-portable-audit-upgrade"
            if phase in {"delivery", "full"}
            else "not_requested"
            if binding_only
            else "host-trace-required"
        ),
        "external_probe_required": list(phase_capabilities(phase, profile))
        + [
            name
            for name in OPTIONAL_PHASE_CAPABILITIES[phase]
            if name in capabilities
        ],
        "host_setup_actions": _build_host_setup_actions(
            profile,
            phase,
            safe_links,
            runtime_root=workspace_root,
            migration_session_root=migration_session_root,
            binding_nonce=nonce,
            binding_digest=binding_digest,
            trusted_bundle_sha256=str(local.get("trusted_bundle_sha256", "missing")),
            portable_provider_signer_available=portable_provider_signer_available,
            include_legacy_rgba_probe=include_legacy_rgba_probe,
        ),
        "migration_selftest": (
            {
                "required": False,
                "contract": MIGRATION_RGBA_PROBE_CONTRACT,
                "status": (
                    "legacy-diagnostic-requested"
                    if include_legacy_rgba_probe
                    else "not-requested"
                ),
                "reason": "rgba-migration-probe-is-explicit-diagnostics-only",
                "explicit_legacy_diagnostic_requested": include_legacy_rgba_probe,
                "portable_signed_upgrade": (
                    "optional"
                    if "migration_probe_finalization" in capabilities
                    else "unavailable-on-selected-adapter"
                    if (adapter_capabilities.get("host.migration.finalize") or {}).get("availability")
                    == "unavailable"
                    else "not-selected"
                ),
                "action_id": (
                    "run-migration-rgba-route-probe"
                    if include_legacy_rgba_probe
                    else None
                ),
                "action_emitted": include_legacy_rgba_probe,
                "before_source_material": False,
                "truth_columns": {
                    "local_pixel_chain_verified": "not-required",
                    "host_route_verified": "not-required-before-source-reading",
                },
                "article_asset_registration_allowed": False,
                "article_asset_registration_policy": (
                    "conditional-on-each-real-asset-passing-provider-acquisition-"
                    "raw-byte-derivation-and-final-quality-gates"
                ),
                "reusable_as_official_asset_proof": False,
            }
            if phase == "migration"
            else {"required": False, "reason": "selected-phase-is-not-migration"}
        ),
        "source_zero_assurance": {
            "mode": (
                "host-enforced-filesystem-lease"
                if "filesystem_access_lease" in capabilities
                else "verified-installed-release-package"
            ),
            "installed_release_verified": installed_registry.get("verified") is True,
            "forbidden_release_trees": [
                "examples",
                "experiments",
                "organizations",
                "output",
            ],
            "host_filesystem_isolation": (
                "selected"
                if "filesystem_access_lease" in capabilities
                else "unavailable-on-selected-adapter"
                if (adapter_capabilities.get("filesystem.access.lease") or {}).get("availability")
                == "unavailable"
                else "not-selected"
            ),
            "claim_host_isolation_without_lease": False,
        },
        "delivery_assurance": (
            {
                "mode": (
                    "portable-signed-audit"
                    if "host_receipt_attestation" in capabilities
                    else "current-session-ui-live-publish"
                    if selected_terminal_state == "publish"
                    and selected_wechat_mode == "ui"
                    else "current-session-api-live-publish"
                    if selected_terminal_state == "publish"
                    and selected_wechat_mode == "api"
                    and "wechat_publication_authority" in capabilities
                    else "current-session-draft"
                ),
                "draft_write_may_proceed_after_current_host_read_write_probes": True,
                "target_terminal_state": selected_terminal_state,
                "selected_publication_route_binding_ready": bool(
                    selected_publication_ready and binding_ready
                ),
                "portable_receipt_verified": False,
                "host_receipt_absence_blocks_draft_write": False,
                "claim_portable_signed_audit_without_receipts": False,
            }
            if phase in {"delivery", "full"}
            else None
        ),
        "checked_at": current_time.isoformat(),
        "workspace_root_sha256": hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest(),
        "local": {
            **local,
            "installed_registry_verified": installed_registry.get("verified") is True,
            "installed_release_sha256": installed_registry.get("release_sha256"),
            "registry_digest": installed_registry.get("registry_digest"),
            "registry_census_sha256": installed_registry.get("census_sha256"),
        },
        "python": python,
        "resolved_harness": harness,
        "resolved_skills": skills,
        "resolved_tool_ids": sorted(tools),
        "resolved_links": safe_links,
        "resolved_capabilities": capabilities,
        "errors": errors,
        "warnings": warnings,
    }
    return _redact_report(report)


def _default_workspace_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _artifact_location_is_private(path: Path, workspace_root: Path) -> bool:
    """Allow external non-Git paths or paths their owning Git tree ignores.

    A sibling user project is not automatically private merely because it is
    outside the installed Skill root.  When the destination belongs to any Git
    worktree, that worktree must positively report the path as ignored.
    """

    absolute_path = _canonical_absolute_path(path)
    resolved_root = workspace_root.resolve()
    try:
        absolute_path.relative_to(resolved_root)
    except ValueError:
        inside_runtime_root = False
    else:
        inside_runtime_root = True
    probe_root = absolute_path if absolute_path.is_dir() else absolute_path.parent
    while not probe_root.exists() and probe_root != probe_root.parent:
        probe_root = probe_root.parent
    try:
        owner = subprocess.run(
            ["git", "-C", str(probe_root), "rev-parse", "--show-toplevel"],
            env=_clean_git_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if owner.returncode != 0:
        return not inside_runtime_root
    git_root_value = owner.stdout.strip()
    if not git_root_value:
        return False
    git_root = Path(git_root_value).resolve()
    try:
        relative = absolute_path.relative_to(git_root)
    except ValueError:
        return False
    try:
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", relative.as_posix()],
            cwd=git_root,
            env=_clean_git_environment(),
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return ignored.returncode == 0


def _canonical_migration_session_root(
    raw: Path | None, workspace_root: Path
) -> Path:
    """Require a real private session root outside the installed runtime."""

    if raw is None or not raw.expanduser().is_absolute():
        raise ValueError("migration requires an explicit absolute --session-root")
    session_root = _canonical_absolute_path(raw)
    if _has_any_symlink_component(session_root):
        raise ValueError("migration session root path must not contain symbolic links")
    try:
        session_root = session_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("migration session root must already exist") from exc
    if not session_root.is_dir():
        raise ValueError("migration session root must be a directory")
    runtime_root = workspace_root.resolve(strict=True)
    try:
        session_root.relative_to(runtime_root)
    except ValueError:
        pass
    else:
        raise ValueError("migration session root must be outside the installed runtime")
    if not _artifact_location_is_private(session_root, runtime_root):
        raise ValueError("migration session root must be outside Git or Git-ignored")
    return session_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path, help="current-session runtime profile JSON")
    parser.add_argument("--phase", choices=sorted(PHASES), default="full")
    parser.add_argument("--workspace-root", type=Path, default=_default_workspace_root())
    parser.add_argument(
        "--session-root",
        type=Path,
        help=(
            "existing absolute private artifact root outside the installed runtime; "
            "required for migration"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--max-probe-age-minutes",
        type=int,
        default=DEFAULT_PROBE_MAX_AGE_MINUTES,
    )
    parser.add_argument(
        "--binding-only",
        action="store_true",
        help="validate local files, safe links, skill hashes, and tool bindings without claiming live readiness",
    )
    parser.add_argument(
        "--include-legacy-rgba-probe",
        action="store_true",
        help=(
            "emit the retired synthetic RGBA route probe as an explicit non-blocking "
            "diagnostic; never required for source reading, authoring, or asset registration"
        ),
    )
    return parser


def build_finalize_migration_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and consume one host-signed migration probe receipt."
    )
    parser.add_argument("binding_report", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--workspace-root", type=Path, default=_default_workspace_root())
    parser.add_argument("--trust-store", type=Path, required=True)
    parser.add_argument("--consumption-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def build_census_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a verified host registry and installed-Skill census."
    )
    parser.add_argument("host_registry_export", type=Path)
    parser.add_argument("--phase", choices=sorted(PHASES), default="full")
    parser.add_argument("--workspace-root", type=Path, default=_default_workspace_root())
    parser.add_argument(
        "--adapter",
        type=Path,
        default=Path("runtime/adapters/codex-desktop.json"),
    )
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def build_init_session_census_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-attested current-session registry census from the "
            "model-visible tool identifier set and verified installed release."
        )
    )
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--visible-tool-id", action="append", default=[], dest="visible_tool_ids"
    )
    parser.add_argument("--workspace-root", type=Path, default=_default_workspace_root())
    parser.add_argument(
        "--adapter", type=Path, default=Path("runtime/adapters/codex-desktop.json")
    )
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def build_init_profile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a runtime profile from a verified census and compact target config."
    )
    parser.add_argument("census", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--workspace-root", type=Path, default=_default_workspace_root())
    parser.add_argument("--output", type=Path, required=True)
    return parser


def build_finalize_session_migration_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a migration probe for current-session operational use."
    )
    parser.add_argument("binding_report", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--workspace-root", type=Path, default=_default_workspace_root())
    parser.add_argument("--consumption-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _write_create_once_json(path: Path, value: dict[str, Any]) -> str:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(encoded)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _private_create_once_output(raw: Path, workspace_root: Path, label: str) -> Path:
    output = _canonical_absolute_path(raw)
    if output.is_symlink() or _has_any_symlink_component(output):
        raise SystemExit(f"{label} path must not contain symbolic links")
    if output.exists():
        raise SystemExit(f"{label} already exists; overwrite is forbidden: {output}")
    if not _artifact_location_is_private(output, workspace_root):
        raise SystemExit(f"{label} must be outside the workspace or Git-ignored: {output}")
    return output


def build_census_main(argv: list[str]) -> int:
    args = build_census_parser().parse_args(argv)
    workspace_root = _canonical_existing_input(args.workspace_root, "workspace root")
    output = _private_create_once_output(args.output, workspace_root, "census output")
    registry_path = _canonical_absolute_path(args.host_registry_export)
    if registry_path.is_symlink() or _has_any_symlink_component(registry_path):
        raise SystemExit("host registry export path must not contain symbolic links")
    adapter = args.adapter.expanduser()
    if not adapter.is_absolute():
        adapter = workspace_root / adapter
    manifest = args.release_manifest.expanduser()
    if not manifest.is_absolute():
        manifest = workspace_root / manifest
    try:
        raw_registry = _read_json(registry_path.resolve(strict=True))
        census = build_host_registry_census(
            raw_registry,
            workspace_root,
            adapter_path=adapter,
            skills_root=args.skills_root,
            release_manifest_path=manifest,
            phase=args.phase,
        )
        digest = _write_create_once_json(output, census)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "created": str(output),
                "registry_digest": census["registry_digest"],
                "file_sha256": digest,
                "tool_count": len(census["tools"]),
                "skill_count": len(census["skills"]),
                "phase_ready": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def init_current_session_census_main(argv: list[str]) -> int:
    args = build_init_session_census_parser().parse_args(argv)
    workspace_root = _canonical_existing_input(args.workspace_root, "workspace root")
    output = _private_create_once_output(args.output, workspace_root, "census output")
    adapter = args.adapter.expanduser()
    if not adapter.is_absolute():
        adapter = workspace_root / adapter
    manifest = args.release_manifest.expanduser()
    if not manifest.is_absolute():
        manifest = workspace_root / manifest
    try:
        census = build_current_session_registry_census(
            args.visible_tool_ids,
            workspace_root,
            phase=args.phase,
            session_id=args.session_id,
            adapter_path=adapter,
            skills_root=args.skills_root,
            release_manifest_path=manifest,
        )
        digest = _write_create_once_json(output, census)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "created": str(output),
                "registry_digest": census["registry_digest"],
                "file_sha256": digest,
                "assurance": "current-session-model-visible-intent",
                "host_attested_registry": False,
                "requires_later_live_probes": True,
                "tool_count": len(census["tools"]),
                "phase_ready": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def init_profile_main(argv: list[str]) -> int:
    args = build_init_profile_parser().parse_args(argv)
    workspace_root = _canonical_existing_input(args.workspace_root, "workspace root")
    output = _private_create_once_output(args.output, workspace_root, "profile output")
    census_path = _canonical_absolute_path(args.census)
    target_path = _canonical_absolute_path(args.target)
    for label, path in (("census", census_path), ("target", target_path)):
        if path.is_symlink() or _has_any_symlink_component(path):
            raise SystemExit(f"{label} path must not contain symbolic links")
    try:
        census = _read_json(census_path.resolve(strict=True))
        target = _read_json(target_path.resolve(strict=True))
        profile = build_runtime_profile_from_census(
            census,
            census_path,
            target,
            workspace_root,
            args.phase,
        )
        digest = _write_create_once_json(output, profile)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "created": str(output),
                "file_sha256": digest,
                "phase": args.phase,
                "generated_from_registry": True,
                "phase_ready": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def finalize_current_session_migration_main(argv: list[str]) -> int:
    args = build_finalize_session_migration_parser().parse_args(argv)
    workspace_root = _canonical_existing_input(args.workspace_root, "workspace root")
    output = _private_create_once_output(args.output, workspace_root, "session report")
    consumption = _private_create_once_output(
        args.consumption_record, workspace_root, "session consumption record"
    )
    binding_path = _canonical_absolute_path(args.binding_report)
    evidence_path = _canonical_absolute_path(args.evidence)
    for label, path in (("binding report", binding_path), ("evidence", evidence_path)):
        if path.is_symlink() or _has_any_symlink_component(path):
            raise SystemExit(f"{label} path must not contain symbolic links")
    try:
        binding = _read_json(binding_path.resolve(strict=True))
        evidence = _read_json(evidence_path.resolve(strict=True))
        binding_sha = _prefixed_file_sha256(binding_path.resolve(strict=True))
        finalized = finalize_current_session_migration(
            binding,
            evidence,
            workspace_root,
            source_binding_report_sha256=binding_sha,
        )
        final_bytes = (
            json.dumps(finalized, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        final_sha = "sha256:" + hashlib.sha256(final_bytes).hexdigest()
        consumption_payload = {
            "schema_version": 1,
            "kind": "org-wechat-migration-session-consumption-v1",
            "binding_nonce": binding.get("binding_nonce"),
            "binding_digest": binding.get("binding_digest"),
            "source_binding_report_sha256": binding_sha,
            "source_evidence_sha256": _prefixed_file_sha256(
                evidence_path.resolve(strict=True)
            ),
            "final_report_sha256": final_sha,
            "consumed_at": datetime.now(timezone.utc).isoformat(),
            "local_create_once_only": True,
            "host_atomic_replay_ledger": False,
            "portable_signed_audit": False,
        }
        _write_create_once_json(consumption, consumption_payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle:
            handle.write(final_bytes)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "created": str(output),
                "consumption_record": str(consumption),
                "operational_ready": True,
                "phase_ready": False,
                "assurance": "current-session-observed-path-not-portable-signed",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def finalize_migration_main(argv: list[str]) -> int:
    args = build_finalize_migration_parser().parse_args(argv)
    workspace_root = _canonical_existing_input(args.workspace_root, "workspace root")
    paths = {
        "binding report": _canonical_absolute_path(args.binding_report),
        "receipt": _canonical_absolute_path(args.receipt),
        "consumption record": _canonical_absolute_path(args.consumption_record),
        "output": _canonical_absolute_path(args.output),
    }
    for label, path in paths.items():
        if path.is_symlink() or _has_any_symlink_component(path):
            raise SystemExit(f"{label} path must not contain symbolic links")
    for label in ("consumption record", "output"):
        path = paths[label]
        if path.exists():
            raise SystemExit(f"{label} already exists; receipt replay/overwrite is forbidden: {path}")
        if not _artifact_location_is_private(path, workspace_root):
            raise SystemExit(f"{label} must be outside the workspace or Git-ignored: {path}")
    try:
        binding_report = _read_json(paths["binding report"].resolve(strict=True))
        receipt = _read_json(paths["receipt"].resolve(strict=True))
        source_sha = _prefixed_file_sha256(paths["binding report"].resolve(strict=True))
        trusted_keys = _load_migration_trust_store(args.trust_store, workspace_root)
        finalized = finalize_migration_binding_report(
            binding_report,
            receipt,
            workspace_root,
            source_binding_report_sha256=source_sha,
            trusted_public_keys=trusted_keys,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    final_bytes = (json.dumps(finalized, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    final_sha = "sha256:" + hashlib.sha256(final_bytes).hexdigest()
    consumption = {
        "schema_version": 1,
        "kind": MIGRATION_CONSUMPTION_KIND,
        "receipt_id": receipt.get("receipt_id"),
        "binding_nonce": binding_report.get("binding_nonce"),
        "binding_digest": binding_report.get("binding_digest"),
        "host_ledger_id": (receipt.get("replay_protection") or {}).get("host_ledger_id"),
        "source_binding_report_sha256": source_sha,
        "final_report_sha256": final_sha,
        "consumed_at": datetime.now(timezone.utc).isoformat(),
        "local_record_is_defense_in_depth": True,
        "host_atomic_nonce_consumption_required": True,
    }
    try:
        _write_create_once_json(paths["consumption record"], consumption)
        paths["output"].parent.mkdir(parents=True, exist_ok=True)
        with paths["output"].open("xb") as handle:
            handle.write(final_bytes)
    except OSError as exc:
        raise SystemExit(f"cannot write create-once migration finalization artifacts: {exc}") from exc
    print(
        json.dumps(
            {
                "created": str(paths["output"]),
                "consumption_record": str(paths["consumption record"]),
                "phase_ready": True,
                "receipt_id": receipt.get("receipt_id"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "init-current-session-census":
        return init_current_session_census_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "build-census":
        return build_census_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in {"init-profile", "build-profile"}:
        return init_profile_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "finalize-current-session-migration":
        return finalize_current_session_migration_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "finalize-migration":
        return finalize_migration_main(sys.argv[2:])
    args = build_parser().parse_args()
    if not 1 <= args.max_probe_age_minutes <= DEFAULT_PROBE_MAX_AGE_MINUTES:
        raise SystemExit(
            f"--max-probe-age-minutes must be between 1 and {DEFAULT_PROBE_MAX_AGE_MINUTES}"
        )
    workspace_root = _canonical_existing_input(args.workspace_root, "workspace root")
    raw_profile_path = _canonical_absolute_path(args.profile)
    raw_output = _canonical_absolute_path(args.output)
    if (
        raw_profile_path.is_symlink()
        or raw_output.is_symlink()
        or _has_any_symlink_component(raw_profile_path)
        or _has_any_symlink_component(raw_output)
    ):
        raise SystemExit("profile and output must not be symbolic links")
    if raw_output.exists():
        raise SystemExit(f"output already exists; choose a new report path: {raw_output}")
    profile_path = raw_profile_path.resolve()
    output = raw_output.resolve()
    for label, artifact in (("profile", profile_path), ("output", output)):
        if not _artifact_location_is_private(artifact, workspace_root):
            raise SystemExit(
                f"{label} must be outside the workspace or in a Git-ignored path: {artifact}"
            )
    try:
        profile = _read_json(profile_path)
        report = validate_runtime_profile(
            profile,
            workspace_root,
            args.phase,
            session_root=args.session_root,
            max_age_minutes=args.max_probe_age_minutes,
            binding_only=args.binding_only,
            include_legacy_rgba_probe=args.include_legacy_rgba_probe,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "created": str(output),
                "ok": report["ok"],
                "phase": report["phase"],
                "check_level": report["check_level"],
                "binding_ready": report["binding_ready"],
                "phase_ready": report["phase_ready"],
                "error_count": len(report["errors"]),
                "warning_count": len(report["warnings"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
