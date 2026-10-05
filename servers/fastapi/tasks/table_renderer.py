"""Render TableRenderSpec → SVG fragment (deterministic bars for ranked modes)."""

from __future__ import annotations

import html
import json
import re
from typing import Any, Callable


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def _esc_attr(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _mix_hex(fg: str, bg: str = "#FFFFFF", alpha: float = 0.28) -> str:
    """Solid wash approximating translucent accent over white (for PPTX fills)."""

    def _rgb(h: str) -> tuple[int, int, int]:
        s = (h or "").lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        if len(s) != 6:
            return (224, 122, 47)
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)

    fr, fg_, fb = _rgb(fg)
    br, bg_, bb = _rgb(bg)
    a = max(0.0, min(1.0, alpha))
    r = int(round(fr * a + br * (1 - a)))
    g = int(round(fg_ * a + bg_ * (1 - a)))
    b = int(round(fb * a + bb * (1 - a)))
    return f"#{r:02X}{g:02X}{b:02X}"


def _align_svg(align: str) -> str:
    a = str(align or "left").strip().casefold()
    if a in {"center", "middle", "ctr"}:
        return "middle"
    if a in {"right", "end", "r"}:
        return "end"
    return "start"


def _align_native(align: str) -> str:
    a = str(align or "left").strip().casefold()
    if a in {"center", "middle", "ctr"}:
        return "ctr"
    if a in {"right", "end", "r"}:
        return "r"
    return "l"


def render_spec_to_native_payload(spec: dict[str, Any]) -> dict[str, Any]:
    """Project RenderSpec styles into native PPTX table metadata (one source of truth)."""
    canvas = spec.get("canvas") or {}
    x = float(canvas.get("x") or 0)
    y = float(canvas.get("y") or 0)
    w = float(canvas.get("width") or 400)
    h = float(canvas.get("height") or 200)
    cols = spec.get("columns") if isinstance(spec.get("columns"), list) else []
    rows_meta = spec.get("rows") if isinstance(spec.get("rows"), dict) else {}
    matrix = rows_meta.get("data") if isinstance(rows_meta.get("data"), list) else []
    theme = spec.get("theme") if isinstance(spec.get("theme"), dict) else {}
    primary = str(theme.get("header_fill") or theme.get("primary") or "#0B3B6F")
    accent = str(theme.get("accent") or "#E07A2F")
    ink = str(theme.get("ink") or "#0F172A")
    surface = str(theme.get("surface") or "#FFFFFF")
    zebra = str(theme.get("zebra") or "#F5F7FA")
    highlight_fill = _mix_hex(accent, surface, 0.28)
    header_color = str(theme.get("header_color") or "#FFFFFF")
    tid = str(spec.get("table_id") or "")

    hi_cells = {
        (int(c["row"]), int(c["col"]))
        for c in (spec.get("cells") or [])
        if isinstance(c, dict)
        and c.get("style") == "highlight"
        and "row" in c
        and "col" in c
    }

    native_columns = [
        {
            "text": str(col.get("name") or ""),
            "fill": primary,
            "color": header_color,
            "bold": True,
            "align": _align_native(str(col.get("align") or "left")),
        }
        for col in cols
        if isinstance(col, dict)
    ]
    native_rows: list[list[dict[str, Any]]] = []
    for ri, row in enumerate(matrix):
        if not isinstance(row, list):
            continue
        cells: list[dict[str, Any]] = []
        for ci, col in enumerate(cols):
            if not isinstance(col, dict):
                continue
            text = str(row[ci]) if ci < len(row) else ""
            is_hi = (ri, ci) in hi_cells
            cell: dict[str, Any] = {
                "text": text,
                "align": _align_native(str(col.get("align") or "left")),
                "color": ink,
                "fill": highlight_fill if is_hi else (zebra if ri % 2 else surface),
            }
            if is_hi:
                cell["bold"] = True
            cells.append(cell)
        if cells:
            native_rows.append(cells)

    # Grid height excludes insight sibling (insight is outside replace group).
    insight = spec.get("insight") if isinstance(spec.get("insight"), dict) else {}
    insight_reserved = 36.0 if insight.get("enabled") else 0.0
    grid_h = max(40.0, h - insight_reserved)
    resolved_rows = (1 if native_columns else 0) + len(native_rows)
    resolved_cols = len(native_columns) or max(
        (len(r) for r in native_rows), default=0
    )
    return {
        "x": x,
        "y": y,
        "width": w,
        "height": grid_h,
        "source_table_id": tid,
        "columns": native_columns,
        "rows": native_rows,
        "row_heights": [1] * max(1, resolved_rows),
        "column_widths": [1] * max(1, resolved_cols),
        "header_fill": primary,
        "header_color": header_color,
    }


