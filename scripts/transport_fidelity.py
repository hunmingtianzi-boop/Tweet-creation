#!/usr/bin/env python3
"""Fail-closed Ardot-to-WeChat transport fidelity contract.

The contract deliberately describes *layers*, rather than a visual approximation:

``handoff.transport_fidelity.export`` is an
``ardot-current-root-layer-export-v1`` export.  Its chapters are in the exact
article order and each chapter binds its Ardot section node to a 390 px
artboard, a text-free 3x background, native text nodes, independent alpha
decorations, and (where used) an Ardot-derived SVG state or an explicit static
fallback.  A renderer can consume ``export.chapters`` directly.

This module validates the frozen manifest and, optionally, the compiled HTML
and a WeChat saved-draft readback.  It does not try to judge a screenshot:
screenshots/evidence are never legal body payloads.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from asset_quality import file_sha256, inspect_png, validate_micro_asset
from wechat_interaction_policy import SVG_SELF_INTERACTION, inspect_html
from workflow_quality import WORKFLOW_ATTRIBUTION_TEXT
from validate_workflow_attribution import current_root_revision_hash
from runtime_preflight import _trusted_bundle_digest


TRANSPORT_SOURCE = "ardot-current-root-layer-export-v1"
CURRENT_ROOT_SOURCE = "ardot-current-root-export"
TRANSPORT_REVISION_ALGORITHM = "ardot-transport-revision-v1"
READBACK_SOURCE = "wechat-saved-draft-readback-v1"
LIVE_RECEIPT_SOURCE = "ardot-host-live-read-receipt-v1"
READBACK_RECEIPT_SOURCE = "wechat-host-saved-draft-receipt-v1"
HOST_RECEIPT_TRUST_STORE_ENV = "ORG_WECHAT_HOST_RECEIPT_TRUST_STORE"
HOST_RECEIPT_TRUST_STORE_DEFAULT = Path(
    "/Library/Application Support/OpenAI/Codex/org-wechat-receipt-trust.json"
)
HOST_RECEIPT_TRUST_STORE_KIND = "org-wechat-host-receipt-trust-store"
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
LIVE_RECEIPT_MAX_TTL_SECONDS = 600
LIVE_ROOT_MAX_AGE_SECONDS = 3600
COMPILE_REPORT_MAX_AGE_SECONDS = 3600
READBACK_MAX_AGE_SECONDS = 3600
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
COMPOSITE_NAME = re.compile(
    r"(?:^|[/_.-])(evidence|qa|review|screenshot|contact|section[-_ ]?composite|composite)(?:$|[/_.-])",
    re.I,
)
TEXT_STYLE_FIELDS = {
    "font_family",
    "font_size_px",
    "line_height_ratio",
    "font_weight",
    "font_style",
    "text_decoration",
    "color",
    "letter_spacing_px",
    "text_align",
    "opacity",
    "rotation_deg",
    "blend_mode",
}
WECHAT_FONT_STACKS = {
    "system-sans-cn": "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif",
    "system-serif-cn": "'Songti SC','STSong','SimSun',serif",
}
ASSET_RENDER_STYLE_FIELDS = {
    "object_fit",
    "object_position",
    "opacity",
    "rotation_deg",
    "blend_mode",
    "mask",
}
INTERACTION_RENDER_STYLE = {
    "opacity": 1,
    "rotation_deg": 0,
    "blend_mode": "normal",
    "overflow": "hidden",
}


def _require_secure_transport_finalization_runtime() -> None:
    """Accept only a fully validated compiler or validator runner marker.

    The transport contract is shared by the two sensitive entrypoints, so its
    private non-diagnostic branch must validate whichever of those entrypoints
    the isolated runner actually bound.  Merely setting a marker is
    insufficient because ``require_secure_runtime`` rechecks isolation,
    sys.path, the workspace roots and the dependency lock.
    """
    from secure_runtime import require_secure_runtime_any

    require_secure_runtime_any(
        {
            "scripts/compile_wechat.py",
            "scripts/validate_transport_fidelity.py",
        }
    )


def normalize_visible_text(value: str) -> str:
    """Normalize transport whitespace while preserving the visible wording."""
    return re.sub(r"\s+", " ", value).strip()


def text_sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(
        normalize_visible_text(value).encode("utf-8")
    ).hexdigest()


def canonical_transport_revision_hash(export: dict[str, Any]) -> str:
    """Return a stable hash for the renderer-consumable Ardot layer export.

    The whole export is canonicalized intentionally: changing geometry, native
    text, an asset hash, or a fallback state changes the revision and requires
    re-freezing the transport handoff.
    """
    canonical_export = {key: value for key, value in export.items() if key != "revision_hash"}
    payload = json.dumps(
        canonical_export, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _parse_rfc3339(value: Any, *, label: str) -> datetime:
    """Parse an aware RFC3339 timestamp and normalize it to UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} captured_at must be an RFC3339 timestamp")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} captured_at must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} captured_at must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _decode_host_receipt_public_key(encoded: Any) -> Ed25519PublicKey:
    try:
        if isinstance(encoded, str) and encoded.startswith("hex:"):
            key = bytes.fromhex(encoded[4:])
        elif isinstance(encoded, str) and encoded.startswith("base64:"):
            key = base64.b64decode(encoded[7:], validate=True)
        else:
            raise ValueError
    except (ValueError, binascii.Error) as exc:
        raise ValueError(
            "host receipt trust-store public_key must be hex: or base64: encoded"
        ) from exc
    if len(key) != 32:
        raise ValueError("host receipt trust-store public_key must contain exactly 32 bytes")
    return Ed25519PublicKey.from_public_bytes(key)


def _host_receipt_trust_material() -> tuple[str, Ed25519PublicKey]:
    """Load an Ed25519 trust root from a host-protected file.

    An ordinary environment value may choose *where* the host installed its
    trust store, but it cannot choose the public key: the file and every parent
    directory must be root-owned, non-symlink and not group/other writable.
    This deliberately fails closed on an unprovisioned harness.  The matching
    private key stays behind the separate ``host.receipt.attest`` capability.
    """

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise ValueError(
            "repository process running as root cannot establish an external host trust boundary"
        )
    configured = os.environ.get(HOST_RECEIPT_TRUST_STORE_ENV)
    candidate = Path(configured) if configured else HOST_RECEIPT_TRUST_STORE_DEFAULT
    if not candidate.is_absolute():
        raise ValueError(f"{HOST_RECEIPT_TRUST_STORE_ENV} must be an absolute path")
    try:
        unresolved = candidate
        if any(item.is_symlink() for item in (unresolved, *unresolved.parents)):
            raise ValueError("host receipt trust-store path must not contain symlinks")
        resolved = unresolved.resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            "host receipt trust store is unavailable; bind host.receipt.attest before delivery"
        ) from exc
    chain = [resolved, *resolved.parents]
    for item in chain:
        try:
            metadata = item.lstat()
        except OSError as exc:
            raise ValueError("host receipt trust-store protection cannot be inspected") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("host receipt trust-store path must not contain symlinks")
        if metadata.st_uid != 0:
            raise ValueError("host receipt trust store and every parent must be root-owned")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError(
                "host receipt trust store and every parent must not be group/other writable"
            )
        if os.access(item, os.W_OK):
            raise ValueError(
                "repository process must not have ACL or effective write access to the host receipt trust store path"
            )
    if not resolved.is_file():
        raise ValueError("host receipt trust store must be a regular file")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("host receipt trust store must be valid UTF-8 JSON") from exc
    required_fields = {
        "schema_version",
        "kind",
        "key_id",
        "public_key",
        "allowed_receipt_sources",
    }
    if not isinstance(payload, dict) or set(payload) != required_fields:
        raise ValueError("host receipt trust store has missing or unsigned extra fields")
    key_id = payload.get("key_id")
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != HOST_RECEIPT_TRUST_STORE_KIND
        or not isinstance(key_id, str)
        or re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", key_id) is None
        or payload.get("allowed_receipt_sources")
        != [LIVE_RECEIPT_SOURCE, READBACK_RECEIPT_SOURCE]
    ):
        raise ValueError("host receipt trust store schema, key id, or source allowlist is invalid")
    return key_id, _decode_host_receipt_public_key(payload.get("public_key"))


def _host_receipt_signature(value: Any) -> bytes:
    if not isinstance(value, str) or not value.startswith("ed25519:"):
        raise ValueError("live-root receipt signature must use ed25519:base64")
    try:
        signature = base64.b64decode(value.removeprefix("ed25519:"), validate=True)
    except binascii.Error as exc:
        raise ValueError("live-root receipt signature must use valid base64") from exc
    if len(signature) != 64:
        raise ValueError("live-root Ed25519 signature must contain exactly 64 bytes")
    return signature


def _live_receipt_payload(receipt: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in receipt.items() if key != "signature"}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _is_wechat_cdn_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "mmbiz.qpic.cn"
        and port is None
        and parsed.username is None
        and parsed.password is None
        and bool(parsed.path and parsed.path.startswith("/"))
        and not parsed.fragment
    )


def path_identity_sha256(path: Path) -> str:
    """Bind a local artifact to its canonical path without exposing that path."""
    return "sha256:" + hashlib.sha256(
        str(path.resolve(strict=False)).encode("utf-8")
    ).hexdigest()


def _snapshot_geometry(raw: dict[str, Any]) -> dict[str, float]:
    """Normalize Ardot geometry for exact current-root/transport comparison."""
    return {key: float(raw[key]) for key in ("x", "y", "width", "height")}


def current_root_transport_snapshot(export: dict[str, Any]) -> dict[str, Any]:
    """Derive the complete body-layer census that the Ardot root must attest.

    The snapshot intentionally excludes local paths and QA screenshots.  It
    binds every actual body source node, layer geometry/style input, z-order,
    and payload hash, so the transport export cannot pair current text with an
    older or manually reconstructed layout.
    """
    sections: list[dict[str, Any]] = []
    body_asset_ids: set[str] = set()
    for chapter in export["chapters"]:
        chapter_height = float(chapter["geometry"]["height"])
        layers: list[dict[str, Any]] = []

        background = chapter["background_layer"]
        body_asset_ids.add(str(background["asset_id"]))
        layers.append(
            {
                "kind": "background",
                "node_id": background["source_node_id"],
                "asset_id": background["asset_id"],
                "asset_sha256": background["sha256"],
                "background_node_export_sha256": background[
                    "background_node_export"
                ]["sha256"],
                "z_index": background["z_index"],
                "geometry": {
                    "x": 0.0,
                    "y": 0.0,
                    "width": 390.0,
                    "height": chapter_height,
                },
                "render_style": background["render_style"],
            }
        )
        for decoration in chapter["decorations"]:
            body_asset_ids.add(str(decoration["asset_id"]))
            layers.append(
                {
                    "kind": "decoration",
                    "node_id": decoration["source_node_id"],
                    "asset_id": decoration["asset_id"],
                    "asset_sha256": decoration["sha256"],
                    "role": decoration["micro_role"],
                    "z_index": decoration["z_index"],
                    "geometry": _snapshot_geometry(decoration["geometry"]),
                    "render_style": decoration["render_style"],
                }
            )
        for photo in chapter["photos"]:
            body_asset_ids.add(str(photo["asset_id"]))
            layers.append(
                {
                    "kind": "photo",
                    "node_id": photo["source_node_id"],
                    "asset_id": photo["asset_id"],
                    "asset_sha256": photo["sha256"],
                    "role": "documentary-evidence",
                    "source_id": photo["source_id"],
                    "z_index": photo["z_index"],
                    "geometry": _snapshot_geometry(photo["geometry"]),
                    "render_style": photo["render_style"],
                }
            )
        for node in chapter["visible_text_nodes"]:
            layers.append(
                {
                    "kind": "text",
                    "node_id": node["node_id"],
                    "text_sha256": node["text_sha256"],
                    "semantic_role": node["semantic_role"],
                    "tag": node["tag"],
                    "style": node["style"],
                    "z_index": node["z_index"],
                    "geometry": _snapshot_geometry(node["geometry"]),
                }
            )
        interaction_raw = chapter.get("interaction")
        interactions = (
            interaction_raw
            if isinstance(interaction_raw, list)
            else [interaction_raw]
        )
        for item in interactions:
            if not isinstance(item, dict):
                continue
            fallback = item["fallback_asset"]
            body_asset_ids.add(str(fallback["asset_id"]))
            layer = {
                "kind": "interaction",
                "node_id": item["source_node_id"],
                "interaction_id": item["interaction_id"],
                "mode": item["mode"],
                "fallback_key": item["fallback_key"],
                "fallback_asset_id": fallback["asset_id"],
                "fallback_asset_sha256": fallback["sha256"],
                "fallback_semantic_sha256": item["fallback_semantic_sha256"],
                "z_index": item["z_index"],
                "geometry": _snapshot_geometry(item["geometry"]),
                "render_style": item["render_style"],
            }
            if item["mode"] == "svg":
                svg = item["svg"]
                body_asset_ids.add(str(svg["asset_id"]))
                layer.update(
                    {
                        "svg_asset_id": svg["asset_id"],
                        "svg_asset_sha256": svg["sha256"],
                        "svg_structure_sha256": item["structure_sha256"],
                        "ardot_state_sha256": item["ardot_state_sha256"],
                        "ardot_states": item["ardot_states"],
                    }
                )
            layers.append(layer)
        layers.sort(key=lambda item: int(item["z_index"]))
        sections.append(
            {
                "chapter_id": chapter["chapter_id"],
                "section_node_id": chapter["section_node_id"],
                "order": chapter["order"],
                "geometry_space": chapter["geometry_space"],
                "geometry": _snapshot_geometry(chapter["geometry"]),
                "layers": layers,
            }
        )
    return {
        "sections": sections,
        "body_asset_ids": sorted(body_asset_ids),
    }


def transport_position_style(
    geometry: dict[str, Any],
    *,
    chapter_height: float,
    extra: str = "",
) -> str:
    """Return the sole CSS mapping for a frozen chapter-local Ardot layer."""
    left = float(geometry["x"]) / 390.0 * 100.0
    top = float(geometry["y"]) / chapter_height * 100.0
    width = float(geometry["width"]) / 390.0 * 100.0
    height = float(geometry["height"]) / chapter_height * 100.0
    return (
        f"position:absolute;left:{left:.6f}%;top:{top:.6f}%;"
        f"width:{width:.6f}%;height:{height:.6f}%;{extra}"
    )


def _layer_render_signature(
    *,
    kind: str,
    layer_id: str,
    role: str,
    source_sha256: str,
    geometry: dict[str, Any],
    z_index: int,
    style: str,
    tag: str,
    mode: str = "",
) -> str:
    return _canonical_sha256(
        {
            "kind": kind,
            "layer_id": layer_id,
            "role": role,
            "source_sha256": source_sha256,
            "geometry": {
                key: float(geometry[key]) for key in ("x", "y", "width", "height")
            },
            "z_index": z_index,
            "style": style,
            "tag": tag,
            "mode": mode,
        }
    )


def text_layer_contract(node: dict[str, Any], *, chapter_height: float) -> dict[str, str]:
    source_style = node["style"]
    font_stack = WECHAT_FONT_STACKS[str(source_style["font_family"])]
    style = transport_position_style(
        node["geometry"],
        chapter_height=chapter_height,
        extra=(
            f"z-index:{int(node['z_index'])};margin:0;overflow:visible;"
            "background:transparent;border:0;border-radius:0;"
            f"font-size:{float(source_style['font_size_px']):g}px;"
            f"line-height:{float(source_style['line_height_ratio']):g};"
            f"font-weight:{int(source_style['font_weight'])};"
            f"font-style:{source_style['font_style']};"
            f"text-decoration:{source_style['text_decoration']};"
            f"letter-spacing:{float(source_style['letter_spacing_px']):g}px;"
            f"text-align:{source_style['text_align']};color:{source_style['color']};white-space:pre-wrap;"
            f"opacity:{float(source_style['opacity']):g};mix-blend-mode:{source_style['blend_mode']};"
            f"font-family:{font_stack};"
        ),
    )
    role = str(node["semantic_role"])
    layer_id = str(node["node_id"])
    source_sha = str(node["text_sha256"])
    tag = str(node["tag"])
    return {
        "kind": "text",
        "layer_id": layer_id,
        "role": role,
        "source_sha256": source_sha,
        "style": style,
        "tag": tag,
        "mode": "",
        "render_signature": _layer_render_signature(
            kind="text",
            layer_id=layer_id,
            role=role,
            source_sha256=source_sha,
            geometry=node["geometry"],
            z_index=int(node["z_index"]),
            style=style,
            tag=tag,
        ),
    }


