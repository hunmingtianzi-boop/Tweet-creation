from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import transport_fidelity as transport_fidelity_module  # noqa: E402
from transport_fidelity import (  # noqa: E402
    LIVE_RECEIPT_SOURCE,
    READBACK_RECEIPT_SOURCE,
    READBACK_SOURCE,
    TRANSPORT_REVISION_ALGORITHM,
    TRANSPORT_SOURCE,
    canonical_svg_structure_sha256,
    canonical_transport_revision_hash,
    current_root_transport_snapshot,
    path_identity_sha256,
    text_sha256,
    validate_transport_fidelity,
    validate_transport_fidelity_diagnostic,
)
from runtime_preflight import _trusted_bundle_digest  # noqa: E402
from compile_wechat import (  # noqa: E402
    _compile_frozen_transport_contract,
    compile_frozen_session_draft,
    compile_frozen_transport,
    compile_frozen_transport_candidate,
)
from asset_quality import file_sha256  # noqa: E402
from validate_workflow_attribution import (  # noqa: E402
    ARDOT_REVISION_ALGORITHM,
    current_root_revision_hash,
)
from workflow_quality import (  # noqa: E402
    WORKFLOW_ATTRIBUTION_MARKER,
    WORKFLOW_ATTRIBUTION_TEXT,
    WORKFLOW_ATTRIBUTION_TEXT_SHA256,
)

ORIGINAL_HOST_RECEIPT_TRUST_MATERIAL = (
    transport_fidelity_module._host_receipt_trust_material
)


def write_png(path: Path, width: int, height: int, *, alpha: bool) -> None:
    """Write a small deterministic RGBA/RGB PNG using only the stdlib."""
    color_type, channels = (6, 4) if alpha else (2, 3)
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            row.extend((36, 88, 120))
            if alpha:
                nx = (x - (width - 1) / 2) / (width * 0.46)
                ny = (y - (height - 1) / 2) / (height * 0.46)
                row.append(255 if nx * nx + ny * ny <= 1 else 0)
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + kind
            + payload
            + zlib.crc32(kind + payload).to_bytes(4, "big")
        )

    ihdr = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes((8, color_type, 0, 0, 0))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


def write_organic_cutout(path: Path, width: int, height: int) -> None:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((28, 20, 214, 160), fill=(42, 126, 184, 255))
    draw.ellipse((130, 48, 274, 154), fill=(228, 132, 52, 255))
    draw.polygon(((58, 42), (16, 88), (92, 118)), fill=(54, 154, 112, 255))
    image.save(path)


