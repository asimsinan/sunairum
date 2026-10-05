"""Shared formula math paint: AST → MathML + OMML metadata (no SVG primary path)."""

from __future__ import annotations

import html
import re
from typing import Any

from tasks.math_ast import (
    ascii_to_ast,
    ast_to_omml,
    ast_to_omml_para,
    ast_to_tex,
    ast_to_unicode,
)


# `\b` fails after commands glued to `_` / `{` (e.g. `\sum_j`); use non-letter.
_TEX_CMD_RE = re.compile(
    r"\\(sum|prod|int|frac|sqrt|left|right|cdot|times|alpha|beta|gamma|delta|"
    r"mu|sigma|lambda|theta|phi|omega|infty|partial|nabla|leq|geq|neq|approx|"
    r"rightarrow|leftarrow|subseteq|supseteq|bigcup|bigcap|mathbb|mathrm|text)"
    r"(?![A-Za-z])"
)


def looks_like_tex(formula: str) -> bool:
    """True when the string already carries TeX commands (not Strategist ASCII)."""
    return bool(_TEX_CMD_RE.search(str(formula or "")))


def render_formula_math(
    formula: str,
    *,
    color: str = "#0F172A",
) -> dict[str, Any] | None:
    """Return math payload or None if ASCII cannot be parsed.

    Primary: MathML for HTML hosts + OMML metadata. SVG is not required.

    When the input is already TeX (``\\sum``, ``\\frac``, …), render it with
    KaTeX directly. The Strategist ASCII AST path treats juxtaposition as
    multiplication and strips ``\\`` from commands, which corrupts real TeX
    like ``C(R)=\\sum_j c(R_j)`` into ``C·R = sum_j·c·R_j``.
    """
    from tasks.formula_katex import render_tex_mathml

    raw = str(formula or "").strip()
    if not raw:
        return None

    if looks_like_tex(raw):
        mathml = render_tex_mathml(raw, display=True, color=color) or ""
        if mathml and (
            "<svg" in mathml.casefold()
            or "foreignObject" in mathml
            or re.search(r"<style\b", mathml, flags=re.I)
        ):
            mathml = ""
        if mathml:
            # Best-effort OMML from ASCII AST; never let AST rewrite the TeX.
            ast = ascii_to_ast(raw)
            display = raw.replace("\\sum", "∑").replace("\\cdot", "⋅")
            display = re.sub(r"\\[a-zA-Z]+", "", display)
            display = re.sub(r"\s+", " ", display).strip() or raw
            w = max(280.0, min(1100.0, len(display) * 14.0 + 48.0))
            return {
                "ast": ast,
                "tex": raw,
                "omml": ast_to_omml(ast) if ast else "",
                "omml_para": ast_to_omml_para(ast) if ast else "",
                "mathml": mathml,
                "svg": "",
                "display": display,
                "width": w,
                "height": 64.0,
                "viewBox": "",
            }

    ast = ascii_to_ast(raw)
    if ast is None:
        # Last resort: try KaTeX on the raw string even without known commands.
        mathml = render_tex_mathml(raw, display=True, color=color) or ""
        if not mathml or "<svg" in mathml.casefold() or "foreignObject" in mathml:
            return None
        return {
            "ast": None,
            "tex": raw,
            "omml": "",
            "omml_para": "",
            "mathml": mathml,
            "svg": "",
            "display": raw,
            "width": max(280.0, min(1100.0, len(raw) * 14.0 + 48.0)),
            "height": 64.0,
            "viewBox": "",
        }
    tex = ast_to_tex(ast)
    if not tex:
        return None
    omml = ast_to_omml(ast)
    omml_para = ast_to_omml_para(ast)
    display = ast_to_unicode(ast) or raw
    mathml = render_tex_mathml(tex, display=True, color=color) or ""
    if mathml and (
        "<svg" in mathml.casefold()
        or "foreignObject" in mathml
        or re.search(r"<style\b", mathml, flags=re.I)
    ):
        mathml = ""
    # Layout estimate from unicode length when MathML has no intrinsic size.
    w = max(280.0, min(1100.0, len(display) * 14.0 + 48.0))
    h = 64.0
    return {
        "ast": ast,
        "tex": tex,
        "omml": omml,
        "omml_para": omml_para,
        "mathml": mathml,
        "svg": "",
        "display": display,
        "width": w,
        "height": h,
        "viewBox": "",
    }


def formula_native_metadata(
    math: dict[str, Any],
    *,
    x: float,
    y: float,
    width: float,
    height: float,
) -> dict[str, Any]:
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "ast": math.get("ast"),
        "tex": math.get("tex") or "",
        "omml": math.get("omml") or "",
        "omml_para": math.get("omml_para") or "",
        "mathml": math.get("mathml") or "",
    }


def embed_math_svg_in_band(
    math: dict[str, Any],
    *,
    band_x: float,
    band_y: float,
    band_w: float,
    band_h: float,
) -> str:
    """Legacy SVG plate helper — returns empty; MathML hosts replace SVG bands."""
    del math, band_x, band_y, band_w, band_h
    return ""


def mathml_host_inner_html(
    math: dict[str, Any],
    *,
    color: str = "#0F172A",
) -> str:
    """Inner HTML for a data-pptx=formula host (MathML or unicode fallback).

    Avoid nested ``</div>`` so simple host regex replaces stay valid.
    """
    mathml = str(math.get("mathml") or "").strip()
    if mathml and "<math" in mathml.casefold():
        # Ensure data marker for deckhtml / QA without wrapping in another div.
        if "data-sunairum-formula" not in mathml.casefold():
            mathml = re.sub(
                r"<math\b",
                '<math data-sunairum-formula="1"',
                mathml,
                count=1,
                flags=re.I,
            )
        # Deliberately no `mathcolor`: the formula inherits the colour of the
        # host it was dropped into. Imposing a palette constant overrode the
        # author's own choice, and on a dark region that meant navy ink on a
        # navy surface — a formula at a contrast ratio of 1.00, invisible. The
        # container already knows which ink its surface needs; `color` is the
        # one thing about a formula that is not the formula's business.
        del color
        # Compact display math — host flex-centers; avoid huge MathJax margins.
        if "style=" not in mathml[:80].casefold():
            mathml = re.sub(
                r"<math\b",
                '<math style="font-size:24px;margin:0;max-width:100%;"',
                mathml,
                count=1,
                flags=re.I,
            )
        return mathml
    display = str(math.get("display") or math.get("tex") or "").strip()
    if not display:
        return ""
    safe = html.escape(display)
    # Single element — no nested div close tags (host regex).
    return (
        f'<span data-sunairum-formula-fallback="1" style="display:block;'
        f'font-family:Georgia,\"Times New Roman\",serif;'
        f'font-size:24px;line-height:1.2;color:{html.escape(color)};'
        f'text-align:center;">{safe}</span>'
    )
