"""Relational model. Timestamps are timezone-aware UTC. Connector secrets are stored only as ciphertext."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from aegisops.core.exceptions import AuditImmutableError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are rejected; use timezone-aware UTC")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_pair"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuthSession(Base):
    """Server-side session record. Only a hash of the token is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "name", name="uq_integrations_kind_name"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(500), default="")
    auth_mode: Mapped[str] = mapped_column(String(32), default="")
    secret_ref: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_health_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ConnectorSetting(Base):
    """Non-secret connection fields plus an encrypted secret bundle."""

    __tablename__ = "connector_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", name="uq_connector_settings_kind"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(String(500), default="")
    auth_mode: Mapped[str] = mapped_column(String(32), default="")
    public_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class BusinessService(Base):
    __tablename__ = "business_services"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_business_services_external"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    criticality: Mapped[str] = mapped_column(String(32), default="unknown")
    owner: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ConfigurationItem(Base):
    __tablename__ = "configuration_items"
    __table_args__ = (UniqueConstraint("tenant_id", "source", "external_id", name="uq_ci_source_external"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    ci_class: Mapped[str] = mapped_column(String(80), default="")
    environment: Mapped[str] = mapped_column(String(32), default="unknown")
    criticality: Mapped[str] = mapped_column(String(32), default="unknown")
    business_service_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_services.id", ondelete="SET NULL"), nullable=True
    )
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_sys_id", name="uq_incidents_external"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_incidents_idempotency"),
        Index("ix_incidents_tenant_state", "tenant_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="servicenow")
    external_number: Mapped[str] = mapped_column(String(64), default="")
    external_sys_id: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(32), default="open")
    source_state: Mapped[str] = mapped_column(String(64), default="")
    priority: Mapped[str] = mapped_column(String(16), default="")
    severity: Mapped[str] = mapped_column(String(16), default="")
    ci_id: Mapped[str | None] = mapped_column(ForeignKey("configuration_items.id"), nullable=True)
    business_service_id: Mapped[str | None] = mapped_column(ForeignKey("business_services.id"), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    work_notes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CorrelationGroup(Base):
    __tablename__ = "correlation_groups"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    summary: Mapped[str] = mapped_column(String(500), default="")
    entity_ref: Mapped[str] = mapped_column(String(200), default="")
    symptom: Mapped[str] = mapped_column(String(200), default="")
    alert_count: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(32), default="open")
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "idempotency_key", name="uq_events_idempotency"),
        Index("ix_events_tenant_received", "tenant_id", "received_at"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(120), default="")
    event_type: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(32), default="")
    entity_ref: Mapped[str] = mapped_column(String(200), default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    correlation_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("correlation_groups.id"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


WORKFLOW_STATES = (
    "RECEIVED",
    "NORMALIZING",
    "ENRICHING",
    "INVESTIGATING",
    "ANALYZING",
    "PLANNING",
    "POLICY_CHECK",
    "AWAITING_APPROVAL",
    "PRECHECKING",
    "EXECUTING",
    "VALIDATING",
    "RESOLVED",
    "PREVENTED",
    "ESCALATED",
    "FAILED",
    "CANCELLED",
)


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_workflows_idempotency"),
        CheckConstraint(
            "state IN (" + ", ".join(f"'{state}'" for state in WORKFLOW_STATES) + ")",
            name="workflow_state",
        ),
        Index("ix_workflows_tenant_state", "tenant_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), default="RECEIVED")
    correlation_id: Mapped[str] = mapped_column(String(48), index=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    correlation_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("correlation_groups.id"), nullable=True
    )
    autonomy_level: Mapped[str] = mapped_column(String(8), default="L3")
    execution_mode: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(32))
    sequence: Mapped[int] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    agent_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text, default="")
    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str] = mapped_column(String(80), default="")
    token_input: Mapped[int] = mapped_column(Integer, default=0)
    token_output: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    agent_execution_id: Mapped[str] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("workflows.id"), nullable=True, index=True)
    agent_execution_id: Mapped[str | None] = mapped_column(ForeignKey("agent_executions.id"), nullable=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(80))
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    content_ref: Mapped[str] = mapped_column(String(500), default="")
    media_type: Mapped[str] = mapped_column(String(80), default="application/json")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MetricObservation(Base):
    __tablename__ = "metric_observations"
    __table_args__ = (Index("ix_metrics_entity_key_time", "tenant_id", "entity_id", "metric_key", "observed_at"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    entity_id: Mapped[str] = mapped_column(String(200))
    metric_key: Mapped[str] = mapped_column(String(120))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(64))
    query_reference: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RCAHypothesis(Base):
    __tablename__ = "rca_hypotheses"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    agent_execution_id: Mapped[str | None] = mapped_column(ForeignKey("agent_executions.id"), nullable=True)
    rank: Mapped[int] = mapped_column(Integer)
    cause: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    limitations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RunbookDefinition(Base):
    __tablename__ = "runbook_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", "version", name="uq_runbook_version"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    slug: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    target_class: Mapped[str] = mapped_column(String(80), default="")
    parameters_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64))
    rollback_defined: Mapped[bool] = mapped_column(Boolean, default=False)
    path: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RunbookCertification(Base):
    __tablename__ = "runbook_certifications"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    runbook_id: Mapped[str] = mapped_column(ForeignKey("runbook_definitions.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    certified_by: Mapped[str] = mapped_column(String(48), default="")
    certified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    evidence_ref: Mapped[str] = mapped_column(String(300), default="")
    scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RemediationPlan(Base):
    __tablename__ = "remediation_plans"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    runbook_id: Mapped[str | None] = mapped_column(ForeignKey("runbook_definitions.id"), nullable=True)
    runbook_version: Mapped[str] = mapped_column(String(40), default="")
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_impact: Mapped[str] = mapped_column(Text, default="")
    rollback_available: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="high")
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    plan_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("remediation_plans.id"), index=True)
    required_role: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    plan_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    runbook_version: Mapped[str] = mapped_column(String(40))
    target_ci_id: Mapped[str | None] = mapped_column(ForeignKey("configuration_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AutomationExecution(Base):
    __tablename__ = "automation_executions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_automation_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("remediation_plans.id"), nullable=True)
    runbook_id: Mapped[str | None] = mapped_column(ForeignKey("runbook_definitions.id"), nullable=True)
    target_ci_id: Mapped[str | None] = mapped_column(ForeignKey("configuration_items.id"), nullable=True)
    external_execution_id: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    phase: Mapped[str] = mapped_column(String(32), default="precheck")
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    automation_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("automation_executions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32))
    checks: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ChangeRecord(Base):
    __tablename__ = "change_records"
    __table_args__ = (UniqueConstraint("tenant_id", "external_sys_id", name="uq_changes_external"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    external_number: Mapped[str] = mapped_column(String(64), default="")
    external_sys_id: Mapped[str] = mapped_column(String(64), default="")
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("workflows.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="open")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("workflows.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(32))
    recipient: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(48), default="")
    correlation_id: Mapped[str] = mapped_column(String(48), default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("workflow_id", "sequence", name="uq_outbox_sequence"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class WorkerLease(Base):
    __tablename__ = "worker_leases"
    __table_args__ = (UniqueConstraint("resource_type", "resource_id", name="uq_worker_lease_resource"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    worker_id: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(80))
    acquired_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OperationalControl(Base):
    """Per-tenant kill switch and autonomy selection. One row per tenant."""

    __tablename__ = "operational_controls"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), unique=True)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    autonomy_level: Mapped[str] = mapped_column(String(8), default="L3")
    freeze_reason: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str] = mapped_column(String(48), default="")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


@event.listens_for(AuditEvent, "before_update")
def _block_audit_update(mapper, connection, target) -> None:  # type: ignore[no-untyped-def]
    raise AuditImmutableError()


@event.listens_for(AuditEvent, "before_delete")
def _block_audit_delete(mapper, connection, target) -> None:  # type: ignore[no-untyped-def]
    raise AuditImmutableError()
