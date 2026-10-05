"""Gallery catalog: ppt-master example packs as design references only.

The home page lists packs under ``servers/fastapi/examples/`` (moved from
ppt-master). These are style inspiration for free_design — never pack_fill
shells. ``templates/decks`` Presenton packs are excluded from the UI.
"""

from __future__ import annotations

import glob
import json
import os
import re

from tasks.generate_task import APP_ROOT

# Packs whose id encodes their family; the rest are titled from their directory.
_FAMILY = re.compile(r"^(?P<family>[a-z]+)_(?P<variant>[a-z]+)$")
_COVER_NAMES = (
    "thumbnail.png",
    "cover.png",
    "thumbnail.jpg",
)
_COVER_IMAGE_HINT = re.compile(r"(^|[_-])(cover|hero|thumbnail)([_-]|\.|$)", re.I)
# Asset backgrounds named cover_bg / hero_bg look blank on gallery cards.
_COVER_BG_SKIP = re.compile(r"(^|[_-])(bg|background|texture|pattern)([_-]|\.|$)", re.I)
_DEFAULT_COLOR = "#1E3A8A"
_GALLERY_EXCLUDED = frozenset({"presentation_core", "README.md", "examples.json"})
_CANVAS_PREFIX = re.compile(r"^ppt\d+_", re.I)
_PUBLISH_SUFFIX = re.compile(r"(?:_ppt\d+)?(?:_test)?_\d{8}$", re.I)
_CANVAS_SUFFIX = re.compile(r"_ppt\d+$", re.I)
_MACHINE_NAME = re.compile(r"[_-]")
_HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def contains_han(text: str | None) -> bool:
    return bool(text and _HAN.search(text))


def _english_or_fallback(text: str | None, fallback: str) -> str:
    raw = str(text or "").strip()
    if not raw or contains_han(raw):
        return fallback
    return raw


def gallery_roots() -> list[str]:
    """Directories that may hold design-reference example packs for the UI.

    Only ``servers/fastapi/examples`` (and optional ``SUNAIRUM_EXAMPLES_DIR``).
    Never ``templates/decks`` — those Presenton packs must not appear in the gallery.
    """
    roots: list[str] = []
    configured = os.environ.get("SUNAIRUM_EXAMPLES_DIR")
    if configured:
        roots.append(configured)
    roots.append(os.path.join(APP_ROOT, "examples"))
    roots.append(os.path.join("/app", "examples"))
    seen: set[str] = set()
    unique: list[str] = []
    for root in roots:
        resolved = os.path.abspath(root)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _looks_machine_name(name: str) -> bool:
    text = name.strip()
    if not text or " " in text:
        return False
    if any(ord(ch) > 127 for ch in text):
        return False
    return bool(_MACHINE_NAME.search(text)) or text.islower()


