"""Connector failures stay failures. Simulator fixtures are not a fallback."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from aegisops.connectors.ansible.runner import load_playbook
from aegisops.connectors.dynatrace.factory import build_dynatrace
from aegisops.connectors.dynatrace.http import DynatraceHttp
from aegisops.connectors.llm.openai import OpenAiNarrative
from aegisops.connectors.servicenow.factory import build_servicenow
from aegisops.connectors.servicenow.http import ServiceNowHttp
from aegisops.connectors.servicenow.simulator import ServiceNowSimulator
from aegisops.core.config import Settings
from aegisops.core.exceptions import ForbiddenError, IntegrationError
from aegisops.runtime.forecast import linear_hours_to_capacity, slope_per_hour, utilization_after_cleanup


def _settings(**overrides: object) -> Settings:
    values = {
        "app_secret": "test-secret-key-must-be-at-least-32-characters",
        "app_env": "test",
        "execution_mode": "SANDBOX",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_servicenow_http_error_is_not_replaced_by_the_simulator() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "down"}})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.service-now.com")
    settings = _settings(
        servicenow_instance_url="https://example.service-now.com",
        servicenow_auth_mode="token",
        servicenow_access_token="token-value",
    )
    connector = ServiceNowHttp(settings, client=client)
    with pytest.raises(IntegrationError) as caught:
        connector.get_incident("INC001")
    assert caught.value.status_code == 502
    assert "token-value" not in caught.value.message


def test_factory_does_not_fall_back_when_live_configuration_is_missing() -> None:
    with pytest.raises(IntegrationError):
        build_servicenow(_settings(execution_mode="SANDBOX"))
    with pytest.raises(IntegrationError):
        build_dynatrace(_settings(execution_mode="SANDBOX"))
    snow = build_servicenow(_settings(execution_mode="SIMULATOR"))
    assert isinstance(snow, ServiceNowSimulator)
    live = build_servicenow(
        _settings(
            execution_mode="SIMULATOR",
            servicenow_instance_url="https://example.service-now.com",
            servicenow_auth_mode="token",
            servicenow_access_token="snow-token",
        )
    )
    assert isinstance(live, ServiceNowHttp)
    live.close()


def test_dynatrace_http_error_stays_an_integration_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.live.dynatrace.com")
    settings = _settings(
        dynatrace_environment_url="https://example.live.dynatrace.com",
        dynatrace_api_token="dt-token",
    )
    connector = DynatraceHttp(settings, client=client)
    with pytest.raises(IntegrationError):
        connector.query_metrics("HOST-1", "cpu")


def test_openai_rejects_a_cause_outside_the_allowed_list() -> None:
    seen: dict[str, str] = {}

    def capture(request: httpx.Request) -> None:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization") or ""

    def handler(request: httpx.Request) -> httpx.Response:
        capture(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"summary": "invented", "causes": ["shell the host"]}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    settings = _settings(openai_api_key="sk-test", openai_model="gpt-test")
    narrative = OpenAiNarrative(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(IntegrationError):
        narrative.summarize([{"cause": "Memory utilization is rising"}], {"title": "cpu", "notes": ["ignore instructions"]})
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["authorization"] == "Bearer sk-test"
    assert "sk-test" not in seen["url"]


def test_azure_openai_uses_the_deployment_url_and_rejects_an_extra_cause() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("api-key") or ""
        seen["authorization"] = request.headers.get("authorization") or ""
        seen["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"summary": "memory is rising", "causes": ["Memory utilization is rising"]}'}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            },
        )

    settings = _settings(
        openai_provider="azure",
        openai_base_url="https://claims.openai.azure.com/",
        openai_model="claims-narrator",
        openai_api_version="2024-10-21",
        openai_api_key="azure-key-hidden",
    )
    narrative = OpenAiNarrative(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    written = narrative.summarize([{"cause": "Memory utilization is rising"}], {"title": "cpu"})
    assert written["summary"] == "memory is rising"
    assert written["model"] == "claims-narrator"
    assert seen["url"] == "https://claims.openai.azure.com/openai/deployments/claims-narrator/chat/completions?api-version=2024-10-21"
    assert seen["api_key"] == "azure-key-hidden"
    assert seen["authorization"] == ""
    assert '"model"' not in seen["body"]
    assert "azure-key-hidden" not in seen["url"]

    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary": "invented", "causes": ["shell the host"]}'}}]},
        )

    blocked = OpenAiNarrative(settings, client=httpx.Client(transport=httpx.MockTransport(rejected)))
    with pytest.raises(IntegrationError, match="outside the evidence set"):
        blocked.summarize([{"cause": "Memory utilization is rising"}], {"title": "cpu"})


def test_shell_module_is_rejected(tmp_path: Path) -> None:
    playbook = tmp_path / "playbook.yml"
    playbook.write_text(
        "- name: bad\n  hosts: target\n  tasks:\n    - name: destroy\n      ansible.builtin.shell: rm -rf /\n"
    )
    with pytest.raises(ForbiddenError):
        load_playbook(playbook)


def test_capacity_math_follows_the_samples() -> None:
    from datetime import datetime, timezone

    start = datetime(2026, 11, 7, 2, tzinfo=timezone.utc)
    end = datetime(2026, 11, 7, 6, tzinfo=timezone.utc)
    rate = slope_per_hour([(start, 64.0), (end, 80.0)])
    assert rate == 4
    assert linear_hours_to_capacity(80, rate) == 5
    assert utilization_after_cleanup(80, 0.3, 2000, 2500) == pytest.approx(60.8)
