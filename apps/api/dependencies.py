"""API dependencies. Database sessions commit on success and roll back on failure."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.core.exceptions import ForbiddenError, UnauthorizedError
from aegisops.core.security import authorize, hash_token, read_session_token
from aegisops.persistence.repositories.identity import IdentityRepository

SESSION_COOKIE = "aegisops_session"


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    session_id: str
    roles: frozenset[str]
    csrf_hash: str


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.sessions()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _token_from_request(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if cookie:
        return cookie
    raise UnauthorizedError()


def get_principal(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Principal:
    token = _token_from_request(request)
    payload = read_session_token(token, settings.app_secret)
    identity = IdentityRepository(session)
    record = identity.get_session_by_hash(hash_token(token))
    if record is None or record.revoked_at is not None:
        raise UnauthorizedError("Session is not active")
    if record.user_id != payload["uid"] or record.tenant_id != payload["tid"]:
        raise UnauthorizedError("Session does not match the token")
    user = identity.get_user(record.tenant_id, record.user_id)
    if not user.is_active:
        raise UnauthorizedError("User is disabled")
    roles = identity.roles_for(user.id)
    principal = Principal(
        user_id=user.id,
        tenant_id=user.tenant_id,
        session_id=record.id,
        roles=frozenset(roles),
        csrf_hash=record.csrf_hash,
    )
    _enforce_csrf(request, principal)
    return principal


def _enforce_csrf(request: Request, principal: Principal) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return
    provided = request.headers.get("x-csrf-token", "")
    if not provided or hash_token(provided) != principal.csrf_hash:
        raise ForbiddenError("CSRF token is missing or invalid")


def require(permission: str):
    def _dependency(principal: Principal = Depends(get_principal)) -> Principal:
        authorize(set(principal.roles), permission)
        return principal

    return _dependency
