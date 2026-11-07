"""Password hashing, session tokens, authorization, and model-input minimization."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from aegisops.core.exceptions import ForbiddenError, UnauthorizedError

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DUMMY_HASH = ""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64encode(salt)}${_b64encode(digest)}"


def _ensure_dummy() -> str:
    global _DUMMY_HASH
    if not _DUMMY_HASH:
        _DUMMY_HASH = hash_password("not-a-real-password")
    return _DUMMY_HASH


def verify_password(password: str, encoded: str | None) -> bool:
    candidate = encoded or _ensure_dummy()
    try:
        algorithm, n_s, r_s, p_s, salt_s, digest_s = candidate.split("$")
        if algorithm != "scrypt":
            return False
        salt = _b64decode(salt_s)
        expected = _b64decode(digest_s)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(expected),
        )
        matched = hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
    if not encoded:
        return False
    return matched


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session_token(
    *,
    secret: str,
    user_id: str,
    tenant_id: str,
    session_id: str,
    ttl_seconds: int,
) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    payload = {
        "uid": user_id,
        "tid": tenant_id,
        "sid": session_id,
        "exp": int(expires_at.timestamp()),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}", expires_at


def read_session_token(token: str, secret: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(signature), expected):
            raise UnauthorizedError("Invalid session")
        payload = json.loads(_b64decode(body))
        if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            raise UnauthorizedError("Session expired")
        return payload
    except UnauthorizedError:
        raise
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise UnauthorizedError("Invalid session") from exc


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "sre": {
        "incident:read",
        "incident:investigate",
        "workflow:read",
        "workflow:cancel",
        "approval:read",
        "approval:decide",
        "runbook:read",
        "integration:read",
        "audit:read",
        "capacity:read",
        "agent:read",
        "control:read",
    },
    "approver": {"incident:read", "workflow:read", "approval:read", "approval:decide", "audit:read", "agent:read"},
    "dba": {
        "incident:read",
        "workflow:read",
        "approval:read",
        "approval:decide",
        "capacity:read",
        "audit:read",
        "agent:read",
    },
    "operator": {
        "incident:read",
        "workflow:read",
        "workflow:cancel",
        "approval:read",
        "runbook:read",
        "integration:read",
        "capacity:read",
        "agent:read",
        "audit:read",
        "control:read",
    },
    "observer": {
        "incident:read",
        "workflow:read",
        "approval:read",
        "runbook:read",
        "integration:read",
        "capacity:read",
        "agent:read",
    },
    "auditor": {"incident:read", "workflow:read", "approval:read", "audit:read", "agent:read", "control:read"},
}

DEFAULT_ROLES = tuple(ROLE_PERMISSIONS)


def permissions_for(roles: set[str]) -> set[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, set())
    return granted


def authorize(roles: set[str], permission: str) -> None:
    granted = permissions_for(roles)
    if "*" in granted or permission in granted:
        return
    raise ForbiddenError(f"Missing permission {permission}", {"permission": permission})


def minimize_for_model(payload: dict, allowed_fields: set[str]) -> dict:
    """Drop every field the model is not explicitly allowed to see."""
    return {key: payload[key] for key in allowed_fields if key in payload}


def redact_mapping(payload: dict) -> dict:
    hidden = {"password", "secret", "token", "api_key", "access_token", "client_secret", "authorization"}
    cleaned: dict = {}
    for key, value in payload.items():
        if key.lower() in hidden or key.lower().endswith("_token") or key.lower().endswith("_secret"):
            cleaned[key] = "[redacted]"
        elif isinstance(value, dict):
            cleaned[key] = redact_mapping(value)
        else:
            cleaned[key] = value
    return cleaned
