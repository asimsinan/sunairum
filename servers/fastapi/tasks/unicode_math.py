"""Normalize Unicode fake-math to PPTX/PDF-safe ASCII + covering fonts."""

from __future__ import annotations

import re

# Phonetic / math subscript & superscript letters/digits commonly emitted by LLMs.
_SUB_MAP = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "ₐ": "a", "ₑ": "e", "ₕ": "h", "ᵢ": "i", "ⱼ": "j",
    "ₖ": "k", "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₒ": "o",
    "ₚ": "p", "ᵣ": "r", "ₛ": "s", "ₜ": "t", "ᵤ": "u",
    "ᵥ": "v", "ₓ": "x",
    "₊": "+", "₋": "-",
}
_SUP_MAP = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "ⁿ": "n", "ⁱ": "i",
}
_OP_MAP = {
    "−": "-",
    "–": "-",
    "—": "-",
    "·": "*",
    "×": "x",
    "÷": "/",
    "ℝ": "R",
    "ℕ": "N",
    "ℤ": "Z",
    "∑": "sum",
    "Σ": "Sigma",
}
_GREEK_FALLBACK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "ε": "epsilon", "θ": "theta", "λ": "lambda", "μ": "mu",
    "π": "pi", "σ": "sigma", "φ": "phi", "ω": "omega",
}

_MATH_FONT = "Cambria, Liberation Serif, DejaVu Serif, serif"
_SUB_CHARS = "".join(_SUB_MAP)
_SUP_CHARS = "".join(_SUP_MAP)
_SUB_RUN = re.compile(f"([{re.escape(_SUB_CHARS)}]+)")
_SUP_RUN = re.compile(f"([{re.escape(_SUP_CHARS)}]+)")


def transliterate_math_text(text: str, *, fold_greek: bool = False) -> str:
    """Convert Unicode sub/superscript math runs to ASCII ``_`` / ``^`` form."""
    if not text:
        return text

    def _sub_repl(match: re.Match[str]) -> str:
        body = "".join(_SUB_MAP.get(ch, ch) for ch in match.group(1))
        return f"_{body}"

    def _sup_repl(match: re.Match[str]) -> str:
        body = "".join(_SUP_MAP.get(ch, ch) for ch in match.group(1))
        return f"^{body}"

    out = _SUB_RUN.sub(_sub_repl, text)
    out = _SUP_RUN.sub(_sup_repl, out)
    for src, dst in _OP_MAP.items():
        out = out.replace(src, dst)
    if fold_greek:
        for src, dst in _GREEK_FALLBACK.items():
            out = out.replace(src, dst)
    # Collapse accidental double underscores from already-ASCII text.
    out = re.sub(r"_{2,}", "_", out)
    out = re.sub(r"\^{2,}", "^", out)
    return out


_BASELINE_TSPAN = re.compile(
    r"<tspan\b([^>]*\bbaseline-shift\b[^>]*)>(.*?)</tspan>",
    re.I | re.S,
)


