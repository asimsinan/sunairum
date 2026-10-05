from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

import models
from database import SessionLocal

logger = logging.getLogger("sunairum.auth")


def migrate_default_user_to_admin(
    storage_root: str | Path,
    db: Session | None = None,
) -> dict:
    """Reassign default_user rows/files to the seeded admin. Idempotent."""
    owns = db is None
    db = db or SessionLocal()
    storage_root = Path(storage_root)
    result = {"moved_projects": 0, "moved_settings": 0, "renamed_storage": False, "admin_id": None}
    try:
        admin = (
            db.query(models.User)
            .filter(models.User.role == "admin", models.User.status == "approved")
            .order_by(models.User.created_at.asc())
            .first()
        )
        if not admin:
            logger.warning("migrate_default_user: no admin user; skip")
            return result
        result["admin_id"] = admin.id

        projects = db.query(models.Project).filter(models.Project.user_id == "default_user").all()
        for proj in projects:
            proj.user_id = admin.id
            result["moved_projects"] += 1

        settings = (
            db.query(models.UserSettings)
            .filter(models.UserSettings.user_id == "default_user")
            .all()
        )
        for row in settings:
            existing = (
                db.query(models.UserSettings)
                .filter(models.UserSettings.user_id == admin.id)
                .first()
            )
            if existing:
                # Prefer admin row; drop legacy.
                db.delete(row)
            else:
                row.user_id = admin.id
                result["moved_settings"] += 1

        db.commit()

        src = storage_root / "default_user"
        dest = storage_root / admin.id
        if src.is_dir():
            if dest.exists():
                # Merge project folders.
                for child in src.iterdir():
                    target = dest / child.name
                    if target.exists():
                        continue
                    shutil.move(str(child), str(target))
                shutil.rmtree(src, ignore_errors=True)
            else:
                shutil.move(str(src), str(dest))
            result["renamed_storage"] = True
            logger.info("Migrated storage/default_user → storage/%s", admin.id)
        return result
    finally:
        if owns:
            db.close()
