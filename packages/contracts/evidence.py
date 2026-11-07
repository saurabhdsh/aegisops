from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    timestamp: datetime
    value: float
    unit: str


class MetricSeries(BaseModel):
    entity_id: str
    metric_key: str
    points: list[MetricPoint]
    source: str
    query_reference: str | None = None


class EvidenceArtifactRecord(BaseModel):
    id: str
    kind: str
    summary: str
    source: str
    content_hash: str
    provenance: dict = Field(default_factory=dict)
