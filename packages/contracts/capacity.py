from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ForecastPoint(BaseModel):
    timestamp: datetime
    value: float
    lower: float | None = None
    upper: float | None = None


class CapacityAssessment(BaseModel):
    asset_id: str
    metric_key: str
    current_utilization: float
    growth_per_hour: float | None
    estimated_exhaustion_at: datetime | None
    method: str
    uncertainty: str
    criticality: str
    recommended_actions: list[str] = Field(default_factory=list)
