"""Extract authoritative design tokens from a gallery example pack.

Gallery packs own the deck design system (palette, type, chrome, icons, mood,
table/formula/chart language). They must never be slot-filled or geometrically
cloned — content and slide geometry stay original.
"""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any

from tasks.generate_task import APP_ROOT

# Pack lock keys → deck palette keys (theme_agent.PALETTE_KEYS + chrome extras).
_COLOR_ALIASES: dict[str, str] = {
    "bg": "background",
    "background": "background",
    "bg_secondary": "secondary_bg",
    "secondary_bg": "secondary_bg",
    "primary": "primary",
    "accent": "accent",
    "secondary": "secondary_accent",
    "secondary_accent": "secondary_accent",
    "text": "body_text",
    "body_text": "body_text",
    "text_secondary": "text_secondary",
    "secondary_text": "text_secondary",
    "muted": "text_secondary",
    "text_tertiary": "text_tertiary",
    "border": "border",
    "accent_tint": "accent_tint",
    "success": "success",
    "warning": "warning",
}

_CHART_PATTERN_RE = re.compile(
    r"\b(basic_table|consulting_table|harvey_balls_table|comparison_table|"
    r"kpi_cards|vertical_pillars|comparison_columns|module_composition|"
    r"vertical_list|bullet_chart|gauge_chart|numbered_steps|icon_grid|"
    r"labeled_card|quadrant_text_bullets)\b",
    re.I,
)


def _gallery_pack_dir(pack_id: str) -> str | None:
    if not pack_id or "/" in pack_id or ".." in pack_id:
        return None
    roots = []
    configured = os.environ.get("SUNAIRUM_EXAMPLES_DIR")
    if configured:
        roots.append(configured)
    roots.append(os.path.join(APP_ROOT, "examples"))
    roots.append(os.path.join("/app", "examples"))
    for root in roots:
        candidate = os.path.join(root, pack_id)
        if os.path.isdir(candidate):
            return candidate
    return None


def _read(path: str, limit: int = 120_000) -> str:
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read(limit)
    except OSError:
        return ""


def _section(md: str, heading: str, max_chars: int = 2000) -> str:
    """Pull a markdown ## section body by heading substring (case-insensitive)."""
    if not md or not heading:
        return ""
    pattern = re.compile(
        rf"(?ims)^##\s+[^\n]*{re.escape(heading)}[^\n]*\n(.*?)(?=^##\s|\Z)"
    )
    match = pattern.search(md)
    if not match:
        return ""
    body = re.sub(r"\n{3,}", "\n\n", match.group(1).strip())
    return body[:max_chars]


def _lock_kv(lock: str, section: str | None = None) -> dict[str, str]:
    """Parse `- key: value` rows; optionally limit to a ## section."""
    text = lock or ""
    if section:
        text = _section(text, section, max_chars=20_000) or ""
    out: dict[str, str] = {}
    for match in re.finditer(
        r"(?m)^-\s+([A-Za-z0-9_-]+):\s*(.+?)\s*$",
        text,
    ):
        key = match.group(1).strip()
        val = match.group(2).strip()
        if key and val:
            out[key] = val
    return out


def _colors_from_lock(lock: str) -> dict[str, str]:
    """Raw hex colors from the colors section (original lock key names)."""
    colors: dict[str, str] = {}
    for key, val in _lock_kv(lock, "colors").items():
        if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", val):
            colors[key] = val.upper() if len(val) in {4, 7, 9} else val
            if len(colors[key]) == 4:
                # #RGB → #RRGGBB
                c = colors[key]
                colors[key] = f"#{c[1]*2}{c[2]*2}{c[3]*2}"
    return colors


def normalize_palette(raw_colors: dict[str, str] | None) -> dict[str, str]:
    """Map pack lock color keys into deck palette + chrome keys."""
    raw = raw_colors or {}
    palette: dict[str, str] = {}
    for src, dest in _COLOR_ALIASES.items():
        val = raw.get(src)
        if val and str(val).startswith("#"):
            palette[dest] = str(val).upper()
    # Non-hex mood keys stay separate (handled by image mood parser).
    return palette


def _primary_family(stack: str) -> str:
    if not stack:
        return ""
    first = stack.split(",")[0].strip().strip("\"'")
    return first


