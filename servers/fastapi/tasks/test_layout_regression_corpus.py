"""Frozen failure corpus for Scene layout and optional live Chromium QA."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from tasks.scene_html_renderer import render_scene_html
from tasks.slide_scene import resolve_slide_scene


CORPUS = Path(__file__).with_name("fixtures") / "layout_regression_corpus.json"


class LayoutRegressionCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(CORPUS.read_text(encoding="utf-8"))

    def test_every_frozen_case_resolves_and_preserves_authored_cards(self):
        self.assertGreaterEqual(len(self.cases), 6)
        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                scene = resolve_slide_scene(case)
                self.assertTrue(scene["ok"], scene["issues"])
                rendered = render_scene_html(slide=case, scene=scene)
                self.assertIn('class="slide"', rendered)
                self.assertIn('data-layout-id="scene-title"', rendered)
                for card in case.get("cards") or []:
                    self.assertIn(card["title"], rendered)
                    self.assertIn(card["body"], rendered)
                if case.get("formula_terms"):
                    self.assertEqual(
                        8,
                        rendered.count("data-sunairum-formula-term="),
                    )
                    self.assertIn(case["formula_gloss"], rendered)

    @unittest.skipUnless(
        os.environ.get("RUN_LAYOUT_E2E") == "1",
        "set RUN_LAYOUT_E2E=1 where Chromium is available",
    )
    def test_every_frozen_case_passes_live_browser_geometry(self):
        from tasks.html_layout_qa import audit_runtime_html_layout

        for case in self.cases:
            with self.subTest(case=case["case_id"]):
                html = render_scene_html(slide=case, scene=resolve_slide_scene(case))
                report = audit_runtime_html_layout(html)
                self.assertTrue(report["ok"], report["hard"])


if __name__ == "__main__":
    unittest.main()
