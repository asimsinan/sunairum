"""Free-design generation path (empty template_id): MD SoT → Constrained HTML → deckhtml PPTX.

Orthogonal to grounding: pdf_strict uses Strategist §IX → grounded_plan bridge;
scratch skips PDF validators. Never routes through pack materialize / Presenton.
Product path is HTML SoT only (html_output/ → preview/ → deckhtml PPTX); do not write svg_output/ or ir/.
"""

from __future__ import annotations

import asyncio
import glob
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from tasks import strategist_agent
from tasks.authoring_budget import AuthoringBudget


def _commit_slide_svg_or_quarantine(path: str, svg: str, reason: str = "") -> tuple[str, list[str]]:
    """Retired: freehand SVG commit path removed in zero-SVG cutover."""
    del path, svg, reason
    raise RuntimeError("retired")

# A Scene v2 slide is designed in a single constrained LLM pass. Browser/layout
# recovery is deterministic and local; it must never multiply API calls.
_MAX_EXECUTOR_PAINTS_PER_SLIDE = 1
_PER_SLIDE_AUTHOR_CALLS = 1
# Strategist and planning calls sit outside per-slide visual authorship.
_AUTHORING_HEADROOM = 12


def _executor_paint_budget(slide: dict[str, Any]) -> int:
    """Remaining Executor paint slots for this slide (shared across QA paths)."""
    used = int(slide.get("_executor_paints") or 0)
    return max(0, _MAX_EXECUTOR_PAINTS_PER_SLIDE - used)


def _record_executor_paint(slide: dict[str, Any]) -> None:
    slide["_executor_paints"] = int(slide.get("_executor_paints") or 0) + 1
    used = int(slide["_executor_paints"])
    print(
        f"[free_design] P{int(slide.get('slide') or 0):02d} "
        f"paints={used}/{_MAX_EXECUTOR_PAINTS_PER_SLIDE}"
    )


class LlmAuthoringError(RuntimeError):
    """LLM unreachable / empty — stop generation; leave deck resumable."""


EXECUTOR_SYSTEM = """You are Sunairum's Executor for free-design slides.

Author ONE complete Constrained HTML page for the requested page
(CSS canvas: width 1280px; height 720px — do not author SVG/viewBox).
Return ONLY the HTML (no markdown fences, no commentary).
Write html_output/ (pipeline materializes ir/ + preview/); never write svg_output/.

## Hard
- Flat export: no data-pptx-placeholder/master/layout/carrier; no Master/Layout attrs.
- Forbidden: <script>, <iframe>, inline event handlers; keep markup Intent-safe.
- Escape reserved characters. Use Unicode, not HTML entities for typography.
- Geometry via CSS (left/top/width/height or flex); no SVG root / viewBox authoring.
- Never paint evidence IDs (ev-page-…) or planner codes (P03 / RESULTS eyebrows).
- Never paint footer project tags, topic taglines, or HERO* / "HERO · …" chrome.
  Never paint page numbers (not P02, 03, 2/8). Pipeline injects one bottom-right n/N footer.
- Never invent table cell text or chart series values.
- When a Figure/Table/Chart/Formula is bound: emit an EMPTY semantic host only.
  Intent fills hosts; do not draw over them; do not invent <img> for figures.
- Prefer simple rect/line motifs in HTML/CSS; avoid huge path blobs.

## Formula don'ts
- Never paint the equation as free text; never emit \\( \\) \\[ \\] or $…$.
- Leave formula host empty (pipeline injects PNG + legend).
- Do not draw a thick rule through the subtitle line under the title.
- Outside host: meaning chrome that explains what the equation does (not legend restatement).

## Motif / table / labels
- No empty chrome plates; every tint/white callout must contain its label (≥12px inset).
- No overlapping labels (same baseline pile-up).
- Table-bound pages: paint left takeaway only; never freehand table grids/highlight bars.
- Motif/icon must encode the paired claim (same card / pair_id); no orphan décor.
- host_void / motif / figure / table zones are NO-TEXT for body copy.
- role=label / role=callout: short labels only (≤6 words); never paragraphs there.

## Defaults (may override when this page's Layout / rhythm asks)
- Honor Locked layout plan regions; paint inside regions only.
- One visual job; vary vs prior diary; paraphrase §IX without dropping claims.
- Title/hero/closing = FULL-BLEED event pages (see Title/Closing HARD in user prompt).
- Do not paint page numbers; pipeline injects a single n/N footer.
- Text ≥12px inset; multi-line body pitch ≥1.35×font-size; peer cards share title band.
- Card anatomy: title top → motif mid → body bottom.
- Labels outside motif ink; Fill Contract: vivid primary/accent + accent_tint.
- Obey compact Craft + Art direction in the user prompt.
"""


def _extract_svg(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:svg|xml)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
    match = re.search(r"(<svg\b[\s\S]*?</svg>)", raw, re.I)
    return match.group(1).strip() if match else raw


# Content-slide titles use the full header band (x=60 → ~1240), not a card column.
_CONTENT_TITLE_MAX_PX = 1180.0
# Title plates with a right visual panel keep a narrower left column.
_TITLE_PLATE_MAX_PX = 700.0
_CONTENT_TITLE_X = 60.0
_TITLE_CHAR_EM = 0.58  # Georgia bold tends wider than Arial averages
_CONTENT_TITLE_MAX_LINES = 3


def _estimate_text_width(text: str, font_size: float) -> float:
    return max(0.0, len(text)) * font_size * _TITLE_CHAR_EM


def _soft_title_break(text: str) -> tuple[str, str] | None:
    """Split near the midpoint on a space/dash when two lines are required."""
    cleaned = " ".join(text.split())
    if len(cleaned) < 36:
        return None
    mid = len(cleaned) // 2
    candidates: list[int] = []
    for idx, ch in enumerate(cleaned):
        if ch in {" ", "—", "–", "-"} and 16 <= idx <= len(cleaned) - 12:
            candidates.append(idx)
    if not candidates:
        return None
    best = min(candidates, key=lambda i: abs(i - mid))
    left = cleaned[:best].rstrip(" —–-")
    right = cleaned[best:].lstrip(" —–-")
    if not left or not right:
        return None
    return left, right


