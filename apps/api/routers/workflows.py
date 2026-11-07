from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.persistence.models import (
    AgentExecution,
    AutomationExecution,
    Notification,
    OutboxEvent,
    RCAHypothesis,
    RemediationPlan,
    ToolExecution,
    ChangeRecord,
    ValidationResult,
)
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.runtime.orchestrator import WorkflowOrchestrator
from apps.api.dependencies import Principal, get_session, get_settings, require
from apps.api.schemas.common import CancelResponse, Page, WorkflowResponse, WorkflowStepResponse

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.get("", response_model=Page[WorkflowResponse])
def list_workflows(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require("workflow:read")),
    session: Session = Depends(get_session),
) -> Page[WorkflowResponse]:
    rows, total = OperationsRepository(session).list_workflows(principal.tenant_id, limit=limit, offset=offset)
    return Page(items=[WorkflowResponse.model_validate(row) for row in rows], total=total, limit=limit, offset=offset)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: str,
    principal: Principal = Depends(require("workflow:read")),
    session: Session = Depends(get_session),
) -> WorkflowResponse:
    return WorkflowResponse.model_validate(
        OperationsRepository(session).get_workflow(principal.tenant_id, workflow_id)
    )


@router.get("/{workflow_id}/steps", response_model=list[WorkflowStepResponse])
def workflow_steps(
    workflow_id: str,
    principal: Principal = Depends(require("workflow:read")),
    session: Session = Depends(get_session),
) -> list[WorkflowStepResponse]:
    rows = OperationsRepository(session).steps_for(principal.tenant_id, workflow_id)
    return [WorkflowStepResponse.model_validate(row) for row in rows]


@router.get("/{workflow_id}/events")
def workflow_events(
    workflow_id: str,
    after: int = Query(0, ge=0),
    principal: Principal = Depends(require("workflow:read")),
    session: Session = Depends(get_session),
) -> dict:
    events = OperationsRepository(session).outbox_after(principal.tenant_id, workflow_id, after)
    return {"items": [_event_payload(event) for event in events]}


@router.get("/{workflow_id}/hypotheses")
def workflow_hypotheses(
    workflow_id: str,
    principal: Principal = Depends(require("workflow:read")),
    session: Session = Depends(get_session),
) -> dict:
    OperationsRepository(session).get_workflow(principal.tenant_id, workflow_id)
    rows = session.scalars(
        select(RCAHypothesis)
        .where(RCAHypothesis.tenant_id == principal.tenant_id, RCAHypothesis.workflow_id == workflow_id)
        .order_by(RCAHypothesis.rank.asc())
    )
    return {
        "items": [
            {
                "rank": row.rank,
                "cause": row.cause,
                "confidence": row.confidence,
                "limitations": row.limitations or [],
                "requires_human_review": row.requires_human_review,
            }
            for row in rows
        ]
    }


@router.get("/{workflow_id}/plan")
def workflow_plan(
    workflow_id: str,
    principal: Principal = Depends(require("workflow:read")),
    session: Session = Depends(get_session),
) -> dict:
    OperationsRepository(session).get_workflow(principal.tenant_id, workflow_id)
    plan = session.scalar(
        select(RemediationPlan)
        .where(RemediationPlan.tenant_id == principal.tenant_id, RemediationPlan.workflow_id == workflow_id)
        .order_by(RemediationPlan.created_at.desc())
    )
    if plan is None:
        return {"plan": None}
    return {
        "plan": {
            "id": plan.id,
            "summary": plan.summary,
            "runbook_version": plan.runbook_version,
            "parameters": plan.parameters or {},
            "risk_level": plan.risk_level,
            "rollback_available": plan.rollback_available,
            "plan_hash": plan.plan_hash,
            "status": plan.status,
        }
    }


@router.get("/{workflow_id}/executions")
def workflow_executions(
    workflow_id: str,
    principal: Principal = Depends(require("workflow:read")),
    session: Session = Depends(get_session),
) -> dict:
    OperationsRepository(session).get_workflow(principal.tenant_id, workflow_id)
    rows = session.scalars(
        select(AutomationExecution).where(
            AutomationExecution.tenant_id == principal.tenant_id,
            AutomationExecution.workflow_id == workflow_id,
        )
    )
    return {
        "items": [
            {
                "id": row.id,
                "status": row.status,
                "phase": row.phase,
                "external_execution_id": row.external_execution_id,
                "result": row.result or {},
            }
            for row in rows
        ]
    }


