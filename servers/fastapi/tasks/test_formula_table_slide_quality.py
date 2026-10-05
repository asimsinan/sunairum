"""Tests for formula + table slide quality pack."""

from __future__ import annotations

import re
import unittest


class FormulaSanitizeTests(unittest.TestCase):
    def test_sanitize_formula_field_strips_tex_delimiters(self):
        from tasks.free_design_pipeline import _sanitize_formula_field

        out = _sanitize_formula_field(r"\( J(R) = \alpha C(R) \)")
        self.assertNotIn(r"\(", out)
        self.assertNotIn(r"\)", out)
        self.assertIn("J(R)", out)

    def test_strip_tex_in_tspans(self):
        from tasks.svg_geometry import strip_raw_tex_delimiters_in_svg

        svg = (
            '<svg viewBox="0 0 1280 720">'
            r'<text x="80" y="200" font-size="16">'
            r'<tspan x="80" dy="0">\(f(R)=\alpha\)</tspan>'
            "</text></svg>"
        )
        out = strip_raw_tex_delimiters_in_svg(svg)
        self.assertNotIn(r"\(", out)
        self.assertIn("f(R)", out)

    def test_remove_freehand_equation_when_host_present(self):
        from tasks.svg_geometry import remove_freehand_equation_text

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-formula-host="1" transform="translate(60,160)">'
            '<rect width="1000" height="200" data-sunairum-formula-plate="1"/>'
            "</g>"
            r'<text x="100" y="300" font-size="18">\(J(R)=C(R)+\beta\)</text>'
            "</svg>"
        )
        out = remove_freehand_equation_text(svg)
        self.assertNotIn("J(R)=C(R)", out)
        self.assertIn("data-sunairum-formula-host", out)


class FormulaPlateLegendTests(unittest.TestCase):
    def test_legend_terms_stay_inside_host_height(self):
        from tasks.formula_visual_intent import render_formula_plate

        frag = render_formula_plate(
            {
                "formula": "J(R) = C(R) + beta",
                "mode": "term_callouts",
                "style": "academic",
            },
            aabb=(60.0, 160.0, 1160.0, 240.0),
            terms="C(R) = total route distance; CV = coefficient; beta,gamma = weights",
            theme={"ink": "#1A365D", "accent": "#3182CE", "surface": "#EBF4FF"},
            images_dir="/tmp",
            formula_id="t_formula",
        )
        self.assertIn("data-sunairum-formula-legend-plate", frag)
        ys = [
            float(m)
            for m in re.findall(
                r'data-sunairum-formula-term="1"[^>]*\by="([-\d.]+)"', frag
            )
        ]
        self.assertTrue(ys)
        self.assertTrue(all(y <= 240.0 - 4.0 for y in ys))

    def test_legend_formats_tex_greek_and_subscripts(self):
        from tasks.formula_visual_intent import (
            format_legend_symbol_svg,
            render_formula_plate,
        )
        from tasks.unicode_math import sanitize_svg_math, svg_has_unsafe_math

        self.assertIn("μ", format_legend_symbol_svg(r"\mu"))
        self.assertNotIn(r"\mu", format_legend_symbol_svg(r"\mu"))
        legend = format_legend_symbol_svg("d_j")
        self.assertNotIn("baseline-shift", legend)
        self.assertIn('dy="4"', legend)
        self.assertIn(">j</tspan>", format_legend_symbol_svg("d_{j}"))

        frag = render_formula_plate(
            {
                "formula": r"CV(R) = sigma / mu",
                "mode": "term_callouts",
                "style": "academic",
            },
            aabb=(60.0, 120.0, 1160.0, 360.0),
            terms=(
                r"d_j = distance of route j; "
                r"\mu = mean nonempty-route distance; "
                r"\sigma = standard deviation of route distances"
            ),
            gloss="The same route-distance vector supports both equity metrics.",
            theme={"ink": "#1A365D", "accent": "#3182CE", "surface": "#EBF4FF"},
            images_dir="/tmp",
            formula_id="t_legend_tex",
        )
        self.assertIn("μ", frag)
        self.assertIn("σ", frag)
        self.assertNotIn(r"\mu", frag)
        self.assertNotIn(r"\sigma", frag)
        self.assertNotIn("baseline-shift", frag)
        self.assertIn('dy="4"', frag)
        self.assertIn("distance of route j", frag)
        wrapped = f'<svg viewBox="0 0 1280 720">{frag}</svg>'
        cleaned = sanitize_svg_math(wrapped)
        self.assertIn("μ", cleaned)
        self.assertIn("σ", cleaned)
        self.assertNotIn("baseline-shift", cleaned)
        self.assertFalse(svg_has_unsafe_math(cleaned))

        legacy = (
            '<svg viewBox="0 0 1280 720">'
            '<text>d<tspan baseline-shift="sub" font-size="70%">j</tspan> = x</text>'
            "</svg>"
        )
        legacy_out = sanitize_svg_math(legacy)
        self.assertNotIn("baseline-shift", legacy_out)
        self.assertIn('dy="4"', legacy_out)


