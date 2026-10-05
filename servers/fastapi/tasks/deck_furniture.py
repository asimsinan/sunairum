"""Facts the user supplies about the talk, which the source could never support.

A user who writes "sunucu Asım" or "presented by Ada Lovelace" is stating a fact
about the presentation, not a claim about the paper. In ``pdf_strict`` every
piece of on-slide text used to need PDF evidence, so free-text presenter names
were rejected even when the model had seen them in author directions.

Deck furniture is the structured form of those talk facts -- presenter,
affiliation, date, occasion -- extracted **by the LLM** from free-text
``additional_instructions``. Nothing here invents a name or institution: empty
means the user did not state it. Downstream prompts also receive the raw
directions so the model can honour natural language without phrase templates.
"""

from __future__ import annotations

import html
import re
from typing import Any, Callable

_FURNITURE_FIELDS = ("presenter", "affiliation", "date", "occasion")
_MAX_VALUE_CHARS = 120
_MAX_AFFILIATION_CHARS = 240

_AFFILIATION_LABEL_RE = re.compile(
    r"(?is)\b(?:affiliations?|institution|kurum|üniversite|universite)\s*:\s*"
    r"(?P<body>.+?)(?="
    r"\b(?:presenter|presented by|speaker|sunucu|konuşmacı|tone|use\s+suitable|"
    r"authors?|date|occasion)\b"
    r"|\Z)"
)

_EXTRACT_SYSTEM = """You extract presentation "deck furniture" from author directions.

Return a JSON object with exactly these string keys:
  presenter, affiliation, date, occasion

Rules:
- Fill a field only when the user clearly states it (any language / phrasing).
- Examples of presenter cues: "presenter", "presented by", "speaker", "sunucu",
  "konuşmacı", "sunan". Examples of affiliation: "affiliation", "institution",
  "university", "department", "kurum", "üniversite", "bölüm".
- Tone, style, length, and topic instructions are NOT furniture — leave those
  fields empty.
- Copy values verbatim (keep titles like Assoc. Prof. Dr.). Do not invent,
  translate names, or guess missing fields.
- Use "" (empty string) for any field not stated.
"""


JsonCaller = Callable[[str, str], dict[str, Any]]


def normalize_furniture(data: Any) -> dict[str, str]:
    """Keep only known non-empty furniture fields, capped in length."""
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for field in _FURNITURE_FIELDS:
        value = data.get(field)
        if value is None:
            continue
        text = " ".join(str(value).split()).strip()
        if not text:
            continue
        limit = _MAX_AFFILIATION_CHARS if field == "affiliation" else _MAX_VALUE_CHARS
        if len(text) <= limit:
            out[field] = text
    return out


def affiliation_from_instructions(instructions: str) -> str:
    """Deterministic Affiliation: span from raw author directions (SoT for reinject)."""
    text = str(instructions or "").strip()
    if not text:
        return ""
    match = _AFFILIATION_LABEL_RE.search(text)
    if not match:
        return ""
    body = " ".join(match.group("body").split()).strip(" ,;")
    if not body:
        return ""
    if len(body) > _MAX_AFFILIATION_CHARS:
        body = body[:_MAX_AFFILIATION_CHARS].rstrip(" ,;")
    return body


def furniture_for_title_reinject(
    furniture: dict[str, str] | None,
    instructions: str = "",
) -> dict[str, str]:
    """Presenter from furniture; affiliation from raw instructions when present."""
    base = normalize_furniture(furniture or {})
    raw_aff = affiliation_from_instructions(instructions)
    if raw_aff:
        base["affiliation"] = raw_aff
    return base