def _pack_title_lines(
    text: str,
    font_size: float,
    *,
    max_width: float = _CONTENT_TITLE_MAX_PX,
    max_lines: int = _CONTENT_TITLE_MAX_LINES,
) -> list[str]:
    """Greedy word-wrap onto the full title band (1–max_lines rows)."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    if _estimate_text_width(cleaned, font_size) <= max_width:
        return [cleaned]
    words = cleaned.split(" ")
    lines: list[str] = []
    current: list[str] = []
    for index, word in enumerate(words):
        trial = " ".join(current + [word]) if current else word
        if current and _estimate_text_width(trial, font_size) > max_width:
            lines.append(" ".join(current))
            # Last allowed line absorbs the remainder so we never orphan a word.
            if len(lines) >= max_lines - 1:
                lines.append(" ".join(words[index:]))
                current = []
                break
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    # Prefer a balanced 2-line split when greedy left a tiny orphan last line
    # (e.g. "... Lead on" / "Quality").
    if len(lines) >= 2 and len(lines[-1].split()) <= 2:
        soft = _soft_title_break(cleaned)
        if soft and all(
            _estimate_text_width(part, font_size) <= max_width for part in soft
        ):
            return [soft[0], soft[1]]
    return lines


def dedupe_stacked_title_texts(svg: str, preferred_title: str = "") -> str:
    """Keep one title-band headline; drop competing / contained duplicates.

    Title plates often ship a short display title (fs=60) plus the long paper
    title (fs=34). Containment must drop the loser even when length ratio < 0.9.
    """
    if not svg:
        return svg
    texts = list(
        re.finditer(
            r"(<text\b([^>]*)>)([\s\S]*?)(</text>)",
            svg,
            flags=re.I,
        )
    )
    if len(texts) < 2:
        return svg

    def _plain(body: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip().casefold()

    def _font_size(attrs: str) -> float:
        match = re.search(r'\bfont-size="([\d.]+)"', attrs or "", flags=re.I)
        try:
            return float(match.group(1)) if match else 0.0
        except ValueError:
            return 0.0

    def _y(attrs: str) -> float:
        match = re.search(r'\by="([\d.]+)"', attrs or "", flags=re.I)
        try:
            return float(match.group(1)) if match else 9999.0
        except ValueError:
            return 9999.0

    candidates = []
    for match in texts:
        attrs, body = match.group(2), match.group(3)
        plain = _plain(body)
        fs = _font_size(attrs)
        y = _y(attrs)
        if fs < 26 or y > 320 or len(plain) < 12:
            continue
        candidates.append((fs, y, plain, match))
    if len(candidates) < 2:
        return svg

    preferred = re.sub(r"\s+", " ", str(preferred_title or "")).strip().casefold()

    def _primary_key(item: tuple) -> tuple:
        fs, y, plain, _match = item
        prefer = 0
        if preferred and (plain == preferred or preferred in plain or plain in preferred):
            prefer = 1
        return (prefer, fs, -y)

    candidates.sort(key=_primary_key, reverse=True)
    primary_plain = candidates[0][2]
    drop_spans: list[tuple[int, int]] = []
    for fs, _ypos, plain, match in candidates[1:]:
        if plain == primary_plain:
            drop_spans.append((match.start(), match.end()))
            continue
        shorter, longer = (
            (plain, primary_plain) if len(plain) <= len(primary_plain) else (primary_plain, plain)
        )
        # Contained titles (short ⊂ long) are competing headlines — drop the non-primary.
        if len(shorter) >= 20 and shorter in longer:
            drop_spans.append((match.start(), match.end()))
            continue
        # Shared long token run (≥20 chars) also counts as a competing headline.
        shared = False
        if len(shorter) >= 20:
            for size in range(min(40, len(shorter)), 19, -1):
                if any(shorter[i : i + size] in longer for i in range(0, len(shorter) - size + 1)):
                    shared = True
                    break
        if shared:
            drop_spans.append((match.start(), match.end()))
    if not drop_spans:
        return svg
    out = svg
    for start, end in sorted(drop_spans, reverse=True):
        out = out[:start] + out[end:]
    return out


def clamp_title_headline_to_canvas(svg: str) -> str:
    """Shrink/wrap a centered title-band headline that bleeds past x∈[48,1232]."""
    if not svg:
        return svg
    match = re.search(
        r"(<text\b(?=[^>]*\bfont-size=\"(\d+(?:\.\d+)?)\")(?=[^>]*\by=\"(\d+(?:\.\d+)?)\")[^>]*>)"
        r"([\s\S]*?)</text>",
        svg,
        flags=re.I,
    )
    if not match:
        return svg
    font_size = float(match.group(2))
    y_pos = float(match.group(3))
    if font_size < 26 or y_pos > 320:
        return svg
    attrs_open = match.group(1)
    inner = match.group(4)
    tspan_bits = re.findall(r"<tspan\b[^>]*>([\s\S]*?)</tspan>", inner, flags=re.I)
    if tspan_bits:
        painted = " ".join(
            " ".join(re.sub(r"\s+", " ", bit).split()) for bit in tspan_bits if bit.strip()
        )
    else:
        painted = " ".join(re.sub(r"<[^>]+>", "", inner).split())
    if not painted:
        return svg
    anchor_middle = bool(re.search(r'text-anchor="middle"', attrs_open, flags=re.I))
    x_match = re.search(r'\bx="([-\d.]+)"', attrs_open)
    try:
        x_pos = float(x_match.group(1)) if x_match else 640.0
    except ValueError:
        x_pos = 640.0
    fs = font_size
    width = _estimate_text_width(painted, fs)
    left = x_pos - width / 2 if anchor_middle else x_pos
    right = x_pos + width / 2 if anchor_middle else x_pos + width
    if left >= 48 and right <= 1232:
        return svg
    while fs > 22 and (
        (x_pos - _estimate_text_width(painted, fs) / 2 if anchor_middle else x_pos) < 48
        or (x_pos + _estimate_text_width(painted, fs) / 2 if anchor_middle else x_pos + _estimate_text_width(painted, fs))
        > 1232
    ):
        fs -= 1.0
    new_open = attrs_open
    if abs(fs - font_size) > 0.01:
        new_open = re.sub(
            r'\bfont-size="[^"]*"',
            f'font-size="{fs:g}"',
            new_open,
            count=1,
        )
    # Prefer wrapping to two lines over ultra-small type when still overflowing.
    if _estimate_text_width(painted, fs) > (1184 if not anchor_middle else 1100):
        split = _soft_title_break(painted)
        if split:
            left_t, right_t = split
            line_gap = max(34.0, round(fs * 1.12))
            ax = x_pos if anchor_middle else _CONTENT_TITLE_X
            new_inner = (
                f'<tspan x="{ax:g}" dy="0">{left_t}</tspan>'
                f'<tspan x="{ax:g}" dy="{line_gap:g}">{right_t}</tspan>'
            )
            return svg[: match.start()] + f"{new_open}{new_inner}</text>" + svg[match.end() :]
    return svg[: match.start()] + f"{new_open}{inner}</text>" + svg[match.end() :]


def _title_band_text_nodes(svg: str) -> list[re.Match[str]]:
    """Large headlines in the cover title band (intentional wrap = multiple nodes)."""
    nodes: list[re.Match[str]] = []
    for match in re.finditer(
        r"(<text\b(?=[^>]*\bfont-size=\"(\d+(?:\.\d+)?)\")(?=[^>]*\by=\"(\d+(?:\.\d+)?)\")[^>]*>)"
        r"([\s\S]*?)</text>",
        svg,
        flags=re.I,
    ):
        try:
            fs = float(match.group(2))
            y_pos = float(match.group(3))
        except ValueError:
            continue
        if fs < 26 or y_pos < 140 or y_pos > 420:
            continue
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(4))).strip()
        if len(plain) < 4:
            continue
        nodes.append(match)
    return nodes


def _looks_like_truncated_title(painted: str, full: str) -> bool:
    """True only for mid-word / ellipsis clips — not intentional short display titles."""
    painted_cf = painted.casefold().rstrip()
    full_cf = full.casefold().rstrip()
    if not painted_cf or not full_cf or painted_cf == full_cf:
        return False
    if painted_cf.endswith(("…", "...")):
        stem = painted_cf.rstrip(".…").rstrip()
        return bool(stem) and full_cf.startswith(stem)
    # Strict prefix that ends mid-word (e.g. "…Routi" → "Routing").
    if full_cf.startswith(painted_cf) and len(full_cf) > len(painted_cf):
        next_ch = full_cf[len(painted_cf)]
        if next_ch not in {" ", "-", "—", "–"}:
            return True
        # Prefix ending on a space but missing most of the title (<55%).
        if next_ch == " " and len(painted_cf) < 0.55 * len(full_cf):
            return True
    return False


def resolve_title_plate_rule_clearance(svg: str) -> str:
    """Keep cover underline / accent bar from trimming title glyphs."""
    if not svg:
        return svg
    nodes = _title_band_text_nodes(svg)
    if not nodes:
        return svg

    last_baseline = 0.0
    max_fs = 0.0
    min_title_x = 1e9
    for match in nodes:
        fs = float(match.group(2))
        y_pos = float(match.group(3))
        baseline, _lines = _title_last_baseline(y_pos, fs, match.group(4))
        last_baseline = max(last_baseline, baseline)
        max_fs = max(max_fs, fs)
        x_m = re.search(r'\bx="([-\d.]+)"', match.group(1))
        if x_m:
            min_title_x = min(min_title_x, float(x_m.group(1)))

    out = svg
    # Push horizontal rules clear of serif descenders (g/y/p); browsers vary.
    min_rule_y = last_baseline + max(40.0, max_fs * 0.7) + 8.0
    line_edits: list[tuple[int, int, str, float]] = []
    for match in re.finditer(r"<line\b([^>]*)/?>", out, flags=re.I):
        attrs = match.group(1)
        try:
            x1 = float(re.search(r'\bx1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y1 = float(re.search(r'\by1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            x2 = float(re.search(r'\bx2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y2 = float(re.search(r'\by2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        # Accent stubs (~orange) can be short; still treat as title underlines.
        if abs(y2 - y1) > 1.5 or abs(x2 - x1) < 80:
            continue
        if y1 < last_baseline - 8 or y1 > last_baseline + 100:
            continue
        if min_title_x < 1e8 and x2 < min_title_x - 20:
            continue
        if y1 + 0.5 >= min_rule_y:
            continue
        replaced = re.sub(r'\by1="[^"]*"', f'y1="{min_rule_y:g}"', match.group(0), count=1)
        replaced = re.sub(r'\by2="[^"]*"', f'y2="{min_rule_y:g}"', replaced, count=1)
        line_edits.append((match.start(), match.end(), replaced, min_rule_y - y1))
    max_delta = max((d for _a, _b, _c, d in line_edits), default=0.0)
    for start, end, replaced, _delta in sorted(line_edits, key=lambda e: -e[0]):
        out = out[:start] + replaced + out[end:]
    # Keep bylines below the moved underline.
    if max_delta > 0.5:
        text_edits: list[tuple[int, int, str]] = []
        for tmatch in re.finditer(
            r"(<text\b(?=[^>]*\by=\"(\d+(?:\.\d+)?)\")(?=[^>]*\bfont-size=\"(\d+(?:\.\d+)?)\")[^>]*>)",
            out,
            flags=re.I,
        ):
            ty = float(tmatch.group(2))
            tfs = float(tmatch.group(3))
            if tfs >= 26 or ty < last_baseline or ty > last_baseline + 140:
                continue
            new_y = ty + max_delta
            new_open = re.sub(r'\by="[^"]*"', f'y="{new_y:g}"', tmatch.group(1), count=1)
            text_edits.append((tmatch.start(), tmatch.end(), new_open))
        for start, end, new_open in sorted(text_edits, key=lambda e: -e[0]):
            out = out[:start] + new_open + out[end:]

    # Nudge title text right of a left accent bar that would shear glyphs.
    if min_title_x < 1e8:
        for match in re.finditer(r"<rect\b([^>]*)/?>", out, flags=re.I):
            attrs = match.group(1)
            try:
                rx = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                ry = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                rw = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
                rh = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            except (AttributeError, TypeError, ValueError):
                continue
            if rw > 24 or rh < 80 or rx > min_title_x:
                continue
            # Bar overlaps the title band vertically.
            if ry + rh < last_baseline - max_fs or ry > last_baseline + 20:
                continue
            need_x = rx + rw + 18.0
            if min_title_x + 0.5 >= need_x:
                continue
            shift = need_x - min_title_x
            for tmatch in reversed(_title_band_text_nodes(out)):
                open_tag = tmatch.group(1)
                x_m = re.search(r'\bx="([-\d.]+)"', open_tag)
                if not x_m:
                    continue
                new_x = float(x_m.group(1)) + shift
                new_open = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', open_tag, count=1)
                new_body = re.sub(r'\bx="[^"]*"', f'x="{new_x:g}"', tmatch.group(4))
                out = (
                    out[: tmatch.start()]
                    + f"{new_open}{new_body}</text>"
                    + out[tmatch.end() :]
                )
            break

    return out




def _count_text_overlaps_in_svg(svg: str) -> int:
    """In-memory text-overlap count via deck_qa geometry (report-only)."""
    if not svg:
        return 0
    try:
        from tasks.deck_qa import _svg_text_records, _text_overlap_issues
    except ImportError:  # pragma: no cover
        from deck_qa import _svg_text_records, _text_overlap_issues  # type: ignore
    records = _svg_text_records(svg)
    return len(_text_overlap_issues(0, records))


def _dump_broken_svg(storage_dir: str, number: int, svg: str, reason: str) -> None:
    try:
        dump_dir = os.path.join(storage_dir, "validation", "broken_svg")
        os.makedirs(dump_dir, exist_ok=True)
        dump_path = os.path.join(dump_dir, f"slide_{int(number):02d}.broken.svg")
        with open(dump_path, "w", encoding="utf-8") as dump:
            dump.write(f"<!-- {reason} -->\n")
            dump.write(svg if isinstance(svg, str) else "")
        print(f"[free_design] wrote broken SVG dump {dump_path}")
    except Exception:
        pass



def _reject_nested_mathjax_hosts(svg: str) -> list[str]:
    """Fail closed when formula hosts still nest MathJax <svg>/<use>."""
    errors: list[str] = []
    if re.search(
        r'data-sunairum-formula-host[^>]*>[\s\S]*?<svg\b',
        svg or "",
        flags=re.I,
    ):
        errors.append("nested_mathjax_svg: formula host must use PNG/flat paths")
    if re.search(
        r'data-sunairum-formula-(?:host|math)[^>]*>[\s\S]*?<use\b',
        svg or "",
        flags=re.I,
    ):
        errors.append("mathjax_use: expand or rasterize before export")
    return errors


def _gate_svg_for_export(svg: str, *, context: str = "") -> tuple[str, list[str]]:
    """Return (svg, errors). errors empty when export-legal."""
    return (svg or "", [])

def _write_gated_svg(path: str, svg: str, *, context: str = "") -> str:
    """Retired: freehand SVG write gate removed in zero-SVG cutover."""
    del path, svg, context
    raise RuntimeError("retired")

def _svg_escape_text(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _content_bullet_tokens(text: str) -> list[str]:
    return [
        tok
        for tok in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?|×|[+\-]?\d+(?:\.\d+)?%?", text.casefold())
        if len(tok) >= 2
    ]


def _normalize_metric_key(text: str) -> str:
    """Collapse whitespace and unify ×/x so 3.05× matches painted 3.05 x."""
    return re.sub(r"\s+", "", (text or "").casefold()).replace("×", "x")


def _content_bullet_already_painted(plain: str, bullet: str) -> bool:
    """True when distinctive metrics/tokens from the bullet already appear on-slide.

    Shared stubs like ``n`` / ``200`` must not mark a different reduction as painted.
    """
    compact = _normalize_metric_key(plain)
    metrics = re.findall(
        r"\d+(?:\.\d+)?\s*[×x]|[+\−\-]?\d+(?:\.\d+)?\s*%",
        bullet,
        flags=re.I,
    )
    if metrics:
        return any(_normalize_metric_key(m) in compact for m in metrics)
    tokens = [
        tok
        for tok in _content_bullet_tokens(bullet)
        if len(tok) >= 3 and tok not in {"and", "the", "for", "with", "from"}
    ]
    if not tokens:
        return False
    hits = sum(1 for tok in tokens if tok in plain)
    return hits >= max(2, int(0.7 * len(tokens)))


def _right_column_fill_items(
    svg: str,
    pack: str,
    slide: dict[str, Any] | None,
) -> list[str]:
    """Choose paintable right-column lines from §IX Content not already on slide."""
    slide = slide or {}
    bullets = _ix_content_bullets_from_pack(pack)
    if not bullets:
        content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
        body = str(content.get("BODY") or "").strip()
        bullets = [
            str(card.get("title") or "").strip()
            for card in _bullet_cards_from_prose(body)
            if card.get("title")
        ]
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", svg or "")).casefold()
    missing: list[str] = []
    for bullet in bullets:
        if not _content_bullet_already_painted(plain, bullet):
            missing.append(bullet.strip())
    items = missing
    if len(items) < 2 and len(bullets) >= 2:
        # Right region still needs a panel even when metrics were dumped left —
        # use the second-half / trade-off slice (Layout asked for it).
        for bullet in bullets[len(bullets) // 2 :]:
            text = bullet.strip()
            if text and text not in items:
                items.append(text)
            if len(items) >= 4:
                break
    if not items:
        core = str(slide.get("core_message") or "").strip()
        if core:
            items = [core]
    # Drop table/figure bindings, section headers, and ultra-short labels.
    cleaned: list[str] = []
    for item in items:
        low = item.casefold().strip()
        if low.startswith("table:") or low.startswith("figure:"):
            continue
        if len(item.strip()) < 8:
            continue
        if re.search(r"(?i)\bincludes?:?\s*$", item.strip()):
            continue
        if item.rstrip().endswith(":") and len(item) < 56:
            continue
        cleaned.append(item.strip()[:160])
    return cleaned[:4]


def normalize_free_design_slide_svg(
    svg: str,
    *,
    role: str = "content",
    layout_plan: dict[str, Any] | None = None,
    full_title: str = "",
) -> str:
    """Retired: freehand SVG normalize removed in zero-SVG cutover."""
    del svg, role, layout_plan, full_title
    raise RuntimeError("retired")


def repair_content_slide_layout(
    svg: str,
    *,
    pack: str = "",
    slide: dict[str, Any] | None = None,
    color_palette: dict[str, str] | None = None,
    role: str = "content",
) -> str:
    """Retired: freehand SVG layout repair removed in zero-SVG cutover."""
    del svg, pack, slide, color_palette, role
    raise RuntimeError("retired")


def apply_free_design_layout_qa(
    svg_dir: str,
    slides: list[dict[str, Any]],
    *,
    deck_furniture: dict[str, str] | None = None,
    source_identity: dict[str, str] | None = None,
    design_spec_md: str = "",
    color_palette: dict[str, str] | None = None,
    additional_instructions: str = "",
) -> dict[str, Any]:
    """Retired no-op: layout QA lives on IR/html_qa under zero-SVG."""
    del (
        svg_dir,
        slides,
        deck_furniture,
        source_identity,
        design_spec_md,
        color_palette,
        additional_instructions,
    )
    return {"repaired": [], "skipped": [], "errors": [], "skipped_html_sot": True}


def fit_title_plate_headline(svg: str, full_title: str = "") -> str:
    """Restore and wrap a title-plate headline so it is not mid-word clipped.

    Cover layouts often reserve ~700px for the title beside a right panel. Models
    sometimes emit a truncated string ("…Routi") instead of wrapping. Prefer the
    planner's full title only when the painted text is clearly a mid-word clip —
    never yank an intentional short display title onto x=60 through the accent bar.
    """
    if not svg:
        return svg
    band = _title_band_text_nodes(svg)
    if not band:
        return svg
    # Join intentional wrap lines before deciding anything is "clipped".
    parts: list[str] = []
    for match in band:
        inner = match.group(4)
        tspan_bits = re.findall(r"<tspan\b[^>]*>([\s\S]*?)</tspan>", inner, flags=re.I)
        if tspan_bits:
            parts.extend(
                " ".join(re.sub(r"\s+", " ", bit).split())
                for bit in tspan_bits
                if bit.strip()
            )
        else:
            plain = " ".join(re.sub(r"<[^>]+>", "", inner).split())
            if plain:
                parts.append(plain)
    painted = " ".join(parts)
    if not painted:
        return svg

    match = band[0]
    font_size = float(match.group(2))
    y_pos = float(match.group(3))
    x_match = re.search(r'\bx="([-\d.]+)"', match.group(1))
    try:
        title_x = float(x_match.group(1)) if x_match else 112.0
    except ValueError:
        title_x = 112.0
    # Keep cover titles clear of the left accent bar; never force content x=60.
    title_x = max(title_x, 96.0)

    title = painted
    full = " ".join(str(full_title or "").split())
    if full and _looks_like_truncated_title(painted, full):
        title = full

    # Per-line column check — multi-line wraps that still overrun the sidebar
    # must re-fit (do not early-return just because tspans/band count ≥ 2).
    line_bits = [p for p in parts if p] or ([title] if title else [])
    per_line_ok = all(
        _estimate_text_width(ln, font_size) <= _TITLE_PLATE_MAX_PX for ln in line_bits
    )
    if title == painted and per_line_ok:
        return resolve_title_plate_rule_clearance(svg)

    fs = font_size
    while fs > 24 and _estimate_text_width(title, fs) > _TITLE_PLATE_MAX_PX * 1.85:
        # Too long even for two lines at this size — shrink first.
        fs -= 1.0

    open_tag = match.group(1)
    if _estimate_text_width(title, fs) <= _TITLE_PLATE_MAX_PX:
        new_inner = title
    else:
        split = _soft_title_break(title)
        if not split:
            while fs > 22 and _estimate_text_width(title, fs) > _TITLE_PLATE_MAX_PX:
                fs -= 1.0
            new_inner = title
        else:
            left, right = split
            while fs > 22 and (
                _estimate_text_width(left, fs) > _TITLE_PLATE_MAX_PX
                or _estimate_text_width(right, fs) > _TITLE_PLATE_MAX_PX
            ):
                fs -= 1.0
            line_gap = max(34.0, round(fs * 1.2))
            new_inner = (
                f'<tspan x="{title_x:g}" dy="0">{left}</tspan>'
                f'<tspan x="{title_x:g}" dy="{line_gap:g}">{right}</tspan>'
            )

    new_open = open_tag
    if abs(fs - font_size) > 0.01:
        new_open = re.sub(
            r'\bfont-size="[^"]*"',
            f'font-size="{fs:g}"',
            new_open,
            count=1,
        )
    if re.search(r'\bx="', new_open):
        new_open = re.sub(r'\bx="[^"]*"', f'x="{title_x:g}"', new_open, count=1)

    # Consolidate sibling wrap fragments whenever we rewrite the headline.
    out = svg
    if len(band) > 1:
        for sibling in reversed(band[1:]):
            out = out[: sibling.start()] + out[sibling.end() :]
        band = _title_band_text_nodes(out)
        if not band:
            return resolve_title_plate_rule_clearance(out)
        match = band[0]
        open_tag = match.group(1)
        new_open = open_tag
        if abs(fs - float(match.group(2))) > 0.01:
            new_open = re.sub(
                r'\bfont-size="[^"]*"',
                f'font-size="{fs:g}"',
                new_open,
                count=1,
            )
        if re.search(r'\bx="', new_open):
            new_open = re.sub(r'\bx="[^"]*"', f'x="{title_x:g}"', new_open, count=1)

    out = out[: match.start()] + f"{new_open}{new_inner}</text>" + out[match.end() :]
    return resolve_title_plate_rule_clearance(out)


_TITLE_RULE_CLEAR_PX = 22.0  # clear below last title baseline before rule
_CONTENT_TITLE_MIN_FS = 24.0


def _content_title_match(svg: str) -> re.Match[str] | None:
    """Best content-header title text (large type in the top band).

    Document order often puts table cells before the title, so "first match"
    is wrong — score by size, weight, and serif family instead.
    """
    pattern = re.compile(
        r"(<text\b(?=[^>]*\bfont-size=\"(\d+(?:\.\d+)?)\")(?=[^>]*\by=\"(\d+(?:\.\d+)?)\")[^>]*>)"
        r"([\s\S]*?)</text>",
        flags=re.I,
    )
    best: re.Match[str] | None = None
    best_score = -1.0
    for match in pattern.finditer(svg or ""):
        try:
            font_size = float(match.group(2))
            y_pos = float(match.group(3))
        except ValueError:
            continue
        if font_size < 18 or y_pos > 130:
            continue
        open_tag = match.group(1)
        score = font_size
        if re.search(r'font-weight="(?:bold|700)"', open_tag, flags=re.I):
            score += 24.0
        if re.search(r"Georgia|serif", open_tag, flags=re.I):
            score += 12.0
        if re.search(r"<tspan\b", match.group(4) or "", flags=re.I):
            score += 6.0
        if score > best_score:
            best_score = score
            best = match
    return best


def _title_last_baseline(y_pos: float, font_size: float, inner: str) -> tuple[float, int]:
    """Return (last baseline Y, line count) from title text inner markup."""
    tspans = list(
        re.finditer(
            r"<tspan\b([^>]*)>([\s\S]*?)</tspan>",
            inner,
            flags=re.I,
        )
    )
    if not tspans:
        return y_pos, 1
    baseline = y_pos
    lines = 0
    for idx, span in enumerate(tspans):
        attrs, body = span.group(1), span.group(2)
        if not re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body)).strip():
            continue
        lines += 1
        dy_m = re.search(r'\bdy="([-\d.]+)"', attrs)
        y_m = re.search(r'\by="([-\d.]+)"', attrs)
        if y_m:
            baseline = float(y_m.group(1))
        elif dy_m:
            # First tspan often uses dy="0" relative to parent y.
            baseline = (y_pos if idx == 0 and abs(float(dy_m.group(1))) < 0.01 else baseline) + float(
                dy_m.group(1)
            )
        elif idx == 0:
            baseline = y_pos
        else:
            baseline += max(36.0, font_size * 1.15)
    return baseline, max(1, lines)


def resolve_content_title_rule_clearance(svg: str, *, role: str = "content") -> str:
    """Push header plate/rule below a wrapped content title (never a fixed rule Y).

    Executor freehand often paints a full-width plate + thin accent rect at a
    fixed Y sized for one line. When the title wraps, the accent cuts glyphs.
    """
    if role in {"title", "closing", "hero"} or not svg:
        return svg
    match = _content_title_match(svg)
    if not match:
        return svg
    font_size = float(match.group(2))
    y_pos = float(match.group(3))
    # Allow slightly crushed titles (fs 20–26) so wrap clearance still runs.
    if font_size < 20 or y_pos > 130:
        return svg
    last_baseline, line_count = _title_last_baseline(y_pos, font_size, match.group(4))
    min_rule_y = last_baseline + _TITLE_RULE_CLEAR_PX
    # Descent cushion so the rule clears glyph bottoms, not just the baseline.
    min_rule_y = max(min_rule_y, last_baseline + font_size * 0.35 + 12.0)

    out = svg
    rule_y: float | None = None

    # Thin full-width accent rect under the title band (common freehand pattern).
    best_rect: re.Match[str] | None = None
    best_rect_y = 1e9
    for rect in re.finditer(r"<rect\b([^>]*)/?>", out, flags=re.I):
        attrs = rect.group(1)
        try:
            x = float(re.search(r'\bx="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if h > 6 or w < 400 or y < y_pos - 4 or y > last_baseline + 48:
            continue
        if y < best_rect_y:
            best_rect_y = y
            best_rect = rect
    if best_rect is not None and best_rect_y + 0.5 < min_rule_y:
        rule_y = min_rule_y
        attrs = best_rect.group(1).rstrip().rstrip("/")
        new_attrs = re.sub(r'\by="[^"]*"', f'y="{rule_y:g}"', attrs, count=1)
        out = out[: best_rect.start()] + f"<rect{new_attrs}/>" + out[best_rect.end() :]

    # Horizontal <line> rules only (never vertical column dividers).
    best_line: re.Match[str] | None = None
    best_line_y = 1e9
    for line in re.finditer(r"<line\b([^>]*)/?>", out, flags=re.I):
        attrs = line.group(1)
        try:
            x1 = float(re.search(r'\bx1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y1 = float(re.search(r'\by1="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            x2 = float(re.search(r'\bx2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            y2 = float(re.search(r'\by2="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if abs(y2 - y1) > 1.5 or abs(x2 - x1) < 400:
            continue
        if y1 < y_pos - 4 or y1 > last_baseline + 48:
            continue
        if y1 < best_line_y:
            best_line_y = y1
            best_line = line
    if best_line is not None and best_line_y + 0.5 < min_rule_y:
        rule_y = min_rule_y if rule_y is None else rule_y
        replaced = re.sub(r'\by1="[^"]*"', f'y1="{rule_y:g}"', best_line.group(0), count=1)
        replaced = re.sub(r'\by2="[^"]*"', f'y2="{rule_y:g}"', replaced, count=1)
        out = out[: best_line.start()] + replaced + out[best_line.end() :]

    if rule_y is None:
        # No overlapping rule — still grow plate when wrap exceeds plate bottom.
        rule_y = min_rule_y if line_count >= 2 else None
    if rule_y is None:
        return out

    # Grow the light title-plate rect so it ends at/under the rule.
    for rect in re.finditer(r"<rect\b([^>]*)/?>", out, flags=re.I):
        attrs = rect.group(1)
        try:
            y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            w = float(re.search(r'\bwidth="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            h = float(re.search(r'\bheight="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if w < 800 or h < 40 or h > 140 or y > y_pos or y + h < y_pos:
            continue
        # Skip the accent rule itself.
        if h <= 6:
            continue
        need_h = max(h, rule_y - y)
        if need_h <= h + 0.5:
            break
        clean = attrs.rstrip().rstrip("/")
        new_attrs = re.sub(r'\bheight="[^"]*"', f'height="{need_h:g}"', clean, count=1)
        out = out[: rect.start()] + f"<rect{new_attrs}/>" + out[rect.end() :]
        break

    # Nudge body/subtitle copy that still sits on/under the rule (skip table cells).
    body_edits: list[tuple[int, int, str]] = []
    for body in re.finditer(
        r"(<text\b([^>]*)>)",
        out,
        flags=re.I,
    ):
        attrs = body.group(2) or ""
        if "data-sunairum-source-table-text" in attrs or "data-sunairum-page-number" in attrs:
            continue
        try:
            body_y = float(re.search(r'\by="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
            body_fs = float(re.search(r'\bfont-size="([-\d.]+)"', attrs).group(1))  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            continue
        if body.start() == match.start():
            continue
        # Include mid-size subtitles (fs 14–22); only skip large titles.
        if body_fs >= 28 or body_y < y_pos or body_y > rule_y + 80:
            continue
        if body_y >= rule_y + 16:
            continue
        target_y = rule_y + 16 + body_fs * 0.2
        new_open = re.sub(r'\by="[^"]*"', f'y="{target_y:g}"', body.group(1), count=1)
        body_edits.append((body.start(), body.end(), new_open))
    for start, end, replacement in sorted(body_edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + replacement + out[end:]
    return out



def _reposition_table_carriers(
    svg: str, x: float, y: float, width: float, height: float
) -> str:
    """Move native table carrier geometry into a recipe band without rewriting copy."""
    import html as html_mod

    def _rewrite(match: re.Match[str]) -> str:
        attrs, body = match.group(1), match.group(2)
        meta = re.search(r"(<metadata\b[^>]*>)(.*?)(</metadata>)", body, flags=re.I | re.S)
        if not meta:
            return match.group(0)
        try:
            payload = json.loads(html_mod.unescape(meta.group(2)).strip())
        except (TypeError, json.JSONDecodeError, ValueError):
            return match.group(0)
        if not isinstance(payload, dict):
            return match.group(0)
        payload["x"] = float(x)
        payload["y"] = float(y)
        payload["width"] = float(width)
        payload["height"] = float(height)
        encoded = html_mod.escape(json.dumps(payload, ensure_ascii=False), quote=False)
        new_body = body[: meta.start()] + f"{meta.group(1)}{encoded}{meta.group(3)}" + body[meta.end() :]
        # Keep absolute rect geometry in sync when present.
        new_body = re.sub(
            r'(<rect\b[^>]*\bx=")[^"]+(")',
            rf"\g<1>{x:g}\2",
            new_body,
            count=1,
            flags=re.I,
        )
        new_body = re.sub(
            r'(<rect\b[^>]*\by=")[^"]+(")',
            rf"\g<1>{y:g}\2",
            new_body,
            count=1,
            flags=re.I,
        )
        new_body = re.sub(
            r'(<rect\b[^>]*\bwidth=")[^"]+(")',
            rf"\g<1>{width:g}\2",
            new_body,
            count=1,
            flags=re.I,
        )
        new_body = re.sub(
            r'(<rect\b[^>]*\bheight=")[^"]+(")',
            rf"\g<1>{height:g}\2",
            new_body,
            count=1,
            flags=re.I,
        )
        return f"<g{attrs}>{new_body}</g>"

    return re.sub(
        r"<g\b([^>]*\bdata-pptx-replace-with=[\"']table[\"'][^>]*)>(.*?)</g>",
        _rewrite,
        svg or "",
        flags=re.I | re.S,
    )


_ROMAN = {
    1: "i",
    2: "ii",
    3: "iii",
    4: "iv",
    5: "v",
    6: "vi",
    7: "vii",
    8: "viii",
    9: "ix",
    10: "x",
    11: "xi",
    12: "xii",
}


def _asset_bind_score(slide: dict[str, Any], *, kind: str, asset_id: str = "") -> int:
    """Higher = better fallback target for an unbound selected asset."""
    layout = " ".join(
        str(slide.get(key) or "")
        for key in ("layout_intent", "visual_job", "content_blocks", "body", "title")
    ).casefold()
    score = 0
    if kind == "table":
        if "table-dominant" in layout or "table dominant" in layout:
            score += 100
        if re.search(r"\btable\b", layout):
            score += 40
        # Prefer the slide that names this table (Table I ↔ src-table-001).
        num_match = re.search(r"src-table-(\d+)", str(asset_id or ""), re.I)
        if num_match:
            n = int(num_match.group(1))
            roman = _ROMAN.get(n, "")
            if roman and re.search(rf"\btable\s+{roman}\b", layout):
                score += 200
            if re.search(rf"\btable\s+{n}\b", layout):
                score += 200
        if str(slide.get("figure_id") or "").strip():
            score -= 80  # prefer not to co-locate with a figure
    else:
        if "figure-dominant" in layout or "figure dominant" in layout:
            score += 100
        if re.search(r"\bfigure\b", layout):
            score += 40
        if asset_id and asset_id.casefold() in layout:
            score += 200
        if str(slide.get("table_id") or "").strip():
            score -= 80
    return score


def _uniquify_asset_bindings(parsed: list[dict[str, Any]]) -> list[str]:
    """Keep each figure_id / table_id on at most one content slide.

    §IX sometimes repeats the same PDF figure on multiple slides (e.g. 3 and 5).
    Keep the best-scoring owner; clear the rest so bind can fill leftovers.
    """
    content = [
        item
        for item in parsed
        if isinstance(item, dict) and str(item.get("role") or "content") == "content"
    ]
    warnings: list[str] = []

    def _dedupe(key: str, kind: str) -> None:
        owners: dict[str, list[dict[str, Any]]] = {}
        for slide in content:
            aid = str(slide.get(key) or "").strip()
            if not aid:
                continue
            owners.setdefault(aid, []).append(slide)
        for aid, slides in owners.items():
            if len(slides) < 2:
                continue
            slides.sort(
                key=lambda s: _asset_bind_score(s, kind=kind, asset_id=aid),
                reverse=True,
            )
            keep = slides[0]
            for loser in slides[1:]:
                loser[key] = ""
                warnings.append(
                    f"cleared duplicate {key}={aid} from slide {loser.get('slide')} "
                    f"(kept on slide {keep.get('slide')})"
                )

    _dedupe("figure_id", "figure")
    _dedupe("table_id", "table")
    return warnings


def _bind_selected_assets(
    parsed: list[dict[str, Any]],
    *,
    selected_figure_ids: list[str],
    selected_table_ids: list[str],
) -> list[str]:
    """Assign remaining selected assets. Never overwrite §IX bindings."""
    content = [item for item in parsed if isinstance(item, dict) and item.get("role") == "content"]
    warnings: list[str] = []

    def _unbound(selected: list[str], key: str) -> list[str]:
        placed = {str(s.get(key) or "").strip() for s in content if s.get(key)}
        return [aid for aid in selected if aid and aid not in placed]

    # Tables first so table-dominant slides claim their band before figures.
    for tid in _unbound(selected_table_ids, "table_id"):
        candidates = [
            s
            for s in content
            if not str(s.get("table_id") or "").strip()
            and not str(s.get("figure_id") or "").strip()
        ]
        if not candidates:
            # Last resort: allow a slide that already has a figure only if nothing else.
            candidates = [s for s in content if not str(s.get("table_id") or "").strip()]
        if not candidates:
            warnings.append(f"selected table {tid} unbound — no empty content slot")
            continue
        candidates.sort(
            key=lambda s: _asset_bind_score(s, kind="table", asset_id=tid), reverse=True
        )
        target = candidates[0]
        if str(target.get("figure_id") or "").strip():
            warnings.append(
                f"selected table {tid} co-located with figure on slide {target.get('slide')}"
            )
        target["table_id"] = tid

    for fid in _unbound(selected_figure_ids, "figure_id"):
        candidates = [
            s
            for s in content
            if not str(s.get("figure_id") or "").strip()
            and not str(s.get("table_id") or "").strip()
        ]
        if not candidates:
            candidates = [s for s in content if not str(s.get("figure_id") or "").strip()]
        if not candidates:
            warnings.append(f"selected figure {fid} unbound — no empty content slot")
            continue
        candidates.sort(
            key=lambda s: _asset_bind_score(s, kind="figure", asset_id=fid), reverse=True
        )
        target = candidates[0]
        if str(target.get("table_id") or "").strip():
            warnings.append(
                f"selected figure {fid} co-located with table on slide {target.get('slide')}"
            )
        target["figure_id"] = fid

    return warnings


def _table_column_texts(table: dict[str, Any]) -> list[str]:
    cols = table.get("columns") if isinstance(table.get("columns"), list) else None
    if not cols:
        cols = table.get("headers") if isinstance(table.get("headers"), list) else []
    out: list[str] = []
    for col in cols or []:
        if isinstance(col, dict):
            text = str(col.get("text") or col.get("label") or "").strip()
        else:
            text = str(col or "").strip()
        if text:
            out.append(text)
    return out


def _slide_table_text_blob(slide: dict[str, Any]) -> str:
    return " ".join(
        str(slide.get(key) or "")
        for key in (
            "title",
            "core_message",
            "body",
            "content_blocks",
            "visual_job",
            "layout_intent",
            "audience_move",
            "callout",
        )
    ).casefold()


def _slide_table_fit_score(slide: dict[str, Any], table: dict[str, Any]) -> int:
    """Score how well a source table matches slide claims (caption + columns)."""
    slide_blob = _slide_table_text_blob(slide)
    if not slide_blob.strip():
        return 0
    caption = str(table.get("caption") or table.get("title") or "").casefold()
    headers = [h.casefold() for h in _table_column_texts(table)]
    header_blob = " ".join(headers)

    score = 0
    for token in re.findall(r"[a-z][a-z0-9-]{2,}", caption):
        if token in {"table", "the", "and", "for", "with", "from", "over", "mean"}:
            continue
        if token in slide_blob:
            score += 8
    for header in headers:
        compact = re.sub(r"\s+", " ", header).strip()
        if len(compact) < 2:
            continue
        if compact in slide_blob:
            score += 28
        # bare metric tokens (cv, gini, jain, brute, hnsw)
        for part in re.findall(r"[a-z][a-z0-9]{1,}", compact):
            if part in {"cv", "gini", "jain", "brute", "hnsw", "method", "cost", "time"} and (
                re.search(rf"\b{re.escape(part)}\b", slide_blob)
            ):
                score += 18

    equity_slide = bool(
        re.search(r"\b(gini|jain)\b", slide_blob)
        or (
            re.search(r"\bcv\b", slide_blob)
            and re.search(r"\b(equity|imbalance|solomon|alns|hero)\b", slide_blob)
        )
    )
    eval_slide = bool(
        re.search(r"\b(evaluation|evals|brute|homberger|reduction)\b", slide_blob)
        and not equity_slide
    )
    # Homberger efficiency slides can mention equity in audience_move — still eval-primary
    if re.search(r"\b(brute|evals|homberger|distance evaluations)\b", slide_blob):
        if not re.search(r"\b(gini|jain)\b", slide_blob):
            eval_slide = True
            equity_slide = False

    equity_table = bool(re.search(r"\b(gini|jain|method)\b", header_blob)) or (
        "cv" in headers or any(h == "cv" or h.startswith("cv ") for h in headers)
    )
    eval_table = bool(re.search(r"\b(brute|hnsw|evals|reduction)\b", header_blob))

    if equity_slide and equity_table:
        score += 160
    if equity_slide and eval_table and not equity_table:
        score -= 220
    if eval_slide and eval_table:
        score += 160
    if eval_slide and equity_table and not eval_table:
        score -= 120

    if "solomon" in caption and "solomon" in slide_blob:
        score += 40
    if "homberger" in caption and "homberger" in slide_blob:
        score += 40
    if "equity" in caption and "equity" in slide_blob:
        score += 35
    if "evaluation" in caption and re.search(r"\b(evaluation|evals)\b", slide_blob):
        score += 35
    # Benchmark / corpus mismatch — don't hand Euro-NeurIPS tables to Solomon slides.
    slide_solomon = "solomon" in slide_blob
    slide_homberger = "homberger" in slide_blob
    slide_asym = bool(re.search(r"\b(asymmetric|euro-neurips|neurips)\b", slide_blob))
    cap_solomon = "solomon" in caption
    cap_homberger = "homberger" in caption
    cap_asym = bool(re.search(r"\b(asymmetric|euro-neurips|neurips)\b", caption))
    if slide_solomon and cap_asym and not slide_asym:
        score -= 120
    if slide_asym and cap_solomon and not slide_solomon:
        score -= 80
    if slide_homberger and cap_solomon and not slide_solomon:
        score -= 60
    if slide_solomon and cap_homberger and not slide_homberger:
        score -= 60
    # Class-structure equity slides prefer Class + ∆ CV style tables over method means.
    class_slide = bool(
        re.search(r"\b(class|classes|structures|structure)\b", slide_blob)
        and re.search(r"\b(cv|equity|hero|alns)\b", slide_blob)
    )
    class_table = "class" in headers and bool(re.search(r"\bcv\b", header_blob))
    method_means = "method" in headers and bool(re.search(r"\b(gini|jain)\b", header_blob))
    if class_slide and class_table:
        score += 90
    if class_slide and method_means and not class_table:
        score -= 70
    return score


def _reconcile_slide_table_bindings(
    parsed: list[dict[str, Any]],
    table_catalog: list[dict[str, Any]],
    selected_table_ids: list[str] | None = None,
) -> list[str]:
    """Fix §IX/bind mistakes when slide claims disagree with table columns/caption.

    Example: Solomon equity copy (CV/Gini/Jain) bound to an HNSW eval-count table.
    """
    if not table_catalog:
        return []
    by_id: dict[str, dict[str, Any]] = {}
    for table in table_catalog:
        if not isinstance(table, dict):
            continue
        tid = str(table.get("table_id") or table.get("id") or "").strip()
        if tid:
            by_id[tid] = table
    if not by_id:
        return []

    # An explicit selection is an instruction, not a hint. Re-scoring may reorder
    # which chosen table lands on which slide, but it must never reach outside the
    # chosen set: swapping in a table the user did not pick both drops one they
    # did and silently changes the deck's evidence. The obedience ledger has no
    # way to tell that apart from a placement failure, so it reported the deck as
    # disobedient — "1 tables missing" — while the swapped-in table sat on screen.
    chosen = {str(value).strip() for value in (selected_table_ids or []) if str(value).strip()}
    if chosen:
        available = {tid: table for tid, table in by_id.items() if tid in chosen}
        if available:
            by_id = available

    content = [
        item
        for item in parsed
        if isinstance(item, dict) and str(item.get("role") or "content") == "content"
    ]
    owners: dict[str, dict[str, Any]] = {}
    for slide in content:
        tid = str(slide.get("table_id") or "").strip()
        if tid:
            owners[tid] = slide

    warnings: list[str] = []
    # Worst mismatches first so they claim the correct unused tables.
    ranked = sorted(
        content,
        key=lambda s: (
            _slide_table_fit_score(s, by_id[tid])
            if (tid := str(s.get("table_id") or "").strip()) in by_id
            else 0
        ),
    )
    for slide in ranked:
        current = str(slide.get("table_id") or "").strip()
        if not current or current not in by_id:
            # Only reconcile existing bindings (do not invent tables for every slide).
            continue
        cur_score = _slide_table_fit_score(slide, by_id[current])
        best_id = current
        best_score = cur_score
        for tid, table in by_id.items():
            score = _slide_table_fit_score(slide, table)
            if score <= best_score:
                continue
            other = owners.get(tid)
            if other is not None and other is not slide:
                other_score = _slide_table_fit_score(other, by_id[tid])
                # Skip tables that already fit their owner better (or nearly so).
                if other_score >= score - 40:
                    continue
            best_score = score
            best_id = tid
        if best_id == current:
            continue
        # Require a clear win, or a hard mismatch (negative current + strong alt).
        if not (best_score >= cur_score + 80 or (cur_score < 0 and best_score >= 80)):
            continue
        other = owners.get(best_id)
        old = current
        if other is not None and other is not slide:
            other_score = _slide_table_fit_score(other, by_id[best_id])
            # Hand the displaced slide the table this one is giving up. Simply
            # freeing it leaves the displaced table owned by nobody, so a
            # selection the user made is dropped from the deck and then reported
            # back to them as missing. Re-scoring may permute which chosen table
            # lands where; it must never reduce how many of them are placed.
            other["table_id"] = old
            owners.pop(best_id, None)
            owners[old] = other
            warnings.append(
                f"swapped table {best_id} from slide {other.get('slide')} "
                f"(fit {other_score}) to slide {slide.get('slide')}, "
                f"slide {other.get('slide')} takes {old}"
            )
        else:
            owners.pop(old, None)
        slide["table_id"] = best_id
        owners[best_id] = slide
        warnings.append(
            f"rebound slide {slide.get('slide')} table {old}→{best_id} "
            f"(fit {cur_score}→{best_score})"
        )
    return warnings


_META_CARD_TITLES = frozenset(
    {
        "title",
        "core message",
        "core message**",
        "authors",
        "author",
        "affiliations",
        "affiliation",
        "content",
        "visual job",
        "layout",
        "figure",
        "table",
        "evidence",
    }
)
_STRATEGIST_FIELD_DUMP_RE = re.compile(
    r"(?im)^\s*[-*]\s*\*\*(?:Title|Core message|Layout|Content|Visual job|Authors?|Affiliations?)\b"
)


def _strip_list_marker(line: str) -> str:
    """Delegate to the one definition of what a list marker is."""
    try:
        from tasks.asset_narrative import strip_list_marker
    except ImportError:  # pragma: no cover - flat-module import path
        from asset_narrative import strip_list_marker  # type: ignore
    return strip_list_marker(line)


def _bullet_cards_from_prose(text: str, *, limit: int = 6) -> list[dict[str, str]]:
    """Split real bullet lines into card/step IR — never strategist field dumps."""
    raw = str(text or "").strip()
    if not raw or _STRATEGIST_FIELD_DUMP_RE.search(raw):
        return []
    chunks: list[str] = []
    for line in raw.splitlines():
        # Only explicit bullets / numbered lines — not paragraph sentence splits.
        if not re.match(r"^\s*(?:[-*•]|\d+[.)])\s+\S", line):
            continue
        cleaned = _strip_list_marker(line)
        cleaned = re.sub(r"^\*+|\*+$", "", cleaned).strip()
        if cleaned:
            chunks.append(cleaned)
    cards: list[dict[str, str]] = []
    for chunk in chunks[:limit]:
        if ":" in chunk[:48]:
            title, _, body = chunk.partition(":")
            title = title.strip().strip("*").strip()
            body = body.strip()
        else:
            words = chunk.split()
            title = " ".join(words[:5]) if len(words) > 8 else chunk[:72]
            body = chunk if title != chunk else ""
            title = title.strip().strip("*").strip()
        if title.casefold().rstrip("*").strip() in _META_CARD_TITLES:
            continue
        if not title:
            continue
        cards.append({"title": title[:80], "body": body[:240]})
    return cards


def _slide_dict_from_parsed(item: dict[str, Any]) -> dict[str, Any]:
    content_blocks = str(item.get("content_blocks") or "")
    role = str(item.get("role") or "content")
    authors = str(item.get("authors") or "")
    affiliations = str(item.get("affiliations") or "")
    subtitle = str(item.get("core_message") or "")
    cards = item.get("cards") if isinstance(item.get("cards"), list) else []
    steps = item.get("steps") if isinstance(item.get("steps"), list) else []
    formula = str(item.get("formula") or "").strip()
    formula_tex = str(item.get("formula_tex") or "").strip()
    formula_terms = str(item.get("formula_terms") or "").strip()
    formula_gloss = str(item.get("formula_gloss") or "").strip()
    content: dict[str, Any] = {
        "TITLE": str(item.get("title") or ""),
        "BODY": "" if role in {"title", "closing"} else content_blocks,
        "SUBTITLE": subtitle,
    }
    if formula:
        content["FORMULA"] = formula
    if formula_tex:
        content["FORMULA_TEX"] = formula_tex
    if formula_terms:
        content["FORMULA_TERMS"] = formula_terms
    if formula_gloss:
        content["FORMULA_GLOSS"] = formula_gloss
    slide = {
        "slide": int(item["slide"]),
        "slide_id": item.get("slide_id") or f"slide-{int(item['slide'])}",
        "title": str(item.get("title") or f"Slide {item['slide']}"),
        "content": content,
        "core_message": item.get("core_message") or "",
        "layout_intent": item.get("layout_intent") or "",
        "visual_job": item.get("visual_job") or "",
        "formula": formula,
        "formula_tex": formula_tex,
        "formula_terms": formula_terms,
        "formula_gloss": formula_gloss,
        "evidence_ids": list(item.get("evidence_ids") or []),
        "body_md": item.get("body") or "",
        "role": role,
        "authors": authors,
        "affiliations": affiliations,
        "figure_id": str(item.get("figure_id") or ""),
        "table_id": str(item.get("table_id") or ""),
        "layout_recipe": str(item.get("layout_recipe") or ""),
        "cards": cards,
        "steps": steps,
        "compare": bool(item.get("compare")),
        "has_process": bool(item.get("has_process")),
        "has_diagram": bool(item.get("has_diagram")),
        "has_chart": bool(item.get("has_chart")),
    }
    try:
        from tasks.content_densify import densify_slide_ir
    except ImportError:  # pragma: no cover
        from content_densify import densify_slide_ir  # type: ignore
    densify_slide_ir(slide)
    slide.pop("layout_recipe", None)
    return slide


_INSTRUCTIONAL_OPENER_RE = re.compile(
    r"^\s*(Introduce|Explain|Describe|Present|Cover|Highlight|Mention|Compare)\b",
    re.I,
)
_SECTION_IX_HDR_RE = re.compile(r"^##\s*IX\.?\s*Content Outline\s*$", re.I | re.M)
_SECTION_X_HDR_RE = re.compile(r"^##\s*X\.?\s*Speaker Notes\s*$", re.I | re.M)
_MULTI_PANEL_LAYOUT_RE = re.compile(
    r"(?i)\b("
    r"two[- ]column|two concerns|two[- ]part|stacked|card(?:s)?|"
    r"left side frames|three vertical|three[- ]column|compare|versus|"
    r"before/?after|pillars|gates"
    r")\b"
)
_MERGED_BOLD_TSPAN_RE = re.compile(
    r"<text\b[^>]*>[\s\S]*?</text>",
    re.I,
)
_BOLD_TSPAN_RE = re.compile(
    r"<tspan\b[^>]*font-weight\s*=\s*[\"']?(?:700|bold)[\"']?[^>]*>",
    re.I,
)


def _content_is_instructional(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    first = re.split(r"(?<=[.!?])\s+", raw, maxsplit=1)[0]
    return bool(_INSTRUCTIONAL_OPENER_RE.search(first) or _INSTRUCTIONAL_OPENER_RE.search(raw))


def persist_slide_design_packs(
    storage_dir: str,
    design_spec_md: str,
    slides: list[dict[str, Any]],
) -> list[str]:
    """Write per-slide Executor packs under ``slide_packs/P0N.md``."""
    packs_dir = os.path.join(storage_dir, "slide_packs")
    os.makedirs(packs_dir, exist_ok=True)
    written: list[str] = []
    for slide in slides:
        try:
            number = int(slide.get("slide") or 0)
        except (TypeError, ValueError):
            continue
        if number < 1:
            continue
        pack = extract_executor_design_pack(
            design_spec_md,
            number,
            body_md_fallback=str(slide.get("body_md") or ""),
        )
        path = os.path.join(packs_dir, f"P{number:02d}.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(pack if pack.endswith("\n") else pack + "\n")
        written.append(path)
    print(f"[free_design] wrote {len(written)} slide packs → slide_packs/")
    return written


def extract_executor_design_pack(
    design_spec_md: str,
    slide_number: int,
    *,
    body_md_fallback: str = "",
) -> str:
    """sample.md-shaped slice: §I–VIII + this §IX + this §X only."""
    raw = str(design_spec_md or "")
    if not raw.strip():
        fallback = str(body_md_fallback or "").strip()
        return fallback

    ix_match = _SECTION_IX_HDR_RE.search(raw)
    x_match = _SECTION_X_HDR_RE.search(raw)
    if not ix_match:
        fallback = str(body_md_fallback or "").strip()
        return fallback or raw.strip()

    prefix = raw[: ix_match.start()].rstrip()
    ix_end = x_match.start() if x_match else len(raw)
    ix_body = raw[ix_match.end() : ix_end]
    page = f"{int(slide_number):02d}"
    slide_hdr = re.compile(
        rf"^###\s*P0*{int(slide_number)}\b[^\n]*$",
        re.I | re.M,
    )
    hdr = slide_hdr.search(ix_body)
    if not hdr:
        fallback = str(body_md_fallback or "").strip()
        if fallback:
            return (
                f"{prefix}\n\n## IX. Content Outline\n\n{fallback}\n"
                if prefix
                else f"## IX. Content Outline\n\n{fallback}\n"
            )
        return prefix

    next_hdr = re.search(r"^###\s*P\d+\b", ix_body[hdr.end() :], re.I | re.M)
    chunk_end = hdr.end() + next_hdr.start() if next_hdr else len(ix_body)
    slide_chunk = ix_body[hdr.start() : chunk_end].strip()

    parts = [
        prefix,
        "",
        "## IX. Content Outline",
        "",
        slide_chunk,
    ]

    if x_match:
        x_body = raw[x_match.end() :]
        # Strategist writes `- **P02:** note` (colon inside bold markers).
        note = re.search(
            rf"^\s*[-*]\s*\*\*P0*{int(slide_number)}:?\*\*\s*(.+)$",
            x_body,
            re.I | re.M,
        )
        if note:
            parts.extend(
                [
                    "",
                    "## X. Speaker Notes (spoken context ONLY — do NOT paint on the slide)",
                    "",
                    f"- **P{page}:** {note.group(1).strip()}",
                ]
            )

    return "\n".join(parts).rstrip() + "\n"


def _ix_content_bullets_from_pack(pack: str) -> list[str]:
    """Pull audience Content bullets from a this-slide design pack."""
    try:
        from tasks.asset_narrative import extract_content_bullets
    except ImportError:  # pragma: no cover
        from asset_narrative import extract_content_bullets  # type: ignore
    return extract_content_bullets(pack)


def _ix_field_from_pack(pack: str, field: str) -> str:
    # Accept `- **Layout:** value` or `- **Layout**: value`.
    # Scope to §IX so §IV Typography ("**Formula:** Georgia…") never wins.
    try:
        from tasks.executor_modes import _pack_section_ix
    except ImportError:  # pragma: no cover
        from executor_modes import _pack_section_ix  # type: ignore
    scope = _pack_section_ix(pack) if pack else ""
    text = scope or pack or ""
    # Multiline display math under Formula (same bug as §IX single-line field).
    if field.casefold() == "formula":
        header = re.search(
            r"(?im)^\s*[-*]\s*\*\*Formula:?\*\*\s*:?\s*(.*)$",
            text,
        )
        if header:
            first = (header.group(1) or "").strip()
            opener_only = bool(
                re.fullmatch(r"(?:\\\[|\$\$|\\\(|\$)\s*", first)
                or first in {"\\[", "$$", "\\(", "$"}
            )
            if first and not opener_only and (
                re.search(r"\\\]|\$\$|\\\)", first)
                or not re.match(r"^(?:\\\[|\$\$)", first)
            ):
                return first
            lines = [first] if first else []
            for line in text[header.end() :].splitlines():
                if re.match(
                    r"^\s*[-*]\s*\*\*(?:"
                    r"Title|Core message|Layout|Content|Evidence|Figure|Table|"
                    r"Formula tex|Formula TeX|Formula terms|Formula Terms|"
                    r"Formula gloss|Formula Gloss|Visual job|Visualization|"
                    r"Page rhythm|Structure|Authors|Affiliations"
                    r"):?\*\*",
                    line,
                    flags=re.I,
                ):
                    break
                lines.append(line.rstrip())
                joined = "\n".join(lines)
                if re.search(r"\\\]|\$\$", joined):
                    break
            return "\n".join(lines).strip()
    match = re.search(
        rf"(?im)^\s*[-*]\s*\*\*{re.escape(field)}:?\*\*\s*:?\s*(.+)$",
        text,
    )
    return match.group(1).strip() if match else ""


def _sanitize_formula_field(raw: str) -> str:
    """Strip fences/backticks and TeX delimiters from FORMULA* IR."""
    try:
        from tasks.formula_visual_intent import sanitize_formula_text
    except ImportError:  # pragma: no cover
        from formula_visual_intent import sanitize_formula_text  # type: ignore
    out = sanitize_formula_text(raw)
    # Bare openers after a truncated multiline parse are not equations.
    if out in {"\\[", "\\]", "$$", "\\(", "\\)", "$"} or re.fullmatch(
        r"\\[\[\]]|\$\$?", out or ""
    ):
        return ""
    return out


def _formula_fields_from_slide(
    slide: dict[str, Any] | None,
    pack: str = "",
) -> tuple[str, str, str, str]:
    """Resolve Formula / Formula tex / terms / gloss from slide IR or pack."""
    try:
        from tasks.executor_modes import is_typography_formula_leak
    except ImportError:  # pragma: no cover
        from executor_modes import is_typography_formula_leak  # type: ignore

    slide = slide if isinstance(slide, dict) else {}
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    body_fallback = str(slide.get("body_md") or slide.get("body") or "")
    formula = _sanitize_formula_field(
        str(slide.get("formula") or "").strip()
        or str(content.get("FORMULA") or "").strip()
        or _ix_field_from_pack(pack, "Formula")
        or _ix_field_from_pack(body_fallback, "Formula")
    )
    if is_typography_formula_leak(formula):
        formula = ""
    formula_tex = _sanitize_formula_field(
        str(slide.get("formula_tex") or "").strip()
        or str(content.get("FORMULA_TEX") or "").strip()
        or _ix_field_from_pack(pack, "Formula tex")
        or _ix_field_from_pack(pack, "Formula TeX")
        or (formula if formula and "\\" in formula else "")
    )
    if is_typography_formula_leak(formula_tex):
        formula_tex = ""
    terms = _sanitize_formula_field(
        str(slide.get("formula_terms") or "").strip()
        or str(content.get("FORMULA_TERMS") or "").strip()
        or _ix_field_from_pack(pack, "Formula terms")
        or _ix_field_from_pack(pack, "Formula Terms")
    )
    gloss = _sanitize_formula_field(
        str(slide.get("formula_gloss") or "").strip()
        or str(content.get("FORMULA_GLOSS") or "").strip()
        or _ix_field_from_pack(pack, "Formula gloss")
        or _ix_field_from_pack(pack, "Formula Gloss")
    )
    if is_typography_formula_leak(gloss):
        gloss = ""
    if is_typography_formula_leak(terms):
        terms = ""
    return formula, terms, gloss, formula_tex


def _wants_body_panels(*, pack: str, slide: dict[str, Any]) -> int:
    """Return desired panel count (0, 2, or 3) from layout cues + content."""
    intent = " ".join(
        [
            str(slide.get("layout_intent") or ""),
            str(slide.get("visual_job") or ""),
            _ix_field_from_pack(pack, "Layout"),
            _ix_field_from_pack(pack, "Visual job"),
        ]
    )
    if not _MULTI_PANEL_LAYOUT_RE.search(intent):
        return 0
    cards = slide.get("cards") if isinstance(slide.get("cards"), list) else []
    bullets = _ix_content_bullets_from_pack(pack)
    if not bullets and not cards:
        content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
        body = str(content.get("BODY") or "").strip()
        bullets = [c.get("title", "") for c in _bullet_cards_from_prose(body) if c.get("title")]
    n_items = len(cards) if cards else len(bullets)
    if n_items < 2:
        return 0
    if re.search(r"(?i)\bthree\b", intent) and n_items >= 3:
        return 3
    return 2


def _cluster_panel_texts(items: list[str], panel_count: int) -> list[str]:
    if panel_count <= 0 or not items:
        return []
    if len(items) <= panel_count:
        return items[:panel_count]
    # Split into roughly equal contiguous groups (two-column / three cards).
    groups: list[str] = []
    size = len(items)
    for i in range(panel_count):
        start = (i * size) // panel_count
        end = ((i + 1) * size) // panel_count
        chunk = items[start:end]
        groups.append(" ".join(chunk).strip())
    return [g for g in groups if g]


def _format_body_panels_block(
    layout, *, pack: str, slide: dict[str, Any], force_panels: bool = False
) -> str:
    panel_count = _wants_body_panels(pack=pack, slide=slide)
    if force_panels and panel_count < 2:
        bullets = _ix_content_bullets_from_pack(pack)
        cards = slide.get("cards") if isinstance(slide.get("cards"), list) else []
        n = len(cards) if cards else len(bullets)
        panel_count = 3 if n >= 3 else 2 if n >= 2 else 0
    if panel_count < 2:
        return ""
    body_region = None
    callout_region = None
    for region in getattr(layout, "regions", []) or []:
        role = str(getattr(region, "role", "") or "")
        if role == "body":
            body_region = region
        elif role == "callout":
            callout_region = region
    if body_region is None:
        return ""

    cards = slide.get("cards") if isinstance(slide.get("cards"), list) else []
    if cards:
        items = []
        for card in cards[:panel_count]:
            title = str(card.get("title") or "").strip()
            body = str(card.get("body") or "").strip()
            items.append(f"{title}: {body}".strip(": ").strip() if body else title)
        texts = _cluster_panel_texts([t for t in items if t], panel_count)
    else:
        bullets = _ix_content_bullets_from_pack(pack)
        if not bullets:
            content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
            body = str(content.get("BODY") or "").strip()
            bullets = [
                c.get("title", "") for c in _bullet_cards_from_prose(body) if c.get("title")
            ]
        texts = _cluster_panel_texts(bullets, panel_count)
    if len(texts) < 2:
        return ""

    gap = 12.0
    usable = max(40.0, float(body_region.height) - gap * (len(texts) - 1))
    band_h = usable / len(texts)
    shared_x = float(body_region.x)
    shared_w = float(body_region.width)
    lines = [
        "## Body panels (inside body AABB; HARD non-overlap)",
        f"SHARED column: every panel uses x={shared_x:g} and w={shared_w:g} (identical).",
        "Each panel owns its band. One <text> per logical string inside the band;",
        "do not merge panel titles into one <text> stream.",
    ]
    if callout_region is not None:
        lines.append(
            f"Callout/formula band (below cards, ≥16px gap): "
            f"x={callout_region.x:g} y={callout_region.y:g} "
            f"w={callout_region.width:g} h={callout_region.height:g}"
        )
    y = float(body_region.y)
    for idx, text in enumerate(texts):
        lines.append(
            f"- panel.{idx}: x={shared_x:g} y={y:g} "
            f"w={shared_w:g} h={band_h:g} ← {text}"
        )
        y += band_h + gap
    return "\n".join(lines)


def strip_empty_figure_slots(svg: str, *, figure_id: str = "") -> str:
    """Remove Executor-invented empty figure holes when no real figure is bound."""
    if not svg:
        return svg or ""
    fid = str(figure_id or "").strip()
    if fid and fid.casefold() not in {"none", "null", "n/a", "-"}:
        return svg

    def _drop_group(match: re.Match[str]) -> str:
        block = match.group(0)
        if re.search(r'data-sunairum-figure-id=["\']none["\']', block, re.I):
            return ""
        if re.search(r'data-sunairum-figure-slot=', block, re.I) and not re.search(
            r'<image\b', block, re.I
        ):
            return ""
        return block

    out = re.sub(
        r"<g\b[^>]*data-sunairum-figure-(?:slot|id)=[^>]*>[\s\S]*?</g>",
        _drop_group,
        svg,
        flags=re.I,
    )
    return out




def detect_merged_multi_card_text(svg: str) -> bool:
    """True when one <text> holds ≥2 bold heading tspans (merged card titles)."""
    if not svg:
        return False
    for block in _MERGED_BOLD_TSPAN_RE.findall(svg):
        if len(_BOLD_TSPAN_RE.findall(block)) >= 2:
            return True
    return False


def composition_fingerprint(
    *,
    number: int,
    mode: str,
    recipe: str,
    svg: str,
    color_palette: dict[str, str] | None = None,
) -> str:
    """Cross-slide visual diary entry used to force composition variety."""
    try:
        from tasks.svg_reflow import composition_fingerprint_from_svg
    except ImportError:  # pragma: no cover
        from svg_reflow import composition_fingerprint_from_svg  # type: ignore

    accent = ""
    if isinstance(color_palette, dict):
        accent = str(
            color_palette.get("accent")
            or color_palette.get("primary")
            or ""
        ).strip()
    struct = composition_fingerprint_from_svg(svg or "", mode=mode)
    return f"P{number:02d}:{struct}|recipe={recipe}|accent={accent or '-'}"


def composition_energy(
    svg: str,
    palette: dict[str, str] | None = None,
) -> float:
    """Rough visual richness score for keep-best (shapes + accent hex hits)."""
    if not svg:
        return 0.0
    score = 0.0
    score += 1.5 * len(re.findall(r"<circle\b|<ellipse\b", svg, flags=re.I))
    score += 1.2 * len(re.findall(r"<polyline\b|<polygon\b", svg, flags=re.I))
    score += 0.8 * len(
        re.findall(r'<path\b[^>]*\bd="[^"]{8,}"', svg, flags=re.I)
    )
    for match in re.finditer(
        r'<rect\b([^>]*)>',
        svg,
        flags=re.I,
    ):
        attrs = match.group(1) or ""
        if "data-sunairum-" in attrs and "slot" in attrs.casefold():
            continue
        fill_m = re.search(r'\bfill="([^"]+)"', attrs, flags=re.I)
        fill = (fill_m.group(1) if fill_m else "").casefold()
        if fill in {"none", "#ffffff", "#fff", "white", ""}:
            continue
        score += 0.6
    pal = palette if isinstance(palette, dict) else {}
    for key in ("accent", "secondary_accent", "success", "warning", "primary"):
        hex_v = str(pal.get(key) or "").strip()
        if hex_v and hex_v.casefold() in svg.casefold():
            score += 2.0
    score += min(8.0, len(svg) / 800.0)
    return score


def _mechanical_repair_hosts(svg: str, slide: dict[str, Any]) -> str:
    try:
        from tasks.intent_hosts import ensure_asset_hosts
    except ImportError:  # pragma: no cover
        from intent_hosts import ensure_asset_hosts  # type: ignore
    return ensure_asset_hosts(svg or "", slide)


def _role_prompt_section(slide: dict[str, Any], *, pack: str) -> str:
    role = str(slide.get("role") or "content").strip().casefold()
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    title = (
        str(slide.get("title") or "").strip()
        or str(content.get("TITLE") or "").strip()
    )
    authors = (
        str(slide.get("authors") or "").strip()
        or str(content.get("SUBTITLE") or "").strip()
    )
    affiliations = str(slide.get("affiliations") or "").strip()
    if role in {"title", "hero"}:
        return (
            "## Title / hero plate (HARD) — dedicated cover prompt\n"
            "This is a TITLE PLATE / event cover, NOT a content slide.\n"
            "Forbidden compositions (reject these):\n"
            "- Content-header pattern: small ~28–40px title + full-width rule + "
            "body/graphic hanging under the header\n"
            "- Card stacks, contribution bullets, labeled diagrams/legends\n"
            "- Mid-slide motif with a large empty right/bottom void and no panel\n\n"
            "Required composition:\n"
            "- Brand-first hero title: Georgia (or lock title face) **56–72px**, "
            "2–4 lines, left column roughly x≈80–720\n"
            "- Authors / affiliations sit **low** on the plate (y≈480–640), "
            "not tucked under a header rule\n"
            "- Full-bleed atmosphere: solid side panel OR large right-band motif "
            "(~x 860–1280, tall) — unlabeled shapes/paths/gradients only\n"
            "- Accent bars / tint masses that read as a cover, not a section page\n"
            "- Do not paint page numbers (pipeline injects n/N)\n\n"
            "Paint ONLY these strings — nothing else as text:\n"
            f"- Hero title: {title or '(from pack)'}\n"
            f"- Authors: {authors or '(omit if empty)'}\n"
            f"- Affiliations: {affiliations or '(omit if empty)'}\n"
            "- FORBIDDEN as text: HERO/section eyebrows, taglines not listed above, "
            "contribution bullets, labeled diagrams/legends, formula plates, "
            "recap of other slides.\n\n"
        )
    if role == "closing":
        core = str(slide.get("core_message") or "").strip() or _ix_field_from_pack(
            pack, "Core message"
        )
        return (
            "## Closing / thank-you plate (HARD) — dedicated close prompt\n"
            "This is a CLOSING PLATE, NOT a content slide with a header.\n"
            "Forbidden compositions (reject these):\n"
            "- Content-header pattern: small title + rule + recap body/cards\n"
            "- Bullet recap, metrics dumps, labeled diagrams from prior slides\n\n"
            "Required composition:\n"
            "- Large closing line (**48–72px**): "
            f"{title or 'Thank you'} — centered or strong left hero, "
            "vertically dominant (not a top header band)\n"
            "- One short takeaway under it (≤2 lines), not a bullet list\n"
            "- Full-bleed quiet atmosphere: tint panel, geometric motif, or "
            "gradient mass — unlabeled only\n"
            "- Leave generous margin; sparse is correct; no card grid\n"
            "- Do not paint page numbers (pipeline injects n/N)\n\n"
            "Paint ONLY these strings — nothing else as text:\n"
            f"- Closing title: {title or 'Thank you'}\n"
            f"- Takeaway line: {core or '(one memorable takeaway)'}\n"
            "- FORBIDDEN: recap bullets, contribution lists, labeled diagrams, "
            "HERO eyebrows, metrics dumps from prior slides.\n\n"
        )
    return ""


def _table_json_for_prompt(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    headers = payload.get("headers") or payload.get("columns") or []
    rows = payload.get("rows") or []
    head_cells: list[str] = []
    for cell in headers:
        if isinstance(cell, dict):
            head_cells.append(str(cell.get("text") or "").strip())
        else:
            head_cells.append(str(cell or "").strip())
    body_rows: list[list[str]] = []
    for row in rows[:24]:
        if not isinstance(row, (list, tuple)):
            continue
        body_rows.append(
            [
                str(c.get("text") if isinstance(c, dict) else c or "").strip()
                for c in row
            ]
        )
    try:
        return json.dumps(
            {"headers": head_cells, "rows": body_rows},
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        return ""


def build_executor_slide_prompt(
    *,
    slide: dict[str, Any],
    spec_lock_md: str,
    design_spec_md: str = "",
    prior_summary: str = "",
    prior_modes: str = "",
    prior_diary: str = "",
    design_reference_brief: str = "",
    layout=None,
    table_render_mode: str = "exact",
    table_payload: dict[str, Any] | None = None,
    craft_block: str = "",
    art_direction_block: str = "",
    layout_plan: dict[str, Any] | None = None,
) -> str:
    """Soft page-closure user prompt — no exclusive AABB recipe law."""
    del layout, table_render_mode  # retired hard-geometry args
    try:
        from tasks.executor_modes import apply_soft_pattern, soft_pattern_brief
    except ImportError:  # pragma: no cover
        from executor_modes import apply_soft_pattern, soft_pattern_brief  # type: ignore
    try:
        from tasks.deck_prompt_context import (
            craft_compact,
            extract_ix_page,
            lock_compact,
            sot_compact,
        )
    except ImportError:  # pragma: no cover
        from deck_prompt_context import (  # type: ignore
            craft_compact,
            extract_ix_page,
            lock_compact,
            sot_compact,
        )

    pack = extract_ix_page(
        design_spec_md,
        int(slide.get("slide") or 0),
        body_md_fallback=str(slide.get("body_md") or ""),
    )
    if not pack.strip():
        pack = extract_executor_design_pack(
            design_spec_md,
            int(slide.get("slide") or 0),
            body_md_fallback=str(slide.get("body_md") or ""),
        )
    apply_soft_pattern(slide)
    pattern = str(slide.get("visualization") or "free_composition")
    page_role = str(slide.get("page_role") or slide.get("role") or "content")
    rhythm = str(slide.get("page_rhythm") or "")
    structure = str(slide.get("structure_atom") or "")
    audience = str(slide.get("audience_move") or "")

    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    body = str(content.get("BODY") or slide.get("content_blocks") or "").strip()
    core = str(slide.get("core_message") or "").strip() or _ix_field_from_pack(
        pack, "Core message"
    )
    ix_bullets = _ix_content_bullets_from_pack(pack)
    check_text = "\n".join(ix_bullets) if ix_bullets else body
    instructional = _content_is_instructional(check_text)

    page = f"{int(slide['slide'])}"
    if slide.get("total_slides"):
        page = f"{page}/{int(slide['total_slides'])}"

    role = str(slide.get("role") or "content").strip().casefold()
    bound_fig = str(slide.get("figure_id") or "").strip()
    if bound_fig.casefold() in {"", "none", "null", "n/a", "-"}:
        bound_fig = ""
    bound_tbl = str(slide.get("table_id") or "").strip()
    if bound_tbl.casefold() in {"", "none", "null", "n/a", "-"}:
        bound_tbl = ""

    role_section = _role_prompt_section(slide, pack=pack)
    pack_ok = bool(pack.strip()) and (
        "## IX. Content Outline" in pack
        or str(slide.get("body_md") or "").strip() in pack
    )
    if pack_ok:
        pack_section = (
            "## design_spec.md (this-slide §IX)\n" f"{pack.rstrip()}\n\n"
        )
    else:
        pack_section = (
            "## This slide IR\n"
            f"- Title: {slide.get('title')}\n"
            f"- Content: {body or '(none)'}\n"
            f"- Core message: {core or '(none)'}\n"
            f"- Layout intent: {slide.get('layout_intent') or 'none'}\n"
            f"- Visual job: {slide.get('visual_job') or 'none'}\n\n"
        )

    sot_snip = sot_compact(design_reference_brief)
    sot_block = (
        f"## Design SoT (compact)\n{sot_snip}\n\n" if sot_snip else ""
    )
    lock_snip = lock_compact(spec_lock_md)
    craft_snip = craft_compact(craft_block) if craft_block else ""

    _has_formula_early = bool(
        str(slide.get("formula") or slide.get("formula_tex") or "").strip()
    )
    host_bound = bool(bound_fig or bound_tbl or _has_formula_early)
    if role in {"title", "hero", "closing"}:
        soft_fields = (
            "## Soft composition (plate — defer to Title/Closing HARD)\n"
            f"- page_role: {page_role}\n"
            f"- visualization/pattern: {pattern} (atmosphere only; no content cards)\n"
            "- Compose a full-bleed title/closing event page — "
            "never a content slide with a header rule.\n\n"
        )
    elif host_bound:
        soft_fields = (
            "## HARD ownership (host-bound — shells + host monopoly)\n"
            f"- page_role: {page_role}\n"
            f"- visualization/pattern: {pattern}\n"
            f"- pattern tip: {soft_pattern_brief(pattern)}\n"
            f"- page_rhythm: {rhythm or '(unset)'}\n"
            f"- structure_atom: {structure or '(unset)'}\n"
            f"- audience_move: {audience or '(unset)'}\n"
            "Fill ONLY pre-painted claim shells (`data-region-id` / "
            "`data-sunairum-claim-shell`) — one claim per shell. "
            "NEVER freehand left claim cards, pale covering plates, pills, "
            "or table chrome inside host AABBs. "
            "Chips: empty g with data-sunairum-chip-spec JSON attr "
            "(DrawingML-safe; NEVER script tags). "
            "Diagrams/node-graphs: g with data-sunairum-diagram-spec JSON attr "
            "in the figure void (pipeline places the widget). "
            "Multi-line copy: dy-stacked tspans OR one claim per shell text.\n\n"
        )
    else:
        soft_fields = (
            "## Soft composition (Defaults — compose within plan regions)\n"
            f"- page_role: {page_role}\n"
            f"- visualization/pattern: {pattern}\n"
            f"- pattern tip: {soft_pattern_brief(pattern)}\n"
            f"- page_rhythm: {rhythm or '(unset)'}\n"
            f"- structure_atom: {structure or '(unset)'}\n"
            f"- audience_move: {audience or '(unset)'}\n"
            "Honor Locked layout plan regions. Do not force identical-width card stacks.\n"
            "Multi-line copy: dy-stacked tspans OR one claim per <text>.\n\n"
        )

    host_block = ""
    if bound_fig:
        host_block += (
            "## Figure host — monopoly\n"
            f"Empty data-sunairum-figure-slot for id `{bound_fig}` "
            "(preferred right band ~640,160,580×400 — never full-bleed).\n"
            "Do not invent the image. LEFT column = fill claim shells only "
            "(no stacked freehand cards, no blank white plates). "
            "Figure void = slot/image (+ optional diagram marker) only.\n\n"
        )
    if bound_tbl:
        try:
            from tasks.table_footprint import footprint_prompt_line, table_footprint_from_payload
        except ImportError:  # pragma: no cover
            from table_footprint import footprint_prompt_line, table_footprint_from_payload  # type: ignore
        band = slide.get("_table_band") if isinstance(slide.get("_table_band"), dict) else None
        if band is None and table_payload is not None:
            band = table_footprint_from_payload(table_payload)
        host_block += (
            "## Table host — JOB / COMPOSITION / GUARDRAILS\n"
            + footprint_prompt_line(band, bound_tbl)
            + "JOB: make the table finding readable (reduction, ranking, cost ratio…). "
            "COMPOSITION: fill LEFT claim shells only (one claim per shell; "
            "chip markers allowed outside host). "
            "GUARDRAILS: empty table host — pipeline injects ranked_bars / top_k / "
            "small grid + insight from real cells. Never freehand table chrome, "
            "row chips, cell text, pale cards, or highlight bars inside the host AABB. "
            "Shorten claims; do not mid-word truncate.\n\n"
        )
    if host_bound and (bound_fig or bound_tbl):
        seed = ""
        try:
            from tasks.host_monopoly import shell_seed_markup

            seed = shell_seed_markup(slide, pack=pack)
        except Exception:
            seed = ""
        if seed.strip():
            host_block += (
                "## Pre-painted claim shells (KEEP groups; fill text only)\n"
                "Include these `<g data-sunairum-claim-shell>` groups in your SVG "
                "and put IR claims into their `data-region-id` texts. "
                "Do not redraw freehand cards in this band.\n"
                f"{seed}\n\n"
            )
            slide["_claim_shell_seed"] = seed
    formula_text, formula_terms, formula_gloss, formula_tex = _formula_fields_from_slide(
        slide, pack
    )
    if formula_text or formula_tex:
        href = str(slide.get("_formula_png_href") or slide.get("_formula_png_data_uri") or "")
        band = slide.get("_formula_band") if isinstance(slide.get("_formula_band"), dict) else {}
        # Echo sanitized Unicode form only — never raw TeX delimiters in the prompt.
        eq_ref = formula_text or formula_tex
        host_block += (
            "## Formula slide — JOB / COMPOSITION / GUARDRAILS\n"
            "JOB: explain what the equation does (trade-off, weights, constraints) "
            "with per-symbol term cards filling the canvas under/beside the host.\n"
            "COMPOSITION: full-width compact formula band (~96px) under title; then a "
            "row/grid — optional 1–2 short takeaways LEFT; RIGHT (or 2×N grid) holds "
            "one card per symbol/term (label + ≤2 short sentences). Ban empty right half "
            "when terms exist. ≥1 non-rect motif; Fill Contract vivid.\n"
            "GUARDRAILS: leave formula-host EMPTY for pipeline MathML inject. "
            "Never typeset the equation as HTML text inside the host; never emit "
            "\\( \\) \\[ \\] or $…$. Do not draw a thick rule through the subtitle.\n"
        )
        if href:
            host_block += (
                f"- Rendered PNG href: `{href}` "
                f"(≈{float(slide.get('_formula_png_width') or 640):g}×"
                f"{float(slide.get('_formula_png_height') or 90):g})\n"
            )
        if band:
            host_block += (
                f"- Reserved band hint: translate("
                f"{band.get('x', 60)},{band.get('y', 160)}) "
                f"w={band.get('w', 1160)} h={band.get('h', 240)}\n"
            )
        host_block += f"- Equation reference (do not paint): {eq_ref}\n"
        if formula_terms:
            host_block += (
                "- Terms — paint as visible term cards filling space under/beside the "
                f"formula (symbol + short explanation). Prefer right column or 2×N grid; "
                f"ban empty right half: {formula_terms}\n"
            )
        if formula_gloss:
            host_block += (
                "- Gloss — use these short explanations on the term cards (grounded; "
                f"do not invent values): {formula_gloss}\n"
            )
        host_block += "\n"

    instructional_note = ""
    if instructional and role not in {"title", "hero", "closing"}:
        lede = core or "(short audience bullets; ban Introduce/Explain openers)"
        instructional_note = (
            "## Instructional Content guard\n"
            "§IX Content looks like speaker cues — brief only; "
            f"paintable lede: {lede}\n\n"
        )

    human_fb = str(slide.get("human_feedback") or "").strip()
    human_feedback_block = (
        f"## Human feedback\n{human_fb}\n\n" if human_fb else ""
    )

    diary = prior_diary.strip() or prior_modes.strip() or "(none)"
    if role in {"title", "hero", "closing"}:
        variety = (
            f"## Prior composition diary\n{diary}\n"
            "Plate pages may echo palette, but must stay full-bleed event covers — "
            "never clone a mid-deck content-header layout.\n\n"
        )
    else:
        variety = (
            f"## Prior composition diary\n{diary}\n"
            "Prefer a different motif than the last pages.\n\n"
        )

    plan = layout_plan if isinstance(layout_plan, dict) else None
    if plan is None and isinstance(slide.get("_layout_plan"), dict):
        plan = slide["_layout_plan"]
    plan_block = ""
    if plan:
        try:
            from tasks.slide_layout_plan import format_layout_plan_block
        except ImportError:  # pragma: no cover
            from slide_layout_plan import format_layout_plan_block  # type: ignore
        plan_block = format_layout_plan_block(plan)

    # Body-panel AABB block from layout plan body/claim regions (was dead).
    body_panels_block = ""
    if plan and _wants_body_panels(pack=pack, slide=slide) >= 2:
        try:
            from types import SimpleNamespace

            regions = []
            for reg in plan.get("regions") or []:
                if not isinstance(reg, dict):
                    continue
                regions.append(
                    SimpleNamespace(
                        role=str(reg.get("role") or ""),
                        x=float(reg.get("x") or 0),
                        y=float(reg.get("y") or 0),
                        w=float(reg.get("w") or 0),
                        h=float(reg.get("h") or 0),
                    )
                )
            layout_obj = SimpleNamespace(regions=regions)
            body_panels_block = _format_body_panels_block(
                layout_obj, pack=pack, slide=slide
            )
        except Exception:
            body_panels_block = ""

    return (
        f"## Executor HTML contract\n"
        "Author ONE complete Constrained HTML page (CSS canvas 1280×720). "
        "Leave bound table/chart/formula/figure hosts empty for Intent inject "
        "(except place pre-rendered formula PNG when href is provided).\n"
        "Artifacts: html_output/ → ir/ → preview/; never write svg_output/.\n"
        "Use CSS tokens for canvas/type/spacing; do not author SVG viewBox.\n\n"
        f"{plan_block}"
        f"{body_panels_block}"
        f"{pack_section}"
        f"{human_feedback_block}"
        f"{role_section}"
        f"{instructional_note}"
        f"{soft_fields}"
        f"{craft_snip or craft_block}"
        f"{art_direction_block}"
        f"{host_block}"
        f"{variety}"
        f"## spec_lock (compact)\n{lock_snip or spec_lock_md[:900]}\n\n"
        f"{sot_block}"
        f"## Prior slides summary\n{prior_summary or '(none)'}\n\n"
        f"## Bindings\n"
        f"- Number: P{int(slide['slide']):02d}\n"
        f"- Role: {role}\n"
        f"- Bound figure: {bound_fig or '(none)'}\n"
        f"- Bound table: {bound_tbl or '(none)'}\n"
        f"- Page footer (do NOT paint — pipeline injects): {page}\n"
    )


def apply_human_feedback_to_slide(
    slide: dict[str, Any],
    feedback: str,
    *,
    call_text: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Attach human feedback and optionally revise slide IR for rematerialize."""
    text = " ".join(str(feedback or "").split()).strip()
    if not text:
        return slide
    slide["human_feedback"] = text
    fb = text.casefold()

    def _shorten_cards(items: list[Any], *, limit: int = 140) -> list[Any]:
        out: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                body = str(item.get("body") or item.get("text") or "").strip()
                if len(body) > limit:
                    item = {**item, "body": body[: limit - 1].rstrip() + "…"}
                out.append(item)
            else:
                out.append(item)
        return out

    if re.search(r"\b(tighten|shorter|concise|kısa)\b", fb):
        cards = slide.get("cards") if isinstance(slide.get("cards"), list) else []
        steps = slide.get("steps") if isinstance(slide.get("steps"), list) else []
        if cards:
            slide["cards"] = _shorten_cards(cards, limit=120)
        if steps:
            slide["steps"] = _shorten_cards(steps, limit=120)
        content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
        body = str(content.get("BODY") or "").strip()
        if len(body) > 220:
            content = {**content, "BODY": body[:219].rstrip() + "…"}
            slide["content"] = content

    if re.search(r"\b(fix overlap|overlap|çakış)\b", fb):
        # Prefer hard-region modes that clamp body away from assets.
        if str(slide.get("figure_id") or "").strip():
            slide["executor_mode"] = slide.get("executor_mode") or "split_figure"
            slide["layout_recipe"] = "title_left_copy_right_figure"
        elif str(slide.get("table_id") or "").strip():
            slide["executor_mode"] = slide.get("executor_mode") or "split_table"
            slide["layout_recipe"] = "title_left_copy_right_table"

    if call_text is not None:
        try:
            prompt = (
                "Revise this slide IR JSON for a rematerialize. Apply the human feedback "
                "as HARD constraints for the Executor HTML author. "
                "Return ONLY JSON with optional keys: title, callout, body, cards "
                "(array of {title,body}), steps (array of {title,body}), layout_recipe, "
                "executor_mode. "
                "Keep figure_id/table_id bindings unchanged. Never return SVG.\n\n"
                f"FEEDBACK:\n{text}\n\n"
                f"SLIDE:\n{json.dumps({k: slide.get(k) for k in ('title', 'callout', 'cards', 'steps', 'content', 'figure_id', 'table_id', 'layout_intent', 'core_message', 'layout_recipe', 'executor_mode')}, ensure_ascii=False)[:7000]}\n"
            )
            raw = str(call_text(
                "You revise presentation slide IR for the Executor. Output JSON only. Never SVG.",
                prompt,
            ) or "").strip()
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                patch = json.loads(match.group(0))
                if isinstance(patch, dict):
                    if patch.get("title"):
                        slide["title"] = str(patch["title"]).strip()
                    if patch.get("callout") is not None:
                        slide["callout"] = str(patch.get("callout") or "").strip()
                    if patch.get("body") is not None:
                        content = (
                            slide.get("content")
                            if isinstance(slide.get("content"), dict)
                            else {}
                        )
                        slide["content"] = {
                            **content,
                            "BODY": str(patch.get("body") or "").strip(),
                        }
                    if isinstance(patch.get("cards"), list) and patch["cards"]:
                        slide["cards"] = patch["cards"]
                    if isinstance(patch.get("steps"), list) and patch["steps"]:
                        slide["steps"] = patch["steps"]
                    if patch.get("layout_recipe"):
                        slide["layout_recipe"] = str(patch["layout_recipe"]).strip()
                    if patch.get("executor_mode"):
                        slide["executor_mode"] = str(patch["executor_mode"]).strip()
        except Exception as error:
            print(f"[free_design] feedback IR revise skipped: {error}")
    return slide


