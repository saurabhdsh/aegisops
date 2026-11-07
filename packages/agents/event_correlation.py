from __future__ import annotations

from pydantic import BaseModel, Field

from aegisops.agents.base import BaseAgent
from aegisops.contracts.agent import AgentContext, AgentResult
from aegisops.runtime.correlation import correlate


class CorrelationInput(BaseModel):
    events: list[dict] = Field(default_factory=list)


class EventCorrelationAgent(BaseAgent):
    name = "event_correlation"
    allows_mutation = False

    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        data = CorrelationInput.model_validate(payload.model_dump())
        groups = correlate(data.events)
        forecasts = sum(1 for item in data.events if item.get("event_type") == "forecast")
        alerts = len(data.events) - forecasts
        summary = f"{forecasts} forecast and {alerts} alerts grouped into {len(groups)} event" if groups else "No events to group"
        return AgentResult(
            status="completed" if groups else "insufficient_evidence",
            summary=summary,
            structured_output={
                "groups": groups,
                "source_count": len(data.events),
                "forecast_count": forecasts,
                "alert_count": alerts,
            },
            tool_call_ids=["events.group"],
        )
