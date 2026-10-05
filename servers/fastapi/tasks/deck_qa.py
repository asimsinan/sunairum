"""Deterministic pre-compile quality checks for a generated deck.

Legacy path ran over ``svg_output/`` + ``images/``. Under zero-SVG, ``run_qa`` /
``run_qa_slide`` skip SVG product checks (IR/html_qa owns layout integrity).
All findings are advisory: recorded in ``validation/qa_report.json`` and
surfaced in the UI, but never withhold generation, compile, or export.
"""
import hashlib
import html
import json
import math
import os
import re

try:
    from PIL import Image
except Exception:  # pragma: no cover - container always ships Pillow
    Image = None

try:
    from .layout_geometry import text_width_px
except ImportError:  # pragma: no cover - supports direct task imports
    from layout_geometry import text_width_px

# A figure is "blank" when it is effectively empty white/near-white.
BLANK_MEAN = 245.0
BLANK_STDDEV = 12.0

_PLACEHOLDER_RE = re.compile(
    r'\{\{[^}]+\}\}|Lorem ipsum|TODO|FIXME|XXX\b|PLACEHOLDER',
    re.I,
)

# Hard font-size limits (mirrors the legacy checker's 1..4000pt band, but in
# SVG px here; px -> pt is 0.75x, so the px floor is 1.5).
FONT_MIN_PX = 1.5
FONT_MAX_PX = 4000.0

# These are visual legibility floors, separate from the malformed-value floor
# above. They can be lowered for a deliberately dense deck without changing the
# hard safety band.
DEFAULT_MIN_FONT_PX = 14.0
ROLE_MIN_FONT_PX = {
    "title": 28.0,
    "subtitle": 16.0,
    "body": 14.0,
    "table": 12.0,
    "table-header": 12.0,
    "metric": 16.0,
    "caption": 11.0,
    "label": 11.0,
    "marker": 10.0,
    "footer": 10.0,
}

# Product policy: QA never withholds generation / compile / export.
# Former hard categories stay listed for reporting/UI emphasis only.
STRUCTURAL_REPORT_CATEGORIES = frozenset({
    "missing-image",
    "blank-image",
    "placeholder-token",
    "slide-count",
    "font-size",
    "table-metadata-missing",
    "table-grid-mismatch",
    "generic-title",
    "table-covers-content",
    "missing-glyph",
})
HARD_BLOCK_CATEGORIES: frozenset[str] = frozenset()

# Categories that never block compile/export even when severity is error.
# (Also dropped from user-facing reports via REPORT_NOISE_CATEGORIES.)
# Dense free_design fit heuristics (text-overflow / text-overlap / canvas-margin)
# stay out of HARD_BLOCK but remain visible in the report — do not add them here.
EDITOR_ADVISORY_CATEGORIES = frozenset({
    "font-too-small",
    "duplicate-text",
    "duplicate-title",
    "duplicate-image",
    "marker-identity-missing",
    "marker-not-centered",
    "marker-outside-circle",
    "card-baseline-misalignment",
    "sparse-composition",
    "repeated-composition",
})

# Non-blocking editor advisories — keep out of user-facing QA reports entirely.
# Checks may still run for repair tooling; results are dropped before persist/UI.
REPORT_NOISE_CATEGORIES = EDITOR_ADVISORY_CATEGORIES


def material_report_issues(issues: list[dict]) -> list[dict]:
    """Drop non-actionable noise categories from a report issue list."""
    return [
        issue
        for issue in issues
        if isinstance(issue, dict)
        and issue.get("category") not in REPORT_NOISE_CATEGORIES
    ]


def hard_blocking_issues(issues: list[dict]) -> list[dict]:
    """Always empty — generation/export must not be blocked by QA."""
    return []