_LOCK_DRIFT_FACES = (
    "source sans",
    "source serif",
    "inter",
    "roboto",
)


def _normalize_lock_face(name: str) -> str:
    """Primary family token; drop trailing version digits (Source Sans 3 → source sans)."""
    primary = str(name or "").split(",")[0].strip().strip("\"'")
    primary = re.sub(r"\s+\d+(\.\d+)?\s*$", "", primary)
    return primary.casefold().strip()


def font_drift_vs_lock(
    svg: str,
    *,
    lock_title: str,
    lock_body: str,
) -> list[str]:
    """Flag invented default faces only when they are not the resolved lock.

    Allows Source Sans / Source Serif when the lock names them (including
    versioned forms like Source Sans 3 / Source Serif 4).
    Advisory only after mechanical rewrite — not a brain-retry driver.
    """
    if not svg:
        return []
    allowed = {
        key
        for key in (_normalize_lock_face(lock_title), _normalize_lock_face(lock_body))
        if key
    }
    if not allowed:
        return []

    def _allowed(face_key: str) -> bool:
        if face_key in allowed:
            return True
        return any(
            face_key == a
            or face_key.startswith(f"{a} ")
            or a.startswith(f"{face_key} ")
            or face_key.startswith(a)
            or a.startswith(face_key)
            for a in allowed
            if len(a) >= 4
        )

    for match in re.finditer(r'font-family="([^"]+)"', svg, flags=re.I):
        face_key = _normalize_lock_face(match.group(1))
        if not face_key or face_key in {
            "serif",
            "sans-serif",
            "monospace",
            "cursive",
            "fantasy",
            "system-ui",
        }:
            continue
        if _allowed(face_key):
            continue
        if any(drift in face_key for drift in _LOCK_DRIFT_FACES):
            title = str(lock_title or "").split(",")[0].strip() or "Georgia"
            body = str(lock_body or "").split(",")[0].strip() or "Arial"
            return [f"font_drift: use lock faces ({title}/{body})"]
    return []


