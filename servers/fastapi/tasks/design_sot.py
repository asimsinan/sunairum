"""Unify Design SoT: gallery pack OR confirm_ui → same token/brief shape."""

from __future__ import annotations

from typing import Any


def craft_curriculum_from_tokens(tokens: dict[str, Any] | None) -> list[str]:
    """Concrete craft Defaults bullets from pack/UI tokens (not 'be beautiful')."""
    data = tokens if isinstance(tokens, dict) else {}
    typo = data.get("typography") if isinstance(data.get("typography"), dict) else {}
    scale = data.get("type_scale") if isinstance(data.get("type_scale"), dict) else {}
    if not scale and isinstance(typo.get("type_scale"), dict):
        scale = typo["type_scale"]
    layout = data.get("layout") if isinstance(data.get("layout"), dict) else {}
    density = str(layout.get("density") or data.get("density") or "medium").casefold()
    body_size = float(scale.get("body") or typo.get("body_size") or 18)
    title_size = float(scale.get("title") or scale.get("heading") or max(32, body_size + 16))
    caption = float(scale.get("caption") or max(12, body_size - 4))
    if density in {"dense", "compact", "high"}:
        margin, gap, card_cap = 36, 16, 4
    elif density in {"sparse", "airy", "low"}:
        margin, gap, card_cap = 56, 28, 2
    else:
        margin, gap, card_cap = 48, 24, 3
    lines = [
        f"Type ladder: title≈{title_size:g}px, body≈{body_size:g}px, caption≈{caption:g}px (±2)",
        f"Page inset ≥{margin}px from canvas edges; ≥{gap}px between sibling blocks",
        "Fill Contract: content energy=vivid; solid primary/accent mass + accent_tint surfaces",
        "Content pages: use secondary_accent at least once; never title+footer-only",
        "Success/warning colors for favorable/adverse metric deltas when comparing",
        "Title/hero/closing: one job + generous air; no KPI strips or card grids",
        f"Content density={density}: prefer ≤{card_cap} cards when using cards",
        "Text stays inside its card/column with ≥12px padding; wrap via tspan or shorten",
        "Never single-line spill across column dividers or past card borders",
        "Never place dark labels on dark motif ink; label outside shapes or on accent_tint plates",
        "Vary motif vs prior diary; do not clone the last page structure",
    ]
    lines.extend(pipeline_method_dna_bullets())
    return lines


def pipeline_method_dna_bullets() -> list[str]:
    """Short bullets from design_methods/_pipeline_method_dna.md."""
    try:
        from pathlib import Path

        path = Path(__file__).resolve().parent / "design_methods" / "_pipeline_method_dna.md"
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    bullets: list[str] = []
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith("- "):
            bullets.append(raw[2:].strip())
        if len(bullets) >= 16:
            break
    return bullets


def pipeline_method_dna_block() -> str:
    bullets = pipeline_method_dna_bullets()
    if not bullets:
        return ""
    return (
        "## Pipeline method DNA (Fill Contract + craft)\n"
        + "\n".join(f"- {x}" for x in bullets)
        + "\n\n"
    )


def craft_curriculum_block(tokens: dict[str, Any] | None) -> str:
    lines = craft_curriculum_from_tokens(tokens)
    if not lines:
        return ""
    return "## Craft curriculum (Defaults — concrete)\n" + "\n".join(f"- {x}" for x in lines) + "\n\n"


