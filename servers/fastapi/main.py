import os
import json
import glob
import re
import time
import asyncio
import hashlib
import fcntl
from contextlib import contextmanager
from pathlib import Path
from xml.etree import ElementTree as ET
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, List
from worker import celery_app
from fastapi import Depends
from database import engine, ensure_schema, get_db, SessionLocal
from sqlalchemy.orm import Session
import models
from llm_client import (
    call_llm_json,
    call_llm_text,
    llm_user_context,
    probe_text_connection,
)
from languages import LANGUAGE_NAMES
from runtime_limits import stale_status_seconds
from auth.bootstrap import seed_admin_if_needed, seed_demo_users_if_needed
from auth.csrf import CsrfHeaderMiddleware
from auth.deps import AuthContext, get_owned_project, require_admin, require_approved
from auth.migrate_default_user import migrate_default_user_to_admin
from auth.routes import router as auth_router
from auth.admin_routes import router as admin_router
from auth.secrets_crypto import decrypt_secret, ensure_encrypted
from auth.sessions import COOKIE_NAME, session_store, SessionStoreUnavailable

# Creates missing tables and adds columns missing from existing ones, which
# create_all alone never did.
ensure_schema(engine)
seed_admin_if_needed()
seed_demo_users_if_needed()

app = FastAPI(title="Sunairum API")

# A wildcard origin combined with credentials let any page a user visited call
# this API with their cookies. Origins are now explicit; set CORS_ALLOW_ORIGINS
# to a comma-separated list for other deployments.
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,https://170-9-238-9.sslip.io",
    ).split(",")
    if origin.strip()
]

