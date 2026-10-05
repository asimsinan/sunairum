"""Optional presentation-method style packs for scratch free_design."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

STYLES_DIR = Path(__file__).resolve().parent / "design_methods" / "styles"
INDEX_PATH = STYLES_DIR / "styles_index.json"


@lru_cache(maxsize=1)
def styles_index() -> dict[str, Any]:
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def list_styles() -> list[dict[str, Any]]:
    """UI catalog: id + summary (+ keywords)."""
    out: list[dict[str, Any]] = []
    for style_id, meta in sorted(styles_index().items()):
        if not isinstance(meta, dict):
            continue
        out.append(
            {
                "id": style_id,
                "summary": str(meta.get("summary") or ""),
                "keywords": list(meta.get("keywords") or []),
            }
        )
    return out


def load_style_method(style_id: str | None) -> str:
    """Condensed method.md for Spec merge. Unknown id → empty."""
    sid = str(style_id or "").strip()
    if not sid or sid not in styles_index():
        return ""
    path = STYLES_DIR / sid / "method.md"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text


def style_method_block(style_id: str | None) -> str:
    body = load_style_method(style_id)
    if not body:
        return ""
    return (
        f"## Presentation style (user-selected: {style_id})\n"
        "Merge with Pipeline method DNA and Fill Contract. Do not invent a second palette.\n\n"
        f"{body}\n\n"
    )


def normalize_style_id(style_id: str | None, *, allow: bool) -> str | None:
    """Return a valid style id only when scratch path allows it."""
    if not allow:
        return None
    sid = str(style_id or "").strip()
    if not sid or sid not in styles_index():
        return None
    return sid
