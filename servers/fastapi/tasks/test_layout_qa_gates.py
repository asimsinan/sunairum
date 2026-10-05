"""Regression tests: reserved table bands, layout gates, notes duration, math glyphs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class ReservedTableBandTests(unittest.TestCase):
    def test_fallback_avoids_full_bleed_when_figure_present(self):
        from tasks.generate_task import materialize_source_table_svg
        from tasks.table_layout import reserved_table_band

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="#fff"/>'
            '<image href="../images/fig.png" x="700" y="160" width="480" height="360" '
            'data-sunairum-figure-id="fig-1"/>'
            '<rect x="80" y="200" width="280" height="160" fill="#eee"/>'
            '<rect x="80" y="380" width="280" height="160" fill="#eee"/>'
            '<rect x="380" y="200" width="280" height="160" fill="#eee"/>'
            "</svg>"
        )
        band = reserved_table_band(svg)
        # Either a compact non-overlapping band, or skip — never full-bleed.
        if band is not None:
            self.assertLess(band["width"] * band["height"], 1000 * 400)
            self.assertLess(band["width"], 1000)

        out = materialize_source_table_svg(
            svg,
            {
                "source_table_id": "src-table-002",
                "columns": ["A", "B"],
                "rows": [["1", "2"]],
            },
        )
        # Must not use the old full-band 1152×480 geometry.
        self.assertNotIn('"width": 1152', out)
        self.assertNotIn('"width":1152', out)
        self.assertNotIn('"height": 480', out)
        if band is not None:
            self.assertIn('data-sunairum-source-table-id="src-table-002"', out)
        else:
            self.assertNotIn("src-table-002", out)

    def test_table_covers_content_fires(self):
        from tasks.table_layout import table_covers_content_issues

        payload = json.dumps(
            {"x": 64, "y": 190, "width": 1152, "height": 480, "columns": [], "rows": []}
        )
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<image href="f.png" x="700" y="160" width="480" height="360"/>'
            f'<g data-pptx-replace-with="table"><metadata>{payload}</metadata></g>'
            "</svg>"
        )
        issues = table_covers_content_issues(svg, slide=2)
        self.assertTrue(any(i["category"] == "table-covers-content" for i in issues))

    def test_raise_figures_above_tables(self):
        from tasks.table_layout import raise_figures_above_tables

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<image href="f.png" x="10" y="10" width="100" height="100" '
            'data-sunairum-figure-id="fig-1"/>'
            '<g data-pptx-replace-with="table"><metadata>{}</metadata></g>'
            "</svg>"
        )
        out = raise_figures_above_tables(svg)
        table_pos = out.find('data-pptx-replace-with="table"')
        fig_pos = out.find('data-sunairum-figure-id="fig-1"')
        self.assertGreater(fig_pos, table_pos)


class TitleDedupeTests(unittest.TestCase):
    def test_removes_stacked_duplicate_titles(self):
        from tasks.free_design_pipeline import dedupe_stacked_title_texts

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="80" y="120" font-size="34">Search for Equitable Vehicle Routing</text>'
            '<text x="80" y="200" font-size="60">Search for Equitable Vehicle Routing</text>'
            "</svg>"
        )
        out = dedupe_stacked_title_texts(svg)
        self.assertEqual(1, out.count("Search for Equitable Vehicle Routing"))
        self.assertIn('font-size="60"', out)

    def test_drops_contained_competing_title_headline(self):
        from tasks.free_design_pipeline import (
            clamp_title_headline_to_canvas,
            dedupe_stacked_title_texts,
        )

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="638.7" y="176" font-size="34" text-anchor="middle">'
            "HNSW Guided Large Neighborhood Search for Equitable Vehicle Routing"
            "</text>"
            '<text x="640" y="320" font-size="60" text-anchor="middle">'
            "Search for Equitable Vehicle Routing"
            "</text>"
            "</svg>"
        )
        out = dedupe_stacked_title_texts(
            svg, preferred_title="Search for Equitable Vehicle Routing"
        )
        self.assertEqual(1, out.count("Equitable Vehicle Routing"))
        self.assertIn('font-size="60"', out)
        self.assertNotIn("HNSW Guided", out)
        clamped = clamp_title_headline_to_canvas(out)
        self.assertIn("Search for Equitable", clamped)

    def test_fit_title_plate_keeps_display_title_off_accent_bar(self):
        from tasks.free_design_pipeline import fit_title_plate_headline
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="78" y="112" width="8" height="178" rx="4" fill="#1E3A8A"/>'
            '<line x1="112" y1="360" x2="708" y2="360" stroke="#1E3A8A" stroke-width="3"/>'
            '<text x="112" y="280" font-size="52" font-weight="bold">'
            "Neighborhood Search for</text>"
            '<text x="112" y="344" font-size="52" font-weight="bold">'
            "Equitable Vehicle Routing</text>"
            "</svg>"
        )
        full = "HNSW Guided Large Neighborhood Search for Equitable Vehicle Routing"
        out = fit_title_plate_headline(svg, full)
        # Must NOT yank an intentional display wrap onto x=60 through the bar.
        self.assertNotIn('x="60"', out)
        self.assertIn("Neighborhood Search for", out)
        self.assertIn("Equitable Vehicle Routing", out)
        rule_y = float(re.search(r'<line[^>]*\by1="([\d.]+)"', out).group(1))
        self.assertGreaterEqual(rule_y, 344 + 28)

    def test_fit_title_plate_restores_midword_clip_only(self):
        from tasks.free_design_pipeline import fit_title_plate_headline

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="112" y="260" font-size="48" font-weight="bold">'
            "Neighborhood Search for Equitable Vehicle Routi</text>"
            "</svg>"
        )
        full = "Neighborhood Search for Equitable Vehicle Routing"
        out = fit_title_plate_headline(svg, full)
        self.assertIn("Routing", out)
        self.assertNotIn("Routi</text>", out)

    def test_uniquify_duplicate_figure_ids(self):
        from tasks.free_design_pipeline import _uniquify_asset_bindings

        parsed = [
            {
                "slide": 3,
                "role": "content",
                "title": "From cost-only repair to HERO",
                "figure_id": "pdf-page-3-picture-1",
                "layout_intent": "figure-dominant diagram",
            },
            {
                "slide": 5,
                "role": "content",
                "title": "HERO separates retrieval",
                "figure_id": "pdf-page-3-picture-1",
                "layout_intent": "two column copy",
            },
        ]
        warnings = _uniquify_asset_bindings(parsed)
        ids = [str(s.get("figure_id") or "") for s in parsed]
        self.assertEqual(1, sum(1 for i in ids if i == "pdf-page-3-picture-1"))
        self.assertTrue(any("cleared duplicate" in w for w in warnings))

    def test_raise_text_above_shapes_keeps_page_last(self):
        from tasks.table_layout import raise_text_above_shapes

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="80" y="200" font-size="18">WORKLOAD SPREAD</text>'
            '<rect x="100" y="180" width="40" height="120" fill="#f00"/>'
            '<text data-sunairum-page-number="1" x="1220" y="698">01 / 14</text>'
            "</svg>"
        )
        out = raise_text_above_shapes(svg)
        label_at = out.find("WORKLOAD SPREAD")
        rect_at = out.find("<rect")
        page_at = out.find('data-sunairum-page-number="1"')
        self.assertGreater(label_at, rect_at)
        self.assertGreater(page_at, label_at)

    def test_clamp_lifts_text_off_card_bottom(self):
        from tasks.table_layout import clamp_freehand_text_to_canvas
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="90" y="536" width="270" height="54" rx="12" fill="#fff" stroke="#93C5FD"/>'
            '<text x="150" y="588" font-size="14" fill="#64748B">context + equity signals</text>'
            "</svg>"
        )
        out = clamp_freehand_text_to_canvas(svg)
        y = float(re.search(r'<text[^>]*\by="([-\d.]+)"', out).group(1))
        # Card bottom is 590; with pad+descent baseline must sit clearly above the stroke.
        self.assertLessEqual(y, 590 - 12 - 3)
        self.assertIn("context + equity signals", out)

    def test_expand_cramped_cards_for_bold_labels(self):
        from tasks.table_layout import (
            clamp_freehand_text_to_canvas,
            expand_cards_for_overflowing_text,
        )
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="92" y="250" width="100" height="145" rx="8" fill="#FFFFFF" stroke="#CBD5E1"/>'
            '<rect x="220" y="250" width="300" height="145" rx="8" fill="#EAF2FF"/>'
            '<circle cx="116" cy="278" r="12" fill="#F59E0B"/>'
            '<text x="140" y="279" font-size="14" font-weight="bold" fill="#0F172A">Equity</text>'
            '<text x="140" y="297" font-size="14" font-weight="bold" fill="#0F172A">retained</text>'
            "</svg>"
        )
        out = expand_cards_for_overflowing_text(svg)
        out = clamp_freehand_text_to_canvas(out)
        card_w = float(
            re.search(
                r'<rect[^>]*\bx="92"[^>]*\bwidth="([\d.]+)"',
                out,
            ).group(1)
        )
        self.assertGreater(card_w, 100)
        self.assertLessEqual(card_w, 220 - 92 - 8)
        attrs = re.search(r"<text\b([^>]*)>retained</text>", out).group(1)
        x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
        fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))
        self.assertLessEqual(x + len("retained") * fs * 0.58, 92 + card_w - 10)
        self.assertGreaterEqual(fs, 12)

    def test_table_layout_imports_on_py311_safe_fstrings(self):
        # Regression: nested quotes in f-strings crash Celery on Python 3.11.
        import tasks.table_layout as tl

        self.assertTrue(callable(tl.fit_freehand_table_columns))
        self.assertTrue(callable(tl.nudge_annotation_off_headlines))

    def test_clamp_shrinks_formula_inside_card(self):
        from tasks.table_layout import clamp_freehand_text_to_canvas
        import re

        formula = "J(R) = D_norm + beta * CV + gamma * Gini"
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="400" y="240" width="480" height="160" rx="12" fill="#EAF2FF"/>'
            f'<text x="420" y="320" font-size="28" font-weight="700" text-anchor="middle">'
            f"{formula}</text>"
            "</svg>"
        )
        # Center the formula on the card midline so clamp recenters after shrink.
        svg = svg.replace('x="420"', 'x="640"')
        out = clamp_freehand_text_to_canvas(svg)
        attrs = re.search(rf"<text\b([^>]*)>{re.escape(formula)}</text>", out).group(1)
        fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))
        x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
        width = len(formula) * fs * 0.58
        self.assertLess(fs, 28)
        self.assertGreaterEqual(x - width / 2, 400 + 8)
        self.assertLessEqual(x + width / 2, 400 + 480 - 8)

    def test_clamp_wraps_monospace_formula_inside_card(self):
        from tasks.table_layout import clamp_freehand_text_to_canvas
        import re

        formula = (
            "Delta J = Delta distance + beta * Delta equity + gamma * Delta balance"
        )
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="70" y="151" width="705" height="211" rx="14" fill="#F8FAFC"/>'
            '<text x="98" y="253" font-family="Consolas, monospace" '
            f'font-size="30" font-weight="700">{formula}</text>'
            "</svg>"
        )
        out = clamp_freehand_text_to_canvas(svg)
        lines = re.findall(
            r'<text\b[^>]*font-family="Consolas[^"]*"[^>]*>([^<]+)</text>',
            out,
        )
        self.assertGreaterEqual(len(lines), 2, out)
        self.assertNotIn(formula, out)
        for line in lines:
            attrs = re.search(
                rf'<text\b([^>]*)>{re.escape(line)}</text>',
                out,
            ).group(1)
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
            fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))
            right = x + len(line) * fs * 0.72
            self.assertLessEqual(right, 70 + 705 - 10, line)

    def test_nudge_annotation_off_headline(self):
        from tasks.table_layout import nudge_annotation_off_headlines
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="120" y="220" font-size="28" font-weight="700">Full candidate scan</text>'
            '<text x="200" y="214" font-size="13" fill="#F59E0B">removed customer</text>'
            "</svg>"
        )
        out = nudge_annotation_off_headlines(svg)
        y = float(re.search(r"<text\b[^>]*\by=\"([-\d.]+)\"[^>]*>removed customer", out).group(1))
        self.assertNotAlmostEqual(y, 214.0, places=0)

    def test_nudge_moves_pill_with_annotation(self):
        from tasks.table_layout import nudge_annotation_off_headlines
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="120" y="220" font-size="28" font-weight="700">Approximate shortlist</text>'
            '<rect x="150" y="198" width="110" height="24" rx="12" fill="#DBEAFE"/>'
            '<text x="165" y="214" font-size="12" fill="#1D4ED8">query vector</text>'
            "</svg>"
        )
        out = nudge_annotation_off_headlines(svg)
        pill_y = float(re.search(r'<rect[^>]*\by="([-\d.]+)"', out).group(1))
        label_y = float(
            re.search(r'<text\b[^>]*\by="([-\d.]+)"[^>]*>query vector', out).group(1)
        )
        self.assertLess(pill_y, 198.0)
        self.assertLess(label_y, 214.0)

    def test_nudge_subtitle_clear_of_donut(self):
        from tasks.table_layout import nudge_annotation_off_headlines
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="420" y="120" font-size="28" font-weight="700">Graph service</text>'
            '<text x="420" y="168" font-size="14" fill="#64748B">'
            "Observed on n = 100 instances.</text>"
            '<circle cx="520" cy="260" r="120" fill="none" stroke="#2563EB" stroke-width="28"/>'
            "</svg>"
        )
        out = nudge_annotation_off_headlines(svg)
        y = float(
            re.search(
                r'<text\b[^>]*\by="([-\d.]+)"[^>]*>Observed on n = 100 instances\.',
                out,
            ).group(1)
        )
        self.assertLess(y, 168.0)


    def test_nudge_bar_value_outside_fill(self):
        from tasks.table_layout import nudge_bar_value_labels
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="88" y="351" width="270" height="28" rx="8" fill="#CBD5E1"/>'
            '<text x="370" y="371" text-anchor="end" font-size="15" font-weight="700">100</text>'
            "</svg>"
        )
        out = nudge_bar_value_labels(svg)
        attrs = re.search(r"<text\b([^>]*)>100</text>", out).group(1)
        x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
        self.assertGreaterEqual(x, 88 + 270 + 8)
        self.assertIn('text-anchor="start"', attrs)

    def test_clamp_ignores_chart_dots_when_reserving_left_rail(self):
        """Network/chart dots must not pin card copy to the right edge."""
        from tasks.table_layout import (
            clamp_freehand_text_to_canvas,
            expand_cards_for_overflowing_text,
        )
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="60" y="190" width="550" height="350" rx="10" fill="#F8FAFC"/>'
            '<rect x="670" y="190" width="550" height="350" rx="10" fill="#F8FAFC"/>'
            '<circle cx="108" cy="238" r="24" fill="#EBF4FB"/>'
            '<circle cx="120" cy="512" r="5" fill="#3B82F6"/>'
            '<circle cx="178" cy="512" r="5" fill="#3B82F6"/>'
            '<circle cx="236" cy="512" r="5" fill="#3B82F6"/>'
            '<circle cx="294" cy="512" r="5" fill="#3B82F6"/>'
            '<circle cx="352" cy="512" r="5" fill="#3B82F6"/>'
            '<circle cx="410" cy="512" r="5" fill="#3B82F6"/>'
            '<circle cx="468" cy="512" r="5" fill="#3B82F6"/>'
            '<circle cx="526" cy="512" r="5" fill="#3B82F6"/>'
            '<text x="537" y="245" font-size="17.28" font-weight="700">'
            "Computational bottleneck</text>"
            '<text x="537" y="315" font-size="13">'
            "VRPTW repair must respect customer service,</text>"
            "</svg>"
        )
        out = expand_cards_for_overflowing_text(svg)
        out = clamp_freehand_text_to_canvas(out)
        attrs = re.search(
            r"<text\b([^>]*)>Computational bottleneck</text>", out
        ).group(1)
        x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
        fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))
        # Must pull left of the gap into the neighbor card (~670).
        self.assertLess(x, 160)
        self.assertLessEqual(x + len("Computational bottleneck") * fs * 0.58, 640)

    def test_clamp_preserves_structured_tspans_with_n_equals(self):
        """Prose like 'n=400' must not be treated as a formula and flattened."""
        from tasks.table_layout import clamp_freehand_text_to_canvas
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="60" y="174" width="480" height="300" rx="12" fill="#EBF4FB"/>'
            '<text x="92" y="469" font-size="18" fill="#1A202C">'
            '<tspan x="92" dy="0">Random-clustered, n=400</tspan>'
            '<tspan x="92" dy="27" fill="#4A5568">3.10x reduction; 1.02 cost ratio</tspan>'
            "</text>"
            "</svg>"
        )
        out = clamp_freehand_text_to_canvas(svg)
        self.assertEqual(out.count("<text"), 1)
        self.assertIn("Random-clustered, n=400", out)
        self.assertIn("1.02 cost ratio", out)
        self.assertIn("<tspan", out)

    def test_expand_grows_card_for_tspan_bottom_and_child_line(self):
        from tasks.table_layout import (
            clamp_shapes_inside_cards,
            expand_cards_for_overflowing_text,
        )
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="686" y="384" width="508" height="102" rx="8" fill="#FFFFFF"/>'
            '<rect x="785" y="442" width="250" height="18" rx="9" fill="#1A365D"/>'
            '<line x1="1058" y1="431" x2="1058" y2="494" stroke="#C53030" stroke-width="2"/>'
            '<text x="1074" y="449" font-size="14" fill="#C53030">Uneven</text>'
            '<text x="1074" y="470" font-size="14" fill="#C53030">load</text>'
            "</svg>"
        )
        out = expand_cards_for_overflowing_text(svg)
        h = float(
            re.search(r'<rect[^>]*\bx="686"[^>]*\bheight="([\d.]+)"', out).group(1)
        )
        self.assertGreater(h, 102)
        out = clamp_shapes_inside_cards(out)
        line = re.search(r"<line\b([^>]*)/?>", out).group(1)
        y2 = float(re.search(r'\by2="([-\d.]+)"', line).group(1))
        self.assertLessEqual(y2, 384 + h - 8)

    def test_resolve_coincident_short_labels(self):
        from tasks.table_layout import resolve_coincident_text_labels
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="1130" y="399" font-size="15">A</text>'
            '<text x="1130" y="399" font-size="15">B</text>'
            '<text x="1130" y="399" font-size="15">C</text>'
            '<text x="1130" y="399" font-size="15">D</text>'
            "</svg>"
        )
        out = resolve_coincident_text_labels(svg)
        xs = [
            float(re.search(r'\bx="([-\d.]+)"', m.group(1)).group(1))
            for m in re.finditer(r"<text\b([^>]*)>[ABCD]</text>", out)
        ]
        self.assertEqual(len(set(round(x) for x in xs)), 4)

    def test_nudge_short_metric_callout(self):
        from tasks.table_layout import nudge_annotation_off_headlines
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="537" y="465" font-size="24" font-weight="700">O(rn)</text>'
            '<text x="537" y="461" font-size="11" fill="#475569">'
            "candidate positions checked during repair</text>"
            "</svg>"
        )
        out = nudge_annotation_off_headlines(svg)
        y = float(
            re.search(
                r'<text\b[^>]*\by="([-\d.]+)"[^>]*>candidate positions',
                out,
            ).group(1)
        )
        self.assertNotAlmostEqual(y, 461.0, places=0)

    def test_resolve_chart_callouts_clear_title_band(self):
        from tasks.table_layout import resolve_chart_callout_overlaps
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="60" y="180" width="790" height="420" rx="12" fill="#F8FAFC"/>'
            '<circle cx="318" cy="272" r="8" fill="#F59E0B"/>'
            '<circle cx="360" cy="261" r="8" fill="#F59E0B"/>'
            '<circle cx="753" cy="221" r="8" fill="#F59E0B"/>'
            '<rect x="274" y="220" width="126" height="52" rx="8" fill="#FFF" stroke="#F59E0B"/>'
            '<rect x="381" y="207" width="126" height="52" rx="8" fill="#FFF" stroke="#F59E0B"/>'
            '<rect x="600" y="188" width="156" height="52" rx="8" fill="#FFF" stroke="#F59E0B"/>'
            '<text x="92" y="218" font-size="20" font-weight="bold">Weight sweep: cost increase vs CV reduction</text>'
            '<text x="92" y="244" font-size="14">Each point is a tested policy setting</text>'
            '<text x="288" y="241" font-size="15">beta=0.6, gamma=0.4</text>'
            '<text x="395" y="228" font-size="15">beta=1.0, gamma=0.6</text>'
            '<text x="614" y="209" font-size="15">beta=2.0, gamma=1.2</text>'
            "</svg>"
        )
        out = resolve_chart_callout_overlaps(svg)
        # Callout tops must sit below the subtitle band (~244).
        ys = [float(y) for y in re.findall(r'<rect[^>]*\by="([-\d.]+)"[^>]*height="52"', out)]
        self.assertTrue(ys)
        self.assertTrue(all(y >= 254 for y in ys), ys)
        # Labels moved with their boxes.
        self.assertIn("beta=2.0, gamma=1.2", out)

    def test_fit_freehand_table_columns_keeps_headers_inside(self):
        from tasks.table_layout import fit_freehand_table_columns
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="84" y="198" width="662" height="48" rx="5" fill="#1E3A8A"/>'
            '<rect x="84" y="254" width="662" height="42" fill="#EAF2FF"/>'
            '<line x1="310" y1="198" x2="310" y2="296" stroke="#CBD5E1"/>'
            '<line x1="468" y1="198" x2="468" y2="296" stroke="#CBD5E1"/>'
            '<text x="102" y="228" font-size="16" font-weight="700" fill="#FFFFFF">Method</text>'
            '<text x="334" y="228" font-size="16" font-weight="700" fill="#FFFFFF">Mean cost signal</text>'
            '<text x="492" y="228" font-size="16" font-weight="700" fill="#FFFFFF">CV signal</text>'
            '<text x="650" y="228" font-size="16" font-weight="700" fill="#FFFFFF">Interpretation</text>'
            '<text x="102" y="281" font-size="17">ALNS cost-only</text>'
            '<text x="650" y="281" font-size="15">retrieval guidance</text>'
            "</svg>"
        )
        out = fit_freehand_table_columns(svg)
        right = 84 + 662
        # Four headers require three vertical dividers.
        divs = re.findall(
            r'<line[^>]*\bx1="([\d.]+)"[^>]*\by1="198"[^>]*\by2="296"',
            out,
        )
        self.assertEqual(3, len(divs))
        for label in ("Interpretation", "retrieval guidance", "Mean cost signal"):
            attrs = re.search(rf"<text\b([^>]*)>{re.escape(label)}</text>", out).group(1)
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))
            fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))
            self.assertLessEqual(x + len(label) * fs * 0.56, right - 4)
            self.assertGreaterEqual(fs, 12)




    def test_fit_source_table_realigns_shifted_numeric_cells(self):
        from tasks.table_layout import fit_freehand_table_columns
        import re

        # Body Cost values wrongly parked under CV (x=490) with end anchor.
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="40" y="276" width="1200" height="38" rx="12" fill="#1E3A8A"/>'
            '<line x1="241" y1="276" x2="241" y2="400" stroke="#CBD5E1"/>'
            '<line x1="441" y1="276" x2="441" y2="400" stroke="#CBD5E1"/>'
            '<line x1="640" y1="276" x2="640" y2="400" stroke="#CBD5E1"/>'
            '<text x="56" y="301" font-size="15" font-weight="700" fill="#FFFFFF">Method</text>'
            '<text x="255" y="301" font-size="15" font-weight="700" fill="#FFFFFF">Cost</text>'
            '<text x="455" y="301" font-size="15" font-weight="700" fill="#FFFFFF">CV</text>'
            '<text x="654" y="301" font-size="15" font-weight="700" fill="#FFFFFF">Gini</text>'
            '<text x="60" y="338" data-sunairum-source-table-text="1" font-size="15">ALNS</text>'
            '<text x="490" y="338" data-sunairum-source-table-text="1" '
            'text-anchor="end" font-size="15">213199.4</text>'
            '<text x="660" y="338" data-sunairum-source-table-text="1" '
            'text-anchor="end" font-size="15">1.2517</text>'
            '<text x="830" y="338" data-sunairum-source-table-text="1" '
            'text-anchor="end" font-size="15">0.4089</text>'
            "</svg>"
        )
        out = fit_freehand_table_columns(svg)
        cost_attrs = re.search(
            r'<text\b([^>]*)>213199\.4</text>',
            out,
        ).group(1)
        cost_x = float(re.search(r'\bx="([-\d.]+)"', cost_attrs).group(1))
        divs = sorted(
            float(x)
            for x in re.findall(
                r'<line[^>]*\bx1="([\d.]+)"[^>]*\by1="276"',
                out,
            )
        )
        self.assertGreaterEqual(len(divs), 2)
        # Cost is column 1: end-aligned inside [div0, div1].
        self.assertGreater(cost_x, divs[0])
        self.assertLessEqual(cost_x, divs[1] + 0.5)
        self.assertIn('text-anchor="end"', cost_attrs)

    def test_title_rule_clearance_pushes_accent_below_wrap(self):
        from tasks.free_design_pipeline import resolve_content_title_rule_clearance
        import re

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="60" y="52" width="1160" height="72" rx="6" fill="#F8FAFC"/>'
            '<rect x="60" y="116" width="1160" height="3" fill="#3B82F6"/>'
            '<text x="60" y="88" font-size="28" font-weight="700" fill="#1E3A8A">'
            '<tspan x="60" dy="0">The effect persists on asymmetric real</tspan>'
            '<tspan x="60" dy="36">world instances-but not uniformly</tspan>'
            "</text>"
            '<text x="76" y="148" font-size="18" fill="#475569">Body lede stays readable.</text>'
            '<line x1="310" y1="198" x2="310" y2="626" stroke="#CBD5E1"/>'
            "</svg>"
        )
        out = resolve_content_title_rule_clearance(svg, role="content")
        accent = re.search(
            r'<rect\b(?=[^>]*height="3")(?=[^>]*width="1160")[^>]*\by="([-\d.]+)"[^>]*/?>',
            out,
        ) or re.search(
            r'<rect\b(?=[^>]*\by="([-\d.]+)")(?=[^>]*height="3")(?=[^>]*width="1160")[^>]*/?>',
            out,
        )
        self.assertIsNotNone(accent)
        rule_y = float(accent.group(1))
        # Second title baseline is 124; rule must sit clearly below it.
        self.assertGreaterEqual(rule_y, 124 + 20)
        # Vertical table divider must stay vertical.
        self.assertIn('y1="198"', out)
        self.assertIn('y2="626"', out)
        plate = re.search(
            r'<rect\b(?=[^>]*fill="#F8FAFC")(?=[^>]*width="1160")[^>]*height="([\d.]+)"',
            out,
        ) or re.search(
            r'<rect\b(?=[^>]*width="1160")(?=[^>]*fill="#F8FAFC")[^>]*height="([\d.]+)"',
            out,
        )
        self.assertIsNotNone(plate)
        self.assertGreaterEqual(52 + float(plate.group(1)), rule_y - 0.5)




class CompileRefuseTests(unittest.TestCase):
    def test_finalize_compile_does_not_refuse_on_stale_qa_gate(self):
        from tasks import generator_agent as ga

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        validation = root / "validation"
        validation.mkdir()
        payload = json.dumps(
            {"x": 64, "y": 190, "width": 1152, "height": 480, "columns": ["A"], "rows": [["1"]]}
        )
        (svg_dir / "slide_01.svg").write_text(
            '<svg viewBox="0 0 1280 720">'
            '<image href="f.png" x="700" y="160" width="480" height="360"/>'
            f'<g data-pptx-replace-with="table"><metadata>{payload}</metadata></g>'
            "</svg>",
            encoding="utf-8",
        )
        (validation / "qa_gate.json").write_text(
            json.dumps({"blocking": True, "gate_green": False}),
            encoding="utf-8",
        )

        # Compile may fail later for missing release artifacts — never for QA/layout.
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=1, stdout="", stderr="boom")
            with self.assertRaises(RuntimeError) as ctx:
                ga.finalize_compile(str(root), project_id="p")
        message = str(ctx.exception).lower()
        self.assertNotIn("layout gate", message)
        self.assertNotIn("pre-pptx gate", message)


class NotesDurationTests(unittest.TestCase):
    def test_allocate_budgets_5m_vs_20m_differ(self):
        from tasks.speaker_notes import allocate_budgets, scaled_role_caps, word_budget

        roles = ["title"] + ["content"] * 13
        caps5 = scaled_role_caps(word_budget(5))
        caps20 = scaled_role_caps(word_budget(20))
        b5 = allocate_budgets(roles, word_budget(5), caps=caps5)
        b20 = allocate_budgets(roles, word_budget(20), caps=caps20)
        self.assertLess(sum(b5), sum(b20) * 0.55)
        self.assertLess(caps5["content"][0], caps20["content"][0])

    def test_thanks_notes_do_not_repeat_slide_slogan(self):
        from tasks.speaker_notes import dedupe_spoken_note, rewrite_to_budget

        messy = "Thank you. Questions are welcome. Thank you Questions welcome."
        clean = dedupe_spoken_note(messy)
        self.assertEqual(clean.casefold().count("thank you"), 1)
        self.assertIn("Questions are welcome", clean)
        self.assertNotIn("Questions welcome", clean)

        note, _warnings = rewrite_to_budget(
            slide_text="Thank you\nQuestions welcome\n14 / 14",
            prior_notes="Thank you. Questions are welcome.",
            budget=30,
            role="thanks",
            call_text=None,
            preserve_facts=False,
            prefer_llm=False,
        )
        self.assertEqual(note.casefold().count("thank you"), 1)
        self.assertNotIn("Questions welcome", note.replace("Questions are welcome", ""))

    def test_title_notes_do_not_repeat_presenter_or_affiliation(self):
        from tasks.speaker_notes import (
            _title_from_svg,
            rewrite_to_budget,
            title_opening_fallback,
        )

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="112" y="280" font-size="52">Neighborhood Search for</text>'
            '<text x="112" y="344" font-size="52">Equitable Vehicle Routing</text>'
            '<text x="60" y="439" font-size="22">Assoc. Prof. Dr. Asım Sinan Yüksel</text>'
            '<text x="112" y="475" font-size="18">'
            "Süleyman Demirel University Department of Computer Engineering, Isparta, Türkiye"
            "</text>"
            "</svg>"
        )
        title = _title_from_svg(svg)
        self.assertIn("Neighborhood Search for", title)
        self.assertIn("Equitable Vehicle Routing", title)
        presenter = "Assoc. Prof. Dr. Asım Sinan Yüksel"
        slide_text = (
            "Neighborhood Search for\nEquitable Vehicle Routing\n"
            f"{presenter}\n"
            "Süleyman Demirel University Department of Computer Engineering, Isparta, Türkiye"
        )
        note = title_opening_fallback(
            slide_title=title,
            slide_text=slide_text,
            presenter=presenter,
            tone="academic",
            budget=90,
        )
        self.assertEqual(1, note.casefold().count(presenter.casefold()))
        self.assertNotIn("University", note)
        self.assertIn("Equitable Vehicle Routing", note)

        rewritten, _warnings = rewrite_to_budget(
            slide_text=slide_text,
            prior_notes="",
            budget=90,
            role="title",
            call_text=None,
            preserve_facts=False,
            context={"presenter": presenter, "tone": "academic"},
            slide_title=title,
            prefer_llm=False,
        )
        self.assertEqual(1, rewritten.casefold().count(presenter.casefold()))
        self.assertNotIn("University", rewritten)
        self.assertNotIn("Isparta", rewritten)

    def test_fit_auto_shortens_long_notes(self):
        from tasks.speaker_notes import fit_notes_to_duration

        root = Path(tempfile.mkdtemp())
        (root / "svg_output").mkdir()
        (root / "notes").mkdir()
        (root / "confirm_ui").mkdir()
        (root / "confirm_ui" / "result.json").write_text(
            json.dumps({"target_duration_minutes": 5, "proactive_speaker_notes": True}),
            encoding="utf-8",
        )
        long = " ".join(["word"] * 200)
        for i in range(1, 4):
            (root / "svg_output" / f"slide_{i:02d}.svg").write_text(
                f'<svg viewBox="0 0 1280 720"><text x="80" y="100" font-size="28">'
                f"Slide {i} title about methods</text>"
                f'<text x="80" y="200" font-size="16">Body copy for slide {i}.</text></svg>',
                encoding="utf-8",
            )
            (root / "notes" / f"slide_{i:02d}.md").write_text(long + "\n", encoding="utf-8")

        report = fit_notes_to_duration(
            root,
            target_duration_minutes=5,
            wpm=125,
            mode="auto",
            call_text=None,
            backup=False,
        )
        self.assertLess(report["actual_words"], 200 * 3)
        self.assertGreaterEqual(report["changed_slides"], 1)

    def test_fit_auto_lengthens_short_notes(self):
        from tasks.speaker_notes import fit_notes_to_duration

        root = Path(tempfile.mkdtemp())
        (root / "svg_output").mkdir()
        (root / "notes").mkdir()
        short = "Brief point."
        body = (
            "The method improves retrieval quality under latency constraints. "
            "Benchmark results show lower cost and better equity metrics. "
            "Ablations confirm each component contributes to the gains observed."
        )
        for i in range(1, 4):
            (root / "svg_output" / f"slide_{i:02d}.svg").write_text(
                f'<svg viewBox="0 0 1280 720"><text x="80" y="100" font-size="28">'
                f"Slide {i} results overview</text>"
                f'<text x="80" y="200" font-size="16">{body}</text></svg>',
                encoding="utf-8",
            )
            (root / "notes" / f"slide_{i:02d}.md").write_text(short + "\n", encoding="utf-8")

        report = fit_notes_to_duration(
            root,
            target_duration_minutes=20,
            wpm=125,
            mode="auto",
            call_text=None,
            backup=False,
        )
        self.assertGreater(report["actual_words"], 3 * 2)
        self.assertGreaterEqual(report["changed_slides"], 1)

    def test_orphan_notes_deleted(self):
        from tasks.speaker_notes import delete_orphan_notes, fit_notes_to_duration

        root = Path(tempfile.mkdtemp())
        (root / "svg_output").mkdir()
        (root / "notes").mkdir()
        (root / "svg_output" / "slide_01.svg").write_text(
            '<svg viewBox="0 0 1280 720"><text x="80" y="100" font-size="32">Title</text></svg>',
            encoding="utf-8",
        )
        (root / "notes" / "slide_01.md").write_text("Hello world notes here.\n", encoding="utf-8")
        (root / "notes" / "slide_99.md").write_text("orphan dump " * 40 + "\n", encoding="utf-8")
        removed = delete_orphan_notes(root)
        self.assertIn("slide_99.md", removed)
        self.assertFalse((root / "notes" / "slide_99.md").exists())

        fit_notes_to_duration(
            root,
            target_duration_minutes=5,
            mode="compress",
            call_text=None,
            backup=False,
        )
        self.assertFalse((root / "notes" / "slide_99.md").exists())

    def test_regenerate_uses_one_batch_llm_call(self):
        from tasks.speaker_notes import fit_notes_to_duration

        root = Path(tempfile.mkdtemp())
        (root / "svg_output").mkdir()
        (root / "notes").mkdir()
        calls = {"n": 0}

        def fake_llm(system: str, user: str) -> str:
            calls["n"] += 1
            self.assertIn("JSON", system)
            return (
                '{"slide_01":"Good morning. Today I will present methods.",'
                '"slide_02":"Next we cover the evaluation setup and metrics.",'
                '"slide_03":"Finally we summarize the main takeaways."}'
            )

        for i in range(1, 4):
            (root / "svg_output" / f"slide_{i:02d}.svg").write_text(
                f'<svg viewBox="0 0 1280 720"><text x="80" y="100" font-size="28">'
                f"Slide {i} title</text></svg>",
                encoding="utf-8",
            )
        progress = []
        report = fit_notes_to_duration(
            root,
            target_duration_minutes=10,
            wpm=125,
            mode="regenerate",
            call_text=fake_llm,
            backup=False,
            progress_callback=lambda cur, tot: progress.append((cur, tot)),
        )
        self.assertEqual(1, calls["n"])
        self.assertEqual(1, report.get("llm_calls"))
        self.assertEqual([(1, 3), (2, 3), (3, 3)], progress)
        self.assertIn("Good morning", (root / "notes" / "slide_01.md").read_text())
        # Notes must not touch SVGs.
        self.assertNotIn("Good morning", (root / "svg_output" / "slide_01.svg").read_text())


class EquationGlyphTests(unittest.TestCase):
    def test_transliterate_norm_subscripts(self):
        from tasks.unicode_math import sanitize_svg_math, svg_has_unsafe_math, transliterate_math_text

        raw = "F = Dₙₒᵣₘ + β · CVₙₒᵣₘ + γ · (1 − J)"
        safe = transliterate_math_text(raw)
        self.assertNotIn("ₙ", safe)
        self.assertIn("D_norm", safe)
        self.assertIn("CV_norm", safe)
        self.assertFalse(any(ch in safe for ch in "ₙₒᵣₘ"))

        svg = (
            f'<svg viewBox="0 0 1280 720">'
            f'<text x="80" y="200" font-family="Georgia" font-size="22">{raw}</text>'
            f"</svg>"
        )
        self.assertTrue(svg_has_unsafe_math(svg))
        out = sanitize_svg_math(svg)
        self.assertFalse(svg_has_unsafe_math(out))
        self.assertIn("D_norm", out)
        self.assertIn("Cambria", out)

    def test_r_sub_and_real_sup(self):
        from tasks.unicode_math import transliterate_math_text

        self.assertEqual("r_1", transliterate_math_text("r₁"))
        self.assertIn("R^14", transliterate_math_text("ℝ¹⁴"))


class DeckQaHardCategoriesTests(unittest.TestCase):
    def test_no_categories_hard_block_export(self):
        from tasks.deck_qa import HARD_BLOCK_CATEGORIES, STRUCTURAL_REPORT_CATEGORIES, hard_blocking_issues

        self.assertEqual(frozenset(), HARD_BLOCK_CATEGORIES)
        self.assertIn("table-covers-content", STRUCTURAL_REPORT_CATEGORIES)
        self.assertIn("missing-glyph", STRUCTURAL_REPORT_CATEGORIES)
        self.assertEqual([], hard_blocking_issues([
            {"category": "missing-image", "severity": "error"},
            {"category": "table-grid-mismatch", "severity": "error"},
        ]))

    def test_normalize_bumps_tiny_table_fonts(self):
        from tasks.deck_qa import check_native_tables, hard_blocking_issues
        from tasks.table_layout import normalize_native_table_metadata

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table">'
            "<metadata>"
            '{"x":40,"y":200,"width":500,"height":300,"columns":[{"text":"A"},{"text":"B"}],'
            '"rows":[[{"text":"one"},{"text":"two"}],[{"text":"three"},{"text":"four"}]],'
            '"style":{"font_size":9,"header_font_size":9}}'
            "</metadata>"
            "</g></svg>"
        )
        fixed = normalize_native_table_metadata(svg)
        compact = fixed.replace(" ", "")
        self.assertTrue('"font_size":12' in compact or '"font_size":12.0' in compact)

        root = Path(tempfile.mkdtemp())
        svg_dir = root / "svg_output"
        svg_dir.mkdir()
        (svg_dir / "slide_01.svg").write_text(fixed, encoding="utf-8")
        issues = check_native_tables(str(svg_dir))
        self.assertFalse(hard_blocking_issues(issues))
        self.assertFalse(any(i.get("category") == "table-grid-mismatch" for i in issues))


if __name__ == "__main__":
    unittest.main()
