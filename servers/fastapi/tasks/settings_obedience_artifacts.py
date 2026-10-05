"""Reconcile Production Settings delivery with canonical slide artifacts.

Placement events are transient pipeline telemetry.  HTML is the durable source
of truth, so late semantic-host injection and resumed generations must be
credited from the final slide documents as well.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any


_ATTR_RE = re.compile(
    r"([:\w-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')",
    flags=re.I,
)


def _attrs(tag: str) -> dict[str, str]:
    return {
        name.casefold(): double if double != "" else single
        for name, double, single in _ATTR_RE.findall(tag or "")
    }


def delivered_asset_ids_from_html(document: str) -> tuple[set[str], set[str]]:
    """Return exact, materially filled figure/table IDs in one HTML document."""
    figures: set[str] = set()
    tables: set[str] = set()
    # Prefer the ID carried by the actual image.  A non-empty src proves the
    # semantic host is filled rather than merely reserved.
    for tag in re.findall(r"<img\b[^>]*>", document or "", flags=re.I | re.S):
        attrs = _attrs(tag)
        figure_id = str(attrs.get("data-sunairum-figure-id") or "").strip()
        src = str(attrs.get("src") or "").strip()
        if figure_id and src:
            figures.add(figure_id)

    # Native table metadata survives HTML authoring and is more reliable than
    # matching visible cell text.
    for tag in re.findall(
        r"<(?:table|div|section)\b[^>]*>", document or "", flags=re.I | re.S
    ):
        attrs = _attrs(tag)
        table_id = str(
            attrs.get("data-sunairum-table-id")
            or attrs.get("data-table-id")
            or ""
        ).strip()
        if table_id and (
            attrs.get("data-pptx", "").casefold() == "table"
            or tag.lstrip().lower().startswith("<table")
        ):
            tables.add(table_id)

    return figures, tables


def delivered_asset_ids(project_dir: str | Path) -> tuple[set[str], set[str]]:
    """Return exact figure/table IDs materialized in final HTML slides."""
    html_dir = Path(project_dir) / "html_output"
    figures: set[str] = set()
    tables: set[str] = set()
    if not html_dir.is_dir():
        return figures, tables
    for path in sorted(html_dir.glob("slide_*.html")):
        try:
            document = path.read_text(encoding="utf-8")
        except OSError:
            continue
        slide_figures, slide_tables = delivered_asset_ids_from_html(document)
        figures.update(slide_figures)
        tables.update(slide_tables)
    return figures, tables


#: Function words that are common in one language and rare in the others we
#: name. Content words are useless here — a Turkish deck about vehicle routing
#: is full of English technical nouns — but function words are not borrowed.
_LANGUAGE_MARKERS: dict[str, frozenset[str]] = {
    "en": frozenset({
        "the", "and", "of", "for", "with", "from", "that", "this", "which",
        "while", "when", "into", "than", "each", "both", "must", "does", "are",
    }),
    "tr": frozenset({
        "ve", "ile", "için", "bir", "bu", "da", "de", "olarak", "daha", "gibi",
        "ancak", "hem", "her", "veya", "ise", "göre", "kadar", "üzerinde",
    }),
    "de": frozenset({
        "und", "der", "die", "das", "mit", "für", "von", "nicht", "auch",
        "aber", "wenn", "durch", "bei", "eine", "einen", "wird",
    }),
    "fr": frozenset({
        "et", "le", "la", "les", "des", "pour", "avec", "dans", "que", "qui",
        "sur", "une", "aux", "par", "plus", "sont",
    }),
    "es": frozenset({
        "y", "el", "la", "los", "las", "para", "con", "que", "una", "por",
        "del", "como", "más", "pero", "son",
    }),
    "it": frozenset({
        "e", "il", "la", "le", "dei", "per", "con", "che", "una", "del",
        "come", "più", "sono", "nella",
    }),
    "pt": frozenset({
        "e", "o", "a", "os", "as", "para", "com", "que", "uma", "dos", "como",
        "mais", "são", "pelo",
    }),
    "nl": frozenset({
        "en", "de", "het", "van", "voor", "met", "dat", "die", "een", "niet",
        "ook", "maar", "wordt",
    }),
}

#: Below this many function words a fragment is a label or a caption, and word
#: frequency says nothing about its language.
_LANGUAGE_MIN_MARKERS = 4

#: Characters that a run of real prose in this language almost always contains
#: and that English never does. This is what makes a *short* slide judgeable: a
#: cover has too few function words to count, but a Turkish title without a
#: single ı/ş/ğ/ç/ö/ü is not Turkish. Only languages whose orthography carries
#: a reliable mark are listed; English deliberately has no entry.
_LANGUAGE_DIACRITICS: dict[str, str] = {
    "tr": "ıİşŞğĞçÇöÖüÜâÂîÎûÛ",
    "de": "äÄöÖüÜß",
    "fr": "àâçéèêëîïôùûüÿœæÀÂÇÉÈÊËÎÏÔÙÛÜŸŒÆ",
    "es": "áéíóúüñÁÉÍÓÚÜÑ¿¡",
    "pt": "ãâáàçéêíóôõúÃÂÁÀÇÉÊÍÓÔÕÚ",
    "pl": "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
    "ru": "абвгдежзийклмнопрстуфхцчшщъыьэюя",
    "ar": "ابتثجحخدذرزسشصضطظعغفقكلمنهوي",
    "zh": "的一是不了在人有我他这中大为上个国",
    "ja": "のにはをがでとしてある",
    "ko": "이가은는을를에서하고",
}

#: A fragment needs at least this many words before its lack of the deck
#: language's characters means anything. A three-word kicker proves nothing.
_LANGUAGE_MIN_WORDS_FOR_SCRIPT = 6

_TEXT_FRAGMENT_RE = re.compile(r">([^<>]+)<")


def visible_text_fragments(document: str) -> list[str]:
    """Each run of visible text in the document, as its own fragment.

    Whole-slide text is the wrong unit for a cover: the presenter's name and
    country supply the deck language's characters ("Doç. Dr. Asım …, Türkiye")
    while the title beside them is still the paper's English. Judging each run
    separately isolates the offending string and names it in the report.
    """
    body = document[document.find("<body") :] if "<body" in document else document
    body = re.sub(r"<(script|style)\b.*?</\1>", "><", body, flags=re.S | re.I)
    fragments: list[str] = []
    for raw in _TEXT_FRAGMENT_RE.findall(body):
        fragment = re.sub(r"\s+", " ", raw).strip()
        if fragment:
            fragments.append(fragment)
    return fragments

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _is_quoted(fragment: str, quoted: set[str]) -> bool:
    """True when this fragment is one of the strings the deck cites verbatim.

    Matched in both directions: the cover renders the title as its own fragment,
    but a byline can also carry several quoted fields in one line.
    """
    if not quoted:
        return False
    needle = _normalize_for_quote(fragment)
    if not needle:
        return False
    return any(needle in value or value in needle for value in quoted)


def _marker_counts(text: str) -> dict[str, int]:
    words = [word.casefold() for word in _WORD_RE.findall(text or "")]
    return {
        code: sum(1 for word in words if word in markers)
        for code, markers in _LANGUAGE_MARKERS.items()
    }


def detect_copy_language(text: str, candidates: Iterable[str]) -> tuple[str, int]:
    """Best-guess language of a block of deck copy, with its evidence count.

    Returns ``("", 0)`` when the text carries too few function words to judge —
    a kicker or an axis label never will, and guessing on those produces noise.
    """
    words = [word.casefold() for word in _WORD_RE.findall(text or "")]
    if not words:
        return "", 0
    scores: dict[str, int] = {}
    for code in candidates:
        markers = _LANGUAGE_MARKERS.get(code)
        if not markers:
            continue
        scores[code] = sum(1 for word in words if word in markers)
    if not scores:
        return "", 0
    best = max(scores, key=lambda code: scores[code])
    if scores[best] < _LANGUAGE_MIN_MARKERS:
        return "", 0
    runner_up = max((v for k, v in scores.items() if k != best), default=0)
    # A decisive lead only; mixed technical prose should not be adjudicated.
    if scores[best] < runner_up * 2:
        return "", 0
    return best, scores[best]


#: Cover fields that are cited rather than written, so they carry the source's
#: language and not the deck's. A paper's title is how the work is found: a
#: translated one exists nowhere and cannot be looked up.
_QUOTED_IDENTITY_FIELDS = ("TITLE", "AUTHORS", "AFFILIATIONS", "SUBTITLE")


def quoted_identity_raw(project_dir: str | Path) -> set[str]:
    """Strings the deck quotes from the source, as written."""
    plan_path = Path(project_dir) / "validation" / "grounded_plan.json"
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    quoted: set[str] = set()
    for slide in plan.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        role = str((slide.get("visual_plan") or {}).get("archetype") or "").casefold()
        if role not in {"hero", "title", "closing"}:
            continue
        content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
        for field in _QUOTED_IDENTITY_FIELDS:
            value = str(content.get(field) or "").strip()
            if value:
                quoted.add(value)
    return quoted


def _normalize_for_quote(value: str) -> str:
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE).casefold()


def off_language_fragments(
    html: str,
    primary_language: str,
    quoted: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Visible strings in `html` that are not in `primary_language`.

    One implementation for two callers: the authoring loop uses it as a contract
    check while a retry can still fix the slide, and the obedience report uses
    it on the delivered deck. They must agree, or the report contradicts the
    gate that was supposed to prevent it.

    Judged per fragment, because whole-slide text hides the case that matters: a
    cover's byline supplies the language's own characters ("Doç. Dr. Asım …,
    Türkiye") while the title beside it is still the source's English. Quoted
    identity is exempt — it is cited, not written.
    """
    code = str(primary_language or "").strip().casefold().split("-")[0]
    alphabet = _LANGUAGE_DIACRITICS.get(code)
    if not alphabet or not html:
        return []
    cited = {_normalize_for_quote(value) for value in quoted if str(value or "").strip()}
    cited.discard("")

    found: list[dict[str, Any]] = []
    for fragment in visible_text_fragments(html):
        words = _WORD_RE.findall(fragment)
        if len(words) < _LANGUAGE_MIN_WORDS_FOR_SCRIPT:
            continue
        needle = _normalize_for_quote(fragment)
        if needle and any(needle in value or value in needle for value in cited):
            continue
        marks = _marker_counts(fragment)
        if marks.get(code, 0):
            continue
        if any(character in alphabet for character in fragment):
            continue
        other = {lang: count for lang, count in marks.items() if lang != code and count}
        if not other:
            continue
        leader = max(other, key=lambda lang: other[lang])
        found.append({
            "expected": code,
            "detected": leader,
            "markers": other[leader],
            "words": len(words),
            "sample": fragment[:160],
            "basis": "no_language_characters",
        })
    return found


