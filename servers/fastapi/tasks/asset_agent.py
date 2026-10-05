"""Native vector visuals for slides the source could not illustrate.

Measured on the run that motivated this module: every produced slide contained zero
``<path>`` elements. No icons, no diagrams, nothing drawn. A slide got a picture only
when the source PDF happened to supply a figure, and when it did not the figure slot
was deleted and the region filled with prose -- 2,531 characters on one bare
background. The beauty ceiling was "text in boxes, occasionally a cropped screenshot".

So this draws. Two constraints decide the shape of it.

**A constrained vocabulary, not freeform SVG.** A model asked for arbitrary markup
produces something that looks plausible and compiles to a raster blob or to nothing.
Six components are offered -- process, comparison, timeline, metric, architecture and
icon-list -- and the model chooses one and fills its fields. Everything is then drawn
here, from rectangles, lines, vendored icon paths and text, all of which the compiler
already emits as native editable DrawingML.

**Labels are the slide's own words.** A synthesized diagram whose captions the model
invented is unsupported generated content wearing a diagram's clothes, and no amount
of tagging it ``design`` makes the words true. So a label may only use vocabulary the
slide's copy already contains, checked here, and the text then carries the slide's own
provenance because it is the slide's own material. The drawing around it -- the boxes,
the arrows, the icons -- is ours, and the group says so.

Text is laid out with the same metrics the renderer uses. A component whose labels do
not fit is refused rather than shrunk: an empty zone is recoverable, and a diagram with
clipped captions is the defect this project spent 187 repair calls on.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

try:
    from . import asset_library, provenance
    from .text_layout import wrap
except ImportError:  # pragma: no cover - supports direct task imports
    import asset_library  # type: ignore[no-redef]
    import provenance  # type: ignore[no-redef]
    from text_layout import wrap  # type: ignore[no-redef]

COMPONENTS = ("process", "comparison", "timeline", "metric", "architecture", "icon-list")

Component = Literal["process", "comparison", "timeline", "metric", "architecture", "icon-list"]

# How many items each component can hold and still be readable at slide distance.
ITEM_LIMITS: dict[str, tuple[int, int]] = {
    "process": (2, 5),
    "comparison": (2, 3),
    "timeline": (2, 5),
    "metric": (2, 4),
    "architecture": (2, 4),
    "icon-list": (2, 5),
}

# Which component says what an archetype means. The planner already decided the slide's
# rhetorical move, so the visual follows it rather than being chosen again by a model.
ARCHETYPE_COMPONENT: dict[str, str] = {
    "procedure": "process",
    "flow-diagram": "process",
    "process": "process",
    "comparison": "comparison",
    "problem-framing": "comparison",
    "timeline": "timeline",
    "metric-cards": "metric",
    "results": "metric",
    "chart": "metric",
    "evidence": "icon-list",
    "narrative": "icon-list",
    "closing": "icon-list",
    "table": "icon-list",
    "quote": "icon-list",
    "formula": "architecture",
    "single-figure": "architecture",
}

# Words a label may use without the slide having said them. Function words carry no
# claim, so requiring the source to contain "and" would reject every honest label.
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is",
    "it", "of", "on", "or", "our", "per", "that", "the", "their", "then", "these",
    "this", "to", "via", "with", "we", "you",
})

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_PATH = re.compile(r"<path\b[^>]*?/>|<path\b[^>]*?>.*?</path>", re.S | re.I)
_D_ATTR = re.compile(r'\bd="([^"]+)"')
_VIEWBOX = re.compile(r'viewBox="([-\d.\s]+)"')


class AssetRefused(ValueError):
    """A visual that cannot be drawn honestly, or cannot be drawn legibly."""


@dataclass(frozen=True)
class AssetItem:
    """One step, column, milestone, metric, layer or point."""

    label: str
    detail: str = ""
    value: str = ""
    icon: str = ""


@dataclass(frozen=True)
class VisualAsset:
    """A visual named in the vocabulary, with the material to fill it."""

    component: str
    items: tuple[AssetItem, ...]
    caption: str = ""

    def __post_init__(self) -> None:
        if self.component not in COMPONENTS:
            raise AssetRefused(f"{self.component!r} is not one of {COMPONENTS}")
        low, high = ITEM_LIMITS[self.component]
        if not low <= len(self.items) <= high:
            raise AssetRefused(
                f"{self.component} holds {low}-{high} items, was given {len(self.items)}"
            )


@dataclass(frozen=True)
class AssetStyle:
    """The deck's theme, as much of it as a drawing needs.

    Defaults exist so a caller without a theme still draws something coherent, not so
    that a theme is optional: the deck theme is authored once per deck and passed in.
    """

    primary: str = "#1E3A8A"
    accent: str = "#F59E0B"
    surface: str = "#F4F6F8"
    background: str = "#FFFFFF"
    body_text: str = "#0F172A"
    heading_family: str = "Inter"
    body_family: str = "Inter"
    label_size: float = 18.0
    detail_size: float = 16.0
    value_size: float = 40.0
    corner_radius: float = 12.0
    gap: float = 20.0


@dataclass
class AssetPlacement:
    """Where a visual was drawn, for the record a QA report reads."""

    component: str
    box: tuple[float, float, float, float]
    items: int
    icons: tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- grounding


def _vocabulary(text: str) -> set[str]:
    return {word.casefold() for word in _WORD.findall(text or "")}


def source_vocabulary(slide: dict) -> set[str]:
    """Every word the slide already says, across its title and copy."""
    parts: list[str] = [str(slide.get("title") or ""), str(slide.get("description") or "")]
    content = slide.get("content")
    if isinstance(content, dict):
        for value in content.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, tuple)):
                parts.extend(str(entry) for entry in value)
    diagram = slide.get("diagram")
    if isinstance(diagram, dict):
        for node in diagram.get("nodes") or []:
            parts.append(node.get("label", "") if isinstance(node, dict) else str(node))
    return _vocabulary(" ".join(parts))


def ungrounded_labels(asset: VisualAsset, vocabulary: set[str]) -> list[str]:
    """Labels using words the slide never said.

    This is the whole reason an Asset Agent is safe to have. A diagram is read as a
    claim about the source, so a model that renames "quantization-aware training" to
    "model compression" while drawing it has asserted something the source did not.
    Numbers are not checked here because a metric value is copied, not composed, and
    is validated against the evidence by the grounding checks that already exist.
    """
    unknown: list[str] = []
    for item in asset.items:
        for text in (item.label, item.detail):
            words = {
                word for word in _vocabulary(text)
                if word not in STOPWORDS and len(word) > 2
            }
            if words - vocabulary:
                unknown.append(text)
    return unknown


# ------------------------------------------------------------------------ composition


def _clean(value: Any, limit: int = 120) -> str:
    return " ".join(str(value or "").split())[:limit]


def _body_points(slide: dict, limit: int = 5) -> list[str]:
    """The slide's own body copy, split into the points it is already making."""
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    points: list[str] = []
    for key in ("BODY", "BULLETS", "POINTS", "SUBTITLE"):
        value = content.get(key)
        if isinstance(value, (list, tuple)):
            points.extend(_clean(entry) for entry in value)
        elif isinstance(value, str) and value.strip():
            for piece in re.split(r"\n+|(?<=[.;])\s+(?=[A-Z0-9])", value):
                cleaned = _clean(piece.lstrip("-•* "))
                if cleaned:
                    points.append(cleaned)
        if points:
            break
    return [point for point in points if point][:limit]


