"""Which of a template pack's images are design, and which are its old subject.

Selecting a template is meant to contribute fonts, design and layout, with the user's
source supplying every word and figure inside it. The image copy step used to sort a
pack's assets by whether its own SVGs referenced them, on the reasoning that an
unreferenced file was leftover demo photography. In an authored pack that axis is
exactly wrong: the referenced images *are* the previous deck's figures. Choosing the
Attention pack therefore copied ``attention_p3_0.png``, ``transformer_family.png`` and
nine more of that paper's diagrams into the project's shared image directory, where
figure fallback and blank-image regeneration could reach them and put another paper's
diagrams in front of the user.

The axis that matters is decorative versus subject: ``paper_texture.jpg`` and
``logo.png`` are design and travel with the template; ``attention_p3_0.png`` is
content and must not. Gallery packs often name a *themed* title plate
``cover_bg.png`` (e.g. a Transformer blueprint). That filename looks decorative
but depicts the pack's original subject, so ``cover``/``hero`` together with a
surface token (``bg``) is treated as subject unless the pack declares
``design`` in ``asset_roles.json``. Unrecognised names stay behind — a missing
background is obvious; a stranger's figure as the user's own is not.
"""

from __future__ import annotations

import json
import os
import re

DESIGN = "design"
SUBJECT = "subject"

# Words that name a piece of the design itself rather than something the deck is
# about. Matched against name tokens, never as substrings, so ``background.png`` is
# design while ``foreground_industry.png`` is not caught by "ground".
_DESIGN_TOKENS = frozenset(
    {
        # Surfaces the content is laid on.
        "bg",
        "background",
        "backdrop",
        "canvas",
        # Identity marks.
        "logo",
        "logos",
        "emblem",
        "brand",
        "branding",
        "wordmark",
        "watermark",
        "crest",
        # Surface treatments.
        "texture",
        "textures",
        "pattern",
        "gradient",
        "grain",
        "noise",
        # Ornament and framing.
        "ornament",
        "decoration",
        "decor",
        "frame",
        "border",
        "divider",
        "rule",
        "ribbon",
        "accent",
        "swatch",
        "mask",
        "overlay",
        "flourish",
        "icon",
        "icons",
        "bullet",
        "glyph",
        # Shapes recovered from a converted PowerPoint: vector furniture, not photos.
        "freeform",
        "shape",
        # Slots a pack ships empty, meant to be replaced by real content.
        "placeholder",
        "replaceable",
        # The pack's own preview tile, never slide content.
        "thumbnail",
        "thumb",
        "preview",
    }
)

# Words that name where an image sits rather than what it depicts. On their own they
# settle nothing, so they count as design only when the name says nothing else and the
# pack draws the asset edge to edge behind its content. Both halves are needed:
# ``cover_hero.png`` is a backdrop, ``first_paper.png`` is a figure inset into a
# 374x444 panel, and ``cover_hermes.jpg`` is full-bleed but names a subject, so the
# leftover word "hermes" keeps it out.
_BACKDROP_TOKENS = frozenset(
    {
        "cover",
        "hero",
        "atmosphere",
        "backdrop",
        "splash",
        "opening",
        "closing",
        "title",
    }
)

