"""Mechanical complementary-column narrative for figure/table slides (IR only)."""

from __future__ import annotations

import html
import re
from typing import Any, Callable

_FIGURE_CLAIMS_RE = re.compile(
    r'<g\b[^>]*\bdata-sunairum-figure-claims="1"[^>]*>[\s\S]*?</g>\s*',
    flags=re.I,
)
_TABLE_ASIDE_RE = re.compile(
    r'<g\b[^>]*\bdata-sunairum-table-aside="1"[^>]*>[\s\S]*?</g>\s*',
    flags=re.I,
)
# §IX Content block: stop at the next same-indent field, not nested **Label:** bullets.
_CONTENT_SECTION_RE = re.compile(
    r"(?ims)^(?P<indent>[ \t]*)[-*]\s*\*\*Content:?\*\*\s*:?\s*\n"
    r"(?P<body>.*?)"
    r"(?=^(?P=indent)[-*]\s*\*\*[A-Za-z]|\Z)",
)
_LABELED_BULLET_RE = re.compile(
    r"^\s*[-*•]\s+\*\*([^*\n:]+):\*\*\s*(.+)$",
    flags=re.M,
)


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


# A list marker is a bullet glyph, or a small integer followed by a separator
# and a space. It is NOT "any leading digit": stripping the whole character
# class `[\s•\-\*\d\.\)\(]+` walks straight past the marker and on into the
# sentence, so "1. 1,74x fewer evaluations" lost the 1 of 1,74 and reached the
# slide as ",74x" -- a metric silently changed by a factor of a hundred. The
# guard that decides a line *is* a list item already knows exactly how long the
# marker is; this strips that and nothing more.
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*\u2022\u2023\u25e6\u2043\u2219]+|\(?\d{1,3}[.)])\s+")


def strip_list_marker(line: str) -> str:
    """Remove one leading list marker from `line`, leaving its content intact."""
    return _LIST_MARKER_RE.sub("", line or "", count=1).strip()


def extract_content_bullets(pack: str) -> list[str]:
    """Audience Content bullets from §IX — Label: body lines only.

    Nested ``- **Feature encoder:** …`` must NOT terminate the Content block
    (that bug emptied figure/table claim panels).
    """
    if not pack:
        return []
    match = _CONTENT_SECTION_RE.search(pack)
    if not match:
        return []
    bullets: list[str] = []
    for line in match.group("body").splitlines():
        labeled = _LABELED_BULLET_RE.match(line)
        if labeled:
            label = labeled.group(1).strip()
            body = labeled.group(2).strip()
            if not body:
                continue
            low = label.casefold()
            if low in {"figure", "table"} or low.startswith("figure") or low.startswith(
                "table"
            ):
                continue
            bullets.append(f"{label}: {body}"[:220])
            continue
        if not re.match(r"^\s*(?:[-*•]|\d+[.)])\s+\S", line):
            continue
        cleaned = strip_list_marker(line)
        cleaned = re.sub(r"^\*\*?|\*\*?$", "", cleaned).strip()
        # Normalize leftover ``Label:** body`` after stripping bold markers.
        cleaned = re.sub(r"^([^*\n:]+):\*\*\s*", r"\1: ", cleaned)
        if not cleaned or cleaned.casefold() in {"figure", "table"}:
            continue
        if cleaned.casefold().startswith("figure:") or cleaned.casefold().startswith(
            "table:"
        ):
            continue
        bullets.append(cleaned[:220])
    return bullets


