"""Slide-to-slide transition choices for PPT setup → deckhtml --slide-transition.

Catalog names must match ``vendor/deckhtml`` ``SLIDE_TRANSITION_EFFECTS``.
``random`` is convert-time variety (a different catalog effect per slide), not
the PowerPoint show-time ``p:random`` meta effect.
"""

from __future__ import annotations

from typing import Any

# Popular chips shown first in the setup UI.
POPULAR_SLIDE_TRANSITIONS: tuple[str, ...] = (
    "fade",
    "push",
    "wipe",
    "cover",
    "dissolve",
    "cut",
    "zoom",
)

# Full deckhtml catalog (excluding ``none``, which means disable).
SLIDE_TRANSITION_EFFECTS: tuple[str, ...] = (
    "fade",
    "fade-through-black",
    "push",
    "wipe",
    "cover",
    "pull",
    "split",
    "blinds",
    "checker",
    "comb",
    "random-bar",
    "strips",
    "wheel",
    "wedge",
    "circle",
    "diamond",
    "plus",
    "newsflash",
    "dissolve",
    "zoom",
    "cut",
    "conveyor",
    "doors",
    "ferris",
    "flash",
    "flip",
    "flythrough",
    "gallery",
    "glitter",
    "honeycomb",
    "pan",
    "prism",
    "reveal",
    "ripple",
    "shred",
    "switch",
    "vortex",
    "warp",
    "wheel-reverse",
    "window",
    "fall-over",
    "drape",
    "curtains",
    "wind",
    "prestige",
    "fracture",
    "crush",
    "peel-off",
    "page-curl-single",
    "page-curl-double",
    "airplane",
    "origami",
    "morph",
)

RANDOM_TOKEN = "random"
DEFAULT_FIXED_TRANSITION = "fade"

_ALLOWED = {RANDOM_TOKEN, *SLIDE_TRANSITION_EFFECTS}


def catalog_payload() -> dict[str, Any]:
    """JSON for the setup UI picker."""
    return {
        "default": DEFAULT_FIXED_TRANSITION,
        "random": RANDOM_TOKEN,
        "popular": list(POPULAR_SLIDE_TRANSITIONS),
        "effects": list(SLIDE_TRANSITION_EFFECTS),
    }


def normalize_slide_transition(
    enabled: bool,
    effect: str | None = None,
) -> str | None:
    """Return a deckhtml ``--slide-transition`` value, or None to disable.

    When animations are off → None (``--no-slide-transitions``).
    When on with empty/unknown effect → default fixed ``fade`` (same on all slides).
    ``random`` keeps convert-time per-slide variety.
    """
    if not enabled:
        return None
    raw = str(effect or "").strip().casefold()
    if not raw or raw in {"none", "off", "false"}:
        return DEFAULT_FIXED_TRANSITION
    if raw in _ALLOWED:
        return raw
    return DEFAULT_FIXED_TRANSITION
