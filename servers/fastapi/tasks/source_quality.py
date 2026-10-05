"""Deterministic quality gates for normalized PDF source artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def table_row_width(row: Any) -> int:
    """Column width of a table row, counting a spanning cell once per column.

    A header cell with ``colspan=2`` occupies two columns but appears once, so
    counting cells would report a spanned header as narrower than its data rows
    and flag a perfectly good table as malformed.
    """
    if not isinstance(row, list):
        return 0
    width = 0
    for cell in row:
        width += max(1, int(cell.get("colspan") or 1)) if isinstance(cell, dict) else 1
    return width


def _garbled_token_count(text: str) -> int:
    tokens = re.findall(r"\S+", text)
    return sum(
        1
        for token in tokens
        if "�" in token or "¨" in token or re.search(r"[A-Za-z]\?[A-Za-z]", token)
    )


def _hyphenation_count(text: str) -> int:
    return len(re.findall(r"(?<=\w)-\n(?=\w)", text))


def evaluate_source_quality(
    sources_dir: str | Path,
    expected_page_count: int,
    *,
    parser_page_count: int | None = None,
) -> dict[str, Any]:
    """Return a quality report; ``accepted`` is the fallback decision."""
    root = Path(sources_dir)
    markdown_path = root / "source.md"
    structure_path = root / "source_structure.json"
    tables_path = root / "source_tables.json"
    errors: list[str] = []
    warnings: list[str] = []
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace") if markdown_path.is_file() else ""
    structure: dict[str, Any] = {}
    tables: dict[str, Any] = {}
    try:
        structure = json.loads(structure_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append("source_structure.json is missing or invalid")
    try:
        tables = json.loads(tables_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append("source_tables.json is missing or invalid")

    pages = structure.get("pages", []) if isinstance(structure, dict) else []
    actual_pages = len(pages) if isinstance(pages, list) else 0
    nonempty_pages = 0
    for page in pages if isinstance(pages, list) else []:
        blocks = page.get("blocks", []) if isinstance(page, dict) else []
        if any(
            isinstance(block, dict)
            and str(block.get("text") or block.get("latex") or block.get("html") or block.get("content") or "").strip()
            for block in blocks
        ):
            nonempty_pages += 1
    if parser_page_count is not None and parser_page_count != expected_page_count:
        errors.append(f"parser page count {parser_page_count} does not match PDF page count {expected_page_count}")
    if actual_pages != expected_page_count:
        errors.append(f"normalized page count {actual_pages} does not match PDF page count {expected_page_count}")
    if expected_page_count and nonempty_pages < expected_page_count:
        errors.append(f"only {nonempty_pages}/{expected_page_count} pages contain usable text")
    if not markdown.strip():
        errors.append("normalized Markdown is empty")

    table_items = tables.get("tables", []) if isinstance(tables, dict) else []
    malformed_tables = 0
    unreliable_table_ids: list[str] = []
    for table in table_items if isinstance(table_items, list) else []:
        headers = table.get("headers", []) if isinstance(table, dict) else []
        rows = table.get("rows", []) if isinstance(table, dict) else []
        if isinstance(table, dict) and table.get("validation_status") != "valid":
            malformed_tables += 1
            unreliable_table_ids.append(str(table.get("table_id") or f"table-{malformed_tables}"))
            continue
        width = table_row_width(headers)
        if width and any(table_row_width(row) != width for row in rows if isinstance(row, list)):
            malformed_tables += 1
            unreliable_table_ids.append(str(table.get("table_id") or f"table-{malformed_tables}"))
    if malformed_tables:
        # A ragged table is a fact about that table, not about the document. Sparse
        # tables are ordinary in real papers -- Table 3 of *Attention Is All You Need*
        # states that unlisted values match the base model, so a faithful parse of it has
        # short rows. Rejecting the source for it discarded fifteen pages of good prose
        # and every figure, and triggered an OCR re-parse that cannot fix a table which
        # was never wrong. The tables are named so the planner can decline to cite them.
        warnings.append(
            f"{malformed_tables} table(s) have inconsistent row lengths: "
            + ", ".join(unreliable_table_ids)
        )

    garbled = _garbled_token_count(markdown)
    hyphenation = _hyphenation_count(markdown)
    token_count = max(1, len(re.findall(r"\S+", markdown)))
    if garbled > max(2, token_count // 100):
        errors.append(f"garbled token rate is too high ({garbled}/{token_count})")
    if hyphenation > max(2, token_count // 200):
        warnings.append(f"{hyphenation} possible broken hyphenation artifact(s)")

    return {
        "accepted": not errors,
        "errors": errors,
        "warnings": warnings,
        "text_quality": {
            "nonempty_pages": nonempty_pages,
            "garbled_token_count": garbled,
            "hyphenation_artifact_count": hyphenation,
            "token_count": token_count,
        },
        "tables": {
            "unreliable": unreliable_table_ids,
            "detected": len(table_items) if isinstance(table_items, list) else 0,
            "structured": sum(1 for table in table_items if isinstance(table, dict) and table.get("validation_status") == "valid") if isinstance(table_items, list) else 0,
        },
    }
