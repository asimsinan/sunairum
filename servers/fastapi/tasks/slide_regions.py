"""Intent host geometry helpers — preferred AABBs only (not page layout law)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CANVAS_W = 1280.0
CANVAS_H = 720.0
MARGIN = 60.0
TITLE_MARGIN = 84.0
TITLE_BAND = (TITLE_MARGIN, 48.0, CANVAS_W - TITLE_MARGIN - 60.0, 92.0)
CONTENT_TOP = 160.0
CONTENT_BOTTOM = 620.0
CHROME_Y = 660.0

try:
    from tasks.intent_hosts import FIGURE_HOST, FORMULA_HOST, TABLE_HOST
except ImportError:  # pragma: no cover
    from intent_hosts import FIGURE_HOST, FORMULA_HOST, TABLE_HOST  # type: ignore


@dataclass(frozen=True)
class Region:
    """Axis-aligned preferred host box (Executor may place hosts elsewhere)."""

    id: str
    role: str
    x: float
    y: float
    width: float
    height: float
    z: int = 0
    padding: float = 16.0

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.width, self.height)

    @property
    def inner_box(self) -> tuple[float, float, float, float]:
        pad = min(self.padding, self.width / 4, self.height / 4)
        return (
            self.x + pad,
            self.y + pad,
            max(1.0, self.width - 2 * pad),
            max(1.0, self.height - 2 * pad),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SlideLayout:
    recipe: str = "host_preferred"
    regions: list[Region] = field(default_factory=list)
    canvas: tuple[float, float] = (CANVAS_W, CANVAS_H)

    def region(self, role: str) -> Region | None:
        for item in self.regions:
            if item.role == role or item.id == role:
                return item
        return None

    def regions_with_role(self, role: str) -> list[Region]:
        return [
            item
            for item in self.regions
            if item.role == role or item.role.startswith(f"{role}.")
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "recipe": self.recipe,
            "canvas": {"width": self.canvas[0], "height": self.canvas[1]},
            "regions": [region.as_dict() for region in self.regions],
        }


def aabb_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    *,
    eps: float = 0.5,
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw <= bx + eps
        or bx + bw <= ax + eps
        or ay + ah <= by + eps
        or by + bh <= ay + eps
    )


def preferred_host_layout(slide: dict[str, Any] | None = None) -> SlideLayout:
    """Preferred empty-host bands for bound assets — not exclusive page regions."""
    slide = slide or {}
    regions: list[Region] = [
        Region("title", "title", *TITLE_BAND, z=10),
        Region(
            "page",
            "page",
            CANVAS_W - MARGIN - 80.0,
            CHROME_Y,
            80.0,
            24.0,
            z=1,
        ),
    ]
    tid = str(slide.get("table_id") or "").strip()
    if tid and tid.casefold() not in {"none", "null", "n/a", "-"}:
        x, y, w, h = TABLE_HOST
        regions.append(Region("table", "table", x, y, w, h, z=20))
    fid = str(slide.get("figure_id") or "").strip()
    if fid and fid.casefold() not in {"none", "null", "n/a", "-"}:
        x, y, w, h = FIGURE_HOST
        regions.append(Region("figure", "figure", x, y, w, h, z=20))
    formula = str(slide.get("formula") or slide.get("formula_tex") or "").strip()
    if formula:
        x, y, w, h = FORMULA_HOST
        regions.append(Region("formula", "formula", x, y, w, h, z=20))
    return SlideLayout(recipe="host_preferred", regions=regions)


def layout_for_slide(slide: dict[str, Any]) -> SlideLayout:
    """Host-preferred layout for Intent inject / shell fallback."""
    return preferred_host_layout(slide)


def persist_slide_regions(validation_dir: str, layouts: list[SlideLayout]) -> None:
    path = Path(validation_dir) / "slide_regions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([layout.as_dict() for layout in layouts], indent=2),
        encoding="utf-8",
    )