_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_NUMBER_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def _matrix_multiply(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
    """Multiply two SVG affine matrices represented as (a,b,c,d,e,f)."""
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def _matrix_point(matrix: tuple[float, ...], x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _parse_transform(value: str | None) -> tuple[float, ...]:
    if not value:
        return _IDENTITY
    result = _IDENTITY
    for name, raw_args in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", value):
        values = [float(v) for v in re.findall(_NUMBER_RE, raw_args)]
        name = name.lower()
        transform = _IDENTITY
        if name == "matrix" and len(values) >= 6:
            transform = tuple(values[:6])
        elif name == "translate" and values:
            transform = (1.0, 0.0, 0.0, 1.0, values[0], values[1] if len(values) > 1 else 0.0)
        elif name == "scale" and values:
            sy = values[1] if len(values) > 1 else values[0]
            transform = (values[0], 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate" and values:
            angle = math.radians(values[0])
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            transform = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(values) >= 3:
                cx, cy = values[1], values[2]
                transform = _matrix_multiply(
                    _matrix_multiply((1.0, 0.0, 0.0, 1.0, cx, cy), transform),
                    (1.0, 0.0, 0.0, 1.0, -cx, -cy),
                )
        result = _matrix_multiply(result, transform)
    return result


def _attrs_from_text(raw_attrs: str) -> dict[str, str]:
    return {
        key.lower(): value
        for key, quote, value in re.findall(r"([:\w.-]+)\s*=\s*([\"'])(.*?)\2", raw_attrs)
    }


def _style_value(attrs: dict[str, str], name: str) -> str | None:
    style = attrs.get("style", "")
    match = re.search(r"(?:^|;)\s*" + re.escape(name) + r"\s*:\s*([^;]+)", style, re.I)
    return match.group(1).strip() if match else None


def _role_tokens(attrs: dict[str, str]) -> tuple[str, ...]:
    values = []
    for key in (
        "role", "data-role", "data-pptx-role", "data-pptx-placeholder",
        "data-sunairum-role", "data-sunairum-marker-id", "id", "class",
        "data-pptx-replace-with", "data-table-role",
    ):
        if attrs.get(key):
            values.extend(re.findall(r"[a-z0-9]+", attrs[key].lower()))
    return tuple(values)


def _svg_contexts(svg: str) -> dict[int, tuple[tuple[float, ...], tuple[str, ...], dict[str, str]]]:
    """Capture inherited transforms and text styles at each SVG element."""
    contexts = {}
    stack = [(_IDENTITY, (), {"font-size": "12"})]
    tag_re = re.compile(r"<(/?)([A-Za-z][\w:.-]*)(\b[^>]*?)(/?)>")
    for match in tag_re.finditer(svg):
        closing, name, raw_attrs, self_close = match.groups()
        name = name.lower()
        if closing:
            if name in {"g", "svg"} and len(stack) > 1:
                stack.pop()
            continue
        attrs = _attrs_from_text(raw_attrs)
        parent_matrix, parent_tokens, parent_styles = stack[-1]
        matrix = _matrix_multiply(parent_matrix, _parse_transform(attrs.get("transform")))
        tokens = parent_tokens + _role_tokens(attrs)
        styles = dict(parent_styles)
        for key in (
            "font-size", "font-weight", "text-anchor", "letter-spacing",
            "display", "visibility", "opacity", "aria-hidden",
        ):
            if key in attrs:
                styles[key] = attrs[key]
            elif (value := _style_value(attrs, key)) is not None:
                styles[key] = value
        contexts[match.start()] = (matrix, tokens, styles | {"tag": name})
        if name in {"g", "svg"} and not self_close:
            stack.append((matrix, tokens, styles | {"tag": name}))
    return contexts


def _numeric(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    match = re.search(_NUMBER_RE, value)
    try:
        return float(match.group(0)) if match else default
    except ValueError:
        return default


def _visible_text(body: str) -> str:
    text = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _text_lines(body: str, attrs: dict[str, str], styles: dict[str, str], fs: float) -> list[tuple[str, float, float]]:
    """Return (visible line, baseline y, x) in the text element's local space."""
    x = _numeric(attrs.get("x"), 0.0)
    y = _numeric(attrs.get("y"), 0.0)
    direct = re.sub(r"<tspan\b[^>]*>.*?</tspan>", "", body, flags=re.S | re.I)
    lines = []
    direct_text = _visible_text(direct)
    if direct_text:
        lines.append((direct_text, y, x))
    current_y = y
    tspans = re.finditer(r"<tspan\b([^>]*)>(.*?)</tspan>", body, re.S | re.I)
    for tspan in tspans:
        t_attrs = _attrs_from_text(tspan.group(1))
        # Absolute tspan y wins over cumulative dy (LLM often mixes both).
        if t_attrs.get("y") is not None and str(t_attrs.get("y") or "").strip() != "":
            current_y = _numeric(t_attrs.get("y"), current_y)
        else:
            dy = _numeric(t_attrs.get("dy"), 0.0)
            if t_attrs.get("dy", "").lower().endswith("em"):
                dy *= fs
            current_y += dy
        line_x = _numeric(t_attrs.get("x"), x + _numeric(t_attrs.get("dx"), 0.0))
        line = _visible_text(tspan.group(2))
        if line:
            lines.append((line, current_y, line_x))
    return lines


def _text_record(match: re.Match, contexts: dict[int, tuple[tuple[float, ...], tuple[str, ...], dict[str, str]]]) -> dict | None:
    raw_attrs, body = match.group(1), match.group(2)
    attrs = _attrs_from_text(raw_attrs)
    matrix, tokens, styles = contexts.get(match.start(), (_IDENTITY, (), {"font-size": "12"}))
    fs = _numeric(attrs.get("font-size"), _numeric(_style_value(attrs, "font-size"), _numeric(styles.get("font-size"), 12.0)))
    if fs <= 0:
        return None
    lines = _text_lines(body, attrs, styles, fs)
    if not lines:
        return None
    weight = attrs.get("font-weight", _style_value(attrs, "font-weight") or styles.get("font-weight", "400"))
    bold = bool(re.search(r"(?:bold|[6-9]00)", weight, re.I))
    letter_spacing = _numeric(attrs.get("letter-spacing"), _numeric(_style_value(attrs, "letter-spacing"), _numeric(styles.get("letter-spacing"), 0.0)))
    font_family = (
        attrs.get("font-family")
        or _style_value(attrs, "font-family")
        or styles.get("font-family")
        or None
    )
    anchor = attrs.get("text-anchor", _style_value(attrs, "text-anchor") or styles.get("text-anchor", "start"))
    local_boxes = []
    for line, baseline, line_x in lines:
        # Must be the same estimator the fitter and the exporter use: a private
        # flat-ratio approximation here silently re-flagged text that had already
        # been fitted, and passed text that would overflow in PowerPoint.
        width = text_width_px(line, fs, letter_spacing, bold, font_family)
        if anchor == "middle":
            left, right = line_x - width / 2.0, line_x + width / 2.0
        elif anchor == "end":
            left, right = line_x - width, line_x
        else:
            left, right = line_x, line_x + width
        local_boxes.append((left, baseline - fs * 0.8, right, baseline + fs * 0.37))
    local_left = min(box[0] for box in local_boxes)
    local_top = min(box[1] for box in local_boxes)
    local_right = max(box[2] for box in local_boxes)
    local_bottom = max(box[3] for box in local_boxes)
    points = [
        _matrix_point(matrix, local_left, local_top),
        _matrix_point(matrix, local_right, local_top),
        _matrix_point(matrix, local_left, local_bottom),
        _matrix_point(matrix, local_right, local_bottom),
    ]
    bounds = (
        min(point[0] for point in points), min(point[1] for point in points),
        max(point[0] for point in points), max(point[1] for point in points),
    )
    scale_y = math.hypot(matrix[2], matrix[3]) or 1.0
    baseline = _matrix_point(matrix, lines[0][2], lines[0][1])
    role = _text_role(attrs, tokens)
    plain = " ".join(line[0] for line in lines)
    display = attrs.get("display", _style_value(attrs, "display") or styles.get("display", "inline")).lower()
    visibility = attrs.get("visibility", _style_value(attrs, "visibility") or styles.get("visibility", "visible")).lower()
    opacity = _numeric(attrs.get("opacity"), _numeric(_style_value(attrs, "opacity"), _numeric(styles.get("opacity"), 1.0)))
    aria_hidden = attrs.get("aria-hidden", styles.get("aria-hidden", "false")).lower()
    return {
        "plain": plain,
        "normalized": re.sub(r"\s+", " ", plain).strip().casefold(),
        "bounds": bounds,
        "baseline": baseline,
        "font_size": fs * scale_y,
        "raw_font_size": fs,
        "font_family": font_family,
        "bold": bold,
        "letter_spacing": letter_spacing,
        "role": role,
        "attrs": attrs,
        "tokens": tokens,
        "start": match.start(),
        "visible": display != "none" and visibility not in {"hidden", "collapse"} and opacity > 0 and aria_hidden != "true",
    }


def _text_role(attrs: dict[str, str], tokens: tuple[str, ...]) -> str:
    all_tokens = set(tokens + _role_tokens(attrs))
    if "marker" in all_tokens or "step" in all_tokens:
        return "marker"
    if "body" in all_tokens or "object" in all_tokens:
        return "body"
    # Layout names such as `title_content` live on the root SVG and therefore
    # appear in every descendant's context. An explicit object placeholder is
    # body copy; it must not inherit `title` from that layout name.
    if "title" in all_tokens or "heading" in all_tokens:
        return "title"
    if "subtitle" in all_tokens or "subhead" in all_tokens:
        return "subtitle"
    if "table" in all_tokens and ("header" in all_tokens or "column" in all_tokens):
        return "table-header"
    if "metric" in all_tokens or "kpi" in all_tokens:
        return "metric"
    if "caption" in all_tokens:
        return "caption"
    if "footer" in all_tokens or "source" in all_tokens:
        return "footer"
    if "label" in all_tokens:
        return "label"
    if "table" in all_tokens or "cell" in all_tokens or "row" in all_tokens:
        return "table"
    return "body"


def _svg_text_records(svg: str, *, include_native_hosts: bool = False) -> list[dict]:
    """Parse visible text records.

    By default skip Intent table/formula host groups so freehand overlap QA
    does not fight injected grids. Pass ``include_native_hosts=True`` for
    table-cell overflow audits that need carrier-local copy.
    """
    contexts = _svg_contexts(svg)
    records = []
    try:
        from tasks.svg_geometry import _inside_protected_native_group
    except ImportError:  # pragma: no cover
        try:
            from svg_geometry import _inside_protected_native_group  # type: ignore
        except ImportError:
            _inside_protected_native_group = None  # type: ignore
    for match in re.finditer(r"<text\b([^>]*)>(.*?)</text>", svg, re.S | re.I):
        if 'data-sunairum-source-table-text="1"' in match.group(1):
            continue
        if 'data-sunairum-page-number="1"' in match.group(1):
            continue
        if (
            not include_native_hosts
            and _inside_protected_native_group is not None
            and _inside_protected_native_group(svg, match.start())
        ):
            continue
        record = _text_record(match, contexts)
        if record and record["normalized"] and record["visible"]:
            records.append(record)
    return records


def _svg_rect_records(svg: str) -> list[dict]:
    contexts = _svg_contexts(svg)
    rects = []
    for match in re.finditer(r"<rect\b([^>]*)/?>", svg, re.S | re.I):
        attrs = _attrs_from_text(match.group(1))
        try:
            x, y = _numeric(attrs.get("x")), _numeric(attrs.get("y"))
            width, height = _numeric(attrs.get("width")), _numeric(attrs.get("height"))
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        matrix, tokens, _ = contexts.get(match.start(), (_IDENTITY, (), {}))
        points = [
            _matrix_point(matrix, x, y), _matrix_point(matrix, x + width, y),
            _matrix_point(matrix, x, y + height), _matrix_point(matrix, x + width, y + height),
        ]
        rects.append({
            "bounds": (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)),
            "attrs": attrs,
            "tokens": tokens,
            "start": match.start(),
        })
    for match in re.finditer(r'<g\b([^>]*data-pptx-bounds="([^"]+)"[^>]*)>', svg, re.S | re.I):
        values = [float(value) for value in re.findall(_NUMBER_RE, match.group(2))]
        if len(values) < 4:
            continue
        x, y, width, height = values[:4]
        matrix, tokens, _ = contexts.get(match.start(), (_IDENTITY, (), {}))
        transformed = _matrix_point(matrix, x, y), _matrix_point(matrix, x + width, y + height)
        rects.append({
            "bounds": (min(transformed[0][0], transformed[1][0]), min(transformed[0][1], transformed[1][1]), max(transformed[0][0], transformed[1][0]), max(transformed[0][1], transformed[1][1])),
            "attrs": _attrs_from_text(match.group(1)),
            "tokens": tokens + ("planned-zone",),
            "start": match.start(),
        })
    return rects


def _svg_line_records(svg: str) -> list[dict]:
    contexts = _svg_contexts(svg)
    lines = []
    for match in re.finditer(r"<line\b([^>]*)/?>", svg, re.S | re.I):
        attrs = _attrs_from_text(match.group(1))
        matrix, tokens, _ = contexts.get(match.start(), (_IDENTITY, (), {}))
        p1 = _matrix_point(matrix, _numeric(attrs.get("x1")), _numeric(attrs.get("y1")))
        p2 = _matrix_point(matrix, _numeric(attrs.get("x2")), _numeric(attrs.get("y2")))
        lines.append({"p1": p1, "p2": p2, "tokens": tokens, "attrs": attrs})
    return lines


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> tuple[float, float]:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])), max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _configured_min_font_px(value: float | None) -> float:
    if value is not None:
        return float(value)
    raw = os.environ.get("DECK_QA_MIN_FONT_PX", os.environ.get("DECK_QA_MIN_FONT_SIZE_PX"))
    try:
        return float(raw) if raw is not None else DEFAULT_MIN_FONT_PX
    except ValueError:
        return DEFAULT_MIN_FONT_PX