_SEPARATORS = re.compile(r"[^0-9A-Za-z\u00c0-\uffff]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# Bookkeeping fragments that say nothing about what an image is: slide indices such as
# ``p01`` or ``s3``, export counters, and content hashes.
_NOISE = re.compile(r"^(?:[a-z]?\d+|[0-9a-f]{8,}|img|image|final|copy|v\d+)$")


def _content_words(tokens: set[str]) -> set[str]:
    """The words in a name that describe a subject, if any survive."""
    return {
        token
        for token in tokens - _DESIGN_TOKENS - _BACKDROP_TOKENS
        if not _NOISE.match(token)
    }


def name_tokens(name: str) -> set[str]:
    """The words in an asset's filename, lowercased.

    Directory and extension are dropped, separators split, and camel case broken up so
    ``coverBg.png``, ``cover-bg.png`` and ``cover_bg.png`` are read the same way.
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    parts: list[str] = []
    for chunk in _SEPARATORS.split(stem):
        if chunk:
            parts.extend(piece for piece in _CAMEL.split(chunk) if piece)
    return {part.casefold() for part in parts}


def declared_roles(images_dir: str | None) -> dict[str, str]:
    """Roles a pack states for its own assets, if it states any.

    A pack may ship ``images/asset_roles.json`` mapping a filename to ``design`` or
    ``subject``. It exists so a designer can keep a background whose name carries no
    decorative word, and so a review of what a pack contributes has somewhere to live.
    """
    if not images_dir:
        return {}
    path = os.path.join(images_dir, "asset_roles.json")
    try:
        with open(path, encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # Accept either a flat mapping or one nested under "assets".
    entries = raw.get("assets") if isinstance(raw.get("assets"), dict) else raw
    roles: dict[str, str] = {}
    for name, role in entries.items():
        if not isinstance(name, str) or not isinstance(role, str):
            continue
        normalized = role.strip().casefold()
        if normalized in {DESIGN, SUBJECT}:
            roles[name.lstrip("./")] = normalized
    return roles


_IMAGE_TAG = re.compile(r"<image\b[^>]*>", re.IGNORECASE)
_ATTRIBUTE = re.compile(r'([\w:.-]+)\s*=\s*"([^"]*)"')
_VIEW_BOX = re.compile(r'\bviewBox\s*=\s*"([^"]*)"', re.IGNORECASE)
# How much of the canvas an image must cover, and how far from the corner it may
# start, to count as drawn behind the content rather than placed within it.
_FULL_BLEED_COVERAGE = 0.9
_FULL_BLEED_ORIGIN = 0.05


def _canvas_size(markup: str) -> tuple[float, float]:
    found = _VIEW_BOX.search(markup)
    if found:
        numbers = [float(value) for value in re.findall(r"[-+]?[\d.]+", found.group(1))]
        if len(numbers) >= 4 and numbers[2] > 0 and numbers[3] > 0:
            return numbers[2], numbers[3]
    return 1280.0, 720.0


def full_bleed_assets(markups) -> set[str]:
    """Assets a pack draws edge to edge, from the pack's own slide markup."""
    names: set[str] = set()
    for markup in markups:
        canvas_width, canvas_height = _canvas_size(markup)
        for tag in _IMAGE_TAG.findall(markup):
            attributes = dict(_ATTRIBUTE.findall(tag))
            href = attributes.get("href") or attributes.get("xlink:href") or ""
            if not href or href.startswith(("data:", "#", "http:", "https:")):
                continue
            try:
                x = float(attributes.get("x", "0") or 0)
                y = float(attributes.get("y", "0") or 0)
                width = float(attributes.get("width", "0") or 0)
                height = float(attributes.get("height", "0") or 0)
            except ValueError:
                continue
            if width < canvas_width * _FULL_BLEED_COVERAGE:
                continue
            if height < canvas_height * _FULL_BLEED_COVERAGE:
                continue
            if abs(x) > canvas_width * _FULL_BLEED_ORIGIN:
                continue
            if abs(y) > canvas_height * _FULL_BLEED_ORIGIN:
                continue
            names.add(href.split("images/", 1)[-1].lstrip("./"))
    return names


def classify_asset(
    name: str,
    declared: dict[str, str] | None = None,
    full_bleed: set[str] | frozenset[str] = frozenset(),
) -> str:
    """Whether one asset belongs to the design or to the pack's former subject."""
    key = name.lstrip("./")
    if declared:
        stated = declared.get(key) or declared.get(os.path.basename(key))
        if stated:
            return stated
    tokens = name_tokens(key)
    # cover_bg / hero_background: themed title plates, not transferable chrome.
    # Packs that truly ship an abstract surface must declare design explicitly.
    if tokens & _BACKDROP_TOKENS and tokens & _DESIGN_TOKENS:
        return SUBJECT
    if tokens & _DESIGN_TOKENS:
        return DESIGN
    if (
        tokens & _BACKDROP_TOKENS
        and not _content_words(tokens)
        and (key in full_bleed or os.path.basename(key) in full_bleed)
    ):
        return DESIGN
    return SUBJECT


def classify_assets(
    names,
    images_dir: str | None = None,
    full_bleed: set[str] | frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Classify a pack's assets, honouring any roles the pack declares."""
    declared = declared_roles(images_dir)
    return {name: classify_asset(name, declared, full_bleed) for name in names}


def design_assets(
    names,
    images_dir: str | None = None,
    full_bleed: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    """Just the assets that travel with the template, in a stable order."""
    roles = classify_assets(names, images_dir, full_bleed)
    return sorted(name for name, role in roles.items() if role == DESIGN)
