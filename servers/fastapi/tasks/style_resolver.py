"""Deterministic Style Resolver: deck tone / Intent style → theme tokens."""

from __future__ import annotations

from typing import Any


_STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "academic": {
        "font_family": "Georgia, Times New Roman, serif",
        "body_family": "Arial, Helvetica Neue, sans-serif",
        "title_size": 32,
        "body_size": 16,
        "header_size": 15,
        "cell_size": 13,
        "row_height": 52,
        "gap": 12,
        "radius": 8,
        "density": "medium",
    },
    "bold": {
        "font_family": "Arial, Helvetica Neue, sans-serif",
        "body_family": "Arial, Helvetica Neue, sans-serif",
        "title_size": 36,
        "body_size": 17,
        "header_size": 16,
        "cell_size": 14,
        "row_height": 56,
        "gap": 14,
        "radius": 12,
        "density": "medium",
    },
    "compact": {
        "font_family": "Arial, Helvetica Neue, sans-serif",
        "body_family": "Arial, Helvetica Neue, sans-serif",
        "title_size": 28,
        "body_size": 14,
        "header_size": 13,
        "cell_size": 12,
        "row_height": 44,
        "gap": 8,
        "radius": 6,
        "density": "high",
    },
}


def resolve_style_tokens(
    *,
    style: str = "",
    visual_style: str = "",
    density: str = "",
    theme: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map style name + deck theme → concrete tokens for Infographic / tables."""
    theme = theme or {}
    key = (style or visual_style or "academic").strip().casefold()
    if key in {"professional", "formal", "paper", "scholarly"}:
        key = "academic"
    if key in {"modern", "punchy", "executive"}:
        key = "bold"
    if key in {"dense", "tight"}:
        key = "compact"
    preset = dict(_STYLE_PRESETS.get(key, _STYLE_PRESETS["academic"]))
    if density:
        preset["density"] = density
    # Palette + type from deck / pack theme (theme wins over presets).
    for src, dst in (
        ("primary", "primary"),
        ("accent", "accent"),
        ("ink", "ink"),
        ("body_text", "ink"),
        ("muted", "muted"),
        ("secondary_text", "muted"),
        ("text_secondary", "muted"),
        ("surface", "surface"),
        ("secondary_bg", "surface"),
        ("background", "surface"),
        ("zebra", "zebra"),
        ("border", "border"),
    ):
        val = str(theme.get(src) or "").strip()
        if val.startswith("#"):
            preset[dst] = val
    for src, dst in (
        ("font_family", "font_family"),
        ("body_family", "body_family"),
        ("title_family", "font_family"),
        ("font", "body_family"),
    ):
        val = str(theme.get(src) or "").strip()
        if val:
            preset[dst] = val
    for src, dst in (
        ("header_size", "header_size"),
        ("body_size", "body_size"),
        ("title_size", "title_size"),
    ):
        raw = theme.get(src)
        if raw is None:
            continue
        try:
            preset[dst] = float(raw)
        except (TypeError, ValueError):
            pass
    preset.setdefault("primary", "#0B3B6F")
    preset.setdefault("accent", "#E07A2F")
    preset.setdefault("ink", "#0F172A")
    preset.setdefault("muted", "#4A5568")
    preset.setdefault("surface", theme.get("surface") or "#F5F7FA")
    preset.setdefault("border", "#E2E8F0")
    preset["style_key"] = key
    return preset

