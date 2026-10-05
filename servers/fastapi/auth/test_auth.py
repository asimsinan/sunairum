"""Auth core + isolation tests (SQLite + fakeredis-like in-memory redis optional)."""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

# Use sqlite for unit tests before importing app modules that bind the engine.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault("SETTINGS_SECRET_KEY", "test-settings-secret-key-32bytes!!")
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")
os.environ.setdefault("ADMIN_EMAIL", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin")


@pytest.fixture(scope="module")
def client():
    redis = pytest.importorskip("redis")
    try:
        r = redis.Redis.from_url(os.environ["REDIS_URL"])
        r.ping()
    except Exception:
        pytest.skip("Redis not available for auth tests")

    from database import Base, engine, ensure_schema
    from auth.bootstrap import seed_admin_if_needed
    import main as main_mod

    Base.metadata.drop_all(bind=engine)
    ensure_schema(engine)
    seed_admin_if_needed()
    with TestClient(main_mod.app) as c:
        yield c


def _csrf():
    return {"X-Requested-With": "sunairum"}


def test_login_default_admin(client: TestClient):
    res = client.post("/api/auth/login", json={"email": "admin", "password": "admin"}, headers=_csrf())
    assert res.status_code == 200, res.text
    assert res.json()["user"]["role"] == "admin"
    assert "sunairum_session" in res.cookies
    cookie = res.cookies.get("sunairum_session")
    # HttpOnly is set via Set-Cookie header
    cookie_header = (res.headers.get("set-cookie") or "").lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header


def test_settings_masks_api_key(client: TestClient):
    login = client.post("/api/auth/login", json={"email": "admin", "password": "admin"}, headers=_csrf())
    assert login.status_code == 200
    save = client.post(
        "/api/settings",
        json={
            "provider": "openai_compatible",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-test-secret-key-1234",
            "model_name": "openai/gpt-4o",
        },
        headers=_csrf(),
    )
    assert save.status_code == 200
    got = client.get("/api/settings")
    assert got.status_code == 200
    body = got.json()
    assert body["api_key_set"] is True
    assert "sk-test-secret" not in body["api_key"]
    assert body["api_key"].startswith("********")


def test_signup_pending_blocked_from_settings(client: TestClient):
    from database import SessionLocal
    import models
    from auth.passwords import hash_password
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    db = SessionLocal()
    try:
        db.add(
            models.User(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=hash_password("password123"),
                display_name="U",
                role="user",
                status="pending",
                created_at=int(time.time()),
            )
        )
        db.commit()
    finally:
        db.close()
    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
        headers=_csrf(),
    )
    assert login.status_code == 200
    assert login.json()["user"]["status"] == "pending"
    blocked = client.get("/api/settings")
    assert blocked.status_code == 403


