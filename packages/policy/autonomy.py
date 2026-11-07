"""L4 eligibility. High-risk actions stay approval-gated at every autonomy level."""

from __future__ import annotations


def automatic_execution_allowed(
    *,
    autonomy_level: str,
    l4_enabled: bool,
    risk_level: str,
    certified: bool,
    emergency_stop: bool,
    prechecks_passed: bool,
    rollback_defined: bool,
    conflicting_change: bool,
) -> tuple[bool, str]:
    if emergency_stop:
        return False, "Emergency stop is active"
    if risk_level == "high":
        return False, "High-risk actions remain approval-gated"
    if autonomy_level != "L4" or not l4_enabled:
        return False, "Autonomy level requires a human approval"
    if not certified:
        return False, "Runbook is not certified for this target"
    if not rollback_defined:
        return False, "Runbook has no tested rollback"
    if conflicting_change:
        return False, "A conflicting change is open"
    if not prechecks_passed:
        return False, "Pre-checks have not passed"
    return True, "Certified L4 conditions passed"
