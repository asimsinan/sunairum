import time
import asyncio
import difflib
import functools
import math
import os
import subprocess
import json
import glob
import logging
import re
import shutil
import sys
import hashlib
import uuid
import html
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Any, Dict
from llm_client import call_llm_json
from celery import shared_task
from tasks.color_contrast import AA_BODY, AA_LARGE, contrast_ratio, ensure_contrast, mix
from tasks import provenance
from tasks.pack_assets import DESIGN, classify_asset
from tasks.deck_furniture import (
    furniture_prompt_block,
    resolve_deck_furniture,
)
from tasks.paraphrase_guard import filter_grounded_replacements

logger = logging.getLogger(__name__)

# Pipeline ownership (free_design only):
# - strategist_agent / free_design_pipeline: MD + flat SVG + owners
# - generator_agent: finalize_compile (PPTX)
# - theme_agent / asset_agent: palette + icons for free_design
# Gallery template_id is a design reference only — never pack_fill.
# Deep QA product removed; AI Fix rematerializes from design_spec.md.

PPTX_COMPILE_TIMEOUT_SECONDS = int(os.environ.get("PPTX_COMPILE_TIMEOUT_SECONDS", "300"))
# Shared with the API so the "is this run dead" threshold always clears the
# worker's longest legitimate silence.
from runtime_limits import FINAL_REPAIR_TIMEOUT_SECONDS  # noqa: E402
OUTLINE_MODEL_CALL_BUDGET = int(os.environ.get("OUTLINE_MODEL_CALL_BUDGET", "8"))
# Shared ceiling across content + storyboard LLM calls (extends outline budget).
AUTHORING_MODEL_CALL_BUDGET = int(os.environ.get("AUTHORING_MODEL_CALL_BUDGET", str(OUTLINE_MODEL_CALL_BUDGET)))
# When 1, Job A pauses at awaiting_user_compile for manual Fix/Generate.
REQUIRE_USER_GENERATE = os.environ.get("REQUIRE_USER_GENERATE", "0") == "1"

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK_PLACEHOLDER_IMAGE = "replaceable_template_image.png"
STRATEGY_FIELDS = (
    ("audience", "Audience"),
    ("communication_intent", "Intent"),
    ("audience_outcome", "Desired outcome"),
    ("core_message", "Core message"),
    ("delivery_context", "Delivery context"),
    ("artifact_afterlife", "Life after the talk"),
)


_SLOT_X_RE = re.compile(r'\bx="([-\d.]+)"')
_SLOT_Y_RE = re.compile(r'\by="([-\d.]+)"')
_SLOT_FRAME_RE = re.compile(r'\s*data-pptx-frame="[^"]*"')


def _render_slot_text(match: re.Match, slot, value: str, source: str = provenance.USER) -> str:
    """Rewrite one ``<text>`` node so its copy already fits the slot's box.

    Three things happen here. The copy is broken into lines that measurably fit, so
    the fitter has nothing to shrink or cut afterwards -- the shrinking and
    cutting is what the checker then reported as a defect, which is how each
    repair produced the next round's work.

    The node also declares the box as its ``data-pptx-frame``, which is what turns
    the exported shape into a text frame that reflows at the slot's width instead
    of one sized to the glyphs that happen to be in it today. Without the frame,
    reflow would wrap at the current text width and a recipient's first edit would
    break the line in an absurd place.

    Last, it records where the copy came from. This is the only moment that fact is
    known: afterwards the words are just words, and the guard that tried to recover
    the answer by comparing them against the pack's could not tell the user's own
    table from the template's copy of it.
    """
    attrs, _body = match.group(1), match.group(2)
    # A slot left blank carries no claim, so it must not carry a stamp either: the QA
    # repair that refilled an emptied byline from the model's memory of the paper would
    # otherwise have found the attribution already made for it.
    attrs = provenance.stamp(attrs, source) if value.strip() else provenance.unstamp(attrs)
    attrs = re.sub(r'\s+data-sunairum-original-text="[^"]*"', "", attrs)
    if value.strip():
        attrs += f' data-sunairum-original-text="{html.escape(value, quote=True)}"'
    escaped = html.escape(value, quote=False)
    box = getattr(slot, "box", None)
    font_size = float(getattr(slot, "font_size", 0.0) or 0.0)
    if not box or font_size <= 0:
        return f"<text{attrs}>{escaped}</text>"

    from tasks.text_layout import layout_block, tspan_markup

    family = getattr(slot, "font_family", "") or None
    layout = layout_block(
        value, box, font_size, family, bool(getattr(slot, "bold", False)),
    )
    found_x = _SLOT_X_RE.search(attrs or "")
    baseline_x = float(found_x.group(1)) if found_x else float(box[0])
    body = escaped if len(layout.lines) <= 1 else tspan_markup(layout, baseline_x)

    found_y = _SLOT_Y_RE.search(attrs or "")
    baseline_y = float(found_y.group(1)) if found_y else float(box[1])
    left, top, width, height = (float(value) for value in box)
    role = str(getattr(slot, "role", "") or "").casefold()
    selector = str(getattr(slot, "selector", "") or "").casefold()
    # The exclusion must name the node, not its layout: a bare substring match on
    # "title" also matched "title-content-object-carrier" -- the body slot of the
    # Title and Content layout -- and quietly disabled centring for every body that
    # lives in a layout with "title" in its name.
    named_furniture = re.search(
        r"(?:^|[-_#])(?:title|heading|headline|subtitle|eyebrow|footer|source|page)(?:[-_]?carrier)?$",
        selector,
    )
    if (
        role not in {"headline", "title", "subtitle", "caption", "footer", "page-number"}
        and not named_furniture
        and layout.height + layout.line_height * 2 < height
    ):
        # Copy pinned to the top of a slot drawn for three times as much of it is
        # what makes a certified panel read as an unfinished container. The panel is
        # layout furniture and cannot be resized per slide under strict adherence,
        # so the copy is centred in the room it was given and the leftover space
        # becomes symmetric padding instead of a hole underneath.
        baseline_y = top + (height - layout.height) / 2 + font_size * 0.8
        attrs = _SLOT_Y_RE.sub(f'y="{baseline_y:g}"', attrs, count=1)
    # The frame has to start at or above the first line's glyph box, because the
    # compiler derives the top inset from the difference and a negative inset is
    # not expressible.
    frame_top = min(top, baseline_y - font_size * 0.9)
    # Enough room for the copy plus a line of headroom, but never more of the
    # slide than the slot owns: a frame the height of the whole panel would be
    # awkward to click past when editing the deck.
    needed = (baseline_y - font_size * 0.9 - frame_top) + layout.height + layout.line_height
    frame_height = max(font_size, min(max(height, font_size), needed))
    cleaned = _SLOT_FRAME_RE.sub("", attrs or "")
    frame = f'{left:g} {frame_top:g} {max(width, 1.0):g} {frame_height:g}'
    return f'<text{cleaned} data-pptx-frame="{frame}">{body}</text>'


def normalize_module_bounds(svg_text: str) -> str:
    """Remove fitter-only bounds from elements outside the layout contract."""
    return re.sub(
        r'(<(?!/?g(?:\s|>))[^>]*?)\s+data-pptx-bounds="[^"]*"',
        r'\1',
        svg_text,
    )

import redis

redis_client = None
try:
    redis_client = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
except Exception as e:
    print(f"Could not connect to Redis: {e}")

async def send_ws_message(project_id: str, message: dict):
    # Most messages carry neither key, and printing them unconditionally emitted
    # hundreds of bare "[project_id]" lines per run.
    label = message.get("status") or message.get("status_key")
    if label:
        logger.info("[%s] %s", project_id, label)
    if redis_client:
        try:
            redis_client.publish(f"project_{project_id}", json.dumps(message))
        except Exception as e:
            logger.warning("Redis publish error: %s", e)

def emit_planning_status(
    loop,
    project_id: str,
    storage_dir: str,
    run_id: str | None,
    message_key: str,
    message: str,
    progress: int,
) -> None:
    """Bump outline sub-phase status for the UI without leaving ``planning``."""
    loop.run_until_complete(
        send_ws_message(project_id, {"status_key": message_key, "progress": progress})
    )
    write_status(
        storage_dir,
        "planning",
        progress,
        message=message,
        message_key=message_key,
        run_id=run_id,
    )


def write_status(storage_dir: str, status: str, progress: int = 0,
                  current: int | None = None, total: int | None = None,
                  message: str = "", title: str = "", run_id: str | None = None,
                  message_key: str | None = None):
    """Persist generation progress so /api/projects can show live status.

    `message` stays English because this layer has no notion of the reader's
    language. `message_key` names the same message so the UI can translate it;
    several phases share one status, so the status alone cannot identify it.
    """
    try:
        status_path = os.path.join(storage_dir, "status.json")
        existing = {}
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    # Cancelled is sticky against stray worker writes, but Resume
                    # must be able to leave cancelled for active generation states.
                    if existing.get("status") == "cancelled" and status != "cancelled":
                        if status not in {
                            "queued",
                            "planning",
                            "generating",
                            "compiling",
                            "rendering",
                            "awaiting_user_compile",
                        }:
                            return
            except Exception:
                pass
        payload = {"status": status, "progress": progress, "updated_at": int(time.time())}
        if current is not None:
            payload["current"] = current
        if total is not None:
            payload["total"] = total
        if message:
            payload["message"] = message
        if message_key:
            payload["message_key"] = message_key
        if title:
            payload["title"] = title
        if run_id or existing.get("run_id"):
            payload["run_id"] = run_id or existing["run_id"]
        if existing.get("task_id"):
            payload["task_id"] = existing["task_id"]
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as e:
        print(f"write_status error: {e}")


def _sha256_path(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _svg_output_hash(svg_dir: str) -> str | None:
    """Retired: svg_output fingerprint unused on zero-SVG path."""
    del svg_dir
    return None


def _write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp-{uuid.uuid4().hex}"
    try:
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)

def convert_em_units(svg_text: str) -> str:
    # Convert 'em' units (e.g. dy="1.4em") to compatible unitless px coordinates
    def repl(match):
        attr = match.group(1)
        val = float(match.group(2))
        px_val = int(val * 24)
        return f'{attr}="{px_val}"'
    return re.sub(r'(dy|dx)="([0-9.-]+)em"', repl, svg_text)

def _gradient_stop_color(svg_text: str, grad_id: str) -> str | None:
    m = re.search(
        r'<(?:linear|radial)Gradient\b[^>]*\bid="' + re.escape(grad_id) + r'"[^>]*>'
        r'[\s\S]*?<stop\b[^>]*stop-color="([^"]+)"',
        svg_text,
    )
    return m.group(1) if m else None

def _path_is_degenerate(d: str) -> bool:
    tokens = re.findall(r'[MLHVZmlhvz]|-?\d+(?:\.\d+)?', d)
    pts = []
    cur = None
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in "MLml":
            try:
                x, y = float(tokens[i + 1]), float(tokens[i + 2])
            except (IndexError, ValueError):
                break
            pts.append((x, y))
            cur = (x, y)
            i += 3
        elif t in "HVhv":
            try:
                v = float(tokens[i + 1])
            except (IndexError, ValueError):
                break
            if t in "Hh":
                cur = (v, cur[1] if cur else 0.0)
            else:
                cur = (cur[0] if cur else 0.0, v)
            pts.append(cur)
            i += 2
        elif t in "CSQTAcsqta":
            return False
        else:
            i += 1
    if len(pts) < 2:
        return False
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (max(xs) - min(xs) < 1e-9) or (max(ys) - min(ys) < 1e-9)

def sanitize_zero_width_gradient_strokes(svg_text: str) -> str:
    """Replace url(#gradient) strokes on zero-width elements with a solid color.

    Native PPTX compile cannot paint objectBoundingBox gradient strokes on
    zero-width elements (lines, straight paths, empty rects); LLM rewrites
    occasionally produce them.
    """
    def swap_stroke(tag: str, grad_id: str) -> str:
        color = _gradient_stop_color(svg_text, grad_id)
        if color:
            return tag.replace(f'stroke="url(#{grad_id})"', f'stroke="{color}"')
        return re.sub(r'\s+stroke="url\(#[^)]+\)"', '', tag, count=1)

    def replace_line(m):
        tag, grad_id = m.group(0), m.group(1)
        return swap_stroke(tag, grad_id)

    def replace_path(m):
        tag, grad_id = m.group(0), m.group(1)
        d_m = re.search(r'\bd="([^"]*)"', tag)
        if not d_m or not _path_is_degenerate(d_m.group(1)):
            return tag
        return swap_stroke(tag, grad_id)

    def replace_rect(m):
        tag, grad_id = m.group(0), m.group(1)
        w_m = re.search(r'\bwidth="(-?\d+(?:\.\d+)?)"', tag)
        h_m = re.search(r'\bheight="(-?\d+(?:\.\d+)?)"', tag)
        w = float(w_m.group(1)) if w_m else None
        h = float(h_m.group(1)) if h_m else None
        if w not in (None, 0) and h not in (None, 0):
            return tag
        return swap_stroke(tag, grad_id)

    svg_text = re.sub(r'<line\b[^>]*stroke="url\(#([^)]+)\)"[^>]*/?>', replace_line, svg_text)
    svg_text = re.sub(r'<path\b[^>]*stroke="url\(#([^)]+)\)"[^>]*/?>', replace_path, svg_text)
    svg_text = re.sub(r'<rect\b[^>]*stroke="url\(#([^)]+)\)"[^>]*/?>', replace_rect, svg_text)
    return svg_text

# Scratch layout default colors -> confirmed palette roles.
# Applied deterministically AFTER the LLM rewrite so the confirmed
# design always shows up, even if the model ignored the palette.
SCRATCH_THEME_MAP = [
    ("#FFFFFF", "background"),
    ("#F8FAFC", "secondary_bg"),
    ("#1E293B", "primary"),
    ("#0F172A", "body_text"),
    ("#64748B", "muted_text"),
    ("#CBD5E1", "secondary_accent"),
    ("#F97316", "accent"),
    ("#F59E0B", "accent"),
    ("#2563EB", "primary"),
    ("#3B82F6", "secondary_accent"),
]

# Roles a palette may omit, and what to derive them from. ``muted_text`` used to
# share the ``body_text`` slot, which collapsed the two tones onto one colour.
THEME_ROLE_FALLBACKS = {
    "secondary_bg": ("background",),
    "secondary_accent": ("accent", "primary"),
    "accent": ("primary",),
}

# How far a derived muted tone travels from the body colour toward the page.
# Enough to read as secondary, not so far that it stops clearing AA for large text.
MUTED_TEXT_BLEND = 0.38

_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\b")


def resolve_theme_palette(color_palette: dict) -> dict:
    """Fill derivable roles and guarantee text stays legible on its background.

    Returns a palette where every text role clears WCAG AA against the surface
    it is painted on, so a caller-supplied palette can never produce a slide
    whose body text is the same colour as the page.
    """
    if not color_palette:
        return {}
    resolved = {key: value for key, value in color_palette.items() if isinstance(value, str) and value.strip()}
    for role, sources in THEME_ROLE_FALLBACKS.items():
        if resolved.get(role):
            continue
        for source in sources:
            if resolved.get(source):
                resolved[role] = resolved[source]
                break

    background = resolved.get("background")
    if not resolved.get("muted_text") and resolved.get("body_text"):
        # Derive a genuinely muted tone rather than aliasing body_text, so the
        # secondary/primary text hierarchy the template encodes survives theming.
        resolved["muted_text"] = (
            mix(resolved["body_text"], background, MUTED_TEXT_BLEND)
            if background
            else resolved["body_text"]
        )
    if background:
        for role, minimum in (("body_text", AA_BODY), ("muted_text", AA_LARGE), ("primary", AA_LARGE)):
            if resolved.get(role):
                resolved[role] = ensure_contrast(resolved[role], background, minimum)
        secondary_bg = resolved.get("secondary_bg")
        if secondary_bg and contrast_ratio(secondary_bg, background) < 1.05:
            # An indistinguishable secondary surface makes cards invisible.
            resolved["secondary_bg"] = ensure_contrast(secondary_bg, background, 1.2)
    return resolved


def _text_width_px(
    text: str,
    fs: float,
    ls: float,
    bold: bool,
    family: str | None = None,
) -> float:
    """Rendered width (px) of ``text`` at size ``fs``.

    Goes through the one primitive the compiler and the QA checks also use, so a
    line this pass considers fitted is not re-flagged later. Pass ``family``
    whenever it is known: it selects real advances from the shipped font file
    instead of the font-blind ratio table.
    """
    from tasks.layout_geometry import text_width_px
    return text_width_px(text, fs, ls, bold, family)

_TEXT_FAMILY_RE = re.compile(r'font-family="([^"]+)"')
_STYLE_FAMILY_RE = re.compile(r'font-family:\s*([^;"]+)')
# Bold detection for fit_text_to_box metrics (attr or CSS style).
_EST_BOLD_RE = re.compile(
    r'(?:font-weight\s*=\s*["\'](?:bold|[6-9]00)["\']|font-weight\s*:\s*(?:bold|[6-9]00)\b)',
    re.I,
)


def _text_family(tag: str) -> str | None:
    """The font family authored on a ``<text>`` tag, if it states one."""
    found = _TEXT_FAMILY_RE.search(tag) or _STYLE_FAMILY_RE.search(tag)
    return found.group(1).strip() if found else None


def _wrap_measured(
    text: str,
    avail: float,
    fs: float,
    family: str | None,
    bold: bool,
    letter_spacing: float,
) -> list[str]:
    from tasks.text_layout import wrap

    return wrap(text, avail, fs, family, bold, letter_spacing) or [""]


def _line_height_for(fs: float, family: str | None, bold: bool) -> float:
    from tasks.text_layout import line_height_for

    return line_height_for(fs, family, bold)


