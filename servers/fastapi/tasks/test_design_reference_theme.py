"""Template design tokens are the deck SoT when a gallery pack is selected."""

from __future__ import annotations

import unittest

from tasks.design_reference import (
    apply_tokens_to_result,
    extract_design_reference,
    normalize_palette,
)
from tasks import theme_agent
from tasks.strategist_agent import project_flat_spec_lock, validate_design_spec_palette


ATTENTION = "ppt169_attention_is_all_you_need"


class DesignReferenceTokensTests(unittest.TestCase):
    def test_attention_palette_aliases(self):
        ref = extract_design_reference(ATTENTION)
        self.assertTrue(ref.get("available"), ref)
        tokens = ref["tokens"]
        palette = tokens["palette"]
        self.assertEqual(palette.get("primary"), "#1A365D")
        self.assertEqual(palette.get("accent"), "#3182CE")
        self.assertEqual(palette.get("secondary_bg"), "#F5F7FA")
        self.assertEqual(palette.get("body_text"), "#1A202C")
        self.assertEqual(palette.get("border"), "#E2E8F0")
        # Alias round-trip
        normalized = normalize_palette(ref["colors"])
        self.assertEqual(normalized["primary"], "#1A365D")
        self.assertEqual(normalized["background"], "#FFFFFF")
        self.assertEqual(normalized["body_text"], "#1A202C")

    def test_attention_typography_and_icons_and_mood(self):
        tokens = extract_design_reference(ATTENTION)["tokens"]
        typo = tokens["typography"]
        # A reference deck's Georgia/Arial resolve to the families we ship and
        # embed: an Office face name would be re-resolved by the reader's
        # PowerPoint and re-wrap the text. See tasks.font_policy.
        from tasks.font_policy import EMBEDDABLE_FAMILIES

        self.assertEqual(typo["heading"]["primary"], "Source Serif 4")
        self.assertEqual(typo["body"]["primary"], "Source Sans 3")
        self.assertIn(typo["code_family"], EMBEDDABLE_FAMILIES)
        self.assertGreaterEqual(float(tokens["type_scale"]["body"]), 18)
        icons = tokens["icons"]
        self.assertEqual(icons["library"], "tabler-outline")
        self.assertEqual(float(icons["stroke_width"]), 2.0)
        self.assertIn("trophy", icons["inventory"])
        mood = tokens["image_mood"]
        self.assertEqual(mood.get("image_rendering"), "blueprint")
        self.assertEqual(mood.get("image_palette"), "cool-corporate")

    def test_attention_table_formula_chart_guidelines(self):
        tokens = extract_design_reference(ATTENTION)["tokens"]
        table = tokens["table"]
        self.assertIn("basic_table", table["preferred_patterns"])
        self.assertEqual(table["header_fill"], "#1A365D")
        # Fill Contract: zebra/surface prefer accent_tint over pale secondary_bg.
        self.assertEqual(table["zebra"], "#EBF4FB")
        self.assertEqual(table["grid_stroke"], "#E2E8F0")
        formula = tokens["formula"]
        self.assertEqual(formula["ink"], "#1A365D")
        self.assertEqual(formula.get("medium"), "png_band")
        self.assertEqual(formula.get("surface"), "#EBF4FB")
        chart = tokens["chart"]
        self.assertIn("kpi_cards", chart["preferred_patterns"])
        self.assertEqual(chart["series"]["primary"], "#1A365D")
        self.assertIn("blueprint", chart.get("rendering_mood") or "")
        chrome = tokens["chrome"]
        self.assertEqual(float(chrome["card_rx"]), 12.0)
        self.assertIn("vertical", str(chrome["header_rhythm"]).casefold())
        footer = str(chrome.get("footer_rhythm") or "").casefold()
        self.assertIn("page number", footer)
        self.assertIn("nothing else", footer)
        self.assertNotIn("short tag", footer)
        self.assertEqual(
            (tokens.get("method") or {}).get("method_id"), "academic-blueprint"
        )

    def test_brief_is_authoritative_not_inspiration(self):
        brief = extract_design_reference(ATTENTION)["brief"]
        self.assertIn("AUTHORITATIVE", brief.upper())
        self.assertNotIn("STYLE INSPIRATION only", brief)
        self.assertIn("Footer chrome:", brief)
        self.assertIn("page number only", brief.casefold())
        self.assertNotIn("short tag", brief.casefold())
        self.assertNotIn("project tag in tertiary", brief.casefold())

    def test_theme_resolve_authored_pack(self):
        ref = extract_design_reference(ATTENTION)
        result = apply_tokens_to_result({}, ref["tokens"])
        calls = []

        def _fake_author(*_a, **_k):
            calls.append(1)
            raise AssertionError("theme author must not run for pack authority")

        # authored=True must short-circuit before author()
        theme = theme_agent.resolve(
            {"palette_source": "pack", "topic": "t"},
            pack_palette=result["color"]["palette"],
            pack_typography=result["typography"],
            authored=True,
            call_json=_fake_author,
        )
        self.assertEqual(theme.authority, "pack")
        self.assertEqual(theme.palette["primary"], "#1A365D")
        self.assertEqual(theme.palette["accent"], "#3182CE")
        self.assertEqual(calls, [])

    def test_adapters_match_attention(self):
        ref = extract_design_reference(ATTENTION)
        tokens = ref["tokens"]
        result = apply_tokens_to_result({}, tokens)
        theme = theme_agent.from_pack(result["color"]["palette"], result["typography"])
        painter = theme_agent.as_painter_theme(theme, tokens)
        self.assertEqual(painter["primary"], "#1A365D")
        self.assertEqual(painter["border"], "#E2E8F0")
        self.assertNotEqual(painter.get("border"), "#D5DEE8")
        # Fill Contract: chrome/surface prefer accent_tint.
        self.assertEqual(painter["surface"], "#EBF4FB")
        table = theme_agent.as_table_theme(theme, tokens)
        self.assertEqual(table["header_fill"], "#1A365D")
        self.assertEqual(table["zebra"], "#EBF4FB")
        self.assertEqual(table["border"], "#E2E8F0")
        formula = theme_agent.as_formula_theme(theme, tokens)
        self.assertEqual(formula["ink"], "#1A365D")
        self.assertEqual(formula["surface"], "#EBF4FB")
        asset = theme_agent.as_asset_style(theme, tokens)
        self.assertEqual(asset.primary, "#1A365D")
        self.assertEqual(asset.accent, "#3182CE")

    def test_spec_lock_emits_pack_rows(self):
        ref = extract_design_reference(ATTENTION)
        result = apply_tokens_to_result(
            {
                "audience": "researchers",
                "core_message": "attention",
                "primary_language": "en",
            },
            ref["tokens"],
        )
        lock = project_flat_spec_lock(
            result=result, design_spec_md="", page_count=4
        )
        self.assertIn("- primary: #1A365D", lock)
        self.assertIn("- accent: #3182CE", lock)
        self.assertIn("- secondary_bg: #F5F7FA", lock)
        self.assertIn("- text: #1A202C", lock)
        self.assertIn("- border: #E2E8F0", lock)
        self.assertIn("- image_rendering: blueprint", lock)
        self.assertIn("- image_palette: cool-corporate", lock)
        self.assertIn('- title_family: "Source Serif 4"', lock)
        self.assertIn('- body_family: "Source Sans 3"', lock)
        for office_face in ("Georgia", "Arial", "Consolas", "Helvetica"):
            self.assertNotIn(office_face, lock)
        self.assertIn("- library: tabler-outline", lock)
        self.assertIn("- stroke_width: 2", lock)
        self.assertIn("kpi_cards", lock)
        self.assertRegex(lock, r"- density: \w+")

    def test_palette_drift_detects_mismatch(self):
        result = apply_tokens_to_result({}, extract_design_reference(ATTENTION)["tokens"])
        bad_spec = "Primary color is #1E3A8A for headings.\nAccent #F59E0B."
        errors = validate_design_spec_palette(bad_spec, result)
        self.assertTrue(any("primary" in e for e in errors), errors)

    def test_density_ignores_incidental_tight_prose(self):
        from tasks.design_reference import _density_from_spec

        # Attention image prompts say "tighter undulation" — must not force high.
        self.assertEqual(
            _density_from_spec(
                "Use tighter undulation on blueprint waves; medium-dense briefing.",
                {"type_scale": {"body": 18}},
            ),
            "medium",
        )
        self.assertEqual(
            _density_from_spec(
                "Deck density: high with tight spacing.",
                {"type_scale": {"body": 18}},
            ),
            "high",
        )
        tokens = extract_design_reference(ATTENTION)["tokens"]
        self.assertEqual((tokens.get("layout") or {}).get("density"), "medium")




if __name__ == "__main__":
    unittest.main()