def _slide_number(name: str) -> int | str:
    m = re.search(r'(\d+)', name)
    return int(m.group(1)) if m else name


def _file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _blank_stats(path: str) -> tuple[float, float]:
    """(mean, stddev) luminance of the image, or (255, 0) on failure."""
    if Image is None:
        return 255.0, 0.0
    try:
        im = Image.open(path).convert("L")
        im.thumbnail((160, 160))
        px = list(im.getdata())
        mean = sum(px) / len(px)
        var = sum((p - mean) ** 2 for p in px) / len(px)
        return mean, var ** 0.5
    except Exception:
        return 255.0, 0.0


def _image_refs(svg_text: str) -> list[str]:
    refs = re.findall(r'\b(?:xlink:)?href="([^"]+\.png|[^"]+\.jpe?g|[^"]+\.webp)"', svg_text, re.I)
    refs += re.findall(r'\b(?:xlink:)?href="([^"]+)"[^>]*data-pptx-[^>]*image', svg_text)
    return refs


def check_images(svg_dir: str, images_dir: str) -> list[dict]:
    """Blank/near-white figures and missing image references."""
    issues: list[dict] = []
    image_cache: dict[str, dict] = {}
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        path = os.path.join(svg_dir, name)
        try:
            with open(path, encoding="utf-8") as stream:
                svg = stream.read()
        except Exception:
            continue
        for href in dict.fromkeys(_image_refs(svg)):
            if href.startswith("data:"):
                continue
            target = href
            if not os.path.isabs(target):
                target = os.path.normpath(os.path.join(svg_dir, target))
            if not os.path.exists(target):
                issues.append({
                    "slide": slide, "category": "missing-image", "severity": "error",
                    "detail": f"referenced image not found: {href}",
                })
                continue
            if target not in image_cache:
                image_cache[target] = {"mean": 0.0, "stddev": 0.0}
                image_cache[target]["mean"], image_cache[target]["stddev"] = _blank_stats(target)
            stats = image_cache[target]
            if stats["mean"] > BLANK_MEAN and stats["stddev"] < BLANK_STDDEV:
                issues.append({
                    "slide": slide, "category": "blank-image", "severity": "error",
                    "detail": f"near-blank image {os.path.basename(target)} "
                              f"(mean {stats['mean']:.0f}, stddev {stats['stddev']:.1f})",
                })
    return issues


