from __future__ import annotations

from pydantic import BaseModel, Field

from aegisops.agents.base import BaseAgent
from aegisops.agents.work import assess_capacity
from aegisops.contracts.agent import AgentContext, AgentResult
from aegisops.runtime.context import ports


class CapacityInput(BaseModel):
    points: list[dict] = Field(default_factory=list)
    criticality: str = "unknown"
    legal_hold: bool = False
    storage_extension_supported: bool = False
    entity_id: str = ""
    ci_external_id: str = ""


class CapacityRiskAgent(BaseAgent):
    name = "capacity_risk"
    allows_mutation = False

    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        data = CapacityInput.model_validate(payload.model_dump())
        forecast = assess_capacity(data.model_dump(), ports().snow, ports().dyna)
        forecast["criticality"] = data.criticality
        status = "completed" if forecast["current_utilization"] is not None else "insufficient_evidence"
        return AgentResult(
            status=status,
            summary=str(forecast.get("summary") or "Disk forecast from stored samples"),
            structured_output=forecast,
            tool_call_ids=[
                "dynatrace.query_metrics",
                "servicenow.get_ci",
                "servicenow.get_related_changes",
                "servicenow.search_similar_fixes",
            ],
        )
