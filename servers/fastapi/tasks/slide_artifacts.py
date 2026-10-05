"""Shared Scene-v2 HTML slide artifact discovery.

Preference for resume / notes / editor (first non-empty folder wins):
  1. html_output/slide_*.html
  2. preview/slide_*.png

Library cover thumbnails prefer preview first, then HTML.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

# Resume / notes / editor: authored HTML first.
SLIDE_ARTIFACT_SOURCES: tuple[tuple[str, str], ...] = (
    ("html_output", "slide_*.html"),
    ("preview", "slide_*.png"),
)

# Library cover / count: raster preview first for FE thumbnails.
COVER_ARTIFACT_SOURCES: tuple[tuple[str, str], ...] = (
    ("preview", "slide_*.png"),
    ("html_output", "slide_*.html"),
)

COVER_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("preview", "slide_01.png"),
    ("html_output", "slide_01.html"),
)

_MIN_EXISTING_BYTES = 64
_STEM_RE = re.compile(r"^slide_(\d+)$")


def list_slide_artifacts(
    project_dir: str | Path,
    *,
    sources: tuple[tuple[str, str], ...] | None = None,
    min_bytes: int = 0,
) -> list[Path]:
    """Return sorted slide files from the first non-empty preferred folder."""
    root = Path(project_dir)
    chain = sources or SLIDE_ARTIFACT_SOURCES
    for folder, pattern in chain:
        directory = root / folder
        if not directory.is_dir():
            continue
        files: list[Path] = []
        for path in directory.glob(pattern):
            if not path.is_file():
                continue
            try:
                if path.stat().st_size <= min_bytes:
                    continue
            except OSError:
                continue
            files.append(path)
        if files:
            return sorted(files, key=lambda p: p.name)
    return []


def existing_slide_numbers(project_dir: str | Path) -> set[int]:
    """Slide indices with a non-empty preferred artifact on disk."""
    found: set[int] = set()
    for path in list_slide_artifacts(project_dir, min_bytes=_MIN_EXISTING_BYTES):
        match = _STEM_RE.match(path.stem)
        if match:
            found.add(int(match.group(1)))
    return found


def cover_artifact_path(project_dir: str | Path) -> Path | None:
    """First-slide cover file: preview PNG, then HTML."""
    root = Path(project_dir)
    for folder, name in COVER_CANDIDATES:
        path = root / folder / name
        if path.is_file():
            return path
    return None


def cover_public_url(
    *,
    user_id: str,
    project_id: str,
    proj_dir: str | Path,
) -> str | None:
    path = cover_artifact_path(proj_dir)
    if path is None:
        return None
    rel = f"{path.parent.name}/{path.name}"
    return f"/api/files/{user_id}/{project_id}/{rel}"


def slide_count(project_dir: str | Path) -> int:
    """Count slides preferring preview, then HTML."""
    return len(
        list_slide_artifacts(project_dir, sources=COVER_ARTIFACT_SOURCES, min_bytes=0)
    )


def regenerate_slide_urls(
    *,
    storage_dir: str | Path,
    rel_prefix: str,
    slide_number: int,
) -> dict[str, Any]:
    """Public file URLs after deck-editor regenerate (preview + HTML)."""
    root = Path(storage_dir)
    stem = f"slide_{int(slide_number):02d}"
    preview = root / "preview" / f"{stem}.png"
    html_path = root / "html_output" / f"{stem}.html"
    scene_path = root / "scene" / f"{stem}.json"

    version = int(time.time())
    for candidate in (preview, html_path, scene_path):
        try:
            if candidate.is_file():
                version = int(os.path.getmtime(candidate))
                break
        except OSError:
            continue

    def _url(path: Path) -> str | None:
        if not path.is_file():
            return None
        return f"/api/files/{rel_prefix}/{path.parent.name}/{path.name}?v={version}"

    preview_url = _url(preview)
    html_url = _url(html_path)
    return {
        "preview_url": preview_url,
        "html_url": html_url,
        "scene_url": _url(scene_path),
        "version": version,
    }