def check_duplicate_images(svg_dir: str) -> list[dict]:
    """Identical image content referenced by more than one slide."""
    issues: list[dict] = []
    usage: dict[str, list[str]] = {}
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        path = os.path.join(svg_dir, name)
        try:
            with open(path, encoding="utf-8") as stream:
                svg = stream.read()
        except Exception:
            continue
        for href in dict.fromkeys(_image_refs(svg)):
            if href.startswith("data:"):
                continue
            target = href
            if not os.path.isabs(target):
                target = os.path.normpath(os.path.join(svg_dir, target))
            if not os.path.exists(target):
                continue
            usage.setdefault(target, []).append(name[:-4])
    for target, slides in usage.items():
        if len(slides) > 1:
            issues.append({
                "slide": ",".join(slides), "category": "duplicate-image",
                "severity": "warning",
                "detail": f"{os.path.basename(target)} reused on slides {', '.join(slides)}",
            })
    return issues


def check_duplicate_visible_text(svg_dir: str) -> list[dict]:
    """Find repeated visible strings on one slide.

    Repeated labels can be intentional, so non-overlapping repeats remain
    warnings. Overlapping repeats are blocking through ``text-overlap``.
    Text on separate slides is handled by the existing duplicate-title check.
    """
    issues: list[dict] = []
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as stream:
                records = _svg_text_records(stream.read())
        except Exception:
            continue
        visible: dict[str, list[dict]] = {}
        for record in records:
            if record["role"] in {"marker", "footer"}:
                continue
            visible.setdefault(record["normalized"], []).append(record)
        for text, matches in visible.items():
            if len(matches) > 1:
                overlap = any(
                    _overlap(first["bounds"], second["bounds"])[0] > 1.0
                    and _overlap(first["bounds"], second["bounds"])[1] > 0.5
                    for index, first in enumerate(matches)
                    for second in matches[index + 1:]
                )
                issues.append({
                    "slide": _slide_number(name),
                    "category": "duplicate-text",
                    "severity": "error" if overlap else "warning",
                    "detail": f"visible text repeated {len(matches)} times: {text[:100]!r}",
                })
    return issues


def check_cross_slide_repetition(svg_dir: str, minimum_chars: int = 40) -> list[dict]:
    """Find substantial body text that appears on more than one slide.

    Only titles were ever compared across slides, so a deck that restated the
    same paragraphs under different headings passed every check. Short strings
    are excluded: labels, axis names and footers legitimately recur.
    """
    by_text: dict[str, list[int | str]] = {}
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as stream:
                records = _svg_text_records(stream.read())
        except OSError:
            continue
        slide = _slide_number(name)
        for text in {
            record["normalized"]
            for record in records
            if record["role"] not in {"marker", "footer"}
            and len(record["normalized"]) >= minimum_chars
        }:
            by_text.setdefault(text, []).append(slide)
    issues: list[dict] = []
    for text, slides in by_text.items():
        if len(slides) > 1:
            issues.append({
                "slide": ",".join(str(slide) for slide in slides),
                "category": "duplicate-text",
                "severity": "warning",
                "detail": (
                    f"identical body text on slides {', '.join(str(s) for s in slides)}: {text[:100]!r}"
                ),
            })
    return issues


def check_svg_text(
    svg_dir: str,
    min_font_px: float | None = None,
    role_min_font_px: dict[str, float] | None = None,
) -> list[dict]:
    """Placeholder tokens, font sizes, duplicate titles, and visible text."""
    issues: list[dict] = []
    titles: dict[str, list[str]] = {}
    default_min = _configured_min_font_px(min_font_px)
    minimums = dict(ROLE_MIN_FONT_PX)
    minimums["body"] = default_min
    if role_min_font_px:
        minimums.update({str(role).lower(): float(size) for role, size in role_min_font_px.items()})
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        path = os.path.join(svg_dir, name)
        try:
            with open(path, encoding="utf-8") as stream:
                svg = stream.read()
        except Exception:
            continue
        records = _svg_text_records(svg)
        candidates = []
        for record in records:
            plain = record["plain"]
            m = _PLACEHOLDER_RE.search(plain)
            if m:
                issues.append({
                    "slide": slide, "category": "placeholder-token", "severity": "error",
                    "detail": f"placeholder text near {m.group(0)!r}: {plain[:80]}",
                })
            # A LEFT:/RIGHT: pair rendered verbatim is a serialized field structure
            # the binder failed to split -- debug output, not prose. One label alone
            # can be legitimate copy ("the left panel shows..."), a pair cannot.
            if len({d.group(1).upper() for d in re.finditer(r"\b(LEFT|RIGHT)\b\s*(?::|—|-\s)", plain)}) == 2:
                issues.append({
                    "slide": slide, "category": "placeholder-token", "severity": "error",
                    "detail": f"serialized LEFT/RIGHT field labels rendered as prose: {plain[:80]}",
                })
            candidates.append(plain)
            if record["role"] == "title" and record["normalized"] in {"slide", "slayt", "page", "title", "untitled"}:
                issues.append({
                    "slide": slide, "category": "generic-title", "severity": "error",
                    "detail": f"generic slide title is not acceptable: {plain!r}",
                })
            overflow = record["attrs"].get("data-sunairum-overflow-lines")
            if overflow and overflow != "0":
                overflow_count = int(overflow)
                # Any declared overflow line hard-blocks: copy escapes its box.
                issues.append({
                    "slide": slide,
                    "category": "text-overflow",
                    "severity": "error",
                    "lines_over_budget": overflow_count,
                    "detail": (
                        f"{overflow} line(s) more copy than the slot holds: {plain[:100]!r}"
                    ),
                })
            raw_size = record["raw_font_size"]
            if raw_size < FONT_MIN_PX or raw_size > FONT_MAX_PX:
                issues.append({
                    "slide": slide, "category": "font-size", "severity": "error",
                    "detail": f"font-size {raw_size:g}px out of range",
                })
            role = record["role"]
            # Free-design chips / axis labels often inherit the default "body"
            # role. Short fragments should use the label floor, not body.
            words = [part for part in re.split(r"\s+", plain) if part]
            if role == "body" and (len(plain) <= 36 or len(words) <= 5):
                role = "label"
            minimum = minimums.get(role, default_min)
            if record["font_size"] < minimum:
                # Dense presentation labels routinely sit under the body floor;
                # keep as advisory so export is not blocked by design type scale.
                issues.append({
                    "slide": slide,
                    "category": "font-too-small",
                    "severity": "warning",
                    "detail": (
                        f"transformed font-size {record['font_size']:.2f}px below "
                        f"{minimum:g}px for role {role}: {plain[:80]!r}"
                    ),
                })
        if candidates:
            title = max(candidates, key=len)
            titles.setdefault(title, []).append(slide)
    for title, slides in titles.items():
        if len(slides) > 1:
            issues.append({
                "slide": ",".join(str(s) for s in slides), "category": "duplicate-title",
                "severity": "warning",
                "detail": f"same title on slides {', '.join(str(s) for s in slides)}: {title[:60]}",
            })
    return issues + check_duplicate_visible_text(svg_dir)


