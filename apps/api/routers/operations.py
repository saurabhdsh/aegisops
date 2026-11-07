from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.core.exceptions import ForbiddenError
from aegisops.observability.audit import audit
from aegisops.persistence.repositories.operations import OperationsRepository
from aegisops.policy.engine import evaluate_autonomy_change
from apps.api.dependencies import Principal, get_session, get_settings, require
from apps.api.schemas.common import AutonomyRequest, ControlResponse, EmergencyStopRequest

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def _response(control) -> ControlResponse:  # type: ignore[no-untyped-def]
    return ControlResponse(
        emergency_stop=control.emergency_stop,
        autonomy_level=control.autonomy_level,
        freeze_reason=control.freeze_reason,
        updated_at=control.updated_at,
    )


def _require_admin(principal: Principal) -> None:
    if "admin" not in principal.roles:
        raise ForbiddenError("Only an admin can change operational controls")


@router.get("/controls", response_model=ControlResponse)
def get_controls(
    principal: Principal = Depends(require("control:read")),
    session: Session = Depends(get_session),
) -> ControlResponse:
    return _response(OperationsRepository(session).control_for(principal.tenant_id))


@router.post("/emergency-stop", response_model=ControlResponse)
def engage_stop(
    body: EmergencyStopRequest,
    request: Request,
    principal: Principal = Depends(require("control:read")),
    session: Session = Depends(get_session),
) -> ControlResponse:
    _require_admin(principal)
    control = OperationsRepository(session).control_for(principal.tenant_id)
    control.emergency_stop = True
    control.freeze_reason = body.reason
    control.updated_by = principal.user_id
    control.updated_at = datetime.now(timezone.utc)
    audit(
        session,
        action="control.emergency_stop",
        resource_type="operational_control",
        resource_id=control.id,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=request.state.correlation_id,
        payload={"reason": body.reason, "external_actions_stopped": False},
    )
    return _response(control)


@router.post("/emergency-stop/clear", response_model=ControlResponse)
def clear_stop(
    request: Request,
    principal: Principal = Depends(require("control:read")),
    session: Session = Depends(get_session),
) -> ControlResponse:
    _require_admin(principal)
    control = OperationsRepository(session).control_for(principal.tenant_id)
    control.emergency_stop = False
    control.freeze_reason = ""
    control.updated_by = principal.user_id
    control.updated_at = datetime.now(timezone.utc)
    audit(
        session,
        action="control.emergency_stop_cleared",
        resource_type="operational_control",
        resource_id=control.id,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=request.state.correlation_id,
        payload={"external_actions_stopped": False},
    )
    return _response(control)


@router.post("/autonomy", response_model=ControlResponse)
def set_autonomy(
    body: AutonomyRequest,
    request: Request,
    principal: Principal = Depends(require("control:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ControlResponse:
    evaluate_autonomy_change(
        requested=body.level,
        l4_enabled=settings.autonomy_l4_enabled,
        actor_roles=set(principal.roles),
    )
    control = OperationsRepository(session).control_for(principal.tenant_id)
    control.autonomy_level = body.level
    control.updated_by = principal.user_id
    control.updated_at = datetime.now(timezone.utc)
    audit(
        session,
        action="control.autonomy_changed",
        resource_type="operational_control",
        resource_id=control.id,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=request.state.correlation_id,
        payload={"level": body.level},
    )
    return _response(control)