# Hard layout integrity — brain-retry + fail-closed (not advisory).
_HARD_INTEGRITY_KEYS = (
    "text_overlaps",
    "ink_through_text",
    "shape_over_title",
    "callout_on_body",
    "table_overlap",
    "table_host_freehand",
    "figure_host_freehand",
    "stacked_left_cards",
    "empty_claim_shells",
    "font_drift",
    "host_claim_overlap",
    "left_panel_overflow",
    "formula_sparse_right",
    "formula_missing_term_cards",
    "formula_title_clip",
    "host_canvas_overflow",
    "host_left_of_lane",
    "canvas_bottom_overflow",
    "canvas_safe_inset",
    "formula_term_ungrounded",
    "formula_term_mismatch",
)
# Soft / calibrated — logged only; never brain-retry or refuse-write alone.
_SOFT_INTEGRITY_KEYS = (
    "text_overflow",
)


def _is_brain_worthy_issue(issue: str) -> bool:
    """Allowlist: illegal SVG + hard layout integrity may burn a paint retry."""
    low = str(issue or "").casefold()
    if not low:
        return False
    keys = (
        "missing_svg",
        "export_gate",
        "forbidden_foreignobject",
        "/>xt",
        "nested <text",
        "nested text",
        "illegal svg",
        "mid-tag",
        "tspans only inside",
    ) + _HARD_INTEGRITY_KEYS
    return any(k in low for k in keys)


def _brain_worthy_issues(issues: list[str]) -> list[str]:
    return [i for i in issues if _is_brain_worthy_issue(i)]


def _issue_key(issue: str) -> str:
    return str(issue or "").split(":", 1)[0].casefold().strip()


def _point_in_aabb(
    x: float, y: float, box: tuple[float, float, float, float] | None
) -> bool:
    if box is None:
        return False
    bx, by, bw, bh = box
    return bx - 4 <= x <= bx + bw + 4 and by - 4 <= y <= by + bh + 4


def _host_aabbs_for_slide(
    svg: str, slide: dict[str, Any]
) -> list[tuple[float, float, float, float]]:
    """Table/figure host boxes Intent will own (skip pre-Intent freehand there)."""
    boxes: list[tuple[float, float, float, float]] = []
    tid = str((slide or {}).get("table_id") or "").strip()
    fid = str((slide or {}).get("figure_id") or "").strip()
    if tid and tid.casefold() not in {"none", "null", "n/a", "-"}:
        try:
            from tasks.intent_hosts import table_host_aabb
        except ImportError:  # pragma: no cover
            from intent_hosts import table_host_aabb  # type: ignore
        try:
            boxes.append(tuple(table_host_aabb(svg)))  # type: ignore[arg-type]
        except Exception:
            pass
    if fid and fid.casefold() not in {"none", "null", "n/a", "-"}:
        try:
            from tasks.host_monopoly import figure_host_aabb
        except ImportError:  # pragma: no cover
            from host_monopoly import figure_host_aabb  # type: ignore
        try:
            box = figure_host_aabb(svg)
            if box is not None:
                boxes.append(tuple(box))  # type: ignore[arg-type]
        except Exception:
            pass
    return boxes


def _count_hard_text_overlaps(svg: str) -> int:
    """Error-severity text overlaps (coverage ≥ 2%), hosts excluded."""
    if not svg:
        return 0
    try:
        from tasks.deck_qa import _svg_text_records, _text_overlap_issues
    except ImportError:  # pragma: no cover
        from deck_qa import _svg_text_records, _text_overlap_issues  # type: ignore
    try:
        records = _svg_text_records(svg, include_native_hosts=False)
        issues = _text_overlap_issues(0, records)
    except Exception:
        return 0
    return sum(
        1
        for item in issues
        if str(item.get("severity") or "") == "error"
        or float(item.get("overlap_coverage") or 0) >= 0.02
    )


def _layout_integrity_issues(
    svg: str,
    slide: dict[str, Any] | None = None,
    *,
    phase: str = "final",
    lock_title: str = "",
    lock_body: str = "",
    font_locked: bool = False,
) -> tuple[list[str], list[str]]:
    """Return (hard_issues, soft_issues) for layout integrity.

    phase:
      - pre_intent: freehand collisions only (not host residuals Intent owns)
      - post_inject / final: full hard set; font_drift only when font_locked
    """
    hard: list[str] = []
    soft: list[str] = []
    slide = slide if isinstance(slide, dict) else {}
    phase_key = str(phase or "final").casefold()
    if not svg or "<svg" not in svg.casefold():
        return hard, soft

    # Freehand collision classes (all phases).
    try:
        n = _count_hard_text_overlaps(svg)
        if n and phase_key == "pre_intent":
            # Drop overlaps wholly inside hosts Intent will wipe.
            host_boxes = _host_aabbs_for_slide(svg, slide)
            if host_boxes:
                try:
                    from tasks.svg_geometry import parse_texts, aabb_intersection_area
                except ImportError:  # pragma: no cover
                    from svg_geometry import (  # type: ignore
                        parse_texts,
                        aabb_intersection_area,
                    )
                items = parse_texts(svg)
                residual = 0
                for i, a in enumerate(items):
                    ax = float(a.get("x") or 0)
                    ay = float(a.get("y") or 0)
                    if any(_point_in_aabb(ax, ay, b) for b in host_boxes):
                        continue
                    for b in items[i + 1 :]:
                        bx = float(b.get("x") or 0)
                        by = float(b.get("y") or 0)
                        if any(_point_in_aabb(bx, by, hb) for hb in host_boxes):
                            continue
                        if aabb_intersection_area(a["box"], b["box"]) > 4.0:
                            residual += 1
                n = residual
        if n:
            hard.append(f"text_overlaps:{n}: separate colliding labels")
    except Exception:
        pass

    try:
        hard.extend(_ink_through_text_qa_issues(svg))
    except Exception:
        pass

    try:
        from tasks.layout_mechanical import (
            callout_on_body_issues,
            shape_over_title_issues,
        )
    except ImportError:  # pragma: no cover
        from layout_mechanical import (  # type: ignore
            callout_on_body_issues,
            shape_over_title_issues,
        )
    try:
        hard.extend(shape_over_title_issues(svg))
    except Exception:
        pass
    try:
        hard.extend(callout_on_body_issues(svg))
    except Exception:
        pass

    # Soft: overflow advisory (high-confidence canvas escapes only as soft count).
    try:
        overflows = _count_text_overflows_in_svg(svg)
        if overflows:
            soft.append(
                f"text_overflow:{overflows}: wrap or shorten copy inside its "
                "card/column; keep ≥12px inset"
            )
    except Exception:
        pass

    # Host residuals — not pre_intent (Intent / monopoly owns them next).
    if phase_key in {"post_inject", "final"}:
        try:
            from tasks.host_monopoly import host_quality_gate_issues
        except ImportError:  # pragma: no cover
            from host_monopoly import host_quality_gate_issues  # type: ignore
        try:
            for issue in host_quality_gate_issues(svg, slide):
                key = _issue_key(issue)
                if key == "text_overlaps" and any(
                    _issue_key(h) == "text_overlaps" for h in hard
                ):
                    continue
                hard.append(issue)
        except Exception:
            pass
        if str(slide.get("table_id") or "").strip():
            try:
                from tasks.slide_renderer import count_freehand_in_table_aabb
                from tasks.intent_hosts import table_host_aabb
                from tasks.host_monopoly import count_freehand_shapes_in_aabb
            except ImportError:  # pragma: no cover
                from slide_renderer import count_freehand_in_table_aabb  # type: ignore
                from intent_hosts import table_host_aabb  # type: ignore
                from host_monopoly import count_freehand_shapes_in_aabb  # type: ignore
            try:
                box = table_host_aabb(svg)
                under = count_freehand_in_table_aabb(svg)
                shapes = count_freehand_shapes_in_aabb(svg, box)
                if under or shapes:
                    if not any(
                        _issue_key(h) in {"table_host_freehand", "table_overlap"}
                        for h in hard
                    ):
                        hard.append(
                            f"table_overlap:text={under}:shapes={shapes}: "
                            f"keep narrative outside table AABB {box}"
                        )
            except Exception:
                pass

    if font_locked and (lock_title or lock_body):
        try:
            hard.extend(
                font_drift_vs_lock(svg, lock_title=lock_title, lock_body=lock_body)
            )
        except Exception:
            pass

    # De-dupe while preserving order.
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return _dedupe(hard), _dedupe(soft)


