"""PPTX compile agent — free_design Job B.

Compiles html_output/ → native PPTX via deckhtml (HTML source of truth).
"""

from __future__ import annotations

import os
from typing import Any

ROLE = "generator_agent"


def finalize_compile(
    storage_dir: str,
    *,
    project_id: str,
    run_id: str = "",
) -> dict[str, Any]:
    """Full Job B: compile PPTX from Constrained HTML, write terminal status."""
    import asyncio

    from tasks.generate_task import send_ws_message, write_status
    from tasks.html_to_pptx import finalize_compile_html

    html_dir = os.path.join(storage_dir, "html_output")
    if not os.path.isdir(html_dir):
        raise RuntimeError("html_output/ missing; cannot compile HTML deck")
    write_status(
        storage_dir,
        "compiling",
        85,
        message="Compiling PPTX from HTML",
        message_key="status_compiling",
        run_id=run_id or None,
    )
    result = finalize_compile_html(
        storage_dir,
        project_id=project_id,
        run_id=run_id or "",
        include_notes=True,
    )
    # UI + /api/projects treat terminal success as done / done_with_issues.
    release_status = ""
    if isinstance(result, dict):
        manifest = result.get("release_manifest")
        if isinstance(manifest, dict):
            release_status = str(manifest.get("status") or "")
    from tasks.release_export import ui_status_for_release

    terminal = ui_status_for_release(release_status) or "done"
    message_key = (
        "status_done_with_issues" if terminal == "done_with_issues" else "status_completed"
    )
    write_status(
        storage_dir,
        terminal,
        100,
        message="PPTX ready",
        message_key=message_key,
        run_id=run_id or None,
    )
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            send_ws_message(
                project_id,
                {"status_key": message_key, "progress": 100, "status": terminal},
            )
        )
        loop.close()
    except Exception:
        pass
    return result
