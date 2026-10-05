"""Build one hash-bound evidence bundle from normalized PDF artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .grounding_models import (
    EvidenceItem,
    SectionNode,
    SourceAsset,
    SourceCell,
    SourceFormula,
    SourceTable,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _page_number(block: dict[str, Any], fallback: int) -> int:
    for key in ("page", "page_num", "page_number", "page_idx", "page_id"):
        value = block.get(key)
        if isinstance(value, int):
            return value + 1 if key in {"page_idx", "page_id"} else max(1, value)
        if isinstance(value, str) and value.isdigit():
            number = int(value)
            return number + 1 if key in {"page_idx", "page_id"} else max(1, number)
    return fallback


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        return [float(value[index]) for index in range(4)]
    except (TypeError, ValueError):
        return None


def _block_kind(block: dict[str, Any]) -> str:
    raw = str(block.get("type") or block.get("category") or block.get("label") or "other").lower()
    if "table_caption" in raw:
        return "table_caption"
    if "table" in raw:
        return "table"
    if "equation" in raw or "formula" in raw:
        return "formula"
    if "image" in raw or "figure" in raw or "picture" in raw:
        return "figure"
    if "reference" in raw or "bibliograph" in raw:
        return "reference"
    if "list" in raw:
        return "list"
    if "text" in raw and block.get("text_level"):
        return "heading"
    if "title" in raw or "heading" in raw:
        return "heading"
    if "text" in raw or "paragraph" in raw:
        return "paragraph"
    return "other"


def _block_text(block: dict[str, Any]) -> str:
    for key in ("text", "content", "latex", "markdown", "caption", "table_caption"):
        value = block.get(key)
        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        if isinstance(value, str) and value.strip():
            return re.sub(r"\s+", " ", value).strip()
    if isinstance(block.get("table_body"), str):
        return re.sub(r"\s+", " ", block["table_body"]).strip()
    return ""


def _section_id(title: str, index: int) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return f"sec-{token or 'document'}-{index:03d}"


def _normalize_cell_text(text: str) -> str:
    """Collapse OCR spacing inside numeric cells (``47 . 7 %`` → ``47.7%``)."""
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", value)
    value = re.sub(r"(?<=[+\-])\s+(?=\d)", "", value)
    value = re.sub(r"(?<=\d)\s+%", "%", value)
    return value


def _normalize_cell(value: Any, table_id: str, row: int, column: int) -> dict[str, Any]:
    if isinstance(value, dict):
        text = _normalize_cell_text(str(value.get("text") or value.get("content") or ""))
        rowspan = int(value.get("rowspan") or 1)
        colspan = int(value.get("colspan") or 1)
        cell_id = str(value.get("cell_id") or f"{table_id}-r{row:03d}-c{column:03d}")
    else:
        text = _normalize_cell_text(str(value or ""))
        rowspan = colspan = 1
        cell_id = f"{table_id}-r{row:03d}-c{column:03d}"
    return {
        "cell_id": cell_id,
        "text": text,
        "rowspan": max(1, rowspan),
        "colspan": max(1, colspan),
    }


def _source_table_records(
    payload: dict[str, Any],
    source_pdf_sha256: str,
    parser: str,
    parser_version: str,
    section_by_page: dict[int, str],
) -> tuple[list[dict[str, Any]], list[EvidenceItem]]:
    records: list[dict[str, Any]] = []
    evidence: list[EvidenceItem] = []
    for index, raw in enumerate(payload.get("tables", []) if isinstance(payload, dict) else [], start=1):
        if not isinstance(raw, dict):
            continue
        table_id = str(raw.get("table_id") or f"table-{index:03d}")
        page_start = int(raw.get("page_start") or raw.get("page") or 1)
        page_end = int(raw.get("page_end") or page_start)
        raw_headers = raw.get("headers") or []
        raw_rows = raw.get("rows") or []
        headers = [_normalize_cell(cell, table_id, 0, col) for col, cell in enumerate(raw_headers, start=1)]
        rows = [
            [_normalize_cell(cell, table_id, row_index, col) for col, cell in enumerate(row, start=1)]
            for row_index, row in enumerate(raw_rows, start=1)
            if isinstance(row, list)
        ]
        table_payload = {"headers": headers, "rows": rows}
        table_hash = _sha256_bytes(json.dumps(table_payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        evidence_id = str(raw.get("evidence_id") or f"ev-page-{page_start:02d}-table-{index:03d}")
        section_id = raw.get("section_id") or section_by_page.get(page_start)
        record = {
            "table_id": table_id,
            "evidence_id": evidence_id,
            "section_id": section_id,
            "page_start": page_start,
            "page_end": page_end,
            "caption": str(raw.get("caption") or ""),
            "caption_evidence_id": raw.get("caption_evidence_id"),
            "headers": headers,
            "rows": rows,
            "source_bbox": _bbox(raw.get("source_bbox")),
            "source_pdf_sha256": source_pdf_sha256,
            "table_sha256": table_hash,
            "validation_status": raw.get("validation_status", "needs_review"),
            "parser": parser,
            "parser_version": parser_version,
        }
        records.append(record)
        evidence.append(EvidenceItem(
            evidence_id=evidence_id,
            kind="table",
            page_start=page_start,
            page_end=page_end,
            bbox=record["source_bbox"],
            section_id=section_id,
            text=record["caption"],
            text_sha256=_sha256_bytes(record["caption"].encode("utf-8")),
            source_pdf_sha256=source_pdf_sha256,
            parser=parser,
            parser_version=parser_version,
        ))
    return records, evidence


def build_evidence_bundle(project_dir: str | Path) -> dict[str, Any]:
    """Enrich normalized parser artifacts and write the evidence bundle."""
    project = Path(project_dir)
    sources = project / "sources"
    parser_manifest = _read_json(sources / "parser_manifest.json", {})
    source_pdf_sha256 = str(parser_manifest.get("source_pdf_sha256") or _sha256_file(project / "source.pdf") or "")
    parser_name = str(parser_manifest.get("parser_selected") or "unknown")
    parser_version = str(parser_manifest.get("parser_version") or "unknown")
    structure_path = sources / "source_structure.json"
    structure = _read_json(structure_path, {"pages": []})
    pages = structure.get("pages", []) if isinstance(structure, dict) else []

    raw_sections: list[dict[str, Any]] = []
    section_by_page: dict[int, str] = {}
    current_section: dict[str, Any] | None = None
    evidence_items: list[dict[str, Any]] = []
    enriched_pages: list[dict[str, Any]] = []
    section_index = 0
    block_index = 0
    for page_entry in pages if isinstance(pages, list) else []:
        if not isinstance(page_entry, dict):
            continue
        page_number = int(page_entry.get("page") or len(enriched_pages) + 1)
        enriched_blocks: list[dict[str, Any]] = []
        for block in page_entry.get("blocks", []) if isinstance(page_entry.get("blocks"), list) else []:
            if not isinstance(block, dict):
                continue
            block_index += 1
            kind = _block_kind(block)
            text = _block_text(block)
            if kind == "heading" and text:
                section_index += 1
                level = int(block.get("text_level") or block.get("level") or 1)
                if re.match(r"^[A-Z][.)]", text) or re.match(r"^\d+(?:\.\d+)*[.)]?\s", text):
                    level = max(2, level)
                current_section = {
                    "section_id": _section_id(text, section_index),
                    "title": text,
                    "level": max(1, level),
                    "parent_section_id": None,
                    "page_start": page_number,
                    "page_end": page_number,
                    "evidence_ids": [],
                    "child_section_ids": [],
                }
                raw_sections.append(current_section)
            if current_section is not None:
                current_section["page_end"] = max(current_section["page_end"], page_number)
                section_by_page.setdefault(page_number, current_section["section_id"])
            evidence_id = str(block.get("evidence_id") or f"ev-page-{page_number:02d}-block-{block_index:03d}")
            section_id = str(block.get("section_id") or (current_section["section_id"] if current_section else "sec-document-000"))
            block_copy = dict(block)
            block_copy.update({"evidence_id": evidence_id, "section_id": section_id, "type": kind})
            enriched_blocks.append(block_copy)
            evidence_items.append(EvidenceItem(
                evidence_id=evidence_id,
                kind=kind if kind in {"heading", "paragraph", "list", "formula", "table", "table_caption", "figure", "figure_caption", "reference"} else "other",
                page_start=page_number,
                page_end=page_number,
                bbox=_bbox(block.get("bbox") or block.get("box")),
                section_id=section_id,
                text=text,
                text_sha256=_sha256_bytes(text.encode("utf-8")),
                source_pdf_sha256=source_pdf_sha256,
                parser=parser_name,
                parser_version=parser_version,
            ).model_dump(mode="json"))
            if current_section is not None and evidence_id not in current_section["evidence_ids"]:
                current_section["evidence_ids"].append(evidence_id)
        enriched_pages.append({"page": page_number, "blocks": enriched_blocks})

    if not raw_sections:
        raw_sections.append({
            "section_id": "sec-document-000",
            "title": "Document",
            "level": 1,
            "parent_section_id": None,
            "page_start": 1,
            "page_end": max(1, len(enriched_pages)),
            "evidence_ids": [item["evidence_id"] for item in evidence_items],
            "child_section_ids": [],
        })

    # Establish simple heading hierarchy from levels.
    stack: list[dict[str, Any]] = []
    for section in raw_sections:
        while stack and stack[-1]["level"] >= section["level"]:
            stack.pop()
        if stack:
            section["parent_section_id"] = stack[-1]["section_id"]
            stack[-1]["child_section_ids"].append(section["section_id"])
        stack.append(section)
    for page_number, section_id in list(section_by_page.items()):
        candidates = [section for section in raw_sections if section["page_start"] <= page_number <= section["page_end"]]
        if candidates:
            section_by_page[page_number] = candidates[-1]["section_id"]

    table_payload = _read_json(sources / "source_tables.json", {"tables": []})
    table_records, table_evidence = _source_table_records(
        table_payload, source_pdf_sha256, parser_name, parser_version, section_by_page
    )
    existing_ids = {item["evidence_id"] for item in evidence_items}
    evidence_items.extend(item.model_dump(mode="json") for item in table_evidence if item.evidence_id not in existing_ids)

    assets_payload = _read_json(sources / "pdf_images" / "source_asset_manifest.json", {})
    assets: list[dict[str, Any]] = []
    for index, raw in enumerate(assets_payload.get("figures", []) if isinstance(assets_payload, dict) else [], start=1):
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("id") or f"pdf-asset-{index:03d}")
        asset = {
            "asset_id": asset_id,
            "file": str(raw.get("file") or ""),
            "source_type": "pdf_vector" if raw.get("source_type") == "pdf_vector" else "pdf_raster",
            "page": int(raw.get("page") or 1),
            "source_pdf_sha256": source_pdf_sha256,
            "sha256": str(raw.get("sha256") or ""),
            "width": raw.get("width"),
            "height": raw.get("height"),
            "placed_ratio": raw.get("placed_ratio") or raw.get("ratio"),
            "bbox": _bbox(raw.get("bbox")),
            "caption_evidence_id": raw.get("caption_evidence_id"),
            "source_asset_links": list(raw.get("source_asset_links") or []),
            "status": raw.get("status", "verified"),
        }
        caption_text = re.sub(r"\s+", " ", str(raw.get("caption_text") or "")).strip().casefold()
        if caption_text and not asset.get("caption_evidence_id"):
            page_number = int(asset.get("page") or 1)
            for evidence_item in evidence_items:
                if (
                    int(evidence_item.get("page_start") or 1) == page_number
                    and caption_text == re.sub(r"\s+", " ", str(evidence_item.get("text") or "")).strip().casefold()
                ):
                    asset["caption_evidence_id"] = evidence_item.get("evidence_id")
                    break
        assets.append(asset)

    formulas: list[dict[str, Any]] = []
    for item in evidence_items:
        if item["kind"] != "formula" or not item.get("text"):
            continue
        formulas.append(SourceFormula(
            formula_id=item["evidence_id"].replace("ev-", "formula-", 1),
            evidence_id=item["evidence_id"],
            section_id=item.get("section_id"),
            page=item["page_start"],
            latex=item["text"],
            source_pdf_sha256=source_pdf_sha256,
            rendering_status="available",
        ).model_dump(mode="json"))

    _write_json(structure_path, {
        **(structure if isinstance(structure, dict) else {}),
        "schema_version": "sunairum.source-structure/v2",
        "source_pdf_sha256": source_pdf_sha256,
        "parser": parser_name,
        "parser_version": parser_version,
        "pages": enriched_pages,
    })
    _write_json(sources / "source_sections.json", {
        "schema_version": "sunairum.source-sections/v1",
        "source_pdf_sha256": source_pdf_sha256,
        "sections": raw_sections,
    })
    _write_json(sources / "source_tables.json", {
        "schema_version": "sunairum.source-tables/v2",
        "source_pdf_sha256": source_pdf_sha256,
        "tables": table_records,
    })
    _write_json(sources / "source_formulas.json", {
        "schema_version": "sunairum.source-formulas/v1",
        "source_pdf_sha256": source_pdf_sha256,
        "formulas": formulas,
    })
    _write_json(sources / "source_assets.json", {
        "schema_version": "sunairum.source-assets/v2",
        "source_pdf_sha256": source_pdf_sha256,
        "assets": assets,
    })
    _write_json(sources / "source_evidence.json", {
        "schema_version": "sunairum.source-evidence/v1",
        "source_pdf_sha256": source_pdf_sha256,
        "evidence": evidence_items,
    })

    parser_hash = _sha256_file(sources / "parser_manifest.json") or ""
    evidence_manifest = {
        "schema_version": "sunairum.evidence-manifest/v1",
        "source_pdf_sha256": source_pdf_sha256,
        "parser_manifest_sha256": parser_hash,
        "sections": [section["section_id"] for section in raw_sections],
        "evidence_count": len(evidence_items),
        "table_count": len(table_records),
        "formula_count": len(formulas),
        "asset_count": len(assets),
        "evidence_file": "source_evidence.json",
    }
    bundle_basis = json.dumps({
        "evidence": evidence_items,
        "sections": raw_sections,
        "tables": table_records,
        "formulas": formulas,
        "assets": assets,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")
    evidence_manifest["bundle_sha256"] = _sha256_bytes(bundle_basis)
    _write_json(sources / "evidence_manifest.json", evidence_manifest)
    return {
        "manifest": evidence_manifest,
        "evidence": evidence_items,
        "sections": raw_sections,
        "tables": table_records,
        "formulas": formulas,
        "assets": assets,
    }
