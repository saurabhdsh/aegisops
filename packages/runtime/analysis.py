"""Read-only RCA for one incident from samples already stored.

This does not open a workflow, call a model, or run a runbook.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.connectors.dynatrace.http import DynatraceHttp
from aegisops.core.config import Settings
from aegisops.persistence.models import BusinessService, ConfigurationItem, MetricObservation, Workflow
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.runtime.connections import dynatrace_ready, overlay
from aegisops.runtime.forecast import slope_per_hour
from aegisops.runtime.signals import rank_hypotheses


def incident_analysis(session: Session, tenant_id: str, incident_id: str, settings: Settings) -> dict:
    incident = OperationsRepository(session).get_incident(tenant_id, incident_id)
    ci = session.get(ConfigurationItem, incident.ci_id) if incident.ci_id else None
    service = session.get(BusinessService, incident.business_service_id) if incident.business_service_id else None
    attributes = ci.attributes if ci and isinstance(ci.attributes, dict) else {}
    entity = str(attributes.get("dynatrace_entity_id") or (ci.name if ci else "") or "")
    tuned = overlay(session, settings, tenant_id)
    source = "stored-samples"
    # Demo catalog entities stay on stored samples. A real entity is queried, and a failed call is not replaced.
    if dynatrace_ready(tuned) and entity and not entity.startswith("DEMO-"):
        client = DynatraceHttp(tuned)
        try:
            cpu = list(client.query_metrics(entity, "cpu").get("points") or [])
            memory = list(client.query_metrics(entity, "memory").get("points") or [])
        finally:
            client.close()
        source = "dynatrace"
    else:
        cpu = _series(session, tenant_id, entity, "cpu")
        memory = _series(session, tenant_id, entity, "memory")
    cpu_points = _tuples(cpu)
    memory_points = _tuples(memory)
    signals = {
        "memory_slope_per_hour": slope_per_hour(memory_points),
        "cpu_slope_per_hour": slope_per_hour(cpu_points),
        "deployment_lag_hours": None,
        "error_rate": None,
        "heap_profile": False,
        "cpu_series": bool(cpu_points),
    }
    hypotheses = rank_hypotheses({**signals, "evidence_ids": []})
    for rank, item in enumerate(hypotheses, start=1):
        item["rank"] = rank
    workflow = session.scalar(
        select(Workflow).where(
            Workflow.tenant_id == tenant_id,
            Workflow.incident_id == incident.id,
            Workflow.kind == "incident",
            Workflow.state.not_in(["CANCELLED", "FAILED"]),
        )
    )
    return {
        "incident_id": incident.id,
        "number": incident.external_number,
        "title": incident.title,
        "state": incident.state,
        "priority": incident.priority,
        "ci_name": ci.name if ci else "",
        "service_name": service.name if service else "",
        "entity_id": entity,
        "source": source,
        "workflow_id": workflow.id if workflow else None,
        "signals": signals,
        "hypotheses": hypotheses,
        "series": {"cpu": cpu, "memory": memory},
        "confidence_note": "Scores are derived from measured slopes and are not calibrated probabilities.",
    }


def _series(session: Session, tenant_id: str, entity: str, metric_key: str) -> list[dict]:
    if not entity:
        return []
    rows = session.scalars(
        select(MetricObservation)
        .where(
            MetricObservation.tenant_id == tenant_id,
            MetricObservation.entity_id == entity,
            MetricObservation.metric_key == metric_key,
        )
        .order_by(MetricObservation.observed_at.asc())
    )
    return [
        {"timestamp": row.observed_at.isoformat(), "value": row.value, "unit": row.unit}
        for row in rows
    ]


def _tuples(points: list[dict]) -> list:
    from datetime import datetime

    parsed = []
    for item in points:
        stamp = datetime.fromisoformat(str(item["timestamp"]))
        parsed.append((stamp, float(item["value"])))
    return parsed
