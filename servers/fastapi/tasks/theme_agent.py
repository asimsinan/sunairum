"""One design system per deck, authored once and applied to every slide.

The tempting version of this is a designer that works slide by slide, choosing colours
and sizes for each page as it goes. That is worse than no designer at all, for two
reasons this project can point at.

The authored packs are already professionally designed -- eleven to fifty-three slides
each, with a palette and a type scale that hold together across the whole deck. A model
picking colours per page is far more likely to degrade that than improve it, so where a
pack states its design, the pack wins and this module only records what it said.

And per-slide authorship drifts. arXiv 2608.03298 puts it plainly: "Across a long deck,
style drifts and visual logic is duplicated." A deck whose body text is 18px on slide
two and 15px on slide six does not read as a design; it reads as a mistake, and it is
the same mistake the per-element font shrinking made before it was deleted.

So the scope here is deck-level and nothing else: palette, type scale, spacing rhythm,
and which vendored family serves which role. Authored once, applied uniformly, and
revised at most once per recurring defect -- because a defect on eight slides is one
theme decision rather than eight copy rewrites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

try:
    from . import asset_library
    from .color_contrast import AA_BODY, AA_LARGE, contrast_ratio, ensure_contrast, parse_hex
    from .repair_economics import ROLE_FLOOR_PX, apply_type_scale, type_scale_revision
except ImportError:  # pragma: no cover - supports direct task imports
    import asset_library  # type: ignore[no-redef]
    from color_contrast import (  # type: ignore[no-redef]
        AA_BODY, AA_LARGE, contrast_ratio, ensure_contrast, parse_hex,
    )
    from repair_economics import (  # type: ignore[no-redef]
        ROLE_FLOOR_PX, apply_type_scale, type_scale_revision,
    )

# The palette a slide addresses. Every deck fills all six, so no slide has to invent a
# colour and no two slides invent different ones.
PALETTE_KEYS = (
    "background", "secondary_bg", "primary", "accent", "secondary_accent", "body_text",
)

# Roles the type scale names, in px on the 1280x720 canvas. Floors come from the repair
# economics module so a theme cannot author a size the QA pass would then report.
TYPE_ROLES = ("title", "heading", "body", "caption")

DEFAULT_PALETTE = {
    "background": "#FFFFFF",
    "secondary_bg": "#F4F6F8",
    "primary": "#1E3A8A",
    "accent": "#F59E0B",
    "secondary_accent": "#3B82F6",
    "body_text": "#0F172A",
}

DEFAULT_TYPE_SCALE = {"title": 44.0, "heading": 26.0, "body": 18.0, "caption": 14.0}

# Margin, the gap between columns, and the gap between stacked blocks. One rhythm per
# deck is what makes eight slides look like one document.
DEFAULT_SPACING = {"margin": 64.0, "gutter": 24.0, "block": 20.0}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_FONT_FAMILY_ATTR = re.compile(r'font-family="([^"]*)"')


@dataclass(frozen=True)
class DeckTheme:
    """The design decisions that belong to the deck rather than to any slide."""

    palette: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PALETTE))
    heading_family: str = "Inter"
    body_family: str = "Inter"
    type_scale: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TYPE_SCALE))
    spacing: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SPACING))
    # Who decided this. A pack's own design is authoritative and is never overwritten.
    authority: str = "default"
    applied_scale: float = 1.0
    revisions: tuple[dict[str, Any], ...] = ()
    notes: str = ""

    @property
    def typography(self) -> dict[str, dict[str, str]]:
        """The shape generation and the run manifest already speak."""
        return {
            "heading": {"primary": self.heading_family, "css": "sans-serif"},
            "body": {"primary": self.body_family, "css": "sans-serif"},
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "palette": dict(self.palette),
            "heading_family": self.heading_family,
            "body_family": self.body_family,
            "type_scale": dict(self.type_scale),
            "spacing": dict(self.spacing),
            "authority": self.authority,
            "applied_scale": self.applied_scale,
            "revisions": list(self.revisions),
            "notes": self.notes,
        }


class ThemeRefused(ValueError):
    """A theme that would ship an illegible deck."""


def _hex_or(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = f"#{text}"
    if _HEX.match(text):
        return text.upper()
    parsed = parse_hex(text)
    return fallback if parsed is None else text.upper()


def normalize(theme: DeckTheme) -> DeckTheme:
    """Make a theme legible before any slide is drawn with it.

    Contrast is repaired rather than reported. A model that picks a handsome mid-grey
    on white has made a readability decision it is not qualified to make, and the
    alternative to nudging the colour is either shipping it or refusing the whole deck
    over one hue.
    """
    palette = {key: _hex_or(theme.palette.get(key), DEFAULT_PALETTE[key]) for key in PALETTE_KEYS}
    background = palette["background"]
    palette["body_text"] = ensure_contrast(palette["body_text"], background, AA_BODY)
    palette["primary"] = ensure_contrast(palette["primary"], background, AA_LARGE)
    palette["accent"] = ensure_contrast(palette["accent"], background, AA_LARGE)
    if theme.authority != "pack" and contrast_ratio(palette["secondary_bg"], background) > 3.0:
        # A "secondary" background that reads as a second background is a panel colour;
        # one that contrasts this hard is a block of colour competing with the content.
        # A pack is exempt: a deliberate dark panel is a design decision someone made.
        palette["secondary_bg"] = DEFAULT_PALETTE["secondary_bg"]
    proposed = {
        role: float(theme.type_scale.get(role, DEFAULT_TYPE_SCALE[role]) or 0.0)
        for role in TYPE_ROLES
    }
    if not proposed["title"] > proposed["heading"] > proposed["body"] >= proposed["caption"]:
        # A scale without hierarchy is not a scale, and raising each size to its own
        # floor would manufacture a hierarchy nobody chose. Fall back to one that has it.
        proposed = dict(DEFAULT_TYPE_SCALE)
    scale = {
        role: max(float(ROLE_FLOOR_PX.get(role, 12.0)), size)
        for role, size in proposed.items()
    }
    spacing = {
        key: max(4.0, float(theme.spacing.get(key, DEFAULT_SPACING[key])))
        for key in DEFAULT_SPACING
    }
    return replace(theme, palette=palette, type_scale=scale, spacing=spacing)


def resolve_family(role: str, requested: str = "") -> str:
    """A family the deck can actually render, resolved from the vendored library.

    A theme naming a font nobody has is the substitution problem in a new place: the
    engine measures one face and the recipient's PowerPoint renders another.
    """
    wanted = str(requested or "").strip()
    if wanted and any(wanted.casefold() == family.casefold() for family in asset_library.families()):
        return next(
            family for family in asset_library.families()
            if family.casefold() == wanted.casefold()
        )
    return asset_library.family_for_role(role) or (asset_library.families() or ["Inter"])[0]


_SERIF_HINTS = (
    "georgia", "times", "garamond", "playfair", "merriweather", "lora",
    "baskerville", "didot", "bodoni", "cambria", "charter", "serif",
)


def _role_for_family(family: str, default_role: str) -> str:
    """The closest vendored role for a family the library does not carry."""
    name = family.casefold()
    if any(hint in name for hint in _SERIF_HINTS) and "sans" not in name:
        return "serif"
    return default_role


def from_pack(palette: dict | None, typography: dict | None) -> DeckTheme:
    """The theme an authored pack already states. This module does not second-guess it.

    Colors and scale are the pack's word. Font families, however, must exist in the
    vendored library or the engine measures one face while PowerPoint renders another —
    so a pack family we do not carry is substituted with the nearest vendored role
    (Georgia -> serif, Arial -> humanist) instead of shipping an unrenderable name.
    """
    typography = typography if isinstance(typography, dict) else {}
    heading = str((typography.get("heading") or {}).get("primary") or "Inter")
    body = str((typography.get("body") or {}).get("primary") or heading)
    scale_src = typography.get("type_scale") if isinstance(typography.get("type_scale"), dict) else {}
    type_scale = {
        role: float(scale_src.get(role, DEFAULT_TYPE_SCALE[role]) or DEFAULT_TYPE_SCALE[role])
        for role in TYPE_ROLES
    }
    # Body size may also arrive as typography.body_size from confirm_ui / pack apply.
    try:
        body_size = float(typography.get("body_size") or 0)
    except (TypeError, ValueError):
        body_size = 0.0
    if body_size > 0:
        type_scale["body"] = body_size
    return normalize(DeckTheme(
        palette={**DEFAULT_PALETTE, **{
            key: str(value) for key, value in (palette or {}).items() if key in PALETTE_KEYS
        }},
        heading_family=resolve_family(_role_for_family(heading, "geometric"), heading),
        body_family=resolve_family(_role_for_family(body, "humanist"), body),
        type_scale=type_scale,
        authority="pack",
        notes="palette and typography as authored by the template pack",
    ))


PROMPT = """You are Sunairum's theme designer. Choose one design system for the
whole deck: it is applied to every slide unchanged.

