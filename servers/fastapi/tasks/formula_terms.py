"""Parse and format formula term-card copy for the Scene v2 renderer."""

from __future__ import annotations

import re


def _strip_wrappers(raw: str) -> str:
    text = str(raw or "").strip()
    text = re.sub(r"^\\\((.*?)\\\)$", r"\1", text, flags=re.S)
    text = re.sub(r"^\\\[(.*?)\\\]$", r"\1", text, flags=re.S)
    text = re.sub(r"^\$+(.*?)\$+$", r"\1", text, flags=re.S)
    return text.strip()


def _unwrap_inline_math(raw: str) -> str:
    text = str(raw or "")
    text = re.sub(r"\\\((.*?)\\\)", r"\1", text)
    text = re.sub(r"\\\[(.*?)\\\]", r"\1", text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    return (
        text.replace("\\(", "")
        .replace("\\)", "")
        .replace("\\[", "")
        .replace("\\]", "")
        .strip()
    )


_SUB_DIGITS = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_SUB_LETTERS = {
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
    "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
    "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
}
_TEX_PROSE = {
    "ldots": "…", "dots": "…", "cdots": "⋯", "vdots": "⋮", "cdot": "·",
    "times": "×", "div": "÷", "pm": "±", "mp": "∓", "leq": "≤",
    "geq": "≥", "neq": "≠", "approx": "≈", "sim": "∼", "infty": "∞",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "sum": "∑", "prod": "∏", "int": "∫", "partial": "∂",
    "nabla": "∇", "forall": "∀", "exists": "∃", "in": "∈", "notin": "∉",
    "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩",
    "emptyset": "∅", "varnothing": "∅",
}


def _subscript(raw: str) -> str:
    return "".join(
        _SUB_LETTERS.get(char.casefold(), char.translate(_SUB_DIGITS)) for char in raw
    )


def _tex_to_unicode(raw: str) -> str:
    text = str(raw or "")
    text = (
        text.replace("\\{", "{")
        .replace("\\}", "}")
        .replace("\\,", " ")
        .replace("\\;", " ")
        .replace("\\:", " ")
        .replace("\\!", "")
        .replace("~", " ")
    )
    text = re.sub(r"\\([A-Za-z]+)\b", lambda match: _TEX_PROSE.get(match.group(1), match.group(1)), text)
    text = re.sub(r"_\{([^}]+)\}", lambda match: _subscript(match.group(1)), text)
    text = re.sub(r"_([A-Za-z0-9]+)", lambda match: _subscript(match.group(1)), text)
    try:
        from tasks.formula_visual_intent import _tex_greek_to_unicode

        text = _tex_greek_to_unicode(text)
    except Exception:  # noqa: BLE001
        pass
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text).replace("\\", "")
    text = re.sub(r"\s*=\s*", " = ", text)
    return re.sub(r"\s+", " ", text).strip()


def format_formula_term_symbol(symbol: str) -> str:
    """Return readable term-card text, for example ``c(R_j)`` → ``c(Rⱼ)``."""
    return _tex_to_unicode(_unwrap_inline_math(_strip_wrappers(symbol)))


def _clean_explanation(raw: str) -> str:
    text = _tex_to_unicode(_unwrap_inline_math(str(raw or "").strip()))
    text = re.sub(r"^\)+\s*", "", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    if text and text[-1] not in ".!?":
        text += "."
    return text


def parse_formula_term_pairs(terms: str, gloss: str) -> list[tuple[str, str]]:
    """Build grounded ``(symbol, explanation)`` pairs without changing geometry."""
    normalized = re.sub(r"\\\(([^=\\\n]{1,48}?)=\\\)", r"\1=", str(terms or ""))
    bits = [item.strip() for item in re.split(r"[;\n|]+", _strip_wrappers(normalized)) if item.strip()]
    gloss_bits = [item.strip() for item in re.split(r"(?:;|\n|\|\|)+", gloss or "") if item.strip()]
    per_term_gloss = len(gloss_bits) == len(bits) and len(bits) > 1
    whole_gloss = _clean_explanation(re.sub(r"\\\((.*?)\\\)", r"\1", gloss or ""))
    pairs: list[tuple[str, str]] = []
    for index, bit in enumerate(bits):
        token = _unwrap_inline_math(bit)
        symbol, separator, explanation = token.partition("=")
        symbol = _unwrap_inline_math(_strip_wrappers(symbol))
        if not separator:
            explanation = ""
        if not explanation:
            if per_term_gloss:
                explanation = gloss_bits[index]
            elif whole_gloss and index == 0:
                explanation = whole_gloss
            else:
                explanation = f"Symbol {format_formula_term_symbol(symbol)} in the equation."
        cleaned = _clean_explanation(explanation)
        if symbol and cleaned:
            pairs.append((symbol, cleaned))
    return pairs[:8]
