"""Shared API shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str | None = None
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    execution_mode: str
    database: str


class PrincipalResponse(BaseModel):
    id: str
    email: str
    display_name: str
    tenant_id: str
    tenant_slug: str
    roles: list[str]


class LoginRequest(BaseModel):
    tenant_slug: str
    email: str
    password: str


class LoginResponse(BaseModel):
    token_type: str = "bearer"
    access_token: str
    csrf_token: str
    expires_at: datetime
    user: PrincipalResponse


class IncidentResponse(BaseModel):
    id: str
    number: str
    title: str
    description: str
    state: str
    source_state: str
    priority: str
    severity: str
    ci_id: str | None
    business_service_id: str | None
    opened_at: datetime | None
    resolved_at: datetime | None
    work_notes: list[str] = []
    ci_name: str = ""
    service_name: str = ""
    version: int

    model_config = {"from_attributes": True}


class EvidenceResponse(BaseModel):
    id: str
    kind: str
    summary: str
    source: str
    content_hash: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowResponse(BaseModel):
    id: str
    kind: str
    state: str
    correlation_id: str
    execution_mode: str
    autonomy_level: str
    version: int
    cancel_requested: bool
    incident_id: str | None
    summary: str
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class WorkflowStepResponse(BaseModel):
    id: str
    name: str
    state: str
    sequence: int
    detail: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CancelResponse(BaseModel):
    state: str
    cancel_requested: bool
    external_action_stopped: bool


class AgentCatalogItem(BaseModel):
    id: str
    name: str
    responsibility: str
    executable: bool


class AgentExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    agent_name: str
    status: str
    summary: str
    confidence: float | None
    model: str
    token_input: int
    token_output: int
    latency_ms: int
    error: str
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ToolCallResponse(BaseModel):
    id: str
    tool_name: str
    status: str
    error: str
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ApprovalResponse(BaseModel):
    id: str
    workflow_id: str
    plan_id: str
    required_role: str
    status: str
    expires_at: datetime
    plan_hash: str
    runbook_version: str
    target_ci_id: str | None

    model_config = {"from_attributes": True}


class DecisionRequest(BaseModel):
    reason: str = ""


class RunbookResponse(BaseModel):
    id: str
    slug: str
    version: str
    name: str
    description: str
    target_class: str
    checksum: str
    rollback_defined: bool

    model_config = {"from_attributes": True}


class CertificationResponse(BaseModel):
    id: str
    status: str
    certified_by: str
    certified_at: datetime | None
    expires_at: datetime | None
    scope: dict | None

    model_config = {"from_attributes": True}


class IntegrationResponse(BaseModel):
    id: str
    kind: str
    name: str
    base_url: str
    auth_mode: str
    secret_ref: str
    status: str
    capabilities: dict | None
    last_health_at: datetime | None
    last_health_status: str
    last_error: str

    model_config = {"from_attributes": True}


class AuditResponse(BaseModel):
    id: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str
    correlation_id: str
    payload: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ControlResponse(BaseModel):
    emergency_stop: bool
    autonomy_level: str
    freeze_reason: str
    updated_at: datetime


class AutonomyRequest(BaseModel):
    level: str


class EmergencyStopRequest(BaseModel):
    reason: str = ""


class AssetResponse(BaseModel):
    id: str
    name: str
    ci_class: str
    environment: str
    criticality: str
    external_id: str


class MetricResponse(BaseModel):
    id: str
    entity_id: str
    metric_key: str
    observed_at: datetime
    value: float
    unit: str
    source: str
    query_reference: str

    model_config = {"from_attributes": True}