def _record_layout_fail(
    placement_live: dict[str, Any],
    number: int,
    issues: list[str],
    *,
    phase: str,
) -> None:
    """Surface layout fail-closed so incomplete decks are not quiet successes."""
    msg = f"slide {number} layout FAIL CLOSED ({phase}): {'; '.join(issues[:4])}"
    placement_live.setdefault("errors", []).append(msg)
    placement_live["layout_failed"] = True
    fails = placement_live.setdefault("layout_fail_slides", [])
    if number not in fails:
        fails.append(number)
    placement_live.setdefault("qa_issues", []).append(
        {"slide": number, "issues": list(issues), "phase": phase, "hard": True}
    )
    print(f"[free_design] P{number:02d} {msg}")


def _count_text_overflows_in_svg(svg: str) -> int:
    """Card/canvas text overflow count (deck_qa heuristics)."""
    try:
        from tasks.deck_qa import _svg_rect_records, _svg_text_records
    except ImportError:  # pragma: no cover
        from deck_qa import _svg_rect_records, _svg_text_records  # type: ignore
    try:
        records = _svg_text_records(svg)
        rects = _svg_rect_records(svg)
    except Exception:
        return 0
    n = 0
    # Canvas margin escapes (viewBox 1280×720).
    for record in records:
        b = record.get("bounds")
        if not b or len(b) < 4:
            continue
        if b[0] < -2 or b[1] < -2 or b[2] > 1282 or b[3] > 722:
            n += 1
    panels = [
        rect["bounds"]
        for rect in rects
        if any(token in rect.get("tokens", ()) for token in ("card", "panel"))
        and rect["bounds"][2] - rect["bounds"][0] >= 120
        and rect["bounds"][3] - rect["bounds"][1] >= 60
    ]
    for panel in panels:
        for record in records:
            bb = record.get("baseline")
            if not bb or len(bb) < 2:
                continue
            if not (panel[0] <= bb[0] <= panel[2] and panel[1] <= bb[1] <= panel[3]):
                continue
            bounds = record.get("bounds")
            if not bounds:
                continue
            if (
                bounds[0] < panel[0] - 1
                or bounds[2] > panel[2] + 1
                or bounds[1] < panel[1] - 1
                or bounds[3] > panel[3] + 1
            ):
                n += 1
    return n


