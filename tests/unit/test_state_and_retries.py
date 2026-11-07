import pytest

from aegisops.core.exceptions import ConflictError
from aegisops.runtime.retries import classify_retry, retry_decision
from aegisops.runtime.state_machine import assert_transition, is_terminal


def test_incident_path_is_legal() -> None:
    states = [
        "RECEIVED",
        "NORMALIZING",
        "ENRICHING",
        "INVESTIGATING",
        "ANALYZING",
        "PLANNING",
        "POLICY_CHECK",
        "AWAITING_APPROVAL",
        "PRECHECKING",
        "EXECUTING",
        "VALIDATING",
        "RESOLVED",
    ]
    for current, nxt in zip(states, states[1:]):
        assert_transition(current, nxt)
    assert is_terminal("RESOLVED")


def test_illegal_transition() -> None:
    with pytest.raises(ConflictError):
        assert_transition("RECEIVED", "EXECUTING")
    with pytest.raises(ConflictError):
        assert_transition("RESOLVED", "INVESTIGATING")


def test_capacity_can_skip_investigation() -> None:
    assert_transition("ENRICHING", "ANALYZING")
    assert_transition("VALIDATING", "PREVENTED")


def test_external_execution_is_reconciled_not_replayed() -> None:
    assert retry_decision(status="running", external_execution_id="job-9") == "reconcile"
    assert classify_retry(TimeoutError(), external_execution_id="job-9") == "reconcile"
    assert classify_retry(TimeoutError(), external_execution_id=None) == "transient"
    assert classify_retry(RuntimeError("bad"), external_execution_id=None) == "permanent"
    assert retry_decision(status="running", external_execution_id=None) == "blocked"