def language_obedience(
    project_dir: str | Path,
    primary_language: str,
) -> dict[str, Any]:
    """Report slides whose visible copy is not in the language the user chose.

    The deck language is confirmed once and then has to survive two LLM stages.
    When it does not the failure is invisible to every geometry gate — the slide
    is beautifully laid out, in the wrong language — so it is checked here,
    against the delivered HTML, the way the audience will read it.
    """
    code = str(primary_language or "").strip().casefold().split("-")[0]
    if code not in _LANGUAGE_MARKERS:
        return {"ok": True, "skipped": "language_not_profiled", "language": code}

    quoted_raw = quoted_identity_raw(project_dir)
    html_dir = Path(project_dir) / "html_output"
    copy: list[tuple[str, str, list[str]]] = []
    for path in sorted(html_dir.glob("slide_*.html")):
        try:
            document = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fragments = visible_text_fragments(document)
        copy.append((path.stem, " ".join(fragments), fragments))

    findings: list[dict[str, Any]] = []
    judged = 0
    for stem, text, fragments in copy:
        detected, evidence = detect_copy_language(text, _LANGUAGE_MARKERS)
        if detected:
            judged += 1
            if detected != code:
                findings.append({
                    "slide": stem,
                    "expected": code,
                    "detected": detected,
                    "markers": evidence,
                    "sample": text[:160],
                    "basis": "word_frequency",
                })
            continue
        # A cover or a section divider carries too few function words to judge
        # on frequency — which is exactly where the wrong language hid: the deck
        # read Turkish throughout while P01 kept the paper's English title. Fall
        # back to orthography, which needs far less text: prose in this language
        # would carry its own characters, and this slide carries none of them
        # while carrying another language's function words.
        for item in off_language_fragments("".join(
            "<p>%s</p>" % fragment for fragment in fragments
        ), code, quoted=quoted_raw):
            findings.append({"slide": stem, **item})
            break
    return {
        "ok": not findings,
        "language": code,
        "slides_judged": judged,
        "slides_seen": len(copy),
        "off_language_slides": findings,
    }


