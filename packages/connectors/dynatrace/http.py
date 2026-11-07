"""Dynatrace Metrics and Problems API v2.

Optional APIs that respond 404 are reported as unavailable capabilities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from aegisops.core.config import Settings
from aegisops.core.exceptions import IntegrationError

_METRIC_SELECTORS = {
    "cpu": "builtin:host.cpu.usage:avg",
    "memory": "builtin:host.mem.usage:avg",
    "disk": "builtin:host.disk.usedPct:avg",
}


class DynatraceHttp:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.Client(
            base_url=settings.dynatrace_environment_url,
            timeout=settings.http_timeout_seconds,
            headers={"Authorization": f"Api-Token {settings.dynatrace_api_token}", "Accept": "application/json"},
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _send(self, method: str, url: str, *, optional: bool = False, **kwargs: Any) -> tuple[int, dict]:
        try:
            response = self.client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Dynatrace request failed: {exc.__class__.__name__}") from exc
        if response.status_code == 404 and optional:
            return 404, {}
        if response.status_code >= 400:
            raise IntegrationError("Dynatrace returned an error", {"status": response.status_code, "path": url})
        if not response.content:
            return response.status_code, {}
        body = response.json()
        return response.status_code, body if isinstance(body, dict) else {"result": body}

    def query_metrics(self, entity_id: str, metric_key: str, *, after_action: bool = False) -> dict:
        del after_action  # Live data is whatever the tenant returns at query time.
        selector = _METRIC_SELECTORS.get(metric_key, metric_key)
        status, body = self._send(
            "GET",
            "/api/v2/metrics/query",
            params={"metricSelector": selector, "entitySelector": _entity_selector(entity_id), "resolution": "5m"},
        )
        points = _points(body)
        return {
            "entity_id": entity_id,
            "metric_key": metric_key,
            "points": points,
            "source": "dynatrace",
            "query_reference": f"/api/v2/metrics/query?metricSelector={selector}&entity={entity_id}",
            "status": status,
        }

    def logs(self, entity_id: str) -> list[dict]:
        status, body = self._send(
            "GET",
            "/api/v2/logs/search",
            optional=True,
            params={"query": f'host("{entity_id.replace(chr(34), "")}")', "limit": 20},
        )
        if status == 404:
            return []
        return list(body.get("results") or [])

    def problems(self) -> list[dict]:
        _status, body = self._send("GET", "/api/v2/problems", params={"pageSize": 50})
        return list(body.get("problems") or [])

    def traces(self, entity_id: str) -> list[dict]:
        status, body = self._send(
            "GET",
            "/api/v2/traces",
            optional=True,
            params={"pageSize": 5, "entitySelector": _entity_selector(entity_id)},
        )
        if status == 404:
            return []
        traces = body.get("traces")
        return list(traces) if isinstance(traces, list) else []

    def health(self) -> dict:
        capabilities: dict[str, str] = {}
        for name, path, optional in (
            ("metrics", "/api/v2/metrics", False),
            ("problems", "/api/v2/problems", False),
            ("logs", "/api/v2/logs/search", True),
            ("traces", "/api/v2/traces", True),
        ):
            status, _body = self._send("GET", path, optional=optional, params={"pageSize": 1})
            capabilities[name] = "unavailable" if status == 404 else "available"
        return {"status": "ok", "capabilities": capabilities}


def _entity_selector(entity_id: str) -> str:
    token = entity_id.replace('"', "")
    if token.startswith(("HOST-", "SERVICE-", "PROCESS_GROUP-", "APPLICATION-", "DEMO-")):
        return f'entityId("{token}")'
    return f'type(HOST),entityName.equals("{token}")'


def _points(body: dict) -> list[dict]:
    points: list[dict] = []
    for result in body.get("result") or []:
        for series in result.get("data") or []:
            timestamps = series.get("timestamps") or []
            values = series.get("values") or []
            for raw_ts, raw_value in zip(timestamps, values):
                if raw_value is None:
                    continue
                stamp = datetime.fromtimestamp(int(raw_ts) / 1000, tz=timezone.utc)
                points.append({"timestamp": stamp.isoformat(), "value": float(raw_value), "unit": "percent"})
    return points
