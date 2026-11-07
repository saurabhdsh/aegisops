from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.persistence.models import BusinessService, ConfigurationItem
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.runtime.analysis import incident_analysis
from aegisops.runtime.engine import OperationsEngine
from aegisops.runtime.live import refresh_servicenow_incidents
from apps.api.dependencies import Principal, get_session, get_settings, require
from apps.api.schemas.common import EvidenceResponse, IncidentResponse, Page

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("", response_model=Page[IncidentResponse])
def list_incidents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require("incident:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Page[IncidentResponse]:
    refresh_servicenow_incidents(session, settings, principal.tenant_id)
    rows, total = OperationsRepository(session).list_incidents(principal.tenant_id, limit=limit, offset=offset)
    return Page(
        items=[_incident(session, row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: str,
    principal: Principal = Depends(require("incident:read")),
    session: Session = Depends(get_session),
) -> IncidentResponse:
    return _incident(session, OperationsRepository(session).get_incident(principal.tenant_id, incident_id))


@router.get("/{incident_id}/analysis")
def incident_rca(
    incident_id: str,
    principal: Principal = Depends(require("incident:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    return incident_analysis(session, principal.tenant_id, incident_id, settings)


@router.get("/{incident_id}/evidence", response_model=list[EvidenceResponse])
def incident_evidence(
    incident_id: str,
    principal: Principal = Depends(require("incident:read")),
    session: Session = Depends(get_session),
) -> list[EvidenceResponse]:
    rows = OperationsRepository(session).evidence_for_incident(principal.tenant_id, incident_id)
    return [EvidenceResponse.model_validate(row) for row in rows]


@router.post("/{incident_id}/investigate")
def investigate(
    incident_id: str,
    principal: Principal = Depends(require("incident:investigate")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    incident = OperationsRepository(session).get_incident(principal.tenant_id, incident_id)
    return OperationsEngine(session, settings).investigate_incident(incident, actor_id=principal.user_id)


def _incident(session: Session, row) -> IncidentResponse:  # type: ignore[no-untyped-def]
    ci = session.get(ConfigurationItem, row.ci_id) if row.ci_id else None
    service = session.get(BusinessService, row.business_service_id) if row.business_service_id else None
    return IncidentResponse(
        id=row.id,
        number=row.external_number,
        title=row.title,
        description=row.description,
        state=row.state,
        source_state=row.source_state,
        priority=row.priority,
        severity=row.severity,
        ci_id=row.ci_id,
        business_service_id=row.business_service_id,
        opened_at=row.opened_at,
        resolved_at=row.resolved_at,
        work_notes=list(row.work_notes or []),
        ci_name=ci.name if ci else "",
        service_name=service.name if service else "",
        version=row.version,
    )
