"""Pull ServiceNow rows when a connection is saved. A failed call stays an error."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.connectors.servicenow.http import ServiceNowHttp
from aegisops.core.config import Settings
from aegisops.core.identifiers import new_id
from aegisops.persistence.models import Incident
from aegisops.runtime.connections import overlay, servicenow_ready

_STATES = {"1": "open", "2": "in_progress", "3": "on_hold", "6": "resolved", "7": "resolved"}


def refresh_servicenow_incidents(session: Session, settings: Settings, tenant_id: str) -> int:
    tuned = overlay(session, settings, tenant_id)
    if not servicenow_ready(tuned):
        return 0
    client = ServiceNowHttp(tuned)
    try:
        rows = client.list_incidents(limit=50)
    finally:
        client.close()
    written = 0
    for row in rows:
        sys_id = str(row.get("sys_id") or "")
        number = str(row.get("number") or "")
        if not sys_id or not number:
            continue
        existing = session.scalar(
            select(Incident).where(
                Incident.tenant_id == tenant_id,
                Incident.source == "servicenow",
                Incident.external_sys_id == sys_id,
            )
        )
        state = _STATES.get(str(row.get("state") or ""), "open")
        opened = _opened(str(row.get("opened_at") or ""))
        if existing is None:
            session.add(
                Incident(
                    id=new_id("inc"),
                    tenant_id=tenant_id,
                    source="servicenow",
                    external_number=number,
                    external_sys_id=sys_id,
                    title=str(row.get("title") or number)[:500],
                    description=str(row.get("description") or ""),
                    state=state,
                    source_state=str(row.get("state") or ""),
                    priority=str(row.get("priority") or ""),
                    opened_at=opened,
                    idempotency_key=f"snow:{sys_id}",
                    work_notes=list(row.get("work_notes") or []),
                )
            )
        else:
            existing.external_number = number
            existing.title = str(row.get("title") or existing.title)[:500]
            existing.description = str(row.get("description") or existing.description)
            existing.state = state
            existing.source_state = str(row.get("state") or existing.source_state)
            existing.priority = str(row.get("priority") or existing.priority)
            if opened is not None:
                existing.opened_at = opened
            existing.work_notes = list(row.get("work_notes") or existing.work_notes or [])
            existing.updated_at = _now()
        written += 1
    session.flush()
    return written


def _now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


def _opened(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