def _typography_from_lock(lock: str) -> dict[str, Any]:
    # Every family here reaches the authored CSS, so it must be one the exporter
    # can embed — an Office face name is resolved by whatever the reader has
    # installed, which is not what Chromium measured. See ``tasks.font_policy``.
    from tasks.font_policy import MONO_FAMILY, SANS_FAMILY, SERIF_FAMILY, resolve_family

    rows = _lock_kv(lock, "typography")
    title_stack = rows.get("title_family") or rows.get("emphasis_family") or SERIF_FAMILY
    body_stack = rows.get("body_family") or rows.get("font_family") or SANS_FAMILY
    title_family = resolve_family(_primary_family(title_stack)) or SERIF_FAMILY
    body_family = resolve_family(_primary_family(body_stack)) or SANS_FAMILY

    def _size(key: str, default: float) -> float:
        try:
            return float(rows.get(key) or default)
        except (TypeError, ValueError):
            return default

    type_scale = {
        "cover_title": _size("cover_title", 64.0),
        "title": _size("title", 36.0),
        "heading": _size("subtitle", 26.0),
        "body": _size("body", 20.0) if rows.get("body") else _size("body", 20.0),
        "caption": _size("annotation", 14.0) or _size("footnote", 11.0),
        "hero_number": _size("hero_number", 48.0),
    }
    # Prefer explicit body from lock; Attention locks body at 20.
    if rows.get("body"):
        try:
            type_scale["body"] = float(rows["body"])
        except (TypeError, ValueError):
            pass
    return {
        "heading": {"primary": title_family, "css": "serif", "stack": title_family},
        "body": {"primary": body_family, "css": "sans-serif", "stack": body_family},
        "emphasis_family": resolve_family(
            _primary_family(rows.get("emphasis_family") or title_stack)
        )
        or title_family,
        "code_family": resolve_family(_primary_family(rows.get("code_family") or ""))
        or MONO_FAMILY,
        "type_scale": type_scale,
        "raw": rows,
    }


def _icons_from_lock(lock: str) -> dict[str, Any]:
    rows = _lock_kv(lock, "icons")
    inventory_raw = rows.get("inventory") or ""
    inventory = [
        part.strip()
        for part in re.split(r"[,|]", inventory_raw)
        if part.strip() and part.strip().casefold() != "none"
    ]
    stroke = rows.get("stroke_width") or ""
    try:
        stroke_f = float(stroke) if stroke else None
    except ValueError:
        stroke_f = None
    return {
        "library": rows.get("library") or "tabler-outline",
        "brand_library": rows.get("brand_library") or "",
        "stroke_width": stroke_f if stroke_f is not None else 2.0,
        "inventory": inventory,
    }


def _page_rhythm_from_lock(lock: str) -> dict[str, str]:
    return dict(_lock_kv(lock, "page_rhythm"))


def _page_charts_from_lock(lock: str) -> dict[str, str]:
    return dict(_lock_kv(lock, "page_charts"))


def _image_mood_from_lock(lock: str, pack_dir: str) -> dict[str, str]:
    rows = _lock_kv(lock, "colors")
    mood = {
        "image_rendering": str(rows.get("image_rendering") or "").strip(),
        "image_palette": str(rows.get("image_palette") or "").strip(),
    }
    prompts_path = os.path.join(pack_dir, "images", "image_prompts.json")
    raw = _read(prompts_path, limit=40_000)
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            if not mood["image_rendering"]:
                mood["image_rendering"] = str(
                    data.get("deck_rendering") or data.get("rendering") or ""
                ).strip()
            if not mood["image_palette"]:
                mood["image_palette"] = str(
                    data.get("deck_palette") or data.get("palette") or ""
                ).strip()
    return mood


