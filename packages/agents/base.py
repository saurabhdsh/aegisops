"""Agent contract. Concrete agents refuse to invent a result until their phase is implemented."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from aegisops.contracts.agent import AgentContext, AgentResult


class BaseAgent(ABC):
    name: str
    allows_mutation: bool = False

    @abstractmethod
    async def execute(self, context: AgentContext, payload: BaseModel) -> AgentResult:
        """Run the agent. Implementations must return a typed result or raise a real error."""
