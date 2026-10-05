"""What each repair costs, and which ones are worth a model call.

The repair loop used to treat every finding the same way: one model call per issue,
in the order the checker happened to report them. The run that motivated this module
spent 187 calls that way, and the issues still open when it was cancelled were
``table-cell-overlap`` and ``font-too-small`` -- geometry, which no amount of
rewriting copy can move. The calls were spent on findings that were never the
model's to fix.

Repairs are ordered here by what they cost and how far they reach:

``deterministic``
    Geometry and structure. Fixed in code or not at all. Costs nothing, so it goes
    first and its results are re-checked before anything is spent.
``copy``
    The one thing a language model is actually the right tool for: saying the same
    thing in fewer words. Worth a call, one slide at a time.
``theme``
    A defect that recurs across the deck is a property of the theme, not of the
    slides. Fixed once for every slide instead of N times, one slide at a time.
``vision``
    Rendering a slide and looking at it is the most expensive signal there is, so it
    is consulted last, once the cheap signals have stopped reporting.

A finding nobody can act on is ``unfixable``: it is reported, and no call is spent
trying.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

# Ordered cheapest first. The loop follows this order.
TIERS = ("deterministic", "copy", "theme", "vision", "unfixable")

# Geometry and structure. Code moves these, or nothing does. Handing a model an SVG
# and asking it to resolve a collision produced the loop this module exists to end.
DETERMINISTIC = frozenset({
    "blank-image",
    "card-baseline-misalignment",
    "duplicate-image",
    "flow-edge-missing",
    "font-size",
    "incomplete-flow",
    "invalid-svg",
    "marker-identity-missing",
    "marker-not-centered",
    "marker-outside-circle",
    "missing-image",
    "plan-incomplete-flow",
    "table-cell-mismatch",
    "table-cell-overlap",
    "table-grid-mismatch",
    "table-metadata-missing",
    "text-clipped",
    "text-overlap",
    "text-icon-overlap",
    "text-rail-collision",
    "text-divider-collision",
    "unsupported-generated-content",
    "visual-zone-overflow",
})

# Too many words for the space, or the wrong words. Shortening prose is the model's job.
COPY = frozenset({
    "card-text-overflow",
    "duplicate-text",
    "duplicate-title",
    "generic-title",
    "placeholder-token",
    "provenance-missing",
    "text-overflow",
})

# Rendered-slide judgement. Expensive to produce and expensive to act on.
VISION = frozenset({
    "rendered-text-overlap",
    "vision-cramped",
    "vision-overlap",
    "vision-text-clipped",
    "vision-visual-context-mismatch",
    "visual-conflict",
})

# Nothing in the repair loop can fix these: they are facts about the source, the
# environment, or the run. Spending a call on one is spending it on nothing.
UNFIXABLE = frozenset({
    "grounding-slide-dropped",
    "grounding-svg-missing",
    "pdf-fallback-forbidden",
    "pdf-source-hash-mismatch",
    "pdf-source-unavailable",
    "recompile",
    "render-validation-failed",
    "render-validation-unavailable",
    "rendered-slide-count",
    "rendered-text-unavailable",
    "repair-timeout",
    "slide-count",
    "visual-semantic-unavailable",
    "visual-unavailable",
})

# A defect this widespread is the theme's, not the slide's. Below the threshold the
# slides are repaired individually; at or above it, one deck-wide revision replaces
# every one of those calls.
THEME_ROUTABLE = frozenset({"card-text-overflow", "font-too-small", "text-overflow"})
RECURRENCE_THRESHOLD = 3

# Readability floors for a deck-wide type-scale revision, in px on the 1280x720 canvas.
ROLE_FLOOR_PX = {"title": 28.0, "heading": 22.0, "body": 16.0, "caption": 13.0}
# One step of the scale. Smaller is not worth a rebuild; larger is a visible redesign.
SCALE_STEP = 0.92
SCALE_FLOOR = 0.8


def tier(category: str) -> str:
    """Which repair tier a finding belongs to."""
    name = str(category or "").strip().lower()
    if name in DETERMINISTIC:
        return "deterministic"
    if name in COPY:
        return "copy"
    if name in VISION:
        return "vision"
    if name in UNFIXABLE:
        return "unfixable"
    if name == "font-too-small":
        # On its own this is a theme decision, never a rewrite of one slide's copy.
        return "theme"
    if name.startswith("aesthetic-"):
        # How the deck looks is a property of its design system. A vision reviewer
        # allowed to reach one slide drifts the deck apart across eight, which is the
        # per-slide designer this project explicitly declined to build.
        return "unfixable" if name.endswith("-unavailable") else "theme"
    if name.startswith("vision-") or name.startswith("rendered-"):
        return "vision"
    if name.startswith("plan-"):
        return "deterministic"
    # An unrecognised finding is assumed to be about wording, which is the only tier
    # where a wrong guess merely wastes one call instead of corrupting geometry.
    return "copy"


def costs_a_model_call(category: str) -> bool:
    """Whether repairing this finding needs a model at all."""
    return tier(category) == "copy"


def sort_key(issue: dict[str, Any]) -> tuple[int, int, str]:
    """Cheapest and most local first, then by slide so a run is reproducible."""
    name = str(issue.get("category") or "")
    slide = issue.get("slide")
    return (
        TIERS.index(tier(name)),
        int(slide) if isinstance(slide, int) else 10**6,
        name,
    )


def order_by_cost(issues: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The findings, cheapest tier first.

    Ordering matters even when everything is eventually attempted: a deterministic
    fix often resolves a finding a later tier would otherwise have paid for.
    """
    return sorted(issues, key=sort_key)


