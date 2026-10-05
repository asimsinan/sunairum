"""The box each text node in a slide may occupy, inferred from the design itself.

Layouts written for this pipeline declare their slots with ``{{PLACEHOLDER}}``
tokens inside a group carrying ``data-pptx-bounds``, so their geometry is simply
read off the markup. Authored gallery packs -- a designer's finished deck reused as
a template -- declare neither: they are ordinary SVG, with a rounded-rectangle
``<path>`` for each card and several independently positioned ``<text>`` nodes
inside it.

Measured against those packs the old reader returned nothing, so no character
budget ever reached the model. Copy was written blind, the fitter shrank and
truncated it to make it fit, and QA then reported the fitter's own output as
defects. This module closes that gap by deriving the same facts from the drawing:
a text node's box runs from its own baseline to the nearest thing it must not
collide with -- a sibling line below it, or the edge of the card it sits in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

try:
    from .layout_geometry import (
        IDENTITY,
        Matrix,
        multiply,
        parse_transform,
        point,
        text_width_px,
    )
except ImportError:  # pragma: no cover - supports direct task imports
    from layout_geometry import (
        IDENTITY,
        Matrix,
        multiply,
        parse_transform,
        point,
        text_width_px,
    )

# Glyph box above and below the baseline, in em. Shared with the fitter so a box
# measured here means the same thing there.
ASC = 0.80
DESC = 0.37
# Minimum air between two stacked lines.
GAP = 4.0
# Inner breathing room from the edge of the card a text sits in. Text placed hard
# against a panel border reads as a mistake even when it technically fits.
PANEL_PAD = 14.0
# Deck safe area: nothing should be measured as though it may run to the canvas cut.
SAFE_MARGIN = 32.0
# A shape has to be big enough to be a container rather than a rule, an icon or an
# accent bar. Below this it is decoration and cannot define a slot's bounds.
MIN_PANEL_WIDTH = 120.0
MIN_PANEL_HEIGHT = 60.0

_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_COMMAND = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)")
_BOLD_WEIGHTS = {"bold", "bolder", "600", "700", "800", "900"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _numbers(raw: str) -> list[float]:
    return [float(match.group(0)) for match in _NUMBER.finditer(raw)]


def path_points(d: str) -> list[tuple[float, float]]:
    """Every on-path point of a path, enough to bound it.

    Control points are ignored and arcs contribute only their endpoint, so a
    rounded rectangle -- which is what these packs draw their cards with -- bounds
    exactly to its corners. Reading the numbers in pairs instead would treat an
    arc's radii and flags as coordinates and produce nonsense.
    """
    points: list[tuple[float, float]] = []
    x = y = 0.0
    start_x = start_y = 0.0
    for match in _COMMAND.finditer(d or ""):
        command = match.group(1)
        values = _numbers(match.group(2))
        upper = command.upper()
        relative = command.islower()
        if upper == "Z":
            x, y = start_x, start_y
            continue
        if upper == "H":
            for value in values:
                x = x + value if relative else value
                points.append((x, y))
            continue
        if upper == "V":
            for value in values:
                y = y + value if relative else value
                points.append((x, y))
            continue
        # Every remaining command ends on an (x, y) pair; the stride is how many
        # numbers precede it in one repetition.
        stride = {"M": 2, "L": 2, "T": 2, "Q": 4, "S": 4, "C": 6, "A": 7}[upper]
        for index in range(0, len(values) - stride + 1, stride):
            chunk = values[index:index + stride]
            dx, dy = chunk[-2], chunk[-1]
            x = x + dx if relative else dx
            y = y + dy if relative else dy
            points.append((x, y))
            if upper == "M" and index == 0:
                start_x, start_y = x, y
    return points


def _shape_box(element: ET.Element, matrix: Matrix) -> tuple[float, float, float, float] | None:
    """Bounding box of a container-like shape, in slide coordinates."""
    tag = _local(element.tag)
    if tag == "rect":
        try:
            x = float(element.get("x", "0"))
            y = float(element.get("y", "0"))
            width = float(element.get("width", "0"))
            height = float(element.get("height", "0"))
        except ValueError:
            return None
        corners = [(x, y), (x + width, y), (x, y + height), (x + width, y + height)]
    elif tag == "path":
        corners = path_points(element.get("d", ""))
        if not corners:
            return None
    else:
        return None
    mapped = [point(matrix, px, py) for px, py in corners]
    xs = [px for px, _ in mapped]
    ys = [py for _, py in mapped]
    return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class TextGeometry:
    """Where one text node sits and how much room it has."""

    selector: str
    panel_id: str
    baseline_x: float
    baseline_y: float
    anchor: str
    font_size: float
    bold: bool
    letter_spacing: float
    # The family actually authored on the node. Measurement without it falls back
    # to a font-blind ratio table, which reads a condensed display face and a wide
    # geometric sans as the same width.
    font_family: str
    left: float
    top: float
    right: float
    bottom: float
    # What the designer put here, and how wide it renders. The authored text fits by
    # definition, so it is the reference for how densely this slot is meant to be
    # filled -- a card label written as one short line should not come back as four.
    content: str
    content_width: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    def as_dict(self) -> dict:
        return {
            "selector": self.selector,
            "panel_id": self.panel_id,
            "x": round(self.left, 2),
            "y": round(self.top, 2),
            "width": round(self.width, 2),
            "height": round(self.height, 2),
            "font_size": self.font_size,
            "bold": self.bold,
            "anchor": self.anchor,
            "letter_spacing": self.letter_spacing,
            "content": self.content,
        }


def _inherited(chain: list[ET.Element], name: str) -> str | None:
    for element in chain:
        value = element.get(name)
        if value is not None:
            return value
        style = element.get("style")
        if style:
            found = re.search(rf"(?:^|;)\s*{re.escape(name)}\s*:\s*([^;]+)", style)
            if found:
                return found.group(1).strip()
    return None


def _float(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    match = _NUMBER.search(value)
    return float(match.group(0)) if match else default


def _canvas(root: ET.Element) -> tuple[float, float]:
    view_box = root.get("viewBox")
    if view_box:
        values = _numbers(view_box)
        if len(values) >= 4:
            return values[2], values[3]
    return _float(root.get("width"), 1280.0), _float(root.get("height"), 720.0)


def infer_text_geometry(root: ET.Element) -> tuple[TextGeometry, ...]:
    """Measure every text node's usable box from the drawing around it."""
    # Selectors must be byte-identical to the ones the filler and repairer use, so
    # they come from the same function rather than a second implementation.
    from template_text_slots import _text_selector

    parent_by_child = {child: parent for parent in root.iter() for child in parent}
    canvas_width, canvas_height = _canvas(root)
    safe = (
        SAFE_MARGIN,
        SAFE_MARGIN,
        canvas_width - SAFE_MARGIN,
        canvas_height - SAFE_MARGIN,
    )

    def chain_of(element: ET.Element) -> list[ET.Element]:
        chain = [element]
        while chain[-1] in parent_by_child:
            chain.append(parent_by_child[chain[-1]])
        return chain

    def matrix_of(element: ET.Element) -> Matrix:
        result = IDENTITY
        for ancestor in reversed(chain_of(element)):
            result = multiply(result, parse_transform(ancestor.get("transform")))
        return result

    # The largest container-like shape drawn directly inside each group. A card's
    # rounded rectangle defines the room its labels have; a 6px accent bar does not.
    panel_by_group: dict[ET.Element, tuple[float, float, float, float]] = {}
    for group in root.iter():
        if _local(group.tag) != "g":
            continue
        best: tuple[float, float, float, float] | None = None
        best_area = 0.0
        for child in group:
            box = _shape_box(child, matrix_of(child))
            if box is None:
                continue
            width, height = box[2] - box[0], box[3] - box[1]
            if width < MIN_PANEL_WIDTH or height < MIN_PANEL_HEIGHT:
                continue
            area = width * height
            if area > best_area:
                best, best_area = box, area
        if best is not None:
            panel_by_group[group] = best

    # Pass one: place every text node, so pass two can see what is below it.
    placed: list[dict] = []
    for element in root.iter():
        if _local(element.tag) != "text":
            continue
        chain = chain_of(element)
        font_size = _float(_inherited(chain, "font-size"), 0.0)
        if font_size <= 0:
            continue
        matrix = matrix_of(element)
        baseline = point(matrix, _float(element.get("x"), 0.0), _float(element.get("y"), 0.0))
        weight = (_inherited(chain, "font-weight") or "").strip().lower()
        panel_id = ""
        panel = safe
        for ancestor in chain:
            if ancestor in panel_by_group:
                panel = panel_by_group[ancestor]
                break
        for ancestor in chain:
            identifier = (ancestor.get("id") or "").strip()
            if identifier:
                panel_id = identifier
                break
        anchor = (_inherited(chain, "text-anchor") or "start").strip() or "start"
        bold = weight in _BOLD_WEIGHTS
        letter_spacing = _float(_inherited(chain, "letter-spacing"), 0.0)
        font_family = (_inherited(chain, "font-family") or "").strip()
        # The room a slot has is bounded by what the design already draws around it,
        # so obstacles are measured from the template's own text rather than guessed
        # from its font size. The authored text fits by definition, which is what
        # makes it a trustworthy reference.
        content = "".join(element.itertext())
        drawn = text_width_px(content, font_size, letter_spacing, bold, font_family)
        if anchor == "middle":
            occupied = (baseline[0] - drawn / 2.0, baseline[0] + drawn / 2.0)
        elif anchor == "end":
            occupied = (baseline[0] - drawn, baseline[0])
        else:
            occupied = (baseline[0], baseline[0] + drawn)
        placed.append({
            "element": element,
            "selector": _text_selector(element, parent_by_child, compact=True),
            "panel_id": panel_id,
            "x": baseline[0],
            "y": baseline[1],
            "font_size": font_size,
            "bold": bold,
            "letter_spacing": letter_spacing,
            "font_family": font_family,
            "anchor": anchor,
            "panel": panel,
            "occupied": occupied,
            "content": content,
            "content_width": drawn,
        })

    results: list[TextGeometry] = []
    for record in placed:
        panel = record["panel"]
        font_size = record["font_size"]
        left_limit = max(panel[0] + PANEL_PAD, safe[0])
        right_limit = min(panel[2] - PANEL_PAD, safe[2])
        top = record["y"] - ASC * font_size

        own_bottom = record["y"] + DESC * font_size

        # Neighbours sharing this text's line restrict how wide it may run: a page
        # number anchored at the right edge must not grow left into the footer note
        # beside it.
        for other in placed:
            if other is record:
                continue
            other_top = other["y"] - ASC * other["font_size"]
            other_bottom = other["y"] + DESC * other["font_size"]
            if other_top >= own_bottom or other_bottom <= top:
                continue
            if other["occupied"][1] <= record["occupied"][0]:
                left_limit = max(left_limit, other["occupied"][1] + GAP)
            elif other["occupied"][0] >= record["occupied"][1]:
                right_limit = min(right_limit, other["occupied"][0] - GAP)

        if record["anchor"] == "middle":
            half = max(0.0, min(record["x"] - left_limit, right_limit - record["x"]))
            left, right = record["x"] - half, record["x"] + half
        elif record["anchor"] == "end":
            left, right = left_limit, min(record["x"], right_limit)
        else:
            left, right = max(record["x"], left_limit), right_limit

        # How far down this text may grow before it hits something. Only neighbours
        # that actually share horizontal space can obstruct it: two labels in
        # different columns of the same card do not.
        bottom = min(panel[3] - PANEL_PAD, safe[3])
        for other in placed:
            if other is record:
                continue
            other_top = other["y"] - ASC * other["font_size"]
            if other_top <= top + 0.5:
                continue
            if other["occupied"][1] <= left or other["occupied"][0] >= right:
                continue
            bottom = min(bottom, other_top - GAP)

        # A single line always has room for itself; a negative box would otherwise
        # report a slot as holding no characters at all.
        bottom = max(bottom, own_bottom)
        results.append(TextGeometry(
            selector=record["selector"],
            panel_id=record["panel_id"],
            baseline_x=record["x"],
            baseline_y=record["y"],
            anchor=record["anchor"],
            font_size=font_size,
            bold=record["bold"],
            letter_spacing=record["letter_spacing"],
            font_family=record.get("font_family", ""),
            left=left,
            top=top,
            right=max(right, left),
            bottom=bottom,
            content=record["content"],
            content_width=record["content_width"],
        ))
    return tuple(results)


