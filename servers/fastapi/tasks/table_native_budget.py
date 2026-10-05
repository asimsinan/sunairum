"""Converter-true native table content height budget (points).

Matches native table wrap math so pre-compile fit and Intent footprint
agree with PPTX compile.
"""

from __future__ import annotations

import html
import json
import math
import re
from typing import Any

# 1 SVG px → 0.75 pt (EMU_PER_PX=9525, 12700 EMU/pt).
_PX_TO_PT = 0.75
_FOOTER_TOP = 660.0
_MARGIN = 16.0
_MIN_FONT = 11.0
_MIN_HEADER_FONT = 12.0

_TABLE_META_RE = re.compile(
    r'(<g\b[^>]*data-pptx-replace-with=["\']table["\'][^>]*>.*?<metadata\b[^>]*>)'
    r"(.*?)"
    r"(</metadata>)",
    flags=re.I | re.S,
)
_TABLE_GROUP_RE = re.compile(
    r'<g\b([^>]*\bdata-pptx-replace-with=["\']table["\'][^>]*)>([\s\S]*?)</g>',
    flags=re.I,
)


def _cell_text(cell: Any) -> str:
    if isinstance(cell, dict):
        return str(cell.get("text", "") or "")
    return str(cell or "")


def content_row_required_pt(
    rows: list[Any],
    *,
    table_width_px: float,
    table_height_px: float,
    style: dict[str, Any] | None = None,
    column_widths: list[Any] | None = None,
    header_rows: int = 1,
) -> tuple[list[float], float, bool]:
    """Return (per_row_pt, required_total_pt, fits) using converter pt math."""
    if not rows or table_width_px <= 0 or table_height_px <= 0:
        return [], 0.0, True
    style = style if isinstance(style, dict) else {}
    font_px = max(float(style.get("font_size") or 18), 1.0)
    header_px = max(float(style.get("header_font_size") or font_px), 1.0)
    font_pt = font_px * _PX_TO_PT
    header_pt = header_px * _PX_TO_PT
    padding = style.get("padding") if isinstance(style.get("padding"), dict) else {}
    h_pad = (
        float(padding.get("left", 12)) * _PX_TO_PT
        + float(padding.get("right", 12)) * _PX_TO_PT
    )
    v_pad = (
        float(padding.get("top", 6)) * _PX_TO_PT
        + float(padding.get("bottom", 6)) * _PX_TO_PT
    )
    n_cols = 0
    for row in rows:
        if isinstance(row, list):
            n_cols = max(n_cols, len(row))
    n_cols = max(1, n_cols)
    col_w = list(column_widths or [1.0] * n_cols)
    if len(col_w) != n_cols:
        col_w = (col_w + [1.0] * n_cols)[:n_cols]
    col_total = max(sum(float(c) for c in col_w), 1.0)
    table_w_pt = table_width_px * _PX_TO_PT
    table_h_pt = table_height_px * _PX_TO_PT
    required: list[float] = []
    for row_index, row in enumerate(rows):
        row_required = 0.0
        cells = row if isinstance(row, list) else [row]
        for col_index, cell in enumerate(cells):
            text = _cell_text(cell)
            cell_pt = header_pt if row_index < header_rows else font_pt
            cell_width = table_w_pt * float(col_w[col_index]) / col_total
            chars_per_line = max(
                1,
                int(max(cell_width - h_pad, 1) / max(cell_pt * 0.53, 1)),
            )
            line_count = max(
                1,
                sum(
                    max(1, (len(line) + chars_per_line - 1) // chars_per_line)
                    for line in text.splitlines() or [""]
                ),
            )
            row_required = max(
                row_required, line_count * cell_pt * 1.3 + v_pad
            )
        required.append(row_required)
    total = sum(required)
    fits = total <= table_h_pt + 1.0
    return required, total, fits


def fit_table_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Grow / shrink font / truncate until content fits footer-capped height."""
    data = dict(payload) if isinstance(payload, dict) else {}
    columns = data.get("columns") or data.get("headers") or []
    rows = data.get("rows") or []
    if not isinstance(rows, list) or not rows:
        return data
    style = dict(data.get("style") or {}) if isinstance(data.get("style"), dict) else {}
    if "font_size" not in style:
        style["font_size"] = float(data.get("font_size") or 15)
    if "header_font_size" not in style:
        style["header_font_size"] = float(data.get("header_font_size") or style["font_size"])
    data["style"] = style
    width = float(data.get("width") or 0)
    height = float(data.get("height") or 0)
    y = float(data.get("y") or 160)
    x = float(data.get("x") or 588)
    if width <= 0:
        width = 624.0
        data["width"] = width
    if height <= 0:
        height = 320.0
        data["height"] = height
    col_w = data.get("column_widths")
    header_rows = int(data.get("header_rows") or 1)

    def _budget(h: float, st: dict[str, Any]) -> tuple[list[float], float, bool]:
        return content_row_required_pt(
            rows,
            table_width_px=width,
            table_height_px=h,
            style=st,
            column_widths=col_w if isinstance(col_w, list) else None,
            header_rows=header_rows,
        )

    max_h = max(height, min(_FOOTER_TOP - y - _MARGIN, 520.0))
    required, total, fits = _budget(height, style)
    if not fits:
        # Grow height first (px): total_pt / 0.75
        need_px = (total / _PX_TO_PT) + 8.0
        height = min(max_h, max(height, need_px))
        data["height"] = height
        required, total, fits = _budget(height, style)

    while not fits and float(style.get("font_size") or 18) > _MIN_FONT:
        style["font_size"] = max(_MIN_FONT, float(style["font_size"]) - 1.0)
        style["header_font_size"] = max(
            _MIN_HEADER_FONT, float(style.get("header_font_size") or style["font_size"]) - 1.0
        )
        required, total, fits = _budget(height, style)

    # Truncate longest cell texts if still short.
    guard = 0
    while not fits and guard < 40:
        guard += 1
        longest_i, longest_j, longest_len = -1, -1, 0
        for i, row in enumerate(rows):
            if not isinstance(row, list):
                continue
            for j, cell in enumerate(row):
                text = _cell_text(cell)
                if len(text) > longest_len and i >= header_rows:
                    longest_len = len(text)
                    longest_i, longest_j = i, j
        if longest_i < 0 or longest_len < 12:
            break
        cell = rows[longest_i][longest_j]
        text = _cell_text(cell)
        new_text = text[: max(8, len(text) - 8)].rstrip() + "…"
        if isinstance(cell, dict):
            cell = dict(cell)
            cell["text"] = new_text
            rows[longest_i][longest_j] = cell
        else:
            rows[longest_i][longest_j] = new_text
        required, total, fits = _budget(height, style)

    data["rows"] = rows
    data["style"] = style
    data["height"] = height
    data["x"] = x
    data["y"] = y
    data["width"] = width
    if required:
        # Store content-driven weights (px-equivalent ratios).
        data["row_heights"] = [max(1.0, r) for r in required]
    data["_native_budget_fits"] = fits
    data["_native_budget_required_pt"] = total
    return data


def _set_attr(attrs: str, name: str, value: str) -> str:
    pat = re.compile(rf'\s*{re.escape(name)}="[^"]*"', flags=re.I)
    cleaned = pat.sub("", attrs or "")
    return f'{cleaned} {name}="{value}"'


def _set_first_rect_size(body: str, width: float, height: float) -> str:
    """Replace width/height on the first <rect> without corrupting other attrs."""
    match = re.search(r"<rect\b([^>]*)>", body or "", flags=re.I)
    if not match:
        return body or ""
    attrs = _set_attr(match.group(1) or "", "width", f"{width:g}")
    attrs = _set_attr(attrs, "height", f"{height:g}")
    tag = f"<rect{attrs}>"
    return body[: match.start()] + tag + body[match.end() :]


def sync_table_host_rect(svg: str, payload: dict[str, Any]) -> str:
    """Update outer rect height/width and transform to match fitted payload."""
    if not svg or not isinstance(payload, dict):
        return svg or ""
    width = float(payload.get("width") or 0)
    height = float(payload.get("height") or 0)
    x = float(payload.get("x") or 0)
    y = float(payload.get("y") or 0)
    if width <= 0 or height <= 0:
        return svg

    def _replace(match: re.Match[str]) -> str:
        attrs, body = match.group(1) or "", match.group(2) or ""
        new_attrs = _set_attr(attrs, "transform", f"translate({x:g},{y:g})")
        if new_attrs and not new_attrs[:1].isspace():
            new_attrs = f" {new_attrs}"
        new_body = _set_first_rect_size(body, width, height)
        return f"<g{new_attrs}>{new_body}</g>"

    return _TABLE_GROUP_RE.sub(_replace, svg, count=1)


def fit_native_tables_in_svg(svg: str) -> str:
    """Fit every native table carrier metadata + sync host rect."""

    def _replace(match: re.Match[str]) -> str:
        prefix, body, suffix = match.group(1), match.group(2), match.group(3)
        try:
            payload = json.loads(html.unescape(body).strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            return match.group(0)
        if not isinstance(payload, dict):
            return match.group(0)
        # Pull x/y/w/h from surrounding attrs when missing
        attrs = prefix
        tr = re.search(
            r'transform\s*=\s*"translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"',
            attrs,
            flags=re.I,
        )
        if tr:
            payload.setdefault("x", float(tr.group(1)))
            payload.setdefault("y", float(tr.group(2)))
        fitted = fit_table_payload(payload)
        encoded = json.dumps(fitted, ensure_ascii=False)
        return f"{prefix}{encoded}{suffix}"

    out = _TABLE_META_RE.sub(_replace, svg or "")
    # Sync rects for each fitted payload
    for match in _TABLE_META_RE.finditer(out):
        try:
            payload = json.loads(html.unescape(match.group(2)).strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            out = sync_table_host_rect(out, payload)
    return out
