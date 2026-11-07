from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aegisops.persistence.repositories.operations import OperationsRepository
from apps.api.dependencies import Principal, get_session, require
from apps.api.schemas.common import MetricResponse

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


@router.get("/metrics", response_model=list[MetricResponse])
def metrics(
    principal: Principal = Depends(require("incident:read")),
    session: Session = Depends(get_session),
) -> list[MetricResponse]:
    return [
        MetricResponse.model_validate(row)
        for row in OperationsRepository(session).list_metrics(principal.tenant_id, limit=200)
    ]