def _spacing_chrome(design_spec: str, palette: dict[str, str]) -> dict[str, Any]:
    spacing: dict[str, float] = {}
    text = design_spec or ""
    for key, patterns in (
        (
            "margin",
            (
                r"(?i)(?:left|right|safe)\s*/?\s*(?:right\s*)?margins?[^0-9]*(\d+)\s*px",
                r"(?i)margins?\s*[:=]\s*(\d+)\s*px",
                r"(?i)(?:left|right)\s+(\d+)\s*px",
            ),
        ),
        (
            "gutter",
            (
                r"(?i)gutter[^0-9]*(\d+)\s*px",
                r"(?i)(?:block|card)\s*gap[^0-9]*(\d+)\s*(?:–|-|to)\s*(\d+)\s*px",
                r"(?i)(?:block|card)\s*gap[^0-9]*(\d+)\s*px",
            ),
        ),
        (
            "pad",
            (
                r"(?i)(?:card\s*)?pad(?:ding)?[^0-9]*(\d+)\s*px",
            ),
        ),
    ):
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                # Prefer upper bound of ranges like 8–16 / 40-60 for Attention cards.
                nums = [float(g) for g in match.groups() if g]
                spacing[key if key != "gutter" else ("block" if "gap" in pattern else key)] = (
                    max(nums) if nums else 0.0
                )
                break
    if "margin" not in spacing and re.search(r"(?i)\b60\s*px\b", text):
        spacing["margin"] = 60.0
    if "block" not in spacing:
        spacing["block"] = 28.0
    if "pad" not in spacing:
        spacing["pad"] = 24.0
    if "margin" not in spacing:
        spacing["margin"] = 60.0

    # Card radius: Attention/academic packs use 12; avoid taking 16 from "8–16px".
    if re.search(r"(?i)\b12\s*px\b.*\b(?:rx|radius|corner)|(?:rx|radius|corner).*\b12\s*px\b", text):
        card_rx = 12.0
    elif re.search(r"(?i)(?:rx|radius|corner)[^0-9]*8\s*(?:–|-|to|/)\s*16", text):
        card_rx = 12.0
    else:
        rx_match = re.search(r"(?i)(?:rx|radius|corner)[^0-9]*(\d+)", text)
        card_rx = float(rx_match.group(1)) if rx_match else 12.0
        if card_rx < 10 or card_rx > 16:
            card_rx = 12.0

    tint = (
        palette.get("accent_tint")
        or palette.get("secondary_bg")
        or palette.get("background")
        or "#EBF4FF"
    )
    surface = tint
    border = palette.get("border") or "#E2E8F0"
    tertiary = palette.get("text_tertiary") or "#A0AEC0"

    surface_notes = ""
    for heading in ("surface", "card", "visual theme", "theme style"):
        chunk = _section(design_spec, heading, max_chars=600)
        if chunk:
            surface_notes = chunk
            break

    gradient_notes = _section(design_spec, "gradient", max_chars=800)
    # Attention / academic-blueprint: vertical accent bar beside title.
    if re.search(r"(?i)vertical|accent\s*bar|6\s*[×x]\s*40|header\s*accent", text):
        header_rhythm = "vertical 6x40 accent bar beside page title"
    elif re.search(r"(?i)academic|blueprint|attention", text):
        header_rhythm = "vertical 6x40 accent bar beside page title"
    else:
        header_rhythm = "page title + thin primary divider"

    return {
        "spacing": spacing,
        "card_rx": card_rx,
        "surface": surface,
        "card": palette.get("background") or "#FFFFFF",
        "border": border,
        "text_tertiary": tertiary,
        "accent_tint": tint,
        "surface_treatment": surface_notes[:800],
        "gradient_notes": gradient_notes[:600],
        "header_rhythm": header_rhythm,
        # Page number only — never HERO*/topic/brand footer lines.
        "footer_rhythm": "muted page number only (right); nothing else in the footer band",
        "accent_bar": {"width": 6.0, "height": 40.0, "x": 60.0, "y": 56.0},
    }


def _remap_page_charts_by_role(
    page_charts: dict[str, str],
    *,
    page_count: int | None = None,
) -> dict[str, str]:
    """Map pack chart templates to roles — never copy Attention P## ids verbatim."""
    role_prefs: dict[str, str] = {}
    for _key, val in (page_charts or {}).items():
        name = str(val).strip()
        if not name:
            continue
        low = name.casefold()
        if "kpi" in low and "kpi" not in role_prefs:
            role_prefs["why_it_matters"] = name
            role_prefs["training_setup"] = name
        elif "table" in low and "table" not in role_prefs:
            role_prefs["comparison_table"] = name
            role_prefs["results"] = name
        elif "pillar" in low or "column" in low:
            role_prefs["limitations"] = name
        elif "list" in low or "ablation" in low:
            role_prefs["ablation"] = name
        elif "step" in low or "process" in low:
            role_prefs["mechanism"] = name
    # Keep preferred pattern names without page-index coupling.
    return role_prefs


