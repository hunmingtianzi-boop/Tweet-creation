#!/usr/bin/env python3
"""Validate the fixed workflow credit in an Ardot handoff and draft readback."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/validate_workflow_attribution.py")

from asset_quality import file_sha256
from workflow_quality import (
    WORKFLOW_ATTRIBUTION_MARKER,
    WORKFLOW_ATTRIBUTION_TEXT,
    WORKFLOW_ATTRIBUTION_TEXT_SHA256,
)
try:
    from safe_paths import (
        SafePathError,
        existing_regular_file,
        new_file_path,
        write_text_create_once,
    )
except ImportError:  # package import in repository tests
    from .safe_paths import (  # type: ignore
        SafePathError,
        existing_regular_file,
        new_file_path,
        write_text_create_once,
    )


ARDOT_REVISION_ALGORITHM = "ardot-root-revision-v1"
RUNTIME_ROOT = Path(__file__).resolve().parent.parent


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def normalize_visible_text(value: str) -> str:
    """Collapse transport whitespace without changing visible wording."""
    return re.sub(r"\s+", " ", value).strip()


def _normalized_asset_hash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    digest = value.removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None
    return f"sha256:{digest}"


def current_root_revision_hash(node_export: dict[str, Any]) -> str:
    """Recompute the current-root revision from content, layers, order, and assets."""
    visible_nodes = node_export.get("visible_text_nodes")
    component_order = node_export.get("component_order")
    assets = node_export.get("assets")
    transport_sections = node_export.get("transport_sections")
    body_asset_ids = node_export.get("body_asset_ids")
    if not isinstance(visible_nodes, list):
        visible_nodes = []
    if not isinstance(component_order, list):
        component_order = []
    if not isinstance(assets, list):
        assets = []
    if not isinstance(transport_sections, list):
        transport_sections = []
    if not isinstance(body_asset_ids, list):
        body_asset_ids = []
    normalized_assets = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        normalized_assets.append(
            {
                "id": item.get("id"),
                "sha256": _normalized_asset_hash(item.get("sha256")),
            }
        )
    payload = {
        "algorithm": ARDOT_REVISION_ALGORITHM,
        "file_id": node_export.get("file_id"),
        "root_node_id": node_export.get("root_node_id"),
        "visible_text_nodes": [
            {
                "node_id": item.get("node_id"),
                "component_name": item.get("component_name"),
                "node_kind": item.get("node_kind"),
                "text": normalize_visible_text(item.get("text", ""))
                if isinstance(item, dict) and isinstance(item.get("text"), str)
                else "",
                "native_editable_text": item.get("native_editable_text"),
                "visible": item.get("visible"),
                "rasterized": item.get("rasterized"),
            }
            for item in visible_nodes
            if isinstance(item, dict)
        ],
        "component_order": [
            {
                "node_id": item.get("node_id"),
                "component_name": item.get("component_name"),
            }
            for item in component_order
            if isinstance(item, dict)
        ],
        # This is the complete current-root section/layer census used by the
        # final transport validator.  Keeping it in the independently
        # recomputed root revision prevents geometry/style/source-node evidence
        # from being edited without invalidating the Ardot revision.
        "transport_sections": transport_sections,
        "body_asset_ids": body_asset_ids,
        "assets": sorted(normalized_assets, key=lambda item: str(item.get("id"))),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _local_evidence_path(handoff_path: Path, location: Any) -> Path | None:
    if not isinstance(location, str) or not location or re.match(r"^https?://", location):
        return None
    base = handoff_path.parent.resolve()
    unresolved = base / location
    if unresolved.is_symlink():
        return None
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.is_file() or candidate.is_symlink():
        return None
    return candidate


def validate_workflow_attribution_handoff(
    handoff_path: Path,
    *,
    saved_draft_visible_text_path: Path | None = None,
    require_readback: bool = False,
) -> dict[str, Any]:
    """Derive attribution facts from immutable current-root evidence."""
    handoff_path = handoff_path.resolve()
    handoff = read_object(handoff_path, "handoff")
    errors: list[str] = []

    if handoff.get("schema_version") != 5:
        errors.append(
            "handoff schema_version must be 5; refreeze legacy bundles with transport fidelity"
        )
    ardot = handoff.get("ardot")
    if not isinstance(ardot, dict):
        ardot = {}
        errors.append("handoff requires ardot metadata")
    for field in (
        "file_id",
        "root_node_id",
        "captured_at",
        "revision_algorithm",
        "revision_hash",
    ):
        if not isinstance(ardot.get(field), str) or not ardot.get(field):
            errors.append(f"handoff ardot.{field} is required")
    if ardot.get("revision_algorithm") != ARDOT_REVISION_ALGORITHM:
        errors.append(
            f"handoff ardot.revision_algorithm must be {ARDOT_REVISION_ALGORITHM}"
        )
    if isinstance(ardot.get("revision_hash"), str) and not re.fullmatch(
        r"sha256:[0-9a-f]{64}", ardot["revision_hash"]
    ):
        errors.append("handoff ardot.revision_hash must be sha256:<64 lowercase hex>")

    attribution = handoff.get("workflow_attribution")
    if not isinstance(attribution, dict):
        attribution = {}
        errors.append("handoff requires workflow_attribution")
    expected_text_hash = f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}"
    expected_fields = {
        "policy_id": WORKFLOW_ATTRIBUTION_MARKER,
        "classification": "repository-usage-credit",
        "text": WORKFLOW_ATTRIBUTION_TEXT,
        "text_sha256": expected_text_hash,
        "node_kind": "TEXT",
        "native_editable_text": True,
        "visible": True,
        "terminal": True,
        "organization_identity": False,
        "body_fact": False,
        "visual_reference": False,
    }
    for field, expected in expected_fields.items():
        if attribution.get(field) != expected:
            errors.append(f"workflow_attribution.{field} must equal {expected!r}")
    node_id = attribution.get("ardot_node_id")
    if not isinstance(node_id, str) or not node_id:
        errors.append("workflow_attribution.ardot_node_id is required")
    component_name = attribution.get("component_name")
    if (
        not isinstance(component_name, str)
        or not component_name.startswith("WeChat/Footer/WorkflowAttribution/")
        or not component_name.removeprefix("WeChat/Footer/WorkflowAttribution/")
    ):
        errors.append("workflow_attribution.component_name is invalid")

    evidence_path = _local_evidence_path(
        handoff_path, attribution.get("node_export_file")
    )
    node_export: dict[str, Any] = {}
    if evidence_path is None:
        errors.append(
            "workflow_attribution.node_export_file must be a local non-symlink file inside the handoff directory"
        )
    else:
        expected_export_hash = f"sha256:{file_sha256(evidence_path)}"
        if attribution.get("node_export_sha256") != expected_export_hash:
            errors.append("workflow_attribution.node_export_sha256 does not match the file")
        try:
            node_export = read_object(evidence_path, "Ardot root node export")
        except ValueError as exc:
            errors.append(str(exc))

    if node_export:
        if node_export.get("schema_version") != 1:
            errors.append("Ardot root node export schema_version must be 1")
        if node_export.get("source") != "ardot-current-root-export":
            errors.append("Ardot root node export source must be ardot-current-root-export")
        if node_export.get("revision_algorithm") != ARDOT_REVISION_ALGORITHM:
            errors.append(
                f"Ardot root node export revision_algorithm must be {ARDOT_REVISION_ALGORITHM}"
            )
        for export_field, ardot_field in (
            ("file_id", "file_id"),
            ("root_node_id", "root_node_id"),
            ("captured_at", "captured_at"),
            ("revision_algorithm", "revision_algorithm"),
            ("revision_hash", "revision_hash"),
        ):
            if node_export.get(export_field) != ardot.get(ardot_field):
                errors.append(
                    f"Ardot root node export {export_field} must match handoff ardot.{ardot_field}"
                )
        nodes_raw = node_export.get("visible_text_nodes")
        nodes = (
            [item for item in nodes_raw if isinstance(item, dict)]
            if isinstance(nodes_raw, list)
            else []
        )
        if not nodes or not isinstance(nodes_raw, list) or len(nodes) != len(nodes_raw):
            errors.append("Ardot root node export visible_text_nodes must be a non-empty object array")
        else:
            normalized_texts = [
                normalize_visible_text(item.get("text", ""))
                if isinstance(item.get("text"), str)
                else ""
                for item in nodes
            ]
            combined = " ".join(normalized_texts)
            if combined.count(WORKFLOW_ATTRIBUTION_TEXT) != 1:
                errors.append("Ardot root must contain the exact workflow attribution once")
            target_matches = [item for item in nodes if item.get("node_id") == node_id]
            if len(target_matches) != 1:
                errors.append("workflow attribution node must occur exactly once in the current root")
            else:
                target = target_matches[0]
                derived = {
                    "component_name": target.get("component_name"),
                    "node_kind": target.get("node_kind"),
                    "native_editable_text": target.get("native_editable_text"),
                    "visible": target.get("visible"),
                }
                for field, actual in derived.items():
                    if actual != attribution.get(field):
                        errors.append(
                            f"workflow attribution {field} differs from the current Ardot root export"
                        )
                if target.get("rasterized") is not False:
                    errors.append("workflow attribution node must not be rasterized")
                if normalize_visible_text(str(target.get("text", ""))) != WORKFLOW_ATTRIBUTION_TEXT:
                    errors.append("workflow attribution node text differs from the fixed text")
                if nodes[-1].get("node_id") != node_id:
                    errors.append("workflow attribution node must be last in visible reading order")

        component_order_raw = node_export.get("component_order")
        component_order = (
            [item for item in component_order_raw if isinstance(item, dict)]
            if isinstance(component_order_raw, list)
            else []
        )
        if (
            not component_order
            or not isinstance(component_order_raw, list)
            or len(component_order) != len(component_order_raw)
            or any(
                not isinstance(item.get("node_id"), str)
                or not item.get("node_id")
                or not isinstance(item.get("component_name"), str)
                or not item.get("component_name")
                for item in component_order
            )
        ):
            errors.append("Ardot root node export component_order must be a non-empty node/component array")
        elif (
            component_order[-1].get("node_id") != node_id
            or component_order[-1].get("component_name") != component_name
        ):
            errors.append("workflow attribution component must be last in current-root component order")

        export_assets_raw = node_export.get("assets")
        export_assets = (
            [item for item in export_assets_raw if isinstance(item, dict)]
            if isinstance(export_assets_raw, list)
            else []
        )
        if not isinstance(export_assets_raw, list) or len(export_assets) != len(
            export_assets_raw or []
        ):
            errors.append("Ardot root node export assets must be an array of objects")
        export_asset_map: dict[str, str] = {}
        for index, item in enumerate(export_assets):
            asset_id = item.get("id")
            digest = _normalized_asset_hash(item.get("sha256"))
            if not isinstance(asset_id, str) or not asset_id or digest is None:
                errors.append(f"Ardot root node export asset {index} requires id and SHA-256")
            elif asset_id in export_asset_map:
                errors.append(f"Ardot root node export duplicates asset id: {asset_id}")
            else:
                export_asset_map[asset_id] = digest

        handoff_assets_raw = handoff.get("assets")
        handoff_assets = (
            [item for item in handoff_assets_raw if isinstance(item, dict)]
            if isinstance(handoff_assets_raw, list)
            else []
        )
        if not isinstance(handoff_assets_raw, list) or len(handoff_assets) != len(
            handoff_assets_raw or []
        ):
            errors.append("handoff assets must be an array of objects")
        handoff_asset_map: dict[str, str] = {}
        for index, item in enumerate(handoff_assets):
            asset_id = item.get("id")
            digest = _normalized_asset_hash(item.get("sha256"))
            if not isinstance(asset_id, str) or not asset_id or digest is None:
                errors.append(f"handoff asset {index} requires id and SHA-256")
            elif asset_id in handoff_asset_map:
                errors.append(f"handoff duplicates asset id: {asset_id}")
            else:
                handoff_asset_map[asset_id] = digest
                asset_path = _local_evidence_path(handoff_path, item.get("path"))
                if asset_path is None:
                    errors.append(
                        f"handoff asset {asset_id} path must be a local non-symlink file inside the handoff directory"
                    )
                elif f"sha256:{file_sha256(asset_path)}" != digest:
                    errors.append(f"handoff asset {asset_id} SHA-256 does not match its file")
        if export_asset_map != handoff_asset_map:
            errors.append("Ardot root node export assets must match handoff assets")

        recomputed_revision_hash = current_root_revision_hash(node_export)
        if node_export.get("revision_hash") != recomputed_revision_hash:
            errors.append(
                "Ardot root node export revision_hash does not match recomputed current-root content/layers/order/assets"
            )
        if ardot.get("revision_hash") != recomputed_revision_hash:
            errors.append(
                "handoff ardot.revision_hash does not match recomputed current-root content/layers/order/assets"
            )

    ardot_evidence_ready = not errors
    readback = {
        "required": require_readback,
        "provided": saved_draft_visible_text_path is not None,
        "present_once": False,
        "terminal": False,
        "ready": not require_readback,
    }
    if saved_draft_visible_text_path is not None:
        try:
            raw_readback = saved_draft_visible_text_path.resolve().read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, UnicodeError) as exc:
            errors.append(f"saved-draft visible-text readback is unavailable: {exc}")
        else:
            normalized_readback = normalize_visible_text(raw_readback)
            readback["present_once"] = normalized_readback.count(WORKFLOW_ATTRIBUTION_TEXT) == 1
            readback["terminal"] = normalized_readback.endswith(WORKFLOW_ATTRIBUTION_TEXT)
            readback["ready"] = readback["present_once"] and readback["terminal"]
            if not readback["present_once"]:
                errors.append("saved draft must contain the exact workflow attribution once")
            if not readback["terminal"]:
                errors.append("saved draft must end with the exact workflow attribution")
    elif require_readback:
        errors.append("saved-draft visible-text readback is required")

    return {
        "ok": not errors,
        "schema_version": handoff.get("schema_version"),
        "policy_id": WORKFLOW_ATTRIBUTION_MARKER,
        "text_sha256": expected_text_hash,
        "ardot_evidence_ready": ardot_evidence_ready,
        "readback": readback,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--saved-draft-visible-text", type=Path)
    parser.add_argument("--require-readback", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        handoff = existing_regular_file(args.handoff, label="handoff")
        saved_draft_visible_text = (
            existing_regular_file(
                args.saved_draft_visible_text,
                label="saved draft visible text",
            )
            if args.saved_draft_visible_text is not None
            else None
        )
        report_path = (
            new_file_path(
                args.report,
                label="workflow attribution report",
                forbidden_root=RUNTIME_ROOT,
            )
            if args.report is not None
            else None
        )
        report = validate_workflow_attribution_handoff(
            handoff,
            saved_draft_visible_text_path=saved_draft_visible_text,
            require_readback=args.require_readback,
        )
    except (SafePathError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if report_path is not None:
        try:
            write_text_create_once(
                report_path,
                payload,
                label="workflow attribution report",
                forbidden_root=RUNTIME_ROOT,
            )
        except SafePathError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    print(payload, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
