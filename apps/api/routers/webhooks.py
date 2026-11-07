from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import hmac

from aegisops.core.config import Settings
from aegisops.core.exceptions import NotFoundError, UnauthorizedError
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.runtime.connections import overlay
from aegisops.runtime.ingest import ingest_event
from apps.api.dependencies import get_session, get_settings


def _require_shared_secret(provided: str, expected: str) -> None:
    if not expected or not provided:
        raise UnauthorizedError("Webhook authentication failed")
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise UnauthorizedError("Webhook authentication failed")

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _tenant_id(session: Session, settings: Settings, request: Request) -> str:
    slug = request.headers.get("x-aegis-tenant") or settings.bootstrap_tenant_slug
    tenant = OperationsRepository(session).tenant_by_slug(slug)
    if tenant is None:
        raise NotFoundError("Tenant not found")
    return tenant.id


async def _ingest(request: Request, session: Session, settings: Settings, source: str, secret: str) -> dict:
    provided = request.headers.get("x-aegis-webhook-token", "")
    _require_shared_secret(provided, secret)
    body = await request.json()
    event, duplicate = ingest_event(
        session,
        tenant_id=_tenant_id(session, settings, request),
        source=source,
        external_id=str(body.get("event_id") or ""),
        event_type=str(body.get("event_type") or "alert"),
        entity_ref=str(body.get("entity_ref") or ""),
        severity=str(body.get("severity") or ""),
        payload=body,
    )
    return {"event_id": event.id, "duplicate": duplicate}


@router.post("/dynatrace")
async def dynatrace_webhook(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    tenant_id = _tenant_id(session, settings, request)
    tuned = overlay(session, settings, tenant_id)
    return await _ingest(request, session, settings, "dynatrace", tuned.dynatrace_webhook_secret)


@router.post("/servicenow")
async def servicenow_webhook(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    tenant_id = _tenant_id(session, settings, request)
    tuned = overlay(session, settings, tenant_id)
    return await _ingest(request, session, settings, "servicenow", tuned.servicenow_webhook_secret)
