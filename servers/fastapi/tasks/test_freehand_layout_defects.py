"""Regression tests for the freehand layout defect pack."""

from __future__ import annotations

import re
import unittest


class PageChromePlacementTests(unittest.TestCase):
    def test_page_number_lifts_above_takeaway_band(self):
        from tasks.generate_task import sanitize_presentation_chrome

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="60" y="620" width="1160" height="80" rx="12" fill="#1A365D"/>'
            '<text x="90" y="660" font-size="16" fill="#fff">'
            "Retrieval narrows the search</text>"
            "</svg>"
        )
        out = sanitize_presentation_chrome(svg, slide_number=3, total_slides=14)
        match = re.search(
            r'data-sunairum-page-number="1"[^>]*\bx="([-\d.]+)"[^>]*\by="([-\d.]+)"',
            out,
        )
        self.assertIsNotNone(match)
        x, y = float(match.group(1)), float(match.group(2))
        self.assertEqual(x, 1220.0)
        self.assertLess(y, 620.0)
        self.assertIn("3/14", out)


class CardTextFitTests(unittest.TestCase):
    def test_per_card_accent_nudges_title_and_body(self):
        from tasks.svg_geometry import ACCENT_CLEARANCE, clear_per_card_accent_rails

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="200" y="200" width="800" height="120" rx="12" fill="#EAF2FF"/>'
            '<rect x="200" y="200" width="8" height="120" fill="#1A365D"/>'
            '<text x="204" y="230" font-size="20" font-weight="bold">'
            "Separation of roles</text>"
            '<text x="210" y="260" font-size="14">'
            "The index controls which positions are examined; "
            "the objective controls which examined position is selected.</text>"
            "</svg>"
        )
        out = clear_per_card_accent_rails(svg)
        xs = [float(v) for v in re.findall(r'<text[^>]*\bx="([-\d.]+)"', out)]
        self.assertTrue(xs)
        self.assertTrue(all(x >= 200 + 8 + ACCENT_CLEARANCE - 0.5 for x in xs))

    def test_title_body_pitch_inside_card(self):
        from tasks.svg_geometry import enforce_card_title_body_pitch

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="80" y="180" width="320" height="160" rx="10" fill="#EAF2FF"/>'
            '<text x="100" y="210" font-size="18" font-weight="bold">BASE CONTEXT</text>'
            '<text x="100" y="220" font-size="13">'
            "Coordinates, time slack, remaining capacity,</text>"
            "</svg>"
        )
        out = enforce_card_title_body_pitch(svg)
        ys = [float(v) for v in re.findall(r'<text[^>]*\by="([-\d.]+)"', out)]
        self.assertGreaterEqual(ys[1] - ys[0], 18.0 * 1.35 - 0.5)

    def test_rewrap_uses_widest_containing_card(self):
        from tasks.svg_reflow import rewrap_overflowing_text

        body = (
            "The index controls which positions are examined; "
            "the objective controls which examined position is selected."
        )
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="100" y="200" width="900" height="140" rx="12" fill="#EAF2FF"/>'
            # Nested narrow panel that must not force the wrap width.
            '<rect x="120" y="220" width="200" height="80" fill="#fff"/>'
            f'<text x="140" y="250" font-size="15">{body}</text>'
            "</svg>"
        )
        out = rewrap_overflowing_text(svg)
        # Wide outer card should keep this as a single tspan/line.
        self.assertLessEqual(out.count("<tspan"), 1)
        self.assertIn("objective controls", out)


