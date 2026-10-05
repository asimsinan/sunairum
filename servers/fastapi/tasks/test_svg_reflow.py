"""Deterministic freehand SVG reflow."""

from __future__ import annotations

import unittest


class SvgReflowTests(unittest.TestCase):
    def test_near_coincident_texts_are_stacked(self):
        from tasks.svg_reflow import near_coincident_pairs, reflow_near_coincident_text

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<text x="142" y="446" font-size="18">Shared Clarke-Wright initial solution</text>'
            '<text x="132" y="446" font-size="18">Same random seed for ALNS variants</text>'
            '<text x="132" y="446" font-size="18">500 iterations * 3 seeds</text>'
            "</svg>"
        )
        self.assertGreaterEqual(len(near_coincident_pairs(svg)), 2)
        out = reflow_near_coincident_text(svg)
        self.assertEqual([], near_coincident_pairs(out))
        ys = []
        import re

        for m in re.finditer(r'\by="([-\d.]+)"', out):
            ys.append(float(m.group(1)))
        self.assertEqual(3, len(ys))
        self.assertGreater(max(ys) - min(ys), 20.0)

    def test_near_coincident_title_stacks_above_body(self):
        """Bold/larger title near body baseline must not land below body (02/03 drift)."""
        from tasks.svg_reflow import reflow_near_coincident_text
        import re

        # Reproduce slide_02: title painted at y≈397 with body at y≈400.
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<text x="80" y="400" font-size="14" fill="#334155">'
            "Exact checks keep routes feasible under tight windows.</text>"
            '<text x="82" y="397" font-size="24" font-weight="700" fill="#1A365D">'
            "HERO direction</text>"
            "</svg>"
        )
        out = reflow_near_coincident_text(svg)
        texts = list(re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", out))
        by_plain = {}
        for m in texts:
            plain = re.sub(r"<[^>]+>", " ", m.group(2)).strip()
            ym = re.search(r'\by="([-\d.]+)"', m.group(1))
            self.assertIsNotNone(ym)
            by_plain[plain] = float(ym.group(1))
        self.assertLess(by_plain["HERO direction"], by_plain[
            "Exact checks keep routes feasible under tight windows."
        ])
        # Must not amplify to title y ≈ 429.4 (old ascending-y stack).
        self.assertLess(by_plain["HERO direction"], 410.0)

    def test_bar_value_gutters_separate_dual_series(self):
        from tasks.svg_reflow import reflow_bar_value_gutters
        import re

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect x="120" y="400" width="200" height="20" fill="#93C5FD"/>'
            '<rect x="120" y="400" width="140" height="20" fill="#1D4ED8"/>'
            '<rect x="420" y="400" width="200" height="20" fill="#FDE68A"/>'
            '<rect x="420" y="400" width="80" height="20" fill="#D97706"/>'
            '<text x="250" y="414" font-size="14">-47.7%</text>'
            '<text x="490" y="414" font-size="14">+12.7%</text>'
            "</svg>"
        )
        out = reflow_bar_value_gutters(svg)
        xs = []
        for m in re.finditer(r'<text\b([^>]*)>', out):
            xm = re.search(r'\bx="([-\d.]+)"', m.group(1))
            if xm:
                xs.append(float(xm.group(1)))
        self.assertEqual(2, len(xs))
        # Left series gutter sits past fill (~260); right series past its fill (~500).
        self.assertGreater(xs[0], 250.0)
        self.assertGreater(xs[1], xs[0] + 40.0)

    def test_evict_circle_under_text(self):
        from tasks.svg_reflow import evict_shapes_under_text
        import re

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<circle cx="90" cy="200" r="10" fill="#FBBF24"/>'
            '<text x="86" y="205" font-size="20">Equity-guided setting</text>'
            "</svg>"
        )
        out = evict_shapes_under_text(svg)
        cm = re.search(r'\bcx="([-\d.]+)"', out)
        self.assertIsNotNone(cm)
        self.assertLess(float(cm.group(1)), 86.0)

    def test_evict_does_not_pull_right_ornament_under_centered_title(self):
        """Middle-anchored titles must not drag right-margin nodes into the headline."""
        from tasks.svg_reflow import evict_shapes_under_text
        import re

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<circle cx="1188" cy="208" r="7" fill="#1E3A8A"/>'
            '<text x="640" y="256" text-anchor="middle" font-size="52" font-weight="700">'
            "HNSW Guided Large Neighborhood Search</text>"
            "</svg>"
        )
        out = evict_shapes_under_text(svg)
        cm = re.search(r'\bcx="([-\d.]+)"', out)
        self.assertIsNotNone(cm)
        self.assertGreaterEqual(float(cm.group(1)), 1100.0)

    def test_repair_cover_ornaments_snaps_nodes_under_title(self):
        from tasks.svg_reflow import repair_cover_ornaments_under_title
        import re

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<path d="M1000 150 C1080 150 1080 208 1188 208" stroke="#93C5FD" '
            'stroke-width="2" fill="none"/>'
            '<circle cx="623" cy="208" r="7" fill="#1E3A8A"/>'
            '<text x="640" y="256" text-anchor="middle" font-size="52">'
            "HNSW Guided Large Neighborhood Search</text>"
            "</svg>"
        )
        out = repair_cover_ornaments_under_title(svg)
        cm = re.search(r'\bcx="([-\d.]+)"', out)
        self.assertIsNotNone(cm)
        self.assertGreaterEqual(float(cm.group(1)), 1100.0)

    def test_split_merged_bullet_list_text_aligns_to_markers(self):
        from tasks.svg_reflow import split_merged_bullet_list_text
        import re

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<circle cx="66" cy="181" r="5" fill="#3B82F6"/>'
            '<circle cx="66" cy="203" r="5" fill="#F59E0B"/>'
            '<text x="100" y="186" font-size="15.3556" fill="#0F172A">'
            '<tspan x="100" dy="0">Approximate retrieval proposes a compact candidate set.</tspan>'
            '<tspan x="100" dy="25">Exact feasibility checks and scalarized scoring determine the insertion.</tspan>'
            "</text>"
            "</svg>"
        )
        out = split_merged_bullet_list_text(svg)
        texts = list(re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", out))
        self.assertEqual(2, len(texts))
        ys = [float(re.search(r'\by="([-\d.]+)"', m.group(1)).group(1)) for m in texts]
        self.assertAlmostEqual(ys[0], 186.0, places=1)
        self.assertAlmostEqual(ys[1], 208.0, places=1)
        self.assertIn("Approximate retrieval", texts[0].group(2))
        self.assertIn("Exact feasibility", texts[1].group(2))
        self.assertNotIn("<tspan", out.casefold())

    def test_split_merged_bullet_list_skips_soft_wrapped_sentence(self):
        from tasks.svg_reflow import split_merged_bullet_list_text
        import re

        # One logical bullet soft-wrapped across tspans beside two stray markers.
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<circle cx="66" cy="181" r="5" fill="#3B82F6"/>'
            '<circle cx="66" cy="203" r="5" fill="#F59E0B"/>'
            '<text x="100" y="186" font-size="15" fill="#0F172A">'
            '<tspan x="100" dy="0">Approximate retrieval proposes a compact candidate set that still needs</tspan>'
            '<tspan x="100" dy="25">exact feasibility checks before insertion.</tspan>'
            "</text>"
            "</svg>"
        )
        out = split_merged_bullet_list_text(svg)
        self.assertEqual(1, len(re.findall(r"<text\b", out)))

    def test_align_row_markers_to_titles_snaps_hollow_circles(self):
        from tasks.svg_reflow import align_row_markers_to_titles
        import re

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<circle cx="76" cy="202" r="16" fill="none" stroke="#3182CE"/>'
            '<circle cx="76" cy="300" r="16" fill="none" stroke="#3182CE"/>'
            '<text x="108" y="238.6" font-size="18" font-weight="700" fill="#1A365D">Solomon</text>'
            '<text x="108" y="357.6" font-size="18" font-weight="700" fill="#1A365D">Homberger</text>'
            "</svg>"
        )
        out = align_row_markers_to_titles(svg)
        cys = [
            float(m.group(1))
            for m in re.finditer(r'\bcy="([-\d.]+)"', out)
        ]
        self.assertEqual(2, len(cys))
        self.assertAlmostEqual(cys[0], 238.6 - 18 * 0.35, places=1)
        self.assertAlmostEqual(cys[1], 357.6 - 18 * 0.35, places=1)

    def test_rewrap_overflowing_text_keeps_lines_inside_canvas(self):
        from tasks.svg_reflow import rewrap_overflowing_text
        import re

        long = (
            "Real-world asymmetric instances with 300-400 customers, "
            "tight time windows, and prescribed fleet sizes across sites, "
            "plus heterogeneous service times that stretch every route plan."
        )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect x="40" y="160" width="1200" height="94" fill="#F5F7FA"/>'
            f'<text x="300" y="213.4" font-size="16" fill="#1A202C">{long}</text>'
            "</svg>"
        )
        out = rewrap_overflowing_text(svg)
        tspans = re.findall(r"<tspan\b[^>]*>([\s\S]*?)</tspan>", out, flags=re.I)
        self.assertGreaterEqual(len(tspans), 2)
        from tasks.text_layout import text_width_px

        for bit in tspans:
            line = re.sub(r"\s+", " ", bit).strip()
            self.assertLessEqual(
                300 + text_width_px(line, 16, font_family="Arial"),
                1220.0,
                msg=line,
            )

    def test_fit_takeaway_band_enforces_label_gap_and_wraps(self):
        from tasks.svg_reflow import fit_takeaway_band
        import re

        claim = (
            "Guided search recovers feasible routes faster than random destroy "
            "while preserving fairness across depot loads."
        )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect x="48" y="560" width="900" height="90" fill="#1A365D"/>'
            '<text x="72" y="594" font-size="14" font-weight="700" fill="#FFFFFF">TAKEAWAY</text>'
            f'<text x="72" y="604" font-size="16" fill="#FFFFFF">{claim}</text>'
            "</svg>"
        )
        out = fit_takeaway_band(svg)
        self.assertNotIn("…", out)
        self.assertNotIn("...", out)
        texts = list(re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", out))
        ys = {}
        for m in texts:
            plain = re.sub(r"<[^>]+>", " ", m.group(2)).strip()
            ym = re.search(r'\by="([-\d.]+)"', m.group(1))
            key = "TAKEAWAY" if plain.startswith("TAKEAWAY") else "body"
            ys[key] = float(ym.group(1))
        self.assertGreaterEqual(ys["body"] - ys["TAKEAWAY"], 14 * 1.35 - 0.5)

    def test_clear_horizontal_path_through_caption(self):
        from tasks.svg_reflow import clear_lines_through_text

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<path d="M482 348 H555" stroke="#3182CE" stroke-width="2" fill="none"/>'
            '<text x="490" y="354" font-size="14" fill="#1A202C">cost + fairness</text>'
            "</svg>"
        )
        out = clear_lines_through_text(svg)
        self.assertNotIn('d="M482 348 H555"', out)
        self.assertIn("cost + fairness", out)


if __name__ == "__main__":
    unittest.main()
