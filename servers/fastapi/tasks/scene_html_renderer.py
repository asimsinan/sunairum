"""Render supported Scene Layout v2 compositions to constrained DeckHTML.

This is intentionally a small component renderer, not a CSS repair layer. It
uses resolved scene regions verbatim and lets runtime geometry QA reject copy
that exceeds those regions.
"""

from __future__ import annotations

import html
import re
from typing import Any


def _copy(slide: dict[str, Any], key: str) -> str:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    return str(slide.get(key) or content.get(key.upper()) or "").strip()


def _claims(slide: dict[str, Any]) -> list[tuple[str, str]]:
    cards = slide.get("cards") if isinstance(slide.get("cards"), list) else []
    if not cards and isinstance(slide.get("steps"), list):
        cards = slide["steps"]
    out: list[tuple[str, str]] = []
    for card in cards:
        if isinstance(card, dict):
            title = str(card.get("title") or "").strip()
            body = str(card.get("body") or card.get("text") or "").strip()
            if title or body:
                out.append((title, body))
    if out:
        return out
    raw = _copy(slide, "content_blocks") or _copy(slide, "body") or _copy(slide, "bullets")
    if isinstance(slide.get("bullets"), list):
        lines = [str(item).strip() for item in slide["bullets"] if str(item).strip()]
    else:
        lines = [re.sub(r"^\s*[-•*]\s*", "", line).strip() for line in raw.splitlines() if line.strip()]
    for line in lines:
        head, separator, tail = line.partition(":")
        out.append((head.strip() if separator else "", tail.strip() if separator else line))
    return out or [("", _copy(slide, "core_message"))]


def _formula_claims(slide: dict[str, Any]) -> list[tuple[str, str]]:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    terms = str(slide.get("formula_terms") or content.get("FORMULA_TERMS") or "").strip()
    gloss = str(slide.get("formula_gloss") or content.get("FORMULA_GLOSS") or "").strip()
    if not terms:
        return []
    from tasks.formula_terms import format_formula_term_symbol, parse_formula_term_pairs

    def _plain(value: str) -> str:
        text = str(value or "").replace("`", "")
        text = re.sub(r"\\\(|\\\)|\\\[|\\\]|\$+", "", text)
        text = re.sub(r"\\beta\b", "β", text)
        text = re.sub(r"\\gamma\b", "γ", text)
        text = re.sub(r"\\(?:mathrm|text)\{([^{}]*)\}", r"\1", text)
        return re.sub(r"\\([A-Za-z]+)", r"\1", text).strip()

    pairs = [
        (_plain(format_formula_term_symbol(symbol)), _plain(explanation))
        for symbol, explanation in parse_formula_term_pairs(terms, gloss)
    ]
    if gloss:
        normalized_gloss = re.sub(r"\s+", " ", _plain(gloss)).strip()
        if normalized_gloss and all(normalized_gloss.casefold() not in body.casefold() for _head, body in pairs):
            pairs.append(("In this equation", normalized_gloss))
    return pairs


def _style(region: dict[str, Any]) -> str:
    return (
        f"position:absolute;left:{region['x']}px;top:{region['y']}px;width:{region['w']}px;height:{region['h']}px;"
    )


