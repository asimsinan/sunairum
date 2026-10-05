"""HTML SoT helpers: author → html_output/ + preview PNG (feeds deckhtml)."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
from typing import Any

from tasks.html_constitution import (
    report_to_dict,
    validate_slide_html,
    wrap_slide_fragment,
)
from tasks.html_flags import ensure_html_dirs, slide_stem


# A bare ordinal such as ``01`` is legitimate diagram furniture.  Treating
# every one/two digit leaf as page chrome deleted process-node badges after the
# visual author had placed them, leaving connector lines crossing empty space.
# Unqualified numbers are removed only from elements whose attributes identify
# them as footer/page furniture; slash labels and explicit P-prefixed labels are
# unambiguous anywhere.
_HTML_PAGE_ONLY_RE = re.compile(r"^(?:P\d{1,2}|\d{1,2}\s*/\s*\d{1,2})$", re.I)
_HTML_BARE_PAGE_ORDINAL_RE = re.compile(r"^\d{1,2}$")
_HTML_PAGE_ATTR_RE = re.compile(
    r"(?:page(?:[-_\s]?number)?|pagination|slide[-_\s]?(?:number|index)|footer|folio)",
    re.I,
)
_HTML_PLANNER_CODE_RE = re.compile(
    r"^P\d{2}(?:\s*/\s*|\s*[·•|]\s*|\s+).+",
    re.I,
)
_HTML_PAGE_MARKER_RE = re.compile(
    r"<[^>]*\bdata-sunairum-page-number\b[^>]*>[\s\S]*?</[^>]+>",
    re.I,
)
_HTML_LEAF_CHROME_RE = re.compile(
    r"<(?P<tag>div|span|p|footer|small|em|strong|b|i|label|aside)\b"
    r"(?P<attrs>[^>]*)>(?P<body>[^<]*)</(?P=tag)\s*>",
    re.I | re.S,
)


def format_slide_page_label(slide_number: int, total_slides: int | None = None) -> str:
    """Canonical footer label: ``1/8``, ``2/8`` (no zero-pad, no ``P`` prefix)."""
    n = max(1, int(slide_number or 1))
    if total_slides is not None and int(total_slides) > 0:
        return f"{n}/{int(total_slides)}"
    return str(n)


def _html_plain_text(markup: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", markup or "")
    return re.sub(r"\s+", " ", plain).strip()


def _html_page_number_inset(html: str, label: str) -> tuple[float, float]:
    """``(right_px, bottom_px)`` for page chrome clear of bottom-right callouts.

    Mirrors SVG ``_page_number_anchor`` (absolute end-anchored glyph), converted to
    CSS ``right`` / ``bottom`` for the HTML footer.
    """
    from tasks.html_constitution import CANVAS_H, CANVAS_W

    # Match SVG defaults: x=1220 end-anchor, y=698 baseline.
    default_x, default_y = 1220.0, 698.0
    label_w = max(40.0, len(label or "00 / 00") * 12.0 * 0.55)
    label_h = 16.0

    def _to_inset(x: float, y: float) -> tuple[float, float]:
        # End-anchored baseline → CSS right/bottom of a line box ~label_h tall.
        right = max(0.0, CANVAS_W - x)
        bottom = max(0.0, CANVAS_H - y)
        return right, bottom

    def _glyph_box(x: float, y: float) -> tuple[float, float, float, float]:
        return (x - label_w - 4.0, y - 12.0, label_w + 8.0, label_h)

    def _overlap(
        a: tuple[float, float, float, float], b: tuple[float, float, float, float]
    ) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

    blockers: list[tuple[float, float, float, float]] = []
    for match in re.finditer(
        r"<[^>]+style=(['\"])(.*?)\1[^>]*>", html or "", flags=re.I | re.S
    ):
        style = match.group(2) or ""
        if not re.search(r"position\s*:\s*absolute", style, flags=re.I):
            continue
        try:
            left_m = re.search(r"(?:^|;)\s*left\s*:\s*(-?[\d.]+)px", style, flags=re.I)
            top_m = re.search(r"(?:^|;)\s*top\s*:\s*(-?[\d.]+)px", style, flags=re.I)
            w_m = re.search(r"(?:^|;)\s*width\s*:\s*(-?[\d.]+)px", style, flags=re.I)
            h_m = re.search(r"(?:^|;)\s*height\s*:\s*(-?[\d.]+)px", style, flags=re.I)
            if not (left_m and top_m and w_m and h_m):
                continue
            x, y = float(left_m.group(1)), float(top_m.group(1))
            w, h = float(w_m.group(1)), float(h_m.group(1))
        except (TypeError, ValueError):
            continue
        if w < 80.0 or h < 36.0:
            continue
        if y + h < 620.0 or x + w < 900.0:
            continue
        blockers.append((x, y, w, h))

    def _clear(x: float, y: float) -> bool:
        box = _glyph_box(x, y)
        return not any(_overlap(box, b) for b in blockers)

    if _clear(default_x, default_y):
        return _to_inset(default_x, default_y)

    covering = [b for b in blockers if _overlap(_glyph_box(default_x, default_y), b)]
    if covering:
        top = min(b[1] for b in covering)
        lifted = max(600.0, top - 10.0)
        if _clear(default_x, lifted):
            return _to_inset(default_x, lifted)
        left = min(b[0] for b in covering)
        shifted = max(200.0, left - 12.0)
        if _clear(shifted, default_y):
            return _to_inset(shifted, default_y)

    for y in range(698, 599, -8):
        if _clear(default_x, float(y)):
            return _to_inset(default_x, float(y))
    return _to_inset(default_x, default_y)


def sanitize_html_presentation_chrome(
    html: str,
    *,
    slide_number: int,
    total_slides: int | None = None,
    chrome_color: str | None = None,
) -> str:
    """Strip LLM page-number variants; inject one bottom-right ``n/N`` footer."""
    from tasks.html_constitution import CANVAS_H, CANVAS_W, ensure_slide_root

    doc = ensure_slide_root(html or "")
    cleaned = _HTML_PAGE_MARKER_RE.sub("", doc)

    def _drop_leaf(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        if re.search(r"\bdata-pptx\b", attrs, flags=re.I):
            return match.group(0)
        plain = _html_plain_text(match.group("body") or "")
        if not plain:
            return match.group(0)
        identified_chrome = (
            str(match.group("tag") or "").casefold() == "footer"
            or bool(_HTML_PAGE_ATTR_RE.search(attrs))
        )
        if (
            _HTML_PAGE_ONLY_RE.fullmatch(plain)
            or _HTML_PLANNER_CODE_RE.match(plain)
            or (identified_chrome and _HTML_BARE_PAGE_ORDINAL_RE.fullmatch(plain))
        ):
            return ""
        return match.group(0)

    # Repeat so nested wrappers of chrome-only leaves collapse.
    for _ in range(3):
        nxt = _HTML_LEAF_CHROME_RE.sub(_drop_leaf, cleaned)
        if nxt == cleaned:
            break
        cleaned = nxt

    label = format_slide_page_label(slide_number, total_slides)
    fill = str(chrome_color or "#94A3B8").strip() or "#94A3B8"
    if not fill.startswith("#"):
        fill = "#94A3B8"
    right_px, bottom_px = _html_page_number_inset(cleaned, label)
    # Sit in the margin band; lift/shift when a callout owns the default corner.
    footer = (
        f'<div data-sunairum-page-number="1" aria-hidden="true" '
        f'style="position:absolute;right:{right_px:.0f}px;bottom:{bottom_px:.0f}px;z-index:40;'
        f'font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:600;'
        f'letter-spacing:0.04em;line-height:18px;height:18px;color:{fill};pointer-events:none;'
        f'user-select:none;">{label}</div>'
    )

    # Prefer insert before closing .slide section.
    section_close = re.search(
        r"(</section\s*>)(\s*</body\s*>)",
        cleaned,
        flags=re.I,
    )
    if section_close:
        return (
            cleaned[: section_close.start(1)]
            + footer
            + cleaned[section_close.start(1) :]
        )
    body_close = re.search(r"</body\s*>", cleaned, flags=re.I)
    if body_close:
        return cleaned[: body_close.start()] + footer + cleaned[body_close.start() :]
    # Last resort: append inside a minimal slide wrapper.
    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"/></head><body>'
        f'<section class="slide" style="width:{CANVAS_W}px;height:{CANVAS_H}px;'
        f'position:relative;">{cleaned}{footer}</section></body></html>'
    )


def sanitize_html_audience_copy(html: str) -> tuple[str, dict[str, Any]]:
    """Remove internal provenance addresses from rendered copy, recursively.

    This is the last boundary before preview/export and therefore also repairs
    resumed projects whose strategist payload predates the planner scrubber.
    Machine-readable IDs remain in attributes; only visible text nodes change.
    Empty recovery cards created solely by a split annotation are removed.
    """
    if not html or not re.search(r"(?:evidence\s*=|ev-page-|src-table-|pdf-page-)", html, re.I):
        return html, {"changed": False, "text_nodes": 0, "empty_cards": 0}
    try:
        from lxml import html as lxml_html
        from tasks.grounded_planner import strip_catalog_provenance_annotations
    except ImportError:  # pragma: no cover
        return html, {"changed": False, "text_nodes": 0, "empty_cards": 0, "skipped": "dependency_unavailable"}
    try:
        document = lxml_html.document_fromstring(html)
    except (TypeError, ValueError):
        return html, {"changed": False, "text_nodes": 0, "empty_cards": 0, "skipped": "html_unreadable"}
    changed = 0
    for node in document.iter():
        if str(getattr(node, "tag", "")).casefold() in {"style", "script"}:
            continue
        if node.text:
            cleaned = strip_catalog_provenance_annotations(node.text)
            if cleaned != node.text:
                node.text = cleaned
                changed += 1
        if node.tail:
            cleaned = strip_catalog_provenance_annotations(node.tail)
            if cleaned != node.tail:
                node.tail = cleaned
                changed += 1
    empty_cards = 0
    for card in list(document.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " scene-card ")]'
    )):
        text = re.sub(r"\s+", " ", card.text_content() or "").strip()
        owns_media = bool(card.xpath('.//*[self::img or self::table or @data-pptx]'))
        if text or owns_media:
            continue
        parent = card.getparent()
        if parent is not None:
            parent.remove(card)
            empty_cards += 1
    if not changed and not empty_cards:
        return html, {"changed": False, "text_nodes": 0, "empty_cards": 0}
    rendered = lxml_html.tostring(document, encoding="unicode", method="html", doctype="<!doctype html>")
    return rendered, {"changed": True, "text_nodes": changed, "empty_cards": empty_cards}


_FONT_SIZE_DECL_RE = re.compile(r"font-size\s*:\s*([\d.]+)px", re.I)


def _declared_font_size(stylesheet: str, node: Any) -> float:
    """Largest font-size the document declares for this element's own classes."""
    largest = 0.0
    for token in str(node.get("class") or "").split():
        for match in re.finditer(
            r"\.%s\s*\{([^{}]*)\}" % re.escape(token), stylesheet
        ):
            for size in _FONT_SIZE_DECL_RE.findall(match.group(1)):
                try:
                    largest = max(largest, float(size))
                except ValueError:
                    continue
    inline = _FONT_SIZE_DECL_RE.search(node.get("style") or "")
    if inline:
        try:
            largest = max(largest, float(inline.group(1)))
        except ValueError:
            pass
    return largest


def _drop_declarations(style: str, properties: tuple[str, ...]) -> str:
    kept = []
    for declaration in style.split(";"):
        name = declaration.split(":", 1)[0].strip().casefold()
        if not name or name in properties:
            continue
        kept.append(declaration.strip())
    return ";".join(kept) + (";" if kept else "")