Return JSON only, in exactly this shape:

{"palette": {"background": "#FFFFFF", "secondary_bg": "#F1F5F9", "primary": "#0B3B6F",
 "accent": "#E07A2F", "secondary_accent": "#3B82F6", "body_text": "#0F172A"},
 "heading_role": "geometric", "body_role": "humanist",
 "type_scale": {"title": 44, "heading": 26, "body": 18, "caption": 14},
 "spacing": {"margin": 64, "gutter": 24, "block": 20},
 "rationale": "one sentence"}

Rules:

- Font roles must be one of: %(roles)s. You choose a role, not a font name; the deck
  renders a vendored family for that role.
- Body text must be comfortably legible against the background. Assume the reader is
  at the back of a room.
- Light backgrounds unless the subject genuinely calls for a dark deck.
- The palette should suit the subject matter rather than being decorative. A clinical
  paper and a consumer launch do not look the same.
- Sizes are px on a 1280x720 canvas.
"""


def author(
    brief: dict[str, Any],
    call_json=None,
    base: DeckTheme | None = None,
) -> DeckTheme:
    """One model call, once per deck, for a deck that has no authored design.

    Failure is uneventful: the default system is a competent one, and a deck rendered
    in it is a deck, whereas a deck blocked on a theme call is nothing.
    """
    starting = base or DeckTheme()
    if call_json is None:
        try:
            from llm_client import call_llm_json

            call_json = call_llm_json
        except Exception:
            return normalize(starting)
    roles = ", ".join(sorted(asset_library.roles())) or "geometric, humanist, serif, display"
    try:
        payload = call_json(
            PROMPT % {"roles": roles},
            "\n".join(
                f"{key}: {value}" for key, value in brief.items() if value
            ) or "No brief was supplied; choose a neutral professional system.",
        )
        if not isinstance(payload, dict):
            raise ThemeRefused("theme proposal is not an object")
    except Exception as error:
        print(f"[theme] proposal unavailable ({error}); using the default design system")
        return normalize(replace(starting, authority="default"))
    palette = payload.get("palette") if isinstance(payload.get("palette"), dict) else {}
    scale = payload.get("type_scale") if isinstance(payload.get("type_scale"), dict) else {}
    spacing = payload.get("spacing") if isinstance(payload.get("spacing"), dict) else {}
    proposed = DeckTheme(
        palette={**DEFAULT_PALETTE, **{
            key: str(value) for key, value in palette.items() if key in PALETTE_KEYS
        }},
        heading_family=resolve_family(str(payload.get("heading_role") or "geometric")),
        body_family=resolve_family(str(payload.get("body_role") or "humanist")),
        type_scale={
            role: float(scale.get(role, DEFAULT_TYPE_SCALE[role]) or DEFAULT_TYPE_SCALE[role])
            for role in TYPE_ROLES
        },
        spacing={
            key: float(spacing.get(key, DEFAULT_SPACING[key]) or DEFAULT_SPACING[key])
            for key in DEFAULT_SPACING
        },
        authority="agent",
        notes=str(payload.get("rationale") or "")[:200],
    )
    return normalize(proposed)


def resolve(
    brief: dict[str, Any],
    pack_palette: dict | None = None,
    pack_typography: dict | None = None,
    authored: bool = False,
    call_json=None,
) -> DeckTheme:
    """The deck's theme, from whichever authority owns it.

    An authored pack owns its own design. A deck built from bare layouts has no design
    yet, and that is the only case where a model is asked to supply one.
    """
    if authored:
        return from_pack(pack_palette, pack_typography)
    if pack_palette and str(brief.get("palette_source") or "") == "user":
        # The user chose these colours in the confirmation step; that is a decision,
        # not a gap for a model to fill.
        return replace(from_pack(pack_palette, pack_typography), authority="user")
    return author(brief, call_json, base=from_pack(pack_palette, pack_typography))


# ---------------------------------------------------------------------------- revision


def revise(theme: DeckTheme, issues: list[dict]) -> tuple[DeckTheme, dict | None]:
    """The one deck-wide change a recurring defect calls for, or nothing.

    "Once per recurring defect" is the whole economics of it: text overflowing on eight
    slides is one type-scale decision, and repairing it as eight copy rewrites is what
    spent 187 model calls on a single run.
    """
    revision = type_scale_revision(issues, theme.applied_scale)
    if not revision:
        return theme, None
    scaled = {
        role: max(ROLE_FLOOR_PX.get(role, 12.0), size * (revision["scale"] / theme.applied_scale))
        for role, size in theme.type_scale.items()
    }
    return replace(
        theme,
        type_scale=scaled,
        applied_scale=revision["scale"],
        revisions=theme.revisions + (revision,),
    ), revision


def absorb(theme: DeckTheme, directives: dict[str, Any]) -> DeckTheme:
    """Fold an aesthetic verdict's advice into the theme, within the same guard rails.

    The rendered review can see what no markup check can -- that a deck is monotonous,
    or that its hierarchy is flat. What it must not do is edit slides, so its verdict
    arrives here as an adjustment to the one thing that applies to all of them.
    """
    scale = dict(theme.type_scale)
    emphasis = float(directives.get("title_emphasis") or 0.0)
    if emphasis:
        scale["title"] = max(ROLE_FLOOR_PX["title"], scale["title"] * (1.0 + max(-0.2, min(0.25, emphasis))))
        scale["heading"] = max(ROLE_FLOOR_PX["heading"], scale["heading"] * (1.0 + max(-0.1, min(0.15, emphasis))))
    spacing = dict(theme.spacing)
    breathing = float(directives.get("breathing_room") or 0.0)
    if breathing:
        for key in spacing:
            spacing[key] = max(4.0, spacing[key] * (1.0 + max(-0.2, min(0.4, breathing))))
    accent = directives.get("accent")
    palette = dict(theme.palette)
    if accent:
        palette["accent"] = _hex_or(accent, palette["accent"])
    return normalize(replace(
        theme, type_scale=scale, spacing=spacing, palette=palette,
        notes=(directives.get("reason") or theme.notes),
    ))


# -------------------------------------------------------------------------- application


def apply_fonts(svg: str, theme: DeckTheme) -> str:
    """Put the deck's families on every text node that names one.

    Uniform by construction. A slide keeping the layout's own font while the rest of
    the deck moved is the style drift this module exists to prevent.
    """
    if not svg:
        return svg

    def swap(match: re.Match) -> str:
        current = match.group(1)
        head = current.split(",")[0].strip().strip("'\"")
        if not head:
            return match.group(0)
        # Headings are set in the heading family; everything else takes the body face.
        heavy = "bold" in current.casefold() or "display" in current.casefold()
        family = theme.heading_family if heavy else theme.body_family
        return f'font-family="{family}, sans-serif"'

    return _FONT_FAMILY_ATTR.sub(swap, svg)


def apply(svg: str, theme: DeckTheme, scale: bool = True) -> str:
    """Apply the deck's theme to one slide's markup."""
    themed = apply_fonts(svg, theme)
    if scale and theme.applied_scale < 1.0:
        themed = apply_type_scale(themed, theme.applied_scale)
    return themed


def as_asset_style(theme: DeckTheme, tokens: dict[str, Any] | None = None):
    """The theme, as the Asset Agent needs to see it, so a drawing matches the deck."""
    try:
        from .asset_agent import AssetStyle
    except ImportError:  # pragma: no cover - supports direct task imports
        from asset_agent import AssetStyle  # type: ignore[no-redef]

    tokens = tokens if isinstance(tokens, dict) else {}
    chart = tokens.get("chart") if isinstance(tokens.get("chart"), dict) else {}
    series = chart.get("series") if isinstance(chart.get("series"), dict) else {}
    chrome = tokens.get("chrome") if isinstance(tokens.get("chrome"), dict) else {}
    primary = str(series.get("primary") or theme.palette["primary"])
    accent = str(series.get("accent") or theme.palette["accent"])
    surface = str(
        chart.get("field")
        or chrome.get("surface")
        or theme.palette["secondary_bg"]
    )
    return AssetStyle(
        primary=primary,
        accent=accent,
        surface=surface,
        background=theme.palette["background"],
        body_text=theme.palette["body_text"],
        heading_family=theme.heading_family,
        body_family=theme.body_family,
        label_size=theme.type_scale["body"],
        # Diagram details are body copy, not footnotes. Keeping the caption scale
        # here produced 14px evidence text inside otherwise readable assets.
        detail_size=max(16.0, theme.type_scale["caption"]),
        value_size=theme.type_scale["title"] * 0.9,
        gap=theme.spacing["gutter"],
        corner_radius=float(chrome.get("card_rx") or 12.0),
    )


def as_painter_theme(
    theme: DeckTheme,
    tokens: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Flat theme dict for Intent inject / materialize — pack chrome, no washes."""
    tokens = tokens if isinstance(tokens, dict) else {}
    chrome = tokens.get("chrome") if isinstance(tokens.get("chrome"), dict) else {}
    palette = theme.palette
    return {
        "primary": palette.get("primary") or "#1A365D",
        "accent": palette.get("accent") or "#3182CE",
        "ink": palette.get("body_text") or "#1A202C",
        "muted": palette.get("text_secondary")
        or chrome.get("text_tertiary")
        or "#4A5568",
        "surface": chrome.get("surface")
        or palette.get("secondary_bg")
        or palette.get("background")
        or "#FFFFFF",
        "card": chrome.get("card") or palette.get("background") or "#FFFFFF",
        "border": chrome.get("border") or palette.get("border") or "#E2E8F0",
        "text_tertiary": chrome.get("text_tertiary")
        or palette.get("text_tertiary")
        or "#A0AEC0",
        "font_family": f"{theme.body_family}, sans-serif",
        "title_family": f"{theme.heading_family}, serif",
        "card_rx": float(chrome.get("card_rx") or 12.0),
    }