def fit_text_to_box(
    svg_text: str,
    margin: float = 100.0,
    max_lines: int = 10,
) -> str:
    """Wrap every ``<text>`` element inside the slide, changing nothing else.

    SVG ``<text>`` does not reflow, so text longer than its slot used to be made
    to fit by force: the font was shrunk toward a floor and the last line was cut
    with an ellipsis. Both were then reported by the checker as defects --
    ``font-too-small`` and ``text-truncated`` -- so this pass authored the work the
    repair loop was called to fix, and the loop could not converge. Copy that
    overruns is a content problem with a content answer: fewer words, or a
    different type scale for the whole deck. Neither is decided here.

    What remains:
      1. resolve absolute coordinates (translate() on <text> and ancestor <g>),
      2. wrap long lines into <tspan> rows against the real geometry,
      3. declare overflow rather than hiding it,
      4. shift colliding siblings apart, which moves text without rewriting it.

    Most slots never reach here: the filler already breaks copy to the slot's box.
    """
    vb_nums = re.findall(r'[\d.]+', re.search(r'viewBox="([^"]+)"', svg_text).group(1)) if re.search(r'viewBox="([^"]+)"', svg_text) else []
    slide_w = float(vb_nums[2]) if len(vb_nums) >= 3 else 1280.0
    slide_h = float(vb_nums[3]) if len(vb_nums) >= 4 else 720.0
    # Rendered line-box factors (matches PowerPoint/LibreOffice metrics).
    ASC = 0.80   # glyph box above baseline (em)
    DESC = 0.37  # glyph box below baseline (em)
    GAP = 4.0    # minimum visual air between sibling line boxes (px)
    CARD_PAD = 48.0  # inner padding of template cards/panels (px)
    CELL_PAD = 20.0  # inner padding of table cells (px)

    def font_size_of(tag: str) -> float | None:
        m = re.search(r'font-size="([\d.]+)', tag)
        if m:
            return float(m.group(1))
        m = re.search(r'style="[^"]*font-size:\s*([\d.]+)px', tag)
        return float(m.group(1)) if m else None

    def bold_of(tag: str) -> bool:
        # Module-level regex; inline fallback so a stale Celery worker import
        # never NameError mid fit_text_to_box again.
        try:
            return bool(_EST_BOLD_RE.search(tag))
        except NameError:  # pragma: no cover
            return bool(
                re.search(
                    r'(?:font-weight\s*=\s*["\'](?:bold|[6-9]00)["\']|font-weight\s*:\s*(?:bold|[6-9]00)\b)',
                    tag or "",
                    flags=re.I,
                )
            )

    def line_width(text: str, fs: float, ls: float, bold: bool) -> float:
        return _text_width_px(text, fs, ls, bold)

    def wrap_lines(text: str, fs: float, ls: float, bold: bool, avail: float) -> list[str]:
        words = text.split()
        if not words:
            return []
        lines, cur = [], ""
        for wd in words:
            trial = f"{cur} {wd}".strip()
            if line_width(trial, fs, ls, bold) <= avail:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines

    def translate_offsets(s: str) -> dict[int, tuple[float, float]]:
        """Map <text>/<rect> start offsets -> accumulated translate() offsets."""
        offsets: dict[int, tuple[float, float]] = {}
        stack = [(0.0, 0.0)]
        tag_re = re.compile(r'<(/?)(g|text|rect)\b([^>]*?)(/?)>')
        for m in tag_re.finditer(s):
            closing, name, attrs, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
            if closing:
                if name == "g" and len(stack) > 1:
                    stack.pop()
                continue
            t = re.search(r'transform="translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"', attrs)
            if name == "g":
                if not selfclose:
                    stack.append((stack[-1][0] + (float(t.group(1)) if t else 0.0),
                                  stack[-1][1] + (float(t.group(2)) if t else 0.0)))
            else:
                tx, ty = stack[-1]
                if t:
                    tx += float(t.group(1))
                    ty += float(t.group(2))
                offsets[m.start()] = (tx, ty)
        return offsets

    def content_lines(body: str) -> list[str]:
        lines = re.findall(r'<tspan[^>]*>(.*?)</tspan>', body, re.S)
        direct = re.sub(r'<tspan.*?</tspan>', '', body, flags=re.S).strip()
        return [l for l in ([direct] if direct else []) + lines if l.strip()]

    def semantic_text(tag: str, body: str) -> str:
        authored = re.search(r'\bdata-sunairum-original-text="([^"]*)"', tag)
        if authored:
            return html.unescape(authored.group(1))
        return " ".join(
            re.sub(r"<[^>]+>", "", line).strip()
            for line in content_lines(body)
            if re.sub(r"<[^>]+>", "", line).strip()
        )

    def parse_text_tag(tag: str) -> tuple[float, float, float, float, str, str]:
        """(x, y, fs, ls, anchor, text) from a <text> tag + body."""
        fs = font_size_of(tag) or 0.0
        x = float(re.search(r'\bx="([-\d.]+)', tag).group(1)) if re.search(r'\bx="([-\d.]+)', tag) else 0.0
        y = float(re.search(r'\by="([-\d.]+)', tag).group(1)) if re.search(r'\by="([-\d.]+)', tag) else 0.0
        ls = float(re.search(r'letter-spacing="([-\d.]+)', tag).group(1)) if re.search(r'letter-spacing="([-\d.]+)', tag) else 0.0
        anchor_m = re.search(r'text-anchor="(\w+)"', tag)
        anchor = anchor_m.group(1) if anchor_m else 'start'
        return x, y, fs, ls, anchor, tag

    def text_extent(x: float, w: float, anchor: str) -> tuple[float, float]:
        if anchor == "middle":
            return x - w / 2.0, x + w / 2.0
        if anchor == "end":
            return x - w, x
        return x, x + w

    def collect_anchors(s: str, offs: dict[int, tuple[float, float]]) -> list[tuple[float, float, float, float | None]]:
        """Absolute (y, x0, x1, fs) for every text/rect; rect fs = None."""
        anchors: list[tuple[float, float, float, float | None]] = []
        for m in re.finditer(r'<text\b([^>]*)>(.*?)</text>', s, re.S):
            tag, body = m.group(1), m.group(2)
            if "data-sunairum-source-table-text=\"1\"" in tag:
                continue
            x, y, fs, ls, anchor, _ = parse_text_tag(tag)
            if fs <= 0:
                continue
            joined = semantic_text(tag, body)
            if not joined:
                continue
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            ax, ay = x + tx, y + ty
            w = line_width(joined, fs, ls, bold_of(tag))
            x0, x1 = text_extent(ax, w, anchor)
            anchors.append((ay, x0, x1, fs))
        for m in re.finditer(r'<rect\b[^>]*?/>', s):
            tag = m.group(0)
            try:
                rx = float(re.search(r'\bx="([-\d.]+)', tag).group(1))
                ry = float(re.search(r'\by="([-\d.]+)', tag).group(1))
                rw = float(re.search(r'\bwidth="([\d.]+)', tag).group(1))
                rh = float(re.search(r'\bheight="([\d.]+)', tag).group(1))
            except Exception:
                continue
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            anchors.append((ty + ry, tx + rx, tx + rx + rw, None))
        return anchors

    def collect_cards(s: str, offs: dict[int, tuple[float, float]]) -> list[tuple[float, float, float, float]]:
        """Card/panel rects (absolute geometry) that can contain text: big
        enough to be a container, not a full-bleed background."""
        cards = []
        for m in re.finditer(r'<rect\b[^>]*?/>', s):
            tag = m.group(0)
            try:
                rx = float(re.search(r'\bx="([-\d.]+)', tag).group(1))
                ry = float(re.search(r'\by="([-\d.]+)', tag).group(1))
                rw = float(re.search(r'\bwidth="([\d.]+)', tag).group(1))
                rh = float(re.search(r'\bheight="([\d.]+)', tag).group(1))
            except Exception:
                continue
            if rw < 100 or rh < 40 or rw >= 0.9 * slide_w:
                continue
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            cards.append((tx + rx, ty + ry, rw, rh))
        for m in re.finditer(r'<g\b([^>]*data-pptx-bounds="([^"]+)"[^>]*)>.*?</g>', s, re.S):
            try:
                values = [float(value) for value in re.findall(r'-?\d+(?:\.\d+)?', m.group(2))]
                rx, ry, rw, rh = values[:4]
            except (ValueError, TypeError):
                continue
            if rw >= 100 and rh >= 40 and rw < 0.98 * slide_w:
                cards.append((rx, ry, rw, rh))
        return cards

    def collect_table_columns(s: str, offs: dict[int, tuple[float, float]]) -> list[tuple[float, float]]:
        """Column x-bounds of a table body, or [].

        Tables are drawn as one large body rect plus text rows aligned on
        middle-anchored column centers. Columns are derived from those centers
        (clustered across rows); boundaries sit halfway between adjacent
        centers, and the first column is split off against the leftmost
        start-anchored text (the row-label column)."""
        bodies = []
        for m in re.finditer(r'<rect\b[^>]*?/>', s):
            tag = m.group(0)
            try:
                rx = float(re.search(r'\bx="([-\d.]+)', tag).group(1))
                ry = float(re.search(r'\by="([-\d.]+)', tag).group(1))
                rw = float(re.search(r'\bwidth="([\d.]+)', tag).group(1))
                rh = float(re.search(r'\bheight="([\d.]+)', tag).group(1))
            except Exception:
                continue
            if rw < 0.5 * slide_w or rh < 0.25 * slide_h or rw >= 0.98 * slide_w:
                continue
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            bodies.append((tx + rx, ty + ry, rw, rh))
        if not bodies:
            return []
        mids: list[tuple[float, float]] = []
        starts: list[float] = []
        for m in re.finditer(r'<text\b([^>]*)>(.*?)</text>', s, re.S):
            tag, body_txt = m.group(1), m.group(2)
            if "data-sunairum-source-table-text=\"1\"" in tag:
                continue
            x, y, fs, ls, anchor, _ = parse_text_tag(tag)
            if fs <= 0 or not re.sub(r'<[^>]+>', '', body_txt).strip():
                continue
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            ax, ay = x + tx, y + ty
            for bx, by, bw, bh in bodies:
                if by <= ay <= by + bh and bx <= ax <= bx + bw:
                    if anchor == 'middle':
                        mids.append((ax, ay))
                    elif anchor == 'start':
                        starts.append(ax)
                    break
        if len(mids) < 4:
            return []
        centers: list[list] = []
        for ax, ay in sorted(mids):
            if centers and abs(ax - centers[-1][0]) < 30:
                centers[-1][0] = (centers[-1][0] + ax) / 2
                centers[-1][2].add(round(ay / 8))
            else:
                centers.append([ax, 1, {round(ay / 8)}])
        centers = [c for c in centers if len(c[2]) >= 2]
        if len(centers) < 2:
            return []
        bx, by, bw, bh = min(bodies, key=lambda b: b[2] * b[3])
        marker = min(starts) if starts else bx
        splits = [(marker + centers[0][0]) / 2.0]
        for i in range(len(centers) - 1):
            splits.append((centers[i][0] + centers[i + 1][0]) / 2.0)
        splits.append((centers[-1][0] + bx + bw) / 2.0)
        cols = [(bx, splits[0])]
        for i in range(1, len(splits)):
            cols.append((splits[i - 1], splits[i]))
        return cols

    def collect_table_rows(s: str, offs: dict[int, tuple[float, float]]) -> list[tuple[float, float]]:
        """Infer table row bands from repeated text baselines inside a table body."""
        bodies = []
        explicit_rows = []
        for m in re.finditer(r'<rect\b[^>]*?/>', s):
            tag = m.group(0)
            try:
                rx = float(re.search(r'\bx="([-\d.]+)', tag).group(1))
                ry = float(re.search(r'\by="([-\d.]+)', tag).group(1))
                rw = float(re.search(r'\bwidth="([\d.]+)', tag).group(1))
                rh = float(re.search(r'\bheight="([\d.]+)', tag).group(1))
            except Exception:
                continue
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            if rw >= 0.5 * slide_w and 32 <= rh <= 0.25 * slide_h and rw < 0.98 * slide_w:
                explicit_rows.append((tx + rx, ty + ry, rw, rh))
            elif rw >= 0.5 * slide_w and rh >= 0.2 * slide_h and rw < 0.98 * slide_w:
                bodies.append((tx + rx, ty + ry, rw, rh))
        if len(explicit_rows) >= 2:
            return [(row[1], row[1] + row[3]) for row in sorted(explicit_rows, key=lambda row: row[1])]
        if not bodies:
            return []

        bx, by, bw, bh = max(bodies, key=lambda body: body[2] * body[3])
        baselines: list[tuple[float, float]] = []
        for m in re.finditer(r'<text\b([^>]*)>(.*?)</text>', s, re.S):
            tag, body = m.group(1), m.group(2)
            if "data-sunairum-source-table-text=\"1\"" in tag:
                continue
            x, y, fs, _, _, _ = parse_text_tag(tag)
            if fs <= 0 or not re.sub(r'<[^>]+>', '', body).strip():
                continue
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            ax, ay = x + tx, y + ty
            if bx <= ax <= bx + bw and by <= ay <= by + bh:
                baselines.append((ay, fs))
        if len(baselines) < 2:
            return []

        clusters: list[list[float]] = []
        for ay, fs in sorted(baselines):
            if clusters and abs(ay - clusters[-1][0]) <= max(fs, clusters[-1][1]) * 0.45:
                clusters[-1][0] = (clusters[-1][0] + ay) / 2
                clusters[-1][1] = max(clusters[-1][1], fs)
            else:
                clusters.append([ay, fs])
        if len(clusters) < 2:
            return []

        boundaries = [by]
        boundaries.extend((clusters[i][0] + clusters[i + 1][0]) / 2 for i in range(len(clusters) - 1))
        boundaries.append(by + bh)
        return list(zip(boundaries, boundaries[1:]))

    def containing_card(ax: float, ay: float, cards: list) -> tuple | None:
        """Smallest card rect containing the point, if any."""
        best = None
        for rx, ry, rw, rh in cards:
            if rx <= ax <= rx + rw and ry <= ay <= ry + rh:
                if best is None or rw * rh < best[2] * best[3]:
                    best = (rx, ry, rw, rh)
        return best

    def vertical_pass(s: str) -> str:
        offs = translate_offsets(s)
        anchors = collect_anchors(s, offs)
        cards = collect_cards(s, offs)
        table_cols = collect_table_columns(s, offs)
        table_rows = collect_table_rows(s, offs)
        planned_zones = []
        for zone_match in re.finditer(r'<g\b([^>]*data-pptx-bounds="([^"]+)"[^>]*)>.*?</g>', s, re.S):
            try:
                values = [float(value) for value in re.findall(r'-?\d+(?:\.\d+)?', zone_match.group(2))]
                if len(values) >= 4:
                    planned_zones.append((zone_match.start(), zone_match.end(), tuple(values[:4])))
            except (TypeError, ValueError):
                continue

        def fit_one(m: re.Match) -> str:
            tag, body = m.group(1), m.group(2)
            if "data-sunairum-source-table-text=\"1\"" in tag:
                return m.group(0)
            if "data-sunairum-flow-label=\"1\"" in tag:
                return m.group(0)
            lines = content_lines(body)
            if not lines:
                return m.group(0)
            x, y, fs, ls, anchor, _ = parse_text_tag(tag)
            if fs <= 0:
                return m.group(0)
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            ax, ay = x + tx, y + ty
            if anchor == 'end':
                avail = ax - margin
            elif anchor == 'middle':
                avail = 2 * (min(ax, slide_w - ax) - margin)
            else:
                avail = slide_w - ax - margin
            # Local card/panel bounds are a tighter constraint than the canvas
            # edge: words that fit the slide can still poke out of their card.
            card = containing_card(ax, ay, cards)
            for zone_start, zone_end, zone in planned_zones:
                if zone_start <= m.start() <= zone_end:
                    card = zone
                    break
            if card:
                rx, ry, rw, rh = card
                if anchor == 'end':
                    avail = min(avail, ax - (rx + CARD_PAD))
                elif anchor == 'middle':
                    avail = min(avail, 2 * min(ax - rx - CARD_PAD, rx + rw - CARD_PAD - ax))
                else:
                    avail = min(avail, rx + rw - CARD_PAD - ax)
                avail *= 0.9
            # Table cells: text must stay inside its column, not just the slide.
            # The estimator now matches the compile-time checker, so a 95%
            # budget plus the cell padding keeps wrapped words clear of the
            # cell edge without over-shrinking.
            for cl, cr in table_cols:
                if cl - 2 <= ax <= cr + 2:
                    if anchor == 'end':
                        avail = min(avail, (ax - cl - CELL_PAD) * 0.95)
                    elif anchor == 'middle':
                        avail = min(avail, 2 * min(ax - cl - CELL_PAD, cr - CELL_PAD - ax) * 0.95)
                    else:
                        avail = min(avail, (cr - CELL_PAD - ax) * 0.95)
                    break
            table_row = next((row for row in table_rows if row[0] - 2 <= ay <= row[1] + 2), None)
            if avail <= 0:
                return m.group(0)
            bold = bold_of(tag)
            joined = semantic_text(tag, body)
            if not joined:
                return m.group(0)

            frame_match = re.search(r'\bdata-pptx-frame="([^"]+)"', tag)
            if frame_match:
                # A certified contract owns this box. Do not infer cards, move the
                # baseline around siblings, or reconstruct copy from tspans.
                from tasks.text_layout import layout_block, tspan_markup

                frame_values = [
                    float(value)
                    for value in re.findall(r"-?\d+(?:\.\d+)?", frame_match.group(1))
                ]
                if len(frame_values) == 4:
                    family = _text_family(tag)
                    layout = layout_block(
                        joined,
                        tuple(frame_values),
                        fs,
                        family,
                        bold,
                        ls,
                    )
                    contract_tag = re.sub(
                        r'\s+data-sunairum-overflow-lines="\d+"', "", tag
                    )
                    if len(layout.lines) > 1:
                        baseline = frame_values[1] + fs * 0.9
                        contract_tag = re.sub(
                            r'\by="[-\d.]+"',
                            f'y="{baseline:g}"',
                            contract_tag,
                            count=1,
                        )
                    if layout.overflow_lines:
                        contract_tag += (
                            f' data-sunairum-overflow-lines="{layout.overflow_lines}"'
                        )
                    contract_body = (
                        html.escape(joined, quote=False)
                        if len(layout.lines) <= 1
                        else tspan_markup(layout, x)
                    )
                    return f"<text{contract_tag}>{contract_body}</text>"

            # Wrap at the size the design authored. The font is never changed:
            # shrinking hid overflow behind unreadable type and the checker then
            # reported the small type as its own defect.
            family = _text_family(tag)
            wrapped = _wrap_measured(joined, avail, fs, family, bold, ls)
            line_h = _line_height_for(fs, family, bold)

            # How many lines this position can actually show, from the slide edge,
            # the enclosing card, the table row, and the next block below.
            budget = slide_h - ay - margin
            if card:
                budget = min(budget, card[1] + card[3] - CARD_PAD - ay)
            if table_row:
                budget = min(budget, table_row[1] - table_row[0] - 2 * CELL_PAD)
            x0, x1 = text_extent(ax, line_width(joined, fs, ls, bold), anchor)
            for a_y, a0, a1, a_fs in anchors:
                if a_y > ay and a0 < x1 and a1 > x0:
                    budget = min(budget, a_y - ay)
            max_rows = max(1, min(max_lines, int(budget // line_h) if line_h > 0 else 1))
            overflow_rows = max(0, len(wrapped) - max_rows)

            # 4) if the line overlaps an x-overlapping sibling above, slide it down.
            #    Moving text is not rewriting it, so this remedy stays.
            final_top = ay - ASC * fs
            shift = 0.0
            for a_y, a0, a1, a_fs in anchors:
                if a_fs is not None and a_y < ay and a0 < x1 and a1 > x0:
                    need = a_y + DESC * a_fs + GAP
                    if final_top < need:
                        shift = max(shift, need - final_top)
            if shift > 0.01:
                for a_y, a0, a1, _ in anchors:
                    if a_y > ay and a0 < x1 and a1 > x0:
                        shift = min(shift, a_y - ay - DESC * fs - GAP)
                shift = min(shift, slide_h - 10 - ay - DESC * fs)
            drawn_text = " ".join(
                re.sub(r"<[^>]+>", "", line).strip()
                for line in lines
                if re.sub(r"<[^>]+>", "", line).strip()
            )
            if (
                shift <= 0.01
                and not table_row
                and not overflow_rows
                and len(wrapped) <= 1
                and line_width(wrapped[0], fs, ls, bold) <= avail
                and "data-sunairum-overflow-lines" not in tag
                and joined == drawn_text
            ):
                # Nothing to change, so the node is returned exactly as it arrived.
                return m.group(0)
            # Overflow is declared, never absorbed. Shrinking or cutting here made
            # this pass the author of the next round's defects.
            tag = re.sub(r'\s+data-sunairum-overflow-lines="\d+"', "", tag)
            if overflow_rows:
                tag += f' data-sunairum-overflow-lines="{overflow_rows}"'
            if shift > 0.01:
                ny = ay + shift - ty
                tag = re.sub(r'\by="[-\d.]+"', f'y="{ny:g}"', tag, count=1)
                ay = ay + shift
            if table_row:
                row_top, row_bottom = table_row
                inner_height = max(1.0, row_bottom - row_top - 2 * CELL_PAD)
                block_height = min(inner_height, len(wrapped) * line_h)
                centered_ay = row_top + CELL_PAD + (inner_height - block_height) / 2 + ASC * fs
                tag = re.sub(r'\by="[-\d.]+"', f'y="{centered_ay - ty:g}"', tag, count=1)
            tag = re.sub(r'\s+data-pptx-bounds="[^"]*"', '', tag)
            out_lines = [f'<text{tag}>']
            for i, ln in enumerate(wrapped):
                if i == 0:
                    out_lines.append(ln)
                else:
                    out_lines.append(f'<tspan x="{x:g}" dy="{line_h:g}">{ln}</tspan>')
            out_lines.append('</text>')
            return "".join(out_lines)

        return re.sub(r'<text\b([^>]*)>(.*?)</text>', fit_one, s, flags=re.S)

    def horizontal_pass(s: str) -> str:
        offs = translate_offsets(s)
        table_cols = collect_table_columns(s, offs)
        cards = collect_cards(s, offs)
        texts = []
        for m in re.finditer(r'<text\b([^>]*)>(.*?)</text>', s, re.S):
            tag, body = m.group(1), m.group(2)
            if "data-sunairum-source-table-text=\"1\"" in tag:
                continue
            lines = content_lines(body)
            if not lines:
                continue
            x, y, fs, ls, anchor, _ = parse_text_tag(tag)
            if fs <= 0:
                continue
            joined = semantic_text(tag, body)
            if not joined:
                continue
            tx, ty = offs.get(m.start(), (0.0, 0.0))
            ax, ay = x + tx, y + ty
            w = line_width(joined, fs, ls, bold_of(tag))
            texts.append({"m": m, "ax": ax, "ay": ay, "w": w, "fs": fs, "anchor": anchor,
                          "orig_ax": ax, "orig_x": x, "tag": tag, "body": body,
                          "container": containing_card(ax, ay, cards)})
        if not texts:
            return s
        texts.sort(key=lambda t: (t["ay"], t["ax"]))
        # group into rows: same baseline within tolerance
        rows: list[list[dict]] = []
        for t in texts:
            placed = False
            for row in rows:
                if (
                    abs(row[0]["ay"] - t["ay"]) <= 0.35 * max(row[0]["fs"], t["fs"])
                    and row[0]["container"] == t["container"]
                ):
                    row.append(t)
                    placed = True
                    break
            if not placed:
                rows.append([t])
        edits: dict[int, tuple[int, str]] = {}
        for row in rows:
            if len(row) < 2:
                continue
            row.sort(key=lambda t: t["ax"])
            # only touch rows with an actual collision
            prev_right = text_extent(row[0]["ax"], row[0]["w"], row[0]["anchor"])[1]
            chain_start = None
            for i in range(1, len(row)):
                t0, _ = text_extent(row[i]["ax"], row[i]["w"], row[i]["anchor"])
                if prev_right + GAP > t0:
                    chain_start = i - 1
                    break
                prev_right = text_extent(row[i]["ax"], row[i]["w"], row[i]["anchor"])[1]
            if chain_start is None:
                continue
            chain = row[chain_start:]
            # redistribute the colliding chain only (pre-chain items stay put):
            # keep the chain's first left and last natural right
            first_left, _ = text_extent(chain[0]["ax"], chain[0]["w"], chain[0]["anchor"])
            last_right = text_extent(chain[-1]["ax"], chain[-1]["w"], chain[-1]["anchor"])[1]
            avail = last_right - first_left
            if avail <= 0:
                continue
            # Labels that still do not fit side by side are left at their authored
            # size and reported as an overlap. Scaling them down to squeeze them in
            # produced the unreadable 12px row the checker then flagged as
            # font-too-small, so the remedy authored the defect.
            # place items sequentially with even gaps
            total_w = sum(t["w"] for t in chain)
            gap = max((avail - total_w) / (len(chain) - 1), 2.0)
            cursor = first_left
            for t in chain:
                left = cursor
                t["ax"] = left + (t["w"] / 2.0 if t["anchor"] == "middle" else (t["w"] if t["anchor"] == "end" else 0.0))
                cursor = left + t["w"] + gap
            for t in chain:
                delta = t["ax"] - t["orig_ax"]
                if abs(delta) < 0.01:
                    continue
                new_tag = t["tag"]
                new_x = t["orig_x"] + delta
                if re.search(r'\bx="[^"]*"', new_tag):
                    new_tag = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', new_tag, count=1)
                else:
                    new_tag = new_tag.replace("<text", f'<text x="{new_x:g}"', 1)
                new_tag = re.sub(r'\s+data-pptx-bounds="[^"]*"', '', new_tag)
                edits[t["m"].start()] = (t["m"].end(), "<text" + new_tag + ">" + t["body"] + "</text>")
        if edits:
            for start, (end, repl) in sorted(edits.items(), reverse=True):
                s = s[:start] + repl + s[end:]
        return s

    for _ in range(2):
        svg_text = vertical_pass(svg_text)
        svg_text = horizontal_pass(svg_text)
    return svg_text

def repair_vision_text_clipping(svg_text: str, issues: list[dict]) -> str:
    """Lift only the exact text a clipping finding identifies.

    Vision prose that merely says "descriptions are clipped" is not a geometry
    target.  Treating it as one previously moved every text baseline on the slide,
    including healthy titles, and repeated repair rounds could move them off-canvas.
    """
    fragments = []
    for issue in issues:
        if issue.get("category") != "vision-text-clipped":
            continue
        detail = str(issue.get("detail", ""))
        quoted = re.findall(r"'([^']*(?:'[A-Za-z][^']*)*)'", detail)
        if quoted:
            fragments.extend(fragment.casefold() for fragment in quoted if len(fragment.strip()) > 3)
    if not fragments:
        return svg_text

    def repair_text(match: re.Match) -> str:
        tag, body = match.group(1), match.group(2)
        plain = re.sub(r"<[^>]+>", " ", body)
        plain = re.sub(r"\s+", " ", plain).strip().casefold()
        if not any(fragment in plain for fragment in fragments):
            return match.group(0)

        size_match = re.search(r'font-size="([\d.]+)"', tag)
        font_size = float(size_match.group(1)) if size_match else 14.0
        # Only the lift remains. This used to also drop the type by a tenth, which
        # traded one reported defect for another: the checker's readability floor
        # then flagged the smaller text, and the next repair round shrank it again.
        lift = max(2.0, font_size * 0.2)
        y_match = re.search(r'\by="([-\d.]+)"', tag)
        if y_match:
            # A baseline above one em cannot show a full line on the 0-based canvas.
            lifted_y = max(font_size, float(y_match.group(1)) - lift)
            tag = re.sub(r'\by="[-\d.]+"', f'y="{lifted_y:g}"', tag, count=1)
        return f"<text{tag}>{body}</text>"

    return re.sub(r"<text\b([^>]*)>(.*?)</text>", repair_text, svg_text, flags=re.S)


# Archetypes whose composition is intentionally sparse; drawn ornaments would
# compete with the single statement these slides exist to make.
_ORNAMENT_FREE_ARCHETYPES = {"title", "hero", "closing"}


def user_directives(result_data: dict) -> str:
    """Render the user's free-text directions as instructions, not as subject matter.

    Directions like "use an academic tone" used to be typed into the prompt box and
    so became part of ``topic``, which is also interpolated into image prompts and
    title fallbacks -- producing figures "about 'use an academic tone'". Keeping
    them in their own field lets them reach the prompts that write copy and no
    others. Presenter / affiliation / date / occasion stated here are talk facts
    and must appear on the title plate even under pdf_strict (no PDF evidence).
    """
    text = str(result_data.get("additional_instructions") or "").strip()
    if not text:
        return ""
    return (
        "Author directions (follow these; they describe how to write and who is "
        "presenting — not what the deck's subject is):\n"
        f"{text}\n"
        "If these directions name a presenter/speaker (any language, e.g. "
        "\"sunucu\", \"presented by\"), affiliation/institution, date, or "
        "occasion, put those facts on the title (and closing, when relevant) "
        "byline verbatim. They are user-supplied talk facts and do NOT require "
        "PDF evidence — even in pdf_strict. Do not invent any of these when "
        "the directions omit them."
    )


def strategy_brief(result_data: dict) -> str:
    """Render the Stage 1 contract the user reviewed as a prompt block.

    The wizard asks the user to confirm audience, intent, outcome, core message,
    delivery context and afterlife, then stored all six and showed them to no one:
    none of the six reached a prompt, so editing them changed nothing about the
    deck. Returns an empty string when nothing was captured.
    """
    lines = [
        f"- {label}: {value}"
        for key, label in STRATEGY_FIELDS
        if (value := str(result_data.get(key) or "").strip())
    ]
    if not lines:
        return ""
    return (
        "Communication brief (confirmed by the user; the deck must serve it):\n"
        + "\n".join(lines)
    )


# Declared in narrative order so validators and content-planner prompts share one set.
AUDIENCE_MOVE_ORDER = (
    "orient", "motivate", "define", "contrast", "evidence",
    "quantify", "illustrate", "sequence", "caution", "conclude", "call-to-action",
)
AUDIENCE_MOVES = set(AUDIENCE_MOVE_ORDER)
PAGE_RHYTHM_ORDER = ("anchor", "dense", "breathing")
PAGE_RHYTHMS = set(PAGE_RHYTHM_ORDER)

# Words the model reaches for instead of the listed ones, mapped to the listed
# move whose job they describe. Snapping these is not leniency: a plan tagged
# "explain" instead of "define" is the right beat under the wrong name, and
# re-asking spent a whole outline call to get the same plan back with one word
# changed. Only genuinely unreadable values should cost a retry.
AUDIENCE_MOVE_SYNONYMS = {
    "agenda": "orient",
    "background": "orient",
    "context": "orient",
    "frame": "orient",
    "intro": "orient",
    "introduction": "orient",
    "overview": "orient",
    "scope": "orient",
    "setup": "orient",
    "engage": "motivate",
    "hook": "motivate",
    "importance": "motivate",
    "persuade": "motivate",
    "problem": "motivate",
    "stakes": "motivate",
    "why": "motivate",
    "clarify": "define",
    "comprehend": "define",
    "definition": "define",
    "describe": "define",
    "explain": "define",
    "grasp": "define",
    "introduce": "define",
    "terminology": "define",
    "understand": "define",
    "compare": "contrast",
    "comparison": "contrast",
    "differ": "contrast",
    "differentiate": "contrast",
    "distinguish": "contrast",
    "tradeoff": "contrast",
    "tradeoffs": "contrast",
    "versus": "contrast",
    "vs": "contrast",
    "analyse": "evidence",
    "analyze": "evidence",
    "assess": "evidence",
    "cite": "evidence",
    "evaluate": "evidence",
    "examine": "evidence",
    "findings": "evidence",
    "inspect": "evidence",
    "interpret": "evidence",
    "justify": "evidence",
    "prove": "evidence",
    "results": "evidence",
    "review": "evidence",
    "substantiate": "evidence",
    "support": "evidence",
    "validate": "evidence",
    "benchmark": "quantify",
    "data": "quantify",
    "measure": "quantify",
    "measurement": "quantify",
    "metrics": "quantify",
    "numbers": "quantify",
    "statistics": "quantify",
    "demonstrate": "illustrate",
    "diagram": "illustrate",
    "example": "illustrate",
    "show": "illustrate",
    "visualize": "illustrate",
    "walkthrough": "illustrate",
    "follow": "sequence",
    "method": "sequence",
    "procedure": "sequence",
    "process": "sequence",
    "roadmap": "sequence",
    "steps": "sequence",
    "timeline": "sequence",
    "trace": "sequence",
    "walk": "sequence",
    "workflow": "sequence",
    "caveat": "caution",
    "caveats": "caution",
    "hedge": "caution",
    "limit": "caution",
    "limitation": "caution",
    "limitations": "caution",
    "qualify": "caution",
    "risk": "caution",
    "risks": "caution",
    "warn": "caution",
    "warning": "caution",
    "close": "conclude",
    "closing": "conclude",
    "conclusion": "conclude",
    "end": "conclude",
    "finish": "conclude",
    "recap": "conclude",
    "summarize": "conclude",
    "summary": "conclude",
    "takeaway": "conclude",
    "takeaways": "conclude",
    "wrap": "conclude",
    "wrapup": "conclude",
    "act": "call-to-action",
    "action": "call-to-action",
    "apply": "call-to-action",
    "ask": "call-to-action",
    "cta": "call-to-action",
    "do": "call-to-action",
    "invite": "call-to-action",
    "nextsteps": "call-to-action",
    "nextstep": "call-to-action",
    "recommend": "call-to-action",
    "recommendation": "call-to-action",
    "recommendations": "call-to-action",
}

PAGE_RHYTHM_SYNONYMS = {
    "focal": "anchor",
    "hero": "anchor",
    "statement": "anchor",
    "detail": "dense",
    "detailed": "dense",
    "heavy": "dense",
    "packed": "dense",
    "rich": "dense",
    "airy": "breathing",
    "breathe": "breathing",
    "light": "breathing",
    "minimal": "breathing",
    "open": "breathing",
    "spacious": "breathing",
    "sparse": "breathing",
}

_VOCABULARY_WORDS = re.compile(r"[a-z0-9]+")


def _marker_baseline_offset(text_tag: str, font_size: float) -> float:
    """Baseline offset in SVG units that vertically centres a numeral in its marker.

    This used to ask ``fc-match`` for the font file. None of the pack families are
    installed system-wide in the container, so fontconfig returned an unrelated
    substitute. Use a constant offset relative to font-size.
    """
    del text_tag
    return font_size * 0.35


def normalize_numbered_step_markers(svg_text: str) -> str:
    """Give vertical procedure markers a shared diameter and centered numeral."""
    circles = []
    for match in re.finditer(r"<circle\b([^>]*)/?>", svg_text):
        tag = match.group(1)
        try:
            cx = float(re.search(r'\bcx="([-\d.]+)"', tag).group(1))
            cy = float(re.search(r'\bcy="([-\d.]+)"', tag).group(1))
            radius = float(re.search(r'\br="([\d.]+)"', tag).group(1))
        except Exception:
            continue
        if 10 <= radius <= 40:
            circles.append({"match": match, "cx": cx, "cy": cy, "r": radius})

    markers = []
    for match in re.finditer(r"<text\b([^>]*)>\s*(\d{1,2})\s*</text>", svg_text, re.S):
        tag, number = match.group(1), match.group(2)
        if number == "00":
            continue
        if 'text-anchor="middle"' not in tag:
            continue
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', tag).group(1))
            y = float(re.search(r'\by="([-\d.]+)"', tag).group(1))
            fs_match = re.search(r'font-size="([\d.]+)"', tag)
            fs = float(fs_match.group(1)) if fs_match else 14.0
        except Exception:
            continue
        nearest = min(circles, key=lambda circle: abs(circle["cx"] - x) + abs(circle["cy"] - y), default=None)
        if nearest and abs(nearest["cx"] - x) <= nearest["r"] * 0.5 and abs(nearest["cy"] - y) <= nearest["r"]:
            markers.append({"circle": nearest, "match": match, "fs": fs, "number": number})

    if not markers:
        return svg_text
    radii = sorted(marker["circle"]["r"] for marker in markers)
    shared_radius = radii[len(radii) // 2]
    replacements = []
    for ordinal, marker in enumerate(markers, start=1):
        marker_id = f"step-{marker['number']}-{ordinal}"
        circle_match = marker["circle"]["match"]
        circle_tag = circle_match.group(0)
        normalized_circle = re.sub(r'\br="[\d.]+"', f'r="{shared_radius:g}"', circle_tag, count=1)
        if "data-sunairum-marker-id=" not in normalized_circle:
            if "/>" in normalized_circle:
                normalized_circle = normalized_circle.replace("/>" , f' data-sunairum-marker-id="{marker_id}"/>', 1)
            else:
                normalized_circle = normalized_circle.replace(">", f' data-sunairum-marker-id="{marker_id}">', 1)
        replacements.append((circle_match.start(), circle_match.end(), normalized_circle))
        text_match = marker["match"]
        text_tag = text_match.group(1)
        cx, cy = marker["circle"]["cx"], marker["circle"]["cy"]
        text_tag = re.sub(r'\bx="[-\d.]+"', f'x="{cx:g}"', text_tag, count=1)
        text_tag = re.sub(r'\by="[-\d.]+"', f'y="{cy + _marker_baseline_offset(text_tag, marker["fs"]):g}"', text_tag, count=1)
        if "data-sunairum-marker-id=" not in text_tag:
            text_tag += f' data-sunairum-marker-id="{marker_id}"'
        replacements.append((text_match.start(), text_match.end(), f'<text{text_tag}>{marker["number"]}</text>'))
    for start, end, replacement in sorted(replacements, reverse=True):
        svg_text = svg_text[:start] + replacement + svg_text[end:]
    return svg_text


# ── Template figure pipeline ────────────────────────────────────────────────
# Template SVGs embed the ORIGINAL template topic's figures (<image href="../images/...">).
# These are replaced per the user's image_source choice: AI-generated figures,
# figures extracted from the uploaded PDF, both, or none.

VALID_IMAGE_ASPECTS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]

def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else None

def _parse_svg_float(value: str | None, default: float = 0.0) -> float:
    if not value:
        return default
    m = re.search(r'-?\d+(?:\.\d+)?', value)
    return float(m.group(0)) if m else default

def _parse_dimension(value: str | None, viewbox_dim: float) -> float:
    """Parse width/height attrs: px (unitless), % of viewBox, or em (1em=24px)."""
    if not value:
        return 0.0
    m = re.search(r'(-?\d+(?:\.\d+)?)\s*(%|em)?', value)
    if not m:
        return 0.0
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "%":
        return num / 100.0 * viewbox_dim
    if unit == "em":
        return num * 24.0
    return num

def _slot_transform_rotation(tag: str) -> float:
    """Extract rotation angle from a transform attr (rotate(...) or matrix(...))."""
    t = _attr(tag, "transform")
    if not t:
        return 0.0
    m = re.search(r'rotate\(\s*(-?\d+(?:\.\d+)?)', t)
    if m:
        return float(m.group(1))
    m = re.search(r'matrix\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)', t)
    if m:
        a, b, c, d = (float(x) for x in m.groups())
        if abs(a) < 1e-6 and abs(b) > 0.999 and abs(c) > 0.999 and abs(d) < 1e-6:
            return 90.0 if b > 0 else -90.0
        if abs(a) < 1e-6 and abs(b) < -0.999 and abs(c) > 0.999 and abs(d) < 1e-6:
            return 90.0
        if abs(a) < 1e-6 and abs(b) > 0.999 and abs(c) < -0.999 and abs(d) < 1e-6:
            return -90.0
    return 0.0

def _viewbox_dims(svg_text: str) -> tuple[float, float]:
    m = re.search(r'viewBox="([^"]+)"', svg_text)
    if m:
        nums = re.findall(r'-?\d+(?:\.\d+)?', m.group(1))
        if len(nums) >= 4:
            return float(nums[2]), float(nums[3])
    return 1280.0, 720.0

def _group_element_end(svg_text: str, open_end: int) -> int:
    """Index after the ``</g>`` that closes the group whose open tag ended at open_end."""
    depth = 1
    pos = open_end
    while pos < len(svg_text) and depth:
        match = re.search(r"</?g\b[^>]*>", svg_text[pos:], flags=re.I)
        if not match:
            return len(svg_text)
        tag = match.group(0)
        pos = pos + match.end()
        if tag.startswith("</"):
            depth -= 1
        elif tag.rstrip().endswith("/>"):
            continue
        else:
            depth += 1
    return pos


def picture_placeholder_ranges(svg_text: str) -> list[tuple[int, int]]:
    """Inclusive-start / exclusive-end spans of ``data-pptx-placeholder="picture"`` groups."""
    ranges: list[tuple[int, int]] = []
    for match in re.finditer(
        r'<g\b[^>]*\bdata-pptx-placeholder="picture"[^>]*>',
        svg_text,
        flags=re.I,
    ):
        ranges.append((match.start(), _group_element_end(svg_text, match.end())))
    return ranges


def _is_replaceable_figure_href(href: str) -> bool:
    if not href or href.startswith("data:"):
        return bool(href)
    base = os.path.basename(href.split("?")[0]).casefold()
    return (
        base == PACK_PLACEHOLDER_IMAGE.casefold()
        or base.startswith("replaceable")
        or "placeholder." in base
        or base.startswith("placeholder")
    )


def _image_is_design_furniture(
    svg_text: str,
    tag: str,
    href: str,
    start: int,
    area_ratio: float,
    picture_ranges: list[tuple[int, int]] | None = None,
) -> bool:
    """True when the image is pack chrome, not a replaceable subject figure slot."""
    if href.startswith("data:") or _is_replaceable_figure_href(href):
        return False
    ranges = picture_ranges if picture_ranges is not None else picture_placeholder_ranges(svg_text)
    under_picture = any(lo <= start < hi for lo, hi in ranges)
    if under_picture:
        return False
    if area_ratio >= 0.7:
        return True
    image_id = (_attr(tag, "id") or "").casefold()
    basename = os.path.basename(href.split("?")[0])
    if image_id.startswith("presenton-image-carrier-"):
        return True
    if basename.casefold().startswith("freeform_"):
        return True
    try:
        if classify_asset(basename) == DESIGN:
            return True
    except Exception:
        pass
    return False


def find_image_slots(svg_text: str, viewbox_w: float, viewbox_h: float) -> list[dict]:
    """Find <image> elements (self-closing or paired); classify backgrounds vs figures.

    The slot ratio is the RENDERED ratio: a transform="rotate(90|270)" swaps
    width/height, which matters for PDF matching and AI aspect selection.

    Design furniture (Presenton decorative carriers, freeform chrome, full-bleed
    backdrops) is marked ``is_design`` / ``is_background`` so it is never treated
    as a subject figure slot. Replaceable picture placeholders stay figures.
    """
    slots = []
    picture_ranges = picture_placeholder_ranges(svg_text)
    for m in re.finditer(r'<image\b[^>]*?(?:/>|>.*?</image>)', svg_text, flags=re.S):
        tag = m.group(0)
        href = _attr(tag, "href")
        if not href:
            continue
        w = _parse_dimension(_attr(tag, "width"), viewbox_w)
        h = _parse_dimension(_attr(tag, "height"), viewbox_h)
        if w <= 0 or h <= 0:
            continue
        rot = abs(_slot_transform_rotation(tag)) % 360
        ratio = round(w / h, 3)
        if 85.0 <= rot <= 95.0 or 265.0 <= rot <= 275.0:
            ratio = round(h / w, 3)
        area_ratio = (w * h) / max(viewbox_w * viewbox_h, 1.0)
        is_design = _image_is_design_furniture(
            svg_text, tag, href, m.start(), area_ratio, picture_ranges
        )
        slots.append({
            "start": m.start(),
            "end": m.end(),
            "tag": tag,
            "href": href,
            "is_data_uri": href.startswith("data:"),
            "x": _parse_dimension(_attr(tag, "x"), viewbox_w),
            "y": _parse_dimension(_attr(tag, "y"), viewbox_h),
            "width": w,
            "height": h,
            "ratio": ratio,
            "area_ratio": area_ratio,
            "is_design": is_design,
            # Fold design furniture into background so existing
            # ``not is_background`` figure filters stay correct.
            "is_background": area_ratio >= 0.7 or is_design,
        })
    return slots

def _image_size(path: str) -> tuple[int, int] | None:
    """Read an image's rendered dimensions (EXIF orientation applied)."""
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            return im.size
    except Exception as e:
        print(f"Image size read failed for {path}: {e}")
        return None

def _sync_image_clip(svg_text: str, tag: str, new_x: float, new_y: float,
                     fit_w: float, fit_h: float) -> str:
    """Update a clip-path rect to exactly cover the image's new frame.

    The PPTX converter requires the clip rect geometry to match the image
    frame; when the image box is meet-fitted, a stale clip rect breaks the
    compile. Returns svg_text with the referenced <clipPath> rect rewritten.
    """
    m = re.search(r'clip-path="url\(#([^)]+)\)"', tag)
    if not m:
        return svg_text
    cid = m.group(1)
    cm = re.search(rf'<clipPath\b[^>]*\bid="{re.escape(cid)}"[^>]*>(.*?)</clipPath>', svg_text, re.S)
    if not cm:
        return svg_text

    def fix_rect(rm: re.Match) -> str:
        rt = rm.group(0)
        rt = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', rt, count=1)
        rt = re.sub(r'\by="[^"]*"', f'y="{new_y:g}"', rt, count=1)
        rt = re.sub(r'\bwidth="[^"]*"', f'width="{fit_w:g}"', rt, count=1)
        return re.sub(r'\bheight="[^"]*"', f'height="{fit_h:g}"', rt, count=1)

    new_inner = re.sub(r'<rect\b[^>]*?>|<rect\b[^>]*/>', fix_rect, cm.group(1), count=1)
    opening = cm.group(0)[: len(cm.group(0)) - len(cm.group(1)) - len("</clipPath>")]
    return svg_text[:cm.start()] + opening + new_inner + "</clipPath>" + svg_text[cm.end():]


def _rect_aligned_to_frame(rect: str, x: float, y: float, w: float, h: float) -> str:
    out = re.sub(r'\bx="[^"]*"', f'x="{x:g}"', rect, count=1)
    out = re.sub(r'\by="[^"]*"', f'y="{y:g}"', out, count=1)
    out = re.sub(r'\bwidth="[^"]*"', f'width="{w:g}"', out, count=1)
    return re.sub(r'\bheight="[^"]*"', f'height="{h:g}"', out, count=1)


def _sync_image_clip_to_frame(svg: str) -> str:
    """Realign every <image> clip-path rect to the image's actual x/y/w/h.

    The native PPTX converter requires a rect clip-path to cover the complete
    image frame (project clip-path check). Repair/materialization passes resize
    the image box but can leave the clipPath stale, so this pass rewrites each
    single-rect clip to exactly match its image's final frame, preserving rx/ry.
    """
    edits: list[tuple[int, int, str]] = []
    for m in re.finditer(r'<image\b[^>]*?(?:/>|>.*?</image>)', svg, re.S):
        clip = re.search(r'clip-path="url\(#([^)]+)\)"', m.group(0))
        if not clip:
            continue
        x = _parse_svg_float(_attr(m.group(0), "x"))
        y = _parse_svg_float(_attr(m.group(0), "y"))
        w = _parse_svg_float(_attr(m.group(0), "width"))
        h = _parse_svg_float(_attr(m.group(0), "height"))
        if w <= 0 or h <= 0:
            continue
        cm = re.search(rf'<clipPath\b[^>]*\bid="{re.escape(clip.group(1))}"[^>]*>(.*?)</clipPath>', svg, re.S)
        if not cm:
            continue
        if _attr(cm.group(0), "clipPathUnits") == "objectBoundingBox":
            continue
        body, n = re.subn(r'<rect\b[^>]*?(?:/>|>.*?</rect>)', lambda p: _rect_aligned_to_frame(p.group(0), x, y, w, h), cm.group(1), count=2)
        if n != 1 or body == cm.group(1):
            continue
        opening = cm.group(0)[: len(cm.group(0)) - len(cm.group(1)) - len("</clipPath>")]
        edits.append((cm.start(), cm.end(), opening + body + "</clipPath>"))
    for start, end, rep in sorted(set(edits), key=lambda e: e[0], reverse=True):
        svg = svg[:start] + rep + svg[end:]
    return svg


def _meet_fit_in_box(
    iw: float,
    ih: float,
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
) -> tuple[float, float, float, float]:
    """Return x, y, width, height for a meet-fit of (iw, ih) centered in the box."""
    if iw <= 0 or ih <= 0 or box_w <= 0 or box_h <= 0:
        return box_x, box_y, box_w, box_h
    scale = min(box_w / iw, box_h / ih)
    fit_w, fit_h = iw * scale, ih * scale
    return (
        box_x + max(0.0, box_w - fit_w) / 2.0,
        box_y + max(0.0, box_h - fit_h) / 2.0,
        fit_w,
        fit_h,
    )


def _set_image_geometry_attrs(tag: str, x: float, y: float, width: float, height: float) -> str:
    tag = re.sub(r'\s+transform="[^"]*"', '', tag, count=1)

    def set_attr(current: str, name: str, val: float) -> str:
        if re.search(rf'\b{name}="', current):
            return re.sub(rf'\b{name}="[^"]*"', f'{name}="{val:g}"', current, count=1)
        return current.replace("<image", f'<image {name}="{val:g}"', 1)

    tag = set_attr(tag, "width", width)
    tag = set_attr(tag, "height", height)
    tag = set_attr(tag, "x", x)
    tag = set_attr(tag, "y", y)
    return tag


def clamp_images_to_boxes(
    svg_text: str,
    storage_dir: str,
    boxes: list[dict] | None = None,
    viewbox_w: float | None = None,
    viewbox_h: float | None = None,
) -> str:
    """Meet-fit each content figure into the nearest planned/template box.

    Used after fill and as the deterministic repair for ``visual-zone-overflow``.
    Design furniture is never rewritten.
    """
    if viewbox_w is None or viewbox_h is None:
        viewbox_w, viewbox_h = _viewbox_dims(svg_text)
    images_dir = os.path.join(storage_dir, "images")
    slots = find_image_slots(svg_text, viewbox_w, viewbox_h)
    planned = [
        box for box in (boxes or [])
        if isinstance(box, dict)
        and not box.get("is_background")
        and not box.get("is_design")
        and float(box.get("width", 0) or 0) > 0
        and float(box.get("height", 0) or 0) > 0
    ]
    for s in reversed(slots):
        if s.get("is_design") or s.get("is_background") or s["is_data_uri"]:
            continue
        source_type = (_attr(s["tag"], "data-sunairum-source-type") or "").lower()
        if source_type in {"template", "background"}:
            continue
        fname = os.path.basename(s["href"])
        path = os.path.join(images_dir, fname)
        if not os.path.exists(path):
            path = os.path.join(storage_dir, fname)
        if not os.path.exists(path):
            continue
        size = _image_size(path)
        if not size:
            continue
        iw, ih = size
        if iw <= 0 or ih <= 0:
            continue
        if planned:
            box = min(
                planned,
                key=lambda item: abs(float(item.get("x", 0)) - s["x"])
                + abs(float(item.get("y", 0)) - s["y"]),
            )
            box_x = float(box.get("x", s["x"]))
            box_y = float(box.get("y", s["y"]))
            box_w = float(box.get("width", s["width"]))
            box_h = float(box.get("height", s["height"]))
        else:
            box_x, box_y, box_w, box_h = s["x"], s["y"], s["width"], s["height"]
        new_x, new_y, fit_w, fit_h = _meet_fit_in_box(iw, ih, box_x, box_y, box_w, box_h)
        tag = _set_image_geometry_attrs(s["tag"], new_x, new_y, fit_w, fit_h)
        svg_text = svg_text[: s["start"]] + tag + svg_text[s["end"] :]
        if 'clip-path="' in s["tag"]:
            svg_text = _sync_image_clip(svg_text, s["tag"], new_x, new_y, fit_w, fit_h)
    return svg_text

def strip_hero_echo_tokens(svg_text: str, preserve_grounded_prefix: bool = False) -> str:
    """Remove placeholder echo tokens the LLM may have left in text elements.

    Template-mode models sometimes echo the layout's "HERO"/"HERO:" placeholder
    into a real title line (and `{{...}}` leftovers). Only standalone tokens are
    removed; combined labels such as "HERO · KEY TAKEAWAYS" are kept.
    """
    svg_text = re.sub(r'\{\{[^}]+\}\}', '', svg_text)
    if preserve_grounded_prefix:
        return svg_text
    return re.sub(
        r'<text\b([^>]*)>\s*(?:HERO|HERO:)\s*</text>',
        '',
        svg_text,
        flags=re.IGNORECASE,
    )


def recentre_framed_copy(svg_text: str) -> str:
    """Put each framed text block back in the middle of the room it declares.

    Copy is centred when it is first bound, but a repair rewrites the words and
    restores the node's protected opening tag -- including its baseline. Copy that
    a repair shortened therefore kept the top baseline it needed when it was three
    lines longer, leaving the hole underneath that rendered review reports as poor
    balance. The frame each node already declares is the room it owns, so the
    correction needs no layout knowledge and is idempotent: a block that fills its
    frame is not moved at all.
    """

    def recentre(match: re.Match) -> str:
        attrs, body = match.group(1), match.group(2)
        frame = re.search(r'\bdata-pptx-frame="([^"]+)"', attrs)
        size = re.search(r'\bfont-size="([\d.]+)"', attrs)
        if not frame or not size:
            return match.group(0)
        values = [float(value) for value in re.split(r"[\s,]+", frame.group(1).strip())]
        if len(values) != 4:
            return match.group(0)
        _left, top, _width, height = values
        font_size = float(size.group(1))
        if font_size <= 0:
            return match.group(0)
        if not re.sub(r"<[^>]+>", " ", body).strip():
            return match.group(0)
        line_height = font_size * 1.2
        # Materialized bodies render every line as a tspan (the first with dy="0"),
        # so tspans are the line count; adding one for the node's own text counted
        # a phantom line and made three-line copy read as too tall to centre.
        tspan_count = len(re.findall(r"<tspan\b", body))
        block = line_height * (tspan_count if tspan_count else 1)
        if block + line_height * 2 >= height:
            return match.group(0)
        baseline = top + (height - block) / 2 + font_size * 0.8
        moved = _SLOT_Y_RE.sub(f'y="{baseline:g}"', attrs, count=1)
        return f"<text{moved}>{body}</text>"

    return re.sub(r'<text\b([^>]*)>(.*?)</text>', recentre, svg_text, flags=re.S)


def slide_body_lines(slide: dict, limit: int = 8) -> list[str]:
    """Flatten a slide's content into display lines, in authoring order."""
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    lines: list[str] = []

    def add(value) -> None:
        if len(lines) >= limit:
            return
        if isinstance(value, str):
            text = " ".join(value.split())
            if text:
                lines.append(text)
        elif isinstance(value, (int, float)):
            lines.append(str(value))
        elif isinstance(value, dict):
            for item in value.values():
                add(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                add(item)

    for key in sorted(content, key=lambda name: (str(name).upper() != "BODY", str(name))):
        if str(key).upper() == "TITLE":
            continue
        add(content[key])
    if not lines:
        grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
        for claim in grounding.get("claims", []) or []:
            if isinstance(claim, dict):
                add(claim.get("text"))
    return lines[:limit]


def minimal_slide_svg(
    slide: dict,
    palette: dict,
    width: float = 1280,
    height: float = 720,
    source: str = provenance.USER,
) -> str:
    """Retired: freehand SVG fallback removed in zero-SVG cutover."""
    del slide, palette, width, height, source
    raise RuntimeError("retired")


def _wrap_plain_text(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines, current = [], words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


_CAPACITY_CACHE: dict[str, dict] = {}


def _picture_carrier_image_tag(
    opening: str,
    *,
    placeholder_href: str,
) -> str:
    bounds = _attr(opening, "data-pptx-bounds") or ""
    parts = bounds.split()
    try:
        x, y, w, h = (float(parts[i]) for i in range(4))
    except (IndexError, ValueError):
        x = y = 0.0
        w = h = 100.0
    slot_id = _attr(opening, "id") or "presenton-image-slot"
    carrier_id = (
        slot_id.replace("-slot-", "-carrier-")
        if "-slot-" in slot_id
        else f"{slot_id}-carrier"
    )
    return (
        f'<image id="{carrier_id}" x="{x}" y="{y}" width="{w}" height="{h}" '
        f'preserveAspectRatio="xMidYMid slice" href="{placeholder_href}" '
        f'data-pptx-carrier="true" />'
    )


def ensure_picture_placeholder_carriers(
    svg_text: str,
    *,
    placeholder_href: str = f"../images/{PACK_PLACEHOLDER_IMAGE}",
) -> str:
    """Guarantee every picture placeholder has exactly one carrier ``<image>``.

    Structured Presenton packs require the same placeholder ids/order as the
    layout prototype. Empty ``<g data-pptx-placeholder="picture">`` groups fail
    compile; deleting them fails the layout lock. Fill with the neutral
    replaceable image instead.
    """
    if not svg_text:
        return ""

    def _fill_empty(match: re.Match[str]) -> str:
        opening = match.group(1)
        return f"{opening}{_picture_carrier_image_tag(opening, placeholder_href=placeholder_href)}</g>"

    filled = re.sub(
        r'(<g\b[^>]*data-pptx-placeholder="picture"[^>]*>)\s*(?:<!--.*?-->\s*)*</g>',
        _fill_empty,
        svg_text,
        flags=re.I | re.S,
    )

    def _expand_sc(match: re.Match[str]) -> str:
        opening = match.group(0)[:-2].rstrip() + ">"
        return (
            f"{opening}"
            f"{_picture_carrier_image_tag(opening, placeholder_href=placeholder_href)}"
            f"</g>"
        )

    return re.sub(
        r'<g\b[^>]*data-pptx-placeholder="picture"[^>]*/>',
        _expand_sc,
        filled,
        flags=re.I,
    )


def restore_picture_placeholders_from_template(
    svg_text: str,
    template_svg: str,
    *,
    placeholder_href: str = f"../images/{PACK_PLACEHOLDER_IMAGE}",
) -> str:
    """Re-insert picture placeholder groups present in the layout but missing in output.

    A prior sanitize deleted empty picture slots; structured export then fails
    because the slide no longer matches the layout prototype.
    """
    if not svg_text or not template_svg:
        return svg_text or ""

    def _picture_groups(source: str) -> dict[str, str]:
        found: dict[str, str] = {}
        for match in re.finditer(
            r'<g\b[^>]*data-pptx-placeholder="picture"[^>]*>.*?</g>',
            source,
            flags=re.I | re.S,
        ):
            block = match.group(0)
            slot_id = _attr(block, "id") or ""
            if slot_id:
                found[slot_id] = block
        return found

    template_groups = _picture_groups(template_svg)
    if not template_groups:
        return svg_text
    present_ids = set(_picture_groups(svg_text))
    missing = [slot_id for slot_id in template_groups if slot_id not in present_ids]
    if not missing:
        return svg_text

    insertions: list[str] = []
    for slot_id in missing:
        block = template_groups[slot_id]
        # Force neutral placeholder so withheld subject photos do not resurface.
        block = re.sub(
            r'((?:xlink:)?href=")[^"]*(")',
            rf'\1{placeholder_href}\2',
            block,
            count=1,
            flags=re.I,
        )
        if 'data-pptx-carrier="true"' not in block and "<image" in block:
            block = re.sub(
                r"(<image\b)",
                r'\1 data-pptx-carrier="true"',
                block,
                count=1,
                flags=re.I,
            )
        # Empty template group → still ensure a carrier.
        block = ensure_picture_placeholder_carriers(
            f"<svg>{block}</svg>",
            placeholder_href=placeholder_href,
        )
        inner = re.search(
            r'<g\b[^>]*data-pptx-placeholder="picture"[^>]*>.*?</g>',
            block,
            flags=re.I | re.S,
        )
        if inner:
            insertions.append(inner.group(0))

    if not insertions:
        return svg_text
    close = svg_text.rfind("</svg>")
    if close < 0:
        return svg_text + "".join(insertions)
    return svg_text[:close] + "".join(insertions) + svg_text[close:]


_GEOMETRY_LENGTH_ATTRS_BY_TAG = {
    "svg": frozenset({"x", "y", "width", "height"}),
    "rect": frozenset({"x", "y", "width", "height", "rx", "ry"}),
    "circle": frozenset({"cx", "cy", "r"}),
    "ellipse": frozenset({"cx", "cy", "rx", "ry"}),
    "line": frozenset({"x1", "y1", "x2", "y2"}),
    "text": frozenset({"x", "y", "font-size"}),
    "tspan": frozenset({"x", "y", "dx", "dy", "font-size"}),
    "image": frozenset({"x", "y", "width", "height"}),
    "use": frozenset({"x", "y", "width", "height"}),
}
_GEOMETRY_NON_NEGATIVE = frozenset(
    {"width", "height", "r", "rx", "ry", "stroke-width", "font-size"}
)
_CANONICAL_GEOMETRY_RE = re.compile(r"^-?(?:\d+(?:\.\d+)?|\.\d+)$")
_EXTRACT_NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)")
_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
}


def _format_geometry_length(value: float) -> str:
    if abs(value) < 1e-15:
        return "0"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _coerce_geometry_length(raw: str, attribute: str) -> str | None:
    """Return a canonical unitless length, or None if raw is already valid."""
    original = str(raw or "")
    text = original.strip()
    if _CANONICAL_GEOMETRY_RE.fullmatch(text):
        number = float(text)
        if attribute in _GEOMETRY_NON_NEGATIVE and number < 0:
            return _format_geometry_length(abs(number))
        # Normalize padded-but-valid values (" 12 ") to the exporter spelling.
        return None if text == original else _format_geometry_length(number)
    # Unitless with trailing px is accepted by the exporter; normalize to unitless.
    if text.lower().endswith("px"):
        candidate = text[:-2].strip()
        if _CANONICAL_GEOMETRY_RE.fullmatch(candidate):
            number = float(candidate)
            if attribute in _GEOMETRY_NON_NEGATIVE and number < 0:
                number = abs(number)
            return _format_geometry_length(number)
    # English number words from sloppy LLM geometry (e.g. height="forty").
    word = text.casefold().strip()
    if word in _NUMBER_WORDS:
        total = float(_NUMBER_WORDS[word])
        if attribute in _GEOMETRY_NON_NEGATIVE and total < 0:
            total = abs(total)
        return _format_geometry_length(total)
    match = _EXTRACT_NUMBER_RE.search(text)
    if match:
        try:
            number = float(match.group(0))
        except ValueError:
            number = None
        if number is not None and number == number:  # finite
            if attribute in _GEOMETRY_NON_NEGATIVE and number < 0:
                number = abs(number)
            return _format_geometry_length(number)
    defaults = {
        "width": 40.0,
        "height": 40.0,
        "r": 4.0,
        "rx": 4.0,
        "ry": 4.0,
        "stroke-width": 1.0,
        "font-size": 16.0,
    }
    return _format_geometry_length(defaults.get(attribute, 0.0))


_CANVAS_WIDTH = 1280.0
_CANVAS_HEIGHT = 720.0
_CANVAS_SHAPE_MARGIN = 16.0


def _fit_circle_inside_canvas(
    cx: float,
    cy: float,
    r: float,
    *,
    width: float = _CANVAS_WIDTH,
    height: float = _CANVAS_HEIGHT,
    margin: float = _CANVAS_SHAPE_MARGIN,
) -> tuple[float, float, float]:
    """Shift/shrink a circle so its full disk stays inside the canvas margin."""
    if r <= 0:
        return cx, cy, r
    max_r = min((width - 2 * margin) / 2.0, (height - 2 * margin) / 2.0)
    if max_r <= 0:
        return cx, cy, r
    if r > max_r:
        r = max_r
    cx = min(max(cx, margin + r), width - margin - r)
    cy = min(max(cy, margin + r), height - margin - r)
    return cx, cy, r


def _fit_ellipse_inside_canvas(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    *,
    width: float = _CANVAS_WIDTH,
    height: float = _CANVAS_HEIGHT,
    margin: float = _CANVAS_SHAPE_MARGIN,
) -> tuple[float, float, float, float]:
    if rx <= 0 or ry <= 0:
        return cx, cy, rx, ry
    max_rx = max(0.0, (width - 2 * margin) / 2.0)
    max_ry = max(0.0, (height - 2 * margin) / 2.0)
    if rx > max_rx:
        rx = max_rx
    if ry > max_ry:
        ry = max_ry
    cx = min(max(cx, margin + rx), width - margin - rx)
    cy = min(max(cy, margin + ry), height - margin - ry)
    return cx, cy, rx, ry


def sanitize_shapes_inside_canvas(svg: str, *, margin: float = _CANVAS_SHAPE_MARGIN) -> str:
    """Keep slide geometry inside the 1280×720 canvas.

    Handles two common spills:
    - Decorative circles/ellipses parked past an edge (title-plate blobs).
    - Full-bleed background ``<rect width="1280" height="720">`` that the deck
      editor accidentally translated (e.g. ``x="223" y="-293"``), which reads as
      the whole slide sliding off-canvas.
    """
    if not svg or not svg.strip():
        return svg
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg

    parent_by_id = {id(child): parent for parent in root.iter() for child in list(parent)}
    changed = False

    def _has_transform(elem: ET.Element) -> bool:
        current: ET.Element | None = elem
        while current is not None:
            if (current.get("transform") or "").strip():
                return True
            current = parent_by_id.get(id(current))
        return False

    def _finite(raw: str | None) -> float | None:
        if raw is None:
            return None
        try:
            value = float(str(raw).strip())
        except ValueError:
            return None
        if value != value:  # NaN
            return None
        return value

    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1].casefold() if "}" in str(elem.tag) else str(elem.tag).casefold()
        if tag == "rect":
            width = _finite(elem.get("width"))
            height = _finite(elem.get("height"))
            if width is None or height is None:
                continue
            # Near-full-bleed backgrounds must pin to the origin. Editor transforms
            # sometimes write x/y onto them and the slide looks "off canvas".
            if width >= _CANVAS_WIDTH - 1 and height >= _CANVAS_HEIGHT - 1:
                x = _finite(elem.get("x")) or 0.0
                y = _finite(elem.get("y")) or 0.0
                if abs(x) > 0.5 or abs(y) > 0.5 or abs(width - _CANVAS_WIDTH) > 0.5 or abs(height - _CANVAS_HEIGHT) > 0.5:
                    elem.set("x", "0")
                    elem.set("y", "0")
                    elem.set("width", f"{_CANVAS_WIDTH:g}")
                    elem.set("height", f"{_CANVAS_HEIGHT:g}")
                    if "transform" in elem.attrib:
                        del elem.attrib["transform"]
                    changed = True
            continue

        if tag not in {"circle", "ellipse"}:
            continue
        # Circles inside translated groups use local coords; clamping those
        # against the slide box would be wrong.
        if _has_transform(elem):
            continue
        if tag == "circle":
            cx = _finite(elem.get("cx"))
            cy = _finite(elem.get("cy"))
            r = _finite(elem.get("r"))
            if cx is None or cy is None or r is None:
                continue
            ncx, ncy, nr = _fit_circle_inside_canvas(cx, cy, r, margin=margin)
            if (ncx, ncy, nr) != (cx, cy, r):
                elem.set("cx", f"{ncx:g}")
                elem.set("cy", f"{ncy:g}")
                elem.set("r", f"{nr:g}")
                changed = True
        else:
            cx = _finite(elem.get("cx"))
            cy = _finite(elem.get("cy"))
            rx = _finite(elem.get("rx"))
            ry = _finite(elem.get("ry"))
            if cx is None or cy is None or rx is None or ry is None:
                continue
            ncx, ncy, nrx, nry = _fit_ellipse_inside_canvas(cx, cy, rx, ry, margin=margin)
            if (ncx, ncy, nrx, nry) != (cx, cy, rx, ry):
                elem.set("cx", f"{ncx:g}")
                elem.set("cy", f"{ncy:g}")
                elem.set("rx", f"{nrx:g}")
                elem.set("ry", f"{nry:g}")
                changed = True

    if not changed:
        return svg
    if root.tag.startswith("{"):
        ns = root.tag[1:].split("}", 1)[0]
        ET.register_namespace("", ns)
    return ET.tostring(root, encoding="unicode")


def sanitize_project_line_end_markers(svg: str) -> str:
    """No-op: SVG marker repair lived in the retired SVG compiler."""
    return svg


def sanitize_project_geometry_lengths(svg: str) -> str:
    """Coerce invalid geometry/text lengths before native export.

    Free-design LLMs occasionally write English words or spaced junk into x/y/
    width/height/font-size (e.g. ``font-size=" thirty"``). Repair here so one
    bad attribute does not abort the deck.
    """
    if not svg or not svg.strip():
        return svg
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        # Regex fallback when the document is not yet well-formed.
        def fix_attr(match: re.Match[str]) -> str:
            attr = match.group(1)
            raw = match.group(2)
            fixed = _coerce_geometry_length(raw, attr.casefold())
            return f'{attr}="{fixed if fixed is not None else raw.strip()}"'

        return re.sub(
            r'\b(x|y|cx|cy|r|rx|ry|x1|y1|x2|y2|dx|dy|width|height|stroke-width|font-size)\s*=\s*"([^"]*)"',
            fix_attr,
            svg,
            flags=re.I,
        )

    changed = False
    # Editor selection chrome — native export rejects class= on <text>.
    _strip_editor_attrs = {
        "class",
        "contenteditable",
        "tabindex",
        "data-sunairum-text-editing",
    }
    _strip_style_props = {
        "width", "height", "x", "y", "cx", "cy", "r", "rx", "ry", "stroke-width",
        "cursor", "touch-action", "user-select", "-webkit-user-select", "outline", "filter",
        # Editor CSS (fill-box helpers) must not block native text export.
        "transform", "transform-origin", "transform-box",
    }
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1] if "}" in str(elem.tag) else str(elem.tag)
        for bad in list(_strip_editor_attrs):
            if bad in elem.attrib:
                del elem.attrib[bad]
                changed = True
        attrs = set(_GEOMETRY_LENGTH_ATTRS_BY_TAG.get(tag.casefold(), frozenset()))
        attrs.add("stroke-width")
        for attribute in attrs:
            raw = elem.get(attribute)
            if raw is None:
                continue
            fixed = _coerce_geometry_length(raw, attribute.casefold())
            if fixed is not None:
                elem.set(attribute, fixed)
                changed = True
        style = elem.get("style")
        if style:
            parts: list[str] = []
            style_changed = False
            for chunk in style.split(";"):
                if not chunk.strip():
                    continue
                if ":" not in chunk:
                    parts.append(chunk)
                    continue
                key, value = chunk.split(":", 1)
                key_norm = key.strip().casefold()
                val = value.strip()
                # Editor/preview sometimes injects style="width:100%;height:auto"
                # on <svg>; native export rejects percentage geometry.
                if key_norm in _strip_style_props:
                    if (
                        key_norm in {"width", "height", "x", "y", "cx", "cy", "r", "rx", "ry", "stroke-width"}
                        and val.casefold() not in {"auto", "none"}
                        and "%" not in val
                    ):
                        fixed = _coerce_geometry_length(val, key_norm)
                        if fixed is None:
                            parts.append(chunk)
                        else:
                            parts.append(f"{key.strip()}:{fixed}")
                            style_changed = True
                        continue
                    style_changed = True
                    continue
                parts.append(chunk)
            if style_changed:
                if parts:
                    elem.set("style", ";".join(parts))
                elif "style" in elem.attrib:
                    del elem.attrib["style"]
                changed = True
    if not changed:
        return svg
    # Keep the default SVG namespace unprefixed (avoid ns0:svg from tostring).
    if root.tag.startswith("{"):
        ns = root.tag[1:].split("}", 1)[0]
        ET.register_namespace("", ns)
    return ET.tostring(root, encoding="unicode")


_EVIDENCE_FOOTER_RE = re.compile(
    r"<text\b[^>]*>[^<]*(?:ev-page-\d+|Evidence\s*:)[^<]*</text>\s*",
    re.I,
)
_PAGE_NUMBER_NODE_RE = re.compile(
    r"<text\b[^>]*\bdata-sunairum-page-number=\"1\"[^>]*>.*?</text>\s*",
    re.I | re.S,
)
_TEXT_NODE_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.I | re.S)
_PLANNER_CODE_RE = re.compile(
    r"^P\d{2}(?:\s*/\s*|\s*[·•|]\s*|\s+).+",
    re.I,
)
_PAGE_ONLY_RE = re.compile(r"^(?:P?\d{1,2})(?:\s*/\s*\d{1,2})?$", re.I)


