"""Lay text out inside a box, using the metrics the renderer will use.

SVG ``<text>`` does not reflow: a node is a baseline and one unwrappable line.
Everything downstream compensated for that -- copy was written to no stated
limit, a fitter then shrank and cut it to make it fit, and the checker reported
the shrinking and cutting as defects, so each repair produced the next round's
work.

This module makes a slot a box instead of a baseline. Text is broken into lines
that measurably fit the box before it is ever written into the slide, so the
common case needs no fitting at all. Where the copy genuinely does not fit, the
overflow is reported rather than silently cut: the answer to too much text is
less text, or a larger type scale, decided by whoever owns that content.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

try:
    from .layout_geometry import line_height_px, text_width_px
except ImportError:  # pragma: no cover - supports direct task imports
    from layout_geometry import line_height_px, text_width_px

# A design's own rhythm is tighter than a font's default line spacing, which
# includes room for accents the deck rarely uses. Clamped so a font with unusual
# vertical metrics cannot produce absurd leading.
MIN_LINE_HEIGHT_FACTOR = 1.05
MAX_LINE_HEIGHT_FACTOR = 1.60
# Card / sidebar / multi-line body: never crush sibling baselines.
CARD_BODY_LINE_HEIGHT_FACTOR = 1.40
MIN_BODY_BASELINE_PITCH_FACTOR = 1.35

_WHITESPACE = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class Line:
    text: str
    width: float


@dataclass(frozen=True)
class BlockLayout:
    """One slot's text, broken into lines that fit its width."""

    lines: tuple[Line, ...]
    font_size: float
    line_height: float
    max_lines: int

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def height(self) -> float:
        """Height the laid-out lines occupy."""
        if not self.lines:
            return 0.0
        return self.font_size + self.line_height * (len(self.lines) - 1)

    @property
    def widest(self) -> float:
        return max((line.width for line in self.lines), default=0.0)

    @property
    def overflow_lines(self) -> int:
        """Lines beyond what the box height allows.

        Wrapping solves width. Height is the failure this replaces: once copy
        wraps, it can still be taller than its box, and PowerPoint's own
        ``normAutofit`` would silently shrink the type to hide it.
        """
        if self.max_lines <= 0:
            return 0
        return max(0, len(self.lines) - self.max_lines)

    @property
    def fits(self) -> bool:
        return self.overflow_lines == 0


@dataclass(frozen=True)
class SlotBudget:
    """How much text a slot can hold, from the same code that wraps it."""

    chars_per_line: int
    max_lines: int
    line_height: float

    @property
    def max_chars(self) -> int:
        return self.chars_per_line * self.max_lines


def line_height_for(
    font_size: float,
    font_family: str | None = None,
    bold: bool = False,
    factor: float | None = None,
) -> float:
    """Baseline-to-baseline spacing in px."""
    if factor is not None:
        return font_size * max(MIN_LINE_HEIGHT_FACTOR, min(MAX_LINE_HEIGHT_FACTOR, factor))
    measured = line_height_px(font_size, font_family, bold)
    if font_size <= 0:
        return measured
    ratio = measured / font_size
    if ratio < MIN_LINE_HEIGHT_FACTOR or ratio > MAX_LINE_HEIGHT_FACTOR:
        ratio = min(max(ratio, MIN_LINE_HEIGHT_FACTOR), MAX_LINE_HEIGHT_FACTOR)
    return font_size * ratio


def min_baseline_pitch(
    font_size: float,
    font_family: str | None = None,
    bold: bool = False,
) -> float:
    """Floor for consecutive baselines in one card/sidebar body."""
    fs = max(1.0, float(font_size))
    measured = line_height_for(
        fs, font_family, bold, factor=CARD_BODY_LINE_HEIGHT_FACTOR
    )
    return max(fs * MIN_BODY_BASELINE_PITCH_FACTOR, measured)


def wrap(
    text: str,
    width: float,
    font_size: float,
    font_family: str | None = None,
    bold: bool = False,
    letter_spacing: float = 0.0,
) -> list[str]:
    """Break ``text`` into lines that each measure within ``width``.

    Explicit newlines are honoured as forced breaks so an authored stanza keeps
    its shape.
    """
    if not text:
        return []
    if width <= 0 or font_size <= 0:
        return [" ".join(text.split())] if text.strip() else []

    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        words = [word for word in _WHITESPACE.split(paragraph.strip()) if word]
        if not words:
            # A blank authored line is a deliberate gap; keep it.
            lines.append("")
            continue
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if current and text_width_px(trial, font_size, letter_spacing, bold, font_family) > width:
                lines.append(current)
                current = word
            else:
                current = trial
            # A word that cannot fit is a structured fit failure, not permission
            # to turn prose into one-character lines. Keep it intact so the
            # caller can select a wider layout or shorten grounded copy.
        if current:
            lines.append(current)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def layout_block(
    text: str,
    box: tuple[float, float, float, float],
    font_size: float,
    font_family: str | None = None,
    bold: bool = False,
    letter_spacing: float = 0.0,
    line_height_factor: float | None = None,
) -> BlockLayout:
    """Break ``text`` to fit ``box`` and report whether it did."""
    _x, _y, width, height = box
    spacing = line_height_for(font_size, font_family, bold, line_height_factor)
    broken = wrap(text, width, font_size, font_family, bold, letter_spacing)
    lines = tuple(
        Line(text=value, width=text_width_px(value, font_size, letter_spacing, bold, font_family))
        for value in broken
    )
    return BlockLayout(
        lines=lines,
        font_size=font_size,
        line_height=spacing,
        max_lines=max_lines_in(height, font_size, spacing),
    )


