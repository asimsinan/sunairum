"""PDF from editor preview PNGs (WYSIWYG), with hi-DPI HTML screenshot fill-in."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from tasks.html_constitution import CANVAS_H, CANVAS_W, PREVIEW_DEVICE_SCALE, PREVIEW_DPI


SLIDE_W_IN = 13.333333
SLIDE_H_IN = 7.5
DPI = PREVIEW_DPI
PREVIEW_PRINT_W = int(round(CANVAS_W * PREVIEW_DEVICE_SCALE))
PREVIEW_PRINT_H = int(round(CANVAS_H * PREVIEW_DEVICE_SCALE))


def _list_html_slides(html_dir: Path) -> list[Path]:
    return sorted(
        p for p in html_dir.glob("slide_*.html") if p.is_file() and p.stat().st_size > 0
    )


def _is_pillow_unavailable_stub(im: Any) -> bool:
    """True for the 1280×720 'Chromium unavailable' preview card."""
    if im.size != (CANVAS_W, CANVAS_H):
        return False
    try:
        from tasks.html_pipeline import _PREVIEW_STUB_BANNER_RGB, _PREVIEW_STUB_BG_RGB

        banner = im.getpixel((40, 24))
        center = im.getpixel((640, 360))
        if not (isinstance(banner, tuple) and isinstance(center, tuple)):
            return False
        br, bg, bb = banner[:3]
        cr, cg, cb = center[:3]
        tr, tg, tb = _PREVIEW_STUB_BANNER_RGB
        xr, xg, xb = _PREVIEW_STUB_BG_RGB
        banner_ok = abs(br - tr) <= 8 and abs(bg - tg) <= 8 and abs(bb - tb) <= 8
        center_ok = abs(cr - xr) <= 12 and abs(cg - xg) <= 12 and abs(cb - xb) <= 12
        return bool(banner_ok and center_ok)
    except Exception:  # noqa: BLE001
        return False


def _preview_png_usable(png_path: Path) -> bool:
    """True when the PNG is a real slide capture at print DPI (300)."""
    if not png_path.is_file():
        return False
    try:
        from PIL import Image

        with Image.open(png_path) as im:
            w, h = im.size
            if w < PREVIEW_PRINT_W - 2 or h < PREVIEW_PRINT_H - 2:
                return False
            return not _is_pillow_unavailable_stub(im)
    except Exception:  # noqa: BLE001
        return False


def _screenshot_html_hidpi(
    html_path: Path, png_path: Path, *, scale: float | None = None
) -> None:
    from playwright.sync_api import sync_playwright

    from tasks.html_constitution import ensure_slide_root
    from tasks.html_render import _screenshot_slide

    doc = ensure_slide_root(html_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="sunairum_hidpi_") as tmp:
        local = Path(tmp) / "slide.html"
        local.write_text(doc, encoding="utf-8")
        uri = local.resolve().as_uri()
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:
                page = browser.new_page(
                    viewport={"width": CANVAS_W, "height": CANVAS_H},
                    device_scale_factor=scale if scale is not None else PREVIEW_DEVICE_SCALE,
                )
                page.goto(uri, wait_until="load", timeout=30_000)
                page.wait_for_timeout(50)
                _screenshot_slide(
                    page, str(png_path), canvas_w=CANVAS_W, canvas_h=CANVAS_H
                )
            finally:
                browser.close()


def _load_rgb(png_path: Path) -> Any:
    from PIL import Image

    with Image.open(png_path) as im:
        return im.convert("RGB")


def _normalize_page_images(images: list[Any]) -> list[Any]:
    """One PDF page size. Mixed 1×/2× decks scale to the largest native capture."""
    from PIL import Image

    if not images:
        return images
    sizes = {im.size for im in images}
    if len(sizes) == 1:
        return images
    max_w = max(im.size[0] for im in images)
    target = (max_w, round(max_w * CANVAS_H / CANVAS_W))
    out: list[Any] = []
    for im in images:
        if im.size == target:
            out.append(im)
        else:
            out.append(im.resize(target, Image.Resampling.LANCZOS))
    return out


def _write_pdf(images: list[Any], pdf_path: Path) -> None:
    if not images:
        raise RuntimeError("HTML PDF produced no page images")
    first, *rest = _normalize_page_images(images)
    dpr = first.size[0] / float(CANVAS_W)
    first.save(
        pdf_path,
        "PDF",
        resolution=96.0 * dpr,
        save_all=bool(rest),
        append_images=rest,
    )


def pdf_from_html_dir(
    html_dir: str | Path,
    pdf_path: str | Path,
    *,
    scale: float | None = None,
    preview_dir: str | Path | None = None,
    prefer_preview: bool = True,
) -> str:
    """Write a multi-page PDF from preview/slide_*.png, screenshoting gaps."""
    root = Path(html_dir)
    slides = _list_html_slides(root)
    if not slides:
        raise FileNotFoundError(f"No slide_*.html in {html_dir}")
    out = Path(pdf_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    dpr = float(scale or os.environ.get("PDF_HTML_SCALE") or PREVIEW_DEVICE_SCALE)
    preview_root = Path(preview_dir) if preview_dir is not None else root.parent / "preview"

    images: list[Any] = []
    used_preview = 0
    used_shot = 0
    with tempfile.TemporaryDirectory(prefix="sunairum_html_pdf_") as tmp:
        tmp_root = Path(tmp)
        for i, html_path in enumerate(slides):
            prev = preview_root / f"{html_path.stem}.png"
            if prefer_preview and _preview_png_usable(prev):
                images.append(_load_rgb(prev))
                used_preview += 1
                continue
            png = tmp_root / f"slide_{i:02d}.png"
            _screenshot_html_hidpi(html_path, png, scale=dpr)
            images.append(_load_rgb(png))
            used_shot += 1
        _write_pdf(images, out)
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError("HTML PDF export did not produce an output file")
    print(f"[pdf] {used_preview} preview PNG(s), {used_shot} hi-DPI screenshot(s)")
    return str(out)
