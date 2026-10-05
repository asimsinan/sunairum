"""Adapter for the Docling PDF parser.

Docling runs in-process rather than behind an HTTP sidecar: its models are
small enough to live in the worker image, so the parse is a library call and
the failure modes are ordinary Python exceptions. Import is still lazy, because
the FastAPI process must stay usable when the models or the package are absent.

``DocumentConverter`` (and its weights) are cached once per worker process and
pipeline config. Celery prefork children each warm their own converter on the
first upload; later uploads reuse it instead of reloading Transformers/TableFormer.

There is deliberately no timeout implemented here. An in-process parse cannot be
interrupted safely from a watchdog thread, and Celery already bounds it: the
``source_import`` queue inherits ``task_time_limit`` from :mod:`worker`, and
``mark_generation_failure`` records a terminal ``source_error`` when it fires.

Semantic normalization lives in :mod:`source_normalizer`; this module only runs
the converter and reports what it produced.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Process-local converter cache: one DocumentConverter per distinct pipeline key.
_converter_lock = threading.Lock()
_converters: dict[tuple[Any, ...], Any] = {}


@dataclass
class DoclingParseResult:
    """Execution result mirroring the shape the source coordinator expects.

    ``document`` carries the in-memory ``DoclingDocument``. Unlike MinerU, whose
    output had to be rediscovered from files on disk, Docling hands back a typed
    document whose items already know their page and bounding box, so the
    normalizer reads the object and the files are written for diagnostics only.
    """

    success: bool
    parser_version: str | None
    output_dir: str
    document: Any | None = None
    markdown_path: str | None = None
    json_path: str | None = None
    page_count: int | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _quiet_torch_dynamo() -> None:
    """Silence torch.compile graph-break warnings raised by the layout model.

    Docling compiles its RT-DETR layout model, and transformers guards a shape
    invariant there with ``torch._check_tensor_all``, which Dynamo cannot trace.
    Each break logs a ~20 line traceback and then runs that region eagerly, so
    the parse is still correct and the output is pure noise — about 40 stderr
    lines per document, which buries real worker errors.

    Compilation itself is left on. Measured on one page: it costs ~9s once per
    worker process and then parses in ~1.9s against ~2.2s uncompiled, so a
    long-lived worker comes out ahead. Set ``DOCLING_VERBOSE_COMPILE=1`` to see
    the warnings again, or ``DOCLING_INFERENCE_COMPILE_TORCH_MODELS=0`` to skip
    compilation and its one-time cost.
    """
    if _flag("DOCLING_VERBOSE_COMPILE", False):
        return
    logging.getLogger("torch._dynamo").setLevel(logging.ERROR)


def _accelerator_device(name: str):
    from docling.datamodel.pipeline_options import AcceleratorDevice

    requested = os.getenv("DOCLING_DEVICE", name).strip().lower()
    mapping = {
        "cpu": AcceleratorDevice.CPU,
        "cuda": AcceleratorDevice.CUDA,
        "mps": AcceleratorDevice.MPS,
        "auto": AcceleratorDevice.AUTO,
    }
    return mapping.get(requested, AcceleratorDevice.CPU)


def build_pipeline_options(*, force_ocr: bool = False):
    """Assemble the PDF pipeline options from configuration.

    Defaults are chosen for the grounded pipeline rather than for speed:
    ``generate_page_images`` is required for ``PictureItem.get_image`` to return
    anything, and ``images_scale`` sets the DPI of every extracted figure at
    ``scale x 72``.
    """
    from docling.datamodel.pipeline_options import (
        AcceleratorOptions,
        PdfPipelineOptions,
        TableFormerMode,
    )

    options = PdfPipelineOptions()
    options.accelerator_options = AcceleratorOptions(device=_accelerator_device("cpu"))
    options.images_scale = float(os.getenv("DOCLING_IMAGES_SCALE", "3.0"))
    options.generate_page_images = True
    options.generate_picture_images = True
    options.do_table_structure = True
    # Off by default because it dominates the parse: on a 6-page paper the same
    # document takes 42s without it and 1098s with it, a 26x cost for the LaTeX of
    # three equations. Enrichment runs a vision model autoregressively over every
    # formula region, which is unavoidably slow on CPU. Formula-dense sources are
    # not the target corpus; set DOCLING_FORMULA_ENRICHMENT=1 when they are.
    # Without it formulas are still located, but carry no text and are therefore
    # dropped from the evidence rather than surfacing as empty claims.
    options.do_formula_enrichment = _flag("DOCLING_FORMULA_ENRICHMENT", False)
    options.do_ocr = force_ocr or _flag("DOCLING_OCR", False)
    if options.do_table_structure:
        mode = os.getenv("DOCLING_TABLE_MODE", "accurate").strip().lower()
        options.table_structure_options.mode = (
            TableFormerMode.FAST if mode == "fast" else TableFormerMode.ACCURATE
        )
    return options


def _version() -> str:
    """Report the installed Docling version for the parser manifest.

    The distribution is ``docling-slim``; asking for ``docling`` records
    ``"unknown"`` in every manifest, which destroys the audit trail the manifest
    exists for. Both names are queried because either can be installed.
    """
    from importlib.metadata import PackageNotFoundError, version

    for distribution in ("docling-slim", "docling"):
        try:
            return version(distribution)
        except PackageNotFoundError:
            continue
        except Exception:  # pragma: no cover - metadata is absent in odd installs
            break
    return "unknown"


def _failure(output_dir: Path, reason: str, **diagnostics: Any) -> DoclingParseResult:
    return DoclingParseResult(
        success=False,
        parser_version=None,
        output_dir=str(output_dir),
        diagnostics=diagnostics,
        failure_reason=reason,
    )


def _converter_cache_key(*, force_ocr: bool) -> tuple[Any, ...]:
    """Stable key for pipeline options that change which models Docling loads."""
    return (
        bool(force_ocr or _flag("DOCLING_OCR", False)),
        os.getenv("DOCLING_DEVICE", "cpu").strip().lower(),
        float(os.getenv("DOCLING_IMAGES_SCALE", "3.0")),
        _flag("DOCLING_FORMULA_ENRICHMENT", False),
        os.getenv("DOCLING_TABLE_MODE", "accurate").strip().lower(),
        _flag("DOCLING_INFERENCE_COMPILE_TORCH_MODELS", True),
    )


def clear_document_converter_cache() -> None:
    """Drop cached converters (tests / after env changes in-process)."""
    with _converter_lock:
        _converters.clear()


def get_document_converter(*, force_ocr: bool = False) -> tuple[Any, bool]:
    """Return ``(DocumentConverter, cache_hit)`` for the active pipeline config."""
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption

    key = _converter_cache_key(force_ocr=force_ocr)
    with _converter_lock:
        cached = _converters.get(key)
        if cached is not None:
            return cached, True
        # Before first convert(), which is where the layout model is built/compiled.
        _quiet_torch_dynamo()
        options = build_pipeline_options(force_ocr=force_ocr)
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        _converters[key] = converter
        return converter, False


def parse_pdf_with_docling(
    pdf_path: str,
    output_dir: str,
    timeout_seconds: int | None = None,
    *,
    force_ocr: bool = False,
) -> DoclingParseResult:
    """Convert one PDF and return the document plus on-disk diagnostics."""
    pdf = Path(pdf_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not pdf.is_file():
        return _failure(output, f"PDF does not exist: {pdf}")
    if os.getenv("DOCLING_MODE", "auto").strip().lower() == "disabled":
        return _failure(output, "Docling disabled by DOCLING_MODE=disabled")

    started = time.time()
    diagnostics: dict[str, Any] = {
        "transport": "in-process",
        "force_ocr": force_ocr,
        "budget_seconds": timeout_seconds,
    }
    try:
        options = build_pipeline_options(force_ocr=force_ocr)
        diagnostics.update({
            "images_scale": options.images_scale,
            "do_ocr": options.do_ocr,
            "do_formula_enrichment": options.do_formula_enrichment,
            "table_mode": str(getattr(options.table_structure_options, "mode", "")),
        })
        converter, cache_hit = get_document_converter(force_ocr=force_ocr)
        diagnostics["converter_cached"] = cache_hit
        conversion = converter.convert(str(pdf))
        document = conversion.document
    except ImportError as exc:
        return _failure(output, f"Docling is not installed: {exc}", **diagnostics)
    except Exception as exc:
        return _failure(output, f"Docling conversion failed: {exc}", **diagnostics)

    diagnostics["duration_seconds"] = round(time.time() - started, 3)
    markdown_path = output / "source.md"
    json_path = output / "docling_document.json"
    try:
        markdown_path.write_text(document.export_to_markdown(), encoding="utf-8")
        json_path.write_text(
            json.dumps(document.export_to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except (OSError, ValueError, TypeError) as exc:
        # The document itself is still usable; only the diagnostics copy failed.
        diagnostics["artifact_write_error"] = str(exc)

    return DoclingParseResult(
        success=True,
        parser_version=_version(),
        output_dir=str(output),
        document=document,
        markdown_path=str(markdown_path) if markdown_path.is_file() else None,
        json_path=str(json_path) if json_path.is_file() else None,
        page_count=len(getattr(document, "pages", {}) or {}) or None,
        diagnostics=diagnostics,
    )