def _table_cells(svg: str, records: list[dict]) -> list[tuple[float, float, float, float]]:
    """Table cells that declare their own box, in absolute coordinates.

    Cells used to be reconstructed by intersecting every rule drawn inside a
    rectangle that looked table-ish. That inferred a grid the renderer never had:
    a decorative divider added a phantom column boundary, and text that sat
    perfectly inside its real cell was reported as crossing an imaginary one.
    Table cells are emitted with their bounds now, so the check reads the box
    instead of guessing it, and a table that declares nothing is not audited on a
    guess.
    """
    cells = []
    for rect in _svg_rect_records(svg):
        attrs = rect["attrs"]
        tokens = set(rect["tokens"])
        if any(key in attrs for key in ("data-table-cell", "data-cell", "data-pptx-cell")) or "cell" in tokens:
            cells.append(rect["bounds"])
    return cells


def _table_text_issues(slide: int | str, svg: str, records: list[dict]) -> list[dict]:
    cells = _table_cells(svg, records)
    if not cells:
        return []
    issues = []
    assigned: dict[int, list[dict]] = {}
    for record in records:
        bx, by = record["baseline"]
        candidates = [cell for cell in cells if cell[0] - 1 <= bx <= cell[2] + 1 and cell[1] - 1 <= by <= cell[3] + 1]
        if not candidates:
            continue
        cell = min(candidates, key=lambda value: (value[2] - value[0]) * (value[3] - value[1]))
        tolerance = max(2.0, record["font_size"] * 0.18)
        if (
            record["bounds"][0] < cell[0] - tolerance
            or record["bounds"][2] > cell[2] + tolerance
            or record["bounds"][1] < cell[1] - tolerance
            or record["bounds"][3] > cell[3] + tolerance
        ):
            issues.append({
                "slide": slide,
                "category": "table-cell-overlap",
                "severity": "error",
                "detail": f"text {record['plain'][:100]!r} crosses table cell ({cell[0]:g},{cell[1]:g},{cell[2] - cell[0]:g},{cell[3] - cell[1]:g})",
            })
        assigned.setdefault(id(cell), []).append(record)
    for group in assigned.values():
        for index, first in enumerate(group):
            for second in group[index + 1:]:
                overlap_x, overlap_y = _overlap(first["bounds"], second["bounds"])
                if overlap_x > 1.0 and overlap_y > 0.5:
                    issues.append({
                        "slide": slide,
                        "category": "table-cell-overlap",
                        "severity": "error",
                        "detail": f"text boxes overlap in one table cell: {first['plain'][:50]!r} / {second['plain'][:50]!r}",
                    })
    return issues


def _text_overlap_issues(slide: int | str, records: list[dict]) -> list[dict]:
    issues = []
    for index, first in enumerate(records):
        for second in records[index + 1:]:
            overlap_x, overlap_y = _overlap(first["bounds"], second["bounds"])
            if overlap_x <= 1.0 or overlap_y <= 0.5:
                continue
            same_baseline = abs(first["baseline"][1] - second["baseline"][1]) <= max(2.0, max(first["font_size"], second["font_size"]) * 0.35)
            kind = "same-baseline" if same_baseline else "partial"
            overlap_area = overlap_x * overlap_y
            first_area = max(
                1.0,
                (first["bounds"][2] - first["bounds"][0])
                * (first["bounds"][3] - first["bounds"][1]),
            )
            second_area = max(
                1.0,
                (second["bounds"][2] - second["bounds"][0])
                * (second["bounds"][3] - second["bounds"][1]),
            )
            coverage = overlap_area / min(first_area, second_area)
            issues.append({
                "slide": slide,
                "category": "text-overlap",
                "severity": "warning" if coverage < 0.02 else "error",
                "overlap_area": round(overlap_area, 2),
                "overlap_coverage": round(coverage, 4),
                "detail": f"{kind} text boxes overlap: {first['plain'][:60]!r} / {second['plain'][:60]!r}",
            })
    return issues


