"""Tenant-scoped reads and the small set of writes the foundation owns."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from aegisops.core.exceptions import ConflictError, NotFoundError
from aegisops.core.identifiers import new_id
from aegisops.persistence.models import (
    AgentExecution,
    ApprovalDecision,
    ApprovalRequest,
    AuditEvent,
    AutomationExecution,
    BusinessService,
    ConfigurationItem,
    EvidenceArtifact,
    Incident,
    Integration,
    MetricObservation,
    OperationalControl,
    OutboxEvent,
    RunbookCertification,
    RunbookDefinition,
    Tenant,
    ToolExecution,
    Workflow,
    WorkflowStep,
)


class OperationsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def tenant_by_slug(self, slug: str) -> Tenant | None:
        return self.session.scalar(select(Tenant).where(Tenant.slug == slug))

    def require_tenant(self, slug: str) -> Tenant:
        tenant = self.tenant_by_slug(slug)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return tenant

    def control_for(self, tenant_id: str) -> OperationalControl:
        control = self.session.scalar(
            select(OperationalControl).where(OperationalControl.tenant_id == tenant_id)
        )
        if control is None:
            raise NotFoundError("Operational control is not configured")
        return control

    def demo_enabled(self, tenant_id: str) -> bool:
        return bool(self.control_for(tenant_id).demo_enabled)

    def list_incidents(self, tenant_id: str, *, limit: int, offset: int) -> tuple[list[Incident], int]:
        base = select(Incident).where(Incident.tenant_id == tenant_id)
        counted = select(func.count()).select_from(Incident).where(Incident.tenant_id == tenant_id)
        if not self.demo_enabled(tenant_id):
            base = base.where(Incident.source != "demo")
            counted = counted.where(Incident.source != "demo")
        total = int(self.session.scalar(counted) or 0)
        rows = list(
            self.session.scalars(base.order_by(Incident.opened_at.desc(), Incident.created_at.desc()).limit(limit).offset(offset))
        )
        return rows, total

    def get_incident(self, tenant_id: str, incident_id: str) -> Incident:
        row = self.session.scalar(
            select(Incident).where(Incident.tenant_id == tenant_id, Incident.id == incident_id)
        )
        if row is None:
            raise NotFoundError("Incident not found")
        return row

    def evidence_for_incident(self, tenant_id: str, incident_id: str) -> list[EvidenceArtifact]:
        self.get_incident(tenant_id, incident_id)
        return list(
            self.session.scalars(
                select(EvidenceArtifact)
                .where(EvidenceArtifact.tenant_id == tenant_id, EvidenceArtifact.incident_id == incident_id)
                .order_by(EvidenceArtifact.created_at.asc())
            )
        )

    def list_workflows(self, tenant_id: str, *, limit: int, offset: int) -> tuple[list[Workflow], int]:
        demo_ids = select(Incident.id).where(Incident.tenant_id == tenant_id, Incident.source == "demo")
        base = select(Workflow).where(Workflow.tenant_id == tenant_id)
        counted = select(func.count()).select_from(Workflow).where(Workflow.tenant_id == tenant_id)
        if not self.demo_enabled(tenant_id):
            visible = or_(Workflow.incident_id.is_(None), Workflow.incident_id.not_in(demo_ids))
            base = base.where(visible)
            counted = counted.where(visible)
        total = int(self.session.scalar(counted) or 0)
        rows = list(
            self.session.scalars(base.order_by(Workflow.created_at.desc()).limit(limit).offset(offset))
        )
        return rows, total

    def get_workflow(self, tenant_id: str, workflow_id: str) -> Workflow:
        row = self.session.scalar(
            select(Workflow).where(Workflow.tenant_id == tenant_id, Workflow.id == workflow_id)
        )
        if row is None:
            raise NotFoundError("Workflow not found")
        return row

    def steps_for(self, tenant_id: str, workflow_id: str) -> list[WorkflowStep]:
        self.get_workflow(tenant_id, workflow_id)
        return list(
            self.session.scalars(
                select(WorkflowStep)
                .where(WorkflowStep.tenant_id == tenant_id, WorkflowStep.workflow_id == workflow_id)
                .order_by(WorkflowStep.sequence.asc())
            )
        )

    def outbox_after(self, tenant_id: str, workflow_id: str, sequence: int) -> list[OutboxEvent]:
        self.get_workflow(tenant_id, workflow_id)
        return list(
            self.session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.tenant_id == tenant_id,
                    OutboxEvent.workflow_id == workflow_id,
                    OutboxEvent.sequence > sequence,
                )
                .order_by(OutboxEvent.sequence.asc())
            )
        )

    def get_agent_execution(self, tenant_id: str, execution_id: str) -> AgentExecution:
        row = self.session.scalar(
            select(AgentExecution).where(
                AgentExecution.tenant_id == tenant_id, AgentExecution.id == execution_id
            )
        )
        if row is None:
            raise NotFoundError("Agent execution not found")
        return row

    def tool_calls_for(self, tenant_id: str, execution_id: str) -> list[ToolExecution]:
        self.get_agent_execution(tenant_id, execution_id)
        return list(
            self.session.scalars(
                select(ToolExecution)
                .where(ToolExecution.tenant_id == tenant_id, ToolExecution.agent_execution_id == execution_id)
                .order_by(ToolExecution.created_at.asc())
            )
        )

    def list_approvals(self, tenant_id: str, *, limit: int, offset: int) -> tuple[list[ApprovalRequest], int]:
        total = int(
            self.session.scalar(
                select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.tenant_id == tenant_id)
            )
            or 0
        )
        rows = list(
            self.session.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.tenant_id == tenant_id)
                .order_by(ApprovalRequest.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total

    def get_approval(self, tenant_id: str, approval_id: str) -> ApprovalRequest:
        row = self.session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.tenant_id == tenant_id, ApprovalRequest.id == approval_id
            )
        )
        if row is None:
            raise NotFoundError("Approval request not found")
        return row

    def decisions_for(self, request_id: str) -> list[ApprovalDecision]:
        return list(
            self.session.scalars(
                select(ApprovalDecision)
                .where(ApprovalDecision.request_id == request_id)
                .order_by(ApprovalDecision.created_at.asc())
            )
        )

    def list_runbooks(self, tenant_id: str) -> list[RunbookDefinition]:
        return list(
            self.session.scalars(
                select(RunbookDefinition)
                .where(RunbookDefinition.tenant_id == tenant_id)
                .order_by(RunbookDefinition.slug.asc(), RunbookDefinition.version.asc())
            )
        )

    def get_runbook(self, tenant_id: str, runbook_id: str) -> RunbookDefinition:
        row = self.session.scalar(
            select(RunbookDefinition).where(
                RunbookDefinition.tenant_id == tenant_id, RunbookDefinition.id == runbook_id
            )
        )
        if row is None:
            raise NotFoundError("Runbook not found")
        return row

    def certifications_for(self, tenant_id: str, runbook_id: str) -> list[RunbookCertification]:
        self.get_runbook(tenant_id, runbook_id)
        return list(
            self.session.scalars(
                select(RunbookCertification).where(
                    RunbookCertification.tenant_id == tenant_id,
                    RunbookCertification.runbook_id == runbook_id,
                )
            )
        )

    def list_integrations(self, tenant_id: str) -> list[Integration]:
        return list(
            self.session.scalars(
                select(Integration).where(Integration.tenant_id == tenant_id).order_by(Integration.kind.asc())
            )
        )

    def running_external_execution(self, tenant_id: str, workflow_id: str) -> AutomationExecution | None:
        return self.session.scalar(
            select(AutomationExecution).where(
                AutomationExecution.tenant_id == tenant_id,
                AutomationExecution.workflow_id == workflow_id,
                AutomationExecution.external_execution_id != "",
                AutomationExecution.status.in_(("running", "partial", "pending")),
            )
        )

    def append_outbox(
        self,
        *,
        tenant_id: str,
        workflow_id: str,
        event_type: str,
        payload: dict,
    ) -> OutboxEvent:
        current = self.session.scalar(
            select(func.max(OutboxEvent.sequence)).where(OutboxEvent.workflow_id == workflow_id)
        )
        event = OutboxEvent(
            id=new_id("obx"),
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            sequence=int(current or 0) + 1,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def add_workflow_step(
        self,
        *,
        tenant_id: str,
        workflow: Workflow,
        name: str,
        state: str,
        detail: dict | None = None,
    ) -> WorkflowStep:
        sequence = int(
            self.session.scalar(
                select(func.max(WorkflowStep.sequence)).where(WorkflowStep.workflow_id == workflow.id)
            )
            or 0
        )
        step = WorkflowStep(
            id=new_id("stp"),
            tenant_id=tenant_id,
            workflow_id=workflow.id,
            name=name,
            state=state,
            sequence=sequence + 1,
            detail=detail,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        self.session.add(step)
        self.session.flush()
        return step

    def list_audit(self, tenant_id: str, *, limit: int, offset: int) -> tuple[list[AuditEvent], int]:
        total = int(
            self.session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
            )
            or 0
        )
        rows = list(
            self.session.scalars(
                select(AuditEvent)
                .where(AuditEvent.tenant_id == tenant_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return rows, total

    def list_assets(self, tenant_id: str) -> list[ConfigurationItem]:
        query = select(ConfigurationItem).where(ConfigurationItem.tenant_id == tenant_id)
        if not self.demo_enabled(tenant_id):
            query = query.where(ConfigurationItem.external_id.not_like("demo-%"))
        return list(self.session.scalars(query.order_by(ConfigurationItem.name.asc())))

    def list_services(self, tenant_id: str) -> list[BusinessService]:
        query = select(BusinessService).where(BusinessService.tenant_id == tenant_id)
        if not self.demo_enabled(tenant_id):
            query = query.where(BusinessService.external_id.not_like("demo-%"))
        return list(self.session.scalars(query.order_by(BusinessService.name.asc())))

    def list_metrics(self, tenant_id: str, *, limit: int) -> list[MetricObservation]:
        return list(
            self.session.scalars(
                select(MetricObservation)
                .where(MetricObservation.tenant_id == tenant_id)
                .order_by(MetricObservation.observed_at.desc())
                .limit(limit)
            )
        )

    def add_decision(
        self,
        *,
        tenant_id: str,
        request: ApprovalRequest,
        actor_id: str,
        decision: str,
        reason: str,
    ) -> ApprovalDecision:
        if request.status != "pending":
            raise ConflictError("Approval request is no longer pending", {"status": request.status})
        record = ApprovalDecision(
            id=new_id("apd"),
            tenant_id=tenant_id,
            request_id=request.id,
            actor_id=actor_id,
            decision=decision,
            reason=reason,
        )
        request.status = decision
        self.session.add(record)
        self.session.flush()
        return record


def expiry_from_now(seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
