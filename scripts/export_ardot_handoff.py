#!/usr/bin/env python3
"""Deterministically freeze a normalized Ardot host export as handoff v5.

The host adapter, not an LLM, supplies ``ardot-host-normalized-export-v1``.
This exporter copies every payload by SHA, derives the current-root/layer
revision graph, generates background/interaction evidence, and emits a
readback *skeleton* explicitly marked as non-evidence.  It never accepts a
previous article or an HTML approximation as input.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    from secure_runtime import require_secure_runtime

    require_secure_runtime("scripts/export_ardot_handoff.py")

from asset_quality import file_sha256
try:
    from safe_paths import (
        SafePathError,
        existing_regular_file,
        new_directory_path,
    )
except ImportError:  # package import in repository tests
    from .safe_paths import (  # type: ignore
        SafePathError,
        existing_regular_file,
        new_directory_path,
    )
from transport_fidelity import (
    CURRENT_ROOT_SOURCE,
    TRANSPORT_REVISION_ALGORITHM,
    TRANSPORT_SOURCE,
    canonical_html_fragment_sha256,
    canonical_svg_structure_sha256,
    canonical_transport_revision_hash,
    current_root_transport_snapshot,
    text_sha256,
)
from validate_workflow_attribution import (
    ARDOT_REVISION_ALGORITHM,
    current_root_revision_hash,
)
from workflow_quality import (
    WORKFLOW_ATTRIBUTION_MARKER,
    WORKFLOW_ATTRIBUTION_TEXT,
    WORKFLOW_ATTRIBUTION_TEXT_SHA256,
)


NORMALIZED_SOURCE = "ardot-host-normalized-export-v1"
READBACK_SKELETON_SOURCE = "wechat-readback-capture-skeleton-v2"
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")
AT_FDCWD = -100
RENAME_NOREPLACE = 1
RENAME_EXCL = 0x00000004


class ExclusiveRenameUnsupported(RuntimeError):
    """Raised when the host cannot make an atomic create-once rename."""


def _exclusive_rename(
    source: Path,
    destination: Path,
    *,
    platform_name: str | None = None,
    libc: Any | None = None,
) -> None:
    """Atomically rename ``source`` only when ``destination`` is absent.

    There is deliberately no ``os.rename`` fallback: a check-then-rename pair
    can overwrite a file or directory created by another process in between.
    Unsupported platforms, C libraries, kernels, or filesystems therefore fail
    closed and leave the source at its staging path.

    ``platform_name`` and ``libc`` are private test seams used to exercise both
    supported host ABIs without weakening the production call.
    """

    platform_name = sys.platform if platform_name is None else platform_name
    libc = ctypes.CDLL(None, use_errno=True) if libc is None else libc
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)

    if platform_name == "darwin":
        try:
            rename = libc.renamex_np
        except AttributeError as exc:
            raise ExclusiveRenameUnsupported(
                "macOS libc does not expose renamex_np(RENAME_EXCL)"
            ) from exc
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(source_bytes, destination_bytes, RENAME_EXCL)
        primitive = "renamex_np(RENAME_EXCL)"
    elif platform_name.startswith("linux"):
        try:
            rename = libc.renameat2
        except AttributeError as exc:
            raise ExclusiveRenameUnsupported(
                "Linux libc does not expose renameat2(RENAME_NOREPLACE)"
            ) from exc
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(
            AT_FDCWD,
            source_bytes,
            AT_FDCWD,
            destination_bytes,
            RENAME_NOREPLACE,
        )
        primitive = "renameat2(RENAME_NOREPLACE)"
    else:
        raise ExclusiveRenameUnsupported(
            f"atomic create-once rename is unsupported on {platform_name!r}"
        )

    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(
            error_number,
            os.strerror(error_number),
            os.fspath(destination),
        )
    unsupported_errors = {
        errno.ENOSYS,
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    if error_number in unsupported_errors:
        raise ExclusiveRenameUnsupported(
            f"host does not support {primitive}: {os.strerror(error_number)}"
        )
    raise OSError(
        error_number,
        os.strerror(error_number),
        os.fspath(destination),
    )


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _sha(path: Path) -> str:
    return "sha256:" + file_sha256(path)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite frozen evidence: {path}")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        _exclusive_rename(temporary, path)
    except FileExistsError as exc:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"frozen evidence collision: {path}") from exc
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class Exporter:
    def __init__(self, source_path: Path, output_dir: Path, *, bindings_path: Path | None = None) -> None:
        # The programmatic exporter is a formal freeze entrypoint too.  Do not
        # let an ordinary import bypass the reviewed scripts/dependency census.
        from secure_runtime import require_secure_runtime

        require_secure_runtime("scripts/export_ardot_handoff.py")
        try:
            self.source_path = existing_regular_file(
                source_path, label="normalized Ardot export"
            )
            self.final_output_dir = new_directory_path(
                output_dir,
                label="handoff output directory",
                forbidden_root=Path(__file__).resolve().parent.parent,
            )
        except SafePathError as exc:
            raise ValueError(str(exc)) from exc
        self.source_root = self.source_path.parent
        parent = self.final_output_dir.parent
        self.output_dir = parent / f".{self.final_output_dir.name}.{uuid.uuid4().hex}.staging"
        self.payload = _read_object(self.source_path, "normalized Ardot export")
        self.semantic_bindings = None
        if bindings_path is not None:
            from ardot_capture_adapter import normalize_capture
            bindings_path = existing_regular_file(bindings_path, label="Ardot semantic bindings")
            self.semantic_bindings = _read_object(bindings_path, "Ardot semantic bindings")
            self.payload = normalize_capture(self.payload, self.semantic_bindings)
        if (
            self.payload.get("schema_version") != 1
            or self.payload.get("source") != NORMALIZED_SOURCE
        ):
            raise ValueError(
                f"normalized export must use schema_version=1 and source={NORMALIZED_SOURCE}"
            )
        raw_assets = self.payload.get("assets")
        if not isinstance(raw_assets, list) or any(
            not isinstance(item, dict) for item in raw_assets
        ):
            raise ValueError("normalized export assets must be an object array")
        self.assets: dict[str, dict[str, Any]] = {}
        for item in raw_assets:
            asset_id = item.get("id")
            if not isinstance(asset_id, str) or not asset_id or asset_id in self.assets:
                raise ValueError("normalized assets require unique non-empty ids")
            self.assets[asset_id] = item
        self.frozen_assets: dict[str, dict[str, Any]] = {}
        captured_at = self.payload.get("ardot", {}).get("captured_at")
        declared_root_algorithm = self.payload.get("ardot", {}).get(
            "revision_algorithm", ARDOT_REVISION_ALGORITHM
        )
        if declared_root_algorithm != ARDOT_REVISION_ALGORITHM:
            raise ValueError(
                "normalized Ardot revision_algorithm must be "
                f"{ARDOT_REVISION_ALGORITHM}"
            )
        if not isinstance(captured_at, str):
            raise ValueError("normalized Ardot captured_at is required")
        try:
            parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("normalized Ardot captured_at must be RFC3339") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("normalized Ardot captured_at must include timezone")
        parsed = parsed.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if parsed > now + timedelta(seconds=30) or now - parsed > timedelta(hours=1):
            raise ValueError("normalized Ardot capture must be fresh and not future-dated")
        self.output_dir.mkdir(mode=0o700)

    def _source_asset_path(self, asset: dict[str, Any]) -> Path:
        location = asset.get("path")
        if not isinstance(location, str) or not location:
            raise ValueError(f"asset {asset.get('id')} requires path")
        candidate = Path(location)
        if not candidate.is_absolute():
            candidate = self.source_root / candidate
        try:
            return existing_regular_file(
                candidate, label=f"asset {asset.get('id')}"
            )
        except SafePathError as exc:
            raise ValueError(str(exc)) from exc

    def freeze_asset(self, asset_id: str) -> dict[str, Any]:
        cached = self.frozen_assets.get(asset_id)
        if cached is not None:
            return dict(cached)
        source = self.assets.get(asset_id)
        if source is None:
            raise ValueError(f"unknown normalized asset: {asset_id}")
        source_path = self._source_asset_path(source)
        digest = _sha(source_path)
        declared = source.get("sha256")
        if declared is not None and declared != digest:
            raise ValueError(f"asset {asset_id} SHA differs from host export")
        slug = SAFE_ID.sub("-", asset_id).strip("-.") or "asset"
        destination = (
            self.output_dir
            / "assets"
            / f"{slug}-{digest.removeprefix('sha256:')[:12]}{source_path.suffix.lower()}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"asset destination collision: {asset_id}")
        source_descriptor = os.open(
            source_path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            source_stat = os.fstat(source_descriptor)
            if not stat.S_ISREG(source_stat.st_mode):
                raise ValueError(f"asset {asset_id} must be a regular file")
            with os.fdopen(source_descriptor, "rb", closefd=False) as source_handle, os.fdopen(
                destination_descriptor, "wb", closefd=False
            ) as destination_handle:
                shutil.copyfileobj(source_handle, destination_handle)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
        finally:
            os.close(source_descriptor)
            os.close(destination_descriptor)
        if _sha(destination) != digest or destination.stat().st_size != source_stat.st_size:
            raise ValueError(f"asset {asset_id} copy readback differs from source")
        frozen = {
            key: value
            for key, value in source.items()
            if key not in {"id", "path", "sha256"}
        }
        frozen.update(
            {
                "asset_id": asset_id,
                "path": destination.relative_to(self.output_dir).as_posix(),
                "sha256": digest,
            }
        )
        self.frozen_assets[asset_id] = frozen
        return dict(frozen)

    def _layer_asset(self, raw: Any, label: str) -> dict[str, Any]:
        if not isinstance(raw, dict) or not isinstance(raw.get("asset_id"), str):
            raise ValueError(f"{label} requires asset_id plus Ardot geometry/style")
        asset = self.freeze_asset(raw["asset_id"])
        asset.update({key: value for key, value in raw.items() if key != "asset_id"})
        return asset

    def _background_evidence(
        self,
        chapter: dict[str, Any],
        background: dict[str, Any],
        *,
        file_id: str,
        root_node_id: str,
    ) -> None:
        evidence = {
            "source": "ardot-background-only-node-export-v1",
            "file_id": file_id,
            "root_node_id": root_node_id,
            "section_node_id": chapter["section_node_id"],
            "source_node_id": background["source_node_id"],
            "asset_id": background["asset_id"],
            "asset_sha256": background["sha256"],
            "text_descendant_count": 0,
            "text_descendant_node_ids": [],
            "width_px": background["width_px"],
            "height_px": background["height_px"],
            "export_scale": background["export_scale"],
        }
        path = (
            self.output_dir
            / "qa"
            / f"background-{SAFE_ID.sub('-', str(background['source_node_id']))}.json"
        )
        _atomic_json(path, evidence)
        background["background_node_export"] = {
            "path": path.relative_to(self.output_dir).as_posix(),
            "sha256": _sha(path),
        }

    def _interaction(
        self,
        raw: dict[str, Any],
        *,
        chapter: dict[str, Any],
        file_id: str,
        root_node_id: str,
    ) -> dict[str, Any]:
        item = dict(raw)
        mode = item.get("mode")
        if mode == "svg":
            svg = self.freeze_asset(str(item.pop("svg_asset_id")))
            svg_path = self.output_dir / svg["path"]
            structure = canonical_svg_structure_sha256(
                svg_path.read_text(encoding="utf-8")
            )
            nested_ids = item.pop("asset_ids", [])
            if nested_ids:
                svg["assets"] = [self.freeze_asset(str(value)) for value in nested_ids]
            item["svg"] = svg
            structure_field = "svg_structure_sha256"
        elif mode == "horizontal-swipe":
            swipe = self.freeze_asset(str(item.pop("swipe_asset_id")))
            swipe_path = self.output_dir / swipe["path"]
            structure = canonical_html_fragment_sha256(
                swipe_path.read_text(encoding="utf-8")
            )
            nested_ids = item.pop("asset_ids", [])
            if nested_ids:
                swipe["assets"] = [
                    self.freeze_asset(str(value)) for value in nested_ids
                ]
            item["swipe"] = swipe
            structure_field = "interaction_structure_sha256"
        elif mode == "static-fallback":
            structure = str(item.get("fallback_semantic_sha256"))
            structure_field = "interaction_structure_sha256"
        else:
            raise ValueError(f"unsupported normalized interaction mode: {mode}")
        item["fallback_asset"] = self.freeze_asset(
            str(item.pop("fallback_asset_id"))
        )
        item["structure_sha256"] = structure
        if mode != "static-fallback":
            evidence = {
                "source": "ardot-interaction-state-export-v1",
                "file_id": file_id,
                "root_node_id": root_node_id,
                "section_node_id": chapter["section_node_id"],
                "source_node_id": item["source_node_id"],
                structure_field: structure,
                "states": [
                    {
                        "name": name,
                        "node_id": item["ardot_states"][name]["node_id"],
                        "tree_sha256": item["ardot_states"][name]["tree_sha256"],
                    }
                    for name in ("closed", "open", "fallback")
                ],
            }
            evidence_path = (
                self.output_dir
                / "qa"
                / f"interaction-{SAFE_ID.sub('-', str(item['source_node_id']))}.json"
            )
            _atomic_json(evidence_path, evidence)
            item["ardot_state_export"] = {
                "path": evidence_path.relative_to(self.output_dir).as_posix(),
                "sha256": _sha(evidence_path),
            }
            item["ardot_state_sha256"] = _sha(evidence_path)
            item["authored_from"] = "ardot-state-export-v1"
        return item

    def _build(self) -> dict[str, Any]:
        ardot = self.payload.get("ardot")
        article = self.payload.get("article")
        chapters = self.payload.get("chapters")
        if not isinstance(ardot, dict) or not isinstance(article, dict):
            raise ValueError("normalized export requires article and ardot objects")
        if not isinstance(chapters, list) or not chapters:
            raise ValueError("normalized export requires non-empty chapters")
        file_id = str(ardot.get("file_id", ""))
        root_node_id = str(ardot.get("root_node_id", ""))
        if not file_id or not root_node_id:
            raise ValueError("normalized Ardot file_id/root_node_id are required")
        rendered_chapters: list[dict[str, Any]] = []
        expected_y = 0.0
        for index, raw in enumerate(chapters, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"chapter {index} must be an object")
            chapter = dict(raw)
            chapter["source"] = TRANSPORT_SOURCE
            chapter["order"] = index
            chapter.setdefault("geometry_space", "article-root-390-v1")
            geometry = chapter.get("geometry")
            if not isinstance(geometry, dict) or geometry.get("x") != 0 or geometry.get("width") != 390:
                raise ValueError(f"chapter {index} requires exact 390 px root geometry")
            if float(geometry.get("y", -1)) != expected_y:
                raise ValueError("normalized chapters must be contiguous and ordered")
            expected_y += float(geometry.get("height", 0))
            background = self._layer_asset(
                chapter.get("background_layer"), f"chapter {index} background"
            )
            self._background_evidence(
                chapter,
                background,
                file_id=file_id,
                root_node_id=root_node_id,
            )
            chapter["background_layer"] = background
            chapter["decorations"] = [
                self._layer_asset(item, f"chapter {index} decoration")
                for item in chapter.get("decorations", [])
            ]
            chapter["photos"] = [
                self._layer_asset(item, f"chapter {index} photo")
                for item in chapter.get("photos", [])
            ]
            reference = chapter.get("reference_screenshot")
            chapter["reference_screenshot"] = self._layer_asset(
                reference, f"chapter {index} reference screenshot"
            )
            nodes = chapter.get("visible_text_nodes")
            if not isinstance(nodes, list):
                raise ValueError(f"chapter {index} visible_text_nodes must be an array")
            for order, node in enumerate(nodes, start=1):
                if not isinstance(node, dict) or not isinstance(node.get("text"), str):
                    raise ValueError(f"chapter {index} text node {order} is invalid")
                node["order"] = order
                node["text_sha256"] = text_sha256(node["text"])
            interactions = chapter.get("interaction")
            items = interactions if isinstance(interactions, list) else [interactions]
            normalized_interactions = [
                self._interaction(
                    item,
                    chapter=chapter,
                    file_id=file_id,
                    root_node_id=root_node_id,
                )
                for item in items
                if isinstance(item, dict)
            ]
            chapter["interaction"] = (
                normalized_interactions
                if isinstance(interactions, list)
                else normalized_interactions[0]
                if normalized_interactions
                else None
            )
            rendered_chapters.append(chapter)

        export = {
            "source": TRANSPORT_SOURCE,
            "revision_algorithm": TRANSPORT_REVISION_ALGORITHM,
            "file_id": file_id,
            "root_node_id": root_node_id,
            "artboard": {"width_px": 390, "height_px": round(expected_y)},
            "chapters": rendered_chapters,
        }
        current_root = {
            "schema_version": 1,
            "source": CURRENT_ROOT_SOURCE,
            "file_id": file_id,
            "root_node_id": root_node_id,
            "captured_at": ardot.get("captured_at"),
            "revision_algorithm": ARDOT_REVISION_ALGORITHM,
            "visible_text_nodes": [
                {
                    "node_id": node["node_id"],
                    "component_name": node.get("component_name"),
                    "node_kind": "TEXT",
                    "text": node["text"],
                    "native_editable_text": True,
                    "visible": True,
                    "rasterized": False,
                }
                for chapter in rendered_chapters
                for node in chapter["visible_text_nodes"]
            ],
            "component_order": self.payload.get("component_order", []),
            "assets": [
                {"id": asset_id, "sha256": asset["sha256"]}
                for asset_id, asset in sorted(self.frozen_assets.items())
            ],
        }
        snapshot = current_root_transport_snapshot(export)
        current_root["transport_sections"] = snapshot["sections"]
        current_root["body_asset_ids"] = snapshot["body_asset_ids"]
        root_revision = current_root_revision_hash(current_root)
        current_root["revision_hash"] = root_revision
        export["current_root_revision_hash"] = root_revision
        export["revision_hash"] = canonical_transport_revision_hash(export)
        root_path = self.output_dir / "qa" / "ardot-root-nodes.json"
        _atomic_json(root_path, current_root)

        top_assets = []
        for asset_id, frozen in sorted(self.frozen_assets.items()):
            source = self.assets[asset_id]
            top_assets.append(
                {
                    "id": asset_id,
                    "path": frozen["path"],
                    "sha256": frozen["sha256"],
                    **{
                        key: value
                        for key, value in source.items()
                        if key not in {"id", "path", "sha256"}
                    },
                }
            )
        all_text_nodes = [
            node
            for chapter in rendered_chapters
            for node in chapter["visible_text_nodes"]
        ]
        attribution_nodes = [
            node
            for node in all_text_nodes
            if node.get("semantic_role") == "workflow-attribution"
            and node.get("text") == WORKFLOW_ATTRIBUTION_TEXT
        ]
        if len(attribution_nodes) != 1 or all_text_nodes[-1] is not attribution_nodes[0]:
            raise ValueError(
                "current Ardot root requires exactly one globally terminal workflow attribution"
            )
        attribution_node = attribution_nodes[0]
        component_order = self.payload.get("component_order")
        if (
            not isinstance(component_order, list)
            or not component_order
            or not isinstance(component_order[-1], dict)
            or component_order[-1].get("node_id") != attribution_node.get("node_id")
            or sum(
                1
                for item in component_order
                if isinstance(item, dict)
                and item.get("node_id") == attribution_node.get("node_id")
            )
            != 1
        ):
            raise ValueError(
                "workflow attribution must also be the unique last current-root component"
            )
        attribution = {
            "policy_id": WORKFLOW_ATTRIBUTION_MARKER,
            "classification": "repository-usage-credit",
            "text": WORKFLOW_ATTRIBUTION_TEXT,
            "text_sha256": f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}",
            "ardot_node_id": attribution_node["node_id"],
            "component_name": attribution_node.get("component_name"),
            "node_kind": "TEXT",
            "native_editable_text": True,
            "visible": True,
            "terminal": True,
            "organization_identity": False,
            "body_fact": False,
            "visual_reference": False,
            "node_export_file": root_path.relative_to(self.output_dir).as_posix(),
            "node_export_sha256": _sha(root_path),
        }
        handoff = {
            "schema_version": 5,
            "article": article,
            "ardot": {
                **ardot,
                "revision_hash": root_revision,
            },
            "workflow_attribution": attribution,
            "assets": top_assets,
            "transport_fidelity": {"source": TRANSPORT_SOURCE, "export": export},
        }
        if "capture_binding" in self.payload:
            _atomic_json(self.output_dir / "qa" / "raw-ardot-capture.json", _read_object(self.source_path, "raw capture"))
            _atomic_json(self.output_dir / "qa" / "semantic-bindings.json", self.semantic_bindings)
            handoff["capture_binding"] = self.payload["capture_binding"]
        from production_intent import freeze_intent, validate_delivery_intent
        handoff["production_intent"] = freeze_intent(article, export)
        intent_errors = validate_delivery_intent(handoff, export)
        if intent_errors:
            raise ValueError("; ".join(intent_errors))
        handoff_path = self.output_dir / "handoff.json"
        _atomic_json(handoff_path, handoff)
        skeleton = {
            "schema_version": 2,
            "source": READBACK_SKELETON_SOURCE,
            "evidence_state": "not-captured",
            "may_satisfy_readback_gate": False,
            "handoff_sha256": _sha(handoff_path),
            "transport_revision_hash": export["revision_hash"],
            "raw_draft": None,
            "cover_hosted_derivative": None,
            "chapters": [
                {
                    "chapter_id": chapter["chapter_id"],
                    "section_node_id": chapter["section_node_id"],
                    "visible_text_node_ids": [
                        node["node_id"] for node in chapter["visible_text_nodes"]
                    ],
                    "asset_ids": sorted(
                        {
                            chapter["background_layer"]["asset_id"],
                            *(item["asset_id"] for item in chapter["decorations"]),
                            *(item["asset_id"] for item in chapter["photos"]),
                        }
                    ),
                    "hosted_assets": [],
                    "screenshot": None,
                    "ardot_reference_screenshot": chapter["reference_screenshot"][
                        "asset_id"
                    ],
                    "interactions": [],
                }
                for chapter in rendered_chapters
            ],
        }
        skeleton_path = self.output_dir / "qa" / "readback-skeleton.json"
        _atomic_json(skeleton_path, skeleton)
        return {
            "schema_version": 1,
            "source": "ardot-handoff-export-report-v1",
            "ok": True,
            "handoff": handoff_path.name,
            "handoff_sha256": _sha(handoff_path),
            "current_root": root_path.relative_to(self.output_dir).as_posix(),
            "readback_skeleton": skeleton_path.relative_to(self.output_dir).as_posix(),
            "transport_revision_hash": export["revision_hash"],
        }

    def run(self) -> dict[str, Any]:
        try:
            # Freeze a cover even when it is not a visible body layer.
            cover_id = self.payload.get("article", {}).get("cover_asset_id")
            if not isinstance(cover_id, str) or cover_id not in self.assets:
                raise ValueError("normalized article requires a registered cover_asset_id")
            self.freeze_asset(cover_id)
            report = self._build()
            for root, directories, files in os.walk(self.output_dir):
                for name in (*directories, *files):
                    candidate = Path(root) / name
                    if candidate.is_symlink():
                        raise ValueError("staged handoff must not contain symlinks")
                directory_descriptor = os.open(root, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
            # Same-filesystem no-replace rename gives consumers an all-or-nothing
            # tree and closes the race between an absence check and commit.
            try:
                _exclusive_rename(self.output_dir, self.final_output_dir)
            except FileExistsError as exc:
                raise ValueError(
                    "handoff output appeared during export; refusing overwrite"
                ) from exc
            return report
        except Exception:
            if self.output_dir.is_dir() and not self.output_dir.is_symlink():
                shutil.rmtree(self.output_dir)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normalized_export", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, help="Normalize the input raw resolved Ardot capture using semantic-only bindings")
    args = parser.parse_args()
    report = Exporter(args.normalized_export, args.output, bindings_path=args.bindings).run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
