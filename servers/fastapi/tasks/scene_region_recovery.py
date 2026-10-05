"""Compatibility boundary for retired Scene-region replacement.

Authored visual DOM is immutable after authoring. Layout QA may adjust scoped
CSS or request object-level export fallback, but it must never substitute a
generic donor region and change the design.
"""

from __future__ import annotations

from typing import Any


def failing_region_ids(layout_ledger: dict[str, Any]) -> list[str]:
    return sorted(
        str(region_id)
        for region_id, entry in (layout_ledger.get("regions") or {}).items()
        if isinstance(entry, dict) and entry.get("issues")
    )


def recover_scene_regions(
    creative_html: str,
    fallback_html: str,
    region_ids: list[str] | tuple[str, ...],
) -> tuple[str, dict[str, Any]]:
    """Retained API that explicitly refuses donor-region substitution."""
    wanted = [str(value).strip() for value in region_ids if str(value).strip()]
    return creative_html, {
        "changed": False,
        "regions": [],
        "requested_regions": wanted,
        "blocked": "authored_dom_immutable",
    }
