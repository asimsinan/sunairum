"""Precompute reserved table band size from payload (cols × rows)."""

from __future__ import annotations

from typing import Any


def table_footprint_from_payload(
    payload: dict[str, Any] | None,
    *,
    preferred: tuple[float, float, float, float] = (588.0, 160.0, 632.0, 440.0),
) -> dict[str, float]:
    """Return soft x,y,w,h for Executor empty-slot reservation."""
    px, py, pw, ph = preferred
    data = payload if isinstance(payload, dict) else {}
    headers = data.get("headers") or data.get("columns") or []
    rows = data.get("rows") or []
    ncols = max(1, len(headers) if isinstance(headers, list) else 1)
    nrows = max(1, len(rows) if isinstance(rows, list) else 1)
    # Cell budget from wrap-aware mins (align with native budget floors).
    need_w = min(1100.0, max(320.0, 48.0 + ncols * 96.0))
    need_h = min(520.0, max(200.0, 56.0 + (nrows + 1) * 44.0 + 40.0))
    try:
        from tasks.table_native_budget import content_row_required_pt

        rows = data.get("rows") or []
        if isinstance(rows, list) and rows:
            style = data.get("style") if isinstance(data.get("style"), dict) else {}
            _req, total_pt, _fits = content_row_required_pt(
                rows,
                table_width_px=need_w,
                table_height_px=need_h,
                style=style or {"font_size": 14, "header_font_size": 15},
                column_widths=data.get("column_widths"),
            )
            need_h = max(need_h, min(520.0, (total_pt / 0.75) + 24.0))
    except Exception:
        pass
    w = min(pw, max(need_w, pw * 0.85))
    h = min(max(ph, need_h), max(need_h, min(520.0, need_h + 24.0)))
    h = min(520.0, max(160.0, h))
    # Prefer right column when wide; keep title band free (y≥160).
    x = max(48.0, min(px, 1280.0 - w - 48.0))
    y = max(160.0, py)
    if y + h > 660.0:
        h = max(160.0, 660.0 - y - 16.0)
    return {"x": x, "y": y, "w": w, "h": h}


def footprint_prompt_line(band: dict[str, float] | None, table_id: str) -> str:
    """HTML host hint (zero-SVG). Legacy SVG group markup removed from prompts."""
    if not band:
        return (
            f'Empty HTML host for id `{table_id}`: '
            f'<div data-pptx="table" data-table-id="{table_id}" '
            f'style="position:absolute;left:520px;top:160px;width:700px;height:400px;"></div>. '
            f"Never invent cell text.\n"
        )
    return (
        f"Empty HTML table host for id `{table_id}`:\n"
        f'  <div data-pptx="table" data-table-id="{table_id}" '
        f'style="position:absolute;left:{band["x"]:g}px;top:{band["y"]:g}px;'
        f'width:{band["w"]:g}px;height:{band["h"]:g}px;"></div>\n'
        "Never invent cell text. Intent fills native a:tbl. "
        "Narrative/callouts OUTSIDE this AABB.\n"
    )