def _count_narrative_in_band(
    svg: str,
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> int:
    n = 0
    for match in re.finditer(r"<text\b([^>]*)>", svg or "", flags=re.I):
        attrs = match.group(1) or ""
        if re.search(
            r"data-sunairum-(?:source-table-text|page-number|table-insight|"
            r"figure-claims|table-aside|formula)",
            attrs,
            flags=re.I,
        ):
            continue
        xm = re.search(r'\bx="([-\d.]+)"', attrs)
        ym = re.search(r'\by="([-\d.]+)"', attrs)
        if not xm or not ym:
            continue
        x, y = float(xm.group(1)), float(ym.group(1))
        if x0 <= x <= x1 and y0 <= y <= y1:
            n += 1
    return n


def _figure_aabb(svg: str) -> tuple[float, float, float, float] | None:
    m = re.search(
        r'<image\b([^>]*\bdata-sunairum-figure-id="[^"]*"[^>]*)/?>',
        svg or "",
        flags=re.I,
    )
    if m:
        attrs = m.group(1) or ""
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            return (x, y, w, h)
        except (AttributeError, TypeError, ValueError):
            pass
    try:
        from tasks.intent_hosts import parse_figure_host_aabb
    except ImportError:  # pragma: no cover
        from intent_hosts import parse_figure_host_aabb  # type: ignore
    return parse_figure_host_aabb(svg)


_META_CLAIM_LABELS = frozenset(
    {
        "title",
        "core message",
        "layout",
        "figure",
        "table",
        "evidence",
        "visual job",
        "visualization",
        "page rhythm",
        "structure",
        "audience move",
        "content",
        "topic",
        "grounding mode",
        "audience",
        "communication intent",
        "selected figures",
        "selected tables",
        "content page count",
        "figure evidence",
    }
)


def _ix_labeled_claim_fallback(pack: str) -> list[str]:
    """Labeled bullets from §IX when Content block is missing/empty."""
    scope = pack or ""
    ix = re.search(r"(?im)^##\s*IX\b.*$", scope)
    if ix:
        scope = scope[ix.start() :]
    items: list[str] = []
    for match in _LABELED_BULLET_RE.finditer(scope):
        label = match.group(1).strip()
        body = match.group(2).strip()
        if not body or label.casefold() in _META_CLAIM_LABELS:
            continue
        line = f"{label}: {body}"
        if line not in items:
            items.append(line[:160])
        if len(items) >= 4:
            break
    return items


def _claim_items(
    svg: str,
    pack: str,
    slide: dict[str, Any],
    fill_items_fn: Callable[[str, str, dict[str, Any] | None], list[str]] | None,
) -> list[str]:
    items: list[str] = []
    # Prefer §IX Content — never scrape Topic / Audience / Grounding preamble.
    for line in extract_content_bullets(pack):
        if line and line not in items:
            items.append(line[:160])
        if len(items) >= 4:
            break
    if len(items) < 2:
        for line in _ix_labeled_claim_fallback(pack):
            if line and line not in items:
                items.append(line)
            if len(items) >= 4:
                break
    if len(items) >= 2:
        return items[:4]
    if fill_items_fn is not None:
        for line in fill_items_fn(svg, pack, slide) or []:
            if line and line not in items:
                items.append(line[:160])
            if len(items) >= 4:
                break
    if not items:
        core = str(slide.get("core_message") or "").strip()
        if core:
            items = [core]
    return items[:4]


def _theme_from_slide(slide: dict[str, Any] | None) -> dict[str, str]:
    data = slide if isinstance(slide, dict) else {}
    palette = data.get("_color_palette") if isinstance(data.get("_color_palette"), dict) else {}
    if not palette:
        palette = data.get("color_palette") if isinstance(data.get("color_palette"), dict) else {}
    accent = str(
        palette.get("accent")
        or palette.get("secondary_accent")
        or palette.get("primary")
        or "#3182CE"
    )
    surface = str(
        palette.get("accent_tint")
        or palette.get("secondary_bg")
        or "#EBF4FF"
    )
    return {
        "accent": accent,
        "ink": str(palette.get("primary") or palette.get("body_text") or "#1A365D"),
        "muted": str(palette.get("text_secondary") or "#4A5568"),
        "surface": surface,
        "border": str(palette.get("border") or "#E2E8F0"),
    }


def _paint_claim_stack(
    items: list[str],
    *,
    x: float,
    y: float,
    w: float,
    marker: str,
    accent: str = "#3182CE",
    ink: str = "#1A365D",
    muted: str = "#4A5568",
    surface: str = "#EBF4FF",
    border: str = "#E2E8F0",
    min_h: float = 0.0,
) -> str:
    if not items:
        return ""
    # Label + body needs ~56px; allow denser stacks when min_h forces a tall panel.
    row_h = 56.0
    content_h = 16.0 + len(items) * row_h
    if min_h > 0:
        h = max(min_h, min(480.0, content_h))
        # Stretch row pitch so 3–4 claims fill the figure column height.
        if len(items) >= 2:
            row_h = max(48.0, min(72.0, (h - 24.0) / len(items)))
    else:
        h = min(420.0, content_h)
    parts = [
        f'<g {marker}="1" transform="translate({x:g},{y:g})">',
        f'<rect x="0" y="0" width="{w:g}" height="{h:g}" rx="10" fill="{_esc(surface)}" '
        f'stroke="{_esc(border)}" stroke-width="1"/>',
        f'<rect x="0" y="0" width="5" height="{h:g}" rx="2" fill="{_esc(accent)}"/>',
    ]
    cy = 28.0
    for item in items:
        block_top = cy
        if ":" in item[:40]:
            label, _, body = item.partition(":")
            parts.append(
                f'<text x="20" y="{cy:g}" font-family="Arial, sans-serif" font-size="14" '
                f'font-weight="700" fill="{_esc(ink)}">{_esc(label.strip())}</text>'
            )
            cy += 18.0
            parts.append(
                f'<text x="20" y="{cy:g}" font-family="Arial, sans-serif" font-size="14" '
                f'fill="{_esc(muted)}">{_esc(body.strip()[:140])}</text>'
            )
        else:
            parts.append(
                f'<text x="20" y="{cy:g}" font-family="Arial, sans-serif" font-size="15" '
                f'fill="{_esc(ink)}">{_esc(item[:160])}</text>'
            )
        cy = block_top + row_h
        if cy > h - 12:
            break
    parts.append("</g>")
    return "".join(parts)


def _shrink_full_bleed_figure(svg: str, figure_id: str) -> str:
    """Snap over-wide PDF figures to the right host so a claim column fits."""
    out = svg or ""
    fid = str(figure_id or "").strip()
    if not fid:
        return out
    pattern = re.compile(
        rf'(<image\b[^>]*\bdata-sunairum-figure-id="{re.escape(fid)}"[^>]*)(/?>)',
        flags=re.I,
    )
    match = pattern.search(out)
    if not match:
        return out
    attrs = match.group(1)
    try:
        fx = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        fy = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        fw = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        fh = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
    except (AttributeError, TypeError, ValueError):
        return out
    left_w = fx - 60.0 - 24.0
    right_w = 1220.0 - (fx + fw + 24.0)
    if max(left_w, right_w) >= 200.0 and fw <= 720.0:
        return out
    try:
        from tasks.intent_hosts import FIGURE_HOST
    except ImportError:  # pragma: no cover
        from intent_hosts import FIGURE_HOST  # type: ignore
    nx, ny, nw, nh = FIGURE_HOST
    # Keep vertical position when already in the content band.
    if 140.0 <= fy <= 220.0:
        ny = fy
    new_attrs = attrs
    for name, value in (("x", nx), ("y", ny), ("width", nw), ("height", nh)):
        if re.search(rf'\b{name}="', new_attrs, flags=re.I):
            new_attrs = re.sub(
                rf'\b{name}="[^"]*"',
                f'{name}="{value:g}"',
                new_attrs,
                count=1,
                flags=re.I,
            )
        else:
            new_attrs = f'{new_attrs} {name}="{value:g}"'
    return out[: match.start()] + new_attrs + match.group(2) + out[match.end() :]


def ensure_figure_claim_column(
    svg: str,
    slide: dict[str, Any],
    pack: str = "",
    *,
    fill_items_fn: Callable[[str, str, dict[str, Any] | None], list[str]] | None = None,
) -> str:
    """Fill complementary band beside a figure from IR claims when empty."""
    out = _FIGURE_CLAIMS_RE.sub("", svg or "")
    fid = str(slide.get("figure_id") or "").strip()
    if not fid or fid.casefold() in {"none", "null", "n/a", "-"}:
        return out
    # Claim shells own the left column — never stack figure-claims on top.
    if 'data-sunairum-claim-shell="' in out:
        return out
    out = _shrink_full_bleed_figure(out, fid)
    aabb = _figure_aabb(out)
    if not aabb:
        return out
    fx, fy, fw, fh = aabb
    fcx = fx + fw / 2.0
    if fcx < 640:
        bx0, bx1 = fx + fw + 24.0, 1220.0
    else:
        bx0, bx1 = 60.0, fx - 24.0
    by0, by1 = max(140.0, fy), min(620.0, fy + fh + 40.0)
    if bx1 - bx0 < 160:
        return out
    # Empty husk cards / accent strips left by the executor must not block densify.
    husk_n = _count_narrative_in_band(out, x0=bx0, y0=by0, x1=bx1, y1=by1)
    if husk_n >= 2:
        # Require real claim prose (≥18 chars), not orphan labels.
        real = 0
        for match in re.finditer(
            r"<text\b([^>]*)>([\s\S]*?)</text>", out or "", flags=re.I
        ):
            attrs, body = match.group(1) or "", match.group(2) or ""
            if "data-sunairum-" in attrs:
                continue
            xm = re.search(r'\bx="([-\d.]+)"', attrs)
            ym = re.search(r'\by="([-\d.]+)"', attrs)
            if not xm or not ym:
                continue
            x, y = float(xm.group(1)), float(ym.group(1))
            if not (bx0 <= x <= bx1 and by0 <= y <= by1):
                continue
            plain = re.sub(r"<[^>]+>", " ", body)
            plain = re.sub(r"\s+", " ", plain).strip()
            if len(plain) >= 18:
                real += 1
        if real >= 2:
            return out
        out = _strip_sparse_aside_chips(out, bx0, by0, bx1, by1)
    items = _claim_items(out, pack, slide, fill_items_fn)
    if len(items) < 1:
        return out
    theme = _theme_from_slide(slide)
    span_h = max(160.0, by1 - by0)
    panel = _paint_claim_stack(
        items,
        x=bx0,
        y=by0,
        w=max(180.0, bx1 - bx0),
        marker="data-sunairum-figure-claims",
        accent=theme["accent"],
        ink=theme["ink"],
        muted=theme["muted"],
        surface=theme["surface"],
        border=theme["border"],
        min_h=span_h,
    )
    if "</svg>" in out:
        return re.sub(r"</svg>\s*$", panel + "\n</svg>", out, count=1, flags=re.I)
    return out + panel


def ensure_table_aside_panel(
    svg: str,
    slide: dict[str, Any],
    pack: str = "",
    *,
    fill_items_fn: Callable[[str, str, dict[str, Any] | None], list[str]] | None = None,
) -> str:
    """Always paint a full-height claim column beside a right-biased table host."""
    out = _TABLE_ASIDE_RE.sub("", svg or "")
    tid = str(slide.get("table_id") or "").strip()
    if not tid or tid.casefold() in {"none", "null", "n/a", "-"}:
        return out
    # Claim shells own the left column — never stack aside on top (M5).
    if 'data-sunairum-claim-shell="' in out:
        return out
    try:
        from tasks.intent_hosts import table_host_aabb
    except ImportError:  # pragma: no cover
        from intent_hosts import table_host_aabb  # type: ignore
    tx, ty, tw, th = table_host_aabb(out)
    tcx = tx + tw / 2.0
    if tcx >= 640:
        bx0, bx1 = 60.0, tx - 24.0
    else:
        bx0, bx1 = tx + tw + 24.0, 1220.0
    by0 = max(140.0, ty)
    by1 = min(620.0, ty + th)
    if bx1 - bx0 < 160:
        return out
    span_h = by1 - by0
    # Skip when the aside already has a real upper-column narrative (≥2 texts
    # in the top 70%). Bottom-only chips (SCOPE) do not count — we replace them.
    upper_n = _count_narrative_in_band(
        out, x0=bx0, y0=by0, x1=bx1, y1=by0 + max(80.0, span_h * 0.7)
    )
    if upper_n >= 2:
        return out
    narrative_n = _count_narrative_in_band(out, x0=bx0, y0=by0, x1=bx1, y1=by1)
    items = _claim_items(out, pack, slide, fill_items_fn)
    if len(items) < 1:
        core = str(slide.get("core_message") or "").strip()
        items = [core] if core else ["Key result from this table."]
    # Drop sparse bottom chips in the aside (e.g. lone SCOPE box) so the
    # full-height panel owns the column.
    if narrative_n <= 3:
        out = _strip_sparse_aside_chips(out, bx0, by0, bx1, by1)
    theme = _theme_from_slide(slide)
    panel = _paint_claim_stack(
        items,
        x=bx0,
        y=by0,
        w=max(180.0, bx1 - bx0),
        marker="data-sunairum-table-aside",
        accent=theme["accent"],
        ink=theme["ink"],
        muted=theme["muted"],
        surface=theme["surface"],
        border=theme["border"],
        min_h=max(160.0, span_h),
    )
    if "</svg>" in out:
        return re.sub(r"</svg>\s*$", panel + "\n</svg>", out, count=1, flags=re.I)
    return out + panel


def _strip_sparse_aside_chips(
    svg: str, x0: float, y0: float, x1: float, y1: float
) -> str:
    """Remove small freehand cards parked in the table aside column."""
    out = svg or ""
    deletes: list[tuple[int, int]] = []
    for match in re.finditer(r"<rect\b([^>]*)/?>", out, flags=re.I):
        attrs = match.group(1) or ""
        if "data-sunairum-" in attrs:
            continue
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if not (x0 - 4 <= x and x + w <= x1 + 4 and y0 - 4 <= y and y + h <= y1 + 4):
            continue
        # Small chip / accent strip in aside — not the page background.
        if w < 520 and 40 <= h <= 220:
            deletes.append((match.start(), match.end()))
    # Also drop texts that lived only inside those chips (lower half aside).
    for match in re.finditer(r"<text\b([^>]*)>([\s\S]*?)</text>", out, flags=re.I):
        attrs = match.group(1) or ""
        if "data-sunairum-" in attrs:
            continue
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if x0 <= x <= x1 and y0 <= y <= y1:
            deletes.append((match.start(), match.end()))
    for start, end in sorted(set(deletes), key=lambda s: s[0], reverse=True):
        out = out[:start] + out[end:]
    return out