def extract_deck_furniture(
    instructions: str,
    *,
    call_json: JsonCaller | None = None,
) -> dict[str, str]:
    """Ask the LLM what talk facts the user stated. Invents nothing.

    Regex phrase matching was removed: natural language (any language) is the
    contract. On LLM failure returns {} so generation still proceeds; raw
    ``additional_instructions`` remain in the author prompts.
    """
    text = str(instructions or "").strip()
    if not text:
        return {}
    if call_json is None:
        try:
            from llm_client import call_llm_json as call_json
        except Exception as import_error:
            print(f"[furniture] LLM client unavailable: {import_error}")
            return {}
    prompt = (
        "Author directions:\n"
        f"{text}\n\n"
        "Extract deck furniture JSON now."
    )
    try:
        raw = call_json(_EXTRACT_SYSTEM, prompt)
    except Exception as error:
        print(f"[furniture] LLM extract failed: {error}")
        return {}
    furniture = normalize_furniture(raw)
    if furniture:
        print(f"[furniture] LLM-extracted deck facts: {furniture}")
    return furniture


def resolve_deck_furniture(
    result_data: dict[str, Any] | None,
    *,
    call_json: JsonCaller | None = None,
    persist: bool = True,
) -> dict[str, str]:
    """Return cached furniture or extract once from additional_instructions."""
    data = result_data if isinstance(result_data, dict) else {}
    cached = data.get("deck_furniture")
    if isinstance(cached, dict) and normalize_furniture(cached):
        return normalize_furniture(cached)
    furniture = extract_deck_furniture(
        str(data.get("additional_instructions") or ""),
        call_json=call_json,
    )
    if persist and furniture:
        data["deck_furniture"] = furniture
    return furniture


def furniture_lines(furniture: dict[str, str]) -> list[str]:
    """The furniture as display lines, in the order a cover reads them."""
    return [furniture[field] for field in _FURNITURE_FIELDS if furniture.get(field)]


def furniture_prompt_block(furniture: dict[str, str]) -> str:
    """Structured reminder after LLM extraction (optional; raw directions also go in)."""
    if not furniture:
        return ""
    stated = "\n".join(f"- {field}: {value}" for field, value in furniture.items())
    return (
        "Deck furniture extracted from the author's directions (not from the "
        "source document — no PDF evidence required; reproduce verbatim on the "
        "title/closing byline; do not invent any other):\n"
        f"{stated}"
    )


def furniture_values(furniture: dict[str, str]) -> set[str]:
    """Every furniture string, for checks that must not treat these as ungrounded."""
    return {value for value in furniture.values() if value}


_ANONYMOUS_AUTHOR = re.compile(
    r"(?i)^\s*anonymous(\s+author(s)?)?\s*$|^\s*authors?\s+withheld\b"
)


def merge_furniture_into_identity(
    identity: dict[str, str] | None,
    furniture: dict[str, str] | None,
) -> dict[str, str]:
    """Prefer user-supplied presenter/affiliation over PDF anonymous bylines."""
    merged = {
        "paper_title": str((identity or {}).get("paper_title") or "").strip(),
        "authors": str((identity or {}).get("authors") or "").strip(),
        "affiliations": str((identity or {}).get("affiliations") or "").strip(),
    }
    presenter = str((furniture or {}).get("presenter") or "").strip()
    affiliation = str((furniture or {}).get("affiliation") or "").strip()
    if presenter:
        authors = merged["authors"]
        if not authors or _ANONYMOUS_AUTHOR.search(authors):
            merged["authors"] = presenter
        elif presenter.casefold() not in authors.casefold():
            merged["authors"] = presenter
    if affiliation:
        aff = merged["affiliations"]
        if not aff or "withheld" in aff.casefold() or "anonymous" in aff.casefold():
            merged["affiliations"] = affiliation
    return merged


def _accent_safe_x(svg: str) -> float:
    del svg
    return 64.0


