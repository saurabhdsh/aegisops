from __future__ import annotations

from pydantic import BaseModel, Field

from aegisops.agents.base import BaseAgent
from aegisops.agents.work import analyze
from aegisops.contracts.agent import AgentContext, AgentResult
from aegisops.runtime.context import ports


class RCAInput(BaseModel):
    entity_id: str | None = None
    title: str = ""
    priority: str = ""
    opened_at: str | None = None
    changes: list[dict] = Field(default_factory=list)
    error_rate: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RCAAgent(BaseAgent):
    name = "rca"
    allows_mutation = False

    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        data = RCAInput.model_validate(payload.model_dump())
        bundle = ports()
        output = analyze(data.model_dump(), bundle.dyna, bundle.narrative)
        status = "completed" if output["hypotheses"] else "insufficient_evidence"
        return AgentResult(
            status=status,
            summary=output["hypotheses"][0]["cause"] if output["hypotheses"] else "No hypothesis met the evidence threshold",
            structured_output=output,
            tool_call_ids=["dynatrace.query_metrics", "dynatrace.logs", "dynatrace.traces"],
            confidence=output["hypotheses"][0]["confidence"] if output["hypotheses"] else None,
        )