@router.get("/{workflow_id}/agents")
def workflow_agents(
    workflow_id: str,
    principal: Principal = Depends(require("workflow:read")),
    session: Session = Depends(get_session),
) -> dict:
    OperationsRepository(session).get_workflow(principal.tenant_id, workflow_id)
    rows = list(
        session.scalars(
            select(AgentExecution)
            .where(AgentExecution.tenant_id == principal.tenant_id, AgentExecution.workflow_id == workflow_id)
            .order_by(AgentExecution.started_at.asc())
        )
    )
    tools = []
    if rows:
        tools = list(
            session.scalars(select(ToolExecution).where(ToolExecution.agent_execution_id.in_([row.id for row in rows])))
        )
    return {
        "items": [
            {
                "id": row.id,
                "agent_name": row.agent_name,
                "status": row.status,
                "summary": row.summary,
                "model": row.model,
                "confidence": row.confidence,
                "latency_ms": row.latency_ms,
                "output": row.output_payload or {},
            }
            for row in rows
        ],
        "tools": [{"id": tool.id, "tool_name": tool.tool_name, "status": tool.status} for tool in tools],
        "validation": _validation(session, principal.tenant_id, workflow_id),
        "notifications": _notifications(session, principal.tenant_id, workflow_id),
        "change": _change(session, principal.tenant_id, workflow_id),
    }


@router.post("/{workflow_id}/cancel", response_model=CancelResponse)
def cancel_workflow(
    workflow_id: str,
    expected_version: int | None = None,
    principal: Principal = Depends(require("workflow:cancel")),
    session: Session = Depends(get_session),
) -> CancelResponse:
    workflow = OperationsRepository(session).get_workflow(principal.tenant_id, workflow_id)
    result = WorkflowOrchestrator(session).request_cancel(workflow, expected_version=expected_version)
    return CancelResponse(**result)


@router.get("/{workflow_id}/stream")
async def stream_workflow(
    workflow_id: str,
    request: Request,
    principal: Principal = Depends(require("workflow:read")),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    last_header = request.headers.get("last-event-id", "0")
    try:
        last_sequence = int(last_header)
    except ValueError:
        last_sequence = 0
    tenant_id = principal.tenant_id

    async def generate():
        sequence = last_sequence
        polls = 0
        while True:
            if await request.is_disconnected():
                break
            events = await asyncio.to_thread(_read_events, request, tenant_id, workflow_id, sequence)
            if events:
                for event in events:
                    sequence = event.sequence
                    yield _format_sse(event)
            else:
                yield ": heartbeat\n\n"
            polls += 1
            if settings.sse_max_polls and polls >= settings.sse_max_polls:
                break
            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(generate(), media_type="text/event-stream")


def _validation(session: Session, tenant_id: str, workflow_id: str) -> dict | None:
    row = session.scalar(
        select(ValidationResult).where(
            ValidationResult.tenant_id == tenant_id,
            ValidationResult.workflow_id == workflow_id,
        )
    )
    if row is None:
        return None
    return {"status": row.status, "summary": row.summary, "checks": row.checks or []}


def _change(session: Session, tenant_id: str, workflow_id: str) -> dict | None:
    row = session.scalar(
        select(ChangeRecord).where(ChangeRecord.tenant_id == tenant_id, ChangeRecord.workflow_id == workflow_id)
    )
    if row is None:
        return None
    return {"number": row.external_number, "state": row.state, "summary": row.summary}


def _notifications(session: Session, tenant_id: str, workflow_id: str) -> list[dict]:
    rows = session.scalars(
        select(Notification).where(Notification.tenant_id == tenant_id, Notification.workflow_id == workflow_id)
    )
    return [
        {"channel": row.channel, "recipient": row.recipient, "subject": row.subject, "body": row.body, "status": row.status}
        for row in rows
    ]


def _read_events(request: Request, tenant_id: str, workflow_id: str, sequence: int) -> list[OutboxEvent]:
    session = request.app.state.sessions()
    try:
        return OperationsRepository(session).outbox_after(tenant_id, workflow_id, sequence)
    finally:
        session.close()


def _event_payload(event: OutboxEvent) -> dict:
    return {
        "event_id": event.id,
        "workflow_id": event.workflow_id,
        "sequence": event.sequence,
        "timestamp": event.created_at.isoformat(),
        "type": event.event_type,
        "payload": event.payload or {},
    }


def _format_sse(event: OutboxEvent) -> str:
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(_event_payload(event))}\n\n"
