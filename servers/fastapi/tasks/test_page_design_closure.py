"""Page-design closure: deletion proof + Design SoT fidelity."""

from __future__ import annotations

import ast
import importlib.util
import re
import unittest
from pathlib import Path

TASKS = Path(__file__).resolve().parent

RETIRED_SYMBOLS = (
    "run_content_layout_harness",
    "align_stacked_card_column",
    "repack_stacked_card_text",
    "normalize_slide_typography",
    "fill_empty_right_column",
    "_rewrite_svg_fonts_to_lock",
    "paint_slide_svg",
    "paint_from_slide_dict",
    "_format_exclusive_regions_block",
    "exclusive_region_violations",
    "apply_mode_to_slide",
    "MODE_TO_RECIPE",
    "recipe_for_mode",
    "MODES_WITH_HARD_REGIONS",
    "widen_content_slide_title",
    "repair_title_plate_svg",
    "allocate_recipe",
    "choose_recipe",
    "RECIPE_NAMES",
    "bullets_to_cards",
    "_enrich_slide_layout_ir",
)

RETIRED_FILES = (
    "content_layout_harness.py",
    "slide_painter.py",
)


def _py_defs(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


class DeletionProofTests(unittest.TestCase):
    def test_retired_files_gone(self):
        for name in RETIRED_FILES:
            self.assertFalse((TASKS / name).exists(), name)
            self.assertIsNone(importlib.util.find_spec(f"tasks.{name[:-3]}"))

    def test_retired_symbols_not_defined(self):
        found: dict[str, str] = {}
        for path in TASKS.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            defs = _py_defs(path)
            for sym in RETIRED_SYMBOLS:
                if sym in defs:
                    found[sym] = path.name
        self.assertEqual({}, found, f"retired symbols still defined: {found}")

    def test_free_design_has_no_theme_apply_or_exclusive_prompt(self):
        text = (TASKS / "free_design_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("theme_agent.apply", text)
        self.assertNotIn("_theme_agent.apply", text)
        self.assertNotIn("Exclusive regions (HARD)", text)
        self.assertNotIn("content_layout_harness", text)
        self.assertNotIn("MODE_TO_RECIPE", text)


class DesignSotFidelityTests(unittest.TestCase):
    def test_confirm_ui_projects_same_token_shape(self):
        from tasks.design_sot import project_confirm_ui_to_design_sot, resolve_design_sot

        ui = {
            "color": {
                "source": "user",
                "palette": {
                    "primary": "#112233",
                    "accent": "#FF6600",
                    "background": "#FFFFFF",
                    "body_text": "#111111",
                },
            },
            "typography": {
                "heading": {"primary": "Playfair Display"},
                "body": {"primary": "IBM Plex Sans"},
                "body_size": 17,
            },
            "visual_style": "memphis",
            "density": "high",
            "mode": "pitch",
        }
        sot = project_confirm_ui_to_design_sot(ui)
        self.assertEqual("confirm_ui", sot["source"])
        self.assertEqual("#112233", sot["tokens"]["palette"]["primary"])
        self.assertEqual("Playfair Display", sot["tokens"]["typography"]["heading"]["primary"])
        self.assertIn("memphis", sot["brief"].casefold())

        resolved = resolve_design_sot(confirm_ui=ui)
        self.assertEqual("confirm_ui", resolved["source"])
        self.assertEqual("#FF6600", resolved["tokens"]["palette"]["accent"])

    def test_pack_wins_over_confirm_ui_when_available(self):
        from tasks.design_sot import resolve_design_sot

        resolved = resolve_design_sot(
            design_reference={
                "available": True,
                "pack_id": "attention-example",
                "brief": "pack brief",
                "tokens": {"palette": {"primary": "#0B3B6F"}, "typography": {}},
            },
            confirm_ui={
                "color": {"palette": {"primary": "#111111"}},
            },
        )
        self.assertEqual("pack", resolved["source"])
        self.assertEqual("#0B3B6F", resolved["tokens"]["palette"]["primary"])


class SoftCompositionTests(unittest.TestCase):
    def test_soft_pattern_does_not_stamp_recipe(self):
        from tasks.executor_modes import apply_soft_pattern

        slide = {
            "role": "content",
            "table_id": "src-table-001",
            "layout_recipe": "title_stack_cards",
        }
        apply_soft_pattern(slide)
        self.assertNotIn("layout_recipe", slide)
        self.assertTrue(str(slide.get("visualization") or ""))

    def test_diversity_fingerprints_differ_across_patterns(self):
        from tasks.free_design_pipeline import composition_fingerprint

        fps = []
        for i, pattern in enumerate(
            ("kpi_cards", "comparison_columns", "formula_band", "process_flow"),
            start=2,
        ):
            svg = (
                f'<svg viewBox="0 0 1280 720">'
                f'<rect x="{40 + i * 10}" y="{160 + i * 20}" width="{400 + i * 30}" '
                f'height="120" fill="#0B3B6F"/>'
                f'<text x="80" y="80">Slide {i} {pattern}</text></svg>'
            )
            fps.append(
                composition_fingerprint(
                    number=i,
                    mode=pattern,
                    recipe=pattern,
                    svg=svg,
                    color_palette={"primary": "#0B3B6F", "secondary_bg": "#F5F7FA"},
                )
            )
        self.assertEqual(4, len(set(fps)))

    def test_executor_prompt_has_no_exclusive_aabb_block(self):
        from tasks.free_design_pipeline import build_executor_slide_prompt

        prompt = build_executor_slide_prompt(
            slide={
                "slide": 3,
                "role": "content",
                "title": "Mechanism",
                "visualization": "annotated_schematic",
                "page_role": "Mechanism detail",
                "content": {"BODY": "- Claim A\n- Claim B"},
            },
            spec_lock_md="- **Title font:** Georgia\n- **Body font:** Arial\n",
            design_spec_md="## Theme\nInk-dominant academic pages.\n",
            prior_summary="",
        )
        low = prompt.casefold()
        self.assertNotIn("exclusive regions", low)
        self.assertNotIn("hard aabb", low)
        self.assertIn("georgia", low)


class FontDriftLockTests(unittest.TestCase):
    def test_lock_source_faces_are_not_drift(self):
        from tasks.free_design_pipeline import font_drift_vs_lock

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text font-family="Source Serif 4, serif">Title</text>'
            '<text font-family="Source Sans 3, sans-serif">Body</text>'
            "</svg>"
        )
        self.assertEqual(
            [],
            font_drift_vs_lock(
                svg, lock_title="Source Serif 4", lock_body="Source Sans 3"
            ),
        )

    def test_inter_is_drift_when_lock_is_georgia_arial(self):
        from tasks.free_design_pipeline import font_drift_vs_lock

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text font-family="Inter, sans-serif">Title</text>'
            "</svg>"
        )
        issues = font_drift_vs_lock(svg, lock_title="Georgia", lock_body="Arial")
        self.assertTrue(issues)
        self.assertIn("font_drift", issues[0])

    def test_source_sans_is_drift_when_not_in_lock(self):
        from tasks.free_design_pipeline import font_drift_vs_lock

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<text font-family="Source Sans 3, sans-serif">Body</text>'
            "</svg>"
        )
        issues = font_drift_vs_lock(svg, lock_title="Georgia", lock_body="Arial")
        self.assertTrue(issues)


class IntentHostInjectTests(unittest.TestCase):
    def test_ensure_hosts_and_table_inject(self):
        from tasks.intent_hosts import ensure_asset_hosts
        from tasks.slide_renderer import inject_table_host

        slide = {"table_id": "src-table-001", "role": "content"}
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<text x="80" y="80">Title</text></svg>'
        )
        hosted = ensure_asset_hosts(svg, slide)
        self.assertIn("data-sunairum-table-slot", hosted)
        payload = {
            "source_table_id": "src-table-001",
            "columns": [{"text": "A"}, {"text": "B"}],
            "rows": [[{"text": "1"}, {"text": "2"}]],
        }
        out, source = inject_table_host(
            hosted,
            slide,
            theme={"primary": "#0B3B6F"},
            resolve_table_payload=lambda _b, tid: payload if tid == "src-table-001" else None,
        )
        self.assertIn("data-sunairum-source-table-id", out)
        self.assertNotEqual("none", source)


if __name__ == "__main__":
    unittest.main()