def _svg_plain_text(svg: str) -> str:
    """Visible text only — tag gaps (tspans) must not defeat presence checks."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", svg or "")).strip()


def _furniture_value_present(svg: str, value: str) -> bool:
    """True when furniture is already painted (including soft-wrapped tspans)."""
    needle = " ".join(str(value or "").split()).casefold()
    if not needle:
        return True
    plain = _svg_plain_text(svg).casefold()
    if needle in plain:
        return True
    # Long affiliations often wrap; a stable stem is enough to skip re-inject.
    stem = needle[:36].rstrip(" ,;:")
    if len(stem) >= 24 and stem in plain:
        return True
    tokens = [tok for tok in re.split(r"[^\w+#]+", needle) if len(tok) >= 4]
    if len(tokens) >= 4:
        hits = sum(1 for tok in tokens if tok in plain)
        if hits >= max(3, int(0.65 * len(tokens))):
            return True
    return False


def _is_furniture_inject_text(markup: str) -> bool:
    """Furniture inject uses muted fill + soft-wrap tspans."""
    return bool(
        "#7A8494" in (markup or "")
        and re.search(r"<tspan\b", markup or "", flags=re.I)
    )


def _affiliation_node_complete(plain: str, needle: str, stem: str) -> bool:
    plain_cf = (plain or "").casefold()
    if not plain_cf or not needle:
        return False
    return bool(
        stem in plain_cf
        and (
            "tel" in plain_cf
            or "isparta" in plain_cf
            or len(plain_cf) >= 0.7 * len(needle)
        )
    )


def _strip_short_institution_suffix(
    svg: str, presenter: str, affiliation: str
) -> str:
    """Remove ``* University`` tails when full SoT affiliation will reinject."""
    if not svg or not presenter or not affiliation:
        return svg
    needle = " ".join(affiliation.split()).casefold()
    # Prefer a stable institution stem (first 3 tokens) for the short suffix.
    tokens = [t for t in re.split(r"[,\s]+", needle) if t]
    if len(tokens) < 2:
        return svg
    short = " ".join(tokens[: min(3, len(tokens))])
    if len(short) < 12 or short not in needle:
        return svg
    # Match presenter line that ends with * short institution (optionally in tspans).
    pattern = re.compile(
        r"(<text\b[^>]*>)([\s\S]*?)(</text>)",
        flags=re.I,
    )
    out = svg
    for match in list(pattern.finditer(svg)):
        plain = _svg_plain_text(match.group(0))
        plain_cf = plain.casefold()
        if presenter.casefold() not in plain_cf:
            continue
        if short not in plain_cf:
            continue
        # Already the full SoT — leave alone.
        if _affiliation_node_complete(plain, needle, needle[:36].rstrip(" ,;:")):
            continue
        # Strip trailing " * institution…" (and soft variants).
        cleaned = re.sub(
            r"\s*[\*·•]\s*" + re.escape(short) + r".*$",
            "",
            plain,
            count=1,
            flags=re.I,
        ).strip()
        if not cleaned or cleaned.casefold() == plain_cf:
            # Also try without requiring the star when line is "Name Institution".
            if plain_cf.startswith(presenter.casefold()):
                cleaned = presenter
            else:
                continue
        if cleaned.casefold() == plain_cf:
            continue
        replacement = f"{match.group(1)}{cleaned}{match.group(3)}"
        out = out[: match.start()] + replacement + out[match.end() :]
        break
    return out


def _dedupe_affiliation_bylines(svg: str, affiliation: str) -> str:
    """Prefer complete SoT affiliation; drop truncated duplicates."""
    needle = " ".join(str(affiliation or "").split()).casefold()
    if not svg or len(needle) < 16:
        return svg
    stem = needle[:36].rstrip(" ,;:")
    if len(stem) < 20:
        return svg
    matches = list(re.finditer(r"<text\b[^>]*>[\s\S]*?</text>", svg, flags=re.I))
    hits: list[re.Match[str]] = []
    for match in matches:
        plain = _svg_plain_text(match.group(0)).casefold()
        if len(plain) < 12:
            continue
        if stem in plain or plain in needle or (
            len(plain) >= 20 and plain[:20] in needle
        ):
            hits.append(match)
            continue
        # Address / tel fragment of the same affiliation block.
        if any(
            marker in plain and marker in needle
            for marker in ("isparta", "türkiye", "tel:", "+90")
        ):
            hits.append(match)
    if len(hits) <= 1:
        return svg

    def _score(match: re.Match[str]) -> tuple:
        attrs_body = match.group(0)
        plain = _svg_plain_text(attrs_body)
        plain_cf = plain.casefold()
        complete = 1 if _affiliation_node_complete(plain, needle, stem) else 0
        injected = 1 if _is_furniture_inject_text(attrs_body) else 0
        middle = 1 if re.search(r'text-anchor="middle"', attrs_body, flags=re.I) else 0
        return (complete, injected, middle, len(plain_cf), -match.start())

    ranked = sorted(hits, key=_score, reverse=True)
    authored = [m for m in hits if not _is_furniture_inject_text(m.group(0))]
    injected = [m for m in hits if _is_furniture_inject_text(m.group(0))]
    authored_blob = " ".join(_svg_plain_text(m.group(0)).casefold() for m in authored)
    authored_covers = bool(
        authored
        and stem[:24] in authored_blob
        and (
            "tel" in authored_blob
            or "isparta" in authored_blob
            or len(authored_blob) >= 0.7 * len(needle)
        )
    )
    keep_complete = next((m for m in ranked if _score(m)[0] == 1), None)

    if authored_covers and injected:
        # Authored already has the full story (often 2 soft lines) — drop inject copies.
        drop = list(injected)
        if len(authored) > 2:
            keep_set = {m.start() for m in authored[:2]}
            drop += [m for m in authored if m.start() not in keep_set]
    elif keep_complete is not None:
        # One complete SoT node (usually inject) — drop truncated fragments.
        drop = [m for m in hits if m.start() != keep_complete.start()]
    elif injected and authored:
        best_inj = max(injected, key=lambda m: len(_svg_plain_text(m.group(0))))
        best_auth = max(authored, key=lambda m: len(_svg_plain_text(m.group(0))))
        if len(_svg_plain_text(best_inj.group(0))) > len(
            _svg_plain_text(best_auth.group(0))
        ) + 8:
            drop = [m for m in hits if m.start() != best_inj.start()]
        else:
            drop = list(injected)
    else:
        keep_set: set[int] = set()
        kept_plain: list[str] = []
        for match in ranked:
            plain = _svg_plain_text(match.group(0)).casefold()
            if any(plain in prev or prev in plain for prev in kept_plain):
                continue
            keep_set.add(match.start())
            kept_plain.append(plain)
            if len(keep_set) >= 2:
                break
        drop = [m for m in hits if m.start() not in keep_set]
    out = svg
    for match in sorted(drop, key=lambda m: m.start(), reverse=True):
        out = out[: match.start()] + out[match.end() :]
    return out


def _html_plain_text(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup or "")).strip()


def _furniture_value_present_html(markup: str, value: str) -> bool:
    """True when furniture is already painted (full string or long-affiliation stem+tel)."""
    needle = " ".join(str(value or "").split()).casefold()
    if not needle:
        return True
    plain = _html_plain_text(markup).casefold()
    if needle in plain:
        return True
    stem = needle[:36].rstrip(" ,;:")
    if len(stem) < 24 or stem not in plain:
        tokens = [tok for tok in re.split(r"[^\w+#]+", needle) if len(tok) >= 4]
        if len(tokens) >= 4:
            hits = sum(1 for tok in tokens if tok in plain)
            if hits >= max(3, int(0.65 * len(tokens))):
                return True
        return False
    # Long affiliations (IEEE bylines): stem alone is not enough — need tel / city / length.
    if len(needle) >= 48:
        return _affiliation_node_complete(_html_plain_text(markup), needle, stem)
    return True


def apply_furniture_to_title_html(markup: str, furniture: dict[str, str] | None) -> str:
    """Backup: inject presenter/affiliation byline when HTML cover omitted them."""
    if not furniture or not markup:
        return markup
    presenter = str(furniture.get("presenter") or "").strip()
    affiliation = str(furniture.get("affiliation") or "").strip()
    if not presenter and not affiliation:
        return markup
    out = markup
    # Replace anonymous placeholders when present.
    if presenter:
        out = re.sub(
            r"Anonymous Author\(s\)",
            html.escape(presenter),
            out,
            count=1,
            flags=re.I,
        )
    if affiliation:
        out = re.sub(
            r"Affiliation withheld for double-anonymous review",
            html.escape(affiliation),
            out,
            count=1,
            flags=re.I,
        )
    need_presenter = bool(presenter) and not _furniture_value_present_html(out, presenter)
    need_aff = bool(affiliation) and not _furniture_value_present_html(out, affiliation)
    if not need_presenter and not need_aff:
        return out

    lines: list[str] = []
    if need_presenter:
        lines.append(
            '<div data-sunairum-furniture="presenter" '
            'style="font-size:18px;line-height:1.3;font-weight:600;color:#1A365D;">'
            f"{html.escape(presenter)}</div>"
        )
    if need_aff:
        lines.append(
            '<div data-sunairum-furniture="affiliation" '
            'style="font-size:14px;line-height:1.35;font-weight:500;color:#4A5568;'
            'max-width:920px;">'
            f"{html.escape(affiliation)}</div>"
        )
    # Absolute bottom rail — covers are rarely flex columns, so margin-top:auto
    # would not land the byline.
    block = (
        '<div data-sunairum-furniture="byline" '
        'style="position:absolute;left:56px;right:56px;bottom:48px;'
        'display:flex;flex-direction:column;gap:6px;z-index:5;">'
        + "".join(lines)
        + "</div>"
    )
    close = re.search(r"</section\s*>", out, flags=re.I)
    if not close:
        return out + block
    return out[: close.start()] + block + out[close.start() :]


def apply_furniture_to_title_svg(svg: str, furniture: dict[str, str] | None) -> str:
    """Backup: rewrite/inject bylines when the slide model omitted furniture."""
    if not furniture or not svg:
        return svg
    presenter = str(furniture.get("presenter") or "").strip()
    affiliation = str(furniture.get("affiliation") or "").strip()
    if not presenter and not affiliation:
        return svg
    out = svg
    safe_x = _accent_safe_x(out)
    if presenter and affiliation:
        out = _strip_short_institution_suffix(out, presenter, affiliation)
    if presenter:
        out = re.sub(
            r"Anonymous Author\(s\)",
            presenter,
            out,
            count=1,
            flags=re.I,
        )
        if not _furniture_value_present(out, presenter):
            out = _inject_presenter_byline(out, presenter, affiliation, safe_x=safe_x)
        # Pull bylines that still sit on/inside the accent rail — never yank a
        # centered cover byline from x≈640 down to the left margin.
        out = re.sub(
            r'(<text\b[^>]*\bx=")(?:[0-9]|[1-7][0-9]|8[0-3])(?:\.\d+)?("([^>]*>)\s*)'
            + re.escape(presenter),
            rf"\g<1>{safe_x:g}\2{presenter}",
            out,
            count=1,
        )
        # Left-rail presenter must not keep text-anchor=middle (half off-canvas).
        out = re.sub(
            r'(<text\b(?=[^>]*\bx="(?:[0-9]|[1-9][0-9]|1[0-4][0-9])(?:\.\d+)?")[^>]*)'
            r'\s*text-anchor="middle"([^>]*>\s*)' + re.escape(presenter),
            r"\1\2" + presenter,
            out,
            count=1,
            flags=re.I,
        )
    if affiliation:
        out = re.sub(
            r"Affiliation withheld for double-anonymous review",
            affiliation,
            out,
            count=1,
            flags=re.I,
        )
        if not _furniture_value_present(out, affiliation):
            out = _inject_affiliation_byline(out, affiliation, presenter, safe_x=safe_x)
        out = _dedupe_affiliation_bylines(out, affiliation)
    return out


def _text_open_attrs(font_size: float = 15.0, fill: str = "#5B6472") -> str:
    return (
        f'font-family="Arial, Helvetica, sans-serif" font-size="{font_size:g}" '
        f'font-weight="500" fill="{fill}"'
    )


def _inject_presenter_byline(
    svg: str, presenter: str, affiliation: str, *, safe_x: float = 100.0
) -> str:
    if affiliation:
        aff_match = re.search(
            r'(<text\b[^>]*\by=")(\d+(?:\.\d+)?)("[^>]*>\s*)'
            + re.escape(affiliation),
            svg,
            flags=re.I,
        )
        if aff_match:
            y_pos = max(40.0, float(aff_match.group(2)) - 22.0)
            insert = (
                f'<text x="{safe_x:g}" y="{y_pos:g}" {_text_open_attrs(16)}>'
                f"{presenter}</text>"
            )
            return svg[: aff_match.start()] + insert + svg[aff_match.start() :]

    page_match = re.search(
        r'<text\b[^>]*\by="(\d+(?:\.\d+)?)"[^>]*>\s*0?\d+\s*/\s*\d+\s*</text>',
        svg,
        flags=re.I,
    )
    y_pos = 560.0
    if page_match:
        y_pos = max(120.0, float(page_match.group(1)) - 40.0)
    insert = f'<text x="{safe_x:g}" y="{y_pos:g}" {_text_open_attrs(16)}>{presenter}</text>'
    close = re.search(r"</svg\s*>", svg, flags=re.I)
    if not close:
        return svg + insert
    return svg[: close.start()] + insert + svg[close.start() :]


def _wrap_byline_inner(text: str, *, x: float = 100.0, max_chars: int = 88) -> str:
    """Soft-wrap a byline into tspans so long affiliations stay inside margins."""
    words = str(text or "").split()
    if not words:
        return ""
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if len(trial) <= max_chars:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if len(lines) == 1:
        return lines[0]
    parts = []
    for index, line in enumerate(lines[:3]):
        dy = "0" if index == 0 else "18"
        parts.append(f'<tspan x="{x:g}" dy="{dy}">{line}</tspan>')
    return "".join(parts)


def _inject_affiliation_byline(
    svg: str, affiliation: str, presenter: str, *, safe_x: float = 100.0
) -> str:
    """Inject affiliation as a closed sibling text node (never nest inside presenter)."""
    inner = _wrap_byline_inner(affiliation, x=safe_x)
    if presenter:
        pres_match = re.search(
            r'(<text\b[^>]*\by=")(\d+(?:\.\d+)?)("[^>]*>\s*(?:<tspan\b[^>]*>\s*)?)'
            + re.escape(presenter)
            + r"(?:\s*</tspan>)?\s*</text>",
            svg,
            flags=re.I,
        )
        if not pres_match:
            # Presenter may share a text node with other chrome — match by plain text.
            for text_match in re.finditer(
                r"<text\b[^>]*>[\s\S]*?</text>", svg, flags=re.I
            ):
                plain = _svg_plain_text(text_match.group(0))
                if plain.casefold().strip() == presenter.casefold():
                    ym = re.search(r'\by="(\d+(?:\.\d+)?)"', text_match.group(0))
                    if ym:
                        y_pos = float(ym.group(1)) + 22.0
                        insert = (
                            f'<text x="{safe_x:g}" y="{y_pos:g}" '
                            f'{_text_open_attrs(14, "#7A8494")}>{inner}</text>'
                        )
                        return (
                            svg[: text_match.end()]
                            + insert
                            + svg[text_match.end() :]
                        )
                    break
        if pres_match:
            y_pos = float(pres_match.group(2)) + 22.0
            insert = (
                f'<text x="{safe_x:g}" y="{y_pos:g}" {_text_open_attrs(14, "#7A8494")}>'
                f"{inner}</text>"
            )
            return svg[: pres_match.end()] + insert + svg[pres_match.end() :]
    close = re.search(r"</svg\s*>", svg, flags=re.I)
    insert = (
        f'<text x="{safe_x:g}" y="582" {_text_open_attrs(14, "#7A8494")}>{inner}</text>'
    )
    if not close:
        return svg + insert
    return svg[: close.start()] + insert + svg[close.start() :]