def rewrite_baseline_shift_tspans(svg: str) -> str:
    """Map unsupported ``baseline-shift`` to DrawingML-safe ``dy`` drops.

    Native PPTX conversion rejects ``baseline-shift`` with no registered
    mapping. Subscript → ``dy="4"`` (+ restore); superscript → ``dy="-4"``.
    """
    if not svg or "baseline-shift" not in svg.lower():
        return svg

    def _repl(match: re.Match[str]) -> str:
        attrs, inner = match.group(1), match.group(2)
        shift_m = re.search(
            r"""baseline-shift\s*=\s*(?:(["'])(.*?)\1|([^\s"'=<>`]+))""",
            attrs,
            re.I,
        )
        shift_raw = ""
        if shift_m:
            shift_raw = (shift_m.group(2) or shift_m.group(3) or "").strip().lower()
            attrs = attrs[: shift_m.start()] + attrs[shift_m.end() :]
        if "baseline-shift" in attrs.lower():

            def _scrub_style(sm: re.Match[str]) -> str:
                nonlocal shift_raw
                body = sm.group(2)
                val_m = re.search(r"baseline-shift\s*:\s*([^;]+)", body, re.I)
                if val_m and not shift_raw:
                    shift_raw = val_m.group(1).strip().lower()
                cleaned = re.sub(
                    r"(?:^|;)\s*baseline-shift\s*:\s*[^;]+;?",
                    "",
                    body,
                    flags=re.I,
                ).strip(" ;")
                if not cleaned:
                    return ""
                return f" style={sm.group(1)}{cleaned}{sm.group(1)}"

            attrs = re.sub(
                r"""\s*style\s*=\s*(["'])(.*?)\1""",
                _scrub_style,
                attrs,
                flags=re.I,
            )
        if not shift_raw:
            attrs = re.sub(r"\s{2,}", " ", attrs).strip()
            return f"<tspan {attrs}>".replace("<tspan >", "<tspan>") + f"{inner}</tspan>"

        is_super = shift_raw in {"super", "superscript"} or shift_raw.startswith("-")
        dy = "-4" if is_super else "4"
        if not re.search(r"\bdy\s*=", attrs, re.I):
            attrs = f'{attrs} dy="{dy}"'
        if (
            not is_super
            and not re.search(r"\bfont-size\s*=", attrs, re.I)
            and "font-size" not in attrs.lower()
        ):
            attrs = f'{attrs} font-size="10"'
        # Prefer absolute px over percent font-size for DrawingML.
        attrs = re.sub(
            r"""font-size\s*=\s*(["'])70%\1""",
            'font-size="10"',
            attrs,
            flags=re.I,
        )
        attrs = re.sub(r"\s{2,}", " ", attrs).strip()
        open_tag = f"<tspan {attrs}>".replace("<tspan >", "<tspan>")
        restore = f'<tspan dy="{("-4" if dy == "4" else "4")}"></tspan>'
        # Avoid double-restore when an older rewrite already appended one.
        return f"{open_tag}{inner}</tspan>{restore}"

    return _BASELINE_TSPAN.sub(_repl, svg)


def sanitize_svg_math(svg: str) -> str:
    """Rewrite text nodes containing Unicode math; swap fonts when needed."""
    if not svg:
        return svg

    svg = rewrite_baseline_shift_tspans(svg)

    def _rewrite_text(match: re.Match[str]) -> str:
        open_tag, body, close = match.group(1), match.group(2), match.group(3)
        plain = re.sub(r"<[^>]+>", "", body)
        if not any(ch in plain for ch in (_SUB_CHARS + _SUP_CHARS + "".join(_OP_MAP))):
            # Still may need Greek on a covering face.
            if any(ch in plain for ch in _GREEK_FALLBACK) and "font-family" in open_tag:
                if "Cambria" not in open_tag and "DejaVu" not in open_tag:
                    open_tag = re.sub(
                        r'font-family="[^"]*"',
                        f'font-family="{_MATH_FONT}"',
                        open_tag,
                        count=1,
                    )
            return f"{open_tag}{body}{close}"

        new_plain = transliterate_math_text(plain, fold_greek=False)
        # If body is a single text run (no tspans with structure we must keep),
        # replace whole body; else replace character-by-character in body.
        if "<" not in body:
            new_body = transliterate_math_text(body, fold_greek=False)
        else:
            new_body = body
            for src, dst in {**_SUB_MAP, **_SUP_MAP, **_OP_MAP}.items():
                if src in new_body:
                    # Apply run-aware transliteration on text-only segments.
                    pass
            parts = re.split(r"(<[^>]+>)", new_body)
            rebuilt: list[str] = []
            for part in parts:
                if part.startswith("<"):
                    rebuilt.append(part)
                else:
                    rebuilt.append(transliterate_math_text(part, fold_greek=False))
            new_body = "".join(rebuilt)

        if "font-family=" in open_tag:
            open_tag = re.sub(
                r'font-family="[^"]*"',
                f'font-family="{_MATH_FONT}"',
                open_tag,
                count=1,
            )
        else:
            open_tag = open_tag[:-1] + f' font-family="{_MATH_FONT}">'
        # Prefer ASCII form; if residual subscripts remain, fold greek too.
        if any(ch in new_body for ch in (_SUB_CHARS + _SUP_CHARS)):
            new_body = transliterate_math_text(new_body, fold_greek=True)
        _ = new_plain  # kept for clarity / future glyph checks
        return f"{open_tag}{new_body}{close}"

    out = re.sub(
        r"(<text\b[^>]*>)(.*?)(</text>)",
        _rewrite_text,
        svg,
        flags=re.I | re.S,
    )
    return out


def svg_has_unsafe_math(svg: str) -> bool:
    plain = re.sub(r"<[^>]+>", "", svg or "")
    return any(ch in plain for ch in (_SUB_CHARS + _SUP_CHARS))
