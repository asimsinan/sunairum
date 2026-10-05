"""Compact deck-level prompt context — avoid resending §I–VIII / full SoT every call."""

from __future__ import annotations

import re
from typing import Any


_SECTION_IX_HDR_RE = re.compile(
    r"^##\s*IX\.?\s*Content Outline\s*$", re.I | re.M
)
_SECTION_X_HDR_RE = re.compile(
    r"^##\s*X\.?\s*Speaker Notes\b[^\n]*$", re.I | re.M
)


def lock_compact(spec_lock_md: str, *, max_chars: int = 2800) -> str:
    """Palette + font families (+ short bans) from spec_lock.md."""
    raw = str(spec_lock_md or "").strip()
    if not raw:
        return ""
    keep: list[str] = []
    for line in raw.splitlines():
        low = line.casefold()
        if any(
            k in low
            for k in (
                "primary",
                "accent",
                "ink",
                "muted",
                "surface",
                "background",
                "font",
                "georgia",
                "arial",
                "heading",
                "body",
                "presentation_method",
                "selected_style",
                "authority",
                "composition",
                "density",
                "decoration",
                "color behavior",
                "typography character",
                "forbid",
                "ban",
                "never",
                "#",
            )
        ):
            keep.append(line.rstrip())
    out = "\n".join(keep).strip() or raw[:max_chars]
    return out[:max_chars].rstrip()


_PALETTE_LOCK_KEYS = (
    "background",
    "secondary_bg",
    "primary",
    "accent",
    "secondary_accent",
    "body_text",
    "text_secondary",
    "text_tertiary",
    "border",
    "accent_tint",
    "success",
    "warning",
    "ink",
    "muted",
    "surface",
    "panel",
)


def palette_lock_block(color_palette: dict[str, Any] | None) -> str:
    """Front-loaded locked swatches from the live deck palette (hosts already use this)."""
    if not isinstance(color_palette, dict) or not color_palette:
        return ""
    # Nested design_tokens.palette wins when present (pack SoT).
    tokens = color_palette.get("design_tokens")
    nested = (
        tokens.get("palette")
        if isinstance(tokens, dict) and isinstance(tokens.get("palette"), dict)
        else None
    )
    source = nested if nested else color_palette
    swatches: list[str] = []
    seen: set[str] = set()
    for key in _PALETTE_LOCK_KEYS:
        value = source.get(key) if isinstance(source, dict) else None
        if value is None and source is not color_palette:
            value = color_palette.get(key)
        text = str(value or "").strip()
        if not text or not text.startswith("#"):
            continue
        if key in seen:
            continue
        seen.add(key)
        swatches.append(f"{key}={text}")
    if not swatches:
        return ""
    heading = color_palette.get("_heading_family") or color_palette.get("heading_font")
    body = color_palette.get("_body_family") or color_palette.get("body_font")
    lines = [
        "## Deck palette (locked)",
        "Use ONLY these hexes for fills, text, borders, and accents. "
        "Do not invent a second palette (no dark theme when the lock is light).",
        "Locked palette: " + ", ".join(swatches) + ".",
    ]
    font_bits = []
    if heading:
        font_bits.append(f"heading={heading}")
    if body:
        font_bits.append(f"body={body}")
    if font_bits:
        lines.append("Fonts: " + ", ".join(font_bits) + ".")
    return "\n".join(lines)


def sot_compact(design_reference_brief: str, *, max_chars: int = 3600) -> str:
    """Design SoT without viz catalog_menu dump."""
    raw = str(design_reference_brief or "").strip()
    if not raw:
        return ""
    # Drop catalog menus / long pattern lists that dominate TTFT.
    raw = re.sub(
        r"(?is)##\s*Visualization catalog.*?(?=^##\s|\Z)",
        "",
        raw,
    )
    raw = re.sub(
        r"(?is)catalog_menu\s*[:=].*?(?=^##\s|\Z)",
        "",
        raw,
    )
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    return raw[:max_chars].rstrip()


def craft_compact(craft_block: str | list[str], *, max_lines: int = 10) -> str:
    """Compact craft rules — never drop spill/inset/Fill Contract lines early."""
    if isinstance(craft_block, list):
        lines = [str(x).strip() for x in craft_block if str(x).strip()]
    else:
        lines = [
            ln.strip().lstrip("-•").strip()
            for ln in str(craft_block or "").splitlines()
            if ln.strip()
        ]
    lines = [ln for ln in lines if ln]
    if not lines:
        return ""
    priority_re = re.compile(
        r"(?i)\b(spill|inset|fill\s*contract|gutter|overlap|host|claim)\b"
    )
    priority = [ln for ln in lines if priority_re.search(ln)]
    rest = [ln for ln in lines if ln not in priority]
    # Keep all priority lines, then fill remaining budget with others.
    kept = priority + rest
    # Cap only the non-priority tail so spill/inset survive.
    if len(kept) > max_lines:
        budget = max(0, max_lines - len(priority))
        kept = priority + rest[:budget]
    return "## Craft (compact)\n" + "\n".join(f"- {ln}" for ln in kept) + "\n"


def extract_ix_page(
    design_spec_md: str,
    slide_number: int,
    *,
    body_md_fallback: str = "",
) -> str:
    """This slide's §IX (+ optional §X note) only — no §I–VIII prefix."""
    raw = str(design_spec_md or "")
    if not raw.strip():
        return str(body_md_fallback or "").strip()

    ix_match = _SECTION_IX_HDR_RE.search(raw)
    x_match = _SECTION_X_HDR_RE.search(raw)
    if not ix_match:
        return str(body_md_fallback or "").strip() or raw.strip()

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
        return (
            f"## IX. Content Outline\n\n{fallback}\n"
            if fallback
            else ""
        )

    next_hdr = re.search(r"^###\s*P\d+\b", ix_body[hdr.end() :], re.I | re.M)
    chunk_end = hdr.end() + next_hdr.start() if next_hdr else len(ix_body)
    slide_chunk = ix_body[hdr.start() : chunk_end].strip()
    parts = ["## IX. Content Outline", "", slide_chunk]

    if x_match:
        x_body = raw[x_match.end() :]
        note = re.search(
            rf"^\s*[-*]\s*\*\*P0*{int(slide_number)}:?\*\*\s*(.+)$",
            x_body,
            re.I | re.M,
        )
        if note:
            parts.extend(
                [
                    "",
                    "## X. Speaker Notes (spoken context ONLY — do NOT paint)",
                    "",
                    f"- **P{page}:** {note.group(1).strip()}",
                ]
            )
    return "\n".join(parts).rstrip() + "\n"


def build_deck_prompt_context(
    *,
    spec_lock_md: str = "",
    design_reference_brief: str = "",
    craft_block: str | list[str] = "",
) -> dict[str, str]:
    return {
        "lock_compact": lock_compact(spec_lock_md),
        "sot_compact": sot_compact(design_reference_brief),
        "craft_compact": craft_compact(craft_block),
    }
