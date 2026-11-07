from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from aegisops.connectors.dynatrace.factory import build_dynatrace
from aegisops.connectors.servicenow.factory import build_servicenow
from aegisops.core.config import Settings
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.runtime.connections import overlay
from apps.api.dependencies import Principal, get_session, get_settings, require
from apps.api.schemas.common import IntegrationResponse

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationResponse])
def list_integrations(
    principal: Principal = Depends(require("integration:read")),
    session: Session = Depends(get_session),
) -> list[IntegrationResponse]:
    return [
        IntegrationResponse.model_validate(row)
        for row in OperationsRepository(session).list_integrations(principal.tenant_id)
    ]


@router.get("/health")
def integration_health(
    principal: Principal = Depends(require("integration:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    rows = OperationsRepository(session).list_integrations(principal.tenant_id)
    return {
        "execution_mode": settings.execution_mode,
        "items": [
            {
                "kind": row.kind,
                "name": row.name,
                "status": row.last_health_status,
                "checked_at": row.last_health_at.isoformat() if row.last_health_at else None,
                "error": row.last_error,
                "capabilities": row.capabilities or {},
            }
            for row in rows
        ],
    }


@router.post("/servicenow/test")
def test_servicenow(
    principal: Principal = Depends(require("integration:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    report = _call(build_servicenow(overlay(session, settings, principal.tenant_id)))
    _record_health(session, principal.tenant_id, "servicenow", report)
    return report


@router.post("/dynatrace/test")
def test_dynatrace(
    principal: Principal = Depends(require("integration:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    report = _call(build_dynatrace(overlay(session, settings, principal.tenant_id)))
    _record_health(session, principal.tenant_id, "dynatrace", report)
    return report


def _call(client: object) -> dict:
    try:
        return client.health()  # type: ignore[attr-defined]
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()


def _record_health(session: Session, tenant_id: str, kind: str, report: dict) -> None:
    now = datetime.now(timezone.utc)
    for row in OperationsRepository(session).list_integrations(tenant_id):
        if row.kind == kind:
            row.last_health_at = now
            row.last_health_status = str(report.get("status") or "")
            row.last_error = ""
            row.capabilities = report.get("capabilities") or {}
