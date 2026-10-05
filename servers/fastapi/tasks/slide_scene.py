"""Deterministic scene geometry for constrained DeckHTML compositions.

LLMs select a composition and supply copy; this module owns the slide plate,
header, lanes, and footer.  It intentionally contains no HTML rewriting.
Renderers consume the resolved boxes and runtime validation remains the final
authority for browser font metrics.
"""

from __future__ import annotations

from typing import Any

from tasks.html_constitution import CANVAS_H, CANVAS_W


SCENE_VERSION = "scene_layout_v2"
SAFE_INSET = 60.0
FOOTER_RESERVE = 42.0
LANE_GAP = 32.0
MIN_LANE_WIDTH = 280.0


def _text(slide: dict[str, Any], *keys: str) -> str:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    for key in keys:
        value = slide.get(key)
        if value is None:
            value = content.get(key.upper())
        value = str(value or "").strip()
        if value:
            return value
    return ""


def _line_count(text: str, *, width: float, font_px: float, max_lines: int) -> int:
    """Conservative pre-render estimate used only for reserved region sizing."""
    if not text:
        return 0
    average_glyph = max(5.0, font_px * 0.52)
    capacity = max(8, int(width / average_glyph))
    words = text.replace("\n", " ").split()
    lines = 1
    used = 0
    for word in words:
        length = max(1, len(word))
        if used and used + 1 + length > capacity:
            lines += 1
            used = length
        else:
            used += length + (1 if used else 0)
    return min(max_lines, max(1, lines))


def _box(identifier: str, role: str, x: float, y: float, w: float, h: float, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": identifier,
        "role": role,
        "x": round(x, 1),
        "y": round(y, 1),
        "w": round(w, 1),
        "h": round(h, 1),
    }
    result.update(extra)
    return result


def _region_copy_budget(region: dict[str, Any]) -> dict[str, int]:
    """Conservative visual-copy budget exposed to the visual author.

    It is deliberately a planning limit, not a truncation rule.  The author
    can use richer typography when it uses less copy, and browser measurement
    still decides release eligibility.
    """
    role = str(region.get("role") or "")
    w, h = float(region.get("w") or 0), float(region.get("h") or 0)
    font = 58.0 if role == "title" else 19.0 if role == "lede" else 17.0
    line_h = 1.1 if role == "title" else 1.35
    lines = max(1, int(h / max(1.0, font * line_h)))
    chars_per_line = max(12, int(w / max(1.0, font * 0.54)))
    return {"max_lines": lines, "max_chars": lines * chars_per_line}


def _composition(slide: dict[str, Any]) -> str:
    requested = str(slide.get("scene_composition") or "").strip().casefold()
    supported = {
        "title",
        "closing",
        "body",
        "two_column",
        "split_figure",
        "split_table",
        "split_chart",
        "formula",
        "process",
        "multi_chart",
    }
    if requested in supported:
        return requested
    raw = " ".join(
        str(slide.get(key) or "")
        for key in ("scene_composition", "visualization", "layout_family", "layout_intent")
    ).casefold()
    role = str(slide.get("role") or slide.get("page_role") or "").strip().casefold()
    if role in {"title", "hero"}:
        return "title"
    if role == "closing":
        return "closing"
    figure = str(slide.get("figure_id") or "").strip().casefold()
    table = str(slide.get("table_id") or "").strip().casefold()
    formula = str(slide.get("formula") or slide.get("formula_tex") or "").strip()
    if formula:
        return "formula"
    if table and table not in {"none", "null", "-", "n/a"}:
        return "split_table"
    if figure and figure not in {"none", "null", "-", "n/a"}:
        return "split_figure"
    if any(token in raw for token in ("comparison_columns", "multi_chart", "small multiples")):
        charts = slide.get("charts") if isinstance(slide.get("charts"), dict) else {}
        if len(charts) >= 2:
            return "multi_chart"
        # A narrative comparison without actual chart payloads is content, not
        # three empty chart hosts. Give its claims two readable lanes.
        return "two_column"
    if any(token in raw for token in ("chart", "ranked", "bar", "plot")):
        return "split_chart"
    if any(token in raw for token in ("process", "steps", "pipeline", "sequence", "diagram")):
        return "process"
    if any(token in raw for token in ("split_figure", "figure", "two-column", "two column", "compare")):
        return "two_column"
    cards = slide.get("cards") if isinstance(slide.get("cards"), list) else []
    bullets = slide.get("bullets") if isinstance(slide.get("bullets"), list) else []
    if max(len(cards), len(bullets)) >= 3:
        return "two_column"
    return "body"


