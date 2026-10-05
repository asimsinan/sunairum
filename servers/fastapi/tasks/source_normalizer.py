"""Normalize parsed documents into Sunairum's source artifact contract."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .source_quality import table_row_width
except ImportError:  # pragma: no cover - supports direct script imports
    from source_quality import table_row_width


@dataclass
class NormalizedSource:
    markdown_path: Path
    structure_path: Path
    tables_path: Path
    image_manifest_path: Path
    page_count: int
    table_count: int
    figure_count: int
    diagnostics: dict[str, Any]


# LaTeX-produced PDFs draw an umlaut, dot or caron as a separate *spacing*
# accent glyph positioned before its base letter, so extraction yields
# "S¨ uleyman" and "T ¨ UB˙ ITAK" rather than "Süleyman" and "TÜBİTAK". The
# accent arrives as a real character in the text stream, not as a combining
# mark, and layout spaces may sit on either side of it. A literal lookup table
# only ever covered the handful of pairs someone happened to hit; recompose the
# accent with its letter instead, and only when the two genuinely form one
# precomposed character — otherwise the accent did not belong to that letter and
# the text is left exactly as extracted.
_SPACING_ACCENTS = {
    "\u00a8": "\u0308",  # diaeresis  ¨ -> combining
    "\u02d9": "\u0307",  # dot above  ˙
    "\u02c7": "\u030c",  # caron      ˇ
    "\u00b4": "\u0301",  # acute      ´
    "\u02da": "\u030a",  # ring above ˚
    "\u00b8": "\u0327",  # cedilla    ¸
    "\u02dc": "\u0303",  # small tilde ˜
    "\u02d8": "\u0306",  # breve      ˘
    "\u02dd": "\u030b",  # double acute ˝
}
# ASCII backtick and tilde are deliberately excluded: they carry meaning in
# Markdown and in code spans.
_ACCENT_CLASS = "".join(_SPACING_ACCENTS)
# One pass, so a pair that cannot compose keeps its original spacing: the
# leading space is only ever dropped together with a successful recomposition.
_ACCENT_BEFORE_LETTER_RE = re.compile(
    rf"(?<=[A-Za-z])([ \t]*)([{_ACCENT_CLASS}])[ \t]*([A-Za-z])"
    rf"|([{_ACCENT_CLASS}])[ \t]*([A-Za-z])"
)


def _recompose_spacing_accents(value: str) -> str:
    """Reattach a spacing accent glyph to the letter it was drawn over."""
    if not value or not any(accent in value for accent in _SPACING_ACCENTS):
        return value

    def repair(match: re.Match[str]) -> str:
        accent = match.group(2) or match.group(4)
        letter = match.group(3) or match.group(5)
        composed = unicodedata.normalize("NFC", letter + _SPACING_ACCENTS[accent])
        return composed if len(composed) == 1 else match.group(0)

    return _ACCENT_BEFORE_LETTER_RE.sub(repair, value)


def _clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", html.unescape(value))
    value = value.replace("\u00ad", "")
    value = re.sub(r"(?<=\w)-\s+(?=\w)", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    # OCR often inserts spaces inside decimals / percents: "47 . 7 %" → "47.7%"
    value = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", value)
    value = re.sub(r"(?<=[+\-])\s+(?=\d)", "", value)
    value = re.sub(r"(?<=\d)\s+%", "%", value)
    return _recompose_spacing_accents(value)


def _normalize_markdown(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = normalized.replace("\u00ad", "")
    normalized = re.sub(r"(?<=\w)-\n(?=\w)", "", normalized)
    normalized = _recompose_spacing_accents(normalized)
    return normalized.strip() + "\n"


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        return [float(value[index]) for index in range(4)]
    except (TypeError, ValueError):
        return None


def _text_from_block(block: dict[str, Any]) -> str:
    for key in ("text", "content", "md", "markdown", "latex"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_text(value)
    return ""




def _block_type(block: dict[str, Any]) -> str:
    value = str(block.get("type") or block.get("category") or block.get("label") or "text").lower()
    if "title" in value or "heading" in value:
        return "heading"
    if "table" in value:
        return "table"
    if "image" in value or "figure" in value or "picture" in value:
        return "figure"
    if "equation" in value or "formula" in value:
        return "formula"
    if "list" in value:
        return "list"
    return "paragraph"
















def _markdown_from_blocks(blocks_by_page: dict[int, list[dict[str, Any]]]) -> str:
    lines: list[str] = []
    for page in sorted(blocks_by_page):
        if page > 1:
            lines.append(f"<!-- page: {page - 1} -->")
        for block in blocks_by_page[page]:
            kind = _block_type(block)
            text = _text_from_block(block)
            if kind == "heading":
                level = min(6, max(1, int(block.get("level") or 2)))
                lines.append(f"{'#' * level} {text}")
            elif kind == "formula":
                lines.extend(["$$", text, "$$"])
            elif text:
                lines.append(text)
            lines.append("")
    return "\n".join(lines)




def _docling_bbox(prov: Any, page_height: float | None) -> list[float] | None:
    """Return ``[x0, y0, x1, y1]`` in top-left origin, the convention on disk."""
    bbox = getattr(prov, "bbox", None)
    if bbox is None:
        return None
    try:
        if page_height:
            bbox = bbox.to_top_left_origin(page_height)
        return [float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)]
    except (AttributeError, TypeError, ValueError):
        return None


def _docling_cell(cell: Any) -> dict[str, Any]:
    return {
        "text": _clean_text(str(getattr(cell, "text", "") or "")),
        "is_header": bool(getattr(cell, "column_header", False) or getattr(cell, "row_header", False)),
        "rowspan": max(1, int(getattr(cell, "row_span", 1) or 1)),
        "colspan": max(1, int(getattr(cell, "col_span", 1) or 1)),
    }


def _docling_table_grid(data: Any) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """Lay Docling's flat cell list back onto a grid, keeping spans intact.

    ``TableData.table_cells`` is a flat list where each cell knows its own row
    and column offsets, so a spanning cell appears once rather than once per
    covered position. Reconstructing the grid by offset preserves that, which is
    what makes ``rowspan``/``colspan`` survive into the evidence bundle.
    """
    cells = list(getattr(data, "table_cells", []) or [])
    if not cells:
        return [], []
    num_rows = int(getattr(data, "num_rows", 0) or 0)
    if not num_rows:
        num_rows = max(int(getattr(cell, "end_row_offset_idx", 1) or 1) for cell in cells)
    grid: list[list[dict[str, Any]]] = [[] for _ in range(num_rows)]
    for cell in cells:
        row_index = int(getattr(cell, "start_row_offset_idx", 0) or 0)
        if 0 <= row_index < num_rows:
            grid[row_index].append((cell, int(getattr(cell, "start_col_offset_idx", 0) or 0)))
    ordered = [
        [_docling_cell(cell) for cell, _ in sorted(row, key=lambda item: item[1])]
        for row in grid
    ]
    ordered = [row for row in ordered if row]
    if not ordered:
        return [], []
    # A table whose first row is not a header still needs a header row, because
    # the quality gate compares every row's width against the header's.
    header_row = ordered[0]
    return header_row, ordered[1:]


_DOCLING_BLOCK_TYPES = {
    "section_header": "heading",
    "title": "heading",
    "table": "table",
    "picture": "image",
    "chart": "image",
    "formula": "equation",
    "list_item": "list",
    "code": "text",
    "caption": "text",
    "footnote": "text",
    "reference": "text",
    "paragraph": "text",
    "text": "text",
}

# Running heads and folios are layout furniture, not source content. Docling
# reports them faithfully, so they have to be discarded here or every page
# contributes a spurious folio number and a repeated journal title.
_DOCLING_DISCARDED = {"page_header", "page_footer"}


def _docling_blocks(document: Any) -> dict[int, list[dict[str, Any]]]:
    """Group document items by their own page number.

    This is the structural reason for the migration: every item carries
    ``prov[].page_no``, so page attribution is read rather than inferred. RC-1
    was caused by inferring it from Markdown that had no page markers.
    """
    from docling_core.types.doc import PictureItem, TableItem

    page_heights: dict[int, float] = {}
    for page_no, page in (getattr(document, "pages", {}) or {}).items():
        size = getattr(page, "size", None)
        if size is not None:
            page_heights[int(page_no)] = float(getattr(size, "height", 0) or 0)

    blocks: dict[int, list[dict[str, Any]]] = {}
    for item, _level in document.iterate_items():
        prov = list(getattr(item, "prov", []) or [])
        if not prov:
            continue
        page = int(getattr(prov[0], "page_no", 1) or 1)
        label = str(getattr(getattr(item, "label", ""), "value", getattr(item, "label", "")) or "")
        block: dict[str, Any] = {
            "type": "discarded" if label in _DOCLING_DISCARDED else _DOCLING_BLOCK_TYPES.get(label, "text"),
            "docling_label": label,
            "page": page,
            "bbox": _docling_bbox(prov[0], page_heights.get(page)),
        }
        if isinstance(item, TableItem):
            header, rows = _docling_table_grid(getattr(item, "data", None))
            if not header:
                continue
            block["table_headers"] = header
            block["table_rows"] = rows
            block["table_caption"] = _clean_text(item.caption_text(document) or "")
            block["text"] = block["table_caption"]
        elif isinstance(item, PictureItem):
            block["image_caption"] = _clean_text(item.caption_text(document) or "")
            block["text"] = block["image_caption"]
        else:
            text = _clean_text(str(getattr(item, "text", "") or ""))
            if not text:
                continue
            block["text"] = text
            if block["type"] == "equation":
                block["latex"] = text
            if block["type"] == "heading":
                # ``level`` is what the bundle turns into section nesting.
                block["text_level"] = int(getattr(item, "level", 1) or 1)
        blocks.setdefault(page, []).append(block)
    return blocks


def _write_docling_figures(document: Any, assets_dir: Path) -> list[dict[str, Any]]:
    """Save every picture the document carries, with its own page and caption.

    Docling renders a crop of the page region, so a chart drawn as vector paths
    comes out as an image just like an embedded photograph. That removes the
    separate vector-figure detector the PyMuPDF path needed, and with it the
    rejection reasons ("not-placed-on-page", "no-embedded-image-data") that
    discarded valid figures.
    """
    from docling_core.types.doc import PictureItem

    page_heights: dict[int, float] = {}
    for page_no, page in (getattr(document, "pages", {}) or {}).items():
        size = getattr(page, "size", None)
        if size is not None:
            page_heights[int(page_no)] = float(getattr(size, "height", 0) or 0)

    manifest: list[dict[str, Any]] = []
    for item, _level in document.iterate_items():
        if not isinstance(item, PictureItem):
            continue
        prov = list(getattr(item, "prov", []) or [])
        page = int(getattr(prov[0], "page_no", 1) or 1) if prov else 1
        try:
            image = item.get_image(document)
        except Exception:
            image = None
        if image is None:
            continue
        index = len(manifest) + 1
        filename = f"docling_figure_{index:03d}.png"
        destination = assets_dir / filename
        try:
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            image.save(destination, format="PNG")
        except (OSError, ValueError):
            continue
        manifest.append({
            "filename": filename,
            "source": "docling",
            "asset_id": f"src-figure-{index:03d}",
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "width": int(image.width),
            "height": int(image.height),
            "page": page,
            "bbox": _docling_bbox(prov[0], page_heights.get(page)) if prov else None,
            "caption": _clean_text(item.caption_text(document) or ""),
        })
    return manifest


def normalize_docling_document(
    result: Any,
    pdf_path: str | Path,
    sources_dir: str | Path,
    expected_page_count: int,
) -> NormalizedSource:
    """Write the shared source artifacts from a ``DoclingDocument``."""
    if not getattr(result, "success", False):
        raise ValueError(getattr(result, "failure_reason", None) or "Docling parse failed")
    document = getattr(result, "document", None)
    if document is None:
        raise ValueError("Docling parse returned no document")

    source_dir = Path(sources_dir)
    source_dir.mkdir(parents=True, exist_ok=True)
    blocks_by_page = _docling_blocks(document)
    page_count = max([expected_page_count, *blocks_by_page.keys()], default=expected_page_count)
    pages = [{"page": page, "blocks": blocks_by_page.get(page, [])} for page in range(1, page_count + 1)]

    tables: list[dict[str, Any]] = []
    for page in sorted(blocks_by_page):
        for block in blocks_by_page[page]:
            if block.get("type") != "table":
                continue
            headers = block.get("table_headers") or []
            rows = block.get("table_rows") or []
            tables.append({
                "table_id": f"src-table-{len(tables) + 1:03d}",
                "page": page,
                "caption": block.get("table_caption", ""),
                "headers": headers,
                "rows": rows,
                "source_bbox": block.get("bbox"),
                "parser": "docling",
                # Spans are read from the model rather than parsed out of HTML,
                # so a reconstructed row is only ragged if the model said so.
                "validation_status": (
                    "valid"
                    if all(table_row_width(row) == table_row_width(headers) for row in rows)
                    else "needs_review"
                ),
                "raw_html": None,
            })

    markdown = ""
    if getattr(result, "markdown_path", None) and Path(result.markdown_path).is_file():
        markdown = Path(result.markdown_path).read_text(encoding="utf-8", errors="replace")
    if not markdown.strip():
        markdown = _markdown_from_blocks(blocks_by_page)

    assets_dir = source_dir / "source_files"
    assets_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = source_dir / "source.md"
    markdown_path.write_text(_normalize_markdown(markdown), encoding="utf-8")
    structure_path = source_dir / "source_structure.json"
    structure_path.write_text(json.dumps({
        "schema_version": "sunairum.source-structure/v1",
        "pages": pages,
        "parser": "docling",
        "parser_version": result.parser_version,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tables_path = source_dir / "source_tables.json"
    tables_path.write_text(json.dumps({
        "schema_version": "sunairum.source-tables/v1",
        "tables": tables,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    image_manifest = _write_docling_figures(document, assets_dir)
    image_manifest_path = assets_dir / "image_manifest.json"
    image_manifest_path.write_text(
        json.dumps(image_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    figure_count = len(image_manifest)
    return NormalizedSource(
        markdown_path=markdown_path,
        structure_path=structure_path,
        tables_path=tables_path,
        image_manifest_path=image_manifest_path,
        page_count=page_count,
        table_count=len(tables),
        figure_count=figure_count,
        diagnostics={
            "structure_source": "docling",
            "blocks_per_page": {str(page): len(blocks) for page, blocks in sorted(blocks_by_page.items())},
            "source_sha256": hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest(),
        },
    )


