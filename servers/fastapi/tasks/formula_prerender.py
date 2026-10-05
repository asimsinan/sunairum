"""Pre-render formula MathML before materialize so hosts get editable math."""

from __future__ import annotations

from typing import Any


def prerender_formula_mathml_for_slide(
    slide: dict[str, Any],
    *,
    theme: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach ``_formula_math`` (MathML + OMML meta) when formula IR is present."""
    try:
        from tasks.formula_visual_intent import sanitize_formula_text
        from tasks.formula_latex_png import resolve_formula_tex
        from tasks.formula_math_render import render_formula_math
        from tasks.intent_hosts import FORMULA_HOST
    except ImportError:  # pragma: no cover
        from formula_visual_intent import sanitize_formula_text  # type: ignore
        from formula_latex_png import resolve_formula_tex  # type: ignore
        from formula_math_render import render_formula_math  # type: ignore
        from intent_hosts import FORMULA_HOST  # type: ignore

    formula = sanitize_formula_text(str(slide.get("formula") or ""))
    formula_tex = sanitize_formula_text(str(slide.get("formula_tex") or ""))
    if formula:
        slide["formula"] = formula
    if formula_tex:
        slide["formula_tex"] = formula_tex
    if not formula and not formula_tex:
        return slide

    tex = resolve_formula_tex(formula, formula_tex)
    if not tex:
        return slide
    ink = str((theme or {}).get("ink") or (theme or {}).get("primary") or "#1A365D")
    math = render_formula_math(tex, color=ink)
    if not math:
        # Try raw formula string through AST when resolve_formula_tex returned TeX
        # that ascii_to_ast cannot parse — fall back to TeX-only MathML worker.
        try:
            from tasks.formula_katex import render_tex_mathml
            from tasks.math_ast import ascii_to_ast, ast_to_omml, ast_to_omml_para, ast_to_unicode

            mathml = render_tex_mathml(tex, display=True, color=ink) or ""
            ast = ascii_to_ast(formula or tex)
            math = {
                "ast": ast,
                "tex": tex,
                "omml": ast_to_omml(ast) if ast else "",
                "omml_para": ast_to_omml_para(ast) if ast else "",
                "mathml": mathml,
                "display": (ast_to_unicode(ast) if ast else "") or formula or tex,
                "width": 480.0,
                "height": 64.0,
            }
        except Exception:
            return slide
    if not math.get("mathml") and not math.get("display"):
        return slide

    slide["_formula_math"] = math
    # Clear legacy PNG keys so inject path cannot prefer rasters.
    slide.pop("_formula_png_href", None)
    slide.pop("_formula_png_data_uri", None)
    slide.pop("_formula_flat_group", None)
    slide["_formula_band"] = {
        "x": FORMULA_HOST[0],
        "y": FORMULA_HOST[1],
        "w": FORMULA_HOST[2],
        "h": FORMULA_HOST[3],
    }
    return slide


def prerender_formula_for_slide(
    slide: dict[str, Any],
    *,
    images_dir: str = "",
    theme: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Back-compat alias — MathML path (images_dir unused)."""
    del images_dir
    return prerender_formula_mathml_for_slide(slide, theme=theme)
