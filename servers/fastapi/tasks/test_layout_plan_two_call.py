"""Two-call layout plan → paint + prompt/QA/table inject contracts."""

from __future__ import annotations

import unittest


class LayoutPlanSchemaTests(unittest.TestCase):
    def test_validate_preserves_host_voids_and_clamps(self):
        from tasks.slide_layout_plan import locked_host_voids, validate_layout_plan

        slide = {
            "table_id": "tbl1",
            "_table_band": {"x": 588, "y": 160, "w": 632, "h": 440},
            "formula": "f(R)=1",
            "_formula_band": {"x": 60, "y": 160, "w": 1160, "h": 240},
        }
        voids = locked_host_voids(slide)
        self.assertGreaterEqual(len(voids), 2)
        plan = validate_layout_plan(
            {
                "job": "show ranking",
                "composition": "table_left_takeaway",
                "regions": [
                    {"id": "left", "role": "body", "x": 40, "y": 180, "w": 500, "h": 300},
                    {
                        "id": "table_host",
                        "role": "host_void",
                        "x": 1,
                        "y": 1,
                        "w": 10,
                        "h": 10,
                    },
                ],
                "rules": [],
            },
            slide=slide,
        )
        hosts = [r for r in plan["regions"] if r["role"] == "host_void"]
        self.assertTrue(any(h["id"] == "table_host" and h["w"] >= 600 for h in hosts))
        self.assertTrue(any(h["id"] == "formula_host" for h in hosts))
        self.assertIn("no freehand in host_void", " ".join(plan["rules"]))

    def test_peer_card_title_y_consensus(self):
        from tasks.slide_layout_plan import validate_layout_plan

        plan = validate_layout_plan(
            {
                "job": "steps",
                "composition": "peer_cards_row",
                "regions": [
                    {
                        "id": "c1",
                        "role": "card",
                        "x": 80,
                        "y": 280,
                        "w": 200,
                        "h": 200,
                        "title_y": 300,
                    },
                    {
                        "id": "c2",
                        "role": "card",
                        "x": 300,
                        "y": 280,
                        "w": 200,
                        "h": 200,
                        "title_y": 320,
                    },
                    {
                        "id": "c3",
                        "role": "card",
                        "x": 520,
                        "y": 280,
                        "w": 200,
                        "h": 200,
                        "title_y": 306,
                    },
                ],
            },
            slide={},
        )
        cards = [r for r in plan["regions"] if r["role"] == "card"]
        ys = {c["title_y"] for c in cards}
        self.assertEqual(len(ys), 1)

    def test_fallback_plan_without_llm(self):
        from tasks.slide_layout_plan import plan_slide_layout

        slide = {"table_id": "t1", "visual_job": "findings"}
        plan = plan_slide_layout(slide=slide, call_text=None)
        self.assertTrue(slide.get("_layout_plan"))
        self.assertTrue(any(r.get("role") == "host_void" for r in plan["regions"]))


class PromptContractTests(unittest.TestCase):
    def test_paint_prompt_includes_locked_plan_and_drops_tree_ban(self):
        from tasks.free_design_pipeline import EXECUTOR_SYSTEM, build_executor_slide_prompt
        from tasks.slide_layout_plan import fallback_layout_plan

        self.assertNotIn("prefer process/cards over freehand trees", EXECUTOR_SYSTEM.casefold())
        slide = {
            "slide": 2,
            "title": "Test",
            "role": "content",
            "content": {"BODY": "A claim"},
            "table_id": "tbl",
            "_table_band": {"x": 588, "y": 160, "w": 632, "h": 440},
        }
        plan = fallback_layout_plan(slide)
        prompt = build_executor_slide_prompt(
            slide=slide,
            spec_lock_md="lock",
            layout_plan=plan,
        )
        self.assertIn("Locked layout plan", prompt)
        self.assertIn("host_void", prompt)
        self.assertIn("JOB:", prompt)
        self.assertIn("LEFT", prompt.upper())

    def test_formula_prompt_has_creative_dos(self):
        from tasks.executor_modes import SOFT_FORMULA_HERO, soft_pattern_brief
        from tasks.free_design_pipeline import build_executor_slide_prompt

        brief = soft_pattern_brief(SOFT_FORMULA_HERO)
        self.assertIn("JOB", brief)
        self.assertIn("term", brief.casefold())
        slide = {
            "slide": 4,
            "title": "Eq",
            "role": "content",
            "formula": "f(R)=1",
            "formula_terms": "R",
            "formula_gloss": "resource set",
            "content": {"BODY": "trade-off"},
            "_formula_band": {"x": 60, "y": 160, "w": 1160, "h": 240},
        }
        prompt = build_executor_slide_prompt(slide=slide, spec_lock_md="lock")
        self.assertIn("term cards", prompt.casefold())
        self.assertIn("EMPTY", prompt.upper() + prompt)


