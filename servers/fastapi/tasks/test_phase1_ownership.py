"""Phase 1 ownership / export geometry regressions (P03/P07/P09/P10/P06)."""

from __future__ import annotations

import unittest

from tasks.art_director import format_art_direction_block, author_art_direction
from tasks.design_sot import craft_curriculum_from_tokens
from tasks.formula_visual_intent import sanitize_formula_text
from tasks.intent_hosts import (
    has_canonical_table_slot,
    normalize_table_host,
)
from tasks.svg_export_gate import sanitize_export_geometry, validate_export_svg
from tasks.table_footprint import table_footprint_from_payload
from tasks.table_renderer import _clear_freehand_in_aabb, compose_table_into_slide
from tasks.free_design_pipeline import _slide_dict_from_parsed, _executor_qa_issues


class TestFormulaTexIR(unittest.TestCase):
    def test_slide_dict_keeps_formula_tex(self):
        slide = _slide_dict_from_parsed(
            {
                "slide": 3,
                "title": "Objective",
                "content_blocks": "x",
                "formula": "R = set",
                "formula_tex": r"R=\bigcup_k R_k",
                "formula_terms": r"\(R\)=routes",
            }
        )
        self.assertEqual(slide["formula_tex"], r"R=\bigcup_k R_k")
        self.assertIn("FORMULA_TEX", slide["content"])

    def test_sanitize_strips_tex_delimiters(self):
        self.assertEqual(sanitize_formula_text(r"\(R\)=routes"), "R=routes")
        self.assertNotIn(r"\(", sanitize_formula_text(r"\[x+y\]"))


class TestTableHostContract(unittest.TestCase):
    def test_normalize_polymorphic_slot(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<g data-sunairum-table-slot="true" data-table-id="src-table-002" '
            'x="60" y="184" width="780" height="432"></g>'
            "</svg>"
        )
        out = normalize_table_host(svg, {"table_id": "src-table-002"})
        self.assertTrue(has_canonical_table_slot(out))
        self.assertEqual(out.count("data-sunairum-table-slot"), 1)
        self.assertIn('data-sunairum-table-slot="1"', out)
        self.assertIn("translate(", out)

    def test_missing_slot_detector_accepts_true_after_normalize(self):
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-table-slot="true" transform="translate(100,160)">'
            '<rect width="400" height="200" fill="none"/></g></svg>'
        )
        issues = _executor_qa_issues(svg, {"table_id": "src-table-003"})
        self.assertFalse(
            any("missing_table_slot" in i for i in issues),
            msg=issues,
        )

    def test_clear_freehand_removes_text_in_aabb(self):
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="600" y="300">Random clustered cases</text>'
            '<text x="60" y="80" data-sunairum-page-number="1">Title</text>'
            "</svg>"
        )
        out = _clear_freehand_in_aabb(svg, (588.0, 160.0, 632.0, 440.0))
        self.assertNotIn("Random clustered", out)
        self.assertIn("Title", out)

    def test_compose_drops_any_slot_form(self):
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-table-slot="">'
            '<rect width="10" height="10"/></g></svg>'
        )
        frag = '<g data-sunairum-source-table-id="t1" transform="translate(10,10)"></g>'
        out = compose_table_into_slide(svg, frag, aabb=(10, 10, 100, 100))
        self.assertNotIn("data-sunairum-table-slot", out)
        self.assertIn("data-sunairum-source-table-id", out)


class TestExportGeometryParity(unittest.TestCase):
    def test_sanitize_strips_empty_path_d(self):
        soup = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<path d="M10 10h10"/>'
            '<path d=""/>'
            '<path d=""/>'
            '<path d="M20 20h5"/>'
            "</svg>"
        )
        cleaned = sanitize_export_geometry(soup)
        self.assertNotIn('d=""', cleaned)
        result = validate_export_svg(cleaned)
        self.assertTrue(result.ok, msg=result.errors)
        self.assertFalse(any("freeform" in e for e in result.errors))


class TestFootprintAndCraft(unittest.TestCase):
    def test_footprint_grows_with_cols(self):
        small = table_footprint_from_payload(
            {"headers": ["a", "b"], "rows": [["1", "2"]]}
        )
        big = table_footprint_from_payload(
            {
                "headers": list("abcdef"),
                "rows": [["1"] * 6 for _ in range(8)],
            }
        )
        self.assertGreaterEqual(big["w"], small["w"])
        self.assertGreaterEqual(big["h"], small["h"])

    def test_craft_curriculum_concrete(self):
        lines = craft_curriculum_from_tokens(
            {
                "type_scale": {"title": 34, "body": 16, "caption": 13},
                "layout": {"density": "medium"},
            }
        )
        self.assertTrue(any("Type ladder" in x for x in lines))
        self.assertTrue(any("inset" in x.casefold() or "Inset" in x for x in lines))

    def test_art_direction_fallback_formats(self):
        brief = author_art_direction(
            {"slide": 9, "role": "content", "table_id": "src-table-003"},
            craft_lines=["≥24px gaps"],
            call_text=None,
        )
        block = format_art_direction_block(brief)
        self.assertIn("Art direction", block)
        self.assertIn("table", block.casefold())


if __name__ == "__main__":
    unittest.main()
