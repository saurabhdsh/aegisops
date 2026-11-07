from __future__ import annotations

from pydantic import BaseModel

from aegisops.agents.base import BaseAgent
from aegisops.contracts.agent import AgentContext, AgentResult
from aegisops.policy.autonomy import automatic_execution_allowed


class GovernanceInput(BaseModel):
    autonomy_level: str
    l4_enabled: bool
    risk_level: str
    certified: bool
    emergency_stop: bool
    rollback_defined: bool
    conflicting_change: bool
    required_role: str


class GovernanceAgent(BaseAgent):
    """Explains the policy engine decision. It does not authorize the action."""

    name = "governance"
    allows_mutation = False

    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        data = GovernanceInput.model_validate(payload.model_dump())
        allowed, reason = automatic_execution_allowed(
            autonomy_level=data.autonomy_level,
            l4_enabled=data.l4_enabled,
            risk_level=data.risk_level,
            certified=data.certified,
            emergency_stop=data.emergency_stop,
            prechecks_passed=True,
            rollback_defined=data.rollback_defined,
            conflicting_change=data.conflicting_change,
        )
        summary = (
            f"Policy engine would allow automatic execution: {reason}"
            if allowed
            else f"Human approval is required ({data.required_role}). {reason}"
        )
        return AgentResult(
            status="completed",
            summary=summary,
            structured_output={"automatic": allowed, "reason": reason, "authoritative": "policy-engine"},
            tool_call_ids=[],
        )
