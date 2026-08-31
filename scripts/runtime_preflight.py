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
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/runtime_preflight.py")


PROFILE_KIND = "org-wechat-runtime-profile"
REPORT_KIND = "org-wechat-runtime-preflight-report"
SCHEMA_VERSION = 1
PHASES = {"bootstrap", "authoring", "delivery", "full"}
DEFAULT_PROBE_MAX_AGE_MINUTES = 60

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
    "runtime/setup-links.json",
    "runtime/adapters/codex-desktop.json",
    "runtime/python-dependency-lock.json",
    "style-presets/prismatic-paper-editorial.json",
    "scripts/orgs.py",
    "scripts/secure_runner.py",
    "scripts/secure_runtime.py",
    "scripts/asset_quality.py",
    "scripts/workflow_quality.py",
    "scripts/build_visual_directions.py",
    "scripts/build_storyboard.py",
    "scripts/build_visual_kit.py",
    "scripts/inspect_asset.py",
    "scripts/build_ardot_manifest.py",
    "scripts/build_visual_review.py",
    "scripts/compile_wechat.py",
    "scripts/transport_fidelity.py",
    "scripts/validate_transport_fidelity.py",
    "scripts/provenance_watermark.py",
    "scripts/wechat_interaction_policy.py",
    "scripts/validate_workflow_attribution.py",
    "skills/ardot-wechat-publisher/SKILL.md",
    "skills/ardot-wechat-publisher/agents/openai.yaml",
    "skills/ardot-wechat-publisher/references/handoff-contract.md",
    "skills/ardot-wechat-publisher/references/wechat-api-delivery.md",
    "skills/ardot-wechat-publisher/references/wechat-interaction-capability.md",
)

LINK_SCAN_FILES = (
    "SKILL.md",
    "README.md",
    "references/使用说明.md",
    "references/organization-pack-migration.md",
    "references/ardot-workflow.md",
    "skills/ardot-wechat-publisher/SKILL.md",
)

EXPECTED_SETUP_LINKS = {
    "ardot_mcp": "https://ardot.tencent.com/mcp",
    "ardot_web": "https://ardot.tencent.com/",
    "wechat_web": "https://mp.weixin.qq.com/",
    "wechat_api": "https://api.weixin.qq.com/",
}

EXPECTED_SEMANTIC_CAPABILITIES = (
    "image.generate",
    "image.inspect",
    "ardot.create",
    "ardot.read",
    "ardot.write",
    "ardot.export",
    "browser.control",
    "computer.use",
    "wechat.draft",
    "host.receipt.attest",
    "secret.resolve",
)

REQUIRED_SKILLS = {
    "org-wechat-studio": "SKILL.md",
    "ardot-wechat-publisher": "skills/ardot-wechat-publisher/SKILL.md",
}

PHASE_LOADED_SKILL = {
    "bootstrap": "org-wechat-studio",
    "authoring": "org-wechat-studio",
    "delivery": "ardot-wechat-publisher",
    "full": "org-wechat-studio",
}

PHASE_CAPABILITIES = {
    "bootstrap": (
        "image_generation",
        "visual_inspection",
        "ardot_bootstrap",
        "secret_store",
    ),
    "authoring": (
        "image_generation",
        "visual_inspection",
        "ardot_authoring",
        "secret_store",
    ),
    "delivery": (
        "visual_inspection",
        "ardot_authoring",
        "wechat_delivery",
        "host_receipt_attestation",
        "secret_store",
    ),
    "full": (
        "image_generation",
        "visual_inspection",
        "ardot_authoring",
        "wechat_delivery",
        "host_receipt_attestation",
        "secret_store",
    ),
}