def reconcile_settings_obedience(
    report: dict[str, Any] | None,
    project_dir: str | Path,
    primary_language: str = "",
) -> dict[str, Any]:
    """Recompute missing assets using events plus canonical HTML evidence."""
    if not isinstance(report, dict):
        return {}
    reconciled = dict(report)
    artifact_figures, artifact_tables = delivered_asset_ids(project_dir)
    placed_figures = {
        str(value).strip()
        for value in reconciled.get("placed_figure_ids") or []
        if str(value).strip()
    } | artifact_figures
    placed_tables = {
        str(value).strip()
        for value in reconciled.get("placed_table_ids") or []
        if str(value).strip()
    } | artifact_tables
    selected_figures = [
        str(value).strip()
        for value in reconciled.get("selected_figure_ids") or []
        if str(value).strip()
    ]
    selected_tables = [
        str(value).strip()
        for value in reconciled.get("selected_table_ids") or []
        if str(value).strip()
    ]
    reconciled["placed_figure_ids"] = sorted(placed_figures)
    reconciled["placed_table_ids"] = sorted(placed_tables)
    reconciled["missing_figure_ids"] = [
        value for value in selected_figures if value not in placed_figures
    ]
    reconciled["missing_table_ids"] = [
        value for value in selected_tables if value not in placed_tables
    ]
    speaker = reconciled.get("speaker_notes")
    notes_ok = not isinstance(speaker, dict) or speaker.get("budget_ok") is not False
    language = str(primary_language or reconciled.get("primary_language") or "")
    if language:
        reconciled["language"] = language_obedience(project_dir, language)
    language_ok = bool(reconciled.get("language", {}).get("ok", True))
    reconciled["ok"] = bool(
        not reconciled["missing_figure_ids"]
        and not reconciled["missing_table_ids"]
        and notes_ok
        and language_ok
    )
    reconciled["artifact_reconciliation"] = {
        "figure_ids": sorted(artifact_figures),
        "table_ids": sorted(artifact_tables),
    }
    return reconciled