class DeckQaAbsoluteYTests(unittest.TestCase):
    def test_absolute_tspan_y_and_block_overlap(self):
        from tasks.deck_qa import _svg_text_records, _text_overlap_issues

        svg = """
        <svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">
          <text x="100" y="200" font-size="16">
            <tspan x="100" y="200">Line one long enough</tspan>
            <tspan x="100" y="210">Line two crushed</tspan>
          </text>
          <text x="100" y="205" font-size="16">Overlapping peer text here</text>
        </svg>
        """
        records = _svg_text_records(svg)
        self.assertGreaterEqual(len(records), 2)
        # Absolute y on second tspan must not be ignored (block taller than one line).
        tall = max(r["bounds"][3] - r["bounds"][1] for r in records)
        self.assertGreater(tall, 16.0)
        issues = _text_overlap_issues(1, records)
        self.assertGreaterEqual(len(issues), 1)


class TableInjectClearTests(unittest.TestCase):
    def test_clear_chip_and_insight_in_band(self):
        from tasks.table_renderer import _clear_freehand_in_aabb

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="588" y="160" width="632" height="440" fill="#fff"/>'
            '<rect x="600" y="400" width="80" height="32" fill="#1A365D"/>'
            '<text x="610" y="420" font-size="14">RC</text>'
            '<text x="40" y="300" font-size="16">Left takeaway stays</text>'
            "</svg>"
        )
        out = _clear_freehand_in_aabb(svg, (588, 160, 632, 440))
        self.assertNotIn(">RC<", out)
        self.assertNotIn('fill="#1A365D"', out)
        self.assertIn("Left takeaway stays", out)

    def test_detect_table_boxes_includes_insight(self):
        from tasks.svg_geometry import detect_table_boxes

        svg = (
            '<svg><g data-sunairum-source-table-id="1" '
            'transform="translate(588,160)">'
            '<rect width="632" height="280"/>'
            "</g>"
            '<g data-sunairum-table-insight="1" transform="translate(588,450)">'
            '<text x="12" y="0">insight</text></g></svg>'
        )
        boxes = detect_table_boxes(svg)
        self.assertTrue(boxes)
        _, y, _, h = boxes[0]
        self.assertGreaterEqual(y + h, 450.0)


class FormulaHostClearTests(unittest.TestCase):
    def test_clear_freehand_in_formula_host(self):
        from tasks.svg_geometry import clear_freehand_in_formula_host

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-formula-host="1" transform="translate(60,160)">'
            '<rect width="1160" height="240" data-sunairum-formula-plate="1"/>'
            '<text data-sunairum-formula-term="1" x="26" y="200">J(R)=index</text>'
            "</g>"
            '<text x="80" y="200" font-size="15">Zero equity weights recover</text>'
            '<text x="80" y="500" font-size="16">Outside stays</text>'
            "</svg>"
        )
        out = clear_freehand_in_formula_host(svg)
        self.assertNotIn("Zero equity", out)
        self.assertIn("Outside stays", out)
        self.assertIn("formula-term", out)


class SpatialRetryHintTests(unittest.TestCase):
    def test_mechanical_issues_do_not_replan(self):
        from tasks.slide_layout_plan import spatial_issues_suggest_replan

        # Overlaps / anatomy / ink are mechanical — no extra Plan+Paint.
        self.assertFalse(spatial_issues_suggest_replan(["text_overlaps:3: collide"]))
        self.assertFalse(spatial_issues_suggest_replan(["font_drift:Georgia"]))
        self.assertFalse(
            spatial_issues_suggest_replan(
                ["card_title_inverted:HERO: title below body — replan card anatomy"]
            )
        )
        self.assertFalse(
            spatial_issues_suggest_replan(["ink_through_text:1: remove axis/path"])
        )
        self.assertFalse(
            spatial_issues_suggest_replan(["takeaway_ellipsis: wrap/grow takeaway band"])
        )

    def test_replan_only_on_host_or_export_failures(self):
        from tasks.slide_layout_plan import spatial_issues_suggest_replan

        self.assertTrue(spatial_issues_suggest_replan(["missing_svg: empty"]))
        self.assertTrue(
            spatial_issues_suggest_replan(["export_gate: nested text debris"])
        )
        self.assertTrue(
            spatial_issues_suggest_replan(["missing_table_slot: host required"])
        )


class CardAnatomyQaTests(unittest.TestCase):
    def test_flags_inverted_peer_title(self):
        from tasks.free_design_pipeline import _executor_qa_issues

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect x="60" y="180" width="340" height="280" rx="12" fill="#EBF4FB"/>'
            '<rect x="440" y="180" width="340" height="280" rx="12" fill="#EBF4FB"/>'
            '<text x="80" y="210" font-size="20" font-weight="700">Fast evaluation</text>'
            '<text x="80" y="360" font-size="14">Body stays low in card one.</text>'
            # Peer title drifted near body baseline (inverted vs peers / body).
            '<text x="460" y="360" font-size="14">Body copy for card two sits here.</text>'
            '<text x="460" y="380" font-size="20" font-weight="700">Approximate retrieval</text>'
            "</svg>"
        )
        issues = _executor_qa_issues(svg, {"page_role": "content"})
        self.assertTrue(
            any("card_title_inverted" in i for i in issues),
            msg=issues,
        )


if __name__ == "__main__":
    unittest.main()