def relax_frozen_text_heights(html: str) -> tuple[str, dict[str, Any]]:
    """Turn a frozen inline height on a text box into a floor.

    The deck editor bakes ``left/top/width/height`` when it lifts an element to
    freeform, and that height is whatever the element measured at that instant.
    If a typography pass had temporarily shrunk the copy, the box keeps the
    small size for good: a display number frozen at ``height:16px`` while it was
    shrunk to 14px kept that box when it returned to 104px, and its glyphs were
    drawn straight across the paragraph beneath it.

    ``min-height`` preserves the size the author dragged while letting the copy
    have the room it needs, so this is applied unconditionally rather than only
    where an overflow is already measurable — the point is that the box can
    never crush its own text again.
    """
    if not html or "data-sun-freeform" not in html:
        return html, {"changed": False, "boxes": 0}
    try:
        from lxml import html as lxml_html
    except ImportError:  # pragma: no cover - production image includes lxml
        return html, {"changed": False, "boxes": 0, "skipped": "dependency_unavailable"}
    try:
        document = lxml_html.document_fromstring(html)
    except (TypeError, ValueError):
        return html, {"changed": False, "boxes": 0, "skipped": "html_unreadable"}

    height_declaration = re.compile(r"(?<![-\w])height\s*:\s*([\d.]+)px\s*;?", re.I)
    stylesheet = "\n".join(node.text or "" for node in document.xpath("//style"))
    relaxed = 0
    restored = 0
    for node in document.xpath('//*[@data-sun-freeform="1"]'):
        style = node.get("style") or ""
        frozen = height_declaration.search(style)
        if not frozen:
            continue
        owns_text = bool((node.text or "").strip()) or any(
            (child.tail or "").strip() for child in node
        )
        if not owns_text:
            continue
        if re.search(r"min-height\s*:", style, re.I):
            continue
        # A single line can never be shorter than its own type, so a frozen box
        # smaller than the element's font-size was measured while the layout was
        # broken — here, while a fit pass had the numeral down at 14px. Such a
        # freeze is not a placement worth preserving: its pinned offsets are
        # stale too, and keeping them only moves the element somewhere else on
        # the slide. Give the element back to the flow it was authored in.
        if float(frozen.group(1)) + 1 < _declared_font_size(stylesheet, node):
            node.set(
                "style",
                _drop_declarations(
                    style,
                    (
                        "position", "left", "top", "right", "bottom",
                        "width", "height",
                        # The zeroed margin was part of the same absolutization;
                        # left behind it overrides the spacing the author set to
                        # separate this block from the one under it.
                        "margin", "margin-top", "margin-bottom",
                        "margin-left", "margin-right", "max-width",
                    ),
                ),
            )
            restored += 1
            continue
        updated = height_declaration.sub(
            lambda match: f"min-height:{match.group(1)}px;height:auto;", style, count=1
        )
        if updated != style:
            node.set("style", updated)
            relaxed += 1
    if not relaxed and not restored:
        return html, {"changed": False, "boxes": 0, "restored_to_flow": 0}
    rendered = lxml_html.tostring(
        document, encoding="unicode", method="html", doctype="<!doctype html>"
    )
    return rendered, {
        "changed": True,
        "boxes": relaxed,
        "restored_to_flow": restored,
    }


def normalize_html_font_families(html: str) -> tuple[str, dict[str, Any]]:
    """Rewrite every authored font stack to a family the exporter can embed.

    This runs before Chromium measures anything, so all three renderers agree.
    An authored ``Arial`` is invisible in the container (fontconfig aliases it to
    Source Sans 3) but decisive on the reader's machine, where PowerPoint prefers
    their installed Arial over the face we embed under that name: the deck then
    lays out against metrics nobody measured, and text drifts out of the boxes
    the layout QA signed off. Naming the shipped family instead means no
    installed font can shadow it. See ``tasks.font_policy``.
    """
    from tasks.font_policy import normalize_font_stack

    if not html:
        return html, {"changed": False, "stacks": 0}

    rewritten = 0
    substitutions: dict[str, str] = {}

    def _rewrite_stack(stack: str) -> str:
        nonlocal rewritten
        normalized = normalize_font_stack(stack)
        if normalized.strip() != stack.strip():
            rewritten += 1
            substitutions.setdefault(stack.strip(), normalized)
        return normalized

    def _font_family_declaration(match: re.Match[str]) -> str:
        return f"{match.group('lead')}{_rewrite_stack(match.group('stack'))}"

    out = re.sub(
        r"(?P<lead>font-family\s*:\s*)(?P<stack>[^;{}\"']*(?:(?:\"[^\"]*\"|'[^']*')[^;{}\"']*)*)",
        _font_family_declaration,
        html,
        flags=re.I,
    )

    def _font_shorthand(match: re.Match[str]) -> str:
        # `font: 36px/44px Georgia, serif` — the family list is everything after
        # the size/line-height, which is the last positional component.
        return f"{match.group('lead')}{match.group('size')}{_rewrite_stack(match.group('stack'))}"

    out = re.sub(
        r"(?P<lead>[;{\"']\s*font\s*:\s*)"
        r"(?P<size>(?:[\w.%-]+\s+)*?[\d.]+(?:px|pt|em|rem|%)(?:\s*/\s*[\d.]+(?:px|pt|em|rem|%)?)?\s+)"
        r"(?P<stack>[^;{}]+)",
        _font_shorthand,
        out,
        flags=re.I,
    )
    return out, {
        "changed": rewritten > 0,
        "stacks": rewritten,
        "substitutions": substitutions,
    }


def normalize_inline_text_boundaries(html: str) -> tuple[str, dict[str, Any]]:
    """Restore word boundaries around authored emphasis runs.

    Markup such as ``value</strong>units`` is valid HTML but renders as one
    stacked word in both Chromium and PowerPoint. Geometry QA cannot identify
    the semantic defect, so normalize only emphasis boundaries where the two
    adjacent characters are word-like. Punctuation and generic spans are left
    unchanged.
    """
    if not html or not re.search(r"</?(?:b|strong|em|i)\b", html, flags=re.I):
        return html, {"changed": False, "boundaries": 0}
    try:
        from lxml import html as lxml_html
    except ImportError:  # pragma: no cover
        return html, {"changed": False, "boundaries": 0, "skipped": "dependency_unavailable"}
    try:
        document = lxml_html.document_fromstring(html)
    except (TypeError, ValueError):
        return html, {"changed": False, "boundaries": 0, "skipped": "html_unreadable"}

    def _word_start(value: str | None) -> bool:
        return bool(value and re.match(r"[\w\d]", value, flags=re.UNICODE))

    def _word_end(value: str | None) -> bool:
        return bool(value and re.search(r"[\w\d]$", value, flags=re.UNICODE))

    def _needs_space_before(value: str | None) -> bool:
        # Sentence punctuation requires following air too (``claim;<em>next``).
        return bool(value and re.search(r"(?:[\w\d]|[;,:!?])$", value, flags=re.UNICODE))

    changed = 0
    for node in document.xpath("//b | //strong | //em | //i"):
        inner = node.text_content() or ""
        if not _word_start(inner):
            continue
        previous = node.getprevious()
        parent = node.getparent()
        if previous is not None:
            prior = previous.tail or ""
            if _needs_space_before(prior):
                previous.tail = prior + " "
                changed += 1
        elif parent is not None:
            prior = parent.text or ""
            if _needs_space_before(prior):
                parent.text = prior + " "
                changed += 1
        # The same punctuation that needs air before the next word needs air
        # after itself: `<em>Interpretation:</em>candidate` rendered as
        # "Interpretation:candidate" because only word characters counted here.
        if _needs_space_before(inner) and _word_start(node.tail):
            node.tail = " " + str(node.tail)
            changed += 1
    if not changed:
        return html, {"changed": False, "boundaries": 0}
    rendered = lxml_html.tostring(
        document, encoding="unicode", method="html", doctype="<!doctype html>"
    )
    return rendered, {"changed": True, "boundaries": changed}


_PREVIEW_STUB_MAX_BYTES = 12_000  # real slide PNGs are typically 50KB+
# Pillow fallback banner fill used when Chromium/playwright is unavailable.
_PREVIEW_STUB_BANNER_RGB = (26, 54, 93)
_PREVIEW_STUB_BG_RGB = (245, 247, 250)


def _preview_looks_stub(png_path: str) -> bool:
    try:
        if not os.path.isfile(png_path):
            return True
        size = os.path.getsize(png_path)
        if size < _PREVIEW_STUB_MAX_BYTES:
            return True
    except OSError:
        return True

    # Full-size Pillow "Chromium unavailable" cards (~18–25KB) were slipping past
    # the byte threshold and poisoning history + thumbnails.
    try:
        from PIL import Image

        with Image.open(png_path) as im:
            if im.size != (1280, 720):
                return False
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
    except Exception:
        return False


def _render_preview_png_once(doc: str, png_path: str) -> None:
    """Single Chromium screenshot attempt (file:// is more reliable than set_content)."""
    import tempfile
    from pathlib import Path

    from playwright.sync_api import sync_playwright
    from tasks.html_constitution import CANVAS_H, CANVAS_W, PREVIEW_DEVICE_SCALE

    os.makedirs(os.path.dirname(os.path.abspath(png_path)) or ".", exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sunairum_preview_") as tmp:
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
                from tasks.html_render import _screenshot_slide, _settle_slide_page

                _settle_slide_page(page)
                _screenshot_slide(page, png_path, canvas_w=CANVAS_W, canvas_h=CANVAS_H)
            finally:
                browser.close()


def _render_preview_png_subprocess(doc: str, png_path: str) -> bool:
    """Fresh Python process — avoids Celery/fork Playwright deadlocks."""
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="sunairum_preview_sub_") as tmp:
        html_path = Path(tmp) / "slide.html"
        html_path.write_text(doc, encoding="utf-8")
        script = (
            "import sys\n"
            "from tasks.html_pipeline import _render_preview_png_once\n"
            "doc=open(sys.argv[1],encoding='utf-8').read()\n"
            "_render_preview_png_once(doc, sys.argv[2])\n"
        )
        runner = Path(tmp) / "run_preview.py"
        runner.write_text(script, encoding="utf-8")
        env = dict(os.environ)
        # Ensure tasks package resolves from fastapi root
        fastapi_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = fastapi_root + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, str(runner), str(html_path), str(png_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
            cwd=fastapi_root,
        )
        if completed.returncode != 0:
            print(
                f"[html] preview subprocess failed: "
                f"{(completed.stderr or completed.stdout or '')[:300]}"
            )
            return False
        return not _preview_looks_stub(png_path)


