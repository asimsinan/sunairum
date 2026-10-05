"""Measured, region-scoped browser-layout repair for authored Scene v2 HTML.

This is intentionally not a template renderer.  It retains the authored DOM,
palette, components, and fixed Scene roots; it only tightens typography and
internal spacing in regions that Chromium measured as failing.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any


_PX_STYLE_RE = re.compile(r"(?P<name>font-size|gap|row-gap|column-gap|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?)\s*:\s*(?P<value>\d+(?:\.\d+)?)px", re.I)
_LINE_HEIGHT_RE = re.compile(r"line-height\s*:\s*(?P<value>\d+(?:\.\d+)?)(?P<unit>px)?", re.I)
#: Repair blocks written under a rule that has since been corrected. They are
#: stripped so the current rule can decide again from the measured page.
#:
#: v4 joined this list because its font-size rule was destructive: it shrank
#: without a bound (a 104px display numeral reached 14.5px over six passes),
#: left `letter-spacing` at its authored px so the shrunken glyphs collided,
#: and scaled the `line-height` that was centring a badge's single line. A deck
#: carrying those blocks keeps the damage even after the rule is fixed, because
#: the loop only rewrites what it re-emits — so the stale blocks have to go.
# Every fit block from every generation, including the current one. A repair
# run re-derives from the authored HTML rather than stacking onto whatever the
# last run left behind. Keeping earlier blocks made a bad rule permanent: a
# `margin-bottom:-527px` emitted by a since-corrected code path survived every
# subsequent export, because nothing re-measured the layout that produced it.
# Re-deriving costs a re-audit and means each rule in the output was produced by
# the code that is running now.
_LEGACY_FIT_RE = re.compile(
    r"/\*\s*deterministic Scene v2 local fit v\d+(?:\s+pass\s+\d+)?\s*\*/.*?"
    r"/\*\s*end deterministic Scene v2 local fit v\d+(?:\s+pass\s+\d+)?\s*\*/",
    re.I | re.S,
)


def _contained_top(value: Any) -> float | None:
    """Reject a suggested offset that would push an element out of its owner.

    ``top`` on an absolutely positioned child resolves against its positioned
    ancestor, so a negative value lifts the element clear of the box it belongs
    to. When a card's ordinal numeral or label escapes that way it lands on the
    neighbouring card and reads as mislabelled content — strictly worse than the
    overlap the repair was trying to resolve. The measurement pass already
    constrains candidates to the owner box; this is the belt-and-braces check so
    a stale or hand-written ledger cannot reintroduce the defect.
    """
    try:
        top = float(value)
    except (TypeError, ValueError):
        return None
    if top < 0:
        return None
    return top


def _spacing_floor(candidate: dict[str, Any], source_name: str) -> float:
    """Smallest value a spacing property may be tightened to.

    A painted ``::before`` marker sits *inside* the padding it is anchored in,
    so that padding is structure rather than slack. Scaling it like ordinary
    spacing walks the bullet into the first character of the copy, which is how
    list markers ended up printed over their own text.
    """
    reserve_key = {
        "paddingLeft": "reservePaddingLeft",
        "paddingTop": "reservePaddingTop",
    }.get(source_name)
    if not reserve_key:
        return 3.0
    try:
        return max(3.0, float(candidate.get(reserve_key) or 0))
    except (TypeError, ValueError):
        return 3.0


#: Least of its authored size a component may be shrunk to across all passes.
#: Each pass measures the size the previous pass produced, so an absolute floor
#: alone does not bound the compounding: a display number authored at 104px was
#: taken to 74.9 → 53.9 → 38.8 → 28.0 → 20.1 → 14.5px over six passes, a 7×
#: cut that is no longer the design and, with its tracking, no longer legible.
#: A component that still does not fit at this bound does not have a typography
#: problem — it has more copy than its region can hold, which is reported.
_MIN_CONTRAST_RATIO = 3.0


def _parse_css_rgb(value: Any) -> tuple[float, float, float] | None:
    """The three channels of an rgb()/rgba() string, or None."""
    match = re.search(
        r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)", str(value or "")
    )
    if not match:
        return None
    return tuple(float(match.group(i)) for i in (1, 2, 3))  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    channels = []
    for raw in rgb:
        c = max(0.0, min(1.0, raw / 255.0))
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lo, hi = sorted((la, lb))
    return (hi + 0.05) / (lo + 0.05)


def _legible_against(
    ink: tuple[float, float, float],
    surface: tuple[float, float, float],
    *,
    floor: float = _MIN_CONTRAST_RATIO,
) -> str | None:
    """The author's ink, moved along lightness only, until it clears `floor`.

    Recolouring is normally the author's business, but ink at 1.6:1 is not a
    palette choice -- the sentence is not there for the reader. Hue and
    saturation are kept exactly: only the value is walked, away from the
    surface, so the result still reads as the colour that was chosen. None when
    even black or white cannot reach the floor (an impossible surface, which is
    a different defect and must stay reported rather than silently repainted).
    """
    import colorsys

    if _contrast_ratio(ink, surface) >= floor:
        return None
    hue, _lightness, saturation = colorsys.rgb_to_hls(*[c / 255.0 for c in ink])
    # Away from the surface: pale ink on a dark panel goes paler, not darker.
    upward = _relative_luminance(surface) < 0.5
    steps = 96
    for i in range(1, steps + 1):
        target = i / steps if upward else 1.0 - (i / steps)
        candidate = colorsys.hls_to_rgb(hue, target, saturation)
        rgb = tuple(round(c * 255.0) for c in candidate)
        if _contrast_ratio(rgb, surface) >= floor:  # type: ignore[arg-type]
            return f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"
    return None


_MAX_CUMULATIVE_FONT_SHRINK = 0.55

#: Air left between copy and the panel it was running under.
_MIN_TRESPASS_GAP = 24.0

#: Vertical padding a box keeps when its overrun is reclaimed from padding.
#: Below this the copy starts touching the box edge it sits in.
_MIN_RETAINED_PADDING = 12.0

# The most a block may be pulled up by a negative bottom margin. Trailing
# leading is worth reclaiming; anything larger moves the block itself.
_MAX_NEGATIVE_PULL = 16.0

_DECLARED_FONT_SIZE_RE = re.compile(r"font-size:\s*([\d.]+)px", re.I)


def _scaled_type_declaration(
    *,
    from_size: float,
    to_size: float,
    line_height: float,
    letter_spacing: float,
    centers_with_line_height: bool,
) -> str:
    """CSS for a font-size change, with everything that must move with it.

    Every property here was forgotten once. Tracking is a ratio to the em, so a
    negative letter-spacing left at its authored px crushed a shrunken numeral
    into a single blot. Line-height is the pitch for flowing copy but the
    *centring* for a single line in a fixed box, where scaling it lifted the
    glyphs off centre. Routing every emitter through one function is what stops
    the next one from remembering only half of this.
    """
    if not (from_size > 0) or not (to_size > 0):
        return ""
    ratio = to_size / from_size
    declaration = f"font-size:{to_size:.2f}px!important;"
    if line_height > 0 and not centers_with_line_height:
        declaration += f"line-height:{max(16.0, line_height * ratio):.2f}px!important;"
    if abs(letter_spacing) > 0.01:
        declaration += f"letter-spacing:{letter_spacing * ratio:.3f}px!important;"
    return declaration


def _authored_font_size(html: str, selector: str) -> float:
    """Largest font-size any rule in the document declares for this selector.

    Both the author's own rule and every earlier repair pass are in the same
    document, so the maximum is the size the component started at.
    """
    needle = selector.strip()
    if not needle:
        return 0.0
    # The repair addresses a measured descendant path; the author declared the
    # size on the element's own class. Both name the same element, so consider
    # each. Taking the maximum only ever makes the floor more conservative.
    needles = {needle}
    last = needle.rsplit(">", 1)[-1].strip()
    if last:
        needles.add(last)
        for token in re.findall(r"\.[-\w]+", last):
            needles.add(token)
    largest = 0.0
    for candidate in needles:
        for match in re.finditer(re.escape(candidate) + r"\s*\{([^{}]*)\}", html):
            for size in _DECLARED_FONT_SIZE_RE.findall(match.group(1)):
                try:
                    largest = max(largest, float(size))
                except ValueError:
                    continue
    return largest


def _component_font_floor(selector: str, role: str) -> float:
    """Keep hierarchy while allowing genuinely auxiliary copy to contract.

    Captions, notes, kickers, metadata and footers are intentionally smaller
    than body copy. Treating every target as 14px prevented measured repair
    from resolving overflowing callout notes and triggered destructive region
    recovery instead.
    """
    semantic = str(selector or "").casefold()
    if any(
        token in semantic
        for token in ("note", "caption", "foot", "meta", "kicker", "eyebrow", "label")
    ):
        return 11.0
    if role == "title":
        return 32.0
    return 14.0


def _scale_for_region(entry: dict[str, Any]) -> float:
    if entry.get("grid_repairs"):
        # Structural track repair carries most of the fix. A small simultaneous
        # tightening absorbs normal font-metric differences without the old
        # destructive 20% shrink.
        return 0.94
    demand = 0.0
    for component in entry.get("components") or []:
        overflow = component.get("overflow") if isinstance(component.get("overflow"), dict) else {}
        box = component.get("box") if isinstance(component.get("box"), dict) else {}
        try:
            demand = max(
                demand,
                float(overflow.get("contentX") or 0) / max(1.0, float(box.get("width") or 1)),
                float(overflow.get("contentY") or 0) / max(1.0, float(box.get("height") or 1)),
            )
        except (TypeError, ValueError):
            continue
    # A stack taller than its region is demand too, and it was invisible here:
    # `components` reports a box overflowing *itself*, and a column of blocks
    # that together run past the region bottom overflows none of them. So a
    # 30px shortfall in a 333px region asked for the 4% floor -- a tightening
    # far too small to recover it -- and with no padding left to reclaim the
    # region simply stayed broken.
    for overrun in entry.get("region_overrun_repairs") or []:
        try:
            height = float(overrun.get("regionHeight") or 0)
            needed = float(overrun.get("overrun") or 0)
        except (TypeError, ValueError):
            continue
        if height > 1 and needed > 0:
            demand = max(demand, needed / height)
    # A measured 5% demand gets a 7.5% reduction; cap a single pass so title
    # hierarchy cannot collapse. A second generation, not repeated shrinking,
    # handles anything that still cannot fit.
    role = str(entry.get("role") or "")
    floor = 0.68 if role == "table" else (0.80 if role == "lede" else 0.72)
    computed = 1.0 - max(0.04, demand * 1.8)
    # Tables accumulate height once per row. A small additional reserve avoids
    # a pass that is mathematically exact but still misses by one font pixel
    # after Chromium rounds every cell and border independently.
    if role == "table":
        computed -= 0.03
    return max(floor, min(0.96, computed))


def _tighten_style(style: str, *, scale: float, role: str) -> str:
    def px(match: re.Match[str]) -> str:
        name = match.group("name")
        value = float(match.group("value"))
        if name.casefold() == "font-size":
            floor = 32.0 if role == "title" else 14.0
            if value > floor:
                value = max(floor, value * scale)
        elif value >= 6.0:
            value = max(3.0, value * scale)
        return f"{name}:{value:.2f}px"

    def line_height(match: re.Match[str]) -> str:
        value = float(match.group("value"))
        unit = match.group("unit") or ""
        if unit:
            return f"line-height:{value if value <= 12.0 else max(12.0, value * scale):.2f}px"
        # Unitless line-height below 1.08 harms readability; keep it above that.
        return f"line-height:{value if value <= 1.08 else max(1.08, value * scale):.3f}"

    return _LINE_HEIGHT_RE.sub(line_height, _PX_STYLE_RE.sub(px, style or ""))


# A previously emitted repair that lifted an element clear of its owner. Decks
# generated before positional repairs were clamped carry these rules baked into
# their authored HTML, and `!important` means a later pass cannot outvote them.
# Strip them so an existing project heals on its next compile instead of keeping
# a numeral pinned over the card above it forever.
# Matched on the declaration alone. A leading ``[^{}\n]*`` selector prefix reads
# naturally but backtracks quadratically: authored slides put their whole
# stylesheet on one line, and on a 419KB line the two patterns together spent
# over ten minutes per slide. The declaration is a fixed shape, so anchoring on
# it keeps the scan linear; the selector in front of it is then trimmed by hand.
_ESCAPING_DECL_RE = re.compile(
    r"\{(?:top:-\d+(?:\.\d+)?px!important;bottom:auto!important"
    r"|left:-\d+(?:\.\d+)?px!important;right:auto!important);?\}"
)
# A selector runs back to the end of the previous rule or the start of the block.
_SELECTOR_STOP = "}{;\n"


def strip_owner_escaping_repairs(html: str) -> tuple[str, int]:
    """Remove baked-in repair rules that positioned an element outside its owner."""
    if not html:
        return html, 0
    pieces: list[str] = []
    cursor = 0
    count = 0
    for match in _ESCAPING_DECL_RE.finditer(html):
        start = match.start()
        while start > cursor and html[start - 1] not in _SELECTOR_STOP:
            start -= 1
        pieces.append(html[cursor:start])
        cursor = match.end()
        count += 1
    if not count:
        return html, 0
    pieces.append(html[cursor:])
    return "".join(pieces), count


_DEAD_HOST_MARKER = "deterministic Scene v2 dead semantic host"


def neutralize_dead_semantic_hosts(
    html: str, report: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    """Stop a hidden-but-painting semantic host from ghosting over the slide.

    The author is asked for an *empty* host that the pipeline fills. Some
    authored slides also render the same bound content themselves and then try to
    hide the host with a near-zero opacity. That value is below the exporter's
    visibility threshold, so the PPTX never contains the host — but Chromium
    still paints it, leaving a faint duplicate formula/table over the authored
    one and generating collision findings against content no reader sees.
    Since nothing downstream consumes such a host, turning it off is lossless.
    """
    inspection = report.get("inspection") if isinstance(report.get("inspection"), dict) else {}
    hosts = [item for item in (inspection.get("deadHosts") or []) if isinstance(item, dict)]
    selectors = sorted({str(item.get("selector") or "").strip() for item in hosts} - {""})
    if not html or not selectors or _DEAD_HOST_MARKER in html:
        return html, []
    try:
        from lxml import html as lxml_html
    except ImportError:  # pragma: no cover - production image includes lxml
        return html, []
    try:
        document = lxml_html.document_fromstring(html)
    except (TypeError, ValueError):
        return html, []
    style_tags = document.xpath("//style")
    if not style_tags:
        return html, []
    rules = "".join(f"{selector}{{display:none!important;}}" for selector in selectors)
    style_tags[0].text = (
        (style_tags[0].text or "")
        + f"\n/* {_DEAD_HOST_MARKER} */\n{rules}\n/* end {_DEAD_HOST_MARKER} */\n"
    )
    rendered = lxml_html.tostring(
        document, encoding="unicode", method="html", doctype="<!doctype html>"
    )
    return rendered, hosts


def repair_scene_html_layout(
    html: str,
    ledger: dict[str, Any],
    *,
    pass_index: int = 1,
) -> tuple[str, dict[str, Any]]:
    """Apply one precise pass to measured failing scene roots."""
    if not html or not isinstance(ledger, dict):
        return html, {"changed": False, "regions": []}
    try:
        from lxml import html as lxml_html
    except ImportError:  # pragma: no cover - production image includes lxml
        return html, {"changed": False, "regions": [], "skipped": "lxml_unavailable"}

    try:
        document = lxml_html.document_fromstring(html)
    except (TypeError, ValueError):
        return html, {"changed": False, "regions": [], "skipped": "html_unreadable"}
    repaired: list[dict[str, Any]] = []
    for region_id, entry in (ledger.get("regions") or {}).items():
        if not isinstance(entry, dict) or not entry.get("issues"):
            continue
        roots = document.xpath('//*[@data-layout-id=$identifier]', identifier=f"scene-{region_id}")
        if not roots:
            continue
        root = roots[0]
        role = str(entry.get("role") or "")
        scale = _scale_for_region(entry)
        changed = False
        for node in root.iterdescendants():
            # Table/formula/image hosts own their internal fit. Generic region
            # repair must not resize injected cells, glyphs, or figure chrome.
            if node.xpath("ancestor-or-self::*[@data-pptx]"):
                continue
            style = str(node.attrib.get("style") or "")
            if not style:
                continue
            tightened = _tighten_style(style, scale=scale, role=role)
            if tightened != style:
                node.attrib["style"] = tightened
                changed = True
        if (
            changed
            or entry.get("components")
            or entry.get("grid_repairs")
            or entry.get("pseudo_repairs")
            or entry.get("decoration_repairs")
            or entry.get("collision_repairs")
            or entry.get("text_collision_repairs")
            or entry.get("round_repairs")
            or entry.get("host_repairs")
            # A channel missing from this list is a channel whose repairs are
            # built but never reached: the region is not counted as repairable,
            # so the loop that would emit them never iterates it.
            or entry.get("region_overrun_repairs")
            or entry.get("host_shortfall_repairs")
            or entry.get("contrast_repairs")
        ):
            repaired.append({"region": region_id, "role": role, "scale": round(scale, 3)})

    if not repaired:
        return html, {"changed": False, "regions": []}
    # Browser-safe containment cures the flex/grid min-content failure without
    # touching the author's absolute root geometry or decorative layers.
    rules = "\n".join(
        f'[data-layout-id="scene-{item["region"]}"] *{{min-width:0;box-sizing:border-box;}}'
        f'[data-layout-id="scene-{item["region"]}"] :is(p,li,h1,h2,h3,h4,h5,h6,span){{overflow-wrap:normal;word-break:normal;}}'
        for item in repaired
    )
    # Returning an element to the flow reflows everything around it, so every
    # other measurement this pass carries describes a layout that will no longer
    # exist. Applying them together squeezed a list item to nine characters a
    # line and scored the whole pass worse than doing nothing, so the structural
    # change goes in alone and the rest is re-measured against the result.
    structural_rules: list[str] = []
    grid_rules: list[str] = []
    for item in repaired:
        entry = (ledger.get("regions") or {}).get(item["region"]) or {}
        root_selector = f'[data-layout-id="scene-{item["region"]}"]'
        for grid in entry.get("grid_repairs") or []:
            selector = str(grid.get("selector") or "").strip()
            if not selector:
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            if grid.get("strategy") == "swap_first_two":
                grid_rules.append(f"{scoped}>:nth-child(1){{grid-column:2!important;}}{scoped}>:nth-child(2){{grid-column:1!important;grid-row:1!important;}}")
            elif grid.get("strategy") == "drop_empty_grid_item":
                spare = str(grid.get("spareSelector") or "").strip()
                if not spare:
                    continue
                spare_scoped = (
                    root_selector
                    if spare == root_selector
                    else f"{root_selector} {spare}"
                )
                # Taking an item out of a grid re-places every item after it,
                # so this is structural and goes in a pass of its own.
                structural_rules.append(f"{spare_scoped}{{display:none!important;}}")
            elif grid.get("strategy") == "refit_grid_tracks":
                # The author's proportion is kept exactly; only the basis
                # changes, from the whole container to the space left once the
                # gap is taken out. Shrinking the gap instead can only converge
                # on the fit, never reach it.
                columns = str(grid.get("suggestedColumns") or "").strip()
                if columns:
                    grid_rules.append(
                        f"{scoped}{{grid-template-columns:{columns}!important;}}"
                    )
            elif grid.get("strategy") == "widen_narrow_track":
                # Move the measured shortfall from the widest track to the
                # starved one, keeping the composition. The fallback below
                # collapses the grid to a single column, which would stack a
                # deliberate two-column figure to fix one caption.
                columns = str(grid.get("suggestedColumns") or "").strip()
                if columns:
                    grid_rules.append(
                        f"{scoped}{{grid-template-columns:{columns}!important;}}"
                    )
            else:
                grid_rules.append(f"{scoped}{{grid-template-columns:minmax(0,1fr)!important;}}")
    pending_grid_rules = grid_rules
    # CSS-class authored components have no inline declaration to tighten.
    # Chromium supplies their computed type metrics and a scoped selector, so
    # preserve hierarchy while overriding only the measured component.
    type_rules: list[str] = []
    spacing_rules: dict[str, str] = {}
    # Selectors whose positioning scheme this pass changes. Every other
    # positional suggestion for them was computed against the geometry they had
    # *before* the change, so applying both in one pass sets an offset for a box
    # that no longer exists -- a paragraph returned to the flow was then given
    # left:-1px from its old absolute frame, and the whole pass scored worse and
    # was thrown away. They are re-measured on the next pass instead.
    unpinned: set[str] = set()
    for item in repaired:
        entry = (ledger.get("regions") or {}).get(item["region"]) or {}
        root_selector = f'[data-layout-id="scene-{item["region"]}"]'
        for component in entry.get("components") or []:
            for candidate in component.get("layout_candidates") or []:
                selector = str(candidate.get("selector") or "").strip()
                if not selector:
                    continue
                scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
                declarations: list[str] = []
                for source_name, css_name in (
                    ("paddingTop", "padding-top"), ("paddingRight", "padding-right"),
                    ("paddingBottom", "padding-bottom"), ("paddingLeft", "padding-left"),
                    ("marginTop", "margin-top"), ("marginBottom", "margin-bottom"),
                    ("rowGap", "row-gap"), ("columnGap", "column-gap"),
                    ("minHeight", "min-height"),
                ):
                    try:
                        value = float(candidate.get(source_name) or 0)
                    except (TypeError, ValueError):
                        continue
                    if value >= 6:
                        floor = _spacing_floor(candidate, source_name)
                        scaled = max(floor, min(value, value * item["scale"]))
                        declarations.append(f"{css_name}:{scaled:.2f}px!important")
                if declarations:
                    spacing_rules[scoped] = ";".join(declarations) + ";"
            overflow = component.get("overflow") if isinstance(component.get("overflow"), dict) else {}
            targets = overflow.get("targets") if isinstance(overflow.get("targets"), list) else []
            candidates = targets
            for candidate in candidates:
                selector = str(candidate.get("selector") or "").strip()
                root_selector = f'[data-layout-id="scene-{item["region"]}"]'
                scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
                try:
                    target_top = float(candidate.get("top") or 0)
                    target_overflow_y = float(candidate.get("overflowY") or 0)
                except (TypeError, ValueError):
                    target_top = target_overflow_y = 0.0
                if (
                    item["role"] == "title"
                    and str(candidate.get("position") or "") == "absolute"
                    and target_top < 0
                ):
                    type_rules.append(f"{scoped}{{top:0!important;}}{root_selector} h1{{padding-top:16px!important;}}")
                elif (
                    selector != root_selector
                    and str(candidate.get("position") or "") == "absolute"
                    and target_overflow_y > 4
                    and target_top >= 0
                ):
                    corrected_top = max(0.0, target_top - target_overflow_y - 1.0)
                    type_rules.append(f"{scoped}{{top:{corrected_top:.2f}px!important;}}")
                try:
                    size = float(candidate.get("fontSize") or 0)
                    line = float(candidate.get("lineHeight") or 0)
                except (TypeError, ValueError):
                    continue
                if not selector or size < 14:
                    continue
                authored = _authored_font_size(html, selector) or size
                scaled = max(
                    _component_font_floor(selector, item["role"]),
                    authored * _MAX_CUMULATIVE_FONT_SHRINK,
                    size * item["scale"],
                )
                if scaled >= size - 0.05:
                    # Already at the bound: shrinking further would trade a fit
                    # for illegibility, and the overflow stays reported.
                    continue
                # Reclaim the overrun from the element's own vertical padding
                # before touching its type. A note overflowing its region by
                # 10px while carrying 30px of padding does not have a typography
                # problem, and shrinking its copy was the only move on offer —
                # so the pass kept being emitted and rejected.
                try:
                    pad_top = float(candidate.get("paddingTop") or 0)
                    pad_bottom = float(candidate.get("paddingBottom") or 0)
                except (TypeError, ValueError):
                    pad_top = pad_bottom = 0.0
                spare = pad_top + pad_bottom - _MIN_RETAINED_PADDING
                if target_overflow_y > 0 and spare >= target_overflow_y:
                    share = target_overflow_y / 2.0
                    type_rules.append(
                        f"{scoped}{{padding-top:{max(0.0, pad_top - share):.2f}px!important;"
                        f"padding-bottom:{max(0.0, pad_bottom - share):.2f}px!important;}}"
                    )
                    continue
                try:
                    tracking = float(candidate.get("letterSpacing") or 0)
                except (TypeError, ValueError):
                    tracking = 0.0
                declaration = _scaled_type_declaration(
                    from_size=size,
                    to_size=scaled,
                    line_height=line,
                    letter_spacing=tracking,
                    centers_with_line_height=bool(candidate.get("centersWithLineHeight")),
                )
                if declaration:
                    type_rules.append(f"{scoped}{{{declaration}}}")
        for host_fit in entry.get("host_repairs") or []:
            selector = str(host_fit.get("selector") or "").strip()
            if not selector or host_fit.get("strategy") != "hug_table_content":
                continue
            try:
                height = float(host_fit.get("suggestedHeight"))
            except (TypeError, ValueError):
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            # Hug the rows the host actually received. The authored height was a
            # guess made before the table existed -- and so was the min-height
            # beneath it, which silently outranks the new height and leaves the
            # dead space exactly where it was. Both are the same guess, so both
            # give way to the measurement.
            type_rules.append(
                f"{scoped}{{height:{max(24.0, height):.2f}px!important;"
                f"min-height:0!important;}}"
            )
        for contrast in entry.get("contrast_repairs") or []:
            selector = str(contrast.get("selector") or "").strip()
            if not selector:
                continue
            if not contrast.get("trespass"):
                # The text belongs on this surface; only the ink is wrong. Hue
                # and saturation are the author's and are kept -- lightness is
                # the one dimension that decides whether the sentence can be
                # read at all.
                ink = _parse_css_rgb(contrast.get("color"))
                surface = _parse_css_rgb(contrast.get("surface"))
                if not ink or not surface:
                    continue
                corrected = _legible_against(ink, surface)
                if not corrected:
                    continue
                scoped = (
                    root_selector
                    if selector == root_selector
                    else f"{root_selector} {selector}"
                )
                type_rules.append(f"{scoped}{{color:{corrected}!important;}}")
                continue
            try:
                surface_left = float(contrast.get("surfaceLeft"))
                box_left = float(contrast.get("boxLeft"))
            except (TypeError, ValueError):
                continue
            width = surface_left - box_left - _MIN_TRESPASS_GAP
            if width < 120:
                # Stopping the text here would leave a column too narrow to
                # read; the region is genuinely over-packed and says so.
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            # The copy is legible on its own surface and illegible where it
            # crosses onto the panel beside it. It was never meant to run under
            # that panel, so it stops at its edge.
            type_rules.append(f"{scoped}{{width:{width:.2f}px!important;max-width:{width:.2f}px!important;}}")

        for shortfall in entry.get("host_shortfall_repairs") or []:
            selector = str(shortfall.get("selector") or "").strip()
            if not selector or shortfall.get("strategy") != "grow_host_to_content":
                continue
            try:
                height = float(shortfall.get("suggestedHeight"))
                above = float(shortfall.get("above") or 0)
            except (TypeError, ValueError):
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            # The host's height was a guess made before the content existed, so
            # grow it to what it actually received — the mirror of
            # hug_table_content. Ink reaching above the host is cleared with
            # padding-top, since the box grows downwards from its own origin.
            declaration = f"height:{max(24.0, height):.2f}px!important;"
            if above > 1:
                declaration += f"padding-top:{above:.2f}px!important;"
            type_rules.append(f"{scoped}{{{declaration}}}")

        for overrun in entry.get("region_overrun_repairs") or []:
            selector = str(overrun.get("selector") or "").strip()
            if not selector:
                continue
            if overrun.get("strategy") == "lift_decoration_out_of_flow":
                # The hairline keeps painting exactly where it painted; it just
                # stops charging the lane for the privilege. The sentence it was
                # pushing out is the content, and content outranks ornament.
                try:
                    top = float(overrun.get("suggestedTop"))
                except (TypeError, ValueError):
                    continue
                scoped = (
                    root_selector
                    if selector == root_selector
                    else f"{root_selector} {selector}"
                )
                type_rules.append(
                    f"{scoped}{{position:absolute!important;top:{top:.2f}px!important;"
                    f"margin-top:0!important;margin-bottom:0!important;}}"
                )
                continue
            if overrun.get("strategy") != "reclaim_region_overrun":
                continue
            try:
                needed = float(overrun.get("overrun") or 0)
                pad_top = float(overrun.get("paddingTop") or 0)
                pad_bottom = float(overrun.get("paddingBottom") or 0)
            except (TypeError, ValueError):
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            # Take it from the padding *above* the stack. In a fixed-height
            # region the bottom padding does not move anything — the content is
            # already past the edge — so splitting the reclaim between top and
            # bottom spent half of it on nothing and the overrun survived.
            spare = pad_top - max(4.0, _MIN_RETAINED_PADDING / 2)
            if needed > 0 and spare >= needed:
                type_rules.append(
                    f"{scoped}{{padding-top:{max(0.0, pad_top - needed):.2f}px!important;}}"
                )
                continue
            # No padding to give: pull the block up by the overrun instead of
            # shrinking its type, which would change every glyph to win 5px.
            # A negative bottom margin only takes back trailing space; past a
            # few pixels it starts hauling the block over whatever precedes it.
            # Uncapped, this emitted margin-bottom:-527px -- one bullet's text
            # dragged bodily up through the list and across the summary line
            # beneath it. Beyond the cap the overrun is structural and belongs
            # to the region and type passes, so it stays reported instead.
            if needed > _MAX_NEGATIVE_PULL:
                continue
            type_rules.append(
                f"{scoped}{{margin-bottom:{-needed:.2f}px!important;}}"
            )

        for round_fit in entry.get("round_repairs") or []:
            selector = str(round_fit.get("selector") or "").strip()
            if not selector or round_fit.get("strategy") != "shrink_to_inscribed":
                continue
            try:
                size = float(round_fit.get("suggestedFontSize"))
            except (TypeError, ValueError):
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            # Shrink the copy to the shape. Growing the badge instead would move
            # whatever it is anchored between, which is usually the whole point
            # of the badge's position. A badge is also where negative tracking
            # and centring line-heights live, so this goes through the same
            # helper as every other font-size change.
            try:
                current = float(round_fit.get("fontSize") or 0)
                tracking = float(round_fit.get("letterSpacing") or 0)
                current_line = float(round_fit.get("lineHeight") or 0)
            except (TypeError, ValueError):
                current = tracking = current_line = 0.0
            target = max(9.0, size)
            declaration = _scaled_type_declaration(
                from_size=current or target,
                to_size=target,
                line_height=current_line or target * 1.1,
                letter_spacing=tracking,
                centers_with_line_height=bool(round_fit.get("centersWithLineHeight")),
            )
            if declaration:
                type_rules.append(f"{scoped}{{{declaration}}}")
        for pseudo in entry.get("pseudo_repairs") or []:
            selector = str(pseudo.get("selector") or "").strip()
            pseudo_kind = str(pseudo.get("pseudo") or "").strip()
            if not selector or pseudo_kind not in {"::before", "::after"}:
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            if pseudo.get("strategy") == "reserve_marker_gutter":
                # Widen the gutter instead of moving the bullet: the marker's
                # position is the design, the padding is what went missing.
                try:
                    needed = float(pseudo.get("suggestedPaddingLeft"))
                except (TypeError, ValueError):
                    continue
                type_rules.append(
                    f"{scoped}{{padding-left:{max(0.0, needed):.2f}px!important;}}"
                )
            elif pseudo.get("strategy") == "transparent_background":
                type_rules.append(f"{scoped}{pseudo_kind}{{background:transparent!important;}}")
            elif pseudo.get("strategy") == "hide_pseudo_text":
                type_rules.append(f'{scoped}{pseudo_kind}{{content:""!important;display:none!important;}}')
            elif pseudo.get("strategy") in {"increase_top", "decrease_top", "set_top"}:
                suggested = _contained_top(pseudo.get("suggestedTop"))
                if suggested is None:
                    # Nothing inside the owner works; hiding ornamental ink beats
                    # painting it over the neighbouring component.
                    type_rules.append(
                        f'{scoped}{pseudo_kind}{{content:""!important;display:none!important;}}'
                    )
                    continue
                type_rules.append(
                    f"{scoped}{pseudo_kind}{{top:{suggested:.2f}px!important;bottom:auto!important;}}"
                )
        for decoration in entry.get("decoration_repairs") or []:
            # Move the rule before considering the copy. A rule carries no
            # content, so relocating it — or dropping it when its owner has no
            # clear band left — costs nothing, while shifting the sentence
            # pushes it further out of a region it may already be overflowing.
            rule_selector = str(decoration.get("ruleSelector") or "").strip()
            rule_strategy = str(decoration.get("ruleStrategy") or "")
            if rule_selector and rule_strategy:
                rule_scoped = (
                    root_selector if rule_selector == root_selector
                    else f"{root_selector} {rule_selector}"
                )
                if rule_strategy == "set_rule_top":
                    top = _contained_top(decoration.get("suggestedRuleTop"))
                    if top is not None:
                        type_rules.append(
                            f"{rule_scoped}{{top:{top:.2f}px!important;bottom:auto!important;}}"
                        )
                        continue
                elif rule_strategy == "set_rule_bottom":
                    try:
                        bottom = float(decoration.get("suggestedRuleBottom"))
                    except (TypeError, ValueError):
                        bottom = -1.0
                    if bottom >= 0:
                        type_rules.append(
                            f"{rule_scoped}{{bottom:{bottom:.2f}px!important;top:auto!important;}}"
                        )
                        continue
                if rule_strategy == "hide_decoration":
                    # Nowhere clear to put it. An accent bar drawn through a
                    # sentence is worse than no accent bar.
                    type_rules.append(f"{rule_scoped}{{display:none!important;}}")
                    continue

            selector = str(decoration.get("targetSelector") or "").strip()
            strategy = str(decoration.get("strategy") or "")
            if not selector:
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            if strategy == "hide_pseudo_decoration":
                # Graphical pseudo ink crossing copy is ornament the author put
                # in the wrong place. There is no owner box to move it inside of
                # (a pseudo has no layout identity of its own), and the copy it
                # crosses is the content — so remove the ornament.
                pseudo_kind = str(decoration.get("pseudo") or "").strip()
                if pseudo_kind not in {"::before", "::after"}:
                    continue
                type_rules.append(
                    f'{scoped}{pseudo_kind}{{content:none!important;display:none!important;}}'
                )
                continue
            if strategy == "move_decoration_absolute":
                suggested_top = _contained_top(decoration.get("suggestedTop"))
                if suggested_top is None:
                    continue
                # The offset belongs to whatever the detector measured as
                # movable. When it names a rule, that rule is the thing to
                # move: `scoped` is the *target* -- the sentence being crowded
                # -- and applying a decoration's offset to it drives the copy
                # hundreds of pixels down the slide, which is how this repair
                # came to be rejected wholesale on every pass.
                moved = str(decoration.get("ruleSelector") or "").strip() or selector
                moved_scoped = (
                    root_selector if moved == root_selector else f"{root_selector} {moved}"
                )
                type_rules.append(
                    f"{moved_scoped}{{top:{suggested_top:.2f}px!important;bottom:auto!important;}}"
                )
                continue
            if strategy == "reserve_left_gutter":
                # A vertical accent bar is cleared sideways: moving the copy
                # down leaves it under the same bar. Indenting past the bar is
                # what the design meant — the bar marks the block, it does not
                # strike through it.
                try:
                    suggested = float(decoration.get("suggestedPaddingLeft"))
                except (TypeError, ValueError):
                    continue
                type_rules.append(
                    f"{scoped}{{padding-left:{max(0.0, suggested):.2f}px!important;}}"
                )
                continue
            if strategy == "report_only":
                # Neither the rule nor the copy can give. Saying so is the
                # honest outcome; emitting a no-op rule would just re-fire.
                continue
            if strategy == "shift_target_up":
                try:
                    suggested = float(decoration.get("suggestedMarginTop"))
                except (TypeError, ValueError):
                    continue
                type_rules.append(f"{scoped}{{margin-top:{max(0.0, suggested):.2f}px!important;}}")
                continue
            if strategy != "shift_target_down":
                continue
            try:
                suggested = float(decoration.get("suggestedMarginTop"))
            except (TypeError, ValueError):
                continue
            type_rules.append(f"{scoped}{{margin-top:{max(0.0, suggested):.2f}px!important;}}")
        for collision in entry.get("collision_repairs") or []:
            selector = str(collision.get("targetSelector") or "").strip()
            strategy = str(collision.get("strategy") or "")
            if strategy == "unpin_band_into_flow":
                movable = str(collision.get("movableSelector") or "").strip()
                if not movable:
                    continue
                band = f"{root_selector} {movable}"
                unpinned.add(band)
                structural_rules.append(
                    f"{band}{{position:static!important;top:auto!important;"
                    f"bottom:auto!important;}}"
                )
                # Back into the flow, after the content it was sitting on top
                # of. `bottom` and `top` are released together so the authored
                # anchors cannot re-pin it.
                type_rules.append(
                    f"{band}{{position:static!important;top:auto!important;"
                    f"bottom:auto!important;}}"
                )
                continue
            if strategy == "reserve_container_bottom":
                movable = str(collision.get("movableSelector") or "").strip()
                if not selector or not movable:
                    continue
                try:
                    pad = float(collision.get("suggestedPaddingBottom"))
                    bottom = float(collision.get("suggestedBottom"))
                except (TypeError, ValueError):
                    continue
                container = root_selector if selector == root_selector else f"{root_selector} {selector}"
                band = f"{root_selector} {movable}"
                # Reserve the lane, and put the band back on the edge it was
                # authored against. A later rule wins over the earlier
                # `top:N!important;bottom:auto!important` that misplaced it.
                type_rules.append(f"{container}{{padding-bottom:{max(0.0, pad):.2f}px!important;}}")
                type_rules.append(
                    f"{band}{{top:auto!important;bottom:{max(0.0, bottom):.2f}px!important;}}"
                )
                continue
            if not selector or strategy not in {"set_absolute_top", "reserve_semantic_bottom"}:
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            if strategy == "reserve_semantic_bottom":
                try:
                    suggested_bottom = float(collision.get("suggestedBottom"))
                except (TypeError, ValueError):
                    continue
                type_rules.append(f"{scoped}{{bottom:{max(0.0, suggested_bottom):.2f}px!important;}}")
                continue
            suggested = _contained_top(collision.get("suggestedTop"))
            if suggested is None:
                continue
            if scoped in unpinned:
                continue
            type_rules.append(
                f"{scoped}{{top:{suggested:.2f}px!important;bottom:auto!important;}}"
            )
        for collision in entry.get("text_collision_repairs") or []:
            selector = str(collision.get("targetSelector") or "").strip()
            if not selector or collision.get("strategy") != "set_absolute_left":
                continue
            try:
                suggested = float(collision.get("suggestedLeft"))
            except (TypeError, ValueError):
                continue
            scoped = root_selector if selector == root_selector else f"{root_selector} {selector}"
            if scoped in unpinned:
                continue
            type_rules.append(
                f"{scoped}{{left:{suggested:.2f}px!important;right:auto!important;}}"
            )
    if structural_rules:
        spacing_rules = {}
        type_rules = structural_rules
        pending_grid_rules = []
    rules += "\n" + "\n".join(pending_grid_rules)
    rules += "\n" + "\n".join(f"{selector}{{{declarations}}}" for selector, declarations in spacing_rules.items())
    rules += "\n" + "\n".join(type_rules)
    style_tags = document.xpath("//style")
    if style_tags:
        style_tag = style_tags[0]
        existing = style_tag.text or ""
        # A declaration the stylesheet already carries is a no-op, and every
        # pass was re-deriving the same ones: one slide ended up with the
        # identical `top:0!important` rule eleven times. Repeated exports then
        # compound it, which is how an authored stylesheet grows into a single
        # 400KB line. Emit only what is genuinely new.
        fresh: list[str] = []
        for line in rules.splitlines():
            candidate = line.strip()
            if not candidate or candidate in existing or candidate in fresh:
                continue
            fresh.append(candidate)
        if not fresh:
            return html, {"changed": False, "regions": [], "skipped": "no_new_rules"}
        marker = f"deterministic Scene v2 local fit v5 pass {max(1, int(pass_index))}"
        style_tag.text = (
            existing
            + f"\n/* {marker} */\n" + "\n".join(fresh) + f"\n/* end {marker} */\n"
        )
    rendered = lxml_html.tostring(document, encoding="unicode", method="html", doctype="<!doctype html>")
    return rendered, {
        "changed": True,
        "regions": repaired,
        "mode": "measured_type_spacing_and_pseudo",
        "pass": max(1, int(pass_index)),
    }


def _layout_score(report: dict[str, Any]) -> float:
    """Comparable severity score; lower is always a safer rendered layout."""
    inspection = report.get("inspection") if isinstance(report.get("inspection"), dict) else {}
    magnitude = 0.0
    for element in inspection.get("elements") or []:
        overflow = element.get("overflow") if isinstance(element.get("overflow"), dict) else {}
        magnitude += float(overflow.get("contentX") or 0) + float(overflow.get("contentY") or 0)
    for collision in inspection.get("collisions") or []:
        magnitude += (
            float(collision.get("width") or 0) * float(collision.get("height") or 0)
        ) / 10.0
    for collision in inspection.get("decorationCollisions") or []:
        magnitude += (
            float(collision.get("width") or 0) * float(collision.get("height") or 0)
        ) / 10.0
    for collision in inspection.get("textCollisions") or []:
        magnitude += (
            float(collision.get("width") or 0) * float(collision.get("height") or 0)
        ) / 10.0
    # Not every hard finding costs the reader the same thing. Text under an
    # opaque surface is not there to be read; text a little past a region
    # boundary is. Scored as equals, the loop preferred hiding a sentence to
    # letting it overflow -- an un-pinned band traded five occlusions for six
    # overruns and was rejected for being "worse". Occlusion outranks overflow.
    occlusions = sum(
        1
        for collision in inspection.get("collisions") or []
        if isinstance(collision, dict) and collision.get("occlusion")
    )
    magnitude += 400_000.0 * occlusions
    magnitude += 100.0 * len(inspection.get("pseudoIssues") or [])
    magnitude += 100.0 * len(inspection.get("wordFragments") or [])
    magnitude += 100.0 * len(inspection.get("narrowText") or [])
    return 100_000.0 * len(report.get("hard") or []) + magnitude


def repair_scene_html_until_stable(
    html: str,
    scene: dict[str, Any],
    *,
    initial_report: dict[str, Any] | None = None,
    max_passes: int = 6,
    time_budget_s: float | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Audit → repair → re-audit until clean or no measured improvement.

    Old v1-v3 blocks used broad tag selectors and are removed before the new
    precise pass. A bounded total of eight accepted v4 passes prevents repeated
    exports from gradually shrinking a slide forever.
    """
    from tasks.html_layout_qa import audit_runtime_html_layout
    from tasks.scene_layout_ledger import build_scene_layout_ledger

    if not html:
        report = initial_report or audit_runtime_html_layout(html)
        return html, report, {"changed": False, "passes": []}

    # Every pass costs a full Chromium measurement, so an unbounded loop can eat
    # more wall-clock than the slide's own authoring. Quality work on one slide
    # must never be able to stall the deck.
    if time_budget_s is None:
        try:
            time_budget_s = float(os.getenv("SUNAIRUM_LAYOUT_REPAIR_BUDGET_S", "45"))
        except (TypeError, ValueError):
            time_budget_s = 45.0
    deadline = time.monotonic() + max(5.0, float(time_budget_s))

    legacy_removed = bool(_LEGACY_FIT_RE.search(html))
    working = _LEGACY_FIT_RE.sub("", html)
    working, escapes_removed = strip_owner_escaping_repairs(working)
    report = (
        initial_report
        if initial_report is not None and not legacy_removed and not escapes_removed
        else audit_runtime_html_layout(working)
    )
    # Switching off dead semantic mirrors is unconditional, not a repair
    # candidate: it removes ink the exporter already ignores, so it can only
    # improve the render and must not compete for the bounded pass budget.
    working, dead_hosts = neutralize_dead_semantic_hosts(working, report)
    if dead_hosts:
        report = audit_runtime_html_layout(working)
    # Count opening markers only; the previous substring count also matched
    # every ``end deterministic`` marker and exhausted the eight-pass budget
    # after only four accepted repairs.
    pass_indices = [
        int(value)
        for value in re.findall(
            r"/\*\s*deterministic Scene v2 local fit v5 pass\s+(\d+)",
            working,
        )
    ]
    existing_passes = len(pass_indices)
    last_pass_index = max(pass_indices, default=0)
    remaining = max(0, min(int(max_passes), 8 - existing_passes))
    accepted: list[dict[str, Any]] = []
    pass_number = last_pass_index
    timed_out = False
    for offset in range(remaining):
        if time.monotonic() >= deadline:
            timed_out = True
            print(
                f"[scene_local_repair] layout repair budget of {time_budget_s:.0f}s spent after "
                f"{len(accepted)} pass(es); keeping the best result so far"
            )
            break
        inspection = report.get("inspection") if isinstance(report.get("inspection"), dict) else {}
        if not report.get("hard") or not inspection.get("available"):
            break
        ledger = build_scene_layout_ledger(scene, report)
        failing = {
            rid: entry
            for rid, entry in (ledger.get("regions") or {}).items()
            if isinstance(entry, dict) and entry.get("issues")
        }
        if not failing:
            break
        # Judge each Scene region on its own. Scoring a whole pass atomically
        # meant one region that got worse discarded every region that got
        # better in the same pass: a table host correctly shrunk to its rows was
        # thrown away because an unrelated panel's band moved badly at the same
        # time. Regions are independent boxes, so they are accepted independently.
        progressed = False
        for region_id, entry in failing.items():
            if time.monotonic() >= deadline:
                timed_out = True
                break
            pass_number += 1
            candidate, meta = repair_scene_html_layout(
                working,
                {**ledger, "regions": {region_id: entry}},
                pass_index=pass_number,
            )
            if not meta.get("changed") or candidate == working:
                continue
            candidate_report = audit_runtime_html_layout(candidate)
            before = _layout_score(report)
            after = _layout_score(candidate_report)
            meta = {
                **meta,
                "region_scored": region_id,
                "score_before": round(before, 2),
                "score_after": round(after, 2),
            }
            if after >= before:
                meta["accepted"] = False
                accepted.append(meta)
                continue
            meta["accepted"] = True
            accepted.append(meta)
            working = candidate
            report = candidate_report
            progressed = True
        if not progressed:
            break

    changed = working != html
    regions: list[dict[str, Any]] = []
    for item in accepted:
        if item.get("accepted"):
            regions.extend(item.get("regions") or [])
    return working, report, {
        "changed": changed,
        "legacy_removed": legacy_removed,
        "owner_escapes_removed": escapes_removed,
        "timed_out": timed_out,
        "dead_hosts": dead_hosts,
        "passes": accepted,
        "regions": regions,
        "converged": not bool(report.get("hard")),
        "remaining_hard": [str(item) for item in report.get("hard") or []],
    }