def as_table_theme(
    theme: DeckTheme,
    tokens: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Theme for table_render_spec / table_renderer."""
    tokens = tokens if isinstance(tokens, dict) else {}
    table = tokens.get("table") if isinstance(tokens.get("table"), dict) else {}
    chrome = tokens.get("chrome") if isinstance(tokens.get("chrome"), dict) else {}
    palette = theme.palette
    return {
        "primary": table.get("header_fill") or palette.get("primary") or "#1A365D",
        "accent": palette.get("accent") or "#3182CE",
        "ink": palette.get("body_text") or "#1A202C",
        "muted": palette.get("text_secondary") or "#4A5568",
        "surface": table.get("surface") or palette.get("background") or "#FFFFFF",
        "zebra": table.get("zebra")
        or chrome.get("accent_tint")
        or palette.get("accent_tint")
        or palette.get("secondary_bg")
        or "#EBF4FF",
        "border": table.get("grid_stroke")
        or chrome.get("border")
        or palette.get("border")
        or "#E2E8F0",
        "header_fill": table.get("header_fill") or palette.get("primary") or "#1A365D",
        "header_color": table.get("header_color") or "#FFFFFF",
        "font": theme.body_family,
        "header_size": float(theme.type_scale.get("caption") or 15),
        "body_size": max(12.0, float(theme.type_scale.get("body") or 13) - 5),
        "preferred_patterns": list(table.get("preferred_patterns") or ["basic_table"]),
    }


def as_formula_theme(
    theme: DeckTheme,
    tokens: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Theme for formula_visual_intent / formula_plate / KaTeX ink."""
    tokens = tokens if isinstance(tokens, dict) else {}
    formula = tokens.get("formula") if isinstance(tokens.get("formula"), dict) else {}
    chrome = tokens.get("chrome") if isinstance(tokens.get("chrome"), dict) else {}
    palette = theme.palette
    ink = formula.get("ink") or palette.get("primary") or "#1A365D"
    return {
        "primary": palette.get("primary") or ink,
        "accent": palette.get("accent") or "#3182CE",
        "ink": ink,
        "body_text": palette.get("body_text") or "#1A202C",
        "muted": formula.get("muted")
        or palette.get("text_secondary")
        or "#4A5568",
        "surface": formula.get("surface")
        or chrome.get("accent_tint")
        or palette.get("accent_tint")
        or palette.get("secondary_bg")
        or "#EBF4FF",
        "stroke": formula.get("stroke") or palette.get("primary") or ink,
        "font_family": f"{theme.heading_family}, serif",
        "body_family": f"{theme.body_family}, sans-serif",
        "layout_hints": list(formula.get("layout_hints") or []),
        "policy": str(formula.get("policy") or ""),
    }


def issues(theme: DeckTheme) -> list[dict]:
    """Everything about a theme that would ship an unreadable deck.

    Empty is the invariant, because ``normalize`` repairs what it can. A finding here
    means something got past it, which is a defect in this module rather than a slide.
    """
    found: list[dict] = []
    background = theme.palette.get("background", "#FFFFFF")
    ratio = contrast_ratio(theme.palette.get("body_text", "#000000"), background)
    if ratio < AA_BODY:
        found.append({
            "slide": "-", "category": "theme-contrast", "severity": "error",
            "detail": f"body text on background is {ratio:.1f}:1, below {AA_BODY}:1",
        })
    for role, size in theme.type_scale.items():
        floor = ROLE_FLOOR_PX.get(role)
        if floor and size < floor:
            found.append({
                "slide": "-", "category": "theme-type-scale", "severity": "error",
                "detail": f"{role} is {size:g}px, below the {floor:g}px floor",
            })
    for role, family in (("heading", theme.heading_family), ("body", theme.body_family)):
        if family not in asset_library.families() and asset_library.families():
            found.append({
                "slide": "-", "category": "theme-font-unavailable", "severity": "error",
                "detail": f"{role} family {family!r} is not in the vendored library",
            })
    return found
