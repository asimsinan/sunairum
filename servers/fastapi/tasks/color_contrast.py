"""WCAG colour maths shared by theming, QA and the structural invariants.

Kept in one place so the generator, the QA checks and the tests cannot disagree
about whether a slide's text is legible.
"""

from __future__ import annotations

import re

HEX = re.compile(r"^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")

# WCAG 2.1 AA: 4.5:1 for body text, 3:1 for large text (>=18pt, or >=14pt bold).
AA_BODY = 4.5
AA_LARGE = 3.0


def parse_hex(colour: str) -> tuple[int, int, int] | None:
    match = HEX.match((colour or "").strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    return tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(channel)))):02X}" for channel in rgb)


def relative_luminance(colour: str | tuple[int, int, int]) -> float:
    rgb = parse_hex(colour) if isinstance(colour, str) else colour
    if rgb is None:
        return 0.0
    channels = []
    for value in rgb:
        srgb = value / 255
        channels.append(srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str | tuple[int, int, int], second: str | tuple[int, int, int]) -> float:
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _blend(rgb: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(  # type: ignore[return-value]
        channel + (target[index] - channel) * amount for index, channel in enumerate(rgb)
    )


def mix(first: str, second: str, amount: float) -> str:
    """Blend ``first`` toward ``second`` by ``amount`` (0.0-1.0)."""
    start, end = parse_hex(first), parse_hex(second)
    if start is None or end is None:
        return first
    return to_hex(_blend(start, end, max(0.0, min(1.0, amount))))


def ensure_contrast(foreground: str, background: str, minimum: float = AA_BODY) -> str:
    """Nudge ``foreground`` toward white or black until it clears ``minimum``.

    Hue is preserved as far as possible: the colour is blended toward whichever
    extreme is further from the background, so a brand accent stays recognisable
    instead of snapping to pure black or white.
    """
    fg = parse_hex(foreground)
    bg = parse_hex(background)
    if fg is None or bg is None:
        return foreground
    if contrast_ratio(fg, bg) >= minimum:
        return to_hex(fg)

    target = (255, 255, 255) if relative_luminance(bg) < 0.5 else (0, 0, 0)
    best = fg
    # 20 steps gives ~5% granularity, enough to stop just past the threshold.
    for step in range(1, 21):
        candidate = _blend(fg, target, step / 20)
        best = candidate
        if contrast_ratio(candidate, bg) >= minimum:
            return to_hex(candidate)
    return to_hex(best)
