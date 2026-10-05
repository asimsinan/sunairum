from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth.bootstrap import write_audit
from auth.deps import AuthContext, require_admin
from auth.passwords import hash_password, normalize_email, validate_password
from auth.sessions import session_store
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserBody(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str = ""
    role: str = "user"
    status: str = "approved"


class ResetPasswordBody(BaseModel):
    password: str = Field(min_length=8)


class RoleBody(BaseModel):
    role: str


class DeleteAllBody(BaseModel):
    confirm: str = Field(description='Must be exactly "DELETE_ALL"')


def _public_user(u: models.User, *, sessions: int | None = None) -> dict:
    row = {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name or "",
        "role": u.role,
        "status": u.status,
        "created_at": u.created_at,
        "approved_at": u.approved_at,
        "approved_by": u.approved_by,
        "last_login_at": u.last_login_at,
        # Never expose API keys. Optional support flags from settings.
        "api_key_set": False,
        "vision_api_key_set": False,
    }
    if sessions is not None:
        row["active_sessions"] = sessions
    return row


def _admin_count(db: Session) -> int:
    return (
        db.query(models.User)
        .filter(models.User.role == "admin", models.User.status == "approved")
        .count()
    )


def _storage_root() -> Path:
    return Path(os.environ.get("STORAGE_ROOT", "/app/storage"))


def _purge_user_data(db: Session, user: models.User) -> None:
    """Revoke sessions and remove DB + filesystem artifacts for a user."""
    session_store.revoke_all(user.id)
    db.query(models.UserSettings).filter(models.UserSettings.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(models.Project).filter(models.Project.user_id == user.id).delete(
        synchronize_session=False
    )
    user_dir = _storage_root() / user.id
    if user_dir.is_dir():
        try:
            shutil.rmtree(user_dir)
        except OSError:
            logger.exception("Failed to remove storage for user %s", user.id)
    db.delete(user)


def _attach_key_flags(db: Session, rows: list[dict]) -> list[dict]:
    ids = [r["id"] for r in rows]
    if not ids:
        return rows
    settings = (
        db.query(models.UserSettings)
        .filter(models.UserSettings.user_id.in_(ids))
        .all()
    )
    by_id = {s.user_id: s for s in settings}
    for row in rows:
        s = by_id.get(row["id"])
        if s:
            row["api_key_set"] = bool(s.api_key)
            row["vision_api_key_set"] = bool(s.vision_api_key)
    return rows


@router.get("/stats")
def admin_stats(auth: AuthContext = Depends(require_admin), db: Session = Depends(get_db)):
    pending = db.query(models.User).filter(models.User.status == "pending").count()
    approved = db.query(models.User).filter(models.User.status == "approved").count()
    rejected = db.query(models.User).filter(models.User.status == "rejected").count()
    disabled = db.query(models.User).filter(models.User.status == "disabled").count()
    total = db.query(models.User).count()
    return {
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "disabled": disabled,
        "total": total,
    }


@router.get("/users")
def list_users(
    status: str | None = None,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(models.User).order_by(models.User.created_at.desc())
    if status:
        q = q.filter(models.User.status == status)
    users = q.limit(500).all()
    rows = [_public_user(u, sessions=session_store.active_count(u.id)) for u in users]
    return {"users": _attach_key_flags(db, rows)}


@router.get("/users/{user_id}")
def get_user(
    user_id: str,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    events = (
        db.query(models.AuditEvent)
        .filter(models.AuditEvent.target_user_id == user_id)
        .order_by(models.AuditEvent.created_at.desc())
        .limit(50)
        .all()
    )
    import json

    audit = [
        {
            "id": e.id,
            "actor_user_id": e.actor_user_id,
            "action": e.action,
            "created_at": e.created_at,
            "meta": json.loads(e.meta_json or "{}"),
        }
        for e in events
    ]
    row = _public_user(user, sessions=session_store.active_count(user.id))
    _attach_key_flags(db, [row])
    return {"user": row, "audit": audit}


@router.post("/users")
def create_user(
    body: CreateUserBody,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    email = normalize_email(body.email)
    if len(email) < 3:
        raise HTTPException(status_code=400, detail="Invalid email")
    err = validate_password(body.password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if body.role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    if body.status not in {"pending", "approved", "rejected", "disabled"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already in use")
    now = int(time.time())
    user = models.User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(body.password),
        display_name=(body.display_name or email.split("@")[0])[:80],
        role=body.role,
        status=body.status,
        created_at=now,
        approved_at=now if body.status == "approved" else None,
        approved_by=auth.user.id if body.status == "approved" else None,
    )
    db.add(user)
    write_audit(
        db,
        actor_user_id=auth.user.id,
        action="admin.user_create",
        target_user_id=user.id,
        meta={"role": user.role, "status": user.status},
    )
    db.commit()
    db.refresh(user)
    return {"user": _public_user(user)}


@router.post("/users/{user_id}/approve")
def approve_user(
    user_id: str,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "approved"
    user.approved_at = int(time.time())
    user.approved_by = auth.user.id
    write_audit(db, actor_user_id=auth.user.id, action="admin.approve", target_user_id=user.id)
    db.commit()
    return {"user": _public_user(user)}


@router.post("/users/{user_id}/reject")
def reject_user(
    user_id: str,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin" and _admin_count(db) <= 1 and user.status == "approved":
        raise HTTPException(status_code=400, detail="Cannot reject the last admin")
    user.status = "rejected"
    write_audit(db, actor_user_id=auth.user.id, action="admin.reject", target_user_id=user.id)
    db.commit()
    session_store.revoke_all(user.id)
    return {"user": _public_user(user)}


@router.post("/users/{user_id}/disable")
def disable_user(
    user_id: str,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin" and user.status == "approved" and _admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot disable the last admin")
    user.status = "disabled"
    write_audit(db, actor_user_id=auth.user.id, action="admin.disable", target_user_id=user.id)
    db.commit()
    session_store.revoke_all(user.id)
    return {"user": _public_user(user)}


@router.post("/users/{user_id}/enable")
def enable_user(
    user_id: str,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "approved"
    user.approved_at = user.approved_at or int(time.time())
    user.approved_by = user.approved_by or auth.user.id
    write_audit(db, actor_user_id=auth.user.id, action="admin.enable", target_user_id=user.id)
    db.commit()
    return {"user": _public_user(user)}


@router.patch("/users/{user_id}/role")
def set_role(
    user_id: str,
    body: RoleBody,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if (
        user.role == "admin"
        and body.role != "admin"
        and user.status == "approved"
        and _admin_count(db) <= 1
    ):
        raise HTTPException(status_code=400, detail="Cannot demote the last admin")
    old = user.role
    user.role = body.role
    write_audit(
        db,
        actor_user_id=auth.user.id,
        action="admin.role_change",
        target_user_id=user.id,
        meta={"from": old, "to": body.role},
    )
    db.commit()
    if body.role != "admin":
        # Force session refresh of role on next request via DB.
        pass
    return {"user": _public_user(user)}


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: str,
    body: ResetPasswordBody,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    err = validate_password(body.password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(body.password)
    write_audit(
        db,
        actor_user_id=auth.user.id,
        action="admin.reset_password",
        target_user_id=user.id,
    )
    db.commit()
    session_store.revoke_all(user.id)
    return {"ok": True}


@router.delete("/users")
def delete_all_users(
    body: DeleteAllBody,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete every user except the acting admin. Requires confirm=DELETE_ALL."""
    if body.confirm != "DELETE_ALL":
        raise HTTPException(status_code=400, detail='confirm must be "DELETE_ALL"')
    targets = (
        db.query(models.User)
        .filter(models.User.id != auth.user.id)
        .all()
    )
    deleted = 0
    for user in targets:
        write_audit(
            db,
            actor_user_id=auth.user.id,
            action="admin.delete",
            target_user_id=user.id,
            meta={"email": user.email, "bulk": True},
        )
        _purge_user_data(db, user)
        deleted += 1
    write_audit(
        db,
        actor_user_id=auth.user.id,
        action="admin.delete_all",
        target_user_id=auth.user.id,
        meta={"deleted": deleted},
    )
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == auth.user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    if user.role == "admin" and user.status == "approved" and _admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last admin")
    email = user.email
    write_audit(
        db,
        actor_user_id=auth.user.id,
        action="admin.delete",
        target_user_id=user.id,
        meta={"email": email},
    )
    _purge_user_data(db, user)
    db.commit()
    return {"ok": True}
