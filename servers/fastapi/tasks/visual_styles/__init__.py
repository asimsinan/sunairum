"""Confirmed visual_style / mode → programmatic composition rules.

These are taste contracts for theme_agent / free_design — not SVG
rosters. Catalog ids from confirm_ui/result.json map to density, ornament
budget, chrome notes, and AI rendering paragraphs. Unknown ids fall back to a
neutral corporate rule.
"""

from __future__ import annotations

from typing import Any

# Slim rule table. Keys match confirm-UI visual_style catalog ids (and a few
# common aliases). Values are consumed by theme/storyboard briefs.
_STYLE_RULES: dict[str, dict[str, Any]] = {
    "swiss-minimal": {
        "density": "low",
        "ornament_budget": 1,
        "chrome": "sharp rules, generous margins, no rounded cards",
        "notes": "Swiss minimal: hierarchy through type and whitespace only",
        "rendering": "minimalist-swiss",
        "rendering_prompt": (
            "Strict Swiss-grid minimalism. Composition snaps to a modular grid; "
            "forms are essential geometric primitives; sans-serif typographic "
            "character with rigorous spacing. Color is sparse — one primary block, "
            "large near-white fields, a single accent. No gradients, shadows, "
            "texture, or decoration. Negative space carries equal weight to filled areas."
        ),
    },
    "minimal": {
        "density": "low",
        "ornament_budget": 1,
        "chrome": "sharp rules, generous margins, no rounded cards",
        "notes": "Minimal: reduce decoration; let statements breathe",
        "rendering": "minimalist-swiss",
        "rendering_prompt": (
            "Restrained minimal composition. Generous whitespace, flat fills, "
            "no gradients or shadows, one accent at most."
        ),
    },
    "soft-corporate": {
        "density": "medium",
        "ornament_budget": 3,
        "chrome": "soft panels, restrained accent bars",
        "notes": "Soft corporate: calm cards, clear sectioning",
        "rendering_prompt": (
            "Calm corporate illustration language: soft panels, clear sectioning, "
            "restrained accent bars, readable and friendly."
        ),
    },
    "corporate": {
        "density": "medium",
        "ornament_budget": 3,
        "chrome": "soft panels, restrained accent bars",
        "notes": "Corporate default: readable, restrained ornaments",
        "rendering_prompt": (
            "Professional corporate visuals: clean hierarchy, restrained ornaments, "
            "clear readable structure."
        ),
    },
    "bold-impact": {
        "density": "high",
        "ornament_budget": 4,
        "chrome": "strong accent blocks, large titles",
        "notes": "Bold impact: emphatic hierarchy, denser ornament permission",
        "rendering_prompt": (
            "Bold impact visuals: large shapes, strong accent blocks, emphatic "
            "contrast, energetic but still presentation-ready."
        ),
    },
    "bold": {
        "density": "high",
        "ornament_budget": 4,
        "chrome": "strong accent blocks, large titles",
        "notes": "Bold: emphatic hierarchy",
        "rendering_prompt": (
            "Bold, high-contrast illustration with emphatic hierarchy and strong accents."
        ),
    },
    "editorial": {
        "density": "medium",
        "ornament_budget": 2,
        "chrome": "asymmetric margins, numbered badges",
        "notes": "Editorial: magazine rhythm, badge-led steps",
        "rendering_prompt": (
            "Editorial magazine rhythm: asymmetric margins, numbered badges, "
            "considered typographic contrast."
        ),
    },
    "consulting": {
        "density": "medium",
        "ornament_budget": 2,
        "chrome": "tight grids, metric chips preferred",
        "notes": "Consulting: structured argument, metric emphasis",
        "rendering_prompt": (
            "Consulting-deck visuals: tight grids, metric emphasis, structured "
            "argument diagrams, crisp and analytical."
        ),
    },
    "brutalist": {
        "density": "high",
        "ornament_budget": 2,
        "chrome": "hard edges, high contrast, raw type",
        "notes": "Brutalist: raw contrast, hard edges",
        "rendering_prompt": (
            "Brutalist presentation visuals: hard edges, high contrast, raw type "
            "energy, minimal polish."
        ),
    },
    "creative": {
        "density": "medium",
        "ornament_budget": 4,
        "chrome": "expressive shapes, playful accent",
        "notes": "Creative: expressive but still slide-legible",
        "rendering_prompt": (
            "Creative but slide-legible visuals: expressive shapes, playful accent, "
            "still clear at presentation distance."
        ),
    },
    "glassmorphism": {
        "density": "medium",
        "ornament_budget": 3,
        "chrome": "frosted panels, soft depth, luminous accents",
        "notes": "Glassmorphism: frosted layers and soft depth",
        "rendering_prompt": (
            "Glassmorphism: frosted translucent panels, soft depth, luminous accents, "
            "modern product aesthetic."
        ),
    },
}

