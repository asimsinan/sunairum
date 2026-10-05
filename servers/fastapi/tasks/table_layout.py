"""Reserved-band table placement so fallback tables never cover authored content."""

from __future__ import annotations

import html
import json
import math
import re
from typing import Any

_MARGIN = 16.0
_TITLE_BAND_BOTTOM = 180.0
_FOOTER_TOP = 660.0
_TABLE_MIN_FONT = 12.0
_TABLE_MIN_HEADER_FONT = 12.0
_TABLE_META_RE = re.compile(
    r'(<g\b[^>]*data-pptx-replace-with=["\']table["\'][^>]*>.*?<metadata\b[^>]*>)'
    r'(.*?)'
    r'(</metadata>)',
    flags=re.I | re.S,
)


def _apply_edits(svg: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply (start, end, replacement) spans right-to-left."""
    out = svg or ""
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        if start < 0 or end < start or end > len(out):
            continue
        out = out[:start] + repl + out[end:]
    return out


def _clean_attrs(attrs: str) -> str:
    """Strip a trailing self-close slash that greedy ``[^>]*`` captures may include."""
    return re.sub(r"/\s*$", "", attrs or "").rstrip()


def _self_close_tag(name: str, attrs: str) -> str:
    cleaned = _clean_attrs(attrs)
    return f"<{name}{cleaned}/>" if cleaned else f"<{name}/>"


def _normalize_table_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Fit table payload with converter-true pt budget (grow/shrink/truncate)."""
    try:
        from tasks.table_native_budget import fit_table_payload
    except ImportError:  # pragma: no cover
        from table_native_budget import fit_table_payload  # type: ignore
    style = payload.get("style")
    if not isinstance(style, dict):
        style = {}
        payload["style"] = style
    style["font_size"] = max(float(style.get("font_size") or 0), _TABLE_MIN_FONT)
    style["header_font_size"] = max(
        float(style.get("header_font_size") or style["font_size"] or 0),
        _TABLE_MIN_HEADER_FONT,
    )
    return fit_table_payload(payload)


def normalize_native_table_metadata(svg: str) -> str:
    """Ensure native table carriers meet readable font / row-fit floors."""

    def _replace(match: re.Match[str]) -> str:
        prefix, body, suffix = match.group(1), match.group(2), match.group(3)
        try:
            payload = json.loads(html.unescape(body).strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            return match.group(0)
        if not isinstance(payload, dict):
            return match.group(0)
        normalized = _normalize_table_payload(payload)
        # Carriers store raw JSON (not entity-escaped); keep that contract.
        encoded = json.dumps(normalized, ensure_ascii=False)
        return f"{prefix}{encoded}{suffix}"

    return _TABLE_META_RE.sub(_replace, svg or "")


def viewbox_dims(svg: str) -> tuple[float, float]:
    match = re.search(
        r'\bviewBox\s*=\s*"\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*"',
        svg or "",
        flags=re.I,
    )
    if not match:
        return 1280.0, 720.0
    try:
        return float(match.group(3)), float(match.group(4))
    except ValueError:
        return 1280.0, 720.0


def _rects_from_images(svg: str) -> list[tuple[float, float, float, float]]:
    rects: list[tuple[float, float, float, float]] = []
    for match in re.finditer(r"<image\b([^>]*)>", svg or "", flags=re.I):
        attrs = match.group(1)
        try:
            x = float(re.search(r'\bx="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
        except (AttributeError, ValueError, TypeError):
            continue
        if w > 40 and h > 40:
            rects.append((x, y, w, h))
    return rects


def _count_content_cards(svg: str) -> int:
    # Heuristic: rounded content panels / large filled rects in the content band.
    count = 0
    for match in re.finditer(r"<rect\b([^>]*)>", svg or "", flags=re.I):
        attrs = match.group(1)
        try:
            y = float(re.search(r'\by="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
        except (AttributeError, ValueError, TypeError):
            continue
        if y < 120 or y > 560:
            continue
        if w >= 180 and h >= 120:
            count += 1
    return count


def _intersects(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def _intersection_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def reserved_table_band(svg: str) -> dict[str, float] | None:
    """Pick a compact non-overlapping band for a fallback native table.

    Returns None when no safe band exists (caller must skip placement).
    """
    vw, vh = viewbox_dims(svg)
    images = _rects_from_images(svg)
    cards = _count_content_cards(svg)
    crowded = bool(images) or cards >= 3

    candidates: list[tuple[float, float, float, float]] = []
    # Right column
    candidates.append((vw * 0.55, _TITLE_BAND_BOTTOM, vw * 0.40, min(400.0, _FOOTER_TOP - _TITLE_BAND_BOTTOM)))
    # Left column (common when figure sits on the right)
    candidates.append((_MARGIN * 2, _TITLE_BAND_BOTTOM, vw * 0.42, min(400.0, _FOOTER_TOP - _TITLE_BAND_BOTTOM)))
    # Bottom band
    candidates.append((_MARGIN * 2, vh * 0.55, vw - _MARGIN * 4, min(260.0, _FOOTER_TOP - vh * 0.55)))
    # Compact center-right / center-left
    candidates.append((vw * 0.48, 220.0, vw * 0.46, 320.0))
    candidates.append((_MARGIN * 2, 220.0, vw * 0.46, 320.0))
    # Narrow strip under title above a mid figure
    candidates.append((_MARGIN * 2, _TITLE_BAND_BOTTOM, vw - _MARGIN * 4, 140.0))

    # Also carve candidates that explicitly avoid each figure bbox.
    for ix, iy, iw, ih in images:
        if ix > vw * 0.4:
            # Figure on right → table on left of it
            candidates.append((_MARGIN * 2, max(_TITLE_BAND_BOTTOM, iy), max(200.0, ix - _MARGIN * 3), min(ih, 400.0)))
        if ix + iw < vw * 0.6:
            # Figure on left → table on right of it
            left = ix + iw + _MARGIN
            candidates.append((left, max(_TITLE_BAND_BOTTOM, iy), max(200.0, vw - left - _MARGIN), min(ih, 400.0)))
        # Below figure
        below_y = iy + ih + _MARGIN
        if below_y + 140 < _FOOTER_TOP:
            candidates.append((ix, below_y, iw, min(220.0, _FOOTER_TOP - below_y)))

    best: tuple[float, float, float, float] | None = None
    best_score = -1.0
    content_area = max(1.0, (vw - 2 * _MARGIN) * (_FOOTER_TOP - _TITLE_BAND_BOTTOM))
    for rect in candidates:
        x, y, w, h = rect
        x = max(_MARGIN, min(x, vw - _MARGIN - 80))
        y = max(_TITLE_BAND_BOTTOM, min(y, _FOOTER_TOP - 80))
        w = max(200.0, min(w, vw - x - _MARGIN))
        h = max(140.0, min(h, _FOOTER_TOP - y))
        band = (x, y, w, h)
        if crowded and (w * h) / content_area > 0.45:
            # Shrink to stay under coverage cap.
            w = min(w, content_area * 0.45 / max(h, 1.0))
            if w < 200:
                continue
            band = (x, y, w, h)
        overlap = sum(_intersection_area(band, img) for img in images)
        if overlap > 4000:
            continue
        score = w * h - overlap * 2
        if score > best_score:
            best_score = score
            best = band

    if best is None:
        return None
    x, y, w, h = best
    if crowded and (w * h) / content_area > 0.45:
        return None
    return {"x": round(x, 2), "y": round(y, 2), "width": round(w, 2), "height": round(h, 2)}


def raise_figures_above_tables(svg: str) -> str:
    """Move figure <image> nodes after table groups so they paint on top."""
    if "data-pptx-replace-with=\"table\"" not in (svg or "") and "data-sunairum-source-table" not in (svg or ""):
        if 'data-pptx-replace-with="table"' not in (svg or ""):
            return svg
    images = list(
        re.finditer(
            r'<image\b[^>]*\bdata-sunairum-figure-id="[^"]*"[^>]*/>',
            svg or "",
            flags=re.I,
        )
    )
    if not images:
        return svg
    # Extract images, remove from current positions, append before </svg>.
    chunks = [m.group(0) for m in images]
    cleaned = svg
    for chunk in chunks:
        cleaned = cleaned.replace(chunk, "", 1)
    closing = cleaned.rfind("</svg>")
    if closing < 0:
        return svg
    return f"{cleaned[:closing]}{''.join(chunks)}{cleaned[closing:]}"


def _table_carrier_spans(svg: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in re.finditer(
        r"<g\b[^>]*\bdata-pptx-replace-with=[\"']table[\"'][^>]*>.*?</g>",
        svg or "",
        flags=re.I | re.S,
    ):
        spans.append((match.start(), match.end()))
    return spans


def _inside_spans(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def raise_text_above_shapes(svg: str) -> str:
    """Move non-table labels after shapes so text paints on top (SVG later = on top).

    Leaves table cell texts inside their carriers. Page numbers stay last.
    """
    if not svg or "<text" not in svg.casefold():
        return svg
    table_spans = _table_carrier_spans(svg)
    texts = list(re.finditer(r"<text\b[^>]*>[\s\S]*?</text>", svg, flags=re.I))
    if not texts:
        return svg
    move: list[str] = []
    page: list[str] = []
    drop_spans: list[tuple[int, int]] = []
    for match in texts:
        chunk = match.group(0)
        attrs_end = chunk.find(">")
        attrs = chunk[5:attrs_end] if attrs_end > 0 else ""
        if _inside_spans(match.start(), table_spans):
            continue
        if re.search(r'data-sunairum-source-table-text="1"', attrs, flags=re.I):
            continue
        if re.search(r'data-sunairum-page-number="1"', attrs, flags=re.I):
            page.append(chunk)
        else:
            move.append(chunk)
        drop_spans.append((match.start(), match.end()))
    if not move and not page:
        return svg
    out = svg
    out = _apply_edits(out, [(s, e, "") for s, e in drop_spans])
    closing = out.rfind("</svg>")
    if closing < 0:
        return svg
    # Labels first, then page chrome last.
    return f"{out[:closing]}{''.join(move)}{''.join(page)}{out[closing:]}"


def _card_rects(svg: str) -> list[tuple[float, float, float, float]]:
    """Rounded/content cards that text should stay inside (not full-slide fills)."""
    cards: list[tuple[float, float, float, float]] = []
    for match in re.finditer(r"<rect\b([^>]*)>", svg or "", flags=re.I):
        attrs = match.group(1)

        def _num(name: str) -> float | None:
            found = re.search(rf'\b{name}="([-\d.]+)"', attrs or "")
            if not found:
                return None
            try:
                return float(found.group(1))
            except ValueError:
                return None

        x, y, w, h = _num("x"), _num("y"), _num("width"), _num("height")
        if None in (x, y, w, h):
            continue
        # Skip formula soft-bands — legend rows sit below them on purpose.
        if re.search(r'data-sunairum-formula-plate="1"', attrs or "", flags=re.I):
            continue
        # Skip full-bleed backgrounds and tiny stubs.
        if w >= 1200 or h >= 680 or w < 80 or h < 36:
            continue
        cards.append((x, y, w, h))  # type: ignore[arg-type]
    return cards


def _containing_card(
    x: float, y: float, cards: list[tuple[float, float, float, float]]
) -> tuple[float, float, float, float] | None:
    hits = [
        card
        for card in cards
        if card[0] - 4 <= x <= card[0] + card[2] + 4
        and card[1] - 4 <= y <= card[1] + card[3] + 8
    ]
    if not hits:
        return None
    # Ignore thin full-width table row/header bands when a real panel also hits;
    # otherwise clamp treats the header bar as the clip box and crushes fonts.
    deep = [card for card in hits if card[3] >= 80]
    pool = deep if deep else hits
    # Prefer the smallest containing card (inner step boxes over outer panel).
    return min(pool, key=lambda c: c[2] * c[3])


def _bar_track_rects(svg: str) -> list[tuple[float, float, float, float]]:
    """Horizontal bar/track rects (short height, medium width) used in chart cards."""
    bars: list[tuple[float, float, float, float]] = []
    for match in re.finditer(r"<rect\b([^>]*)>", svg or "", flags=re.I):
        attrs = match.group(1)

        def _num(name: str) -> float | None:
            found = re.search(rf'\b{name}="([-\d.]+)"', attrs or "")
            if not found:
                return None
            try:
                return float(found.group(1))
            except ValueError:
                return None

        x, y, w, h = _num("x"), _num("y"), _num("width"), _num("height")
        if None in (x, y, w, h):
            continue
        if 40.0 <= w <= 500.0 and 6.0 <= h <= 36.0:
            bars.append((x, y, w, h))  # type: ignore[arg-type]
    return bars


def _aabb_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float], *, pad: float = 4.0
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw + pad <= bx
        or bx + bw + pad <= ax
        or ay + ah + pad <= by
        or by + bh + pad <= ay
    )


def resolve_chart_callout_overlaps(svg: str) -> str:
    """Reposition scatter/line chart callout boxes that collide with titles or peers.

    Pattern: small labeled rects near ``<circle>`` points inside a chart panel, while
    an in-panel title sits above the plot. Shift each callout (rect + contained
    texts) as a group below the title band and away from sibling callouts/points.
    """
    if not svg or "<circle" not in svg.casefold():
        return svg

    def _num(attrs: str, name: str) -> float | None:
        found = re.search(rf'\b{name}="([-\d.]+)"', attrs or "")
        if not found:
            return None
        try:
            return float(found.group(1))
        except ValueError:
            return None

    rect_matches = list(re.finditer(r"<rect\b([^>]*)(/?)>", svg, flags=re.I))
    panels: list[tuple[float, float, float, float]] = []
    callouts: list[dict[str, Any]] = []
    for match in rect_matches:
        attrs = match.group(1)
        x, y, w, h = _num(attrs, "x"), _num(attrs, "y"), _num(attrs, "width"), _num(attrs, "height")
        if None in (x, y, w, h):
            continue
        if w >= 500 and h >= 280:
            panels.append((x, y, w, h))  # type: ignore[arg-type]
        elif 90 <= w <= 220 and 40 <= h <= 80:
            callouts.append(
                {
                    "match": match,
                    "box": (x, y, w, h),
                    "attrs": attrs,
                }
            )
    if not panels or len(callouts) < 2:
        return svg

    circles: list[tuple[float, float]] = []
    for match in re.finditer(r"<circle\b([^>]*)>", svg, flags=re.I):
        attrs = match.group(1)
        cx, cy, r = _num(attrs, "cx"), _num(attrs, "cy"), _num(attrs, "r")
        if None in (cx, cy):
            continue
        if r is not None and r > 20:
            continue
        circles.append((cx, cy))  # type: ignore[arg-type]
    if len(circles) < 2:
        return svg

    text_matches = list(re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", svg, flags=re.I))
    # Title band: non-callout texts near the top of the primary (largest) panel.
    panel = max(panels, key=lambda p: p[2] * p[3])
    px, py, pw, ph = panel
    title_bottom = py + 36.0
    for match in text_matches:
        attrs = match.group(1)
        if "rotate" in (attrs or "").casefold():
            continue
        x, y = _num(attrs, "x"), _num(attrs, "y")
        fs = _num(attrs, "font-size") or 14.0
        if x is None or y is None:
            continue
        if not (px <= x <= px + pw and py <= y <= py + 90):
            continue
        inside_callout = any(
            c["box"][0] - 2 <= x <= c["box"][0] + c["box"][2] + 2
            and c["box"][1] - 2 <= y <= c["box"][1] + c["box"][3] + 8
            for c in callouts
        )
        if inside_callout:
            continue
        title_bottom = max(title_bottom, y + 4.0)

    min_top = max(py + 56.0, title_bottom + 10.0)
    plot_bottom = py + ph - 24.0

    # Attach texts to callouts and nearest circle.
    for callout in callouts:
        bx, by, bw, bh = callout["box"]
        members: list[re.Match[str]] = []
        for match in text_matches:
            attrs = match.group(1)
            if "rotate" in (attrs or "").casefold():
                continue
            x, y = _num(attrs, "x"), _num(attrs, "y")
            if x is None or y is None:
                continue
            if bx - 2 <= x <= bx + bw + 2 and by - 2 <= y <= by + bh + 10:
                members.append(match)
        callout["texts"] = members
        cx, cy = bx + bw / 2, by + bh / 2
        if circles:
            callout["point"] = min(circles, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        else:
            callout["point"] = (cx, cy)

    # Place rightmost / topmost points first so frontier labels settle below title.
    callouts.sort(key=lambda c: (-c["point"][1], -c["point"][0]))
    placed: list[tuple[float, float, float, float]] = []
    edits: list[tuple[int, int, str]] = []  # start, end, replacement for rect/text spans

    for callout in callouts:
        bx, by, bw, bh = callout["box"]
        ptx, pty = callout["point"]
        # Prefer below the point so labels clear the title; fall back above if needed.
        candidates = [
            (ptx - bw / 2, pty + 18.0),
            (ptx - bw / 2, pty - bh - 18.0),
            (ptx + 16.0, pty - bh / 2),
            (ptx - bw - 16.0, pty - bh / 2),
            (ptx - bw / 2, min_top),
        ]
        chosen = None
        for nx, ny in candidates:
            nx = max(px + 12.0, min(nx, px + pw - bw - 12.0))
            ny = max(min_top, min(ny, plot_bottom - bh))
            box = (nx, ny, bw, bh)
            if any(_aabb_overlap(box, other, pad=8.0) for other in placed):
                continue
            # Keep a gap from the data point center.
            if box[0] <= ptx <= box[0] + bw and box[1] <= pty <= box[1] + bh:
                continue
            chosen = box
            break
        if chosen is None:
            # Stack below title with horizontal slot by point x.
            nx = max(px + 12.0, min(ptx - bw / 2, px + pw - bw - 12.0))
            ny = min_top
            while any(_aabb_overlap((nx, ny, bw, bh), other, pad=8.0) for other in placed):
                ny += bh + 10.0
                if ny + bh > plot_bottom:
                    break
            chosen = (nx, ny, bw, bh)

        placed.append(chosen)
        dx = chosen[0] - bx
        dy = chosen[1] - by
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            continue

        # Rewrite callout rect.
        rect_match: re.Match[str] = callout["match"]
        new_attrs = _clean_attrs(callout["attrs"])
        new_attrs = re.sub(r'\bx="[^"]*"', f'x="{chosen[0]:g}"', new_attrs, count=1)
        new_attrs = re.sub(r'\by="[^"]*"', f'y="{chosen[1]:g}"', new_attrs, count=1)
        self_close = (rect_match.group(2) or "").strip() or (
            " /" if rect_match.group(0).rstrip().endswith("/>") else ""
        )
        rect_repl = (
            _self_close_tag("rect", new_attrs)
            if "/" in self_close or rect_match.group(0).rstrip().endswith("/>")
            else f"<rect{_clean_attrs(new_attrs)}>"
        )
        edits.append((rect_match.start(), rect_match.end(), rect_repl))

        for text_match in callout.get("texts") or []:
            attrs = text_match.group(1)
            body = text_match.group(2)
            tx, ty = _num(attrs, "x"), _num(attrs, "y")
            if tx is None or ty is None:
                continue
            new_t_attrs = attrs
            new_t_attrs = re.sub(r'\bx="[^"]*"', f'x="{tx + dx:g}"', new_t_attrs, count=1)
            new_t_attrs = re.sub(r'\by="[^"]*"', f'y="{ty + dy:g}"', new_t_attrs, count=1)
            # Shift absolute tspans too.
            new_body = re.sub(
                r'\bx="([-\d.]+)"',
                lambda m: f'x="{float(m.group(1)) + dx:g}"',
                body,
            )
            edits.append(
                (
                    text_match.start(),
                    text_match.end(),
                    f"<text{new_t_attrs}>{new_body}</text>",
                )
            )

    if not edits:
        return svg
    return _apply_edits(svg, edits)


def nudge_bar_value_labels(svg: str) -> str:
    """Move numeric bar labels outside the bar fill (common end-anchor-inside bug).

    Executors often set ``text-anchor="end"`` at the track tip so ``100`` / ``52.3``
    paint *into* the bar. Place them just to the right with start anchoring.
    """
    if not svg or "<text" not in svg.casefold():
        return svg
    bars = _bar_track_rects(svg)
    if not bars:
        return svg
    _VALUE_RE = re.compile(r"^-?\d+(?:\.\d+)?%?$")
    _GAP = 10.0

    def _rewrite(match: re.Match[str]) -> str:
        attrs, body = match.group(1), match.group(2)
        if re.search(r'data-sunairum-(?:source-table-text|page-number)="1"', attrs or "", flags=re.I):
            return match.group(0)
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        if not _VALUE_RE.fullmatch(plain):
            return match.group(0)
        x_m = re.search(r'\bx="([-\d.]+)"', attrs or "")
        y_m = re.search(r'\by="([-\d.]+)"', attrs or "")
        fs_m = re.search(r'\bfont-size="([-\d.]+)"', attrs or "")
        if not x_m or not y_m or not fs_m:
            return match.group(0)
        try:
            x = float(x_m.group(1))
            y = float(y_m.group(1))
            fs = float(fs_m.group(1))
        except ValueError:
            return match.group(0)
        width = max(8.0, len(plain) * fs * 0.58)
        anchor_end = bool(re.search(r'text-anchor="end"', attrs or "", flags=re.I))
        left = x - width if anchor_end else x
        right = x if anchor_end else x + width
        # Bars whose vertical band intersects the label baseline.
        hits = [
            bar
            for bar in bars
            if bar[1] - 6.0 <= y <= bar[1] + bar[3] + 16.0
            and not (right < bar[0] - 2.0 or left > bar[0] + bar[2] + 2.0)
        ]
        if not hits:
            return match.group(0)
        # Prefer the longest track in that row (full scale, not the fill stub).
        track = max(hits, key=lambda b: b[2])
        track_right = track[0] + track[2]
        track_left = track[0]
        new_attrs = attrs
        # Default: outside to the right.
        new_x = track_right + _GAP
        if new_x + width > 1240.0:
            # Fall back: outside to the left with end anchor.
            new_x = track_left - _GAP
            if re.search(r'text-anchor="', new_attrs, flags=re.I):
                new_attrs = re.sub(
                    r'text-anchor="[^"]*"',
                    'text-anchor="end"',
                    new_attrs,
                    count=1,
                    flags=re.I,
                )
            else:
                new_attrs = f'{new_attrs} text-anchor="end"'
        else:
            if re.search(r'text-anchor="', new_attrs, flags=re.I):
                new_attrs = re.sub(
                    r'text-anchor="[^"]*"',
                    'text-anchor="start"',
                    new_attrs,
                    count=1,
                    flags=re.I,
                )
            else:
                new_attrs = f'{new_attrs} text-anchor="start"'
        new_attrs = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', new_attrs, count=1)
        return f"<text{new_attrs}>{body}</text>"

    return re.sub(
        r"<text\b([^>]*)>([\s\S]*?)</text>",
        _rewrite,
        svg,
        flags=re.I,
    )


def fit_freehand_table_columns(svg: str) -> str:
    """Rebalance Executor-drawn tables so every column header/cell fits inside.

    Models often paint N column headers but only N-2 vertical rules, leaving the
    last label clipped at the header bar. Redistribute column edges from content
    widths, rewrite dividers, and left-pad cell text inside each column.
    """
    if not svg:
        return svg

    _CHAR = 0.56
    _PAD = 14.0
    _MIN_FS = 12.0

    def _est(text: str, fs: float) -> float:
        return max(8.0, len(text) * fs * _CHAR)

    # Header bars: short, wide, with ≥3 header labels on them.
    header_bars: list[tuple[float, float, float, float]] = []
    for match in re.finditer(r"<rect\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1)
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if w < 480 or h < 36 or h > 56:
            continue
        header_bars.append((x, y, w, h))

    if not header_bars:
        return svg

    def _is_numeric_cell(plain: str) -> bool:
        return bool(
            re.fullmatch(
                r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?%?",
                (plain or "").strip(),
            )
        )

    text_nodes: list[dict[str, Any]] = []
    for match in re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", svg, flags=re.I):
        attrs, body = match.group(1), match.group(2)
        # Include materialized PDF tables; only skip page chrome.
        if re.search(r'data-sunairum-page-number="1"', attrs, flags=re.I):
            continue
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        if not plain:
            continue
        text_nodes.append(
            {
                "start": match.start(),
                "end": match.end(),
                "attrs": attrs,
                "body": body,
                "plain": plain,
                "x": x,
                "y": y,
                "fs": fs,
                "anchor_end": bool(
                    re.search(r'text-anchor="end"', attrs or "", flags=re.I)
                ),
                "numeric": _is_numeric_cell(plain),
            }
        )

    out = svg
    # Process bottom-up so string offsets stay valid when rewriting later nodes first.
    for hx, hy, hw, hh in sorted(header_bars, key=lambda b: -b[1]):
        right = hx + hw
        bottom = hy + hh
        # Extend bottom via matching row rects / vertical rules.
        for match in re.finditer(r"<rect\b([^>]*)/?>", out, flags=re.I):
            attrs = match.group(1)
            try:
                rx = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                ry = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                rw = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                rh = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            except (AttributeError, TypeError, ValueError):
                continue
            if abs(rx - hx) <= 2 and abs(rw - hw) <= 2 and hy - 4 <= ry <= bottom + 80:
                bottom = max(bottom, ry + rh)
        for match in re.finditer(r"<line\b([^>]*)/?>", out, flags=re.I):
            attrs = match.group(1)
            try:
                x1 = float(re.search(r'\bx1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                y1 = float(re.search(r'\by1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                x2 = float(re.search(r'\bx2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                y2 = float(re.search(r'\by2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            except (AttributeError, TypeError, ValueError):
                continue
            if abs(x2 - x1) <= 1.5 and hx + 20 < x1 < right - 20 and y1 <= hy + 8 and y2 >= hy + 80:
                bottom = max(bottom, y2)

        headers = sorted(
            [
                t
                for t in text_nodes
                if hx - 4 <= t["x"] <= right + 8
                and hy <= t["y"] <= hy + hh + 4
                and t["fs"] >= 13
            ],
            key=lambda t: t["x"],
        )
        # Deduplicate near-identical x (stacked tspans already flattened to plain).
        deduped: list[dict[str, Any]] = []
        for t in headers:
            if deduped and abs(t["x"] - deduped[-1]["x"]) < 12:
                continue
            deduped.append(t)
        headers = deduped
        if len(headers) < 3:
            continue

        n_cols = len(headers)
        cells = [
            t
            for t in text_nodes
            if hx - 4 <= t["x"] <= right + 20 and hy <= t["y"] <= bottom + 4
        ]
        if len(cells) < n_cols:
            continue

        # Assign columns: headers by x-order; body rows by left→right cell order
        # (nearest-header fails when numeric cells are end-anchored / shifted).
        header_ids = {id(h) for h in headers}
        col_needs = [0.0] * n_cols
        col_members: list[list[dict[str, Any]]] = [[] for _ in range(n_cols)]
        for col, header in enumerate(headers):
            col_members[col].append(header)
            col_needs[col] = max(
                col_needs[col], _est(header["plain"], max(header["fs"], 15.0)) + _PAD * 2
            )

        body_cells = [c for c in cells if id(c) not in header_ids]
        rows: dict[int, list[dict[str, Any]]] = {}
        for cell in body_cells:
            rows.setdefault(int(round(float(cell["y"]))), []).append(cell)
        header_xs = [h["x"] for h in headers]
        for _y, row in rows.items():
            ordered = sorted(row, key=lambda c: float(c["x"]))
            if len(ordered) == n_cols:
                assigned = list(enumerate(ordered))
            else:
                # Fallback: nearest header x (legacy freehand tables).
                assigned = []
                for cell in ordered:
                    col = min(range(n_cols), key=lambda i: abs(cell["x"] - header_xs[i]))
                    assigned.append((col, cell))
            for col, cell in assigned:
                if col < 0 or col >= n_cols:
                    continue
                col_members[col].append(cell)
                target_fs = max(cell["fs"], 14.0)
                col_needs[col] = max(
                    col_needs[col], _est(cell["plain"], target_fs) + _PAD * 2
                )

        inner = max(120.0, hw - 4.0)
        min_share = max(72.0, inner / (n_cols * 1.8))
        needs = [max(min_share, n) for n in col_needs]
        total = sum(needs)
        widths = [n / total * inner for n in needs]
        # Ensure the widest content column isn't crushed below its need when possible.
        for _ in range(3):
            short = [i for i, (w, n) in enumerate(zip(widths, needs)) if w + 0.5 < n]
            if not short:
                break
            deficit = sum(needs[i] - widths[i] for i in short)
            donors = [i for i in range(n_cols) if i not in short and widths[i] > needs[i] + 8]
            spare = sum(widths[i] - needs[i] for i in donors)
            if spare <= 1 or not donors:
                break
            take = min(deficit, spare)
            for i in donors:
                cut = take * ((widths[i] - needs[i]) / spare)
                widths[i] -= cut
            for i in short:
                widths[i] += take * ((needs[i] - widths[i]) / deficit)

        edges = [hx + 2.0]
        for w in widths[:-1]:
            edges.append(edges[-1] + w)
        edges.append(hx + hw - 2.0)

        # Rewrite vertical dividers spanning this table into the new edges.
        new_div_xs = edges[1:-1]
        line_matches = list(re.finditer(r"<line\b([^>]*)/?>", out, flags=re.I))
        table_lines: list[re.Match[str]] = []
        for match in line_matches:
            attrs = match.group(1)
            try:
                x1 = float(re.search(r'\bx1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                y1 = float(re.search(r'\by1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                x2 = float(re.search(r'\bx2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                y2 = float(re.search(r'\by2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            except (AttributeError, TypeError, ValueError):
                continue
            if abs(x2 - x1) > 1.5:
                continue
            if not (hx + 12 < x1 < right - 12 and y1 <= hy + 10 and y2 >= bottom - 12):
                continue
            table_lines.append(match)

        # Replace existing lines (rightmost first) then insert any missing dividers
        # after the header bar so column count matches headers.
        for match in sorted(table_lines, key=lambda m: m.start(), reverse=True):
            out = out[: match.start()] + out[match.end() :]

        insert_at = None
        # Place new dividers just after the header rect when possible.
        hdr_rect = re.search(
            rf'<rect\b(?=[^>]*\bx="{hx:g}")(?=[^>]*\by="{hy:g}")(?=[^>]*\bwidth="{hw:g}")[^>]*/?>',
            out,
            flags=re.I,
        )
        if hdr_rect:
            insert_at = hdr_rect.end()
        else:
            insert_at = 0
            for match in re.finditer(r"<rect\b[^>]*/?>", out, flags=re.I):
                insert_at = match.end()
                break

        divider_svg = "".join(
            f'<line x1="{x:g}" y1="{hy:g}" x2="{x:g}" y2="{bottom:g}" '
            f'stroke="#CBD5E1" stroke-width="1"/>'
            for x in new_div_xs
        )
        out = out[:insert_at] + divider_svg + out[insert_at:]

        # Reposition / resize each cell into its column (edit later nodes first).
        edits: list[tuple[int, int, str]] = []
        for col, members in enumerate(col_members):
            col_left = edges[col]
            col_right = edges[col + 1]
            max_w = max(24.0, col_right - col_left - _PAD * 2)
            for cell in members:
                fs = cell["fs"]
                # Restore crushed fonts from prior clamps when the column can take it.
                if cell in headers:
                    fs = max(fs, 15.0)
                else:
                    fs = max(fs, 14.0)
                while fs > _MIN_FS and _est(cell["plain"], fs) > max_w:
                    fs -= 0.5
                # Numeric / end-anchored value columns stay right-aligned in-cell.
                # Headers stay start-aligned so labels sit on the column left edge.
                right_align = cell not in headers and col > 0 and (
                    bool(cell.get("numeric")) or bool(cell.get("anchor_end"))
                )
                new_attrs = cell["attrs"]
                if right_align:
                    new_x = col_right - _PAD
                    if not re.search(r'text-anchor="end"', new_attrs or "", flags=re.I):
                        new_attrs = f'{new_attrs} text-anchor="end"'
                else:
                    new_x = col_left + _PAD
                    new_attrs = re.sub(
                        r'\s*text-anchor="end"',
                        "",
                        new_attrs or "",
                        flags=re.I,
                    )
                    # Keep right-overflow from rounding by a final nudge.
                    if new_x + _est(cell["plain"], fs) > col_right - 4:
                        new_x = max(
                            col_left + 4.0,
                            col_right - 4.0 - _est(cell["plain"], fs),
                        )
                new_attrs = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', new_attrs, count=1)
                if abs(fs - cell["fs"]) > 0.01:
                    new_attrs = re.sub(
                        r'\bfont-size="[^"]*"',
                        f'font-size="{fs:g}"',
                        new_attrs,
                        count=1,
                    )
                # Refresh span x if present so wrapped lines track the cell.
                new_body = re.sub(
                    r'\bx="[^"]*"',
                    f'x="{new_x:g}"',
                    cell["body"],
                )
                replacement = f"<text{new_attrs}>{new_body}</text>"
                # Match the exact pre-edit snippet (Python 3.11-safe: no nested
                # quotes inside f-string expressions).
                old_snip = (
                    "<text"
                    + str(cell["attrs"])
                    + ">"
                    + str(cell["body"])
                    + "</text>"
                )
                pos = out.find(old_snip)
                if pos < 0:
                    continue
                edits.append((pos, pos + len(old_snip), replacement))
                # Update cell snapshot so duplicate plain rows still match uniquely.
                cell["attrs"] = new_attrs
                cell["body"] = new_body
                cell["x"] = new_x
                cell["fs"] = fs

        out = _apply_edits(out, edits)
        edits = []

        # Refresh text_nodes x/fs for subsequent tables in the same SVG.
        for cell in cells:
            for t in text_nodes:
                if t["start"] == cell["start"]:
                    t["x"] = cell["x"]
                    t["fs"] = cell["fs"]
                    t["attrs"] = cell["attrs"]
                    t["body"] = cell["body"]
                    break

    return out


def _text_block_ink(
    attrs: str, body: str, *, char_em: float = 0.55
) -> tuple[float, float, float, float, float] | None:
    """Return (x, y, left, right, bottom) for a <text> including tspan dy chains."""
    try:
        x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
    except (AttributeError, TypeError, ValueError):
        return None
    bold = bool(re.search(r'font-weight="(?:bold|700)"', attrs, flags=re.I))
    em = 0.58 if bold else char_em
    tspan_bits = list(
        re.finditer(r"<tspan\b([^>]*)>([\s\S]*?)</tspan>", body or "", flags=re.I)
    )
    lines: list[tuple[float, str]] = []
    if tspan_bits:
        cy = y
        for bit in tspan_bits:
            t_attrs, t_body = bit.group(1) or "", bit.group(2) or ""
            dy_m = re.search(r'\bdy="([-\d.]+)"', t_attrs)
            if dy_m:
                try:
                    cy += float(dy_m.group(1))
                except ValueError:
                    pass
            y_m = re.search(r'\by="([-\d.]+)"', t_attrs)
            if y_m:
                try:
                    cy = float(y_m.group(1))
                except ValueError:
                    pass
            plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t_body)).strip()
            if plain:
                lines.append((cy, plain))
    else:
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body or "")).strip()
        if plain:
            lines.append((y, plain))
    if not lines:
        return None
    max_w = max(len(line) * fs * em for _, line in lines)
    max_w = max(8.0, max_w)
    last_y = max(ly for ly, _ in lines)
    bottom = last_y + max(3.0, fs * 0.28)
    anchor_end = bool(re.search(r'text-anchor="end"', attrs, flags=re.I))
    anchor_mid = bool(re.search(r'text-anchor="middle"', attrs, flags=re.I))
    left = x - max_w if anchor_end else (x - max_w / 2 if anchor_mid else x)
    right = x if anchor_end else (x + max_w / 2 if anchor_mid else x + max_w)
    return (x, y, left, right, bottom)


def expand_cards_for_overflowing_text(svg: str) -> str:
    """Grow cramped freehand cards when labels/shapes overflow and free space exists.

    Widens chips into the right gap; lengthens panels when text baselines or child
    bars/lines sit on the bottom stroke.
    """
    if not svg:
        return svg

    _PAD = 12.0
    _GAP = 10.0

    rects: list[dict[str, Any]] = []
    for match in re.finditer(r"<rect\b([^>]*)(/?)>", svg, flags=re.I):
        attrs = match.group(1)
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        rects.append(
            {
                "start": match.start(),
                "end": match.end(),
                "attrs": attrs,
                "self_close": bool(match.group(2)),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        )

    texts: list[dict[str, float]] = []
    for match in re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", svg, flags=re.I):
        attrs, body = match.group(1), match.group(2)
        if re.search(r'data-sunairum-(?:source-table-text|page-number)="1"', attrs, flags=re.I):
            continue
        ink = _text_block_ink(attrs, body)
        if ink is None:
            continue
        x, y, left, right, bottom = ink
        texts.append({"x": x, "y": y, "left": left, "right": right, "bottom": bottom})

    lines: list[dict[str, float]] = []
    for match in re.finditer(r"<line\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1)
        try:
            x1 = float(re.search(r'\bx1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y1 = float(re.search(r'\by1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            x2 = float(re.search(r'\bx2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y2 = float(re.search(r'\by2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        lines.append(
            {
                "x": min(x1, x2),
                "y": min(y1, y2),
                "right": max(x1, x2),
                "bottom": max(y1, y2),
            }
        )

    edits: list[tuple[int, int, str]] = []
    for card in rects:
        if not (70.0 <= card["w"] <= 1220.0 and 48.0 <= card["h"] <= 480.0):
            continue
        if card["h"] < 40 and card["w"] > 200:
            continue
        members = [
            t
            for t in texts
            if card["x"] - 2 <= float(t["x"]) <= card["x"] + card["w"] + 8
            and card["y"] - 2 <= float(t["y"]) <= card["y"] + card["h"] + 10
        ]
        child_rects = [
            r
            for r in rects
            if r is not card
            and r["w"] < card["w"]
            and r["h"] < card["h"]
            and card["x"] - 2 <= r["x"] + r["w"] / 2 <= card["x"] + card["w"] + 2
            and card["y"] - 2 <= r["y"] + r["h"] / 2 <= card["y"] + card["h"] + 2
        ]
        child_lines = [
            ln
            for ln in lines
            if card["x"] - 2 <= ln["x"] <= card["x"] + card["w"] + 8
            and card["y"] - 2 <= ln["y"] <= card["y"] + card["h"] + 10
        ]
        if not members and not child_rects and not child_lines:
            continue
        need_right = card["x"] + card["w"]
        need_bottom = card["y"] + card["h"]
        if members:
            need_right = max(need_right, max(float(t["right"]) for t in members) + _PAD)
            need_bottom = max(
                need_bottom, max(float(t["bottom"]) for t in members) + _PAD
            )
        for r in child_rects:
            need_right = max(need_right, r["x"] + r["w"] + _PAD)
            need_bottom = max(need_bottom, r["y"] + r["h"] + _PAD)
        for ln in child_lines:
            need_right = max(need_right, ln["right"] + _PAD)
            need_bottom = max(need_bottom, ln["bottom"] + _PAD)
        new_w = card["w"]
        new_h = card["h"]
        cy0, cy1 = card["y"], card["y"] + card["h"]
        cx0, cx1 = card["x"], card["x"] + card["w"]

        if need_right > card["x"] + card["w"] + 0.5:
            limit_x = 1240.0
            for other in rects:
                if other is card or other["w"] >= 1200 or other["h"] >= 680:
                    continue
                if other in child_rects:
                    continue
                oy0, oy1 = other["y"], other["y"] + other["h"]
                if oy1 < cy0 + 8 or oy0 > cy1 - 8:
                    continue
                if other["x"] >= card["x"] + card["w"] - 4:
                    limit_x = min(limit_x, other["x"])
            new_w = min(
                max(card["w"], need_right - card["x"]),
                max(card["w"], limit_x - _GAP - card["x"]),
            )

        if need_bottom > card["y"] + card["h"] + 0.5:
            limit_y = 640.0
            for other in rects:
                if other is card or other["w"] >= 1200 or other["h"] >= 680:
                    continue
                if other in child_rects:
                    continue
                ox0, ox1 = other["x"], other["x"] + other["w"]
                if ox1 < cx0 + 8 or ox0 > cx1 + 8:
                    continue
                if other["y"] >= card["y"] + card["h"] - 4:
                    limit_y = min(limit_y, other["y"])
            new_h = min(
                max(card["h"], need_bottom - card["y"]),
                max(card["h"], limit_y - _GAP - card["y"]),
            )

        if new_w <= card["w"] + 0.5 and new_h <= card["h"] + 0.5:
            continue
        clean = _clean_attrs(card["attrs"])
        new_attrs = clean
        if new_w > card["w"] + 0.5:
            new_attrs = re.sub(r'\bwidth="[^"]*"', f'width="{new_w:g}"', new_attrs, count=1)
        if new_h > card["h"] + 0.5:
            new_attrs = re.sub(r'\bheight="[^"]*"', f'height="{new_h:g}"', new_attrs, count=1)
        if svg[card["start"] : card["end"]].rstrip().endswith("/>"):
            replacement = _self_close_tag("rect", new_attrs)
        else:
            replacement = f"<rect{_clean_attrs(new_attrs)}>"
        edits.append((card["start"], card["end"], replacement))
        # Sync shared-origin accent strips (top bar / left rail) with new size.
        for other in rects:
            if other is card:
                continue
            if abs(other["x"] - card["x"]) > 1.0 or abs(other["y"] - card["y"]) > 1.0:
                continue
            o_attrs = _clean_attrs(other["attrs"])
            o_new = o_attrs
            changed = False
            # Top accent: same width as card, short height.
            if other["h"] <= 16 and abs(other["w"] - card["w"]) < 40:
                if new_w > other["w"] + 0.5:
                    o_new = re.sub(r'\bwidth="[^"]*"', f'width="{new_w:g}"', o_new, count=1)
                    changed = True
            # Left rail: same height as card, narrow width.
            if other["w"] <= 16 and abs(other["h"] - card["h"]) < 40:
                if new_h > other["h"] + 0.5:
                    o_new = re.sub(r'\bheight="[^"]*"', f'height="{new_h:g}"', o_new, count=1)
                    changed = True
            if not changed:
                continue
            o_tag = svg[other["start"] : other["end"]]
            o_rep = (
                _self_close_tag("rect", o_new)
                if o_tag.rstrip().endswith("/>")
                else f"<rect{_clean_attrs(o_new)}>"
            )
            edits.append((other["start"], other["end"], o_rep))

    return _apply_edits(svg, edits)


def clamp_shapes_inside_cards(svg: str) -> str:
    """Pull bars/lines that spill past their smallest parent card back inside."""
    if not svg:
        return svg
    cards = _card_rects(svg)
    if not cards:
        return svg
    _PAD = 10.0
    edits: list[tuple[int, int, str]] = []

    def _host(px: float, py: float) -> tuple[float, float, float, float] | None:
        return _containing_card(px, py, cards)

    for match in re.finditer(r"<line\b([^>]*)(/?)>", svg, flags=re.I):
        attrs = match.group(1)
        try:
            x1 = float(re.search(r'\bx1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y1 = float(re.search(r'\by1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            x2 = float(re.search(r'\bx2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y2 = float(re.search(r'\by2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        host = _host((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        if host is None:
            continue
        cx, cy, cw, ch = host
        max_x = cx + cw - _PAD
        max_y = cy + ch - _PAD
        min_x = cx + _PAD
        min_y = cy + _PAD
        nx1, ny1, nx2, ny2 = x1, y1, x2, y2
        # Vertical callout lines: keep inside right/bottom.
        if abs(x1 - x2) < 1.0 and max(x1, x2) > max_x:
            nx1 = nx2 = max_x
        if max(y1, y2) > max_y:
            if y2 >= y1:
                ny2 = max_y
                ny1 = min(ny1, max_y)
            else:
                ny1 = max_y
                ny2 = min(ny2, max_y)
        if min(x1, x2) < min_x and abs(x1 - x2) < 1.0:
            nx1 = nx2 = min_x
        if (nx1, ny1, nx2, ny2) == (x1, y1, x2, y2):
            continue
        new_attrs = _clean_attrs(attrs)
        for name, val in (("x1", nx1), ("y1", ny1), ("x2", nx2), ("y2", ny2)):
            new_attrs = re.sub(
                rf'\b{name}="[^"]*"', f'{name}="{val:g}"', new_attrs, count=1
            )
        tag = svg[match.start() : match.end()]
        replacement = (
            _self_close_tag("line", new_attrs)
            if tag.rstrip().endswith("/>")
            else f"<line{_clean_attrs(new_attrs)}>"
        )
        edits.append((match.start(), match.end(), replacement))

    for match in re.finditer(r"<rect\b([^>]*)(/?)>", svg, flags=re.I):
        attrs = match.group(1)
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        # Short bars/tracks OR nested list-row cards (white pills inside a parent).
        is_bar = 40.0 <= w <= 420.0 and 8.0 <= h <= 36.0
        is_nested_row = 80.0 <= w <= 700.0 and 28.0 <= h <= 96.0
        if not (is_bar or is_nested_row):
            continue
        # Prefer a strictly larger parent card for nested rows (center-point
        # containment so already-overflowing rows still find their host).
        host = None
        parents = [
            card
            for card in cards
            if card[0] - 4 <= x + w * 0.5 <= card[0] + card[2] + 4
            and card[1] - 4 <= y + h * 0.5 <= card[1] + card[3] + 4
            and (card[2] * card[3]) > (w * h) + 40.0
        ]
        if parents:
            host = min(parents, key=lambda c: c[2] * c[3])
        elif is_bar:
            host = _host(x + w / 2.0, y + h / 2.0)
        if host is None:
            continue
        cx, cy, cw, ch = host
        # Skip if this rect IS the host card.
        if abs(x - cx) < 1 and abs(y - cy) < 1 and abs(w - cw) < 1:
            continue
        max_x = cx + cw - _PAD
        max_y = cy + ch - _PAD
        min_x = cx + _PAD
        nx, ny, nw, nh = x, y, w, h
        if x < min_x:
            shift = min_x - x
            nx = min_x
            nw = max(24.0, nw - shift)
        if nx + nw > max_x:
            nw = max(24.0, max_x - nx)
        if y + h > max_y:
            overflow = y + h - max_y
            ny = max(cy + _PAD, y - overflow)
            if ny + nh > max_y:
                nh = max(8.0, max_y - ny)
        if (nx, ny, nw, nh) == (x, y, w, h):
            continue
        new_attrs = _clean_attrs(attrs)
        for name, val in (("x", nx), ("y", ny), ("width", nw), ("height", nh)):
            new_attrs = re.sub(
                rf'\b{name}="[^"]*"', f'{name}="{val:g}"', new_attrs, count=1
            )
        tag = svg[match.start() : match.end()]
        replacement = (
            _self_close_tag("rect", new_attrs)
            if tag.rstrip().endswith("/>")
            else f"<rect{_clean_attrs(new_attrs)}>"
        )
        edits.append((match.start(), match.end(), replacement))

    # Short callout labels (e.g. "Uneven" / "load") that sit past the card edge.
    for match in re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", svg, flags=re.I):
        attrs, body = match.group(1), match.group(2)
        if re.search(r'data-sunairum-(?:source-table-text|page-number)="1"', attrs, flags=re.I):
            continue
        ink = _text_block_ink(attrs, body)
        if ink is None:
            continue
        x, y, left, right, bottom = ink
        try:
            fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body or "")).strip()
        if not plain or len(plain) > 40 or fs > 18:
            continue
        host = _host(x, y)
        if host is None:
            continue
        cx, cy, cw, ch = host
        max_x = cx + cw - _PAD
        max_y = cy + ch - _PAD
        nx, ny = x, y
        if right > max_x + 0.5:
            shift = right - max_x
            nx = x - shift
        if bottom > max_y + 0.5:
            shift = bottom - max_y
            ny = y - shift
        if abs(nx - x) < 0.01 and abs(ny - y) < 0.01:
            continue
        new_attrs = attrs
        if abs(nx - x) >= 0.01:
            new_attrs = re.sub(r'\bx="[^"]*"', f'x="{nx:g}"', new_attrs, count=1)
        if abs(ny - y) >= 0.01:
            new_attrs = re.sub(r'\by="[^"]*"', f'y="{ny:g}"', new_attrs, count=1)
        edits.append((match.start(), match.end(), f"<text{new_attrs}>{body}</text>"))

    return _apply_edits(svg, edits) if edits else svg


def nudge_annotation_off_headlines(svg: str) -> str:
    """Push small annotation labels (and their pills) off large headlines."""
    if not svg:
        return svg
    nodes: list[dict[str, Any]] = []
    for match in re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", svg, flags=re.I):
        attrs, body = match.group(1), match.group(2)
        if re.search(r'data-sunairum-(?:source-table-text|page-number)="1"', attrs, flags=re.I):
            continue
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        if len(plain) < 3:
            continue
        bold = bool(re.search(r'font-weight="(?:bold|700)"', attrs, flags=re.I))
        em = 0.58 if bold else 0.55
        width = max(8.0, len(plain) * fs * em)
        nodes.append(
            {
                "start": match.start(),
                "end": match.end(),
                "attrs": attrs,
                "body": body,
                "plain": plain,
                "x": x,
                "y": y,
                "fs": fs,
                "w": width,
                "h": fs * 1.15,
            }
        )
    if len(nodes) < 2:
        return svg
    # Short callouts like "O(rn)" are headlines for collision purposes even when
    # under 10 characters — otherwise captions park on top of the metric.
    headlines = [
        n
        for n in nodes
        if n["fs"] >= 22
        and (len(n["plain"]) >= 10 or (3 <= len(n["plain"]) <= 12 and n["fs"] >= 22))
    ]
    labels = [n for n in nodes if n["fs"] <= 16 and len(n["plain"]) <= 56]

    # Small pill/chip rects that often wrap annotation labels ("query vector").
    pills: list[dict[str, Any]] = []
    for match in re.finditer(r"<rect\b([^>]*)(/?)>", svg, flags=re.I):
        attrs = match.group(1)
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if not (48.0 <= w <= 240.0 and 16.0 <= h <= 44.0):
            continue
        pills.append(
            {
                "start": match.start(),
                "end": match.end(),
                "attrs": attrs,
                "self_close": bool(match.group(2)),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        )

    edits: list[tuple[int, int, str]] = []
    moved_label_starts: set[int] = set()
    for label in labels if headlines else []:
        lx, ly, lw, lh = label["x"], label["y"] - label["fs"] * 0.85, label["w"], label["h"]
        for head in headlines:
            hx, hy, hw, hh = head["x"], head["y"] - head["fs"] * 0.85, head["w"], head["h"]
            if not _aabb_overlap((lx, ly, lw, lh), (hx, hy, hw, hh), pad=2.0):
                continue
            # Prefer parking the annotation above the headline.
            new_y = hy - 8.0
            if new_y < 48:
                new_y = head["y"] + head["fs"] * 0.55 + 14.0
            dy = new_y - label["y"]
            new_attrs = re.sub(r'\by="[^"]*"', f'y="{new_y:g}"', label["attrs"], count=1)
            edits.append(
                (
                    label["start"],
                    label["end"],
                    f"<text{new_attrs}>{label['body']}</text>",
                )
            )
            moved_label_starts.add(int(label["start"]))
            # Drag any containing pill with the label.
            for pill in pills:
                if not (
                    pill["x"] - 4 <= label["x"] <= pill["x"] + pill["w"] + 4
                    and pill["y"] - 4 <= label["y"] <= pill["y"] + pill["h"] + 8
                ):
                    continue
                new_py = pill["y"] + dy
                clean = _clean_attrs(pill["attrs"])
                new_p_attrs = re.sub(r'\by="[^"]*"', f'y="{new_py:g}"', clean, count=1)
                if pill["self_close"] or svg[pill["start"] : pill["end"]].rstrip().endswith("/>"):
                    repl = _self_close_tag("rect", new_p_attrs)
                else:
                    repl = f"<rect{_clean_attrs(new_p_attrs)}>"
                edits.append((pill["start"], pill["end"], repl))
                break
            break

    # Large donut/ring charts overlapping nearby body copy (subtitle under title).
    rings: list[tuple[float, float, float]] = []
    for match in re.finditer(r"<circle\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1)
        try:
            cx = float(re.search(r'\bcx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            cy = float(re.search(r'\bcy="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            r = float(re.search(r'\br="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if r >= 48.0:
            rings.append((cx, cy, r))
    for node in nodes:
        if int(node["start"]) in moved_label_starts:
            continue
        # Short annotation chips only — long bylines/affiliations must not be
        # yanked onto presenter baselines by a decorative ring on the cover.
        if node["fs"] > 16 or not (12 <= len(node["plain"]) <= 56):
            continue
        tx, ty, tw = float(node["x"]), float(node["y"]), float(node["w"])
        top = ty - node["fs"] * 0.85
        text_box = (tx, top, tw, float(node["h"]))
        for cx, cy, r in rings:
            ring_box = (cx - r, cy - r, 2 * r, 2 * r)
            if not _aabb_overlap(text_box, ring_box, pad=2.0):
                continue
            # Only lift copy that sits on the upper arc (typical subtitle clash).
            if top > cy:
                continue
            new_y = cy - r - 10.0
            if new_y < 56 or new_y >= ty - 0.5:
                continue
            new_attrs = re.sub(r'\by="[^"]*"', f'y="{new_y:g}"', node["attrs"], count=1)
            edits.append(
                (
                    node["start"],
                    node["end"],
                    f"<text{new_attrs}>{node['body']}</text>",
                )
            )
            break

    return _apply_edits(svg, edits)


def resolve_coincident_text_labels(svg: str) -> str:
    """Spread labels that the model stacked on the exact same anchor point.

    Classic freehand failure: A/B/C/D (or title + subtitle) share one (x, y).
    Short tokens fan out horizontally; longer lines drop onto new baselines.
    """
    if not svg or svg.casefold().count("<text") < 2:
        return svg

    nodes: list[dict[str, Any]] = []
    for match in re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", svg, flags=re.I):
        attrs, body = match.group(1), match.group(2)
        if re.search(r'data-sunairum-(?:source-table-text|page-number)="1"', attrs, flags=re.I):
            continue
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        if not plain:
            continue
        nodes.append(
            {
                "start": match.start(),
                "end": match.end(),
                "attrs": attrs,
                "body": body,
                "plain": plain,
                "x": x,
                "y": y,
                "fs": fs,
            }
        )

    # Bucket by rounded anchor.
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for node in nodes:
        key = (int(round(node["x"])), int(round(node["y"])))
        buckets.setdefault(key, []).append(node)

    edits: list[tuple[int, int, str]] = []
    for (_kx, _ky), group in buckets.items():
        if len(group) < 2:
            continue
        # Stable order: keep first as-is, move the rest.
        group = sorted(group, key=lambda n: (n["start"], n["plain"]))
        short = all(len(n["plain"]) <= 4 for n in group)
        for index, node in enumerate(group):
            if index == 0:
                continue
            new_attrs = node["attrs"]
            if short:
                # Fan out along the row (A B C D under a process arrow).
                new_x = node["x"] + index * max(22.0, node["fs"] * 1.6)
                new_attrs = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', new_attrs, count=1)
            else:
                # Drop subsequent lines below the first baseline.
                new_y = node["y"] + index * max(14.0, node["fs"] * 1.15)
                new_attrs = re.sub(r'\by="[^"]*"', f'y="{new_y:g}"', new_attrs, count=1)
            edits.append(
                (node["start"], node["end"], f"<text{new_attrs}>{node['body']}</text>")
            )

    return _apply_edits(svg, edits)


def _split_formula_line(plain: str) -> tuple[str, str] | None:
    """Split a long equation near the middle at ``=`` / ``+`` / ``-`` when possible."""
    text = (plain or "").strip()
    if len(text) < 28:
        return None
    mid = len(text) // 2
    best: tuple[int, int] | None = None  # (distance_from_mid, index)
    for match in re.finditer(r"\s[=+\-]\s", text):
        idx = match.start() + 1  # keep operator on the second line
        # Prefer breaking before '+' / after '='.
        if text[idx] == "=":
            idx = match.end()  # "Delta J =|" then remainder
        dist = abs(idx - mid)
        if best is None or dist < best[0]:
            best = (dist, idx)
    if best is None:
        # Fallback: last space before mid.
        sp = text.rfind(" ", 0, mid + 8)
        if sp < 12:
            return None
        return text[:sp].rstrip(), text[sp:].lstrip()
    idx = best[1]
    left = text[:idx].rstrip()
    right = text[idx:].lstrip()
    if len(left) < 8 or len(right) < 8:
        return None
    return left, right


def clamp_freehand_text_to_canvas(svg: str) -> str:
    """Nudge/shrink freehand <text> away from slide edges AND card borders.

    Fixes labels that sit on the bottom stroke of process-step cards (gap ~0–2px)
    while still keeping the slide safe frame. Skips table cells / page chrome.
    """
    if not svg:
        return svg
    cards = _card_rects(svg)
    icons: list[tuple[float, float, float]] = []
    for match in re.finditer(r"<circle\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1)
        try:
            icons.append(
                (
                    float(re.search(r'\bcx="([-\d.]+)"', attrs).group(1)),  # type: ignore[union-attr]
                    float(re.search(r'\bcy="([-\d.]+)"', attrs).group(1)),  # type: ignore[union-attr]
                    float(re.search(r'\br="([-\d.]+)"', attrs).group(1)),  # type: ignore[union-attr]
                )
            )
        except (AttributeError, TypeError, ValueError):
            continue
    _SLIDE_PAD = 40.0
    _SLIDE_RIGHT = 1240.0
    _SLIDE_BOTTOM = 640.0
    _CARD_PAD = 12.0

    def _rewrite(match: re.Match[str]) -> str:
        attrs, body = match.group(1), match.group(2)
        if re.search(r'data-sunairum-source-table-text="1"', attrs or "", flags=re.I):
            return match.group(0)
        if re.search(r'data-sunairum-page-number="1"', attrs or "", flags=re.I):
            return match.group(0)
        # Formula plate owns its AABBs — do not pull legend rows into the band.
        if re.search(
            r'data-sunairum-formula(?:-term|-plate)?="1"',
            attrs or "",
            flags=re.I,
        ):
            return match.group(0)
        x_m = re.search(r'\bx="([-\d.]+)"', attrs or "")
        y_m = re.search(r'\by="([-\d.]+)"', attrs or "")
        fs_m = re.search(r'\bfont-size="([-\d.]+)"', attrs or "")
        if not x_m or not fs_m:
            return match.group(0)
        try:
            x = float(x_m.group(1))
            y = float(y_m.group(1)) if y_m else 0.0
            fs = float(fs_m.group(1))
        except ValueError:
            return match.group(0)
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        if not plain:
            return match.group(0)
        bold = bool(re.search(r'font-weight="(?:bold|700)"', attrs or "", flags=re.I))
        mono = bool(
            re.search(
                r'font-family="[^"]*(?:Consolas|Courier|Monaco|monospace)',
                attrs or "",
                flags=re.I,
            )
        )
        ink = _text_block_ink(attrs or "", body or "", char_em=0.55)
        # Multi-line titles store one logical string per tspan — width is the
        # longest line, not the joined character count (that crushes headers).
        tspan_lines = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", bit)).strip()
            for bit in re.findall(r"<tspan\b[^>]*>([\s\S]*?)</tspan>", body or "", flags=re.I)
        ]
        tspan_lines = [line for line in tspan_lines if line]
        measure = max((len(line) for line in tspan_lines), default=len(plain))
        # Full-band slide titles must keep page width; card clamp is for body copy.
        is_title_band = y <= 130.0 and fs >= 22.0
        # Slightly conservative for long body lines (process-step descriptions).
        # Monospace formulas are wider than Arial — underestimate caused card spill.
        anchor_end = bool(re.search(r'text-anchor="end"', attrs or "", flags=re.I))
        anchor_mid = bool(re.search(r'text-anchor="middle"', attrs or "", flags=re.I))
        if mono:
            em = 0.72 if bold else 0.68
        else:
            em = 0.60 if bold else (0.58 if measure >= 28 else 0.55)
        if mono:
            width = max(8.0, measure * fs * em)
            left = x - width if anchor_end else (x - width / 2 if anchor_mid else x)
            right = x if anchor_end else (x + width / 2 if anchor_mid else x + width)
            block_bottom = ink[4] if ink is not None else y + max(3.0, fs * 0.28)
        elif ink is not None:
            _, _, left, right, block_bottom = ink
            width = max(8.0, right - left)
        else:
            width = max(8.0, measure * fs * em)
            left = x - width if anchor_end else (x - width / 2 if anchor_mid else x)
            right = x if anchor_end else (x + width / 2 if anchor_mid else x + width)
            block_bottom = y + max(3.0, fs * 0.28)
        # Descenders need room below the baseline.
        descent = max(3.0, fs * 0.28)
        new_attrs = attrs
        new_x, new_y, new_fs = x, y, fs
        # How far the block extends below the first baseline.
        block_depth = max(0.0, block_bottom - y)

        # Slide frame
        if left < _SLIDE_PAD:
            shift = _SLIDE_PAD - left
            new_x += shift
            left += shift
            right += shift
        if new_y > _SLIDE_BOTTOM:
            new_y = _SLIDE_BOTTOM

        card = None if is_title_band else _containing_card(new_x, new_y, cards)
        if card:
            cx, cy, cw, ch = card
            bottom = cy + ch
            top = cy
            # Lift so the last tspan baseline (+ descent) clears the card floor.
            max_y = bottom - _CARD_PAD - descent - block_depth
            if new_y > max_y:
                new_y = max(top + new_fs + 4.0, max_y)
            # Keep left/right inset inside the card. Only left-rail icon badges
            # (medium circles near the card's left edge) reserve the left band —
            # chart dots / network nodes (r≲12) must not pin min_x to the
            # right edge and trap column copy there.
            min_x = cx + _CARD_PAD
            left_rail = cx + min(96.0, max(48.0, cw * 0.22))
            for icx, icy, ir in icons:
                if ir < 14.0 or ir > 48.0:
                    continue
                if icx > left_rail:
                    continue
                if cx - 2 <= icx <= cx + cw + 2 and cy - 2 <= icy <= cy + ch + 2:
                    min_x = max(min_x, icx + ir + 6.0)
            max_right = cx + cw - _CARD_PAD
            if left < min_x:
                shift = min_x - left
                new_x += shift
                left += shift
                right += shift
            # Prefer sliding left into free space before crushing the font.
            if right > max_right and not anchor_end and not anchor_mid:
                shifted = max(min_x, max_right - width)
                if shifted + 0.5 < new_x:
                    new_x = shifted
                    left = new_x
                    right = new_x + width
            # Column cards with a left-rail icon: start-anchored titles/body that
            # the model parked in the right half belong on the left rail (next
            # to the badge), not merely clipped to the card's right edge.
            has_left_icon = min_x > cx + _CARD_PAD + 1.0
            if (
                has_left_icon
                and not anchor_end
                and not anchor_mid
                and len(plain) >= 8
                and new_x > cx + cw * 0.35
            ):
                new_x = min_x
                left = new_x
                right = new_x + width
            # Equations / long formulas need deeper shrink to stay in the plate.
            # Require spaced operators — bare "n=400" in prose must not qualify.
            has_structured_tspans = len(tspan_lines) >= 2
            is_formula = bool(
                (
                    re.search(r"\s[=+*/]\s", plain)
                    or re.search(r"(?:Delta|\\[a-zA-Z]+|\bJ\()\s*", plain)
                )
                and len(plain) >= 18
                and new_fs >= 16
                and not has_structured_tspans
            )
            # Multi-line tspans: width is longest line, never joined character count.
            def _line_width(fs_v: float) -> float:
                if tspan_lines:
                    return max(8.0, max(len(line) for line in tspan_lines) * fs_v * em)
                return max(8.0, len(plain) * fs_v * em)

            min_fs = 10.0 if is_formula else 11.0
            if (right > max_right or left < min_x) and new_fs > min_fs:
                avail = max(24.0, max_right - min_x)
                scale = min(1.0, avail / max(width, 1.0))
                if is_formula:
                    scale = min(scale, 0.92)
                new_fs = max(min_fs, new_fs * max(0.55 if is_formula else 0.72, scale))
                width = _line_width(new_fs)
                if anchor_mid:
                    # Keep centered inside the card after shrink.
                    new_x = (min_x + max_right) / 2.0
                    left = new_x - width / 2
                    right = new_x + width / 2
                elif anchor_end:
                    new_x = max_right
                    left = new_x - width
                    right = new_x
                else:
                    right = new_x + width
                    if right > max_right:
                        new_x = max(min_x, max_right - width)
                        right = new_x + width
                    left = new_x
            # Soft vertical fit: body lines that spill the card bottom.
            if new_y > max_y and new_fs > min_fs + 1:
                new_fs = max(min_fs, new_fs * 0.9)
                new_y = max(top + new_fs + 4.0, max_y)

            # Long equations: wrap at an operator instead of crushing to unreadability.
            # Never flatten authored multi-tspan blocks into sibling <text> nodes.
            width = _line_width(new_fs)
            right = (
                new_x
                if anchor_end
                else (new_x + width / 2 if anchor_mid else new_x + width)
            )
            if (
                is_formula
                and not has_structured_tspans
                and not anchor_end
                and not anchor_mid
                and right > max_right + 1.0
                and len(plain) >= 28
            ):
                split = _split_formula_line(plain)
                if split:
                    line1, line2 = split
                    avail = max(24.0, max_right - min_x)
                    wrap_fs = new_fs
                    for _ in range(4):
                        w1 = len(line1) * wrap_fs * em
                        w2 = len(line2) * wrap_fs * em
                        if max(w1, w2) <= avail:
                            break
                        wrap_fs = max(min_fs, wrap_fs * 0.9)
                    line_gap = max(16.0, wrap_fs * 1.2)
                    y2 = min(max_y, new_y + line_gap)
                    # Keep the first line; emit a sibling for the continuation.
                    attrs1 = re.sub(
                        r'\bfont-size="[^"]*"',
                        f'font-size="{wrap_fs:g}"',
                        new_attrs,
                        count=1,
                    )
                    attrs1 = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', attrs1, count=1)
                    attrs1 = re.sub(r'\by="[^"]*"', f'y="{new_y:g}"', attrs1, count=1)
                    attrs2 = re.sub(
                        r'\bfont-size="[^"]*"',
                        f'font-size="{wrap_fs:g}"',
                        new_attrs,
                        count=1,
                    )
                    attrs2 = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', attrs2, count=1)
                    attrs2 = re.sub(r'\by="[^"]*"', f'y="{y2:g}"', attrs2, count=1)
                    return (
                        f"<text{attrs1}>{line1}</text>"
                        f"<text{attrs2}>{line2}</text>"
                    )

        if right > _SLIDE_RIGHT and new_fs > 12.0 and not is_title_band:
            over = right - _SLIDE_RIGHT
            scale = max(0.7, 1.0 - over / max(width, 1.0))
            new_fs = max(12.0, new_fs * scale)
            width = max(8.0, measure * new_fs * em)
            if anchor_mid:
                right = new_x + width / 2
                left = new_x - width / 2
            elif not anchor_end:
                right = new_x + width
        if left < _SLIDE_PAD and not anchor_end:
            if anchor_mid:
                new_x = max(new_x, _SLIDE_PAD + width / 2)
            else:
                new_x = max(new_x, _SLIDE_PAD)
            left = new_x - width / 2 if anchor_mid else new_x
            right = new_x + width / 2 if anchor_mid else new_x + width

        if abs(new_x - x) > 0.01:
            new_attrs = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', new_attrs, count=1)
        if y_m and abs(new_y - y) > 0.01:
            new_attrs = re.sub(r'\by="[^"]*"', f'y="{new_y:g}"', new_attrs, count=1)
        elif not y_m and abs(new_y - y) > 0.01:
            new_attrs = f'{new_attrs} y="{new_y:g}"'
        if abs(new_fs - fs) > 0.01:
            new_attrs = re.sub(
                r'\bfont-size="[^"]*"',
                f'font-size="{new_fs:g}"',
                new_attrs,
                count=1,
            )
        if new_attrs == attrs:
            return match.group(0)
        return f"<text{new_attrs}>{body}</text>"

    return re.sub(
        r"<text\b([^>]*)>([\s\S]*?)</text>",
        _rewrite,
        svg,
        flags=re.I,
    )


def _text_anchor_points(svg: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for match in re.finditer(r"<text\b([^>]*)>", svg or "", flags=re.I):
        attrs = match.group(1)
        try:
            x = float(re.search(r'\bx="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
        except (AttributeError, ValueError, TypeError):
            continue
        points.append((x, y))
    return points


def _point_in_band(x: float, y: float, band: tuple[float, float, float, float]) -> bool:
    bx, by, bw, bh = band
    return bx <= x <= bx + bw and by <= y <= by + bh


def table_covers_content_issues(svg: str, *, slide: int) -> list[dict[str, Any]]:
    """Emit QA issues when a table carrier heavily overlaps figures/content/text."""
    issues: list[dict[str, Any]] = []
    images = _rects_from_images(svg)
    text_points = _text_anchor_points(svg)
    for match in re.finditer(
        r'<g\b[^>]*data-pptx-replace-with="table"[^>]*>.*?<metadata\b[^>]*>(.*?)</metadata>',
        svg or "",
        flags=re.I | re.S,
    ):
        try:
            payload = json.loads(
                __import__("html").unescape(match.group(1)).strip()
            )
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        try:
            band = (
                float(payload.get("x") or 0),
                float(payload.get("y") or 0),
                float(payload.get("width") or 0),
                float(payload.get("height") or 0),
            )
        except (TypeError, ValueError):
            continue
        for img in images:
            area = _intersection_area(band, img)
            if area > 8000:
                issues.append(
                    {
                        "severity": "error",
                        "category": "table-covers-content",
                        "slide": slide,
                        "message": (
                            f"Table carrier overlaps figure "
                            f"({area:.0f}px² intersection)"
                        ),
                    }
                )
                break
        # Table painted over freehand prose (anchors inside the carrier band).
        # Ignore text that is itself inside the table group by counting only
        # anchors clearly in the band while the carrier is large.
        covered_text = sum(1 for x, y in text_points if _point_in_band(x, y, band))
        if covered_text >= 4 and band[2] * band[3] > 80_000:
            issues.append(
                {
                    "severity": "error",
                    "category": "table-covers-content",
                    "slide": slide,
                    "message": (
                        f"Table carrier overlaps authored text "
                        f"({covered_text} text anchors inside band)"
                    ),
                }
            )
        # Near-full-bleed table over dense authored content.
        vw, vh = viewbox_dims(svg)
        content_area = max(1.0, vw * vh * 0.55)
        if band[2] * band[3] > content_area * 0.55 and _count_content_cards(svg) >= 2:
            issues.append(
                {
                    "severity": "error",
                    "category": "table-covers-content",
                    "slide": slide,
                    "message": "Table carrier covers most of the content area over authored cards",
                }
            )
    return issues


def canvas_margin_issues(svg: str, *, slide: int, margin: float = _MARGIN) -> list[dict[str, Any]]:
    """Flag text/images/tables that escape the safe viewBox inset."""
    vw, vh = viewbox_dims(svg)
    issues: list[dict[str, Any]] = []
    safe = (margin, margin, vw - 2 * margin, vh - 2 * margin)

    def _outside(x: float, y: float, w: float = 0, h: float = 0) -> bool:
        return (
            x < safe[0] - 0.5
            or y < safe[1] - 0.5
            or x + w > safe[0] + safe[2] + 0.5
            or y + h > safe[1] + safe[3] + 0.5
        )

    for match in re.finditer(r"<image\b([^>]*)>", svg or "", flags=re.I):
        attrs = match.group(1)
        try:
            x = float(re.search(r'\bx="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
        except (AttributeError, ValueError, TypeError):
            continue
        if _outside(x, y, w, h):
            issues.append(
                {
                    "severity": "error",
                    "category": "canvas-margin",
                    "slide": slide,
                    "message": f"Image escapes {margin:g}px canvas margin",
                }
            )

    for match in re.finditer(
        r'<g\b[^>]*data-pptx-replace-with="table"[^>]*>.*?<metadata\b[^>]*>(.*?)</metadata>',
        svg or "",
        flags=re.I | re.S,
    ):
        try:
            payload = json.loads(__import__("html").unescape(match.group(1)).strip())
            x = float(payload.get("x") or 0)
            y = float(payload.get("y") or 0)
            w = float(payload.get("width") or 0)
            h = float(payload.get("height") or 0)
        except Exception:
            continue
        if _outside(x, y, w, h):
            issues.append(
                {
                    "severity": "error",
                    "category": "canvas-margin",
                    "slide": slide,
                    "message": f"Table carrier escapes {margin:g}px canvas margin",
                }
            )

    for match in re.finditer(r"<text\b([^>]*)>", svg or "", flags=re.I):
        attrs = match.group(1)
        try:
            x = float(re.search(r'\bx="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([^"]+)"', attrs, re.I).group(1))  # type: ignore[union-attr]
        except (AttributeError, ValueError, TypeError):
            continue
        if x < margin - 0.5 or y > vh - margin + 0.5 or x > vw - margin:
            issues.append(
                {
                    "severity": "error",
                    "category": "canvas-margin",
                    "slide": slide,
                    "message": f"Text anchor ({x:g},{y:g}) outside {margin:g}px margin",
                }
            )
            break  # one per slide is enough to block
    return issues