def bound_asset_kinds(slide: dict[str, Any]) -> list[str]:
    """The asset kinds this slide claims to carry, in binding order."""
    kinds: list[str] = []
    blank = {"", "none", "null", "-", "n/a"}
    if str(slide.get("formula") or slide.get("formula_tex") or "").strip():
        kinds.append("formula")
    if str(slide.get("table_id") or "").strip().casefold() not in blank:
        kinds.append("table")
    if str(slide.get("figure_id") or "").strip().casefold() not in blank:
        kinds.append("figure")
    charts = slide.get("charts")
    if isinstance(charts, dict) and charts:
        kinds.append("chart")
    elif isinstance(charts, list) and charts:
        kinds.append("chart")
    return kinds


def unhosted_assets(slide: dict[str, Any], scene: dict[str, Any]) -> list[str]:
    """Asset kinds bound to the slide that the scene gives no region to.

    `_composition` picks one asset lane: a slide carrying both a table and a
    figure resolves to `split_table`, and the figure keeps its binding with
    nowhere to live. Downstream that figure was injected anyway -- before the
    first `</section>`, at a hard-coded right-hand offset -- and landed on top
    of the table. Two pieces of bound content stacked on each other is not a
    layout defect any repair can undo, because neither one is a few pixels out
    of place: the placement was invented. Naming the mismatch here, while the
    scene is still just numbers, is the only point where it can be resolved by
    binding rather than by guessing.
    """
    roles = {
        str(region.get("role") or "")
        for region in (scene.get("regions") or [])
        if isinstance(region, dict)
    }
    roles |= {
        str(region.get("id") or "")
        for region in (scene.get("regions") or [])
        if isinstance(region, dict)
    }
    surplus: list[str] = []
    for kind in bound_asset_kinds(slide):
        if kind in roles:
            continue
        # A figure may legitimately ride in a generic content lane only when no
        # other asset already owns one; otherwise it has no home.
        surplus.append(kind)
    return surplus


def validate_scene(scene: dict[str, Any]) -> list[str]:
    """Validate deterministic scene boxes before a renderer sees them."""
    issues: list[str] = []
    regions = scene.get("regions") if isinstance(scene.get("regions"), list) else []
    plate_bottom = CANVAS_H - FOOTER_RESERVE
    for region in regions:
        if not isinstance(region, dict):
            continue
        rid = str(region.get("id") or "region")
        x, y = float(region.get("x") or 0), float(region.get("y") or 0)
        w, h = float(region.get("w") or 0), float(region.get("h") or 0)
        if w <= 0 or h <= 0:
            issues.append(f"scene_nonpositive: {rid}")
        if region.get("role") != "footer" and (x < SAFE_INSET - 0.5 or y < SAFE_INSET - 0.5):
            issues.append(f"scene_safe_inset: {rid}")
        if region.get("role") != "footer" and (
            x + w > CANVAS_W - SAFE_INSET + 0.5 or y + h > plate_bottom + 0.5
        ):
            issues.append(f"scene_plate_overflow: {rid}")
        min_w = float(region.get("min_w") or 0)
        if min_w and w + 0.5 < min_w:
            issues.append(f"scene_min_width: {rid} {w:.1f}<{min_w:.1f}")

    for i, a in enumerate(regions):
        if not isinstance(a, dict) or a.get("allow_overlap"):
            continue
        for b in regions[i + 1 :]:
            if not isinstance(b, dict) or b.get("allow_overlap"):
                continue
            ax, ay, aw, ah = (float(a.get(k) or 0) for k in ("x", "y", "w", "h"))
            bx, by, bw, bh = (float(b.get(k) or 0) for k in ("x", "y", "w", "h"))
            if min(ax + aw, bx + bw) - max(ax, bx) > 0.5 and min(ay + ah, by + bh) - max(ay, by) > 0.5:
                issues.append(f"scene_collision: {a.get('id')} overlaps {b.get('id')}")
    return issues


