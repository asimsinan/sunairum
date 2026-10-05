"""Speaker-notes handout PDF for an immutable presentation release."""

from __future__ import annotations

import re
import tempfile
from html import unescape
from pathlib import Path
from xml.sax.saxutils import escape


def _title_from_html(path: Path, fallback: str) -> str:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return fallback
    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", source, flags=re.I | re.S)
    if not match:
        return fallback
    text = re.sub(r"<[^>]+>", " ", match.group(1))
    return unescape(re.sub(r"\s+", " ", text)).strip() or fallback


def _preview_for_slide(root: Path, html_path: Path, temp_dir: Path) -> Path:
    from tasks.html_pdf import _preview_png_usable, _screenshot_html_hidpi

    preview = root / "preview" / f"{html_path.stem}.png"
    if _preview_png_usable(preview):
        return preview
    rendered = temp_dir / f"{html_path.stem}.png"
    _screenshot_html_hidpi(html_path, rendered)
    return rendered


def create_notes_handout_pdf(proj_dir: str | Path, output_path: str | Path) -> dict:
    """Create a polished slide-plus-speaker-notes handout PDF."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph

    from tasks.html_to_pptx import _spoken_note_for_stem, list_html_slides

    root = Path(proj_dir)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    slides = list_html_slides(root / "html_output")
    if not slides:
        raise RuntimeError("No HTML slides are available for notes PDF export")

    font_name = "Helvetica"
    for candidate in (
        Path(__file__).resolve().parents[1] / "assets" / "fonts" / "source-sans-3-400.ttf",
        root / "fonts" / "SourceSans3-Regular.ttf",
        Path("/usr/local/share/fonts/sunairum/SourceSans3-Regular.ttf"),
    ):
        if candidate.is_file():
            try:
                pdfmetrics.registerFont(TTFont("SunairumSans", str(candidate)))
                font_name = "SunairumSans"
                break
            except Exception:  # noqa: BLE001
                pass

    page_w, page_h = A4
    margin = 42.0
    content_w = page_w - margin * 2
    slide_h = content_w * 9.0 / 16.0
    body_style = ParagraphStyle(
        "notes",
        fontName=font_name,
        fontSize=10.5,
        leading=14.2,
        textColor=colors.HexColor("#26364A"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    heading_style = ParagraphStyle(
        "slide-heading",
        fontName=font_name,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#173A68"),
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    pdf = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
    pdf.setTitle("Presentation speaker notes")
    pdf.setSubject("Slides with speaker notes")
    page_number = 0
    with tempfile.TemporaryDirectory(prefix="sunairum-notes-pdf-") as tmp:
        temp_dir = Path(tmp)
        for slide_index, html_path in enumerate(slides, start=1):
            title = _title_from_html(html_path, f"Slide {slide_index}")
            note = _spoken_note_for_stem(root, html_path.stem) or "No speaker notes."
            note_markup = escape(note).replace("\n", "<br/>")
            remaining = Paragraph(note_markup, body_style)
            first_page = True
            while remaining is not None:
                page_number += 1
                heading = f"Slide {slide_index}: {title}"
                if not first_page:
                    heading += " (continued)"
                heading_para = Paragraph(escape(heading), heading_style)
                _heading_w, heading_h = heading_para.wrap(content_w, 48.0)
                heading_para.drawOn(pdf, margin, page_h - margin - heading_h)

                preview = _preview_for_slide(root, html_path, temp_dir)
                if first_page:
                    image_w, image_h = content_w, slide_h
                else:
                    image_w, image_h = 180.0, 101.25
                image_y = page_h - margin - heading_h - 12.0 - image_h
                pdf.drawImage(
                    ImageReader(str(preview)),
                    margin,
                    image_y,
                    width=image_w,
                    height=image_h,
                    preserveAspectRatio=True,
                    anchor="c",
                )

                notes_top = image_y - 25.0
                pdf.setFillColor(colors.HexColor("#2B78B8"))
                pdf.setFont(font_name, 9)
                pdf.drawString(margin, notes_top, "SPEAKER NOTES")
                text_top = notes_top - 18.0
                available_h = text_top - margin - 12.0
                parts = remaining.split(content_w, available_h)
                if not parts:
                    raise RuntimeError(f"Speaker notes cannot fit on a PDF page for {html_path.stem}")
                current = parts[0]
                _width, height = current.wrap(content_w, available_h)
                current.drawOn(pdf, margin, text_top - height)
                remaining = parts[1] if len(parts) > 1 else None

                pdf.setFillColor(colors.HexColor("#6B7789"))
                pdf.setFont(font_name, 8)
                pdf.drawRightString(page_w - margin, 22.0, str(page_number))
                pdf.showPage()
                first_page = False
    pdf.save()
    if not output.is_file() or output.stat().st_size < 500:
        raise RuntimeError("Notes PDF generation produced an empty artifact")
    return {"path": str(output), "pages": page_number, "slides": len(slides)}
