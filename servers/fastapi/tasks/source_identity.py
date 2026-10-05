"""Extract paper title / authors / affiliations from page-1 evidence."""

from __future__ import annotations

import re
from typing import Any


_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_AUTHOR_LINE = re.compile(
    r"(?i)^\s*(?:authors?|by)\s*[:：]\s*(.+)$|^\s*([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,4}(?:\s*,\s*[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,4})+)\s*$"
)
_AFFIL_LINE = re.compile(
    r"(?i)^\s*(?:affiliations?|department|university|institute|lab(?:oratory)?)\b.*$|"
    r"^\s*.*(University|Institute|Department|Laboratory|College|School of)\b.*$"
)


def _page1_texts(bundle: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    structure = bundle.get("structure") if isinstance(bundle.get("structure"), dict) else {}
    for page in structure.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_no = page.get("page") or page.get("page_number") or page.get("n")
        try:
            page_i = int(page_no)
        except (TypeError, ValueError):
            page_i = 1 if not texts else 99
        if page_i != 1:
            continue
        for block in page.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            text = str(block.get("text") or block.get("content") or "").strip()
            if text:
                texts.append(text)
    if texts:
        return texts
    for item in bundle.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        page_no = item.get("page") or item.get("page_number")
        try:
            page_i = int(page_no) if page_no is not None else 1
        except (TypeError, ValueError):
            page_i = 1
        if page_i != 1:
            continue
        text = str(item.get("text") or item.get("quote") or "").strip()
        if text:
            texts.append(text)
    return texts


def extract_source_identity(bundle: dict[str, Any] | None) -> dict[str, str]:
    """Return paper_title, authors, affiliations (empty strings when unknown)."""
    if not isinstance(bundle, dict):
        return {"paper_title": "", "authors": "", "affiliations": ""}
    texts = _page1_texts(bundle)
    paper_title = ""
    authors = ""
    affiliations: list[str] = []
    for text in texts:
        compact = " ".join(text.split())
        if not compact or _CJK.search(compact):
            # Prefer Latin title plate for product English UI; still accept if nothing else.
            pass
        if not paper_title and 12 <= len(compact) <= 220 and not _AUTHOR_LINE.match(compact):
            # First substantial non-author line is usually the title on page 1.
            if not re.match(r"(?i)^(abstract|introduction|keywords)\b", compact):
                paper_title = compact
                continue
        author_match = _AUTHOR_LINE.match(compact)
        if author_match and not authors:
            authors = (author_match.group(1) or author_match.group(2) or "").strip()
            continue
        if _AFFIL_LINE.match(compact) and len(affiliations) < 4:
            affiliations.append(compact)
    if not paper_title and texts:
        paper_title = " ".join(texts[0].split())[:220]
    return {
        "paper_title": paper_title,
        "authors": authors,
        "affiliations": "; ".join(affiliations),
    }


def title_looks_like_topic(title: str, topic: str) -> bool:
    """True when Strategist reused the user topic as the paper title."""
    a = re.sub(r"\W+", " ", (title or "").casefold()).strip()
    b = re.sub(r"\W+", " ", (topic or "").casefold()).strip()
    if not a or not b:
        return False
    if a == b:
        return True
    return a in b or b in a