def resolve_slide_scene(slide: dict[str, Any]) -> dict[str, Any]:
    """Resolve a semantic slide scene with safe, non-overlapping regions.

    The output is serializable and stable enough to hash into a future release
    manifest.  Copy estimates reserve space only; Chromium validation catches
    real font/layout behavior before release.
    """
    title = _text(slide, "title", "TITLE")
    lede = _text(slide, "lede", "subtitle", "core_message", "SUBTITLE")
    eyebrow = _text(slide, "eyebrow", "section", "EYEBROW")
    composition = _composition(slide)
    # A title plate is deck furniture, not a content slide. Outline generation
    # may still attach a core_message/lede to slide 1; never turn that planning
    # prose into a visible cover paragraph. A genuine short subtitle needs an
    # explicit cover field, rather than leaking through the generic lede lane.
    if composition == "title":
        lede = ""
    usable_w = CANVAS_W - SAFE_INSET * 2
    title_lines = _line_count(title, width=usable_w, font_px=44.0, max_lines=3)
    lede_lines = _line_count(lede, width=usable_w, font_px=20.0, max_lines=4)
    eyebrow_h = 25.0 if eyebrow else 0.0
    title_h = (
        max(56.0, title_lines * 52.0) + eyebrow_h
        if title
        else 0.0
    )
    lede_h = max(0.0, lede_lines * 27.0) if lede else 0.0
    header_h = title_h + (14.0 if title_h and lede_h else 0.0) + lede_h
    if composition == "title":
        # Bookends need room for expressive display type.  The previous generic
        # 40px estimate forced authored titles and presenter furniture into two
        # undersized header strips.
        # A long research title can occupy three visual lines when the art
        # direction reserves a right-side motif. Estimate against that narrower
        # editorial measure instead of pretending the full plate is available.
        title_lines = _line_count(
            title, width=min(usable_w, 880.0), font_px=64.0, max_lines=3
        )
        # Display faces frequently have taller ink bounds than their nominal
        # line height. Reserve room for three genuinely large cover lines.
        title_h = max(120.0, title_lines * 90.0) + eyebrow_h if title else 0.0
        lede_h = max(0.0, lede_lines * 32.0) if lede else 0.0
        header_h = title_h + (18.0 if title_h and lede_h else 0.0) + lede_h
    content_y = SAFE_INSET + header_h + 28.0
    content_h = (CANVAS_H - FOOTER_RESERVE) - content_y
    if content_h < 160.0:
        # The scene remains valid, but the caller receives an explicit budget
        # signal rather than a downstream overlap or clipped canvas.
        content_h = 160.0

    regions: list[dict[str, Any]] = []
    if title_h:
        regions.append(_box("title", "title", SAFE_INSET, SAFE_INSET, usable_w, title_h, min_w=420.0))
    if lede_h:
        regions.append(_box("lede", "lede", SAFE_INSET, SAFE_INSET + title_h + (14.0 if title_h else 0.0), usable_w, lede_h, min_w=420.0))

    if composition == "title":
        byline = " · ".join(
            value for value in (
                str(slide.get("authors") or "").strip(),
                str(slide.get("affiliations") or "").strip(),
            ) if value
        )
        if byline:
            byline_y = max(SAFE_INSET + title_h + (22.0 if lede_h else 32.0) + lede_h, 238.0)
            regions.append(
                _box("byline", "byline", SAFE_INSET, byline_y, min(820.0, usable_w), 104.0, min_w=420.0)
            )
    elif composition == "closing":
        regions.append(
            _box("primary", "primary", SAFE_INSET, content_y, usable_w, content_h, min_w=MIN_LANE_WIDTH)
        )
    elif composition in {"split_figure", "split_table", "split_chart"}:
        figure_w = min(580.0, usable_w * 0.5)
        body_w = usable_w - figure_w - LANE_GAP
        if body_w < MIN_LANE_WIDTH:
            figure_w = usable_w - MIN_LANE_WIDTH - LANE_GAP
            body_w = MIN_LANE_WIDTH
        regions.extend(
            [
                _box("primary", "primary", SAFE_INSET, content_y, body_w, content_h, min_w=MIN_LANE_WIDTH),
                _box(
                    "figure" if composition == "split_figure" else "table" if composition == "split_table" else "chart",
                    "figure" if composition == "split_figure" else "table" if composition == "split_table" else "chart",
                    SAFE_INSET + body_w + LANE_GAP,
                    content_y,
                    figure_w,
                    content_h,
                    min_w=360.0,
                ),
            ]
        )
    elif composition == "formula":
        formula_h = 112.0
        formula_gap = 24.0
        remaining_h = content_h - formula_h - formula_gap
        regions.extend(
            [
                _box("formula", "formula", SAFE_INSET, content_y, usable_w, formula_h, min_w=640.0),
                _box("primary", "primary", SAFE_INSET, content_y + formula_h + formula_gap, usable_w, remaining_h, min_w=MIN_LANE_WIDTH),
            ]
        )
    elif composition == "multi_chart":
        claim_w = 300.0
        chart_gap = 18.0
        charts_x = SAFE_INSET + claim_w + LANE_GAP
        chart_w = (usable_w - claim_w - LANE_GAP - chart_gap * 2) / 3
        regions.append(
            _box("primary", "primary", SAFE_INSET, content_y, claim_w, content_h, min_w=MIN_LANE_WIDTH)
        )
        for index in range(3):
            regions.append(
                _box(
                    f"chart_{index + 1}",
                    "chart",
                    charts_x + index * (chart_w + chart_gap),
                    content_y,
                    chart_w,
                    content_h,
                    min_w=200.0,
                )
            )
    elif composition == "process":
        regions.append(
            _box("primary", "process", SAFE_INSET, content_y, usable_w, content_h, min_w=MIN_LANE_WIDTH)
        )
    elif composition == "two_column":
        lane_w = (usable_w - LANE_GAP) / 2
        regions.extend(
            [
                _box("primary", "primary", SAFE_INSET, content_y, lane_w, content_h, min_w=MIN_LANE_WIDTH),
                _box("secondary", "secondary", SAFE_INSET + lane_w + LANE_GAP, content_y, lane_w, content_h, min_w=MIN_LANE_WIDTH),
            ]
        )
    else:
        regions.append(_box("primary", "primary", SAFE_INSET, content_y, usable_w, content_h, min_w=MIN_LANE_WIDTH))

    footer_y = CANVAS_H - FOOTER_RESERVE
    regions.append(_box("footer", "footer", CANVAS_W - 140.0, footer_y, 80.0, 24.0, allow_overlap=True))
    region_budgets = {
        str(region["id"]): _region_copy_budget(region)
        for region in regions
        if region.get("role") != "footer"
    }
    scene = {
        "version": SCENE_VERSION,
        "composition": composition,
        "canvas": {"width": CANVAS_W, "height": CANVAS_H, "safe_inset": SAFE_INSET, "footer_reserve": FOOTER_RESERVE},
        "copy_budget": {
            "title_lines": 2,
            "lede_lines": 0 if composition == "title" else 3,
            "estimated_title_lines": title_lines,
            "estimated_lede_lines": lede_lines,
        },
        "region_copy_budgets": region_budgets,
        "regions": regions,
    }
    # Two different kinds of wrong, and only one of them stops a slide.
    # `issues` means the geometry is unusable -- boxes overlapping, off-canvas,
    # a zero-width region -- and the renderer refuses such a scene outright. An
    # asset bound with no region to put it in is not that: every box is sound
    # and the slide renders exactly as designed; one binding simply has nowhere
    # to go. Folding it into `issues` cleared `ok` and aborted authoring for the
    # whole slide, which is a far worse outcome than the misplacement it was
    # meant to prevent -- and the placement itself is already refused at the
    # point of injection.
    scene["unhosted_assets"] = unhosted_assets(slide, scene)
    scene["issues"] = validate_scene(scene)
    scene["ok"] = not scene["issues"]
    return scene


