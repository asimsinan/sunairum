"""PDF pages come from editor preview PNGs when present at print DPI."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _print_size() -> tuple[int, int]:
    from tasks.html_constitution import CANVAS_H, CANVAS_W, PREVIEW_DEVICE_SCALE

    return (
        int(round(CANVAS_W * PREVIEW_DEVICE_SCALE)),
        int(round(CANVAS_H * PREVIEW_DEVICE_SCALE)),
    )


def _write_png(
    path: Path,
    color: tuple[int, int, int],
    size: tuple[int, int] | None = None,
) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size or _print_size(), color).save(path)


def _write_slide(html_dir: Path, stem: str) -> None:
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / f"{stem}.html").write_text(
        '<section class="slide" style="width:1280px;height:720px"></section>',
        encoding="utf-8",
    )


class HtmlPdfPreviewTests(unittest.TestCase):
    def test_pdf_from_html_dir_uses_preview_pngs_without_screenshot(self):
        from tasks.html_pdf import pdf_from_html_dir

        root = Path(tempfile.mkdtemp())
        html_dir = root / "html_output"
        preview = root / "preview"
        _write_slide(html_dir, "slide_01")
        _write_slide(html_dir, "slide_02")
        _write_png(preview / "slide_01.png", (200, 40, 40))
        _write_png(preview / "slide_02.png", (40, 200, 40))
        out = root / "deck.pdf"

        with mock.patch("tasks.html_pdf._screenshot_html_hidpi") as shot:
            pdf_from_html_dir(html_dir, out, preview_dir=preview)
        shot.assert_not_called()
        self.assertTrue(out.is_file())
        self.assertGreater(out.stat().st_size, 100)
        self.assertTrue(out.read_bytes().startswith(b"%PDF"))

    def test_sub_300dpi_preview_is_recaptured(self):
        from tasks.html_pdf import pdf_from_html_dir

        root = Path(tempfile.mkdtemp())
        html_dir = root / "html_output"
        preview = root / "preview"
        _write_slide(html_dir, "slide_01")
        _write_png(preview / "slide_01.png", (200, 40, 40), size=(1280, 720))
        out = root / "deck.pdf"

        def fake_shot(html_path: Path, png_path: Path, *, scale=None) -> None:
            _write_png(png_path, (40, 40, 200))

        with mock.patch("tasks.html_pdf._screenshot_html_hidpi", side_effect=fake_shot) as shot:
            pdf_from_html_dir(html_dir, out, preview_dir=preview)
        shot.assert_called_once()
        self.assertTrue(out.read_bytes().startswith(b"%PDF"))

    def test_missing_preview_screenshots_that_slide_only(self):
        from tasks.html_pdf import pdf_from_html_dir

        root = Path(tempfile.mkdtemp())
        html_dir = root / "html_output"
        preview = root / "preview"
        _write_slide(html_dir, "slide_01")
        _write_slide(html_dir, "slide_02")
        _write_png(preview / "slide_01.png", (200, 40, 40))
        out = root / "deck.pdf"

        def fake_shot(html_path: Path, png_path: Path, *, scale=None) -> None:
            _write_png(png_path, (40, 40, 200))

        with mock.patch("tasks.html_pdf._screenshot_html_hidpi", side_effect=fake_shot) as shot:
            pdf_from_html_dir(html_dir, out, preview_dir=preview)
        self.assertEqual(1, shot.call_count)
        self.assertEqual("slide_02.html", shot.call_args[0][0].name)
        self.assertTrue(out.read_bytes().startswith(b"%PDF"))

    def test_prefer_preview_false_always_screenshots(self):
        from tasks.html_pdf import pdf_from_html_dir

        root = Path(tempfile.mkdtemp())
        html_dir = root / "html_output"
        preview = root / "preview"
        _write_slide(html_dir, "slide_01")
        _write_png(preview / "slide_01.png", (200, 40, 40))
        out = root / "deck.pdf"

        def fake_shot(html_path: Path, png_path: Path, *, scale=None) -> None:
            _write_png(png_path, (10, 10, 10))

        with mock.patch("tasks.html_pdf._screenshot_html_hidpi", side_effect=fake_shot) as shot:
            pdf_from_html_dir(html_dir, out, preview_dir=preview, prefer_preview=False)
        shot.assert_called_once()


class ReleasePdfPreviewTests(unittest.TestCase):
    def test_ensure_release_pdf_stitches_preview_not_impress(self):
        from tasks import release_export

        root = Path(tempfile.mkdtemp())
        pptx = root / "exports" / "deck.pptx"
        pptx.parent.mkdir(parents=True)
        pptx.write_bytes(b"PK")
        html_dir = root / "html_output"
        preview = root / "preview"
        _write_slide(html_dir, "slide_01")
        _write_png(preview / "slide_01.png", (12, 80, 160))

        def boom_impress(*_a, **_k):
            raise AssertionError("Impress must not run when preview PNGs exist")

        with mock.patch.object(release_export, "_pdf_from_pptx", side_effect=boom_impress), mock.patch(
            "tasks.html_pdf._screenshot_html_hidpi",
            side_effect=AssertionError("screenshot must not run"),
        ):
            out = release_export.ensure_release_pdf(pptx, "sha", root)
        self.assertTrue(Path(out).read_bytes().startswith(b"%PDF"))
        stamp = Path(str(out) + ".source_sha256").read_text(encoding="utf-8")
        self.assertIn("html-preview-v10", stamp)
        self.assertIn("html_preview", stamp)

    def test_complete_preview_failure_does_not_impress(self):
        from tasks import release_export

        root = Path(tempfile.mkdtemp())
        pptx = root / "exports" / "deck.pptx"
        pptx.parent.mkdir(parents=True)
        pptx.write_bytes(b"PK")
        _write_slide(root / "html_output", "slide_01")
        _write_png(root / "preview" / "slide_01.png", (12, 80, 160))
        calls: list[str] = []

        def fake_pptx(*_a, **_k):
            calls.append("pptx")

        with mock.patch("tasks.html_pdf.pdf_from_html_dir", side_effect=RuntimeError("pillow")), mock.patch.object(
            release_export, "_pdf_from_pptx", side_effect=fake_pptx
        ):
            with self.assertRaises(RuntimeError):
                release_export.ensure_release_pdf(pptx, "sha", root)
        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
