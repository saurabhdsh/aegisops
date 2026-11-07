from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aegisops.persistence.repositories.operations import OperationsRepository
from apps.api.dependencies import Principal, get_session, require

router = APIRouter(prefix="/api/v1/topology", tags=["topology"])


@router.get("/services")
def services(
    principal: Principal = Depends(require("incident:read")),
    session: Session = Depends(get_session),
) -> dict:
    rows = OperationsRepository(session).list_services(principal.tenant_id)
    return {
        "items": [
            {"id": row.id, "name": row.name, "criticality": row.criticality, "external_id": row.external_id}
            for row in rows
        ]
    }


@router.get("/configuration-items")
def configuration_items(
    principal: Principal = Depends(require("incident:read")),
    session: Session = Depends(get_session),
) -> dict:
    rows = OperationsRepository(session).list_assets(principal.tenant_id)
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "ci_class": row.ci_class,
                "environment": row.environment,
                "business_service_id": row.business_service_id,
            }
            for row in rows
        ]
    }