def _humanize_name(raw: str) -> str:
    text = raw.strip()
    text = _CANVAS_PREFIX.sub("", text)
    text = _PUBLISH_SUFFIX.sub("", text)
    text = _CANVAS_SUFFIX.sub("", text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.title() if text else raw.strip()


def _title(pack_id: str, readme: str) -> str:
    heading = re.search(r"(?m)^#\s+(.+?)\s*$", readme)
    candidate = heading.group(1).strip() if heading else ""
    if candidate and not _looks_machine_name(candidate) and not contains_han(candidate):
        return candidate
    return _humanize_name(pack_id if pack_id else candidate)


def _summary(readme: str) -> str:
    body = re.sub(r"(?m)^#.*$", "", readme).strip()
    for paragraph in re.split(r"\n\s*\n", body):
        text = " ".join(paragraph.split())
        if contains_han(text):
            continue
        if len(text) > 30 and not text.startswith(("|", "-", "*", "`")):
            return text[:220]
    return ""


def english_style_card_svg(
    *,
    title: str,
    style: str,
    color: str,
    description: str = "",
) -> str:
    """Generated English-only cover used when pack slides contain Chinese."""
    safe_title = (
        title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    safe_style = (
        (style or "authored").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    safe_desc = (
        (description or "")[:120].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    fill = color if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", color or "") else "#1E3A8A"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{fill}"/>
      <stop offset="100%" stop-color="#0F172A"/>
    </linearGradient>
  </defs>
  <rect width="1280" height="720" fill="url(#g)"/>
  <rect x="64" y="64" width="1152" height="592" fill="none" stroke="rgba(255,255,255,0.28)" stroke-width="2"/>
  <text x="96" y="160" fill="#FFFFFF" font-family="Georgia, serif" font-size="22" letter-spacing="4">{safe_style.upper()}</text>
  <text x="96" y="280" fill="#FFFFFF" font-family="Georgia, serif" font-size="54" font-weight="700">{safe_title[:48]}</text>
  <text x="96" y="360" fill="rgba(255,255,255,0.82)" font-family="Arial, sans-serif" font-size="22">{safe_desc}</text>
  <text x="96" y="620" fill="rgba(255,255,255,0.55)" font-family="Arial, sans-serif" font-size="16">Style reference · English preview</text>
</svg>
'''


def _file_has_han(path: str | None) -> bool:
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            return contains_han(handle.read())
    except OSError:
        return False


def pack_has_han_svg(template_id: str, filename: str | None = None) -> bool:
    if filename:
        return _file_has_han(pack_preview_slide(template_id, filename))
    cover = pack_cover(template_id)
    if cover and cover.casefold().endswith(".svg") and _file_has_han(cover):
        return True
    directory = pack_preview_dir(template_id)
    if not directory:
        return False
    for path in sorted(glob.glob(os.path.join(directory, "*.svg")))[:8]:
        if _file_has_han(path):
            return True
    return False


def _primary_color(lock: str) -> str:
    match = re.search(r"(?m)^-\s+primary:\s*(#[0-9A-Fa-f]{3,8})\s*$", lock)
    return match.group(1) if match else _DEFAULT_COLOR


def _style(pack_id: str) -> str:
    match = _FAMILY.match(pack_id)
    return match.group("variant") if match else "authored"


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read()
    except OSError:
        return ""


def _examples_index() -> dict[str, dict]:
    """Gallery blurbs from ``examples/examples.json``, keyed by pack id."""
    for root in gallery_roots():
        candidate = os.path.join(root, "examples.json")
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, encoding="utf-8") as stream:
                loaded = json.load(stream)
        except (OSError, json.JSONDecodeError):
            continue
        projects = loaded.get("projects") if isinstance(loaded, dict) else None
        if not isinstance(projects, list):
            continue
        index: dict[str, dict] = {}
        for project in projects:
            if isinstance(project, dict) and isinstance(project.get("id"), str):
                index[project["id"]] = project
        if index:
            return index
    return {}


def _first_cover_svg(directory: str | None) -> str | None:
    if not directory or not os.path.isdir(directory):
        return None
    svgs = sorted(glob.glob(os.path.join(directory, "*.svg")))
    if not svgs:
        return None
    for path in svgs:
        name = os.path.basename(path).casefold()
        if "cover" in name or name.startswith("01"):
            return path
    return svgs[0]


def _pack_root(template_id: str) -> str | None:
    if not template_id or "/" in template_id or ".." in template_id:
        return None
    for root in gallery_roots():
        candidate = os.path.join(root, template_id)
        if os.path.isdir(candidate):
            return candidate
    return None


def pack_preview_asset_dir(template_id: str) -> str | None:
    """Directory of gallery preview assets (PNG preferred; legacy SVG source)."""
    if not template_id or "/" in template_id or ".." in template_id:
        return None
    for root in gallery_roots():
        preview = os.path.join(root, template_id, "preview")
        if os.path.isdir(preview) and glob.glob(os.path.join(preview, "*.png")):
            return preview
    for subdir in ("svg_final", "svg_output"):
        for root in gallery_roots():
            candidate = os.path.join(root, template_id, subdir)
            if os.path.isdir(candidate) and glob.glob(os.path.join(candidate, "*.svg")):
                return candidate
    return None


_STUB_HEADER = (11, 59, 111)
_STUB_BODY = (30, 41, 59)


def _is_stub_png(png_path: str) -> bool:
    """True when PNG matches the dark placeholder from ``_write_stub_png``."""
    try:
        from PIL import Image

        with Image.open(png_path) as img:
            rgb = img.convert("RGB")
            if rgb.size != (1280, 720):
                return False
            return rgb.getpixel((10, 10)) == _STUB_HEADER and rgb.getpixel((640, 360)) == _STUB_BODY
    except Exception:
        return False


def _is_near_blank_png(png_path: str, *, max_unique: int = 12) -> bool:
    """Reject Playwright screenshots that failed to paint SVG content."""
    try:
        from PIL import Image

        with Image.open(png_path) as img:
            rgb = img.convert("RGB").resize((64, 36))
            return len(set(rgb.getdata())) <= max_unique
    except Exception:
        return True


def _pack_svg_sources(pack: str) -> list[str]:
    for subdir in ("svg_final", "svg_output"):
        sources = sorted(glob.glob(os.path.join(pack, subdir, "*.svg")))
        if sources:
            return sources
    return []


def ensure_pack_png_previews(template_id: str, *, force: bool = False) -> str | None:
    """Materialize preview/*.png for a pack (from SVG bake inputs or existing PNGs).

    Hot path: if ``preview/*.png`` already exists, return immediately (no PIL).
    Use ``force=True`` or ``bake_all_pack_previews`` to replace stubs.
    """
    pack = _pack_root(template_id)
    if not pack:
        return None
    preview_dir = os.path.join(pack, "preview")
    os.makedirs(preview_dir, exist_ok=True)
    existing = sorted(glob.glob(os.path.join(preview_dir, "*.png")))
    if existing and not force:
        return preview_dir
    sources = _pack_svg_sources(pack)
    if not sources:
        return preview_dir if existing else None
    for svg_path in sources:
        stem = os.path.splitext(os.path.basename(svg_path))[0]
        out = os.path.join(preview_dir, f"{stem}.png")
        if os.path.isfile(out) and not force:
            continue
        if not _svg_file_to_png(svg_path, out):
            _write_stub_png(out, stem)
        elif _is_near_blank_png(out) or _is_stub_png(out):
            try:
                os.remove(out)
            except OSError:
                pass
            _write_stub_png(out, stem)
    return preview_dir


def _svg_inline_html(svg_path: str) -> str | None:
    try:
        with open(svg_path, "r", encoding="utf-8", errors="replace") as handle:
            svg = handle.read().strip()
    except OSError:
        return None
    if not svg:
        return None
    # Strip XML declaration / doctype so the fragment embeds cleanly.
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg, count=1, flags=re.I).strip()
    svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg, count=1, flags=re.I).strip()
    if "width=" not in svg[:200].casefold():
        svg = re.sub(
            r"<svg\b",
            '<svg width="1280" height="720"',
            svg,
            count=1,
            flags=re.I,
        )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;background:#111;overflow:hidden'>"
        f"<div style='width:1280px;height:720px'>{svg}</div>"
        "</body></html>"
    )


def _svg_file_to_png(svg_path: str, png_path: str, *, page=None) -> bool:
    html = _svg_inline_html(svg_path)
    if not html:
        return False
    try:
        if page is not None:
            page.set_content(html, wait_until="load")
            page.wait_for_timeout(80)
            page.screenshot(path=png_path, full_page=False)
            return os.path.isfile(png_path) and not _is_near_blank_png(png_path)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                browser_page = browser.new_page(viewport={"width": 1280, "height": 720})
                browser_page.set_content(html, wait_until="load")
                browser_page.wait_for_timeout(80)
                browser_page.screenshot(path=png_path, full_page=False)
            finally:
                browser.close()
        return os.path.isfile(png_path) and not _is_near_blank_png(png_path)
    except Exception:
        return False


def _gallery_pack_ids() -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for root in gallery_roots():
        if not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.listdir(root))
        except OSError:
            continue
        for entry in entries:
            if entry in seen or entry.startswith(".") or entry in _GALLERY_EXCLUDED:
                continue
            if not entry.startswith("ppt169_"):
                continue
            pack_dir = os.path.join(root, entry)
            if not os.path.isdir(pack_dir):
                continue
            seen.add(entry)
            ids.append(entry)
    return ids


def bake_all_pack_previews(*, force: bool = True) -> dict[str, int]:
    """Offline/CI helper: bake preview PNGs for every installed gallery pack."""
    stats: dict[str, int] = {}
    packs = _gallery_pack_ids()
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        for tid in packs:
            ensure_pack_png_previews(tid, force=force)
            stats[tid] = len(pack_preview_slides(tid))
        return stats

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            for tid in packs:
                pack = _pack_root(tid)
                if not pack:
                    continue
                preview_dir = os.path.join(pack, "preview")
                os.makedirs(preview_dir, exist_ok=True)
                sources = _pack_svg_sources(pack)
                count = 0
                for svg_path in sources:
                    stem = os.path.splitext(os.path.basename(svg_path))[0]
                    out = os.path.join(preview_dir, f"{stem}.png")
                    if (
                        os.path.isfile(out)
                        and not force
                        and not _is_stub_png(out)
                        and not _is_near_blank_png(out)
                    ):
                        count += 1
                        continue
                    ok = _svg_file_to_png(svg_path, out, page=page)
                    if not ok:
                        _write_stub_png(out, stem)
                    count += 1 if os.path.isfile(out) else 0
                stats[tid] = count
        finally:
            browser.close()
    return stats


def pathlib_path_uri(path: str) -> str:
    abspath = os.path.abspath(path)
    return "file://" + abspath


def _write_stub_png(png_path: str, label: str) -> None:
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (1280, 720), _STUB_BODY)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 1280, 96], fill=_STUB_HEADER)
        draw.text((48, 36), (label or "preview")[:60], fill=(248, 250, 252))
        img.save(png_path)
    except Exception:
        # Minimal empty file marker — API will 404 if missing
        pass


def pack_preview_dir(template_id: str) -> str | None:
    ensured = ensure_pack_png_previews(template_id)
    if ensured and glob.glob(os.path.join(ensured, "*.png")):
        return ensured
    return pack_preview_asset_dir(template_id)


def pack_preview_slides(template_id: str) -> list[str]:
    """Raster preview filenames only (never advertise .svg to clients)."""
    directory = pack_preview_dir(template_id)
    if not directory:
        return []
    # Keep this cheap — stub filtering belongs in bake, not every API list.
    return [
        os.path.basename(path)
        for path in sorted(glob.glob(os.path.join(directory, "*")))
        if path.casefold().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]


def pack_preview_slide(template_id: str, filename: str) -> str | None:
    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or ".." in filename
    ):
        return None
    low = filename.casefold()
    if not (low.endswith(".png") or low.endswith(".jpg") or low.endswith(".jpeg") or low.endswith(".webp")):
        # Map legacy .svg requests to .png
        if low.endswith(".svg"):
            filename = filename[:-4] + ".png"
        else:
            return None
    ensure_pack_png_previews(template_id)
    directory = pack_preview_dir(template_id)
    if not directory:
        return None
    candidate = os.path.abspath(os.path.join(directory, filename))
    root = os.path.abspath(directory)
    if os.path.commonpath([root, candidate]) != root or not os.path.isfile(candidate):
        return None
    return candidate


def _gallery_pack_path(template_id: str, *parts: str) -> str | None:
    if not template_id or "/" in template_id or ".." in template_id:
        return None
    for root in gallery_roots():
        candidate = os.path.join(root, template_id, *parts)
        if os.path.exists(candidate):
            return candidate
    return None


def pack_cover(template_id: str) -> str | None:
    if not template_id or "/" in template_id or ".." in template_id:
        return None
    pack = _pack_root(template_id)
    if not pack:
        return None
    fast = _pack_cover_fast(pack)
    if fast:
        return fast
    # Bake-input SVG only as last resort for style-card detection; API won't serve it.
    finalized = _first_cover_svg(_gallery_pack_path(template_id, "svg_final"))
    if finalized:
        return finalized
    return _first_cover_svg(pack_preview_asset_dir(template_id))


def cover_thumb_jpeg_bytes(path: str, *, max_width: int = 640, quality: int = 72) -> bytes | None:
    """Downscale a cover image for gallery cards (avoids shipping full 1280×720 PNGs)."""
    try:
        import io

        from PIL import Image

        with Image.open(path) as img:
            rgb = img.convert("RGB")
            if rgb.width > max_width:
                height = max(1, int(round(rgb.height * (max_width / rgb.width))))
                rgb = rgb.resize((max_width, height), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue()
    except Exception:
        return None


def installed_packs() -> list[dict]:
    """ppt-master example packs under gallery roots — design references only."""
    examples = _examples_index()
    seen: set[str] = set()
    packs: list[dict] = []
    for root in gallery_roots():
        if not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.listdir(root))
        except OSError as error:
            # Broken Docker bind (stale nested mount) surfaces as EPERM here.
            print(f"[template_catalog] cannot list {root}: {error}")
            continue
        for entry in entries:
            if entry in seen or entry.startswith(".") or entry in _GALLERY_EXCLUDED:
                continue
            if not entry.startswith("ppt169_"):
                # Only ppt-master example packs for now.
                continue
            pack_dir = os.path.join(root, entry)
            if not os.path.isdir(pack_dir):
                continue
            has_svg = any(
                os.path.isdir(os.path.join(pack_dir, subdir))
                and glob.glob(os.path.join(pack_dir, subdir, "*.svg"))
                for subdir in ("svg_final", "svg_output")
            )
            has_preview = bool(
                os.path.isdir(os.path.join(pack_dir, "preview"))
                and glob.glob(os.path.join(pack_dir, "preview", "*.png"))
            )
            if not has_svg and not has_preview:
                continue
            seen.add(entry)
            example = examples.get(entry) if isinstance(examples.get(entry), dict) else {}
            readme = _read(os.path.join(pack_dir, "README.md"))
            lock = _read(os.path.join(pack_dir, "spec_lock.md"))
            # Listing must stay cheap — never open PNGs/SVGs with PIL here.
            preview_pngs = glob.glob(os.path.join(pack_dir, "preview", "*.png"))
            slide_count = len(preview_pngs)
            if slide_count == 0 and has_svg:
                for subdir in ("svg_final", "svg_output"):
                    n = len(glob.glob(os.path.join(pack_dir, subdir, "*.svg")))
                    if n:
                        slide_count = n
                        break
            cover_path = _pack_cover_fast(pack_dir)
            human = _humanize_name(entry)
            title = _english_or_fallback(
                example.get("title") if isinstance(example.get("title"), str) else None,
                _title(entry, readme) if not contains_han(_title(entry, readme)) else human,
            )
            description = _english_or_fallback(
                (
                    example.get("desc")
                    if isinstance(example.get("desc"), str)
                    else example.get("description")
                    if isinstance(example.get("description"), str)
                    else None
                ),
                _summary(readme) or "Style inspiration for free-design slides.",
            )
            if contains_han(description):
                description = "Style inspiration for free-design slides."
            style = str(example.get("style") or _style(entry))
            if contains_han(style):
                style = _style(entry)
            color = example.get("color") or _primary_color(lock)
            # Style-card only when we have no raster cover (avoid reading SVG bodies).
            use_style_card = not bool(cover_path)
            packs.append({
                "id": entry,
                "folder": entry,
                "title": title,
                "description": description,
                "style": style,
                "color": color,
                "cover": "cover",
                "cover_version": (
                    f"{int(os.path.getmtime(cover_path))}-{os.path.basename(cover_path)}"
                    if cover_path
                    else "style-card"
                ),
                "layout_count": slide_count,
                "certified": False,
                "design_reference": True,
                "available": slide_count > 0,
                "unavailable_reason": "",
                "english_style_card": use_style_card,
            })
    return packs


def _pack_cover_fast(pack_dir: str) -> str | None:
    """Cheap cover path for gallery listing (no PIL, no SVG body reads).

    Prefer baked ``preview/`` slide art over ``images/cover_bg`` assets — those
    backgrounds are often near-white and read as blank thumbnails.
    """
    preview = os.path.join(pack_dir, "preview")
    if os.path.isdir(preview):
        pngs = sorted(glob.glob(os.path.join(preview, "*.png")))
        for path in pngs:
            name = os.path.basename(path).casefold()
            if "cover" in name or name.startswith("01"):
                return path
        if pngs:
            return pngs[0]

    images = os.path.join(pack_dir, "images")
    if os.path.isdir(images):
        for name in _COVER_NAMES:
            candidate = os.path.join(images, name)
            if os.path.isfile(candidate):
                return candidate
        hinted = sorted(
            path
            for path in glob.glob(os.path.join(images, "*"))
            if path.casefold().endswith((".png", ".jpg", ".jpeg", ".webp"))
            and _COVER_IMAGE_HINT.search(os.path.basename(path))
            and not _COVER_BG_SKIP.search(os.path.basename(path))
        )
        if hinted:
            return hinted[0]
    return None


def style_card_for_pack(
    template_id: str,
    *,
    title: str | None = None,
    style: str | None = None,
    color: str | None = None,
    description: str | None = None,
) -> str:
    example = _examples_index().get(template_id) if isinstance(_examples_index().get(template_id), dict) else {}
    readme = ""
    lock = ""
    for root in gallery_roots():
        pack_dir = os.path.join(root, template_id)
        if os.path.isdir(pack_dir):
            readme = _read(os.path.join(pack_dir, "README.md"))
            lock = _read(os.path.join(pack_dir, "spec_lock.md"))
            break
    resolved_title = _english_or_fallback(
        title or (example.get("title") if isinstance(example.get("title"), str) else None),
        _title(template_id, readme),
    )
    resolved_desc = _english_or_fallback(
        description
        or (example.get("desc") if isinstance(example.get("desc"), str) else None)
        or (example.get("description") if isinstance(example.get("description"), str) else None),
        _summary(readme) or "Style inspiration for Constrained HTML slide design.",
    )
    resolved_style = str(style or example.get("style") or _style(template_id))
    if contains_han(resolved_style):
        resolved_style = _style(template_id)
    resolved_color = str(color or example.get("color") or _primary_color(lock) or _DEFAULT_COLOR)
    return english_style_card_svg(
        title=resolved_title,
        style=resolved_style,
        color=resolved_color,
        description=resolved_desc,
    )


def style_card_png_bytes(template_id: str) -> bytes:
    """PNG style card for zero-SVG gallery clients."""
    import io

    from PIL import Image, ImageDraw

    example = _examples_index().get(template_id) if isinstance(_examples_index().get(template_id), dict) else {}
    title = str(example.get("title") or template_id)[:48]
    color = str(example.get("color") or _DEFAULT_COLOR)
    if not color.startswith("#"):
        color = _DEFAULT_COLOR
    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
    except Exception:
        r, g, b = 11, 59, 111
    img = Image.new("RGB", (1280, 720), (248, 250, 252))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 1280, 160], fill=(r, g, b))
    draw.text((64, 64), title, fill=(255, 255, 255))
    draw.text((64, 220), "Design reference", fill=(15, 23, 42))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def english_preview_slides(template_id: str) -> list[str]:
    """Preview filenames that do not contain Chinese; empty means use style card."""
    slides = pack_preview_slides(template_id)
    english = [name for name in slides if not _file_has_han(pack_preview_slide(template_id, name))]
    return english
