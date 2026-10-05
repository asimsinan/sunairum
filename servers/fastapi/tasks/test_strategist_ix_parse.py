"""§IX Content Outline field parsing — colon-inside-bold regression."""

from __future__ import annotations

import unittest

from tasks.strategist_agent import parse_section_ix_slides, resolve_parsed_slide_assets


# Minimal §IX mirroring proj_h2jsj P09/P12 (model emits **Field:** not **Field**:).
_H2JSJ_STYLE_SPEC = """
## IX. Content Outline

### P01: Title Plate
- **Title:** HNSW Guided Large Neighborhood Search
- **Core message:** Equity-aware repair
- **Layout:** Title plate
- **Content:** Title only

### P04: Architecture
- **Title:** Architecture and Feature Space
- **Core message:** System overview
- **Layout:** Figure-dominant asymmetric split
- **Content:** Callouts around the architecture figure
- **Figure:** `pdf-page-3-picture-1` (evidence=`ev-page-03-block-028`)
- **Evidence:** `ev-page-03-block-028`

### P09: Solomon Results
- **Title:** On Solomon instances, equity improves while HNSW reduces effort
- **Core message:** HERO lowers workload imbalance
- **Layout:** Table-dominant slide. Place a selectively reformatted version of Table I
- **Content:** Highlight the relevant rows for ALNS and HERO
- **Table:** `src-table-001` (evidence=`ev-page-04-table-001`)
- **Evidence:** `ev-page-04-block-051`, `ev-page-04-table-001`

### P12: Euro-NeurIPS 2022 Asymmetric Instances
- **Title:** On asymmetric instances, efficiency transfers but the quality trade-off widens
- **Core message:** HERO still reduces repair effort
- **Layout:** Table-dominant asymmetric split. Left region: selected Table VI
- **Content:** Report mean cost, CV, Gini, Jain, and time
- **Table:** `src-table-006` (evidence=`ev-page-05-table-006`)
- **Evidence:** `ev-page-05-block-065`, `ev-page-05-table-006`

### P14: Thank You / Questions
- **Title:** Thank you
- **Core message:** Questions
- **Layout:** Closing
- **Content:** Thank you
"""