def group_by_tier(issues: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """The findings split into the tiers that handle them."""
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in TIERS}
    for issue in issues:
        grouped[tier(str(issue.get("category") or ""))].append(issue)
    return grouped


def recurring_defects(
    issues: Iterable[dict[str, Any]],
    threshold: int = RECURRENCE_THRESHOLD,
) -> dict[str, list[int]]:
    """Categories that recur across enough slides to be the theme's problem.

    Returns the slides each such category was reported on. One deck-wide revision
    settles all of them, where per-slide repair would have cost one call each.
    """
    slides_by_category: dict[str, set[int]] = defaultdict(set)
    for issue in issues:
        category = str(issue.get("category") or "").strip().lower()
        if category not in THEME_ROUTABLE:
            continue
        slide = issue.get("slide")
        if isinstance(slide, int):
            slides_by_category[category].add(slide)
    return {
        category: sorted(slides)
        for category, slides in slides_by_category.items()
        if len(slides) >= max(2, int(threshold))
    }


def type_scale_revision(
    issues: Iterable[dict[str, Any]],
    applied_scale: float = 1.0,
    threshold: int = RECURRENCE_THRESHOLD,
) -> dict[str, Any] | None:
    """The single deck-wide type-scale change a recurring defect calls for.

    This is not the per-element shrink that was deleted from the fitter. That one was
    invisible, applied to whichever line happened to overflow, and left the deck in
    three different sizes for the same role. This is one factor, recorded, applied to
    every slide, and bounded by the readability floors -- a theme decision, which is
    why it happens once.
    """
    recurring = recurring_defects(issues, threshold)
    if not recurring:
        return None
    overflowing = {
        category: slides
        for category, slides in recurring.items()
        if category in {"card-text-overflow", "text-overflow"}
    }
    if not overflowing:
        # Type is too small across the deck, so the scale should grow rather than
        # shrink; that is a redesign, not a repair, and is left to the theme owner.
        return None
    scale = round(float(applied_scale) * SCALE_STEP, 4)
    if scale < SCALE_FLOOR:
        return None
    slides = sorted({slide for found in overflowing.values() for slide in found})
    return {
        "scale": scale,
        "categories": sorted(overflowing),
        "slides": slides,
        "reason": (
            f"{', '.join(sorted(overflowing))} on {len(slides)} slides is a type-scale "
            f"problem, not {len(slides)} copy problems"
        ),
        "calls_avoided": len(slides),
    }


_FONT_SIZE_ATTR = re.compile(r'font-size="([\d.]+)"')
_FONT_SIZE_STYLE = re.compile(r"(font-size:\s*)([\d.]+)px")


def _role_floor(tag: str) -> float:
    role = tag.casefold()
    if "title" in role:
        return ROLE_FLOOR_PX["title"]
    if "heading" in role or "subtitle" in role:
        return ROLE_FLOOR_PX["heading"]
    if "caption" in role or "footnote" in role or "label" in role:
        return ROLE_FLOOR_PX["caption"]
    return ROLE_FLOOR_PX["body"]


def apply_type_scale(svg: str, scale: float) -> str:
    """Apply one type scale uniformly to every text size on a slide.

    Uniform is the point. A scale that skipped some elements would break the size
    relationships the theme is made of, which is the difference between a type scale
    and the per-line shrinking this replaced.
    """
    factor = float(scale)
    if not svg or factor >= 1.0 or factor <= 0:
        return svg

    def scale_tag(match: re.Match) -> str:
        tag, body = match.group(1), match.group(2)
        floor = _role_floor(tag)

        def scale_attr(size_match: re.Match) -> str:
            size = float(size_match.group(1))
            return f'font-size="{max(floor, size * factor):g}"'

        def scale_style(style_match: re.Match) -> str:
            size = float(style_match.group(2))
            return f"{style_match.group(1)}{max(floor, size * factor):g}px"

        tag = _FONT_SIZE_ATTR.sub(scale_attr, tag)
        tag = _FONT_SIZE_STYLE.sub(scale_style, tag)
        return f"<text{tag}>{body}</text>"

    return re.sub(r"<text\b([^>]*)>(.*?)</text>", scale_tag, svg, flags=re.S)


def repair_plan(issues: Iterable[dict[str, Any]], applied_scale: float = 1.0) -> dict[str, Any]:
    """How a set of findings should be worked, and what it will cost.

    The model-call estimate is the number of findings that are actually a model's to
    fix, which is what the budget should be spent on and nothing else.
    """
    found = list(issues)
    grouped = group_by_tier(found)
    revision = type_scale_revision(found, applied_scale)
    theme_covered = set(revision["slides"]) if revision else set()
    copy_calls = [
        issue
        for issue in grouped["copy"]
        if not (
            revision
            and issue.get("slide") in theme_covered
            and str(issue.get("category") or "").lower() in set(revision["categories"])
        )
    ]
    return {
        "order": order_by_cost(found),
        "tiers": {name: len(grouped[name]) for name in TIERS},
        "type_scale_revision": revision,
        "model_calls": len(copy_calls),
        "no_call_needed": len(found) - len(copy_calls),
    }
