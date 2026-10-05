from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from auth.sessions import COOKIE_NAME, CSRF_HEADER, CSRF_VALUE

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CsrfHeaderMiddleware(BaseHTTPMiddleware):
    """Require X-Requested-With on cookie-authenticated mutating requests."""

    async def dispatch(self, request: Request, call_next):
        if request.method in SAFE_METHODS:
            return await call_next(request)
        path = request.url.path or ""
        # Health never needs CSRF.
        if path == "/health":
            return await call_next(request)
        has_session = bool(request.cookies.get(COOKIE_NAME))
        if not has_session:
            return await call_next(request)
        header = request.headers.get(CSRF_HEADER, "")
        if header != CSRF_VALUE:
            return JSONResponse(
                status_code=403,
                content={"detail": {"code": "csrf_failed", "message": "Missing CSRF header"}},
            )
        return await call_next(request)
