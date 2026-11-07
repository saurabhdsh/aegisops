from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IncidentRecord(BaseModel):
    id: str
    tenant_id: str
    number: str
    sys_id: str | None = None
    title: str
    description: str = ""
    state: str
    priority: str
    configuration_item_id: str | None = None
    business_service_id: str | None = None
    opened_at: datetime | None = None
    work_notes: list[str] = Field(default_factory=list)


class ConfigurationItem(BaseModel):
    id: str
    tenant_id: str
    external_id: str
    name: str
    ci_class: str
    environment: str
    criticality: str
    source: str


class HistoricalIncident(BaseModel):
    number: str
    title: str
    resolution_summary: str
    similarity_reason: str
    opened_at: datetime | None = None


class ChangeRecord(BaseModel):
    number: str
    sys_id: str | None = None
    state: str
    summary: str
    opened_at: datetime | None = None
