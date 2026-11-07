"""Durable workflow transitions.

This module records state. It does not invoke agents or infrastructure tools.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from aegisops.core.exceptions import ConflictError
from aegisops.core.identifiers import new_id
from aegisops.persistence.models import Workflow
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.runtime.state_machine import assert_transition, is_terminal


class WorkflowOrchestrator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.operations = OperationsRepository(session)

    def open(
        self,
        *,
        tenant_id: str,
        kind: str,
        correlation_id: str,
        execution_mode: str,
        autonomy_level: str,
        idempotency_key: str,
        incident_id: str | None = None,
        summary: str = "",
    ) -> Workflow:
        workflow = Workflow(
            id=new_id("wf"),
            tenant_id=tenant_id,
            kind=kind,
            state="RECEIVED",
            correlation_id=correlation_id,
            incident_id=incident_id,
            autonomy_level=autonomy_level,
            execution_mode=execution_mode,
            idempotency_key=idempotency_key,
            summary=summary,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(workflow)
        self.session.flush()
        self.operations.append_outbox(
            tenant_id=tenant_id,
            workflow_id=workflow.id,
            event_type="workflow.received",
            payload={"state": "RECEIVED", "kind": kind},
        )
        return workflow

    def transition(
        self,
        workflow: Workflow,
        target: str,
        *,
        expected_version: int | None = None,
        detail: dict | None = None,
    ) -> Workflow:
        if expected_version is not None and workflow.version != expected_version:
            raise ConflictError(
                "Workflow version conflict",
                {"expected": expected_version, "actual": workflow.version},
            )
        assert_transition(workflow.state, target)
        previous = workflow.state
        workflow.state = target
        workflow.version += 1
        workflow.updated_at = datetime.now(timezone.utc)
        if is_terminal(target):
            workflow.finished_at = datetime.now(timezone.utc)
        self.operations.add_workflow_step(
            tenant_id=workflow.tenant_id,
            workflow=workflow,
            name=target,
            state=target,
            detail={"from": previous, **(detail or {})},
        )
        self.operations.append_outbox(
            tenant_id=workflow.tenant_id,
            workflow_id=workflow.id,
            event_type="workflow.transition",
            payload={"from": previous, "to": target, "version": workflow.version},
        )
        self.session.flush()
        return workflow

    def request_cancel(self, workflow: Workflow, *, expected_version: int | None = None) -> dict:
        """Cancel when no external action is in flight.

        If an external execution identifier exists, record the request and leave
        the workflow state unchanged. The caller must reconcile that action.
        """
        if expected_version is not None and workflow.version != expected_version:
            raise ConflictError(
                "Workflow version conflict",
                {"expected": expected_version, "actual": workflow.version},
            )
        if is_terminal(workflow.state):
            raise ConflictError("Workflow is already terminal", {"state": workflow.state})
        external = self.operations.running_external_execution(workflow.tenant_id, workflow.id)
        if external is not None or workflow.state == "EXECUTING":
            workflow.cancel_requested = True
            workflow.version += 1
            self.operations.append_outbox(
                tenant_id=workflow.tenant_id,
                workflow_id=workflow.id,
                event_type="workflow.cancel_requested",
                payload={
                    "state": workflow.state,
                    "external_execution_id": external.external_execution_id if external else "",
                    "note": "Cancellation requested. External execution status must be reconciled.",
                },
            )
            self.session.flush()
            return {
                "state": workflow.state,
                "cancel_requested": True,
                "external_action_stopped": False,
            }
        self.transition(workflow, "CANCELLED", detail={"reason": "operator_cancel"})
        return {"state": workflow.state, "cancel_requested": True, "external_action_stopped": False}