def _split_point(point: str) -> tuple[str, str]:
    """A point as a short label plus the rest of what it says."""
    head, separator, tail = point.partition(":")
    if separator and 2 <= len(head.split()) <= 6:
        return _clean(head, 48), _clean(tail, 110)
    words = point.split()
    return _clean(" ".join(words[:4]), 48), _clean(" ".join(words[4:]), 110)


def choose_component(slide: dict) -> str:
    """The component an archetype means, without asking a model."""
    plan = slide.get("visual_plan") if isinstance(slide.get("visual_plan"), dict) else {}
    archetype = str(plan.get("archetype") or slide.get("archetype") or "").strip().casefold()
    if archetype in ARCHETYPE_COMPONENT:
        return ARCHETYPE_COMPONENT[archetype]
    diagram = slide.get("diagram")
    if isinstance(diagram, dict) and diagram.get("nodes"):
        return "process"
    return "icon-list"


def pick_icon(*terms: str) -> str:
    """The vendored icon that best means these terms, or nothing."""
    found = asset_library.find_icons(*terms, limit=1)
    return str(found[0].get("name") or "") if found else ""


def derive(slide: dict) -> VisualAsset:
    """Compose a visual from the slide's own material, with no model call.

    This is the path taken when the model is unavailable, refuses, or proposes
    something ungrounded. It cannot invent a word, because it only rearranges copy the
    slide already carries.
    """
    component = choose_component(slide)
    low, high = ITEM_LIMITS[component]
    diagram = slide.get("diagram") if isinstance(slide.get("diagram"), dict) else None
    if component == "process" and diagram and diagram.get("nodes"):
        labels = [
            _clean(node.get("label") or node.get("id"), 48) if isinstance(node, dict)
            else _clean(node, 48)
            for node in diagram["nodes"]
        ]
        items = [AssetItem(label=label, icon=pick_icon(label)) for label in labels if label]
    else:
        points = _body_points(slide, high)
        items = []
        for point in points:
            label, detail = _split_point(point)
            if not label:
                continue
            items.append(AssetItem(
                label=label,
                detail=detail if component in {"comparison", "icon-list", "architecture"} else "",
                value=_first_number(point) if component == "metric" else "",
                icon=pick_icon(label) if component in {"process", "icon-list"} else "",
            ))
    items = items[:high]
    if len(items) < low:
        raise AssetRefused(
            f"slide has {len(items)} usable point(s); {component} needs {low}"
        )
    if component == "metric" and not all(item.value for item in items):
        # A metric card with no metric on it is a heading in a box.
        component, low, high = "icon-list", *ITEM_LIMITS["icon-list"]
        items = [AssetItem(label=item.label, detail=item.detail, icon=pick_icon(item.label))
                 for item in items[:high]]
    return VisualAsset(component=component, items=tuple(items))


