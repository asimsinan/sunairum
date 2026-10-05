"""The vendored assets, as generation sees them.

Generation searches the local manifest and nothing else. Three reasons, all of which
are about the deck rather than about tidiness:

A deck built today and rebuilt in a year should use the same bytes, so the type does not
reflow because an upstream shipped a new version of a font in between. The worker already
runs offline for the Docling models and has to keep working that way. And no licence
should ever be accepted by a machine in the middle of producing a deck -- vetting is a
decision a person makes and reviews, which is what the curation tool is for.

So there is no network here, and no fallback that would reach for one. An asset that is
not in the manifest does not exist as far as a deck is concerned.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"

# The weight at and above which the compiler emits ``b="1"``, matching
# ``parse_project_font_weight`` in the compiler's text properties.
BOLD_AT = 600

# A delivered PPTX addresses a face as a typeface name plus a bold and an italic flag, so
# a family has exactly four addressable faces. These are the two upright weights, and the
# library holds only these because a vendored 500 would be a file the engine measures and
# the renderer cannot ask for.
ADDRESSABLE_WEIGHTS = (400, 700)


def renders_as(weight: int) -> int:
    """The weight the delivered deck will actually render for a requested one.

    This is the whole reason the library holds two upright weights rather than five. The
    engine measures the file it resolves; PowerPoint renders the file in the slot. If those
    are different files the widths are fiction on the recipient's machine, which is the
    substitution problem moved to the last step where nothing checks it.
    """
    return 700 if int(weight) >= BOLD_AT else 400


@functools.lru_cache(maxsize=1)
def _manifest() -> dict:
    import json

    try:
        with open(MANIFEST_PATH, encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return {"assets": []}
    return document if isinstance(document, dict) else {"assets": []}


def reload() -> None:
    """Forget the cached manifest. For the curation tool and for tests."""
    _manifest.cache_clear()


def assets(kind: str = "") -> list[dict]:
    """Every vendored asset, optionally of one kind."""
    found = [entry for entry in _manifest().get("assets", []) if isinstance(entry, dict)]
    return [entry for entry in found if not kind or entry.get("kind") == kind]


def families() -> list[str]:
    """The font families available to a theme."""
    return sorted({str(entry.get("family") or "") for entry in assets("font")} - {""})


def font_path(family: str, weight: int = 400, italic: bool = False) -> str:
    """The vendored file for a face, resolved from the manifest rather than fontconfig.

    ``fc-match`` is what this replaces, and the difference matters: fontconfig answers
    with the nearest thing it has installed, so a missing weight silently becomes another
    one and the widths measured at layout time describe a font the renderer never used.
    Here a face either is in the library or is not.
    """
    wanted = str(family or "").strip().casefold()
    # The weight the deck will actually render, not the one it asked for. A request for 599
    # is nearer 700 by arithmetic but renders as regular, so answering with the bold file
    # would measure text the recipient never sees.
    target = renders_as(weight)
    faces = [
        entry for entry in assets("font")
        if str(entry.get("family") or "").casefold() == wanted
        and bool(entry.get("italic")) == bool(italic)
    ]
    if not faces:
        faces = [
            entry for entry in assets("font")
            if str(entry.get("family") or "").casefold() == wanted
        ]
    if not faces:
        return ""
    nearest = min(faces, key=lambda entry: abs(int(entry.get("weight") or 400) - target))
    path = ASSETS_DIR / str(nearest.get("path") or "")
    return str(path) if path.is_file() else ""


def faces(family: str = "") -> list[dict]:
    """The vendored faces, optionally of one family, ordered by weight then slant."""
    wanted = str(family or "").strip().casefold()
    found = [
        entry for entry in assets("font")
        if not wanted or str(entry.get("family") or "").casefold() == wanted
    ]
    return sorted(
        found,
        key=lambda entry: (
            str(entry.get("family") or ""), int(entry.get("weight") or 400),
            bool(entry.get("italic")),
        ),
    )


def roles() -> dict[str, list[str]]:
    """Which families serve which role, so a theme picks a role rather than a font name."""
    grouped: dict[str, set[str]] = {}
    for entry in assets("font"):
        role = str(entry.get("role") or "").strip()
        family = str(entry.get("family") or "").strip()
        if role and family:
            grouped.setdefault(role, set()).add(family)
    return {role: sorted(families) for role, families in sorted(grouped.items())}


def family_for_role(role: str) -> str:
    """One family for a role, or empty. No fallback to a family serving another role."""
    return (roles().get(str(role or "").strip()) or [""])[0]


def unaddressable_faces() -> list[str]:
    """Faces the engine could measure but a delivered deck could never ask for.

    Empty is the invariant. A non-empty answer means the library drifted from what PowerPoint
    can address, and every width measured for those faces is wrong at delivery.
    """
    problems = []
    for entry in assets("font"):
        weight = int(entry.get("weight") or 400)
        if weight not in ADDRESSABLE_WEIGHTS:
            problems.append(
                f"{entry.get('name')}: weight {weight} has its own file, but a deck asking "
                f"for it would be rendered with {renders_as(weight)}"
            )
    return problems


def exact_font_path(family: str, weight: int = 400, italic: bool = False) -> str:
    """The vendored file for exactly this face, or empty. Never a near miss.

    ``font_path`` deliberately answers with the nearest weight, which is right for layout:
    a theme asking for 500 should be measured against the file that will render it. This is
    for embedding, where a near miss is a different thing entirely -- putting the upright
    file in the italic slot delivers roman text where the deck asked for italic.
    """
    wanted = str(family or "").strip().casefold()
    for entry in assets("font"):
        if str(entry.get("family") or "").casefold() != wanted:
            continue
        if int(entry.get("weight") or 400) != int(weight):
            continue
        if bool(entry.get("italic")) != bool(italic):
            continue
        path = ASSETS_DIR / str(entry.get("path") or "")
        if path.is_file():
            return str(path)
    return ""


def embeddable_fonts() -> list[str]:
    """Vendored font files that may be embedded into ``ppt/fonts/``.

    The delivery check looks for that directory, and a recipient's PowerPoint renders the
    metrics we measured only if the font travels with the deck.
    """
    found = []
    for entry in assets("font"):
        if not entry.get("embeddable"):
            continue
        path = ASSETS_DIR / str(entry.get("path") or "")
        if path.is_file():
            found.append(str(path))
    return found


def _filesystem_tabler_icons() -> list[dict]:
    """Curated tabler-outline SVGs under assets/icons/tabler-outline (one primary lib)."""
    root = ASSETS_DIR / "icons" / "tabler-outline"
    if not root.is_dir():
        return []
    found: list[dict] = []
    for path in sorted(root.glob("*.svg")):
        name = path.stem
        found.append(
            {
                "kind": "icon",
                "name": name,
                "path": str(path.relative_to(ASSETS_DIR)),
                "library": "tabler-outline",
                "keywords": [name.replace("-", " "), *name.split("-")],
                "categories": ["tabler-outline"],
                "license_spdx": "MIT",
            }
        )
    return found


def find_icons(*terms: str, limit: int = 8) -> list[dict]:
    """Icons matching what the caller means, best first.

    Searched by keyword and category rather than filename, because the caller knows what
    the icon is for and not what the set decided to call it.
    """
    wanted = [str(term or "").strip().casefold() for term in terms if str(term or "").strip()]
    if not wanted:
        return []
    scored: list[tuple[int, str, dict]] = []
    pool = list(assets("icon")) + _filesystem_tabler_icons()
    seen: set[str] = set()
    for entry in pool:
        name = str(entry.get("name") or "").casefold()
        if name in seen:
            continue
        seen.add(name)
        haystack = {
            *(str(word).casefold() for word in entry.get("keywords") or []),
            *(str(word).casefold() for word in entry.get("categories") or []),
            name,
        }
        score = sum(
            2 if term in haystack else 1 if any(term in word for word in haystack) else 0
            for term in wanted
        )
        if score:
            scored.append((-score, str(entry.get("name") or ""), entry))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [entry for _score, _name, entry in scored[:limit]]


def icon_markup(name: str) -> str:
    """One icon's normalized markup, or an empty string if the library has no such icon."""
    wanted = str(name or "").casefold()
    for entry in list(assets("icon")) + _filesystem_tabler_icons():
        if str(entry.get("name") or "").casefold() != wanted:
            continue
        path = ASSETS_DIR / str(entry.get("path") or "")
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def licenses() -> dict[str, list[str]]:
    """Which assets are under which licence, for the notices a delivered deck needs."""
    grouped: dict[str, list[str]] = {}
    for entry in assets():
        spdx = str(entry.get("license_spdx") or "unknown")
        grouped.setdefault(spdx, []).append(str(entry.get("name") or ""))
    return {spdx: sorted(names) for spdx, names in sorted(grouped.items())}


def is_available(kind: str = "") -> bool:
    """Whether the library has anything of a kind. Nothing here falls back to a network."""
    return bool(assets(kind))


def relative_to_assets(path: str | os.PathLike[str]) -> str:
    """A vendored path expressed relative to the assets directory."""
    try:
        return str(Path(path).resolve().relative_to(ASSETS_DIR.resolve()))
    except ValueError:
        return str(path)
