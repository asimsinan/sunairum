"""Shared layout geometry primitives for generation and QA."""

from __future__ import annotations

import math
import re
from typing import Iterable

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def multiply(left: Matrix, right: Matrix) -> Matrix:
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def parse_transform(value: str | None) -> Matrix:
    result = IDENTITY
    if not value:
        return result
    for name, raw in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", value):
        values = [float(item) for item in re.findall(_NUMBER, raw)]
        name = name.lower()
        operation = IDENTITY
        if name == "matrix" and len(values) >= 6:
            operation = tuple(values[:6])  # type: ignore[assignment]
        elif name == "translate" and values:
            operation = (1.0, 0.0, 0.0, 1.0, values[0], values[1] if len(values) > 1 else 0.0)
        elif name == "scale" and values:
            operation = (values[0], 0.0, 0.0, values[1] if len(values) > 1 else values[0], 0.0, 0.0)
        elif name == "rotate" and values:
            angle = math.radians(values[0])
            operation = (math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle), 0.0, 0.0)
            if len(values) >= 3:
                cx, cy = values[1:3]
                operation = multiply(
                    multiply((1.0, 0.0, 0.0, 1.0, cx, cy), operation),
                    (1.0, 0.0, 0.0, 1.0, -cx, -cy),
                )
        elif name == "skewx" and values:
            operation = (1.0, 0.0, math.tan(math.radians(values[0])), 1.0, 0.0, 0.0)
        elif name == "skewy" and values:
            operation = (1.0, math.tan(math.radians(values[0])), 0.0, 1.0, 0.0, 0.0)
        result = multiply(result, operation)
    return result


def point(matrix: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def bounds(x: float, y: float, width: float, height: float, matrix: Matrix = IDENTITY) -> dict[str, float]:
    points = [point(matrix, px, py) for px, py in ((x, y), (x + width, y), (x, y + height), (x + width, y + height))]
    xs, ys = zip(*points)
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


def effective_scales(matrix: Matrix) -> tuple[float, float, float]:
    a, b, c, d, _e, _f = matrix
    return math.hypot(a, b), math.hypot(c, d), a * c + b * d


def native_estimator_available() -> bool:
    """Advance-width font metrics are not bundled; ratio fallback is used."""
    return False


def has_real_metrics(font_family: str | None, bold: bool = False) -> bool:
    del font_family, bold
    return False


def missing_glyphs(text: str, font_family: str | None, bold: bool = False) -> list[str]:
    del text, font_family, bold
    return []


def text_width_px(
    text: str,
    font_size: float,
    letter_spacing: float = 0.0,
    bold: bool = False,
    font_family: str | None = None,
) -> float:
    """Approximate rendered width of ``text`` (ratio fallback)."""
    del font_family
    ratio = 0.58 if bold else 0.53
    return len(text) * font_size * ratio + max(letter_spacing, 0.0) * max(len(text) - 1, 0)


def line_height_px(
    font_size: float,
    font_family: str | None = None,
    bold: bool = False,
) -> float:
    del font_family, bold
    return font_size * 1.2


SLOT_PADDING_PX = 32.0


def usable_text_width(zone_width: float) -> float:
    """Width available for text inside a slot of ``zone_width``.

    There is no safety margin any more. The old ``TEXT_WIDTH_SAFETY`` factor
    existed to absorb the ratio estimator's error, and it disagreed between the
    fitter and the capacity derivation, so capacity promised more text than the
    fitter would accept and the surplus was truncated and then reported as a
    defect. Real advances need no fudge.
    """
    return max(SLOT_PADDING_PX, zone_width - SLOT_PADDING_PX)


def line_box(baseline_x: float, baseline_y: float, width: float, font_size: float, anchor: str = "start") -> tuple[float, float, float, float]:
    if anchor == "middle":
        left, right = baseline_x - width / 2.0, baseline_x + width / 2.0
    elif anchor == "end":
        left, right = baseline_x - width, baseline_x
    else:
        left, right = baseline_x, baseline_x + width
    return left, baseline_y - font_size * 0.8, right, baseline_y + font_size * 0.37