_NUMBER = re.compile(r"[-+]?\d[\d.,]*\s*(?:%|x|×|bn|m|k|B|M|K)?", re.IGNORECASE)


def _first_number(text: str) -> str:
    found = _NUMBER.search(text or "")
    return _clean(found.group(0), 12) if found else ""


def parse_proposal(payload: Any) -> VisualAsset:
    """Read a model's answer as a visual, or refuse it."""
    if not isinstance(payload, dict):
        raise AssetRefused("proposal is not an object")
    component = str(payload.get("component") or "").strip().casefold()
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise AssetRefused("proposal has no items")
    items: list[AssetItem] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        label = _clean(entry.get("label"), 48)
        if not label:
            continue
        icon = str(entry.get("icon") or "").strip()
        items.append(AssetItem(
            label=label,
            detail=_clean(entry.get("detail"), 110),
            value=_clean(entry.get("value"), 12),
            icon=icon if asset_library.icon_markup(icon) else pick_icon(label),
        ))
    return VisualAsset(
        component=component,
        items=tuple(items),
        caption=_clean(payload.get("caption"), 90),
    )


PROMPT = """You are Sunairum choosing a diagram for one slide of a presentation.

Pick exactly one component from this vocabulary and fill it:

- process: sequential steps that lead to an outcome (2-5 items)
- comparison: two or three alternatives set against each other (2-3 items)
- timeline: milestones in time order (2-5 items)
- metric: headline numbers with what they measure (2-4 items, every item needs a value)
- architecture: layers stacked from foundation to surface (2-4 items)
- icon-list: distinct points that are not sequential (2-5 items)

Rules, all of them binding:

- Every word you write must already appear in the slide copy below. You are arranging
  the slide's own language into a diagram, not describing it in your own words.
- A label is at most six words. A detail is one short clause, or empty.
- If the slide's material does not suit any component, answer {"component": "none"}.

Return JSON only:
{"component": "process", "items": [{"label": "...", "detail": "...", "value": "",
 "icon": "rocket-launch"}]}

Icon names must come from this list, or be omitted: %(icons)s
"""


def propose(slide: dict, call_json=None) -> VisualAsset:
    """Ask a model for a visual, and fall back to composing one ourselves.

    The model's contribution is judgement about which arrangement suits the material.
    It is not trusted with the words: anything it writes that the slide did not say is
    rejected here and the deterministic composition is used instead.
    """
    vocabulary = source_vocabulary(slide)
    if call_json is None:
        try:
            from llm_client import call_llm_json

            call_json = call_llm_json
        except Exception:
            return derive(slide)
    catalogue = ", ".join(
        sorted({str(entry.get("name")) for entry in asset_library.assets("icon")})[:160]
    )
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    brief = "\n".join(
        f"{key}: {value}" for key, value in content.items() if isinstance(value, str)
    )
    try:
        payload = call_json(
            PROMPT % {"icons": catalogue},
            f"Slide title: {slide.get('title', '')}\n"
            f"Planned archetype: {choose_component(slide)}\n\n{brief}",
        )
        asset = parse_proposal(payload)
    except AssetRefused as refusal:
        print(f"[asset] proposal refused ({refusal}); composing from the slide")
        return derive(slide)
    except Exception as error:
        print(f"[asset] proposal unavailable ({error}); composing from the slide")
        return derive(slide)
    ungrounded = ungrounded_labels(asset, vocabulary)
    if ungrounded:
        print(f"[asset] proposal used words the slide never said: {ungrounded[:3]}")
        return derive(slide)
    return asset


# ---------------------------------------------------------------------------- drawing


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def icon_paths(name: str, box: tuple[float, float, float, float], colour: str) -> str:
    """One vendored icon, scaled into a box as plain paths.

    Paths are what the compiler turns into native geometry. An ``<image>`` would be a
    raster at the wrong resolution, and a nested ``<svg>`` would not survive the
    conversion at all.
    """
    markup = asset_library.icon_markup(name)
    if not markup:
        return ""
    found = _VIEWBOX.search(markup)
    extent = 256.0
    if found:
        numbers = [float(value) for value in found.group(1).split()]
        if len(numbers) == 4 and numbers[2] > 0:
            extent = numbers[2]
    x, y, width, height = box
    side = min(width, height)
    scale = side / extent
    offset_x = x + (width - side) / 2
    offset_y = y + (height - side) / 2
    paths = []
    for path in _PATH.finditer(markup):
        geometry = _D_ATTR.search(path.group(0))
        if geometry:
            paths.append(f'<path d="{geometry.group(1)}" fill="{colour}"/>')
    if not paths:
        return ""
    return (
        f'<g transform="translate({offset_x:g},{offset_y:g}) scale({scale:.5g})" '
        f'data-sunairum-icon="{_escape(name)}">{"".join(paths)}</g>'
    )