def _text_plain(body: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", body or "")
    return re.sub(r"\s+", " ", plain).strip()


def _attr_float(attrs: str, name: str, default: float = 0.0) -> float:
    match = re.search(rf'\b{re.escape(name)}="([^"]+)"', attrs or "", flags=re.I)
    if not match:
        return default
    try:
        return float(str(match.group(1)).strip().rstrip("px"))
    except ValueError:
        return default


def repair_title_stack_spacing(svg: str) -> str:
    """Push subtitles/rules down when a large title would collide with them."""
    try:
        from tasks.layout_geometry import text_width_px
    except ImportError:
        from layout_geometry import text_width_px  # type: ignore

    def _fmt(val: float) -> str:
        return f"{val:.1f}".rstrip("0").rstrip(".")

    nodes = list(_TEXT_NODE_RE.finditer(svg))
    if not nodes:
        return svg
    # Prefer the largest top-band title.
    title = None
    for match in nodes:
        attrs, body = match.group(1), match.group(2)
        plain = _text_plain(body)
        if not plain or len(plain) < 12:
            continue
        fs = _attr_float(attrs, "font-size", 0.0)
        y = _attr_float(attrs, "y", 0.0)
        if fs < 28 or y > 160 or y < 20:
            continue
        if title is None or fs > title["fs"]:
            title = {
                "match": match,
                "attrs": attrs,
                "body": body,
                "plain": plain,
                "fs": fs,
                "x": _attr_float(attrs, "x", 60.0),
                "y": y,
                "anchor": (re.search(r'\btext-anchor="([^"]+)"', attrs, flags=re.I) or [None, "start"])[1],
            }
    if not title:
        return svg

    avail = 1220.0 - title["x"] if str(title["anchor"]).lower() != "middle" else 1100.0
    width = text_width_px(title["plain"], title["fs"], 0.0, True, None)
    lines = max(1, int(math.ceil(width / max(avail, 1.0))))
    if len(title["plain"]) > 54:
        lines = max(lines, 2)
    if len(title["plain"]) > 90:
        lines = max(lines, 3)
    existing_tspans = len(re.findall(r"<tspan\b", title["body"], flags=re.I))
    if existing_tspans >= 2:
        lines = max(lines, existing_tspans)
    title_bottom = title["y"] + (lines - 1) * title["fs"] * 1.2 + title["fs"] * 0.28
    min_next = title_bottom + 16.0

    # Only clear collisions with the title block (subtitle / rule under title).
    # Do not repack the whole header band — that can shove labels into the body.
    shifts: list[tuple[int, int, float]] = []
    cursor = min_next
    for match in nodes:
        if match.start() == title["match"].start():
            continue
        attrs = match.group(1)
        if re.search(r'\bdata-sunairum-page-number="1"', attrs, flags=re.I):
            continue
        y = _attr_float(attrs, "y", 0.0)
        fs = max(_attr_float(attrs, "font-size", 14.0), 12.0)
        if y <= title["y"] or y >= min_next or y > 200:
            continue
        y_match = re.search(r'\by="([^"]+)"', attrs, flags=re.I)
        if not y_match:
            continue
        new_y = max(y, cursor + fs * 0.1)
        cursor = new_y + max(14.0, fs * 0.5)
        abs_start = match.start(1) + y_match.start(1)
        abs_end = match.start(1) + y_match.end(1)
        shifts.append((abs_start, abs_end, new_y))

    for line_match in re.finditer(r"<line\b([^>]*)/?>", svg, flags=re.I):
        attrs = line_match.group(1)
        y1 = _attr_float(attrs, "y1", 0.0)
        y2 = _attr_float(attrs, "y2", 0.0)
        if abs(y1 - y2) > 1.0:
            continue
        if y1 <= title["y"] or y1 > 200:
            continue
        # Rules must sit below the title and any subtitle we just placed.
        target = max(y1, cursor + 4.0, min_next + 4.0)
        if target <= y1 + 0.1:
            continue
        for name in ("y1", "y2"):
            ym = re.search(rf'\b{name}="([^"]+)"', attrs, flags=re.I)
            if not ym:
                continue
            abs_start = line_match.start(1) + ym.start(1)
            abs_end = line_match.start(1) + ym.end(1)
            shifts.append((abs_start, abs_end, target))
        cursor = target + 12.0

    out = svg
    for start, end, new_y in sorted(shifts, key=lambda item: item[0], reverse=True):
        out = out[:start] + _fmt(new_y) + out[end:]

    # Wrap long title into tspans for stable native export (skip if already wrapped).
    if lines >= 2 and existing_tspans < 2:
        words = title["plain"].split()
        target = max(1, int(math.ceil(len(words) / lines)))
        chunks: list[str] = []
        buf: list[str] = []
        for word in words:
            buf.append(word)
            if len(buf) >= target and len(chunks) + 1 < lines:
                chunks.append(" ".join(buf))
                buf = []
        if buf:
            chunks.append(" ".join(buf))
        if len(chunks) >= 2:
            x = title["x"]
            fs = title["fs"]
            tspan_bits = []
            for index, chunk in enumerate(chunks):
                dy = "0" if index == 0 else _fmt(fs * 1.2)
                tspan_bits.append(f'<tspan x="{x:g}" dy="{dy}">{chunk}</tspan>')
            old = title["match"].group(0)
            new = re.sub(
                r"(<text\b[^>]*>)(.*?)(</text>)",
                lambda m: m.group(1) + "".join(tspan_bits) + m.group(3),
                old,
                count=1,
                flags=re.I | re.S,
            )
            out = out.replace(old, new, 1)
    return out


def _page_number_anchor(svg: str, label: str) -> tuple[float, float]:
    """Bottom-right page chrome that stays off filled takeaway/callout bands."""
    default_x, default_y = 1220.0, 698.0
    label_w = max(40.0, len(label or "00 / 00") * 12.0 * 0.55)
    label_h = 16.0

    def _glyph_box(x: float, y: float) -> tuple[float, float, float, float]:
        # End-anchored baseline → ink roughly above/left of (x, y).
        return (x - label_w - 4.0, y - 12.0, label_w + 8.0, label_h)

    def _overlap(
        a: tuple[float, float, float, float], b: tuple[float, float, float, float]
    ) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)

    blockers: list[tuple[float, float, float, float]] = []
    for match in re.finditer(r"<rect\b([^>]*)/?>", svg or "", flags=re.I):
        attrs = match.group(1) or ""
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        # Bottom-right chrome zone only; ignore tiny accents / rails.
        if w < 80.0 or h < 36.0:
            continue
        if y + h < 620.0 or x + w < 900.0:
            continue
        blockers.append((x, y, w, h))

    def _clear(x: float, y: float) -> bool:
        box = _glyph_box(x, y)
        return not any(_overlap(box, b) for b in blockers)

    if _clear(default_x, default_y):
        return default_x, default_y

    covering = [b for b in blockers if _overlap(_glyph_box(default_x, default_y), b)]
    if covering:
        top = min(b[1] for b in covering)
        # Sit just above the band (glyph extends ~4px below baseline).
        lifted = max(600.0, top - 10.0)
        if _clear(default_x, lifted):
            return default_x, lifted
        left = min(b[0] for b in covering)
        shifted = max(200.0, left - 12.0)
        if _clear(shifted, default_y):
            return shifted, default_y

    # Walk upward from the default until the glyph clears every blocker.
    for y in range(698, 599, -8):
        if _clear(default_x, float(y)):
            return default_x, float(y)
    return default_x, default_y


