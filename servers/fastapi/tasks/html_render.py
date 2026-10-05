"""Chromium preview PNG for Constrained HTML slides.

Celery prefork makes in-worker Playwright reuse unsafe. Callers should prefer
subprocess helpers when running under Celery.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _preview_looks_stub(png_path: str, *, max_bytes: int = 12_000) -> bool:
    try:
        return (not os.path.isfile(png_path)) or os.path.getsize(png_path) < max_bytes
    except OSError:
        return True


def _in_celery_worker() -> bool:
    if os.environ.get("CELERY_WORKER") or os.environ.get("CELERY_LOADER"):
        return True
    if any("celery" in str(arg).casefold() for arg in sys.argv):
        return True
    try:
        from celery import current_task

        return current_task is not None and getattr(current_task, "request", None) is not None
    except Exception:  # noqa: BLE001
        return False


def _sync_playwright_requires_subprocess() -> bool:
    """True when Sync Playwright is unsafe in the current execution context."""
    if _in_celery_worker():
        return True
    try:
        import asyncio

        asyncio.get_running_loop()
    except RuntimeError:
        return False
    except Exception:  # noqa: BLE001
        return False
    return True


def _settle_slide_page(page: Any) -> None:
    """Wait until browser layout is stable enough to publish as a preview.

    ``load`` only guarantees that the document resource finished loading. Web
    fonts, decoded images, MathJax and layout triggered by those resources can
    still change the slide for several frames afterwards. Publishing during
    that window produces the brief oversized/cropped thumbnail seen by users.
    """
    page.wait_for_function(
        """async () => {
          if (document.fonts?.ready) await document.fonts.ready;
          const images = Array.from(document.images || []);
          await Promise.all(images.map(async (image) => {
            if (!image.complete) {
              await new Promise((resolve) => {
                image.addEventListener('load', resolve, { once: true });
                image.addEventListener('error', resolve, { once: true });
              });
            }
            if (image.decode) await image.decode().catch(() => undefined);
          }));
          return true;
        }""",
        timeout=15_000,
    )
    page.add_style_tag(
        content="*,*::before,*::after{animation:none!important;transition:none!important}"
    )
    page.evaluate(
        """() => new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)))"""
    )


def _screenshot_slide(page: Any, png_path: str, *, canvas_w: int, canvas_h: int) -> None:
    """Capture a settled slide and atomically publish the completed PNG."""
    target = Path(png_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, pending_path = tempfile.mkstemp(
        prefix=f".{target.stem}.", suffix=".pending.png", dir=str(target.parent)
    )
    os.close(fd)
    slide = page.locator(".slide")
    try:
        if slide.count() > 0:
            try:
                slide.first.screenshot(path=pending_path, timeout=8_000)
            except Exception as exc:  # noqa: BLE001
                print(
                    "[html_render] .slide screenshot failed, using viewport clip: "
                    f"{exc}"
                )
                page.screenshot(
                    path=pending_path,
                    clip={"x": 0, "y": 0, "width": canvas_w, "height": canvas_h},
                    timeout=10_000,
                )
        else:
            page.screenshot(
                path=pending_path,
                clip={"x": 0, "y": 0, "width": canvas_w, "height": canvas_h},
                timeout=10_000,
            )
        # Decode before publication. A truncated or invalid image must never
        # replace the last known-good preview visible to polling clients.
        from PIL import Image

        with Image.open(pending_path) as rendered:
            rendered.verify()
        os.replace(pending_path, png_path)
        return
    except Exception as exc:  # noqa: BLE001
        try:
            os.unlink(pending_path)
        except OSError:
            pass
        raise RuntimeError(f"settled slide screenshot failed: {exc}") from exc


def preview_once(doc: str, png_path: str) -> dict[str, Any]:
    """Single Chromium launch: screenshot .slide."""
    from playwright.sync_api import sync_playwright

    from tasks.html_constitution import CANVAS_H, CANVAS_W, PREVIEW_DEVICE_SCALE, ensure_slide_root

    doc = ensure_slide_root(doc)
    os.makedirs(os.path.dirname(os.path.abspath(png_path)) or ".", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sunairum_html_render_") as tmp:
        html_path = Path(tmp) / "slide.html"
        html_path.write_text(doc, encoding="utf-8")
        uri = html_path.resolve().as_uri()
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:
                page = browser.new_page(
                    viewport={"width": CANVAS_W, "height": CANVAS_H},
                    device_scale_factor=PREVIEW_DEVICE_SCALE,
                )
                page.goto(uri, wait_until="load", timeout=30_000)
                _settle_slide_page(page)
                _screenshot_slide(page, png_path, canvas_w=CANVAS_W, canvas_h=CANVAS_H)
            finally:
                browser.close()
    return {
        "preview_ok": not _preview_looks_stub(png_path),
        "engine": "playwright",
    }


def preview_subprocess(doc: str, png_path: str) -> dict[str, Any] | None:
    """Fresh Python process — avoids Celery/fork Playwright deadlocks."""
    with tempfile.TemporaryDirectory(prefix="sunairum_html_render_sub_") as tmp:
        html_path = Path(tmp) / "slide.html"
        html_path.write_text(doc, encoding="utf-8")
        out_json = Path(tmp) / "result.json"
        script = (
            "import json, sys\n"
            "from tasks.html_render import preview_once\n"
            "doc=open(sys.argv[1],encoding='utf-8').read()\n"
            "result=preview_once(doc, sys.argv[2])\n"
            "open(sys.argv[3],'w',encoding='utf-8').write(json.dumps(result))\n"
        )
        runner = Path(tmp) / "run_preview.py"
        runner.write_text(script, encoding="utf-8")
        env = dict(os.environ)
        fastapi_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = fastapi_root + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, str(runner), str(html_path), str(png_path), str(out_json)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
            cwd=fastapi_root,
        )
        if completed.returncode != 0 or not out_json.is_file():
            print(
                f"[html_render] preview subprocess failed: "
                f"{(completed.stderr or completed.stdout or '')[:300]}"
            )
            return None
        import json

        return json.loads(out_json.read_text(encoding="utf-8"))


def measure_and_preview_combined(doc: str, png_path: str) -> dict[str, Any] | None:
    """Back-compat name: preview-only (Slide IR measure retired)."""
    if _sync_playwright_requires_subprocess():
        return preview_subprocess(doc, png_path)
    try:
        return preview_once(doc, png_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[html_render] preview_once failed: {exc}")
        return preview_subprocess(doc, png_path)
