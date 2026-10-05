"""Hard-delete project DB rows and every matching storage tree."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable


def _safe_project_id(project_id: str) -> str:
    pid = str(project_id or "").strip()
    if not pid or pid in {".", ".."} or "/" in pid or "\\" in pid:
        raise ValueError(f"invalid project_id: {project_id!r}")
    return pid


def find_project_storage_dirs(storage_root: str, project_id: str) -> list[str]:
    """Return every `{storage}/{user_or_bucket}/{project_id}` directory that exists."""
    pid = _safe_project_id(project_id)
    root = Path(storage_root)
    if not root.is_dir():
        return []
    found: list[str] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir():
            continue
        # Skip hidden / system dirs
        if entry.name.startswith("."):
            continue
        candidate = entry / pid
        if candidate.is_dir():
            found.append(str(candidate.resolve()))
    return found


def revoke_project_celery_tasks(
    proj_dir: str,
    *,
    revoke: Callable[[str], None] | None = None,
) -> list[str]:
    """Best-effort revoke of task ids recorded in project status files."""
    revoked: list[str] = []
    for name in ("source_status.json", "status.json"):
        path = os.path.join(proj_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        task_id = str((payload or {}).get("task_id") or "").strip()
        if not task_id:
            continue
        if revoke is not None:
            try:
                revoke(task_id)
            except Exception:
                pass
        revoked.append(task_id)
    return revoked


def _rmtree(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    shutil.rmtree(path, ignore_errors=False)
    return not os.path.exists(path)


def _remove_empty_parent(path: str, *, storage_root: str) -> None:
    """Remove parent user bucket if it became empty (never remove storage root)."""
    parent = Path(path).resolve().parent
    root = Path(storage_root).resolve()
    try:
        parent.relative_to(root)
    except ValueError:
        return
    if parent == root:
        return
    try:
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


def purge_project_files(
    storage_root: str,
    project_id: str,
    *,
    preferred_user_id: str | None = None,
    revoke: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Delete all on-disk trees for project_id; revoke celery tasks first."""
    pid = _safe_project_id(project_id)
    dirs = find_project_storage_dirs(storage_root, pid)
    preferred = ""
    if preferred_user_id:
        preferred = str(
            Path(storage_root).joinpath(str(preferred_user_id), pid)
        )
        if os.path.isdir(preferred) and preferred not in dirs:
            dirs.insert(0, preferred)

    revoked: list[str] = []
    removed: list[str] = []
    errors: list[str] = []
    for proj_dir in dirs:
        revoked.extend(revoke_project_celery_tasks(proj_dir, revoke=revoke))
        try:
            if _rmtree(proj_dir):
                removed.append(proj_dir)
                _remove_empty_parent(proj_dir, storage_root=storage_root)
            elif os.path.exists(proj_dir):
                errors.append(f"still_exists:{proj_dir}")
        except OSError as exc:
            errors.append(f"{proj_dir}: {exc}")

    return {
        "project_id": pid,
        "removed_dirs": removed,
        "revoked_tasks": sorted(set(revoked)),
        "errors": errors,
        "ok": not errors and all(
            not os.path.isdir(d) for d in dirs
        ),
    }


def purge_user_storage(storage_root: str, user_id: str) -> dict[str, Any]:
    """Remove the entire user storage bucket (used by Clear All)."""
    uid = str(user_id or "").strip()
    if not uid or uid in {".", ".."} or "/" in uid or "\\" in uid:
        raise ValueError(f"invalid user_id: {user_id!r}")
    user_dir = Path(storage_root) / uid
    if not user_dir.is_dir():
        return {"user_id": uid, "removed": False, "path": str(user_dir)}
    shutil.rmtree(user_dir, ignore_errors=False)
    return {
        "user_id": uid,
        "removed": not user_dir.exists(),
        "path": str(user_dir),
    }