def render_ranked_bars_svg(
    series: list[tuple[str, float]],
    *,
    aabb: tuple[float, float, float, float],
    theme: dict[str, Any] | None = None,
    title: str = "",
) -> str:
    """Deterministic horizontal bar chart from (label, value) series."""
    theme = theme or {}
    x, y, w, h = aabb
    primary = str(theme.get("primary") or "#0B3B6F")
    accent = str(theme.get("accent") or "#E07A2F")
    ink = str(theme.get("ink") or "#0F172A")
    muted = str(theme.get("muted") or "#4A5568")
    surface = str(theme.get("surface") or "#FFFFFF")
    if not series:
        return ""
    pad = 16.0
    title_h = 36.0 if title else 0.0
    n = len(series)
    usable_h = max(40.0, h - 2 * pad - title_h)
    row_h = usable_h / max(1, n)
    max_v = max(abs(v) for _, v in series) or 1.0
    label_w = min(220.0, w * 0.32)
    bar_max = max(40.0, w - 2 * pad - label_w - 72.0)
    parts = [
        f'<g data-sunairum-source-table-chart="1" '
        f'transform="translate({x:.1f},{y:.1f})">',
        f'<rect x="0" y="0" width="{w:.1f}" height="{h:.1f}" rx="8" '
        f'fill="{surface}" stroke="#D5DEE8"/>',
    ]
    if title:
        parts.append(
            f'<text x="{pad:.1f}" y="28" font-family="Arial, sans-serif" '
            f'font-size="18" font-weight="700" fill="{primary}">'
            f"{_esc(title[:72])}</text>"
        )
    for i, (label, val) in enumerate(series):
        ry = pad + title_h + i * row_h
        mid = ry + row_h * 0.55
        bw = bar_max * (abs(val) / max_v)
        fill = accent if i == 0 else primary
        parts.append(
            f'<text x="{pad:.1f}" y="{mid:.1f}" font-family="Arial, sans-serif" '
            f'font-size="14" fill="{ink}">{_esc(str(label)[:40])}</text>'
        )
        parts.append(
            f'<rect x="{pad + label_w:.1f}" y="{ry + 8:.1f}" width="{bw:.1f}" '
            f'height="{max(12.0, row_h - 16):.1f}" rx="4" fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{pad + label_w + bw + 8:.1f}" y="{mid:.1f}" '
            f'font-family="Arial, sans-serif" font-size="13" fill="{muted}">'
            f"{_esc(f'{val:g}')}</text>"
        )
    parts.append("</g>")
    return "".join(parts)


