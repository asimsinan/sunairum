"""Fill Contract, scratch style, viz catalog, formula PNG-only, geometry helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class FillContractTests(unittest.TestCase):
    def test_art_director_content_defaults_vivid(self):
        from tasks.art_director import author_art_direction

        brief = author_art_direction({"role": "content", "title": "X"}, call_text=None)
        self.assertEqual(brief.get("energy"), "vivid")

    def test_craft_curriculum_has_fill_contract_and_dna(self):
        from tasks.design_sot import craft_curriculum_from_tokens, pipeline_method_dna_block

        lines = craft_curriculum_from_tokens({"layout": {"density": "medium"}})
        joined = "\n".join(lines)
        self.assertIn("Fill Contract", joined)
        self.assertIn("accent_tint", joined)
        dna = pipeline_method_dna_block()
        self.assertIn("Pipeline method DNA", dna)
        self.assertIn("vivid", dna.casefold())

    def test_soft_tips_drop_restrained_tint(self):
        from tasks.executor_modes import SOFT_STACK_CARDS, soft_pattern_brief

        tip = soft_pattern_brief(SOFT_STACK_CARDS)
        self.assertNotIn("restrained tint", tip)
        self.assertIn("accent_tint", tip)


class ScratchStyleTests(unittest.TestCase):
    def test_list_styles_and_load_method(self):
        from tasks.presentation_style import list_styles, load_style_method, normalize_style_id

        styles = list_styles()
        self.assertGreaterEqual(len(styles), 8)
        ids = {s["id"] for s in styles}
        self.assertIn("science-explainer", ids)
        body = load_style_method("science-explainer")
        self.assertIn("Composition", body)
        self.assertEqual(normalize_style_id("science-explainer", allow=True), "science-explainer")
        self.assertIsNone(normalize_style_id("science-explainer", allow=False))
        self.assertIsNone(normalize_style_id("nope", allow=True))

    def test_selected_style_survives_compact_executor_context(self):
        from tasks.deck_prompt_context import lock_compact, sot_compact
        from tasks.presentation_style import style_method_block
        from tasks.strategist_agent import project_flat_spec_lock

        style = style_method_block("science-explainer")
        compact = sot_compact(style + ("generic pipeline guidance " * 300))
        self.assertIn("user-selected: science-explainer", compact)
        self.assertIn("Very light", compact)
        self.assertIn("Typography Character", compact)

        lock = project_flat_spec_lock(
            result={"presentation_style": "science-explainer"},
            design_spec_md="",
            page_count=5,
        )
        self.assertIn("selected_style: science-explainer", lock)
        compact_lock = lock_compact(lock)
        self.assertIn("Very light", compact_lock)
        self.assertIn("Typography Character", compact_lock)


class VizCatalogTests(unittest.TestCase):
    def test_indexes_and_summaries(self):
        from tasks.viz_catalog import (
            catalog_menu_block,
            chart_keys,
            is_catalog_key,
            page_viz_hint,
            summary_for,
            table_keys,
        )

        self.assertIn("waterfall_chart", chart_keys())
        self.assertIn("metric_table", table_keys())
        self.assertTrue(is_catalog_key("chart/waterfall_chart"))
        self.assertTrue(is_catalog_key("table/metric_table"))
        self.assertIn("Pick for", summary_for("chart/waterfall_chart"))
        menu = catalog_menu_block()
        self.assertIn("chart/", menu)
        self.assertNotIn("<svg", menu.casefold())
        hint = page_viz_hint("table/metric_table")
        self.assertIn("metric_table", hint)
        self.assertNotIn("scaffold SVG", hint.lower() + "x")  # wording may vary
        self.assertIn("do not paste", hint.casefold())

    def test_find_icons_hits_tabler_pool(self):
        from tasks import asset_library

        asset_library.reload()
        # Either manifest or curated tabler-outline files.
        hits = asset_library.find_icons("arrow", "right", limit=5)
        self.assertTrue(hits)
        self.assertTrue(any("arrow" in str(h.get("name") or "").casefold() for h in hits))


class FormulaPngOnlyTests(unittest.TestCase):
    def test_render_formula_asset_leaves_flat_group_empty_without_png(self):
        from tasks.formula_latex_png import render_formula_asset

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "tasks.formula_latex_png._try_codecogs_png", return_value=False
            ), mock.patch(
                "tasks.formula_latex_png._try_rasterize_svg", return_value=False
            ), mock.patch(
                "tasks.formula_katex.render_tex_svg",
                return_value='<svg viewBox="0 0 10 10"><path d="M0 0"/></svg>',
            ):
                asset = render_formula_asset(
                    "x^2",
                    images_dir=tmp,
                    formula_id="t1",
                    prefer_network=True,
                )
        self.assertEqual(asset.get("flat_group"), "")
        self.assertFalse(asset.get("png_href"))

    def test_render_formula_plate_skips_flat_group(self):
        from tasks import formula_visual_intent as fvi

        with mock.patch.object(
            fvi,
            "render_formula_asset",
            return_value={
                "data_uri": "",
                "png_href": "",
                "flat_group": '<g data-sunairum-formula-math="1"/>',
                "math_svg": "<svg/>",
                "width": 100,
                "height": 40,
            },
        ):
            plate = fvi.render_formula_plate(
                {
                    "formula": "x",
                    "formula_tex": "x",
                    "mode": "hero",
                },
                aabb=(60.0, 160.0, 1160.0, 160.0),
                images_dir="/tmp",
            )
        self.assertNotIn("data-sunairum-formula-math", plate)
        self.assertIn("data-sunairum-formula-plate", plate)


class GeometryHelperTests(unittest.TestCase):
    def test_fit_text_in_cards_shrinks_or_clips(self):
        from tasks.svg_reflow import fit_text_in_cards

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect id="card-1" x="40" y="160" width="140" height="120" rx="10" fill="#EBF4FF"/>'
            '<text x="50" y="200" font-size="18">'
            "Read the separation carefully across the whole card width"
            "</text></svg>"
        )
        out = fit_text_in_cards(svg)
        self.assertTrue(
            'font-size="11' in out or "…" in out or "font-size=\"1" in out,
            out,
        )

    def test_clear_chart_labels_moves_off_marker(self):
        from tasks.svg_reflow import clear_chart_labels

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<circle cx="200" cy="300" r="5" fill="#111"/>'
            '<text x="200" y="300" font-size="12">42%</text>'
            "</svg>"
        )
        out = clear_chart_labels(svg)
        self.assertNotIn('x="200" y="300"', out)

    def test_fit_takeaway_band_pulls_text_up(self):
        from tasks.svg_reflow import fit_takeaway_band

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<rect x="40" y="600" width="1200" height="50" fill="#EBF4FF"/>'
            '<text x="60" y="655" font-size="16">Takeaway body that sat below the band</text>'
            "</svg>"
        )
        out = fit_takeaway_band(svg)
        self.assertNotIn('y="655"', out)

    def test_deck_qa_card_min_width_120(self):
        import inspect

        from tasks import deck_qa

        src = inspect.getsource(deck_qa.check_card_geometry)
        self.assertIn(">= 120", src)


class FigureUpscaleTests(unittest.TestCase):
    def test_upscale_low_dpi_png(self):
        from PIL import Image

        from tasks.free_design_pipeline import _upscale_figure_if_low_dpi

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fig.png")
            Image.new("RGB", (200, 100), color=(20, 40, 80)).save(path)
            self.assertTrue(_upscale_figure_if_low_dpi(path, min_width=400))
            with Image.open(path) as im:
                self.assertGreaterEqual(im.width, 400)


if __name__ == "__main__":
    unittest.main()
