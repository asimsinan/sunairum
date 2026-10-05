"""HTML source-of-truth artifact dirs (html_output + preview)."""

from __future__ import annotations

import os
from pathlib import Path


def html_sot_enabled(storage_dir: str | None = None) -> bool:
    """Constrained HTML → deckhtml is the only product path."""
    del storage_dir
    return True


def ensure_html_dirs(storage_dir: str) -> dict[str, str]:
    """Create source, preview, and resolved-scene artifact directories."""
    root = Path(storage_dir)
    paths = {
        "html_output": str(root / "html_output"),
        "preview": str(root / "preview"),
        "scene": str(root / "scene"),
    }
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    return paths


def write_html_sot_marker(storage_dir: str, *, enabled: bool) -> None:
    """Persist per-deck HTML SoT marker for materialize / compile."""
    validation = Path(storage_dir) / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    import json

    payload = {
        "enabled": bool(enabled),
        "schema": "sunairum.html-sot/v1",
        "source_of_truth": "html_output",
    }
    text = json.dumps(payload, indent=2) + "\n"
    (validation / "html_sot.json").write_text(text, encoding="utf-8")


def slide_stem(number: int) -> str:
    return f"slide_{int(number):02d}"