def _render_preview_png(html: str, png_path: str) -> bool:
    err: Exception | None = None
    from tasks.html_constitution import ensure_slide_root

    doc = ensure_slide_root(html)

    lock_path = os.path.join(os.path.dirname(os.path.abspath(png_path)) or ".", ".preview.lock")
    lock_fd = None
    try:
        import fcntl
        import time

        lock_fd = open(lock_path, "a+", encoding="utf-8")
        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.2)
        else:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
    except Exception:
        lock_fd = None

    try:
        from tasks.html_render import _sync_playwright_requires_subprocess

        if _sync_playwright_requires_subprocess():
            for attempt in range(2):
                if _render_preview_png_subprocess(doc, png_path):
                    return True
                print(f"[html] preview subprocess attempt {attempt + 1}/2 failed")
            err = RuntimeError("preview subprocess failed inside async/Celery context")
        else:
            for attempt in range(2):
                try:
                    _render_preview_png_once(doc, png_path)
                    if not _preview_looks_stub(png_path):
                        return True
                    err = RuntimeError(
                        f"stub-sized preview ({os.path.getsize(png_path)} bytes)"
                    )
                    print(f"[html] preview attempt {attempt + 1}/2 produced stub: {err}")
                except Exception as exc:
                    err = exc
                    print(
                        f"[html] preview playwright attempt {attempt + 1}/2 failed: {exc}"
                    )
                try:
                    import time

                    time.sleep(0.4 * (attempt + 1))
                except Exception:
                    pass

            if _render_preview_png_subprocess(doc, png_path):
                return True
    finally:
        if lock_fd is not None:
            try:
                import fcntl

                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_fd.close()
            except Exception:
                pass

    # Pillow text fallback (never claim success as a real slide preview)
    try:
        from PIL import Image, ImageDraw

        plain = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
        plain = re.sub(r"<style[\s\S]*?</style>", " ", plain, flags=re.I)
        plain = re.sub(r"<br\s*/?>", "\n", plain, flags=re.I)
        plain = re.sub(r"<[^>]+>", " ", plain)
        plain = re.sub(r"[ \t]+", " ", plain)
        lines = [ln.strip() for ln in plain.splitlines() if ln.strip()][:8]
        img = Image.new("RGB", (1280, 720), (245, 247, 250))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 1280, 72], fill=(26, 54, 93))
        draw.text((40, 24), "Slide preview (Chromium unavailable)", fill=(255, 255, 255))
        y = 110
        for line in lines or ["(empty slide)"]:
            draw.text((60, y), line[:90], fill=(26, 32, 44))
            y += 36
        if err is not None:
            draw.text((60, 660), str(err)[:110], fill=(148, 163, 184))
        img.save(png_path)
        return False
    except Exception:
        return False


def repair_stub_previews(storage_dir: str, *, force: bool = False) -> dict[str, Any]:
    """Re-render stub / Chromium-unavailable preview PNGs from html_output."""
    html_dir = os.path.join(storage_dir, "html_output")
    preview_dir = os.path.join(storage_dir, "preview")
    repaired: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    if not os.path.isdir(html_dir):
        return {"repaired": repaired, "failed": failed, "skipped": skipped}
    os.makedirs(preview_dir, exist_ok=True)
    for name in sorted(os.listdir(html_dir)):
        if not re.fullmatch(r"slide_\d+\.html", name):
            continue
        stem = name[:-5]
        html_path = os.path.join(html_dir, name)
        png_path = os.path.join(preview_dir, f"{stem}.png")
        if not force and not _preview_looks_stub(png_path):
            skipped.append(stem)
            continue
        try:
            html = open(html_path, encoding="utf-8").read()
        except OSError as exc:
            failed.append(f"{stem}:{exc}")
            continue
        ok = _render_preview_png(html, png_path)
        if ok and not _preview_looks_stub(png_path):
            repaired.append(stem)
        else:
            failed.append(stem)
    return {"repaired": repaired, "failed": failed, "skipped": skipped}