class BulletAndNestedRowTests(unittest.TestCase):
    def test_pack_icon_clears_bullet_overlap(self):
        from tasks.svg_geometry import ICON_LABEL_GAP, pack_icon_label_pairs

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<circle cx="120" cy="300" r="6" fill="#60A5FA"/>'
            '<text x="118" y="304" font-size="16">Clarke-Wright start</text>'
            "</svg>"
        )
        out = pack_icon_label_pairs(svg)
        x = float(re.search(r'<text[^>]*\bx="([-\d.]+)"', out).group(1))
        self.assertGreaterEqual(x, 120 + 6 + ICON_LABEL_GAP - 0.5)

    def test_clamp_nested_row_inside_parent(self):
        from tasks.table_layout import clamp_shapes_inside_cards

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="80" y="160" width="400" height="280" rx="12" fill="#F1F5F9"/>'
            '<rect x="100" y="220" width="420" height="48" rx="8" fill="#FFFFFF"/>'
            "</svg>"
        )
        out = clamp_shapes_inside_cards(svg)
        row = re.search(
            r'<rect[^>]*\bx="100"[^>]*\bwidth="([-\d.]+)"',
            out,
        )
        self.assertIsNotNone(row)
        self.assertLessEqual(float(row.group(1)), 400 - 10 - (100 - 80))


class FormulaAndTableTests(unittest.TestCase):
    def test_strip_raw_tex_delimiters(self):
        from tasks.svg_geometry import strip_raw_tex_delimiters_in_svg

        svg = (
            '<svg viewBox="0 0 1280 720">'
            r'<text x="100" y="200" font-size="16">'
            r"\(f(R) = \alpha C(R)\)</text>"
            "</svg>"
        )
        out = strip_raw_tex_delimiters_in_svg(svg)
        self.assertNotIn(r"\(", out)
        self.assertNotIn(r"\)", out)
        self.assertIn("f(R)", out)

    def test_formula_plate_pushed_below_prior_text(self):
        from tasks.svg_geometry import clear_formula_plate_overlaps

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="80" y="300" font-size="16">'
            "One normalized score lets repair balance route distance against workload equity"
            "</text>"
            '<g data-sunairum-formula-host="1" transform="translate(80,285)">'
            '<rect x="0" y="0" width="600" height="90" rx="12" fill="#EAF2FF" '
            'data-sunairum-formula-plate="1"/>'
            "</g>"
            "</svg>"
        )
        out = clear_formula_plate_overlaps(svg)
        tm = re.search(
            r'transform="translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)',
            out,
        )
        self.assertIsNotNone(tm)
        self.assertGreater(float(tm.group(2)), 285.0)

    def test_table_insight_stacks_note_and_wraps(self):
        from tasks.table_renderer import render_table_spec_svg

        long_insight = (
            "OR-Tools has lowest Cost (940.1); ALNS+HNSW (cost-only) has "
            "lowest Time (s) (4.25); ALNS (equity) has lowest CV of (0.1226)"
        )
        spec = {
            "table_id": "t1",
            "canvas": {"x": 100, "y": 160, "width": 420, "height": 260},
            "columns": [
                {"name": "A", "x": 100, "width": 200, "align": "left"},
                {"name": "B", "x": 300, "width": 200, "align": "left"},
            ],
            "rows": {"height": 40, "data": [["1", "2"], ["3", "4"]]},
            "header_height": 36,
            "insight": {"enabled": True, "text": long_insight},
            "view_note": "view note",
            "theme": {"font": "Arial", "muted": "#64748B", "ink": "#0F172A"},
        }
        frag = render_table_spec_svg(spec)
        self.assertIn('data-sunairum-table-insight="1"', frag)
        # Note must not share y="0" end-anchor with insight.
        self.assertNotRegex(frag, r'text-anchor="end"')
        self.assertIn("<tspan", frag)
        self.assertIn("view note", frag)

    def test_reserve_table_column_clamps_left_card(self):
        from tasks.svg_geometry import reserve_table_column

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="60" y="200" width="700" height="200" rx="12" fill="#EAF2FF"/>'
            '<text x="80" y="240" font-size="16">Reduction first; monotonicity is not guaranteed</text>'
            '<g data-pptx-replace-with="table" transform="translate(500,180)">'
            '<rect width="620" height="400" fill="#DBEAFE"/>'
            "</g>"
            "</svg>"
        )
        out = reserve_table_column(svg)
        width = float(
            re.search(r'<rect[^>]*\bx="60"[^>]*\bwidth="([-\d.]+)"', out).group(1)
        )
        self.assertLess(width, 700.0)
        self.assertLessEqual(60 + width, 500.0)


if __name__ == "__main__":
    unittest.main()
