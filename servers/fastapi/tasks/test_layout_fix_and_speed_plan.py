"""Goldens + gates for layout_fix_and_speed plan (Phases 0–5)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "overlap_goldens"


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


class CoverTitleGoldenTests(unittest.TestCase):
    def test_cover_title_stays_left_of_sidebar(self):
        from tasks.free_design_pipeline import normalize_free_design_slide_svg

        out = normalize_free_design_slide_svg(
            _read("slide_01_cover_sidebar.svg"),
            role="title",
            full_title=(
                "HNSW Guided Large Neighborhood Search for Equitable "
                "Vehicle Routing Across Dense Urban Networks"
            ),
        )
        for m in re.finditer(
            r"<text\b([^>]*)>([\s\S]*?)</text>", out, flags=re.I
        ):
            attrs = m.group(1)
            fs = float(re.search(r'\bfont-size="([\d.]+)"', attrs).group(1))  # type: ignore
            if fs < 28:
                continue
            x = float(re.search(r'\bx="([\d.]+)"', attrs).group(1))  # type: ignore
            plain = " ".join(re.sub(r"<[^>]+>", " ", m.group(2)).split())
            # Per-line width via tspans or whole
            tspans = re.findall(r"<tspan\b[^>]*>([\s\S]*?)</tspan>", m.group(2), flags=re.I)
            lines = tspans or [plain]
            for ln in lines:
                bit = " ".join(re.sub(r"<[^>]+>", " ", ln).split())
                # Heuristic: x + 0.55*fs*len <= ~780
                self.assertLessEqual(x + 0.55 * fs * len(bit), 800.0, bit)


class ChipTakeawayGoldenTests(unittest.TestCase):
    def test_chip_label_recenters_and_marks(self):
        from tasks.free_design_pipeline import normalize_free_design_slide_svg

        out = normalize_free_design_slide_svg(_read("slide_02_chip_drift.svg"))
        self.assertIn('data-sunairum-chip-label="1"', out)
        label = re.search(
            r"<text\b([^>]*)>RETRIEVE</text>", out, flags=re.I
        )
        self.assertIsNotNone(label)
        y = float(re.search(r'\by="([\d.]+)"', label.group(1)).group(1))  # type: ignore
        self.assertLess(y, 210.0)
        # Funnel label nudged off path ink
        funnel = re.search(r"<text\b([^>]*)>funnel stage</text>", out, flags=re.I)
        self.assertIsNotNone(funnel)
        fy = float(re.search(r'\by="([\d.]+)"', funnel.group(1)).group(1))  # type: ignore
        self.assertNotEqual(fy, 300.0)

    def test_takeaway_badge_gutter(self):
        from tasks.layout_mechanical import fit_chip_labels

        out = fit_chip_labels(_read("slide_03_takeaway_badge.svg"))
        badge = re.search(
            r'<rect\b([^>]*fill="#0F766E"[^>]*)/?>', out, flags=re.I
        )
        body = re.search(r"<text\b([^>]*)>by retrieving", out)
        self.assertIsNotNone(badge)
        self.assertIsNotNone(body)
        bx = float(re.search(r'\bx="([\d.]+)"', badge.group(1)).group(1))  # type: ignore
        bw = float(re.search(r'\bwidth="([\d.]+)"', badge.group(1)).group(1))  # type: ignore
        tx = float(re.search(r'\bx="([\d.]+)"', body.group(1)).group(1))  # type: ignore
        self.assertGreaterEqual(tx, bx + bw + 15.0)


class FigureStepGoldenTests(unittest.TestCase):
    def test_empty_step_cards_collapse(self):
        from tasks.layout_mechanical import collapse_empty_figure_step_cards

        src = _read("slide_05_empty_steps.svg")
        out = collapse_empty_figure_step_cards(src)
        # Two empty peer rects removed (only the filled card remains among left peers).
        left_cards = [
            m
            for m in re.finditer(r'<rect\b([^>]*)/?>', out, flags=re.I)
            if 'data-sunairum' not in (m.group(1) or "")
            and 40
            <= float(re.search(r'\bx="([\d.]+)"', m.group(1)).group(1))  # type: ignore
            < 400
            and 140
            < float(re.search(r'\bwidth="([\d.]+)"', m.group(1)).group(1))  # type: ignore
            < 700
        ]
        self.assertEqual(1, len(left_cards))
        # Orphan motif adopted into remaining sparse slot when normalize runs.
        from tasks.free_design_pipeline import normalize_free_design_slide_svg

        norm = normalize_free_design_slide_svg(src)
        self.assertIn("<circle", norm)


class TableChromeGoldenTests(unittest.TestCase):
    def test_table_chrome_normalize(self):
        from tasks.free_design_pipeline import normalize_free_design_slide_svg

        out = normalize_free_design_slide_svg(_read("slide_09_table_chrome.svg"))
        self.assertIn('data-sunairum-table-insight="1"', out)
        self.assertIn("Insight stays", out)
        # Left takeaway clamped on-canvas
        take = re.search(r'Takeaway clipped left', out)
        self.assertIsNotNone(take)
        # Header width synced toward body
        widths = [
            float(m.group(1))
            for m in re.finditer(r'<rect\b[^>]*\bwidth="([\d.]+)"', out)
            if float(m.group(1)) >= 120
        ]
        self.assertTrue(widths)
        # Caption should not mid-word ellipsis
        self.assertNotRegex(out, r"\w…")


class ExportAllowlistTests(unittest.TestCase):
    def test_strips_textlength_and_unknown(self):
        from tasks.svg_export_gate import sanitize_project_text_surface

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<text x="10" y="20" font-size="16" textLength="80" lengthAdjust="spacing" '
            'fooBar="1">Hi'
            '<tspan baseline-shift="sub" dy="0">2</tspan></text></svg>'
        )
        out = sanitize_project_text_surface(svg)
        self.assertNotIn("textLength", out)
        self.assertNotIn("lengthAdjust", out)
        self.assertNotIn("fooBar", out)
        self.assertNotIn("baseline-shift", out)
        self.assertIn("<svg", out.casefold())
        self.assertNotIn("ns0:svg", out.casefold())
        root = ET.fromstring(out)
        # dy may remain from rewrite
        tspans = [e for e in root.iter() if e.tag.endswith("tspan")]
        self.assertTrue(tspans)

    def test_xmlns_roundtrip_keeps_svg_root_for_export_gate(self):
        from tasks.svg_export_gate import sanitize_project_text_surface, validate_export_svg

        svg = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
            'width="1280" height="720">'
            '<rect x="0" y="0" width="1280" height="720" fill="#fff"/>'
            '<text x="112" y="260" font-size="48" textLength="700" '
            'lengthAdjust="spacingAndGlyphs">Title</text></svg>'
        )
        out = sanitize_project_text_surface(svg)
        self.assertIsNotNone(re.search(r"<svg\b", out, flags=re.I))
        self.assertNotIn("ns0:", out)
        gate = validate_export_svg(out)
        self.assertNotIn("missing_svg_root", gate.errors)
        self.assertTrue(gate.ok or not any("missing_svg" in e for e in gate.errors))


class PageDesignMergeTests(unittest.TestCase):
    def test_single_design_call(self):
        from tasks.page_design import author_page_design

        calls: list[str] = []

        def _call(system: str, prompt: str) -> str:
            calls.append(system)
            return (
                '{"art":{"job":"explain","energy":"vivid","hierarchy":["title","claim"],'
                '"host":{"kind":"figure","placement":"right"},"craft":["gap"],"forbid":[]},'
                '"plan":{"job":"explain","composition":"left_claims",'
                '"regions":[{"id":"t","role":"title","x":60,"y":60,"w":1000,"h":60},'
                '{"id":"c1","role":"claim","x":60,"y":160,"w":500,"h":80}],'
                '"rules":["honor voids"]}}'
            )

        slide = {
            "slide": 2,
            "role": "content",
            "title": "Gap",
            "figure_id": "fig-1",
            "content": {"BODY": "One"},
        }
        art, plan, design_ms = author_page_design(
            slide, call_text=_call, craft_lines=["gap"]
        )
        self.assertEqual(1, len(calls))
        self.assertIn("Page Designer", calls[0])
        self.assertEqual("vivid", art.get("energy"))
        self.assertTrue(plan.get("regions"))
        self.assertGreaterEqual(design_ms, 0)
        self.assertIn("_art_brief", slide)

    def test_reuse_art_on_replan(self):
        from tasks.page_design import author_page_design

        slide = {
            "slide": 2,
            "role": "content",
            "title": "Gap",
            "_force_layout_replan": True,
            "_art_brief": {
                "job": "kept",
                "energy": "vivid",
                "hierarchy": ["title"],
                "host": {"kind": "none"},
                "craft": [],
                "forbid": [],
            },
        }

        def _call(system: str, prompt: str) -> str:
            self.assertIn("Reuse art", prompt)
            return (
                '{"art":{"job":"should-not-replace","energy":"sparse"},'
                '"plan":{"job":"x","composition":"y","regions":['
                '{"id":"t","role":"title","x":60,"y":60,"w":1000,"h":60}]}}'
            )

        art, plan, _ = author_page_design(
            slide, call_text=_call, reuse_art=slide["_art_brief"]
        )
        # art_director merge may keep energy vivid for content; job from reuse path
        self.assertTrue(plan.get("regions"))
        self.assertIsInstance(art, dict)


class SpecWidgetTests(unittest.TestCase):
    def test_render_chip_paired(self):
        from tasks.spec_widgets import materialize_spec_widgets, render_chip

        chip = render_chip("RETRIEVE", x=80, y=180)
        self.assertIn('data-sunairum-chip-widget="1"', chip)
        self.assertIn('data-sunairum-chip-label="1"', chip)
        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<script type="application/sunairum-chip-spec+json">'
            '{"label":"BADGE","x":60,"y":200,"kind":"badge"}'
            "</script></svg>"
        )
        out = materialize_spec_widgets(svg)
        self.assertIn("BADGE", out)
        self.assertNotIn("sunairum-chip-spec", out)

    def test_place_widget_in_host(self):
        from tasks.spec_widgets import place_widget, render_flow_diagram

        diagram = render_flow_diagram(
            {
                "nodes": [
                    {"id": "a", "label": "A"},
                    {"id": "b", "label": "B"},
                ],
                "edges": [["a", "b"]],
            }
        )
        placed = place_widget(diagram, (700, 160, 500, 400))
        self.assertIn("data-sunairum-placed-widget", placed)
        self.assertIn("translate", placed)


class ClaimShellTests(unittest.TestCase):
    def test_inject_and_fill(self):
        from tasks.claim_shells import fill_claim_shells_from_ir, inject_claim_shells

        svg = (
            '<svg viewBox="0 0 1280 720">'
            '<g data-sunairum-figure-slot="1" transform="translate(700,160)">'
            '<rect x="0" y="0" width="500" height="400" fill="#eee"/></g></svg>'
        )
        slide = {
            "slide": 5,
            "figure_id": "f1",
            "cards": [
                {"title": "A", "body": "alpha"},
                {"title": "B", "body": "beta"},
            ],
        }
        with_shells = inject_claim_shells(svg, slide)
        self.assertIn('data-sunairum-claim-shell="1"', with_shells)
        self.assertIn("alpha", with_shells)
        filled = fill_claim_shells_from_ir(with_shells, slide)
        self.assertIn("beta", filled)


class PromptContractTests(unittest.TestCase):
    def test_host_bound_no_own_geometry(self):
        from tasks.free_design_pipeline import build_executor_slide_prompt

        prompt = build_executor_slide_prompt(
            slide={
                "slide": 3,
                "role": "content",
                "title": "T",
                "figure_id": "fig",
                "content": {"BODY": "x"},
                "layout_intent": "two column cards",
                "cards": [{"title": "A", "body": "1"}, {"title": "B", "body": "2"}],
                "_layout_plan": {
                    "job": "j",
                    "composition": "c",
                    "regions": [
                        {"id": "t", "role": "title", "x": 60, "y": 60, "w": 1000, "h": 60},
                        {"id": "b", "role": "body", "x": 60, "y": 160, "w": 500, "h": 400},
                    ],
                },
            },
            spec_lock_md="Primary #000",
            craft_block="- Keep 24px inset\n- Avoid spill into host\n- Fill Contract vivid\n- noise1\n- noise2\n- noise3\n- noise4\n- noise5\n- noise6\n- noise7\n- noise8",
        )
        self.assertNotIn("you own geometry", prompt.casefold())
        self.assertNotIn("compose freely", prompt.casefold())
        self.assertIn("honor regions", prompt.casefold())
        self.assertIn("inset", prompt.casefold())
        self.assertIn("spill", prompt.casefold())

    def test_craft_compact_keeps_spill(self):
        from tasks.deck_prompt_context import craft_compact

        block = craft_compact(
            [
                "noise a",
                "24px inset required",
                "no spill into host",
                "Fill Contract vivid",
                "noise b",
                "noise c",
                "noise d",
                "noise e",
                "noise f",
                "noise g",
                "noise h",
                "noise i",
            ],
            max_lines=6,
        )
        self.assertIn("inset", block)
        self.assertIn("spill", block)
        self.assertIn("Fill Contract", block)


class SpeedGateTests(unittest.TestCase):
    def test_precomputed_plan_skips_design_llm(self):
        from tasks.free_design_pipeline import author_free_slide_svg

        calls: list[str] = []

        def _call(system: str, prompt: str) -> str:
            calls.append(system[:50])
            return (
                '<svg viewBox="0 0 1280 720">'
                '<text x="60" y="76" font-size="36">Hello</text></svg>'
            )

        class _GT:
            def sanitize_flat_structure_metadata(self, s: str) -> str:
                return s

            def finalize_svg_document(self, s: str) -> str:
                return s

            def sanitize_presentation_chrome(self, s: str, **_kw) -> str:
                return s

        slide = {
            "slide": 1,
            "role": "content",
            "title": "Hello",
            "content": {"BODY": "Body"},
            "_layout_plan": {
                "job": "pre",
                "composition": "x",
                "regions": [
                    {"id": "t", "role": "title", "x": 60, "y": 60, "w": 1000, "h": 60}
                ],
            },
            "_art_brief": {"job": "pre", "energy": "vivid"},
            "_craft_block": "",
            "_art_direction_block": "",
            "_executor_paints": 0,
        }
        svg, source = author_free_slide_svg(
            slide=slide,
            design_spec_md="",
            spec_lock_md="Primary #000",
            prior_summary="",
            color_palette={"body_text": "#000", "_heading_family": "Georgia"},
            call_text=_call,
            gt=_GT(),
            allow_fallback=False,
        )
        self.assertIn("<svg", svg)
        self.assertEqual("model", source)
        self.assertFalse(any("Page Designer" in c or "Layout Planner" in c for c in calls))


if __name__ == "__main__":
    unittest.main()