class RuleClearanceTests(unittest.TestCase):
    def test_thick_horizontal_bar_through_subtitle_deleted(self):
        from tasks.svg_reflow import clear_lines_through_text

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="80" y="120" font-size="16">'
            "One route-distance vector connects route cost with workload balance."
            "</text>"
            '<rect x="60" y="112" width="1100" height="6" fill="#3182CE"/>'
            "</svg>"
        )
        out = clear_lines_through_text(svg)
        self.assertNotIn('height="6"', out)
        self.assertIn("One route-distance", out)


class TableIntentBiasTests(unittest.TestCase):
    def test_large_grid_defaults_to_top_k(self):
        from tasks.table_visual_intent import default_table_intent

        analysis = {
            "row_count": 8,
            "columns": ["Method", "Cost", "Time", "CV", "Gini", "Jain"],
            "numeric_columns": ["Cost", "Time", "CV", "Gini", "Jain"],
            "column_stats": [
                {"name": "Cost", "dtype": "number"},
                {"name": "Time", "dtype": "number"},
            ],
        }
        intent = default_table_intent(analysis, "t1")
        self.assertEqual(intent["strategy"]["mode"], "top_k_table")
        self.assertLessEqual(intent["content"]["top_k"], 5)
        self.assertFalse(intent["content"]["show_all_rows"])

    def test_validate_forces_top_k_for_large_full_table(self):
        from tasks.table_visual_intent import validate_table_intent

        analysis = {
            "row_count": 8,
            "columns": ["A", "B", "C", "D", "E", "F"],
            "numeric_columns": ["B"],
            "column_stats": [{"name": "B", "dtype": "number"}],
        }
        out = validate_table_intent(
            {
                "strategy": {"mode": "full_table", "style": "academic"},
                "content": {"show_all_rows": True},
            },
            analysis,
            "t1",
        )
        self.assertEqual(out["strategy"]["mode"], "top_k_table")


class TakeawayPitchTests(unittest.TestCase):
    def test_body_line_pitch_inside_card(self):
        from tasks.svg_geometry import enforce_body_line_pitch

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="60" y="180" width="400" height="280" rx="12" fill="#EAF2FF"/>'
            '<text x="80" y="260" font-size="14">The largest reduction is 3.05x at n=200.</text>'
            '<text x="80" y="270" font-size="14">'
            "At n=1000, evaluations fall from 1.00B</text>"
            "</svg>"
        )
        out = enforce_body_line_pitch(svg)
        ys = [float(v) for v in re.findall(r'<text[^>]*\by="([-\d.]+)"', out)]
        self.assertGreaterEqual(ys[1] - ys[0], 14.0 * 1.35 - 0.5)


class TableHighlightClampTests(unittest.TestCase):
    def test_highlight_stays_inside_grid_width(self):
        from tasks.table_renderer import render_table_spec_svg

        spec = {
            "table_id": "t1",
            "canvas": {"x": 500, "y": 160, "width": 400, "height": 260},
            "columns": [
                {"name": "n", "x": 500, "width": 80, "align": "left"},
                {"name": "Cost ratio", "x": 860, "width": 120, "align": "center"},
            ],
            "rows": {"height": 40, "data": [["200", "0.96"], ["400", "0.97"]]},
            "header_height": 36,
            "cells": [{"row": 0, "col": 1, "style": "highlight"}],
            "insight": {"enabled": False},
            "theme": {"font": "Arial", "accent": "#3182CE"},
        }
        frag = render_table_spec_svg(spec)
        found = False
        for m in re.finditer(r"<rect\b([^>]*)/?>", frag, flags=re.I):
            attrs = m.group(1) or ""
            if 'data-sunairum-table-highlight="1"' not in attrs:
                continue
            found = True
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x + w, 400.0 + 0.5)
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
