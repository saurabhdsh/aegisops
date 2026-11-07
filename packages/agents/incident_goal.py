from __future__ import annotations

from pydantic import BaseModel, Field

from aegisops.agents.base import BaseAgent
from aegisops.contracts.agent import AgentContext, AgentResult


class GoalInput(BaseModel):
    kind: str
    child_agents: list[str] = Field(default_factory=list)


class IncidentGoalAgent(BaseAgent):
    name = "incident_goal"
    allows_mutation = False

    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        data = GoalInput.model_validate(payload.model_dump())
        return AgentResult(
            status="completed",
            summary=f"Coordinated {data.kind} workflow",
            structured_output={"children": data.child_agents},
            tool_call_ids=[f"agent.{name}" for name in data.child_agents],
        )
