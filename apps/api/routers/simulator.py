from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.core.exceptions import ForbiddenError
from aegisops.runtime.scenarios import load_compute_incident, load_disk_capacity
from apps.api.dependencies import Principal, get_session, get_settings, require

router = APIRouter(prefix="/api/v1/simulator/scenarios", tags=["simulator"])


def _simulator(settings: Settings) -> None:
    if settings.execution_mode != "SIMULATOR":
        raise ForbiddenError("Scenario loading is available only in SIMULATOR mode")


@router.post("/compute-incident")
def compute_incident(
    principal: Principal = Depends(require("incident:investigate")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _simulator(settings)
    return load_compute_incident(session, settings, tenant_id=principal.tenant_id, actor_id=principal.user_id)


@router.post("/disk-capacity")
def disk_capacity(
    principal: Principal = Depends(require("capacity:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _simulator(settings)
    return load_disk_capacity(session, settings, tenant_id=principal.tenant_id, actor_id=principal.user_id)
