"""Extract PDF figures and retain provenance links for source assets."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _caption_candidates(project_dir: Path, page_number: int) -> list[dict[str, Any]]:
    structure = _read_json(project_dir / "sources" / "source_structure.json", {})
    candidates: list[dict[str, Any]] = []
    for page in structure.get("pages", []) if isinstance(structure, dict) else []:
        if not isinstance(page, dict) or int(page.get("page") or 1) != page_number:
            continue
        for block in page.get("blocks", []) if isinstance(page.get("blocks"), list) else []:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or block.get("category") or block.get("label") or "").casefold()
            text = str(block.get("text") or block.get("content") or block.get("caption") or "").strip()
            if text and ("caption" in kind or re.match(r"^(?:figure|fig\.?|chart)\s*[\dIVX]", text, re.I)):
                candidates.append({"text": text, "bbox": block.get("bbox") or block.get("box")})
    return candidates


def _selected_parser(project_dir: Path) -> str:
    manifest = _read_json(project_dir / "sources" / "parser_manifest.json", {})
    if isinstance(manifest, dict):
        return str(manifest.get("parser_selected") or "")
    return ""


def _extract_docling_figures(project: Path, out_dir: Path) -> list[dict[str, Any]]:
    """Promote the figures Docling already extracted into the shared shape.

    The parser wrote each picture during normalization, when the document was
    still in memory, together with the page and bounding box the document itself
    reported. Nothing has to be re-derived from the PDF here, so there is no
    detection step and therefore no rejection step.
    """
    manifest = _read_json(project / "sources" / "source_files" / "image_manifest.json", [])
    if not isinstance(manifest, list):
        return []
    figures: list[dict[str, Any]] = []
    for entry in manifest:
        if not isinstance(entry, dict):
            continue
        source_path = project / "sources" / "source_files" / str(entry.get("filename") or "")
        if not source_path.is_file():
            continue
        page = int(entry.get("page") or 1)
        filename = f"fig_{len(figures) + 1:02d}.png"
        shutil.copy2(source_path, out_dir / filename)
        width = int(entry.get("width") or 0)
        height = int(entry.get("height") or 0)
        bbox = entry.get("bbox")
        placed_width = float(bbox[2] - bbox[0]) if isinstance(bbox, list) and len(bbox) >= 4 else float(width)
        placed_height = float(bbox[3] - bbox[1]) if isinstance(bbox, list) and len(bbox) >= 4 else float(height)
        figures.append({
            "id": f"pdf-page-{page}-picture-{len(figures) + 1}",
            "xref": None,
            "file": filename,
            "sha256": str(entry.get("sha256") or ""),
            "width": width,
            "height": height,
            "intrinsic_width": width,
            "intrinsic_height": height,
            "intrinsic_ratio": round(width / max(height, 1), 4),
            "ratio": round(placed_width / max(placed_height, 1.0), 3),
            "placed_ratio": round(placed_width / max(placed_height, 1.0), 3),
            "placed_width": placed_width,
            "placed_height": placed_height,
            "page": page,
            "bbox": bbox,
            "placements": [{
                "page": page,
                "bbox": bbox,
                "width": placed_width,
                "height": placed_height,
                "ratio": round(placed_width / max(placed_height, 1.0), 4),
            }] if bbox else [],
            # Docling links the caption to the figure itself, so this no longer
            # depends on matching a "Figure N" regex against nearby text.
            "caption_text": str(entry.get("caption") or ""),
        })
    return figures


def _attach_caption_metadata(project_dir: Path, figures: list[dict[str, Any]]) -> None:
    for figure in figures:
        page_number = int(figure.get("page") or 1)
        candidates = _caption_candidates(project_dir, page_number)
        if not candidates:
            continue
        figure["caption_text"] = candidates[0]["text"]
        figure["caption_bbox"] = candidates[0].get("bbox")


# Docling renders a crop of the page rather than lifting the embedded original,
# so resolution is a function of ``images_scale`` and can silently degrade if
# that is lowered. A figure narrower than this looks soft on a 1280px slide.
MIN_FIGURE_PIXEL_WIDTH = 600


def _low_resolution(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": figure.get("id"), "page": figure.get("page"), "width": int(figure.get("width") or 0)}
        for figure in figures
        if 0 < int(figure.get("width") or 0) < MIN_FIGURE_PIXEL_WIDTH
    ]


def _write_figure_index(out_dir: Path, figures: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> None:
    soft = _low_resolution(figures)
    (out_dir / "index.json").write_text(
        json.dumps(
            {
                "figures": figures,
                "detected": len(figures) + len(rejected),
                "provenance_verified": len(figures),
                "rejected": rejected,
                "low_resolution": soft,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if soft:
        print(f"{len(soft)} figure(s) below {MIN_FIGURE_PIXEL_WIDTH}px wide: {soft}")


def _build_manifest(pdf_path: Path, figures: list[dict[str, Any]], out_dir: Path) -> None:
    try:
        from tasks.visual_validation import build_pdf_figure_manifest
    except ImportError:  # pragma: no cover - supports direct task imports
        from visual_validation import build_pdf_figure_manifest
    build_pdf_figure_manifest(str(pdf_path), figures, str(out_dir))


def extract_pdf_figures(project_dir: str | Path) -> list[dict[str, Any]]:
    """Collect the figures the parser found, with their page and caption.

    This used to re-derive figures from the PDF: raster images were lifted by
    xref and vector artwork was found by a separate geometry detector, then both
    had to be placed back onto a page. The parser already reports all of that,
    so the work here is promotion rather than detection.
    """
    project = Path(project_dir)
    pdf_path = project / "source.pdf"
    out_dir = project / "sources" / "pdf_images"
    if not pdf_path.is_file():
        return []
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    figures = _extract_docling_figures(project, out_dir)
    _attach_caption_metadata(project, figures)
    _write_figure_index(out_dir, figures, [])
    _build_manifest(pdf_path, figures, out_dir)
    print(f"Extracted {len(figures)} figure(s) from the parsed document")
    return figures