def sanitize_presentation_chrome(
    svg: str,
    *,
    slide_number: int | None = None,
    total_slides: int | None = None,
    chrome_fill: str | None = None,
    chrome_font: str | None = None,
) -> str:
    """Strip evidence/P0N/legacy page chrome; normalize a single page number.

    Intentionally does NOT call repair_title_stack_spacing — geometry nudges
    desync transforms/circles and caused overlap regressions.
    """
    if not svg or not svg.strip():
        return svg
    cleaned = _EVIDENCE_FOOTER_RE.sub("", svg)
    cleaned = _PAGE_NUMBER_NODE_RE.sub("", cleaned)

    def _drop_chrome_text(match: re.Match[str]) -> str:
        attrs, body = match.group(1), match.group(2)
        if re.search(r'\bdata-sunairum-page-number="1"', attrs or "", flags=re.I):
            return ""
        plain = _text_plain(body)
        # Planner codes like "P03 / METHOD FRAMING" anywhere.
        if _PLANNER_CODE_RE.match(plain):
            return ""
        # Any plain page-only label (incl. legacy "14 / 14" inside transforms).
        if _PAGE_ONLY_RE.fullmatch(plain):
            return ""
        return match.group(0)

    cleaned = _TEXT_NODE_RE.sub(_drop_chrome_text, cleaned)
    # Do not run repair_title_stack_spacing here.

    if slide_number is not None and slide_number > 0:
        # Match HTML IR: plain n/N (not P02 / zero-padded 02 / 14).
        label = f"{int(slide_number)}"
        if total_slides and int(total_slides) > 0:
            label = f"{int(slide_number)}/{int(total_slides)}"
        fill = str(chrome_fill or "#94A3B8").strip() or "#94A3B8"
        if not fill.startswith("#"):
            fill = "#94A3B8"
        font = str(chrome_font or "Arial, sans-serif").strip() or "Arial, sans-serif"
        px, py = _page_number_anchor(cleaned, label)
        page_node = (
            f'<text data-sunairum-page-number="1" x="{px:g}" y="{py:g}" text-anchor="end" '
            f'font-family="{font}" font-size="12" fill="{fill}">{label}</text>'
        )
        if re.search(r"</svg>\s*$", cleaned, flags=re.I):
            cleaned = re.sub(r"</svg>\s*$", page_node + "\n</svg>", cleaned, count=1, flags=re.I)
        else:
            cleaned = cleaned.rstrip() + "\n" + page_node + "\n</svg>"
    return cleaned