app.add_middleware(CsrfHeaderMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# User files are served only via authenticated /api/files/... (not public StaticFiles).
storage_path = os.path.join(os.path.dirname(__file__), "storage")
os.makedirs(storage_path, exist_ok=True)
migrate_default_user_to_admin(storage_path)

app.include_router(auth_router)
app.include_router(admin_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Lightweight liveness endpoint for Docker and cloud load balancers."""
    return {"status": "ok"}


def sha256_file(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

# WS manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, project_id: str):
        await websocket.accept()
        self.active_connections[project_id] = websocket

    def disconnect(self, project_id: str):
        if project_id in self.active_connections:
            del self.active_connections[project_id]

    async def send_message(self, message: str, project_id: str):
        if project_id in self.active_connections:
            await self.active_connections[project_id].send_text(message)

manager = ConnectionManager()

# Settings Endpoints
class SettingsUpdate(BaseModel):
    provider: str
    base_url: str
    api_key: str
    model_name: str
    # Slide figure generation engine (separate from text).
    image_provider: str | None = None
    image_model_name: str | None = None
    image_base_url: str | None = None
    image_api_key: str | None = None

API_KEY_MASK = "********"


def _mask_api_key(api_key: str | None) -> str:
    """Show only enough of a stored key to identify it."""
    if not api_key:
        return ""
    return f"{API_KEY_MASK}{api_key[-4:]}" if len(api_key) > 4 else API_KEY_MASK


def _connection_fingerprint(
    *,
    provider: str,
    base_url: str,
    api_key_set: bool,
    model_name: str,
    image_provider: str = "",
    image_model_name: str = "",
    image_base_url: str = "",
    image_api_key_set: bool = False,
) -> str:
    """Stable id for the credential surface a connection test covered."""
    payload = "|".join(
        [
            (provider or "").strip().lower(),
            (base_url or "").strip(),
            "1" if api_key_set else "0",
            (model_name or "").strip(),
            (image_provider or "").strip().lower(),
            (image_model_name or "").strip(),
            (image_base_url or "").strip(),
            "1" if image_api_key_set else "0",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _parse_connection_test(raw: str | None) -> dict | None:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _connection_test_response(settings: models.UserSettings) -> dict | None:
    stored = _parse_connection_test(getattr(settings, "connection_test_json", None))
    if not stored:
        return None
    from tasks.image_settings import normalize_image_provider
    from tasks.settings_validation import SettingsValidationError, coerce_stored_provider

    try:
        image_provider = normalize_image_provider(getattr(settings, "image_provider", None))
    except SettingsValidationError:
        image_provider = "openrouter"
    current_fp = _connection_fingerprint(
        provider=coerce_stored_provider(settings.provider),
        base_url=settings.base_url or "",
        api_key_set=bool(settings.api_key),
        model_name=settings.model_name or "",
        image_provider=image_provider,
        image_model_name=getattr(settings, "image_model_name", None) or "",
        image_base_url=getattr(settings, "image_base_url", None) or "",
        image_api_key_set=bool(getattr(settings, "image_api_key", None)),
    )
    stale = stored.get("fingerprint") != current_fp
    return {**stored, "stale": stale}


def _settings_for_user(db: Session, user_id: str) -> models.UserSettings:
    settings = db.query(models.UserSettings).filter(models.UserSettings.user_id == user_id).first()
    if not settings:
        settings = models.UserSettings(user_id=user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@app.get("/api/settings")
def get_settings(
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    from tasks.image_settings import image_defaults, normalize_image_provider
    from tasks.settings_validation import (
        SettingsValidationError,
        coerce_stored_provider,
        scrub_banned_model,
    )

    settings = _settings_for_user(db, auth.user.id)
    dirty = False
    provider = coerce_stored_provider(settings.provider)
    if settings.provider != provider:
        settings.provider = provider
        dirty = True
    model_name = scrub_banned_model(settings.model_name)
    image_model = scrub_banned_model(getattr(settings, "image_model_name", None))
    if model_name != (settings.model_name or ""):
        settings.model_name = model_name
        dirty = True
    if image_model != (getattr(settings, "image_model_name", None) or ""):
        settings.image_model_name = image_model
        dirty = True
    # Vision QA settings retired — clear any leftover stored values.
    if settings.vision_model_name or settings.vision_base_url or settings.vision_api_key:
        settings.vision_model_name = ""
        settings.vision_base_url = ""
        settings.vision_api_key = ""
        dirty = True
    try:
        image_provider = normalize_image_provider(getattr(settings, "image_provider", None))
    except SettingsValidationError:
        image_provider = "openrouter"
    if (getattr(settings, "image_provider", None) or "") != image_provider:
        settings.image_provider = image_provider
        dirty = True
    if dirty:
        db.commit()
        db.refresh(settings)

    plain_key = decrypt_secret(settings.api_key)
    plain_image = decrypt_secret(getattr(settings, "image_api_key", None))
    # Temporary view for fingerprint helpers (do not persist plaintext).
    view = models.UserSettings(
        user_id=settings.user_id,
        provider=provider,
        base_url=settings.base_url,
        api_key=plain_key,
        model_name=model_name,
        image_provider=image_provider,
        image_model_name=image_model,
        image_base_url=getattr(settings, "image_base_url", None) or "",
        image_api_key=plain_image,
        connection_test_json=settings.connection_test_json,
    )
    return {
        "provider": provider,
        "base_url": settings.base_url,
        # Never echo the secret back. The client needs to know whether one is
        # stored and to recognise it in the form, not to read it.
        "api_key": _mask_api_key(plain_key),
        "api_key_set": bool(plain_key),
        "model_name": model_name,
        "image_provider": image_provider,
        "image_model_name": image_model,
        "image_base_url": getattr(settings, "image_base_url", None) or "",
        "image_api_key": _mask_api_key(plain_image),
        "image_api_key_set": bool(plain_image),
        "image_defaults": image_defaults(image_provider),
        "connection_test": _connection_test_response(view),
    }

@app.post("/api/settings")
def update_settings(
    update_data: SettingsUpdate,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    from tasks.image_settings import normalize_image_provider
    from tasks.settings_validation import SettingsValidationError, validate_settings_payload

    try:
        provider = validate_settings_payload(
            provider=update_data.provider,
            base_url=update_data.base_url,
            model_name=update_data.model_name,
            image_provider=update_data.image_provider,
            image_model_name=update_data.image_model_name,
            image_base_url=update_data.image_base_url,
        )
    except SettingsValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    settings = _settings_for_user(db, auth.user.id)
    settings.provider = provider
    settings.base_url = update_data.base_url
    # The client is shown a mask, so echoing it back must not overwrite the key.
    if update_data.api_key == "":
        settings.api_key = ""
    elif not update_data.api_key.startswith(API_KEY_MASK):
        settings.api_key = ensure_encrypted(update_data.api_key)
    settings.model_name = update_data.model_name

    # Vision QA retired with Deep QA — wipe stored vision credentials on save.
    settings.vision_model_name = ""
    settings.vision_base_url = ""
    settings.vision_api_key = ""

    if update_data.image_provider is not None:
        settings.image_provider = normalize_image_provider(update_data.image_provider)
    if update_data.image_model_name is not None:
        settings.image_model_name = update_data.image_model_name.strip()
    if update_data.image_base_url is not None:
        settings.image_base_url = update_data.image_base_url.strip()
    if update_data.image_api_key is not None:
        if update_data.image_api_key == "":
            settings.image_api_key = ""
        elif not update_data.image_api_key.startswith(API_KEY_MASK):
            settings.image_api_key = ensure_encrypted(update_data.image_api_key.strip())

    db.commit()
    return {"status": "ok"}


class SettingsTestRequest(BaseModel):
    """Probe credentials from the settings form without requiring a prior Save."""

    provider: str
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""
    image_provider: str | None = None
    image_model_name: str | None = None
    image_base_url: str | None = None
    image_api_key: str | None = None
    test_image: bool = True


@app.post("/api/settings/test")
def test_settings(
    body: SettingsTestRequest,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Live-check text and image-engine credentials from form values."""
    from tasks.image_settings import normalize_image_provider, probe_image_connection
    from tasks.settings_validation import SettingsValidationError, validate_settings_payload

    try:
        provider = validate_settings_payload(
            provider=body.provider,
            base_url=body.base_url,
            model_name=body.model_name,
            image_provider=body.image_provider,
            image_model_name=body.image_model_name,
            image_base_url=body.image_base_url,
        )
    except SettingsValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    stored = _settings_for_user(db, auth.user.id)
    stored_key = decrypt_secret(stored.api_key)
    stored_image = decrypt_secret(getattr(stored, "image_api_key", None))

    api_key = body.api_key or ""
    if api_key.startswith(API_KEY_MASK):
        api_key = stored_key or ""

    try:
        image_provider = normalize_image_provider(
            body.image_provider
            if body.image_provider is not None
            else getattr(stored, "image_provider", None)
        )
    except SettingsValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    image_api_key = body.image_api_key or ""
    if image_api_key.startswith(API_KEY_MASK):
        image_api_key = stored_image or ""

    text = probe_text_connection(
        provider=provider,
        base_url=body.base_url or "",
        api_key=api_key,
        model_name=body.model_name or "",
    )
    image = None
    if body.test_image:
        image = probe_image_connection(
            provider=image_provider,
            model_name=(body.image_model_name or "") if body.image_model_name is not None else "",
            base_url=(body.image_base_url or "") if body.image_base_url is not None else "",
            api_key=image_api_key,
        )

    text_ok = bool(text.get("ok"))
    image_ok = True if image is None or image.get("skipped") else bool(image.get("ok"))
    failed_optional = image is not None and not image.get("skipped") and not image.get("ok")
    if text_ok and image_ok:
        status = "ok"
    elif text_ok and failed_optional:
        status = "partial"
    else:
        status = "error"

    image_model = (body.image_model_name or "") if body.image_model_name is not None else ""
    image_base = (body.image_base_url or "") if body.image_base_url is not None else ""
    fingerprint = _connection_fingerprint(
        provider=provider,
        base_url=body.base_url or "",
        api_key_set=bool((api_key or "").strip()),
        model_name=body.model_name or "",
        image_provider=image_provider,
        image_model_name=image_model,
        image_base_url=image_base,
        image_api_key_set=bool((image_api_key or "").strip()),
    )
    record = {
        "status": status,
        "ok": status == "ok",
        "text": text,
        "image": image,
        "tested_at": int(time.time()),
        "fingerprint": fingerprint,
    }
    stored.connection_test_json = json.dumps(record, ensure_ascii=False)
    db.commit()

    return {**record, "stale": False}

# Project storage helpers
def get_project_dir(project_id: str, db: Session = None, user_id: str | None = None):
    resolved = user_id
    if db:
        proj = db.query(models.Project).filter(models.Project.project_id == project_id).first()
        if proj:
            resolved = proj.user_id
    if not resolved:
        raise HTTPException(status_code=404, detail="Project not found")
    proj_dir = os.path.join(storage_path, resolved, project_id)
    os.makedirs(proj_dir, exist_ok=True)
    return proj_dir


@app.get("/api/files/{user_id}/{project_id}/{file_path:path}")
def serve_user_file(
    user_id: str,
    project_id: str,
    file_path: str,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    if user_id != auth.user.id and auth.user.role != "admin":
        raise HTTPException(status_code=404, detail="Not found")
    proj = (
        db.query(models.Project)
        .filter(models.Project.project_id == project_id, models.Project.user_id == user_id)
        .first()
    )
    if not proj and auth.user.role != "admin":
        raise HTTPException(status_code=404, detail="Not found")
    root = Path(storage_path) / user_id / project_id
    target = (root / file_path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    media = None
    suffix = target.suffix.lower()
    if suffix == ".png":
        media = "image/png"
    elif suffix in {".jpg", ".jpeg"}:
        media = "image/jpeg"
    elif suffix == ".webp":
        media = "image/webp"
    elif suffix == ".svg":
        media = "image/svg+xml"
    return FileResponse(path=str(target), media_type=media)


def owned_project_dir(project_id: str, auth: AuthContext, db: Session) -> str:
    """Resolve project storage only after ownership check."""
    proj = get_owned_project(project_id, auth, db)
    return get_project_dir(project_id, db, user_id=proj.user_id)

def get_confirm_dir(project_id: str, db: Session = None, auth: AuthContext | None = None):
    if auth is not None:
        proj_dir = owned_project_dir(project_id, auth, db)
    else:
        proj_dir = get_project_dir(project_id, db)
    confirm_dir = os.path.join(proj_dir, "confirm_ui")
    os.makedirs(confirm_dir, exist_ok=True)
    return confirm_dir


def resolve_grounding_mode(proj_dir: str) -> str:
    """Resolve the immutable content policy for one project."""
    policy_path = os.path.join(proj_dir, "validation", "source_policy.json")
    if os.path.isfile(policy_path):
        try:
            with open(policy_path, "r", encoding="utf-8") as stream:
                mode = json.load(stream).get("grounding_mode")
            if mode in {"pdf_strict", "source_grounded", "scratch"}:
                return mode
        except (OSError, json.JSONDecodeError):
            pass
    if os.path.isfile(os.path.join(proj_dir, "source.pdf")) and os.path.isfile(
        os.path.join(proj_dir, "sources", "parser_manifest.json")
    ):
        return "pdf_strict"
    return "scratch"

# Worker-owned run states only. awaiting_user_compile is a pause for the user —
# it must NOT be treated as active (stale timeout was flipping it to "error"
# and kicking people out of the editor while slides already exist).
GENERATION_ACTIVE_STATUSES = {
    "queued", "planning", "generating", "compiling",
    "rendering",
}
SOURCE_ACTIVE_STATUSES = {"source_uploading", "source_parsing", "source_grounding"}
ACTIVE_STATUSES = GENERATION_ACTIVE_STATUSES | SOURCE_ACTIVE_STATUSES
# Derived from the worker's own budgets rather than hardcoded: see runtime_limits.
STALE_STATUS_SECONDS = stale_status_seconds()

def is_generation_active(proj_dir: str) -> bool:
    """True if this project has a generation task that is queued or running."""
    status_path = os.path.join(proj_dir, "status.json")
    if not os.path.exists(status_path):
        return False
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    if data.get("status") not in ACTIVE_STATUSES:
        return False
    updated_at = data.get("updated_at", 0)
    if time.time() - updated_at > STALE_STATUS_SECONDS:
        return False
    return True

def write_generation_status(
    proj_dir: str,
    status: str,
    progress: int = 0,
    message: str = "",
    task_id: str | None = None,
    message_key: str | None = None,
):
    """Write status.json synchronously (used to mark 'queued' before the worker starts).

    `message` stays English; `message_key` names it so the UI can translate it.
    """
    try:
        status_path = os.path.join(proj_dir, "status.json")
        existing = {}
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}
        # Cancelled is sticky against stray worker writes, but Resume must be
        # able to leave cancelled for active generation states.
        if existing.get("status") == "cancelled" and status != "cancelled":
            if status not in GENERATION_ACTIVE_STATUSES | {"awaiting_user_compile"}:
                return
        payload = {"status": status, "progress": progress, "updated_at": int(time.time())}
        if message:
            payload["message"] = message
        if message_key:
            payload["message_key"] = message_key
        if task_id or existing.get("task_id"):
            payload["task_id"] = task_id or existing["task_id"]
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as e:
        print(f"write_generation_status error: {e}")

@app.get("/api/templates")
async def list_templates(auth: AuthContext = Depends(require_approved)):
    """The template packs this install can actually generate into.

    The gallery used to read a static ``public/examples/examples.json`` that a
    plain checkout never contains, so it showed nothing while seven usable packs
    sat in the repository. Listing them from the same directories the generator
    resolves keeps the two from disagreeing about what exists.
    """
    from tasks.template_catalog import installed_packs

    return {"projects": installed_packs()}


@app.get("/api/styles")
async def list_presentation_styles(auth: AuthContext = Depends(require_approved)):
    """Optional presentation-method packs for scratch free_design (not templates)."""
    from tasks.presentation_style import list_styles

    return {"styles": list_styles()}


@app.get("/api/templates/{template_id}/cover")
async def get_template_cover(template_id: str, auth: AuthContext = Depends(require_approved)):
    from fastapi.responses import Response
    from tasks.template_catalog import cover_thumb_jpeg_bytes, pack_cover

    cache_headers = {
        "Cache-Control": "private, max-age=86400",
        "X-Content-Type-Options": "nosniff",
    }

    def _thumb_or_file(path: str):
        thumb = cover_thumb_jpeg_bytes(path, max_width=720, quality=85)
        if thumb:
            return Response(content=thumb, media_type="image/jpeg", headers=cache_headers)
        return FileResponse(path, headers=cache_headers)

    cover = pack_cover(template_id)
    if cover and not str(cover).casefold().endswith(".svg"):
        return _thumb_or_file(cover)
    # Prefer PNG preview slide 1 — never serve SVG to clients.
    from tasks.template_catalog import ensure_pack_png_previews, pack_preview_slides, pack_preview_slide

    ensure_pack_png_previews(template_id)
    slides = pack_preview_slides(template_id)
    if slides:
        png = pack_preview_slide(template_id, slides[0])
        if png:
            return _thumb_or_file(png)
    from tasks.template_catalog import style_card_png_bytes

    return Response(
        content=style_card_png_bytes(template_id),
        media_type="image/png",
        headers=cache_headers,
    )


@app.get("/api/templates/{template_id}/slides")
async def list_template_slides(template_id: str, auth: AuthContext = Depends(require_approved)):
    """Slide filenames for the gallery preview modal (all languages)."""
    from tasks.template_catalog import pack_preview_slides

    slides = pack_preview_slides(template_id)
    if not slides:
        raise HTTPException(status_code=404, detail="This template has no preview slides")
    return {"slides": slides}


@app.get("/api/templates/{template_id}/slides/{filename}")
async def get_template_slide(template_id: str, filename: str, auth: AuthContext = Depends(require_approved)):
    from fastapi.responses import Response
    from tasks.template_catalog import pack_preview_slide, style_card_for_pack

    # Legacy client fallback — serve PNG style card (no SVG responses).
    if filename in {"__english_style_card__.svg", "__english_style_card__.png"}:
        from tasks.template_catalog import style_card_png_bytes

        return Response(
            content=style_card_png_bytes(template_id),
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )
    slide = pack_preview_slide(template_id, filename)
    if not slide:
        raise HTTPException(status_code=404, detail="Preview slide not found")
    media = "image/png"
    if slide.casefold().endswith(".webp"):
        media = "image/webp"
    elif slide.casefold().endswith((".jpg", ".jpeg")):
        media = "image/jpeg"
    return FileResponse(
        slide,
        media_type=media,
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/projects")
async def list_projects(
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    from tasks.project_library import enrich_project_library_fields, sort_library_projects
    from tasks.release_export import is_published_release, ui_status_for_release

    projects_db = (
        db.query(models.Project)
        .filter(models.Project.user_id == auth.user.id)
        .order_by(models.Project.created_at.desc())
        .all()
    )

    projects = []
    for proj in projects_db:
        proj_dir = os.path.join(storage_path, proj.user_id, proj.project_id)
        exports_dir = os.path.join(proj_dir, "exports")
        release_manifest_path = os.path.join(proj_dir, "validation", "release_manifest.json")
        has_pptx = False
        pptx_url = None
        if os.path.isfile(release_manifest_path):
            try:
                with open(release_manifest_path, "r", encoding="utf-8") as f:
                    release = json.load(f)
                release_path = os.path.realpath(os.path.join(proj_dir, release.get("pptx_path", "")))
                exports_root = os.path.realpath(exports_dir) + os.sep
                has_pptx = (
                    is_published_release(release.get("status"))
                    and release.get("run_id")
                    and release_path.startswith(exports_root)
                    and os.path.isfile(release_path)
                    and release.get("pptx_sha256") == sha256_file(release_path)
                )
                if has_pptx:
                    pptx_url = f"/api/download/{proj.project_id}.pptx"
            except Exception:
                has_pptx = False

        projects.append({
            "project_id": proj.project_id,
            "topic": proj.topic,
            "created_at": proj.created_at,
            "has_pptx": has_pptx,
            "pptx_url": pptx_url,
            "pdf_url": f"/api/download/{proj.project_id}.pdf" if has_pptx else None,
        })
        status_path = os.path.join(proj_dir, "status.json")
        status = "done" if has_pptx else "pending"
        progress = 100 if has_pptx else 0
        slide_current = None
        slide_total = None
        slide_title = None
        status_message = None
        status_message_key = None
        error_message = None
        status_updated_at = None
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
                status = ui_status_for_release(status_data.get("status", status))
                progress = status_data.get("progress", progress)
                slide_current = status_data.get("current")
                slide_total = status_data.get("total")
                slide_title = status_data.get("title")
                status_message = status_data.get("message")
                status_message_key = status_data.get("message_key")
                # Legacy Job B wrote "completed"; library/editor expect done*.
                if status == "completed":
                    status = "done"
                    if not status_message_key:
                        status_message_key = "status_completed"
                status_updated_at = status_data.get("updated_at")
                error_message = status_message if status == "error" else None
                if status in ACTIVE_STATUSES and time.time() - status_data.get("updated_at", 0) > STALE_STATUS_SECONDS:
                    progress = int(progress or 0)
                    if status in SOURCE_ACTIVE_STATUSES:
                        from tasks.source_import import write_source_status

                        status = "source_error"
                        status_message = "Source parsing was interrupted or exceeded the operation deadline"
                        status_message_key = "status_source_interrupted"
                        error_message = status_message
                        write_source_status(
                            proj_dir,
                            status,
                            progress,
                            status_message,
                            message_key=status_message_key,
                            task_id=status_data.get("task_id"),
                            error=status_message,
                        )
                    else:
                        status = "error"
                        status_message = "Generation was interrupted or exceeded the operation deadline"
                        status_message_key = "status_generation_interrupted"
                        error_message = status_message
                        write_generation_status(
                            proj_dir,
                            "error",
                            progress,
                            status_message,
                            status_data.get("task_id"),
                            message_key=status_message_key,
                        )
            except Exception:
                pass
        library = enrich_project_library_fields(
            user_id=proj.user_id,
            project_id=proj.project_id,
            topic=proj.topic,
            has_pdf_flag=proj.has_pdf,
            last_opened_at=getattr(proj, "last_opened_at", None),
            proj_dir=proj_dir,
            status_total=slide_total,
        )
        projects[-1].update({
            "status": status,
            "progress": progress,
            "slide_current": slide_current,
            "slide_total": slide_total,
            "slide_title": slide_title,
            "message": status_message,
            # Names the message so the UI can say it in the reader's language;
            # `message` above stays English for logs and as a fallback.
            "message_key": status_message_key,
            "error_message": error_message,
            "status_updated_at": status_updated_at,
            **library,
        })
        if status in ACTIVE_STATUSES:
            # A rerun can leave an older export in place. Do not present it as
            # the result of the currently active task.
            projects[-1]["has_pptx"] = False
            projects[-1]["pptx_url"] = None
            projects[-1]["pdf_url"] = None
        elif status not in {"done", "done_with_issues"}:
            projects[-1]["has_pptx"] = False
            projects[-1]["pptx_url"] = None
            projects[-1]["pdf_url"] = None
        elif not projects[-1]["has_pptx"]:
            status = "error"
            status_message = "Released PPTX manifest is missing or invalid"
            error_message = status_message
            projects[-1].update({
                "status": status,
                "message": status_message,
                "message_key": "status_release_missing",
                "error_message": error_message,
            })

    return {"projects": sort_library_projects(projects)}


@app.post("/api/projects/{project_id}/touch")
async def touch_project(
    project_id: str,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Record that the user opened this project (library Recents / Continue)."""
    proj = get_owned_project(project_id, auth, db)

    now = int(time.time())
    proj.last_opened_at = now
    db.commit()
    return {"ok": True, "project_id": project_id, "last_opened_at": now}


def _celery_revoke(task_id: str) -> None:
    try:
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    except Exception as revoke_error:
        print(f"[delete] revoke {task_id} skipped: {revoke_error}")


def _purge_owned_project(proj: models.Project) -> dict:
    """Remove every storage tree for project_id, then caller deletes the DB row."""
    try:
        from tasks.project_purge import purge_project_files
    except ImportError:  # pragma: no cover
        from project_purge import purge_project_files  # type: ignore
    return purge_project_files(
        storage_path,
        proj.project_id,
        preferred_user_id=str(proj.user_id or ""),
        revoke=_celery_revoke,
    )


@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Hard-delete one project: revoke tasks, wipe all matching storage dirs, drop DB row."""
    proj = get_owned_project(project_id, auth, db)
    file_result = _purge_owned_project(proj)
    db.delete(proj)
    db.commit()
    # Confirm DB row is gone (no soft-delete).
    lingering = (
        db.query(models.Project)
        .filter(models.Project.project_id == project_id)
        .first()
    )
    if lingering is not None:
        db.delete(lingering)
        db.commit()
    if file_result.get("errors"):
        print(f"[delete] P{project_id} file purge warnings: {file_result['errors']}")
    return {
        "status": "success",
        "message": f"Project {project_id} deleted",
        "removed_dirs": file_result.get("removed_dirs") or [],
        "db_deleted": True,
    }

@app.delete("/api/projects")
async def delete_all_projects(
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Hard-delete every project owned by the current user (History → Clear All)."""
    try:
        from tasks.project_purge import purge_user_storage
    except ImportError:  # pragma: no cover
        from project_purge import purge_user_storage  # type: ignore

    projects = (
        db.query(models.Project)
        .filter(models.Project.user_id == auth.user.id)
        .all()
    )
    removed_dirs: list[str] = []
    for proj in projects:
        file_result = _purge_owned_project(proj)
        removed_dirs.extend(file_result.get("removed_dirs") or [])
        db.delete(proj)
    db.commit()
    # Wipe the whole user bucket so no orphan files remain under this account.
    user_wipe = purge_user_storage(storage_path, auth.user.id)
    remaining = (
        db.query(models.Project)
        .filter(models.Project.user_id == auth.user.id)
        .count()
    )
    if remaining:
        db.query(models.Project).filter(models.Project.user_id == auth.user.id).delete(
            synchronize_session=False
        )
        db.commit()
        remaining = 0
    return {
        "status": "success",
        "message": "All projects deleted",
        "removed_dirs": removed_dirs,
        "user_storage_removed": bool(user_wipe.get("removed")),
        "db_remaining": remaining,
    }

from fastapi import UploadFile, File, Form

@app.post("/api/projects/{project_id}/upload_source")
async def upload_source(
    project_id: str, 
    topic: str = Form(...), 
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)
):
    user_id = auth.user.id
    proj_dir = os.path.join(storage_path, user_id, project_id)
    os.makedirs(proj_dir, exist_ok=True)

    # Save only the uploaded bytes in the request. Parsing and evidence
    # creation continue in Celery so the editor can open immediately.
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")
    file_path = os.path.join(proj_dir, "source.pdf")
    with open(file_path, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    if not os.path.isfile(file_path) or os.path.getsize(file_path) <= 0:
        raise HTTPException(status_code=500, detail="Failed to persist uploaded PDF")

    proj = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    if proj is None:
        proj = models.Project(
            project_id=project_id,
            user_id=user_id,
            topic=topic,
            status="source_uploading",
            has_pdf=1,
            created_at=int(time.time()),
        )
        db.add(proj)
    else:
        proj.topic = topic
        proj.user_id = user_id
        proj.status = "source_uploading"
        proj.has_pdf = 1
    db.commit()

    import fcntl

    from tasks.source_import import (
        SOURCE_ACTIVE_STATUSES,
        read_source_status,
        write_source_status,
    )

    # Idempotent enqueue under a project lock: React Strict Mode / double-submit
    # can POST twice nearly simultaneously; without a lock both would send_task.
    lock_path = os.path.join(proj_dir, ".upload_source.lock")
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            existing = read_source_status(proj_dir)
            existing_task = str(existing.get("task_id") or "").strip()
            existing_status = str(existing.get("status") or "")
            updated_at = int(existing.get("updated_at") or 0)
            age = int(time.time()) - updated_at if updated_at > 0 else 10**9
            if (
                existing_task
                and not existing_task.startswith("pending:")
                and existing_status in SOURCE_ACTIVE_STATUSES
                and age < 180
            ):
                return {
                    "status": "queued",
                    "message": "Source upload accepted; parsing continues in the editor",
                    "task_id": existing_task,
                    "grounding_mode": "pdf_strict",
                    "deduped": True,
                }

            task = celery_app.send_task(
                "tasks.source_import_task.parse_uploaded_source",
                args=[project_id, topic, user_id],
            )
            write_source_status(
                proj_dir,
                "source_uploading",
                0,
                "Upload received; source parsing is queued",
                message_key="source_status_uploading",
                task_id=task.id,
            )
            return {
                "status": "queued",
                "message": "Source upload accepted; parsing continues in the editor",
                "task_id": task.id,
                "grounding_mode": "pdf_strict",
            }
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@app.get("/api/projects/{project_id}/source-status")
async def get_source_status(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    from tasks.source_import import source_status_summary

    project_dir = owned_project_dir(project_id, auth, db)
    summary = source_status_summary(project_dir)
    # Client may open the editor before bytes finish landing. Missing PDF while
    # still in source_uploading is "in flight", not a hard failure — only error
    # once the status file is stale (upload abandoned).
    if (
        not os.path.isfile(os.path.join(project_dir, "source.pdf"))
        and summary["status"] == "source_uploading"
    ):
        updated_at = int(summary.get("updated_at") or 0)
        stale = updated_at > 0 and (int(time.time()) - updated_at) > 120
        if stale:
            summary.update({
                "status": "source_error",
                "error": "Uploaded source was not found",
                "message": "Source upload did not complete",
                "message_key": "source_status_error",
                "ready": False,
            })
        else:
            summary.update({
                "status": "source_uploading",
                "message": "Uploading your PDF...",
                "message_key": "source_status_uploading",
                "ready": False,
                "error": None,
            })
    return summary


@app.get("/api/projects/{project_id}/source-figures")
async def get_source_figures(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Extracted PDF figures for the Both-mode picker (id + thumbnail URL)."""
    project_dir = owned_project_dir(project_id, auth, db)
    proj = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    user_id = proj.user_id if proj else auth.user.id
    index_path = os.path.join(project_dir, "sources", "pdf_images", "index.json")
    figures: list[dict] = []
    if os.path.isfile(index_path):
        try:
            with open(index_path, encoding="utf-8") as handle:
                figures = json.load(handle).get("figures") or []
        except Exception:
            figures = []
    items = []
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        file_name = str(figure.get("file") or "").strip()
        asset_id = str(
            figure.get("id") or figure.get("asset_id") or file_name or ""
        ).strip()
        if not asset_id:
            continue
        thumb = (
            f"/api/files/{user_id}/{project_id}/sources/pdf_images/{file_name}"
            if file_name
            else ""
        )
        items.append({
            "id": asset_id,
            "file": file_name,
            "page": figure.get("page"),
            "ratio": figure.get("ratio"),
            "thumb_url": thumb,
        })
    return {"figures": items}


def _table_cell_text(cell: object) -> str:
    if isinstance(cell, dict):
        return str(cell.get("text") or cell.get("value") or "").strip()
    if cell is None:
        return ""
    return str(cell).strip()


def _table_preview_matrix(
    table: dict,
    *,
    max_rows: int = 4,
    max_cols: int = 4,
    cell_chars: int = 18,
) -> list[list[str]]:
    """Header+rows matrix for the stage3 visual picker / modal."""
    headers = table.get("headers") or []
    rows = table.get("rows") or []
    matrix: list[list[str]] = []
    if isinstance(headers, list) and headers:
        matrix.append([_table_cell_text(cell)[:cell_chars] for cell in headers[:max_cols]])
    if isinstance(rows, list):
        for row in rows[: max(0, max_rows - len(matrix))]:
            if not isinstance(row, list):
                continue
            matrix.append([_table_cell_text(cell)[:cell_chars] for cell in row[:max_cols]])
    return matrix


@app.get("/api/projects/{project_id}/source-tables")
async def get_source_tables(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Extracted PDF tables for the stage3 picker (caption + preview + full)."""
    project_dir = owned_project_dir(project_id, auth, db)
    tables: list[dict] = []
    # Prefer evidence bundle tables; fall back to sources/source_tables.json.
    for candidate in (
        os.path.join(project_dir, "sources", "evidence_bundle.json"),
        os.path.join(project_dir, "validation", "evidence_bundle.json"),
        os.path.join(project_dir, "sources", "source_tables.json"),
    ):
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("tables"), dict):
            raw = payload["tables"].get("tables") or []
        elif isinstance(payload, dict) and isinstance(payload.get("tables"), list):
            raw = payload.get("tables") or []
        elif isinstance(payload, list):
            raw = payload
        else:
            raw = []
        if isinstance(raw, list) and raw:
            tables = [row for row in raw if isinstance(row, dict)]
            break
    items = []
    for index, table in enumerate(tables, start=1):
        table_id = str(table.get("table_id") or table.get("id") or "").strip()
        if not table_id:
            continue
        caption = str(
            table.get("caption") or table.get("title") or table.get("label") or ""
        ).strip()
        page = table.get("page") or table.get("page_start") or table.get("page_number")
        if not caption:
            caption = f"Table {index}" + (f" · page {page}" if page is not None else "")
        preview = _table_preview_matrix(table, max_rows=4, max_cols=4, cell_chars=18)
        full = _table_preview_matrix(table, max_rows=40, max_cols=12, cell_chars=80)
        row_count = len(table.get("rows") or []) if isinstance(table.get("rows"), list) else 0
        header_cols = len(table.get("headers") or []) if isinstance(table.get("headers"), list) else 0
        first_row_cols = (
            len(table["rows"][0])
            if isinstance(table.get("rows"), list) and table["rows"] and isinstance(table["rows"][0], list)
            else 0
        )
        items.append({
            "id": table_id,
            "page": page,
            "caption": caption[:200],
            "preview": preview,
            "full": full,
            "rows": row_count,
            "cols": header_cols or first_row_cols or None,
        })
    return {"tables": items}

@app.get("/api/projects/{project_id}/stage1")
async def get_stage1(project_id: str, topic: str, lang: str = Query("auto"), auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    # Scratch projects have no upload request to create their DB/storage row.
    # Establish ownership idempotently in the first stage-1 transaction.
    proj = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    if proj is None:
        if not re.fullmatch(r"proj_[a-z0-9]{4,32}", project_id):
            raise HTTPException(status_code=400, detail="Invalid project id")
        proj = models.Project(
            project_id=project_id,
            user_id=auth.user.id,
            topic=topic,
            status="created",
            has_pdf=0,
            created_at=int(time.time()),
            last_opened_at=int(time.time()),
        )
        db.add(proj)
        db.commit()
        os.makedirs(os.path.join(storage_path, auth.user.id, project_id), exist_ok=True)
    elif proj.user_id != auth.user.id and auth.user.role != "admin":
        raise HTTPException(status_code=404, detail="Not found")

    confirm_dir = get_confirm_dir(project_id, db, auth)
    project_dir = owned_project_dir(project_id, auth, db)
    from tasks.source_import import SOURCE_ACTIVE_STATUSES, source_status_summary

    if os.path.isfile(os.path.join(project_dir, "source.pdf")):
        source_state = source_status_summary(project_dir)
        if source_state["status"] in SOURCE_ACTIVE_STATUSES:
            raise HTTPException(status_code=409, detail="PDF source is still being parsed")
        if source_state["status"] == "source_error":
            raise HTTPException(status_code=422, detail=source_state.get("error") or "PDF source parsing failed")
        if not source_state["ready"]:
            raise HTTPException(status_code=409, detail="PDF source evidence is not ready")
    grounding_mode = resolve_grounding_mode(project_dir)
    
    # Save session info (topic + language); invalidate cache when language changes
    session_path = os.path.join(confirm_dir, "session.json")
    prev_lang = "auto"
    if os.path.exists(session_path):
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                prev_lang = json.load(f).get("lang", "auto")
        except Exception:
            prev_lang = "auto"
    with open(session_path, "w", encoding="utf-8") as f:
        json.dump({"project_id": project_id, "topic": topic, "lang": lang}, f, ensure_ascii=False, indent=2)
        
    file_path = os.path.join(confirm_dir, "recommendations.stage1.json")
    
    if prev_lang != lang and os.path.exists(file_path):
        os.remove(file_path)
    
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("grounding_mode") == grounding_mode:
            return cached
        os.remove(file_path)
            
    # Generate recommendations via configured OpenAI-compatible LLM
    lang_name = LANGUAGE_NAMES.get(lang, lang)
    if lang == "auto":
        lang_line = "Choose the language of every text value to best fit the topic and the audience."
        primary_language = "auto"
    else:
        lang_line = f"Every text value must be written in {lang_name}."
        primary_language = lang
    system_inst = (
        "You are a professional presentation strategist. Given a topic, define the "
        "objectives and the concept for a presentation about it."
    )
    source_context = ""
    if grounding_mode == "pdf_strict":
        from tasks.grounded_planner import evidence_catalog, load_evidence_bundle
        source_context = (
            "\nPDF STRICT SOURCE EVIDENCE. Use only this PDF evidence for factual claims. "
            "Do not add outside facts or unsupported numbers.\n"
            + evidence_catalog(load_evidence_bundle(project_dir))
        )
    prompt = f"""Topic: '{topic}'.
{source_context}
Produce output that conforms exactly to the JSON schema below. {lang_line}
The placeholder text in the schema describes what each field must contain; replace
every one of them with a concrete value derived from the topic.
{{
  "stage": "stage1",
  "lang": "{primary_language}",
  "primary_language": "{primary_language}",
  "recommend": {{
    "canvas": "ppt169"
  }},
  "audience": {{ "value": "who the presentation is for, e.g. investors and partners" }},
  "communication_intent": {{ "value": "what the presentation sets out to communicate" }},
  "audience_outcome": {{ "value": "what the audience should do or believe afterwards" }},
  "core_message": {{ "value": "the single core message, in one or two sentences" }},
  "delivery_context": {{ "value": "how it will be delivered, e.g. a 15-minute talk" }},
  "artifact_afterlife": {{ "value": "what happens to the deck afterwards, e.g. shared as a PDF" }},
  "content_divergence": {{ "value": "{('Restructure only within the supplied PDF evidence. Do not add external facts.' if grounding_mode == 'pdf_strict' else 'Restructure and expand within the source.')}" }}
}}"""
    try:
        with llm_user_context(auth.user.id):
            data = call_llm_json(system_inst, prompt)
    except RuntimeError as llm_error:
        raise HTTPException(status_code=502, detail=str(llm_error)) from llm_error
    except Exception as llm_error:
        # Surface provider outages as 502 instead of an opaque 500 stack.
        name = type(llm_error).__name__
        if "APIConnectionError" in name or "ConnectError" in name:
            from llm_client import format_llm_connection_error, get_active_settings

            with llm_user_context(auth.user.id):
                settings = get_active_settings()
            raise HTTPException(
                status_code=502,
                detail=format_llm_connection_error(
                    llm_error,
                    provider=settings.provider or "",
                    base_url=settings.base_url or "",
                ),
            ) from llm_error
        raise
    data["stage"] = "stage1"
    data["lang"] = primary_language
    data["primary_language"] = primary_language
    data["grounding_mode"] = grounding_mode
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    return data

class Stage1Confirm(BaseModel):
    canvas: str
    audience: str
    communication_intent: str
    audience_outcome: str
    core_message: str
    delivery_context: str
    artifact_afterlife: str
    template_id: str | None = None
    language: str | None = None

@app.post("/api/projects/{project_id}/stage1/confirm")
async def confirm_stage1(project_id: str, request: Stage1Confirm, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    confirm_dir = get_confirm_dir(project_id, db, auth)
    result_path = os.path.join(confirm_dir, "result.json")
    
    primary_language = request.language or "auto"
    if primary_language not in LANGUAGE_NAMES:
        primary_language = "auto"
    
    result_data = {
        "stage": "stage1",
        "status": "stage1-confirmed",
        "primary_language": primary_language,
        "canvas": request.canvas,
        "audience": request.audience,
        "communication_intent": request.communication_intent,
        "audience_outcome": request.audience_outcome,
        "core_message": request.core_message,
        "delivery_context": request.delivery_context,
        "artifact_afterlife": request.artifact_afterlife,
        "content_divergence": "Restructure and expand within the source."
    }
    result_data["grounding_mode"] = resolve_grounding_mode(owned_project_dir(project_id, auth, db))
    
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    # Template mode: design comes from the selected template (spec_lock.md),
    # so skip the AI design-alternative generation entirely.
    stage2_file = os.path.join(confirm_dir, "recommendations.stage2.json")
    if request.template_id:
        if os.path.exists(stage2_file):
            os.remove(stage2_file)
        stage3_file = os.path.join(confirm_dir, "recommendations.stage3.json")
        if os.path.exists(stage3_file):
            os.remove(stage3_file)
        return {"message": "Stage 1 confirmed", "next_stage": "stage3", "template_design": "applied"}

    # Generate Stage 2 recommendations in the background.
    # The *_tr suffixes below are legacy field names the editor reads; they carry
    # display text in whatever language the user picked, not necessarily Turkish.
    stage2_lang_line = (
        "Choose the language of every text value to match the language of the strategy above."
        if primary_language == "auto"
        else f"Every text value must be written in {LANGUAGE_NAMES.get(primary_language, primary_language)}."
    )
    system_inst = (
        "You are a professional presentation designer. Given a presentation strategy, "
        "produce three coordinated design alternatives (Safe, Shifted, Bold)."
    )
    prompt = f"""Presentation strategy:
{json.dumps(result_data, ensure_ascii=False)}

Produce output that conforms exactly to the JSON schema below. {stage2_lang_line}
The text values shown are examples of the kind of content each field expects;
replace them with values suited to this strategy.
{{
  "stage": "stage2",
  "lang": "{primary_language}",
  "recommend": {{
    "delivery_purpose": "balanced",
    "mode": "pyramid",
    "visual_style": "swiss-minimal",
    "image_usage": ["ai", "provided"]
  }},
  "page_count": {{ "value": "8-12" }},
  "template_application": {{ "value": "how the template palette and layout will be applied, and how copy will be rewritten for the topic" }},
  "image_notes": {{ "value": "the imagery and icon direction, e.g. minimalist technology illustrations" }},
  "custom_candidates": {{
    "mode": {{ "name_tr": "Custom Mode", "behavior_tr": "Dynamic layout adapted to the topic." }},
    "visual_style": {{ "name_tr": "Custom Style", "behavior_tr": "A bespoke combination of typefaces and colours." }},
    "image_strategy": {{ "name_tr": "Custom Visual Strategy", "rendering": "custom", "visual_tr": "Concept illustrations", "mood_tr": "Creative" }}
  }},
  "design_directions": {{
    "selected": 0,
    "candidates": [
      {{
        "name_tr": "Corporate and Safe (Safe)",
        "note_tr": "Clean, restrained, professional lines.",
        "visual_style": "swiss-minimal",
        "icons": "tabler-outline",
        "color": {{
          "name_tr": "Classic Blue",
          "palette": {{
            "background": "#FFFFFF",
            "secondary_bg": "#F8FAFC",
            "primary": "#1E3A8A",
            "accent": "#F59E0B",
            "secondary_accent": "#3B82F6",
            "body_text": "#0F172A"
          }}
        }},
        "typography": {{
          "name_tr": "Inter + Arial",
          "heading": {{ "primary": "Inter", "english": "Arial", "css": "sans-serif" }},
          "body": {{ "primary": "Inter", "english": "Arial", "css": "sans-serif" }},
          "body_size": 24
        }},
        "image_strategy": {{
          "name_tr": "Flat Illustration",
          "rendering": "vector-illustration",
          "visual_tr": "Minimalist flat vector illustrations",
          "mood_tr": "Clean and legible"
        }}
      }},
      {{
        "name_tr": "Creative and Striking (Shifted)",
        "note_tr": "More modern colours and original layouts.",
        "visual_style": "creative",
        "icons": "tabler-filled",
        "color": {{
          "name_tr": "Emerald and Violet",
          "palette": {{
            "background": "#0F172A",
            "secondary_bg": "#1E293B",
            "primary": "#10B981",
            "accent": "#8B5CF6",
            "secondary_accent": "#EC4899",
            "body_text": "#F8FAFC"
          }}
        }},
        "typography": {{
          "name_tr": "Poppins + Helvetica",
          "heading": {{ "primary": "Poppins", "english": "Helvetica", "css": "sans-serif" }},
          "body": {{ "primary": "Poppins", "english": "Helvetica", "css": "sans-serif" }},
          "body_size": 24
        }},
        "image_strategy": {{
          "name_tr": "Glassmorphism",
          "rendering": "glassmorphism",
          "visual_tr": "Translucent elements and gradient transitions",
          "mood_tr": "Modern and technological"
        }}
      }},
      {{
        "name_tr": "Bold and Brutalist (Bold)",
        "note_tr": "High contrast, bold and dynamic.",
        "visual_style": "brutalist",
        "icons": "chunk-filled",
        "color": {{
          "name_tr": "Brutalist Red",
          "palette": {{
            "background": "#F4F4F5",
            "secondary_bg": "#E4E4E7",
            "primary": "#DC2626",
            "accent": "#000000",
            "secondary_accent": "#2563EB",
            "body_text": "#09090B"
          }}
        }},
        "typography": {{
          "name_tr": "Impact + Arial",
          "heading": {{ "primary": "Impact", "english": "Arial", "css": "sans-serif" }},
          "body": {{ "primary": "Arial", "english": "Arial", "css": "sans-serif" }},
          "body_size": 26
        }},
        "image_strategy": {{
          "name_tr": "High Contrast",
          "rendering": "high-contrast",
          "visual_tr": "High contrast black and white imagery",
          "mood_tr": "Bold and clear"
        }}
      }}
    ]
}}"""
    try:
        with llm_user_context(auth.user.id):
            stage2_data = call_llm_json(system_inst, prompt)
        stage2_data["stage"] = "stage2"
        stage2_data["lang"] = primary_language
        with open(stage2_file, "w", encoding="utf-8") as f:
            json.dump(stage2_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to pre-generate stage2: {e}")
        raise HTTPException(status_code=500, detail=f"Could not generate design alternatives (AI error): {e}")
        
    return {"message": "Stage 1 confirmed", "next_stage": "stage2"}

@app.get("/api/projects/{project_id}/stage2")
async def get_stage2(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    confirm_dir = get_confirm_dir(project_id, db, auth)
    file_path = os.path.join(confirm_dir, "recommendations.stage2.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Stage 2 recommendations not ready. Please confirm Stage 1 first.")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

class ColorPaletteSchema(BaseModel):
    background: str
    secondary_bg: str
    primary: str
    accent: str
    secondary_accent: str
    body_text: str

class ColorSchema(BaseModel):
    name_tr: str
    palette: ColorPaletteSchema

class TypographyFontSchema(BaseModel):
    primary: str
    english: str
    css: str

class TypographySchema(BaseModel):
    name_tr: str
    heading: TypographyFontSchema
    body: TypographyFontSchema
    body_size: int

class ImageStrategySchema(BaseModel):
    name_tr: str
    rendering: str
    visual_tr: str
    mood_tr: str

class Stage2Confirm(BaseModel):
    delivery_purpose: str
    mode: str
    visual_style: str
    image_usage: List[str]
    page_count: str
    template_application: str
    image_notes: str
    color: ColorSchema
    typography: TypographySchema
    icons: str
    image_strategy: ImageStrategySchema | None = None

@app.post("/api/projects/{project_id}/stage2/confirm")
async def confirm_stage2(project_id: str, request: Stage2Confirm, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    confirm_dir = get_confirm_dir(project_id, db, auth)
    result_path = os.path.join(confirm_dir, "result.json")
    
    if not os.path.exists(result_path):
        raise HTTPException(status_code=404, detail="Stage 1 must be confirmed first")
        
    with open(result_path, "r", encoding="utf-8") as f:
        result_data = json.load(f)
        
    result_data.update({
        "stage": "stage2",
        "status": "stage2-confirmed",
        "delivery_purpose": request.delivery_purpose,
        "mode": request.mode,
        "visual_style": request.visual_style,
        "image_usage": request.image_usage,
        "page_count": request.page_count,
        "template_application": request.template_application,
        "image_notes": request.image_notes,
        "color": request.color.dict(),
        "typography": request.typography.dict(),
        "icons": request.icons,
    })
    if request.image_strategy:
        result_data["image_strategy"] = request.image_strategy.dict()
        
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
        
    # Generate Stage 3 recommendations
    stage3_file = os.path.join(confirm_dir, "recommendations.stage3.json")
    stage3_data = {
        "stage": "stage3",
        "lang": str(result_data.get("primary_language") or "auto"),
        "recommend": {
            "image_ai_path": "auto",
            "formula_policy": "mixed",
            "generation_mode": "continuous"
        },
        "proactive_speaker_notes": {"value": True},
        "target_duration_minutes": {"value": 15},
        "notes_wpm": {"value": 125},
        "proactive_custom_animations": {"value": False},
        "custom_animation_effect": {"value": "fade"},
        "proactive_narration_audio": {"value": False},
        "refine_spec": {"value": False}
    }
    with open(stage3_file, "w", encoding="utf-8") as f:
        json.dump(stage3_data, f, ensure_ascii=False, indent=2)
        
    return {"message": "Stage 2 confirmed", "next_stage": "stage3"}

class Stage3Confirm(BaseModel):
    image_ai_path: str
    formula_policy: str
    proactive_speaker_notes: bool
    proactive_custom_animations: bool
    custom_animation_effect: str | None = None
    proactive_narration_audio: bool
    # Speak-time budget for duration-aware speaker notes (minutes).
    target_duration_minutes: float | None = 15
    notes_wpm: int | None = 125
    template_id: str | None = None
    topic: str
    n_slides: str | None = None
    language: str | None = None
    # Product choices: ai | both (legacy pdf→both, none→ai).
    # PDF uploads are coerced to both server-side; ai is for scratch illustrations.
    image_source: str = "both"
    # Scratch: Image-engine enrich budget (0–6). Ignored / zeroed for PDF.
    ai_enrich_max_new: int | None = None
    # Under both: which extracted PDF figures may be placed (empty = all eligible).
    selected_figure_ids: list[str] | None = None
    selected_table_ids: list[str] | None = None
    figure_render_mode: str = "exact"
    table_render_mode: str = "exact"
    # Tone, style and constraints. Kept apart from `topic` so it can be handed to
    # the model as a directive rather than reused as the deck's subject matter.
    additional_instructions: str | None = None
    # Scratch-only presentation method pack id (ppt-master styles). Ignored when
    # template_id / design-reference pack is set.
    style_id: str | None = None
    presentation_style: str | None = None

@app.post("/api/projects/{project_id}/generate")
async def generate_ppt_final(project_id: str, request: Stage3Confirm, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    confirm_dir = get_confirm_dir(project_id, db, auth)
    result_path = os.path.join(confirm_dir, "result.json")
    
    if not os.path.exists(result_path):
        # Fallback if UI skipped stages
        result_data = {
            "stage": "stage2",
            "status": "stage2-confirmed",
            "delivery_purpose": "balanced",
            "mode": "pyramid",
            "visual_style": "swiss-minimal",
            "image_usage": ["none"],
            "page_count": "5",
            "template_application": "",
            "image_notes": "",
            "color": {
                "name_tr": "Classic Blue",
                "palette": {
                    "background": "#FFFFFF", "secondary_bg": "#F8FAFC",
                    "primary": "#1E3A8A", "accent": "#F59E0B",
                    "secondary_accent": "#3B82F6", "body_text": "#0F172A"
                }
            },
            "typography": {
                "name_tr": "Inter + Arial",
                "heading": { "primary": "Inter", "english": "Arial", "css": "sans-serif" },
                "body": { "primary": "Inter", "english": "Arial", "css": "sans-serif" },
                "body_size": 24
            },
            "icons": "tabler-outline",
        }
    else:
        with open(result_path, "r", encoding="utf-8") as f:
            result_data = json.load(f)
        
    # Explicit slide count (Auto => leave LLM/template to decide)
    if request.n_slides and request.n_slides.strip().isdigit():
        result_data["page_count"] = {"value": str(int(request.n_slides))}
    elif "page_count" not in result_data:
        result_data["page_count"] = {"value": "8-12"}
    # Presentation language override
    if request.language and request.language in LANGUAGE_NAMES:
        result_data["primary_language"] = request.language
    
    from tasks.image_source_policy import (
        coerce_image_source_for_grounding,
        normalize_ai_enrich_max_new,
        normalize_render_mode,
        normalize_selected_figure_ids,
        normalize_selected_table_ids,
    )
    from tasks.slide_transitions import normalize_slide_transition

    result_data.update({
        "stage": "final",
        "status": "confirmed",
        "image_ai_path": request.image_ai_path,
        "image_source": request.image_source,
        "ai_enrich_max_new": request.ai_enrich_max_new,
        "selected_figure_ids": normalize_selected_figure_ids(request.selected_figure_ids),
        "selected_table_ids": normalize_selected_table_ids(request.selected_table_ids),
        "figure_render_mode": normalize_render_mode(request.figure_render_mode, "exact"),
        "table_render_mode": normalize_render_mode(request.table_render_mode, "exact"),
        "formula_policy": request.formula_policy,
        "proactive_speaker_notes": request.proactive_speaker_notes,
        "proactive_custom_animations": request.proactive_custom_animations,
        "custom_animation_effect": normalize_slide_transition(
            request.proactive_custom_animations,
            request.custom_animation_effect,
        ),
        "proactive_narration_audio": request.proactive_narration_audio,
        "target_duration_minutes": max(
            1.0,
            float(request.target_duration_minutes if request.target_duration_minutes is not None else 15),
        ),
        "notes_wpm": max(60, int(request.notes_wpm if request.notes_wpm is not None else 125)),
        "additional_instructions": (request.additional_instructions or "").strip(),
    })
    # Presentation style: scratch only (never with design-reference template_id).
    style_raw = (request.presentation_style or request.style_id or "").strip()
    if request.template_id:
        result_data.pop("presentation_style", None)
        result_data.pop("style_id", None)
    elif style_raw:
        from tasks.presentation_style import normalize_style_id

        sid = normalize_style_id(style_raw, allow=True)
        if sid:
            result_data["presentation_style"] = sid
            result_data["style_id"] = sid
        else:
            result_data.pop("presentation_style", None)
            result_data.pop("style_id", None)
    else:
        result_data.pop("presentation_style", None)
        result_data.pop("style_id", None)
    if result_data.get("grounding_mode") == "pdf_strict":
        # Claims/evidence from the PDF only; visuals are PDF crops/tables.
        result_data["external_knowledge"] = False
    
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
        
    proj = get_owned_project(project_id, auth, db)
    user_id = proj.user_id
    proj_dir = os.path.join(storage_path, user_id, project_id)
    resolved_grounding_mode = resolve_grounding_mode(proj_dir)
    result_data["grounding_mode"] = resolved_grounding_mode
    result_data["image_source"] = coerce_image_source_for_grounding(
        result_data.get("image_source"), resolved_grounding_mode
    )
    result_data["ai_enrich_max_new"] = normalize_ai_enrich_max_new(
        result_data.get("ai_enrich_max_new"),
        grounding_mode=resolved_grounding_mode,
        image_source=result_data.get("image_source"),
    )
    result_data["selected_figure_ids"] = normalize_selected_figure_ids(
        result_data.get("selected_figure_ids")
    )
    result_data["selected_table_ids"] = normalize_selected_table_ids(
        result_data.get("selected_table_ids")
    )
    result_data["figure_render_mode"] = normalize_render_mode(
        result_data.get("figure_render_mode"), "exact"
    )
    result_data["table_render_mode"] = normalize_render_mode(
        result_data.get("table_render_mode"), "exact"
    )
    if resolved_grounding_mode == "pdf_strict":
        result_data["external_knowledge"] = False
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    # Per-project guard: reject if a generation task is already queued/running
    if is_generation_active(proj_dir):
        raise HTTPException(
            status_code=409,
            detail="This project is already generating. Please wait until it finishes or check the history page.",
        )

    release_manifest_path = os.path.join(proj_dir, "validation", "release_manifest.json")
    if os.path.exists(release_manifest_path):
        os.remove(release_manifest_path)
    write_generation_status(proj_dir, "queued", 0, "Generation queued", message_key="status_queued")

    # Queue the Celery task
    primary_color = None
    try:
        primary_color = result_data["color"]["palette"]["primary"]
    except (KeyError, TypeError):
        pass
    task = celery_app.send_task(
        "tasks.generate_task.run_generation",
        args=[request.topic, project_id, request.template_id, primary_color, user_id]
    )
    write_generation_status(proj_dir, "queued", 0, "Generation queued", task.id, message_key="status_queued")
    
    return {"message": "Generation started", "task_id": task.id, "project_id": project_id}

@app.post("/api/projects/{project_id}/cancel")
async def cancel_generation(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    proj_dir = owned_project_dir(project_id, auth, db)
    status_path = os.path.join(proj_dir, "status.json")
    if not os.path.exists(status_path):
        return {"status": "already_stopped", "project_id": project_id, "reason": "no_status"}
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            status_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=409, detail="Generation status is unavailable") from e
    current = status_data.get("status")
    if current not in GENERATION_ACTIVE_STATUSES:
        # Idempotent: failed/cancelled/completed runs dismiss cleanly to History.
        return {
            "status": "already_stopped",
            "project_id": project_id,
            "previous_status": current,
        }

    task_id = status_data.get("task_id")
    if task_id:
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
    write_generation_status(
        proj_dir,
        "cancelled",
        int(status_data.get("progress") or 0),
        "Generation cancelled by user",
        task_id,
        message_key="status_cancelled",
    )
    await manager.send_message(json.dumps({
        "status_key": "status_cancelled",
        "progress": int(status_data.get("progress") or 0),
    }), project_id)
    return {"status": "cancelled", "project_id": project_id}


@app.post("/api/projects/{project_id}/generate/resume")
async def resume_generation(
    project_id: str,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Continue a cancelled/failed free_design run from persisted design_spec + SVGs."""
    from tasks.free_design_pipeline import can_resume_free_design

    proj_dir = owned_project_dir(project_id, auth, db)
    if is_generation_active(proj_dir):
        raise HTTPException(
            status_code=409,
            detail="This project is already generating. Wait for it to finish or cancel it first.",
        )
    eligibility = can_resume_free_design(proj_dir)
    if not eligibility.get("ok"):
        raise HTTPException(
            status_code=409,
            detail=str(eligibility.get("reason") or "This project cannot be resumed"),
        )

    write_generation_status(
        proj_dir,
        "queued",
        int(eligibility.get("progress") or 0),
        "Resume queued",
        message_key="status_resuming",
    )
    task = celery_app.send_task(
        "tasks.generate_task.resume_generation",
        args=[project_id, auth.user.id],
    )
    write_generation_status(
        proj_dir,
        "queued",
        int(eligibility.get("progress") or 0),
        "Resume queued",
        task.id,
        message_key="status_resuming",
    )
    await manager.send_message(
        json.dumps(
            {
                "status_key": "status_resuming",
                "progress": int(eligibility.get("progress") or 0),
                "missing_slides": eligibility.get("missing_slides") or [],
            }
        ),
        project_id,
    )
    return {
        "message": "Resume started",
        "task_id": task.id,
        "project_id": project_id,
        "missing_slides": eligibility.get("missing_slides") or [],
        "existing_slides": eligibility.get("existing_slides") or [],
    }


@app.get("/api/projects/{project_id}/preview")
async def get_preview(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    proj_dir = owned_project_dir(project_id, auth, db)
    rel_prefix = os.path.relpath(proj_dir, storage_path)
    deck_status = "draft"
    for status_source in (
        os.path.join(proj_dir, "validation", "release_manifest.json"),
        os.path.join(proj_dir, "status.json"),
    ):
        try:
            with open(status_source, encoding="utf-8") as handle:
                raw_status = str(json.load(handle).get("status") or "").strip()
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        if raw_status in {"released", "done"}:
            deck_status = "done"
        elif raw_status in {"released_with_advisories", "released_with_defects", "done_with_issues"}:
            deck_status = "done_with_issues"
        elif raw_status == "draft_invalid":
            deck_status = "draft_invalid"
        elif raw_status:
            deck_status = "draft"
        break
    previous_release_available = os.path.isfile(
        os.path.join(proj_dir, "validation", "previous_release_manifest.json")
    )
    slides = []
    html_dir = os.path.join(proj_dir, "html_output")
    preview_dir = os.path.join(proj_dir, "preview")
    html_files = sorted(glob.glob(os.path.join(html_dir, "slide_*.html")))
    for path in html_files:
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            version = int(os.path.getmtime(path))
        except OSError:
            version = 0
        png = os.path.join(preview_dir, f"{stem}.png")
        if os.path.isfile(png):
            try:
                version = max(version, int(os.path.getmtime(png)))
            except OSError:
                pass
            png_url = f"/api/files/{rel_prefix}/preview/{stem}.png?v={version}"
        else:
            png_url = ""
        html_url = f"/api/files/{rel_prefix}/html_output/{stem}.html?v={version}"
        slides.append({
            "filename": f"{stem}.html",
            "url": png_url or html_url,
            "html_url": html_url,
            "mtime": version,
            "mode": "html",
        })
    return {
        "slides": slides,
        "mode": "html",
        "status": deck_status,
        "previous_release_available": previous_release_available,
    }

@app.post("/api/projects/{project_id}/generate/compile")
async def compile_authored_presentation(
    project_id: str,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Compile the validated Scene-v2 HTML deck after user confirmation."""
    proj_dir = owned_project_dir(project_id, auth, db)
    status: dict = {}
    status_path = os.path.join(proj_dir, "status.json")
    if os.path.isfile(status_path):
        try:
            with open(status_path, encoding="utf-8") as handle:
                status = json.load(handle)
        except (OSError, json.JSONDecodeError):
            status = {}
    current = str(status.get("status") or "")
    if current and current not in {
        "awaiting_user_compile",
        "done",
        "done_with_issues",
        "draft",
        "draft_invalid",
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Project is not awaiting compile (status={current})",
        )
    task = celery_app.send_task(
        "tasks.generate_task.compile_generation",
        args=[project_id, auth.user.id],
    )
    return {"status": "started", "task_id": task.id}


class FixAuthoredRequest(BaseModel):
    slides: list[int] | None = None


class RegenerateSlideRequest(BaseModel):
    slide: int
    feedback: str


@app.post("/api/projects/{project_id}/generate/fix")
async def fix_authored_presentation(
    project_id: str,
    request: FixAuthoredRequest | None = None,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """User Fix: re-check failing slides against the same storyboard, then pause again."""
    owned_project_dir(project_id, auth, db)
    slides = list(request.slides) if request and request.slides else None
    task = celery_app.send_task(
        "tasks.generate_task.fix_authored_slides",
        args=[project_id, auth.user.id, slides],
    )
    return {"status": "started", "task_id": task.id, "slides": slides}


@app.post("/api/projects/{project_id}/generate/regenerate-slide")
async def regenerate_slide_with_feedback(
    project_id: str,
    request: RegenerateSlideRequest,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Deck editor: rematerialize one slide with free-text human feedback."""
    from tasks.regenerate_slide import validate_regenerate_slide_request

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        payload = validate_regenerate_slide_request(
            proj_dir,
            slide=int(request.slide),
            feedback=str(request.feedback or ""),
            generation_active=is_generation_active(proj_dir),
        )
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("bad_request:"):
            raise HTTPException(status_code=400, detail=msg.split(":", 1)[1]) from exc
        if msg.startswith("conflict:"):
            raise HTTPException(status_code=409, detail=msg.split(":", 1)[1]) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    slide_n = int(payload["slide"])
    feedback = str(payload["feedback"])
    write_generation_status(
        proj_dir,
        "queued",
        0,
        f"Regenerate slide {slide_n} queued",
        message_key="status_generating_slide",
    )
    task = celery_app.send_task(
        "tasks.generate_task.regenerate_slide_with_feedback",
        args=[project_id, auth.user.id, slide_n, feedback],
    )
    write_generation_status(
        proj_dir,
        "queued",
        0,
        f"Regenerate slide {slide_n} queued",
        task.id,
        message_key="status_generating_slide",
    )
    return {
        "status": "started",
        "task_id": task.id,
        "slide": slide_n,
        "ok": True,
    }


@app.get("/api/projects/{project_id}/generate/regenerate-slide/result")
async def regenerate_slide_result(
    project_id: str,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Latest regenerate-slide result artifact (for deck-editor polling)."""
    proj_dir = owned_project_dir(project_id, auth, db)
    path = os.path.join(proj_dir, "validation", "regenerate_slide_result.json")
    if not os.path.isfile(path):
        return {"ok": False, "pending": True}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "pending": True}
    return data if isinstance(data, dict) else {"ok": False, "pending": True}


@app.get("/api/projects/{project_id}/grounding-status")
async def get_grounding_status(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Return source, coverage, citation, and grounding-QA metadata for the UI."""
    from tasks.grounding_status import build_grounding_status

    project_dir = owned_project_dir(project_id, auth, db)
    return build_grounding_status(project_dir, storage_path)

from pydantic import BaseModel
class UpdateSvgRequest(BaseModel):
    filename: str
    svg_content: str


class EditElementRequest(BaseModel):
    filename: str
    element_id: str
    instruction: str
    text: str


@app.post("/api/projects/{project_id}/edit_element")
async def edit_element(project_id: str, request: EditElementRequest, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Selection-scoped AI rewrite for one text element (does not mutate SVG)."""
    from tasks.deck_editor import edit_element_text

    proj_dir = owned_project_dir(project_id, auth, db)
    grounding_mode = "scratch"
    try:
        manifest_path = os.path.join(proj_dir, "validation", "run_manifest.json")
        if os.path.isfile(manifest_path):
            with open(manifest_path, encoding="utf-8") as handle:
                grounding_mode = str(json.load(handle).get("grounding_mode") or "scratch")
    except Exception:
        grounding_mode = "scratch"
    try:
        result = edit_element_text(
            text=request.text,
            instruction=request.instruction,
            grounding_mode=grounding_mode,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "status": "ok",
        "filename": request.filename,
        "element_id": request.element_id,
        "text": result.get("text") or request.text,
        "source": result.get("source"),
    }


@app.post("/api/projects/{project_id}/update_svg")
async def update_svg(project_id: str, request: UpdateSvgRequest, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Retired: freehand SVG editor writes are gone (zero-SVG cutover)."""
    del project_id, request, auth, db
    raise HTTPException(
        status_code=410,
        detail="update_svg retired; HTML is source of truth (HtmlEditorShell)",
    )


class UpdateHtmlRequest(BaseModel):
    filename: str
    html_content: str
    refresh_preview: bool = True


@app.post("/api/projects/{project_id}/update_html")
async def update_html(
    project_id: str,
    request: UpdateHtmlRequest,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Persist free-form HTML slide edits to html_output/."""
    from tasks.deck_editor import save_slide_html

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        result = save_slide_html(
            proj_dir,
            request.filename,
            request.html_content,
            refresh_preview=bool(request.refresh_preview),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Save failed: {error}") from error
    hard_count = len((result.get("layout_qa") or {}).get("hard") or [])
    # Editing and releasing have different contracts. A free-form edit is a
    # valid draft even when export QA finds overflow; the unified export
    # transaction owns validation/remediation when the user downloads.
    write_generation_status(
        proj_dir,
        "draft",
        100,
        "Slide HTML updated in editor"
        + (f"; {hard_count} export layout advisory(s) recorded" if hard_count else ""),
        message_key="status_draft",
    )
    return result


class ReorderSlidesRequest(BaseModel):
    filenames: List[str]


@app.post("/api/projects/{project_id}/rebuild")
async def rebuild_project(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Recompile edited Scene-v2 HTML into a downloadable PPTX release."""
    from tasks.deck_editor import rebuild_pptx

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        result = rebuild_pptx(proj_dir, project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        write_generation_status(
            proj_dir,
            "draft_invalid",
            0,
            str(e),
            message_key="status_svg_revalidate",
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {e}") from e

    write_generation_status(
        proj_dir,
        result["status"],
        100,
        "Presentation rebuilt from editor",
        message_key=(
            "status_done_with_issues" if result["status"] == "done_with_issues" else "status_done"
        ),
    )
    return result


@contextmanager
def _project_export_lock(proj_dir: str):
    """Serialize flush/validate/rebuild/publish for a project across API workers."""
    lock_path = Path(proj_dir) / "validation" / ".export.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@app.post("/api/projects/{project_id}/export/{export_format}")
async def export_project_transaction(
    project_id: str,
    export_format: str,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Validate, rebuild, atomically publish, and return one current export."""
    from tasks.deck_editor import rebuild_pptx
    from tasks.release_export import (
        ReleaseExportError,
        ensure_release_notes_pdf,
        ensure_release_pdf,
        resolve_previous_released_pptx,
        resolve_released_pptx,
    )

    if export_format not in {"pptx", "pdf", "notes-pdf"}:
        raise HTTPException(status_code=404, detail="Unsupported export format")
    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        with _project_export_lock(proj_dir):
            rebuild_result = rebuild_pptx(proj_dir, project_id)
            pptx_path, pptx_sha, _manifest = resolve_released_pptx(proj_dir)
            if export_format == "pptx":
                path = pptx_path
                filename = f"{project_id}.pptx"
                media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            elif export_format == "pdf":
                path = ensure_release_pdf(pptx_path, pptx_sha, proj_dir=proj_dir)
                filename = f"{project_id}.pdf"
                media_type = "application/pdf"
            else:
                path = ensure_release_notes_pdf(pptx_path, pptx_sha, proj_dir=proj_dir)
                filename = f"{project_id}-notes.pdf"
                media_type = "application/pdf"
    except Exception as error:  # the old immutable release is never republished as current
        previous_available = False
        try:
            resolve_previous_released_pptx(proj_dir)
            previous_available = True
        except ReleaseExportError:
            pass
        write_generation_status(
            proj_dir,
            "draft_invalid",
            0,
            str(error),
            message_key="status_svg_revalidate",
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Export rebuild failed: {error}",
                "previous_release_available": previous_available,
                "previous_release_url": (
                    f"/api/download/{project_id}.previous.pptx"
                    if previous_available
                    else None
                ),
            },
        ) from error

    write_generation_status(
        proj_dir,
        (
            "done_with_issues"
            if rebuild_result.get("status") in {"released_with_advisories", "released_with_defects"}
            else "done"
        ),
        100,
        "Presentation rebuilt and atomically published",
        message_key=(
            "status_done_with_issues"
            if rebuild_result.get("status") in {"released_with_advisories", "released_with_defects"}
            else "status_done"
        ),
    )
    return FileResponse(path=path, filename=filename, media_type=media_type)


@app.post("/api/projects/{project_id}/slides/reorder")
async def reorder_project_slides(
    project_id: str, request: ReorderSlidesRequest, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)
):
    from tasks.deck_editor import reorder_slides

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        names = reorder_slides(proj_dir, request.filenames)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reorder failed: {e}") from e
    write_generation_status(
        proj_dir,
        "draft",
        0,
        "Slides reordered; export is required",
        message_key="status_svg_export",
    )
    return {"filenames": names, "status": "draft"}


@app.post("/api/projects/{project_id}/slides/{filename}/duplicate")
async def duplicate_project_slide(project_id: str, filename: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    from tasks.deck_editor import duplicate_slide

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        names = duplicate_slide(proj_dir, filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duplicate failed: {e}") from e
    write_generation_status(
        proj_dir, "draft", 0, "Slide duplicated; export is required", message_key="status_svg_export"
    )
    return {"filenames": names, "status": "draft"}


@app.delete("/api/projects/{project_id}/slides/{filename}")
async def delete_project_slide(project_id: str, filename: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    from tasks.deck_editor import delete_slide

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        names = delete_slide(proj_dir, filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}") from e
    write_generation_status(
        proj_dir, "draft", 0, "Slide deleted; export is required", message_key="status_svg_export"
    )
    return {"filenames": names, "status": "draft"}


class NotesFitRequest(BaseModel):
    target_duration_minutes: float | None = None
    wpm: int | None = 125
    preserve_facts: bool = True
    mode: str = "auto"  # auto | compress | regenerate
    backup: bool = True


class NotesUpdateRequest(BaseModel):
    text: str


@app.get("/api/projects/{project_id}/production-settings")
async def get_production_settings(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Return persisted Production Settings for Stage-3 hydration."""
    confirm_dir = get_confirm_dir(project_id, db, auth)
    result_path = os.path.join(confirm_dir, "result.json")
    data: dict = {}
    if os.path.isfile(result_path):
        try:
            with open(result_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}

    def unwrap(value, default=None):
        if isinstance(value, dict) and "value" in value:
            return value.get("value", default)
        return default if value is None else value

    from tasks.slide_transitions import catalog_payload

    effect = unwrap(data.get("custom_animation_effect"), None)
    return {
        "proactive_speaker_notes": bool(unwrap(data.get("proactive_speaker_notes"), True)),
        "target_duration_minutes": float(unwrap(data.get("target_duration_minutes"), 15) or 15),
        "notes_wpm": int(unwrap(data.get("notes_wpm"), 125) or 125),
        "proactive_custom_animations": bool(unwrap(data.get("proactive_custom_animations"), False)),
        "custom_animation_effect": str(effect).strip() if effect else None,
        "slide_transitions": catalog_payload(),
        "proactive_narration_audio": bool(unwrap(data.get("proactive_narration_audio"), False)),
        "image_source": str(unwrap(data.get("image_source"), "both") or "both"),
        "selected_figure_ids": list(data.get("selected_figure_ids") or []),
        "selected_table_ids": list(data.get("selected_table_ids") or []),
        "figure_render_mode": str(data.get("figure_render_mode") or "exact"),
        "table_render_mode": str(data.get("table_render_mode") or "exact"),
    }


@app.get("/api/projects/{project_id}/notes/timing")
async def get_notes_timing(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    from tasks.speaker_notes import load_timing

    proj_dir = owned_project_dir(project_id, auth, db)
    return load_timing(proj_dir)


@app.post("/api/projects/{project_id}/notes/fit-duration")
async def fit_notes_duration(
    project_id: str,
    request: NotesFitRequest,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    from tasks.speaker_notes import fit_notes_to_duration

    proj_dir = owned_project_dir(project_id, auth, db)
    mode = (request.mode or "auto").strip().lower()
    if mode not in {"auto", "compress", "regenerate"}:
        raise HTTPException(status_code=400, detail="mode must be auto, compress, or regenerate")
    try:
        report = fit_notes_to_duration(
            proj_dir,
            target_duration_minutes=request.target_duration_minutes,
            wpm=request.wpm,
            preserve_facts=bool(request.preserve_facts),
            mode=mode,
            backup=bool(request.backup),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fit notes failed: {e}") from e
    return report


@app.post("/api/projects/{project_id}/notes/undo-fit")
async def undo_notes_fit(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    from tasks.speaker_notes import load_timing, restore_notes_backup

    proj_dir = owned_project_dir(project_id, auth, db)
    if not restore_notes_backup(proj_dir):
        raise HTTPException(status_code=404, detail="No notes backup to restore")
    return {"status": "restored", "timing": load_timing(proj_dir)}


@app.get("/api/projects/{project_id}/notes/{filename}")
async def get_slide_notes(project_id: str, filename: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    from tasks.slide_artifacts import list_slide_artifacts
    from tasks.speaker_notes import notes_path_for_svg, read_note

    proj_dir = Path(owned_project_dir(project_id, auth, db))
    stem = filename.replace(".svg", "").replace(".md", "").replace(".html", "").replace(".json", "").replace(".png", "")
    if not re.fullmatch(r"slide_\d+", stem):
        raise HTTPException(status_code=400, detail="Invalid notes filename")
    # Prefer shared artifact discovery; notes keyed by stem, not by .svg on disk.
    artifact = next(
        (p for p in list_slide_artifacts(proj_dir) if p.stem == stem),
        proj_dir / "notes" / f"{stem}.md",
    )
    path = notes_path_for_svg(proj_dir, artifact)
    text = read_note(path)
    return {"filename": f"{stem}.md", "text": text, "word_count": len(text.split())}


@app.put("/api/projects/{project_id}/notes/{filename}")
async def put_slide_notes(
    project_id: str,
    filename: str,
    request: NotesUpdateRequest,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    from tasks.slide_artifacts import list_slide_artifacts
    from tasks.speaker_notes import compute_timing_from_disk, notes_path_for_svg, write_note

    proj_dir = Path(owned_project_dir(project_id, auth, db))
    stem = filename.replace(".svg", "").replace(".md", "").replace(".html", "").replace(".json", "").replace(".png", "")
    if not re.fullmatch(r"slide_\d+", stem):
        raise HTTPException(status_code=400, detail="Invalid notes filename")
    artifact = next(
        (p for p in list_slide_artifacts(proj_dir) if p.stem == stem),
        proj_dir / "notes" / f"{stem}.md",
    )
    path = notes_path_for_svg(proj_dir, artifact)
    write_note(path, request.text or "")
    timing = compute_timing_from_disk(proj_dir)
    timing_path = proj_dir / "notes" / "timing.json"
    timing_path.parent.mkdir(parents=True, exist_ok=True)
    timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"filename": f"{stem}.md", "text": request.text or "", "timing": timing}


@app.post("/api/projects/{project_id}/images")
async def upload_project_image(
    project_id: str,
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    from tasks.deck_editor import save_uploaded_image

    proj_dir = owned_project_dir(project_id, auth, db)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    try:
        saved = save_uploaded_image(proj_dir, file.filename or "upload.png", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}") from e
    rel_prefix = os.path.relpath(proj_dir, storage_path)
    return {
        "filename": saved["filename"],
        "path": saved["relative_path"],
        "url": f"/api/files/{rel_prefix}/images/{saved['filename']}",
    }


class GenerateProjectImageRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "16:9"
    slide: int | None = None


@app.post("/api/projects/{project_id}/images/generate")
async def generate_project_image(
    project_id: str,
    request: GenerateProjectImageRequest,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Generate a figure with Settings → Image engine and store under images/."""
    from tasks.deck_editor import generate_ai_image_for_editor

    proj = get_owned_project(project_id, auth, db)
    proj_dir = owned_project_dir(project_id, auth, db)
    user_id = proj.user_id
    prompt = request.prompt
    aspect_ratio = request.aspect_ratio or "16:9"
    slide = request.slide
    try:
        # Provider calls are sync + long; keep the event loop free for health/proxy.
        saved = await asyncio.to_thread(
            generate_ai_image_for_editor,
            proj_dir,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            user_id=user_id,
            slide=slide,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:
        detail = str(e)
        status = 422 if "Settings → Image engine" in detail else 502
        raise HTTPException(status_code=status, detail=detail) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image generation failed: {e}") from e
    rel_prefix = os.path.relpath(proj_dir, storage_path)
    return {
        "filename": saved["filename"],
        "path": saved["relative_path"],
        "url": f"/api/files/{rel_prefix}/images/{saved['filename']}",
    }


@app.get("/api/download/{project_id}.pptx")
async def download_pptx(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    from tasks.release_export import ReleaseExportError, resolve_released_pptx
    from tasks.deck_editor import rebuild_pptx

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        with _project_export_lock(proj_dir):
            rebuild_pptx(proj_dir, project_id)
            latest_file, _sha, _manifest = resolve_released_pptx(proj_dir)
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Export rebuild failed: {e}") from e
    return FileResponse(
        path=latest_file,
        filename=f"{project_id}.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


@app.get("/api/download/{project_id}.previous.pptx")
async def download_previous_pptx(
    project_id: str,
    auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db),
):
    """Download the last immutable release when current edits cannot rebuild."""
    from tasks.release_export import ReleaseExportError, resolve_previous_released_pptx

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        previous_file, _sha, _manifest = resolve_previous_released_pptx(proj_dir)
    except ReleaseExportError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FileResponse(
        path=previous_file,
        filename=f"{project_id}-previous.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.get("/api/download/{project_id}.pdf")
async def download_pdf(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Export a downloadable PDF from editor preview PNGs (Impress fallback)."""
    from tasks.release_export import ReleaseExportError, ensure_release_pdf, resolve_released_pptx
    from tasks.deck_editor import rebuild_pptx

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        with _project_export_lock(proj_dir):
            rebuild_pptx(proj_dir, project_id)
            pptx_path, pptx_sha, _manifest = resolve_released_pptx(proj_dir)
            pdf_path = ensure_release_pdf(pptx_path, pptx_sha, proj_dir=proj_dir)
    except ReleaseExportError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {e}") from e
    return FileResponse(
        path=pdf_path,
        filename=f"{project_id}.pdf",
        media_type="application/pdf",
    )


@app.get("/api/download/{project_id}.notes.pdf")
async def download_notes_pdf(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Export the released slides with their matching speaker notes."""
    from tasks.release_export import (
        ReleaseExportError,
        ensure_release_notes_pdf,
        resolve_released_pptx,
    )
    from tasks.deck_editor import rebuild_pptx

    proj_dir = owned_project_dir(project_id, auth, db)
    try:
        with _project_export_lock(proj_dir):
            rebuild_pptx(proj_dir, project_id)
            pptx_path, pptx_sha, _manifest = resolve_released_pptx(proj_dir)
            pdf_path = ensure_release_notes_pdf(pptx_path, pptx_sha, proj_dir=proj_dir)
    except ReleaseExportError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Notes PDF export failed: {error}") from error
    return FileResponse(
        path=pdf_path,
        filename=f"{project_id}-notes.pdf",
        media_type="application/pdf",
    )


@app.get("/api/download/{project_id}.html.zip")
async def download_html_player(project_id: str, auth: AuthContext = Depends(require_approved),
    db: Session = Depends(get_db)):
    """Export html_output slides as a Deckflow-style HTML player zip (index.html)."""
    from fastapi.responses import Response

    from tasks.html_player_export import HtmlPlayerExportError, build_html_player_zip

    proj = get_owned_project(project_id, auth, db)
    proj_dir = get_project_dir(project_id, db, user_id=proj.user_id)
    try:
        zip_bytes, filename = build_html_player_zip(
            proj_dir, title=getattr(proj, "topic", None), project_id=project_id
        )
    except HtmlPlayerExportError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HTML export failed: {e}") from e
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )

@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    sid = websocket.cookies.get(COOKIE_NAME)
    db = SessionLocal()
    try:
        if not sid:
            await websocket.close(code=4401)
            return
        try:
            record = session_store.get(sid)
        except SessionStoreUnavailable:
            await websocket.close(code=1013)
            return
        if not record:
            await websocket.close(code=4401)
            return
        user = db.query(models.User).filter(models.User.id == record.get("user_id")).first()
        allowed = bool(user) and (
            (user.role == "admin" and user.status == "approved")
            or user.status == "approved"
        )
        if not allowed:
            await websocket.close(code=4403)
            return
        proj = db.query(models.Project).filter(models.Project.project_id == project_id).first()
        if not proj or (proj.user_id != user.id and user.role != "admin"):
            await websocket.close(code=4403)
            return
        try:
            session_store.touch(sid, record)
        except SessionStoreUnavailable:
            pass
    finally:
        db.close()

    await manager.connect(websocket, project_id)
    
    import redis.asyncio as aioredis
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    redis_client = await aioredis.from_url(redis_url)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"project_{project_id}")
    
    async def redis_listener():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"].decode("utf-8")
                    await manager.send_message(data, project_id)
        except Exception as e:
            print(f"Redis listener error: {e}")

    listener_task = asyncio.create_task(redis_listener())

    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(project_id)
        listener_task.cancel()
        await pubsub.unsubscribe(f"project_{project_id}")
        await redis_client.close()