def project_confirm_ui_to_design_sot(result: dict[str, Any]) -> dict[str, Any]:
    """Project UI-guided confirm_ui/result into pack-shaped tokens + brief."""
    data = result if isinstance(result, dict) else {}
    color = data.get("color") if isinstance(data.get("color"), dict) else {}
    palette_in = color.get("palette") if isinstance(color.get("palette"), dict) else {}
    typo = data.get("typography") if isinstance(data.get("typography"), dict) else {}
    heading = typo.get("heading") if isinstance(typo.get("heading"), dict) else {}
    body = typo.get("body") if isinstance(typo.get("body"), dict) else {}
    icons = data.get("icons") if isinstance(data.get("icons"), dict) else {}

    primary = str(palette_in.get("primary") or "#1A365D")
    accent = str(palette_in.get("accent") or "#3182CE")
    background = str(palette_in.get("background") or "#FFFFFF")
    secondary_bg = str(palette_in.get("secondary_bg") or "#F5F7FA")
    body_text = str(palette_in.get("body_text") or "#1A202C")
    title_family = str(heading.get("primary") or "Georgia")
    body_family = str(body.get("primary") or "Arial")
    body_size = float(typo.get("body_size") or 18)
    visual_style = str(data.get("visual_style") or "blueprint")
    density = str(data.get("density") or "medium")
    mode = str(data.get("mode") or data.get("communication_mode") or "briefing")

    tokens: dict[str, Any] = {
        "source": "confirm_ui",
        "palette": {
            "background": background,
            "secondary_bg": secondary_bg,
            "primary": primary,
            "accent": accent,
            "secondary_accent": str(palette_in.get("secondary_accent") or accent),
            "body_text": body_text,
            "text_secondary": str(palette_in.get("text_secondary") or "#4A5568"),
            "text_tertiary": str(palette_in.get("text_tertiary") or "#A0AEC0"),
            "border": str(palette_in.get("border") or "#E2E8F0"),
            "accent_tint": str(
                palette_in.get("accent_tint")
                or palette_in.get("secondary_bg")
                or secondary_bg
            ),
        },
        "typography": {
            "heading": {"primary": title_family, "css": "serif"},
            "body": {"primary": body_family, "css": "sans-serif"},
            "body_size": body_size,
            "type_scale": dict(typo.get("type_scale") or {}),
        },
        "type_scale": dict(typo.get("type_scale") or {"body": body_size, "title": 36}),
        "icons": {
            "library": icons.get("library") or "tabler-outline",
            "stroke_width": icons.get("stroke_width") or 2,
            "inventory": list(icons.get("inventory") or []),
        },
        "method": {
            "method_id": "ui-guided",
            "preferred_mode": mode,
            "default_consumption_mode": "balanced",
            "summary": f"UI-guided design: mode={mode}, visual_style={visual_style}, density={density}.",
        },
        "layout": {
            "density": density,
            "visual_style": visual_style,
            "page_rhythm": {},
            "page_charts": {},
            "layout_patterns": [],
            "preferred_patterns": [],
        },
        "image_mood": {
            "image_rendering": str(data.get("image_rendering") or visual_style),
            "image_palette": str(data.get("image_palette") or ""),
        },
    }

    brief = (
        f"Design SoT: confirm_ui (no gallery pack).\n"
        f"AUTHORITATIVE user-guided system — obey literally.\n"
        f"- Palette: bg={background} primary={primary} accent={accent} body={body_text}\n"
        f"- Type: title={title_family}, body={body_family}, body_size≈{body_size:g}\n"
        f"- Visual style: {visual_style}; density: {density}; mode: {mode}\n"
        f"- Icons: {tokens['icons']['library']} stroke={tokens['icons']['stroke_width']}\n"
        "Compose original Constrained HTML pages (CSS canvas tokens; "
        "materialize → Slide IR → native PPTX). Write html_output/, ir/, preview/ — "
        "never svg_output/. Do not invent a second palette or type stack. "
        "Leave table/chart/formula/figure hosts empty when bound (Intent fills them).\n"
        "Vary composition across pages (page_role / visualization / rhythm). "
        "Do not force identical card stacks.\n"
    )
    return {
        "pack_id": "",
        "available": True,
        "source": "confirm_ui",
        "brief": brief,
        "tokens": tokens,
    }


def resolve_design_sot(
    *,
    pack_id: str | None = None,
    design_reference: dict[str, Any] | None = None,
    confirm_ui: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pack wins when available; else project confirm_ui into the same shape."""
    ref = design_reference if isinstance(design_reference, dict) else {}
    if ref.get("available") and isinstance(ref.get("tokens"), dict) and ref.get("tokens"):
        return {
            "pack_id": str(ref.get("pack_id") or pack_id or ""),
            "available": True,
            "source": "pack",
            "brief": str(ref.get("brief") or ""),
            "tokens": dict(ref.get("tokens") or {}),
        }
    if pack_id:
        try:
            from tasks.design_reference import extract_design_reference
        except ImportError:  # pragma: no cover
            from design_reference import extract_design_reference  # type: ignore
        extracted = extract_design_reference(str(pack_id))
        if extracted.get("available") and extracted.get("tokens"):
            return {
                "pack_id": str(pack_id),
                "available": True,
                "source": "pack",
                "brief": str(extracted.get("brief") or ""),
                "tokens": dict(extracted.get("tokens") or {}),
            }
    return project_confirm_ui_to_design_sot(confirm_ui or {})
