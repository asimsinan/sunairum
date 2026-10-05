import json
import tempfile
import unittest
from pathlib import Path

from pdf_provenance import (
    MIN_FIGURE_PIXEL_WIDTH,
    _attach_caption_metadata,
    _extract_docling_figures,
    _write_figure_index,
    extract_pdf_figures,
)


class PdfProvenanceTests(unittest.TestCase):
    def test_caption_text_is_selected_from_same_pdf_page(self):
        root = Path(tempfile.mkdtemp())
        structure_path = root / "sources" / "source_structure.json"
        structure_path.parent.mkdir(parents=True)
        structure_path.write_text(json.dumps({
            "pages": [{"page": 2, "blocks": [{
                "type": "figure_caption", "text": "Figure 1: Results", "bbox": [1, 2, 3, 4],
            }]}],
        }), encoding="utf-8")
        figures = [{"id": "pdf-figure-1", "page": 2}]
        _attach_caption_metadata(root, figures)
        self.assertEqual("Figure 1: Results", figures[0]["caption_text"])

    def test_missing_pdf_does_not_create_provenance_output(self):
        root = Path(tempfile.mkdtemp())
        self.assertEqual([], extract_pdf_figures(root))


class DoclingFigureTests(unittest.TestCase):
    """Docling figures are promoted, not re-detected, so nothing is rejected."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.assets = self.root / "sources" / "source_files"
        self.assets.mkdir(parents=True)
        self.out = self.root / "sources" / "pdf_images"
        self.out.mkdir(parents=True)

    def _write_figure(self, name: str, width: int, height: int) -> None:
        from PIL import Image

        Image.new("RGB", (width, height), "white").save(self.assets / name)

    def _manifest(self, entries: list[dict]) -> None:
        (self.assets / "image_manifest.json").write_text(json.dumps(entries), encoding="utf-8")

    def test_page_bbox_and_caption_come_from_the_document(self):
        self._write_figure("docling_figure_001.png", 1200, 800)
        self._manifest([{
            "filename": "docling_figure_001.png", "source": "docling",
            "asset_id": "src-figure-001", "sha256": "abc",
            "width": 1200, "height": 800, "page": 4,
            "bbox": [72.0, 100.0, 540.0, 412.0], "caption": "Figure 2: Latency",
        }])
        figures = _extract_docling_figures(self.root, self.out)
        self.assertEqual(1, len(figures))
        figure = figures[0]
        self.assertEqual(4, figure["page"])
        self.assertEqual("Figure 2: Latency", figure["caption_text"])
        self.assertEqual([72.0, 100.0, 540.0, 412.0], figure["bbox"])
        self.assertEqual(4, figure["placements"][0]["page"])
        self.assertTrue((self.out / figure["file"]).is_file())

    def test_low_resolution_figures_are_reported(self):
        self._write_figure("docling_figure_001.png", 240, 180)
        self._manifest([{
            "filename": "docling_figure_001.png", "asset_id": "src-figure-001",
            "sha256": "abc", "width": 240, "height": 180, "page": 1, "caption": "",
        }])
        figures = _extract_docling_figures(self.root, self.out)
        _write_figure_index(self.out, figures, [])
        index = json.loads((self.out / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(1, len(index["low_resolution"]))
        self.assertEqual([], index["rejected"])

    def test_adequate_figures_are_not_flagged(self):
        self._write_figure("docling_figure_001.png", 1200, 800)
        self._manifest([{
            "filename": "docling_figure_001.png", "asset_id": "src-figure-001",
            "sha256": "abc", "width": 1200, "height": 800, "page": 1, "caption": "",
        }])
        figures = _extract_docling_figures(self.root, self.out)
        _write_figure_index(self.out, figures, [])
        index = json.loads((self.out / "index.json").read_text(encoding="utf-8"))
        self.assertEqual([], index["low_resolution"])


class FigureResolutionConfigTests(unittest.TestCase):
    """The default render scale has to clear the slide's own pixel budget.

    PyMuPDF lifted the embedded original, so resolution was whatever the author
    supplied. Docling renders at ``images_scale x 72`` DPI, which makes the
    default a correctness setting rather than a performance knob.
    """

    def test_default_scale_keeps_a_column_width_figure_sharp(self):
        from docling_parser import build_pipeline_options

        scale = build_pipeline_options().images_scale
        self.assertGreaterEqual(scale, 3.0, "images_scale below 3.0 renders under 216 DPI")
        column_width_points = 252  # 3.5in, a single column in a two-column paper
        self.assertGreaterEqual(column_width_points * scale, MIN_FIGURE_PIXEL_WIDTH)


if __name__ == "__main__":
    unittest.main()
