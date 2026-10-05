"""Intent host inject for table/formula — Executor owns Constrained HTML pages."""

from __future__ import annotations

import re
from typing import Any, Callable


def resolve_content_owner(slide: dict[str, Any]) -> str:
    """Primary content kind for logging / inject routing."""
    if str(slide.get("table_id") or "").strip():
        return "table"
    if str(slide.get("formula") or slide.get("formula_tex") or "").strip():
        return "formula"
    fid = str(slide.get("figure_id") or "").strip()
    if fid and fid.casefold() not in {"none", "null", "n/a", "-"}:
        return "figure"
    return "executor"


def _replace_first_group_with_marker(svg: str, marker: str, replacement: str) -> str:
    """Replace first <g …marker…>…</g> with balanced nesting awareness."""
    low = svg.casefold()
    needle = marker.casefold()
    start = low.find(needle)
    if start < 0:
        return svg
    # Walk back to enclosing <g
    g_start = svg.rfind("<g", 0, start)
    if g_start < 0:
        return svg
    depth = 0
    i = g_start
    n = len(svg)
    while i < n:
        if svg.startswith("<g", i) and (i + 2 == n or not svg[i + 2].isalnum()):
            # opening <g or <g …
            depth += 1
            gt = svg.find(">", i)
            i = gt + 1 if gt >= 0 else i + 2
            continue
        if svg.startswith("</g>", i):
            depth -= 1
            i += 4
            if depth == 0:
                return svg[:g_start] + replacement + svg[i:]
            continue
        i += 1
    return svg


