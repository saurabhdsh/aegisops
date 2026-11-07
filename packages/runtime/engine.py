"""Drive incident and capacity workflows until a gate or a terminal state.

The engine persists every transition. It does not invent connector results.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.agents.capacity_risk import CapacityInput, CapacityRiskAgent
from aegisops.agents.event_correlation import CorrelationInput, EventCorrelationAgent
from aegisops.agents.governance import GovernanceAgent, GovernanceInput
from aegisops.agents.incident_goal import GoalInput, IncidentGoalAgent
from aegisops.agents.rca import RCAAgent, RCAInput
from aegisops.agents.remediation import RemediationAgent, RemediationInput
from aegisops.agents.triage import TriageAgent, TriageInput
from aegisops.agents.validation import ValidationAgent, ValidationInput
from aegisops.connectors.ansible.adapter import AutomationAdapter
from aegisops.connectors.dynatrace.factory import build_dynatrace
from aegisops.connectors.llm.factory import build_narrative
from aegisops.connectors.servicenow.factory import build_servicenow
from aegisops.contracts.agent import AgentContext
from aegisops.core.config import Settings
from aegisops.core.exceptions import ForbiddenError, IntegrationError
from aegisops.core.identifiers import new_id
from aegisops.persistence.models import (
    AgentExecution,
    ApprovalRequest,
    AutomationExecution,
    BusinessService,
    ChangeRecord,
    ConfigurationItem,
    CorrelationGroup,
    EvidenceArtifact,
    Incident,
    MetricObservation,
    Notification,
    RCAHypothesis,
    RemediationPlan,
    RunbookCertification,
    RunbookDefinition,
    ToolExecution,
    ValidationResult,
    Workflow,
)
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.runtime.context import Ports, ports_var
from aegisops.runtime.orchestrator import WorkflowOrchestrator
from aegisops.runtime.state_machine import TERMINAL

_KNOWN_RUNBOOKS = ("restart-claims-service", "cleanup-approved-logs")


def _jsonable(value):
    return json.loads(json.dumps(value, default=str))


def _last_value(observations, metric_key: str) -> float | None:
    matches = [row for row in observations if row.metric_key == metric_key]
    if not matches:
        return None
    matches.sort(key=lambda row: row.observed_at)
    return float(matches[-1].value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OperationsEngine:
    def __init__(self, session: Session, settings: Settings, *, fixtures_only: bool = False) -> None:
        self.session = session
        self.settings = settings
        self.fixtures_only = fixtures_only
        self.orch = WorkflowOrchestrator(session)
        self.ops = OperationsRepository(session)
        self.snow = build_servicenow(settings)
        self.dyna = build_dynatrace(settings)
        self.automation = AutomationAdapter(settings)
        self.narrative = build_narrative(settings)

    def investigate_incident(self, incident: Incident, *, actor_id: str) -> dict:
        self._guard(incident.tenant_id)
        existing = self._open_workflow(incident.tenant_id, incident_id=incident.id)
        if existing is not None:
            return {"workflow_id": existing.id, "state": existing.state, "duplicate": True}
        control = self.ops.control_for(incident.tenant_id)
        workflow = self.orch.open(
            tenant_id=incident.tenant_id,
            kind="incident",
            correlation_id=new_id("cor"),
            execution_mode=self.settings.execution_mode,
            autonomy_level=control.autonomy_level,
            idempotency_key=f"incident:{incident.id}:{incident.version}",
            incident_id=incident.id,
            summary=incident.title,
        )
        self._until_gate(workflow, actor_id)
        return {"workflow_id": workflow.id, "state": workflow.state, "duplicate": False}

    def continue_approved(self, workflow: Workflow, *, actor_id: str) -> Workflow:
        if workflow.state != "AWAITING_APPROVAL":
            return workflow
        self._guard(workflow.tenant_id)
        self.orch.transition(workflow, "PRECHECKING", detail={"reason": "approval_granted"})
        self._until_gate(workflow, actor_id)
        return workflow

    def resume(self, workflow: Workflow, *, actor_id: str = "worker") -> Workflow:
        if workflow.state in TERMINAL or workflow.state == "AWAITING_APPROVAL":
            return workflow
        self._until_gate(workflow, actor_id)
        return workflow

    def _until_gate(self, workflow: Workflow, actor_id: str) -> None:
        self._bind_saved_connections(workflow.tenant_id)
        for _ in range(12):
            if workflow.state in TERMINAL or workflow.state == "AWAITING_APPROVAL":
                return
            self._step(workflow, actor_id)

    def _bind_saved_connections(self, tenant_id: str) -> None:
        from aegisops.connectors.llm.factory import build_narrative
        from aegisops.runtime.connections import overlay

        tuned = overlay(self.session, self.settings, tenant_id)
        self.narrative = build_narrative(tuned)
        if self.fixtures_only:
            return
        from aegisops.connectors.dynatrace.factory import build_dynatrace
        from aegisops.connectors.servicenow.factory import build_servicenow

        self.snow = build_servicenow(tuned)
        self.dyna = build_dynatrace(tuned)
        self.settings = tuned

    def _guard(self, tenant_id: str) -> None:
        if self.ops.control_for(tenant_id).emergency_stop:
            raise ForbiddenError("Emergency stop is active. New executions are blocked.")

    def _step(self, workflow: Workflow, actor_id: str) -> None:
        if workflow.kind == "capacity":
            self._step_capacity(workflow, actor_id)
        else:
            self._step_incident(workflow, actor_id)

    def _step_incident(self, workflow: Workflow, actor_id: str) -> None:
        incident = self.session.get(Incident, workflow.incident_id)
        state = workflow.state
        if state == "RECEIVED":
            self._agent(workflow, IncidentGoalAgent(), GoalInput(kind="incident", child_agents=["triage", "rca", "remediation", "validation", "governance"]), actor_id)
            self.orch.transition(workflow, "NORMALIZING")
        elif state == "NORMALIZING":
            self.orch.transition(workflow, "ENRICHING")
        elif state == "ENRICHING":
            self.orch.transition(workflow, "INVESTIGATING")
        elif state == "INVESTIGATING":
            ci = self.session.get(ConfigurationItem, incident.ci_id) if incident and incident.ci_id else None
            result = self._agent(
                workflow,
                TriageAgent(),
                TriageInput(
                    incident_number=incident.external_number if incident else "",
                    incident_sys_id=incident.external_sys_id if incident else "",
                    title=incident.title if incident else "",
                    priority=incident.priority if incident else "",
                    ci_external_id=ci.external_id if ci else None,
                    work_notes=list(incident.work_notes or []) if incident else [],
                ),
                actor_id,
            )
            self._evidence(workflow, "triage", "Triage enrichment", "servicenow", result.structured_output, incident.id if incident else None)
            self.orch.transition(workflow, "ANALYZING")
        elif state == "ANALYZING":
            ci = self.session.get(ConfigurationItem, incident.ci_id) if incident and incident.ci_id else None
            entity_id = ((ci.attributes or {}) if ci else {}).get("dynatrace_entity_id")
            changes = []
            if ci:
                try:
                    changes = self.snow.get_related_changes(ci.external_id)
                except IntegrationError:
                    changes = []
            health = {}
            try:
                catalog_health = getattr(self.dyna, "incident", {}).get("service_health", {}) if hasattr(self.dyna, "incident") else {}
                health = catalog_health
            except Exception:
                health = {}
            result = self._agent(
                workflow,
                RCAAgent(),
                RCAInput(
                    entity_id=entity_id,
                    title=incident.title if incident else "",
                    priority=incident.priority if incident else "",
                    opened_at=incident.opened_at.isoformat() if incident and incident.opened_at else None,
                    changes=changes,
                    error_rate=health.get("error_rate"),
                    notes=list(incident.work_notes or []) if incident else [],
                ),
                actor_id,
            )
            self._store_series(workflow, result.structured_output.get("series") or {})
            self._store_hypotheses(workflow, result)
            if result.status != "completed":
                self.orch.transition(workflow, "ESCALATED", detail={"reason": "insufficient_evidence"})
            else:
                self.orch.transition(workflow, "PLANNING")
        elif state == "PLANNING":
            self._plan(workflow, actor_id, kind="incident")
        elif state == "POLICY_CHECK":
            self._policy(workflow, actor_id, required_role="sre")
        elif state == "PRECHECKING":
            self._precheck(workflow)
        elif state == "EXECUTING":
            self._execute(workflow)
        elif state == "VALIDATING":
            self._validate_incident(workflow, actor_id)
        else:
            self.orch.transition(workflow, "FAILED", detail={"reason": f"no step for {state}"})

    def _step_capacity(self, workflow: Workflow, actor_id: str) -> None:
        state = workflow.state
        if state == "RECEIVED":
            self._agent(workflow, IncidentGoalAgent(), GoalInput(kind="capacity", child_agents=["event_correlation", "capacity_risk", "remediation", "validation", "governance"]), actor_id)
            self.orch.transition(workflow, "NORMALIZING")
        elif state == "NORMALIZING":
            context = self._capacity_context(workflow)
            events = []
            for item in context.get("events") or []:
                received = item["received_at"]
                if isinstance(received, str):
                    received = datetime.fromisoformat(received.replace("Z", "+00:00"))
                events.append({**item, "received_at": received})
            result = self._agent(workflow, EventCorrelationAgent(), CorrelationInput(events=events), actor_id)
            groups = result.structured_output.get("groups") or []
            if groups:
                group = groups[0]
                opened = group["opened_at"]
                if isinstance(opened, str):
                    opened = datetime.fromisoformat(opened.replace("Z", "+00:00"))
                row = CorrelationGroup(
                    id=new_id("crg"),
                    tenant_id=workflow.tenant_id,
                    summary=str(group["summary"]),
                    entity_ref=str(group.get("entity_ref") or ""),
                    symptom=str(group.get("symptom") or ""),
                    alert_count=int(group["alert_count"]),
                    state="open",
                    opened_at=opened,
                )
                self.session.add(row)
                self.session.flush()
                workflow.correlation_group_id = row.id
            self.orch.transition(workflow, "ENRICHING")
        elif state == "ENRICHING":
            self.orch.transition(workflow, "ANALYZING")
        elif state == "ANALYZING":
            context = self._capacity_context(workflow)
            result = self._agent(
                workflow,
                CapacityRiskAgent(),
                CapacityInput(
                    points=context.get("points") or [],
                    criticality=context.get("criticality") or "unknown",
                    legal_hold=bool(context.get("legal_hold")),
                    storage_extension_supported=bool(context.get("storage_extension_supported")),
                    entity_id=str(context.get("entity_id") or ""),
                    ci_external_id=str(context.get("ci_external_id") or ""),
                ),
                actor_id,
            )
            context["current_utilization"] = result.structured_output.get("current_utilization")
            context["growth_per_hour"] = result.structured_output.get("growth_per_hour")
            measured = result.structured_output.get("points") or context.get("points") or []
            context["points"] = measured
            workflow.summary = json.dumps(context)
            for point in measured:
                stamp = point["timestamp"]
                if isinstance(stamp, str):
                    stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                self.session.add(
                    MetricObservation(
                        id=new_id("met"),
                        tenant_id=workflow.tenant_id,
                        entity_id=context.get("entity_id") or "",
                        metric_key="disk",
                        observed_at=stamp,
                        value=float(point["value"]),
                        unit=point.get("unit") or "percent",
                        source="dynatrace-simulator" if self.settings.execution_mode == "SIMULATOR" else "dynatrace",
                        query_reference="capacity-scenario",
                    )
                )
            if result.status != "completed":
                self.orch.transition(workflow, "ESCALATED", detail={"reason": "no_metrics"})
            else:
                self.orch.transition(workflow, "PLANNING")
        elif state == "PLANNING":
            self._plan(workflow, actor_id, kind="capacity")
        elif state == "POLICY_CHECK":
            self._policy(workflow, actor_id, required_role="dba")
        elif state == "PRECHECKING":
            self._prepare_capacity_sandbox(workflow)
            self._precheck(workflow)
        elif state == "EXECUTING":
            self._execute(workflow)
        elif state == "VALIDATING":
            self._validate_capacity(workflow, actor_id)
        else:
            self.orch.transition(workflow, "FAILED", detail={"reason": f"no step for {state}"})

    def _plan(self, workflow: Workflow, actor_id: str, *, kind: str) -> None:
        context = self._capacity_context(workflow) if kind == "capacity" else {}
        incident = self.session.get(Incident, workflow.incident_id) if workflow.incident_id else None
        ci = self._ci_for(workflow, incident)
        hypotheses = [
            {"cause": row.cause, "confidence": row.confidence}
            for row in self.session.scalars(select(RCAHypothesis).where(RCAHypothesis.workflow_id == workflow.id))
        ]
        runbooks = self._certified_manifests(workflow.tenant_id, ci.external_id if ci else "")
        result = self._agent(
            workflow,
            RemediationAgent(),
            RemediationInput(
                kind=kind,
                hypotheses=hypotheses,
                runbooks=runbooks,
                ci_class=ci.ci_class if ci else "",
                environment=ci.environment if ci else "",
                legal_hold=bool(context.get("legal_hold")),
                archive_required=bool(context.get("archive_required")),
                retention_days=int(context.get("retention_days") or 7),
            ),
            actor_id,
        )
        chosen = (result.structured_output or {}).get("plan")
        if not chosen:
            self.orch.transition(workflow, "ESCALATED", detail={"reason": "no_certified_runbook"})
            return
        manifest = chosen["runbook"]
        parameters = chosen["parameters"]
        plan_hash = hashlib.sha256(
            json.dumps({"slug": manifest["slug"], "version": manifest["version"], "parameters": parameters}, sort_keys=True).encode()
        ).hexdigest()
        definition = self.session.scalar(
            select(RunbookDefinition).where(
                RunbookDefinition.tenant_id == workflow.tenant_id,
                RunbookDefinition.slug == manifest["slug"],
                RunbookDefinition.version == manifest["version"],
            )
        )
        plan = RemediationPlan(
            id=new_id("pln"),
            tenant_id=workflow.tenant_id,
            workflow_id=workflow.id,
            summary=manifest["name"],
            runbook_id=definition.id if definition else None,
            runbook_version=manifest["version"],
            parameters=parameters,
            expected_impact=manifest["description"],
            rollback_available=bool(manifest.get("rollback_defined")),
            risk_level=manifest.get("risk", "high"),
            status="proposed",
            plan_hash=plan_hash,
        )
        self.session.add(plan)
        self.session.flush()
        self.orch.transition(workflow, "POLICY_CHECK")

    def _policy(self, workflow: Workflow, actor_id: str, *, required_role: str) -> None:
        plan = self._latest_plan(workflow)
        control = self.ops.control_for(workflow.tenant_id)
        certified = plan.runbook_id is not None
        result = self._agent(
            workflow,
            GovernanceAgent(),
            GovernanceInput(
                autonomy_level=control.autonomy_level,
                l4_enabled=self.settings.autonomy_l4_enabled,
                risk_level=plan.risk_level,
                certified=certified,
                emergency_stop=control.emergency_stop,
                rollback_defined=plan.rollback_available,
                conflicting_change=False,
                required_role=required_role,
            ),
            actor_id,
        )
        if result.structured_output.get("automatic"):
            self.orch.transition(workflow, "PRECHECKING", detail={"policy": result.summary})
            return
        incident = self.session.get(Incident, workflow.incident_id) if workflow.incident_id else None
        ci = self._ci_for(workflow, incident)
        self.session.add(
            ApprovalRequest(
                id=new_id("apr"),
                tenant_id=workflow.tenant_id,
                workflow_id=workflow.id,
                plan_id=plan.id,
                required_role=required_role,
                status="pending",
                expires_at=_now() + timedelta(minutes=30),
                plan_hash=plan.plan_hash,
                parameters=plan.parameters,
                runbook_version=plan.runbook_version,
                target_ci_id=ci.id if ci else None,
            )
        )
        self.session.flush()
        self.orch.transition(workflow, "AWAITING_APPROVAL", detail={"reason": result.summary})

    def _precheck(self, workflow: Workflow) -> None:
        plan = self._latest_plan(workflow)
        definition = self.session.get(RunbookDefinition, plan.runbook_id) if plan.runbook_id else None
        if definition is None:
            self.orch.transition(workflow, "FAILED", detail={"reason": "runbook_missing"})
            return
        sandbox = self._sandbox(workflow)
        try:
            result = self.automation.precheck(definition.slug, parameters=dict(plan.parameters or {}), sandbox=sandbox)
        except (ForbiddenError, IntegrationError) as exc:
            self.orch.transition(workflow, "FAILED", detail={"reason": exc.message})
            return
        if definition.checksum != result["checksum"]:
            self.orch.transition(workflow, "FAILED", detail={"reason": "checksum_mismatch"})
            return
        self.orch.transition(workflow, "EXECUTING", detail={"precheck": result["summary"]})

    def _execute(self, workflow: Workflow) -> None:
        plan = self._latest_plan(workflow)
        definition = self.session.get(RunbookDefinition, plan.runbook_id)
        existing = self.session.scalar(
            select(AutomationExecution).where(AutomationExecution.workflow_id == workflow.id)
        )
        sandbox = Path(existing.external_execution_id) if existing and existing.external_execution_id else self._sandbox(workflow)
        if existing and existing.external_execution_id and self._action_landed(definition.slug, sandbox):
            existing.status = "succeeded"
            existing.phase = "verify"
            self.orch.transition(workflow, "VALIDATING", detail={"reconciled": True})
            return
        if existing is None:
            existing = AutomationExecution(
                id=new_id("exe"),
                tenant_id=workflow.tenant_id,
                workflow_id=workflow.id,
                plan_id=plan.id,
                runbook_id=definition.id,
                target_ci_id=plan and None,
                external_execution_id=str(sandbox),
                status="running",
                phase="execute",
                parameters=dict(plan.parameters or {}),
                idempotency_key=f"{workflow.id}:{definition.slug}",
                started_at=_now(),
            )
            self.session.add(existing)
            self.session.flush()
        try:
            result = self.automation.execute(
                definition.slug,
                parameters=dict(plan.parameters or {}),
                sandbox=sandbox,
                action="execute",
            )
        except (ForbiddenError, IntegrationError) as exc:
            existing.status = "failed"
            existing.result = {"error": exc.message}
            self.orch.transition(workflow, "FAILED", detail={"reason": exc.message})
            return
        existing.status = "succeeded"
        existing.phase = "verify"
        existing.result = _jsonable(result)
        existing.finished_at = _now()
        self._maybe_change(workflow, definition)
        self.orch.transition(workflow, "VALIDATING")

    def _validate_incident(self, workflow: Workflow, actor_id: str) -> None:
        incident = self.session.get(Incident, workflow.incident_id)
        ci = self.session.get(ConfigurationItem, incident.ci_id) if incident and incident.ci_id else None
        entity_id = ((ci.attributes or {}) if ci else {}).get("dynatrace_entity_id")
        observations = list(
            self.session.scalars(
                select(MetricObservation).where(MetricObservation.tenant_id == workflow.tenant_id, MetricObservation.entity_id == (entity_id or ""))
            )
        )
        pre_cpu = _last_value(observations, "cpu")
        pre_memory = _last_value(observations, "memory")
        health = getattr(self.dyna, "incident", {}).get("after_restart", {}) if hasattr(self.dyna, "incident") else {}
        result = self._agent(
            workflow,
            ValidationAgent(),
            ValidationInput(
                kind="incident",
                entity_id=entity_id,
                pre_cpu=pre_cpu,
                pre_memory=pre_memory,
                error_rate_after=health.get("error_rate"),
                synthetic_ok=health.get("synthetic_ok"),
            ),
            actor_id,
        )
        self._finish_validation(workflow, incident, result)

    def _validate_capacity(self, workflow: Workflow, actor_id: str) -> None:
        context = self._capacity_context(workflow)
        execution = self.session.scalar(select(AutomationExecution).where(AutomationExecution.workflow_id == workflow.id))
        deleted = int((execution.result or {}).get("deleted_bytes") or 0) if execution else 0
        ci = self._ci_for(workflow, None)
        opened = []
        if ci is not None:
            opened = list(
                self.session.scalars(
                    select(Incident).where(Incident.tenant_id == workflow.tenant_id, Incident.ci_id == ci.id)
                )
            )
        result = self._agent(
            workflow,
            ValidationAgent(),
            ValidationInput(
                kind="capacity",
                current_utilization=context["current_utilization"],
                log_share_of_disk=context["log_share_of_disk"],
                deleted_bytes=deleted,
                log_bytes_before=context["log_bytes_before"],
                growth_per_hour=context["growth_per_hour"],
                service_healthy=context["service_healthy"],
                incidents_during_window=len(opened),
            ),
            actor_id,
        )
        self._finish_validation(workflow, None, result, prevented=True)

    def _finish_validation(self, workflow: Workflow, incident: Incident | None, result, *, prevented: bool = False) -> None:
        execution = self.session.scalar(select(AutomationExecution).where(AutomationExecution.workflow_id == workflow.id))
        self.session.add(
            ValidationResult(
                id=new_id("val"),
                tenant_id=workflow.tenant_id,
                workflow_id=workflow.id,
                automation_execution_id=execution.id if execution else None,
                status="passed" if result.structured_output.get("passed") else "failed",
                checks=_jsonable(result.structured_output.get("checks")),
                summary=result.summary,
            )
        )
        note = result.summary
        if incident is not None:
            self._record_note(incident, note)
            self._evidence(workflow, "validation", note, "validation", result.structured_output, incident.id)
        elif prevented:
            self._evidence(workflow, "validation", note, "validation", result.structured_output, None)
            if result.structured_output.get("passed"):
                self._close_capacity_change(workflow, note)
        self.session.add(
            Notification(
                id=new_id("ntf"),
                tenant_id=workflow.tenant_id,
                workflow_id=workflow.id,
                channel="operator-console",
                recipient="on-call SRE" if incident is not None else "on-call DBA",
                subject=(incident.title if incident is not None else "Disk capacity prevented")[:300],
                body=note,
                status="recorded",
            )
        )
        if not result.structured_output.get("passed"):
            self.orch.transition(workflow, "FAILED", detail={"reason": result.summary})
            return
        target = "PREVENTED" if prevented else "RESOLVED"
        self.orch.transition(workflow, target, detail={"validation": result.summary})

    def _record_note(self, incident: Incident, note: str) -> None:
        notes = list(incident.work_notes or [])
        notes.append(note)
        incident.work_notes = notes
        try:
            self.snow.add_work_note(incident.external_number or incident.external_sys_id, note)
        except IntegrationError:
            notes.append("ServiceNow work note was not accepted")
            incident.work_notes = notes
        if self.settings.execution_mode == "SIMULATOR" or self.settings.incident_auto_resolve:
            try:
                self.snow.update_state(incident.external_number, "6", {"close_code": "Solved (Permanently)", "close_notes": note})
                incident.state = "resolved"
                incident.resolved_at = _now()
            except IntegrationError:
                notes.append("ServiceNow closure was not accepted")
                incident.work_notes = notes

    def _agent(self, workflow: Workflow, agent, payload, actor_id: str):
        context = AgentContext(
            workflow_id=workflow.id,
            correlation_id=workflow.correlation_id,
            tenant_id=workflow.tenant_id,
            actor_id=actor_id,
            execution_mode=self.settings.execution_mode,  # type: ignore[arg-type]
            deadline=_now() + timedelta(minutes=20),
        )
        started = _now()
        token = ports_var.set(
            Ports(
                settings=self.settings,
                snow=self.snow,
                dyna=self.dyna,
                automation=self.automation,
                narrative=self.narrative,
            )
        )
        try:
            result = asyncio.run(agent.execute(context, payload))
        finally:
            ports_var.reset(token)
        output = _jsonable(result.structured_output)
        row = AgentExecution(
            id=new_id("agt"),
            tenant_id=workflow.tenant_id,
            workflow_id=workflow.id,
            agent_name=agent.name,
            status=result.status,
            summary=result.summary,
            input_payload=_jsonable(payload.model_dump()),
            output_payload=output,
            confidence=result.confidence,
            model=str(output.get("model") or ""),
            token_input=int(output.get("token_input") or 0),
            token_output=int(output.get("token_output") or 0),
            latency_ms=int((_now() - started).total_seconds() * 1000),
            started_at=started,
            finished_at=_now(),
        )
        self.session.add(row)
        self.session.flush()
        for name in result.tool_call_ids:
            self.session.add(
                ToolExecution(
                    id=new_id("tol"),
                    tenant_id=workflow.tenant_id,
                    agent_execution_id=row.id,
                    tool_name=name,
                    status="completed",
                    request_payload={},
                    response_payload={},
                    started_at=started,
                    finished_at=_now(),
                )
            )
        self.ops.append_outbox(
            tenant_id=workflow.tenant_id,
            workflow_id=workflow.id,
            event_type="agent.completed",
            payload={"agent": agent.name, "status": result.status},
        )
        result.structured_output = output
        return result

    def _evidence(self, workflow, kind, summary, source, payload, incident_id) -> None:
        raw = json.dumps(payload, default=str, sort_keys=True).encode()
        self.session.add(
            EvidenceArtifact(
                id=new_id("evd"),
                tenant_id=workflow.tenant_id,
                workflow_id=workflow.id,
                incident_id=incident_id,
                kind=kind,
                summary=summary,
                source=source,
                provenance={"mode": self.settings.execution_mode},
                content_hash=hashlib.sha256(raw).hexdigest(),
                content_ref="",
            )
        )

    def _store_series(self, workflow: Workflow, series: dict) -> None:
        for metric_key, body in series.items():
            for point in body.get("points") or []:
                stamp = point["timestamp"]
                if isinstance(stamp, str):
                    stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                self.session.add(
                    MetricObservation(
                        id=new_id("met"),
                        tenant_id=workflow.tenant_id,
                        entity_id=body.get("entity_id") or "",
                        metric_key=metric_key,
                        observed_at=stamp,
                        value=float(point["value"]),
                        unit=point.get("unit") or "percent",
                        source=body.get("source") or "",
                        query_reference=body.get("query_reference") or "",
                    )
                )

    def _store_hypotheses(self, workflow: Workflow, result) -> None:
        for index, item in enumerate(result.structured_output.get("hypotheses") or [], start=1):
            self.session.add(
                RCAHypothesis(
                    id=new_id("hyp"),
                    tenant_id=workflow.tenant_id,
                    workflow_id=workflow.id,
                    rank=index,
                    cause=item["cause"],
                    confidence=float(item["confidence"]),
                    evidence_ids=item.get("evidence_ids") or [],
                    limitations=item.get("limitations") or [],
                    requires_human_review=bool(item.get("requires_human_review", True)),
                )
            )
        self._evidence(workflow, "rca", result.summary, "analysis", result.structured_output, workflow.incident_id)

    def _certified_manifests(self, tenant_id: str, external_id: str) -> list[dict]:
        found = []
        now = _now()
        for slug in _KNOWN_RUNBOOKS:
            try:
                manifest = self.automation.load(slug)
            except IntegrationError:
                continue
            definition = self.session.scalar(
                select(RunbookDefinition).where(
                    RunbookDefinition.tenant_id == tenant_id,
                    RunbookDefinition.slug == slug,
                    RunbookDefinition.checksum == manifest["checksum"],
                )
            )
            if definition is None:
                continue
            cert = self.session.scalar(
                select(RunbookCertification).where(
                    RunbookCertification.runbook_id == definition.id,
                    RunbookCertification.status == "certified",
                )
            )
            if cert is None or (cert.expires_at and cert.expires_at < now):
                continue
            allowed = (cert.scope or {}).get("external_ids") or []
            if external_id and allowed and external_id not in allowed:
                continue
            found.append(manifest)
        return found

    def _latest_plan(self, workflow: Workflow) -> RemediationPlan:
        plan = self.session.scalar(
            select(RemediationPlan).where(RemediationPlan.workflow_id == workflow.id).order_by(RemediationPlan.created_at.desc())
        )
        if plan is None:
            raise IntegrationError("Workflow has no remediation plan")
        return plan

    def _ci_for(self, workflow: Workflow, incident: Incident | None) -> ConfigurationItem | None:
        if incident and incident.ci_id:
            return self.session.get(ConfigurationItem, incident.ci_id)
        context = self._capacity_context(workflow)
        external = context.get("ci_external_id")
        if not external:
            return None
        return self.session.scalar(
            select(ConfigurationItem).where(
                ConfigurationItem.tenant_id == workflow.tenant_id,
                ConfigurationItem.external_id == external,
            )
        )

    def _capacity_context(self, workflow: Workflow) -> dict:
        try:
            return json.loads(workflow.summary)
        except (TypeError, json.JSONDecodeError):
            return {}

    def _sandbox(self, workflow: Workflow) -> Path:
        path = Path(tempfile.gettempdir()) / "aegisops" / workflow.id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _prepare_capacity_sandbox(self, workflow: Workflow) -> None:
        logs = self._sandbox(workflow) / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        old = logs / "claims-old.log"
        fresh = logs / "claims-fresh.log"
        if not old.exists():
            old.write_bytes(b"x" * 2000)
            aged = time.time() - 10 * 86400
            os.utime(old, (aged, aged))
        if not fresh.exists():
            fresh.write_bytes(b"y" * 500)
        nested = logs / "nested"
        nested.mkdir(exist_ok=True)
        kept = nested / "kept.log"
        if not kept.exists():
            kept.write_text("keep")
        before = old.stat().st_size + fresh.stat().st_size if old.exists() else fresh.stat().st_size
        context = self._capacity_context(workflow)
        context["log_bytes_before"] = before
        workflow.summary = json.dumps(context)

    def _action_landed(self, slug: str, sandbox: Path) -> bool:
        if slug == "restart-claims-service":
            return (sandbox / "claims-api.restarted").exists()
        if slug == "cleanup-approved-logs":
            logs = sandbox / "logs"
            return logs.exists() and not (logs / "claims-old.log").exists() and (sandbox / "volume.extended").exists()
        return False

    def _maybe_change(self, workflow: Workflow, definition: RunbookDefinition) -> None:
        if definition.slug != "cleanup-approved-logs":
            return
        context = self._capacity_context(workflow)
        try:
            opened = self.snow.create_standard_change(
                ci_id=str(context.get("ci_external_id") or ""),
                summary=definition.name,
            )
        except IntegrationError as exc:
            context["change_error"] = exc.message
            workflow.summary = json.dumps(context)
            return
        self.session.add(
            ChangeRecord(
                id=new_id("chg"),
                tenant_id=workflow.tenant_id,
                external_number=str(opened.get("number") or ""),
                external_sys_id=str(opened.get("sys_id") or ""),
                workflow_id=workflow.id,
                state=str(opened.get("state") or "implement"),
                summary=definition.name,
            )
        )
        context["change_number"] = opened.get("number") or ""
        workflow.summary = json.dumps(context)

    def _close_capacity_change(self, workflow: Workflow, note: str) -> None:
        change = self.session.scalar(select(ChangeRecord).where(ChangeRecord.workflow_id == workflow.id))
        if change is None or not change.external_number:
            return
        close = self.settings.execution_mode == "SIMULATOR" or self.settings.change_auto_close
        try:
            self.snow.add_change_note(change.external_number, note)
            if close:
                self.snow.close_change(change.external_number, note)
                change.state = "closed"
        except IntegrationError as exc:
            context = self._capacity_context(workflow)
            context["change_error"] = exc.message
            workflow.summary = json.dumps(context)
        self._evidence(
            workflow,
            "change",
            f"{change.external_number} {change.state}",
            "servicenow",
            {"number": change.external_number, "state": change.state, "note": note},
            None,
        )

    def _open_workflow(self, tenant_id: str, *, incident_id: str) -> Workflow | None:
        return self.session.scalar(
            select(Workflow)
            .where(
                Workflow.tenant_id == tenant_id,
                Workflow.incident_id == incident_id,
                Workflow.state.notin_(["FAILED", "CANCELLED"]),
            )
            .order_by(Workflow.created_at.desc())
        )

    def ensure_runbook(self, tenant_id: str, slug: str, external_ids: list[str]) -> RunbookDefinition:
        manifest = self.automation.load(slug)
        row = self.session.scalar(
            select(RunbookDefinition).where(
                RunbookDefinition.tenant_id == tenant_id,
                RunbookDefinition.slug == slug,
                RunbookDefinition.version == manifest["version"],
            )
        )
        if row is None:
            row = RunbookDefinition(
                id=new_id("rbk"),
                tenant_id=tenant_id,
                slug=slug,
                version=manifest["version"],
                name=manifest["name"],
                description=manifest.get("description") or "",
                target_class=manifest.get("target_class") or "",
                parameters_schema=manifest.get("parameters"),
                checksum=manifest["checksum"],
                rollback_defined=bool(manifest.get("rollback_defined")),
                path=manifest["path"],
            )
            self.session.add(row)
            self.session.flush()
        else:
            row.name = manifest["name"]
            row.description = manifest.get("description") or ""
            row.parameters_schema = manifest.get("parameters")
            row.checksum = manifest["checksum"]
            row.rollback_defined = bool(manifest.get("rollback_defined"))
        cert = self.session.scalar(select(RunbookCertification).where(RunbookCertification.runbook_id == row.id))
        if cert is None:
            self.session.add(
                RunbookCertification(
                    id=new_id("rbc"),
                    tenant_id=tenant_id,
                    runbook_id=row.id,
                    status="certified",
                    certified_by="fixture",
                    certified_at=_now(),
                    expires_at=_now() + timedelta(days=30),
                    evidence_ref=manifest["path"],
                    scope={"external_ids": external_ids},
                )
            )
            self.session.flush()
        return row


def tick(session: Session, settings: Settings, worker_id: str) -> int:
    from aegisops.runtime.leases import LeaseManager

    rows = list(
        session.scalars(
            select(Workflow).where(Workflow.state.notin_(list(TERMINAL | {"AWAITING_APPROVAL"})))
        )
    )
    processed = 0
    leases = LeaseManager(session)
    engine = OperationsEngine(session, settings)
    for workflow in rows:
        if not leases.acquire(
            worker_id=worker_id,
            resource_type="workflow",
            resource_id=workflow.id,
            ttl_seconds=60,
            tenant_id=workflow.tenant_id,
        ):
            continue
        engine.resume(workflow, actor_id=worker_id)
        leases.release(worker_id=worker_id, resource_type="workflow", resource_id=workflow.id)
        processed += 1
    return processed