def format_scene_layout_block(scene: dict[str, Any]) -> str:
    """Prompt contract for renderers; regions are constraints, not suggestions."""
    if not scene or not isinstance(scene.get("regions"), list):
        return ""
    lines = [
        "## Scene layout contract (required)",
        f"- VERSION: {scene.get('version')}",
        f"- COMPOSITION: {scene.get('composition')}",
        "- Create one direct child for each named region with data-layout-id=\"scene-<id>\" and data-layout-role=\"<role>\".",
        "- Give each region root inline position:absolute and the exact x/y/w/h below in px.",
        "- Put title copy only in title, lede copy only in lede, and content only in primary/secondary.",
        "- For TITLE composition, emit no lede, summary, abstract, claims, bullets, or explanatory prose.",
        "- Regions are sibling lanes: do not overlap them, do not add fixed-position children outside them.",
        "- Use the region width/height as a hard content budget; shorten or simplify rather than clip or shrink below readability.",
    ]
    for region in scene["regions"]:
        budget = (scene.get("region_copy_budgets") or {}).get(str(region.get("id"))) or {}
        lines.append(
            "- "
            f"{region['id']} role={region['role']} "
            f"x={region['x']} y={region['y']} w={region['w']} h={region['h']} "
            f"copy_budget≈{budget.get('max_lines', '?')} lines/{budget.get('max_chars', '?')} chars"
        )
    return "\n".join(lines) + "\n"