CAPABILITY_MODES = {
    "image_generation": {"tool"},
    "visual_inspection": {"tool"},
    "ardot_bootstrap": {"mcp", "ui"},
    "ardot_authoring": {"mcp", "ui"},
    "wechat_delivery": {"api", "ui"},
    "host_receipt_attestation": {"host"},
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

TRUSTED_BUNDLE_PATHS = (
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
    "style-presets/prismatic-paper-editorial.json",
    "scripts/runtime_preflight.py",
    "scripts/secure_runner.py",
    "scripts/secure_runtime.py",
    "scripts/asset_quality.py",
    "scripts/build_visual_directions.py",
    "scripts/build_storyboard.py",
    "scripts/build_visual_kit.py",
    "scripts/inspect_asset.py",
    "scripts/build_ardot_manifest.py",
    "scripts/build_visual_review.py",
    "scripts/compile_wechat.py",
    "scripts/orgs.py",
    "scripts/provenance_watermark.py",
    "scripts/transport_fidelity.py",
    "scripts/validate_transport_fidelity.py",
    "scripts/validate_workflow_attribution.py",
    "scripts/wechat_interaction_policy.py",
    "scripts/workflow_quality.py",
    "skills/ardot-wechat-publisher/SKILL.md",
    "skills/ardot-wechat-publisher/agents/openai.yaml",
    "skills/ardot-wechat-publisher/references/handoff-contract.md",
    "skills/ardot-wechat-publisher/references/wechat-api-delivery.md",
    "skills/ardot-wechat-publisher/references/wechat-interaction-capability.md",
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
    publisher_root = workspace_root / "skills" / "ardot-wechat-publisher"
    scan_files.update(
        path.relative_to(workspace_root).as_posix()
        for path in publisher_root.rglob("*.md")
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
        if setup_links.get("schema_version") != 1 or setup_links.get("kind") != "org-wechat-setup-links":
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.setup_links_schema_invalid",
                "runtime/setup-links.json",
                "setup link registry schema/kind is invalid",
            )
        if setup_links.get("startup_policy") != {
            "open_after_binding": True,
            "prepare_before_source_material": True,
            "wait_for_user_login": True,
            "reprobe_after_login": True,
            "persist_session_query": False,
        }:
            setup_links_status = "failed"
            _error(
                errors,
                "runtime.local.startup_policy_invalid",
                "runtime/setup-links.json.startup_policy",
                "startup policy must open safe targets early, wait for login, and never persist session queries",
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
        for link_id, expected_path in (
            ("authoring_skill", "SKILL.md"),
            ("publisher_skill", "skills/ardot-wechat-publisher/SKILL.md"),
            ("runtime_contract", "references/runtime-preflight.md"),
            ("secure_runner", "scripts/secure_runner.py"),
            ("python_dependency_lock", "runtime/python-dependency-lock.json"),
            ("codex_adapter", "runtime/adapters/codex-desktop.json"),
            ("usage", "references/使用说明.md"),
            ("qa", "references/qa.md"),
        ):
            item = local.get(link_id)
            actual_path = item.get("path") if isinstance(item, dict) else None
            if actual_path != expected_path or not (workspace_root / expected_path).is_file():
                setup_links_status = "failed"
                _error(
                    errors,
                    "runtime.local.setup_link_missing",
                    f"runtime/setup-links.json.local.{link_id}",
                    f"local setup link must resolve to {expected_path}",
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
            adapter.get("schema_version") != 1
            or adapter.get("kind") != "org-wechat-runtime-adapter"
            or adapter.get("harness") != "codex-desktop"
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

    agent_error_count = len(errors)
    _validate_agent_mcp_contract(workspace_root, "agents/openai.yaml", errors)
    _validate_agent_mcp_contract(
        workspace_root,
        "skills/ardot-wechat-publisher/agents/openai.yaml",
        errors,
    )
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


def _validate_python(workspace_root: Path, errors: list[dict[str, str]]) -> dict[str, Any]:
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

    write_probe = "passed"
    try:
        with tempfile.TemporaryDirectory(prefix=".runtime-preflight-", dir=workspace_root) as directory:
            marker = Path(directory) / "probe.txt"
            marker.write_text("runtime-preflight\n", encoding="utf-8")
            if marker.read_text(encoding="utf-8") != "runtime-preflight\n":
                raise OSError("workspace readback mismatch")
    except OSError as exc:
        write_probe = "failed"
        _error(
            errors,
            "runtime.local.workspace_not_writable",
            "workspace_root",
            f"workspace write/read probe failed: {exc}",
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
        "workspace_write_read": write_probe,
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
        adapter.get("schema_version") != 1
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
        if item.get("source") not in {"runtime-registry", "skill-registry"}:
            _error(
                errors,
                "runtime.tools.source_invalid",
                f"{path}.source",
                "tool route must come from the current runtime or skill registry",
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


def _validate_skills(
    profile: dict[str, Any],
    workspace_root: Path,
    phase: str,
    errors: list[dict[str, str]],
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
            entrypoint_path = (workspace_root / entrypoint).resolve()
            try:
                entrypoint_path.relative_to(workspace_root)
            except ValueError:
                _error(
                    errors,
                    "runtime.skills.entrypoint_outside_workspace",
                    f"{path}.entrypoint",
                    "skill entrypoint must stay inside the workspace",
                )
            declared_sha = item.get("sha256")
            if not isinstance(declared_sha, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", declared_sha):
                _error(
                    errors,
                    "runtime.skills.sha256_invalid",
                    f"{path}.sha256",
                    "skill sha256 must be sha256:<64 lowercase hex>",
                )
            elif entrypoint_path.is_file():
                actual_sha = f"sha256:{_sha256(entrypoint_path)}"
                if declared_sha != actual_sha:
                    _error(
                        errors,
                        "runtime.skills.sha256_mismatch",
                        f"{path}.sha256",
                        "loaded skill hash does not match the current project entrypoint",
                    )
            resolved[skill_id] = {
                "entrypoint": entrypoint,
                "sha256": str(declared_sha),
                "status": str(item.get("status")),
            }
    for skill_id, expected in REQUIRED_SKILLS.items():
        if resolved.get(skill_id, {}).get("entrypoint") != expected:
            _error(
                errors,
                "runtime.skills.required_missing",
                f"profile.skills.{skill_id}",
                f"required skill must resolve to {expected}",
            )
    loaded_skill = PHASE_LOADED_SKILL[phase]
    if resolved.get(loaded_skill, {}).get("status") != "loaded":
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


def _validate_capabilities(
    profile: dict[str, Any],
    phase: str,
    tool_map: dict[str, dict[str, Any]],
    links: dict[str, dict[str, Any]],
    safe_links: dict[str, str],
    adapter_capabilities: dict[str, Any],
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
    required = PHASE_CAPABILITIES[phase]
    for name in required:
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
            accepted_statuses = {"passed"}
            if name == "image_generation":
                accepted_statuses.add("bound_unprobed")
            if status not in accepted_statuses:
                _error(
                    errors,
                    "runtime.capability.not_passed",
                    f"{path}.status",
                    f"capability status must be one of {sorted(accepted_statuses)}",
                )
            elif status == "bound_unprobed":
                _warning(
                    warnings,
                    "runtime.capability.imagegen_live_probe_deferred",
                    f"{path}.status",
                    "image generation is bound but unprobed; the first real generation is a blocking live probe",
                )

        if name == "image_generation":
            tool_ids = _require_tool_kinds(
                item.get("tool_ids"),
                f"{path}.tool_ids",
                tool_map,
                errors,
                ({"image.generate"},),
            )
            _require_adapter_routes(
                ("image.generate",), tool_ids, adapter_capabilities, errors, f"{path}.tool_ids"
            )
            probe_methods = {"runtime-registry", "read-only-live"}
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
                    "selected harness has no real host receipt signer; delivery/full must remain blocked",
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
        resolved[name] = {"mode": mode, "tool_ids": tool_ids}

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
        "tool_ids",
        "workspace_link",
        "expected_file_id",
        "expected_root_id",
        "account_link",
        "target_account_ref",
        "secret_refs",
        "path_refs",
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
        "skills": sorted(skill_intent, key=lambda item: str(item.get("id"))),
        "tools": sorted(tool_intent, key=lambda item: str(item.get("id"))),
        "links": dict(sorted(safe_links.items())),
        "capabilities": dict(sorted(capability_intent.items())),
    }
    encoded = json.dumps(intent, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _build_host_setup_actions(
    profile: dict[str, Any],
    phase: str,
    safe_links: dict[str, str],
) -> list[dict[str, Any]]:
    """Return credential-free actions the host must prepare before authoring."""

    actions: list[dict[str, Any]] = [
        {
            "id": "load-phase-skill",
            "action": "load-skill",
            "target": PHASE_LOADED_SKILL[phase],
            "blocking": True,
            "expected_result": "repository-resource-and-sha-match",
        }
    ]
    capabilities = profile.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
    ardot_capability_name = "ardot_bootstrap" if phase == "bootstrap" else "ardot_authoring"
    ardot_capability = capabilities.get(ardot_capability_name)
    ardot_mode = ardot_capability.get("mode") if isinstance(ardot_capability, dict) else None
    if ardot_mode == "mcp":
        actions.append(
            {
                "id": "connect-ardot-mcp",
                "action": "connect",
                "url": EXPECTED_SETUP_LINKS["ardot_mcp"],
                "blocking": True,
                "user_step_if_needed": "complete-ardot-oauth",
                "expected_result": "provider-session-callables-visible",
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
        actions.append(
            {
                "id": "open-ardot-target",
                "action": "open-or-read",
                "url": ardot_url,
                "blocking": True,
                "user_step_if_needed": "complete-ardot-web-login",
                "expected_result": ardot_result,
            }
        )
    if "wechat_delivery" in PHASE_CAPABILITIES[phase]:
        wechat = capabilities.get("wechat_delivery")
        wechat_mode = wechat.get("mode") if isinstance(wechat, dict) else None
        account_link = wechat.get("account_link") if isinstance(wechat, dict) else None
        account_url = safe_links.get(account_link) if isinstance(account_link, str) else None
        if wechat_mode == "api":
            actions.append(
                {
                    "id": "connect-wechat-api-provider",
                    "action": "connect-api-provider",
                    "url": account_url or EXPECTED_SETUP_LINKS["wechat_api"],
                    "blocking": True,
                    "user_step_if_needed": "authorize-wechat-api-provider",
                    "expected_result": "target-account-and-draft-api-access-visible",
                }
            )
        elif wechat_mode == "ui":
            actions.append(
                {
                    "id": "open-wechat-account",
                    "action": "open-or-read",
                    "url": account_url or EXPECTED_SETUP_LINKS["wechat_web"],
                    "blocking": True,
                    "user_step_if_needed": "scan-or-complete-wechat-login",
                    "expected_result": "target-account-and-draft-access-visible",
                }
            )
    if "host_receipt_attestation" in PHASE_CAPABILITIES[phase]:
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
    actions.extend(
        [
            {
                "id": "resolve-watermark-runtime",
                "action": "resolve-secret-references",
                "targets": [
                    "PROVENANCE_WATERMARK_KEY",
                    "PROVENANCE_WATERMARK_PRIVATE_ROOT",
                ],
                "blocking": True,
                "expected_result": "boolean-checks-only-no-values",
            },
            {
                "id": "bind-image-inspection",
                "action": "bind-callables",
                "targets": ["image.inspect"],
                "blocking": True,
                "expected_result": "inspection-callable-visible-neutral-read-required",
            },
        ]
    )
    if "image_generation" in PHASE_CAPABILITIES[phase]:
        actions.append(
            {
                "id": "bind-image-generation",
                "action": "bind-callables",
                "targets": ["image.generate"],
                "blocking": True,
                "expected_result": "callable-visible-first-real-asset-is-live-proof",
            }
        )
    return actions


def validate_runtime_profile(
    profile: dict[str, Any],
    workspace_root: Path,
    phase: str,
    *,
    now: datetime | None = None,
    max_age_minutes: int = DEFAULT_PROBE_MAX_AGE_MINUTES,
    environment: dict[str, str] | None = None,
    binding_only: bool = False,
    challenge_nonce: str | None = None,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"unsupported phase: {phase}")
    if max_age_minutes < 1 or max_age_minutes > DEFAULT_PROBE_MAX_AGE_MINUTES:
        raise ValueError(
            f"max probe age must be between 1 and {DEFAULT_PROBE_MAX_AGE_MINUTES} minutes"
        )
    workspace_root = workspace_root.resolve()
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
    python = _validate_python(workspace_root, errors)
    harness, adapter_capabilities = _validate_harness_adapter(profile, workspace_root, errors)
    skills = _validate_skills(profile, workspace_root, phase, errors)
    tools = _tool_map(profile, adapter_capabilities, errors)
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
        for tool_id in capability.get("tool_ids", [])
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

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "phase": phase,
        "check_level": "binding" if binding_only else "unattested",
        "ok": not errors,
        "binding_ready": binding_ready,
        "phase_ready": False,
        "binding_nonce": nonce if binding_only else None,
        "binding_digest": _binding_digest(
            profile,
            phase,
            safe_links,
            str(local.get("trusted_bundle_sha256", "missing")),
        ),
        "host_attestation": "not_requested" if binding_only else "required",
        "external_probe_required": list(PHASE_CAPABILITIES[phase]),
        "host_setup_actions": _build_host_setup_actions(profile, phase, safe_links),
        "checked_at": current_time.isoformat(),
        "workspace_root_sha256": hashlib.sha256(str(workspace_root).encode("utf-8")).hexdigest(),
        "local": local,
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
    """Allow artifacts outside the repo or in paths Git confirms are ignored."""

    resolved_path = path.resolve()
    resolved_root = workspace_root.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError:
        probe_root = resolved_path if resolved_path.is_dir() else resolved_path.parent
        while not probe_root.exists() and probe_root != probe_root.parent:
            probe_root = probe_root.parent
        try:
            completed = subprocess.run(
                ["git", "-C", str(probe_root), "rev-parse", "--git-dir"],
                env=_clean_git_environment(),
                check=False,
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode != 0
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", "--", relative.as_posix()],
            cwd=resolved_root,
            env=_clean_git_environment(),
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _has_workspace_symlink_component(path: Path, workspace_root: Path) -> bool:
    """Reject ignored-looking paths that escape the workspace through a nested symlink."""

    absolute_path = path.absolute()
    absolute_root = workspace_root.absolute()
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError:
        return False
    cursor = absolute_root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path, help="current-session runtime profile JSON")
    parser.add_argument("--phase", choices=sorted(PHASES), default="full")
    parser.add_argument("--workspace-root", type=Path, default=_default_workspace_root())
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.max_probe_age_minutes <= DEFAULT_PROBE_MAX_AGE_MINUTES:
        raise SystemExit(
            f"--max-probe-age-minutes must be between 1 and {DEFAULT_PROBE_MAX_AGE_MINUTES}"
        )
    workspace_root = args.workspace_root.expanduser().resolve()
    raw_profile_path = args.profile.expanduser().absolute()
    raw_output = args.output.expanduser().absolute()
    if (
        raw_profile_path.is_symlink()
        or raw_output.is_symlink()
        or _has_workspace_symlink_component(raw_profile_path, workspace_root)
        or _has_workspace_symlink_component(raw_output, workspace_root)
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
            max_age_minutes=args.max_probe_age_minutes,
            binding_only=args.binding_only,
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
