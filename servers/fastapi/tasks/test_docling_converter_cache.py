"""DocumentConverter is reused across PDF parses in one process."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tasks.docling_parser import (
    clear_document_converter_cache,
    get_document_converter,
    parse_pdf_with_docling,
)


@pytest.fixture(autouse=True)
def _reset_converter_cache():
    clear_document_converter_cache()
    yield
    clear_document_converter_cache()


def _install_fake_docling(converter_factory):
    """Stub docling imports used by get_document_converter (no real package needed)."""
    docling = ModuleType("docling")
    datamodel = ModuleType("docling.datamodel")
    base_models = ModuleType("docling.datamodel.base_models")
    base_models.InputFormat = SimpleNamespace(PDF="pdf")
    document_converter = ModuleType("docling.document_converter")
    document_converter.DocumentConverter = converter_factory
    document_converter.PdfFormatOption = lambda **kwargs: kwargs

    pipeline_options = ModuleType("docling.datamodel.pipeline_options")
    pipeline_options.AcceleratorDevice = SimpleNamespace(
        CPU="cpu", CUDA="cuda", MPS="mps", AUTO="auto"
    )
    pipeline_options.AcceleratorOptions = lambda **kwargs: SimpleNamespace(**kwargs)
    pipeline_options.PdfPipelineOptions = lambda: SimpleNamespace(
        accelerator_options=None,
        images_scale=3.0,
        generate_page_images=True,
        generate_picture_images=True,
        do_table_structure=True,
        do_formula_enrichment=False,
        do_ocr=False,
        table_structure_options=SimpleNamespace(mode="accurate"),
    )
    pipeline_options.TableFormerMode = SimpleNamespace(FAST="fast", ACCURATE="accurate")

    modules = {
        "docling": docling,
        "docling.datamodel": datamodel,
        "docling.datamodel.base_models": base_models,
        "docling.datamodel.pipeline_options": pipeline_options,
        "docling.document_converter": document_converter,
    }
    return patch.dict(sys.modules, modules)


def test_get_document_converter_reuses_instance():
    ctor = MagicMock(return_value=object())
    with _install_fake_docling(ctor):
        first, hit1 = get_document_converter(force_ocr=False)
        second, hit2 = get_document_converter(force_ocr=False)
    assert first is second
    assert hit1 is False
    assert hit2 is True
    assert ctor.call_count == 1


def test_force_ocr_uses_separate_cache_entry():
    ctor = MagicMock(side_effect=[object(), object()])
    with _install_fake_docling(ctor):
        a, _ = get_document_converter(force_ocr=False)
        b, _ = get_document_converter(force_ocr=True)
    assert a is not b
    assert ctor.call_count == 2


def test_parse_reuses_converter(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    out = tmp_path / "out"
    conversion = SimpleNamespace(
        document=SimpleNamespace(
            pages={1: object()},
            export_to_markdown=lambda: "# hi",
            export_to_dict=lambda: {"pages": 1},
        )
    )
    converter = MagicMock()
    converter.convert.return_value = conversion

    with patch(
        "tasks.docling_parser.get_document_converter",
        side_effect=[(converter, False), (converter, True)],
    ) as get_conv, patch(
        "tasks.docling_parser.build_pipeline_options",
        return_value=SimpleNamespace(
            images_scale=3.0,
            do_ocr=False,
            do_formula_enrichment=False,
            table_structure_options=SimpleNamespace(mode="accurate"),
        ),
    ):
        r1 = parse_pdf_with_docling(str(pdf), str(out / "a"))
        r2 = parse_pdf_with_docling(str(pdf), str(out / "b"))

    assert r1.success and r2.success
    assert r1.diagnostics["converter_cached"] is False
    assert r2.diagnostics["converter_cached"] is True
    assert get_conv.call_count == 2
    assert converter.convert.call_count == 2