_DEFAULT_RULE: dict[str, Any] = {
    "density": "medium",
    "ornament_budget": 3,
    "chrome": "balanced panels and accents",
    "notes": "Neutral professional system",
    "rendering_prompt": (
        "Neutral professional slide illustration: balanced panels, clear hierarchy, "
        "restrained decoration."
    ),
}


def _normalize_id(value: str) -> str:
    return str(value or "").strip().casefold().replace("_", "-").replace(" ", "-")


def resolve_style_id(result_data: dict[str, Any] | None) -> str:
    """Extract the confirmed visual_style id from result.json."""
    data = result_data if isinstance(result_data, dict) else {}
    raw = data.get("visual_style")
    if isinstance(raw, dict):
        raw = raw.get("id") or raw.get("value") or raw.get("name") or ""
    if not raw or str(raw).strip().casefold() == "custom":
        return "corporate"
    return _normalize_id(str(raw))


def resolve_mode_id(result_data: dict[str, Any] | None) -> str:
    data = result_data if isinstance(result_data, dict) else {}
    raw = data.get("mode")
    if isinstance(raw, dict):
        raw = raw.get("id") or raw.get("value") or raw.get("name") or ""
    return _normalize_id(str(raw)) if raw else ""


def style_behavior(result_data: dict[str, Any] | None) -> str:
    data = result_data if isinstance(result_data, dict) else {}
    for key in ("visual_style_behavior", "mode_behavior"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = value.get("value") or value.get("text") or ""
            if str(text).strip():
                return str(text).strip()
    return ""


def rules_for(style_id: str) -> dict[str, Any]:
    key = _normalize_id(style_id)
    if key in _STYLE_RULES:
        return dict(_STYLE_RULES[key])
    # Alias: minimalist-swiss rendering name → swiss-minimal rules
    if key in {"minimalist-swiss", "swiss", "swiss-grid"}:
        return dict(_STYLE_RULES["swiss-minimal"])
    for known, rule in _STYLE_RULES.items():
        if known in key or key in known:
            return dict(rule)
    return dict(_DEFAULT_RULE)


def brief_enrichment(result_data: dict[str, Any] | None) -> dict[str, Any]:
    """Fields to merge into theme_agent / storyboard / figure briefs."""
    style_id = resolve_style_id(result_data)
    mode_id = resolve_mode_id(result_data)
    rule = rules_for(style_id)
    behavior = style_behavior(result_data)
    notes = rule.get("notes", "")
    if behavior:
        notes = f"{notes}. User style direction: {behavior}"
    rendering = ""
    strategy = result_data.get("image_strategy") if isinstance(result_data, dict) else None
    if isinstance(strategy, dict):
        rendering = str(strategy.get("rendering") or "").strip()
    if not rendering:
        rendering = str(rule.get("rendering") or style_id)
    rendering_rule = rules_for(rendering) if rendering else rule
    rendering_prompt = str(
        rendering_rule.get("rendering_prompt") or rule.get("rendering_prompt") or ""
    ).strip()
    art_direction_extra = (
        f"Visual style {style_id}: {rule.get('chrome', '')}. {notes}"
    ).strip()
    if rendering_prompt:
        art_direction_extra = f"{art_direction_extra} AI rendering: {rendering_prompt}".strip()
    return {
        "visual_style": style_id,
        "mode": mode_id,
        "density": rule.get("density", "medium"),
        "ornament_budget": int(rule.get("ornament_budget", 3) or 3),
        "chrome": rule.get("chrome", ""),
        "style_notes": notes,
        "rendering": rendering,
        "rendering_prompt": rendering_prompt,
        "art_direction_extra": art_direction_extra,
    }
