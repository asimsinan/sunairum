"""Deterministic Scene Layout v2 contracts."""

from __future__ import annotations

import unittest

from tasks.slide_scene import FOOTER_RESERVE, SAFE_INSET, format_scene_layout_block, resolve_slide_scene


class SlideSceneTests(unittest.TestCase):
    def _region(self, scene, identifier):
        return next(region for region in scene["regions"] if region["id"] == identifier)

    def test_figure_scene_reserves_measured_header_then_non_overlapping_lanes(self):
        scene = resolve_slide_scene(
            {
                "title": "A title deliberately long enough to use more than one line in the header band",
                "core_message": "A measured lede must reserve its own height before the PDF figure and claim lanes begin.",
                "figure_id": "pdf-page-3-f1",
            }
        )
        self.assertTrue(scene["ok"], scene["issues"])
        title = self._region(scene, "title")
        lede = self._region(scene, "lede")
        primary = self._region(scene, "primary")
        figure = self._region(scene, "figure")
        self.assertGreaterEqual(primary["y"], lede["y"] + lede["h"] + 27.5)
        self.assertLessEqual(primary["x"] + primary["w"] + 31.5, figure["x"])
        self.assertGreaterEqual(figure["w"], 360)
        self.assertGreater(title["h"], 0)

    def test_two_column_scene_has_safe_plate_and_footer_reservation(self):
        scene = resolve_slide_scene(
            {
                "title": "Comparison",
                "core_message": "Two competing mechanisms are compared without letting a callout overlap either column.",
                "visualization": "two_column_compare",
            }
        )
        self.assertTrue(scene["ok"], scene["issues"])
        left = self._region(scene, "primary")
        right = self._region(scene, "secondary")
        self.assertGreaterEqual(left["x"], SAFE_INSET)
        self.assertLess(left["x"] + left["w"], right["x"])
        self.assertLessEqual(right["y"] + right["h"], 720 - FOOTER_RESERVE)

    def test_scene_prompt_requires_semantic_region_roles(self):
        scene = resolve_slide_scene({"title": "Methods", "figure_id": "f1"})
        block = format_scene_layout_block(scene)
        self.assertIn("data-layout-role", block)
        self.assertIn("figure role=figure", block)
        self.assertIn("do not overlap", block)

    def test_renderer_uses_scene_roles_and_figure_host(self):
        from tasks.scene_html_renderer import render_scene_html

        slide = {
            "title": "Measured figure layout",
            "core_message": "The lede is reserved above both lanes.",
            "figure_id": "pdf-page-3-f1",
            "cards": [{"title": "Claim", "body": "A bounded card body."}],
        }
        html = render_scene_html(slide=slide, scene=resolve_slide_scene(slide))
        self.assertIn('data-layout-role="title"', html)
        self.assertIn('data-layout-role="lede"', html)
        self.assertIn('data-layout-role="primary"', html)
        self.assertIn('data-layout-role="figure"', html)
        self.assertIn('data-pptx="figure"', html)

    def test_two_column_renderer_splits_claims_and_preserves_body_minimum(self):
        from tasks.scene_html_renderer import render_scene_html

        slide = {
            "title": "Comparison",
            "visualization": "two_column_compare",
            "cards": [
                {"title": "A", "body": "First claim"},
                {"title": "B", "body": "Second claim"},
                {"title": "C", "body": "Third claim"},
                {"title": "D", "body": "Fourth claim"},
            ],
        }
        html = render_scene_html(
            slide=slide,
            scene=resolve_slide_scene(slide),
            density="compact",
        )
        self.assertIn('data-layout-role="secondary"', html)
        self.assertNotIn("Supporting evidence", html)
        self.assertIn("font-size:16px", html)
        self.assertIn("padding:16px", html)

    def test_specialized_scenes_emit_reserved_native_hosts(self):
        from tasks.scene_html_renderer import render_scene_html

        cases = [
            ({"title": "Formula", "formula": "J(R)=C(R)/C0"}, 'data-pptx="formula"'),
            ({"title": "Evidence", "table_id": "t7"}, 'data-pptx="table"'),
            ({"title": "Results", "visualization": "ranked_bar_chart"}, 'data-pptx="chart"'),
        ]
        for slide, marker in cases:
            with self.subTest(marker=marker):
                scene = resolve_slide_scene(slide)
                self.assertTrue(scene["ok"], scene["issues"])
                rendered = render_scene_html(slide=slide, scene=scene)
                self.assertIn(marker, rendered)

    def test_formula_renderer_emits_every_grounded_term_and_gloss(self):
        from tasks.scene_html_renderer import render_scene_html

        slide = {
            "title": "Objective",
            "formula": "J(R)=C(R)/C_0+beta(1-Jain(R))+gamma CV(R)",
            "formula_terms": (
                "J(R)=repair objective; C(R)=candidate cost; C_0=initial cost; "
                "beta=equity weight; gamma=variation weight; CV(R)=coefficient of variation"
            ),
            "formula_gloss": "Higher equity weights favor balanced route workloads.",
        }
        rendered = render_scene_html(slide=slide, scene=resolve_slide_scene(slide))
        self.assertEqual(6, rendered.count("data-sunairum-formula-term="))
        self.assertIn("Candidate cost", rendered)
        self.assertIn("Coefficient of variation", rendered)
        self.assertIn("Higher equity weights", rendered)

    def test_three_body_cards_choose_two_columns_instead_of_a_tall_stack(self):
        slide = {
            "title": "Results",
            "cards": [
                {"title": "A", "body": "One"},
                {"title": "B", "body": "Two"},
                {"title": "C", "body": "Three"},
            ],
        }
        scene = resolve_slide_scene(slide)
        self.assertEqual("two_column", scene["composition"])
        self.assertTrue(scene["ok"], scene["issues"])

    def test_title_process_and_multi_chart_compositions_have_explicit_regions(self):
        title_scene = resolve_slide_scene({
            "role": "title",
            "title": "Deck title",
            "lede": "Outline prose must not appear on the cover.",
            "core_message": "Nor should this planning summary.",
        })
        self.assertEqual("title", title_scene["composition"])
        self.assertTrue(title_scene["ok"], title_scene["issues"])
        self.assertFalse(any(r["role"] == "lede" for r in title_scene["regions"]))
        self.assertEqual(0, title_scene["copy_budget"]["lede_lines"])

        process_scene = resolve_slide_scene(
            {"title": "Repair sequence", "visualization": "process_steps"}
        )
        self.assertEqual("process", process_scene["composition"])
        self.assertEqual("process", self._region(process_scene, "primary")["role"])

        chart_scene = resolve_slide_scene(
            {
                "title": "Comparison",
                "visualization": "comparison_columns",
                "charts": {"c1": {"series": []}, "c2": {"series": []}, "c3": {"series": []}},
            }
        )
        self.assertEqual("multi_chart", chart_scene["composition"])
        self.assertEqual(3, len([r for r in chart_scene["regions"] if r["role"] == "chart"]))

        narrative_comparison = resolve_slide_scene(
            {"title": "Comparison", "visualization": "comparison_columns"}
        )
        self.assertEqual("two_column", narrative_comparison["composition"])

    def test_process_renderer_prefers_structured_steps_over_planning_markdown(self):
        from tasks.scene_html_renderer import render_scene_html

        slide = {
            "title": "Three-stage process",
            "visualization": "process_steps",
            "body": "\n".join(f"- planning metadata {index}" for index in range(12)),
            "steps": [
                {"title": "Compose", "body": "Resolve named regions."},
                {"title": "Measure", "body": "Inspect Chromium geometry."},
                {"title": "Gate", "body": "Reject invalid output."},
            ],
        }
        rendered = render_scene_html(slide=slide, scene=resolve_slide_scene(slide))
        self.assertIn("Compose", rendered)
        self.assertIn("Measure", rendered)
        self.assertIn("Gate", rendered)
        self.assertNotIn("planning metadata", rendered)

    def test_eyebrow_is_included_in_title_height_budget(self):
        without = resolve_slide_scene({"title": "One-line title"})
        with_eyebrow = resolve_slide_scene(
            {"title": "One-line title", "eyebrow": "Decision logic"}
        )
        self.assertGreater(
            self._region(with_eyebrow, "title")["h"],
            self._region(without, "title")["h"],
        )
        self.assertGreaterEqual(
            self._region(with_eyebrow, "primary")["y"],
            self._region(with_eyebrow, "title")["y"]
            + self._region(with_eyebrow, "title")["h"],
        )


if __name__ == "__main__":
    unittest.main()