def _card_anatomy_qa_issues(svg: str) -> list[str]:
    """Detect inverted card titles / peer title drift → spatial replan."""
    issues: list[str] = []
    if not svg or "<text" not in svg.casefold():
        return issues
    try:
        from tasks.svg_geometry import parse_texts, _attr_float, _RECT_RE
    except ImportError:  # pragma: no cover
        from svg_geometry import parse_texts, _attr_float, _RECT_RE  # type: ignore

    cards: list[tuple[float, float, float, float]] = []
    for match in _RECT_RE.finditer(svg):
        attrs = match.group(1) or ""
        x = _attr_float(attrs, "x")
        y = _attr_float(attrs, "y")
        w = _attr_float(attrs, "width")
        h = _attr_float(attrs, "height")
        if None in (x, y, w, h):
            continue
        assert x is not None and y is not None and w is not None and h is not None
        if w < 140.0 or h < 80.0 or w > 900.0 or h > 480.0:
            continue
        cards.append((x, y, w, h))
    if len(cards) < 1:
        return issues

    items = parse_texts(svg)
    title_ys: list[float] = []
    for cx, cy, cw, ch in cards:
        members = [
            item
            for item in items
            if cx - 4 <= item["x"] <= cx + cw + 4
            and cy - 8 <= item["y"] <= cy + ch + 12
            and 'data-sunairum-page-number="' not in (item.get("attrs") or "")
        ]
        if len(members) < 2:
            continue
        # Title: bold or largest short label; body: smaller / longer / multi-line.
        def _is_titleish(item: dict[str, Any]) -> bool:
            attrs = (item.get("attrs") or "").casefold()
            bold = (
                'font-weight="700"' in attrs
                or 'font-weight="bold"' in attrs
                or "font-weight:700" in attrs
            )
            plain = str(item.get("plain") or "")
            short = len(plain) <= 48 and "<tspan" not in (item.get("body") or "").casefold()
            return bool(bold or (short and float(item.get("fs") or 0) >= 16.0))

        titles = [m for m in members if _is_titleish(m)]
        bodies = [m for m in members if not _is_titleish(m)]
        if not titles or not bodies:
            # Fall back: largest fs vs smaller multi-line / longer copy.
            ordered = sorted(members, key=lambda m: (-float(m.get("fs") or 0), len(str(m.get("plain") or ""))))
            titles = [ordered[0]]
            bodies = ordered[1:]
        # Prefer bold/larger titleish even when painted below body.
        title = sorted(
            titles,
            key=lambda m: (
                -float(m.get("fs") or 0.0),
                len(str(m.get("plain") or "")),
            ),
        )[0]
        body = max(bodies, key=lambda m: float(m.get("y") or 0))
        title_ys.append(float(title["y"]))
        # Inverted: title baseline below body baseline by >8px.
        if float(title["y"]) > float(body["y"]) + 8.0:
            snippet = str(title.get("plain") or "")[:40]
            issues.append(
                f"card_title_inverted:{snippet}: title below body — replan card anatomy"
            )

    if len(title_ys) >= 2:
        median = sorted(title_ys)[len(title_ys) // 2]
        for ty in title_ys:
            if abs(ty - median) > 40.0:
                issues.append(
                    f"card_title_inverted:peer_drift:{ty:g} vs median {median:g}: "
                    "peer cards must share title baseline"
                )
                break
    return issues[:4]


def _ink_through_text_qa_issues(svg: str) -> list[str]:
    """Flag horizontal line/path ink cutting through glyph AABBs."""
    issues: list[str] = []
    if not svg:
        return issues
    try:
        from tasks.svg_reflow import _parse_texts, tbox_hits_hline, _attr_float
    except ImportError:  # pragma: no cover
        from svg_reflow import _parse_texts, tbox_hits_hline, _attr_float  # type: ignore

    texts = _parse_texts(svg)
    if not texts:
        return issues
    # Skip short labels / page chrome.
    bodies = [
        t
        for t in texts
        if len(str(t.get("plain") or "")) >= 8
        and 'data-sunairum-page-number="' not in (t.get("attrs") or "")
    ]
    hits = 0
    for match in re.finditer(r"<line\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1) or ""
        if "data-sunairum-" in attrs.casefold():
            continue
        x1 = _attr_float(attrs, "x1")
        y1 = _attr_float(attrs, "y1")
        x2 = _attr_float(attrs, "x2")
        y2 = _attr_float(attrs, "y2")
        if None in (x1, y1, x2, y2):
            continue
        assert x1 is not None and y1 is not None and x2 is not None and y2 is not None
        if abs(y1 - y2) >= 2.0 or abs(x2 - x1) < 24.0:
            continue
        if any(tbox_hits_hline(t, y1, min(x1, x2), max(x1, x2)) for t in bodies):
            hits += 1
    for match in re.finditer(r"<path\b([^>]*)/?>", svg, flags=re.I):
        attrs = match.group(1) or ""
        if "data-sunairum-" in attrs.casefold() or "data-pptx-" in attrs.casefold():
            continue
        dm = re.search(r'\bd="([^"]*)"', attrs)
        if not dm:
            continue
        d = (dm.group(1) or "").strip()
        hm = re.match(
            r"([Mm])\s*([-\d.]+)[\s,]+([-\d.]+)\s*([Hh])\s*([-\d.]+)\s*$",
            d,
        )
        if not hm:
            continue
        x0, y0 = float(hm.group(2)), float(hm.group(3))
        h_cmd, h_val = hm.group(4), float(hm.group(5))
        x1 = x0 + h_val if h_cmd == "h" else h_val
        if abs(x1 - x0) < 24.0:
            continue
        if any(tbox_hits_hline(t, y0, min(x0, x1), max(x0, x1)) for t in bodies):
            hits += 1
    if hits:
        issues.append(
            f"ink_through_text:{hits}: remove axis/path through captions or replan motif"
        )
    return issues


def _takeaway_ellipsis_qa_issues(svg: str) -> list[str]:
    """IR takeaway claims must not use mid-sentence ellipsis truncation."""
    if not svg:
        return []
    # Prefer tagged takeaway bands; fall back to lower-canvas TAKEAWAY label neighbors.
    chunks: list[str] = []
    for match in re.finditer(
        r'<g\b[^>]*\bdata-sunairum-(?:takeaway|footer-band|table-insight)="1"[^>]*>'
        r"([\s\S]*?)</g>",
        svg,
        flags=re.I,
    ):
        chunks.append(match.group(1) or "")
    if not chunks:
        chunks.append(svg)
    for chunk in chunks:
        if "…" in chunk or "..." in chunk:
            # Ignore decorative ellipsis in labels shorter than a claim.
            for tm in re.finditer(r"<text\b[^>]*>([\s\S]*?)</text>", chunk, flags=re.I):
                plain = re.sub(r"<[^>]+>", " ", tm.group(1) or "")
                plain = re.sub(r"\s+", " ", plain).strip()
                if ("…" in plain or "..." in plain) and len(plain) >= 24:
                    return [
                        "takeaway_ellipsis: wrap/grow takeaway band — never truncate IR claims"
                    ]
    return []


def _label_zone_qa_issues(svg: str, slide: dict[str, Any]) -> list[str]:
    """Flag body-length copy parked in label/callout / host_void plan regions."""
    plan = slide.get("_layout_plan") if isinstance(slide.get("_layout_plan"), dict) else None
    if not plan:
        return []
    try:
        from tasks.svg_geometry import parse_texts
        from tasks.slide_layout_plan import _NO_BODY_ROLES
    except ImportError:  # pragma: no cover
        from svg_geometry import parse_texts  # type: ignore
        from slide_layout_plan import _NO_BODY_ROLES  # type: ignore
    zones = [
        r
        for r in (plan.get("regions") or [])
        if isinstance(r, dict) and str(r.get("role") or "").casefold() in _NO_BODY_ROLES
    ]
    if not zones:
        return []
    issues: list[str] = []
    for item in parse_texts(svg):
        plain = str(item.get("plain") or "")
        words = len(plain.split())
        if words <= 6 and float(item.get("fs") or 0) <= 18:
            continue
        x, y = float(item["x"]), float(item["y"])
        for z in zones:
            zx, zy, zw, zh = (
                float(z["x"]),
                float(z["y"]),
                float(z["w"]),
                float(z["h"]),
            )
            if zx <= x <= zx + zw and zy <= y <= zy + zh:
                role = str(z.get("role") or "zone")
                if role == "host_void" or words > 6:
                    issues.append(
                        f"label_zone_body:{role}:{plain[:40]!r}: "
                        "keep body copy outside no-text / label zones"
                    )
                break
    return issues[:4]


def _missing_slide_title_qa(svg: str, slide: dict[str, Any]) -> list[str]:
    """Table/content slides need a title band (≥28px in y∈[40,120])."""
    role = str(slide.get("role") or "content").casefold()
    if role in {"title", "hero", "closing"}:
        return []
    try:
        from tasks.svg_geometry import parse_texts
    except ImportError:  # pragma: no cover
        from svg_geometry import parse_texts  # type: ignore
    for item in parse_texts(svg):
        if float(item.get("fs") or 0) < 28:
            continue
        if 40.0 <= float(item.get("y") or 0) <= 120.0:
            return []
    if str(slide.get("table_id") or "").strip():
        return [
            "missing_slide_title: need font-size≥28 title in y∈[40,120] "
            "(do not blank title on table pages)"
        ]
    return []


def _executor_qa_issues(svg: str, slide: dict[str, Any], pack: str = "") -> list[str]:
    """Export + pre-Intent freehand integrity for Executor brain retry."""
    del pack
    issues: list[str] = []
    if not svg or "<svg" not in svg.casefold():
        issues.append("missing_svg: output was not a complete <svg>…</svg> document")
        return issues
    # Export gate failures must drive brain retry (never silent recover).
    gated, gate_errors = _gate_svg_for_export(svg, context="author")
    del gated
    issues.extend(gate_errors[:6])
    if "foreignobject" in svg.casefold():
        issues.append("forbidden_foreignObject: use <text>/<tspan> only")
    # Pre-Intent: freehand collisions only (host residuals come post-inject).
    hard, soft = _layout_integrity_issues(svg, slide, phase="pre_intent")
    issues.extend(hard)
    # Soft overflow stays advisory (appended for logs; not brain-worthy).
    issues.extend(soft)
    try:
        issues.extend(_card_anatomy_qa_issues(svg))
    except Exception:
        pass
    try:
        issues.extend(_takeaway_ellipsis_qa_issues(svg))
    except Exception:
        pass
    try:
        issues.extend(_label_zone_qa_issues(svg, slide))
    except Exception:
        pass
    try:
        issues.extend(_missing_slide_title_qa(svg, slide))
    except Exception:
        pass
    # missing_figure_slot / missing_table_slot are mechanical (ensure_asset_hosts)
    # — never brain-retry drivers.
    if str(slide.get("formula") or slide.get("formula_tex") or "").strip():
        if re.search(r"\\\(|\\\[|(?<!\$)\$(?!\$)", svg):
            if re.search(r"<text\b[^>]*>[^<]*\\[\(\[]", svg, flags=re.I):
                issues.append(
                    "raw_tex_in_text: no \\( \\) or $…$ in SVG text; place PNG only"
                )
    return issues


def _post_inject_qa_issues(svg: str, slide: dict[str, Any]) -> list[str]:
    """Hard integrity visible after Intent inject (includes host leftovers)."""
    hard, soft = _layout_integrity_issues(svg, slide, phase="post_inject")
    issues = list(hard) + list(soft)
    if str(slide.get("table_id") or "").strip():
        if 'data-sunairum-table-insight="' not in (svg or "").casefold():
            if "data-sunairum-source-table" in (svg or "").casefold():
                issues.append(
                    "table_insight_protected: missing insight group after Intent inject"
                )
        issues.extend(_missing_slide_title_qa(svg, slide))
    return issues



def _theme_from_palette(color_palette: dict[str, Any] | None) -> dict[str, Any]:
    """Build painter/table/formula theme dicts from the live deck palette + pack tokens."""
    palette = color_palette if isinstance(color_palette, dict) else {}
    tokens = palette.get("design_tokens") if isinstance(palette.get("design_tokens"), dict) else {}
    heading = str(
        palette.get("_heading_family")
        or ((tokens.get("typography") or {}).get("heading") or {}).get("primary")
        or "Georgia"
    )
    body = str(
        palette.get("_body_family")
        or ((tokens.get("typography") or {}).get("body") or {}).get("primary")
        or "Arial"
    )
    try:
        from tasks import theme_agent as _theme_agent

        deck = _theme_agent.DeckTheme(
            palette={
                k: str(v)
                for k, v in palette.items()
                if isinstance(v, str) and str(v).startswith("#")
            },
            heading_family=heading,
            body_family=body,
        )
        return _theme_agent.as_painter_theme(deck, tokens)
    except Exception:
        return {
            "primary": palette.get("primary") or "#1A365D",
            "accent": palette.get("accent") or "#3182CE",
            "ink": palette.get("body_text") or "#1A202C",
            "muted": palette.get("text_secondary") or "#4A5568",
            "surface": palette.get("secondary_bg") or palette.get("background") or "#FFFFFF",
            "card": palette.get("background") or "#FFFFFF",
            "border": palette.get("border") or "#E2E8F0",
            "font_family": f"{body}, sans-serif",
            "title_family": f"{heading}, serif",
        }


def _table_theme_from_palette(color_palette: dict[str, Any] | None) -> dict[str, Any]:
    palette = color_palette if isinstance(color_palette, dict) else {}
    tokens = palette.get("design_tokens") if isinstance(palette.get("design_tokens"), dict) else {}
    try:
        from tasks import theme_agent as _theme_agent

        deck = _theme_agent.DeckTheme(
            palette={
                k: str(v)
                for k, v in palette.items()
                if isinstance(v, str) and str(v).startswith("#")
            },
            heading_family=str(palette.get("_heading_family") or "Georgia"),
            body_family=str(palette.get("_body_family") or "Arial"),
        )
        return _theme_agent.as_table_theme(deck, tokens)
    except Exception:
        return {
            "primary": palette.get("primary") or "#1A365D",
            "accent": palette.get("accent") or "#3182CE",
            "ink": palette.get("body_text") or "#1A202C",
            "muted": palette.get("text_secondary") or "#4A5568",
            "surface": palette.get("background") or "#FFFFFF",
            "zebra": (
                palette.get("accent_tint")
                or palette.get("secondary_bg")
                or "#F5F7FA"
            ),
            "border": palette.get("border") or "#E2E8F0",
            "header_fill": palette.get("primary") or "#1A365D",
            "header_color": "#FFFFFF",
            "font": str(palette.get("_body_family") or "Arial"),
        }


def _formula_theme_from_palette(color_palette: dict[str, Any] | None) -> dict[str, Any]:
    palette = color_palette if isinstance(color_palette, dict) else {}
    tokens = palette.get("design_tokens") if isinstance(palette.get("design_tokens"), dict) else {}
    try:
        from tasks import theme_agent as _theme_agent

        deck = _theme_agent.DeckTheme(
            palette={
                k: str(v)
                for k, v in palette.items()
                if isinstance(v, str) and str(v).startswith("#")
            },
            heading_family=str(palette.get("_heading_family") or "Georgia"),
            body_family=str(palette.get("_body_family") or "Arial"),
        )
        return _theme_agent.as_formula_theme(deck, tokens)
    except Exception:
        return {
            "primary": palette.get("primary") or "#1A365D",
            "ink": palette.get("primary") or "#1A365D",
            "muted": palette.get("text_secondary") or "#4A5568",
            "surface": (
                palette.get("accent_tint")
                or palette.get("secondary_bg")
                or "#F5F7FA"
            ),
            "stroke": palette.get("primary") or "#1A365D",
            "body_text": palette.get("body_text") or "#1A202C",
        }


_LOCK_LANGUAGE_RE = re.compile(r"^-\s*primary_language:\s*(\S+)", re.M)


def _primary_language_from_lock(spec_lock_md: str) -> str:
    """The confirmed deck language, as locked at confirmation time."""
    match = _LOCK_LANGUAGE_RE.search(spec_lock_md or "")
    return match.group(1).strip().strip("\"'") if match else ""


def _materialize_html_slides(
    *,
    slides: list[dict[str, Any]],
    design_spec_md: str,
    storage_dir: str,
    color_palette: dict[str, str],
    budget: AuthoringBudget,
    call_text: Callable[[str, str], str] | None,
    loop=None,
    project_id: str = "",
    write_status=None,
    send_ws_message=None,
    slide_filter: set[int] | None = None,
    design_reference_brief: str = "",
    evidence_bundle: dict[str, Any] | None = None,
    keep_existing: bool = False,
    slide_feedback: dict[int, str] | None = None,
    run_id: str | None = None,
    spec_lock_md: str = "",
) -> dict[str, Any]:
    """HTML materialize path (html_output + preview; Slide IR retired)."""
    # The lock is the only place the confirmed deck language survives to this
    # point, and the visual author needs it: everything it invents on its own —
    # eyebrows, section kickers, figure captions — has no other language signal,
    # so a Turkish deck came back with "ACADEMIC BLUEPRINT · VEHICLE ROUTING"
    # over Turkish body copy.
    primary_language = _primary_language_from_lock(spec_lock_md)
    from tasks.html_flags import ensure_html_dirs, slide_stem
    from tasks.html_pipeline import materialize_html_slide

    dirs = ensure_html_dirs(storage_dir)
    wrapped_call = budget.wrap(call_text) if call_text is not None else None
    # Cover byline: prefer slide authors/affiliations; fall back to confirm_ui furniture.
    instructions_blob = ""
    furniture_blob: dict[str, str] = {}
    result_path = os.path.join(storage_dir, "confirm_ui", "result.json")
    if os.path.isfile(result_path):
        try:
            result_data = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            result_data = {}
        if isinstance(result_data, dict):
            instructions_blob = str(result_data.get("additional_instructions") or "").strip()
            try:
                from tasks.deck_furniture import (
                    furniture_for_title_reinject,
                    resolve_deck_furniture,
                )
            except ImportError:  # pragma: no cover
                from deck_furniture import (  # type: ignore
                    furniture_for_title_reinject,
                    resolve_deck_furniture,
                )
            furniture_blob = furniture_for_title_reinject(
                resolve_deck_furniture(result_data, persist=False),
                instructions_blob,
            )
    authored: list[dict[str, Any]] = []
    targets = [
        slide
        for slide in slides
        if slide_filter is None or int(slide["slide"]) in slide_filter
    ]
    if furniture_blob or instructions_blob:
        # Presenter identity is title-card furniture. A closing slide is
        # "thank you / questions", not a second title card, so pushing the name
        # and affiliation there too printed the same block twice in one deck.
        # Authoring guidance still reaches every bookend; only the visible
        # identity fields are withheld.
        identity_roles = {"title", "hero"}
        for slide in targets:
            role = str(slide.get("role") or "").casefold()
            if role not in {"title", "hero", "closing"}:
                continue
            if instructions_blob and not str(slide.get("additional_instructions") or "").strip():
                slide["additional_instructions"] = instructions_blob
            if role not in identity_roles:
                continue
            presenter = str(furniture_blob.get("presenter") or "").strip()
            affiliation = str(furniture_blob.get("affiliation") or "").strip()
            if presenter and not str(slide.get("authors") or "").strip():
                slide["authors"] = presenter
            if affiliation:
                # Prefer full IEEE affiliation (Tel/city) over a short authored stub.
                current_aff = str(slide.get("affiliations") or "").strip()
                if not current_aff or (
                    len(affiliation) > len(current_aff) + 12
                    and ("tel" in affiliation.casefold() or "isparta" in affiliation.casefold())
                ):
                    slide["affiliations"] = affiliation
    if slide_filter is None:
        targets = sorted(
            targets, key=lambda item: (0 if int(item["slide"]) == 1 else 1, int(item["slide"]))
        )
    total = len(slides)
    prior_diary_bits: list[str] = []
    deck_placement: dict[str, Any] = {"figures": [], "tables": [], "errors": []}

    for slide in targets:
        if _generation_cancelled(storage_dir):
            return {
                "authored": authored,
                "budget_spent": budget.calls_spent,
                "placement_live": deck_placement,
                "enrichment_live": {"attempted": [], "placed": [], "errors": []},
                "ai_enrich_remaining": 0,
                "cancelled": True,
                "html_sot": True,
            }
        number = int(slide["slide"])
        stem = slide_stem(number)
        html_existing = os.path.join(dirs["html_output"], f"{stem}.html")
        feedback_for_slide = ""
        if slide_feedback and number in slide_feedback:
            feedback_for_slide = str(slide_feedback.get(number) or "").strip()
        if (
            keep_existing
            and not feedback_for_slide
            and os.path.isfile(html_existing)
            and os.path.getsize(html_existing) > 64
        ):
            print(f"[html] P{number:02d} skip existing HTML (resume)")
            authored.append({"slide": number, "path": html_existing, "kept": True})
            continue

        try:
            from tasks.content_densify import densify_slide_ir as _densify
        except ImportError:  # pragma: no cover
            from content_densify import densify_slide_ir as _densify  # type: ignore
        _densify(slide)
        slide_title = str(slide.get("title") or f"Slide {number}")
        progress = min(80, 40 + int(40 * (number / max(1, total))))
        if write_status is not None:
            write_status(
                storage_dir,
                "generating",
                progress,
                number,
                total,
                message=f"Authoring HTML slide {number}/{total} ({slide_title})",
                message_key="status_generating_slide",
                title=slide_title,
                run_id=run_id,
            )

        design_ms = 0
        paint_ms = 0
        llm_calls = 0
        native_payloads: dict[str, dict[str, Any]] = {}
        tid = str(slide.get("table_id") or "").strip()
        if tid and tid.casefold() not in {"none", "null", "-"}:
            tbl = _resolve_table_payload(evidence_bundle, tid)
            if tbl:
                native_payloads[tid] = {
                    "columns": tbl.get("columns") or tbl.get("header") or [],
                    "rows": tbl.get("rows") or tbl.get("data") or [],
                    "header_rows": 1,
                }
                # also key as t1 for hosts
                native_payloads["t1"] = native_payloads[tid]
                slide["table"] = native_payloads[tid]
        fid = str(slide.get("figure_id") or "").strip()

        # Ranked bars / comparison columns / chart layouts → chart payloads
        viz = str(slide.get("visualization") or "").casefold()
        layout_intent = str(slide.get("layout_intent") or "").casefold()
        needs_chart = any(
            key in viz or key in layout_intent
            for key in (
                "ranked",
                "bar",
                "chart",
                "comparison_columns",
                "grouped_bar",
                "column_chart",
            )
        )
        if needs_chart:
            from tasks.html_pipeline import resolve_chart_payloads

            cats = slide.get("chart_categories") or []
            series = slide.get("chart_series") or []
            if series:
                native_payloads["c1"] = {
                    "type": "column",
                    "categories": cats,
                    "series": series,
                }
                slide["chart"] = native_payloads["c1"]
            else:
                # Project from evidence tables / slide.chart when available
                probe_html = (
                    '<div data-pptx="chart" data-chart-id="c1"></div>'
                    '<div data-pptx="chart" data-chart-id="c2"></div>'
                    '<div data-pptx="chart" data-chart-id="c3"></div>'
                    if "comparison_columns" in viz or "comparison_columns" in layout_intent
                    else '<div data-pptx="chart" data-chart-id="c1"></div>'
                )
                projected = resolve_chart_payloads(
                    storage_dir=storage_dir,
                    slide=slide,
                    html=probe_html,
                    native_payloads=native_payloads,
                )
                for cid, payload in projected.items():
                    native_payloads[cid] = payload
                if projected:
                    slide["charts"] = projected
                    slide["chart"] = next(iter(projected.values()))
            chart_ids = [
                cid
                for cid in ("c1", "c2", "c3", "c4")
                if cid in native_payloads
            ] or (["c1"] if "c1" in native_payloads else [])
        chart_payload_count = len(
            [key for key in native_payloads if str(key).startswith("c")]
        )
        if chart_payload_count > 3:
            # Scene reserves at most three chart hosts. Dropping the extras costs
            # one visual on one slide; aborting costs the whole deck.
            keep = [key for key in ("c1", "c2", "c3") if key in native_payloads]
            dropped = sorted(set(native_payloads) - set(keep))
            print(
                f"[free_design] slide {slide.get('slide')}: {chart_payload_count} chart payloads "
                f"exceed the three Scene chart hosts; keeping {keep}, dropping {dropped}"
            )
            native_payloads = {key: native_payloads[key] for key in keep}
            chart_ids = [cid for cid in chart_ids if cid in native_payloads]
            if isinstance(slide.get("charts"), dict):
                slide["charts"] = {
                    key: value for key, value in slide["charts"].items() if key in native_payloads
                }
            chart_payload_count = len(keep)
        if needs_chart and chart_payload_count == 0:
            # A visualization suggestion is not a data binding. Without a real
            # chart payload, reserve readable narrative lanes instead of an
            # empty native host (or inviting the LLM to invent values).
            slide["scene_composition"] = "two_column"

        # Native bindings are known before geometry is resolved, so chart/table/
        # figure regions cannot disagree with the final component tree. Scene
        # owns the boxes; the LLM still owns the visual composition inside them.
        from tasks.scene_html_renderer import render_scene_html
        from tasks.scene_html_author import author_scene_html
        from tasks.slide_scene import resolve_slide_scene

        scene = resolve_slide_scene(slide)
        if not scene.get("ok"):
            raise RuntimeError(f"Scene layout invalid: {scene.get('issues')}")
        slide["_layout_scene"] = scene
        author_fallback: dict[str, Any] | None = None
        # This document is a measured *region donor* and retry scaffold only.
        # It must never replace a complete authored slide.
        compact_region_donor = render_scene_html(
            slide=slide,
            scene=scene,
            palette=color_palette,
            density="compact",
        )
        if wrapped_call is None:
            # Test/offline diagnostic renderer only. Production generation must
            # never silently degrade to this deliberately plain fixture.
            html_doc = render_scene_html(
                slide=slide,
                scene=scene,
                palette=color_palette,
            )
        else:
            import time as _time

            author_error = ""
            html_doc = ""
            t_paint = _time.perf_counter()
            def _count_author_attempt() -> None:
                nonlocal llm_calls
                llm_calls += 1

            try:
                html_doc = author_scene_html(
                    slide=slide,
                    scene=scene,
                    primary_language=primary_language,
                    design_spec_md=design_spec_md,
                    design_reference_brief=design_reference_brief,
                    palette=color_palette,
                    call_text=wrapped_call,
                    prior_diary="\n".join(prior_diary_bits[-4:]),
                    feedback=feedback_for_slide,
                    scaffold_html=compact_region_donor,
                    on_attempt=_count_author_attempt,
                )
            except Exception as exc:  # noqa: BLE001
                author_error = str(exc).strip() or "LLM visual authoring failed"
                # Contract errors retain the authored candidate so measured
                # region repair can preserve its composition.
                html_doc = str(getattr(exc, "html", "") or "")
            paint_ms = int((_time.perf_counter() - t_paint) * 1000)
            if not html_doc:
                # No authored document exists to preserve. Keep generation
                # available with the measured scaffold, but do not classify it
                # as a replacement for an authored slide. Normal contract
                # failures retain their creative candidate above.
                print(
                    f"[html] Scene visual author failed P{number:02d}; "
                    f"using measured authoring scaffold and continuing: {author_error}"
                )
                html_doc = compact_region_donor
                author_fallback = {
                    "used": True,
                    "stage": "author_unavailable_scaffold",
                    "reason": author_error,
                    "renderer": "scene_v2_scaffold",
                }

        # Asset materialization owns every host mutation and performs a
        # semantic-tree preflight first.  Never inject a figure here: doing so
        # before the preflight allowed a host accidentally nested in a title to
        # cover an otherwise creative slide.
        placement_live: dict[str, Any] = {"figures": [], "tables": [], "errors": []}

        from tasks.scene_candidate_store import record_scene_candidate

        record_scene_candidate(
            storage_dir,
            slide_number=number,
            stage=("authoring_scaffold" if author_fallback else "creative_normalized"),
            html=html_doc,
            valid=None,
            selected=False,
            metadata={"author_fallback": author_fallback or None},
        )

        result = materialize_html_slide(
            storage_dir=storage_dir,
            slide=slide,
            html=html_doc,
            native_payloads=native_payloads,
            color_palette=color_palette,
            scene=scene,
        )
        fig_meta = result.get("figure_meta")
        if isinstance(fig_meta, dict) and not fig_meta.get("error"):
            placement_live["figures"].append(
                {"slide": number, "figure_id": fid, **fig_meta}
            )
        elif isinstance(fig_meta, dict) and fig_meta.get("error"):
            placement_live["errors"].append(
                f"P{number:02d} figure {fid}: {fig_meta['error']}"
            )
        runtime_report = (
            result.get("runtime_layout_qa")
            if isinstance(result.get("runtime_layout_qa"), dict)
            else {}
        )
        reflowable = [
            str(issue)
            for issue in runtime_report.get("hard") or []
            if str(issue).startswith(
                (
                    "runtime_text_overflow",
                    "runtime_ancestor_clip",
                    "runtime_canvas_overflow",
                    "runtime_word_fragmented",
                    "runtime_sibling_collision",
                )
            )
        ]
        contract_findings = list(
            (result.get("scene_contract") or {}).get("before_injection") or []
        ) + list((result.get("scene_contract") or {}).get("after_injection") or [])
        # materialize_html_slide already performs measured, region-scoped CSS
        # repair. Never ask the LLM to rewrite a completed visual in response to
        # layout QA: even a well-instructed rewrite can change composition. The
        # authored DOM is the immutable visual candidate; unresolved findings
        # remain export diagnostics for object-level handling.
        if not result.get("ok"):
            record_scene_candidate(
                storage_dir,
                slide_number=number,
                stage="creative_measured_invalid",
                html=html_doc,
                valid=False,
                selected=False,
                findings=list((result.get("runtime_layout_qa") or {}).get("hard") or []),
                metadata={"scene_contract": result.get("scene_contract")},
            )
            result["scene_reflow"] = {
                "attempted": False,
                "variant": "authored_dom_preserved",
                "regions": [],
                "initial_hard": reflowable
                or list((result.get("runtime_layout_qa") or {}).get("hard") or []),
                "resolved": False,
                "whole_slide_replaced": False,
            }
        final_html_path = result.get("html_path")
        try:
            final_html = Path(str(final_html_path)).read_text(encoding="utf-8") if final_html_path else ""
        except OSError:
            final_html = ""
        if final_html:
            fallback_stage = str((author_fallback or {}).get("stage") or "")
            selected_stage = (
                "region_recovered"
                if fallback_stage == "region_recovery"
                else "authoring_scaffold"
                if author_fallback
                else "creative_repaired"
            )
            record_scene_candidate(
                storage_dir,
                slide_number=number,
                stage=selected_stage,
                html=final_html,
                valid=bool(result.get("ok")),
                selected=True,
                findings=list((result.get("runtime_layout_qa") or {}).get("hard") or []),
                metadata={
                    "author_fallback": author_fallback or None,
                    "scene_reflow": result.get("scene_reflow"),
                },
            )
        measure_ms = int(result.get("measure_ms") or 0)
        preview_ms = int(result.get("preview_ms") or 0)
        table_meta = result.get("table_meta")
        if isinstance(table_meta, dict) and table_meta.get("table_id") and not table_meta.get("error"):
            bound_tid = str(slide.get("table_id") or table_meta.get("table_id") or "").strip()
            if bound_tid:
                placement_live["tables"].append(
                    {
                        "slide": number,
                        "table_id": bound_tid,
                        "status": table_meta.get("status") or "filled",
                        "columns": table_meta.get("columns"),
                        "rows": table_meta.get("rows"),
                    }
                )
        layout_qa = result.get("layout_qa") if isinstance(result.get("layout_qa"), dict) else {}
        authored.append(
            {
                "slide": number,
                "path": result.get("html_path"),
                "html_path": result.get("html_path"),
                "scene_path": result.get("scene_path"),
                "preview_path": result.get("preview_path"),
                "ok": result.get("ok"),
                "html_sot": True,
                "design_ms": design_ms,
                "paint_ms": paint_ms,
                "measure_ms": measure_ms,
                "preview_ms": preview_ms,
                "llm_calls": llm_calls,
                "layout_qa": layout_qa,
                "author_fallback": author_fallback,
            }
        )
        for key in ("figures", "tables", "errors"):
            for item in placement_live.get(key) or []:
                deck_placement.setdefault(key, []).append(item)
        prior_diary_bits.append(f"P{number:02d} {slide_title[:48]} HTML")
        print(
            f"[html] P{number:02d} html+preview ok={result.get('ok')} "
            f"figures={len(placement_live.get('figures') or [])} "
            f"design_ms={design_ms} paint_ms={paint_ms} "
            f"preview_ms={preview_ms} llm_calls={llm_calls}"
        )

    try:
        from tasks.html_pipeline import repair_stub_previews

        preview_fix = repair_stub_previews(storage_dir)
        if preview_fix.get("repaired"):
            print(f"[html] repaired stub previews: {preview_fix['repaired']}")
    except Exception as preview_exc:  # noqa: BLE001
        print(f"[html] stub preview repair skipped: {preview_exc}")

    return {
        "authored": authored,
        "budget_spent": budget.calls_spent,
        "placement_live": deck_placement,
        "enrichment_live": {"attempted": [], "placed": [], "errors": []},
        "ai_enrich_remaining": 0,
        "html_sot": True,
        "speed_stats": {"slides": len(authored), "sum_paints": len(authored)},
    }


def materialize_free_design_slides(
    *,
    slides: list[dict[str, Any]],
    design_spec_md: str,
    spec_lock_md: str,
    storage_dir: str,
    svg_dir: str,
    color_palette: dict[str, str],
    budget: AuthoringBudget,
    call_text: Callable[[str, str], str] | None,
    gt,
    loop=None,
    project_id: str = "",
    write_status=None,
    send_ws_message=None,
    slide_filter: set[int] | None = None,
    design_reference_brief: str = "",
    evidence_bundle: dict[str, Any] | None = None,
    figure_render_mode: str = "exact",
    table_render_mode: str = "exact",
    keep_existing: bool = False,
    image_source: str = "pdf",
    ai_enrich_max_new: int = 0,
    run_id: str | None = None,
    slide_feedback: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Author slides sequentially (P01 first). Budget wraps call_text when provided.

    Authors Constrained HTML → deckhtml PPTX (html_output/, preview/).
    AI decorative enrich runs live after each eligible content
    slide (shared ``ai_enrich_max_new`` budget). Resume keeps existing artifacts.
    """

    del svg_dir, gt, figure_render_mode, table_render_mode
    del image_source, ai_enrich_max_new  # SVG-era knobs unused on HTML path
    try:
        from tasks.html_flags import write_html_sot_marker
    except ImportError:  # pragma: no cover
        from html_flags import write_html_sot_marker  # type: ignore
    write_html_sot_marker(storage_dir, enabled=True)
    return _materialize_html_slides(
        slides=slides,
        design_spec_md=design_spec_md,
        storage_dir=storage_dir,
        color_palette=color_palette,
        budget=budget,
        call_text=call_text,
        loop=loop,
        project_id=project_id,
        write_status=write_status,
        send_ws_message=send_ws_message,
        slide_filter=slide_filter,
        design_reference_brief=design_reference_brief,
        evidence_bundle=evidence_bundle,
        keep_existing=keep_existing,
        slide_feedback=slide_feedback,
        run_id=run_id,
        spec_lock_md=spec_lock_md,
    )


def _user_instruction_numeric_tokens(storage_dir: str) -> set[str]:
    """Numbers that appear only in user directions / furniture — never hard-block."""
    try:
        from tasks.grounded_planner import canonical_numeric_tokens
    except ImportError:  # pragma: no cover
        from grounded_planner import canonical_numeric_tokens  # type: ignore

    blobs: list[str] = []
    result_path = os.path.join(storage_dir, "confirm_ui", "result.json")
    if os.path.isfile(result_path):
        try:
            data = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            data = {}
        if isinstance(data, dict):
            blobs.append(str(data.get("additional_instructions") or ""))
            furniture = data.get("deck_furniture")
            if isinstance(furniture, dict):
                blobs.extend(str(v) for v in furniture.values() if v)
    tokens: set[str] = set()
    for blob in blobs:
        for value, _unit in canonical_numeric_tokens(blob):
            # Canonical form matches validate_grounded_outline error suffixes.
            tokens.add(format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value))
            tokens.add(str(value))
            tokens.add(str(int(value)) if value == value.to_integral_value() else str(value))
    return tokens


def _is_user_instruction_unsupported_number(error: str, exempt: set[str]) -> bool:
    if ":unsupported-number:" not in error or not exempt:
        return False
    number = str(error).rsplit(":", 1)[-1].strip()
    return number in exempt


def _apply_pdf_grounding_bridge(
    *,
    slides: list[dict[str, Any]],
    design_spec_md: str,
    grounding_mode: str,
    evidence_bundle: dict[str, Any] | None,
    storage_dir: str,
    validation_dir: str,
    run_id: str,
    source_pdf_sha256: str | None,
    update_run_manifest,
    write_status,
) -> dict[str, Any]:
    """§IX → grounded_plan.json with soft repairs; fail closed on hard errors.

    Numbers that appear in the user's additional_instructions / deck furniture
    (presenter, affiliation, postal codes, etc.) are never hard-blocking.
    """
    from tasks.grounded_planner import (
        apply_coverage_plan_section_ids,
        derive_section_coverage_from_slides,
        sanitize_grounded_outline,
        validate_grounded_outline,
        validate_section_coverage,
    )

    presentation_data = strategist_agent.bridge_to_grounded_plan(
        slides,
        grounding_mode=grounding_mode,
        source_pdf_sha256=source_pdf_sha256,
        evidence_bundle=evidence_bundle,
    )
    # Evidence-first coverage: label slides from cited evidence, then gap-fill
    # missing major sections. Avoids document-order index stamps that disagree
    # with narrative §IX titles.
    coverage_plan: list[dict[str, Any]] = []
    if evidence_bundle and grounding_mode == "pdf_strict":
        try:
            coverage_plan = derive_section_coverage_from_slides(
                list(presentation_data.get("slides") or []),
                evidence_bundle,
            )
            presentation_data = apply_coverage_plan_section_ids(
                presentation_data, coverage_plan, replace=True
            )
        except Exception as allocate_error:
            print(f"[free_design] section coverage derive advisory: {allocate_error}")
            coverage_plan = []

    presentation_data = sanitize_grounded_outline(
        presentation_data, evidence_bundle or {}
    )
    grounded_outline, grounding_errors = validate_grounded_outline(
        presentation_data, evidence_bundle or {}
    )
    if grounded_outline is not None:
        try:
            grounding_errors.extend(
                validate_section_coverage(grounded_outline, evidence_bundle or {})
            )
        except Exception as coverage_error:
            # Free-design §IX may not allocate every section; treat coverage as soft.
            print(f"[free_design] section coverage advisory: {coverage_error}")

    # validate_grounded_outline returns outline=None whenever *any* semantic
    # error exists (pack_fill correction contract). Free-design must not treat
    # that as pydantic "shape invalid" — only grounded-schema:* is shape.
    schema_errors = [
        error for error in (grounding_errors or []) if str(error).startswith("grounded-schema:")
    ]
    user_numbers = _user_instruction_numeric_tokens(storage_dir)
    soft_from_instructions = [
        error
        for error in (grounding_errors or [])
        if _is_user_instruction_unsupported_number(str(error), user_numbers)
    ]
    hard_errors = [
        error
        for error in (grounding_errors or [])
        if any(
            token in error
            for token in (
                ":unknown-evidence:",
                ":unsupported-number:",
                ":unsupported-metric:",
                ":claim-quote-not-found:",
                ":unknown-formula:",
            )
        )
        and not _is_user_instruction_unsupported_number(str(error), user_numbers)
    ]
    if soft_from_instructions:
        print(
            "[free_design] user-instruction numbers advisory (not blocking): "
            + "; ".join(str(error) for error in soft_from_instructions[:8])
        )

    if schema_errors and grounding_mode == "pdf_strict":
        detail = "PDF free_design grounded outline rejected (shape invalid): " + "; ".join(
            schema_errors[:8]
        )
        update_run_manifest(status="failed", grounding_error=detail)
        write_status(storage_dir, "failed", 5, message=detail, run_id=run_id)
        raise RuntimeError(detail)
    if hard_errors and grounding_mode == "pdf_strict":
        detail = "PDF free_design grounded outline rejected: " + "; ".join(hard_errors[:20])
        update_run_manifest(status="failed", grounding_error=detail)
        write_status(storage_dir, "failed", 5, message=detail, run_id=run_id)
        raise RuntimeError(detail)
    if grounding_errors and grounded_outline is None:
        print(
            "[free_design] grounding advisory (soft): "
            + "; ".join(str(error) for error in grounding_errors[:12])
        )

    grounded_plan_path = os.path.join(validation_dir, "grounded_plan.json")
    slides_out = presentation_data.get("slides", [])
    if grounded_outline is not None:
        try:
            slides_out = [
                slide.model_dump() if hasattr(slide, "model_dump") else slide
                for slide in grounded_outline.slides
            ]
        except Exception:
            slides_out = presentation_data.get("slides", [])
    # Re-stamp after outline dump so model_dump cannot drop allocated IDs.
    if coverage_plan:
        stamped = apply_coverage_plan_section_ids(
            {"slides": slides_out}, coverage_plan, replace=True
        )
        slides_out = stamped.get("slides") or slides_out
    coverage_compressed = any(
        str(entry.get("coverage_mode") or "") in {"compressed", "grouped", "summary"}
        for entry in coverage_plan
        if isinstance(entry, dict)
    )
    payload = {
        "schema_version": "sunairum.grounded-plan/v1",
        "run_id": run_id,
        "source_pdf_sha256": source_pdf_sha256,
        "grounding_mode": grounding_mode,
        "requested_slide_count": len(slides_out),
        "actual_slide_count": len(slides_out),
        "coverage_compressed": coverage_compressed,
        "coverage_plan": coverage_plan,
        "section_coverage": coverage_plan,
        "slides": slides_out,
        "authoring_mode": "free_design",
        "design_spec_md": "design_spec.md",
    }
    with open(grounded_plan_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    update_run_manifest(
        grounded_plan_sha256=_sha256_file(grounded_plan_path),
        free_design_grounding="bridged",
    )
    return payload


def _sha256_file(path: str) -> str | None:
    import hashlib

    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generation_cancelled(storage_dir: str) -> bool:
    """True when status.json asks the worker to stop (soft cancel between slides)."""
    path = os.path.join(storage_dir, "status.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    return str(payload.get("status") or "") == "cancelled"


def existing_slide_numbers(project_dir: str) -> set[int]:
    """Slide indices with a non-empty preferred artifact (html/preview/svg)."""
    from tasks.slide_artifacts import existing_slide_numbers as _existing

    return _existing(project_dir)


def missing_slide_numbers(slides: list[dict[str, Any]], project_dir: str) -> list[int]:
    """Plan slide numbers that still need an authored artifact (resume gaps)."""
    have = existing_slide_numbers(project_dir)
    missing: list[int] = []
    for slide in slides:
        try:
            number = int(slide.get("slide") or 0)
        except (TypeError, ValueError):
            continue
        if number >= 1 and number not in have:
            missing.append(number)
    return missing


def can_resume_free_design(storage_dir: str, *, worker: bool = False) -> dict[str, Any]:
    """Whether a stopped run can continue from persisted design_spec + slides.

    The API gate (`worker=False`) only accepts cancelled/error/failed. Once the
    API queues the task it writes status=queued, so the worker must accept that
    handoff status (`worker=True`) rather than re-applying the user-facing gate.
    """
    design_path = os.path.join(storage_dir, "design_spec.md")
    lock_path = os.path.join(storage_dir, "spec_lock.md")
    status_path = os.path.join(storage_dir, "status.json")
    status = ""
    progress = 0
    message_key = ""
    if os.path.isfile(status_path):
        try:
            with open(status_path, encoding="utf-8") as handle:
                payload = json.load(handle) or {}
            status = str(payload.get("status") or "")
            progress = int(payload.get("progress") or 0)
            message_key = str(payload.get("message_key") or "")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            status = ""
    has_spec = os.path.isfile(design_path) and os.path.isfile(lock_path)
    planned = 0
    missing: list[int] = []
    missing_notes: list[int] = []
    have = existing_slide_numbers(storage_dir)
    if has_spec:
        try:
            with open(design_path, encoding="utf-8") as handle:
                design_spec_md = handle.read()
            parsed = strategist_agent.parse_section_ix_slides(design_spec_md)
            slides = [{"slide": int(item["slide"])} for item in parsed if item.get("slide")]
            planned = len(slides)
            missing = missing_slide_numbers(slides, storage_dir)
        except Exception as error:
            return {
                "ok": False,
                "reason": f"design_spec unreadable: {error}",
                "status": status,
                "progress": progress,
            }
    try:
        from tasks.speaker_notes import missing_note_numbers, notes_enabled

        if notes_enabled(storage_dir) and have:
            missing_notes = missing_note_numbers(storage_dir)
    except Exception:
        missing_notes = []
    request_ok = has_spec and status in {"cancelled", "error", "failed"}
    # Handoff: API already validated and flipped status to queued/generating.
    handoff_ok = has_spec and status in {
        "queued",
        "planning",
        "generating",
    } and (
        message_key == "status_resuming"
        or bool(worker)
    )
    ok = request_ok or (worker and handoff_ok)
    return {
        "ok": ok,
        "reason": None
        if ok
        else (
            "missing design_spec.md or spec_lock.md"
            if not has_spec
            else f"status={status or 'unknown'} is not resumable"
        ),
        "status": status,
        "progress": progress,
        "planned_slides": planned,
        "existing_slides": sorted(have),
        "missing_slides": missing,
        "missing_notes": missing_notes,
        "notes_complete": not missing_notes if have else False,
    }


def _resolve_figure_file(storage_dir: str, asset_id: str) -> str | None:
    index_path = os.path.join(storage_dir, "sources", "pdf_images", "index.json")
    if not os.path.isfile(index_path):
        return None
    try:
        with open(index_path, encoding="utf-8") as handle:
            figures = json.load(handle).get("figures") or []
    except (OSError, json.JSONDecodeError):
        return None
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        fid = str(figure.get("id") or figure.get("asset_id") or "").strip()
        file_name = str(figure.get("file") or "").strip()
        if fid == asset_id and file_name:
            path = os.path.join(storage_dir, "sources", "pdf_images", file_name)
            return path if os.path.isfile(path) else None
    return None


def _attr_float(attrs: str, name: str, default: float) -> float:
    match = re.search(rf'\b{re.escape(name)}="([^"]+)"', attrs or "", flags=re.I)
    if not match:
        return default
    try:
        return float(str(match.group(1)).strip().rstrip("px"))
    except ValueError:
        return default


def _resolve_table_payload(evidence_bundle: dict[str, Any] | None, table_id: str) -> dict[str, Any] | None:
    if not evidence_bundle or not table_id:
        return None
    tables = (evidence_bundle.get("tables") or {}).get("tables") or evidence_bundle.get("tables") or []
    if not isinstance(tables, list):
        return None
    for table in tables:
        if not isinstance(table, dict):
            continue
        tid = str(table.get("table_id") or table.get("id") or "").strip()
        if tid == table_id:
            payload = dict(table)
            payload.setdefault("source_table_id", tid)
            # Evidence tables use ``headers``; materialize/native export need ``columns``.
            columns = payload.get("columns")
            headers = payload.get("headers")
            if not isinstance(columns, list) or not columns:
                if isinstance(headers, list) and headers:
                    payload["columns"] = list(headers)
            return payload
    return None


def _table_materialized_in_svg(svg: str, table_id: str) -> bool:
    """True when SVG has a native-export-ready carrier for ``table_id``.

    Requires ``source-table-id`` plus parseable metadata with list ``columns``
    and ``rows``. Painted-only Intent grids without metadata are not ready —
    compile would strip them via ``strip_unfilled_native_table_carriers``.
    """
    if not svg or not table_id:
        return False
    for match in re.finditer(
        r"<g\b([^>]*)>(.*?)</g>",
        svg,
        flags=re.I | re.S,
    ):
        attrs, body = match.group(1), match.group(2)
        if f'data-sunairum-source-table-id="{table_id}"' not in attrs:
            continue
        meta = re.search(
            r"<metadata\b[^>]*>(.*?)</metadata>",
            body,
            flags=re.I | re.S,
        )
        if not meta:
            return False
        try:
            import html as _html
            import json as _json

            payload = _json.loads(_html.unescape(meta.group(1)).strip())
        except (TypeError, ValueError):
            return False
        if not isinstance(payload, dict):
            return False
        columns = payload.get("columns")
        rows = payload.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            return False
        if not columns and not rows:
            return False
        return True
    return False


def _svg_has_table_cell_values(svg: str, payload: dict[str, Any]) -> bool:
    """True when most expected header/cell strings appear in the SVG text."""
    if not svg or not isinstance(payload, dict):
        return False
    expected: list[str] = []
    for cell in payload.get("headers") or payload.get("columns") or []:
        text = str(cell.get("text") if isinstance(cell, dict) else cell or "").strip()
        if text:
            expected.append(text)
    for row in payload.get("rows") or []:
        if not isinstance(row, (list, tuple)):
            continue
        for cell in row:
            text = str(cell.get("text") if isinstance(cell, dict) else cell or "").strip()
            if text:
                expected.append(text)
    if not expected:
        return True
    # Require ≥80% of distinct non-trivial cells to appear.
    uniq = [t for t in dict.fromkeys(expected) if len(t) >= 1][:40]
    if not uniq:
        return True
    hits = sum(1 for t in uniq if t in svg)
    return hits >= max(1, int(round(0.8 * len(uniq))))


def _figure_placed_in_svg(svg: str, figure_id: str) -> bool:
    """True when SVG already has a real <image> for ``figure_id``."""
    if not svg or not figure_id:
        return False
    return bool(
        re.search(
            rf'<image\b[^>]*\bdata-sunairum-figure-id="{re.escape(figure_id)}"',
            svg,
            flags=re.I,
        )
    )


def _figure_placed_in_html(html: str, figure_id: str = "") -> bool:
    """True when the exact selected figure is materially filled in HTML."""
    from tasks.settings_obedience_artifacts import delivered_asset_ids_from_html

    figures, _tables = delivered_asset_ids_from_html(html)
    token = str(figure_id or "").strip()
    return token in figures if token else bool(figures)


def _slides_needing_asset_place(
    slides: list[dict[str, Any]],
    svg_dir: str,
    storage_dir: str | None = None,
) -> set[int]:
    """Slides still missing a bound figure image or filled table carrier."""
    need: set[int] = set()
    html_dir = os.path.join(storage_dir or "", "html_output") if storage_dir else ""
    for slide in slides:
        number = int(slide.get("slide") or 0)
        if number < 1:
            continue
        fid = str(slide.get("figure_id") or "").strip()
        html_path = os.path.join(html_dir, f"slide_{number:02d}.html") if html_dir else ""
        if html_path and os.path.isfile(html_path):
            try:
                html = Path(html_path).read_text(encoding="utf-8")
            except OSError:
                need.add(number)
                continue
            has_host = bool(
                re.search(r'data-pptx=["\'](?:figure|image)["\']', html, flags=re.I)
            )
            if (fid or has_host) and not _figure_placed_in_html(html, fid):
                need.add(number)
            continue
        path = os.path.join(svg_dir, f"slide_{number:02d}.svg")
        if not os.path.isfile(path):
            if fid:
                need.add(number)
            continue
        try:
            svg = Path(path).read_text(encoding="utf-8")
        except OSError:
            need.add(number)
            continue
        role = str(slide.get("role") or "content")
        figure_id = str(slide.get("figure_id") or "").strip()
        table_id = str(slide.get("table_id") or "").strip()
        if figure_id and not _figure_placed_in_svg(svg, figure_id):
            need.add(number)
        if table_id and role == "content" and not _table_materialized_in_svg(svg, table_id):
            need.add(number)
    return need


def _carrier_table_y(svg: str) -> float | None:
    """Y of the first native table carrier rect/payload, if any."""
    match = re.search(
        r'<g\b[^>]*\bdata-pptx-replace-with=["\']table["\'][^>]*>'
        r'.*?<metadata\b[^>]*>(.*?)</metadata>',
        svg or "",
        flags=re.I | re.S,
    )
    if not match:
        return None
    try:
        payload = json.loads(html.unescape(match.group(1)).strip())
    except (TypeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return float(payload.get("y") or 0)
    except (TypeError, ValueError):
        return None


_ORPHAN_FIGURE_LABEL = re.compile(
    r"<text\b[^>]*>\s*(?:SYSTEM\s+MAP|FIGURE|DIAGRAM|ARCHITECTURE)\s*</text>\s*",
    flags=re.I,
)


def _strip_orphan_figure_labels(svg: str) -> str:
    """Remove placeholder captions left above empty figure slots.

    Executors often paint labels like \"SYSTEM MAP\" for the reserved region.
    Once a real PDF figure is embedded (usually already titled), those labels
    float in dead space and look unanchored.
    """
    return _ORPHAN_FIGURE_LABEL.sub("", svg)


def _count_existing_ai_enrich_images(svg_dir: str, storage_dir: str) -> int:
    """How many decorative AI enrich images are already on disk / in SVGs (resume)."""
    images_dir = os.path.join(storage_dir, "images")
    count = 0
    if os.path.isdir(images_dir):
        for name in os.listdir(images_dir):
            if re.match(r"^ai_enrich_slide_\d{2}\.png$", name, flags=re.I):
                count += 1
    if count:
        return count
    # Fallback: count AI-sourced images in authored SVGs.
    if not os.path.isdir(svg_dir):
        return 0
    for name in os.listdir(svg_dir):
        if not re.match(r"^slide_\d{2}\.svg$", name, flags=re.I):
            continue
        try:
            svg = Path(os.path.join(svg_dir, name)).read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(r'data-sunairum-image-source="ai"', svg, flags=re.I):
            count += 1
    return count


def _enrich_one_slide_ai_figure(
    *,
    slide: dict[str, Any],
    storage_dir: str,
    svg_dir: str,
    color_palette: dict[str, str],
) -> dict[str, Any]:
    """Retired: SVG-slot AI enrich removed in zero-SVG cutover."""
    del storage_dir, svg_dir, color_palette
    number = int((slide or {}).get("slide") or 0)
    return {"status": "skipped", "slide": number, "reason": "retired_svg_path"}


def enrich_ai_figures(
    *,
    slides: list[dict[str, Any]],
    storage_dir: str,
    svg_dir: str,
    image_source: str,
    color_palette: dict[str, str],
    max_new: int = 2,
    write_status=None,
    run_id: str | None = None,
    loop=None,
    project_id: str = "",
    send_ws_message=None,
    skip_slides: set[int] | None = None,
) -> dict[str, Any]:
    """Gap-fill AI figures for empty content slots (live enrich may have done most)."""
    del slides, storage_dir, svg_dir, image_source, color_palette, max_new
    del write_status, run_id, loop, project_id, send_ws_message, skip_slides
    return {"attempted": [], "placed": [], "errors": [], "skipped_html_sot": True}


def write_settings_obedience(
    *,
    storage_dir: str,
    validation_dir: str,
    result_data: dict[str, Any],
    placement: dict[str, Any],
    enrichment: dict[str, Any] | None = None,
    notes_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record selected vs delivered Production Settings for UI/QA."""
    from tasks.image_source_policy import (
        coerce_image_source_for_grounding,
        normalize_render_mode,
        normalize_selected_figure_ids,
        normalize_selected_table_ids,
    )
    from tasks.speaker_notes import (
        animations_enabled,
        resolve_duration_settings,
        resolve_slide_transition,
    )

    selected_figures = normalize_selected_figure_ids(result_data.get("selected_figure_ids"))
    selected_tables = normalize_selected_table_ids(result_data.get("selected_table_ids"))
    placed_figures = {
        str(item.get("figure_id"))
        for item in (placement.get("figures") or [])
        if isinstance(item, dict) and item.get("figure_id")
    }
    placed_tables = {
        str(item.get("table_id"))
        for item in (placement.get("tables") or [])
        if isinstance(item, dict) and item.get("table_id")
    }
    from tasks.settings_obedience_artifacts import delivered_asset_ids

    artifact_figures, artifact_tables = delivered_asset_ids(storage_dir)
    placed_figures.update(artifact_figures)
    placed_tables.update(artifact_tables)
    missing_figures = [fid for fid in selected_figures if fid not in placed_figures]
    missing_tables = [tid for tid in selected_tables if tid not in placed_tables]
    minutes, wpm = resolve_duration_settings(storage_dir)
    target_words = int(minutes * wpm * (1.0 - 0.12))
    actual_words = int((notes_result or {}).get("actual_words") or 0)
    if not actual_words and isinstance(notes_result, dict):
        timing = notes_result.get("timing") if isinstance(notes_result.get("timing"), dict) else {}
        actual_words = int(timing.get("actual_words") or 0)
    notes_enabled_flag = bool(result_data.get("proactive_speaker_notes", True))
    # Allow ±20% around the buffered target; under-budget decks are also flagged.
    notes_budget_ok = True
    notes_status = str((notes_result or {}).get("status") or "")
    if notes_enabled_flag and target_words > 0 and notes_status in {"generated", "kept"}:
        ratio = actual_words / float(target_words)
        notes_budget_ok = 0.80 <= ratio <= 1.20
    if notes_enabled_flag and (
        notes_status == "incomplete" or list((notes_result or {}).get("missing_notes") or [])
    ):
        notes_budget_ok = False
    enrichment_errors = list((enrichment or {}).get("errors") or [])
    report = {
        "schema_version": "sunairum.settings-obedience/v1",
        "image_source": coerce_image_source_for_grounding(
            result_data.get("image_source"),
            result_data.get("grounding_mode"),
        ),
        "ai_enrich_max_new": int(result_data.get("ai_enrich_max_new") or 0),
        "figure_render_mode": normalize_render_mode(result_data.get("figure_render_mode"), "exact"),
        "table_render_mode": normalize_render_mode(result_data.get("table_render_mode"), "exact"),
        "selected_figure_ids": selected_figures,
        "selected_table_ids": selected_tables,
        "placed_figure_ids": sorted(placed_figures),
        "placed_table_ids": sorted(placed_tables),
        "artifact_reconciliation": {
            "figure_ids": sorted(artifact_figures),
            "table_ids": sorted(artifact_tables),
        },
        "missing_figure_ids": missing_figures,
        "missing_table_ids": missing_tables,
        "placement_errors": list(placement.get("errors") or []),
        "ai_enrichment": enrichment or {},
        "animations_requested": animations_enabled(storage_dir),
        "custom_animation_effect": resolve_slide_transition(storage_dir),
        "speaker_notes": {
            "enabled": notes_enabled_flag,
            "target_duration_minutes": minutes,
            "notes_wpm": wpm,
            "target_words": target_words,
            "actual_words": actual_words,
            "budget_ok": notes_budget_ok,
            "status": (notes_result or {}).get("status"),
        },
        "warnings": (
            ([] if notes_budget_ok or not notes_enabled_flag else ["notes_budget_mismatch"])
            + ([f"ai_enrichment:{err}" for err in enrichment_errors[:6]])
        ),
        "ok": not missing_figures and not missing_tables and notes_budget_ok,
    }
    path = os.path.join(validation_dir, "settings_obedience.json")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
    except OSError as error:
        print(f"[free_design] settings obedience write failed: {error}")
    return report


def _upscale_figure_if_low_dpi(path: str, *, min_width: int = 900) -> bool:
    """LANCZOS-upscale low-DPI PDF crops so placed figures are not soft blobs."""
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        with Image.open(path) as im:
            w, h = im.size
            if w >= min_width:
                return False
            scale = min_width / max(w, 1)
            # Cap extreme blow-ups (tiny icons).
            if scale > 4.0:
                scale = 4.0
            nw = max(1, int(round(w * scale)))
            nh = max(1, int(round(h * scale)))
            if nw <= w:
                return False
            out = im.resize((nw, nh), Image.Resampling.LANCZOS)
            fmt = (im.format or "PNG").upper()
            save_kw: dict[str, Any] = {}
            if fmt in {"JPEG", "JPG"}:
                save_kw["quality"] = 92
                fmt = "JPEG"
            out.save(path, format=fmt, **save_kw)
            return True
    except Exception:
        return False


def place_selected_assets(
    *,
    slides: list[dict[str, Any]],
    storage_dir: str,
    svg_dir: str,
    evidence_bundle: dict[str, Any] | None,
    figure_render_mode: str,
    table_render_mode: str,
    color_palette: dict[str, str],
    slide_filter: set[int] | None = None,
) -> dict[str, Any]:
    """Embed bound PDF figures into HTML hosts (IR rematerialize)."""
    del svg_dir, evidence_bundle, figure_render_mode, table_render_mode, color_palette
    from tasks.html_pipeline import place_pdf_figures_for_html

    return place_pdf_figures_for_html(
        slides=slides,
        storage_dir=storage_dir,
        slide_filter=slide_filter,
    )


def run_free_design(
    *,
    topic: str,
    project_id: str,
    user_id: str,
    storage_dir: str,
    svg_dir: str,
    validation_dir: str,
    run_id: str,
    result_data: dict[str, Any],
    grounding_mode: str,
    evidence_bundle: dict[str, Any] | None,
    color_palette: dict[str, str],
    typography: dict[str, Any],
    image_source: str,
    selected_figure_ids: list,
    visual_policy_block: str,
    page_count_int: int,
    loop,
    update_run_manifest,
    write_status,
    send_ws_message,
    emit_planning_status,
    gt,
    require_user_generate: bool,
    call_text: Callable[[str, str], str] | None = None,
    design_reference_pack: str | None = None,
    design_reference: dict[str, Any] | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Full free_design Job A through awaiting_user_compile / auto-compile handoff.

    When resume=True, reuse design_spec.md / spec_lock.md and skip existing SVGs.
    """
    from tasks.visual_styles import brief_enrichment
    from tasks import theme_agent
    from tasks.design_reference import apply_tokens_to_result
    from tasks.design_sot import resolve_design_sot

    design_reference = design_reference if isinstance(design_reference, dict) else {}
    sot = resolve_design_sot(
        pack_id=design_reference_pack,
        design_reference=design_reference,
        confirm_ui=result_data,
    )
    design_reference_brief = str(sot.get("brief") or design_reference.get("brief") or "")
    try:
        from tasks.design_sot import pipeline_method_dna_block
        from tasks.presentation_style import normalize_style_id, style_method_block
        from tasks.viz_catalog import catalog_menu_block
    except ImportError:  # pragma: no cover
        from design_sot import pipeline_method_dna_block  # type: ignore
        from presentation_style import normalize_style_id, style_method_block  # type: ignore
        from viz_catalog import catalog_menu_block  # type: ignore
    # Scratch-only presentation style; ignored when a design-reference pack is active.
    style_id = normalize_style_id(
        (result_data or {}).get("presentation_style")
        or (result_data or {}).get("style_id"),
        allow=not bool(design_reference_pack),
    )
    if style_id:
        result_data["presentation_style"] = style_id
    dna = pipeline_method_dna_block()
    style_block = style_method_block(style_id)
    catalog = catalog_menu_block()
    # User-selected scratch method is the highest-priority design input. Keep
    # it before generic DNA so compact per-slide prompts cannot truncate it.
    design_reference_brief = (
        f"{style_block}{dna}{design_reference_brief.rstrip()}\n\n{catalog}"
    ).strip()
    pack_tokens = (
        sot.get("tokens")
        if isinstance(sot.get("tokens"), dict)
        else {}
    )
    # Pack SoT or UI-projected SoT — both apply through the same token shape.
    # confirm_ui projection must apply even when color.source is already "user".
    user_locked_palette = str(
        (result_data.get("color") or {}).get("source") or ""
    ).casefold() == "user"
    sot_source = str(sot.get("source") or "")
    sot_owns = bool(pack_tokens) and sot_source in {"pack", "confirm_ui"}
    pack_owns = sot_owns and sot_source == "pack"
    if sot_owns:
        result_data = apply_tokens_to_result(result_data, pack_tokens)
        if str(sot.get("source") or "") == "confirm_ui":
            # Preserve UI authorship marker.
            color = result_data.get("color") if isinstance(result_data.get("color"), dict) else {}
            result_data["color"] = {**color, "source": "user"}
            typo = result_data.get("typography") if isinstance(result_data.get("typography"), dict) else {}
            result_data["typography"] = {**typo, "source": "user"}
        color_palette = dict((result_data.get("color") or {}).get("palette") or color_palette or {})
        typography = dict(result_data.get("typography") or typography or {})

    style_enrichment = brief_enrichment(result_data)
    # When a gallery pack owns the design system, do not invent competing chrome/mood.
    if pack_owns:
        layout = pack_tokens.get("layout") if isinstance(pack_tokens.get("layout"), dict) else {}
        mood = (
            pack_tokens.get("image_mood")
            if isinstance(pack_tokens.get("image_mood"), dict)
            else {}
        )
        style_enrichment = {
            **style_enrichment,
            "visual_style": str(
                layout.get("visual_style")
                or result_data.get("visual_style")
                or style_enrichment.get("visual_style")
                or ""
            ),
            "density": str(
                layout.get("density")
                or result_data.get("density")
                or style_enrichment.get("density")
                or "medium"
            ),
            "rendering_prompt": " × ".join(
                part
                for part in (
                    mood.get("image_rendering"),
                    mood.get("image_palette"),
                )
                if part
            )
            or str(style_enrichment.get("rendering_prompt") or ""),
            "art_direction_extra": str(pack_tokens.get("cover_treatment") or ""),
            "source": "pack",
        }
    # Seed confirm_ui visual_style into result for Strategist fallback.
    if style_enrichment.get("visual_style") and not result_data.get("visual_style"):
        result_data = {**result_data, "visual_style": style_enrichment["visual_style"]}
    if pack_owns and style_enrichment.get("density"):
        result_data = {**result_data, "density": style_enrichment["density"]}

    deck_theme = theme_agent.resolve(
        {
            "topic": topic,
            "audience": result_data.get("audience", ""),
            "art_direction": " ".join(
                part
                for part in (
                    str(result_data.get("image_notes") or ""),
                    visual_policy_block,
                    style_enrichment.get("art_direction_extra", ""),
                    style_enrichment.get("rendering_prompt", ""),
                )
                if part
            ),
            "visual_style": style_enrichment.get("visual_style", ""),
            "mode": style_enrichment.get("mode", ""),
            "density": style_enrichment.get("density", ""),
            "palette_source": "user" if user_locked_palette else ("pack" if pack_owns else ""),
        },
        pack_palette=color_palette,
        pack_typography=typography,
        authored=pack_owns,
    )
    # Fold pack spacing into the deck theme when present.
    if pack_owns and isinstance(pack_tokens.get("spacing"), dict) and pack_tokens["spacing"]:
        from dataclasses import replace as _dc_replace

        merged_spacing = {
            **deck_theme.spacing,
            **{
                k: float(v)
                for k, v in pack_tokens["spacing"].items()
                if k in deck_theme.spacing
            },
        }
        deck_theme = _dc_replace(deck_theme, spacing=merged_spacing)
    color_palette = dict(deck_theme.palette)
    # Keep chrome extras from pack tokens on the live palette for adapters.
    if pack_owns:
        for key in (
            "text_secondary",
            "text_tertiary",
            "border",
            "accent_tint",
            "success",
            "warning",
        ):
            if (pack_tokens.get("palette") or {}).get(key):
                color_palette[key] = pack_tokens["palette"][key]
    # Style Resolver inputs for Infographic / table materialize.
    color_palette["visual_style"] = str(
        style_enrichment.get("visual_style")
        or result_data.get("visual_style")
        or ""
    )
    color_palette["density"] = str(
        style_enrichment.get("density")
        or result_data.get("density")
        or "medium"
    )
    typography = deck_theme.typography
    # Preserve type_scale on typography for downstream adapters.
    if isinstance(typography, dict):
        typography = {
            **typography,
            "type_scale": dict(deck_theme.type_scale),
            "source": "pack" if pack_owns else typography.get("source", ""),
        }

    update_run_manifest(
        authoring_mode="free_design",
        template_id=None,
        scratch_default_pack=None,
        grounding_mode=grounding_mode,
        image_source=image_source,
        selected_figure_ids=selected_figure_ids,
        theme={
            "palette": color_palette,
            "typography": typography,
            "authority": deck_theme.authority,
            "type_scale": dict(deck_theme.type_scale),
            "spacing": dict(deck_theme.spacing),
            "tokens": pack_tokens if pack_owns else {},
        },
        page_count=page_count_int,
        free_design=True,
        design_reference_pack=design_reference_pack,
        presentation_style=style_id,
        presentation_style_applied=bool(style_id and style_block),
    )

    evidence_text = ""
    if grounding_mode == "pdf_strict" and evidence_bundle:
        from tasks.grounded_planner import evidence_catalog

        evidence_text = evidence_catalog(evidence_bundle)

    if not resume:
        emit_planning_status(
            loop,
            project_id,
            storage_dir,
            run_id,
            "status_planning_content",
            "Authoring free-design design_spec.md",
            12,
        )

    # Cover+closing ≈ +2; allow full QA retry budget so mid-deck does not abort.
    slide_n = max(int(page_count_int) + 2, int(page_count_int), 1)
    env_budget = int(os.environ.get("AUTHORING_MODEL_CALL_BUDGET", "8") or 8)
    budget_limit = max(
        slide_n * _PER_SLIDE_AUTHOR_CALLS + _AUTHORING_HEADROOM,
        env_budget,
    )
    budget = AuthoringBudget(limit=budget_limit)
    print(
        f"[free_design] authoring budget limit={budget_limit} "
        f"(slides≈{slide_n} × {_PER_SLIDE_AUTHOR_CALLS} + {_AUTHORING_HEADROOM})"
    )
    if call_text is None:
        try:
            from llm_client import call_llm_text as call_text
        except Exception:
            call_text = None
    strategist_call = budget.wrap(call_text) if call_text is not None else None

    from tasks.source_identity import extract_source_identity
    from tasks.image_source_policy import (
        normalize_selected_table_ids,
        normalize_render_mode,
    )

    source_identity = extract_source_identity(evidence_bundle) if evidence_bundle else {}
    from tasks.deck_furniture import (
        merge_furniture_into_identity,
        resolve_deck_furniture,
    )

    deck_furniture = resolve_deck_furniture(result_data)
    source_identity = merge_furniture_into_identity(source_identity, deck_furniture)
    selected_table_ids = normalize_selected_table_ids(result_data.get("selected_table_ids"))
    # Exact PDF/source assets only — coerce away ai_replica.
    figure_render_mode = "exact"
    table_render_mode = "exact"
    asset_catalog_lines = []
    if selected_figure_ids:
        asset_catalog_lines.append(
            "Figures: " + ", ".join(str(x) for x in selected_figure_ids[:40])
        )
    if selected_table_ids:
        asset_catalog_lines.append(
            "Tables: " + ", ".join(str(x) for x in selected_table_ids[:40])
        )

    if resume:
        design_path = os.path.join(storage_dir, "design_spec.md")
        lock_path = os.path.join(storage_dir, "spec_lock.md")
        if not os.path.isfile(design_path) or not os.path.isfile(lock_path):
            detail = "Resume requires design_spec.md and spec_lock.md from the stopped run"
            write_status(storage_dir, "failed", 5, message=detail, run_id=run_id)
            raise RuntimeError(detail)
        with open(design_path, encoding="utf-8") as handle:
            design_spec_md = handle.read()
        with open(lock_path, encoding="utf-8") as handle:
            spec_lock_md = handle.read()
        paths = {
            "design_spec_md": design_path,
            "spec_lock_md": lock_path,
        }
        strategist_meta = {"source": "resume", "content_page_count": page_count_int}
        # Prefer counts from the persisted §IX plan; fall back to wizard page_count.
        preview_parsed = strategist_agent.parse_section_ix_slides(design_spec_md)
        page_count = len(preview_parsed) if preview_parsed else int(page_count_int)
        content_count = max(page_count - 2, 1) if page_count >= 3 else max(page_count, 1)
        strategist_meta["content_page_count"] = content_count
        strategist_meta["total_page_count"] = page_count
        write_status(
            storage_dir,
            "generating",
            40,
            message="Resuming free-design SVG authoring",
            message_key="status_resuming",
            run_id=run_id,
        )
    else:
        try:
            design_spec_md, strategist_meta = strategist_agent.author_design_spec(
                topic=topic,
                result=result_data,
                evidence_catalog=evidence_text,
                call_text=strategist_call,
                allow_fallback=strategist_call is None,
                design_reference_brief=design_reference_brief,
                source_identity=source_identity,
                grounding_mode=grounding_mode,
                selected_figure_ids=list(selected_figure_ids or []),
                selected_table_ids=selected_table_ids,
                asset_catalog="\n".join(asset_catalog_lines),
            )
        except Exception as strategist_error:
            detail = str(strategist_error).strip() or "Strategist LLM unavailable"
            print(f"[free_design] Strategist LLM stop: {detail}")
            write_status(
                storage_dir,
                "error",
                35,
                message=detail[:240],
                message_key="status_llm_unavailable",
                run_id=run_id,
            )
            update_run_manifest(
                status="error",
                resume_checkpoint=True,
                llm_error=detail[:500],
            )
            if loop is not None and send_ws_message is not None and project_id:
                try:
                    loop.run_until_complete(
                        send_ws_message(
                            project_id,
                            {
                                "status_key": "status_llm_unavailable",
                                "status": "error",
                                "progress": 35,
                                "detail": detail[:240],
                            },
                        )
                    )
                except Exception:
                    pass
            return {
                "status": "error",
                "project_id": project_id,
                "run_id": run_id,
                "llm_failed": True,
                "reason": detail,
                "authoring_mode": "free_design",
            }
        content_count = int(strategist_meta.get("content_page_count") or page_count_int)
        page_count = int(
            strategist_meta.get("total_page_count")
            or strategist_meta.get("page_count")
            or (content_count + 2)
        )
        spec_lock_md = strategist_agent.project_flat_spec_lock(
            result=result_data,
            design_spec_md=design_spec_md,
            page_count=page_count,
        )
        paths = strategist_agent.persist_strategist_artifacts(
            storage_dir,
            design_spec_md=design_spec_md,
            spec_lock_md=spec_lock_md,
        )
        gate1 = strategist_agent.validate_design_spec_md(design_spec_md)
        if gate1:
            raise RuntimeError("Gate 1 failed after persist: " + "; ".join(gate1))
        drift = strategist_agent.validate_design_spec_palette(
            design_spec_md, result_data
        )
        if drift:
            print(
                "[design_tokens] design_spec palette drift (continuing with lock): "
                + "; ".join(drift)
            )

    parsed = strategist_agent.parse_section_ix_slides(design_spec_md)
    if not parsed:
        raise RuntimeError("§IX produced no slides")
    parsed = strategist_agent.ensure_bookend_slides(
        parsed,
        content_count=content_count,
        topic=topic,
        result=result_data,
        source_identity=source_identity,
        grounding_mode=grounding_mode,
    )
    try:
        from tasks.strategist_ir import sanitize_parsed_slides
    except ImportError:  # pragma: no cover
        from strategist_ir import sanitize_parsed_slides  # type: ignore
    parsed = sanitize_parsed_slides(
        parsed,
        storage_dir=storage_dir,
        evidence_bundle=evidence_bundle,
    )
    # Map caption-style §IX fields (e.g. "TABLE IV") onto src-table-* / pdf-page-* ids.
    table_catalog: list[dict[str, Any]] = []
    figure_catalog: list[dict[str, Any]] = []
    if evidence_bundle:
        raw_tables = (evidence_bundle.get("tables") or {}).get("tables") or evidence_bundle.get("tables") or []
        if isinstance(raw_tables, list):
            table_catalog = [item for item in raw_tables if isinstance(item, dict)]
        raw_figs = (evidence_bundle.get("assets") or {}).get("assets") or evidence_bundle.get("figures") or []
        if isinstance(raw_figs, list):
            figure_catalog = [item for item in raw_figs if isinstance(item, dict)]
    if not table_catalog:
        tables_path = os.path.join(storage_dir, "sources", "source_tables.json")
        if os.path.isfile(tables_path):
            try:
                payload = json.loads(Path(tables_path).read_text(encoding="utf-8"))
                raw_tables = payload.get("tables") if isinstance(payload, dict) else payload
                if isinstance(raw_tables, list):
                    table_catalog = [item for item in raw_tables if isinstance(item, dict)]
            except (OSError, json.JSONDecodeError):
                pass
    parsed = strategist_agent.resolve_parsed_slide_assets(
        parsed, tables=table_catalog, figures=figure_catalog
    )
    # One figure/table id → one slide (clear §IX duplicates, then fill gaps).
    uniq_warnings = _uniquify_asset_bindings(parsed)
    if uniq_warnings:
        print("[free_design] asset uniquify: " + "; ".join(uniq_warnings[:12]))
    # §IX wins; fallback scores table-dominant / figure-dominant slides and
    # never stacks table+figure on the same slide unless already co-bound in §IX.
    bind_warnings = _bind_selected_assets(
        parsed,
        selected_figure_ids=list(selected_figure_ids or []),
        selected_table_ids=list(selected_table_ids or []),
    )
    if bind_warnings:
        print("[free_design] asset bind: " + "; ".join(bind_warnings[:12]))
    # §IX sometimes binds the wrong src-table-* (equity copy → eval-count table).
    # Re-score caption/columns against slide claims before materialize.
    fit_warnings = _reconcile_slide_table_bindings(
        parsed, table_catalog, selected_table_ids=list(selected_table_ids or [])
    )
    if fit_warnings:
        print("[free_design] table fit: " + "; ".join(fit_warnings[:12]))
    slides = [_slide_dict_from_parsed(item) for item in parsed]
    try:
        from tasks.executor_modes import apply_soft_pattern
        from tasks.slide_regions import layout_for_slide, persist_slide_regions
    except ImportError:  # pragma: no cover
        from executor_modes import apply_soft_pattern  # type: ignore
        from slide_regions import layout_for_slide, persist_slide_regions  # type: ignore
    region_layouts = []
    deck_density = str(
        (color_palette or {}).get("density")
        or result_data.get("density")
        or "medium"
    )
    pack_layout = {}
    if isinstance(color_palette, dict) and isinstance(
        color_palette.get("design_tokens"), dict
    ):
        pack_layout = (
            color_palette["design_tokens"].get("layout")
            if isinstance(color_palette["design_tokens"].get("layout"), dict)
            else {}
        )
    pack_page_charts = (
        pack_layout.get("page_charts")
        if isinstance(pack_layout.get("page_charts"), dict)
        else {}
    )
    cover_hint = ""
    if isinstance(color_palette, dict) and isinstance(
        color_palette.get("design_tokens"), dict
    ):
        cover_hint = str(
            color_palette["design_tokens"].get("cover_treatment") or ""
        ).strip()
    for slide in slides:
        slide["total_slides"] = len(slides)
        slide["density"] = deck_density
        key = f"P{int(slide.get('slide') or 0):02d}"
        if pack_page_charts.get(key):
            slide["pack_chart_pattern"] = str(pack_page_charts[key])
        if isinstance(color_palette, dict) and isinstance(
            color_palette.get("design_tokens"), dict
        ):
            table_tok = color_palette["design_tokens"].get("table")
            if isinstance(table_tok, dict) and table_tok.get("preferred_patterns"):
                slide["pack_table_patterns"] = list(table_tok["preferred_patterns"])
        role = str(slide.get("role") or "").casefold()
        if cover_hint and role in {"title", "hero"}:
            slide["cover_treatment"] = cover_hint
        # Annotate table row count for recipe choice when evidence is available.
        tid = str(slide.get("table_id") or "").strip()
        if tid and table_catalog:
            for item in table_catalog:
                if str(item.get("table_id") or item.get("id") or "") == tid:
                    rows = item.get("rows") or item.get("preview") or []
                    if isinstance(rows, list):
                        slide["table_rows"] = len(rows)
                    break
        pack_preview = extract_executor_design_pack(
            design_spec_md,
            int(slide.get("slide") or 0),
            body_md_fallback=str(slide.get("body_md") or ""),
        )
        apply_soft_pattern(slide)
        layout = layout_for_slide(slide)
        slide.pop("layout_recipe", None)
        region_layouts.append(layout)
    try:
        persist_slide_regions(validation_dir, region_layouts)
    except OSError as region_error:
        print(f"[free_design] slide_regions persist skipped: {region_error}")

    update_run_manifest(
        design_spec_md_sha256=_sha256_file(paths["design_spec_md"]),
        spec_lock_md_sha256=_sha256_file(paths["spec_lock_md"]),
        strategist_source=strategist_meta.get("source"),
        authoring_llm_calls=budget.calls_spent,
        num_slides=len(slides),
        content_page_count=content_count,
        total_page_count=page_count,
        source_identity=source_identity,
        selected_table_ids=selected_table_ids,
        figure_render_mode=figure_render_mode,
        table_render_mode=table_render_mode,
    )

    if grounding_mode == "pdf_strict":
        emit_planning_status(
            loop,
            project_id,
            storage_dir,
            run_id,
            "status_planning_grounding",
            "Bridging §IX to grounded_plan",
            18,
        )
        source_pdf = os.path.join(storage_dir, "source.pdf")
        source_sha = _sha256_file(source_pdf) if os.path.isfile(source_pdf) else None
        _apply_pdf_grounding_bridge(
            slides=parsed,
            design_spec_md=design_spec_md,
            grounding_mode=grounding_mode,
            evidence_bundle=evidence_bundle,
            storage_dir=storage_dir,
            validation_dir=validation_dir,
            run_id=run_id,
            source_pdf_sha256=source_sha,
            update_run_manifest=update_run_manifest,
            write_status=write_status,
        )

    # Icon acquisition (best-effort; does not block).
    try:
        from tasks.asset_library import find_icons
        from tasks.asset_agent import pick_icon

        icons = result_data.get("icons") if isinstance(result_data.get("icons"), dict) else {}
        terms = []
        if isinstance(icons.get("inventory"), list):
            terms = [str(item) for item in icons["inventory"][:8]]
        if not terms:
            terms = [topic.split()[0]] if topic.split() else ["chart"]
        found = find_icons(*terms, limit=6)
        if found:
            update_run_manifest(icons_resolved=[item.get("name") for item in found if isinstance(item, dict)])
        _ = pick_icon(*terms[:2]) if terms else None
    except Exception as icon_error:
        print(f"[free_design] icon acquire skipped: {icon_error}")

    emit_planning_status(
        loop,
        project_id,
        storage_dir,
        run_id,
        "status_generating",
        "Authoring free-design slides",
        40,
    )

    # Attach pack tokens + font families for materialize adapters.
    if isinstance(color_palette, dict):
        if pack_owns and pack_tokens:
            color_palette["design_tokens"] = pack_tokens
        color_palette["_heading_family"] = str(
            ((typography or {}).get("heading") or {}).get("primary")
            or deck_theme.heading_family
        )
        color_palette["_body_family"] = str(
            ((typography or {}).get("body") or {}).get("primary")
            or deck_theme.body_family
        )

    try:
        from tasks.image_source_policy import (
            coerce_image_source_for_grounding,
            normalize_ai_enrich_max_new,
        )
    except ImportError:  # pragma: no cover
        from image_source_policy import (  # type: ignore
            coerce_image_source_for_grounding,
            normalize_ai_enrich_max_new,
        )
    image_source = coerce_image_source_for_grounding(image_source, grounding_mode)
    ai_enrich_budget = normalize_ai_enrich_max_new(
        result_data.get("ai_enrich_max_new"),
        grounding_mode=grounding_mode,
        image_source=image_source,
    )
    update_run_manifest(
        image_source=image_source,
        ai_enrich_max_new=ai_enrich_budget,
    )

    authoring_failure = ""
    try:
        materialize = materialize_free_design_slides(
            slides=slides,
            design_spec_md=design_spec_md,
            spec_lock_md=spec_lock_md,
            storage_dir=storage_dir,
            svg_dir=svg_dir,
            color_palette=color_palette,
            budget=budget,
            call_text=call_text,
            gt=gt,
            loop=loop,
            project_id=project_id,
            write_status=write_status,
            send_ws_message=send_ws_message,
            design_reference_brief=design_reference_brief,
            evidence_bundle=evidence_bundle,
            figure_render_mode="exact",
            table_render_mode="exact",
            keep_existing=resume,
            image_source=image_source,
            ai_enrich_max_new=ai_enrich_budget,
            run_id=run_id,
        )
    except Exception as authoring_error:  # noqa: BLE001
        # One slide must not cost the deck. Authoring writes each slide to
        # html_output/ as it finishes, so a failure partway through still leaves
        # a real, mostly complete presentation on disk. Compile and publish it
        # with the failure recorded, rather than discarding finished work and
        # leaving the user with nothing to open.
        #
        # A deadline or a cancellation is not a slide failure: it means "stop
        # now", and the slides still missing are missing because there was no
        # time, not because they were unauthorable. Swallowing one shipped a
        # 1-of-14 deck labelled complete, which is worse than a clear failure.
        from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

        if isinstance(authoring_error, (SoftTimeLimitExceeded, TimeLimitExceeded)):
            raise
        authored_now = sorted(existing_slide_numbers(storage_dir))
        if not authored_now:
            raise
        # Never present a partial deck as a whole one.
        if len(authored_now) < len(slides):
            partial_note = (
                f"deck published with {len(authored_now)} of {len(slides)} slides"
            )
            print(f"[free_design] {partial_note}")
        authoring_failure = f"{type(authoring_error).__name__}: {authoring_error}"[:400]
        print(
            f"[free_design] authoring stopped after {len(authored_now)}/{len(slides)} slides "
            f"({authoring_failure}); compiling what is on disk"
        )
        materialize = {
            "authored": [
                {"slide": number,
                 "path": os.path.join(storage_dir, "html_output", f"slide_{number:02d}.html"),
                 "partial_run": True}
                for number in authored_now
            ],
            "budget_spent": getattr(budget, "calls_spent", 0),
            "placement_live": {"figures": [], "tables": [], "errors": []},
            "enrichment_live": {"attempted": [], "placed": [], "errors": []},
            "ai_enrich_remaining": 0,
            "html_sot": True,
            "authoring_failure": authoring_failure,
        }
        update_run_manifest(authoring_failure=authoring_failure)
    if isinstance(materialize, dict) and materialize.get("cancelled"):
        authored_n = len(materialize.get("authored") or [])
        existing_n = len(existing_slide_numbers(storage_dir))
        progress = max(40, min(80, 40 + existing_n * 2))
        if materialize.get("llm_failed"):
            detail = str(materialize.get("reason") or "LLM unavailable").strip()
            stop_slide = materialize.get("stop_slide")
            msg = (
                f"LLM unavailable at P{int(stop_slide):02d}: {detail}"
                if stop_slide
                else f"LLM unavailable: {detail}"
            )
            write_status(
                storage_dir,
                "error",
                progress,
                existing_n,
                len(slides),
                message=msg[:240],
                message_key="status_llm_unavailable",
                run_id=run_id,
            )
            update_run_manifest(
                status="error",
                free_svg_authored=materialize.get("authored"),
                authoring_llm_calls=budget.calls_spent,
                resume_checkpoint=True,
                llm_error=detail[:500],
                stop_slide=stop_slide,
            )
            if loop is not None and send_ws_message is not None and project_id:
                try:
                    loop.run_until_complete(
                        send_ws_message(
                            project_id,
                            {
                                "status_key": "status_llm_unavailable",
                                "status": "error",
                                "progress": progress,
                                "current": existing_n,
                                "total": len(slides),
                                "detail": msg[:240],
                            },
                        )
                    )
                except Exception:
                    pass
            return {
                "status": "error",
                "project_id": project_id,
                "run_id": run_id,
                "authored": authored_n,
                "existing_slides": existing_n,
                "llm_failed": True,
                "reason": detail,
                "stop_slide": stop_slide,
                "authoring_mode": "free_design",
            }
        write_status(
            storage_dir,
            "cancelled",
            progress,
            existing_n,
            len(slides),
            message="Generation cancelled by user",
            message_key="status_cancelled",
            run_id=run_id,
        )
        update_run_manifest(
            status="cancelled",
            free_svg_authored=materialize.get("authored"),
            authoring_llm_calls=budget.calls_spent,
            resume_checkpoint=True,
        )
        return {
            "status": "cancelled",
            "project_id": project_id,
            "run_id": run_id,
            "authored": authored_n,
            "existing_slides": existing_n,
            "authoring_mode": "free_design",
        }

    # Leave the "slide N/N" headline — post-author work can take minutes (AI images).
    existing_n = len(existing_slide_numbers(storage_dir))
    write_status(
        storage_dir,
        "generating",
        66,
        existing_n,
        len(slides),
        message="Slides authored — placing figures and tables",
        message_key="status_placing_assets",
        run_id=run_id,
    )
    try:
        loop.run_until_complete(
            send_ws_message(
                project_id,
                {
                    "status_key": "status_placing_assets",
                    "progress": 66,
                    "current": existing_n,
                    "total": len(slides),
                },
            )
        )
    except Exception:
        pass

    # Safety place only for slides still missing bound assets (live place already did the rest).
    need_place = _slides_needing_asset_place(slides, svg_dir, storage_dir=storage_dir)
    if need_place:
        placement = place_selected_assets(
            slides=slides,
            storage_dir=storage_dir,
            svg_dir=svg_dir,
            evidence_bundle=evidence_bundle,
            figure_render_mode=figure_render_mode,
            table_render_mode=table_render_mode,
            color_palette=color_palette,
            slide_filter=need_place,
        )
    else:
        placement = {"figures": [], "tables": [], "errors": [], "skipped_complete": True}
    live_place = materialize.get("placement_live") if isinstance(materialize, dict) else None
    if isinstance(live_place, dict):
        for key in ("errors", "warnings", "figures", "tables"):
            for item in live_place.get(key) or []:
                placement.setdefault(key, []).append(item)
    # Gap-fill only: live enrich during materialize usually consumed the budget.
    live_enrich = materialize.get("enrichment_live") if isinstance(materialize, dict) else None
    remaining_enrich = int(
        (materialize or {}).get("ai_enrich_remaining", 0)
        if isinstance(materialize, dict)
        else 0
    )
    already_enriched = {
        int(item.get("slide") or 0)
        for item in ((live_enrich or {}).get("placed") or [])
        if isinstance(item, dict)
    }
    enrichment = enrich_ai_figures(
        slides=slides,
        storage_dir=storage_dir,
        svg_dir=svg_dir,
        image_source=image_source,
        color_palette=color_palette,
        max_new=remaining_enrich,
        write_status=write_status,
        run_id=run_id,
        loop=loop,
        project_id=project_id,
        send_ws_message=send_ws_message,
        skip_slides=already_enriched,
    )
    if isinstance(live_enrich, dict):
        for key in ("attempted", "placed", "errors"):
            for item in live_enrich.get(key) or []:
                enrichment.setdefault(key, []).append(item)

    # Speaker notes BEFORE the single deckhtml compile. Notes are merged into the
    # PPTX with python-pptx after deckhtml — never a second full compile.
    notes_result: dict[str, Any] = {"status": "skipped"}
    try:
        from tasks.speaker_notes import maybe_generate_speaker_notes_for_project, notes_enabled

        if notes_enabled(storage_dir):
            write_status(
                storage_dir,
                "planning",
                80,
                message="Writing speaker notes",
                message_key="status_speaker_notes",
                run_id=run_id,
            )
            try:
                loop.run_until_complete(
                    send_ws_message(
                        project_id,
                        {"status_key": "status_speaker_notes", "progress": 80},
                    )
                )
            except Exception:
                pass

            def _notes_progress(current: int, total_notes: int) -> None:
                pct = 80 + int(4 * (current / max(1, total_notes)))
                try:
                    write_status(
                        storage_dir,
                        "planning",
                        pct,
                        current=current,
                        total=total_notes,
                        message=f"Writing speaker notes {current}/{total_notes}",
                        message_key="status_speaker_notes_slide",
                        run_id=run_id,
                    )
                except Exception:
                    pass
                try:
                    loop.run_until_complete(
                        send_ws_message(
                            project_id,
                            {
                                "status_key": "status_speaker_notes_slide",
                                "progress": pct,
                                "current": current,
                                "total": total_notes,
                            },
                        )
                    )
                except Exception:
                    pass

            notes_result = maybe_generate_speaker_notes_for_project(
                storage_dir,
                call_text=None,
                progress_callback=_notes_progress,
                keep_existing=True,
            )
            print(
                f"[free_design] speaker notes status={notes_result.get('status')} "
                f"missing={notes_result.get('missing_notes')}"
            )
        else:
            notes_result = {"status": "disabled"}
    except Exception as notes_error:
        print(f"[free_design] speaker notes skipped: {notes_error}")
        notes_result = {"status": "error", "error": str(notes_error)}

    try:
        write_settings_obedience(
            storage_dir=storage_dir,
            validation_dir=validation_dir,
            result_data=result_data,
            placement=placement,
            enrichment=enrichment,
            notes_result=notes_result,
        )
    except Exception as obedience_error:
        print(f"[free_design] settings obedience skipped: {obedience_error}")

    update_run_manifest(
        authoring_llm_calls=budget.calls_spent,
        free_svg_authored=materialize.get("authored"),
        asset_placement=placement,
        ai_enrichment=enrichment,
        speaker_notes=str(notes_result.get("status") or "ready"),
    )

    if grounding_mode == "pdf_strict":
        try:
            from tasks.grounded_planner import load_evidence_bundle
            from tasks.grounding_qa import run_grounding_qa

            grounded = {}
            grounded_path = os.path.join(validation_dir, "grounded_plan.json")
            if os.path.isfile(grounded_path):
                with open(grounded_path, encoding="utf-8") as handle:
                    grounded = json.load(handle) or {}
            slides_for_qa = grounded.get("slides") if isinstance(grounded, dict) else []
            if not isinstance(slides_for_qa, list):
                slides_for_qa = []
            slide_plan = {}
            plan_path = os.path.join(validation_dir, "slide_plan.json")
            if os.path.isfile(plan_path):
                with open(plan_path, encoding="utf-8") as handle:
                    slide_plan = json.load(handle) or {}
            plans_for_qa = slide_plan.get("slides") if isinstance(slide_plan, dict) else []
            if not isinstance(plans_for_qa, list):
                plans_for_qa = []
            evidence_bundle = load_evidence_bundle(storage_dir)
            gqa = run_grounding_qa(
                slides_for_qa,
                plans_for_qa,
                evidence_bundle if isinstance(evidence_bundle, dict) else {},
                grounding_mode,
            )
            if not isinstance(gqa, dict):
                gqa = {
                    "schema_version": "sunairum.grounding-qa/v1",
                    "status": "failed",
                    "issues": [{"detail": "grounding QA returned no report"}],
                }
            gqa.setdefault("schema_version", "sunairum.grounding-qa/v1")
            gqa_path = os.path.join(validation_dir, "grounding_qa.json")
            with open(gqa_path, "w", encoding="utf-8") as handle:
                json.dump(gqa, handle, ensure_ascii=False, indent=2)
            update_run_manifest(grounding_qa_status=gqa.get("status"))
        except Exception as gqa_error:
            print(f"[free_design] grounding QA skipped: {gqa_error}")

    num_slides = len(existing_slide_numbers(storage_dir)) or len(slides)
    # Optional pause for manual Fix/Generate (env). No Deep QA / qa_gate.
    if require_user_generate:
        update_run_manifest(status="awaiting_user_compile")
        write_status(
            storage_dir,
            "awaiting_user_compile",
            84,
            num_slides,
            num_slides,
            message="Slides ready — Fix or Generate when ready",
            message_key="status_awaiting_user_compile",
            run_id=run_id,
        )
        try:
            loop.run_until_complete(
                send_ws_message(
                    project_id,
                    {
                        "status_key": "status_awaiting_user_compile",
                        "progress": 84,
                        "authoring_mode": "free_design",
                    },
                )
            )
        except Exception:
            pass
        return {
            "status": "awaiting_user_compile",
            "project_id": project_id,
            "run_id": run_id,
            "authoring_mode": "free_design",
        }

    from tasks import generator_agent as _gen

    update_run_manifest(status="ready_to_compile")
    write_status(
        storage_dir,
        "compiling",
        85,
        num_slides,
        num_slides,
        message="Compiling free-design deck",
        message_key="status_compiling",
        run_id=run_id,
    )
    # One deckhtml compile; speaker notes embed inside finalize_compile_html.
    compile_result = _gen.finalize_compile(
        storage_dir,
        project_id=project_id,
        run_id=run_id or "",
    )
    return compile_result


def rematerialize_free_design_slides(
    storage_dir: str,
    slide_numbers: list[int],
    *,
    color_palette: dict[str, str] | None = None,
    call_text: Callable[[str, str], str] | None = None,
    gt=None,
    design_reference_brief: str = "",
    slide_feedback: dict[int, str] | None = None,
    project_id: str = "",
    write_status=None,
    send_ws_message=None,
    loop=None,
) -> dict[str, Any]:
    """Fix / regenerate path: re-author selected slides from project-root MD."""
    if gt is None:
        import tasks.generate_task as gt  # type: ignore

    design_path = os.path.join(storage_dir, "design_spec.md")
    lock_path = os.path.join(storage_dir, "spec_lock.md")
    if not os.path.isfile(design_path) or not os.path.isfile(lock_path):
        raise RuntimeError(
            "free_design Fix requires design_spec.md and spec_lock.md at project root"
        )
    with open(design_path, encoding="utf-8") as handle:
        design_spec_md = handle.read()
    with open(lock_path, encoding="utf-8") as handle:
        spec_lock_md = handle.read()

    parsed = strategist_agent.parse_section_ix_slides(design_spec_md)
    try:
        from tasks.strategist_ir import sanitize_parsed_slides
    except ImportError:  # pragma: no cover
        from strategist_ir import sanitize_parsed_slides  # type: ignore
    parsed = sanitize_parsed_slides(parsed, storage_dir=storage_dir)
    _uniquify_asset_bindings(parsed)
    slides = [_slide_dict_from_parsed(item) for item in parsed]
    by_num = {int(slide["slide"]): slide for slide in slides}
    targets = [by_num[n] for n in slide_numbers if n in by_num]
    if not targets:
        targets = slides

    feedback_map: dict[int, str] = {}
    if slide_feedback:
        for key, value in slide_feedback.items():
            try:
                feedback_map[int(key)] = str(value or "").strip()
            except (TypeError, ValueError):
                continue
    for slide in targets:
        n = int(slide["slide"])
        if n in feedback_map and feedback_map[n]:
            apply_human_feedback_to_slide(
                slide, feedback_map[n], call_text=call_text
            )

    palette = color_palette or {
        "background": "#FFFFFF",
        "primary": "#1E3A8A",
        "accent": "#F59E0B",
        "body_text": "#0F172A",
    }
    budget = AuthoringBudget(
        limit=max(len(targets) * _PER_SLIDE_AUTHOR_CALLS + 4, 4)
    )
    svg_dir = os.path.join(storage_dir, "svg_output")
    own_loop = False
    if loop is None and (write_status is not None or send_ws_message is not None):
        try:
            loop = asyncio.new_event_loop()
            own_loop = True
        except Exception:
            loop = None
    try:
        result = materialize_free_design_slides(
            slides=targets,
            design_spec_md=design_spec_md,
            spec_lock_md=spec_lock_md,
            storage_dir=storage_dir,
            svg_dir=svg_dir,  # unused on zero-SVG path; kept for call signature
            color_palette=palette,
            budget=budget,
            call_text=call_text,
            gt=gt,
            slide_filter={int(s["slide"]) for s in targets},
            design_reference_brief=design_reference_brief,
            slide_feedback=feedback_map or None,
            project_id=project_id,
            write_status=write_status,
            send_ws_message=send_ws_message,
            loop=loop,
        )
    finally:
        if own_loop and loop is not None:
            try:
                loop.close()
            except Exception:
                pass
    return {
        "rebuilt": [int(item["slide"]) for item in result.get("authored") or []],
        "mode": "free_design",
        "budget_spent": result.get("budget_spent"),
        "ts": int(time.time()),
        "feedback_slides": sorted(feedback_map.keys()),
    }