def asset_layer_contract(
    asset: dict[str, Any],
    *,
    chapter_height: float,
    role: str,
    cover: bool = False,
) -> dict[str, str]:
    render_style = asset["render_style"]
    geometry = (
        {"x": 0, "y": 0, "width": 390, "height": chapter_height}
        if cover
        else asset["geometry"]
    )
    if cover:
        style = (
            "position:absolute;inset:0;width:100%;height:100%;display:block;"
            f"z-index:{int(asset['z_index'])};object-fit:{render_style['object_fit']};"
            f"object-position:{render_style['object_position']};opacity:{float(render_style['opacity']):g};"
            f"mix-blend-mode:{render_style['blend_mode']};border:0;border-radius:0;"
        )
    else:
        style = transport_position_style(
            geometry,
            chapter_height=chapter_height,
            extra=(
                f"z-index:{int(asset['z_index'])};display:block;object-fit:{render_style['object_fit']};"
                f"object-position:{render_style['object_position']};opacity:{float(render_style['opacity']):g};"
                f"mix-blend-mode:{render_style['blend_mode']};"
                "border:0;border-radius:0;background:transparent;"
            ),
        )
    # One asset can have multiple visible Ardot instances.  The transport layer
    # identity is therefore the current-root source node, never the asset ID.
    layer_id = str(asset["source_node_id"])
    source_sha = str(asset["sha256"])
    return {
        "kind": "background" if cover else ("decoration" if role == "article-micro" else "photo"),
        "layer_id": layer_id,
        "role": role,
        "source_sha256": source_sha,
        "style": style,
        "tag": "img",
        "mode": "",
        "render_signature": _layer_render_signature(
            kind="background" if cover else ("decoration" if role == "article-micro" else "photo"),
            layer_id=layer_id,
            role=role,
            source_sha256=source_sha,
            geometry=geometry,
            z_index=int(asset["z_index"]),
            style=style,
            tag="img",
        ),
    }


def interaction_layer_contract(
    item: dict[str, Any], *, chapter_height: float
) -> dict[str, str]:
    style = transport_position_style(
        item["geometry"],
        chapter_height=chapter_height,
        extra=(
            f"z-index:{int(item['z_index'])};overflow:hidden;"
            "opacity:1;mix-blend-mode:normal;background:transparent;border:0;border-radius:0;"
        ),
    )
    mode = str(item["mode"])
    source_sha = str(
        item["structure_sha256"]
        if mode == "svg"
        else item["fallback_semantic_sha256"]
    )
    layer_id = str(item["source_node_id"])
    return {
        "kind": "interaction",
        "layer_id": layer_id,
        "role": "interaction",
        "source_sha256": source_sha,
        "style": style,
        "tag": "div",
        "mode": mode,
        "render_signature": _layer_render_signature(
            kind="interaction",
            layer_id=layer_id,
            role="interaction",
            source_sha256=source_sha,
            geometry=item["geometry"],
            z_index=int(item["z_index"]),
            style=style,
            tag="div",
            mode=mode,
        ),
    }


def section_render_contract(
    chapter: dict[str, Any], *, revision_hash: str
) -> dict[str, str]:
    chapter_height = float(chapter["geometry"]["height"])
    ratio = chapter_height / 390.0 * 100.0
    style = (
        f"position:relative;width:100%;height:0;padding-top:{ratio:.6f}%;"
        "overflow:hidden;background:transparent;"
    )
    signature = _canonical_sha256(
        {
            "chapter_id": chapter["chapter_id"],
            "section_node_id": chapter["section_node_id"],
            "revision_hash": revision_hash,
            "geometry": {
                key: float(chapter["geometry"][key])
                for key in ("x", "y", "width", "height")
            },
            "style": style,
        }
    )
    return {"style": style, "render_signature": signature}


