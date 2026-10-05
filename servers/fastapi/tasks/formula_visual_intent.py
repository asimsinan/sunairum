"""Formula Visual Intent → Attention-style formula-band (PNG / flat paths)."""

from __future__ import annotations

import html
import json
import re
from typing import Any, Callable

from tasks.formula_latex_png import render_formula_asset, resolve_formula_tex
from tasks.style_resolver import resolve_style_tokens

FORMULA_INTENT_SYSTEM = """You author FormulaVisualIntent JSON only.
Modes: hero | term_callouts. Never change the equation text.
Do not wrap the equation in backticks or $…$.
Emit JSON: {"mode":"hero"|"term_callouts","style":"academic"|"bold"|"compact"}.
"""


def sanitize_formula_text(raw: str) -> str:
    """Strip fences/backticks and TeX delimiters so legend never shows raw \\(...\\)."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"^```(?:\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Block / inline TeX wrappers (display and inline).
    text = re.sub(r"\\\((.*?)\\\)", r"\1", text, flags=re.S)
    text = re.sub(r"\\\[(.*?)\\\]", r"\1", text, flags=re.S)
    text = re.sub(r"(?<!\$)\$\$(.+?)\$\$(?!\$)", r"\1", text, flags=re.S)
    text = re.sub(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", r"\1", text, flags=re.S)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"`", "$"}:
        text = text[1:-1].strip()
    text = text.replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _fit_flat_math_group(
    flat: str,
    asset: dict[str, Any],
    img_x: float,
    img_y: float,
    img_w: float,
    img_h: float,
) -> str:
    """Scale a pre-flattened math group into the plate image box (meet + center)."""
    aw = max(1.0, float(asset.get("width") or img_w))
    ah = max(1.0, float(asset.get("height") or img_h))
    fit = min(img_w / aw, img_h / ah)
    if ah * fit < 36.0:
        fit = 36.0 / ah
    draw_w, draw_h = aw * fit, ah * fit
    ox = img_x + (img_w - draw_w) / 2.0
    oy = img_y + (img_h - draw_h) / 2.0
    return (
        f'<g transform="translate({ox:.1f},{oy:.1f}) scale({fit:.6f})">{flat}</g>'
    )


def formula_math_too_small(svg: str) -> bool:
    """True when formula math paint is a tiny scribble (P04-class)."""
    if not svg:
        return False
    # Flat MathJax group with microscopic scale (viewBox→tiny ex layout).
    for match in re.finditer(
        r'<g\b[^>]*data-sunairum-formula-math="1"[^>]*>',
        svg or "",
        flags=re.I,
    ):
        sm = re.search(r"\bscale\(([-\d.]+)\)", match.group(0), flags=re.I)
        if sm:
            try:
                if float(sm.group(1)) < 0.05:
                    return True
            except ValueError:
                pass
    for match in re.finditer(
        r'<image\b[^>]*\bdata-sunairum-formula="1"[^>]*/?>',
        svg or "",
        flags=re.I,
    ):
        hm = re.search(r'\bheight="([-\d.]+)"', match.group(0), flags=re.I)
        if hm:
            try:
                if float(hm.group(1)) < 28.0:
                    return True
            except ValueError:
                pass
    return False


def default_formula_intent() -> dict[str, Any]:
    return {"mode": "hero", "style": "academic"}


def validate_formula_intent(intent: dict[str, Any], formula: str) -> dict[str, Any]:
    out = default_formula_intent()
    if not isinstance(intent, dict):
        return out
    mode = str(intent.get("mode") or "hero").strip().casefold()
    if mode not in {"hero", "term_callouts"}:
        mode = "hero"
    style = str(intent.get("style") or "academic").strip().casefold() or "academic"
    out["mode"] = mode
    out["style"] = style
    out["formula"] = sanitize_formula_text(formula)  # immutable echo, sanitized
    return out


def author_formula_visual_intent(
    formula: str,
    *,
    terms: str = "",
    gloss: str = "",
    call_text: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    clean = sanitize_formula_text(formula)
    fallback = default_formula_intent()
    fallback["formula"] = clean
    if terms.strip() and fallback["mode"] == "hero":
        fallback["mode"] = "term_callouts"
    if call_text is None or not clean:
        return fallback
    try:
        raw = str(
            call_text(
                FORMULA_INTENT_SYSTEM,
                json.dumps(
                    {
                        "formula": clean,
                        "terms": sanitize_formula_text(terms),
                        "gloss": sanitize_formula_text(gloss),
                    },
                    ensure_ascii=False,
                ),
            )
            or ""
        ).strip()
    except Exception:
        # Transport / budget failures must stop the run (no silent default Intent).
        raise
    if not raw:
        raise RuntimeError("provider returned an empty FormulaVisualIntent response")
    try:
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
        parsed = json.loads(raw)
    except Exception:
        return fallback
    return validate_formula_intent(parsed, clean)


# TeX / word greek → Unicode for legend symbols (preview-safe; not subscripts).
_TEX_GREEK_UNI = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "epsilon": "ε",
    "zeta": "ζ",
    "eta": "η",
    "theta": "θ",
    "iota": "ι",
    "kappa": "κ",
    "lambda": "λ",
    "mu": "μ",
    "nu": "ν",
    "xi": "ξ",
    "pi": "π",
    "rho": "ρ",
    "sigma": "σ",
    "tau": "τ",
    "phi": "φ",
    "chi": "χ",
    "psi": "ψ",
    "omega": "ω",
    "Alpha": "Α",
    "Beta": "Β",
    "Gamma": "Γ",
    "Delta": "Δ",
    "Theta": "Θ",
    "Lambda": "Λ",
    "Pi": "Π",
    "Sigma": "Σ",
    "Phi": "Φ",
    "Psi": "Ψ",
    "Omega": "Ω",
}
_MATH_LEGEND_FONT = "Georgia, Cambria, Liberation Serif, DejaVu Serif, serif"


def _tex_greek_to_unicode(text: str) -> str:
    """Turn \\mu / \\sigma (and word forms) into Unicode greek — keep ASCII body."""
    out = text or ""
    out = re.sub(r"\\(?:mathrm|text|operatorname)\{([^{}]*)\}", r"\1", out)

    def _cmd(match: re.Match[str]) -> str:
        name = match.group(1)
        return _TEX_GREEK_UNI.get(name) or _TEX_GREEK_UNI.get(name.casefold()) or match.group(0)

    out = re.sub(r"\\([A-Za-z]+)", _cmd, out)
    for name in sorted(_TEX_GREEK_UNI, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(name)}\b", _TEX_GREEK_UNI[name], out)
    return out


def format_legend_symbol_svg(symbol: str) -> str:
    """SVG inline runs for a legend LHS: greek glyphs + dy subscripts.

    Uses ``<tspan dy="…" font-size="…">`` (DrawingML-safe) instead of
    ``baseline-shift`` (rejected by native PPTX) or Unicode subscript
    codepoints (stripped by ``sanitize_svg_math`` / missing-glyph QA).
    Each subscript run is followed by a restoring ``dy`` so trailing
    `` = meaning`` text stays on the parent baseline.
    """
    raw = _tex_greek_to_unicode(sanitize_formula_text(symbol))
    if not raw:
        return ""
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"_\{([^{}]+)\}|_([A-Za-z0-9]+)", raw):
        if match.start() > cursor:
            parts.append(html.escape(raw[cursor : match.start()]))
        sub = match.group(1) or match.group(2) or ""
        # 4px drop ≈ sub at 14px parent; 10px ≈ 70% of 14.
        parts.append(
            f'<tspan dy="4" font-size="10">{html.escape(sub)}</tspan>'
            f'<tspan dy="-4"></tspan>'
        )
        cursor = match.end()
    if cursor < len(raw):
        parts.append(html.escape(raw[cursor:]))
    return "".join(parts) if parts else html.escape(raw)


def _display_greek(text: str) -> str:
    """Plain-text fallback (no SVG) for tests / non-SVG consumers."""
    out = _tex_greek_to_unicode(text or "")
    # Digit-only subs → Unicode (letter subs stay as _j for plain text).
    out = re.sub(
        r"([A-Za-zΑ-Ωα-ω]+)_\{?([0-9]+)\}?",
        lambda m: m.group(1)
        + m.group(2).translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")),
        out,
    )
    return out


def _legend_parts(
    intent: dict[str, Any], terms: str, gloss: str
) -> tuple[list[tuple[str, str]], str]:
    """Return (symbol, meaning) pairs for legend rows + cleaned gloss."""
    term_rows: list[tuple[str, str]] = []
    clean_terms = sanitize_formula_text(terms)
    if (intent.get("mode") == "term_callouts" or clean_terms) and clean_terms:
        for part in re.split(r"\s*[;\n]\s*", clean_terms):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                name, meaning = part.split("=", 1)
                term_rows.append((name.strip(), meaning.strip()))
            elif ":" in part:
                name, meaning = part.split(":", 1)
                term_rows.append((name.strip(), meaning.strip()))
            else:
                term_rows.append((part, ""))
            if len(term_rows) >= 4:
                break
    return term_rows, sanitize_formula_text(gloss)


def render_formula_plate(
    intent: dict[str, Any],
    *,
    aabb: tuple[float, float, float, float],
    terms: str = "",
    gloss: str = "",
    theme: dict[str, Any] | None = None,
    images_dir: str = "",
    formula_id: str = "formula_001",
) -> str:
    """Attention formula-band: accent bar + EQUATION label + PNG/flat math."""
    x, y, w, h = aabb
    formula = sanitize_formula_text(str(intent.get("formula") or ""))
    formula_tex = sanitize_formula_text(str(intent.get("formula_tex") or ""))
    if not formula and not formula_tex:
        return ""
    theme = theme if isinstance(theme, dict) else {}
    tokens = resolve_style_tokens(
        style=str(intent.get("style") or "academic"), theme=theme
    )
    primary = str(
        theme.get("stroke")
        or theme.get("primary")
        or tokens.get("primary")
        or "#1A365D"
    )
    accent = str(theme.get("accent") or tokens.get("accent") or "#3182CE")
    ink = str(
        theme.get("ink")
        or theme.get("primary")
        or tokens.get("primary")
        or "#1A365D"
    )
    muted = str(theme.get("muted") or tokens.get("muted") or "#4A5568")
    surface = str(
        theme.get("surface")
        or theme.get("accent_tint")
        or tokens.get("surface")
        or "#EBF4FF"
    )
    border = str(theme.get("border") or "#E2E8F0")
    body_font = str(theme.get("body_family") or "Arial, sans-serif")
    esc = html.escape

    legend_intent = dict(intent)
    if sanitize_formula_text(terms) and legend_intent.get("mode") == "hero":
        legend_intent["mode"] = "term_callouts"
    term_rows, clean_gloss = _legend_parts(legend_intent, terms, gloss)

    tex = resolve_formula_tex(formula, formula_tex)
    asset: dict[str, Any] = {}
    pre_href = str(intent.get("_prerender_href") or "").strip()
    images_root = images_dir or "/tmp/sunairum_formula_cache"
    if pre_href:
        asset = {
            "png_href": pre_href if not pre_href.startswith("data:") else "",
            "data_uri": pre_href if pre_href.startswith("data:") else "",
            "width": float(intent.get("_prerender_w") or 640),
            "height": float(intent.get("_prerender_h") or 90),
            "flat_group": "",
        }
        # Reject broken prerender (Codecogs red error / empty ink) and re-render.
        try:
            from tasks.formula_latex_png import formula_png_is_usable
            from pathlib import Path
            import base64
            import tempfile

            ok = False
            if pre_href.startswith("data:image/png;base64,"):
                raw = base64.b64decode(pre_href.split(",", 1)[1], validate=False)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp.write(raw)
                    tmp_path = Path(tmp.name)
                try:
                    ok = formula_png_is_usable(tmp_path, ink=ink)
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
            elif not pre_href.startswith("data:"):
                # Relative ../images/foo.png → resolve against images_dir when possible.
                name = Path(pre_href).name
                cand = Path(images_root) / name
                ok = formula_png_is_usable(cand, ink=ink) if cand.is_file() else False
            if not ok:
                asset = {}
        except Exception:
            asset = {}
    if not (asset.get("data_uri") or asset.get("png_href")):
        asset = render_formula_asset(
            tex,
            images_dir=images_root,
            formula_id=formula_id,
            color=ink,
            prefer_network=False,
        )

    # Full-width Attention band + legend surface inside owned AABB.
    band_w = max(280.0, w - 8.0)
    legend_need = 0.0
    if term_rows:
        legend_need += 10.0 + 20.0 * len(term_rows)
    if clean_gloss:
        legend_need += 8.0 + 22.0
    legend_block = (legend_need + 16.0) if (term_rows or clean_gloss) else 0.0
    band_x = max(0.0, (w - band_w) / 2.0)
    band_y = 8.0
    # Size <image> from real PNG aspect: readable size, never stretch.
    aw = max(1.0, float(asset.get("width") or 640.0))
    ah = max(1.0, float(asset.get("height") or 90.0))
    max_w = max(120.0, band_w - 48.0)
    # Leave room for legend surface + bottom pad inside host height.
    max_img_h = max(48.0, min(96.0, h - legend_block - 64.0))
    min_img_h = min(52.0, max_img_h)
    fit_w = max_w / aw
    h_at_w = ah * fit_w
    if h_at_w > max_img_h:
        fit = max_img_h / ah
    elif h_at_w < min_img_h:
        fit = min_img_h / ah
        if aw * fit > max_w:
            fit = max_w / aw
    else:
        fit = fit_w
    img_w = aw * fit
    img_h = ah * fit
    # Equation plate shrinks when legend needs space — never clip terms past host.
    band_h = max(72.0, min(h - legend_block - 20.0, img_h + 44.0))
    img_x = band_x + (band_w - img_w) / 2.0
    img_y = band_y + 28.0 + max(0.0, (band_h - 36.0 - img_h) / 2.0)

    parts = [
        f'<g id="formula-band" data-sunairum-formula-host="1" '
        f'transform="translate({x:.1f},{y:.1f})">',
        f'<rect x="{band_x:.1f}" y="{band_y:.1f}" width="{band_w:.1f}" '
        f'height="{band_h:.1f}" rx="12" fill="{esc(surface)}" '
        f'stroke="{esc(border)}" stroke-width="1.5" data-sunairum-formula-plate="1"/>',
        f'<rect x="{band_x:.1f}" y="{band_y:.1f}" width="6" height="{band_h:.1f}" '
        f'rx="3" fill="{esc(accent)}"/>',
        f'<text data-sunairum-formula="1" x="{band_x + 40:.1f}" '
        f'y="{band_y + 26:.1f}" '
        f'font-family="{esc(body_font)}" font-size="12" font-weight="700" '
        f'fill="{esc(accent)}" letter-spacing="1.5">EQUATION</text>',
    ]
    href = str(asset.get("data_uri") or asset.get("png_href") or "")
    if href:
        parts.append(
            f'<image href="{esc(href)}" x="{img_x:.1f}" y="{img_y:.1f}" '
            f'width="{img_w:.1f}" height="{img_h:.1f}" '
            f'preserveAspectRatio="xMidYMid meet" data-sunairum-formula="1"/>'
        )

    # Legend on its own surface under the plate (still inside host AABB).
    term_x = band_x + 22.0
    if term_rows or clean_gloss:
        legend_top = band_y + band_h + 10.0
        legend_h = min(legend_need + 12.0, max(36.0, h - legend_top - 8.0))
        parts.append(
            f'<rect x="{band_x:.1f}" y="{legend_top:.1f}" width="{band_w:.1f}" '
            f'height="{legend_h:.1f}" rx="10" fill="{esc(surface)}" '
            f'stroke="{esc(border)}" stroke-width="1" '
            f'data-sunairum-formula-legend-plate="1"/>'
        )
        parts.append(
            f'<rect x="{band_x:.1f}" y="{legend_top:.1f}" width="6" '
            f'height="{legend_h:.1f}" rx="3" fill="{esc(accent)}"/>'
        )
        parts.append('<g data-sunairum-formula-legend="1">')
        cursor_y = legend_top + 18.0
        floor = legend_top + legend_h - 8.0
        for symbol, meaning in term_rows:
            if cursor_y > floor:
                break
            symbol_svg = format_legend_symbol_svg(symbol)
            if meaning:
                body = f"{symbol_svg} = {esc(meaning[:100])}"
            else:
                body = symbol_svg
            parts.append(
                f'<text data-sunairum-formula-term="1" x="{term_x:.1f}" '
                f'y="{cursor_y:.1f}" font-family="{esc(_MATH_LEGEND_FONT)}" '
                f'font-size="14" fill="{esc(muted)}">{body}</text>'
            )
            cursor_y += 20.0
        if clean_gloss and cursor_y <= floor:
            gloss_snip = clean_gloss[:220]
            gloss_body = (
                format_legend_symbol_svg(gloss_snip)
                if re.search(r"[\\_]", gloss_snip)
                else esc(gloss_snip)
            )
            parts.append(
                f'<text x="{term_x:.1f}" y="{cursor_y:.1f}" '
                f'font-family="{esc(body_font)}" font-size="15" fill="{esc(ink)}">'
                f"{gloss_body}</text>"
            )
        parts.append("</g>")
    parts.append("</g>")
    return "".join(parts)
