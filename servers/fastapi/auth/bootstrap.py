from __future__ import annotations

import logging
import os
import time
import uuid

from sqlalchemy.orm import Session

import models
from auth.passwords import hash_password, normalize_email
from database import SessionLocal

logger = logging.getLogger("sunairum.auth")


# Shared password for seeded demo accounts (local/dev only).
DEMO_PASSWORD = "demo1234"

DEMO_USERS: list[dict] = [
    {
        "email": "maya@sunairum.demo",
        "display_name": "Maya Chen",
        "role": "user",
        "status": "approved",
    },
    {
        "email": "jordan@sunairum.demo",
        "display_name": "Jordan Lee",
        "role": "user",
        "status": "pending",
    },
    {
        "email": "sam@sunairum.demo",
        "display_name": "Sam Rivera",
        "role": "user",
        "status": "rejected",
    },
    {
        "email": "alex@sunairum.demo",
        "display_name": "Alex Kim",
        "role": "user",
        "status": "disabled",
    },
    {
        "email": "riley@sunairum.demo",
        "display_name": "Riley Park",
        "role": "user",
        "status": "pending",
    },
]


def seed_admin_if_needed(db: Session | None = None) -> models.User | None:
    """Create the default admin when no admin users exist."""
    owns = db is None
    db = db or SessionLocal()
    try:
        admin_count = (
            db.query(models.User)
            .filter(models.User.role == "admin")
            .count()
        )
        if admin_count > 0:
            return None
        email = normalize_email(os.environ.get("ADMIN_EMAIL") or "admin")
        password = os.environ.get("ADMIN_PASSWORD") or "admin"
        user = models.User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password(password),
            display_name="Admin",
            role="admin",
            status="approved",
            created_at=int(time.time()),
            approved_at=int(time.time()),
            approved_by="system",
            last_login_at=None,
            failed_login_count=0,
            locked_until=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        if email == "admin" and password == "admin":
            logger.warning(
                "Seeded default admin login 'admin' / 'admin'. Change the password on /profile immediately."
            )
        else:
            logger.info("Seeded admin user %s", email)
        return user
    finally:
        if owns:
            db.close()


def seed_demo_users_if_needed(db: Session | None = None) -> int:
    """Idempotently seed demo users when SEED_DEMO_USERS=1.

    Returns the number of users created.
    """
    flag = (os.environ.get("SEED_DEMO_USERS") or "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return 0

    owns = db is None
    db = db or SessionLocal()
    created = 0
    try:
        now = int(time.time())
        password_hash = hash_password(DEMO_PASSWORD)
        for spec in DEMO_USERS:
            email = normalize_email(spec["email"])
            if db.query(models.User).filter(models.User.email == email).first():
                continue
            status = spec["status"]
            user = models.User(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=password_hash,
                display_name=spec["display_name"],
                role=spec["role"],
                status=status,
                created_at=now,
                approved_at=now if status == "approved" else None,
                approved_by="system" if status == "approved" else None,
                last_login_at=None,
                failed_login_count=0,
                locked_until=None,
            )
            db.add(user)
            created += 1
        if created:
            db.commit()
            logger.info("Seeded %s demo user(s) (password: %s)", created, DEMO_PASSWORD)
        return created
    finally:
        if owns:
            db.close()


def write_audit(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    target_user_id: str | None = None,
    meta: dict | None = None,
) -> None:
    import json

    db.add(
        models.AuditEvent(
            id=str(uuid.uuid4()),
            actor_user_id=actor_user_id,
            action=action,
            target_user_id=target_user_id,
            meta_json=json.dumps(meta or {}, ensure_ascii=False),
            created_at=int(time.time()),
        )
    )
