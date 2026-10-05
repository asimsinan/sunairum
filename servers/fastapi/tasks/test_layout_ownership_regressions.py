"""Regression tests for durable layout ownership (SS1–SS5 + PPTX fidelity)."""

from __future__ import annotations

import html
import json
import re
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "layout_regressions"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class RegionContractTests(unittest.TestCase):
    def test_reserve_right_column_clamps_left_cards(self):
        from tasks.svg_geometry import detect_right_paint_boxes, reserve_right_column

        svg = _load("ss1_column_vs_diagram.svg")
        boxes = detect_right_paint_boxes(svg)
        self.assertTrue(boxes, "right diagram panel should be detected")
        out = reserve_right_column(svg)
        # Left cards must not extend under the diagram (x≈780).
        for match in re.finditer(r"<rect\b([^>]*)>", out, flags=re.I):
            attrs = match.group(1) or ""
            x_m = re.search(r'\bx="([-\d.]+)"', attrs)
            w_m = re.search(r'\bwidth="([-\d.]+)"', attrs)
            y_m = re.search(r'\by="([-\d.]+)"', attrs)
            if not (x_m and w_m and y_m):
                continue
            x, w, y = float(x_m.group(1)), float(w_m.group(1)), float(y_m.group(1))
            if x > 100 or y < 140 or y > 560:
                continue
            if w < 200:
                continue
            self.assertLessEqual(
                x + w,
                780.0 - 8.0,
                f"left card spills under diagram: x={x} w={w}",
            )
        # Prove clamping happened (fixture starts at width 900).
        card_ws = []
        for match in re.finditer(r"<rect\b([^>]*)>", out, flags=re.I):
            attrs = match.group(1) or ""
            x_m = re.search(r'\bx="([-\d.]+)"', attrs)
            w_m = re.search(r'\bwidth="([-\d.]+)"', attrs)
            y_m = re.search(r'\by="([-\d.]+)"', attrs)
            if not (x_m and w_m and y_m):
                continue
            if float(x_m.group(1)) < 100 and 150 <= float(y_m.group(1)) <= 500:
                card_ws.append(float(w_m.group(1)))
        self.assertTrue(card_ws)
        self.assertTrue(all(w < 900 for w in card_ws), card_ws)



class FormulaOwnerTests(unittest.TestCase):
    def test_sanitize_strips_backticks(self):
        from tasks.formula_visual_intent import sanitize_formula_text
        from tasks.free_design_pipeline import _sanitize_formula_field

        raw = "`Delta = beta * Equity`"
        self.assertNotIn("`", sanitize_formula_text(raw))
        self.assertNotIn("`", _sanitize_formula_field(raw))

    def test_intent_plate_legend_below_band(self):
        from tasks.formula_visual_intent import (
            author_formula_visual_intent,
            render_formula_plate,
        )

        intent = author_formula_visual_intent(
            "`E = mc^2`",
            terms="m = mass; c = light speed",
            gloss="Energy equivalence",
            call_text=None,
        )
        self.assertNotIn("`", intent["formula"])
        frag = render_formula_plate(
            intent,
            aabb=(80, 160, 1120, 400),
            terms="m = mass; c = light speed",
            gloss="Energy equivalence",
        )
        self.assertIn('data-sunairum-formula-host="1"', frag)
        self.assertIn('data-sunairum-formula-plate="1"', frag)
        self.assertNotIn("`", frag)
        rect = re.search(
            r'<rect[^>]*data-sunairum-formula-plate="1"[^/]*?/?>', frag, flags=re.I
        )
        self.assertIsNotNone(rect)
        hm = re.search(r'\bheight="([-\d.]+)"', rect.group(0))  # type: ignore
        ym = re.search(r'\by="([-\d.]+)"', rect.group(0))  # type: ignore
        self.assertIsNotNone(hm)
        self.assertIsNotNone(ym)
        self.assertLess(float(hm.group(1)), 200.0)  # type: ignore
        band_bottom = float(ym.group(1)) + float(hm.group(1))  # type: ignore
        # Legend terms live below the equation band (sibling of replace group).
        self.assertIn('data-sunairum-formula-legend="1"', frag)
        term_m = re.search(
            r'<text[^>]*data-sunairum-formula-term="1"[^>]*\by="([-\d.]+)"', frag
        ) or re.search(
            r'<text[^>]*\by="([-\d.]+)"[^>]*data-sunairum-formula-term="1"', frag
        )
        self.assertIsNotNone(term_m)
        self.assertGreater(float(term_m.group(1)), band_bottom)  # type: ignore
        # Preview math (KaTeX) or text fail-soft must be present.
        self.assertTrue(
            "data-sunairum-formula-math" in frag
            or 'data-sunairum-formula="1"' in frag
        )

    def test_harness_skips_fit_when_intent_host_present(self):
        from tasks.formula_plate import fit_formula_plate

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-formula-host="1">'
            '<text data-sunairum-formula="1">KEEP_ME</text></g></svg>'
        )
        out = fit_formula_plate(
            svg, formula="Delta = beta * Equity", terms="beta=x", gloss=""
        )
        self.assertIn("KEEP_ME", out)
        self.assertEqual(out.count("data-sunairum-formula="), 1)

    def test_fit_formula_strips_backticks_and_soft_band(self):
        from tasks.formula_plate import fit_formula_plate

        svg = _load("ss3_formula_dual_grammar.svg")
        out = fit_formula_plate(
            svg,
            formula="`Delta = beta * Equity + gamma * Norm`",
            terms="beta = market exposure",
            gloss="",
        )
        self.assertNotIn("`", out)
        self.assertIn('data-sunairum-formula-plate="1"', out)
        # Untagged blue soft band should be gone (only tagged plate remains among large soft rects)
        blues = re.findall(r'fill="#DBEAFE"', out, flags=re.I)
        self.assertEqual(blues, [])