def inject_formula_into_html(
    html: str,
    *,
    storage_dir: str,
    slide: dict[str, Any],
    color_palette: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Fill data-pptx=formula hosts with MathML (editable OMML via deckhtml)."""
    del storage_dir  # reserved for future asset cache; MathML is inline
    if not html:
        return html, None
    has_host = bool(re.search(r'data-pptx=["\']formula["\']', html, flags=re.I))
    formula = str(slide.get("formula") or "").strip()
    formula_tex = str(slide.get("formula_tex") or "").strip()
    if not has_host and not (formula or formula_tex):
        return html, None

    already = bool(
        re.search(
            r'data-pptx=["\']formula["\'][^>]*>\s*(?:<math\b|[^<]*data-sunairum-formula)',
            html,
            flags=re.I | re.S,
        )
    )

    ink = (
        (color_palette or {}).get("primary")
        or (color_palette or {}).get("body_text")
        or "#1A365D"
    )
    try:
        from tasks.formula_prerender import prerender_formula_mathml_for_slide
        from tasks.formula_math_render import mathml_host_inner_html
    except ImportError:  # pragma: no cover
        from formula_prerender import prerender_formula_mathml_for_slide  # type: ignore
        from formula_math_render import mathml_host_inner_html  # type: ignore

    if already:
        return html, {"status": "already_filled"}
    if not has_host:
        raise ValueError("Scene v2 formula slide is missing its resolved formula host")

    prerender_formula_mathml_for_slide(slide, theme={"ink": ink, "primary": ink})
    math = slide.get("_formula_math") if isinstance(slide.get("_formula_math"), dict) else None
    filler = ""
    if math:
        filler = mathml_host_inner_html(math, color=str(ink))
    if not filler:
        import html as html_lib

        plain = formula_tex or formula
        plain = re.sub(r"^\\\(|\\\)$|^\\\[|\\\]$|^\$+|\$+$", "", plain).strip()
        if not plain:
            return html, None
        safe = html_lib.escape(plain)
        # Span only — host regex closes on first </div>
        filler = (
            f'<span data-sunairum-formula-fallback="1" style="display:block;'
            f'font-family:Georgia,\"Times New Roman\",serif;font-size:24px;line-height:1.2;'
            f'color:{html_lib.escape(str(ink))};text-align:center;">{safe}</span>'
        )

    host_re = re.compile(
        r'(<div\b[^>]*\bdata-pptx=["\']formula["\'][^>]*>)(.*?)(</div>)',
        flags=re.I | re.S,
    )
    out = host_re.sub(lambda m: f"{m.group(1)}{filler}{m.group(3)}", html, count=1)
    has_mathml = bool(math and str(math.get("mathml") or "").strip())
    return out, {
        "status": "filled",
        "has_mathml": has_mathml,
        "has_png": False,
        "formula_id": str(slide.get("formula_id") or "f1"),
    }


def _match_div_block(
    html: str, open_start: int
) -> tuple[str, str, str, int] | None:
    """Return a balanced ``div`` block beginning at ``open_start``."""
    if open_start < 0 or open_start >= len(html):
        return None
    opening = re.match(r"<div\b[^>]*>", html[open_start:], flags=re.I)
    if not opening:
        return None
    open_tag = opening.group(0)
    body_start = open_start + opening.end()
    opens = re.compile(r"<div\b", flags=re.I)
    closes = re.compile(r"</div\s*>", flags=re.I)
    cursor = body_start
    depth = 1
    while cursor < len(html) and depth:
        next_open = opens.search(html, cursor)
        next_close = closes.search(html, cursor)
        if not next_close:
            return None
        if next_open and next_open.start() < next_close.start():
            depth += 1
            cursor = next_open.end()
            continue
        depth -= 1
        if depth == 0:
            return (
                open_tag,
                html[body_start : next_close.start()],
                next_close.group(0),
                next_close.end(),
            )
        cursor = next_close.end()
    return None


def _cell_text(cell: Any) -> str:
    if isinstance(cell, dict):
        return str(cell.get("text") or cell.get("value") or cell.get("name") or "")
    return str(cell or "")


def _load_table_payload(storage_dir: str, table_id: str) -> dict[str, Any] | None:
    """Resolve table rows/columns from source_tables.json when needed."""
    import json

    tid = str(table_id or "").strip()
    if not tid:
        return None
    path = os.path.join(storage_dir, "sources", "source_tables.json")
    if not os.path.isfile(path):
        return None
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError):
        return None
    tables = data.get("tables") if isinstance(data, dict) else data
    if isinstance(tables, dict):
        tables = tables.get("tables") or []
    if not isinstance(tables, list):
        return None
    for table in tables:
        if not isinstance(table, dict):
            continue
        if str(table.get("table_id") or table.get("id") or "").strip() != tid:
            continue
        payload = dict(table)
        columns = payload.get("columns")
        headers = payload.get("headers")
        if not isinstance(columns, list) or not columns:
            if isinstance(headers, list) and headers:
                payload["columns"] = list(headers)
        rows = payload.get("rows")
        if not isinstance(rows, list):
            rows = payload.get("data") or []
            payload["rows"] = rows
        payload.setdefault("header_rows", 1)
        return payload
    return None


def _payload_from_preview_html(html: str) -> dict[str, Any] | None:
    """Rebuild columns/rows from an already-filled table preview host."""
    m = re.search(
        r'<table\b[^>]*data-sunairum-table-preview[^>]*>(.*?)</table>',
        html or "",
        flags=re.I | re.S,
    )
    if not m:
        return None
    body = m.group(1)
    rows_html = re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, flags=re.I | re.S)
    if not rows_html:
        return None

    def _cells(tr: str) -> list[str]:
        return [
            re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, flags=re.I | re.S)
        ]

    parsed = [_cells(tr) for tr in rows_html]
    parsed = [r for r in parsed if any(r)]
    if not parsed:
        return None
    # Header row if first cells look like labels / th present.
    has_th = bool(re.search(r"<th\b", rows_html[0], flags=re.I))
    if has_th:
        return {"columns": parsed[0], "rows": parsed[1:], "header_rows": 1}
    return {"columns": [], "rows": parsed, "header_rows": 0}


def _load_table_payload_fallback(
    storage_dir: str, html: str
) -> dict[str, Any] | None:
    """Best-effort payload when host data-table-id does not match source ids."""
    preview = _payload_from_preview_html(html)
    if preview and (preview.get("rows") or preview.get("columns")):
        return preview
    import json

    path = os.path.join(storage_dir, "sources", "source_tables.json")
    if not os.path.isfile(path):
        return None
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError):
        return None
    tables = data.get("tables") if isinstance(data, dict) else data
    if not isinstance(tables, list) or not tables:
        return None
    best = None
    best_n = -1
    for table in tables:
        if not isinstance(table, dict):
            continue
        rows = table.get("rows") or table.get("data") or []
        n = len(rows) if isinstance(rows, list) else 0
        if n > best_n:
            best_n = n
            best = table
    if not isinstance(best, dict):
        return None
    return _load_table_payload(
        storage_dir, str(best.get("table_id") or best.get("id") or "")
    ) or (
        {
            "columns": best.get("columns") or best.get("headers") or [],
            "rows": best.get("rows") or best.get("data") or [],
            "header_rows": 1,
        }
    )


def _looks_numeric_cell(text: str) -> bool:
    t = (text or "").strip().replace(",", "")
    if not t:
        return False
    return bool(re.match(r"^[<>~±]?\s*[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\s*[%x×*]?\s*$", t))


def _px_from_style(style: str, prop: str) -> float | None:
    m = re.search(
        rf"(?:^|;)\s*{re.escape(prop)}\s*:\s*(-?[\d.]+)px",
        style or "",
        flags=re.I,
    )
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _table_wrap_lines(text: str, *, col_w: float, font_size: float, pad_x: float) -> int:
    """Rough wrap-line count for a fixed-layout cell (Arial-ish)."""
    usable = max(28.0, col_w - 2 * pad_x)
    # Slightly optimistic char width so we do not over-shrink dense tables.
    char_w = max(4.0, font_size * 0.50)
    per_line = max(6, int(usable / char_w))
    t = (text or "").strip() or " "
    return max(1, (len(t) + per_line - 1) // per_line)


def _table_column_widths(columns: list[Any], rows: list[Any], host_w: float) -> list[float]:
    n_cols = max(len(columns), max((len(r) for r in rows if isinstance(r, (list, tuple))), default=1), 1)
    weights: list[float] = []
    for ci in range(n_cols):
        values = [_cell_text(columns[ci])] if ci < len(columns) else []
        values.extend(_cell_text(row[ci]) for row in rows[:12] if isinstance(row, (list, tuple)) and ci < len(row))
        numeric = bool(values) and sum(_looks_numeric_cell(v) for v in values[1:] or values) >= max(1, len(values[1:] or values) // 2)
        longest = max((len(v) for v in values), default=1)
        weights.append(1.0 if numeric else max(1.5, min(4.0, longest / 9.0)))
    total = sum(weights) or 1.0
    return [host_w * weight / total for weight in weights]


def _estimate_table_natural_height(
    columns: list[Any],
    rows: list[Any],
    *,
    host_w: float,
    pad_y: float,
    pad_x: float,
    fs_body: float,
    fs_head: float,
) -> float:
    n_cols = max(
        len(columns),
        max((len(r) for r in rows if isinstance(r, (list, tuple))), default=1),
        1,
    )
    col_widths = _table_column_widths(columns, rows, host_w)
    col_w = col_widths[0] if col_widths else host_w / n_cols
    # Header + 1px border per row
    height = pad_y * 2 + fs_head * 1.25 + 1.0
    for row in rows:
        cells = row if isinstance(row, (list, tuple)) else [row]
        method = _cell_text(cells[0]) if cells else ""
        lines = _table_wrap_lines(
            method, col_w=col_w, font_size=fs_body, pad_x=pad_x
        )
        height += pad_y * 2 + lines * fs_body * 1.25 + 1.0
    return height


def _table_density_for_host(
    columns: list[Any],
    rows: list[Any],
    *,
    host_w: float,
    host_h: float,
) -> dict[str, float]:
    """Uniformly shrink padding/fonts so the table fits the host height."""
    pad_y, pad_x = 14.0, 18.0
    fs_body, fs_head = 15.0, 12.0
    if host_h <= 0 or host_w <= 0:
        return {
            "pad_y": pad_y,
            "pad_x": pad_x,
            "fs_body": fs_body,
            "fs_head": fs_head,
            "scale": 1.0,
        }
    natural = _estimate_table_natural_height(
        columns,
        rows,
        host_w=host_w,
        pad_y=pad_y,
        pad_x=pad_x,
        fs_body=fs_body,
        fs_head=fs_head,
    )
    if natural <= host_h + 0.5:
        return {
            "pad_y": pad_y,
            "pad_x": pad_x,
            "fs_body": fs_body,
            "fs_head": fs_head,
            "scale": 1.0,
            "natural_h": natural,
        }
    scale = max(0.55, min(1.0, (host_h - 2.0) / natural))
    # Floors keep labels readable; prefer tighter pad before unreadably small type.
    return {
        "pad_y": max(4.0, round(pad_y * scale)),
        "pad_x": max(6.0, round(pad_x * scale)),
        "fs_body": max(10.0, round(fs_body * scale)),
        "fs_head": max(9.0, round(fs_head * scale)),
        "scale": scale,
        "natural_h": natural,
    }


def _render_table_html(
    payload: dict[str, Any],
    *,
    accent: str = "#1A365D",
    accent_soft: str = "#EBF4FB",
    host_w: float | None = None,
    host_h: float | None = None,
) -> str:
    """Polished HTML table preview (pipeline-owned; Executor leaves host empty)."""
    import html as html_lib

    columns = payload.get("columns") if isinstance(payload.get("columns"), list) else []
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    if not columns and not rows:
        return ""
    # Infer numeric columns from body samples
    numeric_cols: set[int] = set()
    for ci in range(max(len(columns), max((len(r) for r in rows if isinstance(r, (list, tuple))), default=0))):
        samples = []
        for row in rows[:8]:
            if isinstance(row, (list, tuple)) and ci < len(row):
                samples.append(_cell_text(row[ci]))
        if samples and sum(1 for s in samples if _looks_numeric_cell(s)) >= max(1, len(samples) // 2):
            numeric_cols.add(ci)

    dens = _table_density_for_host(
        columns,
        rows,
        host_w=float(host_w or 580.0),
        host_h=float(host_h or 440.0),
    )
    pad_y = int(dens["pad_y"])
    pad_x = int(dens["pad_x"])
    fs_body = int(dens["fs_body"])
    fs_head = int(dens["fs_head"])
    pad = f"{pad_y}px {pad_x}px"
    col_widths = _table_column_widths(columns, rows, float(host_w or 580.0))
    col_total = sum(col_widths) or 1.0
    colgroup = "<colgroup>" + "".join(
        f'<col style="width:{width / col_total * 100:.2f}%">' for width in col_widths
    ) + "</colgroup>"

    head_cells = []
    for ci, col in enumerate(columns):
        align = "right" if ci in numeric_cols else "left"
        head_cells.append(
            f'<th style="padding:{pad};text-align:{align};font-size:{fs_head}px;font-weight:700;'
            f'letter-spacing:0.05em;text-transform:uppercase;color:#FFFFFF;'
            f'background:{accent};'
            f'border:none;border-right:1px solid rgba(255,255,255,.14);">'
            f"{html_lib.escape(_cell_text(col))}</th>"
        )
    body_rows = []
    for i, row in enumerate(rows):
        cells = row if isinstance(row, (list, tuple)) else [row]
        bg = "#FFFFFF" if i % 2 == 0 else accent_soft
        tds = []
        for ci, cell in enumerate(cells):
            text = _cell_text(cell)
            align = "right" if ci in numeric_cols else "left"
            weight = "700" if ci == 0 else "500"
            color = accent if ci == 0 else "#1A202C"
            tds.append(
                f'<td style="padding:{pad};font-size:{fs_body}px;font-weight:{weight};'
                f'color:{color};text-align:{align};border:none;'
                f'border-bottom:1px solid #E2E8F0;background:{bg};'
                f'line-height:1.25;vertical-align:middle;">'
                f"{html_lib.escape(text)}</td>"
            )
        body_rows.append(f"<tr>{''.join(tds)}</tr>")
    thead = f"<thead><tr>{''.join(head_cells)}</tr></thead>" if head_cells else ""
    tbody = f"<tbody>{''.join(body_rows)}</tbody>" if body_rows else ""
    return (
        # Chrome fills the host card; table rows stay flex:none (no giant empty cells).
        f'<div data-sunairum-table-chrome="1" style="width:100%;height:100%;'
        f'flex:1 1 auto;min-height:0;'
        f'overflow:hidden;background:#FFFFFF;'
        f'display:flex;flex-direction:column;justify-content:flex-start;">'
        # flex:none — never stretch rows to fill the host (was flex:1 → huge empty cells)
        f'<table data-sunairum-table-preview="1" style="width:100%;flex:none;height:auto;'
        f'border-collapse:collapse;table-layout:fixed;'
        f'font-family:Arial,Helvetica,sans-serif;">'
        f"{colgroup}{thead}{tbody}</table></div>"
    )


def inject_table_into_html(
    html: str,
    *,
    storage_dir: str,
    slide: dict[str, Any],
    native_payloads: dict[str, dict[str, Any]] | None = None,
    color_palette: dict[str, str] | None = None,
    host_box: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Fill/refresh data-pptx=table hosts with a polished HTML table preview."""
    if not html or not re.search(r'data-pptx=["\']table["\']', html, flags=re.I):
        return html, None

    tid = str(slide.get("table_id") or "").strip()
    if not tid:
        m = re.search(r'data-table-id=["\']([^"\']+)["\']', html, flags=re.I)
        tid = m.group(1).strip() if m else ""
    payloads = native_payloads or {}
    payload = None
    if tid:
        payload = payloads.get(tid) or payloads.get("t1")
    if not isinstance(payload, dict) or not (
        payload.get("columns") or payload.get("rows")
    ):
        slide_table = slide.get("table")
        if isinstance(slide_table, dict):
            payload = slide_table
    if not isinstance(payload, dict) or not (
        payload.get("columns") or payload.get("rows")
    ):
        payload = _load_table_payload(storage_dir, tid) if tid else None
    if not isinstance(payload, dict) or not (
        payload.get("columns") or payload.get("rows")
    ):
        # Alias IDs (e.g. solomon-results-table) — fall back to largest source table
        # or cells already painted into the host preview.
        payload = _load_table_payload_fallback(storage_dir, html)
    if not isinstance(payload, dict):
        return html, {"error": f"no payload for {tid or 'table'}"}

    accent = (
        (color_palette or {}).get("primary")
        or (color_palette or {}).get("ink")
        or "#1A365D"
    )
    soft = (
        (color_palette or {}).get("panel")
        or (color_palette or {}).get("surface")
        or "#EBF4FB"
    )

    host_open_re = re.compile(
        r'<div\b[^>]*\bdata-pptx=["\']table["\'][^>]*>',
        flags=re.I,
    )
    host_open_m = host_open_re.search(html)
    if not host_open_m:
        return html, None

    # Match the full host block (nested chrome </div> must not truncate).
    block = _match_div_block(html, host_open_m.start())
    if not block:
        return html, None
    open_tag0, _old_body, close0, block_end = block

    style_m = re.search(r'style="([^"]*)"', open_tag0, flags=re.I)
    host_style = style_m.group(1) if style_m else ""
    host_w = float((host_box or {}).get("width") or _px_from_style(host_style, "width") or 580.0)
    host_h = float((host_box or {}).get("height") or _px_from_style(host_style, "height") or 440.0)

    columns = payload.get("columns") if isinstance(payload.get("columns"), list) else []
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    natural = _estimate_table_natural_height(
        columns,
        rows,
        host_w=host_w,
        pad_y=14.0,
        pad_x=18.0,
        fs_body=15.0,
        fs_head=12.0,
    )
    dens = _table_density_for_host(
        columns, rows, host_w=host_w, host_h=host_h
    )
    fitted_h = host_h

    table_html = _render_table_html(
        payload,
        accent=str(accent),
        accent_soft=str(soft),
        host_w=host_w,
        host_h=fitted_h,
    )
    if not table_html:
        return html, {"error": "empty table payload"}

    open_tag = _apply_table_host_chrome(open_tag0)
    if tid and "data-table-id=" not in open_tag.casefold():
        open_tag = open_tag[:-1] + f' data-table-id="{tid}">'
    out = html[: host_open_m.start()] + open_tag + table_html + close0 + html[block_end:]
    if tid:
        slide["table_id"] = tid
        slide["table"] = payload
    return out, {
        "status": "filled",
        "table_id": tid,
        "columns": len(payload.get("columns") or []),
        "rows": len(payload.get("rows") or []),
        "host_h": fitted_h,
        "table_scale": dens.get("scale"),
        "natural_h": dens.get("natural_h") or natural,
        "pin_height": False,
    }


TABLE_HOST_CHROME = (
    "overflow:hidden;border-radius:14px;background:#FFFFFF;"
    "border:1px solid #D0DCEA;box-shadow:0 10px 28px rgba(26,54,93,.10);"
    "padding:0;box-sizing:border-box;"
)


def _apply_table_host_chrome(open_tag: str) -> str:
    """Give a table exactly one edge owner and keep reinjection idempotent."""
    props = (
        r"overflow\s*:\s*[^;]+;?",
        r"border-radius\s*:\s*[^;]+;?",
        r"background(?:-color)?\s*:\s*[^;]+;?",
        r"border\s*:\s*[^;]+;?",
        r"box-shadow\s*:\s*[^;]+;?",
        r"padding\s*:\s*[^;]+;?",
        r"box-sizing\s*:\s*[^;]+;?",
    )

    def _rewrite(match: re.Match[str]) -> str:
        quote = match.group(1)
        body = match.group(2)
        for prop in props:
            body = re.sub(prop, "", body, flags=re.I)
        body = re.sub(r";{2,}", ";", body).strip().strip(";")
        merged = TABLE_HOST_CHROME + (f"{body};" if body else "")
        return f'style={quote}{merged}{quote}'

    if re.search(r'\bstyle=["\']', open_tag, flags=re.I):
        return re.sub(
            r'\bstyle=(["\'])(.*?)\1', _rewrite, open_tag,
            count=1, flags=re.I | re.S,
        )
    return open_tag[:-1] + f' style="{TABLE_HOST_CHROME}">' if open_tag.endswith(">") else open_tag


def _parse_chart_number(raw: Any) -> float | None:
    text = _cell_text(raw).strip().replace(",", "")
    if not text:
        return None
    m = re.match(r"^[+-]?(?:\d+\.?\d*|\.\d+)", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _chart_series_colors(color_palette: dict[str, str] | None) -> list[str]:
    pal = color_palette or {}
    primary = str(pal.get("primary") or pal.get("ink") or "#1A365D")
    accent = str(pal.get("accent") or pal.get("secondary") or "#3182CE")
    muted = str(pal.get("muted") or "#90CDF4")
    return [muted, primary, accent, "#2B6CB0", "#63B3ED"]


def _render_line_chart_html(
    categories: list[str],
    series: list[dict[str, Any]],
    colors: list[str],
    *,
    mixed_scale: bool,
) -> str:
    """Inline-SVG trend preview for line/area chart hosts.

    Each series is normalised against its own extent when the metrics differ by
    orders of magnitude -- a cost in the hundreds of thousands beside a ratio
    near 1 would otherwise flatten the small one onto the axis. The printed end
    labels carry the true magnitudes.
    """
    import html as html_lib

    width, height = 320.0, 180.0
    pad_l, pad_r, pad_t, pad_b = 34.0, 46.0, 12.0, 26.0
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    numeric: list[list[float]] = []
    for item in series:
        row: list[float] = []
        for value in item.get("values") or []:
            try:
                row.append(float(value))
            except (TypeError, ValueError):
                row.append(0.0)
        numeric.append(row)
    points = max((len(row) for row in numeric), default=0)
    if points < 2:
        return ""

    flat = [value for row in numeric for value in row]
    global_lo, global_hi = min(flat), max(flat)

    def _extent(row: list[float]) -> tuple[float, float]:
        if mixed_scale and row:
            return min(row), max(row)
        return global_lo, global_hi

    def _x(index: int) -> float:
        return pad_l + plot_w * (index / (points - 1))

    paths: list[str] = []
    legend: list[str] = []
    for si, row in enumerate(numeric):
        if len(row) < 2:
            continue
        lo, hi = _extent(row)
        span = (hi - lo) or 1.0
        color = colors[si % len(colors)]
        coords = [
            f"{_x(i):.1f},{pad_t + plot_h - plot_h * ((value - lo) / span):.1f}"
            for i, value in enumerate(row)
        ]
        paths.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(coords)}"/>'
        )
        for coord in coords:
            cx, cy = coord.split(",")
            paths.append(f'<circle cx="{cx}" cy="{cy}" r="2.6" fill="{color}"/>')
        end_x, end_y = coords[-1].split(",")
        paths.append(
            f'<text x="{float(end_x) + 6:.1f}" y="{float(end_y) + 4:.1f}" '
            f'font-size="10" fill="{color}">{html_lib.escape(f"{row[-1]:g}")}</text>'
        )
        name = html_lib.escape(str(series[si].get("name") or series[si].get("label") or "")[:20])
        if name:
            legend.append(
                f'<span style="display:inline-flex;align-items:center;gap:5px;">'
                f'<span style="width:12px;height:2.5px;background:{color};display:inline-block;"></span>'
                f'<span style="font-size:11px;color:#4A5568;">{name}</span></span>'
            )

    axis = (
        f'<path d="M{pad_l:.1f},{pad_t:.1f} V{pad_t + plot_h:.1f} H{pad_l + plot_w:.1f}" '
        f'fill="none" stroke="#CBD5E0" stroke-width="1"/>'
    )
    ticks: list[str] = []
    for i in range(points):
        label = html_lib.escape(str(categories[i])[:10]) if i < len(categories) else str(i + 1)
        ticks.append(
            f'<text x="{_x(i):.1f}" y="{height - pad_b + 14:.1f}" font-size="10" '
            f'fill="#4A5568" text-anchor="middle">{label}</text>'
        )

    legend_html = (
        f'<div style="display:flex;gap:14px;flex-wrap:wrap;justify-content:center;">'
        f'{"".join(legend)}</div>'
        if legend
        else ""
    )
    return (
        f'<div data-sunairum-chart-preview="1" data-pptx-kind="ignore" '
        f'style="display:flex;flex-direction:column;align-items:center;justify-content:center;'
        f'gap:6px;width:100%;height:100%;padding:8px;box-sizing:border-box;">'
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" preserveAspectRatio="xMidYMid meet" '
        f'style="width:100%;flex:1;min-height:0;" xmlns="http://www.w3.org/2000/svg">'
        f'{axis}{"".join(ticks)}{"".join(paths)}</svg>{legend_html}</div>'
    )


