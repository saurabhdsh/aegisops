from __future__ import annotations

from pydantic import BaseModel, Field

from aegisops.agents.base import BaseAgent
from aegisops.agents.work import select_runbook
from aegisops.contracts.agent import AgentContext, AgentResult


class RemediationInput(BaseModel):
    kind: str
    hypotheses: list[dict] = Field(default_factory=list)
    runbooks: list[dict] = Field(default_factory=list)
    ci_class: str = ""
    environment: str = ""
    legal_hold: bool = False
    archive_required: bool = False
    retention_days: int = 7


class RemediationAgent(BaseAgent):
    name = "remediation"
    allows_mutation = False

    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        data = RemediationInput.model_validate(payload.model_dump())
        chosen = select_runbook(data.model_dump())
        if chosen is None:
            return AgentResult(
                status="insufficient_evidence",
                summary="No certified runbook matched the evidence",
                structured_output={"plan": None},
                tool_call_ids=["runbooks.match"],
            )
        return AgentResult(
            status="completed",
            summary=chosen["runbook"]["name"],
            structured_output={"plan": chosen},
            tool_call_ids=["runbooks.match"],
        )
