"""Soft composition hints for Executor — no hard AABB recipe stamping."""

from __future__ import annotations

import re
from typing import Any

# Soft pattern labels (prompt fuel only — never exclusive region law).
SOFT_SPLIT_TABLE = "table_takeaway"
SOFT_SPLIT_FIGURE = "figure_legend"
SOFT_PROCESS_FLOW = "process_flow"
SOFT_STACK_CARDS = "kpi_cards"
SOFT_FORMULA_HERO = "formula_band"
SOFT_CHART_SIDEBAR = "chart_sidebar"
SOFT_FREE_CANVAS = "free_composition"
SOFT_TWO_COLUMN = "comparison_columns"

# Back-compat aliases used by older tests / logs.
MODE_SPLIT_TABLE = "split_table"
MODE_SPLIT_FIGURE = "split_figure"
MODE_PROCESS_FLOW = "process_flow"
MODE_STACK_CARDS = "stack_cards"
MODE_FORMULA_HERO = "formula_hero"
MODE_CHART_SIDEBAR = "chart_sidebar"
MODE_FREE_CANVAS = "free_canvas"
MODE_TWO_COLUMN_TAKEAWAY = "two_column_takeaway"

MODE_NAMES = frozenset(
    {
        MODE_SPLIT_TABLE,
        MODE_SPLIT_FIGURE,
        MODE_PROCESS_FLOW,
        MODE_STACK_CARDS,
        MODE_FORMULA_HERO,
        MODE_CHART_SIDEBAR,
        MODE_FREE_CANVAS,
        MODE_TWO_COLUMN_TAKEAWAY,
    }
)

_TYPOGRAPHY_FORMULA_RE = re.compile(
    r"(?i)\b(georgia|arial|helvetica|inter|roboto|font(?:-family)?|typeface|"
    r"monospaced|sans-serif|serif|spacing where useful)\b"
)
_PROCESS_RE = re.compile(
    r"(?i)\b(process|pipeline|numbered stages?|step chips|destroy.?and.?repair)\b"
)
_CHART_RE = re.compile(r"(?i)\b(chart|bar(?:s)?|plot|metrics comparison)\b")
_COMPARE_RE = re.compile(
    r"(?i)\b(ablation|kpi|compare|comparison|two[- ]column|pillars|versus)\b"
)


def _pack_section_ix(pack: str) -> str:
    if not pack:
        return ""
    match = re.search(r"(?im)^##\s*IX\.?\s*Content Outline\s*$", pack)
    if not match:
        if re.search(r"(?im)^###\s*P\d+", pack):
            return pack
        return pack
    rest = pack[match.end() :]
    end = re.search(r"(?im)^##\s*X\.?\s+", rest)
    return rest[: end.start()] if end else rest


def _ix_field(pack: str, field: str) -> str:
    if not pack:
        return ""
    scope = _pack_section_ix(pack)
    match = re.search(
        rf"(?im)^\s*[-*]\s*\*\*{re.escape(field)}:?\*\*\s*:?\s*(.+)$",
        scope,
    )
    return match.group(1).strip() if match else ""