def _render_chart_html(
    payload: dict[str, Any],
    *,
    color_palette: dict[str, str] | None = None,
) -> str:
    """HTML column/bar preview for empty data-pptx=chart hosts (no SVG)."""
    import html as html_lib

    categories = [str(c) for c in (payload.get("categories") or [])]
    series = payload.get("series") if isinstance(payload.get("series"), list) else []
    series = [s for s in series if isinstance(s, dict)]
    if not series:
        return ""
    if not categories:
        first_vals = series[0].get("values") or []
        categories = [str(i + 1) for i in range(len(first_vals))]
    colors = _chart_series_colors(color_palette)
    max_v = 0.0
    all_vals: list[float] = []
    for s in series:
        for v in s.get("values") or []:
            try:
                fv = abs(float(v))
            except (TypeError, ValueError):
                continue
            all_vals.append(fv)
            max_v = max(max_v, fv)
    if max_v <= 0:
        max_v = 1.0
    # Cost (~2e5) vs CV (~1.2): shared axis hides the small metric (PPT) or
    # fakes it with an 8% floor (HTML). Use independent visual weight + labels.
    pos = [v for v in all_vals if v > 0]
    mixed_scale = len(pos) >= 2 and (max(pos) / min(pos) >= 20.0)

    def _bar_pct(val: float, series_max: float | None = None) -> float:
        if abs(val) <= 0:
            return 0.0
        if mixed_scale and series_max and series_max > 0:
            return max(35.0, min(100.0, abs(val) / series_max * 100.0))
        if mixed_scale:
            # Dual-axis analogue: each positive metric reads as a full bar;
            # the printed number carries the true magnitude.
            return 88.0
        denom = series_max if series_max and series_max > 0 else max_v
        return max(8.0, min(100.0, abs(val) / denom * 100.0))

    ctype = str(payload.get("type") or payload.get("chart_type") or "column").casefold()
    horizontal = "bar" in ctype and "column" not in ctype

    if "line" in ctype or "trend" in ctype or "area" in ctype:
        # A trend is not a bar. The PPTX side has always exported `line`, but the
        # preview drew columns for it, so an author asking for a trend saw the
        # wrong figure and drew one by hand out of rotated rules instead. The
        # polyline is plotted from the same values the export uses, so the slope
        # on screen is the slope in the deck.
        return _render_line_chart_html(
            categories,
            series,
            colors,
            mixed_scale=mixed_scale,
        )

    bars: list[str] = []
    if len(series) == 1:
        values = list(series[0].get("values") or [])
        for i, cat in enumerate(categories):
            try:
                val = float(values[i]) if i < len(values) else 0.0
            except (TypeError, ValueError):
                val = 0.0
            pct = _bar_pct(val)
            color = colors[i % len(colors)]
            label = html_lib.escape(str(cat)[:18])
            num = html_lib.escape(f"{val:g}")
            if horizontal:
                bars.append(
                    f'<div style="display:flex;align-items:center;gap:8px;margin:6px 0;">'
                    f'<div style="width:48px;flex:none;font-size:11px;color:#4A5568;">{label}</div>'
                    f'<div style="flex:1;height:22px;background:#EDF2F7;border-radius:4px;overflow:hidden;">'
                    f'<div style="width:{pct:.1f}%;height:100%;background:{color};"></div></div>'
                    f'<div style="width:40px;flex:none;font-size:11px;color:#1A202C;">{num}</div></div>'
                )
            else:
                bars.append(
                    f'<div style="display:flex;flex-direction:column;align-items:center;'
                    f'justify-content:flex-end;height:100%;flex:1;min-width:0;gap:4px;">'
                    f'<div style="font-size:11px;color:#4A5568;line-height:1;">{num}</div>'
                    f'<div style="width:100%;max-width:52px;height:{pct:.1f}%;'
                    f'background:{color};border-radius:6px 6px 0 0;"></div>'
                    f'<div style="font-size:11px;color:#1A202C;line-height:1.2;text-align:center;">'
                    f"{label}</div></div>"
                )
    else:
        # Grouped columns: one group per category. Per-series max when mixed-scale.
        series_maxima: list[float] = []
        for s in series:
            m = 0.0
            for v in s.get("values") or []:
                try:
                    m = max(m, abs(float(v)))
                except (TypeError, ValueError):
                    continue
            series_maxima.append(m if m > 0 else max_v)
        for i, cat in enumerate(categories):
            group_bars = []
            for si, s in enumerate(series):
                values = list(s.get("values") or [])
                try:
                    val = float(values[i]) if i < len(values) else 0.0
                except (TypeError, ValueError):
                    val = 0.0
                pct = _bar_pct(val, series_maxima[si] if mixed_scale else None)
                color = colors[si % len(colors)]
                num = html_lib.escape(f"{val:g}")
                group_bars.append(
                    f'<div style="display:flex;flex-direction:column;align-items:center;'
                    f'justify-content:flex-end;height:100%;flex:1;gap:2px;">'
                    f'<div style="font-size:10px;color:#4A5568;">{num}</div>'
                    f'<div style="width:100%;max-width:28px;height:{pct:.1f}%;'
                    f'background:{color};border-radius:4px 4px 0 0;"></div></div>'
                )
            label = html_lib.escape(str(cat)[:18])
            bars.append(
                f'<div style="display:flex;flex-direction:column;align-items:center;'
                f'justify-content:flex-end;height:100%;flex:1;min-width:0;gap:4px;">'
                f'<div style="display:flex;align-items:flex-end;gap:4px;width:100%;'
                f'height:100%;justify-content:center;">{"".join(group_bars)}</div>'
                f'<div style="font-size:11px;color:#1A202C;">{label}</div></div>'
            )

    direction = (
        "flex-direction:column;justify-content:center;"
        if horizontal
        else "align-items:flex-end;justify-content:space-around;"
    )
    return (
        f'<div data-sunairum-chart-preview="1" data-pptx-kind="ignore" '
        f'style="display:flex;{direction}'
        f'width:100%;height:100%;padding:10px 8px 6px;box-sizing:border-box;gap:8px;">'
        f"{''.join(bars)}</div>"
    )


