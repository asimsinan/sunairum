"""Densify Strategist IR for Executor / Intent — multi-line Content, cards/steps, markdown strip."""

from __future__ import annotations

import re
from typing import Any

_MD_BOLD_RE = re.compile(r"\*+([^*]+)\*+")
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
# Stop only at known §IX field labels — not bold labels inside Content bullets
# (e.g. "- **Candidate retrieval:** …").
_IX_FIELD_STOP = (
    r"(?=^\s*[-*]\s*\*\*(?:"
    r"Title|Core message|Core Message|Layout|Content|Cards|Steps|Visual job|"
    r"Visual Job|Evidence|Figure|Table|Formula|Formula terms|Formula Terms|"
    r"Formula gloss|Formula Gloss|Authors|Affiliations|Author|Affiliation|"
    r"Infographic template|Infographic Template|Infographic DSL"
    r"):?\*\*|\Z)"
)
_CONTENT_BLOCK_RE = re.compile(
    rf"(?ims)^\s*[-*]\s*\*\*Content:?\*\*\s*:?\s*\n(.*?){_IX_FIELD_STOP}"
)
_CONTENT_INLINE_RE = re.compile(
    rf"(?ims)^\s*[-*]\s*\*\*Content:?\*\*\s*:?\s*(.+?){_IX_FIELD_STOP}"
)
_CARDS_BLOCK_RE = re.compile(
    rf"(?ims)^\s*[-*]\s*\*\*Cards:?\*\*\s*:?\s*\n(.*?){_IX_FIELD_STOP}"
)
_STEPS_BLOCK_RE = re.compile(
    rf"(?ims)^\s*[-*]\s*\*\*Steps:?\*\*\s*:?\s*\n(.*?){_IX_FIELD_STOP}"
)
_LAYOUT_FAMILY_RE = re.compile(
    r"(?i)\b("
    r"body_bullets|card_row|process_steps|two_column_compare|two_column_takeaway|"
    r"chart_sidebar|split_figure|split_table|formula_hero|diagram"
    r")\b"
)
_META_TITLES = frozenset(
    {
        "title",
        "core message",
        "layout",
        "content",
        "visual job",
        "evidence",
        "figure",
        "table",
        "formula",
    }
)


def strip_markdown_inline(text: str) -> str:
    """Remove bold markers and leading bullet chrome from a claim string."""
    out = str(text or "").strip()
    out = _MD_BOLD_RE.sub(r"\1", out)
    out = _BULLET_PREFIX_RE.sub("", out)
    out = out.replace("**", "").strip()
    return out


def _lines_from_block(block: str) -> list[str]:
    bullets: list[str] = []
    for line in (block or "").splitlines():
        if not re.match(r"^\s*(?:[-*•]|\d+[.)])\s+\S", line):
            # Also accept indented continuation of a multi-line Content dump
            # that uses "; " separators on one line.
            continue
        cleaned = strip_markdown_inline(line)
        if not cleaned:
            continue
        low = cleaned.casefold()
        if low.startswith("figure:") or low.startswith("table:"):
            continue
        if low in _META_TITLES:
            continue
        bullets.append(cleaned)
    if not bullets and block.strip():
        # Single-line Content: "a; b; c" or prose after **Content:**
        inline = strip_markdown_inline(block.splitlines()[0] if block.splitlines() else block)
        for part in re.split(r"\s*;\s*", inline):
            part = strip_markdown_inline(part)
            if part and part.casefold() not in _META_TITLES:
                bullets.append(part)
    return bullets


def extract_content_bullets_from_body_md(body_md: str) -> list[str]:
    """Pull Content bullets from a §IX slide chunk (body_md)."""
    text = str(body_md or "")
    if not text.strip():
        return []
    match = _CONTENT_BLOCK_RE.search(text)
    if match:
        bullets = _lines_from_block(match.group(1))
        if bullets:
            return bullets
    match = _CONTENT_INLINE_RE.search(text)
    if match:
        return _lines_from_block(match.group(1))
    return []


