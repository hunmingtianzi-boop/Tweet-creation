from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_transport_fidelity as transport_test_helpers

from scripts.export_ardot_handoff import (
    AT_FDCWD,
    RENAME_EXCL,
    RENAME_NOREPLACE,
    ExclusiveRenameUnsupported,
    Exporter,
    NORMALIZED_SOURCE,
    _atomic_json,
    _exclusive_rename,
)
from scripts.asset_quality import file_sha256
from scripts.compile_wechat import compile_frozen_session_draft
from scripts.transport_fidelity import (
    _export_delivery_assets,
    resolve_local_asset,
    validate_transport_fidelity_diagnostic,
)
from scripts.validate_workflow_attribution import (
    validate_workflow_attribution_handoff,
)


class ArdotHandoffExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secure_runtime = patch("secure_runtime.require_secure_runtime")
        self.secure_runtime.start()
        self.addCleanup(self.secure_runtime.stop)

    def normalized_fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        case = transport_test_helpers.TransportFidelityTests("run")
        temporary, handoff_path, handoff = case.make_bundle()
        root = handoff_path.parent
        export = copy.deepcopy(handoff["transport_fidelity"]["export"])
        root_export = json.loads(
            (root / "qa" / "ardot-root-nodes.json").read_text(encoding="utf-8")
        )

        assets: dict[str, dict] = {}

        def register(asset: dict, **metadata: object) -> str:
            asset_id = asset["asset_id"]
            record = {
                "id": asset_id,
                "path": asset["path"],
                "sha256": asset["sha256"],
                **metadata,
            }
            assets[asset_id] = record
            return asset_id

        chapters = []
        component_names = {
            item["node_id"]: item.get("component_name")
            for item in root_export["visible_text_nodes"]
        }
        for original in export["chapters"]:
            chapter = copy.deepcopy(original)
            background = chapter["background_layer"]
            register(
                background,
                kind="background",
                origin="generated-illustrative",
                visual_role="illustrative-atmosphere",
            )
            chapter["background_layer"] = {
                key: value
                for key, value in background.items()
                if key not in {"path", "sha256", "background_node_export"}
            }
            for field in ("decorations", "photos"):
                converted = []
                for item in chapter[field]:
                    if field == "decorations":
                        register(
                            item,
                            kind="decoration",
                            origin="derived",
                            visual_role="article-micro",
                            roles=["inline-explainer"],
                        )
                    else:
                        register(
                            item,
                            kind="photo",
                            origin="photographed",
                            visual_role="documentary-evidence",
                            source_id=f"source:{item['asset_id']}",
                        )
                    converted.append(
                        {
                            key: value
                            for key, value in item.items()
                            if key not in {"path", "sha256"}
                        }
                    )
                chapter[field] = converted
            reference = chapter["reference_screenshot"]
            register(reference, kind="qa-reference", origin="official")
            chapter["reference_screenshot"] = {
                key: value
                for key, value in reference.items()
                if key not in {"path", "sha256"}
            }
            for node in chapter["visible_text_nodes"]:
                node["component_name"] = component_names[node["node_id"]]
                node.pop("text_sha256", None)
            interaction = chapter["interaction"]
            svg = interaction.pop("svg")
            fallback = interaction.pop("fallback_asset")
            register(svg, kind="interaction-source", origin="derived")
            register(fallback, kind="interaction-fallback", origin="derived")
            interaction.pop("ardot_state_export", None)
            interaction.pop("ardot_state_sha256", None)
            interaction.pop("structure_sha256", None)
            interaction.pop("authored_from", None)
            interaction["svg_asset_id"] = svg["asset_id"]
            interaction["fallback_asset_id"] = fallback["asset_id"]
            chapters.append(chapter)

        cover = next(item for item in handoff["assets"] if item["id"] == "cover")
        assets["cover"] = {
            "id": "cover",
            "path": cover["path"],
            "sha256": cover["sha256"],
            "role": "cover",
            "kind": "cover",
            "origin": "derived",
        }
        normalized = {
            "schema_version": 1,
            "source": NORMALIZED_SOURCE,
            "article": {
                **handoff["article"],
                "cover_asset_id": "cover",
            },
            "ardot": {
                "file_id": export["file_id"],
                "root_node_id": export["root_node_id"],
                "captured_at": handoff["ardot"]["captured_at"],
                "revision_algorithm": "ardot-root-revision-v1",
            },
            "assets": list(assets.values()),
            "chapters": chapters,
            "component_order": root_export["component_order"],
        }
        normalized_path = root / "normalized.json"
        normalized_path.write_text(
            json.dumps(normalized, ensure_ascii=False), encoding="utf-8"
        )
        return temporary, normalized_path

    def test_programmatic_exporter_requires_locked_runtime(self) -> None:
        temporary, source = self.normalized_fixture()
        self.addCleanup(temporary.cleanup)
        self.secure_runtime.stop()
        try:
            with self.assertRaises(SystemExit):
                Exporter(source, source.parent / "untrusted-api-output")
        finally:
            self.secure_runtime.start()

    def test_export_is_deterministic_and_transport_valid(self) -> None:
        temporary, source = self.normalized_fixture()
        self.addCleanup(temporary.cleanup)
        first = source.parent / "handoff-a"
        second = source.parent / "handoff-b"
        report_a = Exporter(source, first).run()
        report_b = Exporter(source, second).run()
        self.assertEqual(report_a["handoff_sha256"], report_b["handoff_sha256"])
        self.assertEqual(
            (first / "handoff.json").read_bytes(),
            (second / "handoff.json").read_bytes(),
        )
        validated = validate_transport_fidelity_diagnostic(first / "handoff.json")
        self.assertTrue(validated["ok"], validated)
        attribution = validate_workflow_attribution_handoff(first / "handoff.json")
        self.assertTrue(attribution["ok"], attribution)
        skeleton = json.loads(
            (first / "qa" / "readback-skeleton.json").read_text(encoding="utf-8")
        )
        self.assertFalse(skeleton["may_satisfy_readback_gate"])

    def test_normalized_export_compiles_with_preuploaded_account_map(self) -> None:
        temporary, source = self.normalized_fixture()
        self.addCleanup(temporary.cleanup)
        output = source.parent / "handoff-compile"
        Exporter(source, output).run()
        handoff_path = output / "handoff.json"
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        export = handoff["transport_fidelity"]["export"]
        observed_at = datetime.now(timezone.utc).isoformat()
        body_assets = []
        for index, (asset_id, descriptor) in enumerate(
            sorted(_export_delivery_assets(export).items()), start=1
        ):
            source_path = resolve_local_asset(handoff_path, descriptor["path"])
            self.assertIsNotNone(source_path)
            assert source_path is not None
            body_assets.append(
                {
                    "asset_id": asset_id,
                    "source_sha256": descriptor["sha256"],
                    "source_byte_length": source_path.stat().st_size,
                    "source_content_type": "image/png",
                    "hosted_url": f"https://mmbiz.qpic.cn/exporter-e2e-{index}",
                    "uploaded_at": observed_at,
                    "response_sha256": "sha256:" + f"{index:064x}"[-64:],
                    "status": "uploaded",
                }
            )
        cover = next(
            asset
            for asset in handoff["assets"]
            if asset["id"] == handoff["article"]["cover_asset_id"]
        )
        cover_path = resolve_local_asset(handoff_path, cover["path"])
        self.assertIsNotNone(cover_path)
        assert cover_path is not None
        upload_map = {
            "schema_version": 1,
            "source": "wechat-account-upload-map-v1",
            "target_account_ref": "appid:exporter-e2e",
            "created_at": observed_at,
            "handoff_sha256": "sha256:" + file_sha256(handoff_path),
            "transport_revision_hash": export["revision_hash"],
            "account_preflight": {
                "status": "passed",
                "target_account_ref": "appid:exporter-e2e",
                "checked_at": observed_at,
                "credential_binding": "sha256:" + "9" * 64,
                "capabilities": {
                    "draft_read": True,
                    "material_read": True,
                    "uploadimg": "proven-only-by-upload-transaction",
                    "material_write": "proven-only-by-upload-transaction",
                    "draft_write": "proven-only-by-draft-transaction",
                    "freepublish": "proven-only-by-submit-and-status-readback",
                },
            },
            "body_assets": body_assets,
            "cover": {
                "asset_id": cover["id"],
                "source_sha256": cover["sha256"],
                "source_byte_length": cover_path.stat().st_size,
                "source_content_type": "image/png",
                "media_id": "permanent-exporter-cover",
                "hosted_url": "https://mmbiz.qpic.cn/exporter-cover",
                "uploaded_at": observed_at,
                "response_sha256": "sha256:" + "8" * 64,
                "status": "uploaded",
            },
        }
        upload_map_path = output / "upload-map.json"
        upload_map_path.write_text(
            json.dumps(upload_map, ensure_ascii=False), encoding="utf-8"
        )
        compiled_dir = output / "compiled"
        helper = transport_test_helpers.TransportFidelityTests("run")
        live_root = helper.live_root(
            handoff_path, compiled_dir / "wechat-candidate.html"
        )
        with patch("secure_runtime.require_secure_runtime"):
            compiled = compile_frozen_session_draft(
                handoff_path,
                compiled_dir,
                live_root_path=live_root,
                upload_map_path=upload_map_path,
                check=True,
            )
        self.assertTrue(compiled["ok"], compiled)
        self.assertEqual(compiled["selected_payload"], "static")

    def test_refuses_overwrite_symlink_and_non_regular_input(self) -> None:
        temporary, source = self.normalized_fixture()
        self.addCleanup(temporary.cleanup)
        output = source.parent / "handoff"
        Exporter(source, output).run()
        with self.assertRaisesRegex(ValueError, "new and absent"):
            Exporter(source, output)

        source_link = source.parent / "normalized-link.json"
        source_link.symlink_to(source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            Exporter(source_link, source.parent / "from-link")

        directory_input = source.parent / "not-a-file"
        directory_input.mkdir()
        with self.assertRaisesRegex(ValueError, "regular.*file"):
            Exporter(directory_input, source.parent / "from-directory")

        output_link = source.parent / "output-link"
        output_link.symlink_to(source.parent / "elsewhere")
        with self.assertRaisesRegex(ValueError, "symlink"):
            Exporter(source, output_link)

    def test_rejects_symlink_in_any_source_asset_or_output_ancestor(self) -> None:
        temporary, source = self.normalized_fixture()
        self.addCleanup(temporary.cleanup)

        source_parent_alias = source.parent / "source-parent-alias"
        source_parent_alias.symlink_to(source.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            Exporter(
                source_parent_alias / source.name,
                source.parent / "from-ancestor-source-link",
            )

        real_output_parent = source.parent / "real-output-parent"
        nested = real_output_parent / "nested"
        nested.mkdir(parents=True)
        output_parent_alias = source.parent / "output-parent-alias"
        output_parent_alias.symlink_to(real_output_parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            Exporter(source, output_parent_alias / "nested" / "handoff")
        self.assertFalse((nested / "handoff").exists())

        payload = json.loads(source.read_text(encoding="utf-8"))
        first_asset = payload["assets"][0]
        asset_parent_alias = source.parent / "asset-parent-alias"
        asset_parent_alias.symlink_to(source.parent, target_is_directory=True)
        first_asset["path"] = f"{asset_parent_alias.name}/{first_asset['path']}"
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "symlink"):
            Exporter(source, source.parent / "from-ancestor-asset-link").run()
        self.assertFalse((source.parent / "from-ancestor-asset-link").exists())

    def test_rejects_preexisting_asset_symlink_and_nonterminal_attribution(self) -> None:
        temporary, source = self.normalized_fixture()
        self.addCleanup(temporary.cleanup)
        payload = json.loads(source.read_text(encoding="utf-8"))
        first_asset = payload["assets"][0]
        linked = source.parent / "asset-link.png"
        linked.symlink_to(source.parent / first_asset["path"])
        first_asset["path"] = linked.name
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "symlink"):
            Exporter(source, source.parent / "symlink-output").run()

        linked.unlink()
        clean_temporary, clean_source = self.normalized_fixture()
        # The second fixture owns its own temporary directory, so keep it
        # explicitly alive for the remainder of this assertion.
        self.addCleanup(clean_temporary.cleanup)
        bad = json.loads(clean_source.read_text(encoding="utf-8"))
        bad["chapters"][0]["visible_text_nodes"].append(
            {
                **bad["chapters"][0]["visible_text_nodes"][0],
                "node_id": "later-text",
                "component_name": "WeChat/Body/Later",
                "text": "This appears after the attribution",
            }
        )
        bad["component_order"].append(
            {"node_id": "later-text", "component_name": "WeChat/Body/Later"}
        )
        clean_source.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "globally terminal"):
            Exporter(clean_source, clean_source.parent / "bad-terminal").run()

    def test_atomic_json_does_not_overwrite_target_created_at_commit(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            destination = root / "evidence.json"
            real_rename = _exclusive_rename

            def race(source: Path, target: Path) -> None:
                self.assertEqual(target, destination)
                target.write_bytes(b"race-winner")
                real_rename(source, target)

            with patch(
                "scripts.export_ardot_handoff._exclusive_rename", side_effect=race
            ):
                with self.assertRaisesRegex(ValueError, "evidence collision"):
                    _atomic_json(destination, {"should": "not overwrite"})

            self.assertEqual(destination.read_bytes(), b"race-winner")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_final_directory_does_not_overwrite_target_created_at_commit(self) -> None:
        temporary, source = self.normalized_fixture()
        self.addCleanup(temporary.cleanup)
        destination = source.parent / "handoff-race"
        real_rename = _exclusive_rename
        raced = False

        def race(staging: Path, target: Path) -> None:
            nonlocal raced
            if target == destination.resolve() and not raced:
                raced = True
                target.mkdir()
                (target / "sentinel").write_bytes(b"race-winner")
            real_rename(staging, target)

        with patch(
            "scripts.export_ardot_handoff._exclusive_rename", side_effect=race
        ):
            with self.assertRaisesRegex(ValueError, "appeared during export"):
                Exporter(source, destination).run()

        self.assertTrue(raced)
        self.assertEqual((destination / "sentinel").read_bytes(), b"race-winner")
        self.assertEqual(list(source.parent.glob(".handoff-race.*.staging")), [])

    def test_exclusive_rename_refuses_preexisting_file_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            source_file = root / "source-file"
            target_file = root / "target-file"
            source_file.write_bytes(b"source")
            target_file.write_bytes(b"target")
            with self.assertRaises(FileExistsError):
                _exclusive_rename(source_file, target_file)
            self.assertEqual(source_file.read_bytes(), b"source")
            self.assertEqual(target_file.read_bytes(), b"target")

            source_dir = root / "source-dir"
            target_dir = root / "target-dir"
            source_dir.mkdir()
            target_dir.mkdir()
            (source_dir / "source").write_bytes(b"source")
            (target_dir / "target").write_bytes(b"target")
            with self.assertRaises(FileExistsError):
                _exclusive_rename(source_dir, target_dir)
            self.assertEqual((source_dir / "source").read_bytes(), b"source")
            self.assertEqual((target_dir / "target").read_bytes(), b"target")

    def test_linux_backend_uses_renameat2_noreplace(self) -> None:
        calls: list[tuple[object, ...]] = []

        class FakeFunction:
            argtypes: object = None
            restype: object = None

            def __call__(self, *args: object) -> int:
                calls.append(args)
                return 0

        function = FakeFunction()
        _exclusive_rename(
            Path("/source"),
            Path("/destination"),
            platform_name="linux",
            libc=SimpleNamespace(renameat2=function),
        )
        self.assertEqual(
            calls,
            [
                (
                    AT_FDCWD,
                    os.fsencode("/source"),
                    AT_FDCWD,
                    os.fsencode("/destination"),
                    RENAME_NOREPLACE,
                )
            ],
        )

    def test_macos_backend_uses_renamex_np_excl(self) -> None:
        calls: list[tuple[object, ...]] = []

        class FakeFunction:
            argtypes: object = None
            restype: object = None

            def __call__(self, *args: object) -> int:
                calls.append(args)
                return 0

        function = FakeFunction()
        _exclusive_rename(
            Path("/source"),
            Path("/destination"),
            platform_name="darwin",
            libc=SimpleNamespace(renamex_np=function),
        )
        self.assertEqual(
            calls,
            [(os.fsencode("/source"), os.fsencode("/destination"), RENAME_EXCL)],
        )

    def test_unsupported_exclusive_rename_fails_closed(self) -> None:
        with self.assertRaisesRegex(ExclusiveRenameUnsupported, "unsupported"):
            _exclusive_rename(
                Path("/source"),
                Path("/destination"),
                platform_name="freebsd",
                libc=SimpleNamespace(),
            )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            destination = root / "evidence.json"
            with patch(
                "scripts.export_ardot_handoff._exclusive_rename",
                side_effect=ExclusiveRenameUnsupported("no primitive"),
            ):
                with self.assertRaises(ExclusiveRenameUnsupported):
                    _atomic_json(destination, {"must": "not appear"})
            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
