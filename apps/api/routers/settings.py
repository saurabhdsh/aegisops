from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aegisops.core.config import Settings
from aegisops.core.exceptions import IntegrationError
from aegisops.observability.audit import audit
from aegisops.runtime.connections import masked_view, probe, save_dynatrace, save_openai, save_servicenow
from aegisops.runtime.demo import set_demo
from apps.api.dependencies import Principal, get_session, get_settings, require

router = APIRouter(prefix="/api/v1/settings/connections", tags=["settings"])


class ServiceNowConnection(BaseModel):
    instance_url: str = ""
    auth_mode: str = "oauth"
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    username: str = ""
    password: str = ""
    webhook_secret: str = ""
    table_incident: str = "incident"
    table_ci: str = "cmdb_ci"
    table_change: str = "change_request"


class DemoSwitch(BaseModel):
    enabled: bool


class OpenAiConnection(BaseModel):
    provider: str = "openai"
    base_url: str = ""
    model: str = ""
    api_version: str = "2024-10-21"
    api_key: str = ""


class DynatraceConnection(BaseModel):
    environment_url: str = ""
    api_token: str = ""
    webhook_secret: str = ""


@router.get("/demo")
def get_demo(
    principal: Principal = Depends(require("integration:read")),
    session: Session = Depends(get_session),
) -> dict:
    from sqlalchemy import func, select

    from aegisops.persistence.models import Incident
    from aegisops.persistence.repositories.operations import OperationsRepository

    enabled = OperationsRepository(session).demo_enabled(principal.tenant_id)
    count = int(
        session.scalar(
            select(func.count()).select_from(Incident).where(
                Incident.tenant_id == principal.tenant_id,
                Incident.source == "demo",
            )
        )
        or 0
    )
    return {"enabled": enabled, "incident_count": count if enabled else 0}


@router.put("/demo")
def put_demo(
    body: DemoSwitch,
    request: Request,
    principal: Principal = Depends(require("integration:write")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = set_demo(
        session,
        settings,
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        enabled=body.enabled,
    )
    audit(
        session,
        action="demo.toggled",
        resource_type="operational_control",
        resource_id="demo",
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=getattr(request.state, "correlation_id", ""),
        payload={"enabled": body.enabled, "incident_count": result["incident_count"]},
    )
    return result


@router.get("")
def get_connections(
    principal: Principal = Depends(require("integration:read")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    return masked_view(session, settings, principal.tenant_id)


@router.put("/servicenow")
def put_servicenow(
    body: ServiceNowConnection,
    request: Request,
    principal: Principal = Depends(require("integration:write")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    save_servicenow(session, settings, principal.tenant_id, body.model_dump())
    audit(
        session,
        action="connection.servicenow_saved",
        resource_type="connector_setting",
        resource_id="servicenow",
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=getattr(request.state, "correlation_id", ""),
        payload={"instance_url": body.instance_url, "auth_mode": body.auth_mode},
    )
    return masked_view(session, settings, principal.tenant_id)


@router.put("/dynatrace")
def put_dynatrace(
    body: DynatraceConnection,
    request: Request,
    principal: Principal = Depends(require("integration:write")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    save_dynatrace(session, settings, principal.tenant_id, body.model_dump())
    audit(
        session,
        action="connection.dynatrace_saved",
        resource_type="connector_setting",
        resource_id="dynatrace",
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=getattr(request.state, "correlation_id", ""),
        payload={"environment_url": body.environment_url},
    )
    return masked_view(session, settings, principal.tenant_id)


@router.put("/openai")
def put_openai(
    body: OpenAiConnection,
    request: Request,
    principal: Principal = Depends(require("integration:write")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    save_openai(session, settings, principal.tenant_id, body.model_dump())
    audit(
        session,
        action="connection.openai_saved",
        resource_type="connector_setting",
        resource_id="openai",
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        correlation_id=getattr(request.state, "correlation_id", ""),
        payload={"provider": body.provider, "base_url": body.base_url, "model": body.model},
    )
    return masked_view(session, settings, principal.tenant_id)


@router.post("/servicenow/test")
def test_servicenow(
    principal: Principal = Depends(require("integration:write")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _probe(session, settings, principal.tenant_id, "servicenow")


@router.post("/dynatrace/test")
def test_dynatrace(
    principal: Principal = Depends(require("integration:write")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _probe(session, settings, principal.tenant_id, "dynatrace")


@router.post("/openai/test")
def test_openai(
    principal: Principal = Depends(require("integration:write")),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _probe(session, settings, principal.tenant_id, "openai")


def _probe(session: Session, settings: Settings, tenant_id: str, kind: str) -> dict:
    try:
        return probe(session, settings, tenant_id, kind)
    except IntegrationError:
        session.commit()
        raise
