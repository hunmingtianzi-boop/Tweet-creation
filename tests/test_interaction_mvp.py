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


class InteractionMvpTests(unittest.TestCase):
    def test_ab_build_has_input_parity_and_isolated_interactions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            comparison = MODULE.build(output_root=output)
            self.assertTrue(comparison["parity_passed"])
            a = (output / "a-baseline" / "wechat.html").read_text(encoding="utf-8")
            b = (output / "b-dynamic" / "wechat.html").read_text(encoding="utf-8")
            self.assertNotIn("data-interaction=", a)
            self.assertIn('data-interaction="tap-reveal"', b)
            self.assertIn('data-interaction="horizontal-swipe"', b)
            self.assertEqual(
                comparison["variants"]["a-baseline"]["input_sha256"],
                comparison["variants"]["b-dynamic"]["input_sha256"],
            )

    def test_wechat_outputs_have_no_active_script_or_external_stylesheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            MODULE.build(output_root=output)
            for path in output.glob("*/wechat*.html"):
                body = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"<(script|style|iframe|form|link)\b", body, re.I), path)
                self.assertLess(len(body), 20000, path)

    def test_dynamic_has_complete_static_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            MODULE.build(output_root=output)
            content = json.loads((ROOT / "experiments" / "interaction-mvp" / "content.json").read_text(encoding="utf-8"))
            fallback = (output / "b-dynamic" / "wechat-fallback.html").read_text(encoding="utf-8")
            for item in content["ecosystem"]:
                self.assertIn(item["name"], fallback)
                self.assertIn(item["summary"], fallback)
            for item in content["moments"]:
                self.assertIn(item["caption"], fallback)

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
        self.assertEqual(evidence["source_policy"]["mode"], "source-zero")
        self.assertEqual({board["variant"] for board in evidence["boards"]}, {"a-baseline", "b-dynamic"})
        for record in [*evidence["boards"], *evidence["native_components"][:2]]:
            screenshot = experiment / record["screenshot"]
            self.assertTrue(screenshot.is_file())
            self.assertEqual(hashlib.sha256(screenshot.read_bytes()).hexdigest(), record["sha256"])


if __name__ == "__main__":
    unittest.main()
