"""Persist a webhook once. A repeated external id returns the original row."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aegisops.core.exceptions import AegisError
from aegisops.core.identifiers import new_id
from aegisops.persistence.models import Event


def ingest_event(
    session: Session,
    *,
    tenant_id: str,
    source: str,
    external_id: str,
    event_type: str,
    entity_ref: str = "",
    severity: str = "",
    payload: dict | None = None,
) -> tuple[Event, bool]:
    if not external_id:
        raise AegisError("validation_error", "event_id is required", 422)
    key = f"{source}:{external_id}"
    existing = session.scalar(
        select(Event).where(Event.tenant_id == tenant_id, Event.source == source, Event.idempotency_key == key)
    )
    if existing is not None:
        return existing, True
    row = Event(
        id=new_id("evt"),
        tenant_id=tenant_id,
        source=source,
        external_id=external_id,
        event_type=event_type,
        severity=severity,
        entity_ref=entity_ref,
        payload=payload or {},
        received_at=datetime.now(timezone.utc),
        idempotency_key=key,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(Event).where(Event.tenant_id == tenant_id, Event.source == source, Event.idempotency_key == key)
        )
        if existing is None:
            raise
        return existing, True
    return row, False
