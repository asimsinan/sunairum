"""Math AST dual-emit: KaTeX preview + OMML native formula."""

from __future__ import annotations

import html
import json
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "layout_regressions"


class MathAstTests(unittest.TestCase):
    def test_ascii_to_ast_subscript_eq(self):
        from tasks.math_ast import ascii_to_ast, ast_to_omml, ast_to_tex

        ast = ascii_to_ast("C_0 = beta * Equity")
        self.assertIsNotNone(ast)
        self.assertEqual(ast["type"], "eq")
        self.assertEqual(ast["lhs"]["type"], "sub")
        tex = ast_to_tex(ast)
        self.assertIn("C", tex)
        self.assertIn("0", tex)
        self.assertIn("\\beta", tex)
        omml = ast_to_omml(ast)
        self.assertIn("<m:oMath>", omml)
        self.assertIn("<m:sSub>", omml)
        self.assertIn(">C<", omml)
        self.assertIn(">0<", omml)
        self.assertIn("β", omml)

    def test_frac_and_failsoft(self):
        from tasks.math_ast import ascii_to_ast, ast_to_tex

        ast = ascii_to_ast("a/b")
        self.assertIsNotNone(ast)
        self.assertIn("\\frac", ast_to_tex(ast))
        self.assertIsNone(ascii_to_ast(""))
        self.assertIsNone(ascii_to_ast("@@@"))


class KatexPreviewTests(unittest.TestCase):
    def test_mathjax_mathml_smoke(self):
        from tasks.formula_katex import katex_available, render_tex_mathml

        if not katex_available():
            self.skipTest("node/mathjax unavailable")
        mml = render_tex_mathml(r"C_{0} = \beta")
        self.assertIn("<math", mml.casefold())
        self.assertIn("data-sunairum-formula-math", mml)
        self.assertNotIn("<svg", mml.casefold())
        self.assertNotIn("foreignObject", mml)

    def test_mathjax_svg_legacy_smoke(self):
        from tasks.formula_katex import katex_available, render_tex_svg

        if not katex_available():
            self.skipTest("node/mathjax unavailable")
        svg = render_tex_svg(r"C_{0} = \beta")
        self.assertIn("<svg", svg)
        self.assertIn("data-sunairum-formula-math", svg)
        self.assertNotIn("foreignObject", svg)
        self.assertNotRegex(svg, r"<style\b", msg="style tags forbidden in slide SVG")
        self.assertIn("<path", svg.casefold())

    def test_plate_shows_math_without_pptx(self):
        from tasks.formula_visual_intent import (
            author_formula_visual_intent,
            render_formula_plate,
        )
        from tasks.formula_math_render import render_formula_math

        intent = author_formula_visual_intent(
            "C_0 = beta * x",
            terms="C_0 = initial capital",
            call_text=None,
        )
        frag = render_formula_plate(
            intent,
            aabb=(40, 140, 1200, 500),
            terms="C_0 = initial capital",
            gloss="",
        )
        self.assertIn('data-sunairum-formula-host="1"', frag)
        self.assertIn('id="formula-band"', frag)
        self.assertIn("EQUATION", frag)
        self.assertNotIn("`", frag)
        # Attention path: PNG/flat math — no OMML replace / nested MathJax publish.
        self.assertNotIn('data-pptx-replace-with="formula"', frag)
        self.assertNotRegex(frag, r"<svg\b[^>]*data-sunairum-formula-math")
        self.assertIn('data-sunairum-formula-legend="1"', frag)
        self.assertIn("initial capital", frag)
        self.assertTrue(
            'data-sunairum-formula="1"' in frag
            or "data-sunairum-formula-math" in frag
            or "<image" in frag.casefold()
        )
        math = render_formula_math("C_0 = beta * x")
        self.assertIsNotNone(math)


class OmmlNativeTests(unittest.TestCase):
    @staticmethod
    def _scripts_path() -> str:
        import sys

        scripts = str(Path(__file__).resolve().parents[1] / "sunairum_scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        return scripts

    def test_validate_and_build_native_formula(self):
        from tasks.math_ast import ascii_to_ast, ast_to_omml, ast_to_omml_para

        self._scripts_path()
        from svg_to_pptx.drawingml.context import ConvertContext  # noqa: E402
        from svg_to_pptx.native_objects.formula import (  # noqa: E402
            _build_native_formula,
            _validate_formula_payload,
        )

        ast = ascii_to_ast("C_0 = beta * x")
        payload = {
            "x": 100,
            "y": 200,
            "width": 400,
            "height": 80,
            "ast": ast,
            "omml": ast_to_omml(ast),
            "omml_para": ast_to_omml_para(ast),
        }
        para = _validate_formula_payload(payload)
        self.assertIn("<m:oMathPara>", para)
        self.assertIn("<m:sSub>", para)
        elem = ET.Element("g")
        elem.set("data-pptx-replace-with", "formula")
        meta = ET.SubElement(elem, "metadata")
        meta.set("type", "application/json")
        meta.text = json.dumps(payload)
        ET.SubElement(elem, "rect", {"x": "0", "y": "0", "width": "400", "height": "80"})
        ctx = ConvertContext()
        result = _build_native_formula(elem, ctx, payload)
        self.assertIn("<m:oMath", result.xml)
        self.assertIn("<p:sp>", result.xml)
        self.assertIn('txBox="1"', result.xml)

    def test_native_kinds_include_formula(self):
        self._scripts_path()
        from svg_to_pptx.native_objects.marker_common import _NATIVE_KINDS  # noqa: E402

        self.assertIn("formula", _NATIVE_KINDS)

    def test_fixture_plate_inject(self):
        from tasks.formula_visual_intent import (
            author_formula_visual_intent,
            render_formula_plate,
        )

        svg = (FIXTURES / "ss_formula_c0.svg").read_text(encoding="utf-8")
        intent = author_formula_visual_intent("C_0 = beta * Equity", call_text=None)
        frag = render_formula_plate(intent, aabb=(40, 140, 1200, 480))
        out = svg.replace("</svg>", frag + "</svg>")
        self.assertIn("data-sunairum-formula-host", out)
        self.assertNotIn("`C_0", out)


if __name__ == "__main__":
    unittest.main()
