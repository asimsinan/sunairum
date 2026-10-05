"""Build TableRenderSpec (sample1s.json shape) from Intent + Style + AABB."""

from __future__ import annotations

from typing import Any

from tasks.style_resolver import resolve_style_tokens
from tasks.table_analyzer import template_insight


def _view_matrix(
    analysis: dict[str, Any], intent: dict[str, Any]
) -> tuple[list[str], list[list[str]]]:
    columns = list(analysis.get("columns") or [])
    matrix = [list(r) for r in (analysis.get("matrix") or [])]
    content = intent.get("content") if isinstance(intent.get("content"), dict) else {}
    if isinstance(content.get("columns"), list) and content["columns"]:
        keep = [c for c in content["columns"] if c in columns]
        if keep:
            idxs = [columns.index(c) for c in keep]
            columns = keep
            matrix = [[row[i] if i < len(row) else "" for i in idxs] for row in matrix]
    top_k = content.get("top_k")
    if isinstance(top_k, int) and top_k > 0:
        matrix = matrix[:top_k]
    elif not content.get("show_all_rows", True) and len(matrix) > 8:
        matrix = matrix[:8]
    return columns, matrix


def _column_align(name: str, index: int, analysis: dict[str, Any]) -> str:
    """left for label col; center for numeric; left for other text."""
    if index == 0:
        return "left"
    stats = {
        str(s.get("name")): s
        for s in (analysis.get("column_stats") or [])
        if isinstance(s, dict)
    }
    st = stats.get(name)
    if st and st.get("dtype") == "number":
        return "center"
    return "left"


def _highlight_cells(
    analysis: dict[str, Any],
    intent: dict[str, Any],
    columns: list[str],
    matrix: list[list[str]],
    col_meta: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    emph = intent.get("emphasis") if isinstance(intent.get("emphasis"), dict) else {}
    rules = emph.get("rules") if isinstance(emph.get("rules"), list) else []
    stats = {
        str(s.get("name")): s
        for s in (analysis.get("column_stats") or [])
        if isinstance(s, dict)
    }
    # Map original row indices — view may truncate; match by row content
    full = analysis.get("matrix") or []
    highlights: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        col = str(rule.get("column") or "")
        if col not in columns:
            continue
        st = stats.get(col)
        if not st or st.get("dtype") != "number":
            continue
        direction = str(rule.get("direction") or "min")
        ri_full = int(st["min_row"] if direction == "min" else st["max_row"])
        if ri_full < 0 or ri_full >= len(full):
            continue
        target_row = full[ri_full]
        # find in view
        for ri, row in enumerate(matrix):
            if row and target_row and row[0] == target_row[0]:
                ci = columns.index(col)
                meta = col_meta[ci] if ci < len(col_meta) else {}
                highlights.append(
                    {
                        "row": ri,
                        "col": ci,
                        "text": row[ci] if ci < len(row) else "",
                        "style": "highlight",
                        "x": meta.get("x"),
                        "y": None,  # filled in build
                        "width": meta.get("width"),
                        "height": None,
                    }
                )
                break
    return highlights


def build_table_render_spec(
    analysis: dict[str, Any],
    intent: dict[str, Any],
    *,
    aabb: tuple[float, float, float, float],
    theme: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """sample1s-shaped RenderSpec. Canvas height is content-sized, top-aligned in AABB."""
    x, y, w, h = aabb
    strat = intent.get("strategy") if isinstance(intent.get("strategy"), dict) else {}
    mode = str(strat.get("mode") or "full_table")
    tokens = resolve_style_tokens(
        style=str(strat.get("style") or "academic"),
        density=str(strat.get("density") or ""),
        theme=theme,
    )
    columns, matrix = _view_matrix(analysis, intent)
    n_cols = max(1, len(columns))
    label_w = min(390.0, w * 0.28)
    rest = max(40.0, w - label_w - 16)
    num_w = rest / max(1, n_cols - 1) if n_cols > 1 else rest
    col_meta: list[dict[str, Any]] = []
    cx = x + 8
    for i, name in enumerate(columns):
        width = label_w if i == 0 else num_w
        col_meta.append(
            {
                "name": name,
                "x": cx,
                "width": width,
                "align": _column_align(name, i, analysis),
            }
        )
        cx += width

    row_h = float(tokens.get("row_height") or 52)
    header_h = row_h
    insight_cfg = intent.get("insight") if isinstance(intent.get("insight"), dict) else {}
    insight_enabled = bool(insight_cfg.get("enabled", True))
    # Always reserve insight band for table_with_insight.
    if mode == "table_with_insight":
        insight_enabled = True
    insight_intent = {
        **intent,
        "insight": {**insight_cfg, "enabled": insight_enabled},
    }
    insight_text = template_insight(analysis, insight_intent) if insight_enabled else ""
    insight_h = 36.0 if insight_enabled else 0.0
    avail = max(row_h * 2, h - insight_h - 8)
    max_rows = max(1, int(avail // row_h) - 1)
    if len(matrix) > max_rows:
        matrix = matrix[:max_rows]

    # Content-sized painted height (empty space stays below for slide callouts).
    painted_h = header_h + len(matrix) * row_h + insight_h + 8.0
    painted_h = min(float(h), max(header_h + row_h + insight_h, painted_h))

    highlights = _highlight_cells(analysis, intent, columns, matrix, col_meta)
    cells_out: list[dict[str, Any]] = []
    for hi in highlights:
        ri, ci = int(hi["row"]), int(hi["col"])
        meta = col_meta[ci]
        cells_out.append(
            {
                "cell_id": f"{analysis.get('table_id')}-r{ri:03d}-c{ci:03d}",
                "x": meta["x"],
                "y": y + header_h + ri * row_h,
                "width": meta["width"],
                "height": row_h,
                "text": hi.get("text") or "",
                "style": "highlight",
                "row": ri,
                "col": ci,
            }
        )

    return {
        "table_id": str(analysis.get("table_id") or intent.get("table_id") or ""),
        "mode": mode,
        "canvas": {"x": x, "y": y, "width": w, "height": painted_h},
        "columns": col_meta,
        "rows": {"height": row_h, "data": matrix},
        "header_height": header_h,
        "cells": cells_out,
        "theme": {
            "font": theme.get("font")
            or tokens.get("body_family")
            or tokens.get("font_family")
            or "Arial",
            "header_size": theme.get("header_size") or tokens.get("header_size") or 15,
            "body_size": theme.get("body_size") or tokens.get("cell_size") or 13,
            "primary": theme.get("header_fill")
            or theme.get("primary")
            or tokens.get("primary"),
            "accent": theme.get("accent") or tokens.get("accent"),
            "ink": theme.get("ink") or tokens.get("ink"),
            "muted": theme.get("muted") or tokens.get("muted"),
            "surface": theme.get("surface") or tokens.get("surface") or "#FFFFFF",
            "zebra": theme.get("zebra") or tokens.get("zebra"),
            "border": theme.get("border") or tokens.get("border") or "#E2E8F0",
            "header_fill": theme.get("header_fill")
            or theme.get("primary")
            or tokens.get("primary"),
            "header_color": theme.get("header_color") or "#FFFFFF",
        },
        "insight": {
            "text": insight_text,
            "position": insight_cfg.get("position") or "bottom",
            "enabled": insight_enabled,
        },
        "view_note": (
            f"showing {len(matrix)} of {analysis.get('row_count')} rows"
            if len(matrix) < int(analysis.get("row_count") or 0)
            else ""
        ),
    }
