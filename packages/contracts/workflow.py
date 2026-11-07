from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


WorkflowState = Literal[
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
]


class WorkflowRecord(BaseModel):
    id: str
    tenant_id: str
    kind: Literal["incident", "capacity"]
    state: WorkflowState
    correlation_id: str
    execution_mode: Literal["LIVE", "SANDBOX", "SIMULATOR"]
    autonomy_level: Literal["L3", "L4"]
    version: int
    cancel_requested: bool = False
    deadline: datetime | None = None
    incident_id: str | None = None
    summary: str = ""
