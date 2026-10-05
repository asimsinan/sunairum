"""Tests for fail-safe compile / formula fit / narrative / label / keep-best plan."""

from __future__ import annotations

import re
import unittest


class FormulaPlateFitTests(unittest.TestCase):
    def test_flatten_to_plate_scale_not_tiny(self):
        from tasks.formula_latex_png import flatten_math_svg_to_group

        # Wide viewBox, tiny layout-like target must still meet plate box.
        math = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -200 2800 900" '
            'data-sunairum-math-w="61" data-sunairum-math-h="20">'
            '<path d="M10 10 L100 10"/></svg>'
        )
        flat = flatten_math_svg_to_group(math, width=480, height=56, fill="#1A365D")
        self.assertIn("data-sunairum-formula-math", flat)
        sm = __import__("re").search(r"scale\(([-\d.]+)\)", flat)
        self.assertIsNotNone(sm)
        self.assertGreaterEqual(float(sm.group(1)), 0.015)

    def test_formula_math_too_small_detects_p04_scale(self):
        from tasks.formula_visual_intent import formula_math_too_small

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-formula-math="1" transform="scale(0.021717)">'
            '<path d="M1 1"/></g></svg>'
        )
        self.assertTrue(formula_math_too_small(svg))
        ok = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-formula-math="1" transform="scale(0.2)">'
            '<path d="M1 1"/></g></svg>'
        )
        self.assertFalse(formula_math_too_small(ok))


class LabelLegibilityTests(unittest.TestCase):
    def test_lift_text_off_ink_moves_label_off_center_dot(self):
        from tasks.svg_reflow import lift_text_off_ink

        svg = """<svg viewBox="0 0 1280 720">
  <circle cx="640" cy="368" r="82" fill="#EBF4FB" stroke="#1A365D"/>
  <circle cx="640" cy="368" r="8" fill="#3182CE"/>
  <line x1="584" y1="368" x2="696" y2="368" stroke="#1A365D"/>
  <text x="640" y="376" text-anchor="middle" font-size="16" fill="#1A365D">insertion position</text>
</svg>"""
        out = lift_text_off_ink(svg)
        self.assertIn('r="82"', out)
        self.assertIn('r="8"', out)
        # Label y should move below motif or get a halo
        import re

        tm = re.search(
            r'<text[^>]*y="([-\d.]+)"[^>]*>insertion position</text>',
            out,
            flags=re.I,
        )
        halo = 'data-sunairum-text-halo="1"' in out
        if tm:
            self.assertTrue(float(tm.group(1)) > 400 or halo)
        else:
            self.assertTrue(halo)


class FigureHostTests(unittest.TestCase):
    def test_normalize_polymorphic_figure_slot(self):
        from tasks.intent_hosts import ensure_asset_hosts, has_canonical_figure_slot

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-figure-slot="true" data-sunairum-figure-id="fig1" '
            'transform="translate(100,160)"><rect width="200" height="100" fill="none"/></g>'
            "</svg>"
        )
        out = ensure_asset_hosts(svg, {"figure_id": "fig1"})
        self.assertTrue(has_canonical_figure_slot(out) or 'data-sunairum-figure-slot="1"' in out)

    def test_bound_image_satisfies_host(self):
        from tasks.free_design_pipeline import _executor_qa_issues
        from tasks.intent_hosts import ensure_asset_hosts

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<image href="../images/x.png" x="60" y="160" width="480" height="360" '
            'data-sunairum-figure-id="fig1"/>'
            "</svg>"
        )
        repaired = ensure_asset_hosts(svg, {"figure_id": "fig1"})
        issues = _executor_qa_issues(repaired, {"figure_id": "fig1"})
        self.assertFalse(any("missing_figure" in i for i in issues))