class TransportFidelityTests(unittest.TestCase):
    LIVE_RECEIPT_PRIVATE_KEY = Ed25519PrivateKey.generate()
    LIVE_RECEIPT_PUBLIC_KEY = LIVE_RECEIPT_PRIVATE_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    def setUp(self) -> None:
        self.trust_material = patch(
            "transport_fidelity._host_receipt_trust_material",
            return_value=(
                "test-host-receipt-key",
                self.LIVE_RECEIPT_PRIVATE_KEY.public_key(),
            ),
        )
        self.trust_material.start()
        self.addCleanup(self.trust_material.stop)

    def test_environment_public_key_and_user_owned_trust_store_cannot_be_trust_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trust_store = Path(directory) / "trust.json"
            trust_store.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "org-wechat-host-receipt-trust-store",
                        "key_id": "attacker-selected-key",
                        "public_key": "hex:" + self.LIVE_RECEIPT_PUBLIC_KEY.hex(),
                        "allowed_receipt_sources": [
                            LIVE_RECEIPT_SOURCE,
                            READBACK_RECEIPT_SOURCE,
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "ORG_WECHAT_HOST_RECEIPT_PUBLIC_KEY": "hex:"
                    + self.LIVE_RECEIPT_PUBLIC_KEY.hex(),
                    "ORG_WECHAT_HOST_RECEIPT_TRUST_STORE": str(trust_store),
                },
                clear=False,
            ):
                with self.assertRaisesRegex(ValueError, r"root|trust boundary|symlink"):
                    ORIGINAL_HOST_RECEIPT_TRUST_MATERIAL()

    def test_acl_write_access_to_apparently_root_owned_trust_store_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trust_store = Path(directory) / "trust.json"
            trust_store.write_text("{}", encoding="utf-8")
            protected_metadata = Mock(st_uid=0, st_mode=0o100444)
            with (
                patch.dict(
                    os.environ,
                    {"ORG_WECHAT_HOST_RECEIPT_TRUST_STORE": str(trust_store)},
                    clear=False,
                ),
                patch.object(transport_fidelity_module.os, "geteuid", return_value=501),
                patch.object(Path, "lstat", return_value=protected_metadata),
                patch.object(transport_fidelity_module.os, "access", return_value=True),
            ):
                with self.assertRaisesRegex(ValueError, "ACL or effective write access"):
                    ORIGINAL_HOST_RECEIPT_TRUST_MATERIAL()

    def make_bundle(self) -> tuple[tempfile.TemporaryDirectory[str], Path, dict]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        write_png(root / "background.png", 1170, 360, alpha=False)
        write_organic_cutout(root / "motif.png", 300, 180)
        write_png(root / "fallback.png", 120, 40, alpha=False)
        write_png(root / "cover.png", 900, 383, alpha=False)
        write_png(root / "ardot-chapter-1.png", 390, 120, alpha=False)
        fallback_semantic_sha256 = "sha256:" + "7" * 64
        svg_text = (
            "<svg data-interaction='svg-smil-self' "
            "data-policy-version='wechat-svg-smil-self-v1' "
            "data-fallback-key='toggle-1' "
            f"data-fallback-hash='{fallback_semantic_sha256}' viewBox='0 0 10 10'>"
            "<rect width='10' height='10'><set attributeName='opacity' "
            "to='0' begin='click'/></rect></svg>"
        )
        (root / "interaction.svg").write_text(svg_text, encoding="utf-8")

        def asset(asset_id: str, name: str, **extra: object) -> dict:
            data = (root / name).read_bytes()
            return {
                "asset_id": asset_id,
                "path": name,
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                **extra,
            }

        background = asset(
            "chapter-1-background", "background.png", width_px=1170, export_scale=3,
            height_px=360, contains_text=False, text_baked=False, text_node_count=0,
            source_node_id="9:2", z_index=0,
            render_style={
                "object_fit": "cover",
                "object_position": "50% 50%",
                "opacity": 1,
                "rotation_deg": 0,
                "blend_mode": "normal",
                "mask": "none",
            },
        )
        background_export_path = root / "qa" / "background-9-2.json"
        background_export_path.parent.mkdir(parents=True, exist_ok=True)
        background_export = {
            "source": "ardot-background-only-node-export-v1",
            "file_id": "file-1",
            "root_node_id": "1:1",
            "section_node_id": "9:1",
            "source_node_id": "9:2",
            "asset_id": background["asset_id"],
            "asset_sha256": background["sha256"],
            "text_descendant_count": 0,
            "text_descendant_node_ids": [],
            "width_px": 1170,
            "height_px": 360,
            "export_scale": 3,
        }
        background_export_path.write_text(
            json.dumps(background_export, ensure_ascii=False), encoding="utf-8"
        )
        background["background_node_export"] = {
            "path": "qa/background-9-2.json",
            "sha256": "sha256:" + file_sha256(background_export_path),
        }
        decoration = asset(
            "chapter-1-motif",
            "motif.png",
            alpha=True,
            independent=True,
            contained_in_background=False,
            role="article-micro",
            micro_role="inline-explainer",
            source_node_id="12:3",
            z_index=1,
            geometry={"x": 22, "y": 5, "width": 80, "height": 20},
            render_style={
                "object_fit": "contain",
                "object_position": "50% 50%",
                "opacity": 1,
                "rotation_deg": 0,
                "blend_mode": "normal",
                "mask": "none",
            },
        )
        svg = asset("chapter-1-toggle-svg", "interaction.svg")
        fallback = asset("chapter-1-toggle-fallback", "fallback.png")
        cover = asset("cover", "cover.png")
        svg_structure_sha256 = canonical_svg_structure_sha256(svg_text)
        state_export_path = root / "qa" / "interaction-15-3.json"
        state_export = {
            "source": "ardot-interaction-state-export-v1",
            "file_id": "file-1",
            "root_node_id": "1:1",
            "section_node_id": "9:1",
            "source_node_id": "15:3",
            "svg_structure_sha256": svg_structure_sha256,
            "states": [
                {"name": "closed", "node_id": "15:4", "tree_sha256": "sha256:" + "4" * 64},
                {"name": "open", "node_id": "15:5", "tree_sha256": "sha256:" + "5" * 64},
                {"name": "fallback", "node_id": "15:6", "tree_sha256": "sha256:" + "6" * 64},
            ],
        }
        state_export_path.write_text(
            json.dumps(state_export, ensure_ascii=False), encoding="utf-8"
        )
        state_export_sha256 = "sha256:" + file_sha256(state_export_path)
        text = {
            "node_id": "11:9", "text": "可编辑正文", "text_sha256": text_sha256("可编辑正文"),
            "native_editable_text": True, "visible": True, "rasterized": False,
            "semantic_role": "body", "tag": "p", "order": 1,
            "z_index": 2,
            "style": {
                "font_family": "system-sans-cn",
                "font_size_px": 16,
                "line_height_ratio": 1.8,
                "font_weight": 400,
                "font_style": "normal",
                "text_decoration": "none",
                "color": "#173B4E",
                "letter_spacing_px": 0,
                "text_align": "left",
                "opacity": 1,
                "rotation_deg": 0,
                "blend_mode": "normal",
            },
            "geometry": {"x": 24, "y": 30, "width": 342, "height": 20},
        }
        attribution = {
            "node_id": "11:10",
            "text": WORKFLOW_ATTRIBUTION_TEXT,
            "text_sha256": text_sha256(WORKFLOW_ATTRIBUTION_TEXT),
            "native_editable_text": True,
            "visible": True,
            "rasterized": False,
            "semantic_role": "workflow-attribution",
            "tag": "p",
            "order": 2,
            "z_index": 4,
            "style": {
                "font_family": "system-sans-cn",
                "font_size_px": 12,
                "line_height_ratio": 1.7,
                "font_weight": 400,
                "font_style": "normal",
                "text_decoration": "none",
                "color": "#173B4E",
                "letter_spacing_px": 0,
                "text_align": "center",
                "opacity": 1,
                "rotation_deg": 0,
                "blend_mode": "normal",
            },
            "geometry": {"x": 24, "y": 90, "width": 342, "height": 20},
        }
        chapter = {
            "source": TRANSPORT_SOURCE, "chapter_id": "chapter-1", "section_node_id": "9:1", "order": 1,
            "geometry_space": "article-root-390-v1",
            "geometry": {"x": 0, "y": 0, "width": 390, "height": 120},
            "reference_screenshot": asset(
                "chapter-1-reference", "ardot-chapter-1.png", width_px=390
            ),
            "background_layer": background, "visible_text_nodes": [text, attribution], "decorations": [decoration],
            "photos": [],
            "interaction": {
                "interaction_id": "toggle-1", "mode": "svg", "authored_from": "ardot-state-export-v1",
                "source_node_id": "15:3", "ardot_state_sha256": state_export_sha256,
                "ardot_states": {
                    "closed": {"node_id": "15:4", "tree_sha256": "sha256:" + "4" * 64},
                    "open": {"node_id": "15:5", "tree_sha256": "sha256:" + "5" * 64},
                    "fallback": {"node_id": "15:6", "tree_sha256": "sha256:" + "6" * 64},
                },
                "ardot_state_export": {
                    "path": "qa/interaction-15-3.json",
                    "sha256": state_export_sha256,
                },
                "structure_sha256": svg_structure_sha256,
                "fallback_key": "toggle-1",
                "fallback_semantic_sha256": fallback_semantic_sha256,
                "fallback_asset": fallback,
                "z_index": 3,
                "render_style": {
                    "opacity": 1,
                    "rotation_deg": 0,
                    "blend_mode": "normal",
                    "overflow": "hidden",
                },
                "geometry": {"x": 24, "y": 55, "width": 342, "height": 25}, "svg": svg,
            },
        }
        export = {
            "source": TRANSPORT_SOURCE, "revision_algorithm": TRANSPORT_REVISION_ALGORITHM,
            "file_id": "file-1", "root_node_id": "1:1", "artboard": {"width_px": 390, "height_px": 120},
            "chapters": [chapter],
        }
        captured_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        root_export_path = root / "qa" / "ardot-root-nodes.json"
        root_assets = [background, decoration, svg, fallback, cover]
        root_export = {
            "schema_version": 1,
            "source": "ardot-current-root-export",
            "file_id": "file-1",
            "root_node_id": "1:1",
            "captured_at": captured_at,
            "revision_algorithm": ARDOT_REVISION_ALGORITHM,
            "visible_text_nodes": [
                {
                    "node_id": "11:9",
                    "component_name": "WeChat/Body/Current",
                    "node_kind": "TEXT",
                    "text": "可编辑正文",
                    "native_editable_text": True,
                    "visible": True,
                    "rasterized": False,
                },
                {
                    "node_id": "11:10",
                    "component_name": "WeChat/Footer/WorkflowAttribution/Current",
                    "node_kind": "TEXT",
                    "text": WORKFLOW_ATTRIBUTION_TEXT,
                    "native_editable_text": True,
                    "visible": True,
                    "rasterized": False,
                },
            ],
            "component_order": [
                {"node_id": "9:1", "component_name": "WeChat/Section/Current"},
                {"node_id": "9:2", "component_name": "WeChat/Background/Current"},
                {"node_id": "12:3", "component_name": "WeChat/Micro/Current"},
                {"node_id": "15:3", "component_name": "WeChat/Interaction/Current"},
                {"node_id": "11:9", "component_name": "WeChat/Body/Current"},
                {
                    "node_id": "11:10",
                    "component_name": "WeChat/Footer/WorkflowAttribution/Current",
                },
            ],
            "assets": [
                {"id": item["asset_id"], "sha256": item["sha256"]}
                for item in root_assets
            ],
        }
        transport_snapshot = current_root_transport_snapshot(export)
        root_export["transport_sections"] = transport_snapshot["sections"]
        root_export["body_asset_ids"] = transport_snapshot["body_asset_ids"]
        root_revision = current_root_revision_hash(root_export)
        root_export["revision_hash"] = root_revision
        export["current_root_revision_hash"] = root_revision
        export["revision_hash"] = canonical_transport_revision_hash(export)
        root_export_path.write_text(
            json.dumps(root_export, ensure_ascii=False), encoding="utf-8"
        )
        manifest = {
            "schema_version": 5,
            "article": {
                "title": "Current article",
                "digest": "Current digest",
                "content_html": "wechat.html",
                "cover_asset_id": "cover",
            },
            "ardot": {
                "file_id": "file-1",
                "root_node_id": "1:1",
                "captured_at": captured_at,
                "revision_algorithm": ARDOT_REVISION_ALGORITHM,
                "revision_hash": root_revision,
            },
            "workflow_attribution": {
                "policy_id": WORKFLOW_ATTRIBUTION_MARKER,
                "classification": "repository-usage-credit",
                "text": WORKFLOW_ATTRIBUTION_TEXT,
                "text_sha256": f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}",
                "ardot_node_id": "11:10",
                "component_name": "WeChat/Footer/WorkflowAttribution/Current",
                "node_kind": "TEXT",
                "native_editable_text": True,
                "visible": True,
                "terminal": True,
                "organization_identity": False,
                "body_fact": False,
                "visual_reference": False,
                "node_export_file": "qa/ardot-root-nodes.json",
                "node_export_sha256": "sha256:" + file_sha256(root_export_path),
            },
            "assets": [
                {
                    "id": item["asset_id"],
                    "path": item["path"],
                    "sha256": item["sha256"],
                    "role": "cover" if item["asset_id"] == "cover" else "body-image",
                    **(
                        {"wechat_thumb_media_id": "thumb-test-100001"}
                        if item["asset_id"] == "cover"
                        else {}
                    ),
                }
                for item in root_assets
            ],
            "transport_fidelity": {"source": TRANSPORT_SOURCE, "export": export},
        }
        manifest_path = root / "handoff.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return temporary, manifest_path, manifest

    def report(self, manifest_path: Path, **kwargs: object) -> dict:
        if kwargs.get("require_readback") and "expected_target_account_ref" not in kwargs:
            kwargs["expected_target_account_ref"] = "test-visible-account"
        return validate_transport_fidelity_diagnostic(manifest_path, **kwargs)

    def rewrite(self, path: Path, manifest: dict) -> None:
        export = manifest["transport_fidelity"]["export"]
        export.pop("revision_hash", None)
        export["revision_hash"] = canonical_transport_revision_hash(export)
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def rewrite_root(self, path: Path, manifest: dict, node_export: dict) -> None:
        node_export_path = path.parent / "qa" / "ardot-root-nodes.json"
        root_revision = current_root_revision_hash(node_export)
        node_export["revision_hash"] = root_revision
        node_export_path.write_text(
            json.dumps(node_export, ensure_ascii=False), encoding="utf-8"
        )
        manifest["ardot"]["revision_hash"] = root_revision
        manifest["workflow_attribution"]["node_export_sha256"] = (
            "sha256:" + file_sha256(node_export_path)
        )
        export = manifest["transport_fidelity"]["export"]
        export["current_root_revision_hash"] = root_revision
        export.pop("revision_hash", None)
        export["revision_hash"] = canonical_transport_revision_hash(export)
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def live_root(self, path: Path, intended_html_path: Path) -> Path:
        source = path.parent / "qa" / "ardot-root-nodes.json"
        destination = path.parent / "qa" / "live-ardot-root-nodes.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        frozen_time = datetime.fromisoformat(payload["captured_at"])
        payload["captured_at"] = (frozen_time + timedelta(seconds=1)).isoformat()
        destination.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.write_live_receipt(path, destination, intended_html_path)
        return destination

    def live_receipt(self, path: Path) -> Path:
        return path.parent / "qa" / "live-ardot-root-receipt.json"

    def write_live_receipt(
        self, path: Path, live_root: Path, intended_html_path: Path
    ) -> Path:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        export = manifest["transport_fidelity"]["export"]
        frozen = path.parent / "qa" / "ardot-root-nodes.json"
        live_payload = json.loads(live_root.read_text(encoding="utf-8"))
        captured_at = datetime.fromisoformat(live_payload["captured_at"])
        observed_at = captured_at + timedelta(milliseconds=100)
        receipt = {
            "schema_version": 1,
            "source": LIVE_RECEIPT_SOURCE,
            "signature_algorithm": "ed25519",
            "key_id": "test-host-receipt-key",
            "nonce": "ab" * 16,
            "provider": "test-ardot-provider",
            "session_id": "test-session",
            "request_id": "test-request",
            "runtime_binding_nonce": "test_runtime_binding_nonce_1234567890",
            "runtime_binding_digest": "sha256:" + "6" * 64,
            "trusted_bundle_sha256": _trusted_bundle_digest(ROOT),
            "file_id": export["file_id"],
            "root_node_id": export["root_node_id"],
            "root_revision_hash": export["current_root_revision_hash"],
            "transport_revision_hash": export["revision_hash"],
            "handoff_sha256": "sha256:" + file_sha256(path),
            "frozen_export_sha256": "sha256:" + file_sha256(frozen),
            "live_export_sha256": "sha256:" + file_sha256(live_root),
            "output_html_path_identity_sha256": path_identity_sha256(
                intended_html_path
            ),
            "captured_at": live_payload["captured_at"],
            "observed_at": observed_at.isoformat(),
            "expires_at": (observed_at + timedelta(minutes=5)).isoformat(),
        }
        encoded = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        receipt["signature"] = "ed25519:" + base64.b64encode(
            self.LIVE_RECEIPT_PRIVATE_KEY.sign(encoded)
        ).decode("ascii")
        destination = self.live_receipt(path)
        destination.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
        return destination

    def write_valid_readback(self, path: Path, manifest: dict) -> Path:
        revision = manifest["transport_fidelity"]["export"]["revision_hash"]
        observed_at = datetime.now(timezone.utc)
        screenshot = path.parent / "readback-chapter-1.png"
        write_png(screenshot, 390, 120, alpha=False)
        cover_download = path.parent / "saved-cover.png"
        cover_download.write_bytes((path.parent / "cover.png").read_bytes())
        interaction = manifest["transport_fidelity"]["export"]["chapters"][0][
            "interaction"
        ]
        readback = path.parent / "readback.json"
        readback.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": READBACK_SOURCE,
                    "target_account_ref": "test-visible-account",
                    "draft_id": "test-draft-100001",
                    "title": manifest["article"]["title"],
                    "digest": manifest["article"]["digest"],
                    "cover_asset_id": manifest["article"]["cover_asset_id"],
                    "thumb_media_id": "thumb-test-100001",
                    "cover_hosted_derivative": {
                        "url": "https://mmbiz.qpic.cn/saved-cover",
                        "downloaded_path": cover_download.name,
                        "downloaded_sha256": "sha256:"
                        + file_sha256(cover_download),
                        "downloaded_byte_length": cover_download.stat().st_size,
                    },
                    "transport_revision_hash": revision,
                    "observed_at": observed_at.isoformat(),
                    "chapters": [
                        {
                            "chapter_id": "chapter-1",
                            "section_node_id": "9:1",
                            "visible_text_node_ids": ["11:9", "11:10"],
                            "visible_text_sha256": text_sha256(
                                f"可编辑正文 {WORKFLOW_ATTRIBUTION_TEXT}"
                            ),
                            "asset_ids": [
                                "chapter-1-background",
                                "chapter-1-motif",
                            ],
                            "hosted_assets": [
                                {
                                    "asset_id": asset_id,
                                    "url": f"https://mmbiz.qpic.cn/{asset_id}",
                                    "downloaded_path": filename,
                                    "downloaded_sha256": "sha256:"
                                    + file_sha256(path.parent / filename),
                                }
                                for asset_id, filename in (
                                    ("chapter-1-background", "background.png"),
                                    ("chapter-1-motif", "motif.png"),
                                )
                            ],
                            "screenshot": {
                                "path": screenshot.name,
                                "sha256": "sha256:" + file_sha256(screenshot),
                                "width_px": 390,
                            },
                            "interactions": [
                                {
                                    "interaction_id": "toggle-1",
                                    "mode": "svg",
                                    "signature_sha256": interaction[
                                        "structure_sha256"
                                    ],
                                    "structure_path": "interaction.svg",
                                    "structure_file_sha256": "sha256:"
                                    + file_sha256(path.parent / "interaction.svg"),
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return readback

    def write_readback_receipt(
        self,
        path: Path,
        *,
        readback: Path,
        compiled_html: Path,
        compile_report: Path,
    ) -> Path:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        export = manifest["transport_fidelity"]["export"]
        readback_payload = json.loads(readback.read_text(encoding="utf-8"))
        live_receipt_path = self.live_receipt(path)
        live_receipt = json.loads(live_receipt_path.read_text(encoding="utf-8"))
        observed_at = datetime.fromisoformat(readback_payload["observed_at"])
        receipt = {
            "schema_version": 1,
            "source": READBACK_RECEIPT_SOURCE,
            "signature_algorithm": "ed25519",
            "key_id": "test-host-receipt-key",
            "nonce": "cd" * 16,
            "provider": "test-wechat-provider",
            "session_id": "test-wechat-session",
            "request_id": "test-wechat-request",
            "runtime_binding_nonce": live_receipt["runtime_binding_nonce"],
            "runtime_binding_digest": live_receipt["runtime_binding_digest"],
            "trusted_bundle_sha256": _trusted_bundle_digest(ROOT),
            "target_account_ref": readback_payload["target_account_ref"],
            "draft_id": readback_payload["draft_id"],
            "title": readback_payload["title"],
            "digest": readback_payload["digest"],
            "cover_asset_id": readback_payload["cover_asset_id"],
            "thumb_media_id": readback_payload["thumb_media_id"],
            "cover_hosted_url": readback_payload["cover_hosted_derivative"][
                "url"
            ],
            "cover_downloaded_sha256": readback_payload[
                "cover_hosted_derivative"
            ]["downloaded_sha256"],
            "cover_downloaded_byte_length": readback_payload[
                "cover_hosted_derivative"
            ]["downloaded_byte_length"],
            "handoff_sha256": "sha256:" + file_sha256(path),
            "transport_revision_hash": export["revision_hash"],
            "output_html_path_identity_sha256": path_identity_sha256(
                compiled_html
            ),
            "compiled_html_sha256": "sha256:" + file_sha256(compiled_html),
            "compile_report_sha256": "sha256:" + file_sha256(compile_report),
            "live_receipt_sha256": "sha256:" + file_sha256(live_receipt_path),
            "readback_sha256": "sha256:" + file_sha256(readback),
            "observed_at": readback_payload["observed_at"],
            "expires_at": (observed_at + timedelta(minutes=5)).isoformat(),
        }
        encoded = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        receipt["signature"] = "ed25519:" + base64.b64encode(
            self.LIVE_RECEIPT_PRIVATE_KEY.sign(encoded)
        ).decode("ascii")
        destination = path.parent / "readback-receipt.json"
        destination.write_text(
            json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
        )
        return destination

    def test_clean_manifest_html_and_readback_pass(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "compiled"
        live_root = self.live_root(path, output / "wechat-candidate.html")
        compile_result = compile_frozen_transport_candidate(
            path,
            output,
            live_root_path=live_root,
            live_receipt_path=self.live_receipt(path),
            check=True,
        )
        self.assertTrue(compile_result["ok"], compile_result)
        html = output / "wechat-candidate.html"
        readback = self.write_valid_readback(path, manifest)
        readback_receipt = self.write_readback_receipt(
            path,
            readback=readback,
            compiled_html=html,
            compile_report=output / "candidate-report.json",
        )
        report = self.report(
            path,
            html_path=html,
            live_root_path=live_root,
            live_receipt_path=self.live_receipt(path),
            compile_report_path=output / "candidate-report.json",
            require_compile_report=True,
            readback_path=readback,
            readback_receipt_path=readback_receipt,
            require_readback=True,
        )
        self.assertTrue(report["ok"], report)

        forged_readback = json.loads(readback.read_text(encoding="utf-8"))
        fallback = path.parent / "fallback.png"
        for hosted in forged_readback["chapters"][0]["hosted_assets"]:
            hosted["url"] = f"https://mmbiz.qpic.cn/forged/{hosted['asset_id']}"
            hosted["downloaded_path"] = fallback.name
            hosted["downloaded_sha256"] = "sha256:" + file_sha256(fallback)
        readback.write_text(
            json.dumps(forged_readback, ensure_ascii=False), encoding="utf-8"
        )
        forged = self.report(
            path,
            html_path=html,
            live_root_path=live_root,
            live_receipt_path=self.live_receipt(path),
            compile_report_path=output / "candidate-report.json",
            require_compile_report=True,
            readback_path=readback,
            readback_receipt_path=readback_receipt,
            require_readback=True,
        )
        self.assertIn("transport.readback_receipt", forged["error_codes"])

    def test_readback_binds_article_cover_and_wechat_hosted_urls(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "readback-binding-output"
        live_root = self.live_root(path, output / "wechat-candidate.html")
        compiled = compile_frozen_transport_candidate(
            path,
            output,
            live_root_path=live_root,
            check=True,
        )
        self.assertTrue(compiled["ok"], compiled)
        readback = self.write_valid_readback(path, manifest)
        original = json.loads(readback.read_text(encoding="utf-8"))

        variants: list[tuple[str, dict, str]] = []
        wrong_title = json.loads(json.dumps(original))
        wrong_title["title"] = "Other article"
        variants.append(("title", wrong_title, "transport.readback_article"))
        wrong_digest = json.loads(json.dumps(original))
        wrong_digest["digest"] = "Other digest"
        variants.append(("digest", wrong_digest, "transport.readback_article"))
        wrong_cover_id = json.loads(json.dumps(original))
        wrong_cover_id["cover_asset_id"] = "chapter-1-background"
        variants.append(("cover-asset", wrong_cover_id, "transport.readback_cover"))
        wrong_thumb = json.loads(json.dumps(original))
        wrong_thumb["thumb_media_id"] = "thumb-from-another-account"
        variants.append(("thumb-media", wrong_thumb, "transport.readback_cover"))
        evil_cover_host = json.loads(json.dumps(original))
        evil_cover_host["cover_hosted_derivative"]["url"] = (
            "https://evil.example/saved-cover"
        )
        variants.append(("cover-host", evil_cover_host, "transport.readback_cover"))
        wrong_cover_hash = json.loads(json.dumps(original))
        wrong_cover_hash["cover_hosted_derivative"]["downloaded_sha256"] = (
            "sha256:" + "0" * 64
        )
        variants.append(("cover-hash", wrong_cover_hash, "transport.readback_cover"))
        wrong_cover_length = json.loads(json.dumps(original))
        wrong_cover_length["cover_hosted_derivative"][
            "downloaded_byte_length"
        ] += 1
        variants.append(("cover-length", wrong_cover_length, "transport.readback_cover"))
        evil_body_host = json.loads(json.dumps(original))
        evil_body_host["chapters"][0]["hosted_assets"][0]["url"] = (
            "https://evil.example/forged-body"
        )
        variants.append(("body-host", evil_body_host, "transport.readback"))

        for label, payload, expected_code in variants:
            with self.subTest(label=label):
                readback.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                report = self.report(
                    path,
                    html_path=output / "wechat-candidate.html",
                    live_root_path=live_root,
                    compile_report_path=output / "candidate-report.json",
                    require_compile_report=True,
                    readback_path=readback,
                    require_readback=True,
                )
                self.assertIn(expected_code, report["error_codes"], report)

        readback.write_text(
            json.dumps(original, ensure_ascii=False), encoding="utf-8"
        )
        unbound_cover_manifest = json.loads(path.read_text(encoding="utf-8"))
        cover_record = next(
            item
            for item in unbound_cover_manifest["assets"]
            if item["id"] == "cover"
        )
        cover_record["wechat_thumb_media_id"] = None
        path.write_text(
            json.dumps(unbound_cover_manifest, ensure_ascii=False),
            encoding="utf-8",
        )
        unbound_cover = validate_transport_fidelity_diagnostic(
            path,
            readback_path=readback,
            expected_target_account_ref="test-visible-account",
        )
        self.assertIn("transport.readback_cover", unbound_cover["error_codes"])

    def test_imported_compiler_emits_diagnostic_only_candidate(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "output"
        report = compile_frozen_transport_candidate(
            path,
            output,
            live_root_path=self.live_root(path, output / "wechat-candidate.html"),
            live_receipt_path=self.live_receipt(path),
            check=True,
        )
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["candidate_valid"])
        self.assertFalse(report["draft_write_eligible"])
        self.assertFalse(report["delivery_eligible"])
        self.assertFalse(report["portable_audit_verified"])
        self.assertFalse(report["publication_preflight_eligible"])
        self.assertFalse(report["publication_authorized"])
        self.assertEqual(report["assurance_scope"], "diagnostic-candidate")
        self.assertFalse(report["finalization_verified"])
        self.assertEqual(report["source"], TRANSPORT_SOURCE)
        html = output / "wechat-candidate.html"
        self.assertTrue(html.is_file())
        self.assertFalse((output / "wechat.html").exists())
        self.assertFalse((output / "compile-report.json").exists())

    def test_unsigned_candidate_report_cannot_claim_draft_write_eligibility(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "tampered-session-output"
        live_root = self.live_root(path, output / "wechat-candidate.html")
        original = compile_frozen_transport_candidate(
            path,
            output,
            live_root_path=live_root,
            check=True,
        )
        self.assertTrue(original["ok"], original)
        report_path = output / "candidate-report.json"
        forged = json.loads(report_path.read_text(encoding="utf-8"))
        forged["assurance_scope"] = "current-session-draft"
        forged["draft_write_eligible"] = True
        forged["artifact_binding"]["candidate_html"]["source"] = (
            "wechat-session-draft-candidate-v1"
        )
        report_path.write_text(
            json.dumps(forged, ensure_ascii=False), encoding="utf-8"
        )

        validated = validate_transport_fidelity_diagnostic(
            path,
            html_path=output / "wechat-candidate.html",
            live_root_path=live_root,
            compile_report_path=report_path,
            require_compile_report=True,
        )
        self.assertFalse(validated["ok"], validated)
        self.assertFalse(validated["draft_write_eligible"])
        self.assertIn("transport.compile_artifact", validated["error_codes"])

    def test_session_draft_candidate_does_not_require_host_signature(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "session-draft-output"
        live_root = self.live_root(path, output / "wechat-candidate.html")
        with patch("secure_runtime.require_secure_runtime"):
            report = compile_frozen_session_draft(
                path,
                output,
                live_root_path=live_root,
                check=True,
            )

        self.assertTrue(report["ok"], report)
        self.assertFalse(report["draft_write_eligible"])
        self.assertFalse(report["delivery_eligible"])
        self.assertFalse(report["portable_audit_verified"])
        self.assertFalse(report["publication_preflight_eligible"])
        self.assertFalse(report["publication_authorized"])
        self.assertIsNone(report["artifact_binding"]["live_root_receipt"])
        self.assertEqual(
            report["artifact_binding"]["live_root_export"]["path"],
            str(live_root.resolve()),
        )
        self.assertTrue((output / "wechat-candidate.html").is_file())
        html = output / "wechat-candidate.html"
        payload = html.read_text(encoding="utf-8")
        self.assertIn('data-ardot-section-node="9:1"', payload)
        self.assertIn('data-transport-text-node-id="11:9"', payload)
        self.assertIn('data-transport-asset-id="chapter-1-motif"', payload)
        self.assertIn('data-transport-layer-id="12:3"', payload)

        readback = self.write_valid_readback(path, manifest)
        verified = self.report(
            path,
            html_path=html,
            live_root_path=live_root,
            compile_report_path=output / "candidate-report.json",
            require_compile_report=True,
            readback_path=readback,
            require_readback=True,
        )
        self.assertTrue(verified["ok"], verified)
        self.assertFalse(verified["draft_write_eligible"])
        self.assertTrue(verified["session_readback_structural_match"])
        self.assertFalse(verified["portable_audit_verified"])
        self.assertFalse(verified["readback_receipt_verified"])

    def test_secure_cli_supports_current_session_draft_chain(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "secure-session-output"
        live_root = self.live_root(path, output / "wechat-candidate.html")
        runner = [
            sys.executable,
            "-I",
            "-S",
            "scripts/secure_runner.py",
        ]
        compiled = subprocess.run(
            runner
            + [
                "scripts/compile_wechat.py",
                "--transport-fidelity",
                str(path),
                "--live-root-export",
                str(live_root),
                "--session-draft",
                "--output",
                str(output),
                "--check",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr or compiled.stdout)
        compile_report = json.loads(compiled.stdout)
        self.assertFalse(compile_report["draft_write_eligible"], compile_report)
        self.assertFalse(compile_report["portable_audit_verified"])

        validated = subprocess.run(
            runner
            + [
                "scripts/validate_transport_fidelity.py",
                str(path),
                "--html",
                str(output / "wechat-candidate.html"),
                "--live-root-export",
                str(live_root),
                "--require-live-root",
                "--compile-report",
                str(output / "candidate-report.json"),
                "--require-compile-report",
                "--session-draft",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(validated.returncode, 0, validated.stderr or validated.stdout)
        validation_report = json.loads(validated.stdout)
        self.assertFalse(validation_report["draft_write_eligible"], validation_report)
        self.assertFalse(validation_report["portable_audit_verified"])
        self.assertFalse(validation_report["publication_preflight_eligible"])
        self.assertFalse(validation_report["publication_authorized"])

    def test_portable_audit_requires_both_receipts_and_never_authorizes_publish(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "signed-output"
        live_root = self.live_root(path, output / "wechat.html")
        live_receipt = self.live_receipt(path)
        with (
            patch("secure_runtime.require_secure_runtime"),
            patch(
                "transport_fidelity._require_secure_transport_finalization_runtime"
            ),
        ):
            compiled = compile_frozen_transport(
                path,
                output,
                live_root_path=live_root,
                live_receipt_path=live_receipt,
                check=True,
            )
        self.assertTrue(compiled["ok"], compiled)
        self.assertTrue(compiled["draft_write_eligible"])
        self.assertFalse(compiled["delivery_eligible"])
        self.assertFalse(compiled["portable_audit_verified"])
        self.assertFalse(compiled["publication_preflight_eligible"])
        self.assertFalse(compiled["publication_authorized"])
        self.assertFalse(compiled["finalization_verified"])

        with patch(
            "transport_fidelity._require_secure_transport_finalization_runtime"
        ):
            before_readback = transport_fidelity_module._validate_transport_fidelity_contract(
                path,
                html_path=output / "wechat.html",
                live_root_path=live_root,
                live_receipt_path=live_receipt,
                require_live_root=True,
                compile_report_path=output / "compile-report.json",
                require_compile_report=True,
                diagnostic=False,
            )
        self.assertTrue(before_readback["ok"], before_readback)
        self.assertFalse(before_readback["portable_audit_verified"])
        self.assertFalse(before_readback["delivery_eligible"])
        self.assertFalse(before_readback["publication_preflight_eligible"])
        self.assertFalse(before_readback["publication_authorized"])

        readback = self.write_valid_readback(path, manifest)
        readback_receipt = self.write_readback_receipt(
            path,
            readback=readback,
            compiled_html=output / "wechat.html",
            compile_report=output / "compile-report.json",
        )
        with patch(
            "transport_fidelity._require_secure_transport_finalization_runtime"
        ):
            portable = transport_fidelity_module._validate_transport_fidelity_contract(
                path,
                html_path=output / "wechat.html",
                live_root_path=live_root,
                live_receipt_path=live_receipt,
                require_live_root=True,
                compile_report_path=output / "compile-report.json",
                require_compile_report=True,
                readback_path=readback,
                readback_receipt_path=readback_receipt,
                require_readback=True,
                expected_target_account_ref="test-visible-account",
                diagnostic=False,
            )
        self.assertTrue(portable["ok"], portable)
        self.assertTrue(portable["portable_audit_verified"])
        self.assertTrue(portable["delivery_eligible"])
        self.assertTrue(portable["publication_preflight_eligible"])
        self.assertTrue(portable["finalization_verified"])
        self.assertFalse(portable["publication_authorized"])

    def test_imported_finalization_apis_require_the_isolated_runner(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "forbidden-final-output"
        with self.assertRaises(SystemExit):
            compile_frozen_session_draft(path, output, check=True)
        with self.assertRaises(SystemExit):
            compile_frozen_transport(path, output, check=True)
        with self.assertRaises(SystemExit):
            validate_transport_fidelity(path)
        with self.assertRaises(SystemExit):
            _compile_frozen_transport_contract(
                path, output, check=True, finalization=True
            )
        with self.assertRaises(SystemExit):
            _compile_frozen_transport_contract(
                path,
                output,
                check=True,
                finalization=False,
                session_draft=True,
            )
        with self.assertRaises(SystemExit):
            transport_fidelity_module._validate_transport_fidelity_contract(
                path, diagnostic=False
            )
        self.assertFalse((output / "wechat.html").exists())
        self.assertFalse((output / "compile-report.json").exists())
        self.assertFalse((output / "wechat-candidate.html").exists())
        self.assertFalse((output / "candidate-report.json").exists())

    def test_native_font_and_visual_style_cannot_be_silently_substituted(self) -> None:
        for label, mutate in (
            (
                "unsupported-font",
                lambda chapter: chapter["visible_text_nodes"][0]["style"].update(
                    {"font_family": "unmapped-display-font"}
                ),
            ),
            (
                "ignored-text-transform",
                lambda chapter: chapter["visible_text_nodes"][0]["style"].update(
                    {"text_transform": "uppercase"}
                ),
            ),
            (
                "unsupported-image-rotation",
                lambda chapter: chapter["decorations"][0]["render_style"].update(
                    {"rotation_deg": 12}
                ),
            ),
        ):
            with self.subTest(label=label):
                temporary, path, manifest = self.make_bundle()
                self.addCleanup(temporary.cleanup)
                mutate(manifest["transport_fidelity"]["export"]["chapters"][0])
                self.rewrite(path, manifest)
                report = self.report(path)
                self.assertTrue(
                    {
                        "transport.native_text.mapping",
                        "transport.decoration.independent",
                    }
                    & set(report["error_codes"]),
                    report,
                )

    def test_final_compile_requires_complete_current_root_attribution(self) -> None:
        for missing in ("ardot", "workflow_attribution"):
            with self.subTest(missing=missing):
                temporary, path, manifest = self.make_bundle()
                self.addCleanup(temporary.cleanup)
                manifest.pop(missing)
                path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                output = path.parent / "output"
                report = compile_frozen_transport_candidate(
                    path,
                    output,
                    live_root_path=self.live_root(path, output / "wechat-candidate.html"),
                    live_receipt_path=self.live_receipt(path),
                    check=True,
                )
                self.assertFalse(report["delivery_eligible"], report)
                self.assertIn("transport.attribution", report["error_codes"])
                self.assertFalse((output / "wechat.html").exists())

        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "missing-live-output"
        missing_live = compile_frozen_transport_candidate(path, output, check=True)
        self.assertFalse(missing_live["delivery_eligible"], missing_live)
        self.assertIn("transport.current_root_live", missing_live["error_codes"])
        self.assertFalse((output / "wechat.html").exists())

    def test_fresh_live_root_read_must_match_and_cannot_reuse_frozen_file(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        frozen = path.parent / "qa" / "ardot-root-nodes.json"
        intended_html = path.parent / "compiled" / "wechat.html"
        valid_live = self.live_root(path, intended_html)
        valid = self.report(
            path,
            live_root_path=valid_live,
            live_receipt_path=self.live_receipt(path),
            intended_html_path=intended_html,
            require_live_root=True,
        )
        self.assertTrue(valid["ok"], valid)
        self.assertTrue(valid["diagnostic_current_root_receipt_valid"])
        self.assertFalse(valid["current_root_live_verified"])
        self.assertFalse(valid["delivery_eligible"])

        receipt_path = self.live_receipt(path)
        wrong_bundle = json.loads(receipt_path.read_text(encoding="utf-8"))
        wrong_bundle["trusted_bundle_sha256"] = "sha256:" + "0" * 64
        unsigned = {
            key: value for key, value in wrong_bundle.items() if key != "signature"
        }
        encoded = json.dumps(
            unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        wrong_bundle["signature"] = "ed25519:" + base64.b64encode(
            self.LIVE_RECEIPT_PRIVATE_KEY.sign(encoded)
        ).decode("ascii")
        receipt_path.write_text(
            json.dumps(wrong_bundle, ensure_ascii=False), encoding="utf-8"
        )
        wrong_release = self.report(
            path,
            live_root_path=valid_live,
            live_receipt_path=receipt_path,
            intended_html_path=intended_html,
            require_live_root=True,
        )
        self.assertIn(
            "transport.current_root_receipt", wrong_release["error_codes"]
        )
        self.write_live_receipt(path, valid_live, intended_html)

        session_only = self.report(
            path,
            live_root_path=valid_live,
            require_live_root=True,
        )
        self.assertTrue(session_only["ok"], session_only)
        self.assertFalse(session_only["draft_write_eligible"])
        self.assertEqual(session_only["assurance_scope"], "diagnostic-only")
        self.assertFalse(session_only["portable_audit_verified"])
        self.assertFalse(session_only["diagnostic_current_root_receipt_valid"])

        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_payload["signature"] = "ed25519:" + base64.b64encode(
            b"\0" * 64
        ).decode("ascii")
        receipt_path.write_text(
            json.dumps(receipt_payload, ensure_ascii=False), encoding="utf-8"
        )
        forged = self.report(
            path,
            live_root_path=valid_live,
            live_receipt_path=receipt_path,
            intended_html_path=intended_html,
            require_live_root=True,
        )
        self.assertIn("transport.current_root_receipt", forged["error_codes"])

        reused = self.report(
            path,
            live_root_path=frozen,
            require_live_root=True,
        )
        self.assertIn("transport.current_root_live", reused["error_codes"])

        copied = path.parent / "qa" / "renamed-frozen-root.json"
        copied.write_bytes(frozen.read_bytes())
        copied_report = self.report(
            path,
            live_root_path=copied,
            require_live_root=True,
        )
        self.assertIn("transport.current_root_live", copied_report["error_codes"])

        hardlink = path.parent / "qa" / "hardlinked-frozen-root.json"
        os.link(frozen, hardlink)
        hardlink_report = self.report(
            path,
            live_root_path=hardlink,
            require_live_root=True,
        )
        self.assertIn("transport.current_root_live", hardlink_report["error_codes"])

        stale = path.parent / "qa" / "stale-reformatted-root.json"
        stale_payload = json.loads(frozen.read_text(encoding="utf-8"))
        stale.write_text(
            json.dumps(stale_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        stale_report = self.report(
            path,
            live_root_path=stale,
            require_live_root=True,
        )
        self.assertIn("transport.current_root_live", stale_report["error_codes"])

        live = self.live_root(path, intended_html)
        payload = json.loads(live.read_text(encoding="utf-8"))
        payload["visible_text_nodes"][0]["text"] = "Changed in live Ardot"
        payload["revision_hash"] = current_root_revision_hash(payload)
        live.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        changed = self.report(
            path,
            live_root_path=live,
            require_live_root=True,
        )
        self.assertIn("transport.current_root_live", changed["error_codes"])

    def test_live_root_must_be_recent_and_not_future_dated(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        intended_html = path.parent / "compiled" / "wechat-candidate.html"
        live = self.live_root(path, intended_html)
        payload = json.loads(live.read_text(encoding="utf-8"))
        payload["captured_at"] = (
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat()
        live.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        future = self.report(path, live_root_path=live, require_live_root=True)
        self.assertIn("transport.current_root_live", future["error_codes"])

        frozen = path.parent / "qa" / "ardot-root-nodes.json"
        frozen_payload = json.loads(frozen.read_text(encoding="utf-8"))
        frozen_payload["captured_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=3)
        ).isoformat()
        frozen.write_text(
            json.dumps(frozen_payload, ensure_ascii=False), encoding="utf-8"
        )
        manifest["workflow_attribution"]["node_export_sha256"] = (
            "sha256:" + file_sha256(frozen)
        )
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        stale_payload = json.loads(frozen.read_text(encoding="utf-8"))
        stale_payload["captured_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        live.write_text(
            json.dumps(stale_payload, ensure_ascii=False), encoding="utf-8"
        )
        stale = self.report(path, live_root_path=live, require_live_root=True)
        self.assertIn("transport.current_root_live", stale["error_codes"])

    def test_session_readback_binds_target_and_fresh_ordering(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "session-readback-output"
        live_root = self.live_root(path, output / "wechat-candidate.html")
        with patch("secure_runtime.require_secure_runtime"):
            compiled = compile_frozen_session_draft(
                path,
                output,
                live_root_path=live_root,
                check=True,
            )
        self.assertTrue(compiled["ok"], compiled)
        html = output / "wechat-candidate.html"
        compile_report = output / "candidate-report.json"
        readback = self.write_valid_readback(path, manifest)

        payload = json.loads(readback.read_text(encoding="utf-8"))
        payload["target_account_ref"] = "wrong-account"
        readback.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        wrong_target = self.report(
            path,
            html_path=html,
            live_root_path=live_root,
            compile_report_path=compile_report,
            require_compile_report=True,
            readback_path=readback,
            require_readback=True,
        )
        self.assertIn("transport.readback_target", wrong_target["error_codes"])
        self.assertFalse(wrong_target["session_readback_structural_match"])

        payload["target_account_ref"] = "test-visible-account"
        payload["observed_at"] = json.loads(
            compile_report.read_text(encoding="utf-8")
        )["compiled_at"]
        readback.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        stale_order = self.report(
            path,
            html_path=html,
            live_root_path=live_root,
            compile_report_path=compile_report,
            require_compile_report=True,
            readback_path=readback,
            require_readback=True,
        )
        self.assertIn("transport.readback_time", stale_order["error_codes"])
        self.assertFalse(stale_order["session_readback_structural_match"])

        missing_target = validate_transport_fidelity_diagnostic(
            path,
            html_path=html,
            live_root_path=live_root,
            compile_report_path=compile_report,
            require_compile_report=True,
            readback_path=readback,
            require_readback=True,
        )
        self.assertIn("transport.readback_target", missing_target["error_codes"])
        self.assertFalse(missing_target["session_readback_structural_match"])

    def test_compile_report_must_be_recent_and_not_future_dated(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "future-compile-output"
        live_root = self.live_root(path, output / "wechat-candidate.html")
        with patch("secure_runtime.require_secure_runtime"):
            compiled = compile_frozen_session_draft(
                path,
                output,
                live_root_path=live_root,
                check=True,
            )
        self.assertTrue(compiled["ok"], compiled)
        compile_report = output / "candidate-report.json"
        payload = json.loads(compile_report.read_text(encoding="utf-8"))
        payload["compiled_at"] = (
            datetime.now(timezone.utc) + timedelta(minutes=5)
        ).isoformat()
        compile_report.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        future = self.report(
            path,
            html_path=output / "wechat-candidate.html",
            live_root_path=live_root,
            compile_report_path=compile_report,
            require_compile_report=True,
        )
        self.assertIn("transport.compile_artifact", future["error_codes"])

    def test_html_postflight_rejects_unstyled_or_wrong_asset_layers(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "output"
        report = compile_frozen_transport_candidate(
            path,
            output,
            live_root_path=self.live_root(path, output / "wechat-candidate.html"),
            live_receipt_path=self.live_receipt(path),
            check=True,
        )
        self.assertTrue(report["ok"], report)
        html = output / "wechat-candidate.html"
        original = html.read_text(encoding="utf-8")
        unstyled = re.sub(
            r'(<img[^>]+data-transport-layer-kind="background"[^>]+style=")[^"]*(")',
            r"\1\2",
            original,
            count=1,
        )
        html.write_text(unstyled, encoding="utf-8")
        invalid = self.report(path, html_path=html)
        self.assertIn("transport.render_signature", invalid["error_codes"])

        hidden_section = original.replace(
            'style="position:relative;width:100%;height:0;',
            'style="display:none;',
            1,
        )
        html.write_text(hidden_section, encoding="utf-8")
        invalid = self.report(path, html_path=html)
        self.assertIn("transport.mapping", invalid["error_codes"])

        html.write_text(original.replace("assets/chapter-1-background-", "assets/missing-background-", 1), encoding="utf-8")
        invalid = self.report(path, html_path=html)
        self.assertIn("transport.render_signature", invalid["error_codes"])

    def test_signed_layers_reject_unsigned_descendants_and_extra_attributes(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "dom-output"
        compiled = compile_frozen_transport_candidate(
            path,
            output,
            live_root_path=self.live_root(path, output / "wechat-candidate.html"),
            live_receipt_path=self.live_receipt(path),
            check=True,
        )
        self.assertTrue(compiled["ok"], compiled)
        html = output / "wechat-candidate.html"
        original = html.read_text(encoding="utf-8")
        background = re.search(
            r'<img[^>]+data-transport-layer-kind="background"[^>]*>', original
        )
        self.assertIsNotNone(background)
        variants = {
            "text-overlay": original.replace(
                "可编辑正文</p>",
                '可编辑正文<span style="position:absolute;inset:0;background:#fff"></span></p>',
                1,
            ),
            "duplicate-known-image": original.replace(
                "可编辑正文</p>",
                f"可编辑正文{background.group(0)}</p>",
                1,
            ),
            "interaction-sibling": original.replace(
                "</svg></div>", "</svg><div></div></div>", 1
            ),
            "unsigned-attribute": original.replace(
                "<img ", '<img loading="lazy" ', 1
            ),
            "duplicate-root-style": original.replace(
                '<div data-transport-source=',
                '<div style="display:none" data-transport-source=',
                1,
            ),
        }
        for label, payload in variants.items():
            with self.subTest(label=label):
                html.write_text(payload, encoding="utf-8")
                report = self.report(path, html_path=html)
                self.assertIn("transport.render_signature", report["error_codes"])

    def test_compile_report_binds_the_exact_final_html_file_and_bytes(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "binding-output"
        live_root = self.live_root(path, output / "wechat-candidate.html")
        compiled = compile_frozen_transport_candidate(
            path,
            output,
            live_root_path=live_root,
            live_receipt_path=self.live_receipt(path),
            check=True,
        )
        self.assertTrue(compiled["ok"], compiled)
        html = output / "wechat-candidate.html"
        compile_report = output / "candidate-report.json"
        binding = compiled["artifact_binding"]["candidate_html"]
        self.assertEqual(binding["sha256"], "sha256:" + file_sha256(html))
        self.assertEqual(binding["byte_length"], html.stat().st_size)
        self.assertEqual(binding["device"], html.stat().st_dev)
        self.assertEqual(binding["inode"], html.stat().st_ino)
        verified = self.report(
            path,
            html_path=html,
            live_root_path=live_root,
            live_receipt_path=self.live_receipt(path),
            compile_report_path=compile_report,
            require_compile_report=True,
        )
        self.assertTrue(verified["ok"], verified)
        detached_report = self.report(
            path,
            html_path=html,
            compile_report_path=compile_report,
            require_compile_report=True,
        )
        self.assertIn("transport.compile_artifact", detached_report["error_codes"])

        replica = path.parent / "binding-output-copy"
        shutil.copytree(output, replica)
        replica_html = replica / "wechat-candidate.html"
        replica_report_path = replica / "candidate-report.json"
        replica_report = json.loads(replica_report_path.read_text(encoding="utf-8"))
        replica_binding = replica_report["artifact_binding"]["candidate_html"]
        replica_stat = replica_html.stat()
        replica_binding["path_identity_sha256"] = path_identity_sha256(replica_html)
        replica_binding["device"] = replica_stat.st_dev
        replica_binding["inode"] = replica_stat.st_ino
        replica_report_path.write_text(
            json.dumps(replica_report, ensure_ascii=False), encoding="utf-8"
        )
        copied_directory = self.report(
            path,
            html_path=replica_html,
            live_root_path=live_root,
            live_receipt_path=self.live_receipt(path),
            compile_report_path=replica_report_path,
            require_compile_report=True,
        )
        self.assertIn(
            "transport.compile_artifact", copied_directory["error_codes"]
        )

        original = html.read_text(encoding="utf-8")
        html.write_text(original + "\n", encoding="utf-8")
        tampered = self.report(
            path,
            html_path=html,
            live_root_path=live_root,
            live_receipt_path=self.live_receipt(path),
            compile_report_path=compile_report,
            require_compile_report=True,
        )
        self.assertIn("transport.compile_artifact", tampered["error_codes"])

        html.write_text(original, encoding="utf-8")
        copy_path = output / "same-bytes-copy.html"
        copy_path.write_bytes(html.read_bytes())
        substituted = self.report(
            path,
            html_path=copy_path,
            live_root_path=live_root,
            live_receipt_path=self.live_receipt(path),
            compile_report_path=compile_report,
            require_compile_report=True,
        )
        self.assertIn("transport.compile_artifact", substituted["error_codes"])
        missing = self.report(path, require_compile_report=True)
        self.assertIn("transport.compile_artifact", missing["error_codes"])

    def test_svg_signature_and_ardot_state_export_are_recomputed(self) -> None:
        for label, mutate in (
            (
                "forged-structure",
                lambda interaction: interaction.update(
                    {"structure_sha256": "sha256:" + "0" * 64}
                ),
            ),
            (
                "missing-state-export",
                lambda interaction: interaction.pop("ardot_state_export"),
            ),
        ):
            with self.subTest(label=label):
                temporary, path, manifest = self.make_bundle()
                self.addCleanup(temporary.cleanup)
                interaction = manifest["transport_fidelity"]["export"]["chapters"][0][
                    "interaction"
                ]
                mutate(interaction)
                self.rewrite(path, manifest)
                report = self.report(path)
                self.assertIn(
                    "transport.interaction.freehand_svg", report["error_codes"]
                )

        for label, mutate in (
            (
                "missing-tree-hash",
                lambda states: states["closed"].pop("tree_sha256"),
            ),
            (
                "duplicate-state-node",
                lambda states: states["open"].update(
                    {"node_id": states["closed"]["node_id"]}
                ),
            ),
        ):
            with self.subTest(label=label):
                temporary, path, manifest = self.make_bundle()
                self.addCleanup(temporary.cleanup)
                interaction = manifest["transport_fidelity"]["export"]["chapters"][0][
                    "interaction"
                ]
                mutate(interaction["ardot_states"])
                self.rewrite(path, manifest)
                report = self.report(path)
                self.assertIn(
                    "transport.interaction.freehand_svg", report["error_codes"]
                )

    def test_background_requires_exact_3x_size_and_background_only_export(self) -> None:
        for label, mutate, expected in (
            (
                "oversized-width",
                lambda background: background.update({"width_px": 1171}),
                "transport.background.resolution",
            ),
            (
                "wrong-height",
                lambda background: background.update({"height_px": 359}),
                "transport.background.resolution",
            ),
            (
                "missing-node-export",
                lambda background: background.pop("background_node_export"),
                "transport.background.text",
            ),
        ):
            with self.subTest(label=label):
                temporary, path, manifest = self.make_bundle()
                self.addCleanup(temporary.cleanup)
                background = manifest["transport_fidelity"]["export"]["chapters"][0][
                    "background_layer"
                ]
                mutate(background)
                self.rewrite(path, manifest)
                self.assertIn(expected, self.report(path)["error_codes"])

        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        write_png(path.parent / "background.png", 1170, 8, alpha=False)
        self.assertIn(
            "transport.background.resolution", self.report(path)["error_codes"]
        )

    def test_frozen_chapters_must_cover_the_complete_artboard_height(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        manifest["transport_fidelity"]["export"]["artboard"]["height_px"] = 121
        self.rewrite(path, manifest)
        self.assertIn("transport.mapping", self.report(path)["error_codes"])

        for label, y in (("gap", 1), ("overlap", -1)):
            with self.subTest(label=label):
                temporary, path, manifest = self.make_bundle()
                self.addCleanup(temporary.cleanup)
                manifest["transport_fidelity"]["export"]["chapters"][0][
                    "geometry"
                ]["y"] = y
                self.rewrite(path, manifest)
                self.assertIn("transport.mapping", self.report(path)["error_codes"])

    def test_current_root_section_layer_census_and_body_assets_are_exact(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        manifest["transport_fidelity"]["export"]["chapters"][0]["decorations"][
            0
        ]["geometry"]["x"] = 40
        self.rewrite(path, manifest)
        stale_root = self.report(path)
        self.assertIn("transport.attribution", stale_root["error_codes"])

        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        manifest["transport_fidelity"]["export"]["chapters"][0]["decorations"][
            0
        ]["source_node_id"] = "12:99"
        self.rewrite(path, manifest)
        swapped_instance = self.report(path)
        self.assertIn("transport.attribution", swapped_instance["error_codes"])

        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        node_export_path = path.parent / "qa" / "ardot-root-nodes.json"
        node_export = json.loads(node_export_path.read_text(encoding="utf-8"))
        node_export["body_asset_ids"] = node_export["body_asset_ids"][:-1]
        root_revision = current_root_revision_hash(node_export)
        node_export["revision_hash"] = root_revision
        node_export_path.write_text(
            json.dumps(node_export, ensure_ascii=False), encoding="utf-8"
        )
        manifest["ardot"]["revision_hash"] = root_revision
        manifest["workflow_attribution"]["node_export_sha256"] = (
            "sha256:" + file_sha256(node_export_path)
        )
        export = manifest["transport_fidelity"]["export"]
        export["current_root_revision_hash"] = root_revision
        export.pop("revision_hash", None)
        export["revision_hash"] = canonical_transport_revision_hash(export)
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        incomplete = self.report(path)
        self.assertIn("transport.attribution", incomplete["error_codes"])

        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        node_export_path = path.parent / "qa" / "ardot-root-nodes.json"
        node_export = json.loads(node_export_path.read_text(encoding="utf-8"))
        node_export["component_order"].insert(
            -1,
            {
                "node_id": "99:1",
                "component_name": "WeChat/Micro/VisibleButOmitted",
            },
        )
        self.rewrite_root(path, manifest, node_export)
        omitted_visible_component = self.report(path)
        self.assertIn(
            "transport.attribution", omitted_visible_component["error_codes"]
        )

    def test_readback_is_bound_to_revision_and_recomputed_saved_svg(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        readback = self.write_valid_readback(path, manifest)
        payload = json.loads(readback.read_text(encoding="utf-8"))
        payload["transport_revision_hash"] = "sha256:" + "0" * 64
        readback.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.assertIn(
            "transport.readback",
            self.report(path, readback_path=readback, require_readback=True)[
                "error_codes"
            ],
        )

        readback = self.write_valid_readback(path, manifest)
        payload = json.loads(readback.read_text(encoding="utf-8"))
        payload["chapters"][0]["hosted_assets"][0]["url"] = (
            "https://example.com/not-wechat.png"
        )
        readback.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.assertIn(
            "transport.readback",
            self.report(path, readback_path=readback, require_readback=True)[
                "error_codes"
            ],
        )

        readback = self.write_valid_readback(path, manifest)
        saved_svg = path.parent / "saved-mutated.svg"
        saved_svg.write_text("<svg viewBox='0 0 2 2'/>", encoding="utf-8")
        payload = json.loads(readback.read_text(encoding="utf-8"))
        interaction = payload["chapters"][0]["interactions"][0]
        interaction["structure_path"] = saved_svg.name
        interaction["structure_file_sha256"] = "sha256:" + file_sha256(saved_svg)
        readback.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.assertIn(
            "transport.readback",
            self.report(path, readback_path=readback, require_readback=True)[
                "error_codes"
            ],
        )

    def test_stable_codes_cover_each_fail_closed_boundary(self) -> None:
        cases = {
            "transport.mixed_sources": lambda manifest: manifest["transport_fidelity"].__setitem__("source", "manual-html-v1"),
            "transport.mapping": lambda manifest: manifest["transport_fidelity"]["export"].__setitem__("artboard", {"width_px": 391, "height_px": 844}),
            "transport.composite_raster": lambda manifest: manifest["transport_fidelity"]["export"]["chapters"][0]["background_layer"].__setitem__("path", "evidence/section-composite.png"),
            "transport.background.text": lambda manifest: manifest["transport_fidelity"]["export"]["chapters"][0]["background_layer"].__setitem__("contains_text", True),
            "transport.background.resolution": lambda manifest: manifest["transport_fidelity"]["export"]["chapters"][0]["background_layer"].__setitem__("width_px", 1169),
            "transport.native_text.hash": lambda manifest: manifest["transport_fidelity"]["export"]["chapters"][0]["visible_text_nodes"][0].__setitem__("text_sha256", "sha256:" + "b" * 64),
            "transport.native_text.order": lambda manifest: manifest["transport_fidelity"]["export"]["chapters"][0]["visible_text_nodes"][0].__setitem__("order", 2),
            "transport.decoration.independent": lambda manifest: manifest["transport_fidelity"]["export"]["chapters"][0]["decorations"][0].pop("path"),
            "transport.decoration.alpha": lambda manifest: manifest["transport_fidelity"]["export"]["chapters"][0]["decorations"][0].__setitem__("alpha", False),
            "transport.interaction.freehand_svg": lambda manifest: manifest["transport_fidelity"]["export"]["chapters"][0]["interaction"].__setitem__("authored_from", "manual-redraw-v1"),
        }
        for expected, mutate in cases.items():
            with self.subTest(expected=expected):
                temporary, path, manifest = self.make_bundle()
                self.addCleanup(temporary.cleanup)
                mutate(manifest)
                self.rewrite(path, manifest)
                self.assertIn(expected, self.report(path)["error_codes"])

    def test_html_composite_and_readback_are_rejected(self) -> None:
        temporary, path, _ = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        output = path.parent / "composite-output"
        compiled = compile_frozen_transport_candidate(
            path,
            output,
            live_root_path=self.live_root(path, output / "wechat-candidate.html"),
            live_receipt_path=self.live_receipt(path),
            check=True,
        )
        self.assertTrue(compiled["ok"], compiled)
        html = output / "wechat-candidate.html"
        payload = html.read_text(encoding="utf-8")
        html.write_text(
            re.sub(
                r'src="assets/chapter-1-background-[^"]+"',
                'src="evidence/section-composite.png"',
                payload,
                count=1,
            ),
            encoding="utf-8",
        )
        report = self.report(path, html_path=html)
        self.assertIn("transport.composite_raster", report["error_codes"])
        self.assertIn("transport.render_signature", report["error_codes"])
        readback = path.parent / "readback.json"
        readback.write_text(json.dumps({"source": "wrong", "chapters": []}), encoding="utf-8")
        report = self.report(path, readback_path=readback, require_readback=True)
        self.assertIn("transport.readback", report["error_codes"])

    def test_require_readback_is_fail_closed(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        report = self.report(path, require_readback=True)
        self.assertFalse(report["ok"])
        self.assertEqual(
            set(report["error_codes"]),
            {
                "transport.compile_artifact",
                "transport.readback",
            },
        )

        readback = self.write_valid_readback(path, manifest)
        detached = self.report(
            path, readback_path=readback, require_readback=True
        )
        self.assertIn("transport.compile_artifact", detached["error_codes"])

    def test_geometry_style_and_background_changes_invalidate_transport_revision(self) -> None:
        for label, mutate in (
            (
                "geometry",
                lambda export: export["chapters"][0]["visible_text_nodes"][0][
                    "geometry"
                ].__setitem__("x", 30),
            ),
            (
                "style",
                lambda export: export["chapters"][0]["visible_text_nodes"][0][
                    "style"
                ].__setitem__("font_size_px", 18),
            ),
            (
                "background",
                lambda export: export["chapters"][0]["background_layer"].__setitem__(
                    "sha256", "sha256:" + "e" * 64
                ),
            ),
        ):
            with self.subTest(label=label):
                temporary, path, manifest = self.make_bundle()
                self.addCleanup(temporary.cleanup)
                export = manifest["transport_fidelity"]["export"]
                frozen_revision = export["revision_hash"]
                mutate(export)
                self.assertNotEqual(
                    canonical_transport_revision_hash(export), frozen_revision
                )
                path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                report = self.report(path)
                self.assertIn("transport.mapping", report["error_codes"])

    def test_workflow_attribution_must_be_native_unique_and_terminal(self) -> None:
        temporary, path, manifest = self.make_bundle()
        self.addCleanup(temporary.cleanup)
        export = manifest["transport_fidelity"]["export"]
        attribution = export["chapters"][0]["visible_text_nodes"][-1]
        attribution["text"] = "被改动的感谢语"
        attribution["text_sha256"] = text_sha256(attribution["text"])
        self.rewrite(path, manifest)
        report = self.report(path)
        self.assertIn("transport.workflow_attribution", report["error_codes"])


if __name__ == "__main__":
    unittest.main()
