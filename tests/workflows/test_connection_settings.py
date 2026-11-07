"""Connection settings store secrets encrypted and test the real HTTP clients."""

from __future__ import annotations

from sqlalchemy import select

from aegisops.core.secretbox import open_secret, seal
from aegisops.runtime.connections import overlay
from aegisops.persistence.models import AuditEvent, ConnectorSetting
from tests.conftest import auth_header


def test_secretbox_round_trip() -> None:
    blob = seal("token-value", "test-secret-key-must-be-at-least-32-characters")
    assert "token-value" not in blob
    assert open_secret(blob, "test-secret-key-must-be-at-least-32-characters") == "token-value"


def test_saved_secrets_are_not_returned_and_blank_keeps_them(api) -> None:
    headers = auth_header(api)
    saved = api.put(
        "/api/v1/settings/connections/servicenow",
        headers=headers,
        json={
            "instance_url": "http://127.0.0.1:9",
            "auth_mode": "token",
            "access_token": "snow-token-should-stay-hidden",
            "table_incident": "incident",
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()["servicenow"]
    assert body["instance_url"] == "http://127.0.0.1:9"
    assert body["has_access_token"] is True
    assert "snow-token-should-stay-hidden" not in saved.text

    again = api.put(
        "/api/v1/settings/connections/servicenow",
        headers=headers,
        json={"instance_url": "http://127.0.0.1:9", "auth_mode": "token", "access_token": ""},
    )
    assert again.status_code == 200
    assert again.json()["servicenow"]["has_access_token"] is True

    session = api.app.state.sessions()
    try:
        row = session.scalar(select(ConnectorSetting).where(ConnectorSetting.kind == "servicenow"))
        assert row is not None
        opened = open_secret(row.secret_ciphertext, api.app.state.settings.app_secret)
        assert "snow-token-should-stay-hidden" in opened
        audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "connection.servicenow_saved"))
        assert audit is not None
        assert "snow-token-should-stay-hidden" not in str(audit.payload)
    finally:
        session.close()


def test_a_saved_servicenow_connection_is_used_for_the_incident_board(api) -> None:
    headers = auth_header(api)
    saved = api.put(
        "/api/v1/settings/connections/servicenow",
        headers=headers,
        json={"instance_url": "http://127.0.0.1:9", "auth_mode": "token", "access_token": "snow-token-hidden"},
    )
    assert saved.status_code == 200, saved.text
    listed = api.get("/api/v1/incidents", headers=headers)
    assert listed.status_code == 502, listed.text
    assert listed.json()["error"]["code"] == "integration_error"
    assert "snow-token-hidden" not in listed.text
    probed = api.post("/api/v1/integrations/servicenow/test", headers=headers)
    assert probed.status_code == 502, probed.text
    assert "snow-token-hidden" not in probed.text


def test_connection_test_calls_the_saved_endpoint(api) -> None:
    headers = auth_header(api)
    api.put(
        "/api/v1/settings/connections/dynatrace",
        headers=headers,
        json={"environment_url": "http://127.0.0.1:9", "api_token": "dt-token-hidden"},
    )
    probed = api.post("/api/v1/settings/connections/dynatrace/test", headers=headers)
    assert probed.status_code == 502, probed.text
    assert probed.json()["error"]["code"] == "integration_error"
    assert "dt-token-hidden" not in probed.text
    listed = api.get("/api/v1/settings/connections", headers=headers)
    assert listed.json()["dynatrace"]["last_health_status"] == "error"


def test_openai_and_azure_keys_stay_hidden_and_a_failed_call_stays_an_error(api) -> None:
    headers = auth_header(api)
    missing = api.put(
        "/api/v1/settings/connections/openai",
        headers=headers,
        json={"provider": "azure", "base_url": "", "model": "claims-narrator", "api_key": "azure-key-hidden"},
    )
    assert missing.status_code == 422

    saved = api.put(
        "/api/v1/settings/connections/openai",
        headers=headers,
        json={
            "provider": "azure",
            "base_url": "http://127.0.0.1:9",
            "model": "claims-narrator",
            "api_version": "2024-10-21",
            "api_key": "azure-key-hidden",
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()["openai"]
    assert body["provider"] == "azure"
    assert body["base_url"] == "http://127.0.0.1:9"
    assert body["model"] == "claims-narrator"
    assert body["has_api_key"] is True
    assert "azure-key-hidden" not in saved.text

    again = api.put(
        "/api/v1/settings/connections/openai",
        headers=headers,
        json={"provider": "azure", "base_url": "http://127.0.0.1:9", "model": "claims-narrator", "api_key": ""},
    )
    assert again.status_code == 200
    assert again.json()["openai"]["has_api_key"] is True

    session = api.app.state.sessions()
    try:
        row = session.scalar(select(ConnectorSetting).where(ConnectorSetting.kind == "openai"))
        assert row is not None
        opened = open_secret(row.secret_ciphertext, api.app.state.settings.app_secret)
        assert "azure-key-hidden" in opened
        audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "connection.openai_saved"))
        assert audit is not None
        assert "azure-key-hidden" not in str(audit.payload)
    finally:
        session.close()

    probed = api.post("/api/v1/settings/connections/openai/test", headers=headers)
    assert probed.status_code == 502, probed.text
    assert probed.json()["error"]["code"] == "integration_error"
    assert "azure-key-hidden" not in probed.text
    listed = api.get("/api/v1/settings/connections", headers=headers)
    assert listed.json()["openai"]["last_health_status"] == "error"


def test_blank_openai_key_keeps_the_process_key(api) -> None:
    headers = auth_header(api)
    saved = api.put(
        "/api/v1/settings/connections/openai",
        headers=headers,
        json={"provider": "openai", "model": "gpt-test", "api_key": ""},
    )
    assert saved.status_code == 200, saved.text
    session = api.app.state.sessions()
    try:
        row = session.scalar(select(ConnectorSetting).where(ConnectorSetting.kind == "openai"))
        assert row is not None
        tuned = overlay(
            session,
            api.app.state.settings.model_copy(update={"openai_api_key": "process-key"}),
            row.tenant_id,
        )
        assert tuned.openai_api_key == "process-key"
        assert tuned.openai_model == "gpt-test"
        assert tuned.execution_mode == "SIMULATOR"
    finally:
        session.close()
