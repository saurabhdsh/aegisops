"""Simulator scenarios exercise the real workflow engine and the restricted runner."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sqlalchemy import func, select

from aegisops.core.identifiers import new_id
from aegisops.persistence.models import (
    AgentExecution,
    AutomationExecution,
    ChangeRecord,
    CorrelationGroup,
    ToolExecution,
    ValidationResult,
    Workflow,
)
from tests.conftest import auth_header


def test_compute_incident_stops_for_approval_then_resolves(api) -> None:
    headers = auth_header(api)
    started = api.post("/api/v1/simulator/scenarios/compute-incident", headers=headers)
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["state"] == "AWAITING_APPROVAL"
    workflow_id = body["workflow_id"]

    hypotheses = api.get(f"/api/v1/workflows/{workflow_id}/hypotheses", headers=headers)
    causes = hypotheses.json()["items"]
    assert 1 <= len(causes) <= 3
    assert "Memory utilization is rising" in causes[0]["cause"]
    assert causes[0]["requires_human_review"] is True

    agents = api.get(f"/api/v1/workflows/{workflow_id}/agents", headers=headers)
    tool_names = {item["tool_name"] for item in agents.json()["tools"]}
    assert "shell" not in tool_names
    assert all("rm" not in name for name in tool_names)
    triage = next(item for item in agents.json()["items"] if item["agent_name"] == "triage")
    assert "Similar incidents returned: 3" == triage["summary"]
    assert "dynatrace.traces" in tool_names

    plan = api.get(f"/api/v1/workflows/{workflow_id}/plan", headers=headers).json()["plan"]
    assert plan["summary"] == "Restart Claims API and add one node"
    assert plan["parameters"]["service_name"] == "claims-api"
    assert plan["parameters"]["node_count"] == "1"
    assert plan["rollback_available"] is True

    approvals = api.get("/api/v1/approvals", headers=headers).json()["items"]
    pending = next(item for item in approvals if item["workflow_id"] == workflow_id and item["status"] == "pending")
    approved = api.post(f"/api/v1/approvals/{pending['id']}/approve", headers=headers, json={"reason": "evidence checked"})
    assert approved.status_code == 200, approved.text

    finished = api.get(f"/api/v1/workflows/{workflow_id}", headers=headers).json()
    assert finished["state"] == "RESOLVED"
    execution = api.get(f"/api/v1/workflows/{workflow_id}/executions", headers=headers).json()["items"][0]
    assert execution["result"]["executor"] == "restricted-runbook-runner"
    marker = Path(execution["external_execution_id"]) / "claims-api.restarted"
    assert marker.read_text() == "restarted\n"
    assert (Path(execution["external_execution_id"]) / "claims-api.node").read_text() == "added 1 node\n"
    incident = api.get(f"/api/v1/incidents/{finished['incident_id']}", headers=headers)
    assert incident.status_code == 200, incident.text
    assert incident.json()["state"] == "resolved"
    assert incident.json()["number"] == "INC0012345"
    assert any("Recovery checks passed" in note for note in incident.json()["work_notes"])

    again = api.post("/api/v1/simulator/scenarios/compute-incident", headers=headers)
    assert again.json()["duplicate"] is True
    assert again.json()["workflow_id"] == workflow_id


def test_existing_execution_marker_is_reconciled(api) -> None:
    headers = auth_header(api)
    started = api.post("/api/v1/simulator/scenarios/compute-incident", headers=headers)
    workflow_id = started.json()["workflow_id"]
    sandbox = Path(tempfile.gettempdir()) / "aegisops" / workflow_id
    sandbox.mkdir(parents=True, exist_ok=True)
    marker = sandbox / "claims-api.restarted"
    marker.write_text("preexisting\n")
    session = api.app.state.sessions()
    try:
        workflow = session.get(Workflow, workflow_id)
        session.add(
            AutomationExecution(
                id=new_id("exe"),
                tenant_id=workflow.tenant_id,
                workflow_id=workflow.id,
                external_execution_id=str(sandbox),
                status="running",
                phase="execute",
                idempotency_key=f"{workflow.id}:restart-claims-service",
                parameters={"service_name": "claims-api"},
            )
        )
        session.commit()
    finally:
        session.close()
    approvals = api.get("/api/v1/approvals", headers=headers).json()["items"]
    pending = next(item for item in approvals if item["workflow_id"] == workflow_id)
    approved = api.post(f"/api/v1/approvals/{pending['id']}/approve", headers=headers, json={"reason": "reconcile"})
    assert approved.status_code == 200, approved.text
    finished = api.get(f"/api/v1/workflows/{workflow_id}", headers=headers).json()
    assert finished["state"] == "RESOLVED"
    assert marker.read_text() == "preexisting\n"


def test_disk_capacity_consolidates_alerts_and_prevents_after_approval(api) -> None:
    headers = auth_header(api)
    started = api.post("/api/v1/simulator/scenarios/disk-capacity", headers=headers)
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["state"] == "AWAITING_APPROVAL"
    assert body["alert_count"] == 50
    workflow_id = body["workflow_id"]

    session = api.app.state.sessions()
    try:
        group = session.scalar(select(CorrelationGroup).where(CorrelationGroup.tenant_id != ""))
        assert group is not None
        assert group.alert_count == 51
        event_count = session.scalar(select(func.count()).select_from(CorrelationGroup))
    finally:
        session.close()
    assert event_count == 1

    approvals = api.get("/api/v1/approvals", headers=headers).json()["items"]
    pending = next(item for item in approvals if item["workflow_id"] == workflow_id)
    assert pending["required_role"] == "dba"
    approved = api.post(f"/api/v1/approvals/{pending['id']}/approve", headers=headers, json={"reason": "dba checked"})
    assert approved.status_code == 200, approved.text
    finished = api.get(f"/api/v1/workflows/{workflow_id}", headers=headers).json()
    assert finished["state"] == "PREVENTED"

    execution = api.get(f"/api/v1/workflows/{workflow_id}/executions", headers=headers).json()["items"][0]
    assert execution["result"]["deleted_bytes"] == 2000
    sandbox = Path(execution["external_execution_id"])
    logs = sandbox / "logs"
    assert not (logs / "claims-old.log").exists()
    assert (logs / "claims-fresh.log").exists()
    assert (logs / "nested" / "kept.log").read_text() == "keep"
    assert (sandbox / "volume.extended").read_text() == "extended 1 volume\n"

    session = api.app.state.sessions()
    try:
        validation = session.scalar(select(ValidationResult).where(ValidationResult.workflow_id == workflow_id))
        change = session.scalar(select(ChangeRecord).where(ChangeRecord.workflow_id == workflow_id))
        agent = session.scalar(
            select(AgentExecution).where(
                AgentExecution.workflow_id == workflow_id,
                AgentExecution.agent_name == "validation",
            )
        )
        assert validation is not None and validation.status == "passed"
        assert "before an incident" in validation.summary
        assert change is not None and change.state == "closed"
        assert change.external_number == "CHG0044101"
        assert agent is not None
        assert agent.output_payload["utilization"] == pytest.approx(60.8)
        assert agent.output_payload["before_utilization"] == 80
        assert agent.output_payload["incident_avoided"] is True
        assert agent.output_payload["hours_to_exhaustion"] == pytest.approx(9.8)
        capacity_agent = session.scalar(
            select(AgentExecution).where(
                AgentExecution.workflow_id == workflow_id,
                AgentExecution.agent_name == "capacity_risk",
            )
        )
        assert capacity_agent is not None
        enriched = capacity_agent.output_payload
        assert enriched["configuration_item"]["name"] == "claims-db-01"
        assert enriched["business_service"]["name"] == "Claims"
        assert enriched["business_service"]["criticality"] == "tier-1"
        assert enriched["related_changes"][0]["number"] == "CHG009880"
        assert len(enriched["similar_fixes"]) == 3
        assert enriched["growth_per_hour"] == 4
        grouped = session.scalar(
            select(AgentExecution).where(
                AgentExecution.workflow_id == workflow_id,
                AgentExecution.agent_name == "event_correlation",
            )
        )
        assert grouped is not None
        assert grouped.output_payload["forecast_count"] == 1
        assert grouped.output_payload["alert_count"] == 50
    finally:
        session.close()

    forecasts = api.get("/api/v1/capacity/forecasts", headers=headers).json()["items"]
    disk = next(item for item in forecasts if item["entity_id"] == "HOST-CLAIMS-DB-01")
    assert disk["current_utilization"] == 80
    assert disk["growth_per_hour"] == 4
    assert disk["hours_to_exhaustion"] == 5
    assert [point["value"] for point in disk["points"]] == [64, 68, 72, 76, 80]
    repeated = api.post("/api/v1/simulator/scenarios/disk-capacity", headers=headers)
    assert repeated.json()["duplicate"] is True


def test_l4_executes_certified_restart_and_disk_cleanup(api) -> None:
    api.app.state.settings.autonomy_l4_enabled = True
    headers = auth_header(api)
    changed = api.post("/api/v1/operations/autonomy", headers=headers, json={"level": "L4"})
    assert changed.status_code == 200, changed.text
    incident = api.post("/api/v1/simulator/scenarios/compute-incident", headers=headers)
    assert incident.status_code == 200, incident.text
    assert incident.json()["state"] == "RESOLVED"
    capacity = api.post("/api/v1/simulator/scenarios/disk-capacity", headers=headers)
    assert capacity.status_code == 200, capacity.text
    assert capacity.json()["state"] == "PREVENTED"


def test_webhook_replay_returns_the_original_event(api) -> None:
    headers = {"X-Aegis-Webhook-Token": "test-webhook-secret"}
    payload = {"event_id": "problem-9", "event_type": "problem", "entity_ref": "HOST-1", "severity": "warning"}
    first = api.post("/api/v1/webhooks/dynatrace", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False
    second = api.post("/api/v1/webhooks/dynatrace", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["event_id"] == first.json()["event_id"]


def test_integration_probes_use_the_simulator_in_simulator_mode(api) -> None:
    headers = auth_header(api)
    snow = api.post("/api/v1/integrations/servicenow/test", headers=headers)
    dyna = api.post("/api/v1/integrations/dynatrace/test", headers=headers)
    assert snow.status_code == 200, snow.text
    assert snow.json()["mode"] == "SIMULATOR"
    assert dyna.status_code == 200, dyna.text
    assert dyna.json()["capabilities"]["traces"] == "available"


def test_prompt_injection_does_not_create_a_tool(api) -> None:
    headers = auth_header(api)
    started = api.post("/api/v1/simulator/scenarios/compute-incident", headers=headers)
    workflow_id = started.json()["workflow_id"]
    session = api.app.state.sessions()
    try:
        names = set(session.scalars(select(ToolExecution.tool_name)))
    finally:
        session.close()
    assert "shell" not in names
    agents = api.get(f"/api/v1/workflows/{workflow_id}/agents", headers=headers).json()
    assert any("Ignore previous instructions" not in item["summary"] for item in agents["items"])