def is_typography_formula_leak(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    return bool(_TYPOGRAPHY_FORMULA_RE.search(raw))


def resolve_soft_pattern(slide: dict[str, Any], *, pack: str = "") -> str:
    """Soft visualization/pattern hint for the Executor prompt (not a recipe)."""
    if str(slide.get("visualization") or "").strip():
        return str(slide.get("visualization")).strip()
    role = str(slide.get("role") or "content").strip().casefold()
    if role in {"title", "hero", "closing"}:
        return SOFT_FREE_CANVAS
    table_id = str(slide.get("table_id") or "").strip()
    figure_id = str(slide.get("figure_id") or "").strip()
    if figure_id.casefold() in {"", "none", "null", "n/a", "-"}:
        figure_id = ""
    if table_id.casefold() in {"", "none", "null", "n/a", "-"}:
        table_id = ""
    if table_id:
        return SOFT_SPLIT_TABLE
    if figure_id:
        return SOFT_SPLIT_FIGURE
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    formula = (
        str(slide.get("formula") or "").strip()
        or str(content.get("FORMULA") or "").strip()
        or _ix_field(pack, "Formula")
    )
    if formula and is_typography_formula_leak(formula):
        formula = ""
    if formula:
        return SOFT_FORMULA_HERO
    intent = " ".join(
        [
            str(slide.get("layout_intent") or ""),
            str(slide.get("visual_job") or ""),
            str(slide.get("page_role") or ""),
            _ix_field(pack, "Layout"),
        ]
    )
    if _PROCESS_RE.search(intent):
        return SOFT_PROCESS_FLOW
    if _CHART_RE.search(intent):
        return SOFT_CHART_SIDEBAR
    if _COMPARE_RE.search(intent):
        return SOFT_TWO_COLUMN
    return SOFT_FREE_CANVAS


def resolve_executor_mode(slide: dict[str, Any], *, pack: str = "") -> str:
    """Legacy name → soft pattern (no layout_recipe stamp)."""
    pattern = resolve_soft_pattern(slide, pack=pack)
    reverse = {
        SOFT_SPLIT_TABLE: MODE_SPLIT_TABLE,
        SOFT_SPLIT_FIGURE: MODE_SPLIT_FIGURE,
        SOFT_PROCESS_FLOW: MODE_PROCESS_FLOW,
        SOFT_STACK_CARDS: MODE_STACK_CARDS,
        SOFT_FORMULA_HERO: MODE_FORMULA_HERO,
        SOFT_CHART_SIDEBAR: MODE_CHART_SIDEBAR,
        SOFT_FREE_CANVAS: MODE_FREE_CANVAS,
        SOFT_TWO_COLUMN: MODE_TWO_COLUMN_TAKEAWAY,
    }
    return reverse.get(pattern, MODE_FREE_CANVAS)


def apply_soft_pattern(slide: dict[str, Any], mode: str = "") -> dict[str, Any]:
    """Soft-only: set visualization hint; never stamp layout AABBs."""
    pattern = str(slide.get("visualization") or "").strip()
    if not pattern:
        pattern = resolve_soft_pattern(slide)
    slide["visualization"] = pattern
    if mode:
        slide["executor_mode"] = mode if mode in MODE_NAMES else MODE_FREE_CANVAS
    else:
        slide["executor_mode"] = resolve_executor_mode(slide)
    # Clear hard recipe authorship leftovers.
    slide.pop("layout_recipe", None)
    return slide


def soft_pattern_brief(pattern: str) -> str:
    """Defaults-style soft guidance (may override when Layout asks)."""
    tips = {
        SOFT_SPLIT_TABLE: (
            "JOB: make the table finding readable — surface insights beside the grid. "
            "COMPOSITION (HTML): LEFT claim column "
            "(data-sunairum-claim stack; left≈60; width≤500; ends ≤560) + EMPTY RIGHT "
            'table host <div data-pptx="table" data-table-id="…" '
            'style="position:absolute;left:640px;top:140px;width:580px;height:480px;">. '
            "Gap between claims and table ≥28px. GUARDRAILS: never invent cells; never "
            "overlap the table host onto claims; pipeline fills polished HTML + native a:tbl. "
            "Claim cards use min-height + padding — no clipped multi-line body text."
        ),
        SOFT_SPLIT_FIGURE: (
            "JOB: explain the figure. COMPOSITION (HTML): LEFT claim column "
            "(data-sunairum-claim stack; left≈60; width≤500; ends ≤560) + EMPTY RIGHT "
            'figure host <div data-pptx="figure" data-figure-id="…" '
            'style="position:absolute;left:640px;top:140px;width:560px;height:480px;">. '
            "Gap between claims and figure ≥28px (leave room for host shadow). "
            "Left panel must fit the remaining lane — never widen claims under the figure. "
            "Use accent_tint panel + secondary_accent mark on claims. "
            "GUARDRAILS: no invented image src; no SVG; never overlap the figure host onto claims."
        ),
        SOFT_PROCESS_FLOW: (
            "JOB: readable step sequence. COMPOSITION (HTML): peer flex cards with shared "
            "title rhythm; motif mid / body bottom."
        ),
        SOFT_STACK_CARDS: (
            "JOB: KPI readout. COMPOSITION (HTML): accent_tint cards + secondary_accent signal."
        ),
        SOFT_FORMULA_HERO: (
            "JOB: show what the equation does with per-symbol explanations. COMPOSITION (HTML): "
            "title/eyebrow/optional subtitle in a flex header with min-height (never a short fixed "
            "height that clips into the formula); full-width compact empty data-pptx=\"formula\" "
            "band (~96px tall) under the title block; UNDER the band a two-column row — optional "
            "1–2 short takeaways on the LEFT only if needed; RIGHT (or 2×N grid spanning the lower "
            "canvas) holds one card per equation symbol/term (symbol label + ≤2 short sentences "
            "from FORMULA_TERMS/GLOSS). Ban empty right half when terms exist. Never paint TeX as "
            "HTML text inside the host. Never let title/subtitle sit behind the formula plate."
        ),
        SOFT_CHART_SIDEBAR: (
            "JOB: chart + interpretation. COMPOSITION (HTML): EMPTY "
            '<div data-pptx="chart" data-chart-id="…"> host + aside claims. '
            "Never CSS bar charts — Intent fills native c:chart."
        ),
        SOFT_TWO_COLUMN: "Comparison columns (HTML flex) — distinct left/right jobs.",
        SOFT_FREE_CANVAS: (
            "Free HTML composition — one visual job; Fill Contract vivid; no SVG."
        ),
    }
    # MODE_* log aliases map onto SOFT tips (no duplicate tip strings).
    mode_alias = {
        MODE_SPLIT_TABLE: SOFT_SPLIT_TABLE,
        MODE_SPLIT_FIGURE: SOFT_SPLIT_FIGURE,
        MODE_PROCESS_FLOW: SOFT_PROCESS_FLOW,
        MODE_STACK_CARDS: SOFT_STACK_CARDS,
        MODE_FORMULA_HERO: SOFT_FORMULA_HERO,
        MODE_CHART_SIDEBAR: SOFT_CHART_SIDEBAR,
        MODE_TWO_COLUMN_TAKEAWAY: SOFT_TWO_COLUMN,
        MODE_FREE_CANVAS: SOFT_FREE_CANVAS,
    }
    key = mode_alias.get(pattern, pattern)
    return tips.get(key, tips[SOFT_FREE_CANVAS])
