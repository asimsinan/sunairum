"""Persisted state and summaries for asynchronous source parsing."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


SOURCE_ACTIVE_STATUSES = {"source_uploading", "source_parsing", "source_grounding"}
SOURCE_TERMINAL_STATUSES = {"source_ready", "source_error"}
SOURCE_STATUS_FILENAME = "source_status.json"
GENERATION_ACTIVE_STATUSES = {"queued", "planning", "generating", "compiling", "qa", "qa_fixing", "rendering"}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def read_source_status(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir)
    for path in (project / SOURCE_STATUS_FILENAME, project / "status.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def write_source_status(
    project_dir: str | Path,
    status: str,
    progress: int,
    message: str,
    *,
    message_key: str | None = None,
    task_id: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Record parse progress.

    `message` stays English because this layer has no notion of the reader's
    language; `message_key` names the phase so the UI can translate it. Two
    phases share the `source_parsing` status, so the status alone is not enough
    to identify the message.
    """
    project = Path(project_dir)
    existing = read_source_status(project)
    payload = {
        "status": status,
        "progress": max(0, min(100, int(progress))),
        "updated_at": int(time.time()),
        "message": message,
    }
    if message_key:
        payload["message_key"] = message_key
    if task_id or existing.get("task_id"):
        payload["task_id"] = task_id or existing["task_id"]
    if error:
        payload["error"] = error
    _atomic_json(project / SOURCE_STATUS_FILENAME, payload)

    # Keep the legacy status endpoint useful while parsing, but never replace
    # an active generation status after source readiness has been established.
    generation_status_path = project / "status.json"
    try:
        generation_status = json.loads(generation_status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        generation_status = {}
    if not isinstance(generation_status, dict) or generation_status.get("status") not in GENERATION_ACTIVE_STATUSES:
        _atomic_json(generation_status_path, payload)
    return payload


def source_status_summary(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir)
    status = read_source_status(project)
    parser = {}
    evidence = {}
    parser_path = project / "sources" / "parser_manifest.json"
    evidence_path = project / "sources" / "evidence_manifest.json"
    try:
        parser = json.loads(parser_path.read_text(encoding="utf-8")) if parser_path.is_file() else {}
    except json.JSONDecodeError:
        parser = {}
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.is_file() else {}
    except json.JSONDecodeError:
        evidence = {}
    stored_status = str(status.get("status") or "")
    resolved_status = (
        stored_status
        if stored_status in SOURCE_ACTIVE_STATUSES | SOURCE_TERMINAL_STATUSES
        else ("source_ready" if evidence else "source_uploading")
    )
    progress = int(status.get("progress") or 0)
    message = str(status.get("message") or "")
    message_key = str(status.get("message_key") or "")
    if resolved_status == "source_ready" and stored_status != "source_ready":
        progress = 100
        message = "PDF source is ready for the Communication Contract"
        message_key = "source_status_ready"
    return {
        "status": resolved_status,
        "progress": progress,
        "message": message,
        "message_key": message_key,
        "error": status.get("error") if resolved_status == "source_error" else None,
        "updated_at": status.get("updated_at"),
        "task_id": status.get("task_id"),
        "ready": resolved_status == "source_ready" and bool(evidence),
        "parser_selected": parser.get("parser_selected"),
        "parser_version": parser.get("parser_version"),
        "fallback_used": bool(parser.get("fallback_used")),
        "fallback_reason": parser.get("fallback_reason"),
        "pages": int(parser.get("page_count") or 0),
        "tables": int(evidence.get("table_count") or parser.get("tables", {}).get("structured") or 0),
        "figures": int(evidence.get("asset_count") or parser.get("figures", {}).get("detected") or 0),
        "formulas": int(evidence.get("formula_count") or 0),
    }
