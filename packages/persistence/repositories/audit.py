from __future__ import annotations

from sqlalchemy.orm import Session

from aegisops.core.identifiers import new_id
from aegisops.core.security import redact_mapping
from aegisops.persistence.models import AuditEvent


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str = "",
        tenant_id: str | None = None,
        actor_id: str | None = None,
        correlation_id: str = "",
        payload: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=new_id("aud"),
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=correlation_id,
            payload=redact_mapping(payload or {}),
        )
        self.session.add(event)
        self.session.flush()
        return event