def test_project_idor(client: TestClient):
    from database import SessionLocal
    import models
    from auth.passwords import hash_password
    import uuid

    admin_login = client.post("/api/auth/login", json={"email": "admin", "password": "admin"}, headers=_csrf())
    assert admin_login.status_code == 200
    admin_id = admin_login.json()["user"]["id"]

    email = f"other_{uuid.uuid4().hex[:8]}@example.com"
    other_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        pid = f"proj_idor_{uuid.uuid4().hex[:8]}"
        db.add(
            models.Project(
                project_id=pid,
                user_id=admin_id,
                topic="secret",
                status="created",
                created_at=int(time.time()),
            )
        )
        db.add(
            models.User(
                id=other_id,
                email=email,
                password_hash=hash_password("password123"),
                display_name="Other",
                role="user",
                status="approved",
                created_at=int(time.time()),
                approved_at=int(time.time()),
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/auth/login", json={"email": email, "password": "password123"}, headers=_csrf())
    denied = client.get(f"/api/projects/{pid}/preview")
    assert denied.status_code in {403, 404}


def test_csrf_required_when_session_present(client: TestClient):
    login = client.post("/api/auth/login", json={"email": "admin", "password": "admin"}, headers=_csrf())
    assert login.status_code == 200
    res = client.post("/api/auth/logout")  # missing CSRF header
    assert res.status_code == 403


def test_revoke_on_disable(client: TestClient):
    from database import SessionLocal
    import models
    from auth.passwords import hash_password
    import uuid

    email = f"dis_{uuid.uuid4().hex[:8]}@example.com"
    target_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        db.add(
            models.User(
                id=target_id,
                email=email,
                password_hash=hash_password("password123"),
                display_name="Dis",
                role="user",
                status="approved",
                created_at=int(time.time()),
                approved_at=int(time.time()),
            )
        )
        db.commit()
    finally:
        db.close()

    user_client = TestClient(client.app)
    login = user_client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
        headers=_csrf(),
    )
    assert login.status_code == 200
    me = user_client.get("/api/auth/me")
    assert me.status_code == 200

    admin = client.post("/api/auth/login", json={"email": "admin", "password": "admin"}, headers=_csrf())
    assert admin.status_code == 200
    disabled = client.post(f"/api/admin/users/{target_id}/disable", headers=_csrf())
    assert disabled.status_code == 200
    me2 = user_client.get("/api/auth/me")
    assert me2.status_code == 401


def test_admin_users_omit_api_keys(client: TestClient):
    client.post("/api/auth/login", json={"email": "admin", "password": "admin"}, headers=_csrf())
    users = client.get("/api/admin/users").json()["users"]
    for u in users:
        assert "api_key" not in u
        assert "vision_api_key" not in u


def test_admin_delete_user(client: TestClient):
    import uuid

    import models
    from database import SessionLocal

    email = f"del_{uuid.uuid4().hex[:8]}@example.com"
    target_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        db.add(
            models.User(
                id=target_id,
                email=email,
                password_hash="x",
                display_name="to-delete",
                role="user",
                status="approved",
                created_at=int(time.time()),
                approved_at=int(time.time()),
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/auth/login", json={"email": "admin", "password": "admin"}, headers=_csrf())
    res = client.delete(f"/api/admin/users/{target_id}", headers=_csrf())
    assert res.status_code == 200, res.text
    users = client.get("/api/admin/users").json()["users"]
    assert all(u["id"] != target_id for u in users)


def test_admin_delete_all_keeps_self(client: TestClient):
    import uuid

    import models
    from database import SessionLocal

    db = SessionLocal()
    try:
        for _ in range(2):
            db.add(
                models.User(
                    id=str(uuid.uuid4()),
                    email=f"bulk_{uuid.uuid4().hex[:8]}@example.com",
                    password_hash="x",
                    display_name="bulk",
                    role="user",
                    status="pending",
                    created_at=int(time.time()),
                )
            )
        db.commit()
    finally:
        db.close()

    login = client.post("/api/auth/login", json={"email": "admin", "password": "admin"}, headers=_csrf())
    admin_id = login.json()["user"]["id"]
    bad = client.request(
        "DELETE",
        "/api/admin/users",
        headers={**_csrf(), "Content-Type": "application/json"},
        json={"confirm": "nope"},
    )
    assert bad.status_code == 400
    res = client.request(
        "DELETE",
        "/api/admin/users",
        headers={**_csrf(), "Content-Type": "application/json"},
        json={"confirm": "DELETE_ALL"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] >= 2
    users = client.get("/api/admin/users").json()["users"]
    assert len(users) == 1
    assert users[0]["id"] == admin_id


def test_signup_disabled_when_flag_off(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SIGNUP_ENABLED", "0")
    res = client.post(
        "/api/auth/signup",
        json={"email": "closed@example.com", "password": "password123", "display_name": "Closed"},
        headers=_csrf(),
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "signup_disabled"


def test_signup_enabled_by_default_creates_pending(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import uuid

    monkeypatch.delenv("SIGNUP_ENABLED", raising=False)
    email = f"open_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "display_name": "Open"},
        headers=_csrf(),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "pending"
