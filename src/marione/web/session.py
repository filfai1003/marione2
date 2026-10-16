"""Signed-cookie sessions (stdlib only). The cookie holds only the visitor's Discord user id and a
short-lived OAuth `state`; the HMAC signature makes it tamper-proof. No password and no Discord
token is ever stored."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

COOKIE_NAME = "marione_session"
MAX_AGE_SECONDS = 30 * 24 * 3600


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sig(raw: bytes, secret: str) -> str:
    return _b64e(hmac.new(secret.encode(), raw, hashlib.sha256).digest())


def dumps(data: dict[str, Any], secret: str, *, now: float | None = None) -> str:
    payload = dict(data)
    payload["exp"] = int((time.time() if now is None else now) + MAX_AGE_SECONDS)
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return _b64e(raw) + "." + _sig(raw, secret)


def loads(token: str, secret: str, *, now: float | None = None) -> dict[str, Any]:
    """The session dict, or {} for anything missing, forged, malformed or expired."""
    if not secret or not token:
        return {}
    try:
        body, sig = token.split(".", 1)
        raw = _b64d(body)
        if not hmac.compare_digest(sig, _sig(raw, secret)):
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        if float(data.get("exp", 0)) < (time.time() if now is None else now):
            return {}
        return data
    except (ValueError, TypeError):
        return {}
