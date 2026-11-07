"""Legal workflow transitions. Terminal states have no outbound edge."""

from __future__ import annotations

from aegisops.core.exceptions import ConflictError
from aegisops.persistence.models import WORKFLOW_STATES

TERMINAL = frozenset({"RESOLVED", "PREVENTED", "ESCALATED", "FAILED", "CANCELLED"})

_ALLOWED: dict[str, frozenset[str]] = {
    "RECEIVED": frozenset({"NORMALIZING", "CANCELLED", "FAILED"}),
    "NORMALIZING": frozenset({"ENRICHING", "ESCALATED", "FAILED", "CANCELLED"}),
    "ENRICHING": frozenset({"INVESTIGATING", "ANALYZING", "ESCALATED", "FAILED", "CANCELLED"}),
    "INVESTIGATING": frozenset({"ANALYZING", "ESCALATED", "FAILED", "CANCELLED"}),
    "ANALYZING": frozenset({"PLANNING", "ESCALATED", "FAILED", "CANCELLED"}),
    "PLANNING": frozenset({"POLICY_CHECK", "ESCALATED", "FAILED", "CANCELLED"}),
    "POLICY_CHECK": frozenset({"AWAITING_APPROVAL", "PRECHECKING", "ESCALATED", "FAILED", "CANCELLED"}),
    "AWAITING_APPROVAL": frozenset({"PRECHECKING", "CANCELLED", "FAILED", "ESCALATED"}),
    "PRECHECKING": frozenset({"EXECUTING", "FAILED", "ESCALATED", "CANCELLED"}),
    "EXECUTING": frozenset({"VALIDATING", "FAILED", "ESCALATED", "CANCELLED"}),
    "VALIDATING": frozenset({"RESOLVED", "PREVENTED", "FAILED", "ESCALATED"}),
    "RESOLVED": frozenset(),
    "PREVENTED": frozenset(),
    "ESCALATED": frozenset(),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
}


def assert_transition(current: str, target: str) -> None:
    if current not in WORKFLOW_STATES or target not in WORKFLOW_STATES:
        raise ConflictError("Unknown workflow state", {"current": current, "target": target})
    if target not in _ALLOWED[current]:
        raise ConflictError(
            f"Transition {current} -> {target} is not allowed",
            {"current": current, "target": target},
        )


def is_terminal(state: str) -> bool:
    return state in TERMINAL
