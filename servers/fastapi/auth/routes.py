from __future__ import annotations

import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth.bootstrap import write_audit
from auth.deps import AuthContext, require_approved, require_authenticated
from auth.passwords import (
    hash_password,
    normalize_email,
    validate_password,
    verify_password,
)
from auth.sessions import (
    COOKIE_NAME,
    SessionStoreUnavailable,
    absolute_hours,
    cookie_secure,
    idle_minutes,
    login_lockout_minutes,
    login_max_failures,
    session_store,
)
from database import get_db


def _signup_enabled() -> bool:
    """Public self-serve signup is on by default; set SIGNUP_ENABLED=0 to close it."""
    flag = (os.environ.get("SIGNUP_ENABLED") or "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return flag in {"1", "true", "yes", "on"}

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupBody(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


class ProfilePatch(BaseModel):
    display_name: str | None = None
    email: str | None = None


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


def _set_session_cookie(response: Response, sid: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=sid,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
        max_age=absolute_hours() * 3600,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def _user_payload(user: models.User, session: dict | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name or "",
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }
    if session:
        payload["idle_expires_at"] = session.get("idle_expires_at")
        payload["absolute_expires_at"] = session.get("absolute_expires_at")
        payload["session_idle_minutes"] = idle_minutes()
        payload["session_absolute_hours"] = absolute_hours()
    return payload


@router.post("/signup")
def signup(body: SignupBody, request: Request, db: Session = Depends(get_db)):
    if not _signup_enabled():
        raise HTTPException(
            status_code=403,
            detail={"code": "signup_disabled", "message": "Public registration is closed"},
        )
    email = normalize_email(body.email)
    if len(email) < 3 or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    err = validate_password(body.password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    try:
        if session_store.rate_limit_hit(f"signup:{request.client.host if request.client else 'x'}", 10, 3600):
            raise HTTPException(status_code=429, detail="Too many signup attempts")
    except SessionStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="Session store unavailable") from exc

    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        # No enumeration — same response shape.
        return {"status": "pending", "message": "If this email is new, it awaits approval."}

    user = models.User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(body.password),
        display_name=(body.display_name or email.split("@")[0])[:80],
        role="user",
        status="pending",
        created_at=int(time.time()),
    )
    db.add(user)
    db.commit()
    return {"status": "pending", "message": "If this email is new, it awaits approval."}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    email = normalize_email(body.email)
    try:
        if session_store.rate_limit_hit(f"login_ip:{request.client.host if request.client else 'x'}", 60, 900):
            raise HTTPException(status_code=429, detail="Too many login attempts")
    except SessionStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="Session store unavailable") from exc

    user = db.query(models.User).filter(models.User.email == email).first()
    now = int(time.time())
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=403, detail="Account temporarily locked")

    ok = bool(user and verify_password(user.password_hash, body.password))
    if not ok:
        if user:
            user.failed_login_count = int(user.failed_login_count or 0) + 1
            if user.failed_login_count >= login_max_failures():
                user.locked_until = now + login_lockout_minutes() * 60
                user.failed_login_count = 0
            db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.status == "disabled":
        raise HTTPException(status_code=403, detail={"code": "disabled", "status": "disabled"})

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()

    try:
        sid, record = session_store.create(
            user_id=user.id,
            role=user.role,
            status=user.status,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except SessionStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="Session store unavailable") from exc

    _set_session_cookie(response, sid)
    return {"user": _user_payload(user, record)}


@router.post("/logout")
def logout(
    response: Response,
    auth: AuthContext = Depends(require_authenticated),
):
    session_store.destroy(auth.session_id, auth.user.id)
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(auth: AuthContext = Depends(require_authenticated)):
    return {"user": _user_payload(auth.user, auth.session)}


@router.patch("/me")
def patch_me(
    body: ProfilePatch,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == auth.user.id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    if body.display_name is not None:
        user.display_name = body.display_name.strip()[:80]
    if body.email is not None:
        new_email = normalize_email(body.email)
        if len(new_email) < 3:
            raise HTTPException(status_code=400, detail="Invalid email")
        clash = (
            db.query(models.User)
            .filter(models.User.email == new_email, models.User.id != user.id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=400, detail="Email already in use")
        old = user.email
        user.email = new_email
        write_audit(
            db,
            actor_user_id=user.id,
            action="profile.email_change",
            target_user_id=user.id,
            meta={"from": old, "to": new_email},
        )
    db.commit()
    db.refresh(user)
    return {"user": _user_payload(user, auth.session)}


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == auth.user.id).first()
    if not user or not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    err = validate_password(body.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    user.password_hash = hash_password(body.new_password)
    write_audit(
        db,
        actor_user_id=user.id,
        action="profile.password_change",
        target_user_id=user.id,
    )
    db.commit()
    # Revoke other sessions; keep current.
    try:
        sids = list(session_store.client.smembers(f"user_sessions:{user.id}") or [])
        for sid in sids:
            if sid != auth.session_id:
                session_store.destroy(sid, user.id)
        session_store.client.sadd(f"user_sessions:{user.id}", auth.session_id)
    except Exception:
        session_store.revoke_all(user.id)
    return {"ok": True}


@router.post("/session/touch")
def session_touch(auth: AuthContext = Depends(require_authenticated)):
    return {
        "ok": True,
        "idle_expires_at": auth.session.get("idle_expires_at"),
        "absolute_expires_at": auth.session.get("absolute_expires_at"),
    }
