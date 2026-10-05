"""Library / Recents enrichment for GET /api/projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_display_title(
    *,
    topic: str | None,
    proj_dir: str | Path,
) -> str:
    """paper_title → first grounded slide title → topic → Untitled."""
    root = Path(proj_dir)
    run_manifest = _read_json(root / "validation" / "run_manifest.json")
    identity = run_manifest.get("source_identity")
    if isinstance(identity, dict):
        paper = str(identity.get("paper_title") or "").strip()
        if paper:
            return paper
    grounded = _read_json(root / "validation" / "grounded_plan.json")
    slides = grounded.get("slides")
    if isinstance(slides, list):
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            title = str(slide.get("title") or "").strip()
            if title:
                return title
    topic_text = str(topic or "").strip()
    if topic_text:
        return topic_text
    return "Untitled"


def resolve_cover_url(
    *,
    user_id: str,
    project_id: str,
    proj_dir: str | Path,
) -> str | None:
    from tasks.slide_artifacts import cover_public_url

    return cover_public_url(
        user_id=user_id, project_id=project_id, proj_dir=proj_dir
    )


def resolve_slide_count(
    *,
    proj_dir: str | Path,
    status_total: Any = None,
) -> int:
    from tasks.slide_artifacts import slide_count as _slide_count

    root = Path(proj_dir)
    count = _slide_count(root)
    if count:
        return count
    run_manifest = _read_json(root / "validation" / "run_manifest.json")
    for key in ("num_slides", "total_page_count", "page_count"):
        raw = run_manifest.get(key)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    try:
        total = int(status_total)
        if total > 0:
            return total
    except (TypeError, ValueError):
        pass
    return 0


def resolve_has_pdf(*, has_pdf_flag: Any, proj_dir: str | Path) -> bool:
    if int(has_pdf_flag or 0) == 1:
        return True
    root = Path(proj_dir)
    return (root / "source.pdf").is_file() or (root / "sources" / "source.pdf").is_file()


def sort_library_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """last_opened_at DESC NULLS LAST, then created_at DESC."""

    def key(item: dict[str, Any]) -> tuple[int, int, int]:
        opened = item.get("last_opened_at")
        try:
            opened_i = int(opened) if opened is not None else 0
        except (TypeError, ValueError):
            opened_i = 0
        has_opened = 1 if opened_i > 0 else 0
        try:
            created = int(item.get("created_at") or 0)
        except (TypeError, ValueError):
            created = 0
        # Sort descending: negate values; NULLS LAST via has_opened.
        return (has_opened, opened_i, created)

    return sorted(projects, key=key, reverse=True)


def enrich_project_library_fields(
    *,
    user_id: str,
    project_id: str,
    topic: str | None,
    has_pdf_flag: Any,
    last_opened_at: Any,
    proj_dir: str | Path,
    status_total: Any = None,
) -> dict[str, Any]:
    """Return display fields for the library / Recents UI."""
    opened: int | None
    try:
        opened = int(last_opened_at) if last_opened_at is not None else None
        if opened is not None and opened <= 0:
            opened = None
    except (TypeError, ValueError):
        opened = None
    return {
        "display_title": resolve_display_title(topic=topic, proj_dir=proj_dir),
        "cover_url": resolve_cover_url(
            user_id=user_id, project_id=project_id, proj_dir=proj_dir
        ),
        "slide_count": resolve_slide_count(proj_dir=proj_dir, status_total=status_total),
        "has_pdf": resolve_has_pdf(has_pdf_flag=has_pdf_flag, proj_dir=proj_dir),
        "last_opened_at": opened,
    }
