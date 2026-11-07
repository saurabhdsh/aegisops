from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ApprovalRequestRecord(BaseModel):
    id: str
    workflow_id: str
    plan_hash: str
    runbook_version: str
    required_role: str
    status: Literal["pending", "approved", "rejected", "expired"]
    expires_at: datetime
    target_ci_id: str | None = None


class ApprovalDecisionRecord(BaseModel):
    id: str
    request_id: str
    actor_id: str
    decision: Literal["approved", "rejected"]
    reason: str
