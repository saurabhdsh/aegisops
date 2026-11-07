from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RemediationPlanRecord(BaseModel):
    id: str
    runbook_id: str
    runbook_version: str
    parameters: dict
    expected_impact: str
    rollback_available: bool
    risk_level: Literal["low", "medium", "high"]
    plan_hash: str


class PrecheckResult(BaseModel):
    runbook_id: str
    target_id: str
    passed: bool
    checks: list[dict] = Field(default_factory=list)
    summary: str


class ExecutionResult(BaseModel):
    execution_id: str
    external_execution_id: str | None
    status: Literal["succeeded", "failed", "partial", "running"]
    summary: str
    log_excerpt: str = ""


class VerificationResult(BaseModel):
    execution_id: str
    status: Literal["verified", "failed", "inconclusive"]
    summary: str


class RollbackResult(BaseModel):
    execution_id: str
    status: Literal["succeeded", "failed", "not_supported"]
    summary: str
