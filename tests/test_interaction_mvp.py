from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "experiments" / "interaction-mvp" / "build_experiment.py"
SPEC = importlib.util.spec_from_file_location("interaction_mvp", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
TEST_FALLBACK_HASH = "sha256:" + "a" * 64


class InteractionMvpTests(unittest.TestCase):
    def test_ab_build_has_input_parity_and_isolated_interactions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            comparison = MODULE.build(output_root=output)
            self.assertTrue(comparison["parity_passed"])
            a = (output / "a-baseline" / "candidate-fragment.html").read_text(encoding="utf-8")
            b = (output / "b-dynamic" / "candidate-fragment.html").read_text(encoding="utf-8")
            self.assertNotIn("data-interaction=", a)
            self.assertIn('data-interaction="svg-smil-self"', b)
            self.assertIn('data-interaction="horizontal-swipe"', b)
            self.assertIn('begin="click"', b)
            self.assertIn("<animateTransform", b)
            self.assertNotIn("<details", b)
            self.assertNotRegex(b, r"\sid=")
            self.assertNotRegex(b, r'begin="[^"]+\.click"')
            self.assertEqual(
                comparison["variants"]["a-baseline"]["input_sha256"],
                comparison["variants"]["b-dynamic"]["input_sha256"],
            )
            self.assertEqual(
                comparison["interaction_policy_version"],
                MODULE.POLICY_VERSION,
            )

    def test_dynamic_candidate_is_safe_but_not_certified_without_readback_and_mobile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            MODULE.build(output_root=output)
            report = json.loads(
                (output / "b-dynamic" / "interaction-policy-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(report["ok"], report["errors"])
            self.assertEqual(report["status"], "candidate")
            self.assertFalse(report["dynamic_eligible"])
            self.assertEqual(report["recommended_payload"], "static-fallback")
            self.assertTrue(report["fallback_complete"])
            self.assertIn("saved-draft readback is missing", report["certification_errors"])

    def test_saved_readback_and_ios_android_evidence_certify_dynamic_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            MODULE.build(output_root=output)
            candidate = (output / "b-dynamic" / "candidate-fragment.html").read_text(encoding="utf-8")
            fallback = (output / "b-dynamic" / "static-fallback-fragment.html").read_text(
                encoding="utf-8"
            )
            profile = {
                "schema_version": 1,
                "policy_version": MODULE.POLICY_VERSION,
                "status": "passed",
                "target_account_id": "account-under-test",
                "draft_id": "draft-under-test",
                "verified_at": "2026-08-28T18:03:00+08:00",
                "valid_until": "2099-08-28T18:03:00+08:00",
                "probe_sha256": "a" * 64,
                "readback_sha256": "b" * 64,
                "clients": [
                    {
                        "platform": "ios",
                        "wechat_version": "test-version-ios",
                        "result": "passed",
                        "preview_evidence": "evidence/ios-preview.png",
                    },
                    {
                        "platform": "android",
                        "wechat_version": "test-version-android",
                        "result": "passed",
                        "preview_evidence": "evidence/android-preview.png",
                    },
                ],
            }
            report = MODULE.audit_transport(
                candidate,
                fallback_html=fallback,
                readback_html=candidate,
                mobile_profile=profile,
                target_account_id="account-under-test",
            )
            self.assertTrue(report["dynamic_eligible"], report["certification_errors"])
            self.assertEqual(report["status"], "certified")
            self.assertEqual(report["recommended_payload"], "dynamic")

    def test_legacy_details_and_cross_id_smil_are_rejected(self) -> None:
        legacy = MODULE.audit_transport(
            '<details data-interaction="tap-reveal"><summary>open</summary>x</details>',
            fallback_html='<div data-fallback-key="x">x</div>',
        )
        self.assertFalse(legacy["ok"])
        self.assertTrue(any("forbidden tag <details>" in item for item in legacy["errors"]))

        cross_id = MODULE.audit_transport(
            f'<svg id="card" data-interaction="svg-smil-self" data-policy-version="{MODULE.POLICY_VERSION}" data-fallback-key="x" data-fallback-hash="{TEST_FALLBACK_HASH}">'
            '<g><animateTransform attributeName="transform" begin="card.click">'
            '</animateTransform></g></svg>',
            fallback_html=f'<div data-fallback-key="x" data-fallback-hash="{TEST_FALLBACK_HASH}">x</div>',
        )
        self.assertFalse(cross_id["ok"])
        self.assertTrue(any("id is forbidden" in item for item in cross_id["errors"]))
        self.assertTrue(any('begin="click"' in item for item in cross_id["errors"]))

    def test_self_trigger_set_is_inside_the_fixed_allowlist(self) -> None:
        candidate = (
            f'<svg data-interaction="svg-smil-self" data-policy-version="{MODULE.POLICY_VERSION}" data-fallback-key="color" data-fallback-hash="{TEST_FALLBACK_HASH}">'
            '<circle fill="#000"><set attributeName="fill" to="#fff" '
            'begin="click" fill="freeze"></set></circle></svg>'
        )
        report = MODULE.audit_transport(
            candidate,
            fallback_html=f'<div data-fallback-key="color" data-fallback-hash="{TEST_FALLBACK_HASH}">color</div>',
        )
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["candidate"]["self_begin_click_count"], 1)

    def test_active_markup_and_external_svg_images_are_rejected(self) -> None:
        for payload in (
            "<style>p{color:red}</style><p>x</p>",
            '<a href="javascript:alert(1)">x</a>',
            '<p onclick="alert(1)">x</p>',
            '<p style="background:url(javascript:alert(1))">x</p>',
        ):
            report = MODULE.audit_transport(payload)
            self.assertFalse(report["ok"], payload)

        external_image = (
            f'<svg data-interaction="svg-smil-self" data-policy-version="{MODULE.POLICY_VERSION}" data-fallback-key="image" '
            f'data-fallback-hash="{TEST_FALLBACK_HASH}">'
            '<image href="https://example.com/photo.png"></image>'
            '<g><set attributeName="opacity" to="0" begin="click"></set></g></svg>'
        )
        fallback = (
            f'<div data-fallback-key="image" data-fallback-hash="{TEST_FALLBACK_HASH}">'
            "image</div>"
        )
        rejected = MODULE.audit_transport(external_image, fallback_html=fallback)
        self.assertFalse(rejected["ok"])
        self.assertTrue(any("mmbiz.qpic.cn" in item for item in rejected["errors"]))

        wechat_image = external_image.replace(
            "https://example.com/photo.png",
            "https://mmbiz.qpic.cn/mmbiz_png/example/640",
        )
        accepted = MODULE.audit_transport(wechat_image, fallback_html=fallback)
        self.assertTrue(accepted["ok"], accepted["errors"])

    def test_fallback_hash_and_readback_signature_mismatches_cannot_certify(self) -> None:
        candidate = (
            f'<svg data-interaction="svg-smil-self" data-policy-version="{MODULE.POLICY_VERSION}" data-fallback-key="x" '
            f'data-fallback-hash="{TEST_FALLBACK_HASH}"><g>'
            '<animateTransform attributeName="transform" type="translate" '
            'values="0 0;0 -10" dur="0.3s" begin="click" fill="freeze">'
            "</animateTransform></g></svg>"
        )
        wrong_fallback = (
            '<div data-fallback-key="x" data-fallback-hash="sha256:' + "b" * 64 + '">x</div>'
        )
        mismatch = MODULE.audit_transport(candidate, fallback_html=wrong_fallback)
        self.assertFalse(mismatch["ok"])
        self.assertTrue(any("semantic hashes" in item for item in mismatch["errors"]))

        fallback = (
            f'<div data-fallback-key="x" data-fallback-hash="{TEST_FALLBACK_HASH}">x</div>'
        )
        changed_readback = candidate.replace('values="0 0;0 -10"', 'values="0 0;0 -8"')
        report = MODULE.audit_transport(
            candidate,
            fallback_html=fallback,
            readback_html=changed_readback,
            mobile_profile={
                "schema_version": 1,
                "policy_version": MODULE.POLICY_VERSION,
                "status": "passed",
                "target_account_id": "account",
                "draft_id": "draft",
                "verified_at": "2026-08-28T18:03:00+08:00",
                "valid_until": "2099-08-28T18:03:00+08:00",
                "probe_sha256": "a" * 64,
                "readback_sha256": "b" * 64,
                "clients": [
                    {
                        "platform": platform,
                        "wechat_version": "test",
                        "result": "passed",
                        "preview_evidence": f"evidence/{platform}.png",
                    }
                    for platform in ("ios", "android")
                ],
            },
            target_account_id="account",
        )
        self.assertFalse(report["dynamic_eligible"])
        self.assertTrue(
            any("SMIL structure signatures" in item for item in report["certification_errors"])
        )

    def test_mobile_profile_is_account_specific_unexpired_and_cross_platform(self) -> None:
        candidate = (
            f'<svg data-interaction="svg-smil-self" data-policy-version="{MODULE.POLICY_VERSION}" data-fallback-key="x" '
            f'data-fallback-hash="{TEST_FALLBACK_HASH}"><circle>'
            '<set attributeName="fill" to="#fff" begin="click"></set>'
            "</circle></svg>"
        )
        fallback = (
            f'<div data-fallback-key="x" data-fallback-hash="{TEST_FALLBACK_HASH}">x</div>'
        )
        incomplete_profile = {
            "schema_version": 1,
            "policy_version": MODULE.POLICY_VERSION,
            "status": "passed",
            "target_account_id": "wrong-account",
            "draft_id": "draft",
            "probe_sha256": "a" * 64,
            "readback_sha256": "b" * 64,
            "verified_at": "2020-01-01T00:00:00Z",
            "valid_until": "2020-02-01T00:00:00Z",
            "clients": [
                {
                    "platform": "ios",
                    "wechat_version": "test",
                    "result": "passed",
                    "preview_evidence": "evidence/ios.png",
                }
            ],
        }
        report = MODULE.audit_transport(
            candidate,
            fallback_html=fallback,
            readback_html=candidate,
            mobile_profile=incomplete_profile,
            target_account_id="target-account",
        )
        self.assertFalse(report["dynamic_eligible"])
        joined = "\n".join(report["certification_errors"])
        self.assertIn("does not match", joined)
        self.assertIn("expired", joined)
        self.assertIn("android", joined)

    def test_candidate_fragments_have_no_active_script_or_external_stylesheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            MODULE.build(output_root=output)
            for path in output.glob("*/*fragment.html"):
                body = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"<(script|style|iframe|form|link)\b", body, re.I), path)
                self.assertLess(len(body), 20000, path)

    def test_dynamic_has_complete_static_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            MODULE.build(output_root=output)
            content = json.loads((ROOT / "experiments" / "interaction-mvp" / "content.json").read_text(encoding="utf-8"))
            fallback = (output / "b-dynamic" / "static-fallback-fragment.html").read_text(encoding="utf-8")
            for item in content["ecosystem"]:
                self.assertIn(item["name"], fallback)
                self.assertIn(item["summary"], fallback)
            for item in content["moments"]:
                self.assertIn(item["caption"], fallback)

    def test_experiment_cannot_create_a_delivery_or_clipboard_import_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "import-assistant.html").write_text(
                "<button>copy old wechat html</button>", encoding="utf-8"
            )
            stale_variant = output / "b-dynamic"
            stale_variant.mkdir()
            (stale_variant / "wechat.html").write_text(
                "<article>obsolete delivery payload</article>", encoding="utf-8"
            )
            comparison = MODULE.build(output_root=output)
            self.assertFalse((output / "import-assistant.html").exists())
            self.assertEqual(list(output.glob("*/wechat*.html")), [])
            self.assertEqual(
                comparison["removed_stale_delivery_artifacts"],
                ["b-dynamic/wechat.html", "import-assistant.html"],
            )
            for record in comparison["variants"].values():
                self.assertFalse(record["delivery_eligible"])
                self.assertEqual(
                    record["delivery_blocker"],
                    "transport.source.experiment_renderer_forbidden",
                )
            dashboard = (output / "compare.html").read_text(encoding="utf-8")
            self.assertNotIn("ClipboardItem", dashboard)
            self.assertNotIn("导入微信公众号", dashboard)
            self.assertIn("实验片段不可投递", dashboard)

    def test_both_variants_copy_the_same_photo_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            MODULE.build(output_root=output)
            a_assets = sorted(path.name for path in (output / "a-baseline" / "assets").iterdir())
            b_assets = sorted(path.name for path in (output / "b-dynamic" / "assets").iterdir())
            self.assertEqual(a_assets, b_assets)

    def test_ardot_evidence_is_hashed_and_source_zero(self) -> None:
        experiment = ROOT / "experiments" / "interaction-mvp"
        evidence = json.loads((experiment / "ardot-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["schema_version"], 2)
        self.assertEqual(evidence["source_policy"]["mode"], "source-zero")
        self.assertEqual({board["variant"] for board in evidence["boards"]}, {"a-baseline", "b-dynamic"})
        for record in [*evidence["boards"], *evidence["native_components"][:2]]:
            screenshot = experiment / record["screenshot"]
            self.assertTrue(screenshot.is_file())
            self.assertEqual(hashlib.sha256(screenshot.read_bytes()).hexdigest(), record["sha256"])
        selectors = {item["html_selector"] for item in evidence["runtime_mapping"]}
        self.assertIn('[data-interaction="svg-smil-self"]', selectors)
        self.assertNotIn('[data-interaction="tap-reveal"]', selectors)
        self.assertEqual(evidence["capability_evidence"]["mobile_runtime_status"], "pending")

    def test_live_probe_fixture_preserves_structure_without_claiming_mobile_runtime(self) -> None:
        fixture_dir = ROOT / "tests" / "fixtures" / "wechat-capability"
        source = fixture_dir / "probe-v2-source.html"
        readback = json.loads((fixture_dir / "probe-v2-readback.json").read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), readback["source_sha256"])
        observed = readback["observed_structure"]
        self.assertTrue(readback["prior_cross_id_probe"]["source_used_ids"])
        self.assertEqual(readback["prior_cross_id_probe"]["ids_after_save"], 0)
        self.assertEqual(observed["ids_after_save"], 0)
        self.assertTrue(observed["css_horizontal_overflow_preserved"])
        self.assertEqual(
            {item["tag"] for item in observed["self_trigger_elements"]},
            {"set", "animateTransform"},
        )
        self.assertTrue(all(item["begin"] == "click" for item in observed["self_trigger_elements"]))
        self.assertEqual(readback["mobile_runtime"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