def extract_structured_cards_from_body_md(body_md: str) -> list[dict[str, str]]:
    text = str(body_md or "")
    match = _CARDS_BLOCK_RE.search(text)
    if not match:
        return []
    return claim_cards_from_lines(_lines_from_block(match.group(1)))


def extract_structured_steps_from_body_md(body_md: str) -> list[dict[str, str]]:
    text = str(body_md or "")
    match = _STEPS_BLOCK_RE.search(text)
    if not match:
        return []
    return claim_cards_from_lines(_lines_from_block(match.group(1)))


def claim_cards_from_lines(bullets: list[str], *, limit: int = 6) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for chunk in bullets[:limit]:
        cleaned = strip_markdown_inline(chunk)
        if not cleaned:
            continue
        if ":" in cleaned[:48]:
            title, _, body = cleaned.partition(":")
            title = strip_markdown_inline(title)
            body = strip_markdown_inline(body)
        else:
            words = cleaned.split()
            title = " ".join(words[:5]) if len(words) > 8 else cleaned[:72]
            body = cleaned if title != cleaned else ""
            title = strip_markdown_inline(title)
        if title.casefold() in _META_TITLES:
            continue
        if not title:
            continue
        cards.append({"title": title[:80], "body": body[:240]})
    return cards


def count_claim_lines(text: str) -> int:
    raw = str(text or "").strip()
    if not raw:
        return 0
    lines = [strip_markdown_inline(ln) for ln in re.split(r"[\n;]+", raw) if ln.strip()]
    return len([ln for ln in lines if ln])


def normalize_layout_family(layout_intent: str) -> str:
    """Soft layout family hint from Layout prose (not AABB recipe)."""
    text = str(layout_intent or "").strip()
    match = _LAYOUT_FAMILY_RE.search(text)
    if match:
        return match.group(1).casefold()
    low = text.casefold()
    if any(t in low for t in ("process", "pipeline", "stages", "step")):
        return "process_steps"
    if any(t in low for t in ("chart", "bar", "plot", "metrics")):
        return "chart_sidebar"
    if any(t in low for t in ("two-column", "two column", "synthesis", "bottom-line")):
        return "two_column_takeaway"
    if any(t in low for t in ("compare", "versus", "vs.")):
        return "two_column_compare"
    if any(t in low for t in ("card", "pillar", "kpi", "stack")):
        return "card_row"
    if any(t in low for t in ("diagram", "architecture", "schematic")):
        return "diagram"
    if "formula" in low:
        return "formula_hero"
    return "body_bullets"