class TableBudgetTests(unittest.TestCase):
    def test_fit_grows_or_shrinks_until_budget(self):
        from tasks.table_native_budget import content_row_required_pt, fit_table_payload

        rows = [
            [{"text": "Method"}, {"text": "Cost"}],
            [{"text": "A very long method name that wraps"}, {"text": "1234.5"}],
            [{"text": "Another long row label here"}, {"text": "9999.9"}],
            [{"text": "Third wrapping label text"}, {"text": "111.1"}],
            [{"text": "Fourth wrapping label text"}, {"text": "222.2"}],
            [{"text": "Fifth wrapping label text"}, {"text": "333.3"}],
        ]
        payload = {
            "x": 588,
            "y": 160,
            "width": 624,
            "height": 200,
            "columns": ["Method", "Cost"],
            "rows": rows,
            "style": {"font_size": 16, "header_font_size": 16},
        }
        fitted = fit_table_payload(payload)
        _req, total, fits = content_row_required_pt(
            fitted["rows"],
            table_width_px=float(fitted["width"]),
            table_height_px=float(fitted["height"]),
            style=fitted.get("style"),
        )
        self.assertTrue(fits or float(fitted["height"]) >= 200)
        self.assertGreater(total, 0)

    def test_sync_table_host_rect_keeps_well_formed_attrs(self):
        import xml.etree.ElementTree as ET

        from tasks.table_native_budget import fit_native_tables_in_svg, sync_table_host_rect

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-pptx-replace-with="table" data-sunairum-source-table-id="t1" '
            'transform="translate(588,160)">'
            "<metadata>"
            '{"x":588,"y":160,"width":624,"height":200,'
            '"columns":["A","B"],'
            '"rows":[['
            '{"text":"h1"},{"text":"h2"}],'
            '[{"text":"long cell that needs space aaa"},{"text":"1"}],'
            '[{"text":"long cell that needs space bbb"},{"text":"2"}],'
            '[{"text":"long cell that needs space ccc"},{"text":"3"}],'
            '[{"text":"long cell that needs space ddd"},{"text":"4"}]'
            "],"
            '"style":{"font_size":16,"header_font_size":16}}'
            "</metadata>"
            '<rect x="0" y="0" width="624" height="200" rx="8" '
            'fill="#F5F7FA" stroke="#E2E8F0" stroke-width="1"/>'
            "</g></svg>"
        )
        out = fit_native_tables_in_svg(svg)
        ET.fromstring(out)
        self.assertNotRegex(out, r'height="[-\d.]+"[-\d.]')
        synced = sync_table_host_rect(
            svg,
            {"x": 588, "y": 160, "width": 624, "height": 424},
        )
        ET.fromstring(synced)
        self.assertIn('height="424"', synced)
        self.assertIn('rx="8"', synced)
        self.assertNotIn('height="424"424', synced)


