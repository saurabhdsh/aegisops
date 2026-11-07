from datetime import datetime, timedelta, timezone

import pytest

from aegisops.core.exceptions import AuditImmutableError, ConflictError
from aegisops.core.identifiers import new_id
from aegisops.persistence.models import (
    ApprovalRequest,
    AuditEvent,
    AutomationExecution,
    Incident,
    RemediationPlan,
)
from aegisops.persistence.session import create_db_engine, create_session_factory
from aegisops.runtime.leases import LeaseManager
from aegisops.runtime.orchestrator import WorkflowOrchestrator
from tests.conftest import auth_header


def test_leases_are_exclusive(api) -> None:
    sessions = api.app.state.sessions
    first = sessions()
    second = sessions()
    try:
        assert LeaseManager(first).acquire(
            worker_id="worker-a", resource_type="workflow", resource_id="wf", ttl_seconds=30
        )
        first.commit()
        assert not LeaseManager(second).acquire(
            worker_id="worker-b", resource_type="workflow", resource_id="wf", ttl_seconds=30
        )
        second.rollback()
        owned = sessions()
        try:
            lease = LeaseManager(owned)
            row_session = owned
            from sqlalchemy import select
            from aegisops.persistence.models import WorkerLease

            row = row_session.scalar(select(WorkerLease).where(WorkerLease.resource_id == "wf"))
            assert row is not None
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
            row_session.commit()
        finally:
            owned.close()
        assert LeaseManager(second).acquire(
            worker_id="worker-b", resource_type="workflow", resource_id="wf", ttl_seconds=30
        )
        second.commit()
    finally:
        first.close()
        second.close()