def finalize_svg_document(svg: str) -> str:
    """Legacy no-op — SVG freehand stack removed; prefer Slide IR."""
    return svg or ""


def sanitize_flat_structure_metadata(svg: str) -> str:
    """Remove flat-export Master/Layout metadata without removing native carriers."""
    forbidden = (
        "data-pptx-master", "data-pptx-master-name", "data-pptx-layout",
        "data-pptx-layout-name", "data-pptx-layer", "data-pptx-editable",
        "data-pptx-placeholder", "data-pptx-idx", "data-pptx-carrier",
    )
    for name in forbidden:
        svg = re.sub(rf'\s+{re.escape(name)}="[^"]*"', "", svg)
    return svg


def strip_unfilled_native_table_carriers(svg: str) -> str:
    """Drop table markers the native exporter would reject for having no rows.

    Templatized gallery layouts ship empty ``data-pptx-replace-with="table"``
    carriers as geometry placeholders. When no source table is bound, leaving
    them in the SVG makes native PPTX compile raise for an empty table and
    abort the whole deck.
    """
    carrier_re = re.compile(
        r'<g\b[^>]*data-pptx-replace-with="table"[^>]*>.*?</g>',
        re.S | re.I,
    )

    def keep_or_drop(match: re.Match) -> str:
        markup = match.group(0)
        metadata = re.search(r'<metadata\b[^>]*>(.*?)</metadata>', markup, re.S | re.I)
        if not metadata:
            return ""
        try:
            payload = json.loads(html.unescape(metadata.group(1)).strip())
        except (TypeError, json.JSONDecodeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        columns = payload.get("columns")
        rows = payload.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            return ""
        # Native export builds [columns] + rows; either alone is enough for ≥1 row.
        if not columns and not rows:
            return ""
        return markup

    return carrier_re.sub(keep_or_drop, svg)


def materialize_source_table_svg(svg: str, table_payload: dict | None = None) -> str:
    """Replace or add a table carrier with exact bound source cells."""
    if isinstance(table_payload, dict):
        already_id = str(table_payload.get("source_table_id") or "").strip()
        if already_id and re.search(
            rf'data-sunairum-source-table-id="{re.escape(already_id)}"',
            svg or "",
            flags=re.I,
        ):
            columns = table_payload.get("columns")
            rows = table_payload.get("rows")
            if not isinstance(columns, list) or not columns:
                headers = table_payload.get("headers")
                if isinstance(headers, list) and headers:
                    columns = list(headers)
            if not isinstance(columns, list):
                columns = []
            if not isinstance(rows, list):
                rows = []

            def _carrier_has_native_metadata(body: str) -> bool:
                meta = re.search(
                    r"<metadata\b[^>]*>(.*?)</metadata>",
                    body or "",
                    flags=re.I | re.S,
                )
                if not meta:
                    return False
                try:
                    payload = json.loads(html.unescape(meta.group(1)).strip())
                except (TypeError, json.JSONDecodeError):
                    return False
                if not isinstance(payload, dict):
                    return False
                cols = payload.get("columns")
                rws = payload.get("rows")
                if not isinstance(cols, list) or not isinstance(rws, list):
                    return False
                return bool(cols or rws)

            def _bind_or_strip(match: re.Match) -> str:
                attrs, body = match.group(1), match.group(2)
                if f'data-sunairum-source-table-id="{already_id}"' not in attrs:
                    return match.group(0)
                # Painted Intent grids may omit metadata — inject so compile strip
                # does not delete the carrier.
                if not _carrier_has_native_metadata(body) and (columns or rows):
                    resolved_rows = (1 if columns else 0) + len(rows)
                    resolved_cols = len(columns) if columns else max(
                        (len(row) for row in rows if isinstance(row, list)),
                        default=0,
                    )
                    x = float(table_payload.get("x", 80) or 80)
                    y = float(table_payload.get("y", 200) or 200)
                    width = float(table_payload.get("width", 1120) or 1120)
                    height = float(table_payload.get("height", 400) or 400)
                    transform = re.search(
                        r'transform="\s*translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"',
                        attrs,
                        flags=re.I,
                    )
                    if transform:
                        x, y = float(transform.group(1)), float(transform.group(2))
                    bound = {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "source_table_id": already_id,
                        "columns": columns,
                        "rows": rows,
                        "row_heights": [1] * max(1, resolved_rows),
                        "column_widths": [1] * max(1, resolved_cols),
                    }
                    encoded = html.escape(
                        json.dumps(bound, ensure_ascii=False), quote=False
                    )
                    meta_tag = (
                        f'<metadata type="application/json">{encoded}</metadata>'
                    )
                    if re.search(r"<metadata\b", body, flags=re.I):
                        body = re.sub(
                            r"<metadata\b[^>]*>.*?</metadata>",
                            meta_tag,
                            body,
                            count=1,
                            flags=re.I | re.S,
                        )
                    else:
                        body = meta_tag + body
                # Do not rewrite cells. Still strip a leftover parent translate
                # so absolute cell coords are not double-offset.
                clean = re.sub(r'\s*transform="[^"]*"', "", attrs, flags=re.I)
                return f"<g{clean}>{body}</g>"

            return re.sub(
                r"<g\b([^>]*)>(.*?)</g>",
                _bind_or_strip,
                svg or "",
                flags=re.I | re.S,
            )

    carrier_re = re.compile(
        r'<g\b([^>]*data-pptx-replace-with="table"[^>]*)>(.*?)</g>',
        re.S | re.I,
    )

    def _native_table_axis_counts(columns: list, rows: list) -> tuple[int, int]:
        # Native export resolves rows as [columns] + rows when columns is non-empty.
        resolved_rows = (1 if columns else 0) + len(rows)
        resolved_cols = len(columns) if columns else (
            max((len(row) for row in rows if isinstance(row, list)), default=0)
        )
        return resolved_rows, resolved_cols

    def add_fallback_carrier(source_svg: str, payload: dict) -> str:
        """Fill an authored table slot, or inject a recipe-owned table region.

        Never paste an opaque carrier over freehand prose via reserved_table_band.
        """
        source_table_id = str(payload.get("source_table_id") or "").strip()
        columns = payload.get("columns")
        rows = payload.get("rows")
        if not source_table_id or not isinstance(columns, list) or not isinstance(rows, list):
            return source_svg

        def _band_from_slot(svg_text: str) -> dict[str, float] | None:
            slot = re.search(
                r'<g\b([^>]*\bdata-sunairum-table-slot="[^"]*"[^>]*)>(.*?)</g>',
                svg_text,
                flags=re.I | re.S,
            )
            if not slot:
                return None
            attrs, body = slot.group(1), slot.group(2)
            x = y = 0.0
            transform = re.search(
                r'transform="\s*translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)"',
                attrs,
                flags=re.I,
            )
            if transform:
                try:
                    x, y = float(transform.group(1)), float(transform.group(2))
                except ValueError:
                    x = y = 0.0
            rect = re.search(
                r'<rect\b[^>]*\bwidth="([-\d.]+)"[^>]*\bheight="([-\d.]+)"',
                body,
                flags=re.I,
            )
            if not rect:
                rect = re.search(
                    r'<rect\b[^>]*\bheight="([-\d.]+)"[^>]*\bwidth="([-\d.]+)"',
                    body,
                    flags=re.I,
                )
                if rect:
                    try:
                        return {
                            "x": x,
                            "y": y,
                            "width": float(rect.group(2)),
                            "height": float(rect.group(1)),
                            "slot_span": slot.span(),
                        }
                    except ValueError:
                        return None
            if not rect:
                return None
            try:
                return {
                    "x": x,
                    "y": y,
                    "width": float(rect.group(1)),
                    "height": float(rect.group(2)),
                    "slot_span": slot.span(),
                }
            except ValueError:
                return None

        band = _band_from_slot(source_svg)
        if not band:
            # Recipe-owned geometry (right/bottom table) — not content-blind reserved_table_band.
            try:
                from tasks.intent_hosts import TABLE_HOST
            except ImportError:  # pragma: no cover
                from intent_hosts import TABLE_HOST  # type: ignore
            tx, ty, tw, th = TABLE_HOST
            band = {
                "x": tx,
                "y": ty,
                "width": tw,
                "height": th,
                "slot_span": None,
            }

        resolved_rows, resolved_cols = _native_table_axis_counts(columns, rows)
        fallback_payload = {
            "x": band["x"],
            "y": band["y"],
            "width": band["width"],
            "height": band["height"],
            "source_table_id": source_table_id,
            "columns": columns,
            "rows": rows,
            "row_heights": [1] * resolved_rows,
            "column_widths": [1] * max(1, resolved_cols),
            "style": payload.get("style") if isinstance(payload.get("style"), dict) else {},
        }
        safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", source_table_id).strip("-") or "source"
        metadata = html.escape(json.dumps(fallback_payload, ensure_ascii=False), quote=False)
        carrier = (
            f'<g id="sunairum-source-table-carrier-{safe_id}" data-pptx-replace-with="table" '
            f'data-sunairum-table-id="{html.escape(source_table_id, quote=True)}">'
            f'<rect x="{band["x"]:g}" y="{band["y"]:g}" width="{band["width"]:g}" '
            f'height="{band["height"]:g}" fill="#ffffff" stroke="#d0d5dd" stroke-width="1"/>'
            f'<metadata type="application/json">{metadata}</metadata></g>'
        )
        span = band.get("slot_span")
        if span:
            start, end = span
            return f"{source_svg[:start]}{carrier}{source_svg[end:]}"
        closing_svg = source_svg.rfind("</svg>")
        if closing_svg < 0:
            return source_svg
        return f"{source_svg[:closing_svg]}{carrier}{source_svg[closing_svg:]}"

    CELL_FONT_FAMILY = "Arial, sans-serif"
    CELL_PAD_X = 8.0
    CELL_PAD_Y = 6.0

    def replace(match: re.Match) -> str:
        attrs, body = match.group(1), match.group(2)
        metadata = re.search(r'<metadata\b[^>]*>(.*?)</metadata>', body, re.S | re.I)
        if not metadata:
            # Empty slot without metadata — leave intact (add_fallback fills earlier).
            if re.search(r'data-sunairum-table-slot=', attrs, flags=re.I):
                return match.group(0)
            return ""
        try:
            payload = json.loads(html.unescape(metadata.group(1)).strip())
        except (TypeError, json.JSONDecodeError):
            return ""
        source_table_id = payload.get("source_table_id")
        columns = payload.get("columns")
        rows = payload.get("rows")
        # Unfilled templatizer carriers must not reach native export.
        if not source_table_id or not isinstance(columns, list) or not isinstance(rows, list):
            return ""
        if not columns and not rows:
            return ""
        x = float(payload.get("x", 0) or 0)
        y = float(payload.get("y", 0) or 0)
        width = float(payload.get("width", 800) or 800)
        height = float(payload.get("height", 400) or 400)
        # Absolute cell geometry must not ride a parent translate (side-slot bug:
        # transform(540,160) + payload x=24,width=1232 → past right edge).
        # Clamp into the content frame above page chrome (y≈698).
        _SAFE_L, _SAFE_T, _SAFE_R, _SAFE_B = 40.0, 160.0, 1240.0, 620.0
        x = max(_SAFE_L, min(x, _SAFE_R - 80.0))
        y = max(_SAFE_T, min(y, _SAFE_B - 40.0))
        width = max(80.0, min(width, _SAFE_R - x))
        height = max(40.0, min(height, _SAFE_B - y))
        payload["x"], payload["y"], payload["width"], payload["height"] = x, y, width, height
        style = payload.get("style") if isinstance(payload.get("style"), dict) else {}
        # Readability floor: never emit tiny table type. Prefer 13–14pt.
        _MIN_TABLE_FS = 12.0
        font_size = max(_MIN_TABLE_FS, min(14.0, float(style.get("font_size", 14) or 14)))
        header_size = max(
            _MIN_TABLE_FS, min(14.0, float(style.get("header_font_size", font_size) or font_size))
        )
        header_fill = str(
            style.get("header_fill") or style.get("theme_primary") or "#E2E8F0"
        ).strip() or "#E2E8F0"
        text_fill = str(
            style.get("text_fill") or style.get("theme_text") or "#334155"
        ).strip() or "#334155"
        header_text_fill = str(
            style.get("header_text_fill") or text_fill
        ).strip() or text_fill
        # When restyled to a saturated primary, prefer white header labels.
        if style.get("theme_primary") and not style.get("header_text_fill"):
            header_text_fill = "#FFFFFF"

        def _cell_plain(cell) -> str:
            raw = str(cell.get("text", "") if isinstance(cell, dict) else cell)
            # Match evidence OCR cleanup so preview/PPTX stay readable.
            raw = re.sub(r"\s+", " ", raw).strip()
            raw = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", raw)
            raw = re.sub(r"(?<=[+\-])\s+(?=\d)", "", raw)
            raw = re.sub(r"(?<=\d)\s+%", "%", raw)
            return raw

        def _normalize_grid(grid: list) -> list:
            out: list = []
            for item in grid:
                if isinstance(item, list):
                    out.append(_normalize_grid(item))
                elif isinstance(item, dict):
                    cleaned = dict(item)
                    cleaned["text"] = _cell_plain(item)
                    out.append(cleaned)
                else:
                    out.append(_cell_plain(item))
            return out

        columns = _normalize_grid(columns if isinstance(columns, list) else [])
        rows = _normalize_grid(rows if isinstance(rows, list) else [])
        payload["columns"] = columns
        payload["rows"] = rows

        # Content-aware column weights from measured cell strings (not equal 1/n).
        column_count = max(1, len(columns))
        col_weights: list[float] = []
        for column_index in range(column_count):
            samples: list[str] = []
            if column_index < len(columns):
                samples.append(_cell_plain(columns[column_index]))
            for row in rows:
                if isinstance(row, list) and column_index < len(row):
                    samples.append(_cell_plain(row[column_index]))
            longest = max((len(s) for s in samples), default=1)
            col_weights.append(max(4.0, float(longest)))
        weight_sum = sum(col_weights) or float(column_count)
        column_widths_frac = [w / weight_sum for w in col_weights]

        def native_height_estimate(
            check_rows: list,
            body_pt: float,
            head_pt: float,
            *,
            width_px: float,
            fracs: list[float],
        ) -> float:
            width_pt = width_px * 0.75
            total = 0.0
            for row_index, row in enumerate([columns, *check_rows]):
                cell_pt = head_pt if row_index == 0 else body_pt
                need = 0.0
                for column_index in range(column_count):
                    col_w = width_pt * fracs[column_index]
                    chars = max(1, int(max(col_w - 18.0, 1.0) / max(cell_pt * 0.53, 1.0)))
                    cell = row[column_index] if isinstance(row, list) and column_index < len(row) else ""
                    value = _cell_plain(cell)
                    lines = max(
                        1,
                        sum(
                            max(1, (len(line) + chars - 1) // chars)
                            for line in (value.splitlines() or [""])
                        ),
                    )
                    need = max(need, lines * cell_pt * 1.3 + 9.0)
                total += need
            return total

        # Prefer keeping ≥12pt: grow the carrier within the safe frame, then
        # drop trailing rows. Never shrink below the readability floor.
        zone_height_pt = height * 0.75
        max_height_px = max(height, _SAFE_B - y)
        fitted = font_size
        for candidate in (font_size, 13.0, _MIN_TABLE_FS):
            if candidate > font_size + 0.01:
                continue
            need_pt = native_height_estimate(
                rows, candidate, min(header_size, candidate), width_px=width, fracs=column_widths_frac
            )
            if need_pt <= zone_height_pt:
                fitted = candidate
                break
            # Grow band before giving up on this font size.
            need_px = need_pt / 0.75
            if need_px <= max_height_px + 0.5:
                height = min(max_height_px, max(height, need_px))
                payload["height"] = height
                zone_height_pt = height * 0.75
                fitted = candidate
                break
            fitted = candidate
        else:
            fitted = _MIN_TABLE_FS

        while (
            len(rows) > 1
            and native_height_estimate(
                rows, fitted, min(header_size, fitted), width_px=width, fracs=column_widths_frac
            )
            > height * 0.75
        ):
            rows = rows[:-1]
        payload["rows"] = rows
        payload.pop("row_heights", None)
        font_size = max(_MIN_TABLE_FS, fitted)
        header_size = max(_MIN_TABLE_FS, min(header_size, font_size + 1.0))
        style = {
            **style,
            "font_size": font_size,
            "header_font_size": header_size,
        }
        payload["style"] = style
        # Keep axis weights aligned with native resolution ([columns]+rows).
        resolved_rows, resolved_cols = _native_table_axis_counts(
            columns if isinstance(columns, list) else [],
            rows if isinstance(rows, list) else [],
        )
        if resolved_rows:
            payload["row_heights"] = [1] * resolved_rows
        if resolved_cols:
            # Persist fractional widths for the native exporter.
            payload["column_widths"] = [
                max(1, int(round(frac * 100))) for frac in column_widths_frac
            ]

        from tasks.text_layout import line_height_for, wrap as wrap_to_width

        all_rows = [columns, *rows] if columns else list(rows)
        row_count = max(1, len(all_rows))
        # Pixel column edges from content-aware fractions.
        col_pixel_widths = [width * frac for frac in column_widths_frac]

        # Cell text is broken against the cell's real width using the same metrics
        # the renderer uses. It used to be wrapped by dividing the column width by
        # a flat 0.55em character guess, so a wide cell under-filled and a narrow
        # one overran into its neighbour -- which is what the checker reported as
        # table-cell-overlap, the largest single error category on the last run.
        wrapped: list[list[list[str]]] = []
        for row_index, row in enumerate(all_rows):
            cell_font = header_size if row_index == 0 else font_size
            bold = row_index == 0
            row_lines: list[list[str]] = []
            for column_index in range(column_count):
                cell = row[column_index] if column_index < len(row) else ""
                value = _cell_plain(cell)
                inner_width = max(1.0, col_pixel_widths[column_index] - CELL_PAD_X * 2)
                row_lines.append(
                    wrap_to_width(value, inner_width, cell_font, CELL_FONT_FAMILY, bold) or [""]
                )
            wrapped.append(row_lines)

        # Rows are as tall as their tallest cell needs, so a two-line cell no longer
        # has to spill to be readable. Where the whole table needs more room than the
        # layout gave it, the shortfall is declared rather than drawn over the
        # neighbouring rows.
        needs: list[float] = []
        for row_index, row_lines in enumerate(wrapped):
            cell_font = header_size if row_index == 0 else font_size
            spacing = line_height_for(cell_font, CELL_FONT_FAMILY, row_index == 0)
            tallest = max(len(lines) for lines in row_lines)
            needs.append(cell_font + spacing * (tallest - 1) + CELL_PAD_Y * 2)
        required = sum(needs)
        if required <= height:
            slack = (height - required) / row_count
            heights = [need + slack for need in needs]
            overflow_rows = 0
        else:
            scale = height / required
            heights = [need * scale for need in needs]
            overflow_rows = sum(
                1 for index, need in enumerate(needs) if heights[index] < need - 0.5
            )

        tops: list[float] = []
        cursor = y
        for value in heights:
            tops.append(cursor)
            cursor += value

        parts = [
            f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" fill="#FFFFFF" stroke="#D6DCE3" stroke-width="1"/>',
            f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{heights[0]:g}" fill="{html.escape(header_fill, quote=True)}"/>',
        ]
        dropped_lines = 0
        for row_index, row_lines in enumerate(wrapped):
            cell_font = header_size if row_index == 0 else font_size
            spacing = line_height_for(cell_font, CELL_FONT_FAMILY, row_index == 0)
            row_top = tops[row_index]
            row_height = heights[row_index]
            capacity = max(1, int((row_height - CELL_PAD_Y * 2 - cell_font) / spacing) + 1)
            col_x_cursor = x
            for column_index, lines in enumerate(row_lines):
                column_width = col_pixel_widths[column_index]
                cell_x = col_x_cursor
                # The cell's box is declared, so the checker reads it instead of
                # reconstructing a grid from the rules drawn between cells.
                parts.append(
                    f'<rect data-pptx-cell="{row_index}-{column_index}" '
                    f'x="{cell_x:g}" y="{row_top:g}" width="{column_width:g}" '
                    f'height="{row_height:g}" fill="none"/>'
                )
                visible = lines[:capacity]
                dropped_lines += max(0, len(lines) - capacity)
                if not any(line.strip() for line in visible):
                    col_x_cursor += column_width
                    continue
                block = cell_font + spacing * (len(visible) - 1)
                baseline = row_top + max(
                    CELL_PAD_Y + cell_font, (row_height - block) / 2 + cell_font,
                )
                spans = "".join(
                    f'<tspan x="{cell_x + CELL_PAD_X:g}" dy="{0 if index == 0 else spacing:g}">'
                    f'{html.escape(line, quote=False)}</tspan>'
                    for index, line in enumerate(visible)
                )
                fill = header_text_fill if row_index == 0 else text_fill
                parts.append(
                    f'<text data-sunairum-source-table-text="1" '
                    f'{provenance.ATTRIBUTE}="{provenance.EVIDENCE}" x="{cell_x + CELL_PAD_X:g}" '
                    f'y="{baseline:g}" fill="{html.escape(fill, quote=True)}" font-family="{CELL_FONT_FAMILY}" '
                    f'font-size="{cell_font:g}" '
                    f'font-weight="{"700" if row_index == 0 else "400"}">{spans}</text>'
                )
                col_x_cursor += column_width
        col_edge = x
        for column_index in range(1, column_count):
            col_edge += col_pixel_widths[column_index - 1]
            line_x = col_edge
            parts.append(f'<line x1="{line_x:g}" y1="{y:g}" x2="{line_x:g}" y2="{y + height:g}" stroke="#D6DCE3" stroke-width="1"/>')
        for row_index in range(1, row_count):
            line_y = tops[row_index]
            parts.append(f'<line x1="{x:g}" y1="{line_y:g}" x2="{x + width:g}" y2="{line_y:g}" stroke="#D6DCE3" stroke-width="1"/>')
        metadata_json = html.escape(json.dumps(payload, ensure_ascii=False), quote=False)
        # Idempotent: strip prior markers before re-stamping (second place pass).
        clean_attrs = re.sub(
            r'\s*data-sunairum-source-table-id="[^"]*"',
            "",
            attrs,
            flags=re.I,
        )
        clean_attrs = re.sub(
            r'\s*data-sunairum-table-overflow="[^"]*"',
            "",
            clean_attrs,
            flags=re.I,
        )
        clean_attrs = re.sub(
            r'\s*data-sunairum-table-dropped-lines="[^"]*"',
            "",
            clean_attrs,
            flags=re.I,
        )
        # Absolute payload coords + parent translate double-applies geometry.
        clean_attrs = re.sub(
            r'\s*transform="[^"]*"',
            "",
            clean_attrs,
            flags=re.I,
        )
        overflow_attr = ""
        if overflow_rows or dropped_lines:
            # Declared, not hidden: too much table for its box is a content problem
            # with a content answer -- fewer rows, shorter cells, or more room.
            overflow_attr = (
                f' data-sunairum-table-overflow="{max(overflow_rows, 1)}"'
                f' data-sunairum-table-dropped-lines="{dropped_lines}"'
            )
        return (
            f'<g{clean_attrs} data-sunairum-source-table-id="{html.escape(str(source_table_id), quote=True)}"'
            f'{overflow_attr}>'
            f'<metadata type="application/json">{metadata_json}</metadata>{"".join(parts)}</g>'
        )

    if isinstance(table_payload, dict):
        # Accept evidence-shaped payloads (headers) as well as columns.
        if not isinstance(table_payload.get("columns"), list) or not table_payload.get("columns"):
            headers = table_payload.get("headers")
            if isinstance(headers, list) and headers:
                table_payload = {**table_payload, "columns": list(headers)}
        has_carrier = bool(carrier_re.search(svg))
        # Empty Executor slots carry data-pptx-replace-with="table" but no
        # metadata — treat them like a missing carrier so add_fallback fills
        # the slot instead of replace() deleting it.
        has_bound_metadata = bool(
            re.search(
                r'data-pptx-replace-with="table"[^>]*>[\s\S]*?<metadata\b',
                svg or "",
                flags=re.I,
            )
        )
        if not has_carrier or not has_bound_metadata:
            svg = add_fallback_carrier(svg, table_payload)
        else:
            # Templatizer carriers ship geometry only. Bind the slide's table
            # into their metadata before replace/strip so a real table is not
            # discarded as "unfilled".
            def bind_payload(match: re.Match) -> str:
                attrs, body = match.group(1), match.group(2)
                metadata = re.search(
                    r'(<metadata\b[^>]*>)(.*?)(</metadata>)', body, re.S | re.I,
                )
                if not metadata:
                    return match.group(0)
                try:
                    payload = json.loads(html.unescape(metadata.group(2)).strip())
                except (TypeError, json.JSONDecodeError):
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                if isinstance(table_payload.get("columns"), list):
                    payload["columns"] = table_payload["columns"]
                if isinstance(table_payload.get("rows"), list):
                    payload["rows"] = table_payload["rows"]
                columns_bound = payload.get("columns") if isinstance(payload.get("columns"), list) else []
                rows_bound = payload.get("rows") if isinstance(payload.get("rows"), list) else []
                resolved_rows, resolved_cols = _native_table_axis_counts(columns_bound, rows_bound)
                if resolved_rows:
                    payload["row_heights"] = [1] * resolved_rows
                if resolved_cols:
                    payload["column_widths"] = [1] * resolved_cols
                if table_payload.get("source_table_id"):
                    payload["source_table_id"] = table_payload["source_table_id"]
                if isinstance(table_payload.get("style"), dict):
                    payload["style"] = {
                        **(payload.get("style") if isinstance(payload.get("style"), dict) else {}),
                        **table_payload["style"],
                    }
                encoded = html.escape(json.dumps(payload, ensure_ascii=False), quote=False)
                new_body = (
                    body[: metadata.start()]
                    + f"{metadata.group(1)}{encoded}{metadata.group(3)}"
                    + body[metadata.end() :]
                )
                return f"<g{attrs}>{new_body}</g>"

            svg = carrier_re.sub(bind_payload, svg)
    return strip_unfilled_native_table_carriers(carrier_re.sub(replace, svg))


def fit_text_to_planned_zones(svg: str) -> str:
    """Wrap text against the exact ``data-pptx-bounds`` slot geometry."""
    zones = []
    for group in re.finditer(r'<g\b([^>]*data-pptx-bounds="([^"]+)"[^>]*)>.*?</g>', svg, re.S):
        values = [float(value) for value in re.findall(r'-?\d+(?:\.\d+)?', group.group(2))]
        if len(values) >= 4:
            zones.append((group.start(), group.end(), values[:4]))
    edits = []
    for match in re.finditer(r'<text\b([^>]*)>(.*?)</text>', svg, re.S):
        zone = next((item[2] for item in zones if item[0] <= match.start() <= item[1]), None)
        if zone is None:
            continue
        attrs, body = match.group(1), match.group(2)
        if "data-pptx-frame=" in attrs:
            # Certified frame layout was already resolved by fit_text_to_box with
            # the shared metrics engine. A second, padding-based capacity formula
            # disagreed on two-line slots and reintroduced false overflow findings.
            continue
        plain = re.sub(r'<[^>]+>', ' ', body)
        plain = re.sub(r'\s+', ' ', html.unescape(plain)).strip()
        if not plain:
            continue
        fs_match = re.search(r'font-size="([\d.]+)', attrs)
        fs = float(fs_match.group(1)) if fs_match else 16.0
        weight = re.search(r'font-weight="([^"]+)', attrs)
        bold = bool(weight and (weight.group(1) == "bold" or weight.group(1).isdigit() and int(weight.group(1)) >= 600))
        x_match = re.search(r'\bx="([-\d.]+)', attrs)
        x = x_match.group(1) if x_match else "0"
        from tasks.layout_geometry import usable_text_width

        family = _text_family(attrs)
        available = usable_text_width(zone[2])
        lines = _wrap_measured(plain, available, fs, family, bold, 0.0)
        line_h = _line_height_for(fs, family, bold)
        capacity = max(1, int(max(1.0, zone[3] - 20.0) // max(line_h, 1.0)))
        overflow_rows = max(0, len(lines) - capacity)
        if len(lines) == 1 and lines[0] == plain and not overflow_rows:
            if "data-sunairum-overflow-lines" in attrs:
                replacement_attrs = re.sub(r'\s+data-sunairum-overflow-lines="\d+"', '', attrs)
                edits.append((match.start(1), match.end(1), replacement_attrs))
            continue
        rebuilt = [lines[0]]
        for line in lines[1:]:
            rebuilt.append(f'<tspan x="{x}" dy="{line_h:g}">{html.escape(line, quote=False)}</tspan>')
        new_attrs = re.sub(r'\s+data-sunairum-overflow-lines="\d+"', '', attrs)
        y_match = re.search(r'\by="([-\d.]+)', new_attrs)
        minimum_y = zone[1] + fs * 0.8
        if y_match and float(y_match.group(1)) < minimum_y:
            new_attrs = re.sub(r'\by="[-\d.]+', f'y="{minimum_y:g}', new_attrs, count=1)
        # The copy stays whole. Cutting the tail with an ellipsis deleted content
        # the reader needed and the checker then reported the cut as a defect.
        if overflow_rows:
            new_attrs += f' data-sunairum-overflow-lines="{overflow_rows}"'
        edits.append((match.start(), match.end(), f"<text{new_attrs}>{''.join(rebuilt)}</text>"))
    for start, end, replacement in reversed(edits):
        svg = svg[:start] + replacement + svg[end:]
    return svg


def _slot_pairs(response: object) -> list[tuple[str, str]]:
    """Pull (selector, text) pairs out of whatever shape the model returned.

    Order is preserved so a response that identifies slots only by position can
    still be applied. Returns [] when there is genuinely nothing to apply.
    """
    def from_item(item: object) -> tuple[str, str] | None:
        if not isinstance(item, dict):
            return None
        selector = next(
            (str(item[key]) for key in _SLOT_SELECTOR_KEYS
             if item.get(key) is not None and str(item[key]).strip()),
            None,
        )
        text = next(
            (item[key] for key in _SLOT_TEXT_KEYS if isinstance(item.get(key), (str, int, float))),
            None,
        )
        if selector is None or text is None:
            return None
        return selector, str(text)

    def from_container(container: object, depth: int = 0) -> list[tuple[str, str]]:
        if isinstance(container, list):
            pairs = [pair for pair in (from_item(item) for item in container) if pair]
            if pairs:
                return pairs
            # A bare list of strings is positional: ["Title", "Body"].
            return [
                (str(index + 1), str(item))
                for index, item in enumerate(container)
                if isinstance(item, (str, int, float))
            ]
        if not isinstance(container, dict):
            return []
        single = from_item(container)
        if single:
            # One slot object, not a selector-keyed map.
            return [single]
        # The list is sometimes wrapped twice, as {"data": {"slots": [...]}}.
        if depth < 3:
            for key in _SLOT_CONTAINER_KEYS:
                if key in container:
                    pairs = from_container(container[key], depth + 1)
                    if pairs:
                        return pairs
        # {"#title": "Hello"} — the selector is the key.
        return [
            (str(key), str(value))
            for key, value in container.items()
            if isinstance(value, (str, int, float))
        ]

    return from_container(response)


def _resolve_slot_replacements(response: object, slots: "list | tuple") -> dict[str, str]:
    """Map a model response onto real slot selectors, keyed by exact selector.

    The model paraphrases identifiers as readily as it paraphrases enum values,
    so accept the compact selector, the legacy one, a case fold, a unique role,
    a 1-based index, or the slot's current text.
    """
    editable = [slot for slot in slots if slot.editable]
    if not editable:
        return {}

    by_key: dict[str, str] = {}
    role_counts: dict[str, int] = {}
    for slot in editable:
        role_counts[slot.role.strip().lower()] = role_counts.get(slot.role.strip().lower(), 0) + 1
    for position, slot in enumerate(editable, start=1):
        candidates = [
            slot.selector,
            slot.legacy_selector,
            slot.selector.lower(),
            slot.legacy_selector.lower(),
            str(position),
            slot.current_text.strip().lower(),
        ]
        # A role is only an identifier when exactly one slot claims it.
        if role_counts.get(slot.role.strip().lower()) == 1:
            candidates.append(slot.role.strip().lower())
        for candidate in candidates:
            if candidate:
                by_key.setdefault(candidate, slot.selector)

    resolved: dict[str, str] = {}
    unmatched: list[str] = []
    for raw_selector, text in _slot_pairs(response):
        key = raw_selector.strip()
        target = by_key.get(key) or by_key.get(key.lower())
        if target is None:
            unmatched.append(text)
            continue
        resolved.setdefault(target, text)

    # Every value landed somewhere unrecognizable, but the count matches the
    # editable slots exactly: the model answered in order and named the slots
    # badly. Applying positionally beats discarding the copy.
    if not resolved and len(unmatched) == len(editable):
        return {slot.selector: text for slot, text in zip(editable, unmatched)}
    return resolved


def repair_template_slots(
    svg: str,
    slide: dict,
    slide_plan: dict,
    issues: list[dict],
    language_instruction: str,
    grounding_mode: str = "none",
) -> str:
    """Request repair copy by existing selectors without allowing SVG edits."""
    from template_text_slots import analyze_template_text_slots
    from tasks.slot_geometry import attach_slot_geometry

    root = ET.fromstring(svg)
    # A repair that does not know the slot's budget writes copy that overflows again,
    # which is how the repair loop kept rediscovering the same overflow.
    slots = attach_slot_geometry(analyze_template_text_slots(root), root)
    editable_slots = [slot for slot in slots if slot.editable]
    if not editable_slots:
        # This template locks all of its text, so no copy repair is possible.
        # Failing here reported a model error for a template constraint.
        return svg
    grounded = grounding_mode == "pdf_strict"
    grounding = slide.get("grounding") if isinstance(slide.get("grounding"), dict) else {}
    instruction = (
        "You are Sunairum. Return JSON only with replacement text for existing "
        "presentation slots. Never return SVG, markup, coordinates, styles, or new "
        "selectors. Each slot states max_chars and target_chars: a replacement longer "
        "than max_chars overflows the slot and is rejected, and nothing shrinks or "
        "trims it to fit, so shorten the wording instead. "
    )
    if grounded:
        # Shortening is allowed here, and only shortening. Anything that would change
        # what the source says is rejected below rather than trusted.
        instruction += (
            "This deck is grounded in a source document. Say the same thing in fewer "
            "words: keep every number, unit and named entity exactly as given, add no "
            "fact that is not already in the text you are replacing, and never "
            "introduce a number that does not appear in the supplied evidence. "
        )
    response = call_llm_json(
        instruction + language_instruction,
        json.dumps({
            "slide": slide.get("title", ""),
            "plan": slide_plan,
            "issues": issues,
            "slots": [slot.model_payload() for slot in editable_slots],
            **(
                {"evidence": {
                    "claims": grounding.get("claims", []),
                    "metrics": grounding.get("metrics", []),
                }}
                if grounded else {}
            ),
            "output": {"slots": [{"selector": "existing selector", "text": "short replacement"}]},
        }, ensure_ascii=False),
    )
    values = _resolve_slot_replacements(response, slots)
    if grounded and values:
        values, rejected = filter_grounded_replacements(
            values,
            {slot.selector: slot.current_text for slot in slots},
            slide,
        )
        for reason in rejected:
            print(f"[qa] grounded paraphrase rejected {reason}")
    if not values:
        raise ValueError("repair slot response did not contain replacements")
    matches = list(re.finditer(r'<text\b([^>]*)>(.*?)</text>', svg, re.S))
    edits = []
    for match, slot in zip(matches, slots):
        if not slot.editable:
            continue
        value = values.get(slot.selector)
        if value is not None:
            # A repair rewords what was already there, so the provenance is inherited
            # rather than reassigned: shortening a grounded sentence does not make it
            # ours, and a repair must not be able to launder a leak into a stamp.
            inherited = provenance.source_of(match.group(1)) or (
                provenance.EVIDENCE if grounded else provenance.USER
            )
            edits.append((
                match.start(0), match.end(0),
                _render_slot_text(match, slot, value, inherited),
            ))
    for start, end, replacement in reversed(edits):
        svg = svg[:start] + replacement + svg[end:]
    return svg


def _finalize_failed_generation(storage_dir: str, error: BaseException) -> dict[str, Any] | None:
    """Guarantee a terminal status, serving any release the run did produce.

    A raised task used to leave status.json on its last *active* phase, so the
    UI sat on "Compiling PPTX…" until the stale-status watchdog eventually
    rewrote it as a generic interruption error. The generation is over either
    way: record that, and if a publishable release exists, hand it over rather
    than hiding a finished deck behind a failed step.
    """
    detail = f"{type(error).__name__}: {error}"[:500]
    try:
        from tasks.release_export import ReleaseExportError, resolve_released_pptx

        try:
            pptx_path, _sha, manifest = resolve_released_pptx(storage_dir)
        except ReleaseExportError:
            pptx_path, manifest = "", None
        if pptx_path and manifest:
            write_status(
                storage_dir,
                "done_with_issues",
                100,
                message="Presentation published with unresolved issues",
                message_key="status_done_with_issues",
            )
            print(f"[generate] published despite late failure ({detail})")
            return {
                "ok": True,
                "pptx_path": pptx_path,
                "project_id": os.path.basename(storage_dir.rstrip("/")),
                "release_manifest": manifest,
                "late_failure": detail,
            }
    except Exception as exc:  # noqa: BLE001
        print(f"[generate] release lookup after failure failed: {exc}")
    write_status(storage_dir, "error", 100, message=detail, message_key="status_generation_failed")
    return None


@shared_task(name="tasks.generate_task.run_generation")
def run_generation(topic: str, project_id: str, template_id: str | None = None, theme_color: str | None = None, user_id: str = ""):
    if not user_id:
        raise ValueError("user_id is required")
    from llm_client import llm_user_context

    loop = asyncio.get_event_loop()
    base_dir = os.path.dirname(os.path.dirname(__file__))
    storage_dir = os.path.join(base_dir, "storage", user_id, project_id)
    try:
        with llm_user_context(user_id):
            return _run_generation_body(topic, project_id, template_id, theme_color, user_id, loop)
    except Exception as error:  # noqa: BLE001
        served = _finalize_failed_generation(storage_dir, error)
        if served is not None:
            return served
        raise


def _run_generation_body(topic, project_id, template_id, theme_color, user_id, loop):
    # 1. Initialize Paths
    base_dir = os.path.dirname(os.path.dirname(__file__))
    storage_dir = os.path.join(base_dir, "storage", user_id, project_id)
    svg_dir = os.path.join(storage_dir, "svg_output")
    validation_dir = os.path.join(storage_dir, "validation")
    os.makedirs(validation_dir, exist_ok=True)
    try:
        from tasks.html_flags import (
            ensure_html_dirs,
            write_html_sot_marker,
            html_sot_enabled,
        )
    except ImportError:  # pragma: no cover
        from html_flags import (  # type: ignore
            ensure_html_dirs,
            write_html_sot_marker,
            html_sot_enabled,
        )
    html_sot = html_sot_enabled(storage_dir)
    if html_sot:
        ensure_html_dirs(storage_dir)
        write_html_sot_marker(storage_dir, enabled=True)
    run_id = uuid.uuid4().hex
    run_manifest_path = os.path.join(validation_dir, "run_manifest.json")
    run_manifest = {
        "schema_version": "sunairum.run-manifest/v1",
        "run_id": run_id,
        "project_id": project_id,
        "status": "running",
        "native_source_directory": "html_output" if html_sot else "svg_output",
        "html_sot": bool(html_sot),
        "started_at": int(time.time()),
    }

    def update_run_manifest(status: str | None = None, **fields) -> None:
        if status is not None:
            run_manifest["status"] = status
        run_manifest.update(fields)
        _write_json_atomic(run_manifest_path, run_manifest)

    update_run_manifest()
    release_manifest_path = os.path.join(validation_dir, "release_manifest.json")
    if os.path.exists(release_manifest_path):
        # Keep the last immutable artifact available while a replacement deck
        # is being authored/compiled. If every current-run writer encounters an
        # infrastructure failure, the compiler can still publish this verified
        # release with an explicit advisory instead of leaving downloads empty.
        previous_release_manifest_path = os.path.join(
            validation_dir, "previous_release_manifest.json"
        )
        temporary_previous = previous_release_manifest_path + ".tmp"
        try:
            shutil.copy2(release_manifest_path, temporary_previous)
            os.replace(temporary_previous, previous_release_manifest_path)
        finally:
            if os.path.exists(temporary_previous):
                os.remove(temporary_previous)
        os.remove(release_manifest_path)
    # A new run owns its grounding artifacts. Do not let the UI report a plan
    # or QA result produced by an earlier PDF or generation run.
    for stale_artifact in (
        "grounded_plan.json",
        "grounding_qa.json",
        "rendered_grounding_qa.json",
        "quality_review.json",
        "qa_report.json",
        "qa_gate.json",
        "qa_live.json",
    ):
        stale_path = os.path.join(validation_dir, stale_artifact)
        if os.path.exists(stale_path):
            os.remove(stale_path)
    write_status(storage_dir, "generating", 0, message="Generation started", message_key="status_started", run_id=run_id)
    # One-time wipe of leftover svg_output from prior SVG-era runs (do not recreate).
    for stale_svg in glob.glob(os.path.join(svg_dir, "slide_*.svg")):
        try:
            os.remove(stale_svg)
        except OSError as e:
            print(f"[{project_id}] could not remove stale SVG {stale_svg}: {e}")
    if os.path.isdir(svg_dir) and not os.listdir(svg_dir):
        try:
            os.rmdir(svg_dir)
        except OSError:
            pass

    # Always free_design. A gallery template_id is a design reference only
    # (palette / type / layout patterns) — never pack_fill materialization.
    design_reference_pack = str(template_id).strip() if template_id else None
    design_reference: dict = {}
    if design_reference_pack:
        from tasks.design_reference import extract_design_reference

        design_reference = extract_design_reference(design_reference_pack)
        if design_reference.get("available"):
            print(f"[design_reference] using pack {design_reference_pack!r} as style inspiration")
            update_run_manifest(
                authoring_mode="free_design",
                free_design=True,
                design_reference_pack=design_reference_pack,
                design_reference_title=design_reference.get("title"),
            )
        else:
            print(
                f"[design_reference] pack {design_reference_pack!r} missing under "
                "examples/; continuing free_design without reference"
            )
            design_reference_pack = None
            design_reference = {}
            update_run_manifest(
                authoring_mode="free_design",
                free_design=True,
                design_reference_pack=None,
                template_pack_rejected=template_id,
                template_pack_rejected_reason="not installed under servers/fastapi/examples",
            )
    else:
        print("No template_id; routing to free_design (MD + flat SVG)")
        update_run_manifest(
            authoring_mode="free_design",
            scratch_default_pack=None,
            free_design=True,
            design_reference_pack=None,
        )
    # Clear pack_fill template id so downstream never materializes shells.
    template_id = None

    # Read confirmed result.json
    result_path = os.path.join(storage_dir, "confirm_ui", "result.json")
    result_data = {}
    if os.path.exists(result_path):
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
        except Exception as e:
            print(f"Failed to read result.json: {e}")
            
    grounding_mode = result_data.get("grounding_mode")
    if grounding_mode not in {"pdf_strict", "source_grounded", "scratch"}:
        grounding_mode = (
            "pdf_strict"
            if os.path.isfile(os.path.join(storage_dir, "source.pdf"))
            and os.path.isfile(os.path.join(storage_dir, "sources", "parser_manifest.json"))
            else "scratch"
        )
    evidence_bundle = None
    if grounding_mode == "pdf_strict":
        if not os.path.isfile(os.path.join(storage_dir, "source.pdf")):
            detail = "PDF strict generation requires the immutable source.pdf artifact"
            update_run_manifest(status="failed", grounding_error=detail)
            write_status(storage_dir, "failed", 0, message=detail, run_id=run_id)
            raise RuntimeError(detail)
        from tasks.evidence_bundle import build_evidence_bundle
        from tasks.grounded_planner import load_evidence_bundle

        if not os.path.isfile(os.path.join(storage_dir, "sources", "evidence_manifest.json")):
            build_evidence_bundle(storage_dir)
        evidence_bundle = load_evidence_bundle(storage_dir)
    from tasks.image_source_policy import (
        coerce_image_source_for_grounding,
        normalize_ai_enrich_max_new,
        normalize_selected_figure_ids,
        visual_policy_prompt_block,
    )

    # pdf_strict = claim SoT + PDF visuals only; scratch may use Image-engine enrich.
    image_source = coerce_image_source_for_grounding(
        result_data.get("image_source", "both"), grounding_mode
    )
    selected_figure_ids = normalize_selected_figure_ids(result_data.get("selected_figure_ids"))
    result_data["image_source"] = image_source
    result_data["selected_figure_ids"] = selected_figure_ids
    result_data["ai_enrich_max_new"] = normalize_ai_enrich_max_new(
        result_data.get("ai_enrich_max_new"),
        grounding_mode=grounding_mode,
        image_source=image_source,
    )
    visual_policy_block = visual_policy_prompt_block(
        image_source,
        selected_figure_ids=selected_figure_ids,
        grounding_mode=grounding_mode,
    )
            
    # Default fallbacks if not present in result_data
    page_count_data = result_data.get("page_count", "6")
    if isinstance(page_count_data, dict):
        page_count = page_count_data.get("value", "6")
    else:
        page_count = str(page_count_data)
        
    try:
        page_count_int = int(re.search(r'\d+', page_count).group())
    except:
        page_count_int = 6
        
    # Gallery pack owns design tokens unless the user explicitly locked Stage-2 colors.
    user_locked_palette = str(
        (result_data.get("color") or {}).get("source") or ""
    ).casefold() == "user"
    if (
        design_reference.get("available")
        and design_reference.get("tokens")
        and not user_locked_palette
    ):
        from tasks.design_reference import apply_tokens_to_result

        result_data = apply_tokens_to_result(result_data, design_reference["tokens"])
        try:
            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump(result_data, handle, ensure_ascii=False, indent=2)
        except OSError as token_persist_error:
            print(f"[design_tokens] persist skipped: {token_persist_error}")

    color_palette = result_data.get("color", {}).get("palette", {
        "background": "#FFFFFF", "secondary_bg": "#F8FAFC",
        "primary": "#1E3A8A", "accent": "#F59E0B",
        "secondary_accent": "#3B82F6", "body_text": "#0F172A"
    })
    typography = result_data.get("typography", {
        "heading": {"primary": "Arial", "css": "sans-serif"},
        "body": {"primary": "Arial", "css": "sans-serif"}
    })
    image_notes = str(result_data.get("image_notes") or "").strip()
    directives = user_directives(result_data)
    # LLM-extract talk facts (presenter/affiliation/…) from free-text directions
    # so pdf_strict can treat them as grounding-exempt without phrase templates.
    deck_furniture = resolve_deck_furniture(result_data)
    # Persist so speaker_notes / later passes reuse the cache (no second LLM extract).
    if deck_furniture and isinstance(result_data, dict):
        result_data["deck_furniture"] = deck_furniture
        try:
            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump(result_data, handle, ensure_ascii=False, indent=2)
        except OSError as furniture_persist_error:
            print(f"[furniture] persist skipped: {furniture_persist_error}")
    furniture_block = furniture_prompt_block(deck_furniture)
    deck_context = "\n".join(
        part
        for part in (
            f"Deck topic: {topic}",
            strategy_brief(result_data),
            directives,
            furniture_block,
        )
        if part
    )
    resolved_language = result_data.get("primary_language", "auto")
    update_run_manifest(
        image_source=image_source,
        selected_figure_ids=selected_figure_ids,
        visual_policy=visual_policy_block,
        grounding_mode=grounding_mode,
        language=resolved_language,
        typography=typography,
        deck_furniture=deck_furniture,
        source_pdf_sha256=_sha256_path(os.path.join(storage_dir, "source.pdf")),
        template_id=None,
        design_reference_pack=design_reference_pack,
        evidence_manifest_sha256=(
            _sha256_path(os.path.join(storage_dir, "sources", "evidence_manifest.json"))
            if grounding_mode == "pdf_strict" else None
        ),
    )
    result_data["grounding_mode"] = grounding_mode
    result_data["source_pdf_sha256"] = run_manifest.get("source_pdf_sha256")
    result_data["evidence_manifest_sha256"] = run_manifest.get("evidence_manifest_sha256")
    if grounding_mode == "pdf_strict":
        source_artifact_hashes = {
            name: _sha256_path(os.path.join(storage_dir, "sources", name))
            for name in (
                "parser_manifest.json",
                "evidence_manifest.json",
                "source_evidence.json",
                "source_structure.json",
                "source_sections.json",
                "source_tables.json",
                "source_formulas.json",
                "source_assets.json",
            )
        }
        update_run_manifest(source_artifact_hashes=source_artifact_hashes)

    # Pack_fill removed: every generate run is free_design (± design reference).
    from tasks.free_design_pipeline import run_free_design

    return run_free_design(
        topic=topic,
        project_id=project_id,
        user_id=user_id,
        storage_dir=storage_dir,
        svg_dir=svg_dir,
        validation_dir=validation_dir,
        run_id=run_id,
        result_data=result_data,
        grounding_mode=grounding_mode,
        evidence_bundle=evidence_bundle if isinstance(evidence_bundle, dict) else None,
        color_palette=color_palette,
        typography=typography,
        image_source=image_source,
        selected_figure_ids=selected_figure_ids,
        visual_policy_block=visual_policy_block,
        page_count_int=page_count_int,
        loop=loop,
        update_run_manifest=update_run_manifest,
        write_status=write_status,
        send_ws_message=send_ws_message,
        emit_planning_status=emit_planning_status,
        gt=sys.modules[__name__],
        require_user_generate=REQUIRE_USER_GENERATE,
        design_reference_pack=design_reference_pack,
        design_reference=design_reference,
    )

    # pack_fill materialize path removed — gallery packs are design references only.

@shared_task(name="tasks.generate_task.compile_generation")
def compile_generation(project_id: str, user_id: str = ""):
    """Job B: full compile + release manifest after user Generate."""
    if not user_id:
        raise ValueError("user_id is required")
    from llm_client import llm_user_context
    from tasks import generator_agent as _gen

    with llm_user_context(user_id):
        storage_dir = os.path.join(os.environ.get("STORAGE_ROOT", "/app/storage"), user_id, project_id)
        # Free-design may have deferred notes until Generate — fill them now.
        try:
            from tasks.speaker_notes import (
                maybe_generate_speaker_notes_for_project,
                missing_note_numbers,
                notes_enabled,
            )

            if notes_enabled(storage_dir) and missing_note_numbers(storage_dir):
                maybe_generate_speaker_notes_for_project(
                    storage_dir, call_text=None, keep_existing=True
                )
        except Exception as notes_err:
            print(f"[compile] deferred notes before Generate skipped: {notes_err}")
        return _gen.finalize_compile(storage_dir, project_id=project_id)


@shared_task(name="tasks.generate_task.resume_generation")
def resume_generation(project_id: str, user_id: str = ""):
    """Continue a cancelled/failed free_design run without wiping authored SVGs."""
    if not user_id:
        raise ValueError("user_id is required")
    from llm_client import llm_user_context

    loop = asyncio.get_event_loop()
    with llm_user_context(user_id):
        return _resume_generation_body(project_id, user_id, loop)


def _resume_generation_body(project_id: str, user_id: str, loop):
    from tasks.free_design_pipeline import can_resume_free_design, run_free_design
    from tasks.design_reference import extract_design_reference
    from tasks.image_source_policy import (
        coerce_image_source_for_grounding,
        normalize_ai_enrich_max_new,
        normalize_selected_figure_ids,
        visual_policy_prompt_block,
    )

    base_dir = os.path.dirname(os.path.dirname(__file__))
    storage_root = os.environ.get("STORAGE_ROOT") or os.path.join(base_dir, "storage")
    storage_dir = os.path.join(storage_root, user_id, project_id)
    svg_dir = os.path.join(storage_dir, "svg_output")
    validation_dir = os.path.join(storage_dir, "validation")
    os.makedirs(validation_dir, exist_ok=True)

    # worker=True: API already moved status to queued before this task starts.
    eligibility = can_resume_free_design(storage_dir, worker=True)
    if not eligibility.get("ok"):
        detail = str(eligibility.get("reason") or "Project is not resumable")
        write_status(storage_dir, "error", 0, message=detail, message_key="status_resume_failed")
        raise RuntimeError(detail)

    run_manifest_path = os.path.join(validation_dir, "run_manifest.json")
    run_manifest: dict = {}
    if os.path.isfile(run_manifest_path):
        try:
            with open(run_manifest_path, encoding="utf-8") as handle:
                run_manifest = json.load(handle) or {}
        except (OSError, json.JSONDecodeError):
            run_manifest = {}
    run_id = str(run_manifest.get("run_id") or uuid.uuid4().hex)
    if not run_manifest:
        run_manifest = {
            "schema_version": "sunairum.run-manifest/v1",
            "run_id": run_id,
            "project_id": project_id,
            "started_at": int(time.time()),
        }

    def update_run_manifest(status: str | None = None, **fields) -> None:
        if status is not None:
            run_manifest["status"] = status
        run_manifest.update(fields)
        _write_json_atomic(run_manifest_path, run_manifest)

    update_run_manifest(status="running", resumed_at=int(time.time()), resume=True)
    write_status(
        storage_dir,
        "generating",
        int(eligibility.get("progress") or 40),
        message="Resuming generation from saved slides",
        message_key="status_resuming",
        run_id=run_id,
    )

    result_path = os.path.join(storage_dir, "confirm_ui", "result.json")
    result_data: dict = {}
    if os.path.isfile(result_path):
        try:
            with open(result_path, encoding="utf-8") as handle:
                result_data = json.load(handle) or {}
        except (OSError, json.JSONDecodeError) as error:
            print(f"[resume] Failed to read result.json: {error}")

    topic = str(
        result_data.get("topic")
        or run_manifest.get("topic")
        or ""
    ).strip() or "Presentation"

    design_reference_pack = run_manifest.get("design_reference_pack")
    design_reference: dict = {}
    if design_reference_pack:
        design_reference = extract_design_reference(str(design_reference_pack))
        if not design_reference.get("available"):
            design_reference_pack = None
            design_reference = {}

    grounding_mode = result_data.get("grounding_mode") or run_manifest.get("grounding_mode")
    if grounding_mode not in {"pdf_strict", "source_grounded", "scratch"}:
        grounding_mode = (
            "pdf_strict"
            if os.path.isfile(os.path.join(storage_dir, "source.pdf"))
            and os.path.isfile(os.path.join(storage_dir, "sources", "parser_manifest.json"))
            else "scratch"
        )
    evidence_bundle = None
    if grounding_mode == "pdf_strict":
        from tasks.evidence_bundle import build_evidence_bundle
        from tasks.grounded_planner import load_evidence_bundle

        if not os.path.isfile(os.path.join(storage_dir, "sources", "evidence_manifest.json")):
            build_evidence_bundle(storage_dir)
        evidence_bundle = load_evidence_bundle(storage_dir)

    image_source = coerce_image_source_for_grounding(
        result_data.get("image_source") or run_manifest.get("image_source") or "both",
        grounding_mode,
    )
    selected_figure_ids = normalize_selected_figure_ids(
        result_data.get("selected_figure_ids") or run_manifest.get("selected_figure_ids")
    )
    result_data["image_source"] = image_source
    result_data["ai_enrich_max_new"] = normalize_ai_enrich_max_new(
        result_data.get("ai_enrich_max_new", run_manifest.get("ai_enrich_max_new")),
        grounding_mode=grounding_mode,
        image_source=image_source,
    )
    visual_policy_block = visual_policy_prompt_block(
        image_source,
        selected_figure_ids=selected_figure_ids,
        grounding_mode=grounding_mode,
    )

    page_count_data = result_data.get("page_count", "6")
    if isinstance(page_count_data, dict):
        page_count = page_count_data.get("value", "6")
    else:
        page_count = str(page_count_data)
    try:
        page_count_int = int(re.search(r"\d+", str(page_count)).group())
    except Exception:
        page_count_int = int(eligibility.get("planned_slides") or 6) or 6

    theme = run_manifest.get("theme") if isinstance(run_manifest.get("theme"), dict) else {}
    color_palette = (
        theme.get("palette")
        if isinstance(theme.get("palette"), dict)
        else result_data.get("color", {}).get("palette")
    ) or {
        "background": "#FFFFFF",
        "secondary_bg": "#F8FAFC",
        "primary": "#1E3A8A",
        "accent": "#F59E0B",
        "secondary_accent": "#3B82F6",
        "body_text": "#0F172A",
    }
    typography = (
        theme.get("typography")
        if isinstance(theme.get("typography"), dict)
        else result_data.get("typography")
    ) or {
        "heading": {"primary": "Arial", "css": "sans-serif"},
        "body": {"primary": "Arial", "css": "sans-serif"},
    }

    return run_free_design(
        topic=topic,
        project_id=project_id,
        user_id=user_id,
        storage_dir=storage_dir,
        svg_dir=svg_dir,
        validation_dir=validation_dir,
        run_id=run_id,
        result_data=result_data,
        grounding_mode=grounding_mode,
        evidence_bundle=evidence_bundle if isinstance(evidence_bundle, dict) else None,
        color_palette=color_palette,
        typography=typography,
        image_source=image_source,
        selected_figure_ids=selected_figure_ids,
        visual_policy_block=visual_policy_block,
        page_count_int=page_count_int,
        loop=loop,
        update_run_manifest=update_run_manifest,
        write_status=write_status,
        send_ws_message=send_ws_message,
        emit_planning_status=emit_planning_status,
        gt=sys.modules[__name__],
        require_user_generate=REQUIRE_USER_GENERATE,
        design_reference_pack=str(design_reference_pack) if design_reference_pack else None,
        design_reference=design_reference,
        resume=True,
    )


@shared_task(name="tasks.generate_task.fix_authored_slides")
def fix_authored_slides(
    project_id: str,
    user_id: str = "",
    slide_numbers: list[int] | None = None,
):
    """User Fix: rematerialize failing slides from design_spec.md (free_design only)."""
    if not user_id:
        raise ValueError("user_id is required")
    from llm_client import llm_user_context

    with llm_user_context(user_id):
        return _fix_authored_slides_body(project_id, user_id, slide_numbers)


@shared_task(name="tasks.generate_task.regenerate_slide_with_feedback")
def regenerate_slide_with_feedback(
    project_id: str,
    user_id: str,
    slide_number: int,
    feedback: str,
):
    """Deck-editor: rematerialize one slide applying human feedback."""
    if not user_id:
        raise ValueError("user_id is required")
    from llm_client import llm_user_context

    with llm_user_context(user_id):
        return _regenerate_slide_with_feedback_body(
            project_id, user_id, int(slide_number), str(feedback or "")
        )


def _regenerate_slide_with_feedback_body(
    project_id: str,
    user_id: str,
    slide_number: int,
    feedback: str,
):
    import asyncio
    from llm_client import call_llm_text
    from tasks.design_reference import design_reference_brief
    from tasks.free_design_pipeline import rematerialize_free_design_slides

    storage_dir = os.path.join(
        os.environ.get("STORAGE_ROOT", "/app/storage"), user_id, project_id
    )
    validation_dir = os.path.join(storage_dir, "validation")
    os.makedirs(validation_dir, exist_ok=True)

    run_manifest_path = os.path.join(validation_dir, "run_manifest.json")
    run_manifest: dict = {}
    if os.path.isfile(run_manifest_path):
        try:
            with open(run_manifest_path, encoding="utf-8") as handle:
                run_manifest = json.load(handle)
        except (OSError, json.JSONDecodeError):
            run_manifest = {}

    prior_status = "awaiting_user_compile"
    status_path = os.path.join(storage_dir, "status.json")
    if os.path.isfile(status_path):
        try:
            with open(status_path, encoding="utf-8") as handle:
                prior = json.load(handle)
            if isinstance(prior, dict) and prior.get("status"):
                # Avoid leaving the project stuck in generating after regen.
                if prior.get("status") not in {
                    "queued",
                    "planning",
                    "generating",
                    "compiling",
                    "rendering",
                }:
                    prior_status = str(prior.get("status"))
        except (OSError, json.JSONDecodeError):
            pass

    theme = run_manifest.get("theme") if isinstance(run_manifest.get("theme"), dict) else {}
    palette = theme.get("palette") if isinstance(theme.get("palette"), dict) else {}
    ref_brief = design_reference_brief(run_manifest.get("design_reference_pack"))

    write_status(
        storage_dir,
        "generating",
        45,
        slide_number,
        slide_number,
        message=f"Regenerating slide {slide_number} from feedback",
        message_key="status_generating_slide",
        title=f"Slide {slide_number}",
    )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            send_ws_message(
                project_id,
                {
                    "status_key": "status_generating_slide",
                    "progress": 45,
                    "current": slide_number,
                    "total": slide_number,
                    "slide": slide_number,
                    "title": f"Slide {slide_number}",
                },
            )
        )
        rebuild = rematerialize_free_design_slides(
            storage_dir,
            [slide_number],
            color_palette=palette,
            call_text=call_llm_text,
            gt=sys.modules[__name__],
            design_reference_brief=ref_brief,
            slide_feedback={slide_number: feedback},
            project_id=project_id,
            write_status=write_status,
            send_ws_message=send_ws_message,
            loop=loop,
        )
    finally:
        try:
            loop.close()
        except Exception:
            pass

    rel_prefix = os.path.relpath(
        storage_dir, os.environ.get("STORAGE_ROOT", "/app/storage")
    )
    from tasks.slide_artifacts import regenerate_slide_urls

    urls = regenerate_slide_urls(
        storage_dir=storage_dir,
        rel_prefix=rel_prefix,
        slide_number=int(slide_number),
    )
    preview_url = urls.get("preview_url")
    html_url = urls.get("html_url")
    scene_url = urls.get("scene_url")
    result = {
        "ok": True,
        "slide": int(slide_number),
        "preview_url": preview_url,
        "html_url": html_url,
        "scene_url": scene_url,
        "rebuilt": rebuild.get("rebuilt") or [],
        "ts": int(time.time()),
    }
    _write_json_atomic(
        os.path.join(validation_dir, "regenerate_slide_result.json"), result
    )
    write_status(
        storage_dir,
        prior_status if prior_status not in {"error", "failed", "cancelled"} else "done",
        100,
        slide_number,
        slide_number,
        message=f"Regenerated slide {slide_number}",
        message_key="status_regenerate_slide_done",
    )
    try:
        loop2 = asyncio.new_event_loop()
        loop2.run_until_complete(
            send_ws_message(
                project_id,
                {
                    "status_key": "status_regenerate_slide_done",
                    "progress": 100,
                    "slide": slide_number,
                    "preview_url": preview_url,
                    "html_url": html_url,
                    "scene_url": scene_url,
                    "ok": True,
                },
            )
        )
        loop2.close()
    except Exception:
        pass
    return result


def _fix_authored_slides_body(project_id, user_id, slide_numbers):
    storage_dir = os.path.join(os.environ.get("STORAGE_ROOT", "/app/storage"), user_id, project_id)
    validation_dir = os.path.join(storage_dir, "validation")
    svg_dir = os.path.join(storage_dir, "svg_output")
    from tasks import strategist_agent as _strategist
    from tasks.design_reference import design_reference_brief
    from tasks.free_design_pipeline import rematerialize_free_design_slides

    run_manifest_path = os.path.join(validation_dir, "run_manifest.json")
    run_manifest: dict = {}
    if os.path.isfile(run_manifest_path):
        try:
            with open(run_manifest_path, encoding="utf-8") as handle:
                run_manifest = json.load(handle)
        except (OSError, json.JSONDecodeError):
            run_manifest = {}

    if not slide_numbers:
        design_path = os.path.join(storage_dir, "design_spec.md")
        if os.path.isfile(design_path):
            with open(design_path, encoding="utf-8") as handle:
                slide_numbers = [
                    int(item["slide"])
                    for item in _strategist.parse_section_ix_slides(handle.read())
                ]

    write_status(
        storage_dir, "generating", 82,
        message="Rematerializing slides from design_spec.md",
        message_key="status_fixing_slides",
    )

    theme = run_manifest.get("theme") if isinstance(run_manifest.get("theme"), dict) else {}
    palette = theme.get("palette") if isinstance(theme.get("palette"), dict) else {}
    ref_brief = design_reference_brief(run_manifest.get("design_reference_pack"))

    rebuild = rematerialize_free_design_slides(
        storage_dir,
        list(slide_numbers or []),
        color_palette=palette,
        gt=sys.modules[__name__],
        design_reference_brief=ref_brief,
    )
    _write_json_atomic(os.path.join(validation_dir, "fix_request.json"), {
        "schema_version": "sunairum.fix-request/v1",
        "slides": list(slide_numbers or []),
        "rebuild": rebuild,
        "ts": int(time.time()),
    })

    num_slides = 0
    try:
        from tasks.slide_artifacts import existing_slide_numbers as _existing_nums

        num_slides = len(_existing_nums(storage_dir))
    except Exception:
        num_slides = (
            len(glob.glob(os.path.join(svg_dir, "slide_*.svg")))
            if os.path.isdir(svg_dir)
            else 0
        )
    if REQUIRE_USER_GENERATE:
        write_status(
            storage_dir,
            "awaiting_user_compile",
            84,
            num_slides,
            num_slides,
            message="Fix rematerialized slides; review and Generate when ready",
            message_key="status_awaiting_user_compile",
        )
        return {
            "status": "awaiting_user_compile",
            "project_id": project_id,
            "slides": list(slide_numbers or []),
            "rebuilt": rebuild.get("rebuilt") or [],
        }
    return compile_generation(project_id, user_id=user_id)
