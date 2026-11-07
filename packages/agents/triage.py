from __future__ import annotations

from pydantic import BaseModel, Field

from aegisops.agents.base import BaseAgent
from aegisops.agents.work import triage
from aegisops.contracts.agent import AgentContext, AgentResult
from aegisops.runtime.context import ports


class TriageInput(BaseModel):
    incident_number: str = ""
    incident_sys_id: str = ""
    title: str = ""
    priority: str = ""
    ci_external_id: str | None = None
    work_notes: list[str] = Field(default_factory=list)


class TriageAgent(BaseAgent):
    name = "triage"
    allows_mutation = False

    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        data = TriageInput.model_validate(payload.model_dump())
        output = triage(data.model_dump(), ports().snow)
        status = "completed" if output.get("impacted_ci") or output.get("priority") else "insufficient_evidence"
        return AgentResult(
            status=status,
            summary=f"Similar incidents returned: {output['similar_count']}",
            structured_output=output,
            tool_call_ids=["servicenow.get_incident", "servicenow.get_ci", "servicenow.search_similar"],
        )