def test_audit_rows_cannot_be_updated_or_deleted(api) -> None:
    session = api.app.state.sessions()
    try:
        event = AuditEvent(
            id=new_id("aud"),
            action="test.event",
            resource_type="test",
            resource_id="1",
            payload={"token": "should-not-matter"},
        )
        session.add(event)
        session.commit()
        event.action = "tampered"
        with pytest.raises(AuditImmutableError):
            session.commit()
        session.rollback()
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE audit_events SET action = 'tampered'"))
            session.commit()
        session.rollback()
        session.delete(event)
        with pytest.raises(AuditImmutableError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_workflow_cancel_does_not_claim_an_external_action_stopped(api) -> None:
    session = api.app.state.sessions()
    try:
        from sqlalchemy import select
        from aegisops.persistence.models import Tenant

        tenant = session.scalar(select(Tenant).where(Tenant.slug == "default"))
        assert tenant is not None
        orchestrator = WorkflowOrchestrator(session)
        workflow = orchestrator.open(
            tenant_id=tenant.id,
            kind="incident",
            correlation_id=new_id("cor"),
            execution_mode="SIMULATOR",
            autonomy_level="L3",
            idempotency_key=new_id("idem"),
        )
        for target in ("NORMALIZING", "ENRICHING", "INVESTIGATING", "ANALYZING", "PLANNING", "POLICY_CHECK", "AWAITING_APPROVAL", "PRECHECKING", "EXECUTING"):
            orchestrator.transition(workflow, target)
        session.add(
            AutomationExecution(
                id=new_id("exe"),
                tenant_id=tenant.id,
                workflow_id=workflow.id,
                external_execution_id="ansible-job-1",
                status="running",
                phase="execute",
                idempotency_key=new_id("idem"),
            )
        )
        session.flush()
        result = orchestrator.request_cancel(workflow)
        assert result["external_action_stopped"] is False
        assert result["cancel_requested"] is True
        assert workflow.state == "EXECUTING"
        session.commit()
    finally:
        session.close()

    headers = auth_header(api)
    listed = api.get("/api/v1/workflows", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


def test_sse_replays_persisted_outbox(api) -> None:
    session = api.app.state.sessions()
    try:
        from sqlalchemy import select
        from aegisops.persistence.models import Tenant

        tenant = session.scalar(select(Tenant).where(Tenant.slug == "default"))
        workflow = WorkflowOrchestrator(session).open(
            tenant_id=tenant.id,
            kind="incident",
            correlation_id=new_id("cor"),
            execution_mode="SIMULATOR",
            autonomy_level="L3",
            idempotency_key=new_id("idem"),
        )
        session.commit()
        workflow_id = workflow.id
        sequence = 1
    finally:
        session.close()

    headers = auth_header(api)
    with api.stream("GET", f"/api/v1/workflows/{workflow_id}/stream", headers=headers) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "workflow.received" in body
    assert f"id: {sequence}" in body

    with api.stream(
        "GET",
        f"/api/v1/workflows/{workflow_id}/stream",
        headers={**headers, "Last-Event-ID": "1"},
    ) as response:
        replay = "".join(response.iter_text())
    assert "workflow.received" not in replay


def test_illegal_persisted_transition(api) -> None:
    session = api.app.state.sessions()
    try:
        from sqlalchemy import select
        from aegisops.persistence.models import Tenant

        tenant = session.scalar(select(Tenant).where(Tenant.slug == "default"))
        workflow = WorkflowOrchestrator(session).open(
            tenant_id=tenant.id,
            kind="incident",
            correlation_id=new_id("cor"),
            execution_mode="SIMULATOR",
            autonomy_level="L3",
            idempotency_key=new_id("idem"),
        )
        with pytest.raises(ConflictError):
            WorkflowOrchestrator(session).transition(workflow, "EXECUTING")
    finally:
        session.rollback()
        session.close()


def test_approval_binding_and_emergency_stop(api) -> None:
    session = api.app.state.sessions()
    try:
        from sqlalchemy import select
        from aegisops.persistence.models import Tenant

        tenant = session.scalar(select(Tenant).where(Tenant.slug == "default"))
        incident = Incident(
            id=new_id("inc"),
            tenant_id=tenant.id,
            external_number="INC001",
            external_sys_id="sys1",
            title="Claims CPU",
            idempotency_key="inc-1",
            state="open",
        )
        session.add(incident)
        workflow = WorkflowOrchestrator(session).open(
            tenant_id=tenant.id,
            kind="incident",
            correlation_id=new_id("cor"),
            execution_mode="SIMULATOR",
            autonomy_level="L3",
            idempotency_key="wf-1",
            incident_id=incident.id,
        )
        plan = RemediationPlan(
            id=new_id("pln"),
            tenant_id=tenant.id,
            workflow_id=workflow.id,
            summary="restart",
            runbook_version="1.0.0",
            plan_hash="abc123",
            risk_level="medium",
        )
        session.add(plan)
        session.flush()
        approval = ApprovalRequest(
            id=new_id("apr"),
            tenant_id=tenant.id,
            workflow_id=workflow.id,
            plan_id=plan.id,
            required_role="sre",
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            plan_hash="abc123",
            runbook_version="1.0.0",
        )
        session.add(approval)
        session.commit()
        approval_id = approval.id
        incident_id = incident.id
        workflow_id = workflow.id
    finally:
        session.close()

    headers = auth_header(api)
    investigated = api.post(f"/api/v1/incidents/{incident_id}/investigate", headers=headers)
    assert investigated.status_code == 200, investigated.text
    assert investigated.json()["duplicate"] is True
    assert investigated.json()["workflow_id"] == workflow_id
    assert investigated.json()["state"] == "RECEIVED"

    approved = api.post(f"/api/v1/approvals/{approval_id}/approve", headers=headers, json={"reason": "checked"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    again = api.post(f"/api/v1/approvals/{approval_id}/approve", headers=headers, json={"reason": "again"})
    assert again.status_code == 409

    stop = api.post("/api/v1/operations/emergency-stop", headers=headers, json={"reason": "drill"})
    assert stop.status_code == 200
    assert stop.json()["emergency_stop"] is True
    assert stop.json()["freeze_reason"] == "drill"
