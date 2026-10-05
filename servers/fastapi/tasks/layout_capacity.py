"""Per-slot capacity contracts derived from the layout templates themselves.

The generator used to be told only which layout to use, never how much text that
layout could hold, so overflow was discovered after the fact and papered over by
shrinking and truncating. Measuring each slot's real box and type size turns
"will it fit" into a question answerable before a single character is written.

Capacity is derived from the templates rather than hand-written so it cannot
drift when a layout is edited.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from .layout_geometry import text_width_px, usable_text_width
    from .slot_geometry import infer_text_geometry_from_svg
except ImportError:  # pragma: no cover - supports direct task imports
    from layout_geometry import text_width_px, usable_text_width
    from slot_geometry import infer_text_geometry_from_svg

# Ratio of line box to font size for the deck's sans stack.
LINE_HEIGHT = 1.32
# A representative mixed-case sample; per-cluster estimation makes the measured
# width depend on the characters, so capacity is expressed against typical prose
# rather than a worst case of all-wide glyphs.
SAMPLE = "The quick brown fox jumps over the lazy dog and then rests again "

_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
_GROUP = re.compile(r"<g\b[^>]*>", re.S)
_BOUNDS = re.compile(r'data-pptx-bounds="\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*"')
_TEXT = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')


# Geometric capacity is not the same as good density: a 504px-tall panel holds
# fifteen lines of 22px prose, which fits and still makes an unreadable slide.
# The recommended budget is what the generator is asked to aim for; max_chars
# stays as the mechanical limit nothing may exceed.
RECOMMENDED_BODY_LINES = 6
RECOMMENDED_TITLE_LINES = 2
_TITLE_SLOT = re.compile(r"TITLE|HEADING|HEADLINE")


@dataclass(frozen=True)
class SlotCapacity:
    """How much copy one named slot can hold at its designed type size."""

    slot: str
    x: float
    y: float
    width: float
    height: float
    font_size: float
    bold: bool
    max_lines: int
    chars_per_line: int
    max_chars: int
    recommended_lines: int
    recommended_chars: int

    def as_dict(self) -> dict:
        return asdict(self)


def chars_per_line(
    width: float,
    font_size: float,
    bold: bool = False,
    font_family: str | None = None,
) -> int:
    """How many characters of typical prose fit across ``width``.

    Delegates to the module that also performs the wrapping, so the budget the
    copy editor is given is the budget the wrapper enforces. ``font_family``
    selects real advances from the shipped font file, so a condensed face reports
    the extra characters it genuinely fits instead of inheriting an average.
    """
    if width <= 0 or font_size <= 0:
        return 0
    try:
        from .text_layout import slot_budget
    except ImportError:  # pragma: no cover - supports direct task imports
        from text_layout import slot_budget
    return slot_budget(
        (0.0, 0.0, width, font_size), font_size, font_family, bold, sample=SAMPLE,
    ).chars_per_line


def max_lines(height: float, font_size: float, line_height: float = LINE_HEIGHT) -> int:
    """How many lines of ``font_size`` fit in ``height``, never fewer than one.

    ``line_height`` is baseline-to-baseline spacing, so it is larger than a single
    line's own glyph box: a slot drawn exactly one line tall divides to less than
    one and used to report zero. Sixty-eight declared slots across the shipped packs
    were affected, most of them titles, and ``content_schema`` turned each zero into
    ``maxLength: 1`` -- telling the generator a 64px headline could hold one
    character. A slot exists to hold text, so it holds at least a line of it; the
    height decides how many *more* fit. The native fill checker already floors at
    one for the same reason.
    """
    if height <= 0 or font_size <= 0:
        return 0
    return max(1, int(height / (font_size * line_height)))


def _attrs(raw: str) -> dict[str, str]:
    return {key: value for key, value in _ATTR.findall(raw)}


def _is_bold(attrs: dict[str, str]) -> bool:
    weight = attrs.get("font-weight", "")
    style = attrs.get("style", "")
    return weight in {"bold", "600", "700", "800", "900"} or "font-weight:700" in style.replace(" ", "")


def slot_capacities(template_svg: str) -> dict[str, SlotCapacity]:
    """Measure every placeholder slot in a layout template.

    A slot's box comes from the enclosing group's ``data-pptx-bounds`` and its
    type size from the carrier ``<text>``, which is exactly what the compiler
    honours, so the numbers describe the real rendered slide.
    """
    capacities: dict[str, SlotCapacity] = {}
    groups = [(match.start(), match.group(0)) for match in _GROUP.finditer(template_svg)]
    for match in _TEXT.finditer(template_svg):
        names = _PLACEHOLDER.findall(match.group(2))
        if not names:
            continue
        attrs = _attrs(match.group(1))
        try:
            font_size = float(attrs.get("font-size", "0"))
        except ValueError:
            font_size = 0.0
        if font_size <= 0:
            continue
        box = None
        for start, raw in reversed(groups):
            if start < match.start():
                found = _BOUNDS.search(raw)
                if found:
                    box = tuple(float(found.group(index)) for index in (1, 2, 3, 4))
                    break
        if box is None:
            continue
        x, y, width, height = box
        bold = _is_bold(attrs)
        family = attrs.get("font-family", "")
        per_line = chars_per_line(usable_text_width(width), font_size, bold, family)
        lines = max_lines(height, font_size)
        for name in names:
            ceiling = RECOMMENDED_TITLE_LINES if _TITLE_SLOT.search(name) else RECOMMENDED_BODY_LINES
            recommended_lines = max(1, min(lines, ceiling)) if lines else 0
            # A layout may spend the same token in several places: a body paragraph
            # and, further down, a page number in the footer. Keyed by name alone the
            # last one won, so `02_large_title_list_footer` reported a BODY budget of
            # four characters -- its page number -- instead of the 1080px column the
            # copy is actually written into, and reflow then broke every line after a
            # letter or two. The budget belongs to the slot that holds the content.
            existing = capacities.get(name)
            if existing is not None and existing.max_chars >= per_line * lines:
                continue
            capacities[name] = SlotCapacity(
                slot=name,
                x=x, y=y, width=width, height=height,
                font_size=font_size,
                bold=bold,
                max_lines=lines,
                chars_per_line=per_line,
                max_chars=per_line * lines,
                recommended_lines=recommended_lines,
                recommended_chars=per_line * recommended_lines,
            )
    return capacities


def inferred_slot_capacities(template_svg: str) -> dict[str, SlotCapacity]:
    """Measure an authored layout that declares no slots at all.

    A designer's finished deck reused as a template has no ``{{PLACEHOLDER}}`` tokens
    and no ``data-pptx-bounds``; it is just drawing. Its slots are therefore keyed by
    the same selector the filler and repairer address them with, and their boxes come
    from the drawing itself -- see :mod:`slot_geometry`.

    The budget follows the design rather than the raw geometry. A card label the
    designer wrote as one short line is measured as one line, because letting a
    generator put four lines where the design has one is what made these decks
    collide in the first place.
    """
    capacities: dict[str, SlotCapacity] = {}
    for geometry in infer_text_geometry_from_svg(template_svg):
        available = max(0.0, geometry.width)
        per_line = chars_per_line(
            available, geometry.font_size, geometry.bold, geometry.font_family,
        )
        if per_line <= 0:
            continue
        # The design draws at least one line here, so the box holds at least one.
        lines = max(1, max_lines(geometry.height, geometry.font_size))
        authored_lines = 1
        if available > 0 and geometry.content_width > 0:
            authored_lines = max(1, int(-(-geometry.content_width // available)))
        recommended = max(1, min(lines, authored_lines))
        capacities[geometry.selector] = SlotCapacity(
            slot=geometry.selector,
            x=round(geometry.left, 2),
            y=round(geometry.top, 2),
            width=round(geometry.width, 2),
            height=round(geometry.height, 2),
            font_size=geometry.font_size,
            bold=geometry.bold,
            max_lines=lines,
            chars_per_line=per_line,
            max_chars=per_line * lines,
            recommended_lines=recommended,
            recommended_chars=per_line * recommended,
        )
    return capacities


def measure_layout_slots(template_svg: str) -> dict[str, SlotCapacity]:
    """Capacity for one layout, however it declares its slots.

    Declared placeholders win: they are the layout's own statement of intent, and
    reading them keeps the packs written for this pipeline measuring exactly as
    before. Inference is the fallback for authored packs, which previously measured
    nothing and so were generated into with no budget at all.
    """
    declared = slot_capacities(template_svg)
    if declared:
        return declared
    return inferred_slot_capacities(template_svg)


def layout_capacities(templates_dir: str | Path, *, infer: bool = True) -> dict[str, dict[str, dict]]:
    """Capacity contracts for every layout in a template pack."""
    root = Path(templates_dir)
    measure = measure_layout_slots if infer else slot_capacities
    result: dict[str, dict[str, dict]] = {}
    for path in sorted(root.glob("*.svg")):
        try:
            markup = path.read_text(encoding="utf-8")
        except OSError:
            continue
        slots = measure(markup)
        if slots:
            result[path.stem] = {name: slot.as_dict() for name, slot in slots.items()}
    return result


def content_schema(capacity: dict[str, dict], *, required: tuple[str, ...] = ()) -> dict:
    """Compile a layout's capacity contract into a JSON Schema for the content pass.

    Expressing the limits as schema means an over-long value is rejected
    mechanically at the point of generation instead of being silently shrunk to
    fit several stages later.
    """
    properties = {}
    for name, slot in sorted(capacity.items()):
        limit = int(slot.get("max_chars") or 0)
        target = int(slot.get("recommended_chars") or limit)
        properties[name] = {
            "type": "string",
            "maxLength": max(1, limit),
            "description": (
                f"Aim for about {target} characters; {limit} is the hard limit. "
                f"Renders as up to {slot.get('recommended_lines')} line(s) of "
                f"{slot.get('font_size')}px text."
            ),
        }
    return {
        "type": "object",
        "properties": properties,
        "required": [name for name in required if name in properties],
        "additionalProperties": False,
    }


def write_capacity_registry(templates_dir: str | Path, destination: str | Path) -> Path:
    payload = layout_capacities(templates_dir)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
