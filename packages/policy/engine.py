"""Deterministic authorization for approval decisions.

The Governance Agent may explain a decision. This module makes it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aegisops.core.exceptions import ConflictError, ForbiddenError
from aegisops.persistence.models import ApprovalRequest, OperationalControl


def evaluate_approval(
    request: ApprovalRequest,
    *,
    actor_roles: set[str],
    control: OperationalControl,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(timezone.utc)
    if control.emergency_stop:
        raise ForbiddenError("Emergency stop is active. New approvals are rejected.")
    if request.status != "pending":
        raise ConflictError("Approval request is no longer pending", {"status": request.status})
    expires = request.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < current:
        raise ConflictError("Approval request has expired")
    if "admin" in actor_roles:
        return
    if request.required_role == "dba":
        if "dba" not in actor_roles:
            raise ForbiddenError("This change requires the dba role")
        return
    if request.required_role not in actor_roles and "approver" not in actor_roles and "sre" not in actor_roles:
        raise ForbiddenError(f"This change requires the {request.required_role} role")


def evaluate_autonomy_change(*, requested: str, l4_enabled: bool, actor_roles: set[str]) -> None:
    if "admin" not in actor_roles:
        raise ForbiddenError("Only an admin can change autonomy")
    if requested == "L4" and not l4_enabled:
        raise ForbiddenError("L4 autonomy is disabled by configuration")
    if requested not in {"L3", "L4"}:
        raise ConflictError("Autonomy level must be L3 or L4")
