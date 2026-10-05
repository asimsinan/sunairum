"""Append-only candidate provenance for Scene-authored slides.

The selected HTML remains in ``html_output``.  These snapshots explain how it
was chosen and prevent a measured recovery from erasing the creative source.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", str(value or "candidate").casefold()).strip("-") or "candidate"


def record_scene_candidate(
    storage_dir: str | Path,
    *,
    slide_number: int,
    stage: str,
    html: str,
    valid: bool | None = None,
    selected: bool = False,
    findings: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stage_name = str(stage or "")
    meta = metadata or {}
    forbidden_selected_stages = {
        "emergency_slide_fallback",
        "whole_slide_fallback",
        "full_slide_raster_fallback",
    }
    if selected and (
        stage_name in forbidden_selected_stages
        or bool(meta.get("whole_slide_replaced"))
    ):
        raise ValueError(
            "A whole-slide replacement cannot become the selected Scene candidate"
        )
    root = Path(storage_dir) / "validation" / "candidates" / f"slide_{int(slide_number):02d}"
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        index = {"version": "sunairum.scene-candidates/v1", "slide": int(slide_number), "candidates": []}
    entries = index.get("candidates") if isinstance(index.get("candidates"), list) else []
    digest = hashlib.sha256((html or "").encode("utf-8")).hexdigest()
    ordinal = len(entries) + 1
    filename = f"{ordinal:02d}_{_slug(stage)}_{digest[:10]}.html"
    html_path = root / filename
    html_path.write_text(html if html.endswith("\n") else html + "\n", encoding="utf-8")
    if selected:
        for previous in entries:
            if isinstance(previous, dict):
                previous["selected"] = False
    entry = {
        "stage": stage_name,
        "sha256": digest,
        "html": filename,
        "valid": valid,
        "selected": bool(selected),
        "findings": [str(item) for item in (findings or [])],
        "metadata": meta,
    }
    entries.append(entry)
    index["candidates"] = entries
    index["selected_sha256"] = digest if selected else index.get("selected_sha256")
    temporary = index_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, index_path)
    return entry
