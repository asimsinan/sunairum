"""Preferred host AABBs + canonical table/formula host contract."""

from __future__ import annotations

import re
from typing import Any

# Soft preferred bands (Executor may place hosts elsewhere; inject uses declared slot).
FIGURE_HOST = (640.0, 160.0, 580.0, 400.0)
TABLE_HOST = (588.0, 160.0, 632.0, 440.0)
# Compact equation band (MathML is single-line; tall hosts caused empty panels).
FORMULA_HOST = (60.0, 200.0, 1160.0, 96.0)

_TABLE_SLOT_OPEN_RE = re.compile(
    r"<g\b([^>]*\bdata-sunairum-table-slot\b[^>]*)>([\s\S]*?)</g>",
    flags=re.I,
)


def preferred_host_aabb(kind: str) -> tuple[float, float, float, float]:
    key = (kind or "").strip().casefold()
    if key == "table":
        return TABLE_HOST
    if key == "formula":
        return FORMULA_HOST
    return FIGURE_HOST


def _esc(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _attr(attrs: str, name: str) -> str | None:
    match = re.search(rf'\b{name}\s*=\s*"([^"]*)"', attrs or "", flags=re.I)
    if match:
        return match.group(1)
    match = re.search(rf"\b{name}\s*=\s*'([^']*)'", attrs or "", flags=re.I)
    return match.group(1) if match else None


def _num_attr(attrs: str, name: str) -> float | None:
    raw = _attr(attrs, name)
    if raw is None or not str(raw).strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_table_host_aabb(
    svg: str,
) -> tuple[float, float, float, float] | None:
    """Parse first table-slot AABB from transform+rect or bare x/y/width/height."""
    for match in _TABLE_SLOT_OPEN_RE.finditer(svg or ""):
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        tr = re.search(
            r'transform\s*=\s*"translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"',
            attrs,
            flags=re.I,
        )
        rw = re.search(r'<rect\b[^>]*\bwidth\s*=\s*"([-\d.]+)"', body, flags=re.I)
        rh = re.search(r'<rect\b[^>]*\bheight\s*=\s*"([-\d.]+)"', body, flags=re.I)
        if tr and rw and rh:
            return (
                float(tr.group(1)),
                float(tr.group(2)),
                float(rw.group(1)),
                float(rh.group(1)),
            )
        x = _num_attr(attrs, "x")
        y = _num_attr(attrs, "y")
        w = _num_attr(attrs, "width")
        h = _num_attr(attrs, "height")
        if None not in (x, y, w, h):
            assert x is not None and y is not None and w is not None and h is not None
            return (x, y, w, h)
    return None


def has_table_slot_marker(svg: str) -> bool:
    return bool(re.search(r"\bdata-sunairum-table-slot\b", svg or "", flags=re.I))


_FIGURE_SLOT_OPEN_RE = re.compile(
    r"<g\b([^>]*\bdata-sunairum-figure-slot\b[^>]*)>([\s\S]*?)</g>",
    flags=re.I,
)


def has_figure_slot_marker(svg: str) -> bool:
    return bool(re.search(r"\bdata-sunairum-figure-slot\b", svg or "", flags=re.I))


def has_bound_figure_image(svg: str, figure_id: str) -> bool:
    fid = str(figure_id or "").strip()
    if not fid:
        return False
    return bool(
        re.search(
            rf'<image\b[^>]*\bdata-sunairum-figure-id="{re.escape(fid)}"',
            svg or "",
            flags=re.I,
        )
    )


def parse_figure_host_aabb(
    svg: str,
) -> tuple[float, float, float, float] | None:
    for match in _FIGURE_SLOT_OPEN_RE.finditer(svg or ""):
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        tr = re.search(
            r'transform\s*=\s*"translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"',
            attrs,
            flags=re.I,
        )
        rw = re.search(r'<rect\b[^>]*\bwidth\s*=\s*"([-\d.]+)"', body, flags=re.I)
        rh = re.search(r'<rect\b[^>]*\bheight\s*=\s*"([-\d.]+)"', body, flags=re.I)
        if tr and rw and rh:
            return (
                float(tr.group(1)),
                float(tr.group(2)),
                float(rw.group(1)),
                float(rh.group(1)),
            )
        x = _num_attr(attrs, "x")
        y = _num_attr(attrs, "y")
        w = _num_attr(attrs, "width")
        h = _num_attr(attrs, "height")
        if None not in (x, y, w, h):
            assert x is not None and y is not None and w is not None and h is not None
            return (x, y, w, h)
    return None


def has_canonical_figure_slot(svg: str) -> bool:
    for match in _FIGURE_SLOT_OPEN_RE.finditer(svg or ""):
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        slot = (_attr(attrs, "data-sunairum-figure-slot") or "").strip()
        if slot not in {"1", "true", "injected", ""}:
            # Accept common polymorphic truthy forms; reject explicit "0"/"false".
            if slot.casefold() in {"0", "false", "no"}:
                continue
        if not re.search(r'transform\s*=\s*"translate\(', attrs, flags=re.I):
            continue
        if not re.search(r"<rect\b[^>]*\bwidth\s*=", body, flags=re.I):
            continue
        return True
    return False


def canonical_figure_host_markup(
    fid: str,
    aabb: tuple[float, float, float, float] | None = None,
) -> str:
    x, y, w, h = aabb or FIGURE_HOST
    return (
        f'<g data-sunairum-figure-slot="1" data-sunairum-figure-id="{_esc(fid)}" '
        f'transform="translate({x:g},{y:g})">'
        f'<rect width="{w:g}" height="{h:g}" fill="none"/></g>'
    )


def normalize_figure_host(svg: str, slide: dict[str, Any]) -> str:
    """Coerce polymorphic figure slots to one canonical empty host."""
    fid = str(slide.get("figure_id") or "").strip()
    if not fid or fid.casefold() in {"none", "null", "n/a", "-"}:
        return svg or ""
    out = svg or ""
    if has_bound_figure_image(out, fid):
        # Image already placed — drop empty duplicate slots only.
        out = re.sub(
            r"<g\b[^>]*\bdata-sunairum-figure-slot\b[^>]*>"
            r"(?:(?!<image\b)[\s\S])*?</g>\s*",
            "",
            out,
            flags=re.I,
        )
        return out
    parsed = parse_figure_host_aabb(out)
    aabb = parsed or FIGURE_HOST
    # Prefer preferred right host when parsed is tiny / missing.
    if parsed and (parsed[2] < 280 or parsed[3] < 200):
        aabb = FIGURE_HOST
    out = re.sub(
        r"<g\b[^>]*\bdata-sunairum-figure-slot\b[^>]*>[\s\S]*?</g>\s*",
        "",
        out,
        flags=re.I,
    )
    host = canonical_figure_host_markup(fid, aabb)
    if "</svg>" in out:
        return re.sub(r"</svg>\s*$", host + "\n</svg>", out, count=1, flags=re.I)
    return out + "\n" + host


def has_canonical_table_slot(svg: str) -> bool:
    """True when a slot uses slot=\"1\" + transform + inner rect (canonical)."""
    for match in _TABLE_SLOT_OPEN_RE.finditer(svg or ""):
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        slot = (_attr(attrs, "data-sunairum-table-slot") or "").strip()
        if slot != "1":
            continue
        if not re.search(r'transform\s*=\s*"translate\(', attrs, flags=re.I):
            continue
        if not re.search(r"<rect\b[^>]*\bwidth\s*=", body, flags=re.I):
            continue
        return True
    return False


def canonical_table_host_markup(
    tid: str,
    aabb: tuple[float, float, float, float] | None = None,
) -> str:
    x, y, w, h = aabb or TABLE_HOST
    return (
        f'<g data-sunairum-table-slot="1" data-sunairum-table-id="{_esc(tid)}" '
        f'data-pptx-replace-with="table" transform="translate({x:g},{y:g})">'
        f'<rect width="{w:g}" height="{h:g}" fill="none"/></g>'
    )


def normalize_table_host(svg: str, slide: dict[str, Any]) -> str:
    """Coerce polymorphic table slots to one canonical host; drop duplicates."""
    tid = str(slide.get("table_id") or "").strip()
    if not tid or tid.casefold() in {"none", "null", "n/a", "-"}:
        return svg or ""
    out = svg or ""
    band = slide.get("_table_band") if isinstance(slide.get("_table_band"), dict) else None
    preferred = TABLE_HOST
    if band:
        preferred = (
            float(band.get("x", TABLE_HOST[0])),
            float(band.get("y", TABLE_HOST[1])),
            float(band.get("w", TABLE_HOST[2])),
            float(band.get("h", TABLE_HOST[3])),
        )
    parsed = parse_table_host_aabb(out)
    aabb = parsed or preferred
    # Remove every table-slot group (any attribute form).
    out = re.sub(
        r"<g\b[^>]*\bdata-sunairum-table-slot\b[^>]*>[\s\S]*?</g>\s*",
        "",
        out,
        flags=re.I,
    )
    # Also drop bare empty preferred duplicates left as data-table-id only hosts.
    out = re.sub(
        r"<g\b[^>]*\bdata-table-id\s*=\s*\"[^\"]*\"[^>]*>\s*</g>\s*",
        "",
        out,
        flags=re.I,
    )
    host = canonical_table_host_markup(tid, aabb)
    if "</svg>" in out:
        return re.sub(r"</svg>\s*$", host + "\n</svg>", out, count=1, flags=re.I)
    return out + "\n" + host


def ensure_asset_hosts(svg: str, slide: dict[str, Any]) -> str:
    """Inject/normalize empty figure/table/formula hosts when bound."""
    out = svg or ""
    tid = str(slide.get("table_id") or "").strip()
    if tid and tid.casefold() not in {"none", "null", "n/a", "-"}:
        if has_table_slot_marker(out):
            out = normalize_table_host(out, slide)
        else:
            band = slide.get("_table_band") if isinstance(slide.get("_table_band"), dict) else None
            aabb = TABLE_HOST
            if band:
                aabb = (
                    float(band.get("x", TABLE_HOST[0])),
                    float(band.get("y", TABLE_HOST[1])),
                    float(band.get("w", TABLE_HOST[2])),
                    float(band.get("h", TABLE_HOST[3])),
                )
            host = canonical_table_host_markup(tid, aabb)
            out = re.sub(r"</svg>\s*$", host + "\n</svg>", out, count=1, flags=re.I)
    fid = str(slide.get("figure_id") or "").strip()
    if fid and fid.casefold() not in {"none", "null", "n/a", "-"}:
        if has_bound_figure_image(out, fid):
            pass
        elif has_figure_slot_marker(out):
            out = normalize_figure_host(out, slide)
        else:
            host = canonical_figure_host_markup(fid, FIGURE_HOST)
            out = re.sub(r"</svg>\s*$", host + "\n</svg>", out, count=1, flags=re.I)
    formula = str(slide.get("formula") or slide.get("formula_tex") or "").strip()
    if formula and "data-sunairum-formula-host" not in out and 'id="formula-band"' not in out:
        x, y, w, h = FORMULA_HOST
        host = (
            f'<g id="formula-band" data-sunairum-formula-host="1" '
            f'transform="translate({x:g},{y:g})">'
            f'<rect width="{w:g}" height="{h:g}" fill="none"/></g>'
        )
        out = re.sub(r"</svg>\s*$", host + "\n</svg>", out, count=1, flags=re.I)
    return out


def formula_host_aabb(svg: str) -> tuple[float, float, float, float]:
    """Parse formula host transform+rect, else preferred band."""
    match = re.search(
        r'data-sunairum-formula-host[^>]*transform="translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"'
        r'[^>]*>\s*<rect[^>]*width="([-\d.]+)"[^>]*height="([-\d.]+)"',
        svg or "",
        flags=re.I | re.S,
    )
    if not match:
        match = re.search(
            r'id="formula-band"[^>]*transform="translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"'
            r'[^>]*>\s*<rect[^>]*width="([-\d.]+)"[^>]*height="([-\d.]+)"',
            svg or "",
            flags=re.I | re.S,
        )
    if match:
        return (
            float(match.group(1)),
            float(match.group(2)),
            float(match.group(3)),
            float(match.group(4)),
        )
    return FORMULA_HOST


def table_host_aabb(svg: str) -> tuple[float, float, float, float]:
    parsed = parse_table_host_aabb(svg)
    return parsed if parsed is not None else TABLE_HOST
