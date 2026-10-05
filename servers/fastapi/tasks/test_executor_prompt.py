"""Executor per-slide prompt + design_spec pack + layout modes."""

from __future__ import annotations

import unittest


_MINI_SPEC = """\
<!-- sunairum-schema: design-spec/v1 -->
# Demo - Design Spec

## I. Project Information

- **Core message:** Demo core

## III. Visual Theme

- **Style:** Corporate academic
- Primary navy: `#1E3A8A`
- Accent amber: `#F59E0B`

## V. Layout Principles

- Each slide has one governing assertion.

## IX. Content Outline

### P01: Title Plate

- **Title:** Title Plate
- **Content:**
  - Cover line
- **Layout:** Centered title plate
- **Visual job:** Establish identity

### P02: Why Vehicle Routing Needs Both Scale and Balance

- **Title:** Why Vehicle Routing Needs Both Scale and Balance
- **Core message:** Cost-focused repair can be computationally expensive and operationally unbalanced.
- **Layout:** Two-column composition; left side frames the VRPTW setting and workload concern, while right side contrasts exhaustive insertion evaluation with balanced workload goals.
- **Content:**
  - VRPTW must respect customer service windows and vehicle capacity.
  - ALNS repair repeatedly evaluates candidate insertion positions.
  - Cost minimization alone can leave drivers with uneven route workloads.
  - The design target: fewer evaluated candidates without abandoning feasibility checks.
- **Visual job:** Make the computational bottleneck and operational gap legible before introducing HERO.
- **Evidence:** `ev-page-01-block-007`

### P03: The Design Question Behind HERO

- **Title:** The Design Question Behind HERO
- **Content:**
  - Can repair search avoid scanning the full insertion space?
- **Layout:** Large central question with a memorable gap framing
- **Visual job:** State the research gap

### P04: Equity-Aware Insertion Objective

- **Title:** Equity-Aware Insertion Objective
- **Core message:** HERO trades distance for lower CV through a normalized objective.
- **Layout:** Centered formula block with labeled terms; balance scale for cost-equity.
- **Content:**
  - Workload = route travel distance
  - F = D_norm + beta CV_norm + gamma (1 - J_norm)
- **Visual job:** Explain the objective semantics

## X. Speaker Notes

- **P01:** Introduce the paper title and presenter.
- **P02:** Explain the operational setting and why total distance is not the only meaningful routing outcome.
- **P03:** Introduce the central design question.
- **P04:** Walk through the formula.
"""