def _load_academic_blueprint_method() -> dict[str, Any]:
    path = os.path.join(
        os.path.dirname(__file__), "design_methods", "academic_blueprint.md"
    )
    raw = _read(path, limit=40_000)
    if not raw:
        return {}
    preferred = "instructional"
    consumption = "balanced"
    m = re.search(r"(?m)^preferred_mode:\s*(\S+)", raw)
    if m:
        preferred = m.group(1).strip()
    m = re.search(r"(?m)^default_consumption_mode:\s*(\S+)", raw)
    if m:
        consumption = m.group(1).strip()
    roles: list[str] = []
    for line in raw.splitlines():
        if line.strip().startswith("|") and "Composition tendency" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and cells[0] and cells[0] != "Role" and not cells[0].startswith("---"):
                roles.append(cells[0])
    return {
        "method_id": "academic-blueprint",
        "preferred_mode": preferred,
        "default_consumption_mode": consumption,
        "page_roles": roles,
        "brief": raw[:4000],
    }


def _pack_uses_academic_method(pack_id: str, design_spec: str) -> bool:
    pid = (pack_id or "").casefold()
    if "attention" in pid or "academic" in pid or "blueprint" in pid:
        return True
    return bool(
        re.search(
            r"(?i)academic\s*blueprint|paper\s*deep-?read|instructional",
            design_spec or "",
        )
    )


def _preferred_patterns(design_spec: str, page_charts: dict[str, str]) -> list[str]:
    found: list[str] = []
    for val in page_charts.values():
        name = str(val).strip()
        if name and name not in found:
            found.append(name)
    for match in _CHART_PATTERN_RE.finditer(design_spec or ""):
        name = match.group(1).casefold()
        if name not in found:
            found.append(name)
    return found


def _table_guidelines(
    design_spec: str, palette: dict[str, str], preferred: list[str]
) -> dict[str, Any]:
    table_patterns = [
        p
        for p in preferred
        if "table" in p.casefold()
    ] or ["basic_table"]
    return {
        "preferred_patterns": table_patterns,
        "header_fill": palette.get("primary") or "#1A365D",
        "header_color": "#FFFFFF",
        "zebra": palette.get("accent_tint")
        or palette.get("secondary_bg")
        or "#EBF4FF",
        "grid_stroke": palette.get("border") or "#E2E8F0",
        "surface": palette.get("background") or "#FFFFFF",
        "treatment_notes": (_section(design_spec, "visualization", max_chars=800) or "")[:600],
    }


def _formula_guidelines(design_spec: str, palette: dict[str, str]) -> dict[str, Any]:
    policy = ""
    policy_sec = _section(design_spec, "formula", max_chars=800)
    if policy_sec:
        policy = policy_sec
    ink = palette.get("primary") or "#1A365D"
    # Explicit formula color in prose: color `#1A365D`
    color_match = re.search(
        r"(?i)(?:formula|rendered)[^\n#]*?(#[0-9A-Fa-f]{6})",
        design_spec or "",
    )
    if color_match:
        ink = color_match.group(1).upper()
    return {
        "ink": ink,
        "surface": palette.get("accent_tint")
        or palette.get("secondary_bg")
        or "#EBF4FF",
        "stroke": palette.get("primary") or ink,
        "muted": palette.get("text_secondary") or "#4A5568",
        "policy": policy[:500],
        "policy_mode": "mixed",
        "medium": "png_band",
        "layout_hints": ["centered formula + caption", "formula hero band"],
        "treatment_notes": policy[:400],
    }


