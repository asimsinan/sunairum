from __future__ import annotations

from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
from auth.sessions import COOKIE_NAME, SessionStoreUnavailable, session_store
from database import get_db


@dataclass
class AuthContext:
    user: models.User
    session_id: str
    session: dict


def _load_session(request: Request, sid: str | None) -> tuple[str, dict]:
    if not sid:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Login required"})
    try:
        record = session_store.get(sid)
    except SessionStoreUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "session_store_unavailable", "message": "Session store unavailable"},
        ) from exc
    if not record:
        raise HTTPException(
            status_code=401,
            detail={"code": "session_expired", "message": "Session expired"},
        )
    now_idle = int(record.get("idle_expires_at", 0))
    now_abs = int(record.get("absolute_expires_at", 0))
    import time

    now = int(time.time())
    if now >= now_abs or now >= now_idle:
        session_store.destroy(sid, record.get("user_id"))
        raise HTTPException(
            status_code=401,
            detail={"code": "session_expired", "message": "Session expired"},
        )
    try:
        touched = session_store.touch(sid, record)
    except SessionStoreUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "session_store_unavailable", "message": "Session store unavailable"},
        ) from exc
    if not touched:
        raise HTTPException(
            status_code=401,
            detail={"code": "session_expired", "message": "Session expired"},
        )
    request.state.session_id = sid
    request.state.session_record = touched
    return sid, touched


def require_authenticated(
    request: Request,
    db: Session = Depends(get_db),
    sunairum_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> AuthContext:
    sid, record = _load_session(request, sunairum_session)
    user = db.query(models.User).filter(models.User.id == record["user_id"]).first()
    if not user or user.status == "disabled":
        session_store.destroy(sid, record.get("user_id"))
        raise HTTPException(
            status_code=401,
            detail={"code": "session_expired", "message": "Session expired"},
        )
    # Keep session role/status aligned with DB.
    if user.role != record.get("role") or user.status != record.get("status"):
        record["role"] = user.role
        record["status"] = user.status
        try:
            session_store.touch(sid, record)
        except SessionStoreUnavailable:
            pass
    return AuthContext(user=user, session_id=sid, session=record)


def require_approved(auth: AuthContext = Depends(require_authenticated)) -> AuthContext:
    if auth.user.role == "admin" or auth.user.status == "approved":
        return auth
    raise HTTPException(
        status_code=403,
        detail={"code": "not_approved", "message": "Account is not approved", "status": auth.user.status},
    )


def require_admin(auth: AuthContext = Depends(require_authenticated)) -> AuthContext:
    if auth.user.role != "admin" or auth.user.status != "approved":
        raise HTTPException(
            status_code=403,
            detail={"code": "admin_required", "message": "Admin access required"},
        )
    return auth


def get_owned_project(
    project_id: str,
    auth: AuthContext,
    db: Session,
    *,
    allow_admin: bool = False,
) -> models.Project:
    proj = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    if proj.user_id != auth.user.id and not (allow_admin and auth.user.role == "admin"):
        raise HTTPException(status_code=404, detail="Project not found")
    return proj
