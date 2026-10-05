"""Formula plate pack fields, prompts, and deterministic fitter."""

from __future__ import annotations

import re
import unittest


class FormulaPlateParseTests(unittest.TestCase):
    def test_parse_formula_fields_from_section_ix(self):
        from tasks.strategist_agent import parse_section_ix_slides

        md = """
## IX. Content Outline
### P01: Cover
- **Title:** Paper
- **Content:** Title plate
### P08: Objective
- **Title:** Insertion Rule
- **Core message:** Equity weights steer insertion
- **Layout:** Formula plate left; decision panel right
- **Content:**
  - Cost-only vs equity-guided modes
- **Formula:** Delta J = Delta distance + beta * Delta equity + gamma * Delta balance
- **Formula terms:** beta=equity weight; gamma=balance weight
- **Formula gloss:** Choose the feasible insertion with the smallest objective change.
### P09: Thanks
- **Title:** Thank you
- **Content:** Thanks
"""
        slides = parse_section_ix_slides(md)
        by_num = {int(s["slide"]): s for s in slides}
        self.assertEqual(
            "Delta J = Delta distance + beta * Delta equity + gamma * Delta balance",
            by_num[8]["formula"],
        )
        self.assertIn("beta=equity weight", by_num[8]["formula_terms"])
        self.assertTrue(by_num[8]["formula_gloss"].startswith("Choose the feasible"))


class FormulaPlatePromptTests(unittest.TestCase):
    def test_pack_formula_sets_formula_pattern_and_prompt_block(self):
        from tasks.free_design_pipeline import build_executor_slide_prompt

        design = """
## IX. Content Outline
### P08: Objective
- **Title:** The Insertion Rule Can Trade Cost for Balance
- **Core message:** Equity weights steer insertion
- **Layout:** Formula plate left; modes right
- **Content:**
  - Cost-only mode
  - Equity-guided mode
- **Formula:** Delta J = Delta distance + beta * Delta equity + gamma * Delta balance
- **Formula terms:** beta=equity weight; gamma=balance weight
- **Formula gloss:** Choose the feasible insertion with the smallest objective change.
- **Visual job:** Show tunable equity policy
### P09: Thanks
- **Title:** Thank you
"""
        slide = {
            "slide": 8,
            "role": "content",
            "title": "The Insertion Rule Can Trade Cost for Balance",
            "content": {"BODY": "Cost-only vs equity-guided"},
            "formula": "Delta J = Delta distance + beta * Delta equity + gamma * Delta balance",
            "formula_terms": "beta=equity weight; gamma=balance weight",
            "formula_gloss": "Choose the feasible insertion with the smallest objective change.",
            "layout_intent": "Formula plate left",
            "figure_id": "",
            "table_id": "",
        }
        prompt = build_executor_slide_prompt(
            slide=slide,
            spec_lock_md="lock",
            design_spec_md=design,
        )
        self.assertIn(
            slide.get("executor_mode") or slide.get("visualization") or "",
            {"formula_hero", "formula_band"},
        )
        self.assertIn("## Formula host", prompt)
        self.assertIn(
            "Delta J = Delta distance + beta * Delta equity + gamma * Delta balance",
            prompt,
        )
        self.assertIn("beta=equity weight", prompt)
        self.assertIn("formula-band", prompt.casefold())


class FormulaPlateFitTests(unittest.TestCase):
    def test_fit_restyles_consolas_wrap_into_cambria_plate(self):
        from tasks.formula_plate import fit_formula_plate

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="#fff"/>'
            '<text x="82" y="253" font-family="Consolas, monospace" font-size="16.5" '
            'font-weight="700" fill="#0F172A">Delta J = Delta distance</text>'
            '<text x="82" y="272.8" font-family="Consolas, monospace" font-size="16.5" '
            'font-weight="700" fill="#0F172A">'
            "+ beta * Delta equity + gamma * Delta balance</text>"
            "</svg>"
        )
        out = fit_formula_plate(
            svg,
            formula=(
                "Delta J = Delta distance + beta * Delta equity + gamma * Delta balance"
            ),
            terms="beta=equity weight; gamma=balance weight",
            gloss="Choose the feasible insertion with the smallest objective change.",
            color_palette={"primary": "#1E3A8A", "secondary_bg": "#F8FAFC"},
        )
        self.assertNotIn("Consolas", out)
        self.assertIn('data-sunairum-formula-plate="1"', out)
        self.assertIn('id="formula-band"', out)
        self.assertIn("EQUATION", out)
        self.assertIn('data-sunairum-formula-term="1"', out)
        self.assertIn("β = equity weight", out)
        self.assertIn("Choose the feasible insertion", out)
        # Attention band: image / flat math / formula marker (no nested MathJax publish).
        self.assertTrue(
            "data-sunairum-formula-math" in out
            or 'data-sunairum-formula="1"' in out
            or "<image" in out.casefold()
        )
        self.assertNotIn('data-pptx-replace-with="formula"', out)


if __name__ == "__main__":
    unittest.main()
