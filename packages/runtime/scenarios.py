"""Load simulator catalogs into the database and start the matching workflow."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.core.exceptions import ForbiddenError
from aegisops.core.identifiers import new_id
from aegisops.persistence.models import BusinessService, ConfigurationItem, Event, Incident, Workflow
from aegisops.runtime.engine import OperationsEngine

_ROOT = Path(__file__).resolve().parents[2] / "fixtures"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_simulator(settings: Settings) -> None:
    if settings.execution_mode != "SIMULATOR":
        raise ForbiddenError("Scenario loading is available only in SIMULATOR mode")


def load_compute_incident(session: Session, settings: Settings, *, tenant_id: str, actor_id: str) -> dict:
    _require_simulator(settings)
    catalog = json.loads((_ROOT / "incident_scenario" / "catalog.json").read_text())
    engine = OperationsEngine(session, settings, fixtures_only=True)
    engine.ensure_runbook(tenant_id, "restart-claims-service", [catalog["ci"]["external_id"]])
    service = _service(session, tenant_id, catalog["ci"]["business_service"])
    ci = _ci(session, tenant_id, catalog["ci"], service.id, catalog["metrics"]["entity_id"])
    incident_body = catalog["incident"]
    incident = session.scalar(
        select(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.source == "servicenow",
            Incident.external_sys_id == incident_body["sys_id"],
        )
    )
    if incident is None:
        incident = Incident(
            id=new_id("inc"),
            tenant_id=tenant_id,
            source="servicenow",
            external_number=incident_body["number"],
            external_sys_id=incident_body["sys_id"],
            title=incident_body["title"],
            description=incident_body["description"],
            state="open",
            source_state=incident_body["state"],
            priority=incident_body["priority"],
            ci_id=ci.id,
            business_service_id=service.id,
            opened_at=_parse(catalog["opened_at"]),
            idempotency_key=f"snow:{incident_body['sys_id']}",
            work_notes=list(incident_body.get("work_notes") or []),
        )
        session.add(incident)
        session.flush()
    result = engine.investigate_incident(incident, actor_id=actor_id)
    result["incident_id"] = incident.id
    return result


def load_disk_capacity(session: Session, settings: Settings, *, tenant_id: str, actor_id: str) -> dict:
    _require_simulator(settings)
    catalog = json.loads((_ROOT / "capacity_scenario" / "catalog.json").read_text())
    engine = OperationsEngine(session, settings, fixtures_only=True)
    engine.ensure_runbook(tenant_id, "cleanup-approved-logs", [catalog["host"]["external_id"]])
    service = _service(session, tenant_id, catalog["host"]["business_service"])
    ci = _ci(session, tenant_id, catalog["host"], service.id, catalog["host"]["entity_id"])
    existing = session.scalar(
        select(Workflow).where(
            Workflow.tenant_id == tenant_id,
            Workflow.idempotency_key == "capacity:claims-db",
            Workflow.state.notin_(["FAILED", "CANCELLED"]),
        )
    )
    if existing is not None:
        return {
            "workflow_id": existing.id,
            "state": existing.state,
            "duplicate": True,
            "alert_count": catalog["alert_count"],
            "configuration_item_id": ci.id,
        }
    base = datetime.now(timezone.utc) - timedelta(minutes=20)
    forecast = catalog.get("forecast_event") or {}
    events = []
    if forecast:
        events.append(
            {
                "id": forecast["id"],
                "entity_ref": catalog["host"]["entity_id"],
                "symptom": catalog["symptom"],
                "event_type": "forecast",
                "received_at": base.isoformat(),
            }
        )
        _event(
            session,
            tenant_id=tenant_id,
            external_id=forecast["id"],
            event_type="forecast",
            entity_ref=catalog["host"]["entity_id"],
            payload={"symptom": catalog["symptom"], "message": forecast.get("message") or ""},
            received_at=base,
            idempotency_key=f"disk-{forecast['id']}",
        )
    for index in range(int(catalog["alert_count"])):
        events.append(
            {
                "id": f"alert-{index}",
                "entity_ref": catalog["host"]["entity_id"],
                "symptom": catalog["symptom"],
                "event_type": "alert",
                "received_at": (base + timedelta(seconds=index + 1)).isoformat(),
            }
        )
        _event(
            session,
            tenant_id=tenant_id,
            external_id=f"disk-{index}",
            event_type="alert",
            entity_ref=catalog["host"]["entity_id"],
            payload={"symptom": catalog["symptom"]},
            received_at=base + timedelta(seconds=index + 1),
            idempotency_key=f"disk-{index}",
        )
    context = {
        "points": catalog["disk_series"],
        "criticality": catalog["host"]["criticality"],
        "legal_hold": catalog["legal_hold"],
        "archive_required": catalog["archive_required"],
        "retention_days": catalog["retention_days"],
        "storage_extension_supported": catalog["storage_extension_supported"],
        "log_share_of_disk": catalog["log_share_of_disk"],
        "service_healthy": catalog["service_healthy"],
        "ci_external_id": catalog["host"]["external_id"],
        "entity_id": catalog["host"]["entity_id"],
        "events": events,
    }
    from aegisops.persistence.repositories.operations import OperationsRepository

    control = OperationsRepository(session).control_for(tenant_id)
    workflow = engine.orch.open(
        tenant_id=tenant_id,
        kind="capacity",
        correlation_id=new_id("cor"),
        execution_mode=settings.execution_mode,
        autonomy_level=control.autonomy_level,
        idempotency_key="capacity:claims-db",
        summary=json.dumps(context),
    )
    engine._until_gate(workflow, actor_id)
    return {
        "workflow_id": workflow.id,
        "state": workflow.state,
        "duplicate": False,
        "alert_count": catalog["alert_count"],
        "configuration_item_id": ci.id,
    }


def _event(session: Session, *, tenant_id: str, external_id: str, event_type: str, entity_ref: str, payload: dict, received_at: datetime, idempotency_key: str) -> None:
    existing = session.scalar(
        select(Event).where(
            Event.tenant_id == tenant_id,
            Event.source == "dynatrace",
            Event.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return
    session.add(
        Event(
            id=new_id("evt"),
            tenant_id=tenant_id,
            source="dynatrace",
            external_id=external_id,
            event_type=event_type,
            severity="warning",
            entity_ref=entity_ref,
            payload=payload,
            received_at=received_at,
            idempotency_key=idempotency_key,
        )
    )


def _service(session: Session, tenant_id: str, body: dict) -> BusinessService:
    row = session.scalar(
        select(BusinessService).where(
            BusinessService.tenant_id == tenant_id,
            BusinessService.external_id == body["external_id"],
        )
    )
    if row is None:
        row = BusinessService(
            id=new_id("svc"),
            tenant_id=tenant_id,
            external_id=body["external_id"],
            name=body["name"],
            criticality=body.get("criticality") or "unknown",
        )
        session.add(row)
        session.flush()
    return row


def _ci(session: Session, tenant_id: str, body: dict, service_id: str, entity_id: str) -> ConfigurationItem:
    row = session.scalar(
        select(ConfigurationItem).where(
            ConfigurationItem.tenant_id == tenant_id,
            ConfigurationItem.source == "servicenow",
            ConfigurationItem.external_id == body["external_id"],
        )
    )
    if row is None:
        row = ConfigurationItem(
            id=new_id("ci"),
            tenant_id=tenant_id,
            external_id=body["external_id"],
            source="servicenow",
            name=body["name"],
            ci_class=body["class"],
            environment=body.get("environment") or "unknown",
            criticality=body.get("criticality") or "unknown",
            business_service_id=service_id,
            attributes={"dynatrace_entity_id": entity_id},
        )
        session.add(row)
        session.flush()
    return row
