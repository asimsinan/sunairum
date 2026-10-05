"""User image-source policy: ai | both (legacy pdf/none normalized).

PDF uploads always use ``both`` (exact PDF figures/tables). Scratch may use
``ai`` for Image-engine illustration enrich into figure slots.
"""

from __future__ import annotations

from typing import Any


def normalize_image_source(value: str | None) -> str:
    """Collapse legacy values to the two product choices."""
    raw = str(value or "both").strip().casefold()
    if raw == "pdf":
        return "both"
    if raw == "none":
        return "ai"
    if raw in ("ai", "both"):
        return raw
    return "both"


def coerce_image_source_for_grounding(
    image_source: str | None,
    grounding_mode: str | None,
) -> str:
    """PDF-strict runs always place PDF assets; never keep wizard ``ai``."""
    mode = normalize_image_source(image_source)
    if str(grounding_mode or "").strip().casefold() == "pdf_strict":
        return "both"
    return mode


def normalize_ai_enrich_max_new(
    value: Any,
    *,
    grounding_mode: str | None,
    image_source: str | None,
    default_scratch: int = 3,
    cap: int = 6,
) -> int:
    """Enrich budget: PDF always 0; scratch+ai uses client value or default."""
    if str(grounding_mode or "").strip().casefold() == "pdf_strict":
        return 0
    mode = normalize_image_source(image_source)
    if mode != "ai":
        return 0
    try:
        if value is None:
            n = int(default_scratch)
        else:
            n = int(value)
    except (TypeError, ValueError):
        n = int(default_scratch)
    return max(0, min(int(cap), n))


def normalize_selected_figure_ids(value: Any) -> list[str]:
    """Stable list of PDF figure asset ids the user opted into (both mode)."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        asset = str(item or "").strip()
        if not asset or asset in seen:
            continue
        seen.add(asset)
        out.append(asset)
    return out


def normalize_selected_table_ids(value: Any) -> list[str]:
    """Stable list of PDF table ids the user opted into."""
    return normalize_selected_figure_ids(value)


def normalize_render_mode(value: str | None, default: str = "exact") -> str:
    raw = str(value or default).strip().casefold()
    if raw in ("exact", "ai_replica"):
        return raw
    return default


def visual_policy_prompt_block(
    image_source: str,
    *,
    selected_figure_ids: list[str] | None = None,
    grounding_mode: str | None = None,
) -> str:
    """Short brief fragment for content / aesthetic / storyboard / figure prompts."""
    mode = coerce_image_source_for_grounding(image_source, grounding_mode)
    selected = normalize_selected_figure_ids(selected_figure_ids)
    if mode == "ai":
        return (
            "Visual mode: scratch + AI illustrations. Reserve empty figure slots "
            "(data-sunairum-figure-slot) on content slides that benefit from a "
            "raster illustration; the Image engine may fill those slots later. "
            "Author charts, diagrams, and tables as Constrained HTML hosts "
            "(table/chart/formula/figure); Intent fills empty hosts — "
            "do not invent PDF crops."
        )
    if selected:
        ids = ", ".join(selected[:24])
        more = f" (+{len(selected) - 24} more)" if len(selected) > 24 else ""
        return (
            "Visual mode: PDF assets. Prefer user-selected PDF figures/tables for "
            f"bound slides (eligible figures: {ids}{more}). Do not invent "
            "replacement raster illustrations for unbound slides."
        )
    return (
        "Visual mode: PDF assets. Prefer extracted PDF figures/tables when bound. "
        "All extracted figures are eligible when no explicit selection was made. "
        "Do not invent replacement raster illustrations for unbound slides."
    )
