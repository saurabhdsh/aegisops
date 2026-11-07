from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from aegisops.observability.audit import audit
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.core.config import Settings
from aegisops.policy.engine import evaluate_approval
from aegisops.runtime.engine import OperationsEngine
from apps.api.dependencies import Principal, get_session, get_settings, require
from apps.api.schemas.common import ApprovalResponse, DecisionRequest, Page

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.get("", response_model=Page[ApprovalResponse])
def list_approvals(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require("approval:read")),
    session: Session = Depends(get_session),
) -> Page[ApprovalResponse]:
    rows, total = OperationsRepository(session).list_approvals(principal.tenant_id, limit=limit, offset=offset)
    return Page(items=[ApprovalResponse.model_validate(row) for row in rows], total=total, limit=limit, offset=offset)


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval(
    approval_id: str,
    principal: Principal = Depends(require("approval:read")),
    session: Session = Depends(get_session),
) -> ApprovalResponse:
    return ApprovalResponse.model_validate(
        OperationsRepository(session).get_approval(principal.tenant_id, approval_id)
    )


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
def approve(
    approval_id: str,
    body: DecisionRequest,
    request: Request,
    principal: Principal = Depends(require("approval:decide")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApprovalResponse:
    return _decide(session, request, principal, approval_id, "approved", body.reason, settings)


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
def reject(
    approval_id: str,
    body: DecisionRequest,
    request: Request,
    principal: Principal = Depends(require("approval:decide")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ApprovalResponse:
    return _decide(session, request, principal, approval_id, "rejected", body.reason, settings)


def _decide(
    session: Session,
    request: Request,
    principal: Principal,
    approval_id: str,
    decision: str,
    reason: str,
    settings: Settings,
) -> ApprovalResponse:
    operations = OperationsRepository(session)
    approval = operations.get_approval(principal.tenant_id, approval_id)
    control = operations.control_for(principal.tenant_id)
    now = datetime.now(timezone.utc)
    if approval.expires_at < now and approval.status == "pending":
        approval.status = "expired"
        session.commit()
        from aegisops.core.exceptions import ConflictError

        raise ConflictError("Approval request has expired")
    evaluate_approval(approval, actor_roles=set(principal.roles), control=control, now=now)
    operations.add_decision(
        tenant_id=principal.tenant_id,
        request=approval,
        actor_id=principal.user_id,
        decision=decision,
        reason=reason,
    )
    audit(
        session,
        action=f"approval.{decision}",
        resource_type="approval_request",
        resource_id=approval.id,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=request.state.correlation_id,
        payload={"plan_hash": approval.plan_hash, "runbook_version": approval.runbook_version},
    )
    workflow = operations.get_workflow(principal.tenant_id, approval.workflow_id)
    if decision == "approved" and workflow.state == "AWAITING_APPROVAL":
        OperationsEngine(session, settings).continue_approved(workflow, actor_id=principal.user_id)
    elif decision == "rejected" and workflow.state == "AWAITING_APPROVAL":
        from aegisops.runtime.orchestrator import WorkflowOrchestrator

        WorkflowOrchestrator(session).transition(workflow, "CANCELLED", detail={"reason": "approval_rejected"})
    return ApprovalResponse.model_validate(approval)