def _strip_formula_leftovers(svg: str) -> str:
    """Remove freehand equation / TeX-delimiter text outside the Intent plate."""
    out = svg or ""
    # Drop leftover MathJax nests outside hosts.
    out = re.sub(
        r"<svg\b[^>]*>[\s\S]*?</svg>",
        lambda m: m.group(0)
        if "data-sunairum-formula" in m.group(0).casefold()
        or m.group(0).strip().startswith("<svg")
        and m.start() < 20
        else m.group(0),
        out,
        flags=re.I,
    )
    # Strip visible TeX delimiter runs in freehand text.
    def _scrub_text(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        if "data-sunairum-formula" in attrs.casefold():
            return match.group(0)
        plain = re.sub(r"<[^>]+>", "", body)
        if re.search(r"\\\(|\\\[|\$\$|\\frac|\\sum|\\beta", plain):
            return ""
        return match.group(0)

    out = re.sub(r"<text\b([^>]*)>([\s\S]*?)</text>", _scrub_text, out, flags=re.I)
    return out


def inject_table_host(
    svg: str,
    slide: dict[str, Any],
    *,
    theme: dict[str, Any] | None = None,
    call_text: Callable[[str, str], str] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
    resolve_table_payload: Callable[[dict[str, Any] | None, str], dict[str, Any] | None]
    | None = None,
) -> tuple[str, str]:
    """Fill empty table host; return (svg, intent_source)."""
    try:
        from tasks.intent_hosts import ensure_asset_hosts, table_host_aabb
    except ImportError:  # pragma: no cover
        from intent_hosts import ensure_asset_hosts, table_host_aabb  # type: ignore

    out = ensure_asset_hosts(svg, slide)
    tid = str(slide.get("table_id") or "").strip()
    if not tid:
        return out, "none"
    payload = None
    if resolve_table_payload is not None:
        payload = resolve_table_payload(evidence_bundle, tid)
    if not payload:
        return out, "mapper"
    from tasks.table_renderer import fill_table_content

    class _HostLayout:
        def region(self, name: str):
            if name != "table":
                return None
            x, y, w, h = table_host_aabb(out)

            class _R:
                pass

            r = _R()
            r.x, r.y, r.width, r.height = x, y, w, h
            return r

    filled, source = fill_table_content(
        out,
        slide,
        table_payload=payload,
        layout=_HostLayout(),
        theme=theme or {},
        call_text=call_text,
    )
    return filled, source


def inject_formula_host(
    svg: str,
    slide: dict[str, Any],
    *,
    theme: dict[str, Any] | None = None,
    call_text: Callable[[str, str], str] | None = None,
) -> tuple[str, str]:
    """Fill empty formula host with PNG/flat band; clear freehand in reserved AABB."""
    try:
        from tasks.intent_hosts import ensure_asset_hosts, formula_host_aabb
        from tasks.table_renderer import _clear_freehand_in_aabb
    except ImportError:  # pragma: no cover
        from intent_hosts import ensure_asset_hosts, formula_host_aabb  # type: ignore
        from table_renderer import _clear_freehand_in_aabb  # type: ignore
    from tasks.formula_visual_intent import (
        author_formula_visual_intent,
        render_formula_plate,
        sanitize_formula_text,
    )

    out = ensure_asset_hosts(svg, slide)
    formula = sanitize_formula_text(str(slide.get("formula") or ""))
    formula_tex = sanitize_formula_text(str(slide.get("formula_tex") or ""))
    terms = sanitize_formula_text(str(slide.get("formula_terms") or ""))
    gloss = sanitize_formula_text(str(slide.get("formula_gloss") or ""))
    if not (formula or formula_tex):
        return out, "none"
    aabb = formula_host_aabb(out)
    # Clear Executor narrative under the reserved band before inject.
    out = _clear_freehand_in_aabb(out, aabb)
    intent = author_formula_visual_intent(
        formula or formula_tex, terms=terms, gloss=gloss, call_text=call_text
    )
    intent["formula"] = formula or formula_tex
    if formula_tex:
        intent["formula_tex"] = formula_tex
    # Prefer pre-rendered asset from pipeline when present.
    if slide.get("_formula_png_href") or slide.get("_formula_png_data_uri"):
        intent["_prerender_href"] = str(
            slide.get("_formula_png_data_uri") or slide.get("_formula_png_href") or ""
        )
        intent["_prerender_w"] = float(slide.get("_formula_png_width") or 640)
        intent["_prerender_h"] = float(slide.get("_formula_png_height") or 90)
    images_dir = str(slide.get("_images_dir") or (theme or {}).get("images_dir") or "")
    theme_with_images = dict(theme or {})
    if images_dir:
        theme_with_images["images_dir"] = images_dir
    plate = render_formula_plate(
        intent,
        aabb=aabb,
        terms=terms,
        gloss=gloss,
        theme=theme_with_images,
        images_dir=images_dir,
        formula_id=str(slide.get("formula_id") or "formula_001"),
    )
    if not plate:
        return out, "none"
    if "data-sunairum-formula-host" in out or 'id="formula-band"' in out:
        out = _replace_first_group_with_marker(out, "data-sunairum-formula-host", plate)
        if plate not in out and 'id="formula-band"' in out:
            out = _replace_first_group_with_marker(out, 'id="formula-band"', plate)
    else:
        out = re.sub(r"</svg>\s*$", plate + "\n</svg>", out, count=1, flags=re.I)
    out = _strip_formula_leftovers(out)
    return out, "mapper"


def count_freehand_in_table_aabb(svg: str) -> int:
    """Count freehand <text> baselines intersecting Intent table carrier AABB."""
    match = re.search(
        r'data-sunairum-source-table-id[^>]*transform="translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"',
        svg or "",
        flags=re.I,
    )
    if not match:
        try:
            from tasks.intent_hosts import table_host_aabb
        except ImportError:  # pragma: no cover
            from intent_hosts import table_host_aabb  # type: ignore
        ax, ay, aw, ah = table_host_aabb(svg)
    else:
        ax, ay = float(match.group(1)), float(match.group(2))
        # Estimate from following rect if present
        aw, ah = 632.0, 440.0
        rect = re.search(
            r'data-sunairum-source-table-id[\s\S]{0,400}?width="([-\d.]+)"[^>]*height="([-\d.]+)"',
            svg or "",
            flags=re.I,
        )
        if rect:
            aw, ah = float(rect.group(1)), float(rect.group(2))
    ar, ab = ax + aw, ay + ah
    n = 0
    for tm in re.finditer(r"<text\b([^>]*)>", svg or "", flags=re.I):
        attrs = tm.group(1) or ""
        if "data-sunairum-source-table" in attrs or "data-sunairum-table" in attrs:
            continue
        if "data-sunairum-page-number" in attrs:
            continue
        # Skip Intent insight/aside trees (local y under translate).
        head = (svg or "")[: tm.start()]
        protected = False
        for marker in (
            "data-sunairum-table-insight",
            "data-sunairum-table-aside",
            'data-pptx-replace-with="table"',
        ):
            idx = head.rfind(marker)
            if idx < 0:
                continue
            g_open = head.rfind("<g", 0, idx + 1)
            if g_open < 0:
                continue
            fragment = (svg or "")[g_open : tm.start()]
            opens = len(re.findall(r"<g\b", fragment, flags=re.I))
            closes = len(re.findall(r"</g\s*>", fragment, flags=re.I))
            if opens > closes:
                protected = True
                break
        if protected:
            continue
        ym = re.search(r'\by="([-\d.]+)"', attrs)
        xm = re.search(r'\bx="([-\d.]+)"', attrs)
        if not ym:
            continue
        y = float(ym.group(1))
        x = float(xm.group(1)) if xm else ax + 1
        if ax - 4 <= x <= ar + 4 and ay - 4 <= y <= ab + 4 and 140 <= y <= 680:
            n += 1
    return n


def render_slide(
    slide: dict[str, Any],
    *,
    theme: dict[str, Any] | None = None,
    slide_number: int = 1,
    total_slides: int = 1,
    call_text: Callable[[str, str], str] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
    visual_style: str = "",
    density: str = "",
    resolve_table_payload: Callable[[dict[str, Any] | None, str], dict[str, Any] | None]
    | None = None,
    base_svg: str = "",
) -> tuple[str, str, str]:
    """Inject Intent into empty Constrained HTML / legacy hosts. No page authorship.

    When base_svg is empty, returns a minimal shell (tests/dev only).
    """
    del visual_style, density
    owner = resolve_content_owner(slide)
    theme = theme or {}
    svg = base_svg or ""
    if not svg:
        title = str((slide or {}).get("title") or "Slide")
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">'
            f'<text x="64" y="80" font-size="32">{title}</text>'
            f'<text x="1200" y="700" text-anchor="end" font-size="12">'
            f"{slide_number}/{total_slides}</text></svg>"
        )
    intent_source = "none"
    if owner == "table":
        svg, intent_source = inject_table_host(
            svg,
            slide,
            theme=theme,
            call_text=call_text,
            evidence_bundle=evidence_bundle,
            resolve_table_payload=resolve_table_payload,
        )
    elif owner == "formula":
        svg, intent_source = inject_formula_host(
            svg, slide, theme=theme, call_text=call_text
        )
    else:
        try:
            from tasks.intent_hosts import ensure_asset_hosts
        except ImportError:  # pragma: no cover
            from intent_hosts import ensure_asset_hosts  # type: ignore
        svg = ensure_asset_hosts(svg, slide)
    return svg, owner, intent_source