def _chart_guidelines(
    design_spec: str,
    palette: dict[str, str],
    preferred: list[str],
    mood: dict[str, str],
) -> dict[str, Any]:
    chart_patterns = [p for p in preferred if "table" not in p.casefold()]
    return {
        "preferred_patterns": chart_patterns or preferred,
        "series": {
            "primary": palette.get("primary") or "#1A365D",
            "accent": palette.get("accent") or "#3182CE",
            "secondary": palette.get("secondary_accent") or "#63B3ED",
        },
        "field": palette.get("background") or "#FFFFFF",
        "grid_stroke": palette.get("border") or "#E2E8F0",
        "rendering_mood": " × ".join(
            part for part in (mood.get("image_rendering"), mood.get("image_palette")) if part
        ),
        "treatment_notes": (_section(design_spec, "visualization", max_chars=800) or "")[:600],
    }


def _cover_treatment(design_spec: str) -> str:
    for heading in ("cover", "image resource", "layout"):
        chunk = _section(design_spec, heading, max_chars=500)
        if chunk and re.search(r"(?i)cover|full-bleed|scrim|hero", chunk):
            return chunk[:500]
    if re.search(r"(?i)full-bleed|scrim|calm region", design_spec or ""):
        return "full-bleed cover with scrim and calm title region"
    return "title plate with restrained chrome"


def _layout_pattern_hints(pack_dir: str) -> list[str]:
    """Layout-pattern vocabulary without reading pack SVG geometry.

    Prefer preview/ PNG stems, then design_spec section headings, then
    legacy svg_final stems only as offline labels (never cloned as geometry).
    """
    preview_dir = os.path.join(pack_dir, "preview")
    if os.path.isdir(preview_dir):
        paths = sorted(
            glob.glob(os.path.join(preview_dir, "*.png"))
            + glob.glob(os.path.join(preview_dir, "*.html"))
        )
        if paths:
            hints = []
            for path in paths[:16]:
                stem = os.path.splitext(os.path.basename(path))[0]
                stem = re.sub(r"^\d+_", "", stem)
                hints.append(stem.replace("_", " "))
            return hints
    design_spec = ""
    try:
        with open(os.path.join(pack_dir, "design_spec.md"), encoding="utf-8") as handle:
            design_spec = handle.read(40_000)
    except OSError:
        design_spec = ""
    headings = re.findall(r"(?m)^#{2,3}\s+(.+)$", design_spec or "")
    if headings:
        return [h.strip()[:80] for h in headings[:16] if h.strip()]
    # Legacy pack folders may still store SVG previews on disk; use stems as
    # prose labels only — never scrape geometry into the HTML Executor.
    for subdir in ("svg_final", "svg_output"):
        paths = sorted(glob.glob(os.path.join(pack_dir, subdir, "*.svg")))
        if not paths:
            continue
        hints = []
        for path in paths[:16]:
            stem = os.path.splitext(os.path.basename(path))[0]
            stem = re.sub(r"^\d+_", "", stem)
            hints.append(stem.replace("_", " ") + " (pattern label)")
        return hints
    return []


def _density_from_spec(design_spec: str, typography: dict[str, Any]) -> str:
    """Infer deck density from explicit density language — not incidental 'tight' prose."""
    body = float((typography.get("type_scale") or {}).get("body") or 18)
    text = design_spec or ""
    if re.search(r"(?i)\b(sparse|low[\s-]?density|density\s*[:=]\s*low)\b", text):
        return "low"
    if re.search(
        r"(?i)\b("
        r"high[\s-]?density|dense[\s-]?brief|density\s*[:=]\s*high|"
        r"tight\s+(?:spacing|density|layout)|compact\s+density"
        r")\b",
        text,
    ):
        return "high"
    if re.search(
        r"(?i)\b("
        r"medium[\s-]?dense|medium[\s-]?density|medium[\s-]?high|"
        r"density\s*[:=]\s*medium"
        r")\b",
        text,
    ):
        return "medium"
    if body >= 20:
        return "medium"
    if body <= 15:
        return "high"
    return "medium"


def _visual_style_from_spec(design_spec: str) -> str:
    match = re.search(
        r"\*\*Theme Style\*\*[:\s]*([^\n]+)|"
        r"visual\s*style[:\s]*\*?\*?([^\n*]+)",
        design_spec or "",
        flags=re.I,
    )
    if match:
        return (match.group(1) or match.group(2) or "").strip()[:80]
    if re.search(r"cool-corporate|corporate", design_spec or "", flags=re.I):
        return "corporate"
    if re.search(r"swiss", design_spec or "", flags=re.I):
        return "swiss-minimal"
    return "corporate"


