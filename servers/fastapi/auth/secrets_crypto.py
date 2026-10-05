from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:v1:"


def _fernet() -> Fernet | None:
    raw = (os.environ.get("SETTINGS_SECRET_KEY") or "").strip()
    if not raw:
        return None
    # Accept either a Fernet key or any passphrase (derived).
    try:
        if raw.startswith("fernet:"):
            return Fernet(raw.removeprefix("fernet:").encode("utf-8"))
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    except Exception:
        return None


def encrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith(_PREFIX):
        return value
    f = _fernet()
    if f is None:
        return value
    token = f.encrypt(value.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value
    f = _fernet()
    if f is None:
        return ""
    try:
        return f.decrypt(value.removeprefix(_PREFIX).encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception):
        return ""


def ensure_encrypted(value: str | None) -> str:
    """Re-encrypt plaintext legacy values; leave ciphertext alone."""
    if not value:
        return ""
    if value.startswith(_PREFIX):
        return value
    return encrypt_secret(value)
