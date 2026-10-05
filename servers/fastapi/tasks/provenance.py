"""Where every word on a slide came from, recorded rather than inferred.

A template contributes fonts, layout and design. Every word inside it is supposed to
be replaced by the user's material, and the previous guard tried to establish that
after the fact: collect every phrase the pack writes anywhere, collect what the slide
was entitled to say, and report any overlap as a leak. Inference cannot settle this.
The pack that motivated the guard was authored from the same paper the user supplied,
so its words and the source's words are the same words -- and Table 1 of the user's
own paper, copied cell for cell out of the evidence bundle, was reported as the pack's
copy and refused. The phrases were identical. Only the provenance differed, and the
provenance was the one thing the guard did not have.

So it is written down at the moment the text is placed. Each rendered text node
carries ``data-sunairum-source``:

``evidence``
    Taken from the user's source document.
``user``
    Supplied by the user directly -- their instructions, presenter name, title.
``design``
    Authored by the template or by us: furniture, page numbers, axis labels, a
    heading whose words carry no claim.

An element with no provenance cannot render. Unreplaced pack copy has no provenance
by construction, so a leak is now a missing stamp rather than a phrase that resembles
one, and no amount of coincidence between the pack and the source can hide it.
"""

from __future__ import annotations

import html
import re
from typing import Iterable

ATTRIBUTE = "data-sunairum-source"

EVIDENCE = "evidence"
USER = "user"
DESIGN = "design"
SOURCES = (EVIDENCE, USER, DESIGN)

_TEXT_NODE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S | re.I)
_SOURCE_ATTR = re.compile(rf'\s*{ATTRIBUTE}="([^"]*)"')
_PLACEHOLDER = re.compile(r"\{\{|\}\}")

# Numbering, bullets and single glyphs. These are furniture wherever they appear, and
# demanding a provenance stamp for a page number would be pedantry rather than a check.
# Bare "Page"/"Slide" labels from designed packs are chrome, not claims.
STRUCTURAL = re.compile(
    r"""^(?:
        [\d\W_]+
        | (?:page|slide)
        | (?:page|slide|step|no|part|chapter|section)\s*[\divxlc]+ (?:\s*(?:/|of)\s*\d+)?
        | [\divxlc]+\s*(?:/|of)\s*\d+
        | [ivxlc]+
        | \w
    )$""",
    re.IGNORECASE | re.VERBOSE,
)


def normalize(source: str | None) -> str:
    """The vocabulary term for a source, or an empty string if it is not one."""
    name = str(source or "").strip().lower()
    return name if name in SOURCES else ""


def stamp(attributes: str, source: str) -> str:
    """Put a provenance on one ``<text>`` tag's attributes, replacing any earlier one."""
    resolved = normalize(source)
    if not resolved:
        raise ValueError(f"{source!r} is not one of {SOURCES}")
    return f'{_SOURCE_ATTR.sub("", attributes or "")} {ATTRIBUTE}="{resolved}"'


def unstamp(attributes: str) -> str:
    """Take any provenance off a tag.

    A slot with nothing in it says nothing, so it owns no source. Leaving a stamp on an
    emptied node would let the next thing to write into it inherit the claim: the repair
    pass that refilled a blanked byline from the model's memory of the paper would have
    arrived pre-attributed to the evidence.
    """
    return _SOURCE_ATTR.sub("", attributes or "")


def stamp_node(node: str, source: str) -> str:
    """Put a provenance on a complete ``<text>`` element."""
    match = _TEXT_NODE.search(node or "")
    if not match:
        return node
    return f"<text{stamp(match.group(1), source)}>{match.group(2)}</text>"


def stamp_document(svg: str, source: str) -> str:
    """Give every text node in a document the same provenance.

    Used where a whole document has one origin: a table materialized from the source,
    or a diagram we authored ourselves.
    """
    resolved = normalize(source)
    if not resolved or not svg:
        return svg
    return _TEXT_NODE.sub(
        lambda match: f"<text{stamp(match.group(1), resolved)}>{match.group(2)}</text>",
        svg,
    )


def source_of(attributes: str) -> str:
    """The provenance declared on a tag, or an empty string."""
    found = _SOURCE_ATTR.search(attributes or "")
    return normalize(found.group(1)) if found else ""


def _plain(body: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return re.sub(r"\s+", " ", value).strip()


def needs_provenance(text: str) -> bool:
    """Whether a run of text is a claim someone has to own.

    Furniture and unfilled placeholders are exempt: the former says nothing, and the
    latter is already reported as a placeholder token.
    """
    value = _plain(text)
    if not value or _PLACEHOLDER.search(value):
        return False
    return not STRUCTURAL.match(value)


def _covering_groups(svg: str) -> list[tuple[int, int]]:
    """Spans of ``<g>`` elements that declare a provenance for everything inside them.

    A group can own its contents. The case that needs this is a native-object carrier:
    a layout draws a sample table so the slot can be seen in a preview, and the
    compiler replaces the whole group with a real table built from its metadata. Those
    sample runs are the design's, and saying so once on the group is something a
    designer can read in the file -- unlike an exemption hidden in this module.
    """
    covering: list[tuple[int, int]] = []
    for match in re.finditer(r"<g\b([^>]*)>", svg or "", re.I):
        if not source_of(match.group(1)):
            continue
        depth, position = 1, match.end()
        for tag in re.finditer(r"<(/?)g\b[^>]*?(/?)>", svg[match.end():], re.I):
            if tag.group(2) == "/":
                continue
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                position = match.end() + tag.end()
                break
        else:
            position = len(svg)
        covering.append((match.start(), position))
    return covering


def unprovenanced(svg: str) -> list[str]:
    """Every run of text on a slide that does not say where it came from.

    Unreplaced template copy lands here, which is what makes the old leak guard
    unnecessary: it is not that the words resemble the pack's, it is that nobody
    claims them.
    """
    covering = _covering_groups(svg)
    missing: list[str] = []
    for match in _TEXT_NODE.finditer(svg or ""):
        if source_of(match.group(1)):
            continue
        if any(start <= match.start() < end for start, end in covering):
            continue
        if needs_provenance(match.group(2)):
            missing.append(_plain(match.group(2)))
    return missing


def census(svg: str) -> dict[str, int]:
    """How many text runs on a slide come from each source."""
    covering = _covering_groups(svg)
    counts = {name: 0 for name in SOURCES}
    counts["unstamped"] = 0
    for match in _TEXT_NODE.finditer(svg or ""):
        source = source_of(match.group(1))
        if not source:
            group = next(
                (span for span in covering if span[0] <= match.start() < span[1]), None,
            )
            if group is not None:
                found = _SOURCE_ATTR.search(svg[group[0]:group[0] + 400])
                source = normalize(found.group(1)) if found else ""
        if source:
            counts[source] += 1
        elif needs_provenance(match.group(2)):
            counts["unstamped"] += 1
    return counts


def slide_issues(svg: str, slide: int | str = "-") -> list[dict]:
    """Blocking findings for text that renders without declaring an origin."""
    missing = unprovenanced(svg)
    if not missing:
        return []
    shown = "; ".join(repr(value[:60]) for value in missing[:6])
    return [{
        "slide": slide,
        "category": "provenance-missing",
        "severity": "error",
        "detail": (
            f"{len(missing)} text run(s) render without a source: {shown}"
        ),
    }]


def deck_issues(slides: Iterable[tuple[int | str, str]]) -> list[dict]:
    """The same check across a deck, given ``(slide number, markup)`` pairs."""
    issues: list[dict] = []
    for slide, svg in slides:
        issues.extend(slide_issues(svg, slide))
    return issues