def build_design_tokens(
    *,
    pack_id: str,
    design_spec: str,
    spec_lock: str,
    pack_dir: str,
) -> dict[str, Any]:
    """Canonical structured tokens from pack lock + design_spec."""
    raw_colors = _colors_from_lock(spec_lock)
    # Also keep non-hex color-section strings for mood
    palette = normalize_palette(raw_colors)
    typography = _typography_from_lock(spec_lock)
    icons = _icons_from_lock(spec_lock)
    mood = _image_mood_from_lock(spec_lock, pack_dir)
    chrome = _spacing_chrome(design_spec, palette)
    page_rhythm = _page_rhythm_from_lock(spec_lock)
    raw_page_charts = _page_charts_from_lock(spec_lock)
    page_charts = _remap_page_charts_by_role(raw_page_charts)
    preferred = _preferred_patterns(design_spec, raw_page_charts)
    table = _table_guidelines(design_spec, palette, preferred)
    formula = _formula_guidelines(design_spec, palette)
    # Mixed policy (Attention): block equations → PNG formula-band.
    if re.search(r"(?i)mixed|codecogs|formula_manifest|PNG", design_spec or ""):
        formula["policy_mode"] = "mixed"
        formula["medium"] = "png_band"
    else:
        formula.setdefault("policy_mode", "mixed")
        formula.setdefault("medium", "png_band")
    chart = _chart_guidelines(design_spec, palette, preferred, mood)
    layout_patterns = _layout_pattern_hints(pack_dir)
    density = _density_from_spec(design_spec, typography)
    visual_style = _visual_style_from_spec(design_spec)
    method: dict[str, Any] = {}
    if _pack_uses_academic_method(pack_id, design_spec):
        method = _load_academic_blueprint_method()
        if method.get("preferred_mode") and visual_style in {"corporate", ""}:
            visual_style = "blueprint"

    return {
        "pack_id": pack_id,
        "palette": palette,
        "raw_colors": raw_colors,
        "typography": typography,
        "type_scale": typography.get("type_scale") or {},
        "spacing": chrome.get("spacing") or {},
        "chrome": {
            "surface": chrome["surface"],
            "card": chrome["card"],
            "border": chrome["border"],
            "text_tertiary": chrome["text_tertiary"],
            "accent_tint": chrome["accent_tint"],
            "card_rx": chrome["card_rx"],
            "header_rhythm": chrome["header_rhythm"],
            "footer_rhythm": chrome["footer_rhythm"],
            "surface_treatment": chrome["surface_treatment"],
            "gradient_notes": chrome["gradient_notes"],
            "accent_bar": chrome.get("accent_bar") or {},
        },
        "icons": icons,
        "image_mood": mood,
        "table": table,
        "formula": formula,
        "chart": chart,
        "method": method,
        "cover_treatment": _cover_treatment(design_spec),
        "layout": {
            "density": density,
            "visual_style": visual_style,
            "page_rhythm": page_rhythm,
            "page_charts": page_charts,
            "page_charts_raw": raw_page_charts,
            "layout_patterns": layout_patterns,
            "preferred_patterns": preferred,
        },
    }