class _SVGCanonicalParser(HTMLParser):
    """Canonicalize actual SVG structure, ignoring only injected transport IDs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[Any] = []
        self.depth = 0
        self.root_count = 0
        self.invalid = False

    @staticmethod
    def attrs(attrs: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
        return sorted(
            (str(key).lower(), "" if value is None else str(value))
            for key, value in attrs
            if str(key).lower() != "data-transport-interaction-id"
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if self.depth == 0:
            if name != "svg":
                self.invalid = True
            else:
                self.root_count += 1
        self.events.append(["start", name, self.attrs(attrs)])
        self.depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        self.events.append(["end", tag.lower()])
        self.depth -= 1
        if self.depth < 0:
            self.invalid = True

    def handle_data(self, data: str) -> None:
        visible = re.sub(r"\s+", " ", data).strip()
        if visible:
            self.events.append(["text", visible])


def canonical_svg_structure_sha256(svg_text: str) -> str:
    parser = _SVGCanonicalParser()
    parser.feed(svg_text)
    parser.close()
    if parser.invalid or parser.depth != 0 or parser.root_count != 1 or not parser.events:
        raise ValueError("SVG must contain exactly one balanced root")
    return _canonical_sha256(parser.events)


def resolve_local_asset(manifest_path: Path, location: Any) -> Path | None:
    """Resolve a non-symlink payload file inside a frozen manifest directory.

    Remote URLs, symlinks and paths escaping the handoff are rejected.  This
    keeps a hash in a handoff meaningful after it is frozen for publishing.
    """
    if not isinstance(location, str) or not location or re.match(r"^https?://", location):
        return None
    root = manifest_path.resolve().parent
    candidate = (root / location)
    if candidate.is_symlink():
        return None
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if not resolved.is_file() or resolved.is_symlink():
        return None
    return resolved


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    """Read PNG/JPEG dimensions without making optional image libraries a gate."""
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if not data.startswith(b"\xff\xd8"):
        return None
    cursor = 2
    while cursor + 9 < len(data):
        if data[cursor] != 0xFF:
            cursor += 1
            continue
        while cursor < len(data) and data[cursor] == 0xFF:
            cursor += 1
        marker = data[cursor]
        cursor += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if cursor + 2 > len(data):
            break
        length = int.from_bytes(data[cursor:cursor + 2], "big")
        if length < 2 or cursor + length > len(data):
            break
        if marker in {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        } and length >= 7:
            return (
                int.from_bytes(data[cursor + 5:cursor + 7], "big"),
                int.from_bytes(data[cursor + 3:cursor + 5], "big"),
            )
        cursor += length
    return None


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _asset_digest(path: Path) -> str:
    return f"sha256:{file_sha256(path)}"


class _TransportHTML(HTMLParser):
    """Read exact frozen layers without executing page code."""

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    ROOT_ATTRS = {"data-transport-source", "data-ardot-root-node", "style"}
    SECTION_ATTRS = {
        "data-transport-chapter-id",
        "data-ardot-section-node",
        "data-transport-revision",
        "data-transport-section-signature",
        "style",
    }
    IMAGE_LAYER_ATTRS = {
        "src",
        "data-transport-asset-id",
        "data-transport-role",
        "alt",
        "data-transport-layer-kind",
        "data-transport-layer-id",
        "data-transport-source-sha256",
        "data-transport-render-signature",
        "style",
    }
    TEXT_LAYER_ATTRS = {
        "data-transport-text-node-id",
        "data-transport-text-sha256",
        "data-transport-semantic-role",
        "data-transport-layer-kind",
        "data-transport-layer-id",
        "data-transport-role",
        "data-transport-source-sha256",
        "data-transport-render-signature",
        "style",
    }
    INTERACTION_LAYER_ATTRS = {
        "data-transport-interaction-id",
        "data-transport-interaction-mode",
        "data-transport-layer-kind",
        "data-transport-layer-id",
        "data-transport-role",
        "data-transport-source-sha256",
        "data-transport-render-signature",
        "style",
    }
    STATIC_FALLBACK_ATTRS = {
        "src",
        "data-transport-asset-id",
        "data-transport-role",
        "alt",
        "style",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[dict[str, str]] = []
        self.image_occurrences: list[tuple[str, str, str, str]] = []
        self.sections: list[tuple[str, str, str, str, str]] = []
        self.sources: list[str] = []
        self.roots: list[tuple[str, str]] = []
        self.interactions: list[str | None] = []
        self.raw_svgs: list[str | None] = []
        self.svg_structures: list[tuple[str | None, str | None]] = []
        self.layers_by_chapter: dict[str, list[dict[str, str]]] = {}
        self.unmarked_top_level: list[str] = []
        self.unexpected_descendants: list[str] = []
        self.unexpected_document: list[str] = []
        self.malformed = False
        self._root_open = False
        self._root_closed = False
        self._section_id: str | None = None
        self._section_stack: list[str] = []
        self._text_stack: list[tuple[str, str, list[str]]] = []
        self.text_nodes: list[tuple[str, str]] = []
        self._svg_parser: _SVGCanonicalParser | None = None
        self._svg_identifier: str | None = None
        self._active_layer: dict[str, str] | None = None
        self._active_layer_child_count = 0

    @staticmethod
    def _values(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {str(key).lower(): "" if value is None else str(value) for key, value in attrs}

    @staticmethod
    def _layer(tag: str, values: dict[str, str]) -> dict[str, str]:
        return {
            "kind": values.get("data-transport-layer-kind", ""),
            "layer_id": values.get("data-transport-layer-id", ""),
            "role": values.get("data-transport-role", ""),
            "source_sha256": values.get("data-transport-source-sha256", ""),
            "style": values.get("style", ""),
            "tag": tag,
            "mode": values.get("data-transport-interaction-mode", ""),
            "render_signature": values.get("data-transport-render-signature", ""),
        }

    def _record_image(self, values: dict[str, str], parent_layer_id: str) -> None:
        self.images.append(values)
        self.image_occurrences.append(
            (
                str(self._section_id or ""),
                parent_layer_id,
                values.get("data-transport-asset-id", ""),
                values.get("data-transport-role", ""),
            )
        )

    def _flag_descendant(self, tag: str) -> None:
        layer_id = (
            self._active_layer.get("layer_id", "unknown")
            if self._active_layer is not None
            else "unknown"
        )
        self.unexpected_descendants.append(
            f"{self._section_id}:{layer_id}:{tag}"
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attribute_names = [str(key).lower() for key, _ in attrs]
        if len(attribute_names) != len(set(attribute_names)):
            self.malformed = True
            self.unexpected_document.append(f"duplicate-attributes:{tag}")
            return
        values = self._values(attrs)
        if values.get("data-transport-source"):
            self.sources.append(values["data-transport-source"])

        # The compiled artifact is one exact transport root.  Nothing may sit
        # beside it or wrap its section list.
        if self._section_id is None:
            if not self._root_open:
                if (
                    self._root_closed
                    or tag != "div"
                    or values.get("data-transport-source") != TRANSPORT_SOURCE
                ):
                    self.unexpected_document.append(f"outside-root:{tag}")
                    return
                self._root_open = True
                if set(values) != self.ROOT_ATTRS:
                    self.unexpected_document.append("root-attributes")
                self.roots.append(
                    (
                        values.get("data-ardot-root-node", ""),
                        values.get("style", ""),
                    )
                )
                return
            if tag != "section":
                self.unexpected_document.append(f"root-child:{tag}")
                return
            if set(values) != self.SECTION_ATTRS:
                self.unexpected_document.append("section-attributes")
            if self._section_id is not None:
                self.malformed = True
                return
            self._section_id = values.get("data-transport-chapter-id", "")
            self._section_stack = []
            self.sections.append(
                (
                    self._section_id,
                    values.get("data-ardot-section-node", ""),
                    values.get("data-transport-revision", ""),
                    values.get("style", ""),
                    values.get("data-transport-section-signature", ""),
                )
            )
            self.layers_by_chapter.setdefault(self._section_id, [])
            return

        if tag == "section":
            self.malformed = True
            return
        direct_layer = not self._section_stack
        if direct_layer:
            if not values.get("data-transport-layer-kind"):
                self.unmarked_top_level.append(f"{self._section_id}:{tag}")
            else:
                layer = self._layer(tag, values)
                self.layers_by_chapter[self._section_id].append(layer)
                kind = layer["kind"]
                expected_attrs = (
                    self.IMAGE_LAYER_ATTRS
                    if kind in {"background", "decoration", "photo"}
                    else self.TEXT_LAYER_ATTRS
                    if kind == "text"
                    else self.INTERACTION_LAYER_ATTRS
                    if kind == "interaction"
                    else set()
                )
                expected_tag = (
                    "img"
                    if kind in {"background", "decoration", "photo"}
                    else "div"
                    if kind == "interaction"
                    else tag
                )
                if not expected_attrs or set(values) != expected_attrs or tag != expected_tag:
                    self.unmarked_top_level.append(
                        f"{self._section_id}:{layer['layer_id']}:attributes"
                    )
                if tag == "img":
                    self._record_image(values, layer["layer_id"])
                elif tag not in self.VOID_TAGS:
                    self._active_layer = dict(layer)
                    self._active_layer["interaction_id"] = values.get(
                        "data-transport-interaction-id", ""
                    )
                    self._active_layer_child_count = 0
        else:
            if values.get("data-transport-layer-kind"):
                self._flag_descendant(f"nested-layer-{tag}")
            inside_svg = self._svg_parser is not None
            if not inside_svg:
                active = self._active_layer or {}
                direct_child = len(self._section_stack) == 1
                mode = active.get("mode")
                allowed = False
                if active.get("kind") == "interaction" and direct_child:
                    if mode == "svg" and tag == "svg":
                        allowed = (
                            self._active_layer_child_count == 0
                            and values.get("data-transport-interaction-id")
                            == active.get("interaction_id")
                        )
                    elif mode == "static-fallback" and tag == "img":
                        allowed = (
                            self._active_layer_child_count == 0
                            and set(values) == self.STATIC_FALLBACK_ATTRS
                            and values.get("data-transport-role")
                            == "interaction-fallback"
                            and values.get("alt") == ""
                            and values.get("style")
                            == "display:block;width:100%;height:100%;object-fit:contain;"
                        )
                    self._active_layer_child_count += 1
                if not allowed:
                    self._flag_descendant(tag)
                if tag == "img":
                    self._record_image(values, active.get("layer_id", ""))
        if tag == "svg":
            identifier = values.get("data-transport-interaction-id")
            self.raw_svgs.append(identifier)
            if identifier:
                self.interactions.append(identifier)
            if self._svg_parser is None:
                self._svg_parser = _SVGCanonicalParser()
                self._svg_identifier = identifier
        if self._svg_parser is not None:
            self._svg_parser.handle_starttag(tag, attrs)
        if tag != "svg" and "data-transport-interaction-id" in values:
            self.interactions.append(values.get("data-transport-interaction-id"))
        node_id = values.get("data-transport-text-node-id")
        if node_id:
            self._text_stack.append((tag, node_id, []))
        if self._section_id is not None and tag not in self.VOID_TAGS:
            self._section_stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        for _, _, chunks in self._text_stack:
            chunks.append(data)
        if self._svg_parser is not None:
            self._svg_parser.handle_data(data)
        if not normalize_visible_text(data):
            return
        if self._section_id is None:
            self.unexpected_document.append("visible-text-outside-section")
        elif not self._section_stack:
            self.unmarked_top_level.append(f"{self._section_id}:text")
        elif self._svg_parser is None and (
            self._active_layer is None
            or self._active_layer.get("kind") != "text"
        ):
            self._flag_descendant("visible-text")

    def handle_comment(self, data: str) -> None:
        if self._section_id is not None:
            self._flag_descendant("comment")
        else:
            self.unexpected_document.append("comment")

    def handle_decl(self, decl: str) -> None:
        self.unexpected_document.append("declaration")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        # A stack keeps nested native text wrappers deterministic without
        # accidentally closing a tracked node for an ordinary <em>/<strong>.
        if self._text_stack and self._text_stack[-1][0] == tag:
            _, node_id, chunks = self._text_stack.pop()
            self.text_nodes.append((node_id, normalize_visible_text("".join(chunks))))
        if self._svg_parser is not None:
            self._svg_parser.handle_endtag(tag)
            if tag == "svg" and self._svg_parser.depth == 0:
                parser = self._svg_parser
                digest = None
                if not parser.invalid and parser.root_count == 1 and parser.events:
                    digest = _canonical_sha256(parser.events)
                self.svg_structures.append((self._svg_identifier, digest))
                self._svg_parser = None
                self._svg_identifier = None
        if self._section_id is None:
            if self._root_open and tag == "div":
                self._root_open = False
                self._root_closed = True
            else:
                self.unexpected_document.append(f"unexpected-end:{tag}")
            return
        if tag == "section" and not self._section_stack:
            if self._active_layer is not None:
                self.malformed = True
            self._section_id = None
            return
        if self._section_stack and self._section_stack[-1] == tag:
            if (
                len(self._section_stack) == 1
                and self._active_layer is not None
                and self._active_layer.get("tag") == tag
            ):
                if (
                    self._active_layer.get("kind") == "interaction"
                    and self._active_layer_child_count != 1
                ):
                    self._flag_descendant("interaction-child-count")
                self._active_layer = None
                self._active_layer_child_count = 0
            self._section_stack.pop()
        else:
            self.malformed = True


class _Validator:
    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path.resolve()
        self.errors: list[dict[str, str]] = []
        self.asset_ids: dict[str, tuple[str, str]] = {}
        self.chapter_text: dict[str, list[dict[str, Any]]] = {}
        self.chapter_assets: dict[str, set[str]] = {}
        self.chapter_layers: dict[str, list[dict[str, str]]] = {}
        self.interaction_ids: set[str] = set()
        self.chapter_interactions: dict[str, list[dict[str, str]]] = {}
        self.text_node_ids: set[str] = set()
        self.export_file_id = ""
        self.export_root_node_id = ""
        self.frozen_current_root_export: dict[str, Any] | None = None
        self.frozen_current_root_export_path: Path | None = None
        self.bound_session_candidate = False
        self.bound_compile_assurance_scope: str | None = None
        self.bound_compile_observed_at: datetime | None = None

    def fail(self, code: str, message: str) -> None:
        self.errors.append({"code": code, "message": message})

    def require(self, condition: bool, code: str, message: str) -> bool:
        if not condition:
            self.fail(code, message)
        return condition

    def asset(
        self,
        raw: Any,
        *,
        chapter_id: str,
        role: str,
        require_alpha: bool = False,
        background: bool = False,
        body_image: bool = True,
    ) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            self.fail("transport.decoration.independent", f"{chapter_id} {role} must be an object")
            return None
        asset_id, location, digest = raw.get("asset_id"), raw.get("path"), raw.get("sha256")
        if not self.require(
            isinstance(asset_id, str) and bool(asset_id),
            "transport.decoration.independent",
            f"{chapter_id} {role} requires asset_id",
        ):
            return None
        if not self.require(
            isinstance(location, str) and bool(location),
            "transport.decoration.independent",
            f"{chapter_id} {role} requires local path",
        ):
            return None
        if not self.require(
            _is_sha256(digest),
            "transport.decoration.independent",
            f"{chapter_id} {role} requires sha256:<64 lowercase hex>",
        ):
            return None
        if COMPOSITE_NAME.search(location):
            self.fail(
                "transport.composite_raster",
                f"{chapter_id} {role} cannot point at evidence/QA/section-composite payload: {location}",
            )
        path = resolve_local_asset(self.manifest_path, location)
        if path is None:
            self.fail("transport.decoration.independent", f"{chapter_id} {role} path is not a local frozen payload")
            return None
        if _asset_digest(path) != digest:
            self.fail("transport.decoration.independent", f"{chapter_id} {role} SHA-256 does not match file")
        known = self.asset_ids.get(asset_id)
        descriptor = (location, digest)
        if known is not None and known != descriptor:
            self.fail("transport.mapping", f"asset_id {asset_id} maps to more than one frozen payload")
        self.asset_ids[asset_id] = descriptor
        if body_image:
            self.chapter_assets.setdefault(chapter_id, set()).add(asset_id)
        if require_alpha:
            if raw.get("independent") is not True or raw.get("contained_in_background") is not False:
                self.fail(
                    "transport.decoration.independent",
                    f"{chapter_id} {role} must be an independent layer outside the background/composite",
                )
            if raw.get("role") != "article-micro":
                self.fail(
                    "transport.decoration.independent",
                    f"{chapter_id} {role} must declare role=article-micro",
                )
            alpha = raw.get("alpha")
            alpha_ok = alpha is True or (
                isinstance(alpha, dict)
                and alpha.get("required") is True
                and alpha.get("verified") is True
            )
            self.require(
                alpha_ok,
                "transport.decoration.alpha",
                f"{chapter_id} {role} requires alpha=true or verified alpha evidence",
            )
            try:
                inspection = inspect_png(path)
            except (OSError, ValueError) as exc:
                self.fail("transport.decoration.alpha", f"{chapter_id} {role} alpha cannot be decoded: {exc}")
            else:
                if (
                    inspection.get("alpha_analysis") != "decoded"
                    or not inspection.get("has_alpha_channel")
                    or not inspection.get("has_transparent_pixels")
                ):
                    self.fail("transport.decoration.alpha", f"{chapter_id} {role} is not a true-alpha PNG")
            micro_role = raw.get("micro_role")
            if not isinstance(micro_role, str):
                self.fail(
                    "transport.decoration.alpha",
                    f"{chapter_id} {role} requires its semantic micro_role",
                )
            else:
                cutout = validate_micro_asset(path, micro_role)
                if not cutout.get("ok"):
                    self.fail(
                        "transport.decoration.alpha",
                        f"{chapter_id} {role} does not match the approved cutout gate: "
                        + "; ".join(cutout.get("errors", [])),
                    )
        if background:
            dimensions = _image_dimensions(path)
            declared_width = raw.get("width_px")
            if declared_width != 1170:
                self.fail("transport.background.resolution", f"{chapter_id} background requires width_px = 1170")
            if dimensions is None or dimensions[0] != 1170:
                self.fail("transport.background.resolution", f"{chapter_id} background payload must be exactly 1170 px wide")
            if raw.get("export_scale") != 3:
                self.fail("transport.background.resolution", f"{chapter_id} background export_scale must be 3")
            if raw.get("contains_text") is not False or raw.get("text_baked") is not False:
                self.fail("transport.background.text", f"{chapter_id} background must be explicitly text-free")
            if raw.get("text_node_count") != 0:
                self.fail(
                    "transport.background.text",
                    f"{chapter_id} background text_node_count must be 0",
                )
        return raw

    def json_evidence(
        self, raw: Any, *, code: str, label: str
    ) -> tuple[dict[str, Any] | None, Path | None]:
        if not isinstance(raw, dict):
            self.fail(code, f"{label} requires a hash-bound local JSON export")
            return None, None
        path = resolve_local_asset(self.manifest_path, raw.get("path"))
        digest = raw.get("sha256")
        if path is None or not _is_sha256(digest) or _asset_digest(path) != digest:
            self.fail(code, f"{label} JSON export is missing or hash-invalid")
            return None, path
        try:
            return _read_object(path, label), path
        except ValueError as exc:
            self.fail(code, str(exc))
            return None, path

    def background_node_evidence(
        self,
        background: Any,
        *,
        chapter_id: str,
        section_node_id: str,
        expected_width: int,
        expected_height: int,
    ) -> None:
        if not isinstance(background, dict):
            return
        source_node_id = background.get("source_node_id")
        if not isinstance(source_node_id, str) or not source_node_id:
            self.fail(
                "transport.background.text",
                f"{chapter_id} background requires source_node_id",
            )
            return
        evidence, _ = self.json_evidence(
            background.get("background_node_export"),
            code="transport.background.text",
            label=f"{chapter_id} Ardot background-only node export",
        )
        if evidence is None:
            return
        expected = {
            "source": "ardot-background-only-node-export-v1",
            "file_id": self.export_file_id,
            "root_node_id": self.export_root_node_id,
            "section_node_id": section_node_id,
            "source_node_id": source_node_id,
            "asset_id": background.get("asset_id"),
            "asset_sha256": background.get("sha256"),
            "text_descendant_count": 0,
            "text_descendant_node_ids": [],
            "width_px": expected_width,
            "height_px": expected_height,
            "export_scale": 3,
        }
        for field, value in expected.items():
            if evidence.get(field) != value:
                self.fail(
                    "transport.background.text",
                    f"{chapter_id} background-only node export {field} must equal {value!r}",
                )

    def interaction_state_evidence(
        self,
        item: dict[str, Any],
        *,
        chapter_id: str,
        section_node_id: str,
        structure_sha256: str,
    ) -> None:
        evidence_raw = item.get("ardot_state_export")
        evidence, path = self.json_evidence(
            evidence_raw,
            code="transport.interaction.freehand_svg",
            label=f"{chapter_id} interaction {item.get('interaction_id')} Ardot state export",
        )
        if evidence is None or path is None:
            return
        actual_digest = _asset_digest(path)
        if item.get("ardot_state_sha256") != actual_digest:
            self.fail(
                "transport.interaction.freehand_svg",
                f"{chapter_id} interaction Ardot state SHA must equal its actual export file",
            )
        expected = {
            "source": "ardot-interaction-state-export-v1",
            "file_id": self.export_file_id,
            "root_node_id": self.export_root_node_id,
            "section_node_id": section_node_id,
            "source_node_id": item.get("source_node_id"),
            "svg_structure_sha256": structure_sha256,
        }
        for field, value in expected.items():
            if evidence.get(field) != value:
                self.fail(
                    "transport.interaction.freehand_svg",
                    f"{chapter_id} interaction state export {field} must equal {value!r}",
                )
        authored_states = item.get("ardot_states")
        expected_names = ("closed", "open", "fallback")
        normalized_states: list[dict[str, str]] = []
        state_node_ids: list[str] = []
        if not isinstance(authored_states, dict) or set(authored_states) != set(
            expected_names
        ):
            self.fail(
                "transport.interaction.freehand_svg",
                f"{chapter_id} interaction must bind exact closed/open/fallback Ardot states",
            )
            return
        for name in expected_names:
            state = authored_states.get(name)
            if (
                not isinstance(state, dict)
                or set(state) != {"node_id", "tree_sha256"}
                or not isinstance(state.get("node_id"), str)
                or not state["node_id"]
                or not _is_sha256(state.get("tree_sha256"))
            ):
                self.fail(
                    "transport.interaction.freehand_svg",
                    f"{chapter_id} interaction {name} state requires a non-empty node_id and tree_sha256",
                )
                return
            state_node_ids.append(state["node_id"])
            normalized_states.append(
                {
                    "name": name,
                    "node_id": state["node_id"],
                    "tree_sha256": state["tree_sha256"],
                }
            )
        if len(set(state_node_ids)) != len(expected_names):
            self.fail(
                "transport.interaction.freehand_svg",
                f"{chapter_id} interaction closed/open/fallback states require distinct Ardot node IDs",
            )
        if evidence.get("states") != normalized_states:
            self.fail(
                "transport.interaction.freehand_svg",
                f"{chapter_id} interaction state export must exactly match the bound state nodes and tree hashes",
            )

    def geometry(self, raw: Any, *, code: str, label: str) -> bool:
        if not isinstance(raw, dict):
            self.fail(code, f"{label} requires geometry")
            return False
        required = ("x", "width", "y", "height")
        if not all(
            isinstance(raw.get(key), (int, float)) and not isinstance(raw.get(key), bool)
            for key in required
        ):
            self.fail(code, f"{label} geometry requires numeric x, y, width, height")
            return False
        if not all(math.isfinite(float(raw[key])) for key in required):
            self.fail(code, f"{label} geometry values must be finite")
            return False
        if raw["width"] <= 0 or raw["height"] <= 0:
            self.fail(code, f"{label} geometry width and height must be positive")
            return False
        return True

    def asset_render_style(
        self,
        raw: Any,
        *,
        code: str,
        label: str,
        allowed_object_fit: set[str],
    ) -> None:
        position_pattern = re.compile(
            r"^(?:100(?:\.0+)?|[0-9]{1,2}(?:\.\d+)?)% "
            r"(?:100(?:\.0+)?|[0-9]{1,2}(?:\.\d+)?)%$"
        )
        if not isinstance(raw, dict) or set(raw) != ASSET_RENDER_STYLE_FIELDS:
            self.fail(code, f"{label} requires the complete supported render_style")
            return
        if (
            raw.get("object_fit") not in allowed_object_fit
            or not isinstance(raw.get("object_position"), str)
            or position_pattern.fullmatch(raw["object_position"]) is None
            or not isinstance(raw.get("opacity"), (int, float))
            or isinstance(raw.get("opacity"), bool)
            or float(raw["opacity"]) != 1.0
            or not isinstance(raw.get("rotation_deg"), (int, float))
            or isinstance(raw.get("rotation_deg"), bool)
            or float(raw["rotation_deg"]) != 0.0
            or raw.get("blend_mode") != "normal"
            or raw.get("mask") != "none"
        ):
            self.fail(
                code,
                f"{label} uses an unsupported crop, opacity, rotation, blend, or mask; resolve it in the frozen Ardot asset",
            )

    def visible_text(self, chapter_id: str, raw: Any) -> None:
        if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
            self.fail("transport.native_text.mapping", f"{chapter_id} visible_text_nodes must be an array of objects")
            return
        ids: set[str] = set()
        nodes: list[dict[str, Any]] = []
        for index, node in enumerate(raw, start=1):
            label = f"{chapter_id} text node {index}"
            node_id, text = node.get("node_id"), node.get("text")
            if not isinstance(node_id, str) or not node_id or node_id in ids:
                self.fail("transport.native_text.mapping", f"{label} needs a unique node_id")
            elif node_id in self.text_node_ids:
                self.fail(
                    "transport.native_text.mapping",
                    f"{label} reuses a text node from another chapter",
                )
            else:
                ids.add(node_id)
                self.text_node_ids.add(node_id)
            if not isinstance(text, str) or not normalize_visible_text(text):
                self.fail("transport.native_text.hash", f"{label} requires non-empty visible text")
            elif node.get("text_sha256") != text_sha256(text):
                self.fail("transport.native_text.hash", f"{label} text_sha256 does not match normalized text")
            if node.get("native_editable_text") is not True or node.get("visible") is not True or node.get("rasterized") is not False:
                self.fail("transport.native_text.mapping", f"{label} must be visible native editable non-raster text")
            if not isinstance(node.get("semantic_role"), str) or not node["semantic_role"]:
                self.fail("transport.native_text.mapping", f"{label} requires semantic_role")
            if node.get("tag") not in {"p", "span", "h1", "h2", "h3", "h4", "blockquote", "li"}:
                self.fail("transport.native_text.mapping", f"{label} has unsupported native tag")
            style = node.get("style")
            if not isinstance(style, dict) or set(style) != TEXT_STYLE_FIELDS:
                self.fail("transport.native_text.mapping", f"{label} requires complete native style evidence")
            elif (
                style.get("font_family") not in WECHAT_FONT_STACKS
                or style.get("font_style") not in {"normal", "italic"}
                or style.get("text_decoration")
                not in {"none", "underline", "line-through"}
                or not isinstance(style.get("opacity"), (int, float))
                or isinstance(style.get("opacity"), bool)
                or float(style["opacity"]) != 1.0
                or not isinstance(style.get("rotation_deg"), (int, float))
                or isinstance(style.get("rotation_deg"), bool)
                or float(style["rotation_deg"]) != 0.0
                or style.get("blend_mode") != "normal"
                or not isinstance(style.get("font_size_px"), (int, float))
                or isinstance(style.get("font_size_px"), bool)
                or not 10 <= float(style["font_size_px"]) <= 72
                or not isinstance(style.get("line_height_ratio"), (int, float))
                or isinstance(style.get("line_height_ratio"), bool)
                or not 1 <= float(style["line_height_ratio"]) <= 2.2
                or not isinstance(style.get("font_weight"), int)
                or isinstance(style.get("font_weight"), bool)
                or not 100 <= style["font_weight"] <= 900
                or not isinstance(style.get("color"), str)
                or re.fullmatch(r"#[0-9A-Fa-f]{6}", style["color"]) is None
                or not isinstance(style.get("letter_spacing_px"), (int, float))
                or isinstance(style.get("letter_spacing_px"), bool)
                or not -1 <= float(style["letter_spacing_px"]) <= 4
                or style.get("text_align") not in {"left", "center", "right", "justify"}
            ):
                self.fail(
                    "transport.native_text.mapping",
                    f"{label} native style values are outside the safe renderer contract",
                )
            self.geometry(node.get("geometry"), code="transport.native_text.mapping", label=label)
            if node.get("order") != index:
                self.fail("transport.native_text.order", f"{label} order must be {index}")
            if not isinstance(node.get("z_index"), int) or isinstance(
                node.get("z_index"), bool
            ):
                self.fail(
                    "transport.native_text.mapping",
                    f"{label} requires integer z_index from the Ardot layer order",
                )
            nodes.append(node)
        self.chapter_text[chapter_id] = nodes

    def interaction(
        self, chapter_id: str, raw: Any, *, section_node_id: str
    ) -> None:
        if raw is None:
            return
        entries = raw if isinstance(raw, list) else [raw]
        if any(not isinstance(item, dict) for item in entries):
            self.fail("transport.interaction.freehand_svg", f"{chapter_id} interaction must be object(s)")
            return
        for index, item in enumerate(entries, start=1):
            label = f"{chapter_id} interaction {index}"
            interaction_id = item.get("interaction_id")
            if not isinstance(interaction_id, str) or not interaction_id or interaction_id in self.interaction_ids:
                self.fail("transport.interaction.freehand_svg", f"{label} needs a unique interaction_id")
            else:
                self.interaction_ids.add(interaction_id)
            self.geometry(item.get("geometry"), code="transport.interaction.freehand_svg", label=label)
            if item.get("render_style") != INTERACTION_RENDER_STYLE:
                self.fail(
                    "transport.interaction.freehand_svg",
                    f"{label} requires the exact supported interaction render_style",
                )
            if not isinstance(item.get("z_index"), int) or isinstance(
                item.get("z_index"), bool
            ):
                self.fail(
                    "transport.interaction.freehand_svg",
                    f"{label} requires integer z_index from the Ardot layer order",
                )
            mode = item.get("mode")
            actual_signature: str | None = None
            if not isinstance(item.get("source_node_id"), str) or not item.get(
                "source_node_id"
            ):
                self.fail(
                    "transport.interaction.freehand_svg",
                    f"{label} requires its current-root source_node_id",
                )
            if not isinstance(item.get("fallback_key"), str) or not item.get(
                "fallback_key"
            ):
                self.fail(
                    "transport.interaction.fallback",
                    f"{label} requires fallback_key",
                )
            if mode == "svg":
                if item.get("authored_from") != "ardot-state-export-v1":
                    self.fail("transport.interaction.freehand_svg", f"{label} SVG must be derived from an Ardot state export")
                if not _is_sha256(item.get("ardot_state_sha256")):
                    self.fail("transport.interaction.freehand_svg", f"{label} SVG needs source_node_id and ardot_state_sha256")
                if not _is_sha256(item.get("structure_sha256")):
                    self.fail(
                        "transport.interaction.freehand_svg",
                        f"{label} SVG requires a sanitizer readback structure_sha256",
                    )
                svg = item.get("svg")
                if not isinstance(svg, dict):
                    self.fail("transport.interaction.freehand_svg", f"{label} SVG requires frozen svg asset evidence")
                else:
                    self.asset(
                        svg,
                        chapter_id=chapter_id,
                        role="SVG",
                        require_alpha=False,
                        body_image=False,
                    )
                    svg_path = resolve_local_asset(self.manifest_path, svg.get("path"))
                    if svg_path is not None:
                        try:
                            svg_text = svg_path.read_text(encoding="utf-8")
                            actual_signature = canonical_svg_structure_sha256(svg_text)
                        except (OSError, UnicodeError, ValueError) as exc:
                            self.fail(
                                "transport.interaction.freehand_svg",
                                f"{label} SVG structure cannot be canonicalized: {exc}",
                            )
                        else:
                            if item.get("structure_sha256") != actual_signature:
                                self.fail(
                                    "transport.interaction.freehand_svg",
                                    f"{label} structure_sha256 does not match the actual frozen SVG",
                                )
                            policy = inspect_html(svg_text, label)
                            if (
                                policy.get("errors")
                                or policy.get("interactions", {}).get(SVG_SELF_INTERACTION) != 1
                                or int(policy.get("smil_count", 0)) < 1
                            ):
                                self.fail(
                                    "transport.interaction.freehand_svg",
                                    f"{label} is not one policy-valid self-trigger interactive SVG: "
                                    + "; ".join(policy.get("errors", [])),
                                )
                            fallback_key = item.get("fallback_key")
                            fallback_hash = item.get("fallback_semantic_sha256")
                            if (
                                not isinstance(fallback_key, str)
                                or not fallback_key
                                or not _is_sha256(fallback_hash)
                                or policy.get("fallback_sequence") != [fallback_key]
                                or policy.get("fallback_hashes", {}).get(fallback_key)
                                != fallback_hash
                            ):
                                self.fail(
                                    "transport.interaction.fallback",
                                    f"{label} SVG policy markers must match its frozen fallback key/hash",
                                )
                            self.interaction_state_evidence(
                                item,
                                chapter_id=chapter_id,
                                section_node_id=section_node_id,
                                structure_sha256=actual_signature,
                            )
                    fallback = item.get("fallback_asset")
                    if fallback is None:
                        self.fail(
                            "transport.interaction.fallback",
                            f"{label} SVG requires an information-equivalent fallback_asset",
                        )
                    else:
                        self.asset(
                            fallback,
                            chapter_id=chapter_id,
                            role="SVG fallback",
                            require_alpha=False,
                            body_image=False,
                        )
            elif mode == "static-fallback":
                if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                    self.fail("transport.interaction.fallback", f"{label} static fallback requires an explicit reason")
                fallback = item.get("fallback_asset")
                if fallback is None:
                    self.fail("transport.interaction.fallback", f"{label} static fallback requires fallback_asset")
                else:
                    self.asset(fallback, chapter_id=chapter_id, role="fallback", require_alpha=False)
                if not _is_sha256(item.get("fallback_semantic_sha256")):
                    self.fail(
                        "transport.interaction.fallback",
                        f"{label} static fallback requires fallback_semantic_sha256",
                    )
            else:
                self.fail("transport.interaction.freehand_svg", f"{label} mode must be svg or static-fallback")
            if isinstance(interaction_id, str) and interaction_id and mode in {
                "svg",
                "static-fallback",
            }:
                signature = (
                    actual_signature or item.get("structure_sha256")
                    if mode == "svg"
                    else item.get("fallback_semantic_sha256")
                )
                self.chapter_interactions.setdefault(chapter_id, []).append(
                    {
                        "interaction_id": interaction_id,
                        "mode": str(mode),
                        "signature_sha256": str(signature),
                    }
                )

    def export(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            self.fail("transport.mapping", "transport_fidelity.export must be an object")
            return None
        if raw.get("source") != TRANSPORT_SOURCE:
            self.fail("transport.mixed_sources", f"export.source must be {TRANSPORT_SOURCE}")
        if raw.get("revision_algorithm") != TRANSPORT_REVISION_ALGORITHM:
            self.fail("transport.mapping", f"export.revision_algorithm must be {TRANSPORT_REVISION_ALGORITHM}")
        for field in ("file_id", "root_node_id"):
            if not isinstance(raw.get(field), str) or not raw[field]:
                self.fail("transport.mapping", f"export.{field} is required")
        self.export_file_id = str(raw.get("file_id") or "")
        self.export_root_node_id = str(raw.get("root_node_id") or "")
        artboard = raw.get("artboard")
        if not isinstance(artboard, dict) or artboard.get("width_px") != 390 or not isinstance(artboard.get("height_px"), int) or artboard["height_px"] <= 0:
            self.fail("transport.mapping", "export.artboard must be a positive-height 390 px artboard")
        chapters = raw.get("chapters")
        if not isinstance(chapters, list) or not chapters or any(not isinstance(item, dict) for item in chapters):
            self.fail("transport.mapping", "export.chapters must be a non-empty object array")
            return raw
        seen_ids: set[str] = set()
        seen_nodes: set[str] = set()
        expected_chapter_y = 0.0
        for index, chapter in enumerate(chapters, start=1):
            chapter_id, section_node_id = chapter.get("chapter_id"), chapter.get("section_node_id")
            label = f"chapter {index}"
            if chapter.get("source") != TRANSPORT_SOURCE:
                self.fail("transport.mixed_sources", f"{label} source must be {TRANSPORT_SOURCE}")
            if not isinstance(chapter_id, str) or not chapter_id or chapter_id in seen_ids:
                self.fail("transport.mapping", f"{label} needs a unique chapter_id")
                chapter_id = f"invalid-{index}"
            seen_ids.add(chapter_id)
            if not isinstance(section_node_id, str) or not section_node_id or section_node_id in seen_nodes:
                self.fail("transport.mapping", f"{label} needs a unique section_node_id")
            seen_nodes.add(str(section_node_id))
            if chapter.get("order") != index:
                self.fail("transport.mapping", f"{label} order must be {index}")
            chapter_geometry = chapter.get("geometry")
            if not self.geometry(
                chapter_geometry,
                code="transport.mapping",
                label=f"{label} section",
            ):
                chapter_geometry = {}
            elif (
                chapter_geometry.get("x") != 0
                or chapter_geometry.get("width") != 390
                or chapter.get("geometry_space") != "article-root-390-v1"
                or not math.isclose(
                    float(chapter_geometry.get("y", math.nan)),
                    expected_chapter_y,
                    abs_tol=1e-6,
                )
            ):
                self.fail(
                    "transport.mapping",
                    f"{label} must start at y={expected_chapter_y:g} in the continuous 390 px article-root geometry space",
                )
            if isinstance(chapter_geometry.get("height"), (int, float)) and not isinstance(
                chapter_geometry.get("height"), bool
            ) and math.isfinite(float(chapter_geometry["height"])):
                expected_chapter_y += float(chapter_geometry["height"])
            chapter_artboard = chapter.get("artboard")
            if chapter_artboard is not None and chapter_artboard != artboard:
                self.fail("transport.mapping", f"{label} artboard must match export.artboard")
            for forbidden in ("section_composite", "composite_raster", "evidence_image", "qa_image"):
                if chapter.get(forbidden):
                    self.fail("transport.composite_raster", f"{label} cannot contain {forbidden}")
            screenshot = chapter.get("reference_screenshot")
            if not isinstance(screenshot, dict) or screenshot.get("width_px") != 390:
                self.fail(
                    "transport.mapping",
                    f"{label} requires a 390 px Ardot reference_screenshot",
                )
            else:
                screenshot_path = resolve_local_asset(
                    self.manifest_path, screenshot.get("path")
                )
                dimensions = (
                    _image_dimensions(screenshot_path) if screenshot_path is not None else None
                )
                if (
                    screenshot_path is None
                    or not _is_sha256(screenshot.get("sha256"))
                    or _asset_digest(screenshot_path) != screenshot.get("sha256")
                    or dimensions is None
                    or dimensions[0] != 390
                    or not isinstance(chapter_geometry.get("height"), (int, float))
                    or dimensions[1] != round(float(chapter_geometry["height"]))
                ):
                    self.fail(
                        "transport.mapping",
                        f"{label} reference screenshot is missing or hash-invalid",
                    )
            background = chapter.get("background_layer")
            self.asset(background, chapter_id=chapter_id, role="background", background=True)
            if isinstance(background, dict):
                self.asset_render_style(
                    background.get("render_style"),
                    code="transport.mapping",
                    label=f"{label} background",
                    allowed_object_fit={"cover"},
                )
            if not isinstance(background, dict) or background.get("z_index") != 0:
                self.fail(
                    "transport.mapping",
                    f"{label} background z_index must be 0",
                )
            if isinstance(background, dict) and isinstance(
                chapter_geometry.get("height"), (int, float)
            ):
                chapter_height = float(chapter_geometry["height"])
                expected_background_height = round(chapter_height * 3)
                background_path = resolve_local_asset(
                    self.manifest_path, background.get("path")
                )
                dimensions = (
                    _image_dimensions(background_path)
                    if background_path is not None
                    else None
                )
                if (
                    not math.isfinite(chapter_height)
                    or expected_background_height <= 0
                    or dimensions != (1170, expected_background_height)
                    or background.get("width_px") != 1170
                    or background.get("height_px") != expected_background_height
                ):
                    self.fail(
                        "transport.background.resolution",
                        f"{chapter_id} background must be the complete 1170 x "
                        f"{expected_background_height} 3x chapter export",
                    )
                self.background_node_evidence(
                    background,
                    chapter_id=chapter_id,
                    section_node_id=str(section_node_id),
                    expected_width=1170,
                    expected_height=expected_background_height,
                )
            self.visible_text(chapter_id, chapter.get("visible_text_nodes"))
            decorations = chapter.get("decorations")
            decoration_items = decorations if isinstance(decorations, list) else []
            if not isinstance(decorations, list) or any(not isinstance(item, dict) for item in decorations):
                self.fail("transport.decoration.independent", f"{chapter_id} decorations must be an array")
            else:
                for decoration_index, decoration in enumerate(decorations, start=1):
                    self.asset(decoration, chapter_id=chapter_id, role=f"decoration {decoration_index}", require_alpha=True)
                    self.geometry(decoration.get("geometry"), code="transport.decoration.independent", label=f"{chapter_id} decoration {decoration_index}")
                    self.asset_render_style(
                        decoration.get("render_style"),
                        code="transport.decoration.independent",
                        label=f"{chapter_id} decoration {decoration_index}",
                        allowed_object_fit={"contain"},
                    )
                    if not isinstance(decoration.get("source_node_id"), str) or not decoration.get("source_node_id"):
                        self.fail(
                            "transport.decoration.independent",
                            f"{chapter_id} decoration {decoration_index} requires its current-root source_node_id",
                        )
                    if not isinstance(decoration.get("z_index"), int) or isinstance(
                        decoration.get("z_index"), bool
                    ):
                        self.fail(
                            "transport.decoration.independent",
                            f"{chapter_id} decoration {decoration_index} requires integer z_index",
                        )
            photos = chapter.get("photos")
            photo_items = photos if isinstance(photos, list) else []
            if not isinstance(photos, list) or any(
                not isinstance(item, dict) for item in photos
            ):
                self.fail(
                    "transport.mapping",
                    f"{chapter_id} photos must be an explicit array",
                )
            else:
                for photo_index, photo in enumerate(photos, start=1):
                    self.asset(
                        photo,
                        chapter_id=chapter_id,
                        role=f"documentary photo {photo_index}",
                    )
                    self.geometry(
                        photo.get("geometry"),
                        code="transport.mapping",
                        label=f"{chapter_id} documentary photo {photo_index}",
                    )
                    self.asset_render_style(
                        photo.get("render_style"),
                        code="transport.mapping",
                        label=f"{chapter_id} documentary photo {photo_index}",
                        allowed_object_fit={"contain", "cover"},
                    )
                    if (
                        photo.get("role") != "documentary-evidence"
                        or not isinstance(photo.get("source_node_id"), str)
                        or not photo.get("source_node_id")
                        or not isinstance(photo.get("source_id"), str)
                        or not photo.get("source_id")
                        or not isinstance(photo.get("alt"), str)
                        or not photo.get("alt").strip()
                        or photo.get("independent") is not True
                    ):
                        self.fail(
                            "transport.mapping",
                            f"{chapter_id} documentary photo {photo_index} must remain an independent sourced evidence layer with alt text",
                        )
                    if not isinstance(photo.get("z_index"), int) or isinstance(
                        photo.get("z_index"), bool
                    ):
                        self.fail(
                            "transport.mapping",
                            f"{chapter_id} documentary photo {photo_index} requires integer z_index",
                        )
            self.interaction(
                chapter_id,
                chapter.get("interaction"),
                section_node_id=str(section_node_id),
            )
            interaction_raw = chapter.get("interaction")
            interactions = (
                interaction_raw if isinstance(interaction_raw, list) else [interaction_raw]
            )
            layer_z = [0]
            layer_z.extend(
                item.get("z_index")
                for item in chapter.get("visible_text_nodes", [])
                if isinstance(item, dict) and isinstance(item.get("z_index"), int)
            )
            layer_z.extend(
                item.get("z_index")
                for item in decoration_items if isinstance(item, dict) and isinstance(item.get("z_index"), int)
            )
            layer_z.extend(
                item.get("z_index")
                for item in photo_items
                if isinstance(item, dict) and isinstance(item.get("z_index"), int)
            )
            layer_z.extend(
                item.get("z_index")
                for item in interactions if isinstance(item, dict) and isinstance(item.get("z_index"), int)
            )
            if len(layer_z) != len(set(layer_z)):
                self.fail(
                    "transport.mapping",
                    f"{label} layer z_index values must be unique",
                )
            if isinstance(chapter_geometry.get("height"), (int, float)):
                chapter_height = float(chapter_geometry["height"])
                try:
                    expected_layers = [
                        asset_layer_contract(
                            background,
                            chapter_height=chapter_height,
                            role="background",
                            cover=True,
                        )
                    ]
                    expected_layers.extend(
                        asset_layer_contract(
                            item,
                            chapter_height=chapter_height,
                            role="article-micro",
                        )
                        for item in decoration_items
                    )
                    expected_layers.extend(
                        asset_layer_contract(
                            item,
                            chapter_height=chapter_height,
                            role="documentary-evidence",
                        )
                        for item in photo_items
                    )
                    expected_layers.extend(
                        text_layer_contract(item, chapter_height=chapter_height)
                        for item in self.chapter_text.get(chapter_id, [])
                    )
                    expected_layers.extend(
                        interaction_layer_contract(item, chapter_height=chapter_height)
                        for item in interactions
                        if isinstance(item, dict)
                        and item.get("mode") in {"svg", "static-fallback"}
                    )
                    self.chapter_layers[chapter_id] = expected_layers
                except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                    self.fail(
                        "transport.mapping",
                        f"{chapter_id} cannot derive an exact layer render contract: {exc}",
                    )
        if (
            isinstance(artboard, dict)
            and isinstance(artboard.get("height_px"), int)
            and not math.isclose(
                expected_chapter_y, float(artboard["height_px"]), abs_tol=1e-6
            )
        ):
            self.fail(
                "transport.mapping",
                "the frozen chapters must form one continuous, non-overlapping cover of the complete Ardot artboard",
            )
        expected = canonical_transport_revision_hash(raw)
        if raw.get("revision_hash") != expected:
            self.fail("transport.mapping", "export.revision_hash does not match canonical transport export")
        all_text_nodes = [
            node
            for chapter in chapters
            if isinstance(chapter, dict)
            for node in self.chapter_text.get(str(chapter.get("chapter_id")), [])
        ]
        attribution_nodes = [
            node
            for node in all_text_nodes
            if normalize_visible_text(str(node.get("text", "")))
            == WORKFLOW_ATTRIBUTION_TEXT
        ]
        if (
            len(attribution_nodes) != 1
            or not all_text_nodes
            or attribution_nodes[0] is not all_text_nodes[-1]
            or attribution_nodes[0].get("semantic_role") != "workflow-attribution"
        ):
            self.fail(
                "transport.workflow_attribution",
                "the exact workflow attribution must be one native terminal text node",
            )
        return raw

    def crosslink_handoff(
        self, handoff: dict[str, Any], export: dict[str, Any]
    ) -> None:
        """Bind the layer export to the separately frozen current-root evidence."""
        ardot = handoff.get("ardot")
        if not isinstance(ardot, dict):
            self.fail(
                "transport.attribution",
                "handoff requires complete top-level ardot current-root metadata",
            )
            return
        for field in ("file_id", "root_node_id"):
            if ardot.get(field) != export.get(field):
                self.fail(
                    "transport.attribution",
                    f"transport export {field} must match handoff ardot.{field}",
                )
        if export.get("current_root_revision_hash") != ardot.get("revision_hash"):
            self.fail(
                "transport.attribution",
                "transport export must bind the exact current-root revision hash",
            )
        attribution = handoff.get("workflow_attribution")
        if not isinstance(attribution, dict):
            self.fail(
                "transport.attribution",
                "handoff requires complete workflow_attribution current-root evidence",
            )
            return
        node_export_path = resolve_local_asset(
            self.manifest_path, attribution.get("node_export_file")
        )
        if (
            node_export_path is None
            or attribution.get("node_export_sha256") != _asset_digest(node_export_path)
        ):
            self.fail(
                "transport.attribution",
                "workflow attribution node export is missing or hash-invalid",
            )
            return
        try:
            node_export = _read_object(node_export_path, "Ardot current-root node export")
        except ValueError as exc:
            self.fail("transport.attribution", str(exc))
            return
        self.frozen_current_root_export = node_export
        self.frozen_current_root_export_path = node_export_path
        if (
            node_export.get("source") != CURRENT_ROOT_SOURCE
            or node_export.get("file_id") != export.get("file_id")
            or node_export.get("root_node_id") != export.get("root_node_id")
        ):
            self.fail(
                "transport.attribution",
                "transport file/root must match the hash-bound Ardot current-root node export",
            )
        if (
            node_export.get("revision_hash") != ardot.get("revision_hash")
            or export.get("current_root_revision_hash")
            != node_export.get("revision_hash")
        ):
            self.fail(
                "transport.attribution",
                "transport, handoff, and current-root layer evidence must share one root revision",
            )
        root_nodes = node_export.get("visible_text_nodes")
        if not isinstance(root_nodes, list) or any(
            not isinstance(item, dict) for item in root_nodes
        ):
            self.fail(
                "transport.attribution",
                "Ardot current-root node export must contain the complete visible text order",
            )
        else:
            expected_text = [
                (str(item.get("node_id", "")), normalize_visible_text(str(item.get("text", ""))))
                for item in root_nodes
            ]
            transport_text = [
                (str(node.get("node_id", "")), normalize_visible_text(str(node.get("text", ""))))
                for chapter in export.get("chapters", [])
                if isinstance(chapter, dict)
                for node in self.chapter_text.get(str(chapter.get("chapter_id")), [])
            ]
            if transport_text != expected_text:
                self.fail(
                    "transport.attribution",
                    "transport native text nodes must exactly match the current-root node export",
                )
            if (
                not transport_text
                or attribution.get("ardot_node_id") != transport_text[-1][0]
            ):
                self.fail(
                    "transport.attribution",
                    "transport terminal attribution node must match the current-root attribution node",
                )
        root_assets = node_export.get("assets")
        root_asset_map: dict[str, str] = {}
        if isinstance(root_assets, list):
            for item in root_assets:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    digest = item.get("sha256")
                    if isinstance(digest, str):
                        root_asset_map[item["id"]] = (
                            digest if digest.startswith("sha256:") else f"sha256:{digest}"
                        )
        try:
            expected_snapshot = current_root_transport_snapshot(export)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            self.fail(
                "transport.attribution",
                f"transport cannot derive its current-root section/layer census: {exc}",
            )
            expected_snapshot = {"sections": [], "body_asset_ids": []}
        if node_export.get("transport_sections") != expected_snapshot["sections"]:
            self.fail(
                "transport.attribution",
                "transport chapter nodes, absolute geometry, layer sources, z-order, styles, and interaction state must exactly match the current-root section/layer census",
            )
        component_order = node_export.get("component_order")
        component_ids: list[str] = []
        if not isinstance(component_order, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("node_id"), str)
            or not item["node_id"]
            for item in component_order
        ):
            self.fail(
                "transport.attribution",
                "current-root component_order must be the complete visible render-node census",
            )
        else:
            component_ids = [str(item["node_id"]) for item in component_order]
            expected_component_ids = [
                node_id
                for section in expected_snapshot["sections"]
                for node_id in (
                    [str(section["section_node_id"])]
                    + [str(layer["node_id"]) for layer in section["layers"]]
                )
            ]
            if (
                len(component_ids) != len(set(component_ids))
                or len(expected_component_ids) != len(set(expected_component_ids))
                or set(component_ids) != set(expected_component_ids)
            ):
                self.fail(
                    "transport.attribution",
                    "transport must cover every visible current-root section/layer source node exactly once; extra or omitted component nodes are forbidden",
                )
        expected_body_assets = expected_snapshot["body_asset_ids"]
        if node_export.get("body_asset_ids") != expected_body_assets:
            self.fail(
                "transport.attribution",
                "transport body asset coverage must exactly match the current-root body asset census",
            )
        if sorted(self.asset_ids) != expected_body_assets:
            self.fail(
                "transport.attribution",
                "derived transport body assets are incomplete or duplicated",
            )
        for asset_id, (_, digest) in self.asset_ids.items():
            if root_asset_map.get(asset_id) != digest:
                self.fail(
                    "transport.attribution",
                    f"transport asset {asset_id} is not hash-identical to the current-root export",
                )

    def live_current_root(self, path: Path, export: dict[str, Any]) -> bool:
        """Compare a fresh host-owned Ardot read with the frozen root snapshot."""
        if path.is_symlink():
            self.fail(
                "transport.current_root_live",
                "live current-root export must be a fresh non-symlink host capture",
            )
            return False
        try:
            live_path = path.resolve(strict=True)
            live = _read_object(live_path, "live Ardot current-root export")
        except (OSError, ValueError) as exc:
            self.fail("transport.current_root_live", str(exc))
            return False
        if (
            self.frozen_current_root_export is None
            or self.frozen_current_root_export_path is None
        ):
            self.fail(
                "transport.current_root_live",
                "frozen current-root evidence is unavailable for live comparison",
            )
            return False
        try:
            reuses_frozen_file = live_path.samefile(self.frozen_current_root_export_path)
        except OSError:
            reuses_frozen_file = live_path == self.frozen_current_root_export_path
        if reuses_frozen_file:
            self.fail(
                "transport.current_root_live",
                "live current-root evidence must be a new host read, not the frozen handoff file or a hard link to it",
            )
            return False
        frozen = self.frozen_current_root_export
        try:
            frozen_captured_at = _parse_rfc3339(
                frozen.get("captured_at"), label="frozen current-root export"
            )
            live_captured_at = _parse_rfc3339(
                live.get("captured_at"), label="live current-root export"
            )
        except ValueError as exc:
            self.fail("transport.current_root_live", str(exc))
            return False
        now = datetime.now(timezone.utc)
        if (
            live_captured_at > now + timedelta(seconds=30)
            or (now - live_captured_at).total_seconds()
            > LIVE_ROOT_MAX_AGE_SECONDS
        ):
            self.fail(
                "transport.current_root_live",
                "live current-root export is future-dated or too old for the active delivery session",
            )
            return False
        if (
            live_captured_at <= frozen_captured_at
            or _asset_digest(live_path)
            == _asset_digest(self.frozen_current_root_export_path)
        ):
            self.fail(
                "transport.current_root_live",
                "live current-root evidence must be newly captured after the frozen export; a renamed or byte-copied frozen file is not live proof",
            )
            return False
        compared_fields = (
            "schema_version",
            "source",
            "file_id",
            "root_node_id",
            "revision_algorithm",
            "revision_hash",
            "visible_text_nodes",
            "component_order",
            "assets",
            "transport_sections",
            "body_asset_ids",
        )
        if (
            current_root_revision_hash(live) != live.get("revision_hash")
            or live.get("revision_hash") != export.get("current_root_revision_hash")
            or any(live.get(field) != frozen.get(field) for field in compared_fields)
        ):
            self.fail(
                "transport.current_root_live",
                "fresh Ardot current-root text, sections, layers, styles, sources, or assets differ from the frozen handoff",
            )
            return False
        return True

    def live_current_root_receipt(
        self,
        path: Path,
        *,
        live_root_path: Path,
        export: dict[str, Any],
        expected_html_path: Path,
    ) -> bool:
        """Verify a short-lived host-signed attestation for the actual Ardot read.

        A structurally matching JSON file cannot authenticate where it came from.
        The signing key is therefore injected by the harness's trusted receipt
        verifier, not stored in the handoff or this repository.
        """
        if path.is_symlink():
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt must be a non-symlink host artifact",
            )
            return False
        try:
            receipt_path = path.resolve(strict=True)
            receipt = _read_object(receipt_path, "Ardot host live-read receipt")
            resolved_live_root = live_root_path.resolve(strict=True)
        except (OSError, ValueError) as exc:
            self.fail("transport.current_root_receipt", str(exc))
            return False
        required_fields = {
            "schema_version",
            "source",
            "signature_algorithm",
            "key_id",
            "nonce",
            "provider",
            "session_id",
            "request_id",
            "runtime_binding_nonce",
            "runtime_binding_digest",
            "trusted_bundle_sha256",
            "file_id",
            "root_node_id",
            "root_revision_hash",
            "transport_revision_hash",
            "handoff_sha256",
            "frozen_export_sha256",
            "live_export_sha256",
            "output_html_path_identity_sha256",
            "captured_at",
            "observed_at",
            "expires_at",
            "signature",
        }
        if set(receipt) != required_fields:
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt has missing or unsigned extra fields",
            )
            return False
        scalar_fields = ("key_id", "provider", "session_id", "request_id")
        if any(
            not isinstance(receipt.get(field), str)
            or re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", receipt[field]) is None
            for field in scalar_fields
        ):
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt requires bounded provider/session/request/key identifiers",
            )
            return False
        if (
            not isinstance(receipt.get("runtime_binding_nonce"), str)
            or re.fullmatch(
                r"[A-Za-z0-9_-]{32,128}", receipt["runtime_binding_nonce"]
            )
            is None
            or not _is_sha256(receipt.get("runtime_binding_digest"))
            or not _is_sha256(receipt.get("trusted_bundle_sha256"))
            or not _is_sha256(receipt.get("output_html_path_identity_sha256"))
        ):
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt requires signed runtime binding and intended-output identities",
            )
            return False
        try:
            expected_key_id, public_key = _host_receipt_trust_material()
        except ValueError as exc:
            self.fail("transport.current_root_receipt", str(exc))
            return False
        if receipt.get("key_id") != expected_key_id:
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt key_id does not match the trusted host configuration",
            )
        if (
            receipt.get("schema_version") != 1
            or receipt.get("source") != LIVE_RECEIPT_SOURCE
            or receipt.get("signature_algorithm") != "ed25519"
            or not isinstance(receipt.get("nonce"), str)
            or re.fullmatch(r"[0-9a-f]{32,64}", receipt["nonce"]) is None
        ):
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt schema, nonce, algorithm, or signature is invalid",
            )
            return False
        try:
            signature = _host_receipt_signature(receipt.get("signature"))
        except ValueError as exc:
            self.fail("transport.current_root_receipt", str(exc))
            return False
        if self.frozen_current_root_export_path is None:
            self.fail(
                "transport.current_root_receipt",
                "frozen current-root export is unavailable for receipt binding",
            )
            return False
        expected_bindings = {
            "file_id": export.get("file_id"),
            "root_node_id": export.get("root_node_id"),
            "root_revision_hash": export.get("current_root_revision_hash"),
            "transport_revision_hash": export.get("revision_hash"),
            "handoff_sha256": _asset_digest(self.manifest_path),
            "frozen_export_sha256": _asset_digest(
                self.frozen_current_root_export_path
            ),
            "live_export_sha256": _asset_digest(resolved_live_root),
            "trusted_bundle_sha256": _trusted_bundle_digest(WORKSPACE_ROOT),
            "output_html_path_identity_sha256": path_identity_sha256(
                expected_html_path
            ),
        }
        if any(receipt.get(field) != value for field, value in expected_bindings.items()):
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt is not bound to this handoff, frozen export, live bytes, and transport revision",
            )
            return False
        try:
            live_export = _read_object(resolved_live_root, "live Ardot current-root export")
            captured_at = _parse_rfc3339(
                receipt.get("captured_at"), label="live-root receipt"
            )
            live_captured_at = _parse_rfc3339(
                live_export.get("captured_at"), label="live current-root export"
            )
            observed_at = _parse_rfc3339(
                receipt.get("observed_at"), label="live-root receipt observed_at"
            )
            expires_at = _parse_rfc3339(
                receipt.get("expires_at"), label="live-root receipt expires_at"
            )
        except ValueError as exc:
            self.fail("transport.current_root_receipt", str(exc))
            return False
        now = datetime.now(timezone.utc)
        if (
            receipt.get("captured_at") != live_export.get("captured_at")
            or captured_at != live_captured_at
            or observed_at < captured_at
            or (observed_at - captured_at).total_seconds() > 30
            or expires_at <= observed_at
            or (expires_at - observed_at).total_seconds()
            > LIVE_RECEIPT_MAX_TTL_SECONDS
            or observed_at > now + timedelta(seconds=30)
            or now >= expires_at
        ):
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt time window is stale, future-dated, or not bound to the captured export",
            )
            return False
        try:
            public_key.verify(signature, _live_receipt_payload(receipt))
        except InvalidSignature:
            self.fail(
                "transport.current_root_receipt",
                "live-root receipt signature is not authenticated by the trusted host public key",
            )
            return False
        return not any(
            error["code"] == "transport.current_root_receipt"
            for error in self.errors
        )

    def compile_report(
        self,
        path: Path,
        export: dict[str, Any],
        *,
        explicit_html_path: Path | None = None,
        live_root_path: Path | None = None,
        live_receipt_path: Path | None = None,
        diagnostic: bool = False,
    ) -> Path | None:
        """Recompute a compiled-HTML binding.

        ``diagnostic=True`` accepts only the explicitly non-portable,
        current-session draft-candidate schema. It can bind a structurally
        verified live export without pretending that local JSON authenticates
        its external origin, and can never be mistaken for the final signed
        ``wechat.html`` compile report.
        """
        if path.is_symlink():
            self.fail(
                "transport.compile_artifact",
                "compile report must be a local non-symlink file",
            )
            return None
        try:
            report_path = path.resolve(strict=True)
            payload = _read_object(report_path, "compile report")
        except (OSError, ValueError) as exc:
            self.fail("transport.compile_artifact", str(exc))
            return None
        try:
            compiled_at = _parse_rfc3339(
                payload.get("compiled_at"), label="compile report"
            )
        except ValueError as exc:
            self.fail("transport.compile_artifact", str(exc))
            return None
        now = datetime.now(timezone.utc)
        if (
            compiled_at > now + timedelta(seconds=30)
            or (now - compiled_at).total_seconds()
            > COMPILE_REPORT_MAX_AGE_SECONDS
        ):
            self.fail(
                "transport.compile_artifact",
                "compile report is future-dated or too old for the active delivery session",
            )
            return None
        binding_container = payload.get("artifact_binding")
        binding_key = "candidate_html" if diagnostic else "wechat_html"
        binding = (
            binding_container.get(binding_key)
            if isinstance(binding_container, dict)
            else None
        )
        receipt_binding = (
            binding_container.get("live_root_receipt")
            if isinstance(binding_container, dict)
            else None
        )
        live_root_binding = (
            binding_container.get("live_root_export")
            if isinstance(binding_container, dict)
            else None
        )
        outputs = payload.get("outputs")
        try:
            handoff = _read_object(self.manifest_path, "handoff manifest")
        except ValueError as exc:
            self.fail("transport.compile_artifact", str(exc))
            return None
        article = handoff.get("article")
        postflight_ok_field = "diagnostic_ok" if diagnostic else "ok"
        preflight_root_field = (
            "session_live_root_structural_match"
            if diagnostic
            else "current_root_live_verified"
        )
        compile_assurance_scope = payload.get("assurance_scope")
        common_unfinished_state = (
            payload.get("portable_audit_verified") is False
            and payload.get("publication_preflight_eligible") is False
            and payload.get("publication_authorized") is False
            and payload.get("finalization_verified") is False
        )
        if diagnostic:
            report_mode_valid = (
                payload.get("delivery_eligible") is False
                and payload.get("candidate_valid") is True
                and payload.get("draft_write_eligible") is False
                and common_unfinished_state
                and compile_assurance_scope
                in {"current-session-draft", "diagnostic-candidate"}
            )
        else:
            report_mode_valid = (
                payload.get("delivery_eligible") is False
                and payload.get("draft_write_eligible") is True
                and compile_assurance_scope == "portable-signed-draft-candidate"
                and common_unfinished_state
            )
        if (
            payload.get("ok") is not True
            or not report_mode_valid
            or payload.get("source") != TRANSPORT_SOURCE
            or payload.get("revision_hash") != export.get("revision_hash")
            or payload.get("handoff_sha256") != _asset_digest(self.manifest_path)
            or not isinstance(payload.get("postflight"), dict)
            or payload["postflight"].get(postflight_ok_field) is not True
            or not isinstance(payload.get("preflight"), dict)
            or payload["preflight"].get(preflight_root_field) is not True
            or not isinstance(outputs, dict)
            or not isinstance(binding, dict)
            or not isinstance(live_root_binding, dict)
            or (not diagnostic and not isinstance(receipt_binding, dict))
            or (
                diagnostic
                and live_receipt_path is not None
                and not isinstance(receipt_binding, dict)
            )
            or (
                diagnostic
                and live_receipt_path is None
                and receipt_binding is not None
            )
            or not isinstance(article, dict)
        ):
            self.fail(
                "transport.compile_artifact",
                "compile report does not bind one successful postflight to this handoff revision",
            )
            return None
        required_live_root_binding = {
            "source",
            "path",
            "path_identity_sha256",
            "sha256",
            "byte_length",
            "device",
            "inode",
        }
        if live_root_path is None or live_root_path.is_symlink():
            self.fail(
                "transport.compile_artifact",
                "compile report requires the original non-symlink fresh live-root export",
            )
            return None
        try:
            resolved_live_root = live_root_path.resolve(strict=True)
            live_root_stat = resolved_live_root.stat()
        except OSError as exc:
            self.fail("transport.compile_artifact", str(exc))
            return None
        expected_live_root_binding = {
            "source": CURRENT_ROOT_SOURCE,
            "path": str(resolved_live_root),
            "path_identity_sha256": path_identity_sha256(resolved_live_root),
            "sha256": _asset_digest(resolved_live_root),
            "byte_length": live_root_stat.st_size,
            "device": live_root_stat.st_dev,
            "inode": live_root_stat.st_ino,
        }
        if (
            set(live_root_binding) != required_live_root_binding
            or live_root_binding != expected_live_root_binding
        ):
            self.fail(
                "transport.compile_artifact",
                "compile report fresh live-root binding is missing, rewritten, or stale",
            )
            return None
        required_receipt_binding = {
            "source",
            "path_identity_sha256",
            "sha256",
            "key_id",
            "signature_algorithm",
            "runtime_binding_nonce",
            "runtime_binding_digest",
            "trusted_bundle_sha256",
            "output_html_path_identity_sha256",
            "expires_at",
        }
        if live_receipt_path is None:
            if not diagnostic:
                self.fail(
                    "transport.compile_artifact",
                    "compile report requires the original non-symlink live-root receipt",
                )
                return None
        else:
            if live_receipt_path.is_symlink():
                self.fail(
                    "transport.compile_artifact",
                    "compile report requires the original non-symlink live-root receipt",
                )
                return None
            try:
                resolved_receipt = live_receipt_path.resolve(strict=True)
                receipt_payload = _read_object(
                    resolved_receipt, "Ardot host live-read receipt"
                )
            except (OSError, ValueError) as exc:
                self.fail("transport.compile_artifact", str(exc))
                return None
            expected_receipt_binding = {
                "source": LIVE_RECEIPT_SOURCE,
                "path_identity_sha256": path_identity_sha256(resolved_receipt),
                "sha256": _asset_digest(resolved_receipt),
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
            if (
                not isinstance(receipt_binding, dict)
                or set(receipt_binding) != required_receipt_binding
                or receipt_binding != expected_receipt_binding
            ):
                self.fail(
                    "transport.compile_artifact",
                    "compile report live-root receipt binding is missing, rewritten, or stale",
                )
                return None
        required_binding = {
            "source",
            "path",
            "sha256",
            "byte_length",
            "transport_revision_hash",
            "path_identity_sha256",
            "device",
            "inode",
        }
        expected_binding_source = (
            "wechat-session-draft-candidate-v1"
            if compile_assurance_scope == "current-session-draft"
            else "wechat-diagnostic-candidate-v1"
            if diagnostic
            else "wechat-compiled-artifact-v1"
        )
        expected_output_key = "candidate" if diagnostic else "wechat"
        if (
            set(binding) != required_binding
            or binding.get("source") != expected_binding_source
            or binding.get("path") != outputs.get(expected_output_key)
            or (
                not diagnostic
                and binding.get("path") != article.get("content_html")
            )
            or binding.get("transport_revision_hash") != export.get("revision_hash")
            or not _is_sha256(binding.get("sha256"))
            or not _is_sha256(binding.get("path_identity_sha256"))
            or not isinstance(binding.get("byte_length"), int)
            or isinstance(binding.get("byte_length"), bool)
            or binding.get("byte_length", 0) <= 0
            or not isinstance(binding.get("device"), int)
            or isinstance(binding.get("device"), bool)
            or not isinstance(binding.get("inode"), int)
            or isinstance(binding.get("inode"), bool)
        ):
            self.fail(
                "transport.compile_artifact",
                "compile report contains an invalid final WeChat HTML binding",
            )
            return None
        bound_path = resolve_local_asset(report_path, binding.get("path"))
        if bound_path is None:
            self.fail(
                "transport.compile_artifact",
                "bound WeChat HTML must be a local non-symlink file beside the compile report",
            )
            return None
        bound_stat = bound_path.stat()
        if (
            _asset_digest(bound_path) != binding.get("sha256")
            or bound_stat.st_size != binding.get("byte_length")
            or path_identity_sha256(bound_path)
            != binding.get("path_identity_sha256")
            or (
                isinstance(receipt_binding, dict)
                and path_identity_sha256(bound_path)
                != receipt_binding.get("output_html_path_identity_sha256")
            )
            or bound_stat.st_dev != binding.get("device")
            or bound_stat.st_ino != binding.get("inode")
        ):
            self.fail(
                "transport.compile_artifact",
                "final WeChat HTML path identity, inode or bytes differ from the compile artifact binding",
            )
        if explicit_html_path is not None:
            if explicit_html_path.is_symlink():
                self.fail(
                    "transport.compile_artifact",
                    "explicit WeChat HTML must not be a symlink",
                )
            else:
                try:
                    explicit_resolved = explicit_html_path.resolve(strict=True)
                except OSError as exc:
                    self.fail("transport.compile_artifact", str(exc))
                else:
                    if explicit_resolved != bound_path:
                        self.fail(
                            "transport.compile_artifact",
                            "explicit WeChat HTML is not the exact file bound by the compile report",
                        )
        self.bound_session_candidate = (
            compile_assurance_scope == "current-session-draft"
        )
        self.bound_compile_assurance_scope = (
            compile_assurance_scope
            if isinstance(compile_assurance_scope, str)
            else None
        )
        self.bound_compile_observed_at = compiled_at
        return bound_path

    def html(self, path: Path, export: dict[str, Any]) -> None:
        try:
            parser = _TransportHTML()
            parser.feed(path.read_text(encoding="utf-8"))
            parser.close()
        except (OSError, UnicodeError) as exc:
            self.fail("transport.mapping", f"compiled HTML is unavailable: {exc}")
            return
        chapters = export.get("chapters") if isinstance(export.get("chapters"), list) else []
        expected_sections = [
            (*(
                str(item.get("chapter_id", "")),
                str(item.get("section_node_id", "")),
                str(export.get("revision_hash", "")),
            ), section_render_contract(
                item, revision_hash=str(export.get("revision_hash", ""))
            )["style"], section_render_contract(
                item, revision_hash=str(export.get("revision_hash", ""))
            )["render_signature"])
            for item in chapters
            if isinstance(item, dict)
        ]
        if parser.sources != [TRANSPORT_SOURCE]:
            self.fail(
                "transport.mixed_sources",
                "compiled HTML must declare exactly one frozen Ardot transport source",
            )
        expected_root = [
            (
                str(export.get("root_node_id", "")),
                "width:100%;margin:0;padding:0;background:transparent;",
            )
        ]
        if parser.roots != expected_root or parser._root_open or not parser._root_closed:
            self.fail(
                "transport.render_signature",
                "compiled HTML must contain one exact frozen transport root",
            )
        if parser.sections != expected_sections:
            self.fail("transport.mapping", "compiled HTML chapter order/mapping differs from Ardot export")
        if (
            parser.malformed
            or parser.unmarked_top_level
            or parser.unexpected_descendants
            or parser.unexpected_document
        ):
            self.fail(
                "transport.render_signature",
                "compiled HTML contains malformed, unsigned, or non-canonical DOM content: "
                + ", ".join(
                    parser.unmarked_top_level
                    + parser.unexpected_descendants
                    + parser.unexpected_document
                ),
            )
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            chapter_id = str(chapter.get("chapter_id", ""))
            if parser.layers_by_chapter.get(chapter_id, []) != self.chapter_layers.get(
                chapter_id, []
            ):
                self.fail(
                    "transport.render_signature",
                    f"compiled chapter {chapter_id} layer role/style/geometry/z-index/signature differs from the frozen export",
                )
        for image in parser.images:
            source = image.get("src", "")
            asset_id = image.get("data-transport-asset-id")
            if COMPOSITE_NAME.search(source) or image.get("data-transport-role") in {"evidence", "qa", "section-composite"}:
                self.fail("transport.composite_raster", f"compiled body contains evidence/QA/section-composite image: {source}")
            if not isinstance(asset_id, str) or asset_id not in self.asset_ids:
                self.fail("transport.mapping", "every compiled body image needs a known data-transport-asset-id")
            elif source:
                compiled_asset = resolve_local_asset(path, source)
                expected_digest = self.asset_ids[asset_id][1]
                if compiled_asset is None or _asset_digest(compiled_asset) != expected_digest:
                    self.fail(
                        "transport.render_signature",
                        f"compiled image {asset_id} source does not match its frozen bytes",
                    )
        expected_image_assets = {
            asset_id
            for chapter in chapters
            if isinstance(chapter, dict)
            for asset_id in self.chapter_assets.get(str(chapter.get("chapter_id")), set())
        }
        svg_asset_ids = {
            item.get("svg", {}).get("asset_id")
            for chapter in chapters
            if isinstance(chapter, dict)
            for item in (
                chapter.get("interaction")
                if isinstance(chapter.get("interaction"), list)
                else [chapter.get("interaction")]
            )
            if isinstance(item, dict) and item.get("mode") == "svg"
        }
        expected_image_assets -= {item for item in svg_asset_ids if isinstance(item, str)}
        expected_image_occurrences: list[tuple[str, str, str, str]] = []
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            chapter_id = str(chapter.get("chapter_id", ""))
            background = chapter.get("background_layer")
            if isinstance(background, dict):
                expected_image_occurrences.append(
                    (
                        chapter_id,
                        str(background.get("source_node_id", "")),
                        str(background.get("asset_id", "")),
                        "background",
                    )
                )
            for item in chapter.get("decorations", []):
                if isinstance(item, dict):
                    expected_image_occurrences.append(
                        (
                            chapter_id,
                            str(item.get("source_node_id", "")),
                            str(item.get("asset_id", "")),
                            "article-micro",
                        )
                    )
            for item in chapter.get("photos", []):
                if isinstance(item, dict):
                    expected_image_occurrences.append(
                        (
                            chapter_id,
                            str(item.get("source_node_id", "")),
                            str(item.get("asset_id", "")),
                            "documentary-evidence",
                        )
                    )
            interaction_raw = chapter.get("interaction")
            interactions = (
                interaction_raw
                if isinstance(interaction_raw, list)
                else [interaction_raw]
            )
            for item in interactions:
                if isinstance(item, dict) and item.get("mode") == "static-fallback":
                    fallback = item.get("fallback_asset")
                    if isinstance(fallback, dict):
                        expected_image_occurrences.append(
                            (
                                chapter_id,
                                str(item.get("source_node_id", "")),
                                str(fallback.get("asset_id", "")),
                                "interaction-fallback",
                            )
                        )
        if parser.image_occurrences != expected_image_occurrences:
            self.fail(
                "transport.render_signature",
                "compiled body image occurrence/order/parent coverage differs from the frozen layer grammar",
            )
        actual_image_assets = {
            image.get("data-transport-asset-id")
            for image in parser.images
            if image.get("data-transport-asset-id")
        }
        if actual_image_assets != expected_image_assets:
            self.fail(
                "transport.mapping",
                "compiled body image coverage differs from the frozen Ardot layer export",
            )
        expected_text = [
            (node.get("node_id"), normalize_visible_text(node.get("text", "")))
            for chapter in chapters if isinstance(chapter, dict)
            for node in self.chapter_text.get(chapter.get("chapter_id"), [])
        ]
        if parser.text_nodes != expected_text:
            self.fail("transport.native_text.order", "compiled native text node order/text differs from Ardot export")
        if any(identifier is None for identifier in parser.raw_svgs):
            self.fail("transport.interaction.freehand_svg", "compiled body contains an SVG without a transport interaction id")
        if set(item for item in parser.interactions if item) != self.interaction_ids:
            self.fail("transport.interaction.freehand_svg", "compiled interaction ids differ from frozen Ardot export")
        expected_svg_structures = [
            (entry["interaction_id"], entry["signature_sha256"])
            for chapter in chapters
            if isinstance(chapter, dict)
            for entry in self.chapter_interactions.get(str(chapter.get("chapter_id")), [])
            if entry.get("mode") == "svg"
        ]
        if parser.svg_structures != expected_svg_structures:
            self.fail(
                "transport.interaction.freehand_svg",
                "compiled inline SVG structure signatures differ from the actual frozen SVG files",
            )

    def readback(
        self,
        path: Path,
        export: dict[str, Any],
        *,
        expected_target_account_ref: str | None = None,
        not_before: datetime | None = None,
        now: datetime | None = None,
    ) -> None:
        if path.is_symlink():
            self.fail(
                "transport.readback",
                "saved-draft readback must be a local non-symlink host export",
            )
            return
        try:
            payload = _read_object(path, "saved-draft readback")
        except ValueError as exc:
            self.fail("transport.readback", str(exc))
            return
        required_fields = {
            "schema_version",
            "source",
            "target_account_ref",
            "draft_id",
            "title",
            "digest",
            "cover_asset_id",
            "thumb_media_id",
            "cover_hosted_derivative",
            "transport_revision_hash",
            "observed_at",
            "chapters",
        }
        if set(payload) != required_fields:
            self.fail(
                "transport.readback",
                "saved-draft readback has missing or unsigned extra top-level fields",
            )
            return
        if payload.get("schema_version") != 1:
            self.fail("transport.readback", "readback.schema_version must be 1")
        if payload.get("source") != READBACK_SOURCE:
            self.fail("transport.readback", f"readback.source must be {READBACK_SOURCE}")
        for field in ("target_account_ref", "draft_id"):
            value = payload.get(field)
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 256
                or any(ord(char) < 32 for char in value)
            ):
                self.fail(
                    "transport.readback",
                    f"readback.{field} must be one bounded visible identifier",
                )
        try:
            handoff = _read_object(self.manifest_path, "handoff manifest")
        except ValueError as exc:
            self.fail("transport.readback", str(exc))
            handoff = {}
        article = handoff.get("article")
        assets = handoff.get("assets")
        expected_cover_asset_id = (
            article.get("cover_asset_id") if isinstance(article, dict) else None
        )
        cover_assets = [
            item
            for item in assets
            if isinstance(item, dict)
            and item.get("id") == expected_cover_asset_id
            and item.get("role") == "cover"
        ] if isinstance(assets, list) else []
        if (
            not isinstance(article, dict)
            or not isinstance(article.get("title"), str)
            or not article["title"].strip()
            or not isinstance(article.get("digest"), str)
            or not isinstance(expected_cover_asset_id, str)
            or not expected_cover_asset_id
            or len(cover_assets) != 1
        ):
            self.fail(
                "transport.readback_cover",
                "handoff article title, digest, and one matching role=cover asset are required for saved-draft verification",
            )
            cover_asset: dict[str, Any] = {}
        else:
            cover_asset = cover_assets[0]
        if isinstance(article, dict) and (
            payload.get("title") != article.get("title")
            or payload.get("digest") != article.get("digest")
        ):
            self.fail(
                "transport.readback_article",
                "saved-draft title and digest must exactly match the frozen handoff article",
            )
        if payload.get("cover_asset_id") != expected_cover_asset_id:
            self.fail(
                "transport.readback_cover",
                "saved-draft cover_asset_id must match the frozen handoff article and role=cover asset",
            )
        thumb_media_id = payload.get("thumb_media_id")
        if (
            not isinstance(thumb_media_id, str)
            or not thumb_media_id.strip()
            or len(thumb_media_id) > 512
            or any(ord(char) < 32 for char in thumb_media_id)
        ):
            self.fail(
                "transport.readback_cover",
                "saved-draft thumb_media_id must be one bounded visible identifier",
            )
        expected_thumb_media_id = cover_asset.get("wechat_thumb_media_id")
        if (
            not isinstance(expected_thumb_media_id, str)
            or not expected_thumb_media_id.strip()
            or len(expected_thumb_media_id) > 512
            or any(ord(char) < 32 for char in expected_thumb_media_id)
        ):
            self.fail(
                "transport.readback_cover",
                "the frozen role=cover asset must bind a non-empty target-account wechat_thumb_media_id before final compilation",
            )
        elif thumb_media_id != expected_thumb_media_id:
            self.fail(
                "transport.readback_cover",
                "saved-draft thumb_media_id differs from the target-account cover material bound to the cover asset",
            )
        cover_derivative = payload.get("cover_hosted_derivative")
        required_cover_derivative_fields = {
            "url",
            "downloaded_path",
            "downloaded_sha256",
            "downloaded_byte_length",
        }
        if (
            not isinstance(cover_derivative, dict)
            or set(cover_derivative) != required_cover_derivative_fields
            or not _is_wechat_cdn_url(cover_derivative.get("url"))
            or not _is_sha256(cover_derivative.get("downloaded_sha256"))
            or not isinstance(cover_derivative.get("downloaded_byte_length"), int)
            or isinstance(cover_derivative.get("downloaded_byte_length"), bool)
            or cover_derivative.get("downloaded_byte_length", 0) <= 0
        ):
            self.fail(
                "transport.readback_cover",
                "saved-draft cover requires the actual https://mmbiz.qpic.cn derivative and downloaded SHA-256/byte length",
            )
        else:
            downloaded_cover = resolve_local_asset(
                path, cover_derivative.get("downloaded_path")
            )
            if (
                downloaded_cover is None
                or _asset_digest(downloaded_cover)
                != cover_derivative.get("downloaded_sha256")
                or downloaded_cover.stat().st_size
                != cover_derivative.get("downloaded_byte_length")
            ):
                self.fail(
                    "transport.readback_cover",
                    "saved-draft cover derivative bytes are missing or differ from the bound download hash/length",
                )
        if (
            expected_target_account_ref is not None
            and payload.get("target_account_ref") != expected_target_account_ref
        ):
            self.fail(
                "transport.readback_target",
                "saved-draft readback target account differs from the account bound by the active delivery session",
            )
        try:
            observed_at = _parse_rfc3339(
                payload.get("observed_at"), label="saved-draft readback"
            )
        except ValueError as exc:
            self.fail("transport.readback", str(exc))
        else:
            current_time = now or datetime.now(timezone.utc)
            if (
                observed_at > current_time + timedelta(seconds=30)
                or (current_time - observed_at).total_seconds()
                > READBACK_MAX_AGE_SECONDS
                or (not_before is not None and observed_at <= not_before)
            ):
                self.fail(
                    "transport.readback_time",
                    "saved-draft readback must be fresh, after this exact compilation, and not future-dated",
                )
        if payload.get("transport_revision_hash") != export.get("revision_hash"):
            self.fail(
                "transport.readback",
                "readback transport_revision_hash must match the current frozen export",
            )
        chapters = payload.get("chapters")
        source_chapters = export.get("chapters") if isinstance(export.get("chapters"), list) else []
        if not isinstance(chapters, list) or len(chapters) != len(source_chapters):
            self.fail("transport.readback", "readback must contain every exported chapter once")
            return
        for index, (actual, source) in enumerate(zip(chapters, source_chapters), start=1):
            if not isinstance(actual, dict) or not isinstance(source, dict):
                self.fail("transport.readback", f"readback chapter {index} must be an object")
                continue
            chapter_id = source.get("chapter_id")
            expected_nodes = self.chapter_text.get(chapter_id, [])
            expected_ids = [node.get("node_id") for node in expected_nodes]
            expected_hash = text_sha256(" ".join(str(node.get("text", "")) for node in expected_nodes))
            if actual.get("chapter_id") != chapter_id or actual.get("section_node_id") != source.get("section_node_id"):
                self.fail("transport.readback", f"readback chapter {index} mapping differs from Ardot export")
            if actual.get("visible_text_node_ids") != expected_ids or actual.get("visible_text_sha256") != expected_hash:
                self.fail("transport.readback", f"readback chapter {index} native text differs from Ardot export")
            expected_assets = sorted(self.chapter_assets.get(chapter_id, set()))
            if actual.get("asset_ids") != expected_assets:
                self.fail("transport.readback", f"readback chapter {index} asset ids differ from frozen export")
            hosted_assets = actual.get("hosted_assets")
            if not isinstance(hosted_assets, list):
                self.fail(
                    "transport.readback",
                    f"readback chapter {index} requires hosted_assets with downloaded hashes",
                )
            else:
                hosted_ids: list[str] = []
                for hosted in hosted_assets:
                    if not isinstance(hosted, dict):
                        self.fail("transport.readback", f"readback chapter {index} hosted asset is invalid")
                        continue
                    hosted_ids.append(str(hosted.get("asset_id")))
                    if not _is_wechat_cdn_url(hosted.get("url")):
                        self.fail(
                            "transport.readback",
                            f"readback chapter {index} hosted asset must be the actual https://mmbiz.qpic.cn object returned by WeChat",
                        )
                    if not _is_sha256(hosted.get("downloaded_sha256")):
                        self.fail("transport.readback", f"readback chapter {index} hosted asset requires downloaded_sha256")
                    downloaded = resolve_local_asset(path, hosted.get("downloaded_path"))
                    if (
                        downloaded is None
                        or _asset_digest(downloaded) != hosted.get("downloaded_sha256")
                    ):
                        self.fail(
                            "transport.readback",
                            f"readback chapter {index} hosted asset downloaded bytes are missing or hash-invalid",
                        )
                if sorted(hosted_ids) != expected_assets:
                    self.fail("transport.readback", f"readback chapter {index} hosted assets are incomplete")
            screenshot = actual.get("screenshot")
            if not isinstance(screenshot, dict) or screenshot.get("width_px") != 390:
                self.fail("transport.readback", f"readback chapter {index} requires a 390 px screenshot")
            else:
                screenshot_path = resolve_local_asset(path, screenshot.get("path"))
                if (
                    screenshot_path is None
                    or not _is_sha256(screenshot.get("sha256"))
                    or _asset_digest(screenshot_path) != screenshot.get("sha256")
                    or _image_dimensions(screenshot_path) is None
                    or _image_dimensions(screenshot_path)
                    != (
                        390,
                        round(float(source.get("geometry", {}).get("height", 0))),
                    )
                ):
                    self.fail(
                        "transport.readback",
                        f"readback chapter {index} screenshot evidence is missing or hash-invalid",
                    )
            actual_interactions = actual.get("interactions")
            normalized_interactions: list[dict[str, str]] = []
            if not isinstance(actual_interactions, list) or any(
                not isinstance(item, dict) for item in actual_interactions
            ):
                self.fail(
                    "transport.readback",
                    f"readback chapter {index} interactions must be an evidence array",
                )
            else:
                for interaction in actual_interactions:
                    normalized = {
                        "interaction_id": str(interaction.get("interaction_id", "")),
                        "mode": str(interaction.get("mode", "")),
                        "signature_sha256": str(interaction.get("signature_sha256", "")),
                    }
                    normalized_interactions.append(normalized)
                    if normalized["mode"] == "svg":
                        svg_path = resolve_local_asset(
                            path, interaction.get("structure_path")
                        )
                        if (
                            svg_path is None
                            or interaction.get("structure_file_sha256")
                            != _asset_digest(svg_path)
                        ):
                            self.fail(
                                "transport.readback",
                                f"readback chapter {index} SVG structure evidence is missing or hash-invalid",
                            )
                        else:
                            try:
                                recomputed = canonical_svg_structure_sha256(
                                    svg_path.read_text(encoding="utf-8")
                                )
                            except (OSError, UnicodeError, ValueError) as exc:
                                self.fail(
                                    "transport.readback",
                                    f"readback chapter {index} SVG structure cannot be recomputed: {exc}",
                                )
                            else:
                                if recomputed != normalized["signature_sha256"]:
                                    self.fail(
                                        "transport.readback",
                                        f"readback chapter {index} SVG signature is not derived from saved bytes",
                                    )
            if normalized_interactions != self.chapter_interactions.get(chapter_id, []):
                self.fail(
                    "transport.readback",
                    f"readback chapter {index} interaction mode/signature differs from frozen export",
                )

    def saved_draft_readback_receipt(
        self,
        path: Path,
        *,
        readback_path: Path,
        compiled_html_path: Path,
        compile_report_path: Path,
        live_receipt_path: Path,
        export: dict[str, Any],
    ) -> bool:
        """Authenticate saved-draft evidence as a current host observation."""
        inputs = {
            "receipt": path,
            "readback": readback_path,
            "compiled HTML": compiled_html_path,
            "compile report": compile_report_path,
            "live-root receipt": live_receipt_path,
        }
        if any(candidate.is_symlink() for candidate in inputs.values()):
            self.fail(
                "transport.readback_receipt",
                "saved-draft receipt and every bound artifact must be non-symlink files",
            )
            return False
        try:
            resolved = {
                label: candidate.resolve(strict=True)
                for label, candidate in inputs.items()
            }
            receipt = _read_object(resolved["receipt"], "saved-draft host receipt")
            readback = _read_object(resolved["readback"], "saved-draft readback")
            live_receipt = _read_object(
                resolved["live-root receipt"], "Ardot host live-read receipt"
            )
        except (OSError, ValueError) as exc:
            self.fail("transport.readback_receipt", str(exc))
            return False
        required_fields = {
            "schema_version",
            "source",
            "signature_algorithm",
            "key_id",
            "nonce",
            "provider",
            "session_id",
            "request_id",
            "runtime_binding_nonce",
            "runtime_binding_digest",
            "trusted_bundle_sha256",
            "target_account_ref",
            "draft_id",
            "title",
            "digest",
            "cover_asset_id",
            "thumb_media_id",
            "cover_hosted_url",
            "cover_downloaded_sha256",
            "cover_downloaded_byte_length",
            "handoff_sha256",
            "transport_revision_hash",
            "output_html_path_identity_sha256",
            "compiled_html_sha256",
            "compile_report_sha256",
            "live_receipt_sha256",
            "readback_sha256",
            "observed_at",
            "expires_at",
            "signature",
        }
        if set(receipt) != required_fields:
            self.fail(
                "transport.readback_receipt",
                "saved-draft host receipt has missing or unsigned extra fields",
            )
            return False
        scalar_fields = (
            "key_id",
            "provider",
            "session_id",
            "request_id",
        )
        if any(
            not isinstance(receipt.get(field), str)
            or re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", receipt[field]) is None
            for field in scalar_fields
        ):
            self.fail(
                "transport.readback_receipt",
                "saved-draft receipt requires bounded host identifiers",
            )
            return False
        if (
            receipt.get("schema_version") != 1
            or receipt.get("source") != READBACK_RECEIPT_SOURCE
            or receipt.get("signature_algorithm") != "ed25519"
            or not isinstance(receipt.get("nonce"), str)
            or re.fullmatch(r"[0-9a-f]{32,64}", receipt["nonce"]) is None
            or not isinstance(receipt.get("runtime_binding_nonce"), str)
            or re.fullmatch(
                r"[A-Za-z0-9_-]{32,128}", receipt["runtime_binding_nonce"]
            )
            is None
        ):
            self.fail(
                "transport.readback_receipt",
                "saved-draft receipt schema, nonce, or algorithm is invalid",
            )
            return False
        try:
            signature = _host_receipt_signature(receipt.get("signature"))
        except ValueError as exc:
            self.fail("transport.readback_receipt", str(exc))
            return False
        try:
            expected_key_id, public_key = _host_receipt_trust_material()
        except ValueError as exc:
            self.fail("transport.readback_receipt", str(exc))
            return False
        expected_bindings = {
            "key_id": expected_key_id,
            "runtime_binding_nonce": live_receipt.get("runtime_binding_nonce"),
            "runtime_binding_digest": live_receipt.get("runtime_binding_digest"),
            "trusted_bundle_sha256": _trusted_bundle_digest(WORKSPACE_ROOT),
            "target_account_ref": readback.get("target_account_ref"),
            "draft_id": readback.get("draft_id"),
            "title": readback.get("title"),
            "digest": readback.get("digest"),
            "cover_asset_id": readback.get("cover_asset_id"),
            "thumb_media_id": readback.get("thumb_media_id"),
            "cover_hosted_url": (
                readback.get("cover_hosted_derivative", {}).get("url")
                if isinstance(readback.get("cover_hosted_derivative"), dict)
                else None
            ),
            "cover_downloaded_sha256": (
                readback.get("cover_hosted_derivative", {}).get(
                    "downloaded_sha256"
                )
                if isinstance(readback.get("cover_hosted_derivative"), dict)
                else None
            ),
            "cover_downloaded_byte_length": (
                readback.get("cover_hosted_derivative", {}).get(
                    "downloaded_byte_length"
                )
                if isinstance(readback.get("cover_hosted_derivative"), dict)
                else None
            ),
            "handoff_sha256": _asset_digest(self.manifest_path),
            "transport_revision_hash": export.get("revision_hash"),
            "output_html_path_identity_sha256": path_identity_sha256(
                resolved["compiled HTML"]
            ),
            "compiled_html_sha256": _asset_digest(resolved["compiled HTML"]),
            "compile_report_sha256": _asset_digest(resolved["compile report"]),
            "live_receipt_sha256": _asset_digest(resolved["live-root receipt"]),
            "readback_sha256": _asset_digest(resolved["readback"]),
        }
        if any(receipt.get(field) != value for field, value in expected_bindings.items()):
            self.fail(
                "transport.readback_receipt",
                "saved-draft receipt is not bound to this runtime, account, draft, handoff, compile artifact, and readback bytes",
            )
            return False
        try:
            observed_at = _parse_rfc3339(
                receipt.get("observed_at"), label="saved-draft receipt observed_at"
            )
            readback_observed_at = _parse_rfc3339(
                readback.get("observed_at"), label="saved-draft readback"
            )
            expires_at = _parse_rfc3339(
                receipt.get("expires_at"), label="saved-draft receipt expires_at"
            )
        except ValueError as exc:
            self.fail("transport.readback_receipt", str(exc))
            return False
        now = datetime.now(timezone.utc)
        if (
            observed_at != readback_observed_at
            or expires_at <= observed_at
            or (expires_at - observed_at).total_seconds()
            > LIVE_RECEIPT_MAX_TTL_SECONDS
            or observed_at > now + timedelta(seconds=30)
            or now >= expires_at
        ):
            self.fail(
                "transport.readback_receipt",
                "saved-draft receipt time window is stale, future-dated, or not bound to the readback observation",
            )
            return False
        try:
            public_key.verify(signature, _live_receipt_payload(receipt))
        except InvalidSignature:
            self.fail(
                "transport.readback_receipt",
                "saved-draft receipt is not authenticated by the trusted host public key",
            )
            return False
        return not any(
            error["code"] == "transport.readback_receipt"
            for error in self.errors
        )


def _validate_transport_fidelity_contract(
    manifest_path: Path,
    *,
    html_path: Path | None = None,
    intended_html_path: Path | None = None,
    live_root_path: Path | None = None,
    live_receipt_path: Path | None = None,
    require_live_root: bool = False,
    compile_report_path: Path | None = None,
    require_compile_report: bool = False,
    readback_path: Path | None = None,
    readback_receipt_path: Path | None = None,
    require_readback: bool = False,
    expected_target_account_ref: str | None = None,
    diagnostic: bool,
) -> dict[str, Any]:
    """Validate a frozen handoff manifest plus optional compiled/readback evidence.

    The manifest must contain a top-level ``transport_fidelity`` object.  This
    is intentionally separate from a renderer's ordinary article schema so a
    hand-authored HTML approximation cannot silently become publishable.
    """
    if not diagnostic:
        # The private final branch is security-sensitive too; callers cannot
        # bypass the public wrapper by importing this implementation directly.
        _require_secure_transport_finalization_runtime()
    manifest_path = manifest_path.resolve()
    handoff = _read_object(manifest_path, "handoff manifest")
    validator = _Validator(manifest_path)
    if handoff.get("schema_version") != 5:
        validator.fail(
            "transport.mapping",
            "handoff schema_version must be 5; refreeze the current Ardot root",
        )
    fidelity = handoff.get("transport_fidelity")
    export: dict[str, Any] | None = None
    if not isinstance(fidelity, dict):
        validator.fail("transport.mapping", "handoff requires transport_fidelity")
    else:
        if fidelity.get("source") != TRANSPORT_SOURCE:
            validator.fail("transport.mixed_sources", f"transport_fidelity.source must be {TRANSPORT_SOURCE}")
        export = validator.export(fidelity.get("export"))
    if export is not None:
        validator.crosslink_handoff(handoff, export)
    live_root_structural_match = False
    live_receipt_verified = False
    if export is not None and live_root_path is not None:
        live_root_structural_match = validator.live_current_root(
            live_root_path, export
        )
    elif require_live_root:
        validator.fail(
            "transport.current_root_live",
            "a fresh host-owned Ardot current-root export is required for final compilation",
        )
    if (
        export is not None
        and live_root_path is not None
        and live_receipt_path is not None
        and live_root_structural_match
    ):
        receipt_html_path = intended_html_path or html_path
        if receipt_html_path is None:
            validator.fail(
                "transport.current_root_receipt",
                "host receipt verification requires the intended final WeChat HTML path",
            )
        else:
            live_receipt_verified = validator.live_current_root_receipt(
                live_receipt_path,
                live_root_path=live_root_path,
                export=export,
                expected_html_path=receipt_html_path,
            )
    elif require_live_root and live_receipt_path is None and not diagnostic:
        validator.fail(
            "transport.current_root_receipt",
            "a short-lived host-signed receipt for the actual Ardot live read is required",
        )
    current_root_live_verified = (
        live_root_structural_match and live_receipt_verified
    )
    bound_html_path: Path | None = None
    if export is not None and compile_report_path is not None:
        compile_root_ready = (
            live_root_structural_match if diagnostic else current_root_live_verified
        )
        if not compile_root_ready:
            validator.fail(
                "transport.compile_artifact",
                "compile-report verification requires a matching fresh live export"
                + ("" if diagnostic else " and authenticated host receipt"),
            )
        bound_html_path = validator.compile_report(
            compile_report_path,
            export,
            explicit_html_path=html_path,
            live_root_path=live_root_path,
            live_receipt_path=live_receipt_path,
            diagnostic=diagnostic,
        )
    elif require_compile_report:
        validator.fail(
            "transport.compile_artifact",
            "the hash-bound compile report is required before upload or paste",
        )
    effective_html_path = html_path or bound_html_path
    if export is not None and effective_html_path is not None:
        validator.html(effective_html_path.resolve(), export)
    if require_readback and compile_report_path is None:
        validator.fail(
            "transport.compile_artifact",
            "saved-draft readback requires the hash-bound successful compile report",
        )
    if require_readback and (
        not isinstance(expected_target_account_ref, str)
        or not expected_target_account_ref.strip()
        or len(expected_target_account_ref) > 256
        or any(ord(char) < 32 for char in expected_target_account_ref)
    ):
        validator.fail(
            "transport.readback_target",
            "saved-draft verification requires the exact target account from the active delivery preflight",
        )
    if export is not None and readback_path is not None:
        validator.readback(
            readback_path.resolve(),
            export,
            expected_target_account_ref=expected_target_account_ref,
            not_before=validator.bound_compile_observed_at,
        )
    elif require_readback:
        validator.fail("transport.readback", "saved-draft readback is required")
    readback_receipt_verified = False
    if (
        export is not None
        and readback_path is not None
        and readback_receipt_path is not None
        and effective_html_path is not None
        and compile_report_path is not None
        and live_receipt_path is not None
    ):
        readback_receipt_verified = validator.saved_draft_readback_receipt(
            readback_receipt_path,
            readback_path=readback_path,
            compiled_html_path=effective_html_path,
            compile_report_path=compile_report_path,
            live_receipt_path=live_receipt_path,
            export=export,
        )
    elif readback_receipt_path is not None:
        validator.fail(
            "transport.readback_receipt",
            "provided saved-draft receipt cannot be verified without the complete live/compile artifact chain",
        )
    elif require_readback and not diagnostic:
        validator.fail(
            "transport.readback_receipt",
            "saved-draft completion requires the host-signed readback receipt and complete live/compile artifact chain",
        )
    report = {
        "ok": not validator.errors,
        "contract_ok": not validator.errors,
        "source": TRANSPORT_SOURCE,
        "revision_algorithm": TRANSPORT_REVISION_ALGORITHM,
        "revision_hash": export.get("revision_hash") if export else None,
        "html_checked": effective_html_path is not None,
        "live_root_checked": live_root_path is not None,
        "live_root_structural_match": live_root_structural_match,
        "live_receipt_checked": live_receipt_path is not None,
        "contract_current_root_receipt_valid": current_root_live_verified,
        "compile_report_checked": compile_report_path is not None,
        "readback_checked": readback_path is not None,
        "readback_receipt_checked": readback_receipt_path is not None,
        "contract_readback_receipt_valid": readback_receipt_verified,
        "error_codes": sorted({error["code"] for error in validator.errors}),
        "errors": validator.errors,
    }
    if diagnostic:
        session_readback_structural_match = bool(
            require_readback and readback_path is not None and report["ok"]
        )
        report.update(
            {
                "assurance_scope": (
                    "current-session-draft"
                    if validator.bound_session_candidate
                    else "diagnostic-only"
                ),
                "diagnostic_ok": report["ok"],
                "delivery_eligible": False,
                # The unsigned candidate/report can establish structural
                # correspondence, never authority to write.  A current host
                # may perform the reversible draft action only from its own
                # live tool trace and must not serialize that authority here.
                "draft_write_eligible": False,
                "portable_audit_verified": False,
                "publication_preflight_eligible": False,
                "publication_authorized": False,
                "session_live_root_structural_match": live_root_structural_match,
                "session_readback_structural_match": session_readback_structural_match,
                "finalization_verified": False,
                "diagnostic_current_root_receipt_valid": current_root_live_verified,
                "diagnostic_readback_receipt_valid": readback_receipt_verified,
                # These final assurance fields remain false by construction in
                # every ordinary imported diagnostic call.
                "current_root_live_verified": False,
                "readback_receipt_verified": False,
            }
        )
    else:
        portable_audit_verified = (
            report["ok"]
            and require_readback
            and current_root_live_verified
            and compile_report_path is not None
            and effective_html_path is not None
            and readback_path is not None
            and readback_receipt_verified
        )
        report.update(
            {
                "assurance_scope": (
                    "portable-signed-audit"
                    if portable_audit_verified
                    else "portable-signed-draft-preflight"
                ),
                "draft_write_eligible": report["ok"]
                and current_root_live_verified,
                "delivery_eligible": portable_audit_verified,
                "portable_audit_verified": portable_audit_verified,
                "publication_preflight_eligible": portable_audit_verified,
                "publication_authorized": False,
                "finalization_verified": portable_audit_verified,
                "current_root_live_verified": current_root_live_verified,
                "readback_receipt_verified": readback_receipt_verified,
            }
        )
    return report


def validate_transport_fidelity_diagnostic(
    manifest_path: Path,
    *,
    html_path: Path | None = None,
    intended_html_path: Path | None = None,
    live_root_path: Path | None = None,
    live_receipt_path: Path | None = None,
    require_live_root: bool = False,
    compile_report_path: Path | None = None,
    require_compile_report: bool = False,
    readback_path: Path | None = None,
    readback_receipt_path: Path | None = None,
    require_readback: bool = False,
    expected_target_account_ref: str | None = None,
) -> dict[str, Any]:
    """Run current-session structural checks without portable final assurance.

    A matching fresh live root can establish current-session structural
    correspondence, but this unsigned helper always reports
    ``draft_write_eligible=false``, ``delivery_eligible=false`` and
    ``portable_audit_verified=false``; it never turns local JSON into external
    provenance or publication proof. Matching signed receipt details, when
    present, remain diagnostic only.
    """
    return _validate_transport_fidelity_contract(
        manifest_path,
        html_path=html_path,
        intended_html_path=intended_html_path,
        live_root_path=live_root_path,
        live_receipt_path=live_receipt_path,
        require_live_root=require_live_root,
        compile_report_path=compile_report_path,
        require_compile_report=require_compile_report,
        readback_path=readback_path,
        readback_receipt_path=readback_receipt_path,
        require_readback=require_readback,
        expected_target_account_ref=expected_target_account_ref,
        diagnostic=True,
    )


def validate_transport_fidelity(
    manifest_path: Path,
    *,
    html_path: Path | None = None,
    intended_html_path: Path | None = None,
    live_root_path: Path | None = None,
    live_receipt_path: Path | None = None,
    require_live_root: bool = False,
    compile_report_path: Path | None = None,
    require_compile_report: bool = False,
    readback_path: Path | None = None,
    readback_receipt_path: Path | None = None,
    require_readback: bool = False,
    expected_target_account_ref: str | None = None,
) -> dict[str, Any]:
    """Return final transport assurance only inside the isolated runner."""
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/validate_transport_fidelity.py")
    return _validate_transport_fidelity_contract(
        manifest_path,
        html_path=html_path,
        intended_html_path=intended_html_path,
        live_root_path=live_root_path,
        live_receipt_path=live_receipt_path,
        require_live_root=require_live_root,
        compile_report_path=compile_report_path,
        require_compile_report=require_compile_report,
        readback_path=readback_path,
        readback_receipt_path=readback_receipt_path,
        require_readback=require_readback,
        expected_target_account_ref=expected_target_account_ref,
        diagnostic=False,
    )