def _text(
    text: str,
    x: float,
    y: float,
    width: float,
    size: float,
    family: str,
    colour: str,
    bold: bool,
    anchor: str,
    max_lines: int,
) -> str:
    """One measured text node, refused rather than clipped.

    Wrapping happens here so the preview and the compiled deck agree, and so a label
    that needs more room than the component has is a refusal at composition time
    instead of an overflow discovered by a reader.
    """
    if not text:
        return ""
    lines = wrap(text, width, size, family, bold)
    if len(lines) > max_lines:
        raise AssetRefused(f"{text!r} needs {len(lines)} lines, the component allows {max_lines}")
    spacing = size * 1.3
    tspans = "".join(
        f'<tspan x="{x:g}" dy="{0 if index == 0 else spacing:g}">{_escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    weight = ' font-weight="700"' if bold else ""
    return (
        f'<text x="{x:g}" y="{y:g}" text-anchor="{anchor}" fill="{colour}" '
        f'font-family="{_escape(family)}, sans-serif" font-size="{size:g}"{weight}>'
        f"{tspans}</text>"
    )


def _panel(x: float, y: float, width: float, height: float, style: AssetStyle,
           fill: str | None = None, stroke: str | None = None) -> str:
    return (
        f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" '
        f'rx="{style.corner_radius:g}" fill="{fill or style.surface}" '
        f'stroke="{stroke or style.primary}" stroke-width="1.5"/>'
    )


def _row_boxes(box: tuple[float, float, float, float], count: int, gap: float) -> list[tuple[float, float, float, float]]:
    x, y, width, height = box
    cell = (width - gap * (count - 1)) / count
    return [(x + index * (cell + gap), y, cell, height) for index in range(count)]


def _column_boxes(box: tuple[float, float, float, float], count: int, gap: float) -> list[tuple[float, float, float, float]]:
    x, y, width, height = box
    cell = (height - gap * (count - 1)) / count
    return [(x, y + index * (cell + gap), width, cell) for index in range(count)]


def _draw_process(asset: VisualAsset, box: tuple[float, float, float, float], style: AssetStyle) -> str:
    cells = _row_boxes(box, len(asset.items), style.gap * 1.6)
    parts: list[str] = [
        '<defs><marker id="sunairum-asset-arrow" markerWidth="9" markerHeight="9" '
        f'refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="{style.primary}"/>'
        "</marker></defs>"
    ]
    for index, (item, cell) in enumerate(zip(asset.items, cells)):
        cx, cy, cw, ch = cell
        parts.append(_panel(cx, cy, cw, ch, style))
        cursor = cy + 28.0
        if item.icon:
            drawn = icon_paths(item.icon, (cx + cw / 2 - 18, cursor, 36, 36), style.accent)
            if drawn:
                parts.append(drawn)
                cursor += 52.0
        parts.append(_text(
            item.label, cx + cw / 2, cursor + style.label_size, cw - 28, style.label_size,
            style.heading_family, style.body_text, True, "middle", 3,
        ))
        if index:
            previous = cells[index - 1]
            y_mid = cy + ch / 2
            parts.append(
                f'<line x1="{previous[0] + previous[2] + 4:g}" y1="{y_mid:g}" '
                f'x2="{cx - 6:g}" y2="{y_mid:g}" stroke="{style.primary}" '
                'stroke-width="2" marker-end="url(#sunairum-asset-arrow)"/>'
            )
    return "".join(parts)


def _draw_comparison(asset: VisualAsset, box: tuple[float, float, float, float], style: AssetStyle) -> str:
    cells = _row_boxes(box, len(asset.items), style.gap)
    parts: list[str] = []
    for item, (cx, cy, cw, ch) in zip(asset.items, cells):
        parts.append(_panel(cx, cy, cw, ch, style, fill=style.background))
        parts.append(
            f'<rect x="{cx:g}" y="{cy:g}" width="{cw:g}" height="{style.label_size * 2.6:g}" '
            f'rx="{style.corner_radius:g}" fill="{style.primary}"/>'
        )
        parts.append(_text(
            item.label, cx + 20, cy + style.label_size * 1.7, cw - 40, style.label_size,
            style.heading_family, style.background, True, "start", 1,
        ))
        parts.append(_text(
            item.detail, cx + 20, cy + style.label_size * 4.2, cw - 40, style.detail_size,
            style.body_family, style.body_text, False, "start",
            max(1, int((ch - style.label_size * 4.2) / (style.detail_size * 1.3))),
        ))
    return "".join(parts)


def _draw_timeline(asset: VisualAsset, box: tuple[float, float, float, float], style: AssetStyle) -> str:
    x, y, width, height = box
    axis = y + height * 0.45
    parts = [
        f'<line x1="{x:g}" y1="{axis:g}" x2="{x + width:g}" y2="{axis:g}" '
        f'stroke="{style.primary}" stroke-width="3"/>'
    ]
    count = len(asset.items)
    step = width / max(1, count - 1) if count > 1 else 0.0
    slot = (width / count) - style.gap
    for index, item in enumerate(asset.items):
        cx = x + step * index if count > 1 else x + width / 2
        parts.append(
            f'<circle cx="{cx:g}" cy="{axis:g}" r="10" fill="{style.accent}" '
            f'stroke="{style.background}" stroke-width="3"/>'
        )
        if item.value:
            parts.append(_text(
                item.value, cx, axis - 28, slot, style.detail_size, style.heading_family,
                style.primary, True, "middle", 1,
            ))
        parts.append(_text(
            item.label, cx, axis + 36, slot, style.label_size, style.heading_family,
            style.body_text, True, "middle", 3,
        ))
    return "".join(parts)


def _draw_metric(asset: VisualAsset, box: tuple[float, float, float, float], style: AssetStyle) -> str:
    cells = _row_boxes(box, len(asset.items), style.gap)
    parts: list[str] = []
    for item, (cx, cy, cw, ch) in zip(asset.items, cells):
        parts.append(_panel(cx, cy, cw, ch, style, fill=style.surface, stroke=style.surface))
        parts.append(
            f'<rect x="{cx:g}" y="{cy:g}" width="{cw:g}" height="6" '
            f'rx="3" fill="{style.accent}"/>'
        )
        parts.append(_text(
            item.value or item.label, cx + cw / 2, cy + ch * 0.45, cw - 24, style.value_size,
            style.heading_family, style.primary, True, "middle", 1,
        ))
        parts.append(_text(
            item.label if item.value else item.detail, cx + cw / 2, cy + ch * 0.45 + style.label_size * 2,
            cw - 24, style.label_size, style.body_family, style.body_text, False, "middle",
            max(1, int((ch * 0.5) / (style.label_size * 1.3))),
        ))
    return "".join(parts)


def _draw_architecture(asset: VisualAsset, box: tuple[float, float, float, float], style: AssetStyle) -> str:
    cells = _column_boxes(box, len(asset.items), style.gap * 0.6)
    parts: list[str] = []
    for index, (item, (cx, cy, cw, ch)) in enumerate(zip(asset.items, cells)):
        inset = index * 18.0
        parts.append(_panel(
            cx + inset, cy, cw - inset * 2, ch, style,
            fill=style.surface if index % 2 else style.background,
        ))
        parts.append(_text(
            item.label, cx + inset + 24, cy + ch / 2 + style.label_size * 0.35, cw - inset * 2 - 48,
            style.label_size, style.heading_family, style.body_text, True, "start", 1,
        ))
        if item.detail:
            parts.append(_text(
                item.detail, cx + cw - inset - 24, cy + ch / 2 + style.detail_size * 0.35,
                (cw - inset * 2) * 0.45, style.detail_size, style.body_family,
                style.body_text, False, "end", 1,
            ))
    return "".join(parts)


def _draw_icon_list(asset: VisualAsset, box: tuple[float, float, float, float], style: AssetStyle) -> str:
    cells = _column_boxes(box, len(asset.items), style.gap * 0.5)
    parts: list[str] = []
    for item, (cx, cy, cw, ch) in zip(asset.items, cells):
        badge = min(ch - 8, 52.0)
        parts.append(
            f'<rect x="{cx:g}" y="{cy + (ch - badge) / 2:g}" width="{badge:g}" '
            f'height="{badge:g}" rx="{badge / 2:g}" fill="{style.surface}"/>'
        )
        if item.icon:
            parts.append(icon_paths(
                item.icon,
                (cx + badge * 0.22, cy + (ch - badge) / 2 + badge * 0.22, badge * 0.56, badge * 0.56),
                style.primary,
            ))
        text_x = cx + badge + 20
        text_w = cw - badge - 20
        parts.append(_text(
            item.label, text_x, cy + style.label_size + 4, text_w, style.label_size,
            style.heading_family, style.body_text, True, "start", 1,
        ))
        parts.append(_text(
            item.detail, text_x, cy + style.label_size * 2.6, text_w, style.detail_size,
            style.body_family, style.body_text, False, "start",
            max(1, int((ch - style.label_size * 2.6) / (style.detail_size * 1.3))),
        ))
    return "".join(parts)


_DRAW = {
    "process": _draw_process,
    "comparison": _draw_comparison,
    "timeline": _draw_timeline,
    "metric": _draw_metric,
    "architecture": _draw_architecture,
    "icon-list": _draw_icon_list,
}


def render(
    asset: VisualAsset,
    box: tuple[float, float, float, float],
    style: AssetStyle | None = None,
    source: str = provenance.DESIGN,
) -> str:
    """Draw a visual into a box, as markup the compiler turns into native shapes.

    The group records that the drawing is ours. The text inside it carries ``source``,
    which is the slide's own provenance because a label may only use the slide's own
    words -- the check that makes an Asset Agent safe rather than a way to launder
    invented copy as design.
    """
    resolved = style or AssetStyle()
    x, y, width, height = box
    if width < 200 or height < 90:
        raise AssetRefused(f"a {width:g}x{height:g} zone is too small for a diagram")
    body = _DRAW[asset.component](asset, box, resolved)
    stamped = provenance.stamp_document(body, source)
    return (
        f'<g data-sunairum-asset="{asset.component}" data-sunairum-asset-source="design" '
        f'data-sunairum-asset-bounds="{x:g} {y:g} {width:g} {height:g}">{stamped}</g>'
    )


def fit(
    asset: VisualAsset,
    box: tuple[float, float, float, float],
    style: AssetStyle | None = None,
    source: str = provenance.DESIGN,
) -> tuple[str, VisualAsset]:
    """Draw the visual, dropping trailing items until it fits, or refusing.

    Dropping an item is a real loss, so it is bounded by the component's own minimum
    and reported by the returned asset. What it replaces is worse: shrinking type until
    the labels fit, which is the silent-shrink failure this pipeline removed.
    """
    low, _high = ITEM_LIMITS[asset.component]
    current = asset
    while True:
        try:
            return render(current, box, style, source), current
        except AssetRefused:
            if len(current.items) <= low:
                raise
            current = VisualAsset(
                component=current.component,
                items=current.items[:-1],
                caption=current.caption,
            )


def compose(
    slide: dict,
    box: tuple[float, float, float, float],
    style: AssetStyle | None = None,
    source: str = provenance.DESIGN,
    call_json=None,
) -> tuple[str, AssetPlacement]:
    """A drawn visual for a slide and a zone, or a refusal.

    Refusal is a normal outcome. A zone left empty is a slide that looks sparse; a
    diagram forced into it is a slide that says something the source did not, or says
    it in type nobody can read.
    """
    asset = propose(slide, call_json)
    ungrounded = ungrounded_labels(asset, source_vocabulary(slide))
    if ungrounded:
        raise AssetRefused(f"labels not present in the slide: {ungrounded[:3]}")
    markup, placed = fit(asset, box, style, source)
    return markup, AssetPlacement(
        component=placed.component,
        box=box,
        items=len(placed.items),
        icons=tuple(item.icon for item in placed.items if item.icon),
    )


def insert(svg: str, markup: str) -> str:
    """Put drawn markup into a slide, just inside the closing tag."""
    close = svg.rfind("</svg>")
    if close < 0:
        return svg + markup
    return svg[:close] + markup + svg[close:]


def vacant_zones(
    before: Iterable[dict],
    after_svg: str,
    minimum_area: float = 40_000.0,
) -> list[tuple[float, float, float, float]]:
    """Visual slots the figure pipeline had and no longer fills.

    A slot with no source figure and no generated image is deleted outright, which is
    how a deck ends up with four slides carrying no visual at all. Those coordinates
    are the design's own answer to where a visual belongs, so they are exactly where a
    synthesized one goes.
    """
    remaining = [
        (
            _number(tag, "x"),
            _number(tag, "y"),
            _number(tag, "width"),
            _number(tag, "height"),
        )
        for tag in re.findall(r'<image\b[^>]*?(?:/>|>.*?</image>)', after_svg or "", re.S)
    ]
    zones: list[tuple[float, float, float, float]] = []
    for slot in before:
        if slot.get("is_background"):
            continue
        width = float(slot.get("width") or 0)
        height = float(slot.get("height") or 0)
        if width * height < minimum_area:
            continue
        box = (float(slot.get("x") or 0), float(slot.get("y") or 0), width, height)
        if any(_covers(box, image) for image in remaining):
            continue
        zones.append(box)
    return sorted(zones, key=lambda zone: -zone[2] * zone[3])


OCCUPIED_FRACTION = 0.5


def _covers(slot: tuple[float, float, float, float], image: tuple[float, float, float, float]) -> bool:
    """Whether a surviving image is the thing this slot was holding.

    Occupancy used to be an exact match on the origin, but a figure is fitted to its
    slot's aspect and so is inset from it -- the source figure on slide 4 sat at
    x=20.6 in a slot starting at x=0. The slot then read as empty and the agent drew
    a synthesized visual straight over the paper's own chart.
    """
    _, _, slot_width, slot_height = slot
    area = slot_width * slot_height
    if area <= 0:
        return False
    overlap_width = max(0.0, min(slot[0] + slot_width, image[0] + image[2]) - max(slot[0], image[0]))
    overlap_height = max(0.0, min(slot[1] + slot_height, image[1] + image[3]) - max(slot[1], image[1]))
    return (overlap_width * overlap_height) / area >= OCCUPIED_FRACTION


def _number(tag: str, name: str) -> float:
    found = re.search(rf'\b{name}="([-\d.]+)', tag)
    return float(found.group(1)) if found else 0.0


# --------------------------------------------------------------------------- ornaments
#
# Ornaments are the composer's second vocabulary. Where a component (above) fills a
# figure-sized zone with a diagram, an ornament dresses the slide's existing copy:
# an icon beside each bullet, a numbered badge in the header margin, an accent bar
# along the edge, a row of metric chips in a vacant band. They attach to what the
# layout already placed and never move it, which is what keeps them safe on strict
# templates. Every root group carries ``data-sunairum-ornament`` so budgets and plan
# validation can count them, and any text they add is either design furniture (a
# slide number) or the slide's own words, stamped accordingly.

ORNAMENT_DENSITY_LIMITS = {"low": 3, "medium": 4, "high": 5}

# Kinds whose real rendering happens elsewhere in the pipeline (a full drawn
# component, or the image pipeline). As ornaments they degrade to the subtle bar.
_SIDEBAR_FALLBACK_KINDS = {"mini-flow", "comparison-panel", "hero-image"}

_TEXT_NODE_ORN = re.compile(r'<text\b([^>]*)>(.*?)</text>', re.S | re.I)


def _point_icon(text: str) -> str:
    """The icon a sentence means, searched by its content words."""
    words = [
        word for word in _WORD.findall(str(text or "").casefold())
        if word not in STOPWORDS and len(word) > 2
    ]
    return pick_icon(*words[:8]) if words else ""


def _ornament_group(kind: str, body: str) -> str:
    return f'<g data-sunairum-ornament="{_escape(kind)}">{body}</g>'


def _accent_colour(treatment: dict, style: AssetStyle) -> str:
    role = str(treatment.get("accent_role") or "accent1")
    return style.primary if role == "accent2" else style.accent


def _numbered_badge(
    slide_number: int,
    style: AssetStyle,
    viewbox: tuple[float, float],
    colour: str,
    source: str,
) -> str:
    """A numbered disc in the top-right margin, like an editorial section marker."""
    if slide_number < 1:
        raise AssetRefused("a badge needs a slide number")
    width, _height = viewbox
    radius = 22.0
    cx, cy = width - 64.0, 56.0
    label = _text(
        str(slide_number), cx, cy + style.label_size * 0.36, radius * 2,
        style.label_size, style.heading_family, style.background, True, "middle", 1,
    )
    body = (
        f'<circle cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="{colour}"/>'
        + provenance.stamp_document(label, source)
    )
    return _ornament_group("numbered-badge", body)


def _accent_sidebar(
    slide: dict,
    style: AssetStyle,
    viewbox: tuple[float, float],
    colour: str,
) -> str:
    """A slim accent bar along the left margin with an icon at its head.

    Draws only in the outer margin (x < 48), which no shipped layout claims, so
    it cannot collide with furniture or copy.
    """
    _width, height = viewbox
    top, bottom = 140.0, height - 72.0
    if bottom - top < 160:
        raise AssetRefused("slide is too short for a sidebar")
    parts = [
        f'<rect x="24" y="{top:g}" width="7" height="{bottom - top:g}" rx="3.5" fill="{colour}"/>'
    ]
    icon = _point_icon(str(slide.get("title") or ""))
    if icon:
        drawn = icon_paths(icon, (14.0, top - 42.0, 28.0, 28.0), colour)
        if drawn:
            parts.append(drawn)
    return _ornament_group("accent-sidebar", "".join(parts))


def _body_text_anchors(svg_text: str, limit: int) -> list[tuple[float, float, float]]:
    """Anchor points (x, y, font-size) of body copy that could take an icon bullet.

    Only text with margin room to its left qualifies; titles and footers are
    excluded by size, and stacked lines of one paragraph collapse to the first.
    """
    anchors: list[tuple[float, float, float]] = []
    seen_y: list[float] = []
    for match in _TEXT_NODE_ORN.finditer(svg_text):
        attrs, body = match.group(1), match.group(2)
        if "data-sunairum-ornament" in attrs or "data-sunairum-icon" in attrs:
            continue
        plain = re.sub(r"<[^>]+>", " ", body).strip()
        if len(plain) < 12:
            continue
        x = re.search(r'\bx="([-\d.]+)"', attrs)
        y = re.search(r'\by="([-\d.]+)"', attrs)
        size = re.search(r'font-size="([\d.]+)"', attrs)
        if not (x and y and size):
            continue
        font_size = float(size.group(1))
        if not 12.0 <= font_size <= 22.0:
            continue
        text_x, text_y = float(x.group(1)), float(y.group(1))
        if text_x < 96.0:
            continue
        if any(abs(text_y - other) < font_size * 2.2 for other in seen_y):
            continue
        seen_y.append(text_y)
        anchors.append((text_x, text_y, font_size))
        if len(anchors) >= limit:
            break
    return anchors


def _icon_bullets(
    svg_text: str,
    slide: dict,
    treatment: dict,
    style: AssetStyle,
    colour: str,
) -> tuple[str, list[str]]:
    """A small icon in the margin beside each distinct body point."""
    limit = ORNAMENT_DENSITY_LIMITS.get(str(treatment.get("density") or "low"), 3)
    anchors = _body_text_anchors(svg_text, limit)
    if not anchors:
        raise AssetRefused("no body copy with margin room for icon bullets")
    requested = [str(name) for name in treatment.get("icons") or [] if str(name).strip()]
    points = _body_points(slide, len(anchors)) or [str(slide.get("title") or "")]
    parts: list[str] = []
    used: list[str] = []
    for index, (x, y, font_size) in enumerate(anchors):
        if index < len(requested) and asset_library.icon_markup(requested[index]):
            icon = requested[index]
        else:
            icon = _point_icon(points[index % len(points)])
        if not icon:
            continue
        side = min(24.0, font_size * 1.4)
        drawn = icon_paths(icon, (x - side - 14.0, y - side * 0.82, side, side), colour)
        if drawn:
            parts.append(drawn)
            used.append(icon)
    if not parts:
        raise AssetRefused("no vendored icon matches the slide's points")
    return _ornament_group("icon-bullets", "".join(parts)), used


def _metric_chips(
    slide: dict,
    band: tuple[float, float, float, float],
    style: AssetStyle,
    colour: str,
    source: str,
) -> str:
    """A row of small value chips in a vacant band, from the slide's own numbers."""
    points = _body_points(slide, 6)
    chips: list[tuple[str, str]] = []
    for point in points:
        value = _first_number(point)
        if value:
            label, _detail = _split_point(point)
            chips.append((value, label))
        if len(chips) >= 4:
            break
    if len(chips) < 2:
        raise AssetRefused("slide copy carries fewer than two numbers to chip")
    x, y, width, height = band
    chip_h = min(height, 84.0)
    cells = _row_boxes((x, y + (height - chip_h) / 2, width, chip_h), len(chips), style.gap)
    parts: list[str] = []
    for (value, label), (cx, cy, cw, ch) in zip(chips, cells):
        parts.append(
            f'<rect x="{cx:g}" y="{cy:g}" width="{cw:g}" height="{ch:g}" '
            f'rx="{style.corner_radius:g}" fill="{style.surface}"/>'
        )
        parts.append(f'<rect x="{cx:g}" y="{cy:g}" width="5" height="{ch:g}" rx="2.5" fill="{colour}"/>')
        parts.append(_text(
            value, cx + 22, cy + ch * 0.46, cw - 34, style.label_size * 1.3,
            style.heading_family, style.primary, True, "start", 1,
        ))
        parts.append(_text(
            label, cx + 22, cy + ch * 0.46 + style.detail_size * 1.4, cw - 34,
            style.detail_size, style.body_family, style.body_text, False, "start", 1,
        ))
    return _ornament_group("metric-chips", provenance.stamp_document("".join(parts), source))


def compose_ornaments(
    svg_text: str,
    slide: dict,
    treatment: dict | None,
    style: AssetStyle | None = None,
    source: str = provenance.DESIGN,
    slide_number: int = 0,
    viewbox: tuple[float, float] = (1280.0, 720.0),
    band: tuple[float, float, float, float] | None = None,
) -> tuple[str, list[dict]]:
    """Dress a slide per its planned treatment; refusal leaves it untouched.

    Returns the (possibly) decorated SVG and a record per drawn ornament for the
    manifest. One treatment produces at most two ornaments (its main dressing
    plus the numbered badge motif), staying well inside the plan's budget.
    """
    if not isinstance(treatment, dict):
        return svg_text, []
    kind = str(treatment.get("kind") or "none")
    if kind == "none" or "data-sunairum-ornament" in svg_text:
        return svg_text, []
    resolved = style or AssetStyle()
    colour = _accent_colour(treatment, resolved)
    drawn: list[dict] = []
    effective = "accent-sidebar" if kind in _SIDEBAR_FALLBACK_KINDS else kind
    try:
        if effective == "icon-bullets":
            markup, icons = _icon_bullets(svg_text, slide, treatment, resolved, colour)
            svg_text = insert(svg_text, markup)
            drawn.append({"slide": slide_number, "ornament": "icon-bullets", "icons": icons})
        elif effective == "numbered-badge":
            svg_text = insert(svg_text, _numbered_badge(slide_number, resolved, viewbox, colour, provenance.DESIGN))
            drawn.append({"slide": slide_number, "ornament": "numbered-badge"})
        elif effective == "metric-chips":
            if band is None:
                raise AssetRefused("no vacant band for metric chips")
            svg_text = insert(svg_text, _metric_chips(slide, band, resolved, colour, source))
            drawn.append({"slide": slide_number, "ornament": "metric-chips", "zone": list(band)})
        elif effective == "accent-sidebar":
            svg_text = insert(svg_text, _accent_sidebar(slide, resolved, viewbox, colour))
            drawn.append({"slide": slide_number, "ornament": "accent-sidebar"})
    except AssetRefused as refusal:
        print(f"[ornament] slide {slide_number or '?'}: {effective} refused ({refusal})")
        # A refused main dressing can still fall back to the sidebar, which asks
        # nothing of the copy.
        if effective not in {"accent-sidebar", "numbered-badge"}:
            try:
                svg_text = insert(svg_text, _accent_sidebar(slide, resolved, viewbox, colour))
                drawn.append({"slide": slide_number, "ornament": "accent-sidebar"})
            except AssetRefused:
                return svg_text, drawn
    return svg_text, drawn
