from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aegisops.persistence.repositories.operations import OperationsRepository
from apps.api.dependencies import Principal, get_session, require
from apps.api.schemas.common import CertificationResponse, RunbookResponse

router = APIRouter(prefix="/api/v1/runbooks", tags=["runbooks"])


@router.get("", response_model=list[RunbookResponse])
def list_runbooks(
    principal: Principal = Depends(require("runbook:read")),
    session: Session = Depends(get_session),
) -> list[RunbookResponse]:
    return [
        RunbookResponse.model_validate(row)
        for row in OperationsRepository(session).list_runbooks(principal.tenant_id)
    ]


@router.get("/{runbook_id}", response_model=RunbookResponse)
def get_runbook(
    runbook_id: str,
    principal: Principal = Depends(require("runbook:read")),
    session: Session = Depends(get_session),
) -> RunbookResponse:
    return RunbookResponse.model_validate(
        OperationsRepository(session).get_runbook(principal.tenant_id, runbook_id)
    )


@router.get("/{runbook_id}/certification", response_model=list[CertificationResponse])
def certification(
    runbook_id: str,
    principal: Principal = Depends(require("runbook:read")),
    session: Session = Depends(get_session),
) -> list[CertificationResponse]:
    rows = OperationsRepository(session).certifications_for(principal.tenant_id, runbook_id)
    return [CertificationResponse.model_validate(row) for row in rows]