class TableGeometryAndPptxTests(unittest.TestCase):
    def _sample(self):
        from tasks.table_analyzer import analyze_table
        from tasks.table_render_spec import build_table_render_spec
        from tasks.table_visual_intent import default_table_intent, validate_table_intent

        table = {
            "table_id": "src-table-042",
            "caption": "Solver cost",
            "headers": [
                {"text": "Method"},
                {"text": "Cost"},
                {"text": "Latency"},
            ],
            "rows": [
                [{"text": "Gurobi"}, {"text": "120"}, {"text": "9"}],
                [{"text": "OR-Tools"}, {"text": "80"}, {"text": "12"}],
                [{"text": "CBC"}, {"text": "95"}, {"text": "15"}],
            ],
        }
        analysis = analyze_table(table)
        intent = validate_table_intent(
            default_table_intent(analysis, "src-table-042"),
            analysis,
            "src-table-042",
        )
        spec = build_table_render_spec(
            analysis, intent, aabb=(80, 180, 1120, 440), theme={"primary": "#0B3B6F"}
        )
        return analysis, intent, spec

    def test_content_sized_canvas_not_full_aabb(self):
        _, _, spec = self._sample()
        self.assertLess(spec["canvas"]["height"], 440.0)
        self.assertGreater(spec["canvas"]["height"], 100.0)

    def test_numeric_columns_center_aligned(self):
        _, _, spec = self._sample()
        aligns = {c["name"]: c["align"] for c in spec["columns"]}
        self.assertEqual(aligns["Method"], "left")
        self.assertEqual(aligns["Cost"], "center")
        self.assertEqual(aligns["Latency"], "center")

    def test_insight_reserved_and_present(self):
        _, _, spec = self._sample()
        self.assertTrue(spec["insight"]["enabled"])
        self.assertIn("OR-Tools", spec["insight"]["text"])
        self.assertIn("Cost", spec["insight"]["text"])

    def test_clear_freehand_guides_before_inject(self):
        from tasks.table_renderer import compose_table_into_slide, render_table_spec_svg

        _, _, spec = self._sample()
        frag = render_table_spec_svg(spec)
        svg = _load("ss4_table_orphan_guides.svg")
        out = compose_table_into_slide(svg, frag, aabb=(80, 180, 1120, 440))
        self.assertNotIn('<line ', out.casefold().replace("<line\n", "<line "))
        # No vertical hairline guides left in the table band
        lines = re.findall(r"<line\b[^>]*>", out, flags=re.I)
        self.assertEqual(lines, [])
        self.assertIn('data-sunairum-source-table-id="src-table-042"', out)

    def test_native_metadata_projects_fill_bold_align(self):
        from tasks.table_renderer import render_spec_to_native_payload, render_table_spec_svg

        _, _, spec = self._sample()
        payload = render_spec_to_native_payload(spec)
        self.assertTrue(payload["columns"])
        for col in payload["columns"]:
            self.assertEqual(col.get("fill"), "#0B3B6F")
            self.assertEqual(col.get("color"), "#FFFFFF")
            self.assertTrue(col.get("bold"))
            self.assertIn(col.get("align"), {"l", "ctr", "r"})
        # Highlight Cost on OR-Tools row
        hi = None
        for row in payload["rows"]:
            if row and row[0].get("text") == "OR-Tools":
                hi = row[1]
                break
        self.assertIsNotNone(hi)
        self.assertTrue(hi.get("bold"))  # type: ignore
        self.assertTrue(hi.get("fill"))  # type: ignore
        self.assertNotEqual(hi.get("fill"), "#FFFFFF")  # type: ignore

        frag = render_table_spec_svg(spec)
        meta = re.search(
            r"<metadata\b[^>]*>(.*?)</metadata>", frag, flags=re.I | re.S
        )
        self.assertIsNotNone(meta)
        data = json.loads(html.unescape(meta.group(1)))  # type: ignore
        self.assertEqual(data["columns"][0]["fill"], "#0B3B6F")
        # Insight must be sibling outside replace group
        self.assertIn('data-sunairum-table-insight="1"', frag)
        replace = re.search(
            r'<g\b[^>]*data-pptx-replace-with="table"[^>]*>([\s\S]*?)</g>',
            frag,
            flags=re.I,
        )
        self.assertIsNotNone(replace)
        self.assertNotIn("OR-Tools has", replace.group(1))  # type: ignore
        self.assertIn("OR-Tools has", frag)

    def test_insight_survives_strip_unfilled(self):
        from tasks.generate_task import strip_unfilled_native_table_carriers
        from tasks.table_renderer import render_table_spec_svg

        _, _, spec = self._sample()
        frag = render_table_spec_svg(spec)
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            f"{frag}</svg>"
        )
        after = strip_unfilled_native_table_carriers(svg)
        self.assertIn('data-pptx-replace-with="table"', after)
        self.assertIn('data-sunairum-table-insight="1"', after)
        self.assertIn("OR-Tools", after)


if __name__ == "__main__":
    unittest.main()
