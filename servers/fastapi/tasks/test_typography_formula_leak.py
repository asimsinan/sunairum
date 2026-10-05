"""§IV Typography '- **Formula:** Georgia…' must not force formula_hero."""

from __future__ import annotations

import unittest


_PACK_WITH_TYPOGRAPHY = """\
## III. Visual Theme
- Primary: #0B3B6F

## IV. Typography System
- **Title family:** Georgia
- **Formula:** Georgia or Arial with clear monospaced spacing where useful
- **Emphasis:** Georgia or bold Arial

## IX. Content Outline

### P02: Why repair efficiency and workload equity belong together
- **Title:** Why repair efficiency and workload equity belong together
- **Core message:** Cost-only routing can leave driver workloads uneven.
- **Layout:** two_column_takeaway — left bottleneck, right equity gap
- **Content:**
  - VRPTW must respect customer service windows and vehicle capacity.
  - ALNS repair repeatedly examines insertion positions.
  - Cost-only routing can leave driver workloads uneven.
- **Visual job:** Join efficiency and equity before HERO.

## X. Speaker Notes
- **P02:** Spoken only
"""


class TypographyFormulaLeakTests(unittest.TestCase):
    def test_ix_field_ignores_typography_formula(self):
        from tasks.executor_modes import _ix_field, is_typography_formula_leak

        self.assertTrue(
            is_typography_formula_leak(
                "Georgia or Arial with clear monospaced spacing where useful"
            )
        )
        self.assertEqual("", _ix_field(_PACK_WITH_TYPOGRAPHY, "Formula"))
        self.assertIn(
            "two_column_takeaway",
            _ix_field(_PACK_WITH_TYPOGRAPHY, "Layout"),
        )

    def test_mode_not_formula_hero_from_typography(self):
        from tasks.executor_modes import resolve_executor_mode

        slide = {
            "slide": 2,
            "role": "content",
            "title": "Why repair efficiency and workload equity belong together",
            "content": {
                "BODY": (
                    "- VRPTW must respect windows.\n"
                    "- ALNS repair examines insertions.\n"
                    "- Cost-only routing leaves uneven workloads."
                )
            },
            "layout_intent": "two_column_takeaway — left bottleneck, right equity gap",
            "formula": "",
            "figure_id": "",
            "table_id": "",
        }
        mode = resolve_executor_mode(slide, pack=_PACK_WITH_TYPOGRAPHY)
        self.assertNotEqual("formula_hero", mode)

    def test_formula_fields_skip_typography_leak(self):
        from tasks.free_design_pipeline import _formula_fields_from_slide

        formula, terms, gloss, _tex = _formula_fields_from_slide(
            {"slide": 2, "role": "content", "formula": ""},
            _PACK_WITH_TYPOGRAPHY,
        )
        self.assertEqual("", formula)
        self.assertNotIn("Georgia", formula)
        self.assertNotIn("Georgia", gloss)

    def test_real_ix_formula_still_wins(self):
        from tasks.executor_modes import resolve_executor_mode
        from tasks.free_design_pipeline import _formula_fields_from_slide

        pack = _PACK_WITH_TYPOGRAPHY.replace(
            "- **Visual job:** Join efficiency and equity before HERO.",
            "- **Formula:** J = D + beta * CV\n"
            "- **Formula gloss:** Prefer balanced insertions.\n"
            "- **Visual job:** Join efficiency and equity before HERO.",
        )
        formula, _, gloss, _tex = _formula_fields_from_slide({"formula": ""}, pack)
        self.assertEqual("J = D + beta * CV", formula)
        self.assertEqual("Prefer balanced insertions.", gloss)
        slide = {
            "slide": 2,
            "role": "content",
            "formula": formula,
            "content": {"BODY": "- a\n- b\n- c"},
            "figure_id": "",
            "table_id": "",
        }
        self.assertEqual("formula_hero", resolve_executor_mode(slide, pack=pack))


if __name__ == "__main__":
    unittest.main()
