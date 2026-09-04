#!/usr/bin/env python3
"""Compile a frozen Ardot handoff for delivery or article JSON for authoring preview."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/compile_wechat.py")

from build_storyboard import build_storyboard_plan
from build_visual_kit import build_visual_kit_plan
from asset_quality import file_sha256
from wechat_interaction_policy import CurrentSessionMobileAuthority, audit_transport
from transport_fidelity import (
    CURRENT_ROOT_SOURCE,
    LIVE_RECEIPT_SOURCE,
    TRANSPORT_SOURCE,
    WECHAT_CONTENT_MAX_BYTES,
    WECHAT_CONTENT_MAX_CHARS,
    WECHAT_DIGEST_MAX_CHARS,
    WECHAT_AUTHOR_MAX_CHARS,
    WECHAT_TITLE_MAX_CHARS,
    asset_layer_contract,
    interaction_layer_contract,
    path_identity_sha256,
    resolve_local_asset,
    section_render_contract,
    text_layer_contract,
    transport_position_style as frozen_transport_position_style,
    _validate_transport_fidelity_contract,
    validate_wechat_upload_map,
    validate_transport_fidelity_diagnostic,
)
from asset_role_policy import validate_asset_role, validate_background_assignment
from pack_assets import PackAssetResolutionError, canonical_pack_root, resolve_pack_asset
try:
    from safe_paths import (
        SafePathError,
        existing_directory,
        existing_regular_file,
        new_directory_path,
    )
except ImportError:  # package import in repository tests
    from .safe_paths import (  # type: ignore
        SafePathError,
        existing_directory,
        existing_regular_file,
        new_directory_path,
    )
from validate_workflow_attribution import validate_workflow_attribution_handoff
from workflow_quality import (
    WORKFLOW_ATTRIBUTION_MARKER,
    WORKFLOW_ATTRIBUTION_TEXT,
    WORKFLOW_ATTRIBUTION_TEXT_SHA256,
    WATERMARK_SCHEME,
    asset_watermark_requirement,
    calibration_state,
    validate_asset_watermark,
    validate_interaction_plan,
    validate_production_preferences,
    validate_typography_plan,
    validate_visual_review,
    watermark_inventory,
    watermark_policy,
)


REMOTE_SRC = re.compile(r"^(?:https?://|data:)", re.I)
PLACEHOLDERS = re.compile(r"(?:待补充|待确认|待提供|PLACEHOLDER|\bTBD\b|\bTODO\b)", re.I)
UNSAFE_WECHAT = re.compile(
    r"<(?:script|style|iframe|form|link|details|summary|foreignObject|object|embed)\b",
    re.I,
)
SUPPORTED_BLOCKS = {
    "hero",
    "lead",
    "section",
    "text",
    "statement",
    "metrics",
    "timeline",
    "gallery",
    "case",
    "roles",
    "quote",
    "steps",
    "image",
    "cta",
    "references",
    "footer",
}
MICRO_TRANSPORT_WIDTHS = {
    "floating-spot": 0.34,
    "section-transition": 0.68,
    "inline-explainer": 0.46,
    "closing-motif": 0.38,
}
MICRO_TRANSPORT_ALIGNMENTS = {
    "floating-spot": "right",
    "section-transition": "left",
    "inline-explainer": "right",
    "closing-motif": "left",
}


def _write_text_create_once(path: Path, value: str) -> None:
    """Write one compiler-owned artifact without following or replacing paths."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        encoded = value.encode("utf-8")
        with os.fdopen(descriptor, "wb", closefd=True) as destination:
            descriptor = -1
            destination.write(encoded)
            destination.flush()
            os.fsync(destination.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc


def style(**values: Any) -> str:
    return ";".join(
        f"{key.replace('_', '-')}:{value}"
        for key, value in values.items()
        if value is not None and value != ""
    )


def paragraphs(items: list[Any], color: str) -> str:
    return "".join(
        f'<p style="margin:0 0 14px;line-height:1.82;font-size:16px;color:{color};letter-spacing:.015em;">{esc(item)}</p>'
        for item in items
    )


def _relative_luminance(color: str) -> float:
    """Return WCAG relative luminance for a #RRGGBB color."""
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        color = "#FFFFFF"

    def channel(value: int) -> float:
        normalized = value / 255.0
        return (
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def workflow_attribution_presentation(tokens: dict[str, str]) -> dict[str, Any]:
    """Choose a visible credit color even when organization tokens collide."""
    surface = tokens.get("surface", "#FFFFFF")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", surface):
        surface = "#FFFFFF"
    candidates = [tokens.get("body", "#4A4A4A"), "#111111", "#FFFFFF"]
    scored: list[tuple[float, str]] = []
    surface_luminance = _relative_luminance(surface)
    for candidate in candidates:
        if not isinstance(candidate, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", candidate):
            continue
        candidate_luminance = _relative_luminance(candidate)
        ratio = (max(surface_luminance, candidate_luminance) + 0.05) / (
            min(surface_luminance, candidate_luminance) + 0.05
        )
        scored.append((ratio, candidate.upper()))
    ratio, color = max(scored)
    return {
        "surface_color": surface.upper(),
        "text_color": color,
        "contrast_ratio": round(ratio, 3),
    }


def render_workflow_attribution(tokens: dict[str, str]) -> str:
    """Render the fixed, visible, terminal repository-usage credit."""
    presentation = workflow_attribution_presentation(tokens)
    return (
        f'<section data-workflow-attribution="{esc(WORKFLOW_ATTRIBUTION_MARKER)}" '
        f'data-workflow-attribution-contrast="{presentation["contrast_ratio"]}" '
        f'style="padding:18px 24px 26px;text-align:center;background:{presentation["surface_color"]};">'
        f'<span style="font-size:12px;line-height:1.7;color:{presentation["text_color"]};">'
        f'{esc(WORKFLOW_ATTRIBUTION_TEXT)}</span></section>'
    )


def slug_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned or "asset"


@dataclass
class CompileContext:
    spec_path: Path
    org_dir: Path
    output_dir: Path
    organization: dict[str, Any]
    sources_doc: dict[str, Any]
    components_doc: dict[str, Any]
    assets_doc: dict[str, Any]
    route: dict[str, Any]
    check: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    copied_assets: list[dict[str, Any]] = field(default_factory=list)
    watermark_checks: list[dict[str, Any]] = field(default_factory=list)
    watermark_checked_outputs: set[str] = field(default_factory=set)
    component_ids: list[str] = field(default_factory=list)
    used_source_ids: set[str] = field(default_factory=set)

    @property
    def tokens(self) -> dict[str, str]:
        return self.organization["visual"]["tokens"]

    @property
    def source_ids(self) -> set[str]:
        return {
            item["id"]
            for item in self.sources_doc.get("sources", [])
            if isinstance(item, dict) and item.get("id")
        }

    @property
    def registered_components(self) -> set[str]:
        return {
            item["id"]
            for item in self.components_doc.get("components", [])
            if isinstance(item, dict) and item.get("id")
        }

    def use_source(self, source_id: Any, label: str, required: bool = False) -> None:
        if not source_id:
            if required:
                self.errors.append(f"{label} requires source_id")
            return
        if source_id not in self.source_ids:
            self.errors.append(f"{label} references unknown source_id: {source_id}")
            return
        self.used_source_ids.add(str(source_id))

    def component(self, block: dict[str, Any]) -> str:
        block_type = block.get("type", "unknown")
        component_id = str(block.get("component", f"core.{block_type}"))
        self.component_ids.append(component_id)
        if component_id not in self.registered_components:
            self.warnings.append(f"unregistered component ID: {component_id}")
        return component_id

    def variant(self, block: dict[str, Any], block_type: str) -> str:
        explicit = block.get("variant")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        configured = self.route.get("component_variants", {}).get(block_type)
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        defaults = {
            "warm-community": {
                "hero": "soft-stage", "section": "soft-marker", "statement": "editorial-pullout",
                "roles": "role-bands", "steps": "journey-path", "cta": "launch-pad",
            },
            "technical": {
                "hero": "technical-stage", "section": "index-rail", "statement": "open-rule",
                "metrics": "number-field", "timeline": "mission-line", "case": "process-strip",
                "steps": "process-rail", "cta": "action-gate",
            },
            "poster": {
                "hero": "poster-stage", "section": "poster-band", "statement": "poster-callout",
                "metrics": "number-field", "timeline": "action-line", "cta": "poster-gate",
            },
            "institutional": {
                "hero": "quiet-editorial", "section": "editorial-head", "statement": "open-rule",
                "metrics": "ledger", "timeline": "report-line", "case": "evidence-ledger",
                "cta": "quiet-gate",
            },
            "editorial": {
                "hero": "image-stage", "section": "editorial-head", "statement": "editorial-pullout",
                "gallery": "photo-story", "cta": "action-gate",
            },
        }
        return defaults.get(self.route.get("layout", "editorial"), {}).get(block_type, "standard")

    def asset_src(self, source: Any, label: str) -> str:
        if not isinstance(source, str) or not source.strip():
            self.errors.append(f"{label} requires a non-empty image src")
            return ""
        registered = {
            item.get("id"): item
            for item in self.assets_doc.get("assets", [])
            if isinstance(item, dict) and item.get("id")
        }
        registered_asset = registered.get(source)
        if registered_asset is None:
            self.errors.append(
                f"{label} must reference an asset ID registered in this organization pack: {source}"
            )
            return source
        registered_location = registered_asset.get("location")
        try:
            candidate = resolve_pack_asset(
                self.org_dir,
                registered_location,
                label=f"registered asset {source} location",
            )
        except PackAssetResolutionError as exc:
            self.errors.append(str(exc))
            return source
        digest = hashlib.sha1(str(candidate).encode("utf-8")).hexdigest()[:10]
        target_name = f"{slug_part(candidate.stem)}-{digest}{candidate.suffix.lower()}"
        asset_dir = self.output_dir / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        target = asset_dir / target_name
        if not target.exists() or candidate.stat().st_mtime_ns > target.stat().st_mtime_ns:
            shutil.copy2(candidate, target)
        relative = f"assets/{target_name}"
        source_sha256 = file_sha256(candidate)
        output_sha256 = file_sha256(target)
        # The resolver has already proven this exact serialized location is a
        # canonical pack-relative path.
        public_source = str(registered_location)
        record = {
            "source": public_source,
            "output": relative,
            "source_sha256": source_sha256,
            "output_sha256": output_sha256,
        }
        if record not in self.copied_assets:
            self.copied_assets.append(record)
        if source_sha256 != output_sha256:
            self.errors.append(
                f"watermark.copy_hash_mismatch: copied asset bytes differ for {label}"
            )
        output_key = str(target.resolve())
        evidence = (
            registered_asset.get("watermark")
            if isinstance(registered_asset, dict)
            else None
        )
        policy = watermark_policy(self.organization)
        requirement = (
            asset_watermark_requirement(registered_asset, target)
            if isinstance(registered_asset, dict)
            else {"in_scope": False}
        )
        if (
            isinstance(registered_asset, dict)
            and output_key not in self.watermark_checked_outputs
            and (
                isinstance(evidence, dict)
                or (policy.get("mode") == "required" and requirement.get("in_scope"))
            )
        ):
            watermark_check = validate_asset_watermark(
                registered_asset,
                target,
                expected_scheme=str(policy.get("scheme") or WATERMARK_SCHEME),
                expected_key_id=(
                    str(policy.get("key_id"))
                    if isinstance(policy.get("key_id"), str)
                    else None
                ),
                pack_dir=self.org_dir,
                require_evidence=policy.get("mode") == "required",
            )
            watermark_check["asset_location"] = registered_asset.get("location")
            watermark_check["output"] = relative
            watermark_check["source_sha256"] = source_sha256
            watermark_check["output_sha256"] = output_sha256
            self.watermark_checks.append(watermark_check)
            self.watermark_checked_outputs.add(output_key)
            self.errors.extend(watermark_check["errors"])
        return relative

    def image_html(self, item: dict[str, Any], label: str, extra_style: str = "") -> str:
        src = self.asset_src(item.get("src"), label)
        alt = item.get("alt")
        if not isinstance(alt, str) or not alt.strip():
            self.errors.append(f"{label} requires useful alt text")
            alt = ""
        if item.get("source_id"):
            self.use_source(item.get("source_id"), label)
        return (
            f'<img src="{esc(src)}" alt="{esc(alt)}" '
            f'style="display:block;width:100%;height:100%;object-fit:cover;{extra_style}">'
        )


def route_shape(ctx: CompileContext) -> dict[str, str]:
    layout = ctx.route["layout"]
    if layout == "warm-community":
        return {"radius": "18px", "border_width": "1px", "shadow": "0 10px 28px rgba(0,0,0,.06)"}
    if layout == "editorial":
        return {"radius": "8px", "border_width": "1px", "shadow": "0 8px 24px rgba(0,0,0,.05)"}
    return {"radius": "0", "border_width": "2px", "shadow": "none"}


def render_micro_component(
    ctx: CompileContext,
    item: dict[str, Any],
    instance_index: int,
) -> str:
    """Render a text-free, partial-width static equivalent of one Ardot ornament."""
    role = str(item.get("role", ""))
    asset_id = item.get("id")
    width_ratio = MICRO_TRANSPORT_WIDTHS.get(role, 0.42)
    alignment = MICRO_TRANSPORT_ALIGNMENTS.get(role, "left")
    src = ctx.asset_src(asset_id, f"visual kit transport role {role}")
    concrete_subject = str(item.get("concrete_subject") or role)
    action = str(item.get("action") or "")
    alt = f"{concrete_subject}，{action}".strip("，")
    width_percent = round(width_ratio * 100)
    margin = "0 0 0 auto" if alignment == "right" else "0 auto 0 0"
    instance_id = item.get("_transport_instance_id") or f"transport-{instance_index}"
    return (
        f'<section data-visual-role="article-micro" data-micro-role="{esc(role)}" '
        f'data-micro-instance="{esc(instance_id)}" data-micro-copy="none" '
        f'style="padding:8px 24px 14px;background:transparent;">'
        f'<div data-micro-asset="{esc(asset_id)}" data-micro-width-ratio="{width_ratio:.2f}" '
        f'style="width:{width_percent}%;margin:{margin};">'
        f'<img src="{esc(src)}" alt="{esc(alt)}" '
        f'style="display:block;width:100%;height:auto;object-fit:contain;"></div></section>'
    )


def _transport_position_style(
    geometry: dict[str, Any],
    *,
    chapter_height: float,
    extra: str = "",
) -> str:
    """Map frozen 390 px Ardot geometry to a width-responsive layer."""
    return frozen_transport_position_style(
        geometry, chapter_height=chapter_height, extra=extra
    )


def _copy_frozen_transport_asset(
    manifest_path: Path,
    output_dir: Path,
    asset: dict[str, Any],
    copied: dict[str, str],
) -> str:
    """Copy the exact hash-bound handoff payload without re-encoding it."""
    asset_id = str(asset["asset_id"])
    if asset_id in copied:
        return copied[asset_id]
    source = resolve_local_asset(manifest_path, asset.get("path"))
    if source is None:
        raise ValueError(f"frozen transport asset is unavailable: {asset_id}")
    digest = str(asset["sha256"]).removeprefix("sha256:")
    suffix = source.suffix.lower() or ".bin"
    filename = f"{slug_part(asset_id)}-{digest[:12]}{suffix}"
    destination = output_dir / "assets" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if file_sha256(destination) != digest:
            raise ValueError(f"frozen transport destination hash collision: {asset_id}")
    else:
        shutil.copyfile(source, destination)
    relative = f"assets/{filename}"
    copied[asset_id] = relative
    return relative


def _render_frozen_text_node(
    node: dict[str, Any],
    *,
    chapter_height: float,
) -> str:
    contract = text_layer_contract(node, chapter_height=chapter_height)
    tag = str(node["tag"])
    return (
        f'<{tag} data-transport-text-node-id="{esc(node["node_id"])}" '
        f'data-transport-text-sha256="{esc(node["text_sha256"])}" '
        f'data-transport-semantic-role="{esc(node["semantic_role"])}" '
        f'data-transport-layer-kind="{contract["kind"]}" '
        f'data-transport-layer-id="{esc(contract["layer_id"])}" '
        f'data-transport-role="{esc(contract["role"])}" '
        f'data-transport-source-sha256="{esc(contract["source_sha256"])}" '
        f'data-transport-render-signature="{esc(contract["render_signature"])}" '
        f'style="{contract["style"]}">{esc(node["text"])}</{tag}>'
    )


def _render_frozen_asset_layer(
    manifest_path: Path,
    output_dir: Path,
    asset: dict[str, Any],
    copied: dict[str, str],
    *,
    chapter_height: float,
    role: str,
    cover: bool = False,
    upload_map: dict[str, Any] | None = None,
) -> str:
    if upload_map is None:
        source = _copy_frozen_transport_asset(manifest_path, output_dir, asset, copied)
    else:
        mapped = upload_map.get("_body_by_id", {}).get(str(asset.get("asset_id")))
        if not isinstance(mapped, dict) or not isinstance(mapped.get("hosted_url"), str):
            raise ValueError(
                f"target-account upload map is missing {asset.get('asset_id')}"
            )
        source = mapped["hosted_url"]
        copied[str(asset["asset_id"])] = source
    contract = asset_layer_contract(
        asset, chapter_height=chapter_height, role=role, cover=cover
    )
    return (
        f'<img src="{esc(source)}" data-transport-asset-id="{esc(asset["asset_id"])}" '
        f'data-transport-role="{esc(role)}" alt="{esc(asset.get("alt", ""))}" '
        f'data-transport-layer-kind="{contract["kind"]}" '
        f'data-transport-layer-id="{esc(contract["layer_id"])}" '
        f'data-transport-source-sha256="{esc(contract["source_sha256"])}" '
        f'data-transport-render-signature="{esc(contract["render_signature"])}" '
        f'style="{contract["style"]}">'
    )


def _wechat_asset_src(
    manifest_path: Path,
    output_dir: Path,
    asset: dict[str, Any],
    copied: dict[str, str],
    upload_map: dict[str, Any] | None,
) -> str:
    if upload_map is None:
        return _copy_frozen_transport_asset(
            manifest_path, output_dir, asset, copied
        )
    mapped = upload_map.get("_body_by_id", {}).get(str(asset.get("asset_id")))
    if not isinstance(mapped, dict) or not isinstance(mapped.get("hosted_url"), str):
        raise ValueError(
            f"target-account upload map is missing {asset.get('asset_id')}"
        )
    copied[str(asset["asset_id"])] = mapped["hosted_url"]
    return str(mapped["hosted_url"])


def _validate_wechat_article_limits(handoff: dict[str, Any], content: str) -> list[str]:
    article = handoff.get("article")
    if not isinstance(article, dict):
        return ["handoff article metadata is missing"]
    errors: list[str] = []
    title = article.get("title")
    digest = article.get("digest")
    author = article.get("author", "")
    if not isinstance(title, str) or not title.strip() or len(title) > WECHAT_TITLE_MAX_CHARS:
        errors.append(f"article title must contain 1-{WECHAT_TITLE_MAX_CHARS} characters")
    if not isinstance(digest, str) or len(digest) > WECHAT_DIGEST_MAX_CHARS:
        errors.append(f"article digest must contain at most {WECHAT_DIGEST_MAX_CHARS} characters")
    if not isinstance(author, str) or len(author) > WECHAT_AUTHOR_MAX_CHARS:
        errors.append(f"article author must contain at most {WECHAT_AUTHOR_MAX_CHARS} characters")
    if len(content) >= WECHAT_CONTENT_MAX_CHARS:
        errors.append(f"article HTML must contain fewer than {WECHAT_CONTENT_MAX_CHARS} characters")
    if len(content.encode("utf-8")) >= WECHAT_CONTENT_MAX_BYTES:
        errors.append(f"article HTML must contain fewer than {WECHAT_CONTENT_MAX_BYTES} UTF-8 bytes")
    return errors


_UPLOAD_TAG = re.compile(r"<(?:img|image)\b[^>]*>", re.I)
_UPLOAD_ID_ATTR = re.compile(
    r"\bdata-upload-asset-id\s*=\s*(['\"])([A-Za-z0-9._:-]{1,160})\1",
    re.I,
)


def _materialize_interaction_uploads(
    fragment: str,
    upload_map: dict[str, Any] | None,
) -> str:
    """Replace only explicit SHA-mapped interaction image placeholders.

    No unrestricted URL replacement is permitted.  Source fragments must bind
    each nested bitmap as both ``data-upload-asset-id=X`` and
    ``wechat-asset://X``; the final value comes from the validated account map.
    """

    if upload_map is None:
        return fragment

    def replace_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        marker = _UPLOAD_ID_ATTR.search(tag)
        if marker is None:
            return tag
        asset_id = marker.group(2)
        mapped = upload_map.get("_body_by_id", {}).get(asset_id)
        if not isinstance(mapped, dict):
            raise ValueError(
                f"interaction image {asset_id} is missing from the target-account upload map"
            )
        hosted_url = mapped.get("hosted_url")
        if not isinstance(hosted_url, str):
            raise ValueError(f"interaction image {asset_id} has no hosted URL")
        placeholder = f"wechat-asset://{asset_id}"
        attributes = list(
            re.finditer(r"\b(?:src|href|xlink:href)\s*=\s*(['\"])(.*?)\1", tag, re.I)
        )
        targets = [item for item in attributes if item.group(2) == placeholder]
        if len(targets) != 1:
            raise ValueError(
                f"interaction image {asset_id} must contain exactly one matching wechat-asset placeholder"
            )
        target = targets[0]
        return tag[: target.start(2)] + hosted_url + tag[target.end(2) :]

    return _UPLOAD_TAG.sub(replace_tag, fragment)


def _compile_frozen_transport_contract(
    manifest_path: Path,
    output_dir: Path,
    *,
    live_root_path: Path | None = None,
    live_receipt_path: Path | None = None,
    check: bool = True,
    finalization: bool,
    session_draft: bool = False,
    interaction_probe: bool = False,
    upload_map_path: Path | None = None,
    mobile_profile_path: Path | None = None,
    interaction_readback_path: Path | None = None,
    current_session_mobile_authority: CurrentSessionMobileAuthority | None = None,
) -> dict[str, Any]:
    """Compile a frozen layer export after the caller selects its trust scope."""
    if finalization and session_draft:
        raise ValueError("finalization and session_draft modes are mutually exclusive")
    if interaction_probe and not session_draft:
        raise ValueError("interaction_probe requires session_draft mode")
    if finalization or session_draft:
        # Keep the private engine fail-closed as well.  Importing this module
        # and calling a write-eligible implementation directly must not bypass
        # the public API's secure-runtime check.
        from secure_runtime import require_secure_runtime

        require_secure_runtime("scripts/compile_wechat.py")
    try:
        manifest_path = existing_regular_file(
            manifest_path, label="frozen handoff manifest"
        )
        output_dir = new_directory_path(
            output_dir,
            label="frozen compile output directory",
            forbidden_root=Path(__file__).resolve().parent.parent,
        )
    except SafePathError as exc:
        raise ValueError(str(exc)) from exc
    try:
        output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError as exc:
        raise ValueError(
            f"cannot create frozen compile output directory safely: {exc}"
        ) from exc
    artifact_path = output_dir / (
        "wechat.html" if finalization else "wechat-candidate.html"
    )
    dynamic_path = output_dir / (
        "wechat-dynamic.html" if finalization else "wechat-dynamic-candidate.html"
    )
    static_path = output_dir / (
        "wechat-static.html" if finalization else "wechat-static-candidate.html"
    )
    preview_path = output_dir / (
        "index.html" if finalization else "candidate-preview.html"
    )
    report_path = output_dir / (
        "compile-report.json" if finalization else "candidate-report.json"
    )
    owned_outputs: set[Path] = set()
    try:
        if finalization:
            preflight = _validate_transport_fidelity_contract(
                manifest_path,
                intended_html_path=artifact_path,
                live_root_path=live_root_path,
                live_receipt_path=live_receipt_path,
                require_live_root=True,
                upload_map_path=upload_map_path,
                require_upload_map=True,
                diagnostic=False,
            )
        else:
            preflight = validate_transport_fidelity_diagnostic(
                manifest_path,
                intended_html_path=artifact_path,
                live_root_path=live_root_path,
                live_receipt_path=live_receipt_path,
                require_live_root=True,
                upload_map_path=upload_map_path,
                require_upload_map=session_draft,
            )
    except ValueError as exc:
        preflight = {
            "ok": False,
            "source": TRANSPORT_SOURCE,
            "revision_hash": None,
            "error_codes": ["transport.mapping"],
            "errors": [{"code": "transport.mapping", "message": str(exc)}],
        }
    errors = list(preflight.get("errors", []))
    live_root_binding = None
    if preflight.get("ok") and live_root_path is not None:
        try:
            if live_root_path.is_symlink():
                raise ValueError("live-root export must not be a symlink")
            resolved_live_root = live_root_path.resolve(strict=True)
            live_root_payload = read_json(resolved_live_root)
            if live_root_payload.get("source") != CURRENT_ROOT_SOURCE:
                raise ValueError(
                    f"live-root export source must be {CURRENT_ROOT_SOURCE}"
                )
            live_root_stat = resolved_live_root.stat()
            live_root_binding = {
                "source": CURRENT_ROOT_SOURCE,
                "path": str(resolved_live_root),
                "path_identity_sha256": path_identity_sha256(resolved_live_root),
                "sha256": f"sha256:{file_sha256(resolved_live_root)}",
                "byte_length": live_root_stat.st_size,
                "device": live_root_stat.st_dev,
                "inode": live_root_stat.st_ino,
            }
        except (OSError, ValueError, TypeError) as exc:
            errors.append(
                {
                    "code": "transport.current_root_live",
                    "message": f"cannot bind the fresh live-root export: {exc}",
                }
            )
    live_receipt_binding = None
    if preflight.get("ok") and live_receipt_path is not None:
        try:
            resolved_receipt = live_receipt_path.resolve(strict=True)
            receipt_payload = read_json(resolved_receipt)
            live_receipt_binding = {
                "source": LIVE_RECEIPT_SOURCE,
                "path": str(resolved_receipt),
                "path_identity_sha256": path_identity_sha256(resolved_receipt),
                "sha256": f"sha256:{file_sha256(resolved_receipt)}",
                "key_id": receipt_payload.get("key_id"),
                "signature_algorithm": receipt_payload.get("signature_algorithm"),
                "runtime_binding_nonce": receipt_payload.get("runtime_binding_nonce"),
                "runtime_binding_digest": receipt_payload.get("runtime_binding_digest"),
                "trusted_bundle_sha256": receipt_payload.get("trusted_bundle_sha256"),
                "output_html_path_identity_sha256": receipt_payload.get(
                    "output_html_path_identity_sha256"
                ),
                "expires_at": receipt_payload.get("expires_at"),
            }
        except (OSError, ValueError, TypeError) as exc:
            errors.append(
                {
                    "code": "transport.current_root_receipt",
                    "message": f"cannot bind the verified live-root receipt: {exc}",
                }
            )
    try:
        attribution_preflight = validate_workflow_attribution_handoff(manifest_path)
    except ValueError as exc:
        attribution_preflight = {"ok": False, "errors": [str(exc)]}
    if not attribution_preflight.get("ok"):
        errors.extend(
            {"code": "transport.attribution", "message": str(message)}
            for message in attribution_preflight.get("errors", [])
        )
    copied: dict[str, str] = {}
    fragment = ""
    dynamic_fragment = ""
    static_fragment = ""
    selected_payload = "dynamic"
    fallback_fragments: list[str] = []
    if preflight.get("ok"):
        handoff = read_json(manifest_path)
        export = handoff["transport_fidelity"]["export"]
        upload_map: dict[str, Any] | None = None
        if upload_map_path is not None:
            try:
                upload_map = validate_wechat_upload_map(
                    upload_map_path,
                    manifest_path=manifest_path,
                    handoff=handoff,
                    export=export,
                )
            except (OSError, ValueError) as exc:
                errors.append({"code": "transport.upload_map", "message": str(exc)})
        rendered_dynamic_chapters: list[str] = []
        rendered_static_chapters: list[str] = []
        try:
            for chapter in export["chapters"]:
                chapter_height = float(chapter["geometry"]["height"])
                base_layers = [
                    _render_frozen_asset_layer(
                        manifest_path,
                        output_dir,
                        chapter["background_layer"],
                        copied,
                        chapter_height=chapter_height,
                        role="background",
                        cover=True,
                        upload_map=upload_map,
                    )
                ]
                base_layers.extend(
                    _render_frozen_asset_layer(
                        manifest_path,
                        output_dir,
                        item,
                        copied,
                        chapter_height=chapter_height,
                        role="article-micro",
                        upload_map=upload_map,
                    )
                    for item in chapter["decorations"]
                )
                base_layers.extend(
                    _render_frozen_asset_layer(
                        manifest_path,
                        output_dir,
                        item,
                        copied,
                        chapter_height=chapter_height,
                        role="documentary-evidence",
                        upload_map=upload_map,
                    )
                    for item in chapter["photos"]
                )
                base_layers.extend(
                    _render_frozen_text_node(item, chapter_height=chapter_height)
                    for item in chapter["visible_text_nodes"]
                )
                dynamic_layers = list(base_layers)
                static_layers = list(base_layers)
                interactions = chapter.get("interaction")
                interaction_items = interactions if isinstance(interactions, list) else [interactions]
                for item in interaction_items:
                    if not isinstance(item, dict):
                        continue
                    contract = interaction_layer_contract(
                        item, chapter_height=chapter_height
                    )
                    wrapper_style = contract["style"]
                    fallback = item["fallback_asset"]
                    fallback_src = _wechat_asset_src(
                        manifest_path,
                        output_dir,
                        fallback,
                        copied,
                        upload_map,
                    )
                    fallback_payload = (
                        f'<img src="{esc(fallback_src)}" '
                        f'data-transport-asset-id="{esc(fallback["asset_id"])}" '
                        'data-transport-role="interaction-fallback" alt="" '
                        'style="display:block;width:100%;height:100%;object-fit:contain;">'
                    )
                    dynamic_payload = fallback_payload
                    if item["mode"] == "svg":
                        svg_asset = item["svg"]
                        svg_path = resolve_local_asset(manifest_path, svg_asset["path"])
                        if svg_path is None:
                            raise ValueError(
                                f"frozen SVG is unavailable: {svg_asset['asset_id']}"
                            )
                        svg_text = svg_path.read_text(encoding="utf-8")
                        if not re.match(r"\s*<svg\b", svg_text):
                            raise ValueError(
                                f"frozen SVG root is invalid: {svg_asset['asset_id']}"
                            )
                        svg_text = _materialize_interaction_uploads(
                            svg_text, upload_map
                        )
                        dynamic_payload = re.sub(
                            r"<svg\b",
                            f'<svg data-transport-interaction-id="{esc(item["interaction_id"])}"',
                            svg_text,
                            count=1,
                        )
                        fallback_fragments.append(
                            f'<img src="{esc(fallback_src)}" '
                            f'data-fallback-key="{esc(item["fallback_key"])}" '
                            f'data-fallback-hash="{esc(item["fallback_semantic_sha256"])}" '
                            f'data-transport-asset-id="{esc(fallback["asset_id"])}" '
                            'alt="">'
                        )
                    elif item["mode"] == "horizontal-swipe":
                        swipe_asset = item.get("swipe")
                        swipe_path = resolve_local_asset(
                            manifest_path,
                            swipe_asset.get("path") if isinstance(swipe_asset, dict) else None,
                        )
                        if swipe_path is None:
                            raise ValueError(
                                f"frozen horizontal-swipe fragment is unavailable: {item.get('interaction_id')}"
                            )
                        dynamic_payload = _materialize_interaction_uploads(
                            swipe_path.read_text(encoding="utf-8"), upload_map
                        )
                        fallback_fragments.append(
                            f'<img src="{esc(fallback_src)}" '
                            f'data-fallback-key="{esc(item["fallback_key"])}" '
                            f'data-fallback-hash="{esc(item["fallback_semantic_sha256"])}" '
                            f'data-transport-asset-id="{esc(fallback["asset_id"])}" alt="">'
                        )
                    wrapper_prefix = (
                        f'<div data-transport-interaction-id="{esc(item["interaction_id"])}" '
                        f'data-transport-interaction-mode="{esc(item["mode"])}" '
                        f'data-transport-layer-kind="{contract["kind"]}" '
                        f'data-transport-layer-id="{esc(contract["layer_id"])}" '
                        f'data-transport-role="{esc(contract["role"])}" '
                        f'data-transport-source-sha256="{esc(contract["source_sha256"])}" '
                        f'data-transport-render-signature="{esc(contract["render_signature"])}" '
                        f'style="{wrapper_style}">'
                    )
                    dynamic_layers.append(wrapper_prefix + dynamic_payload + "</div>")
                    static_layers.append(wrapper_prefix + fallback_payload + "</div>")
                # The section aspect-ratio wrapper is itself frozen. A correct
                # child layer sequence inside a hidden/resized wrapper is not a
                # faithful transport.
                section_contract = section_render_contract(
                    chapter, revision_hash=export["revision_hash"]
                )
                section_prefix = (
                    f'<section data-transport-chapter-id="{esc(chapter["chapter_id"])}" '
                    f'data-ardot-section-node="{esc(chapter["section_node_id"])}" '
                    f'data-transport-revision="{esc(export["revision_hash"])}" '
                    f'data-transport-section-signature="{esc(section_contract["render_signature"])}" '
                    f'style="{section_contract["style"]}">'
                )
                rendered_dynamic_chapters.append(
                    section_prefix + "".join(dynamic_layers) + "</section>"
                )
                rendered_static_chapters.append(
                    section_prefix + "".join(static_layers) + "</section>"
                )
            root_prefix = (
                f'<div data-transport-source="{TRANSPORT_SOURCE}" '
                f'data-ardot-root-node="{esc(export["root_node_id"])}" '
            )
            dynamic_fragment = (
                root_prefix
                + 'data-transport-payload-variant="dynamic" '
                + 'style="width:100%;margin:0;padding:0;background:transparent;">'
                + "".join(rendered_dynamic_chapters)
                + "</div>"
            )
            static_fragment = (
                root_prefix
                + 'data-transport-payload-variant="static" '
                + 'style="width:100%;margin:0;padding:0;background:transparent;">'
                + "".join(rendered_static_chapters)
                + "</div>"
            )
        except (KeyError, OSError, UnicodeError, ValueError, TypeError) as exc:
            errors.append({"code": "transport.mapping", "message": str(exc)})
    if not errors:
        _write_text_create_once(dynamic_path, dynamic_fragment)
        owned_outputs.add(dynamic_path)
        _write_text_create_once(static_path, static_fragment)
        owned_outputs.add(static_path)
        mobile_profile = (
            read_json(mobile_profile_path) if mobile_profile_path is not None else None
        )
        interaction_readback = (
            interaction_readback_path.read_text(encoding="utf-8")
            if interaction_readback_path is not None
            else None
        )
        interaction_policy = audit_transport(
            dynamic_fragment,
            fallback_html="".join(fallback_fragments) if fallback_fragments else None,
            readback_html=interaction_readback,
            mobile_profile=mobile_profile,
            target_account_id=(
                upload_map.get("target_account_ref")
                if isinstance(upload_map, dict)
                else None
            ),
            allow_upload_placeholders=upload_map is None,
            mobile_profile_path=mobile_profile_path,
            current_session_mobile_authority=current_session_mobile_authority,
        )
        selected_payload = (
            "dynamic"
            if interaction_probe
            or (not finalization and not session_draft)
            or interaction_policy.get("recommended_payload") == "dynamic"
            else "static"
        )
        fragment = dynamic_fragment if selected_payload == "dynamic" else static_fragment
        _write_text_create_once(artifact_path, fragment)
        owned_outputs.add(artifact_path)
        if finalization:
            dynamic_postflight = _validate_transport_fidelity_contract(
                manifest_path,
                html_path=dynamic_path,
                upload_map_path=upload_map_path,
                require_upload_map=True,
                diagnostic=False,
            )
            static_postflight = _validate_transport_fidelity_contract(
                manifest_path,
                html_path=static_path,
                upload_map_path=upload_map_path,
                require_upload_map=True,
                diagnostic=False,
            )
        else:
            dynamic_postflight = validate_transport_fidelity_diagnostic(
                manifest_path,
                html_path=dynamic_path,
                upload_map_path=upload_map_path,
                require_upload_map=session_draft,
            )
            static_postflight = validate_transport_fidelity_diagnostic(
                manifest_path,
                html_path=static_path,
                upload_map_path=upload_map_path,
                require_upload_map=session_draft,
            )
        selected_postflight = (
            dynamic_postflight if selected_payload == "dynamic" else static_postflight
        )
        postflight = {
            "ok": bool(dynamic_postflight.get("ok") and static_postflight.get("ok")),
            "contract_ok": bool(
                dynamic_postflight.get("contract_ok")
                and static_postflight.get("contract_ok")
            ),
            "selected_payload": selected_payload,
            "selected": selected_postflight,
            "dynamic": dynamic_postflight,
            "static": static_postflight,
            "errors": list(dynamic_postflight.get("errors", []))
            + list(static_postflight.get("errors", [])),
        }
        errors.extend(postflight["errors"])
        errors.extend(
            {"code": "transport.interaction.policy", "message": message}
            for message in interaction_policy.get("errors", [])
        )
        errors.extend(
            {"code": "transport.wechat_limit", "message": message}
            for message in _validate_wechat_article_limits(handoff, fragment)
        )
    else:
        postflight = {"ok": False, "error_codes": []}
        interaction_policy = {"status": "not-checked", "errors": []}
    if errors:
        # Only remove artifacts created by this invocation inside its brand-new
        # mode-0700 output directory.  Pre-existing evidence can never reach
        # this branch because the directory itself is create-once.
        for owned in owned_outputs:
            try:
                owned.unlink()
            except FileNotFoundError:
                pass
    else:
        _write_text_create_once(
            preview_path,
            '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>*{box-sizing:border-box}body{margin:0;background:#ddd}main{width:min(390px,100%);margin:auto}</style>'
            f'</head><body><main>{fragment}</main></body></html>',
        )
        owned_outputs.add(preview_path)
    artifact_binding = None
    if not errors and artifact_path.is_file():
        artifact_stat = artifact_path.stat()
        artifact_binding = {
            "source": (
                "wechat-compiled-artifact-v1"
                if finalization
                else "wechat-session-draft-candidate-v1"
                if session_draft
                else "wechat-diagnostic-candidate-v1"
            ),
            "path": artifact_path.name,
            "sha256": f"sha256:{file_sha256(artifact_path)}",
            "byte_length": artifact_stat.st_size,
            "transport_revision_hash": preflight.get("revision_hash"),
            "path_identity_sha256": path_identity_sha256(artifact_path),
            "device": artifact_stat.st_dev,
            "inode": artifact_stat.st_ino,
        }
    interaction_evidence_binding = None
    if not errors and mobile_profile_path is not None:
        resolved_mobile_profile = mobile_profile_path.resolve(strict=True)
        resolved_interaction_readback = (
            interaction_readback_path.resolve(strict=True)
            if interaction_readback_path is not None
            else None
        )
        interaction_evidence_binding = {
            "mobile_profile": {
                "path": str(resolved_mobile_profile),
                "sha256": "sha256:" + file_sha256(resolved_mobile_profile),
            },
            "interaction_readback": (
                {
                    "path": str(resolved_interaction_readback),
                    "sha256": "sha256:" + file_sha256(resolved_interaction_readback),
                }
                if resolved_interaction_readback is not None
                else None
            ),
            "current_session_live_authority_used": (
                current_session_mobile_authority is not None
            ),
        }
    report = {
        "schema_version": 2,
        "ok": not errors,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "candidate_valid": not errors and not finalization,
        # An unsigned session report is a structural binding only.  The
        # current host may still choose to write the bound candidate while it
        # owns the live tool trace, but that action policy must not become a
        # portable eligibility claim in a model-writable JSON file.
        "draft_write_eligible": not errors and finalization,
        "delivery_eligible": False,
        "portable_audit_verified": False,
        "publication_preflight_eligible": False,
        "publication_authorized": False,
        "interaction_probe_only": bool(interaction_probe),
        "assurance_scope": (
            "portable-signed-draft-candidate"
            if finalization
            else "current-session-interaction-probe"
            if interaction_probe
            else "current-session-draft"
            if session_draft
            else "diagnostic-candidate"
        ),
        "finalization_verified": False,
        "source": TRANSPORT_SOURCE,
        "revision_hash": preflight.get("revision_hash"),
        "handoff_sha256": f"sha256:{file_sha256(manifest_path)}",
        "selected_payload": selected_payload if not errors else None,
        "upload_map_binding": (
            {
                "source": upload_map.get("source"),
                "target_account_ref": upload_map.get("target_account_ref"),
                "path": upload_map.get("_resolved_path"),
                "sha256": upload_map.get("_sha256"),
                "path_identity_sha256": path_identity_sha256(
                    Path(str(upload_map.get("_resolved_path")))
                ),
                "cover_media_id": upload_map.get("cover", {}).get("media_id"),
            }
            if not errors and isinstance(locals().get("upload_map"), dict)
            else None
        ),
        "artifact_binding": {
            "wechat_html": artifact_binding if finalization else None,
            "candidate_html": artifact_binding if not finalization else None,
            "live_root_export": live_root_binding,
            "live_root_receipt": live_receipt_binding,
        },
        "preflight": preflight,
        "attribution_preflight": attribution_preflight,
        "postflight": postflight,
        "interaction_policy": interaction_policy,
        "interaction_evidence_binding": interaction_evidence_binding,
        "copied_assets": copied,
        "error_codes": sorted({item.get("code", "transport.mapping") for item in errors}),
        "errors": errors,
        "outputs": {
            "wechat": artifact_path.name if not errors and finalization else None,
            "candidate": (
                artifact_path.name if not errors and not finalization else None
            ),
            "preview": preview_path.name if not errors else None,
            "dynamic": dynamic_path.name if not errors else None,
            "static": static_path.name if not errors else None,
            "selected_payload": selected_payload if not errors else None,
            "report": report_path.name,
        },
    }
    _write_text_create_once(
        report_path,
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    return report


def compile_frozen_transport_candidate(
    manifest_path: Path,
    output_dir: Path,
    *,
    live_root_path: Path | None = None,
    live_receipt_path: Path | None = None,
    check: bool = True,
    upload_map_path: Path | None = None,
    mobile_profile_path: Path | None = None,
    interaction_readback_path: Path | None = None,
    current_session_mobile_authority: CurrentSessionMobileAuthority | None = None,
) -> dict[str, Any]:
    """Build a diagnostic candidate that is never write-eligible.

    This ordinary-import API never creates ``wechat.html`` or
    ``compile-report.json`` and always returns ``draft_write_eligible=false``.
    Use :func:`compile_frozen_session_draft` through the isolated runner when
    the active publisher intends to write a WeChat draft.
    """
    return _compile_frozen_transport_contract(
        manifest_path,
        output_dir,
        live_root_path=live_root_path,
        live_receipt_path=live_receipt_path,
        check=check,
        finalization=False,
        session_draft=False,
        upload_map_path=upload_map_path,
        mobile_profile_path=mobile_profile_path,
        interaction_readback_path=interaction_readback_path,
        current_session_mobile_authority=current_session_mobile_authority,
    )


def compile_frozen_session_draft(
    manifest_path: Path,
    output_dir: Path,
    *,
    live_root_path: Path | None = None,
    live_receipt_path: Path | None = None,
    check: bool = True,
    upload_map_path: Path | None = None,
    mobile_profile_path: Path | None = None,
    interaction_readback_path: Path | None = None,
    current_session_mobile_authority: CurrentSessionMobileAuthority | None = None,
    interaction_probe: bool = False,
) -> dict[str, Any]:
    """Build a current-session structural candidate in the isolated runner.

    The active host may use this exact candidate for a reversible draft write
    while it owns the live tool trace.  The unsigned report deliberately never
    serializes that action policy as ``draft_write_eligible=true``.
    """
    return _compile_frozen_transport_contract(
        manifest_path,
        output_dir,
        live_root_path=live_root_path,
        live_receipt_path=live_receipt_path,
        check=check,
        finalization=False,
        session_draft=True,
        interaction_probe=interaction_probe,
        upload_map_path=upload_map_path,
        mobile_profile_path=mobile_profile_path,
        interaction_readback_path=interaction_readback_path,
        current_session_mobile_authority=current_session_mobile_authority,
    )


def compile_frozen_transport(
    manifest_path: Path,
    output_dir: Path,
    *,
    live_root_path: Path | None = None,
    live_receipt_path: Path | None = None,
    check: bool = True,
    upload_map_path: Path | None = None,
    mobile_profile_path: Path | None = None,
    interaction_readback_path: Path | None = None,
    current_session_mobile_authority: CurrentSessionMobileAuthority | None = None,
    interaction_probe: bool = False,
) -> dict[str, Any]:
    """Compile final ``wechat.html`` only inside the isolated runner."""
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/compile_wechat.py")
    return _compile_frozen_transport_contract(
        manifest_path,
        output_dir,
        live_root_path=live_root_path,
        live_receipt_path=live_receipt_path,
        check=check,
        finalization=True,
        session_draft=False,
        interaction_probe=interaction_probe,
        upload_map_path=upload_map_path,
        mobile_profile_path=mobile_profile_path,
        interaction_readback_path=interaction_readback_path,
        current_session_mobile_authority=current_session_mobile_authority,
    )


def hero(ctx: CompileContext, block: dict[str, Any], component: str) -> str:
    t = ctx.tokens
    layout = ctx.route["layout"]
    variant = ctx.variant(block, "hero")
    background = block.get("background")
    background_style = ""
    if background:
        src = ctx.asset_src(background, "hero background")
        if not block.get("background_alt"):
            ctx.errors.append("hero background requires background_alt")
        background_style = style(
            background_image=f"url('{esc(src)}')",
            background_size="cover",
            background_position="center",
        )
    dark_stage = layout in {"poster", "technical"}
    section_bg = t["ink"] if dark_stage else t["surface_alt"]
    panel_bg = t["ink"] if dark_stage else t["surface"]
    title_color = t.get("on_accent", t["white"]) if dark_stage else t["ink"]
    body_color = t.get("on_accent", t["white"]) if dark_stage else t["body"]
    accent = t["accent_alt"] if dark_stage else t["accent"]
    if background:
        panel_bg = "rgba(10,13,18,.88)" if dark_stage else "rgba(255,255,255,.91)"
    cta = ""
    if block.get("cta"):
        cta = f'<div style="display:inline-block;margin-top:18px;padding:9px 13px;background:{accent};color:{t.get("on_accent_alt", t["ink"])};font-size:13px;font-weight:800;">{esc(block["cta"])}</div>'
    panel_width = "88%" if layout in {"editorial", "warm-community"} else "100%"
    panel_margin = "0 0 0 auto" if layout == "editorial" else "0"
    panel_border = f"border-left:7px solid {accent};" if layout in {"technical", "institutional"} else f"border-top:7px solid {accent};"
    return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" aria-label="{esc(block.get("background_alt", ""))}" style="min-height:560px;padding:26px;background:{section_bg};{background_style}display:flex;align-items:flex-end;">
<div style="width:{panel_width};margin:{panel_margin};padding:25px 23px;background:{panel_bg};{panel_border}">
<div style="font-size:10px;font-weight:900;letter-spacing:.14em;color:{accent};">{esc(block.get("eyebrow", ctx.organization["identity"]["short_name"]))}</div>
<h1 style="margin:13px 0 0;font-size:40px;line-height:1.12;letter-spacing:-.04em;color:{title_color};font-weight:900;">{esc(block["title"])}</h1>
<p style="margin:15px 0 0;max-width:28em;font-size:16px;line-height:1.72;color:{body_color};font-weight:650;">{esc(block.get("subtitle", ""))}</p>{cta}
</div></section>'''


def render_block(ctx: CompileContext, block: dict[str, Any], index: int) -> str:
    kind = block.get("type")
    if kind not in SUPPORTED_BLOCKS:
        ctx.errors.append(f"block {index} has unsupported type: {kind}")
        return ""
    component = ctx.component(block)
    variant = ctx.variant(block, str(kind))
    t = ctx.tokens
    shape = route_shape(ctx)

    if kind == "hero":
        return hero(ctx, block, component)

    if kind in {"lead", "text"}:
        items = block.get("paragraphs")
        if not isinstance(items, list) or not items:
            ctx.errors.append(f"block {index} ({kind}) requires paragraphs")
            items = []
        if kind == "lead":
            rendered_paragraphs = "".join(
                f'<p style="margin:0 0 {18 if item_index == 0 else 13}px;font-size:{19 if item_index == 0 else 15}px;line-height:{1.72 if item_index == 0 else 1.82};font-weight:{750 if item_index == 0 else 450};color:{t["ink"] if item_index == 0 else t["body"]};">{esc(item)}</p>'
                for item_index, item in enumerate(items)
            )
            return f'<section data-component="{esc(component)}" data-variant="lead-open" style="padding:38px 28px 31px;background:{t["surface"]};border-bottom:1px solid {t["border"]};">{rendered_paragraphs}</section>'
        return f'<section data-component="{esc(component)}" data-variant="text-open" style="padding:24px 28px 34px;background:{t["surface"]};">{paragraphs(items, t["body"])}</section>'

    if kind == "section":
        number = block.get("number")
        badge = f'<div style="flex:0 0 62px;font-size:34px;line-height:1;font-weight:900;color:{t["accent"]};">{esc(number)}</div>' if number is not None else ""
        kicker = f'<div style="margin-bottom:6px;font-size:10px;font-weight:800;letter-spacing:.1em;color:{t["accent"]};">{esc(block["kicker"])}</div>' if block.get("kicker") else ""
        if variant == "poster-band":
            return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="padding:30px 25px;background:{t["accent"]};border-top:8px solid {t["accent_alt"]};">
<div style="font-size:11px;font-weight:900;letter-spacing:.12em;color:{t["accent_alt"]};">{esc(number if number is not None else block.get("kicker", ""))}</div><h2 style="margin:11px 0 0;font-size:29px;line-height:1.2;color:{t.get("on_accent", t["white"])};">{esc(block["title"])}</h2></section>'''
        if variant in {"index-rail", "editorial-head"}:
            return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="display:flex;gap:16px;padding:40px 26px 18px;background:{t["surface"]};border-top:3px solid {t["ink"]};">
{badge}<div style="flex:1;">{kicker}<h2 style="margin:0;font-size:27px;line-height:1.28;letter-spacing:-.02em;color:{t["ink"]};">{esc(block["title"])}</h2></div></section>'''
        return f'''<section data-component="{esc(component)}" style="display:flex;gap:12px;padding:34px 24px 14px;background:{t["surface"]};border-top:{shape["border_width"]} solid {t["border"]};">
{badge}<div style="flex:1;">{kicker}<h2 style="margin:0;font-size:25px;line-height:1.35;color:{t["ink"]};">{esc(block["title"])}</h2></div></section>'''

    if kind == "statement":
        body = f'<p style="margin:13px 0 0;font-size:14px;line-height:1.75;color:{t["body"]};">{esc(block["body"])}</p>' if block.get("body") else ""
        if variant in {"open-rule", "editorial-pullout"}:
            align = "right" if variant == "editorial-pullout" else "left"
            inset = "42px 25px 46px 58px" if variant == "editorial-pullout" else "35px 28px"
            return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="padding:{inset};background:{t["surface_alt"]};text-align:{align};border-left:9px solid {t["accent"]};">
<div style="font-size:10px;font-weight:900;letter-spacing:.14em;color:{t["accent"]};">{esc(block.get("label", "KEY MESSAGE"))}</div>
<h3 style="margin:12px 0 0;font-size:27px;line-height:1.38;letter-spacing:-.02em;color:{t["ink"]};">{esc(block["title"])}</h3>{body}</section>'''
        if variant == "poster-callout":
            return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="padding:34px 26px;background:{t["ink"]};border-bottom:10px solid {t["accent_alt"]};">
<div style="font-size:10px;font-weight:900;letter-spacing:.14em;color:{t["accent_alt"]};">{esc(block.get("label", "KEY MESSAGE"))}</div><h3 style="margin:12px 0 0;font-size:29px;line-height:1.3;color:{t["white"]};">{esc(block["title"])}</h3></section>'''
        return f'''<section data-component="{esc(component)}" style="padding:22px 24px;background:{t["surface_alt"]};">
<div style="padding:20px;background:{t["surface"]};border:{shape["border_width"]} solid {t["border"]};border-radius:{shape["radius"]};box-shadow:{shape["shadow"]};">
<div style="font-size:10px;font-weight:800;letter-spacing:.1em;color:{t["accent"]};">{esc(block.get("label", "KEY MESSAGE"))}</div>
<h3 style="margin:10px 0 0;font-size:23px;line-height:1.45;color:{t["ink"]};">{esc(block["title"])}</h3>{body}</div></section>'''

    if kind == "metrics":
        items = block.get("items", [])
        if not isinstance(items, list) or not items:
            ctx.errors.append(f"block {index} (metrics) requires items")
            items = []
        cards = []
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                ctx.errors.append(f"metric {item_index} must be an object")
                continue
            ctx.use_source(item.get("source_id"), f"metric {item_index}", required=True)
            if variant in {"number-field", "ledger"}:
                cards.append(
                    f'<div style="display:inline-block;vertical-align:top;width:50%;min-height:132px;padding:21px 16px;background:{t["surface"]};border-top:2px solid {t["ink"]};">'
                    f'<div style="font-size:38px;line-height:1;font-weight:900;letter-spacing:-.04em;color:{t["accent"]};">{esc(item.get("value", ""))}</div>'
                    f'<div style="margin-top:12px;max-width:12em;font-size:12px;line-height:1.55;font-weight:750;color:{t["ink"]};">{esc(item.get("label", ""))}</div></div>'
                )
            else:
                cards.append(
                    f'<div style="display:inline-block;vertical-align:top;width:47%;min-height:114px;margin:0 1.5% 10px;padding:14px 12px;background:{t["surface_alt"]};border:{shape["border_width"]} solid {t["border"]};border-radius:{shape["radius"]};">'
                    f'<div style="font-size:28px;line-height:1.08;font-weight:900;color:{t["accent"]};">{esc(item.get("value", ""))}</div>'
                    f'<div style="margin-top:8px;font-size:12px;line-height:1.5;font-weight:700;color:{t["ink"]};">{esc(item.get("label", ""))}</div></div>'
                )
        padding = "24px 18px 32px" if variant not in {"number-field", "ledger"} else "18px 24px 36px"
        return f'<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="padding:{padding};background:{t["surface"]};">{"".join(cards)}</section>'

    if kind == "timeline":
        rows = []
        for item_index, item in enumerate(block.get("items", [])):
            if not isinstance(item, dict):
                ctx.errors.append(f"timeline item {item_index} must be an object")
                continue
            ctx.use_source(item.get("source_id"), f"timeline item {item_index}")
            rows.append(
                f'<div style="display:flex;gap:12px;margin-bottom:11px;"><div style="flex:0 0 76px;padding:8px;background:{t["accent_alt"]};color:{t.get("on_accent_alt", t["ink"])};font-size:12px;font-weight:900;">{esc(item.get("label", ""))}</div>'
                f'<div style="flex:1;padding:7px 0;font-size:14px;line-height:1.68;color:{t["body"]};">{esc(item.get("description", ""))}</div></div>'
            )
        return f'<section data-component="{esc(component)}" style="padding:22px 24px;background:{t["surface_alt"]};border-top:{shape["border_width"]} solid {t["border"]};border-bottom:{shape["border_width"]} solid {t["border"]};">{"".join(rows)}</section>'

    if kind == "gallery":
        slides = []
        for image_index, item in enumerate(block.get("images", [])):
            if not isinstance(item, dict):
                ctx.errors.append(f"gallery image {image_index} must be an object")
                continue
            image = ctx.image_html(item, f"gallery image {image_index}")
            slides.append(
                f'<div style="display:inline-block;vertical-align:top;width:84%;margin-right:10px;white-space:normal;">'
                f'<div style="height:220px;overflow:hidden;background:{t["surface_alt"]};border:{shape["border_width"]} solid {t["border"]};border-radius:{shape["radius"]};">{image}</div>'
                f'<div style="padding:8px 2px 0;font-size:12px;line-height:1.5;color:{t["body"]};">{esc(item.get("caption", ""))}</div></div>'
            )
        if not slides:
            ctx.errors.append(f"block {index} (gallery) requires images")
        return f'''<section data-component="{esc(component)}" style="padding:14px 0 24px 24px;background:{t["surface"]};">
<div style="margin:0 24px 7px 0;text-align:right;font-size:10px;color:{t["accent"]};font-weight:800;letter-spacing:.08em;">左右滑动 →</div>
<div style="overflow-x:auto;overflow-y:hidden;white-space:nowrap;-webkit-overflow-scrolling:touch;padding-bottom:5px;">{"".join(slides)}</div></section>'''

    if kind == "case":
        ctx.use_source(block.get("source_id"), f"case block {index}")
        rows = "".join(
            f'<div style="padding:13px 14px;border-top:{shape["border_width"]} solid {t["border"]};font-size:14px;line-height:1.7;color:{t["body"]};"><b style="color:{t["accent"]};">{label}</b>　{esc(block.get(key, ""))}</div>'
            for label, key in (("问题", "problem"), ("方法", "approach"), ("产出", "output"))
        )
        evidence = f'<div style="padding:12px 14px;border-top:{shape["border_width"]} solid {t["border"]};background:{t["accent_alt"]};font-size:13px;line-height:1.65;color:{t.get("on_accent_alt", t["ink"])};"><b>证据</b>　{esc(block["evidence"])}</div>' if block.get("evidence") else ""
        return f'<section data-component="{esc(component)}" style="margin:16px 24px;background:{t["surface"]};border:{shape["border_width"]} solid {t["border"]};border-radius:{shape["radius"]};overflow:hidden;"><h3 style="margin:0;padding:15px 14px;background:{t["accent"]};color:{t.get("on_accent", t["white"])};font-size:20px;">{esc(block["name"])}</h3>{rows}{evidence}</section>'

    if kind == "roles":
        cards = []
        for item in block.get("items", []):
            cards.append(
                f'<div style="margin-bottom:10px;padding:15px 14px;background:{t["surface_alt"]};border-left:5px solid {t["accent"]};border-radius:{shape["radius"]};">'
                f'<div style="font-size:17px;font-weight:900;color:{t["ink"]};">{esc(item.get("name", ""))}</div>'
                f'<div style="margin-top:6px;font-size:13px;line-height:1.68;color:{t["body"]};">{esc(item.get("description", ""))}</div></div>'
            )
        return f'<section data-component="{esc(component)}" style="padding:12px 24px 24px;background:{t["surface"]};">{"".join(cards)}</section>'

    if kind == "quote":
        ctx.use_source(block.get("source_id"), f"quote block {index}", required=True)
        if not block.get("attribution"):
            ctx.errors.append(f"quote block {index} requires attribution")
        return f'''<section data-component="{esc(component)}" style="padding:30px 26px;background:{t["accent"]};color:{t.get("on_accent", t["white"])};">
<div style="font-size:34px;line-height:1;color:{t["accent_alt"]};">“</div><blockquote style="margin:2px 0 0;font-size:21px;line-height:1.65;font-weight:800;">{esc(block.get("text", ""))}</blockquote>
<div style="margin-top:12px;font-size:12px;opacity:.82;">— {esc(block.get("attribution", ""))}</div></section>'''

    if kind == "steps":
        rows = []
        for item_index, item in enumerate(block.get("items", []), 1):
            if isinstance(item, str):
                title, description = item, ""
            else:
                title, description = item.get("title", ""), item.get("description", "")
            desc = f'<div style="margin-top:4px;font-size:13px;line-height:1.6;color:{t["body"]};">{esc(description)}</div>' if description else ""
            rows.append(
                f'<div style="display:flex;gap:12px;margin-bottom:10px;"><div style="flex:0 0 32px;height:32px;background:{t["accent_alt"]};color:{t.get("on_accent_alt", t["ink"])};text-align:center;line-height:32px;font-weight:900;">{item_index:02d}</div>'
                f'<div style="flex:1;padding:5px 0;font-size:15px;font-weight:800;color:{t["ink"]};">{esc(title)}{desc}</div></div>'
            )
        return f'<section data-component="{esc(component)}" style="padding:20px 24px;background:{t["surface"]};">{"".join(rows)}</section>'

    if kind == "image":
        image = ctx.image_html(block, f"image block {index}")
        caption = f'<div style="padding:8px 2px 0;font-size:12px;line-height:1.5;color:{t["body"]};">{esc(block["caption"])}</div>' if block.get("caption") else ""
        return f'<section data-component="{esc(component)}" style="padding:16px 24px;background:{t["surface"]};"><div style="height:260px;overflow:hidden;border-radius:{shape["radius"]};">{image}</div>{caption}</section>'

    if kind == "cta":
        steps = "".join(
            f'<div style="margin-bottom:8px;font-size:14px;line-height:1.65;color:{t.get("on_accent", t["white"])};"><b style="color:{t["accent_alt"]};">{item_index:02d}</b>　{esc(item)}</div>'
            for item_index, item in enumerate(block.get("steps", []), 1)
        )
        body = f'<p style="margin:10px 0 15px;font-size:14px;line-height:1.75;color:{t.get("on_accent", t["white"])};">{esc(block["body"])}</p>' if block.get("body") else ""
        button = f'<div style="display:inline-block;margin-top:10px;padding:9px 13px;background:{t["accent_alt"]};color:{t.get("on_accent_alt", t["ink"])};font-size:13px;font-weight:900;">{esc(block["button"])}</div>' if block.get("button") else ""
        qr_html = ""
        if block.get("qr"):
            qr = block["qr"]
            if qr.get("origin") not in {"user-supplied", "official"}:
                ctx.errors.append(f"cta block {index} QR origin must be user-supplied or official")
            qr_html = f'<div style="width:150px;margin:18px auto 0;padding:8px;background:{t["white"]};">{ctx.image_html(qr, f"cta QR {index}", "object-fit:contain;")}</div>'
        return f'<section data-component="{esc(component)}" style="padding:26px 24px;background:{t["accent"]};"><h2 style="margin:0;font-size:25px;line-height:1.4;color:{t.get("on_accent", t["white"])};">{esc(block["title"])}</h2>{body}{steps}{button}{qr_html}</section>'

    if kind == "references":
        items = []
        for item_index, item in enumerate(block.get("items", [])):
            ctx.use_source(item.get("source_id"), f"reference {item_index}", required=True)
            items.append(f'<li style="margin:0 0 7px;line-height:1.6;">{esc(item.get("label", item.get("source_id", "")))}</li>')
        return f'<section data-component="{esc(component)}" style="padding:22px 26px;background:{t["surface_alt"]};font-size:12px;color:{t["body"]};"><div style="margin-bottom:9px;font-weight:900;color:{t["ink"]};">来源与说明</div><ol style="margin:0;padding-left:18px;">{"".join(items)}</ol></section>'

    if kind == "footer":
        logo_html = ""
        if block.get("logo"):
            logo = block["logo"]
            if isinstance(logo, str):
                logo_item = {"src": logo, "alt": f'{ctx.organization["identity"]["name"]} logo'}
            else:
                logo_item = logo
            logo_html = f'<div style="width:64px;height:64px;margin:0 auto 12px;">{ctx.image_html(logo_item, "footer logo", "object-fit:contain;")}</div>'
        return f'<section data-component="{esc(component)}" style="padding:32px 24px;text-align:center;background:{t["surface"]};border-top:{shape["border_width"]} solid {t["border"]};">{logo_html}<div style="font-size:17px;font-weight:900;color:{t["ink"]};">{esc(block.get("name", ctx.organization["identity"]["name"]))}</div><div style="margin-top:7px;font-size:12px;line-height:1.6;color:{t["body"]};">{esc(block.get("tagline", ""))}</div><div style="margin-top:12px;font-size:10px;color:{t["body"]};opacity:.72;">{esc(block.get("credits", ""))}</div></section>'

    raise AssertionError(f"unhandled block type: {kind}")


def load_context(spec_path: Path, org_dir: Path, output_dir: Path, check: bool) -> tuple[CompileContext, dict[str, Any]]:
    spec_path = spec_path.resolve()
    org_dir = canonical_pack_root(org_dir)
    spec = read_json(spec_path)
    organization = read_json(org_dir / "organization.json")
    sources_doc = read_json(org_dir / "sources.json")
    components_doc = read_json(org_dir / "components.json")
    assets_doc = read_json(org_dir / "assets.json")

    errors: list[str] = []
    if spec.get("schema_version") != 1:
        errors.append("article.schema_version must be 1")
    if spec.get("organization_id") != organization.get("id"):
        errors.append("article.organization_id must match organization pack")
    article_type = spec.get("article_type")
    article_types = organization.get("article_types", {})
    if article_type not in article_types:
        errors.append(f"unknown article_type: {article_type}")
        article_config = {}
    else:
        article_config = article_types[article_type]
    route_id = spec.get("route") or article_config.get("route") or organization.get("visual", {}).get("default_route")
    route_map = {item["id"]: item for item in organization.get("visual", {}).get("routes", [])}
    route = route_map.get(route_id)
    if route is None:
        errors.append(f"unknown route: {route_id}")
        route = {"id": str(route_id), "label": str(route_id), "layout": "editorial", "dominant_style": "unknown"}

    output_dir.mkdir(parents=True, exist_ok=True)
    ctx = CompileContext(
        spec_path=spec_path,
        org_dir=org_dir,
        output_dir=output_dir.resolve(),
        organization=organization,
        sources_doc=sources_doc,
        components_doc=components_doc,
        assets_doc=assets_doc,
        route=route,
        check=check,
        errors=errors,
    )
    return ctx, spec


def compile_article(spec_path: Path, org_dir: Path, output_dir: Path, check: bool) -> dict[str, Any]:
    ctx, spec = load_context(spec_path, org_dir, output_dir, check)
    ardot_doc = read_json(org_dir / "ardot.json")
    production_preferences = validate_production_preferences(
        spec,
        resolved_route_id=ctx.route.get("id"),
    )
    ctx.errors.extend(production_preferences["errors"])
    calibration = calibration_state(
        ctx.organization,
        ctx.route.get("id"),
        ctx.assets_doc,
        require_background_family=production_preferences.get("generate_backgrounds") is True,
    )
    ctx.errors.extend(calibration["blocking_reasons"])
    storyboard = build_storyboard_plan(spec_path)
    ctx.errors.extend(storyboard["errors"])
    try:
        visual_kit_plan = build_visual_kit_plan(spec_path, org_dir)
        ctx.errors.extend(visual_kit_plan["blocking_reasons"])
    except ValueError as exc:
        ctx.errors.append(str(exc))
        production_preferences = validate_production_preferences(
            spec,
            resolved_route_id=ctx.route.get("id"),
        )
        fallback_count = production_preferences.get("micro_component_count")
        if (
            not isinstance(fallback_count, int)
            or isinstance(fallback_count, bool)
            or not 0 <= fallback_count <= 4
        ):
            # This path is already blocked.  Zero is a no-work sentinel, not a
            # production choice, and prevents an invalid record from reviving
            # the retired four-component default.
            fallback_count = 0
        visual_kit_plan = {
            "ready_for_layout": False,
            "semantic_errors": [str(exc)],
            "blocking_reasons": [str(exc)],
            "requested_micro_component_count": fallback_count,
            "selected_roles": [],
        }
    typography = validate_typography_plan(spec, ctx.organization, ardot_doc)
    ctx.errors.extend(typography["errors"])
    interaction_plan = validate_interaction_plan(spec, ardot_doc, spec_path)
    ctx.errors.extend(interaction_plan["errors"])
    serialized = json.dumps(spec, ensure_ascii=False)
    markers = sorted(set(match.group(0) for match in PLACEHOLDERS.finditer(serialized)))
    if markers:
        ctx.errors.append(f"article contains placeholders: {', '.join(markers)}")
    visual_kit = spec.get("visual_kit")
    article_id = spec.get("article_id")
    requested_micro_component_count = visual_kit_plan.get(
        "requested_micro_component_count", 0
    )
    if (
        not isinstance(requested_micro_component_count, int)
        or isinstance(requested_micro_component_count, bool)
        or not 0 <= requested_micro_component_count <= 4
    ):
        requested_micro_component_count = 0
    selected_roles_raw = visual_kit_plan.get("selected_roles")
    selected_roles_list = [
        item for item in selected_roles_raw if isinstance(item, str)
    ] if isinstance(selected_roles_raw, list) else []
    selected_roles = set(selected_roles_list)
    expected_visual_kit_status = (
        "not-requested" if requested_micro_component_count == 0 else "approved"
    )
    if not isinstance(article_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", article_id):
        ctx.errors.append("article.article_id must be a lowercase hyphenated slug")
    kit_assets: list[dict[str, Any]] = []
    if not isinstance(visual_kit, dict):
        ctx.errors.append("article requires an approved visual_kit before layout or final transport")
    else:
        if visual_kit.get("status") != expected_visual_kit_status:
            ctx.errors.append(
                "article.visual_kit.status must be "
                f"{expected_visual_kit_status} for the selected component count"
            )
        raw_assets = visual_kit.get("assets")
        if isinstance(raw_assets, list):
            kit_assets = [item for item in raw_assets if isinstance(item, dict)]
        else:
            ctx.errors.append("article.visual_kit.assets must be an array")
    registered_assets = {
        item.get("id"): item
        for item in ctx.assets_doc.get("assets", [])
        if isinstance(item, dict) and item.get("id")
    }
    provenance_watermark = watermark_inventory(
        ctx.organization,
        ctx.assets_doc,
        ctx.org_dir,
    )
    ctx.errors.extend(provenance_watermark["errors"])
    ctx.warnings.extend(provenance_watermark["warnings"])
    kit_roles = {item.get("role") for item in kit_assets if isinstance(item.get("role"), str)}
    unique_kit_asset_ids = {
        item.get("id") for item in kit_assets if isinstance(item.get("id"), str)
    }
    fresh_kit_asset_ids: set[str] = set()
    for role in sorted(selected_roles - kit_roles):
        ctx.errors.append(f"article.visual_kit is missing selected generated role: {role}")
    for role in sorted(kit_roles - selected_roles):
        ctx.errors.append(f"article.visual_kit contains an unselected generated role: {role}")
    for item in kit_assets:
        asset_id = item.get("id")
        role = item.get("role", "<missing-role>")
        registered = registered_assets.get(asset_id)
        if registered is None:
            ctx.errors.append(f"visual kit role {role} references unknown asset: {asset_id}")
            continue
        role_errors = validate_asset_role(registered, "article-micro")
        ctx.errors.extend(
            f"visual kit role {role}: {message}" for message in role_errors
        )
        if article_id not in (registered.get("generated_for_articles") or []):
            ctx.errors.append(
                f"visual kit role {role} must use an asset freshly generated for article {article_id}"
            )
        elif not role_errors and isinstance(asset_id, str):
            fresh_kit_asset_ids.add(asset_id)
        ctx.asset_src(asset_id, f"visual kit role {role}")
    if len(fresh_kit_asset_ids) != requested_micro_component_count:
        ctx.errors.append(
            "article.visual_kit requires exactly "
            f"{requested_micro_component_count} distinct assets freshly generated for this article; "
            f"found {len(fresh_kit_asset_ids)}"
        )
    visual_review: dict[str, Any] = {}
    visual_review_report = {"ready": False, "errors": ["visual review was not loaded"]}
    micro_transport_items: list[dict[str, Any]] = []
    visual_review_file = spec.get("visual_review_file")
    if not isinstance(visual_review_file, str) or not visual_review_file.strip():
        ctx.errors.append("article requires visual_review_file with real Ardot node screenshots")
    else:
        review_path = Path(visual_review_file)
        if not review_path.is_absolute():
            review_path = (spec_path.parent / review_path).resolve()
        try:
            loaded_review = read_json(review_path)
            if not isinstance(loaded_review, dict):
                raise ValueError("visual review must be a JSON object")
            visual_review = loaded_review
            visual_review_report = validate_visual_review(visual_review, spec, spec_path)
            ctx.errors.extend(visual_review_report["errors"])
            if interaction_plan["module_count"]:
                review_ardot = (
                    visual_review.get("ardot")
                    if isinstance(visual_review.get("ardot"), dict)
                    else {}
                )
                expected_design_url = ardot_doc.get("design_file", {}).get("url")
                if review_ardot.get("file_url") != expected_design_url:
                    ctx.errors.append(
                        "interaction visual review must belong to the organization Ardot file"
                    )
            expected_density = ctx.organization.get("visual", {}).get("calibration", {}).get("density_mode")
            if visual_review_report.get("density_mode") != expected_density:
                ctx.errors.append(
                    f"visual review density mode must match organization calibration: {expected_density}"
                )
            kit_item_by_role = {
                item.get("role"): item
                for item in kit_assets
                if isinstance(item.get("role"), str)
            }
            screenshot_chapter_by_node = {
                item.get("node_id"): item.get("chapter_id")
                for item in visual_review.get("screenshots", [])
                if isinstance(item, dict)
            }
            layout = visual_review.get("micro_component_layout")
            placements = layout.get("placements") if isinstance(layout, dict) else []
            if isinstance(placements, list):
                for placement in placements:
                    if not isinstance(placement, dict):
                        continue
                    source_item = kit_item_by_role.get(placement.get("role"))
                    if not isinstance(source_item, dict):
                        continue
                    transport_item = dict(source_item)
                    transport_item["_transport_instance_id"] = placement.get("instance_node_id")
                    screenshot_chapter = screenshot_chapter_by_node.get(
                        placement.get("screenshot_node_id")
                    )
                    if isinstance(screenshot_chapter, str) and screenshot_chapter:
                        transport_item["storyboard_chapter"] = screenshot_chapter
                    micro_transport_items.append(transport_item)
        except ValueError as exc:
            ctx.errors.append(str(exc))
    if not micro_transport_items:
        micro_transport_items = kit_assets
    blocks = spec.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        ctx.errors.append("article.blocks must be a non-empty array")
        blocks = []
    family_id = calibration.get("background_family", {}).get("id")
    for block_index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "gallery":
            for image_index, image in enumerate(block.get("images", [])):
                if not isinstance(image, dict):
                    continue
                ref = image.get("src")
                asset = registered_assets.get(ref)
                if not asset:
                    ctx.errors.append(
                        f"gallery evidence {block_index}.{image_index} must use a registered documentary photo"
                    )
                    continue
                ctx.errors.extend(
                    f"gallery evidence asset {ref}: {message}"
                    for message in validate_asset_role(asset, "evidence-use")
                )
        background_ref = block.get("background")
        if isinstance(background_ref, str) and background_ref in registered_assets:
            background = registered_assets[background_ref]
            background_errors = validate_background_assignment(
                background,
                generated_backgrounds_enabled=(
                    production_preferences.get("generate_backgrounds") is True
                ),
            )
            ctx.errors.extend(
                f"article background {background_ref}: {message}"
                for message in background_errors
            )
            if (
                not background_errors
                and background.get("background_family_id") != family_id
            ):
                ctx.errors.append(
                    f"generated background is outside the calibrated family {family_id}: {background_ref}"
                )
    micro_after_block: dict[int, list[dict[str, Any]]] = {}
    chapter_by_id = {
        chapter.get("id"): chapter
        for chapter in storyboard.get("chapters", [])
        if isinstance(chapter, dict) and isinstance(chapter.get("id"), str)
    }
    for item in micro_transport_items:
        chapter = chapter_by_id.get(item.get("storyboard_chapter"))
        block_indices = chapter.get("block_indices", []) if isinstance(chapter, dict) else []
        valid_indices = [
            index
            for index in block_indices
            if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(blocks)
        ]
        if not valid_indices:
            ctx.errors.append(
                f"visual kit role {item.get('role')} has no valid storyboard block for transport"
            )
            continue
        target_index = (
            valid_indices[-1]
            if item.get("role") in {"section-transition", "closing-motif"}
            else valid_indices[0]
        )
        micro_after_block.setdefault(target_index, []).append(item)
    rendered_parts: list[str] = []
    micro_transport_count = 0
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        rendered_parts.append(render_block(ctx, block, index))
        for item in micro_after_block.get(index, []):
            micro_transport_count += 1
            rendered_parts.append(render_micro_component(ctx, item, micro_transport_count))
    rendered = "".join(rendered_parts)
    if len(rendered_blocks := [block for block in blocks if isinstance(block, dict)]) != len(blocks):
        ctx.errors.append("every article block must be an object")

    t = ctx.tokens
    workflow_attribution_display = workflow_attribution_presentation(t)
    workflow_attribution_html = render_workflow_attribution(t)
    rendered += workflow_attribution_html
    fragment = (
        f'<section data-organization="{esc(ctx.organization.get("id", ""))}" '
        f'data-route="{esc(ctx.route.get("id", ""))}" '
        f'style="max-width:100%;margin:0 auto;background:{t["surface"]};font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;">'
        f"{rendered}</section>"
    )
    workflow_attribution = {
        "required": True,
        "policy_id": WORKFLOW_ATTRIBUTION_MARKER,
        "classification": "repository-usage-credit",
        "text": WORKFLOW_ATTRIBUTION_TEXT,
        "text_sha256": f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}",
        "marker": WORKFLOW_ATTRIBUTION_MARKER,
        "present_once": fragment.count(WORKFLOW_ATTRIBUTION_TEXT) == 1,
        "marker_present_once": fragment.count(
            f'data-workflow-attribution="{WORKFLOW_ATTRIBUTION_MARKER}"'
        )
        == 1,
        "terminal": fragment.endswith(workflow_attribution_html + "</section>"),
        **workflow_attribution_display,
        "contrast_ready": workflow_attribution_display["contrast_ratio"] >= 4.5,
    }
    workflow_attribution["ready"] = all(
        workflow_attribution[field]
        for field in ("present_once", "marker_present_once", "terminal", "contrast_ready")
    )
    if not workflow_attribution["ready"]:
        ctx.errors.append(
            "workflow attribution must appear exactly once as the final visible article section"
        )
    if UNSAFE_WECHAT.search(fragment):
        ctx.errors.append("wechat fragment contains an unsafe tag")
    interaction_policy = audit_transport(fragment)
    ctx.errors.extend(interaction_policy["errors"])
    max_chars = ctx.organization.get("publishing", {}).get("max_content_chars")
    if isinstance(max_chars, int) and len(fragment) > max_chars:
        ctx.errors.append(f"wechat fragment exceeds configured max_content_chars: {len(fragment)} > {max_chars}")

    preview = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(spec.get("title", "WeChat preview"))}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#e8e8e8}}main{{width:min(430px,100%);margin:24px auto;background:{t["surface"]};box-shadow:0 12px 42px rgba(0,0,0,.13)}}@media(max-width:480px){{main{{margin:0;box-shadow:none}}}}</style>
</head><body><main>{fragment}</main></body></html>'''

    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = ctx.output_dir / "index.html"
    authoring_preview_path = ctx.output_dir / "authoring-preview.html"
    legacy_delivery_path = ctx.output_dir / "wechat.html"
    if legacy_delivery_path.is_file():
        legacy_delivery_path.unlink()
    if not ctx.errors:
        authoring_preview_path.write_text(fragment, encoding="utf-8")
        preview_path.write_text(preview, encoding="utf-8")
    else:
        for stale_transport in (preview_path, authoring_preview_path):
            if stale_transport.exists() and stale_transport.is_file():
                stale_transport.unlink()
    report = {
        "ok": not ctx.errors,
        "delivery_eligible": False,
        "source": "article-json-authoring-preview-v1",
        "delivery_blocker": {
            "code": "transport.source.article_json_renderer_forbidden",
            "message": (
                "This template-rendered HTML is an authoring preview only. Freeze the current "
                "Ardot root as an ardot-current-root-layer-export-v1 handoff before delivery."
            ),
        },
        "article": {
            "title": spec.get("title"),
            "article_id": article_id,
            "organization_id": spec.get("organization_id"),
            "article_type": spec.get("article_type"),
            "route_id": ctx.route.get("id"),
            "route_layout": ctx.route.get("layout"),
        },
        "production_preferences": production_preferences,
        "calibration": calibration,
        "provenance_watermark": {
            **provenance_watermark,
            "copy_checks": ctx.watermark_checks,
            "used_verified_asset_ids": sorted(
                {
                    item.get("asset_id")
                    for item in ctx.watermark_checks
                    if item.get("ready")
                    and isinstance(item.get("evidence"), dict)
                    and isinstance(item.get("detection"), dict)
                    and item["detection"].get("authenticated") is True
                    and isinstance(item.get("transport_simulation"), dict)
                    and item["transport_simulation"].get("payload_authenticated") is True
                    and isinstance(item.get("asset_id"), str)
                }
            ),
            "ready": provenance_watermark["ready"]
            and all(item.get("ready") for item in ctx.watermark_checks),
        },
        "workflow_attribution": workflow_attribution,
        "storyboard": storyboard,
        "counts": {
            "blocks": len(rendered_blocks),
            "html_characters": len(fragment),
            "copied_assets": len(ctx.copied_assets),
        },
        "visual_kit": {
            "requested_component_count": requested_micro_component_count,
            "selected_roles": selected_roles_list,
            "required_roles": selected_roles_list,
            "registered_roles": sorted(role for role in kit_roles if role),
            "unique_asset_count": len(unique_kit_asset_ids),
            "fresh_asset_count": len(fresh_kit_asset_ids),
            "semantic_errors": visual_kit_plan["semantic_errors"],
            "ready": visual_kit_plan["ready_for_layout"],
            "transport_instance_count": micro_transport_count,
            "transport_policy": {
                "maximum_image_width_ratio": 0.72,
                "copy_mode": "text-free-static-equivalent",
                "frame": "none",
            },
        },
        "typography": typography,
        "interaction_authoring": interaction_plan,
        "visual_review": visual_review_report,
        "interaction_policy": interaction_policy,
        "component_ids": list(dict.fromkeys(ctx.component_ids)),
        "source_ids": sorted(ctx.used_source_ids),
        "copied_assets": ctx.copied_assets,
        "warnings": list(dict.fromkeys(ctx.warnings)),
        "errors": list(dict.fromkeys(ctx.errors)),
        "outputs": {
            "preview": preview_path.name if not ctx.errors else None,
            "authoring_preview": authoring_preview_path.name if not ctx.errors else None,
            "wechat": None,
            "report": "compile-report.json",
        },
    }
    (ctx.output_dir / "compile-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", type=Path, nargs="?")
    parser.add_argument(
        "--transport-fidelity",
        type=Path,
        help="frozen Ardot layer handoff; the only delivery-eligible input",
    )
    parser.add_argument(
        "--authoring-preview",
        action="store_true",
        help="explicitly allow the article.json template adapter as a non-delivery preview",
    )
    parser.add_argument(
        "--session-draft",
        action="store_true",
        help="compile a current-session draft candidate without claiming portable signed audit",
    )
    parser.add_argument(
        "--interaction-probe",
        action="store_true",
        help=(
            "select the dynamic payload only for a reversible existing-draft "
            "sanitizer/mobile probe; never publication eligible"
        ),
    )
    parser.add_argument(
        "--live-root-export",
        type=Path,
        help="fresh host-owned Ardot current-root export required for final compilation",
    )
    parser.add_argument(
        "--live-root-receipt",
        type=Path,
        help="short-lived host-signed receipt for the actual Ardot live read",
    )
    parser.add_argument(
        "--upload-map",
        type=Path,
        help="target-account SHA upload map; mandatory for session/final draft compilation",
    )
    parser.add_argument(
        "--mobile-profile",
        type=Path,
        help="host-signed short-lived iOS/Android compatibility profile",
    )
    parser.add_argument(
        "--interaction-readback",
        type=Path,
        help="saved probe-draft HTML used to certify the dynamic payload",
    )
    parser.add_argument("--org", type=Path, help="Organization pack directory for authoring preview")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Exit non-zero when final QA fails")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.transport_fidelity:
        if args.article or args.authoring_preview or args.org:
            raise SystemExit(
                "--transport-fidelity is exclusive; final transport cannot mix article.json or org template inputs"
            )
        compiler = (
            compile_frozen_session_draft
            if args.session_draft
            else compile_frozen_transport
        )
        report = compiler(
            args.transport_fidelity,
            args.output,
            live_root_path=args.live_root_export,
            live_receipt_path=args.live_root_receipt,
            check=args.check,
            upload_map_path=args.upload_map,
            mobile_profile_path=args.mobile_profile,
            interaction_readback_path=args.interaction_readback,
            interaction_probe=args.interaction_probe,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.check and not report["ok"]:
            raise SystemExit(1)
        return
    if args.session_draft or args.interaction_probe:
        raise SystemExit("--session-draft/--interaction-probe require --transport-fidelity")
    if not args.article or not args.org or not args.authoring_preview:
        raise SystemExit(
            "article.json is authoring-only: pass --authoring-preview and --org, or use "
            "--transport-fidelity with a frozen Ardot layer handoff for final WeChat delivery"
        )
    try:
        article = existing_regular_file(args.article, label="article")
        organization = existing_directory(args.org, label="organization pack")
        output = new_directory_path(
            args.output,
            label="authoring preview output directory",
            forbidden_root=Path(__file__).resolve().parent.parent,
        )
        report = compile_article(article, organization, output, args.check)
    except (SafePathError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.check and not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
