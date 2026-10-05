"""Coordinate primary parsing, quality validation, and fallback.

Docling is the only backend. ``SOURCE_PARSER`` is kept as an explicit selector
rather than being inlined, because the fallback is a second Docling pass with
different options and the manifest has to record which one produced the output.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

try:
    from .docling_parser import parse_pdf_with_docling
    from .pdf_pages import count_pdf_pages
    from .source_normalizer import normalize_docling_document
    from .source_quality import evaluate_source_quality
except ImportError:  # pragma: no cover - supports direct imports from /app/tasks
    from docling_parser import parse_pdf_with_docling
    from pdf_pages import count_pdf_pages
    from source_normalizer import normalize_docling_document
    from source_quality import evaluate_source_quality


SUPPORTED_PARSERS = ("docling",)
DEFAULT_PARSER = "docling"
FALLBACK_PARSER = "docling_ocr"


def configured_parser() -> str:
    value = os.getenv("SOURCE_PARSER", DEFAULT_PARSER).strip().lower()
    return value if value in SUPPORTED_PARSERS else DEFAULT_PARSER


def _run_parser(name: str, pdf: Path, raw_dir: Path, timeout: int) -> Any:
    return parse_pdf_with_docling(str(pdf), str(raw_dir), timeout)


def _normalize(name: str, result: Any, pdf: Path, sources_dir: Path, pages: int) -> Any:
    return normalize_docling_document(result, pdf, sources_dir, pages)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _page_count(path: Path) -> int:
    return count_pdf_pages(path)


def _write_manifest(sources_dir: Path, payload: dict[str, Any]) -> Path:
    path = sources_dir / "parser_manifest.json"
    _atomic_json(path, payload)
    return path


def update_parser_manifest(project_dir: str | Path, *, figures: list[dict[str, Any]] | None = None) -> Path | None:
    """Update post-provenance figure counts without changing parser identity."""
    path = Path(project_dir) / "sources" / "parser_manifest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if figures is not None:
        payload.setdefault("figures", {})["provenance_verified"] = len(figures)
        payload["figures"]["detected"] = max(payload["figures"].get("detected", 0), len(figures))
    _atomic_json(path, payload)
    return path


def parse_project_pdf(
    project_dir: str | Path,
    pdf_path: str | Path,
    *,
    project_manager: Any | None = None,
) -> dict[str, Any]:
    """Parse one project PDF and return the upload-facing parser summary."""
    started = time.time()
    project = Path(project_dir).resolve()
    pdf = Path(pdf_path).resolve()
    if pdf.suffix.lower() != ".pdf":
        raise ValueError("Source parser accepts PDF files only")
    if not pdf.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf}")
    max_bytes = int(os.getenv("PDF_MAX_BYTES", str(50 * 1024 * 1024)))
    if pdf.stat().st_size > max_bytes:
        raise ValueError(f"PDF exceeds configured size limit ({max_bytes} bytes)")
    pages = _page_count(pdf)
    max_pages = int(os.getenv("PDF_MAX_PAGES", "1000"))
    if pages > max_pages:
        raise ValueError(f"PDF exceeds configured page limit ({max_pages})")

    sources_dir = project / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    requested = configured_parser()
    raw_dir = sources_dir / requested
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    source_digest = _source_hash(pdf)
    timeout = int(os.getenv("SOURCE_PARSER_TIMEOUT_SECONDS", "900"))
    parsed = _run_parser(requested, pdf, raw_dir, timeout)
    _atomic_json(raw_dir / "diagnostics.json", {
        "success": parsed.success,
        "parser_version": parsed.parser_version,
        "failure_reason": parsed.failure_reason,
        "diagnostics": parsed.diagnostics,
    })
    quality: dict[str, Any] = {}
    selected = requested
    fallback_used = False
    fallback_reason: str | None = None
    table_count = 0
    figure_count = 0

    if parsed.success:
        try:
            normalized = _normalize(requested, parsed, pdf, sources_dir, pages)
            quality = evaluate_source_quality(
                sources_dir,
                pages,
                parser_page_count=parsed.page_count,
            )
            if quality.get("accepted"):
                shutil.copy2(pdf, sources_dir / "source.pdf")
                table_count = normalized.table_count
                figure_count = normalized.figure_count
                if project_manager is not None:
                    project_manager._propagate_companion_image_assets(normalized.markdown_path, project)  # noqa: SLF001
            else:
                fallback_reason = f"{requested} quality gate failed: " + "; ".join(quality.get("errors", []))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            fallback_reason = f"{requested} output normalization failed: {exc}"
    else:
        fallback_reason = parsed.failure_reason or f"{requested} failed without a reason"

    parser_version = parsed.parser_version

    if fallback_reason is not None:
        # The fallback is a genuine second attempt rather than a downgrade: the
        # same engine runs again with OCR forced on, which is what rescues a
        # scanned or partly-scanned PDF. The old fallback re-extracted the text
        # layer with PyMuPDF, which cannot help when there is no text layer.
        selected = FALLBACK_PARSER
        fallback_used = True
        retry_dir = sources_dir / FALLBACK_PARSER
        if retry_dir.exists():
            shutil.rmtree(retry_dir)
        retry_dir.mkdir(parents=True, exist_ok=True)
        for stale in (
            sources_dir / "source.pdf",
            sources_dir / "source.md",
            sources_dir / "source_structure.json",
            sources_dir / "source_tables.json",
        ):
            stale.unlink(missing_ok=True)
        stale_assets = sources_dir / "source_files"
        if stale_assets.exists():
            shutil.rmtree(stale_assets)
        retry = parse_pdf_with_docling(str(pdf), str(retry_dir), timeout, force_ocr=True)
        _atomic_json(retry_dir / "diagnostics.json", {
            "success": retry.success,
            "parser_version": retry.parser_version,
            "failure_reason": retry.failure_reason,
            "diagnostics": retry.diagnostics,
        })
        if not retry.success:
            raise RuntimeError(
                f"OCR retry failed after {fallback_reason}: {retry.failure_reason}"
            )
        normalized = normalize_docling_document(retry, pdf, sources_dir, pages)
        quality = evaluate_source_quality(sources_dir, pages, parser_page_count=retry.page_count)
        if not quality.get("accepted"):
            raise RuntimeError(
                "OCR retry failed the source quality gate: " + "; ".join(quality.get("errors", []))
            )
        table_count = normalized.table_count
        figure_count = normalized.figure_count
        parser_version = retry.parser_version
        shutil.copy2(pdf, sources_dir / "source.pdf")

    manifest = {
        "schema_version": "sunairum.parser-manifest/v1",
        "parser_requested": requested,
        "parser_selected": selected,
        "parser_version": parser_version,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "source_pdf_sha256": source_digest,
        "page_count": pages,
        "text_quality": quality.get("text_quality", {}),
        "tables": {
            "detected": table_count,
            "structured": quality.get("tables", {}).get("structured", table_count),
        },
        "figures": {"detected": figure_count, "provenance_verified": 0},
        "quality": quality,
        "parser_diagnostics": parsed.diagnostics,
        "started_at": started,
        "completed_at": time.time(),
        "duration_seconds": round(time.time() - started, 3),
    }
    manifest_path = _write_manifest(sources_dir, manifest)
    copied_source = sources_dir / "source.pdf"
    if not copied_source.is_file() or _source_hash(copied_source) != source_digest:
        raise RuntimeError("normalized sources/source.pdf does not match the uploaded source.pdf")
    return {
        "parser_requested": requested,
        "parser_selected": selected,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "pages": pages,
        "tables_found": table_count,
        "figures_found": figure_count,
        "markdown_path": str(normalized.markdown_path),
        "parser_manifest": str(manifest_path),
        "quality": quality,
    }