def apply_tokens_to_result(result: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    """Write pack tokens into confirm_ui-shaped result_data (mutates + returns)."""
    if not tokens:
        return result
    out = result if isinstance(result, dict) else {}
    palette = dict(tokens.get("palette") or {})
    # Deck palette keys expected by strategist / theme_agent
    deck_palette = {
        "background": palette.get("background") or "#FFFFFF",
        "secondary_bg": palette.get("secondary_bg") or "#F5F7FA",
        "primary": palette.get("primary") or "#1A365D",
        "accent": palette.get("accent") or "#3182CE",
        "secondary_accent": palette.get("secondary_accent") or "#63B3ED",
        "body_text": palette.get("body_text") or "#1A202C",
    }
    # Preserve chrome extras for adapters
    for key in (
        "text_secondary",
        "text_tertiary",
        "border",
        "accent_tint",
        "success",
        "warning",
    ):
        if palette.get(key):
            deck_palette[key] = palette[key]

    out["color"] = {
        **(out.get("color") if isinstance(out.get("color"), dict) else {}),
        "palette": deck_palette,
        "source": "pack",
    }
    typo = tokens.get("typography") if isinstance(tokens.get("typography"), dict) else {}
    out["typography"] = {
        "heading": dict(typo.get("heading") or {"primary": "Georgia", "css": "serif"}),
        "body": dict(typo.get("body") or {"primary": "Arial", "css": "sans-serif"}),
        "body_size": float((tokens.get("type_scale") or {}).get("body") or 18),
        "type_scale": dict(tokens.get("type_scale") or typo.get("type_scale") or {}),
        "source": "pack",
    }
    icons = tokens.get("icons") if isinstance(tokens.get("icons"), dict) else {}
    out["icons"] = {
        "library": icons.get("library") or "tabler-outline",
        "brand_library": icons.get("brand_library") or "",
        "stroke_width": icons.get("stroke_width") or 2,
        "inventory": list(icons.get("inventory") or []),
        "source": "pack",
    }
    mood = tokens.get("image_mood") if isinstance(tokens.get("image_mood"), dict) else {}
    if mood.get("image_rendering"):
        out["image_rendering"] = mood["image_rendering"]
    if mood.get("image_palette"):
        out["image_palette"] = mood["image_palette"]
    layout = tokens.get("layout") if isinstance(tokens.get("layout"), dict) else {}
    if layout.get("visual_style"):
        out["visual_style"] = layout["visual_style"]
    if layout.get("density"):
        out["density"] = layout["density"]
    out["design_tokens"] = tokens
    return out


def extract_design_reference(pack_id: str) -> dict[str, Any]:
    """Structured design reference for Strategist / Executor / theme SoT."""
    pack_dir = _gallery_pack_dir(pack_id)
    if not pack_dir:
        return {"pack_id": pack_id, "available": False, "brief": "", "tokens": {}}

    design_spec = _read(os.path.join(pack_dir, "design_spec.md"))
    spec_lock = _read(os.path.join(pack_dir, "spec_lock.md"), limit=40_000)
    readme = _read(os.path.join(pack_dir, "README.md"), limit=20_000)

    tokens = build_design_tokens(
        pack_id=pack_id,
        design_spec=design_spec,
        spec_lock=spec_lock,
        pack_dir=pack_dir,
    )
    colors = tokens.get("raw_colors") or {}
    palette_section = _section(design_spec, "palette") or _section(design_spec, "color")
    type_section = _section(design_spec, "typograph") or _section(design_spec, "font")
    layout_section = _section(design_spec, "layout") or _section(design_spec, "structure")
    icon_section = _section(design_spec, "icon") or _section(design_spec, "ornament")
    patterns = list((tokens.get("layout") or {}).get("layout_patterns") or [])

    title_match = re.search(r"(?m)^#\s+(.+)$", readme) or re.search(
        r"(?m)^#\s+(.+)$", design_spec
    )
    title = (title_match.group(1).strip() if title_match else pack_id)

    brief_parts = [
        f"Design reference pack: {pack_id} ({title}).",
        "Executor owns Constrained HTML pages (materialize → Slide IR → native PPTX). "
        "Obey palette/type/spacing as CSS/HTML tokens; never clone pack slide geometry "
        "or legacy SVG markup. Write html_output/ (+ ir/, preview/) — never svg_output/.",
        "This pack is the AUTHORITATIVE design system for the deck: colors, typography, "
        "icons, spacing/chrome, AI image mood, density, page rhythm, and table/formula/chart "
        "language. Do NOT invent a second palette, type stack, icon library, or image mood. "
        "Do NOT clone slide geometry, group ids, placeholder tokens, or the pack's original "
        "subject copy. Author original Constrained HTML pages that obey this system; leave "
        "table/chart/formula/figure hosts empty when bound (Intent fills them).",
    ]
    method = tokens.get("method") if isinstance(tokens.get("method"), dict) else {}
    if method.get("method_id"):
        brief_parts.append(
            f"Method pack: {method.get('method_id')} "
            f"(preferred_mode={method.get('preferred_mode')}, "
            f"consumption_default={method.get('default_consumption_mode')}). "
            "Follow its page-role vocabulary (Cover, Why it matters, Formula block, "
            "Results, Ablation, …) for instructional paper decks."
        )
        if method.get("brief"):
            brief_parts.append(
                "Method notes:\n" + str(method.get("brief") or "")[:1600]
            )
    chrome = tokens.get("chrome") if isinstance(tokens.get("chrome"), dict) else {}
    if chrome.get("header_rhythm"):
        brief_parts.append(f"Header chrome: {chrome['header_rhythm']}.")
    if chrome.get("footer_rhythm"):
        brief_parts.append(f"Footer chrome: {chrome['footer_rhythm']}.")
    spacing = tokens.get("spacing") if isinstance(tokens.get("spacing"), dict) else {}
    if spacing:
        brief_parts.append(
            "Spacing: "
            + ", ".join(f"{k}={v:g}px" for k, v in list(spacing.items())[:6])
            + f"; card_rx={chrome.get('card_rx', 12)}."
        )
    scale = tokens.get("type_scale") if isinstance(tokens.get("type_scale"), dict) else {}
    if scale:
        brief_parts.append(
            "Type scale: "
            + ", ".join(f"{k}={v}" for k, v in list(scale.items())[:6])
            + "."
        )
    palette = tokens.get("palette") or {}
    if palette:
        swatches = ", ".join(f"{k}={v}" for k, v in list(palette.items())[:14])
        brief_parts.append(f"Locked palette: {swatches}.")
    mood = tokens.get("image_mood") or {}
    if mood.get("image_rendering") or mood.get("image_palette"):
        brief_parts.append(
            f"AI image mood: rendering={mood.get('image_rendering') or 'n/a'}, "
            f"palette={mood.get('image_palette') or 'n/a'}."
        )
    icons = tokens.get("icons") or {}
    if icons:
        brief_parts.append(
            f"Icons: library={icons.get('library')}, stroke_width={icons.get('stroke_width')}, "
            f"inventory={', '.join(list(icons.get('inventory') or [])[:12])}."
        )
    layout = tokens.get("layout") or {}
    brief_parts.append(
        f"Density={layout.get('density')}; visual_style={layout.get('visual_style')}; "
        f"cover={tokens.get('cover_treatment') or 'n/a'}."
    )
    if tokens.get("table"):
        brief_parts.append(
            "Table language: preferred="
            + ", ".join((tokens["table"].get("preferred_patterns") or [])[:6])
            + f"; header={tokens['table'].get('header_fill')}; "
            f"zebra={tokens['table'].get('zebra')}."
        )
    if tokens.get("formula"):
        brief_parts.append(
            f"Formula language: ink={tokens['formula'].get('ink')}; "
            f"surface={tokens['formula'].get('surface')}."
        )
    if tokens.get("chart"):
        brief_parts.append(
            "Chart language: preferred="
            + ", ".join((tokens["chart"].get("preferred_patterns") or [])[:8])
            + f"; series primary={((tokens['chart'].get('series') or {}).get('primary'))}."
        )
    if palette_section:
        brief_parts.append(f"Palette notes:\n{palette_section[:900]}")
    if type_section:
        brief_parts.append(f"Typography notes:\n{type_section[:900]}")
    if layout_section:
        brief_parts.append(f"Layout language:\n{layout_section[:900]}")
    if icon_section:
        brief_parts.append(f"Icon / ornament language:\n{icon_section[:700]}")
    if patterns:
        brief_parts.append(
            "Example page pattern names (structure vocabulary, do not copy geometry): "
            + ", ".join(patterns)
            + "."
        )

    brief = "\n\n".join(brief_parts)
    brief = re.sub(r"[\u3400-\u9fff\uf900-\ufaff]+", " ", brief)
    brief = re.sub(r"\s{2,}", " ", brief).strip()
    title = re.sub(r"[\u3400-\u9fff\uf900-\ufaff]+", " ", title)
    title = re.sub(r"\s{2,}", " ", title).strip() or pack_id
    return {
        "pack_id": pack_id,
        "available": True,
        "title": title,
        "colors": colors,
        "palette": palette,
        "tokens": tokens,
        "layout_patterns": patterns,
        "brief": brief[:8000],
    }


def design_reference_brief(pack_id: str | None) -> str:
    if not pack_id:
        return ""
    return str(extract_design_reference(pack_id).get("brief") or "")
