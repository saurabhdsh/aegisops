"""Tenant connection settings. Secrets are encrypted. A blank secret field keeps the stored value."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.connectors.dynatrace.http import DynatraceHttp
from aegisops.connectors.llm.openai import OpenAiNarrative
from aegisops.connectors.servicenow.http import ServiceNowHttp
from aegisops.core.config import Settings
from aegisops.core.exceptions import AegisError, IntegrationError
from aegisops.core.identifiers import new_id
from aegisops.core.secretbox import open_secret, seal
from aegisops.persistence.models import ConnectorSetting, Integration

_SNOW_SECRETS = ("client_secret", "access_token", "password", "webhook_secret")
_DYNA_SECRETS = ("api_token", "webhook_secret")
_OPENAI_DEFAULT = "https://api.openai.com/v1"


def servicenow_ready(settings: Settings) -> bool:
    if not settings.servicenow_instance_url:
        return False
    if settings.servicenow_auth_mode == "basic":
        return bool(settings.servicenow_username and settings.servicenow_password)
    if settings.servicenow_auth_mode == "oauth":
        return bool(settings.servicenow_access_token or (settings.servicenow_client_id and settings.servicenow_client_secret))
    return bool(settings.servicenow_access_token)


def dynatrace_ready(settings: Settings) -> bool:
    return bool(settings.dynatrace_environment_url and settings.dynatrace_api_token)


def masked_view(session: Session, settings: Settings, tenant_id: str) -> dict:
    snow = _row(session, tenant_id, "servicenow")
    dyna = _row(session, tenant_id, "dynatrace")
    model = _row(session, tenant_id, "openai")
    snow_public, snow_secret = _parts(settings, snow)
    dyna_public, dyna_secret = _parts(settings, dyna)
    model_public, model_secret = _parts(settings, model)
    provider = (model.auth_mode if model else "") or settings.openai_provider
    return {
        "execution_mode": settings.execution_mode,
        "servicenow": {
            "instance_url": (snow.base_url if snow else "") or settings.servicenow_instance_url,
            "auth_mode": (snow.auth_mode if snow else "") or settings.servicenow_auth_mode,
            "client_id": snow_public.get("client_id") or settings.servicenow_client_id,
            "username": snow_public.get("username") or settings.servicenow_username,
            "table_incident": snow_public.get("table_incident") or settings.servicenow_table_incident,
            "table_ci": snow_public.get("table_ci") or settings.servicenow_table_ci,
            "table_change": snow_public.get("table_change") or settings.servicenow_table_change,
            "has_client_secret": bool(snow_secret.get("client_secret") or settings.servicenow_client_secret),
            "has_access_token": bool(snow_secret.get("access_token") or settings.servicenow_access_token),
            "has_password": bool(snow_secret.get("password") or settings.servicenow_password),
            "has_webhook_secret": bool(snow_secret.get("webhook_secret") or settings.servicenow_webhook_secret),
            **_health(session, tenant_id, "servicenow"),
        },
        "dynatrace": {
            "environment_url": (dyna.base_url if dyna else "") or settings.dynatrace_environment_url,
            "has_api_token": bool(dyna_secret.get("api_token") or settings.dynatrace_api_token),
            "has_webhook_secret": bool(dyna_secret.get("webhook_secret") or settings.dynatrace_webhook_secret),
            **_health(session, tenant_id, "dynatrace"),
        },
        "openai": {
            "provider": provider,
            "base_url": (model.base_url if model else "") or settings.openai_base_url,
            "model": model_public.get("model") or settings.openai_model,
            "api_version": model_public.get("api_version") or settings.openai_api_version,
            "has_api_key": bool(model_secret.get("api_key") or settings.openai_api_key),
            **_health(session, tenant_id, "openai"),
        },
    }


def save_servicenow(session: Session, settings: Settings, tenant_id: str, body: dict) -> None:
    _save(
        session,
        settings,
        tenant_id,
        kind="servicenow",
        base_url=str(body.get("instance_url") or "").strip().rstrip("/"),
        auth_mode=str(body.get("auth_mode") or "oauth"),
        public={
            "client_id": str(body.get("client_id") or "").strip(),
            "username": str(body.get("username") or "").strip(),
            "table_incident": str(body.get("table_incident") or "incident").strip() or "incident",
            "table_ci": str(body.get("table_ci") or "cmdb_ci").strip() or "cmdb_ci",
            "table_change": str(body.get("table_change") or "change_request").strip() or "change_request",
        },
        secrets={key: body.get(key) for key in _SNOW_SECRETS},
    )


def save_dynatrace(session: Session, settings: Settings, tenant_id: str, body: dict) -> None:
    _save(
        session,
        settings,
        tenant_id,
        kind="dynatrace",
        base_url=str(body.get("environment_url") or "").strip().rstrip("/"),
        auth_mode="token",
        public={},
        secrets={key: body.get(key) for key in _DYNA_SECRETS},
    )


def save_openai(session: Session, settings: Settings, tenant_id: str, body: dict) -> None:
    provider = str(body.get("provider") or "openai").strip().lower()
    if provider not in {"openai", "azure"}:
        raise AegisError("validation_error", "Model provider must be openai or azure", 422)
    base_url = str(body.get("base_url") or "").strip().rstrip("/")
    if provider == "openai" and not base_url:
        base_url = _OPENAI_DEFAULT
    if provider == "azure" and not base_url:
        raise AegisError("validation_error", "Azure OpenAI endpoint is required", 422)
    model_name = str(body.get("model") or "").strip()
    if not model_name:
        raise AegisError("validation_error", "A model or Azure deployment name is required", 422)
    _save(
        session,
        settings,
        tenant_id,
        kind="openai",
        base_url=base_url,
        auth_mode=provider,
        public={
            "model": model_name,
            "api_version": str(body.get("api_version") or settings.openai_api_version or "2024-10-21").strip(),
        },
        secrets={"api_key": body.get("api_key")},
    )


def probe(session: Session, settings: Settings, tenant_id: str, kind: str) -> dict:
    tuned = overlay(session, settings, tenant_id)
    try:
        if kind == "servicenow":
            if not tuned.servicenow_instance_url:
                raise AegisError("validation_error", "ServiceNow instance URL is required", 422)
            report = ServiceNowHttp(tuned).health()
        elif kind == "dynatrace":
            if not tuned.dynatrace_environment_url or not tuned.dynatrace_api_token:
                raise AegisError("validation_error", "Dynatrace environment URL and API token are required", 422)
            report = DynatraceHttp(tuned).health()
        elif kind == "openai":
            if not tuned.openai_api_key or not tuned.openai_model:
                raise AegisError("validation_error", "An API key and a model or deployment name are required", 422)
            if tuned.openai_provider == "azure" and not tuned.openai_base_url:
                raise AegisError("validation_error", "Azure OpenAI endpoint is required", 422)
            narrative = OpenAiNarrative(tuned)
            try:
                report = narrative.health()
            finally:
                narrative.close()
        else:
            raise AegisError("validation_error", "Unknown connector", 422)
    except IntegrationError as exc:
        _write_health(session, tenant_id, kind, "error", exc.message, {})
        raise
    _write_health(session, tenant_id, kind, "ok", "", report.get("capabilities") or {})
    report["mode"] = "live"
    return report


def overlay(session: Session, settings: Settings, tenant_id: str) -> Settings:
    """Return settings with saved connection values applied. Does not change execution mode."""
    snow = _row(session, tenant_id, "servicenow")
    dyna = _row(session, tenant_id, "dynatrace")
    model = _row(session, tenant_id, "openai")
    snow_public, snow_secret = _parts(settings, snow)
    dyna_public, dyna_secret = _parts(settings, dyna)
    model_public, model_secret = _parts(settings, model)
    updates: dict = {}
    if snow is not None and snow.base_url:
        updates["servicenow_instance_url"] = snow.base_url
        updates["servicenow_auth_mode"] = snow.auth_mode or settings.servicenow_auth_mode
        updates["servicenow_client_id"] = snow_public.get("client_id") or ""
        updates["servicenow_username"] = snow_public.get("username") or ""
        updates["servicenow_table_incident"] = snow_public.get("table_incident") or "incident"
        updates["servicenow_table_ci"] = snow_public.get("table_ci") or "cmdb_ci"
        updates["servicenow_table_change"] = snow_public.get("table_change") or "change_request"
        updates["servicenow_client_secret"] = snow_secret.get("client_secret") or ""
        updates["servicenow_access_token"] = snow_secret.get("access_token") or ""
        updates["servicenow_password"] = snow_secret.get("password") or ""
        updates["servicenow_webhook_secret"] = snow_secret.get("webhook_secret") or settings.servicenow_webhook_secret
    if dyna is not None and dyna.base_url:
        updates["dynatrace_environment_url"] = dyna.base_url
        updates["dynatrace_api_token"] = dyna_secret.get("api_token") or ""
        updates["dynatrace_webhook_secret"] = dyna_secret.get("webhook_secret") or settings.dynatrace_webhook_secret
    if model is not None and model.base_url:
        updates["openai_provider"] = model.auth_mode or "openai"
        updates["openai_base_url"] = model.base_url
        updates["openai_model"] = model_public.get("model") or ""
        updates["openai_api_version"] = model_public.get("api_version") or settings.openai_api_version
        updates["openai_api_key"] = model_secret.get("api_key") or settings.openai_api_key
    if not updates:
        return settings
    return settings.model_copy(update=updates)


def _save(
    session: Session,
    settings: Settings,
    tenant_id: str,
    *,
    kind: str,
    base_url: str,
    auth_mode: str,
    public: dict,
    secrets: dict,
) -> None:
    if not base_url:
        raise AegisError("validation_error", f"{kind} URL is required", 422)
    if kind == "servicenow" and auth_mode not in {"oauth", "token", "basic"}:
        raise AegisError("validation_error", "ServiceNow auth mode must be oauth, token, or basic", 422)
    row = _row(session, tenant_id, kind)
    _, current = _parts(settings, row)
    merged = dict(current)
    for key, value in secrets.items():
        if value is None:
            continue
        text = str(value)
        if text == "":
            continue
        merged[key] = text
    if row is None:
        row = ConnectorSetting(
            id=new_id("cns"),
            tenant_id=tenant_id,
            kind=kind,
            base_url=base_url,
            auth_mode=auth_mode,
            public_config=public,
            secret_ciphertext=seal(json.dumps(merged), settings.app_secret),
        )
        session.add(row)
    else:
        row.base_url = base_url
        row.auth_mode = auth_mode
        row.public_config = public
        row.secret_ciphertext = seal(json.dumps(merged), settings.app_secret)
        row.updated_at = datetime.now(timezone.utc)
    _ensure_integration(session, tenant_id, kind, base_url, auth_mode)
    session.flush()


def _row(session: Session, tenant_id: str, kind: str) -> ConnectorSetting | None:
    return session.scalar(
        select(ConnectorSetting).where(ConnectorSetting.tenant_id == tenant_id, ConnectorSetting.kind == kind)
    )


def _parts(settings: Settings, row: ConnectorSetting | None) -> tuple[dict, dict]:
    if row is None:
        return {}, {}
    public = dict(row.public_config or {})
    if not row.secret_ciphertext:
        return public, {}
    try:
        secret = json.loads(open_secret(row.secret_ciphertext, settings.app_secret) or "{}")
    except (ValueError, json.JSONDecodeError):
        secret = {}
    if not isinstance(secret, dict):
        secret = {}
    return public, {key: str(value) for key, value in secret.items() if value}


def _health(session: Session, tenant_id: str, kind: str) -> dict:
    row = session.scalar(
        select(Integration).where(Integration.tenant_id == tenant_id, Integration.kind == kind, Integration.name == "default")
    )
    if row is None:
        return {"last_health_status": "unknown", "last_error": "", "last_health_at": None}
    return {
        "last_health_status": row.last_health_status,
        "last_error": row.last_error,
        "last_health_at": row.last_health_at.isoformat() if row.last_health_at else None,
    }


def _ensure_integration(session: Session, tenant_id: str, kind: str, base_url: str, auth_mode: str) -> Integration:
    row = session.scalar(
        select(Integration).where(Integration.tenant_id == tenant_id, Integration.kind == kind, Integration.name == "default")
    )
    if row is None:
        row = Integration(
            id=new_id("int"),
            tenant_id=tenant_id,
            kind=kind,
            name="default",
            base_url=base_url,
            auth_mode=auth_mode,
            secret_ref="connector_settings",
            status="configured",
        )
        session.add(row)
        session.flush()
    else:
        row.base_url = base_url
        row.auth_mode = auth_mode
        row.secret_ref = "connector_settings"
        row.status = "configured"
    return row


def _write_health(session: Session, tenant_id: str, kind: str, status: str, error: str, capabilities: dict) -> None:
    row = session.scalar(
        select(Integration).where(Integration.tenant_id == tenant_id, Integration.kind == kind, Integration.name == "default")
    )
    if row is None:
        return
    row.last_health_at = datetime.now(timezone.utc)
    row.last_health_status = status
    row.last_error = error[:500]
    row.capabilities = capabilities
    row.status = "ok" if status == "ok" else "error"
