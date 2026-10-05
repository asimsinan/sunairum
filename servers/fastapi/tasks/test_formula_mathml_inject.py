"""MathML formula host injection (editable OMML path)."""

from __future__ import annotations

import unittest


class FormulaMathmlInjectTests(unittest.TestCase):
    def test_inject_mathml_not_png(self):
        from tasks.formula_katex import katex_available
        from tasks.html_pipeline import inject_formula_into_html

        if not katex_available():
            self.skipTest("node/mathjax unavailable")

        html = (
            '<section class="slide">'
            '<div data-pptx="formula" data-formula-id="f1" '
            'style="width:400px;height:120px;"></div></section>'
        )
        slide = {
            "formula": "C_0 = beta * x",
            "formula_tex": r"C_{0}=\beta x",
            "formula_id": "f1",
        }
        out, meta = inject_formula_into_html(
            html,
            storage_dir="/tmp",
            slide=slide,
            color_palette={"primary": "#1A365D"},
        )
        self.assertEqual(meta.get("status"), "filled")
        self.assertTrue(meta.get("has_mathml"))
        self.assertFalse(meta.get("has_png"))
        self.assertIn("<math", out.casefold())
        self.assertNotIn("<img", out.casefold())
        self.assertNotIn("<svg", out.casefold())


if __name__ == "__main__":
    unittest.main()
