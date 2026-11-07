from __future__ import annotations

from pydantic import BaseModel

from aegisops.agents.base import BaseAgent
from aegisops.agents.work import validate_recovery
from aegisops.contracts.agent import AgentContext, AgentResult
from aegisops.runtime.context import ports


class ValidationInput(BaseModel):
    kind: str
    entity_id: str | None = None
    pre_cpu: float | None = None
    pre_memory: float | None = None
    error_rate_after: float | None = None
    synthetic_ok: bool | None = None
    current_utilization: float | None = None
    log_share_of_disk: float | None = None
    deleted_bytes: int | None = None
    log_bytes_before: int | None = None
    growth_per_hour: float | None = None
    service_healthy: bool | None = None
    incidents_during_window: int = 0


class ValidationAgent(BaseAgent):
    name = "validation"
    allows_mutation = False

    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        data = ValidationInput.model_validate(payload.model_dump())
        output = validate_recovery(data.model_dump(), ports().dyna)
        return AgentResult(
            status="completed" if output["passed"] else "failed",
            summary=output["summary"],
            structured_output=output,
            tool_call_ids=["metrics.cleanup"] if data.kind == "capacity" else ["dynatrace.query_metrics"],
        )
