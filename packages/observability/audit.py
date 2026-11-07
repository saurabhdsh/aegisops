"""Audit facade used by the API. Writes go through the append-only repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from aegisops.persistence.repositories.audit import AuditRepository


def audit(
    session: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    tenant_id: str | None = None,
    actor_id: str | None = None,
    correlation_id: str = "",
    payload: dict | None = None,
) -> None:
    AuditRepository(session).record(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        payload=payload,
    )
