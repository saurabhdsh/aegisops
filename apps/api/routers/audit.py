from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from aegisops.persistence.repositories.operations import OperationsRepository
from apps.api.dependencies import Principal, get_session, require
from apps.api.schemas.common import AuditResponse, Page

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", response_model=Page[AuditResponse])
def list_audit(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require("audit:read")),
    session: Session = Depends(get_session),
) -> Page[AuditResponse]:
    rows, total = OperationsRepository(session).list_audit(principal.tenant_id, limit=limit, offset=offset)
    return Page(
        items=[AuditResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