def render_table_spec_svg(spec: dict[str, Any]) -> str:
    """Draw exact cell grid from RenderSpec; insight is a sibling outside replace group."""
    canvas = spec.get("canvas") or {}
    x = float(canvas.get("x") or 0)
    y = float(canvas.get("y") or 0)
    w = float(canvas.get("width") or 400)
    h = float(canvas.get("height") or 200)
    cols = spec.get("columns") if isinstance(spec.get("columns"), list) else []
    rows_meta = spec.get("rows") if isinstance(spec.get("rows"), dict) else {}
    matrix = rows_meta.get("data") if isinstance(rows_meta.get("data"), list) else []
    row_h = float(rows_meta.get("height") or 52)
    header_h = float(spec.get("header_height") or row_h)
    theme = spec.get("theme") if isinstance(spec.get("theme"), dict) else {}
    font = str(theme.get("font") or "Arial").split(",")[0].strip().strip('"') or "Arial"
    hs = float(theme.get("header_size") or 15)
    bs = float(theme.get("body_size") or 13)
    primary = str(theme.get("header_fill") or theme.get("primary") or "#0B3B6F")
    ink = str(theme.get("ink") or "#0F172A")
    muted = str(theme.get("muted") or "#4A5568")
    surface = str(theme.get("surface") or "#FFFFFF")
    accent = str(theme.get("accent") or "#E07A2F")
    zebra = str(theme.get("zebra") or "#F5F7FA")
    border = str(theme.get("border") or "#E2E8F0")
    header_color = str(theme.get("header_color") or "#FFFFFF")
    tid = str(spec.get("table_id") or "")
    tid_attr = _esc_attr(tid)

    hi_coords = {
        (int(c["row"]), int(c["col"]))
        for c in (spec.get("cells") or [])
        if isinstance(c, dict)
        and c.get("style") == "highlight"
        and "row" in c
        and "col" in c
    }

    insight = spec.get("insight") if isinstance(spec.get("insight"), dict) else {}
    insight_enabled = bool(insight.get("enabled")) and bool(insight.get("text"))
    insight_band = 36.0 if insight.get("enabled") else 0.0
    grid_h = max(header_h + row_h, h - insight_band)

    metadata_payload = render_spec_to_native_payload(spec)
    metadata_json = html.escape(
        json.dumps(metadata_payload, ensure_ascii=False), quote=False
    )

    parts = [
        f'<g data-sunairum-source-table-id="{tid_attr}" data-pptx-replace-with="table" '
        f'transform="translate({x:.1f},{y:.1f})">',
        f'<metadata type="application/json">{metadata_json}</metadata>',
        f'<rect x="0" y="0" width="{w:.1f}" height="{grid_h:.1f}" rx="8" '
        f'fill="{surface}" stroke="{border}" stroke-width="1"/>',
    ]
    # Header
    for col in cols:
        if not isinstance(col, dict):
            continue
        cx = float(col.get("x") or 0) - x
        cw = float(col.get("width") or 80)
        parts.append(
            f'<rect x="{cx:.1f}" y="0" width="{cw:.1f}" height="{header_h:.1f}" '
            f'fill="{primary}"/>'
        )
        anchor = _align_svg(str(col.get("align") or "left"))
        if anchor == "middle":
            tx = cx + cw / 2.0
        elif anchor == "end":
            tx = cx + cw - 8
        else:
            tx = cx + 8
        parts.append(
            f'<text data-sunairum-source-table-text="1" x="{tx:.1f}" '
            f'y="{header_h * 0.65:.1f}" text-anchor="{anchor}" '
            f'font-family="{_esc(font)}" font-size="{hs:.1f}" font-weight="700" '
            f'fill="{header_color}">{_esc(col.get("name"))}</text>'
        )

    for ri, row in enumerate(matrix):
        if not isinstance(row, list):
            continue
        ry = header_h + ri * row_h
        bg = zebra if ri % 2 else surface
        parts.append(
            f'<rect x="0" y="{ry:.1f}" width="{w:.1f}" height="{row_h:.1f}" fill="{bg}"/>'
        )
        for ci, col in enumerate(cols):
            if not isinstance(col, dict) or ci >= len(row):
                continue
            cx = float(col.get("x") or 0) - x
            cw = float(col.get("width") or 80)
            # Keep highlight washes inside the table grid (no right overhang).
            cx = max(0.0, min(cx, max(0.0, w - 4.0)))
            cw = max(4.0, min(cw, w - cx))
            text = str(row[ci])
            is_hi = (ri, ci) in hi_coords
            if is_hi:
                parts.append(
                    f'<rect x="{cx:.1f}" y="{ry:.1f}" width="{cw:.1f}" '
                    f'height="{row_h:.1f}" fill="{accent}" opacity="0.25" '
                    f'data-sunairum-table-highlight="1"/>'
                )
            anchor = _align_svg(str(col.get("align") or "left"))
            if anchor == "middle":
                tx = cx + cw / 2.0
            elif anchor == "end":
                tx = cx + cw - 8
            else:
                tx = cx + 8
            weight = ' font-weight="700"' if is_hi else ""
            parts.append(
                f'<text data-sunairum-source-table-text="1" x="{tx:.1f}" '
                f'y="{ry + row_h * 0.65:.1f}" text-anchor="{anchor}" '
                f'font-family="{_esc(font)}" font-size="{bs:.1f}"{weight} '
                f'fill="{ink}">{_esc(text)}</text>'
            )

    parts.append("</g>")

    # Insight / view_note live OUTSIDE the pptx-replace group so native swap keeps them.
    # Place inside the reserved insight band (not grid_h+22 spill past host bottom).
    note = str(spec.get("view_note") or "").strip()
    if insight_enabled or note:
        band_h = max(insight_band, 28.0)
        iy = y + max(0.0, h - band_h)
        # Prefer just under the painted grid when that still fits in the host.
        under_grid = y + grid_h + 8.0
        if under_grid + 16.0 <= y + h:
            iy = under_grid
        parts.append(
            f'<g data-sunairum-table-insight="1" transform="translate({x:.1f},{iy:.1f})">'
        )
        insight_text = ""
        if insight_enabled:
            insight_text = str((insight or {}).get("text") or "").strip()
        avail = max(80.0, w - 24.0)
        cursor_y = 0.0
        insight_box_h = max(20.0, (y + h) - iy - 4.0)
        if insight_text:
            try:
                from tasks.text_layout import BlockLayout, Line, layout_block, tspan_markup
            except ImportError:  # pragma: no cover
                from text_layout import (  # type: ignore
                    BlockLayout,
                    Line,
                    layout_block,
                    tspan_markup,
                )
            block = layout_block(
                insight_text,
                (12.0, 0.0, avail, insight_box_h),
                12.0,
                font_family=font,
                bold=False,
                line_height_factor=1.25,
            )
            kept = tuple(block.lines[: max(1, block.max_lines)] or block.lines[:1])
            if block.overflow_lines > 0 and kept:
                last = kept[-1]
                text = last.text.rstrip()
                if not text.endswith("…"):
                    text = text[: max(1, len(text) - 1)].rstrip() + "…"
                kept = kept[:-1] + (Line(text=text, width=last.width),)
            kept_layout = BlockLayout(
                lines=kept,
                font_size=block.font_size,
                line_height=block.line_height,
                max_lines=max(block.max_lines, len(kept)),
            )
            body = tspan_markup(kept_layout, 12.0)
            parts.append(
                f'<text data-sunairum-source-table-text="1" x="12" y="0" '
                f'font-family="{_esc(font)}" font-size="12" '
                f'fill="{muted}">{body}</text>'
            )
            cursor_y = max(14.0, kept_layout.height)
        if note:
            # Stack under insight — never share a baseline (avoids end∩start pile-up).
            note_y = cursor_y + (4.0 if insight_text else 0.0)
            parts.append(
                f'<text data-sunairum-source-table-text="1" x="12" y="{note_y:.1f}" '
                f'font-family="{_esc(font)}" '
                f'font-size="10" fill="{muted}">{_esc(note)}</text>'
            )
        parts.append("</g>")
    return "".join(parts)


