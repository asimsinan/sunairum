from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any

import redis

COOKIE_NAME = "sunairum_session"
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "sunairum"


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://redis:6379/0")


def idle_minutes() -> int:
    return max(1, int(os.environ.get("SESSION_IDLE_MINUTES", "30")))


def absolute_hours() -> int:
    return max(1, int(os.environ.get("SESSION_ABSOLUTE_HOURS", "12")))


def cookie_secure() -> bool:
    return os.environ.get("SESSION_COOKIE_SECURE", "").strip() in {"1", "true", "True", "yes"}


def login_max_failures() -> int:
    return max(3, int(os.environ.get("LOGIN_MAX_FAILURES", "8")))


def login_lockout_minutes() -> int:
    return max(1, int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15")))


class SessionStore:
    def __init__(self, client: redis.Redis | None = None):
        self._client = client

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis.from_url(_redis_url(), decode_responses=True)
        return self._client

    def _session_key(self, sid: str) -> str:
        return f"session:{sid}"

    def _user_set_key(self, user_id: str) -> str:
        return f"user_sessions:{user_id}"

    def create(
        self,
        *,
        user_id: str,
        role: str,
        status: str,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        now = int(time.time())
        sid = secrets.token_urlsafe(32)
        idle_exp = now + idle_minutes() * 60
        abs_exp = now + absolute_hours() * 3600
        record = {
            "user_id": user_id,
            "role": role,
            "status": status,
            "created_at": now,
            "last_seen_at": now,
            "absolute_expires_at": abs_exp,
            "idle_expires_at": idle_exp,
            "user_agent_hash": (user_agent or "")[:200],
            "ip": (ip or "")[:64],
        }
        ttl = max(1, min(idle_exp, abs_exp) - now)
        pipe = self.client.pipeline()
        pipe.set(self._session_key(sid), json.dumps(record), ex=ttl)
        pipe.sadd(self._user_set_key(user_id), sid)
        pipe.execute()
        return sid, record

    def get(self, sid: str) -> dict[str, Any] | None:
        if not sid:
            return None
        try:
            raw = self.client.get(self._session_key(sid))
        except redis.RedisError as exc:
            raise SessionStoreUnavailable(str(exc)) from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def touch(self, sid: str, record: dict[str, Any]) -> dict[str, Any] | None:
        now = int(time.time())
        abs_exp = int(record["absolute_expires_at"])
        if now >= abs_exp:
            self.destroy(sid, record.get("user_id"))
            return None
        idle_exp = now + idle_minutes() * 60
        if idle_exp > abs_exp:
            idle_exp = abs_exp
        if now >= int(record.get("idle_expires_at", 0)):
            self.destroy(sid, record.get("user_id"))
            return None
        record = {
            **record,
            "last_seen_at": now,
            "idle_expires_at": idle_exp,
        }
        ttl = max(1, min(idle_exp, abs_exp) - now)
        try:
            self.client.set(self._session_key(sid), json.dumps(record), ex=ttl)
        except redis.RedisError as exc:
            raise SessionStoreUnavailable(str(exc)) from exc
        return record

    def destroy(self, sid: str, user_id: str | None = None) -> None:
        if not sid:
            return
        try:
            if user_id is None:
                existing = self.get(sid)
                user_id = existing.get("user_id") if existing else None
            pipe = self.client.pipeline()
            pipe.delete(self._session_key(sid))
            if user_id:
                pipe.srem(self._user_set_key(user_id), sid)
            pipe.execute()
        except redis.RedisError:
            pass

    def revoke_all(self, user_id: str) -> int:
        try:
            sids = list(self.client.smembers(self._user_set_key(user_id)) or [])
            if not sids:
                self.client.delete(self._user_set_key(user_id))
                return 0
            pipe = self.client.pipeline()
            for sid in sids:
                pipe.delete(self._session_key(sid))
            pipe.delete(self._user_set_key(user_id))
            pipe.execute()
            return len(sids)
        except redis.RedisError as exc:
            raise SessionStoreUnavailable(str(exc)) from exc

    def active_count(self, user_id: str) -> int:
        try:
            return int(self.client.scard(self._user_set_key(user_id)) or 0)
        except redis.RedisError:
            return 0

    def rate_limit_hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Return True if over limit (should reject)."""
        try:
            full = f"rl:{key}"
            count = self.client.incr(full)
            if count == 1:
                self.client.expire(full, window_seconds)
            return count > limit
        except redis.RedisError as exc:
            raise SessionStoreUnavailable(str(exc)) from exc


class SessionStoreUnavailable(RuntimeError):
    pass


session_store = SessionStore()