def check_native_tables(svg_dir: str) -> list[dict]:
    """Validate native table carriers before the SVG fallback can be used."""
    issues: list[dict] = []
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as stream:
                svg = stream.read()
        except Exception:
            continue
        for group in re.finditer(
            r'<g\b[^>]*data-pptx-replace-with=["\']table["\'][^>]*>(.*?)</g>',
            svg,
            re.S | re.I,
        ):
            body = group.group(1)
            metadata = re.search(r'<metadata\b[^>]*>(.*?)</metadata>', body, re.S | re.I)
            if not metadata:
                issues.append({
                    "slide": slide, "category": "table-metadata-missing", "severity": "error",
                    "detail": "native table carrier has no JSON metadata",
                })
                continue
            try:
                payload = json.loads(html.unescape(metadata.group(1)).strip())
                columns = payload.get("columns", [])
                rows = payload.get("rows", [])
                style = payload.get("style", {})
                if not isinstance(columns, list) or not columns or not isinstance(rows, list) or not rows:
                    raise ValueError("table requires non-empty columns and rows")
                if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
                    raise ValueError("table rows do not match column count")
                font_size = float(style.get("font_size", 0) or 0)
                header_size = float(style.get("header_font_size", font_size) or 0)
                # Dense exact-PDF tables often shrink below 12px to fit. That is a
                # readability advisory — not a broken grid. Export still auto-bumps
                # fonts in rebuild_pptx; do not hard-block the deck here.
                if font_size < ROLE_MIN_FONT_PX["table"] or header_size < ROLE_MIN_FONT_PX["table-header"]:
                    issues.append({
                        "slide": slide,
                        "category": "table-font-size",
                        "severity": "warning",
                        "detail": (
                            f"table fonts {font_size:g}/{header_size:g}px below "
                            f"readable minimum "
                            f"{ROLE_MIN_FONT_PX['table']:g}/{ROLE_MIN_FONT_PX['table-header']:g}px"
                        ),
                    })
                    font_size = max(font_size, ROLE_MIN_FONT_PX["table"])
                    header_size = max(header_size, ROLE_MIN_FONT_PX["table-header"])
                table_width = float(payload.get("width", 0) or 0)
                table_height = float(payload.get("height", 0) or 0)
                column_weights = payload.get("column_widths") or [1] * len(columns)
                row_weights = payload.get("row_heights") or [1] * len(rows)
                if len(column_weights) != len(columns):
                    column_weights = list(column_weights[:len(columns)])
                    column_weights.extend([1] * (len(columns) - len(column_weights)))
                if len(row_weights) != len(rows):
                    row_weights = list(row_weights[:len(rows)])
                    row_weights.extend([1] * (len(rows) - len(row_weights)))
                if table_width > 0 and table_height > 0:
                    weight_total = max(sum(float(value) for value in column_weights), 1.0)
                    row_total = max(sum(float(value) for value in row_weights), 1.0)
                    padding = style.get("padding", {}) if isinstance(style.get("padding"), dict) else {}
                    horizontal_padding = float(padding.get("left", 12)) + float(padding.get("right", 12))
                    vertical_padding = float(padding.get("top", 6)) + float(padding.get("bottom", 6))
                    for row_index, row in enumerate(rows):
                        allocated_height = table_height * float(row_weights[row_index]) / row_total
                        required_height = 0.0
                        for col_index, cell in enumerate(row):
                            text = str(cell.get("text", "") if isinstance(cell, dict) else cell)
                            cell_width = table_width * float(column_weights[col_index]) / weight_total
                            chars_per_line = max(1, int(max(cell_width - horizontal_padding, 1) / max(font_size * 0.53, 1)))
                            line_count = max(1, max((math.ceil(len(line) / chars_per_line) for line in text.splitlines()), default=1))
                            required_height = max(required_height, line_count * max(font_size * 1.3, 1) + vertical_padding)
                        if required_height > allocated_height + 2:
                            raise ValueError(
                                f"row {row_index + 1} requires about {required_height:.1f}px but has {allocated_height:.1f}px"
                            )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                issues.append({
                    "slide": slide, "category": "table-grid-mismatch", "severity": "error",
                    "detail": f"invalid native table metadata: {exc}",
                })
    return issues


def check_number_marker_geometry(svg_dir: str) -> list[dict]:
    """Check numeric labels against nearby transformed circle geometry."""
    issues: list[dict] = []
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as stream:
                svg = stream.read()
        except Exception:
            continue
        contexts = _svg_contexts(svg)
        circles = []
        for match in re.finditer(r"<circle\b([^>]*)/?>", svg, re.S | re.I):
            attrs = _attrs_from_text(match.group(1))
            radius = _numeric(attrs.get("r"))
            if radius <= 0:
                continue
            matrix = contexts.get(match.start(), (_IDENTITY, (), {}))[0]
            center = _matrix_point(matrix, _numeric(attrs.get("cx")), _numeric(attrs.get("cy")))
            scale_x = math.hypot(matrix[0], matrix[1]) or 1.0
            scale_y = math.hypot(matrix[2], matrix[3]) or 1.0
            circles.append((center[0], center[1], radius * max(scale_x, scale_y), match.start(), attrs.get("data-sunairum-marker-id")))
        if not circles:
            continue
        records = _svg_text_records(svg)
        numeric = [record for record in records if re.fullmatch(r"\d{1,2}", record["plain"].strip())]
        for cx, cy, radius, _start, marker_id in circles:
            candidates = []
            for record in numeric:
                bx0, by0, bx1, by1 = record["bounds"]
                tx, ty = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
                distance = math.hypot(tx - cx, ty - cy)
                if distance <= radius * 1.5:
                    candidates.append((distance, record, tx, ty))
            if not candidates:
                continue
            _, record, tx, ty = min(candidates, key=lambda value: value[0])
            if not marker_id or not record["attrs"].get("data-sunairum-marker-id"):
                issues.append({
                    "slide": slide,
                    "category": "marker-identity-missing",
                    "severity": "warning",
                    "detail": f"numeric marker {record['plain']!r} is not bound to a stable marker ID",
                })
            center_tolerance = max(2.0, radius * 0.12)
            if abs(tx - cx) > center_tolerance or abs(ty - cy) > center_tolerance:
                issues.append({
                    "slide": slide,
                    "category": "marker-not-centered",
                    "severity": "warning",
                    "detail": f"numeric marker {record['plain']!r} is offset from circle center by ({tx - cx:.2f},{ty - cy:.2f})",
                })
            if tx - radius * 0.85 < cx - radius or tx + radius * 0.85 > cx + radius or ty - radius * 0.85 < cy - radius or ty + radius * 0.85 > cy + radius:
                issues.append({
                    "slide": slide,
                    "category": "marker-outside-circle",
                    "severity": "warning",
                    "detail": f"numeric marker {record['plain']!r} does not fit inside its circle",
                })
    return issues


def check_card_geometry(svg_dir: str) -> list[dict]:
    """Validate repeated metric-card text against card panels and rhythms."""
    issues: list[dict] = []
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as stream:
                svg = stream.read()
            records = _svg_text_records(svg)
            rects = _svg_rect_records(svg)
        except Exception:
            continue
        panels = [
            rect["bounds"] for rect in rects
            if any(token in rect["tokens"] for token in ("card", "panel"))
            and rect["bounds"][2] - rect["bounds"][0] >= 120
            and rect["bounds"][3] - rect["bounds"][1] >= 100
        ]
        if len(panels) < 2:
            continue
        baselines = []
        for panel in panels:
            inside = [
                record for record in records
                if panel[0] <= record["baseline"][0] <= panel[2]
                and panel[1] <= record["baseline"][1] <= panel[3]
                and set(record["tokens"]).intersection({"card", "kpi", "metric", "value"})
            ]
            for record in inside:
                if record["bounds"][0] < panel[0] or record["bounds"][2] > panel[2] or record["bounds"][1] < panel[1] or record["bounds"][3] > panel[3]:
                    issues.append({
                        "slide": slide, "category": "card-text-overflow", "severity": "error",
                        "detail": f"card text exceeds panel: {record['plain'][:100]!r}",
                    })
                baselines.append((record["font_size"], record["baseline"][1]))
        grouped_baselines: dict[int, list[float]] = {}
        for font_size, baseline in baselines:
            grouped_baselines.setdefault(round(font_size), []).append(baseline)
        if any(values and max(values) - min(values) > 8.0 for values in grouped_baselines.values()):
            issues.append({
                "slide": slide, "category": "card-baseline-misalignment", "severity": "error",
                "detail": "repeated card text does not share a baseline rhythm",
            })
    return issues


