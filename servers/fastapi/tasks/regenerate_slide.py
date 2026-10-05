"""Deck-editor regenerate-slide request validation and artifacts."""

from __future__ import annotations

import json
import os
import time
from typing import Any


def validate_regenerate_slide_request(
    proj_dir: str,
    *,
    slide: int,
    feedback: str,
    generation_active: bool,
) -> dict[str, Any]:
    """Validate + persist regenerate request. Raises ValueError with code prefix.

    Prefixes: ``bad_request:``, ``conflict:``.
    """
    text = " ".join(str(feedback or "").split()).strip()
    if not text:
        raise ValueError("bad_request:Feedback must not be empty")
    slide_n = int(slide)
    if slide_n < 1:
        raise ValueError("bad_request:slide must be >= 1")
    if generation_active:
        raise ValueError(
            "conflict:This project is already generating. "
            "Wait for it to finish or cancel it first."
        )

    design_path = os.path.join(proj_dir, "design_spec.md")
    lock_path = os.path.join(proj_dir, "spec_lock.md")
    if not os.path.isfile(design_path) or not os.path.isfile(lock_path):
        raise ValueError(
            "conflict:Regenerate requires free-design design_spec.md and spec_lock.md"
        )

    try:
        from tasks import strategist_agent as _strategist
    except ImportError:  # pragma: no cover
        import strategist_agent as _strategist  # type: ignore

    with open(design_path, encoding="utf-8") as handle:
        design_md = handle.read()
    try:
        parsed = _strategist.parse_section_ix_slides(design_md)
    except Exception as exc:
        raise ValueError(f"conflict:Could not parse design_spec §IX: {exc}") from exc
    known = {int(item["slide"]) for item in parsed if item.get("slide") is not None}
    if slide_n not in known:
        raise ValueError(f"bad_request:Slide {slide_n} is not in design_spec §IX")

    validation_dir = os.path.join(proj_dir, "validation")
    os.makedirs(validation_dir, exist_ok=True)
    payload = {
        "schema_version": "sunairum.regenerate-slide-request/v1",
        "slide": slide_n,
        "feedback": text,
        "ts": int(time.time()),
    }
    with open(
        os.path.join(validation_dir, "regenerate_slide_request.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return payload