def render_scene_html(
    *,
    slide: dict[str, Any],
    scene: dict[str, Any],
    palette: dict[str, str] | None = None,
    density: str = "comfortable",
) -> str:
    """Return a complete, measured-region HTML slide for a supported scene."""
    regions = {str(region.get("id")): region for region in scene.get("regions") or [] if isinstance(region, dict)}
    primary = regions.get("primary")
    if not primary and scene.get("composition") not in {"title"}:
        raise ValueError("Scene renderer requires a primary region")
    colors = palette or {}
    bg = html.escape(str(colors.get("background") or "#FFFFFF"))
    ink = html.escape(str(colors.get("body_text") or "#182B49"))
    primary_color = html.escape(str(colors.get("primary") or "#173A68"))
    muted = html.escape(str(colors.get("muted") or colors.get("secondary_text") or "#52627A"))
    surface = html.escape(str(colors.get("accent_tint") or "#EDF5FC"))
    title = html.escape(_copy(slide, "title"))
    lede = html.escape(_copy(slide, "lede") or _copy(slide, "subtitle") or _copy(slide, "core_message"))
    eyebrow = html.escape(str(slide.get("eyebrow") or slide.get("section") or "").strip())

    header = ""
    if "title" in regions:
        eyebrow_html = f'<div class="scene-eyebrow">{eyebrow}</div>' if eyebrow else ""
        header += f'<div data-layout-id="scene-title" data-layout-role="title" class="scene-title" style="{_style(regions["title"])}">{eyebrow_html}<h1 data-layout-id="text-title">{title}</h1></div>'
    if "lede" in regions:
        header += f'<div data-layout-id="scene-lede" data-layout-role="lede" class="scene-lede" style="{_style(regions["lede"])}"><p data-layout-id="text-lede">{lede}</p></div>'

    composition_name = str(scene.get("composition") or "body").casefold()
    formula_mode = composition_name == "formula"
    closing_mode = composition_name == "closing"
    claims = [] if closing_mode else (_formula_claims(slide) if formula_mode else _claims(slide))
    if not claims and not closing_mode:
        claims = _claims(slide)
    # This renderer is a deterministic region donor and retry scaffold; its card
    # grid is fixed, so very long copy cannot all be laid out here. That is a
    # limit of *this* renderer, not of the deck: the LLM author is not bound by
    # the grid and routinely composes such a slide well. Refusing used to abort
    # the whole generation from one over-long slide, losing thirteen finished
    # ones with it. Lay out what fits and record the remainder instead.
    max_cards = 9 if formula_mode else 8
    overflow_cards = max(0, len(claims) - max_cards)
    if overflow_cards:
        print(
            f"[scene_html_renderer] slide {slide.get('slide')}: "
            f"{len(claims)} content cards exceed the {max_cards}-card grid; "
            f"donor renders {max_cards} and marks {overflow_cards} as overflow"
        )
        claims = claims[:max_cards]

    def _cards(items: list[tuple[str, str]], prefix: str) -> str:
        return "".join(
        f'<article class="scene-card"'
        + (
            f' data-sunairum-formula-term="term-{index}" data-formula-symbol="{html.escape(head, quote=True)}"'
            if formula_mode and head != "In this equation"
            else ""
        )
        + ">"
        + (f'<h2 data-layout-id="{prefix}-card-{index}-title">{html.escape(head)}</h2>' if head else "")
        + f'<p data-layout-id="{prefix}-card-{index}-body">{html.escape(body)}</p></article>'
        for index, (head, body) in enumerate(items, start=1)
        if head or body
        )

    secondary = regions.get("secondary")
    if secondary and len(claims) > 1:
        split_at = (len(claims) + 1) // 2
        primary_claims = claims[:split_at]
        secondary_claims = claims[split_at:]
    else:
        primary_claims = claims
        secondary_claims = []
    primary_role = str(primary.get("role") if primary else "primary")
    primary_class = (
        "scene-panel scene-process"
        if primary_role == "process"
        else (
            "scene-panel scene-formula-terms scene-formula-many"
            if len(claims) > 6
            else "scene-panel scene-formula-terms"
        )
        if formula_mode
        else "scene-panel"
    )
    if primary and closing_mode:
        closing_author = html.escape(str(slide.get("authors") or "").strip())
        closing_affiliation = html.escape(str(slide.get("affiliations") or "").strip())
        closing_identity = "".join(
            (
                f'<p class="scene-closing-author">{closing_author}</p>' if closing_author else "",
                f'<p class="scene-closing-affiliation">{closing_affiliation}</p>' if closing_affiliation else "",
            )
        )
        primary_html = (
            f'<div data-layout-id="scene-primary" data-layout-role="{html.escape(primary_role, quote=True)}" '
            f'class="scene-closing" style="{_style(primary)}">'
            '<div class="scene-closing-orbit" aria-hidden="true" data-pptx-kind="ignore">?</div>'
            '<div class="scene-closing-rule" aria-hidden="true" data-pptx-kind="ignore"></div>'
            f'{closing_identity}</div>'
        )
    else:
        primary_html = (
            f'<div data-layout-id="scene-primary" data-layout-role="{html.escape(primary_role, quote=True)}" class="{primary_class}" '
            f'style="{_style(primary)}">{_cards(primary_claims, "primary")}</div>'
            if primary
            else ""
        )
    secondary_html = ""
    if secondary:
        secondary_body = _cards(secondary_claims, "secondary") or '<div class="scene-empty">Supporting evidence</div>'
        secondary_html = (
            f'<div data-layout-id="scene-secondary" data-layout-role="secondary" class="scene-panel" style="{_style(secondary)}">'
            f'{secondary_body}</div>'
        )
    figure_html = ""
    figure = regions.get("figure")
    if figure:
        fid = html.escape(str(slide.get("figure_id") or "f1"), quote=True)
        figure_html = (
            f'<div data-layout-id="scene-figure" data-layout-role="figure" data-pptx="figure" data-figure-id="{fid}" '
            f'class="scene-figure" style="{_style(figure)}"></div>'
        )

    host_html = ""
    table_region = regions.get("table")
    if table_region:
        table_id = html.escape(str(slide.get("table_id") or "t1"), quote=True)
        host_html += (
            f'<div data-layout-id="scene-table" data-layout-role="table" data-pptx="table" data-table-id="{table_id}" '
            f'class="scene-host" style="{_style(table_region)}"></div>'
        )
    chart_regions = [
        region
        for identifier, region in regions.items()
        if identifier == "chart" or identifier.startswith("chart_")
    ]
    for index, chart_region in enumerate(chart_regions, start=1):
        region_id = html.escape(str(chart_region.get("id") or f"chart_{index}"), quote=True)
        host_html += (
            f'<div data-layout-id="scene-{region_id}" data-layout-role="chart" data-pptx="chart" data-chart-id="c{index}" '
            f'class="scene-host" style="{_style(chart_region)}"></div>'
        )
    formula_region = regions.get("formula")
    if formula_region:
        host_html += (
            f'<div data-layout-id="scene-formula" data-layout-role="formula" data-pptx="formula" data-formula-id="f1" '
            f'class="scene-host scene-formula" style="{_style(formula_region)}"></div>'
        )

    byline = " · ".join(
        value
        for value in (
            str(slide.get("authors") or "").strip(),
            str(slide.get("affiliations") or "").strip(),
        )
        if value
    )
    byline_region = regions.get("byline")
    byline_html = (
        f'<div data-layout-id="scene-byline" data-layout-role="byline" class="scene-byline" '
        f'style="{_style(byline_region)}">{html.escape(byline)}</div>'
        if byline and byline_region
        else ""
    )

    compact = str(density).casefold() == "compact"
    panel_padding = 16 if compact else 20
    panel_gap = 8 if compact else 12
    card_gap = 8 if compact else 12
    body_line = 1.25 if compact else 1.35
    composition = html.escape(str(scene.get("composition") or "body"), quote=True)
    overflow_attr = (
        f' data-sunairum-scene-card-overflow="{overflow_cards}"' if overflow_cards else ""
    )
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}} html,body{{margin:0;width:1280px;height:720px;overflow:hidden}}
.slide{{position:relative;width:1280px;height:720px;background:{bg};font-family:Inter,Arial,sans-serif;color:{ink};}}
.slide::before{{content:"";position:absolute;inset:0;background:linear-gradient(rgba(49,130,206,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(49,130,206,.035) 1px,transparent 1px);background-size:32px 32px;pointer-events:none;}}
[data-layout-role]{{position:absolute;}}
.scene-title{{border-left:6px solid #3182CE;padding-left:18px;}}
.scene-title h1{{margin:0;padding-top:4px;color:{primary_color};font-family:Georgia,serif;font-size:36px;line-height:1.05;letter-spacing:-.02em;}}
.scene-eyebrow{{margin-bottom:10px;color:{primary_color};font-size:13px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;}}
.scene-lede p{{margin:0;color:{muted};font-size:20px;line-height:1.35;}}
.scene-panel{{display:flex;flex-direction:column;gap:{panel_gap}px;padding:{panel_padding}px;background:#FFFFFF;border:1px solid #D7E3EF;border-radius:16px;box-shadow:0 10px 28px rgba(26,54,93,.08);overflow:hidden;}}
.scene-panel[data-layout-id="scene-primary"]{{background:{primary_color};border-color:{primary_color};}}
.scene-panel[data-layout-id="scene-primary"] .scene-card h2{{color:#90CDF4;}}
.scene-panel[data-layout-id="scene-primary"] .scene-card p{{color:#F4F8FC;}}
.scene-panel[data-layout-id="scene-primary"] .scene-card + .scene-card{{border-top-color:rgba(255,255,255,.18);}}
.scene-card{{min-width:0;flex:1;padding:2px 0;}}
.scene-card + .scene-card{{border-top:1px solid #D7E3EF;padding-top:{card_gap}px;}}
.scene-card h2{{margin:0 0 5px;color:{primary_color};font-size:18px;line-height:1.2;}}
.scene-card p{{margin:0;color:{ink};font-size:16px;line-height:{body_line};}}
.scene-process{{flex-direction:row;align-items:stretch;}}
.scene-process[data-layout-id="scene-primary"]{{background:linear-gradient(135deg,{primary_color},#244D7D);padding:{panel_padding}px;}}
.scene-process .scene-card{{padding:18px;min-width:0;background:#FFF;border:1px solid #D7E3EF;border-radius:14px;}}
.scene-process[data-layout-id="scene-primary"] .scene-card h2{{color:{primary_color};}}
.scene-process[data-layout-id="scene-primary"] .scene-card p{{color:{ink};}}
.scene-process .scene-card + .scene-card{{border-top:1px solid #D7E3EF;padding-top:18px;}}
.scene-formula-terms{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:minmax(0,1fr);}}
.scene-formula-terms[data-layout-id="scene-primary"]{{background:{surface};border-color:#D7E3EF;}}
.scene-formula-terms[data-layout-id="scene-primary"] .scene-card h2{{color:{primary_color};}}
.scene-formula-terms[data-layout-id="scene-primary"] .scene-card p{{color:{ink};}}
.scene-formula-many{{grid-template-columns:repeat(3,minmax(0,1fr));}}
.scene-formula-terms .scene-card{{padding:10px 12px;background:#FFF;border:1px solid #D7E3EF;border-radius:12px;}}
.scene-formula-terms .scene-card + .scene-card{{border-top:1px solid #D7E3EF;padding-top:10px;}}
.scene-empty{{margin:auto;color:{muted};font-size:16px;text-align:center;}}
.scene-closing{{display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:visible;text-align:center;}}
.scene-closing::before{{content:"";position:absolute;inset:70px 110px;background:linear-gradient(135deg,{primary_color},#244D7D);border-radius:18px;box-shadow:0 18px 42px rgba(26,54,93,.16);}}
.scene-closing-orbit{{position:absolute;right:150px;top:62px;color:rgba(99,179,237,.16);font:260px/1 Georgia,serif;}}
.scene-closing-rule{{position:relative;width:92px;height:3px;margin-bottom:24px;background:#63B3ED;}}
.scene-closing-author{{position:relative;margin:0;color:#FFF;font-size:22px;line-height:30px;}}
.scene-closing-affiliation{{position:relative;max-width:760px;margin:14px 0 0;color:rgba(255,255,255,.76);font-size:16px;line-height:24px;}}
.scene-figure{{display:flex;align-items:center;justify-content:center;padding:12px;border:1px solid #D7E3EF;border-radius:16px;background:#FFF;}}
.scene-figure img{{max-width:100%;max-height:100%;object-fit:contain;}}
.scene-host{{display:flex;align-items:stretch;justify-content:stretch;padding:12px;border:1px solid #D7E3EF;border-radius:16px;background:#FFF;box-shadow:0 10px 28px rgba(26,54,93,.08);}}
.scene-formula{{align-items:center;justify-content:center;background:{surface};}}
.scene-byline{{position:absolute;color:{muted};font-size:16px;line-height:1.35;}}
</style></head><body><section class="slide" data-sunairum-scene-fallback="1" data-scene-composition="{composition}"{overflow_attr}>{header}{primary_html}{secondary_html}{figure_html}{host_html}{byline_html}</section></body></html>'''