def check_text_geometry(svg_dir: str) -> list[dict]:
    """Check transformed text bounds, sibling collisions, and table cells."""
    issues: list[dict] = []
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as svg_file:
                svg = svg_file.read()
            records = _svg_text_records(svg)
            native_records = _svg_text_records(svg, include_native_hosts=True)
            rects = _svg_rect_records(svg)
        except Exception:
            continue
        view_box = re.search(r"viewBox\s*=\s*[\"']\s*" + _NUMBER_RE + r"\s+" + _NUMBER_RE + r"\s+(" + _NUMBER_RE + r")", svg, re.I)
        slide_width = _numeric(view_box.group(1), 1280.0) if view_box else 1280.0
        rect_bounds = [rect["bounds"] for rect in rects if rect["bounds"][2] - rect["bounds"][0] < 0.95 * slide_width]
        for record in records:
            if "chart" in record["tokens"]:
                continue
            frame_values = [
                float(value)
                for value in re.findall(_NUMBER_RE, record["attrs"].get("data-pptx-frame", ""))
            ]
            if len(frame_values) == 4:
                from tasks.text_layout import layout_block

                framed = layout_block(
                    record["plain"],
                    tuple(frame_values),
                    record["raw_font_size"],
                    record.get("font_family"),
                    bool(record.get("bold")),
                    float(record.get("letter_spacing") or 0.0),
                )
                if framed.fits:
                    # Structured export reflows this semantic copy in its declared
                    # frame. Raw SVG glyph bounds are not the release artifact.
                    continue
            bx, by = record["baseline"]
            candidates = []
            for rect in rect_bounds:
                if not (rect[0] <= bx <= rect[2] and rect[1] <= by <= rect[3]):
                    continue
                rw = rect[2] - rect[0]
                rh = rect[3] - rect[1]
                # Tall thin left accent rails are not text frames.
                if rect[0] <= 100 and rw <= 16 and rh >= 120 and rh > rw * 4:
                    continue
                candidates.append(rect)
            if not candidates:
                continue
            rx, ry, right, bottom = min(candidates, key=lambda rect: (rect[2] - rect[0]) * (rect[3] - rect[1]))
            tolerance = max(2.0, record["font_size"] * 0.18)
            left = record["bounds"][0]
            if (
                left < rx - tolerance or record["bounds"][2] > right + tolerance
                or record["bounds"][1] < ry - tolerance or record["bounds"][3] > bottom + tolerance
            ):
                issues.append({
                    "slide": slide,
                    "category": "text-overflow",
                    "severity": "error",
                    "detail": f"text {record['plain'][:100]!r} exceeds its containing rectangle ({rx:g},{ry:g},{right - rx:g},{bottom - ry:g})",
                })
        issues += _text_overlap_issues(slide, records)
        issues += _table_text_issues(slide, svg, native_records)
    return issues


SPARSE_PANEL_SLACK_FRACTION = 0.25
SPARSE_PANEL_SLACK_PX = 60.0
SPARSE_PANEL_MIN_AREA = 120_000.0


def check_composition_density(svg_dir: str) -> list[dict]:
    """Report panels that hold far less than they were drawn to hold.

    A certified panel is sized for the most copy its slot may carry. A grounded
    deck routinely carries less, and the result is an empty framed box around one
    paragraph. Rendered review reported that as poor balance without ever saying
    which box, so it was neither reproducible nor repairable. Measuring it here
    names the panel and costs no model call.
    """
    issues: list[dict] = []
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as stream:
                svg = stream.read()
            records = _svg_text_records(svg)
            rects = _svg_rect_records(svg)
        except Exception:
            continue
        visuals = []
        for raw in re.findall(r"<image\b([^>]*)>", svg, re.S | re.I):
            attrs = _attrs_from_text(raw)
            width, height = _numeric(attrs.get("width")), _numeric(attrs.get("height"))
            if width > 0 and height > 0:
                visuals.append((_numeric(attrs.get("x")), _numeric(attrs.get("y")), width, height))
        # A native table or chart is the panel's content even though its cells cover
        # little of it, so its declared box counts as occupancy.
        for payload in re.findall(
            r'data-pptx-replace-with="(?:table|chart)"[^>]*>\s*<metadata\b[^>]*>(.*?)</metadata>',
            svg,
            re.S,
        ):
            try:
                native = json.loads(payload)
                visuals.append((
                    float(native["x"]), float(native["y"]),
                    float(native["width"]), float(native["height"]),
                ))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        for rect in rects:
            left, top, right, bottom = rect["bounds"]
            width, height = right - left, bottom - top
            if width * height < SPARSE_PANEL_MIN_AREA:
                continue
            if not any(token in rect["tokens"] for token in ("card", "panel")):
                continue
            fill = str(rect["attrs"].get("fill") or "").strip().lower()
            if "data-pptx-bounds" in rect["attrs"] or fill in ("", "none"):
                # A slot box is a contract, not something a reader can see. Only a
                # drawn panel can look like an unfinished container.
                continue
            if any(
                image[0] < right and image[0] + image[2] > left
                and image[1] < bottom and image[1] + image[3] > top
                for image in visuals
            ):
                continue
            inside = [
                record["bounds"] for record in records
                if left <= record["baseline"][0] <= right
                and top <= record["baseline"][1] <= bottom
            ]
            if not inside:
                continue
            # Glyph area is the wrong measure: one short line in a wide panel covers
            # almost none of it and still looks deliberate, and a panel is furniture
            # that cannot be resized per slide. What reads as unfinished is copy
            # pinned to the top with a hole underneath, so the measure is how
            # lopsided the leftover space is.
            above = min(box[1] for box in inside) - top
            below = bottom - max(box[3] for box in inside)
            lopsided = below - above
            if lopsided <= SPARSE_PANEL_SLACK_PX or lopsided / height <= SPARSE_PANEL_SLACK_FRACTION:
                continue
            issues.append({
                "slide": slide,
                "category": "sparse-composition",
                "severity": "error" if lopsided / height > 0.5 else "warning",
                "detail": (
                    f"panel {rect['attrs'].get('id') or 'unnamed'} ({left:g},{top:g},{width:g},{height:g}) "
                    f"holds its content {lopsided:g}px ({lopsided / height * 100:.0f}%) above centre"
                ),
            })
    return issues


def check_layout_variety(svg_dir: str, run_limit: int = 3) -> list[dict]:
    """Report a deck that reuses one composition for run after run."""
    layouts: list[tuple[int, str]] = []
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as stream:
                svg = stream.read()
        except Exception:
            continue
        found = re.search(r'data-pptx-layout="([^"]+)"', svg)
        layouts.append((_slide_number(name), found.group(1) if found else ""))
    issues: list[dict] = []
    run: list[int] = []
    current = None
    for slide, layout in layouts + [(0, None)]:
        if layout == current and layout:
            run.append(slide)
            continue
        if current and len(run) >= run_limit:
            issues.append({
                "slides": list(run),
                "slide": ",".join(str(number) for number in run),
                "category": "repeated-composition",
                "severity": "warning",
                "detail": f"{len(run)} consecutive slides use the {current!r} composition",
            })
        current, run = layout, [slide]
    return issues


