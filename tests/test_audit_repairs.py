"""Regression fixtures are synthetic; none certifies a live platform/account."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_quality import compare_screenshots, validate_viewport_review
from production_intent import digest, freeze_intent, validate_delivery_intent
from runtime_preflight import phase_capabilities, _build_host_setup_actions
from transport_fidelity import text_layer_contract, section_render_contract, text_sha256
from wechat_interaction_policy import _validate_mobile_profile, MOBILE_PROFILE_SOURCE, POLICY_VERSION
from ardot_capture_adapter import normalize_capture


def article():
    return {"route": "test-route", "production_preferences": {
        "status": "confirmed", "confirmed_by": "editor", "micro_component_count": 0,
        "use_svg": False, "style_route": "test-route", "generate_backgrounds": False}}


class AuditRepairTests(unittest.TestCase):
    def test_identical_pixels_are_valid_but_a_missing_content_region_is_not(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = Image.new("RGB", (390, 600), "white")
            first.paste("black", (0, 0, 390, 120))
            first.save(root / "a.png")
            first.save(root / "same.png")
            Image.new("RGB", first.size, "white").save(root / "lost.png")
            self.assertTrue(compare_screenshots(root / "a.png", root / "same.png")["ok"])
            self.assertFalse(compare_screenshots(root / "a.png", root / "lost.png")["ok"])
            first.paste("white", (100, 0, 132, 32))
            first.save(root / "local.png")
            result = compare_screenshots(root / "a.png", root / "local.png")
            self.assertLess(result["mean_error"], .03)
            self.assertFalse(result["ok"])

    def test_optional_generation_drives_requirements_and_setup_actions(self):
        profile = {"generation": {"micro_component_count": 0, "generate_backgrounds": False, "generate_cover": False}, "capabilities": {}}
        self.assertEqual(phase_capabilities("authoring", profile), ("visual_inspection", "ardot_authoring"))
        actions = _build_host_setup_actions(profile, "authoring", {})
        self.assertFalse(any("chatgpt" in item["id"] or "provider-acquisition-chain" in item["id"] for item in actions))
        profile["generation"]["generate_cover"] = True
        self.assertIn("opaque_image_generation", phase_capabilities("authoring", profile))
        self.assertNotIn("rgba_cutout_generation", phase_capabilities("authoring", profile))
        profile["generation"]["micro_component_count"] = 1
        self.assertIn("rgba_cutout_generation", phase_capabilities("authoring", profile))
        profile["generation"]["micro_component_count"] = False
        with self.assertRaises(ValueError):
            phase_capabilities("full", profile)

    def test_final_intent_rejects_changed_choices_and_refrozen_wrong_assets(self):
        export = {"chapters": [{"decorations": [], "interaction": []}]}
        handoff = {"article": article(), "assets": []}
        handoff["production_intent"] = freeze_intent(handoff["article"], export)
        self.assertEqual(validate_delivery_intent(handoff, export), [])
        handoff["article"]["production_preferences"]["use_svg"] = True
        self.assertTrue(validate_delivery_intent(handoff, export))
        handoff["article"] = article()
        export["chapters"][0]["decorations"] = [{"asset_id": "unrequested"}]
        handoff["production_intent"] = freeze_intent(handoff["article"], export)
        self.assertTrue(any("count" in x for x in validate_delivery_intent(handoff, export)))
        export["chapters"][0]["decorations"] = []
        handoff["article"]["production_preferences"]["generate_backgrounds"] = True
        handoff["production_intent"] = freeze_intent(handoff["article"], export)
        self.assertTrue(any("background" in x for x in validate_delivery_intent(handoff, export)))

    def test_mobile_editor_review_is_explicit_nonportable_and_byte_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            now = datetime.now(timezone.utc)
            content = "synthetic interaction test"
            sha = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
            profile = {"schema_version": 2, "source": MOBILE_PROFILE_SOURCE, "signature_algorithm": None,
                "assurance_scope": "current-session-editor-reviewed", "key_id": None, "signature": None,
                "nonce": "12" * 16, "policy_version": POLICY_VERSION, "status": "passed", "target_account_id": "test-account",
                "draft_id": "test-draft", "verified_at": now.isoformat(), "valid_until": (now + timedelta(hours=1)).isoformat(),
                "probe_sha256": sha, "readback_sha256": sha, "host_session_id": "synthetic-test", "host_trace_sha256": "sha256:" + "1" * 64,
                "editor_review": {"reviewed_by": "synthetic-test-editor", "review_event_id": "synthetic-confirmation", "scope": "exact-draft-and-both-mobile-interactions"}, "clients": []}
            for i, platform in enumerate(("ios", "android")):
                path = root / f"{platform}.png"
                Image.new("RGB", (390, 844), (50+i, 80, 100)).save(path)
                profile["clients"].append({"platform": platform, "wechat_version": "synthetic", "result": "passed",
                    "preview_evidence": {"path": path.name, "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                    "byte_length": path.stat().st_size, "captured_at": now.isoformat(), "device_session_id": platform}})
            path = root / "profile.json"
            path.write_text(json.dumps(profile))
            args = dict(profile_path=path, candidate_html=content, readback_html=content)
            self.assertFalse(_validate_mobile_profile(profile, "test-account", **args)[0])
            ok, errors, scope = _validate_mobile_profile(profile, "test-account", allow_editor_review=True, **args)
            self.assertTrue(ok, errors)
            self.assertEqual(scope, "current-session-editor-reviewed")
            self.assertFalse(_validate_mobile_profile(profile, "other-account", allow_editor_review=True, **args)[0])
            args["readback_html"] = "changed"
            self.assertFalse(_validate_mobile_profile(profile, "test-account", allow_editor_review=True, **args)[0])

    def test_browser_scales_text_with_container_not_outer_viewport(self):
        playwright = os.environ.get("WECHAT_TEST_PLAYWRIGHT")
        if not playwright:
            self.skipTest("set WECHAT_TEST_PLAYWRIGHT to the installed Playwright module for real-browser regression")
        node = {"node_id": "test-text", "semantic_role": "body", "tag": "p", "z_index": 1,
            "geometry": {"x": 20, "y": 10, "width": 340, "height": 30}, "text_sha256": text_sha256("测试"),
            "style": {"font_family": "system-sans-cn", "font_size_px": 16, "line_height_ratio": 1.5,
            "font_weight": 400, "font_style": "normal", "text_decoration": "none", "letter_spacing_px": 0,
            "text_align": "left", "color": "#000000", "opacity": 1, "blend_mode": "normal"}}
        chapter = {"chapter_id": "test", "section_node_id": "test-section", "geometry": {"x": 0, "y": 0, "width": 390, "height": 100}}
        style = text_layer_contract(node, chapter_height=100)["style"]
        section = section_render_contract(chapter, revision_hash="test")["style"]
        html = f'<div id="fixture"><section style="{section}"><p data-transport-text-node-id="test-text" style="{style}">{"字"*19}</p></section></div>'
        completed = subprocess.run(["node", str(ROOT / "tests/browser_responsive_probe.cjs")], input=json.dumps({"html": html}), text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        samples = json.loads(completed.stdout)
        self.assertEqual([s["width_px"] for s in samples], [320, 390, 430])
        for sample in samples:
            measured = sample["text_layers"][0]
            self.assertAlmostEqual(measured["font_size_px"], 16 * sample["width_px"] / 390, delta=.01)
            self.assertLessEqual(measured["scroll_height_px"], measured["height_px"] + 1)

    def test_viewport_review_cannot_be_omitted(self):
        self.assertTrue(validate_viewport_review(None, base=ROOT, export={}, content_sha256="", account="", draft=""))

    def test_adapter_derives_native_text_and_rejects_background_text(self):
        from workflow_quality import WORKFLOW_ATTRIBUTION_TEXT
        text = {"id": "text", "type": "text", "name": "Footer", "x": 20, "y": 20, "width": 350, "height": 30,
                "content": WORKFLOW_ATTRIBUTION_TEXT, "fontSize": 16, "fontWeight": "400", "fontName": {"family": "PingFang SC", "style": "Regular"},
                "fill": "#000000", "lineHeight": {"unit": "PIXELS", "value": 24}}
        background = {"id": "bg", "type": "frame", "name": "Background", "x": 0, "y": 0, "width": 390, "height": 100}
        section = {"id": "section", "type": "frame", "x": 0, "y": 0, "width": 390, "height": 100, "children": [background, text]}
        capture = {"source": "ardot-batch-read-capture-v1", "file_id": "test", "root_node_id": "root", "captured_at": datetime.now(timezone.utc).isoformat(),
            "root": {"id": "root", "type": "frame", "x": 500, "y": 100, "width": 390, "height": 100, "children": [section]}}
        bindings = {"article": article(), "assets": [], "font_mapping": {"PingFang SC": "system-sans-cn"}, "chapters": [{
            "chapter_id": "test", "section_node_id": "section", "reference_screenshot": {"asset_id": "reference"},
            "background_layer": {"source_node_id": "bg", "asset_id": "background"},
            "visible_text_nodes": [{"node_id": "text", "tag": "p", "semantic_role": "workflow-attribution"}]}]}
        result = normalize_capture(capture, bindings)
        self.assertEqual(result["chapters"][0]["geometry"]["x"], 0)
        self.assertEqual(result["chapters"][0]["visible_text_nodes"][0]["text"], WORKFLOW_ATTRIBUTION_TEXT)
        self.assertEqual(result["chapters"][0]["visible_text_nodes"][0]["geometry"]["x"], 20)
        background["children"] = [text]
        section["children"] = [background]
        with self.assertRaisesRegex(ValueError, "background subtree contains text"):
            normalize_capture(capture, bindings)