def _attr_float(attrs: str, name: str) -> float | None:
    match = re.search(rf'\b{name}="([-\d.]+)"', attrs or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _clear_freehand_in_aabb(
    svg: str, aabb: tuple[float, float, float, float]
) -> str:
    """Remove freehand shapes AND text inside the table AABB before Intent inject."""
    if not svg or "<svg" not in svg.casefold():
        return svg or ""
    ax, ay, aw, ah = aabb
    ar = ax + aw
    ab = ay + ah

    def _inside(x: float, y: float, w: float = 0.0, h: float = 0.0) -> bool:
        return not (x + w < ax + 8 or y + h < ay + 8 or x > ar - 8 or y > ab - 8)

    def _protected(attrs: str) -> bool:
        low = (attrs or "").casefold()
        return any(
            token in low
            for token in (
                "data-sunairum-page-number",
                "data-sunairum-source-table",
                "data-sunairum-table-",
                "data-pptx-replace-with",
                "data-sunairum-formula",
                "data-sunairum-figure",
                "data-sunairum-table-insight",
                "data-sunairum-table-aside",
                "data-sunairum-claim-shell",
                "data-region-id",
                "data-sunairum-chip-",
                "data-sunairum-placed-widget",
                "data-sunairum-diagram-widget",
            )
        )

    def _inside_protected_group(pos: int) -> bool:
        """Skip Intent insight/aside/source-table trees (attrs alone miss local text)."""
        head = (svg or "")[:pos]
        # Last open of a protected group before pos that hasn't closed.
        for marker in (
            'data-sunairum-table-insight',
            'data-sunairum-table-aside',
            'data-pptx-replace-with="table"',
            "data-sunairum-source-table",
            "data-sunairum-claim-shell",
            "data-sunairum-placed-widget",
            "data-sunairum-chip-widget",
            "data-sunairum-diagram-widget",
        ):
            idx = head.rfind(marker)
            if idx < 0:
                continue
            g_open = head.rfind("<g", 0, idx + 1)
            if g_open < 0:
                continue
            fragment = (svg or "")[g_open:pos]
            opens = len(re.findall(r"<g\b", fragment, flags=re.I))
            closes = len(re.findall(r"</g\s*>", fragment, flags=re.I))
            if opens > closes:
                return True
        return False

    edits: list[tuple[int, int]] = []
    for match in re.finditer(r"<line\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1) or ""
        if _protected(attrs):
            continue
        x1 = _attr_float(attrs, "x1")
        y1 = _attr_float(attrs, "y1")
        x2 = _attr_float(attrs, "x2")
        y2 = _attr_float(attrs, "y2")
        if None in (x1, y1, x2, y2):
            continue
        assert x1 is not None and y1 is not None and x2 is not None and y2 is not None
        lx, ly = min(x1, x2), min(y1, y2)
        lw, lh = abs(x2 - x1), abs(y2 - y1)
        if _inside(lx, ly, max(lw, 1.0), max(lh, 1.0)):
            edits.append((match.start(), match.end()))

    for match in re.finditer(r"<path\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1) or ""
        if "data-sunairum-" in attrs or _protected(attrs):
            continue
        d = ""
        dm = re.search(r'\bd="([^"]*)"', attrs)
        if dm:
            d = dm.group(1)
        if not re.search(r"[HhVvLl]", d):
            continue
        mm = re.search(r"[Mm]\s*([-\d.]+)[,\s]+([-\d.]+)", d)
        if not mm:
            continue
        px, py = float(mm.group(1)), float(mm.group(2))
        if ax <= px <= ar and ay <= py <= ab:
            edits.append((match.start(), match.end()))

    for match in re.finditer(r"<rect\b([^>]*)(/?)>", svg, flags=re.I):
        attrs = match.group(1) or ""
        if "data-sunairum-" in attrs or "data-pptx-" in attrs or _protected(attrs):
            continue
        rx = _attr_float(attrs, "x")
        ry = _attr_float(attrs, "y")
        rw = _attr_float(attrs, "width")
        rh = _attr_float(attrs, "height")
        if None in (rx, ry, rw, rh):
            continue
        assert rx is not None and ry is not None and rw is not None and rh is not None
        # Quality-first: drop ANY non-protected freehand rect intersecting the
        # host AABB (mid-size pale cards that only partially overlap used to survive).
        is_page_bg = rw >= 1200 and rh >= 680
        is_host_shell = (
            abs(rx - ax) < 2
            and abs(ry - ay) < 2
            and abs(rw - aw) < 4
            and abs(rh - ah) < 4
        )
        intersects = not (
            rx + rw < ax + 4 or ry + rh < ay + 4 or rx > ar - 4 or ry > ab - 4
        )
        if intersects and not is_page_bg and not is_host_shell:
            edits.append((match.start(), match.end()))

    for match in re.finditer(r"<circle\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1) or ""
        if _protected(attrs) or "data-sunairum-" in attrs:
            continue
        cx = _attr_float(attrs, "cx")
        cy = _attr_float(attrs, "cy")
        r = _attr_float(attrs, "r") or 0.0
        if cx is None or cy is None:
            continue
        if ax - r <= cx <= ar + r and ay - r <= cy <= ab + r:
            edits.append((match.start(), match.end()))

    for match in re.finditer(r"<ellipse\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1) or ""
        if _protected(attrs) or "data-sunairum-" in attrs:
            continue
        cx = _attr_float(attrs, "cx")
        cy = _attr_float(attrs, "cy")
        rx = _attr_float(attrs, "rx") or 0.0
        ry = _attr_float(attrs, "ry") or 0.0
        if cx is None or cy is None:
            continue
        if ax - rx <= cx <= ar + rx and ay - ry <= cy <= ab + ry:
            edits.append((match.start(), match.end()))

    # Ancestor translate for nested freehand chips (local y="12" under g translate).
    def _ancestor_translate(pos: int) -> tuple[float, float]:
        ox = oy = 0.0
        head = svg[:pos]
        for gm in re.finditer(
            r'<g\b([^>]*\btransform="[^"]*translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)[^"]*"[^>]*)>',
            head,
            flags=re.I,
        ):
            # Best-effort: last open translate before this node.
            try:
                ox, oy = float(gm.group(2)), float(gm.group(3))
            except ValueError:
                pass
        return ox, oy

    # Freehand text whose baseline sits inside the reserved band (P09 bullets under grid).
    for match in re.finditer(r"<text\b([^>]*)>[\s\S]*?</text>", svg, flags=re.I):
        attrs = match.group(1) or ""
        if _protected(attrs) or _inside_protected_group(match.start()):
            continue
        tx = _attr_float(attrs, "x")
        ty = _attr_float(attrs, "y")
        ox, oy = _ancestor_translate(match.start())
        if tx is None or ty is None:
            tr = re.search(
                r'transform\s*=\s*"translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"',
                attrs,
                flags=re.I,
            )
            if tr:
                tx, ty = float(tr.group(1)), float(tr.group(2))
        if tx is None or ty is None:
            continue
        abs_x, abs_y = tx + ox, ty + oy
        # Protect global title band / footer only for absolute coords.
        if abs_y < 140.0 or abs_y > 680.0:
            continue
        if _inside(abs_x, abs_y - 14.0, 80.0, 20.0):
            edits.append((match.start(), match.end()))

    if not edits:
        return svg
    out = svg
    for start, end in sorted(edits, reverse=True):
        out = out[:start] + out[end:]
    return out


def compose_table_into_slide(
    svg: str,
    fragment: str,
    *,
    aabb: tuple[float, float, float, float] | None = None,
) -> str:
    if not svg or not fragment:
        return svg
    cleaned = svg
    if aabb is not None:
        cleaned = _clear_freehand_in_aabb(cleaned, aabb)
    # Any polymorphic table-slot form (not only slot="1").
    cleaned = re.sub(
        r"<g\b[^>]*\bdata-sunairum-table-slot\b[^>]*>[\s\S]*?</g>",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r'<g\b[^>]*data-sunairum-source-table-id=[^>]*>[\s\S]*?</g>',
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r'<g\b[^>]*data-sunairum-table-insight="1"[^>]*>[\s\S]*?</g>',
        "",
        cleaned,
        flags=re.I,
    )
    if "</svg>" in cleaned:
        return cleaned.replace("</svg>", fragment + "</svg>", 1)
    return cleaned + fragment


def fill_table_content(
    svg: str,
    slide: dict[str, Any],
    *,
    table_payload: dict[str, Any],
    layout,
    theme: dict[str, Any] | None = None,
    call_text: Callable[[str, str], str] | None = None,
) -> tuple[str, str]:
    """Intent → RenderSpec → SVG. Returns (svg, dsl_source llm|mapper|none)."""
    from tasks.table_analyzer import analyze_table, project_chart_series
    from tasks.table_render_spec import build_table_render_spec
    from tasks.table_visual_intent import author_table_visual_intent

    # Normalize payload to analyzer shape
    table = {
        "table_id": table_payload.get("source_table_id")
        or table_payload.get("table_id")
        or slide.get("table_id"),
        "caption": table_payload.get("caption") or "",
        "headers": table_payload.get("headers")
        or [{"text": c} for c in (table_payload.get("columns") or [])],
        "rows": table_payload.get("rows") or [],
    }
    # columns may be list of strings
    if table["headers"] and isinstance(table["headers"][0], str):
        table["headers"] = [{"text": h} for h in table["headers"]]
    # rows may be list of list of strings
    norm_rows = []
    for row in table["rows"]:
        if not isinstance(row, list):
            continue
        norm_rows.append(
            [{"text": (c.get("text") if isinstance(c, dict) else c)} for c in row]
        )
    table["rows"] = norm_rows

    analysis = analyze_table(table)
    region = layout.region("table") if layout is not None else None
    if region is not None:
        aabb = (region.x, region.y, region.width, region.height)
    else:
        aabb = (24.0, 160.0, 1232.0, 440.0)

    intent = author_table_visual_intent(
        analysis,
        table_id=str(table.get("table_id") or ""),
        slide=slide,
        aabb=aabb,
        call_text=call_text,
    )
    dsl_src = "llm" if call_text is not None else "mapper"
    mode = str((intent.get("strategy") or {}).get("mode") or "")

    if mode == "ranked_bars":
        series = project_chart_series(analysis)
        if series:
            from tasks.style_resolver import resolve_style_tokens

            tokens = resolve_style_tokens(
                style=str((intent.get("strategy") or {}).get("style") or "academic"),
                theme=theme,
            )
            bar_theme = {
                **(theme or {}),
                "primary": tokens.get("primary") or (theme or {}).get("primary"),
                "accent": tokens.get("accent") or (theme or {}).get("accent"),
                "ink": tokens.get("ink") or (theme or {}).get("ink"),
                "muted": tokens.get("muted") or (theme or {}).get("muted"),
                "surface": tokens.get("surface") or (theme or {}).get("surface"),
            }
            frag = render_ranked_bars_svg(
                series,
                aabb=aabb,
                theme=bar_theme,
                title=str(
                    slide.get("title") or analysis.get("caption") or "Results"
                ),
            )
            if frag:
                return compose_table_into_slide(svg, frag, aabb=aabb), dsl_src

    spec = build_table_render_spec(analysis, intent, aabb=aabb, theme=theme)
    fragment = render_table_spec_svg(spec)
    return compose_table_into_slide(svg, fragment, aabb=aabb), dsl_src
