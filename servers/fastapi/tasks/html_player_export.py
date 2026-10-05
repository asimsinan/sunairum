"""Deckflow-style HTML player export from html_output slides.

Builds a self-contained index.html with gzip+base64 page payloads and a
viewport-fit player (arrow/click nav, autoplay, fullscreen), packaged as a zip.
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from tasks.html_constitution import CANVAS_H, CANVAS_W
from tasks.slide_artifacts import list_slide_artifacts

DEFAULT_PAGE_WIDTH = CANVAS_W
DEFAULT_PAGE_HEIGHT = CANVAS_H

_BRAND_HREF = "https://sunairum.com/?utm_source=sunairum&utm_medium=html&utm_campaign=watermark&utm_content=slide_footer"
_BRAND_LABEL = "© Designed with Sunairum"

_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class HtmlPlayerExportError(Exception):
    """Raised when HTML player export cannot be built."""


def _safe_slug(title: str, fallback: str = "presentation") -> str:
    raw = (title or "").strip() or fallback
    slug = _SLUG_RE.sub("-", raw).strip("-._")
    if not slug:
        slug = fallback
    return slug[:80]


def compress_page_html(html: str) -> str:
    """Gzip + base64 encode one slide HTML document (Deckflow player format)."""
    raw = html.encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    return base64.b64encode(compressed).decode("ascii")


def collect_html_pages(project_dir: str | Path) -> list[str]:
    """Return ordered slide HTML strings from html_output (or preferred artifacts)."""
    root = Path(project_dir)
    html_dir = root / "html_output"
    if html_dir.is_dir():
        paths = sorted(
            (p for p in html_dir.glob("slide_*.html") if p.is_file() and p.stat().st_size > 0),
            key=lambda p: p.name,
        )
    else:
        paths = [
            p
            for p in list_slide_artifacts(root)
            if p.suffix.lower() == ".html" and p.is_file()
        ]
    if not paths:
        raise HtmlPlayerExportError("No HTML slides found (expected html_output/slide_*.html)")
    pages: list[str] = []
    for path in paths:
        try:
            pages.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise HtmlPlayerExportError(f"Failed to read {path.name}: {exc}") from exc
    return pages


def build_player_data(
    pages_html: list[str],
    *,
    page_width: int = DEFAULT_PAGE_WIDTH,
    page_height: int = DEFAULT_PAGE_HEIGHT,
) -> dict[str, Any]:
    return {
        "pages": [compress_page_html(html) for html in pages_html],
        "pageWidth": int(page_width),
        "pageHeight": int(page_height),
    }


def render_player_index_html(
    *,
    title: str,
    player_data: dict[str, Any],
    brand_href: str = _BRAND_HREF,
    brand_label: str = _BRAND_LABEL,
) -> str:
    """Render the self-contained HTML player (adapted from Deckflow export)."""
    safe_title = (title or "Presentation").replace("<", "&lt;").replace(">", "&gt;")
    # Embed as a JS object literal via JSON (safe for script context).
    player_json = json.dumps(player_data, separators=(",", ":"), ensure_ascii=False)
    brand_href_esc = brand_href.replace('"', "&quot;")
    brand_label_esc = brand_label.replace("<", "&lt;").replace(">", "&gt;")

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{safe_title}</title>
    <meta name="description" content="Powered by Sunairum" />
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        background: #111;
        color: #fff;
        font-family: sans-serif;
      }}
      #root {{
        position: absolute;
        left: 50%;
        top: 50%;
        width: 1280px;
        height: 752px;
        transform-origin: center center;
      }}
      #playerCanvas {{
        position: relative;
        width: 1280px;
        height: 720px;
      }}
      #frame {{
        width: 100%;
        height: 100%;
        border: 0;
        background: #fff;
      }}
      #playerChrome {{
        box-sizing: border-box;
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        width: 100%;
        height: 32px;
        padding: 0 8px;
        background: #111;
      }}
      #brandMark {{
        position: static;
        justify-self: center;
        font-size: 11px;
        line-height: 1.2;
        user-select: text;
        pointer-events: auto;
        color: rgba(255, 255, 255, 0.9);
        padding: 3px 6px;
      }}
      #brandMark a {{
        color: inherit;
        text-decoration: none;
      }}
      #brandMark a:hover {{
        text-decoration: underline;
      }}
      #brandMark.brand-mark-none {{
        display: none;
      }}
      #brandMark.brand-mark-left-top {{
        justify-self: start;
      }}
      #brandMark.brand-mark-right-top {{
        justify-self: end;
      }}
      #brandMark.brand-mark-right-bottom {{
        justify-self: center;
      }}
      #brandMark.brand-mark-left-bottom {{
        justify-self: start;
      }}
      #pageHint {{
        position: static;
        justify-self: start;
        font-size: 11px;
        color: rgba(255, 255, 255, 0.42);
        padding: 3px 6px;
        pointer-events: none;
      }}
      #toolbar {{
        position: static;
        justify-self: end;
        display: flex;
        gap: 8px;
      }}
      #toolbar button {{
        border: 0;
        border-radius: 6px;
        padding: 6px 9px;
        font-size: 12px;
        color: rgba(255, 255, 255, 0.9);
        background: rgba(0, 0, 0, 0.45);
        cursor: pointer;
      }}
      #fullscreenOverlay {{
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        pointer-events: none;
        background:
          radial-gradient(circle at center, rgba(0, 0, 0, 0.12) 0%, rgba(0, 0, 0, 0.52) 100%);
        z-index: 20;
      }}
      #fullscreenOverlay.hidden {{
        display: none;
      }}
      #fullscreenBtn {{
        position: relative;
        border: 0;
        border-radius: 999px;
        padding: 18px 42px;
        font-size: 26px;
        font-weight: 800;
        letter-spacing: 0.08em;
        line-height: 1;
        pointer-events: auto;
        color: #fff;
        background: linear-gradient(135deg, rgba(21, 107, 255, 0.95), rgba(64, 192, 255, 0.95));
        box-shadow:
          0 0 0 1px rgba(255, 255, 255, 0.22) inset,
          0 12px 36px rgba(12, 76, 196, 0.5),
          0 0 40px rgba(36, 149, 255, 0.4);
        cursor: pointer;
        transition: transform 180ms ease, box-shadow 220ms ease, filter 220ms ease;
        animation: fullscreen-btn-breathe 1.9s ease-in-out infinite;
      }}
      #fullscreenBtn::before,
      #fullscreenBtn::after {{
        content: "";
        position: absolute;
        inset: -14px;
        border-radius: 999px;
        pointer-events: none;
        border: 2px solid rgba(126, 206, 255, 0.72);
      }}
      #fullscreenBtn::before {{
        animation: fullscreen-btn-ripple 2.4s ease-out infinite;
      }}
      #fullscreenBtn::after {{
        animation: fullscreen-btn-ripple 2.4s ease-out 1.2s infinite;
      }}
      #fullscreenBtn:hover {{
        transform: translateY(-2px) scale(1.03);
        box-shadow:
          0 0 0 1px rgba(255, 255, 255, 0.35) inset,
          0 16px 44px rgba(7, 73, 196, 0.58),
          0 0 54px rgba(36, 149, 255, 0.52);
        filter: brightness(1.06);
      }}
      #fullscreenBtn:active {{
        transform: translateY(0) scale(0.98);
      }}
      #fullscreenDockBtn {{
        display: none;
      }}
      #fullscreenDockBtn.visible {{
        display: inline-flex;
      }}
      @keyframes fullscreen-btn-ripple {{
        0% {{
          opacity: 0.9;
          transform: scale(0.92);
        }}
        70% {{
          opacity: 0.18;
        }}
        100% {{
          opacity: 0;
          transform: scale(1.26);
        }}
      }}
      @keyframes fullscreen-btn-breathe {{
        0%, 100% {{
          transform: translateY(0) scale(1);
        }}
        50% {{
          transform: translateY(-1px) scale(1.018);
        }}
      }}
    </style>
  </head>
  <body>
    <div id="root">
      <div id="playerCanvas">
        <iframe id="frame" title="html-player-frame"></iframe>
      </div>
      <div id="playerChrome" aria-label="Presentation controls">
        <div id="pageHint"></div>
        <div id="brandMark" class="brand-mark-right-bottom">
          <a href="{brand_href_esc}" target="_blank" rel="noopener noreferrer">{brand_label_esc}</a>
        </div>
        <div id="toolbar">
          <button id="autoPlayBtn" type="button">Auto: Off</button>
          <button id="fullscreenDockBtn" type="button">Fullscreen</button>
        </div>
      </div>
    </div>
    <div id="fullscreenOverlay">
      <button id="fullscreenBtn" type="button">Fullscreen</button>
    </div>
    <script>
      const playerData = {player_json};
      const compressedPages = playerData.pages;
      const frameEl = document.getElementById("frame");
      const rootEl = document.getElementById("root");
      const playerCanvasEl = document.getElementById("playerCanvas");
      const pageHintEl = document.getElementById("pageHint");
      const autoPlayBtnEl = document.getElementById("autoPlayBtn");
      const fullscreenDockBtnEl = document.getElementById("fullscreenDockBtn");
      const fullscreenOverlayEl = document.getElementById("fullscreenOverlay");
      const fullscreenBtnEl = document.getElementById("fullscreenBtn");
      const browserLanguage = String(navigator.language || "").toLowerCase();
      const isChinese = browserLanguage.startsWith("zh");
      const i18n = isChinese
        ? {{
            htmlLang: "zh-CN",
            autoOff: "自动播放：关闭",
            autoSeconds: "自动播放：{{seconds}}秒",
            enterFullscreen: "全屏显示",
            exitFullscreen: "退出全屏",
            noPage: "没有页面",
            decodeFailed: "解码失败",
            autoPlayPrompt: "设置每页播放秒数（输入 0 关闭）",
            invalidNumber: "请输入大于等于 0 的数字",
          }}
        : {{
            htmlLang: "en",
            autoOff: "Auto: Off",
            autoSeconds: "Auto: {{seconds}}s",
            enterFullscreen: "Fullscreen",
            exitFullscreen: "Exit Fullscreen",
            noPage: "No page",
            decodeFailed: "Decode failed",
            autoPlayPrompt: "Set autoplay seconds per page (enter 0 to disable)",
            invalidNumber: "Please enter a number greater than or equal to 0.",
          }};
      const pageWidth = Number(playerData.pageWidth) > 0 ? Number(playerData.pageWidth) : 1280;
      const pageHeight = Number(playerData.pageHeight) > 0 ? Number(playerData.pageHeight) : 720;
      const playerChromeHeight = 32;
      const decodedPages = new Array(compressedPages.length);
      let index = 0;
      let autoPlayTimer = null;
      let autoPlayDurationMs = 0;

      function base64ToUint8Array(value) {{
        const binary = atob(value);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) {{
          bytes[i] = binary.charCodeAt(i);
        }}
        return bytes;
      }}

      async function decodePage(base64Data) {{
        if (typeof DecompressionStream !== "function") {{
          throw new Error("DecompressionStream(gzip) is not supported in this browser.");
        }}
        const bytes = base64ToUint8Array(base64Data);
        const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
        const arrayBuffer = await new Response(stream).arrayBuffer();
        return new TextDecoder().decode(arrayBuffer);
      }}

      async function getPage(pageIndex) {{
        if (decodedPages[pageIndex] !== undefined) {{
          return decodedPages[pageIndex];
        }}
        const decoded = await decodePage(compressedPages[pageIndex]);
        decodedPages[pageIndex] = decoded;
        return decoded;
      }}

      function updateRootScale() {{
        const viewportWidth = Math.max(window.innerWidth, document.documentElement.clientWidth, 1);
        const viewportHeight = Math.max(window.innerHeight, document.documentElement.clientHeight, 1);
        const playerHeight = pageHeight + playerChromeHeight;
        const scale = Math.min(viewportWidth / pageWidth, viewportHeight / playerHeight);
        rootEl.style.width = pageWidth + "px";
        rootEl.style.height = playerHeight + "px";
        rootEl.style.transform = "translate(-50%, -50%) scale(" + scale + ")";
      }}

      function dockFullscreenButton() {{
        fullscreenOverlayEl.classList.add("hidden");
        fullscreenDockBtnEl.classList.add("visible");
        updateFullscreenButtonLabel();
      }}

      function updateFullscreenButtonLabel() {{
        if (document.fullscreenElement) {{
          fullscreenDockBtnEl.textContent = i18n.exitFullscreen;
          fullscreenBtnEl.textContent = i18n.exitFullscreen;
          return;
        }}
        fullscreenDockBtnEl.textContent = i18n.enterFullscreen;
        fullscreenBtnEl.textContent = i18n.enterFullscreen;
      }}

      function fitFrameContent() {{
        if (!frameEl.contentDocument) {{
          return;
        }}
        const htmlEl = frameEl.contentDocument.documentElement;
        const bodyEl = frameEl.contentDocument.body;
        if (!htmlEl || !bodyEl) {{
          return;
        }}
        bodyEl.style.zoom = "1";
        bodyEl.style.transformOrigin = "top left";
        htmlEl.style.width = pageWidth + "px";
        htmlEl.style.height = pageHeight + "px";
        bodyEl.style.width = pageWidth + "px";
        bodyEl.style.height = pageHeight + "px";
      }}

      async function render() {{
        if (!compressedPages.length) {{
          pageHintEl.textContent = i18n.noPage;
          frameEl.srcdoc = "";
          return;
        }}
        try {{
          frameEl.srcdoc = await getPage(index);
          pageHintEl.textContent = (index + 1) + " / " + compressedPages.length;
          restartAutoPlay();
        }} catch (error) {{
          pageHintEl.textContent = i18n.decodeFailed;
          frameEl.srcdoc = "";
        }}
      }}

      async function move(step) {{
        if (!compressedPages.length) {{
          return;
        }}
        const next = Math.max(0, Math.min(compressedPages.length - 1, index + step));
        if (next !== index) {{
          index = next;
          dockFullscreenButton();
          await render();
        }}
      }}

      async function onArrowKey(event) {{
        if (event.key === "ArrowRight" || event.key === "ArrowDown") {{
          event.preventDefault();
          await move(1);
        }} else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {{
          event.preventDefault();
          await move(-1);
        }}
      }}

      const CLICK_NAV_MOVE_THRESHOLD_PX = 5;
      let clickNavPointer = null;

      function isInteractiveNavTarget(target) {{
        if (!target || typeof target.closest !== "function") {{
          return false;
        }}
        return Boolean(
          target.closest(
            "a, button, input, textarea, select, label, summary, option, [contenteditable='true'], [contenteditable=''], [role='button'], [role='link'], [role='textbox'], [role='checkbox'], [role='radio'], [role='menuitem']",
          ),
        );
      }}

      function hasTextSelection(doc) {{
        if (!doc || typeof doc.getSelection !== "function") {{
          return false;
        }}
        const selection = doc.getSelection();
        if (!selection || selection.isCollapsed) {{
          return false;
        }}
        return Boolean(String(selection).trim());
      }}

      function onClickNavPointerDown(event) {{
        if (event.button !== 0) {{
          return;
        }}
        const doc = (event.target && event.target.ownerDocument) || document;
        clickNavPointer = {{
          x: event.clientX,
          y: event.clientY,
          hadSelection: hasTextSelection(doc),
        }};
      }}

      async function onClickNav(event) {{
        if (event.button !== 0) {{
          return;
        }}
        const pointer = clickNavPointer;
        clickNavPointer = null;
        if (!pointer) {{
          return;
        }}
        if (
          Math.abs(event.clientX - pointer.x) > CLICK_NAV_MOVE_THRESHOLD_PX ||
          Math.abs(event.clientY - pointer.y) > CLICK_NAV_MOVE_THRESHOLD_PX
        ) {{
          return;
        }}
        if (isInteractiveNavTarget(event.target)) {{
          return;
        }}
        const doc = event.currentTarget && event.currentTarget.nodeType === 9
          ? event.currentTarget
          : (event.target && event.target.ownerDocument) || document;
        if (pointer.hadSelection || hasTextSelection(doc)) {{
          return;
        }}
        const width = Math.max(
          (doc.documentElement && doc.documentElement.clientWidth) || 0,
          (doc.body && doc.body.clientWidth) || 0,
          1,
        );
        await move(event.clientX >= width / 2 ? 1 : -1);
      }}

      function bindArrowHandlers(target) {{
        if (!target || typeof target.addEventListener !== "function") {{
          return;
        }}
        target.addEventListener("keydown", onArrowKey);
      }}

      function bindClickNavHandlers(target) {{
        if (!target || typeof target.addEventListener !== "function") {{
          return;
        }}
        target.addEventListener("mousedown", onClickNavPointerDown);
        target.addEventListener("click", onClickNav);
      }}

      function clearAutoPlayTimer() {{
        if (autoPlayTimer) {{
          clearTimeout(autoPlayTimer);
          autoPlayTimer = null;
        }}
      }}

      function updateAutoPlayButtonLabel() {{
        if (autoPlayDurationMs <= 0) {{
          autoPlayBtnEl.textContent = i18n.autoOff;
          return;
        }}
        autoPlayBtnEl.textContent = i18n.autoSeconds.replace("{{seconds}}", String(autoPlayDurationMs / 1000));
      }}

      function restartAutoPlay() {{
        clearAutoPlayTimer();
        if (autoPlayDurationMs <= 0 || compressedPages.length <= 1) {{
          return;
        }}
        autoPlayTimer = setTimeout(async () => {{
          if (index >= compressedPages.length - 1) {{
            index = 0;
            await render();
            return;
          }}
          await move(1);
        }}, autoPlayDurationMs);
      }}

      function configureAutoPlay() {{
        const raw = window.prompt(i18n.autoPlayPrompt, autoPlayDurationMs > 0 ? String(autoPlayDurationMs / 1000) : "0");
        if (raw === null) {{
          return;
        }}
        const seconds = Number(raw);
        if (!Number.isFinite(seconds) || seconds < 0) {{
          window.alert(i18n.invalidNumber);
          return;
        }}
        autoPlayDurationMs = Math.floor(seconds * 1000);
        updateAutoPlayButtonLabel();
        restartAutoPlay();
      }}

      async function requestFullscreenMode() {{
        const el = document.documentElement;
        if (document.fullscreenElement) {{
          if (document.exitFullscreen) {{
            await document.exitFullscreen();
          }}
          return;
        }}
        if (el.requestFullscreen) {{
          await el.requestFullscreen();
        }}
        dockFullscreenButton();
      }}

      document.documentElement.lang = i18n.htmlLang;
      updateFullscreenButtonLabel();
      bindArrowHandlers(document);
      autoPlayBtnEl.addEventListener("click", configureAutoPlay);
      fullscreenDockBtnEl.addEventListener("click", () => {{
        void requestFullscreenMode();
      }});
      fullscreenBtnEl.addEventListener("click", () => {{
        void requestFullscreenMode();
      }});
      document.addEventListener("fullscreenchange", () => {{
        if (document.fullscreenElement) {{
          fullscreenOverlayEl.classList.add("hidden");
          fullscreenDockBtnEl.classList.add("visible");
        }}
        updateFullscreenButtonLabel();
      }});
      frameEl.addEventListener("load", () => {{
        try {{
          if (frameEl.contentDocument) {{
            bindArrowHandlers(frameEl.contentDocument);
            bindClickNavHandlers(frameEl.contentDocument);
          }}
          fitFrameContent();
        }} catch {{
          // Ignore cross-origin style access errors; srcdoc should normally be same-origin.
        }}
      }});
      window.addEventListener("resize", updateRootScale);
      updateAutoPlayButtonLabel();
      playerCanvasEl.style.width = pageWidth + "px";
      playerCanvasEl.style.height = pageHeight + "px";
      updateRootScale();

      void render();
    </script>
  </body>
</html>
"""


def build_html_player_zip(
    project_dir: str | Path,
    *,
    title: str | None = None,
    project_id: str | None = None,
) -> tuple[bytes, str]:
    """Build a zip containing ``{slug}/index.html``.

    Returns ``(zip_bytes, download_filename)``.
    """
    pages = collect_html_pages(project_dir)
    display_title = (title or "").strip() or project_id or "presentation"
    slug = _safe_slug(display_title, fallback=project_id or "presentation")
    player_data = build_player_data(pages)
    index_html = render_player_index_html(title=display_title, player_data=player_data)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{slug}/index.html", index_html.encode("utf-8"))
    return buf.getvalue(), f"{slug}-html.zip"


def write_html_player_export(
    project_dir: str | Path,
    *,
    title: str | None = None,
    project_id: str | None = None,
    out_path: str | Path | None = None,
) -> Path:
    """Write the HTML player zip under ``exports/`` (or ``out_path``)."""
    zip_bytes, filename = build_html_player_zip(
        project_dir, title=title, project_id=project_id
    )
    if out_path is None:
        exports = Path(project_dir) / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        out_path = exports / filename
    else:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(zip_bytes)
    return out_path