def densify_slide_ir(slide: dict[str, Any]) -> dict[str, Any]:
    """Claim-text cleanup for soft IR — no recipe composition."""
    role = str(slide.get("role") or "content").strip().casefold()
    if role in {"title", "hero", "closing"}:
        return slide

    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    body = str(content.get("BODY") or slide.get("content_blocks") or "").strip()
    body_md = str(slide.get("body_md") or slide.get("body") or "").strip()
    claim_n = count_claim_lines(body)

    density_hint = str(slide.get("density") or "").casefold()
    min_claims_hint = 2 if density_hint in {"low", "sparse"} else 3
    from_md = extract_content_bullets_from_body_md(body_md)
    if claim_n < min_claims_hint and from_md:
        body = "\n".join(f"- {b}" for b in from_md)
        claim_n = len(from_md)

    # Strip markdown leaks from BODY.
    if body:
        cleaned_lines = [
            strip_markdown_inline(ln) for ln in re.split(r"[\n;]+", body) if ln.strip()
        ]
        cleaned_lines = [ln for ln in cleaned_lines if ln]
        body = "\n".join(f"- {ln}" for ln in cleaned_lines) if cleaned_lines else ""
        claim_n = len(cleaned_lines)

    # Soft IR may carry cards/steps from Strategist; do not mint them here for recipes.
    cards = slide.get("cards") if isinstance(slide.get("cards"), list) else []
    steps = slide.get("steps") if isinstance(slide.get("steps"), list) else []

    cleaned_lines = [
        strip_markdown_inline(ln) for ln in re.split(r"[\n;]+", body) if ln.strip()
    ] if body else []
    cleaned_lines = [ln for ln in cleaned_lines if ln]

    # Density floor: expand from core_message when still thin and no assets.
    # Pack density=low lowers the floor so sparse academic packs stay breathable.
    table_id = str(slide.get("table_id") or "").strip()
    figure_id = str(slide.get("figure_id") or "").strip()
    has_asset = bool(table_id or figure_id)
    density = str(slide.get("density") or "").casefold()
    min_claims = 2 if density in {"low", "sparse"} else 3
    if density in {"high", "dense", "tight"}:
        min_claims = 4
    if not has_asset and claim_n < min_claims and len(cards) < 2 and len(steps) < 2:
        core = strip_markdown_inline(str(slide.get("core_message") or ""))
        extras = from_md or cleaned_lines
        pool = list(dict.fromkeys([*extras, *([core] if core else [])]))
        if len(pool) >= 2:
            body = "\n".join(f"- {strip_markdown_inline(p)}" for p in pool[:6])
            claim_n = min(6, len(pool))
        elif core and claim_n < 1:
            body = f"- {core}"
            claim_n = 1

    # Table / formula slides: prefer §IX Content bullets for the insight column,
    # and surface gloss/core as the callout under those claims.
    formula = str(slide.get("formula") or "").strip()
    formula_terms = strip_markdown_inline(str(slide.get("formula_terms") or ""))
    formula_gloss = strip_markdown_inline(str(slide.get("formula_gloss") or ""))
    if table_id or formula:
        if from_md and len(from_md) >= max(2, claim_n):
            body = "\n".join(f"- {strip_markdown_inline(b)}" for b in from_md[:6])
            claim_n = min(6, len(from_md))
            cleaned_lines = [strip_markdown_inline(b) for b in from_md[:6]]
        if not str(slide.get("callout") or "").strip():
            gloss = formula_gloss
            core = strip_markdown_inline(str(slide.get("core_message") or ""))
            if formula and gloss:
                slide["callout"] = gloss
            elif core:
                slide["callout"] = core
        # Keep terms/gloss on the slide + content so Executor paints term cards.
        if formula and not formula_terms:
            # Derive crude term labels from equation tokens when Strategist omitted them.
            tokens = re.findall(
                r"\b([A-Za-zΑ-Ωα-ω][A-Za-z0-9Α-Ωα-ω_]{0,12})\b",
                formula,
            )
            skip = {
                "frac",
                "sum",
                "min",
                "max",
                "log",
                "exp",
                "sin",
                "cos",
                "tan",
                "and",
                "or",
                "the",
                "for",
                "with",
            }
            uniq = [t for t in dict.fromkeys(tokens) if t.casefold() not in skip]
            if uniq:
                formula_terms = ", ".join(uniq[:6])
                slide["formula_terms"] = formula_terms
        if formula and formula_gloss:
            slide["formula_gloss"] = formula_gloss

    slide["content"] = {
        **content,
        "BODY": body,
        "TITLE": content.get("TITLE") or slide.get("title") or "",
        "SUBTITLE": content.get("SUBTITLE")
        or slide.get("core_message")
        or content.get("SUBTITLE")
        or "",
        **(
            {"FORMULA_TERMS": formula_terms, "FORMULA_GLOSS": formula_gloss}
            if formula and (formula_terms or formula_gloss)
            else {}
        ),
    }
    slide["content_blocks"] = body
    if cards:
        slide["cards"] = [
            {
                "title": strip_markdown_inline(str(c.get("title") or "")),
                "body": strip_markdown_inline(str(c.get("body") or c.get("text") or "")),
            }
            for c in cards
            if isinstance(c, dict)
        ]
    if steps:
        slide["steps"] = [
            {
                "title": strip_markdown_inline(str(s.get("title") or "")),
                "body": strip_markdown_inline(str(s.get("body") or s.get("text") or "")),
            }
            for s in steps
            if isinstance(s, dict)
        ]
    return slide
