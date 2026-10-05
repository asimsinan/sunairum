"""One font policy for the whole pipeline: only ship what we can embed.

A deck is measured three times — Chromium for the previews and layout QA,
LibreOffice for the PDF, PowerPoint on the reader's machine — and every stage
must resolve the same glyphs or the line breaks move.  Naming ``Arial`` breaks
that: the container has no Arial, so fontconfig aliases it to Source Sans 3 and
Chromium measures Source Sans 3; the PPTX still says ``Arial``, and PowerPoint
prefers the reader's *installed* Arial over any face we embed under that name.
Different widths, different wraps — text drifts out of the boxes we measured and
lands on top of its neighbours.

So the authored CSS may only name families we ship as files.  Those are not
installed on a typical machine, which is the point: nothing can shadow them, the
embedded face wins, and PowerPoint reproduces Chromium's layout exactly.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

#: Families shipped in ``assets/fonts`` (and copied into the image font dir).
#: ``deckhtml``'s embedder resolves each of these to a real file, so a slide that
#: names only these is fully self-contained in the exported PPTX.
SANS_FAMILY = "Source Sans 3"
SERIF_FAMILY = "Source Serif 4"
MONO_FAMILY = "Liberation Mono"
CONDENSED_FAMILY = "Barlow Condensed"

EMBEDDABLE_FAMILIES: frozenset[str] = frozenset(
    {SANS_FAMILY, SERIF_FAMILY, MONO_FAMILY, CONDENSED_FAMILY, "Inter"}
)

#: Office and system faces authors reach for, mapped to the shipped equivalent.
_SUBSTITUTIONS: dict[str, str] = {
    # sans
    "arial": SANS_FAMILY,
    "arial narrow": CONDENSED_FAMILY,
    "helvetica": SANS_FAMILY,
    "helvetica neue": SANS_FAMILY,
    "calibri": SANS_FAMILY,
    "segoe ui": SANS_FAMILY,
    "verdana": SANS_FAMILY,
    "tahoma": SANS_FAMILY,
    "roboto": SANS_FAMILY,
    "open sans": SANS_FAMILY,
    "lato": SANS_FAMILY,
    "noto sans": SANS_FAMILY,
    "liberation sans": SANS_FAMILY,
    "source sans pro": SANS_FAMILY,
    "-apple-system": SANS_FAMILY,
    "blinkmacsystemfont": SANS_FAMILY,
    "system-ui": SANS_FAMILY,
    "ui-sans-serif": SANS_FAMILY,
    # serif
    "georgia": SERIF_FAMILY,
    "cambria": SERIF_FAMILY,
    "times": SERIF_FAMILY,
    "times new roman": SERIF_FAMILY,
    "garamond": SERIF_FAMILY,
    "palatino": SERIF_FAMILY,
    "book antiqua": SERIF_FAMILY,
    "liberation serif": SERIF_FAMILY,
    "source serif pro": SERIF_FAMILY,
    "ui-serif": SERIF_FAMILY,
    # mono
    "consolas": MONO_FAMILY,
    "courier": MONO_FAMILY,
    "courier new": MONO_FAMILY,
    "menlo": MONO_FAMILY,
    "monaco": MONO_FAMILY,
    "sf mono": MONO_FAMILY,
    "dejavu sans mono": MONO_FAMILY,
    "jetbrains mono": MONO_FAMILY,
    "source code pro": MONO_FAMILY,
    "ui-monospace": MONO_FAMILY,
    # condensed display
    "oswald": CONDENSED_FAMILY,
    "roboto condensed": CONDENSED_FAMILY,
}

#: CSS generic keywords, kept as the trailing fallback in a rewritten stack.
_GENERICS: dict[str, str] = {
    "serif": SERIF_FAMILY,
    "sans-serif": SANS_FAMILY,
    "monospace": MONO_FAMILY,
    "cursive": SERIF_FAMILY,
    "fantasy": SANS_FAMILY,
    "system-ui": SANS_FAMILY,
    "ui-sans-serif": SANS_FAMILY,
    "ui-serif": SERIF_FAMILY,
    "ui-monospace": MONO_FAMILY,
    "ui-rounded": SANS_FAMILY,
    "math": SERIF_FAMILY,
    "emoji": SANS_FAMILY,
    "fangsong": SERIF_FAMILY,
}

#: File slug each shipped family is stored under in the font directory.
_FAMILY_SLUG: dict[str, str] = {
    SANS_FAMILY: "source-sans-3",
    SERIF_FAMILY: "source-serif-4",
    MONO_FAMILY: "liberation-mono",
    CONDENSED_FAMILY: "barlow-condensed",
    "Inter": "inter",
}


def _font_dirs() -> list[Path]:
    dirs: list[Path] = []
    for raw in (os.environ.get("DECKHTML_FONTS_DIR"), os.environ.get("SUNAIRUM_FONTS_DIR")):
        if raw and Path(raw).is_dir():
            dirs.append(Path(raw))
    bundled = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    if bundled.is_dir():
        dirs.append(bundled)
    return dirs


@lru_cache(maxsize=1)
def available_families() -> frozenset[str]:
    """Shipped families whose files are actually present in this environment.

    Naming a family we cannot embed is the failure this module exists to
    prevent, and one of them — Liberation Mono — is staged by the image build
    rather than committed, so its presence is a property of the environment and
    has to be checked, not assumed.
    """
    found = set()
    dirs = _font_dirs()
    for family, slug in _FAMILY_SLUG.items():
        for directory in dirs:
            if any(directory.glob(f"{slug}*.ttf")) or any(directory.glob(f"{slug}*.otf")):
                found.add(family)
                break
    return frozenset(found) or EMBEDDABLE_FAMILIES


def _embeddable(family: str) -> str:
    """Return `family` if we can embed it here, else the nearest face we can.

    A missing face degrades to one we ship rather than to the reader's guess:
    code set in the body sans is a cosmetic loss, code the reader's renderer
    re-measures is text landing on top of its neighbour.
    """
    usable = available_families()
    if family in usable:
        return family
    for fallback in (SANS_FAMILY, SERIF_FAMILY, "Inter"):
        if fallback in usable:
            return fallback
    return SANS_FAMILY


_QUOTED = re.compile(r"""^\s*(['"])(?P<name>.*?)\1\s*$""")


def _clean(token: str) -> str:
    match = _QUOTED.match(token)
    return (match.group("name") if match else token).strip()


def _quote(family: str) -> str:
    return f"'{family}'" if " " in family else family


def resolve_family(name: str) -> str:
    """Return the shipped family a requested face maps to, if we can embed it."""
    cleaned = _clean(name)
    if cleaned in EMBEDDABLE_FAMILIES:
        return _embeddable(cleaned)
    key = cleaned.casefold()
    for table in (_SUBSTITUTIONS, _GENERICS):
        if key in table:
            return _embeddable(table[key])
    return ""


def normalize_font_stack(stack: str) -> str:
    """Rewrite a CSS font-family list so every named face is one we ship.

    The generic keyword the author ended the stack with decides what an unknown
    face becomes, so a display face in a serif stack stays a serif.  The generic
    itself is preserved as the last resort.
    """
    tokens = [token for token in (part.strip() for part in stack.split(",")) if token]
    if not tokens:
        return stack
    generic = ""
    for token in reversed(tokens):
        if _clean(token).casefold() in _GENERICS:
            generic = _clean(token).casefold()
            break
    default = _embeddable(_GENERICS.get(generic, SANS_FAMILY))

    primary = ""
    for token in tokens:
        cleaned = _clean(token)
        if not cleaned or cleaned.casefold() in _GENERICS:
            continue
        primary = resolve_family(cleaned) or default
        break
    if not primary:
        primary = default

    out = [_quote(primary)]
    if generic:
        out.append(generic)
    elif primary != default:
        out.append(_quote(default))
    return ", ".join(out)
