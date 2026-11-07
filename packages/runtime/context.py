"""Ports available to an agent while the engine is running."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from aegisops.core.config import Settings
from aegisops.core.exceptions import AegisError


@dataclass
class Ports:
    settings: Settings
    snow: Any
    dyna: Any
    automation: Any
    narrative: Any


ports_var: ContextVar[Ports | None] = ContextVar("aegisops_ports", default=None)


def ports() -> Ports:
    current = ports_var.get()
    if current is None:
        raise AegisError("agent_context", "Agent was called outside the execution engine", 409)
    return current