def max_lines_in(height: float, font_size: float, line_height: float) -> int:
    """How many lines of ``font_size`` fit in ``height``, never fewer than one.

    A slot exists to hold text, so it holds at least a line of it; the height
    decides how many more. Measuring the first line as a full line-height used to
    report zero for any slot drawn exactly one line tall.
    """
    if height <= 0 or font_size <= 0:
        return 1
    if line_height <= 0:
        return 1
    return max(1, int((height - font_size) / line_height) + 1)


def slot_budget(
    box: tuple[float, float, float, float],
    font_size: float,
    font_family: str | None = None,
    bold: bool = False,
    letter_spacing: float = 0.0,
    line_height_factor: float | None = None,
    sample: str = "the quick brown fox jumps over a lazy dog and keeps going ",
) -> SlotBudget:
    """What a slot can hold, measured the same way it will be wrapped."""
    _x, _y, width, height = box
    spacing = line_height_for(font_size, font_family, bold, line_height_factor)
    lines = max_lines_in(height, font_size, spacing)
    if width <= 0 or font_size <= 0:
        return SlotBudget(chars_per_line=0, max_lines=lines, line_height=spacing)
    per_char = (
        text_width_px(sample, font_size, letter_spacing, bold, font_family) / len(sample)
    )
    if per_char <= 0:
        return SlotBudget(chars_per_line=0, max_lines=lines, line_height=spacing)
    # Word wrap leaves unused width at line ends; keep promised capacity under wrap.
    chars_per_line = max(0, int((width / per_char) * 0.85))
    return SlotBudget(
        chars_per_line=chars_per_line,
        max_lines=lines,
        line_height=spacing,
    )


def tspan_markup(
    layout: BlockLayout,
    x: float,
    escape: bool = True,
) -> str:
    """Render laid-out lines as ``<tspan>`` rows for a ``<text>`` node body.

    The first row carries ``dy="0"`` so the node keeps the baseline the design
    drew; later rows advance by the measured line height.
    """
    parts: list[str] = []
    for index, line in enumerate(layout.lines):
        value = html.escape(line.text, quote=False) if escape else line.text
        dy = 0.0 if index == 0 else layout.line_height
        parts.append(f'<tspan x="{x:g}" dy="{dy:g}">{value}</tspan>')
    return "".join(parts)


def exceeds_measured_slot(text: str, spec: dict) -> dict | None:
    """How ``text`` overruns a measured slot, or None when it fits.

    A character count alone is not a fit test. Copy can be well under a slot's
    ``max_chars`` and still need more lines than the slot has -- long unbreakable
    words in a narrow column are the usual cause -- and the only thing that used
    to notice was the fitter, which then shrank the type to hide it. Both the
    width and the line count are checked here, before the copy is written into a
    slide.
    """
    if not isinstance(spec, dict) or not isinstance(text, str) or not text:
        return None
    limit = int(spec.get("max_chars") or 0)
    if limit and len(text) > limit:
        return {
            "reason": "chars",
            "length": len(text),
            "max_chars": limit,
            "overflow": len(text) - limit,
        }
    width = float(spec.get("width") or 0.0)
    height = float(spec.get("height") or 0.0)
    font_size = float(spec.get("font_size") or 0.0)
    if width <= 0 or font_size <= 0:
        return None
    layout = layout_block(
        text,
        (0.0, 0.0, width, height),
        font_size,
        spec.get("font_family") or None,
        bool(spec.get("bold")),
    )
    allowed = int(spec.get("max_lines") or 0) or layout.max_lines
    if len(layout.lines) <= allowed:
        return None
    return {
        "reason": "lines",
        "length": len(text),
        "max_chars": limit or 0,
        "lines": len(layout.lines),
        "max_lines": allowed,
        "overflow": len(layout.lines) - allowed,
    }


def fits_in_slot(
    text: str,
    box: tuple[float, float, float, float],
    font_size: float,
    font_family: str | None = None,
    bold: bool = False,
    letter_spacing: float = 0.0,
) -> bool:
    """Whether ``text`` fits ``box`` at this size without shrinking or cutting."""
    return layout_block(
        text, box, font_size, font_family, bold, letter_spacing,
    ).fits
