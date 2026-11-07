"""Deterministic ServiceNow and Dynatrace fleet used by the settings demo switch."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.core.exceptions import ForbiddenError
from aegisops.core.identifiers import new_id
from aegisops.persistence.models import (
    BusinessService,
    ConfigurationItem,
    Event,
    Incident,
    MetricObservation,
    OperationalControl,
)
from aegisops.runtime.scenarios import load_compute_incident, load_disk_capacity

_SERVICES = (
    ("demo-svc-payments", "Payments", "tier-1"),
    ("demo-svc-policy", "Policy", "tier-1"),
    ("demo-svc-billing", "Billing", "tier-2"),
    ("demo-svc-identity", "Identity", "tier-1"),
    ("demo-svc-member", "Member", "tier-2"),
    ("demo-svc-provider", "Provider", "tier-2"),
    ("demo-svc-pharmacy", "Pharmacy", "tier-1"),
    ("demo-svc-claims-batch", "Claims batch", "tier-2"),
)

_TITLES = (
    "CPU saturation on the application host",
    "Memory growth after the latest deployment",
    "Error rate above the service objective",
    "Disk utilization climbing on the data volume",
    "Checkout latency above two seconds",
    "Synthetic transaction failing",
    "Thread pool exhaustion under peak load",
    "Garbage-collection pauses above one second",
    "Connection pool waiting on the database",
    "Elevated response time on the public API",
    "Process restart loop after deployment",
    "Queue depth growing on the worker",
)


def fleet_size() -> int:
    return 52


def set_demo(session: Session, settings: Settings, *, tenant_id: str, actor_id: str, enabled: bool) -> dict:
    control = session.scalar(select(OperationalControl).where(OperationalControl.tenant_id == tenant_id))
    if control is None:
        raise ForbiddenError("Operational control is not configured")
    control.demo_enabled = enabled
    control.updated_by = actor_id
    control.updated_at = datetime.now(timezone.utc)
    seeded = 0
    if enabled:
        seeded = _seed(session, tenant_id)
        if settings.execution_mode == "SIMULATOR":
            load_compute_incident(session, settings, tenant_id=tenant_id, actor_id=actor_id)
            load_disk_capacity(session, settings, tenant_id=tenant_id, actor_id=actor_id)
    count = int(
        session.scalar(
            select(func.count()).select_from(Incident).where(Incident.tenant_id == tenant_id, Incident.source == "demo")
        )
        or 0
    )
    return {"enabled": enabled, "incident_count": count, "seeded": seeded}


def _seed(session: Session, tenant_id: str) -> int:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    services = {item[0]: _service(session, tenant_id, *item) for item in _SERVICES}
    created = 0
    for index in range(fleet_size()):
        service_key, service_name, criticality = _SERVICES[index % len(_SERVICES)]
        number = f"INC{10001 + index}"
        sys_id = f"{index + 1:032x}"
        entity = f"DEMO-HOST-{index + 1:02d}"
        ci = _ci(session, tenant_id, index, services[service_key].id, criticality, entity)
        existing = session.scalar(
            select(Incident).where(Incident.tenant_id == tenant_id, Incident.external_sys_id == sys_id)
        )
        opened = now - timedelta(hours=index * 3)
        priority = str((index % 4) + 1)
        state = ("open", "in_progress", "on_hold", "resolved")[index % 4]
        title = f"{_TITLES[index % len(_TITLES)]} · {service_name}"
        problem = f"P-{20000 + index}"
        if existing is None:
            session.add(
                Incident(
                    id=new_id("inc"),
                    tenant_id=tenant_id,
                    source="demo",
                    external_number=number,
                    external_sys_id=sys_id,
                    title=title,
                    description=f"Dynatrace problem {problem} opened against {ci.name} for {service_name}.",
                    state=state,
                    source_state="2" if state != "resolved" else "6",
                    priority=priority,
                    severity="1" if priority in {"1", "2"} else "2",
                    ci_id=ci.id,
                    business_service_id=services[service_key].id,
                    opened_at=opened,
                    resolved_at=opened + timedelta(hours=2) if state == "resolved" else None,
                    idempotency_key=f"demo:{sys_id}",
                    work_notes=[f"Dynatrace problem {problem} correlated to {entity}."],
                )
            )
            created += 1
        _metrics(session, tenant_id, entity, opened, index)
        _problem(session, tenant_id, index, entity, problem, title, opened)
    session.flush()
    return created


def _service(session: Session, tenant_id: str, external_id: str, name: str, criticality: str) -> BusinessService:
    row = session.scalar(
        select(BusinessService).where(BusinessService.tenant_id == tenant_id, BusinessService.external_id == external_id)
    )
    if row is None:
        row = BusinessService(
            id=new_id("svc"),
            tenant_id=tenant_id,
            external_id=external_id,
            name=name,
            criticality=criticality,
        )
        session.add(row)
        session.flush()
    return row


def _ci(session: Session, tenant_id: str, index: int, service_id: str, criticality: str, entity: str) -> ConfigurationItem:
    external_id = f"demo-host-{index + 1:02d}"
    row = session.scalar(
        select(ConfigurationItem).where(
            ConfigurationItem.tenant_id == tenant_id,
            ConfigurationItem.external_id == external_id,
        )
    )
    if row is None:
        row = ConfigurationItem(
            id=new_id("ci"),
            tenant_id=tenant_id,
            external_id=external_id,
            source="servicenow",
            name=f"app-{index + 1:02d}",
            ci_class="cmdb_ci_linux_server",
            environment="production",
            criticality=criticality,
            business_service_id=service_id,
            attributes={"dynatrace_entity_id": entity},
        )
        session.add(row)
        session.flush()
    return row


def _metrics(session: Session, tenant_id: str, entity: str, opened: datetime, index: int) -> None:
    existing = session.scalar(
        select(MetricObservation.id).where(
            MetricObservation.tenant_id == tenant_id,
            MetricObservation.entity_id == entity,
            MetricObservation.metric_key == "cpu",
        )
    )
    if existing is not None:
        return
    cpu_start = 28 + (index % 12)
    memory_start = 40 + (index % 18)
    for step in range(4):
        stamp = opened - timedelta(hours=3 - step)
        session.add(_point(tenant_id, entity, "cpu", stamp, cpu_start + step * (6 if index % 5 == 0 else 2)))
        session.add(_point(tenant_id, entity, "memory", stamp, memory_start + step * (7 if index % 4 == 0 else 1)))
        if index % 7 == 0:
            session.add(_point(tenant_id, entity, "disk", stamp, 58 + step * 6))


def _point(tenant_id: str, entity: str, metric_key: str, stamp: datetime, value: float) -> MetricObservation:
    return MetricObservation(
        id=new_id("met"),
        tenant_id=tenant_id,
        entity_id=entity,
        metric_key=metric_key,
        observed_at=stamp,
        value=float(value),
        unit="percent",
        source="dynatrace",
        query_reference=f"demo:{entity}:{metric_key}",
    )


def _problem(session: Session, tenant_id: str, index: int, entity: str, problem: str, title: str, opened: datetime) -> None:
    key = f"demo-problem-{index}"
    existing = session.scalar(select(Event.id).where(Event.tenant_id == tenant_id, Event.idempotency_key == key))
    if existing is not None:
        return
    session.add(
        Event(
            id=new_id("evt"),
            tenant_id=tenant_id,
            source="dynatrace",
            external_id=problem,
            event_type="problem",
            severity="critical" if index % 4 == 0 else "warning",
            entity_ref=entity,
            payload={"title": title, "problem_id": problem},
            received_at=opened,
            idempotency_key=key,
        )
    )