def _chart_payload_attr(
    payload: dict[str, Any],
    *,
    color_palette: dict[str, str] | None = None,
) -> str:
    """Compact JSON for data-chart-payload (HTML attr; escaped quotes)."""
    import html as html_lib
    import json

    categories = [str(c) for c in (payload.get("categories") or [])]
    series_in = payload.get("series") if isinstance(payload.get("series"), list) else []
    series = []
    for s in series_in:
        if not isinstance(s, dict):
            continue
        vals = []
        for v in s.get("values") or []:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                vals.append(0.0)
        series.append({"name": str(s.get("name") or s.get("label") or "Series"), "values": vals})
    ctype = str(payload.get("type") or payload.get("chart_type") or "column")
    # The colours the HTML preview is about to paint. Without them the export
    # falls back to pptxgenjs defaults and, for a dual-axis combo, hands both
    # sub-charts the *first* default colour -- so "Cost" and "CV" came out as
    # two identical red bars with two identical red legend swatches. Carrying
    # the palette makes the exported chart match the preview by construction
    # rather than by coincidence.
    blob = json.dumps(
        {
            "type": ctype,
            "categories": categories,
            "series": series,
            "colors": [
                str(c).lstrip("#").upper()
                for c in _chart_series_colors(color_palette)[: max(2, len(categories))]
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return html_lib.escape(blob, quote=True)


def _chart_payloads_from_table(
    table_payload: dict[str, Any],
    chart_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Project a source table into one or more column-chart payloads."""
    headers_raw = table_payload.get("columns") or table_payload.get("headers") or []
    headers = [_cell_text(h) for h in headers_raw]
    rows = table_payload.get("rows") if isinstance(table_payload.get("rows"), list) else []
    if not headers or not rows:
        return {}

    def _is_delta_header(h: str) -> bool:
        hl = h.casefold()
        return "∆" in h or "delta" in hl or hl.startswith("Δ")

    prefer: list[int] = []
    numeric: list[int] = []
    for i, h in enumerate(headers):
        if i == 0:
            continue
        hl = h.casefold()
        if _is_delta_header(h):
            continue
        sample = None
        for row in rows[:3]:
            if isinstance(row, (list, tuple)) and i < len(row):
                sample = _parse_chart_number(row[i])
                if sample is not None:
                    break
        if sample is None:
            continue
        numeric.append(i)
        if "alns" in hl or "hero" in hl:
            prefer.append(i)
    cols = prefer[:2] if len(prefer) >= 2 else numeric[:2]
    if not cols:
        return {}

    def _short_label(h: str) -> str:
        hl = h.casefold()
        if "alns" in hl:
            return "ALNS"
        if "hero" in hl:
            return "HERO"
        return (h.split() or [h])[0][:16]

    cat_labels = [_short_label(headers[i]) for i in cols]
    ids = [str(c).strip() for c in chart_ids if str(c).strip()] or ["c1"]
    out: dict[str, dict[str, Any]] = {}

    if len(ids) >= 2 and len(rows) >= 2:
        for idx, cid in enumerate(ids):
            if idx >= len(rows):
                break
            row = rows[idx]
            if not isinstance(row, (list, tuple)):
                continue
            values = []
            for ci in cols:
                values.append(_parse_chart_number(row[ci]) if ci < len(row) else None)
            if any(v is None for v in values):
                continue
            out[cid] = {
                "type": "column",
                "categories": list(cat_labels),
                "series": [{"name": "Value", "values": [float(v) for v in values]}],
            }
        return out

    row_labels = []
    for i, row in enumerate(rows):
        if isinstance(row, (list, tuple)) and row:
            row_labels.append(_cell_text(row[0])[:18] or str(i + 1))
        else:
            row_labels.append(str(i + 1))
    series = []
    for j, ci in enumerate(cols):
        vals = []
        for row in rows:
            if isinstance(row, (list, tuple)) and ci < len(row):
                vals.append(_parse_chart_number(row[ci]) or 0.0)
            else:
                vals.append(0.0)
        series.append({"name": cat_labels[j], "values": vals})
    out[ids[0]] = {
        "type": "column",
        "categories": row_labels,
        "series": series,
    }
    return out


def _table_id_from_evidence(storage_dir: str, evidence_id: str) -> str | None:
    tid_hint = str(evidence_id or "").strip()
    if not tid_hint:
        return None
    # ev-page-05-table-004 → try src-table-004 via evidence_id match
    path = os.path.join(storage_dir, "sources", "source_tables.json")
    if not os.path.isfile(path):
        return None
    try:
        import json

        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError):
        return None
    tables = data.get("tables") if isinstance(data, dict) else data
    if not isinstance(tables, list):
        return None
    for table in tables:
        if not isinstance(table, dict):
            continue
        if str(table.get("evidence_id") or "").strip() == tid_hint:
            return str(table.get("table_id") or table.get("id") or "").strip() or None
    return None


def resolve_chart_payloads(
    *,
    storage_dir: str,
    slide: dict[str, Any],
    html: str,
    native_payloads: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve chart series for each data-chart-id host on the slide."""
    chart_ids = re.findall(r'data-chart-id=["\']([^"\']+)["\']', html or "", flags=re.I)
    chart_ids = [c.strip() for c in chart_ids if c.strip()]
    out: dict[str, dict[str, Any]] = {}
    payloads = native_payloads or {}

    for cid in chart_ids:
        cand = payloads.get(cid) or payloads.get(cid.replace("chart_", "c"))
        if isinstance(cand, dict) and (cand.get("series") or cand.get("categories")):
            out[cid] = {
                "type": cand.get("type") or "column",
                "categories": list(cand.get("categories") or []),
                "series": list(cand.get("series") or []),
            }

    charts_field = slide.get("charts")
    if isinstance(charts_field, dict):
        for cid, cand in charts_field.items():
            if isinstance(cand, dict) and (cand.get("series") or cand.get("categories")):
                out.setdefault(
                    str(cid),
                    {
                        "type": cand.get("type") or "column",
                        "categories": list(cand.get("categories") or []),
                        "series": list(cand.get("series") or []),
                    },
                )
    elif isinstance(charts_field, list):
        for i, cand in enumerate(charts_field):
            if not isinstance(cand, dict):
                continue
            cid = str(cand.get("id") or (chart_ids[i] if i < len(chart_ids) else f"c{i+1}"))
            if cand.get("series") or cand.get("categories"):
                out.setdefault(
                    cid,
                    {
                        "type": cand.get("type") or "column",
                        "categories": list(cand.get("categories") or []),
                        "series": list(cand.get("series") or []),
                    },
                )

    single = slide.get("chart")
    if isinstance(single, dict) and (single.get("series") or single.get("categories")):
        key = chart_ids[0] if chart_ids else "c1"
        out.setdefault(
            key,
            {
                "type": single.get("type") or "column",
                "categories": list(single.get("categories") or []),
                "series": list(single.get("series") or []),
            },
        )

    if chart_ids and all(cid in out for cid in chart_ids):
        return out

    # Evidence / bound table → comparison charts
    table_ids: list[str] = []
    tid = str(slide.get("table_id") or "").strip()
    if tid and tid.casefold() not in {"none", "null", "-"}:
        table_ids.append(tid)
    for eid in slide.get("evidence_ids") or []:
        resolved = _table_id_from_evidence(storage_dir, str(eid))
        if resolved:
            table_ids.append(resolved)
    # Also parse visualization like table/src-table-004
    viz = str(slide.get("visualization") or "")
    m = re.search(r"(src-table-\d+)", viz, flags=re.I)
    if m:
        table_ids.append(m.group(1))

    for tid in table_ids:
        tbl = _load_table_payload(storage_dir, tid)
        if not tbl:
            continue
        projected = _chart_payloads_from_table(tbl, chart_ids or ["c1"])
        for cid, payload in projected.items():
            out.setdefault(cid, payload)
        if chart_ids and all(cid in out for cid in chart_ids):
            break

    # Caption fallback: "from 0.360 with ALNS to 0.188 with HERO"
    if chart_ids and any(cid not in out for cid in chart_ids):
        pairs = re.findall(
            r"from\s+([0-9]+(?:\.[0-9]+)?)\s+with\s+([A-Za-z0-9+_-]+)\s+to\s+"
            r"([0-9]+(?:\.[0-9]+)?)\s+with\s+([A-Za-z0-9+_-]+)",
            html or "",
            flags=re.I,
        )
        for i, cid in enumerate(chart_ids):
            if cid in out or i >= len(pairs):
                continue
            a, la, b, lb = pairs[i]
            out[cid] = {
                "type": "column",
                "categories": [la.upper() if len(la) <= 6 else la, lb.upper() if len(lb) <= 6 else lb],
                "series": [{"name": "Value", "values": [float(a), float(b)]}],
            }
    return out


def inject_chart_into_html(
    html: str,
    *,
    storage_dir: str,
    slide: dict[str, Any],
    native_payloads: dict[str, dict[str, Any]] | None = None,
    color_palette: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Fill empty data-pptx=chart hosts with HTML column/bar previews."""
    if not html or not re.search(r'data-pptx=["\']chart["\']', html, flags=re.I):
        return html, None
    if re.search(
        r'data-pptx=["\']chart["\'][^>]*>\s*<div\b[^>]*data-sunairum-chart-preview',
        html,
        flags=re.I | re.S,
    ):
        return html, {"status": "already_filled"}

    resolved = resolve_chart_payloads(
        storage_dir=storage_dir,
        slide=slide,
        html=html,
        native_payloads=native_payloads,
    )
    if not resolved:
        return html, {"error": "no chart payloads"}

    host_re = re.compile(
        r'(<div\b[^>]*\bdata-pptx=["\']chart["\'][^>]*>)(.*?)(</div>)',
        flags=re.I | re.S,
    )
    filled = 0

    def _fill(match: re.Match[str]) -> str:
        nonlocal filled
        open_tag, body, close = match.group(1), match.group(2), match.group(3)
        if re.search(r"data-sunairum-chart-preview", body or "", flags=re.I):
            return match.group(0)
        cid_m = re.search(r'data-chart-id=["\']([^"\']+)["\']', open_tag, flags=re.I)
        cid = cid_m.group(1).strip() if cid_m else ""
        payload = resolved.get(cid) if cid else None
        if not payload:
            # fall back to positional
            keys = list(resolved.keys())
            payload = resolved.get(keys[filled]) if filled < len(keys) else None
        if not isinstance(payload, dict):
            return match.group(0)
        chart_html = _render_chart_html(payload, color_palette=color_palette)
        if not chart_html:
            return match.group(0)
        payload_attr = _chart_payload_attr(payload, color_palette=color_palette)
        if "data-chart-payload=" not in open_tag.casefold():
            open_tag = open_tag[:-1] + f' data-chart-payload="{payload_attr}">'
        if "overflow" not in open_tag.casefold():
            if 'style="' in open_tag:
                open_tag = re.sub(
                    r'style="',
                    'style="overflow:hidden;',
                    open_tag,
                    count=1,
                    flags=re.I,
                )
            else:
                open_tag = open_tag[:-1] + ' style="overflow:hidden;">'
        filled += 1
        return f"{open_tag}{chart_html}{close}"

    out = host_re.sub(_fill, html)
    if filled:
        slide["charts"] = resolved
        if len(resolved) == 1:
            slide["chart"] = next(iter(resolved.values()))
        return out, {"status": "filled", "charts": list(resolved.keys()), "count": filled}
    return html, {"error": "hosts not filled", "resolved": list(resolved.keys())}


def materialize_html_slide(
    *,
    storage_dir: str,
    slide: dict[str, Any],
    html: str,
    native_payloads: dict[str, dict[str, Any]] | None = None,
    color_palette: dict[str, str] | None = None,
    scene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, inject hosts, persist HTML, preview, and resolved scene artifacts."""
    from tasks.html_constitution import ensure_slide_root

    if not isinstance(scene, dict) or scene.get("version") != "scene_layout_v2":
        raise ValueError("Scene v2 is required to materialize a slide")
    dirs = ensure_html_dirs(storage_dir)
    number = int(slide.get("slide") or 0)
    stem = slide_stem(number)
    html = ensure_slide_root(html)
    html, _audience_copy = sanitize_html_audience_copy(html)
    html, _inline_boundaries = normalize_inline_text_boundaries(html)
    # Before any measurement: the deck must name only faces we can embed, or
    # Chromium, LibreOffice and the reader's PowerPoint each pick a different
    # one and the layout we verified is not the layout they see.
    html, _font_families = normalize_html_font_families(html)
    # A frozen inline height must not be able to crush its own copy.
    html, _frozen_heights = relax_frozen_text_heights(html)
    report = validate_slide_html(html)
    if not report.ok:
        html = wrap_slide_fragment(html)
        report = validate_slide_html(html)

    # Semantic hosts are mutation targets.  Validate their tree ownership
    # before injecting an absolute-positioned native asset: a figure inside a
    # title region otherwise becomes positioned relative to the title and can
    # cover the entire slide.  Do not mutate an invalid authored tree; return a
    # diagnosable non-release result instead.
    from tasks.scene_html_author import normalize_scene_authored_html, validate_scene_authored_html

    html, _scene_normalization = normalize_scene_authored_html(html, scene)

    scene_contract_before = validate_scene_authored_html(html, scene)
    host_injection_allowed = not scene_contract_before
    figure_meta: dict[str, Any] | None = None
    host_boxes: dict[str, dict[str, Any]] = {}
    if host_injection_allowed and re.search(r'data-pptx=["\'](?:figure|image|table|chart|formula)["\']', html, flags=re.I):
        from tasks.html_runtime_layout import inspect_html_layout

        host_inspection = inspect_html_layout(html)
        if host_inspection.get("available"):
            for element in host_inspection.get("elements") or []:
                kind = str(element.get("pptx") or "").casefold()
                box = element.get("box") if isinstance(element.get("box"), dict) else None
                if kind and box:
                    host_boxes.setdefault("figure" if kind == "image" else kind, box)
            scene_boxes = {
                str(region.get("role") or "").casefold(): region
                for region in scene.get("regions") or []
                if isinstance(region, dict)
            }
            for kind, box in host_boxes.items():
                owner = scene_boxes.get(kind) or {}
                try:
                    width = float(box.get("width") or 0)
                    height = float(box.get("height") or 0)
                    owner_width = float(owner.get("w") or 0)
                    owner_height = float(owner.get("h") or 0)
                except (TypeError, ValueError):
                    continue
                if (
                    width < max(48.0, owner_width * 0.25)
                    or height < max(36.0, owner_height * 0.25)
                ):
                    scene_contract_before.append(
                        f"semantic_host_too_small:{kind}:{width:.1f}x{height:.1f}"
                    )
            host_injection_allowed = not scene_contract_before

    # Always fill empty PDF figure hosts here (not only in the author loop),
    # so mid-run previews and rematerialize never leave dashed blanks.
    fid = str(slide.get("figure_id") or "").strip()
    has_empty_host = bool(
        re.search(r'data-pptx=["\'](?:figure|image)["\']', html or "", flags=re.I)
    ) and not re.search(
        r'data-pptx=["\'](?:figure|image)["\'][^>]*>\s*<img\b',
        html or "",
        flags=re.I | re.S,
    )
    if host_injection_allowed and ((fid and fid.casefold() not in {"none", "null", "-"}) or has_empty_host):
        if not fid or fid.casefold() in {"none", "null", "-", "figure", "figure_host", "image"}:
            m = re.search(
                r'data-figure-id=["\']([^"\']+)["\']',
                html or "",
                flags=re.I,
            )
            host_fid = (m.group(1).strip() if m else "")
            if host_fid and host_fid.casefold() not in {
                "figure",
                "figure_host",
                "image",
                "img",
            }:
                fid = host_fid
        if fid and fid.casefold() not in {"none", "null", "-", "figure", "figure_host", "image"}:
            html, figure_meta = inject_pdf_figure_into_html(
                html, storage_dir=storage_dir, figure_id=fid
            )
            if figure_meta and not figure_meta.get("error"):
                slide["figure_id"] = fid

    # Always panel-chrome figure hosts — including already-filled PDF <img>s.
    html, _fig_chrome = normalize_figure_hosts(html)

    payloads = dict(native_payloads or {})
    table_meta: dict[str, Any] | None = None
    if host_injection_allowed:
        html, table_meta = inject_table_into_html(
            html,
            storage_dir=storage_dir,
            slide=slide,
            native_payloads=payloads,
            color_palette=color_palette,
            host_box=host_boxes.get("table"),
        )
    # Keep table payloads available for host inject (HTML SoT — no Slide IR).
    tid = str(slide.get("table_id") or "").strip()
    if tid and isinstance(slide.get("table"), dict):
        payloads.setdefault(tid, dict(slide["table"]))
        payloads.setdefault("t1", dict(slide["table"]))

    if host_injection_allowed:
        html, _formula_meta = inject_formula_into_html(
            html,
            storage_dir=storage_dir,
            slide=slide,
            color_palette=color_palette,
        )

    # Pass latex into native payloads for empty formula hosts / PPTX text fallback
    latex = str(slide.get("formula_tex") or slide.get("formula") or "").strip()
    if latex:
        payloads.setdefault("f1", {"latex": latex, "text": latex})
        payloads.setdefault("formula", {"latex": latex, "text": latex})

    if host_injection_allowed:
        html, _chart_meta = inject_chart_into_html(
            html,
            storage_dir=storage_dir,
            slide=slide,
            native_payloads=payloads,
            color_palette=color_palette,
        )
    charts = slide.get("charts") if isinstance(slide.get("charts"), dict) else {}
    for cid, chart_payload in charts.items():
        if isinstance(chart_payload, dict):
            payloads.setdefault(str(cid), dict(chart_payload))
    if isinstance(slide.get("chart"), dict):
        payloads.setdefault("c1", dict(slide["chart"]))

    # Filled hosts should not keep authoring dashed outlines
    html = html.replace(
        "[data-pptx]{outline:1px dashed rgba(0,0,0,.15);}",
        "[data-pptx]:empty{outline:1px dashed rgba(0,0,0,.15);}",
    )

    lane_meta = {"changed": False, "skipped": "scene_owned"}
    term_meta = {"changed": False, "skipped": "scene_owned"}

    # One canonical footer: strip P02/03/in-card digits, inject n/N bottom-right.
    total = slide.get("total_slides")
    try:
        total_n = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_n = None
    chrome = None
    if isinstance(color_palette, dict):
        chrome = (
            color_palette.get("muted")
            or color_palette.get("secondary_text")
            or color_palette.get("body_text")
        )
    html = sanitize_html_presentation_chrome(
        html,
        slide_number=number,
        total_slides=total_n,
        chrome_color=str(chrome) if chrome else None,
    )
    report = validate_slide_html(html)
    scene_contract_after = validate_scene_authored_html(html, scene)

    layout_qa = {
        "ok": True,
        "issues": [],
        "hard": [],
        "skipped": "scene_runtime_authoritative",
    }

    from tasks.html_layout_qa import audit_runtime_html_layout
    from tasks.scene_layout_ledger import build_scene_layout_ledger

    runtime_layout_qa = audit_runtime_html_layout(html)
    layout_ledger = build_scene_layout_ledger(scene, runtime_layout_qa)
    local_repair = {"changed": False, "regions": []}
    # Bounded Chromium feedback loop: accept a pass only when a fresh audit
    # improves. This also migrates retired broad-selector repair blocks.
    inspection = runtime_layout_qa.get("inspection") if isinstance(runtime_layout_qa.get("inspection"), dict) else {}
    if inspection.get("available"):
        from tasks.scene_local_repair import repair_scene_html_until_stable

        html, runtime_layout_qa, local_repair = repair_scene_html_until_stable(
            html,
            scene,
            initial_report=runtime_layout_qa,
        )
        if local_repair.get("changed"):
            report = validate_slide_html(html)
            scene_contract_after = validate_scene_authored_html(html, scene)
            layout_ledger = build_scene_layout_ledger(scene, runtime_layout_qa)
    if runtime_layout_qa.get("issues"):
        print(f"[html] runtime layout QA P{number:02d}: {runtime_layout_qa['issues']}")
    layout_hard = list(runtime_layout_qa.get("hard") or [])

    html_path = os.path.join(dirs["html_output"], f"{stem}.html")
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(html if html.endswith("\n") else html + "\n")
    scene_path = os.path.join(dirs["scene"], f"{stem}.json")
    with open(scene_path, "w", encoding="utf-8") as handle:
        json.dump(scene, handle, indent=2, sort_keys=True)
        handle.write("\n")

    import time as _time

    png_path = os.path.join(dirs["preview"], f"{stem}.png")
    t_p = _time.perf_counter()
    preview_ok = _render_preview_png(html, png_path)
    if not preview_ok or _preview_looks_stub(png_path):
        preview_ok = _render_preview_png(html, png_path)
    preview_ms = int((_time.perf_counter() - t_p) * 1000)
    return {
        "ok": (
            report.ok
            and not scene_contract_before
            and not scene_contract_after
            and bool(preview_ok)
            and not _preview_looks_stub(png_path)
            and not layout_hard
        ),
        "html_path": html_path,
        "scene_path": scene_path,
        "preview_path": png_path,
        "preview_ok": bool(preview_ok) and not _preview_looks_stub(png_path),
        "constitution": report_to_dict(report),
        "preview_ms": preview_ms,
        "table_meta": table_meta,
        "figure_meta": figure_meta,
        "host_boxes": host_boxes,
        "scene_contract": {
            "before_injection": scene_contract_before,
            "after_injection": scene_contract_after,
            "host_injection_allowed": host_injection_allowed,
        },
        "host_lane": lane_meta,
        "layout_qa": layout_qa,
        "runtime_layout_qa": runtime_layout_qa,
        "layout_ledger": layout_ledger,
        "local_layout_repair": local_repair,
        "formula_terms_meta": term_meta,
    }


# Rounded canvas chrome for PDF/AI figure hosts (matches table panel language).
FIGURE_HOST_CHROME = (
    "overflow:hidden;border-radius:16px;background:#FFFFFF;"
    "border:1px solid #D0DCEA;"
    "box-shadow:0 10px 28px rgba(26,54,93,.10),0 1px 0 rgba(26,54,93,.06);"
    "padding:18px;box-sizing:border-box;"
)


def _apply_figure_host_chrome(open_tag: str) -> str:
    """Ensure figure/image host open-tag has rounded panel chrome."""
    chrome = FIGURE_HOST_CHROME
    if re.search(r'\bstyle=["\']', open_tag, flags=re.I):
        # Drop prior copies of chrome props so re-inject stays tidy.
        def _scrub(style_body: str) -> str:
            props = (
                r"overflow\s*:\s*[^;]+;?",
                r"border-radius\s*:\s*[^;]+;?",
                r"background(?:-color)?\s*:\s*[^;]+;?",
                r"border\s*:\s*[^;]+;?",
                r"box-shadow\s*:\s*[^;]+;?",
                r"padding\s*:\s*[^;]+;?",
                r"box-sizing\s*:\s*[^;]+;?",
            )
            out = style_body
            for prop in props:
                out = re.sub(prop, "", out, flags=re.I)
            return re.sub(r";{2,}", ";", out).strip().strip(";")

        def _rewrite(match: re.Match[str]) -> str:
            quote = match.group(1)
            body = _scrub(match.group(2))
            merged = chrome + (f"{body};" if body else "")
            return f'style={quote}{merged}{quote}'

        return re.sub(
            r'\bstyle=(["\'])(.*?)\1',
            _rewrite,
            open_tag,
            count=1,
            flags=re.I | re.S,
        )
    if open_tag.endswith(">"):
        return open_tag[:-1] + f' style="{chrome}">'
    return open_tag + f' style="{chrome}"'


def normalize_figure_hosts(html: str) -> tuple[str, dict[str, Any]]:
    """Apply rounded panel chrome to every figure/image host (filled or empty).

    Rematerialize used to skip already-filled hosts, so PDF figures stayed bare
    while left claim cards looked "panelled".
    """
    if not html or "data-pptx" not in html.casefold():
        return html, {"changed": False, "hosts": 0}

    host_re = re.compile(
        r"<div\b[^>]*\bdata-pptx=[\"'](?:figure|image)[\"'][^>]*>",
        flags=re.I,
    )
    edits: list[tuple[int, int, str]] = []
    for m in host_re.finditer(html):
        open_tag = m.group(0)
        chromed = _apply_figure_host_chrome(open_tag)
        if chromed != open_tag:
            edits.append((m.start(), m.end(), chromed))
    edits.sort(key=lambda e: e[0], reverse=True)
    out = html
    for start, end, new_open in edits:
        out = out[:start] + new_open + out[end:]

    # Soften filled <img> corners to match the panel inset.
    out2, n_img = re.subn(
        r'(<img\b[^>]*\bdata-sunairum-figure-id=["\'][^"\']+["\'][^>]*\bstyle=["\'])([^"\']*)(["\'])',
        lambda m: (
            m.group(1)
            + (
                m.group(2)
                if "border-radius" in m.group(2).casefold()
                else (m.group(2).rstrip(";") + ";border-radius:8px")
            )
            + m.group(3)
        ),
        out,
        flags=re.I,
    )
    # A semantic host has one visual owner: the injected native/raster object.
    # Authoring guides drawn with ::before/::after are useful while the host is
    # empty, but after injection they otherwise paint crosshairs over a real
    # PDF figure and are separately exported as anonymous decoration.  Keep an
    # explicit opt-in for rare authored overlays whose ownership is intentional.
    guard_rule = (
        "\n/* data-sunairum-semantic-host-ownership=1 */"
        "[data-pptx]:not(:empty):not([data-pptx-keep-pseudo])::before,"
        "[data-pptx]:not(:empty):not([data-pptx-keep-pseudo])::after{"
        "content:none!important;display:none!important;}"
    )
    # Migrate the short-lived multi-style implementation so Scene's one-style
    # constitution remains true for projects generated during rollout.
    out2 = re.sub(
        r'<style\b[^>]*data-sunairum-semantic-host-ownership=["\']1["\'][^>]*>[\s\S]*?</style\s*>',
        "",
        out2,
        flags=re.I,
    )
    if "data-sunairum-semantic-host-ownership=1" not in out2:
        style_close = re.search(r"</style\s*>", out2, flags=re.I)
        if style_close:
            out2 = out2[: style_close.start()] + guard_rule + "\n" + out2[style_close.start() :]
    return out2, {
        "changed": out2 != html,
        "hosts": len(edits),
        "img_radius": n_img,
    }


def _resolve_pdf_figure_path(storage_dir: str, asset_id: str) -> str | None:
    """Resolve pdf_images crop by id, filename, or caption alias (no free_design import)."""
    import json

    index_path = os.path.join(storage_dir, "sources", "pdf_images", "index.json")
    if not os.path.isfile(index_path):
        return None
    try:
        figures = json.loads(open(index_path, encoding="utf-8").read()).get("figures") or []
    except (OSError, ValueError):
        return None
    needle = (asset_id or "").strip().casefold()
    if not needle:
        return None
    # Exact id / file first
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        fid = str(figure.get("id") or figure.get("asset_id") or "").strip()
        file_name = str(figure.get("file") or "").strip()
        if not file_name:
            continue
        path = os.path.join(storage_dir, "sources", "pdf_images", file_name)
        if not os.path.isfile(path):
            continue
        if fid.casefold() == needle or file_name.casefold() == needle:
            return path
    # Caption / alias (LLM host ids like hero_architecture)
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        file_name = str(figure.get("file") or "").strip()
        caption = str(figure.get("caption_text") or "").casefold()
        if not file_name:
            continue
        path = os.path.join(storage_dir, "sources", "pdf_images", file_name)
        if not os.path.isfile(path):
            continue
        tokens = [t for t in re.split(r"[_\s\-]+", needle) if len(t) >= 3]
        if needle in caption or needle.replace("_", " ") in caption:
            return path
        if tokens and all(t in caption for t in tokens[:2]):
            return path
        if "hero" in needle and "hero" in caption:
            return path
        if "architecture" in needle and "architecture" in caption:
            return path
    return None


def _file_to_data_uri(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as handle:
        raw = handle.read()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


_SCENE_SECTION_RE = re.compile(
    r'<section\b[^>]*\bdata-layout-id=["\']scene-(?P<role>[a-z-]+)["\'][^>]*>',
    flags=re.I,
)


def _figure_host_region(html: str) -> tuple[int, int] | None:
    """Where an unhosted figure may go: (open-tag end, close-tag start).

    A figure region is the right answer when the scene has one. Failing that,
    any content region the author left empty will hold it without displacing
    anything. A region that already carries copy, a table or a formula is not a
    candidate at any price -- putting the figure there guarantees the overlap
    this function exists to avoid. None means the slide has no room, which is a
    binding problem to report rather than a placement to invent.
    """
    if not html:
        return None
    candidates: list[tuple[int, int, str]] = []
    for match in _SCENE_SECTION_RE.finditer(html):
        role = (match.group("role") or "").casefold()
        if role in {"title", "lede", "byline", "footer"}:
            continue
        close = html.find("</section>", match.end())
        if close < 0:
            continue
        body = html[match.end():close]
        if re.search(r"<(?:p|h[1-6]|ul|ol|li|table|math|img)\b", body, flags=re.I):
            continue
        if re.search(r"\bdata-pptx=", body, flags=re.I):
            continue
        if re.sub(r"<[^>]*>", "", body).strip():
            continue
        candidates.append((match.end(), close, role))
    if not candidates:
        return None
    candidates.sort(key=lambda item: 0 if item[2] in {"figure", "image"} else 1)
    start, close, _role = candidates[0]
    return start, close


def inject_pdf_figure_into_html(
    html: str,
    *,
    storage_dir: str,
    figure_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Copy PDF crop into images/ and fill data-pptx=figure host (data URI for preview)."""
    fid = str(figure_id or "").strip()
    if not fid or not html:
        return html, None
    src = _resolve_pdf_figure_path(storage_dir, fid)
    if not src:
        # Host may use a made-up id — try first index figure matching HERO/caption later
        src = _resolve_pdf_figure_path(storage_dir, fid)
    if not src:
        return html, None

    images_dir = os.path.join(storage_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    ext = os.path.splitext(src)[1] or ".png"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", fid)
    dest_name = f"pdf_{safe}{ext}"
    dest = os.path.join(images_dir, dest_name)
    try:
        shutil.copy2(src, dest)
    except OSError as exc:
        return html, {"error": str(exc), "figure_id": fid}

    data_uri = _file_to_data_uri(dest)
    img = (
        f'<img data-sunairum-figure-id="{safe}" alt="" '
        f'style="width:100%;height:100%;object-fit:contain;display:block;'
        f'border-radius:8px;" '
        f'src="{data_uri}"/>'
    )

    host_re = re.compile(
        r'(<div\b[^>]*\bdata-pptx=["\'](?:figure|image)["\'][^>]*>)(.*?)(</div>)',
        flags=re.I | re.S,
    )

    def _fill(match: re.Match[str]) -> str:
        open_tag, _body, close = match.group(1), match.group(2), match.group(3)
        # Normalize data-figure-id to the real asset id
        if re.search(r'\bdata-figure-id=', open_tag, flags=re.I):
            open_tag = re.sub(
                r'\bdata-figure-id=["\'][^"\']*["\']',
                f'data-figure-id="{fid}"',
                open_tag,
                count=1,
                flags=re.I,
            )
        else:
            open_tag = open_tag[:-1] + f' data-figure-id="{fid}" data-image-src="1">'
        if "data-image-src=" not in open_tag.casefold():
            open_tag = open_tag[:-1] + ' data-image-src="1">'
        open_tag = _apply_figure_host_chrome(open_tag)
        return f"{open_tag}{img}{close}"

    if host_re.search(html or ""):
        out = host_re.sub(_fill, html, count=1)
    else:
        placed_region = _figure_host_region(html)
        if placed_region is None:
            # Every region on this slide is already carrying content. The old
            # behaviour was to drop the host before the *first* </section> --
            # the title lane -- at a hard-coded left:640px;top:140px, on the
            # assumption that the right half of the slide is free. When the
            # right half is the table region, the figure lands on top of the
            # table: two pieces of bound content stacked on one another, and no
            # layout repair can separate them because neither is misplaced by a
            # few pixels -- the placement itself was a guess.
            return html, {
                "error": (
                    "no free region for the figure host: every scene region on "
                    "this slide already carries content"
                ),
                "figure_id": fid,
            }
        region_open, region_close = placed_region
        # Filling the region rather than positioning inside it: the region is
        # the layout contract, so the host inherits a box that is guaranteed not
        # to be somewhere else's.
        host = (
            f'<div data-pptx="figure" data-figure-id="{fid}" data-image-src="1" '
            f'style="width:100%;height:100%;box-sizing:border-box;'
            f'{FIGURE_HOST_CHROME}">{img}</div>'
        )
        out = html[:region_close] + host + html[region_close:]
        del region_open

    return out, {
        "figure_id": fid,
        "href": f"../images/{dest_name}",
        "abs_path": dest,
        "mode": "exact",
    }


def place_pdf_figures_for_html(
    *,
    slides: list[dict[str, Any]],
    storage_dir: str,
    slide_filter: set[int] | None = None,
) -> dict[str, Any]:
    """Fill HTML figure hosts + rematerialize IR/preview for bound PDF figures."""
    placed: dict[str, Any] = {"figures": [], "tables": [], "errors": []}
    html_dir = os.path.join(storage_dir, "html_output")
    if not os.path.isdir(html_dir):
        return placed
    for slide in slides:
        number = int(slide.get("slide") or 0)
        if slide_filter is not None and number not in slide_filter:
            continue
        fid = str(slide.get("figure_id") or "").strip()
        stem = slide_stem(number)
        html_path = os.path.join(html_dir, f"{stem}.html")
        if not os.path.isfile(html_path):
            continue
        try:
            html = open(html_path, encoding="utf-8").read()
        except OSError as exc:
            placed["errors"].append(str(exc))
            continue
        # Infer figure id from host attribute when slide binding missing
        if not fid:
            m = re.search(
                r'data-pptx=["\'](?:figure|image)["\'][^>]*data-figure-id=["\']([^"\']+)["\']',
                html,
                flags=re.I,
            )
            if not m:
                m = re.search(
                    r'data-figure-id=["\']([^"\']+)["\'][^>]*data-pptx=["\'](?:figure|image)["\']',
                    html,
                    flags=re.I,
                )
            if m:
                fid = m.group(1).strip()
        if not fid:
            continue
        # Resolve aliases like hero_architecture → real pdf-page id via path lookup
        resolved = _resolve_pdf_figure_path(storage_dir, fid)
        if not resolved:
            # Fall back to design-spec style ids already on slide after bind
            placed["errors"].append(f"slide {number}: figure {fid} not found in pdf_images")
            continue
        # Prefer canonical id from index when alias matched by caption
        try:
            import json

            index = json.loads(
                open(
                    os.path.join(storage_dir, "sources", "pdf_images", "index.json"),
                    encoding="utf-8",
                ).read()
            )
            for fig in index.get("figures") or []:
                if not isinstance(fig, dict):
                    continue
                if os.path.join(storage_dir, "sources", "pdf_images", str(fig.get("file") or "")) == resolved:
                    fid = str(fig.get("id") or fid)
                    break
        except (OSError, ValueError):
            pass

        new_html, meta = inject_pdf_figure_into_html(
            html, storage_dir=storage_dir, figure_id=fid
        )
        if not meta or meta.get("error"):
            placed["errors"].append(
                f"slide {number}: {meta.get('error') if meta else 'inject failed'}"
            )
            continue
        if new_html == html and "data:image" not in html:
            placed["errors"].append(f"slide {number}: host not filled for {fid}")
            continue
        slide["figure_id"] = fid
        result = materialize_html_slide(
            storage_dir=storage_dir,
            slide=slide,
            html=new_html,
        )
        placed["figures"].append(
            {
                "slide": number,
                "figure_id": fid,
                "href": meta.get("href"),
                "mode": "exact",
                "preview": result.get("preview_path"),
            }
        )
    return placed
