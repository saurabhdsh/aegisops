from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.core.exceptions import UnauthorizedError
from aegisops.core.identifiers import new_id
from aegisops.core.security import hash_token, issue_session_token, new_csrf_token
from aegisops.observability.audit import audit
from aegisops.persistence.models import Tenant
from aegisops.persistence.repositories.identity import IdentityRepository
from aegisops.persistence.repositories.operations import OperationsRepository
from apps.api.dependencies import SESSION_COOKIE, Principal, get_principal, get_session, get_settings
from apps.api.schemas.common import LoginRequest, LoginResponse, PrincipalResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_payload(session: Session, principal_user_id: str, tenant_id: str) -> PrincipalResponse:
    identity = IdentityRepository(session)
    user = identity.get_user(tenant_id, principal_user_id)
    tenant = session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    return PrincipalResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        tenant_id=tenant_id,
        tenant_slug=tenant.slug if tenant else "",
        roles=sorted(identity.roles_for(user.id)),
    )


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    operations = OperationsRepository(session)
    tenant = operations.tenant_by_slug(body.tenant_slug.strip())
    identity = IdentityRepository(session)
    user = identity.authenticate(tenant.id, body.email, body.password) if tenant else None
    if user is None:
        if tenant is None:
            identity.authenticate("missing", body.email, body.password)
        audit(
            session,
            action="auth.login_failed",
            resource_type="user",
            tenant_id=tenant.id if tenant else None,
            payload={"email": body.email.strip().lower()},
        )
        session.commit()
        raise UnauthorizedError("Invalid credentials")
    csrf = new_csrf_token()
    record = identity.add_session(
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash=hash_token(new_id("pre")),
        csrf_hash=hash_token(csrf),
        expires_at=user.updated_at,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    token, expires_at = issue_session_token(
        secret=settings.app_secret,
        user_id=user.id,
        tenant_id=user.tenant_id,
        session_id=record.id,
        ttl_seconds=settings.session_ttl_seconds,
    )
    record.token_hash = hash_token(token)
    record.expires_at = expires_at
    audit(
        session,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        correlation_id=request.state.correlation_id,
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return LoginResponse(
        access_token=token,
        csrf_token=csrf,
        expires_at=expires_at,
        user=_user_payload(session, user.id, user.tenant_id),
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict:
    identity = IdentityRepository(session)
    token = request.headers.get("authorization", "")
    raw = token[7:].strip() if token.lower().startswith("bearer ") else request.cookies.get(SESSION_COOKIE, "")
    record = identity.get_session_by_hash(hash_token(raw)) if raw else None
    if record is not None:
        identity.revoke(record)
    audit(
        session,
        action="auth.logout",
        resource_type="session",
        resource_id=principal.session_id,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=request.state.correlation_id,
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "signed_out"}


@router.get("/me", response_model=PrincipalResponse)
def me(principal: Principal = Depends(get_principal), session: Session = Depends(get_session)) -> PrincipalResponse:
    return _user_payload(session, principal.user_id, principal.tenant_id)
