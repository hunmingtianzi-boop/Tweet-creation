from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from asset_quality import file_sha256  # noqa: E402
from validate_workflow_attribution import (  # noqa: E402
    ARDOT_REVISION_ALGORITHM,
    current_root_revision_hash,
    validate_workflow_attribution_handoff,
)
from workflow_quality import (  # noqa: E402
    WORKFLOW_ATTRIBUTION_MARKER,
    WORKFLOW_ATTRIBUTION_TEXT,
    WORKFLOW_ATTRIBUTION_TEXT_SHA256,
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class WorkflowAttributionHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture_index = 0

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_fixture(
        self,
        *,
        mutate_export: Callable[[dict[str, Any]], None] | None = None,
        mutate_handoff: Callable[[dict[str, Any]], None] | None = None,
    ) -> Path:
        self.fixture_index += 1
        fixture = self.root / f"fixture-{self.fixture_index}"
        asset_dir = fixture / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        cover_path = asset_dir / "cover.png"
        photo_path = asset_dir / "photo-1.png"
        cover_path.write_bytes(b"current cover transport bytes")
        photo_path.write_bytes(b"current photo transport bytes")
        cover_sha = file_sha256(cover_path)
        photo_sha = file_sha256(photo_path)
        export_path = fixture / "qa" / "ardot-root-nodes.json"
        captured_at = "2026-08-31T18:00:00+08:00"
        node_export = {
            "schema_version": 1,
            "source": "ardot-current-root-export",
            "file_id": "ardot-file-current",
            "root_node_id": "30:0",
            "captured_at": captured_at,
            "revision_algorithm": ARDOT_REVISION_ALGORITHM,
            "visible_text_nodes": [
                {
                    "node_id": "30:1",
                    "component_name": "WeChat/Hero/Fresh",
                    "node_kind": "TEXT",
                    "text": "Current article title",
                    "native_editable_text": True,
                    "visible": True,
                    "rasterized": False,
                },
                {
                    "node_id": "90:1",
                    "component_name": "WeChat/Footer/WorkflowAttribution/Fresh",
                    "node_kind": "TEXT",
                    "text": WORKFLOW_ATTRIBUTION_TEXT,
                    "native_editable_text": True,
                    "visible": True,
                    "rasterized": False,
                },
            ],
            "component_order": [
                {"node_id": "30:1", "component_name": "WeChat/Hero/Fresh"},
                {
                    "node_id": "90:1",
                    "component_name": "WeChat/Footer/WorkflowAttribution/Fresh",
                },
            ],
            "assets": [
                {"id": "cover", "sha256": cover_sha},
                {"id": "photo-1", "sha256": photo_sha},
            ],
        }
        revision_hash = current_root_revision_hash(node_export)
        node_export["revision_hash"] = revision_hash
        if mutate_export:
            mutate_export(node_export)
        write_json(export_path, node_export)
        handoff = {
            "schema_version": 4,
            "ardot": {
                "file_id": "ardot-file-current",
                "root_node_id": "30:0",
                "captured_at": captured_at,
                "revision_algorithm": ARDOT_REVISION_ALGORITHM,
                "revision_hash": revision_hash,
            },
            "workflow_attribution": {
                "policy_id": WORKFLOW_ATTRIBUTION_MARKER,
                "classification": "repository-usage-credit",
                "text": WORKFLOW_ATTRIBUTION_TEXT,
                "text_sha256": f"sha256:{WORKFLOW_ATTRIBUTION_TEXT_SHA256}",
                "ardot_node_id": "90:1",
                "component_name": "WeChat/Footer/WorkflowAttribution/Fresh",
                "node_kind": "TEXT",
                "native_editable_text": True,
                "visible": True,
                "terminal": True,
                "organization_identity": False,
                "body_fact": False,
                "visual_reference": False,
                "node_export_file": "qa/ardot-root-nodes.json",
                "node_export_sha256": f"sha256:{file_sha256(export_path)}",
            },
            "assets": [
                {
                    "id": "cover",
                    "path": "assets/cover.png",
                    "sha256": cover_sha,
                    "role": "cover",
                },
                {
                    "id": "photo-1",
                    "path": "assets/photo-1.png",
                    "sha256": photo_sha,
                    "role": "body-image",
                },
            ],
        }
        if mutate_handoff:
            mutate_handoff(handoff)
        handoff_path = fixture / "handoff.json"
        write_json(handoff_path, handoff)
        return handoff_path

    def test_current_root_and_saved_draft_readback_pass(self) -> None:
        handoff_path = self.make_fixture()
        readback_path = handoff_path.parent / "saved-draft-visible-text.txt"
        readback_path.write_text(
            f"Current article title\n\n{WORKFLOW_ATTRIBUTION_TEXT}\n",
            encoding="utf-8",
        )
        report = validate_workflow_attribution_handoff(
            handoff_path,
            saved_draft_visible_text_path=readback_path,
            require_readback=True,
        )
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(report["ardot_evidence_ready"])
        self.assertTrue(report["readback"]["present_once"])
        self.assertTrue(report["readback"]["terminal"])

    def test_legacy_changed_hidden_rasterized_nonterminal_and_stale_fail(self) -> None:
        export_cases = {
            "changed-text": lambda value: value["visible_text_nodes"][-1].update(
                {"text": "感谢其他工作流。"}
            ),
            "body-changed-after-revision": lambda value: value["visible_text_nodes"][
                0
            ].update({"text": "BODY CHANGED AFTER CLAIMED REVISION"}),
            "hidden": lambda value: value["visible_text_nodes"][-1].update(
                {"visible": False}
            ),
            "rasterized": lambda value: value["visible_text_nodes"][-1].update(
                {"rasterized": True}
            ),
            "wrong-kind": lambda value: value["visible_text_nodes"][-1].update(
                {"node_kind": "IMAGE"}
            ),
            "nonterminal": lambda value: value["visible_text_nodes"].append(
                {
                    "node_id": "91:1",
                    "component_name": "WeChat/Footer/Extra/Fresh",
                    "node_kind": "TEXT",
                    "text": "Trailing text",
                    "native_editable_text": True,
                    "visible": True,
                    "rasterized": False,
                }
            ),
            "stale-revision": lambda value: value.update(
                {"revision_hash": "sha256:" + "b" * 64}
            ),
            "missing-node": lambda value: value.update(
                {"visible_text_nodes": value["visible_text_nodes"][:1]}
            ),
        }
        for label, mutate in export_cases.items():
            with self.subTest(label=label):
                report = validate_workflow_attribution_handoff(
                    self.make_fixture(mutate_export=mutate)
                )
                self.assertFalse(report["ok"])
                self.assertFalse(report["ardot_evidence_ready"])

        handoff_cases = {
            "legacy-v3": lambda value: value.update({"schema_version": 3}),
            "changed-policy": lambda value: value["workflow_attribution"].update(
                {"policy_id": "other-policy"}
            ),
            "changed-component": lambda value: value["workflow_attribution"].update(
                {"component_name": "WeChat/Footer/Other/Fresh"}
            ),
            "forged-export-hash": lambda value: value["workflow_attribution"].update(
                {"node_export_sha256": "sha256:" + "0" * 64}
            ),
        }
        for label, mutate in handoff_cases.items():
            with self.subTest(label=label):
                report = validate_workflow_attribution_handoff(
                    self.make_fixture(mutate_handoff=mutate)
                )
                self.assertFalse(report["ok"])
                self.assertFalse(report["ardot_evidence_ready"])

    def test_saved_draft_requires_exactly_one_terminal_credit(self) -> None:
        handoff_path = self.make_fixture()
        cases = {
            "missing": "Current article title",
            "duplicate": f"{WORKFLOW_ATTRIBUTION_TEXT} body {WORKFLOW_ATTRIBUTION_TEXT}",
            "nonterminal": f"{WORKFLOW_ATTRIBUTION_TEXT} trailing text",
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                readback_path = handoff_path.parent / f"readback-{label}.txt"
                readback_path.write_text(text, encoding="utf-8")
                report = validate_workflow_attribution_handoff(
                    handoff_path,
                    saved_draft_visible_text_path=readback_path,
                    require_readback=True,
                )
                self.assertFalse(report["ok"])
                self.assertFalse(report["readback"]["ready"])

    def test_changed_transport_asset_invalidates_handoff(self) -> None:
        handoff_path = self.make_fixture()
        (handoff_path.parent / "assets" / "cover.png").write_bytes(b"changed cover")
        report = validate_workflow_attribution_handoff(handoff_path)
        self.assertFalse(report["ok"])
        self.assertFalse(report["ardot_evidence_ready"])
        self.assertTrue(any("does not match its file" in item for item in report["errors"]))

    def test_cli_exit_codes_match_gate(self) -> None:
        handoff_path = self.make_fixture()
        good = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_workflow_attribution.py"), str(handoff_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(good.returncode, 0, good.stderr + good.stdout)
        broken = copy.deepcopy(json.loads(handoff_path.read_text(encoding="utf-8")))
        broken["schema_version"] = 3
        write_json(handoff_path, broken)
        bad = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_workflow_attribution.py"), str(handoff_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bad.returncode, 1, bad.stderr + bad.stdout)


if __name__ == "__main__":
    unittest.main()
