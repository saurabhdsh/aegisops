from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.core.exceptions import AegisError, NotFoundError
from aegisops.persistence.models import MetricObservation
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.connectors.dynatrace.http import DynatraceHttp
from aegisops.runtime.connections import dynatrace_ready, overlay
from aegisops.runtime.forecast import linear_hours_to_capacity, slope_per_hour
from aegisops.runtime.scenarios import load_disk_capacity
from apps.api.dependencies import Principal, get_session, get_settings, require
from apps.api.schemas.common import AssetResponse

router = APIRouter(prefix="/api/v1/capacity", tags=["capacity"])


@router.get("/assets", response_model=list[AssetResponse])
def assets(
    principal: Principal = Depends(require("capacity:read")),
    session: Session = Depends(get_session),
) -> list[AssetResponse]:
    return [
        AssetResponse(
            id=row.id,
            name=row.name,
            ci_class=row.ci_class,
            environment=row.environment,
            criticality=row.criticality,
            external_id=row.external_id,
        )
        for row in OperationsRepository(session).list_assets(principal.tenant_id)
    ]


@router.get("/forecasts")
def forecasts(
    principal: Principal = Depends(require("capacity:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {"items": _forecasts(session, settings, principal.tenant_id)}


@router.get("/risks")
def risks(
    principal: Principal = Depends(require("capacity:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    items = [
        item
        for item in _forecasts(session, settings, principal.tenant_id)
        if item["current_utilization"] >= 75 or (item["hours_to_exhaustion"] is not None and item["hours_to_exhaustion"] <= 6)
    ]
    return {"items": items}


@router.post("/{asset_id}/assess")
def assess(
    asset_id: str,
    principal: Principal = Depends(require("capacity:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    known = {row.id: row for row in OperationsRepository(session).list_assets(principal.tenant_id)}
    asset = known.get(asset_id)
    if asset is None:
        raise NotFoundError("Capacity asset not found")
    if settings.execution_mode == "SIMULATOR" and asset.external_id == "ci-claims-db-01":
        return load_disk_capacity(session, settings, tenant_id=principal.tenant_id, actor_id=principal.user_id)
    raise AegisError(
        "insufficient_evidence",
        "No simulator catalog or stored disk series is available for this asset",
        409,
    )


def _forecasts(session: Session, settings: Settings, tenant_id: str) -> list[dict]:
    tuned = overlay(session, settings, tenant_id)
    if dynatrace_ready(tuned):
        return _live_disk(session, tuned, tenant_id)
    query = select(MetricObservation).where(
        MetricObservation.tenant_id == tenant_id,
        MetricObservation.metric_key == "disk",
    )
    if not OperationsRepository(session).demo_enabled(tenant_id):
        query = query.where(MetricObservation.entity_id.not_like("DEMO-%"))
    rows = list(session.scalars(query.order_by(MetricObservation.observed_at.asc())))
    grouped: dict[str, list[MetricObservation]] = {}
    for row in rows:
        grouped.setdefault(row.entity_id, []).append(row)
    items = []
    for entity_id, points in grouped.items():
        unique: list[MetricObservation] = []
        seen: set = set()
        for point in points:
            if point.observed_at in seen:
                continue
            seen.add(point.observed_at)
            unique.append(point)
        series = [(point.observed_at, point.value) for point in unique]
        current = series[-1][1]
        rate = slope_per_hour(series)
        hours = linear_hours_to_capacity(current, rate) if rate is not None else None
        items.append(
            {
                "entity_id": entity_id,
                "current_utilization": current,
                "growth_per_hour": rate,
                "hours_to_exhaustion": hours,
                "sample_count": len(series),
                "method": "linear",
                "source": unique[-1].source,
                "points": [{"timestamp": stamp.isoformat(), "value": value} for stamp, value in series],
            }
        )
    return items


def _live_disk(session: Session, settings: Settings, tenant_id: str) -> list[dict]:
    from datetime import datetime

    client = DynatraceHttp(settings)
    items = []
    try:
        for asset in OperationsRepository(session).list_assets(tenant_id):
            entity = str((asset.attributes or {}).get("dynatrace_entity_id") or "")
            if not entity or entity.startswith("DEMO-"):
                continue
            points = list(client.query_metrics(entity, "disk").get("points") or [])
            parsed = []
            for point in points:
                try:
                    stamp = datetime.fromisoformat(str(point.get("timestamp") or "").replace("Z", "+00:00"))
                except ValueError:
                    continue
                parsed.append((stamp, float(point["value"])))
            if len(parsed) < 2:
                continue
            current = parsed[-1][1]
            rate = slope_per_hour(parsed)
            hours = linear_hours_to_capacity(current, rate) if rate is not None else None
            items.append(
                {
                    "entity_id": entity,
                    "current_utilization": current,
                    "growth_per_hour": rate,
                    "hours_to_exhaustion": hours,
                    "sample_count": len(parsed),
                    "method": "linear",
                    "source": "dynatrace",
                    "points": [{"timestamp": stamp.isoformat(), "value": value} for stamp, value in parsed],
                }
            )
    finally:
        client.close()
    return items