def infer_text_geometry_from_svg(markup: str) -> tuple[TextGeometry, ...]:
    try:
        root = ET.fromstring(markup)
    except ET.ParseError:
        return ()
    return infer_text_geometry(root)


def attach_slot_geometry(slots: tuple, root: ET.Element) -> tuple:
    """Give each template text slot the box and budget measured from the design.

    This is the join that lets the copy editor, the fitter and the QA checker talk
    about the same box. They used to disagree: the editor had no box at all, so it
    wrote to no limit; the fitter measured one from the markup and shrank the copy;
    and the checker then reported the shrink as a defect.

    Slots whose layout declares its own capacity are left alone, and a slot that
    cannot be measured is returned unchanged rather than given a fabricated budget.
    """
    # Imported here so the capacity module can depend on this one without a cycle.
    try:
        from .layout_capacity import chars_per_line, max_lines
    except ImportError:  # pragma: no cover - supports direct task imports
        from layout_capacity import chars_per_line, max_lines

    # A layout that declares its own bounds already has a capacity contract, applied
    # through content_schema. Inferring a second one would give the same slot two
    # different budgets, which is the disagreement this whole change exists to end.
    if any(element.get("data-pptx-bounds") for element in root.iter()):
        return slots

    by_selector = {item.selector: item for item in infer_text_geometry(root)}
    if not by_selector:
        return slots
    enriched = []
    for slot in slots:
        geometry = by_selector.get(getattr(slot, "selector", ""))
        if geometry is None or not hasattr(slot, "with_geometry"):
            enriched.append(slot)
            continue
        available = max(0.0, geometry.width)
        per_line = chars_per_line(
            available, geometry.font_size, geometry.bold, geometry.font_family,
        )
        if per_line <= 0:
            enriched.append(slot)
            continue
        lines = max(1, max_lines(geometry.height, geometry.font_size))
        authored_lines = 1
        if available > 0 and geometry.content_width > 0:
            authored_lines = max(1, int(-(-geometry.content_width // available)))
        recommended = max(1, min(lines, authored_lines))
        enriched.append(slot.with_geometry(
            box=(geometry.left, geometry.top, geometry.width, geometry.height),
            font_size=geometry.font_size,
            bold=geometry.bold,
            font_family=geometry.font_family,
            max_chars=per_line * lines,
            recommended_chars=per_line * recommended,
        ))
    return tuple(enriched)