class TestStrategistIxParse(unittest.TestCase):
    def test_colon_inside_bold_extracts_table_and_figure_ids(self):
        slides = parse_section_ix_slides(_H2JSJ_STYLE_SPEC)
        by_num = {int(s["slide"]): s for s in slides}
        self.assertEqual("src-table-001", by_num[9]["table_id"])
        self.assertEqual("src-table-006", by_num[12]["table_id"])
        self.assertEqual("pdf-page-3-picture-1", by_num[4]["figure_id"])
        self.assertIn("Table-dominant", by_num[9]["layout_intent"])
        self.assertTrue(by_num[9]["title"].startswith("On Solomon"))

    def test_colon_outside_bold_still_works(self):
        md = """
## IX. Content Outline
### P01: Cover
- **Title**: Paper Title
- **Table**: `src-table-002`
### P02: Thanks
- **Title**: Thank you
"""
        slides = parse_section_ix_slides(md)
        by_num = {int(s["slide"]): s for s in slides}
        self.assertEqual("Paper Title", by_num[1]["title"])
        self.assertEqual("src-table-002", by_num[1]["table_id"])

    def test_composition_ir_fields_parsed(self):
        md = """
## IX. Content Outline
### P01: Cover
- **Title:** Paper
- **Audience move:** orient to topic
- **Page rhythm:** anchor
- **Visualization:** hero_bleed
- **Calm region:** left
### P02: Objective
- **Title:** Objective
- **Layout:** formula_hero — band + steps
- **Audience move:** grasp the objective
- **Page rhythm:** dense
- **Visualization:** formula_band
- **Structure:** order
- **Formula:** J(R) = C(R)/C_0 + beta * CV(R)
- **Formula tex:** J(R)=\\frac{C(R)}{C_0}+\\beta CV(R)
- **Content:**
  - Claim one
  - Claim two
### P03: Thanks
- **Title:** Thank you
- **Page rhythm:** breathing
"""
        slides = parse_section_ix_slides(md)
        by_num = {int(s["slide"]): s for s in slides}
        self.assertEqual("anchor", by_num[1]["page_rhythm"])
        self.assertEqual("hero_bleed", by_num[1]["visualization"])
        self.assertEqual("left", by_num[1]["calm_region"])
        self.assertEqual("formula_band", by_num[2]["visualization"])
        self.assertEqual("order", by_num[2]["structure_atom"])
        self.assertIn("beta", by_num[2]["formula"])
        self.assertIn("frac", by_num[2]["formula_tex"])
        self.assertEqual("dense", by_num[2]["page_rhythm"])

    def test_multiline_display_formula_not_truncated_to_opener(self):
        md = r"""
## IX. Content Outline
### P04: Routing Objective
- **Title:** One route-distance vector supports cost and equity
- **Layout:** formula_hero
- **Formula:** \[
J(R)=\frac{C(R)}{C_0}+\beta\,\mathrm{CV}(R)+\gamma\,[1-Jain(R)]
\]
- **Formula terms:** `C(R)=total route distance`
- **Formula gloss:** Equity weights accept more distance when balance improves.
### P05: Thanks
- **Title:** Thank you
"""
        slides = parse_section_ix_slides(md)
        by_num = {int(s["slide"]): s for s in slides}
        formula = by_num[4]["formula"]
        self.assertNotEqual("\\[", formula)
        self.assertIn("J(R)", formula)
        self.assertIn("frac", formula)
        self.assertIn("\\]", formula)

    def test_resolve_from_body_when_field_empty(self):
        slides = [
            {
                "slide": 1,
                "title": "x",
                "body": "- **Table:** `src-table-001` (evidence=`ev-x`)\n",
                "table_id": "",
                "figure_id": "",
                "table_field": "",
                "figure_field": "",
            }
        ]
        out = resolve_parsed_slide_assets(slides, tables=[], figures=[])
        self.assertEqual("src-table-001", out[0]["table_id"])

    def test_user_instruction_numbers_never_hard_block(self):
        from tasks.free_design_pipeline import _is_user_instruction_unsupported_number

        exempt = {"32200", "2022"}
        self.assertTrue(
            _is_user_instruction_unsupported_number(
                "slide-1:unsupported-number:32200", exempt
            )
        )
        self.assertFalse(
            _is_user_instruction_unsupported_number(
                "slide-3:unsupported-number:1.74", exempt
            )
        )
        self.assertFalse(
            _is_user_instruction_unsupported_number(
                "slide-3:unknown-evidence:ev-x", exempt
            )
        )

    def test_intent_bind_prefers_table_dominant_not_figure_slides(self):
        from tasks.free_design_pipeline import _bind_selected_assets

        parsed = [
            {"slide": 1, "role": "title", "title": "Cover", "table_id": "", "figure_id": ""},
            {
                "slide": 2,
                "role": "content",
                "title": "Why",
                "layout_intent": "two cards",
                "table_id": "",
                "figure_id": "",
            },
            {
                "slide": 3,
                "role": "content",
                "title": "Architecture",
                "layout_intent": "Figure-dominant asymmetric split",
                "table_id": "",
                "figure_id": "",
            },
            {
                "slide": 9,
                "role": "content",
                "title": "Solomon Results",
                "layout_intent": "Table-dominant slide. Place Table I",
                "table_id": "",
                "figure_id": "",
            },
            {
                "slide": 12,
                "role": "content",
                "title": "Euro-NeurIPS",
                "layout_intent": "Table-dominant asymmetric split. Table VI",
                "table_id": "",
                "figure_id": "",
            },
            {"slide": 14, "role": "closing", "title": "Thanks", "table_id": "", "figure_id": ""},
        ]
        warnings = _bind_selected_assets(
            parsed,
            selected_figure_ids=["pdf-page-3-picture-1"],
            selected_table_ids=["src-table-001", "src-table-006"],
        )
        by_num = {int(s["slide"]): s for s in parsed}
        self.assertEqual("src-table-001", by_num[9]["table_id"])
        self.assertEqual("src-table-006", by_num[12]["table_id"])
        self.assertEqual("pdf-page-3-picture-1", by_num[3]["figure_id"])
        self.assertFalse(by_num[9].get("figure_id"))
        self.assertFalse(by_num[3].get("table_id"))
        self.assertEqual([], warnings)

    def test_reconcile_rewrites_equity_slide_bound_to_eval_table(self):
        """Solomon equity claims must not keep an HNSW eval-count table."""
        from tasks.free_design_pipeline import _reconcile_slide_table_bindings

        catalog = [
            {
                "table_id": "src-table-001",
                "caption": "TABLE I MEAN RESULTS OVER SOLOMON INSTANCES.",
                "headers": [
                    {"text": "Method"},
                    {"text": "Cost"},
                    {"text": "CV"},
                    {"text": "Gini"},
                    {"text": "Jain"},
                    {"text": "Time (s)"},
                ],
            },
            {
                "table_id": "src-table-002",
                "caption": "TABLE II HNSW EVALUATION REDUCTION ON HOMBERGER CLUSTERED INSTANCES.",
                "headers": [
                    {"text": "n"},
                    {"text": "Brute evals"},
                    {"text": "HNSW evals"},
                    {"text": "Reduction"},
                    {"text": "Cost ratio"},
                ],
            },
            {
                "table_id": "src-table-003",
                "caption": "TABLE III HNSW EVALUATION REDUCTION BY INSTANCE STRUCTURE.",
                "headers": [
                    {"text": "Class"},
                    {"text": "n"},
                    {"text": "Brute"},
                    {"text": "HNSW"},
                    {"text": "Reduction"},
                    {"text": "Cost ratio"},
                ],
            },
            {
                "table_id": "src-table-004",
                "caption": "TABLE IV HERO AND COST ONLY ALNS BY SOLOMON CLASS.",
                "headers": [
                    {"text": "Class"},
                    {"text": "ALNS CV"},
                    {"text": "HERO CV"},
                    {"text": "∆ CV"},
                    {"text": "∆ Cost"},
                ],
            },
        ]
        parsed = [
            {
                "slide": 9,
                "role": "content",
                "title": "On Solomon instances, equity guidance lowers imbalance at a cost",
                "core_message": "HERO reports lower CV and Gini and a higher Jain’s index than cost-only ALNS",
                "content_blocks": "Equity effect: lower CV and Gini, higher Jain. Quality context vs OR-Tools.",
                "table_id": "src-table-003",  # wrong: eval structure table
            },
            {
                "slide": 10,
                "role": "content",
                "title": "Retrieval reduces evaluations across Homberger structures",
                "core_message": "HNSW lowers distance evaluations; reductions span 1.43× to 3.05×",
                "content_blocks": "Brute evals vs HNSW evals; cost ratios near one.",
                "table_id": "src-table-002",
            },
            {
                "slide": 11,
                "role": "content",
                "title": "Equity gains persist across instance structures",
                "core_message": "HERO reduces route-distance CV across Solomon classes",
                "content_blocks": "Class C/R/RC ALNS CV vs HERO CV and cost deltas.",
                "table_id": "src-table-003",
            },
        ]
        warnings = _reconcile_slide_table_bindings(parsed, catalog)
        by_num = {int(s["slide"]): s for s in parsed}
        self.assertEqual("src-table-001", by_num[9]["table_id"], warnings)
        self.assertEqual("src-table-002", by_num[10]["table_id"], warnings)
        self.assertEqual("src-table-004", by_num[11]["table_id"], warnings)
        self.assertTrue(any("rebound" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
