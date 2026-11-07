from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    workflow_id: str
    correlation_id: str
    tenant_id: str
    actor_id: str
    execution_mode: Literal["LIVE", "SANDBOX", "SIMULATOR"]
    deadline: datetime
    evidence_ids: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    status: Literal["completed", "failed", "waiting_approval", "insufficient_evidence"]
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    structured_output: dict
    tool_call_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None