def check_slide_count(svg_dir: str, expected: int | None) -> list[dict]:
    if not expected:
        return []
    found = len([n for n in os.listdir(svg_dir) if n.endswith(".svg")])
    if found != expected:
        return [{
            "slide": "-", "category": "slide-count", "severity": "error",
            "detail": f"expected {expected} slides, found {found}",
        }]
    return []


def run_qa_slide(storage_dir: str, slide_number: int) -> dict:
    """QA checks restricted to one slide (used by the first-page gate)."""
    try:
        from tasks.html_flags import html_sot_enabled
    except ImportError:  # pragma: no cover
        from html_flags import html_sot_enabled  # type: ignore
    if html_sot_enabled(storage_dir):
        return {
            "slides_checked": 1,
            "status": "skipped",
            "issues": [],
            "error_count": 0,
            "skipped_html_sot": True,
        }
    svg_dir = os.path.join(storage_dir, "svg_output")
    images_dir = os.path.join(storage_dir, "images")
    issues = [
        i for i in (
            check_images(svg_dir, images_dir)
            + check_duplicate_images(svg_dir)
            + check_svg_text(svg_dir)
            + check_text_geometry(svg_dir)
            + check_native_tables(svg_dir)
            + check_number_marker_geometry(svg_dir)
            + check_card_geometry(svg_dir)
        )
        if i.get("slide") == slide_number
    ]
    issues = material_report_issues(issues)
    errors = [i for i in issues if i["severity"] == "error"]
    return {
        "slides_checked": 1,
        "status": "failed" if errors else ("passed-with-warnings" if issues else "passed"),
        "issues": sorted(issues, key=lambda i: i["category"]),
        "error_count": len(errors),
    }


def check_table_covers_and_margins(svg_dir: str) -> list[dict]:
    """Table∩figure collisions and canvas-margin escapes."""
    try:
        from tasks.table_layout import canvas_margin_issues, table_covers_content_issues
    except ImportError:  # pragma: no cover
        from table_layout import canvas_margin_issues, table_covers_content_issues  # type: ignore
    issues: list[dict] = []
    if not os.path.isdir(svg_dir):
        return issues
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as handle:
                svg = handle.read()
        except OSError:
            continue
        for issue in table_covers_content_issues(svg, slide=slide) + canvas_margin_issues(
            svg, slide=slide
        ):
            # Normalize to deck_qa issue shape (detail + message).
            issues.append(
                {
                    "slide": issue.get("slide", slide),
                    "category": issue.get("category"),
                    "severity": issue.get("severity") or "error",
                    "detail": issue.get("message") or issue.get("detail") or "",
                }
            )
    return issues


def check_missing_glyphs(svg_dir: str) -> list[dict]:
    """Hard-block leftover Unicode math glyphs Georgia/Arial cannot paint."""
    try:
        from tasks.unicode_math import svg_has_unsafe_math
    except ImportError:  # pragma: no cover
        from unicode_math import svg_has_unsafe_math  # type: ignore
    issues: list[dict] = []
    if not os.path.isdir(svg_dir):
        return issues
    for name in sorted(os.listdir(svg_dir)):
        if not name.endswith(".svg"):
            continue
        slide = _slide_number(name)
        try:
            with open(os.path.join(svg_dir, name), encoding="utf-8") as handle:
                svg = handle.read()
        except OSError:
            continue
        if svg_has_unsafe_math(svg):
            issues.append(
                {
                    "slide": slide,
                    "category": "missing-glyph",
                    "severity": "error",
                    "detail": "Unicode subscript/superscript math remains after sanitize",
                }
            )
    return issues


def check_figure_title_and_icon_overlap(svg_dir: str) -> list[dict]:
    """Retired with SVG freehand geometry stack."""
    del svg_dir
    return []


def run_qa(storage_dir: str, expected_slides: int | None = None) -> dict:
    """Run all deterministic checks; return a report dict (never raises)."""
    try:
        from tasks.html_flags import html_sot_enabled
    except ImportError:  # pragma: no cover
        from html_flags import html_sot_enabled  # type: ignore
    if html_sot_enabled(storage_dir):
        # Zero-SVG: skip svg_output product path; IR/html_qa owns layout checks.
        return {
            "generated_at": None,
            "slides_checked": expected_slides,
            "status": "skipped",
            "issues": [],
            "error_count": 0,
            "hard_error_count": 0,
            "advisory_error_count": 0,
            "skipped_html_sot": True,
        }
    svg_dir = os.path.join(storage_dir, "svg_output")
    images_dir = os.path.join(storage_dir, "images")
    issues: list[dict] = []
    if os.path.isdir(svg_dir):
        issues += check_images(svg_dir, images_dir)
        issues += check_duplicate_images(svg_dir)
        issues += check_svg_text(svg_dir)
        issues += check_text_geometry(svg_dir)
        issues += check_native_tables(svg_dir)
        issues += check_number_marker_geometry(svg_dir)
        issues += check_card_geometry(svg_dir)
        issues += check_cross_slide_repetition(svg_dir)
        issues += check_composition_density(svg_dir)
        issues += check_layout_variety(svg_dir)
        issues += check_table_covers_and_margins(svg_dir)
        issues += check_missing_glyphs(svg_dir)
        issues += check_figure_title_and_icon_overlap(svg_dir)
        issues += check_slide_count(svg_dir, expected_slides)
    if not os.path.isdir(svg_dir):
        issues.append({
            "slide": "-", "category": "slide-count", "severity": "error",
            "detail": f"svg_output/ missing in {storage_dir}",
        })
    issues = material_report_issues(issues)
    errors = [i for i in issues if i["severity"] == "error"]
    hard = hard_blocking_issues(issues)
    status = "failed" if hard else ("passed-with-warnings" if issues or errors else "passed")
    return {
        "generated_at": None,
        "slides_checked": expected_slides,
        "status": status,
        "issues": sorted(issues, key=lambda i: (str(i.get("slide", "-")), i["category"])),
        "error_count": len(errors),
        "hard_error_count": len(hard),
        "advisory_error_count": max(0, len(errors) - len(hard)),
    }


def write_report(storage_dir: str, report: dict, path: str | None = None) -> str:
    if path is None:
        path = os.path.join(storage_dir, "validation", "qa_report.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path