class NarrativePanelTests(unittest.TestCase):
    def test_figure_claim_column_fills_empty_right(self):
        from tasks.asset_narrative import ensure_figure_claim_column

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="90" y="90" font-size="36">Title</text>'
            '<image href="../images/a.png" x="60" y="160" width="480" height="360" '
            'data-sunairum-figure-id="fig1"/>'
            '<text x="88" y="620" font-size="20">Takeaway only</text>'
            "</svg>"
        )
        pack = (
            "### P06: Demo\n"
            "- **Topic:** Should never appear in claims\n"
            "- **Content:**\n"
            "  - **Destroy:** removes customers.\n"
            "  - **Retrieve:** HNSW returns candidates.\n"
            "  - **Filter:** feasibility stays exact.\n"
            "- **Visual job:** Keep figure and claims together.\n"
        )
        out = ensure_figure_claim_column(
            svg, {"figure_id": "fig1", "core_message": "core"}, pack
        )
        self.assertIn('data-sunairum-figure-claims="1"', out)
        self.assertIn("Destroy", out)
        self.assertIn("removes customers", out)
        self.assertNotIn("Should never appear", out)

    def test_content_bullets_include_nested_labels(self):
        from tasks.asset_narrative import extract_content_bullets

        pack = (
            "- **Topic:** preamble meta\n"
            "- **Content:**\n"
            "  - **Feature encoder:** maps positions to vectors.\n"
            "  - **HNSW index:** returns candidates.\n"
            "- **Visual job:** explain the figure\n"
        )
        bullets = extract_content_bullets(pack)
        self.assertEqual(2, len(bullets))
        self.assertTrue(bullets[0].startswith("Feature encoder:"))
        self.assertIn("maps positions", bullets[0])

    def test_full_bleed_figure_shrinks_for_claim_column(self):
        from tasks.asset_narrative import ensure_figure_claim_column

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="90" y="90" font-size="36">Title</text>'
            '<image href="../images/a.png" x="128" y="194" width="1040" height="308" '
            'data-sunairum-figure-id="fig2"/>'
            '<text x="88" y="620" font-size="20">Takeaway only</text>'
            "</svg>"
        )
        pack = (
            "- **Content:**\n"
            "  - **Snapshot:** refresh distances.\n"
            "  - **Candidate pool:** retrieve k nearest.\n"
            "  - **Commit:** insert and update index.\n"
        )
        out = ensure_figure_claim_column(
            svg, {"figure_id": "fig2", "core_message": "core"}, pack
        )
        self.assertIn('data-sunairum-figure-claims="1"', out)
        self.assertIn("Snapshot", out)
        self.assertIn("refresh distances", out)
        img = re.search(
            r'<image[^>]*data-sunairum-figure-id="fig2"[^>]*>', out, flags=re.I
        )
        self.assertIsNotNone(img)
        w = float(re.search(r'\bwidth="([-\d.]+)"', img.group(0)).group(1))
        self.assertLessEqual(w, 720.0)

    def test_table_aside_fills_empty_left(self):
        from tasks.asset_narrative import ensure_table_aside_panel

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="90" y="90" font-size="36">Title</text>'
            '<g data-pptx-replace-with="table" data-sunairum-source-table-id="t1" '
            'transform="translate(588,160)">'
            '<rect width="600" height="300" fill="#F5F7FA"/>'
            "</g></svg>"
        )
        pack = (
            "### P10: Demo\n"
            "- **Content:**\n"
            "  - **Retrieval effect:** HNSW keeps cost similar.\n"
            "  - **Equity effect:** HERO improves balance.\n"
        )
        out = ensure_table_aside_panel(
            svg, {"table_id": "t1", "core_message": "split"}, pack
        )
        self.assertIn('data-sunairum-table-aside="1"', out)
        self.assertIn("Retrieval", out)

    def test_aside_skips_when_left_already_rich(self):
        from tasks.asset_narrative import ensure_table_aside_panel

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text x="60" y="180" font-size="20">Insight one about the table</text>'
            '<text x="60" y="220" font-size="20">Insight two about the table</text>'
            '<g data-pptx-replace-with="table" transform="translate(588,160)">'
            '<rect width="600" height="300" fill="#eee"/></g></svg>'
        )
        out = ensure_table_aside_panel(
            svg,
            {"table_id": "t1"},
            "- **Content:**\n  - **A:** aaa\n  - **B:** bbb\n",
        )
        self.assertNotIn('data-sunairum-table-aside="1"', out)


class KeepBestEnergyTests(unittest.TestCase):
    def test_composition_energy_prefers_richer(self):
        from tasks.free_design_pipeline import composition_energy

        stub = '<svg viewBox="0 0 1280 720"><text x="10" y="20">Hi</text></svg>'
        rich = (
            '<svg viewBox="0 0 1280 720">'
            '<circle cx="100" cy="100" r="20" fill="#3182CE"/>'
            '<polyline points="0,0 10,10" stroke="#63B3ED"/>'
            '<rect x="0" y="0" width="100" height="40" fill="#EBF4FB"/>'
            "</svg>"
        )
        pal = {"accent": "#3182CE", "secondary_accent": "#63B3ED"}
        self.assertGreater(composition_energy(rich, pal), composition_energy(stub, pal))

    def test_qa_feedback_preserve_density(self):
        import inspect

        from tasks import free_design_pipeline as fdp

        src = inspect.getsource(fdp.author_free_slide_svg)
        self.assertIn("Preserve existing accent", src)

    def test_soft_tips_energy_floor(self):
        from tasks.executor_modes import SOFT_SPLIT_FIGURE, SOFT_SPLIT_TABLE, soft_pattern_brief

        self.assertIn("secondary_accent", soft_pattern_brief(SOFT_SPLIT_FIGURE))
        self.assertIn("insights", soft_pattern_brief(SOFT_SPLIT_TABLE).casefold())

    def test_art_director_vivid_for_figure(self):
        from tasks.art_director import author_art_direction

        brief = author_art_direction(
            {"role": "content", "figure_id": "fig1", "title": "T"},
            craft_lines=["gap 24"],
            call_text=None,
        )
        self.assertEqual(brief.get("energy"), "vivid")

    def test_fill_empty_right_column_still_retired(self):
        import ast
        from pathlib import Path

        path = Path(__file__).resolve().parent / "free_design_pipeline.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertNotIn("fill_empty_right_column", names)
        self.assertIn("composition_energy", names)


if __name__ == "__main__":
    unittest.main()