class ExecutorPromptTests(unittest.TestCase):
    def test_strategist_prompt_separates_content_from_speaker_notes(self):
        from tasks.strategist_agent import SYSTEM_PROMPT

        self.assertIn("viewer-readable on-slide", SYSTEM_PROMPT)
        self.assertIn("§X Speaker Notes", SYSTEM_PROMPT)
        self.assertIn("Forbidden as Content openers", SYSTEM_PROMPT)
        self.assertIn("Introduce", SYSTEM_PROMPT)
        for marker in (
            "# CONTEXT",
            "# OBJECTIVE",
            "# STYLE",
            "# TONE",
            "# AUDIENCE",
            "# RESPONSE",
        ):
            self.assertIn(marker, SYSTEM_PROMPT)

    def test_extract_pack_is_sample_shaped(self):
        from tasks.free_design_pipeline import extract_executor_design_pack

        pack = extract_executor_design_pack(_MINI_SPEC, 2)
        self.assertIn("## III. Visual Theme", pack)
        self.assertIn("#1E3A8A", pack)
        self.assertIn("### P02: Why Vehicle Routing Needs Both Scale and Balance", pack)
        self.assertIn("ALNS repair repeatedly evaluates candidate insertion positions.", pack)
        self.assertNotIn("### P03:", pack)
        self.assertIn("do NOT paint on the slide", pack)



    def test_chart_metrics_beats_formula_language(self):
        from tasks.executor_modes import resolve_executor_mode

        slide = {
            "slide": 11,
            "role": "content",
            "title": "Across Solomon classes",
            "content": {
                "BODY": "CV reduction and cost increase relative to the baseline. Bars show percentages."
            },
            "layout_intent": "Grouped bars for CV reduction vs cost increase",
            "visual_job": "Show metrics comparison across classes",
            "has_chart": True,
        }
        self.assertEqual("chart_sidebar", resolve_executor_mode(slide, pack=""))





    def test_false_formula_hero_rejected_without_formula_ir(self):
        from tasks.executor_modes import resolve_executor_mode

        mode = resolve_executor_mode(
            {
                "role": "content",
                "title": "What the results support",
                "content": {"BODY": "HERO objective synthesis on the left"},
                "layout_intent": "Two-column synthesis; bottom-line takeaway",
                "formula": "",
            }
        )
        self.assertNotEqual("formula_hero", mode)
        self.assertEqual("two_column_takeaway", mode)


    def test_strip_empty_figure_slots(self):
        from tasks.free_design_pipeline import strip_empty_figure_slots

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text x="40" y="80">Keep</text>'
            '<g data-sunairum-figure-slot="1" data-sunairum-figure-id="none" '
            'transform="translate(640,160)">'
            '<rect width="616" height="400" fill="none"/></g>'
            "</svg>"
        )
        out = strip_empty_figure_slots(svg, figure_id="")
        self.assertIn("Keep", out)
        self.assertNotIn("figure-slot", out)
        self.assertNotIn('figure-id="none"', out)
        kept = strip_empty_figure_slots(
            svg.replace('figure-id="none"', 'figure-id="pdf-page-3-picture-1"'),
            figure_id="pdf-page-3-picture-1",
        )
        self.assertIn("figure-slot", kept)



    def test_detect_merged_multi_card_text(self):
        from tasks.free_design_pipeline import detect_merged_multi_card_text

        merged = (
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<text x="40" y="200">'
            '<tspan font-weight="700">VRPTW setting</tspan>'
            '<tspan dy="40" font-weight="700">Computational bottleneck</tspan>'
            "</text></svg>"
        )
        self.assertTrue(detect_merged_multi_card_text(merged))


    def test_soft_prompt_hosts_not_hard_aabb(self):
        from tasks.free_design_pipeline import build_executor_slide_prompt, EXECUTOR_SYSTEM

        self.assertIn("## Hard", EXECUTOR_SYSTEM)
        self.assertIn("## Defaults", EXECUTOR_SYSTEM)
        self.assertNotIn("Exclusive regions", EXECUTOR_SYSTEM)
        prompt = build_executor_slide_prompt(
            slide={
                "slide": 9,
                "role": "content",
                "title": "Results table",
                "table_id": "src-table-002",
                "layout_intent": "Table on the right",
                "content": {"BODY": "Benchmark summary"},
            },
            spec_lock_md="lock",
            design_spec_md="",
            prior_summary="",
        )
        self.assertIn("Table host", prompt)
        self.assertNotIn("## Design language (HARD)", prompt)

    def test_host_layout_figure_only_when_bound(self):
        from tasks.slide_regions import layout_for_slide

        layout = layout_for_slide({"role": "content", "figure_id": ""})
        self.assertEqual("host_preferred", layout.recipe)
        self.assertIsNone(layout.region("figure"))
        layout2 = layout_for_slide({"role": "content", "figure_id": "pdf-1"})
        self.assertIsNotNone(layout2.region("figure"))

    def test_instructional_content_guard_in_prompt(self):
        from tasks.free_design_pipeline import build_executor_slide_prompt

        prompt = build_executor_slide_prompt(
            slide={
                "slide": 3,
                "role": "content",
                "title": "Motivation",
                "core_message": "Balance matters as much as speed.",
                "content": {
                    "BODY": (
                        "Introduce customers, time windows, capacity. "
                        "Explain that ALNS repair evaluates insertions."
                    )
                },
            },
            spec_lock_md="lock",
            design_spec_md="",
            prior_summary="",
        )
        self.assertIn("Instructional Content guard", prompt)
        self.assertIn("brief only", prompt.casefold())

    def test_prior_diary_in_soft_prompt(self):
        from tasks.free_design_pipeline import build_executor_slide_prompt

        prompt = build_executor_slide_prompt(
            slide={
                "slide": 3,
                "role": "content",
                "title": "Gap",
                "layout_intent": "Large central question",
                "content": {"BODY": "One idea"},
            },
            spec_lock_md="lock",
            design_spec_md="",
            prior_summary="",
            prior_diary="P02:kpi_cards:stack:3cards",
        )
        self.assertIn("Prior composition diary", prompt)
        self.assertIn("kpi_cards", prompt)
        self.assertIn("different motif", prompt.casefold())

    def test_title_plate_dedicated_prompt(self):
        from tasks.free_design_pipeline import EXECUTOR_SYSTEM, build_executor_slide_prompt

        self.assertIn("FULL-BLEED event pages", EXECUTOR_SYSTEM)
        prompt = build_executor_slide_prompt(
            slide={
                "slide": 1,
                "role": "title",
                "title": "HERO: Equity-Aware Routing",
                "authors": "Ada Lovelace",
                "affiliations": "Analytical Engines Lab",
                "content": {"TITLE": "HERO: Equity-Aware Routing", "SUBTITLE": "Ada Lovelace"},
            },
            spec_lock_md="lock",
            design_spec_md=_MINI_SPEC,
            prior_summary="",
            prior_diary="P02:kpi_cards:stack:3cards",
        )
        self.assertIn("dedicated cover prompt", prompt)
        self.assertIn("TITLE PLATE", prompt)
        self.assertIn("56–72px", prompt)
        self.assertIn("Content-header pattern", prompt)
        self.assertIn("Ada Lovelace", prompt)
        self.assertIn("defer to Title/Closing HARD", prompt)
        self.assertNotIn("Instructional Content guard", prompt)
        self.assertIn("full-bleed event covers", prompt.casefold())
        self.assertNotIn("Prefer a different motif than the last pages", prompt)

    def test_closing_plate_dedicated_prompt(self):
        from tasks.free_design_pipeline import build_executor_slide_prompt

        prompt = build_executor_slide_prompt(
            slide={
                "slide": 12,
                "role": "closing",
                "title": "Thank you",
                "core_message": "Balance routes, not only miles.",
                "content": {"TITLE": "Thank you"},
            },
            spec_lock_md="lock",
            design_spec_md="",
            prior_summary="",
        )
        self.assertIn("dedicated close prompt", prompt)
        self.assertIn("CLOSING PLATE", prompt)
        self.assertIn("48–72px", prompt)
        self.assertIn("Balance routes, not only miles.", prompt)
        self.assertIn("defer to Title/Closing HARD", prompt)
        self.assertNotIn("Instructional Content guard", prompt)

    def test_ensure_asset_hosts_injects_figure_slot(self):
        from tasks.intent_hosts import ensure_asset_hosts

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<text x="80" y="200">Near figure</text></svg>'
        )
        out = ensure_asset_hosts(svg, {"figure_id": "pdf-page-1-picture-1"})
        self.assertIn("data-sunairum-figure-slot", out)
        self.assertIn("pdf-page-1-picture-1", out)









if __name__ == "__main__":
    unittest.main()
