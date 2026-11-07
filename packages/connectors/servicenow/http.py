"""ServiceNow Table API client.

Field names are configurable because instances do not share custom columns.
A non-2xx response raises IntegrationError. This client never reads fixtures.
"""

from __future__ import annotations

from typing import Any

import httpx

from aegisops.core.config import Settings
from aegisops.core.exceptions import IntegrationError


def _value(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("value") or field.get("display_value") or "")
    if field is None:
        return ""
    return str(field)


class ServiceNowHttp:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.Client(
            base_url=settings.servicenow_instance_url,
            timeout=settings.http_timeout_seconds,
        )
        self.tables = {
            "incident": settings.servicenow_table_incident,
            "ci": settings.servicenow_table_ci,
            "change": settings.servicenow_table_change,
            "service": settings.servicenow_table_service,
        }

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _headers(self) -> dict[str, str]:
        mode = self.settings.servicenow_auth_mode
        if mode == "basic":
            return {"Accept": "application/json"}
        token = self.settings.servicenow_access_token
        if not token and mode == "oauth":
            token = self._client_credentials_token()
        if not token:
            raise IntegrationError("ServiceNow token is not configured")
        return {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    def _auth(self) -> httpx.BasicAuth | None:
        if self.settings.servicenow_auth_mode == "basic":
            return httpx.BasicAuth(self.settings.servicenow_username, self.settings.servicenow_password)
        return None

    def _client_credentials_token(self) -> str:
        response = self._send(
            "POST",
            "/oauth_token.do",
            data={
                "grant_type": "client_credentials",
                "client_id": self.settings.servicenow_client_id,
                "client_secret": self.settings.servicenow_client_secret,
            },
            headers={"Accept": "application/json"},
            auth=None,
        )
        token = str(response.get("access_token") or "")
        if not token:
            raise IntegrationError("ServiceNow token response did not include an access token")
        return token

    def _send(self, method: str, url: str, **kwargs: Any) -> dict:
        headers = kwargs.pop("headers", None) or self._headers()
        auth = kwargs.pop("auth", self._auth())
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self.client.request(method, url, headers=headers, auth=auth, **kwargs)
            except httpx.HTTPError as exc:
                raise IntegrationError(f"ServiceNow request failed: {exc.__class__.__name__}") from exc
            if response.status_code == 429 and attempt < 3:
                continue
            if response.status_code >= 400:
                raise IntegrationError(
                    "ServiceNow returned an error",
                    {"status": response.status_code, "path": url.split("?")[0]},
                )
            if not response.content:
                return {}
            body = response.json()
            return body if isinstance(body, dict) else {"result": body}

    def _page(self, table: str, query: str, *, limit: int) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while len(rows) < limit:
            page_size = min(100, limit - len(rows))
            body = self._send(
                "GET",
                f"/api/now/table/{table}",
                params={
                    "sysparm_query": query,
                    "sysparm_limit": page_size,
                    "sysparm_offset": offset,
                    "sysparm_display_value": "all",
                },
            )
            page = body.get("result") or []
            if not isinstance(page, list) or not page:
                break
            rows.extend(item for item in page if isinstance(item, dict))
            if len(page) < page_size:
                break
            offset += len(page)
        return rows[:limit]

    def list_incidents(self, limit: int = 50) -> list[dict]:
        rows = self._page(self.tables["incident"], "ORDERBYDESCopened_at", limit=limit)
        return [_normalize_incident(row) for row in rows]

    def get_incident(self, incident_id: str) -> dict:
        field = "sys_id" if len(incident_id) == 32 and incident_id.isalnum() else "number"
        rows = self._page(self.tables["incident"], f"{field}={incident_id}", limit=1)
        if not rows:
            raise IntegrationError("ServiceNow incident was not found", {"id": incident_id})
        return _normalize_incident(rows[0])

    def get_ci(self, ci_id: str) -> dict:
        rows = self._page(self.tables["ci"], f"sys_id={ci_id}", limit=1)
        if not rows:
            raise IntegrationError("ServiceNow configuration item was not found", {"id": ci_id})
        return _normalize_ci(rows[0])

    def get_related_changes(self, ci_id: str) -> list[dict]:
        rows = self._page(self.tables["change"], f"cmdb_ci={ci_id}^ORDERBYDESCsys_created_on", limit=10)
        return [_normalize_change(row) for row in rows]

    def search_similar_fixes(self, ci_id: str, limit: int = 3) -> list[dict]:
        rows = self._page(self.tables["change"], f"cmdb_ci={ci_id}^state=3^ORDERBYDESCsys_created_on", limit=limit)
        return [_normalize_change(row) for row in rows]

    def create_standard_change(self, *, ci_id: str, summary: str) -> dict:
        body = self._send(
            "POST",
            f"/api/now/table/{self.tables['change']}",
            json={"short_description": summary[:160], "type": "standard", "description": f"Configuration item {ci_id}"},
        )
        row = body.get("result") if isinstance(body.get("result"), dict) else body
        opened = _normalize_change(row)
        if not opened.get("number") or not opened.get("sys_id"):
            raise IntegrationError("ServiceNow did not return a standard change number")
        opened["type"] = "standard"
        opened["state"] = opened.get("state") or "implement"
        return opened

    def add_change_note(self, number: str, note: str) -> dict:
        current = self._change_by_number(number)
        self._send(
            "PATCH",
            f"/api/now/table/{self.tables['change']}/{current['sys_id']}",
            json={"work_notes": note},
        )
        return {"verified": True, "sys_id": current["sys_id"]}

    def close_change(self, number: str, note: str) -> dict:
        current = self._change_by_number(number)
        self._send(
            "PATCH",
            f"/api/now/table/{self.tables['change']}/{current['sys_id']}",
            json={"state": "3", "close_notes": note, "work_notes": note},
        )
        return {**current, "state": "closed"}

    def _change_by_number(self, number: str) -> dict:
        rows = self._page(self.tables["change"], f"number={number}", limit=1)
        if not rows:
            raise IntegrationError("ServiceNow change was not found", {"number": number})
        return _normalize_change(rows[0])

    def search_similar_incidents(self, incident: dict, limit: int = 3) -> list[dict]:
        number = incident.get("number") or ""
        ci = incident.get("ci_sys_id") or ""
        query = f"number!={number}"
        if ci:
            query += f"^cmdb_ci={ci}"
        rows = self._page(self.tables["incident"], query + "^ORDERBYDESCopened_at", limit=limit)
        return [_normalize_history(row) for row in rows]

    def add_work_note(self, incident_id: str, note: str) -> dict:
        current = self.get_incident(incident_id)
        sys_id = current.get("sys_id") or incident_id
        self._send(
            "PATCH",
            f"/api/now/table/{self.tables['incident']}/{sys_id}",
            json={"work_notes": note},
        )
        confirmed = self.get_incident(sys_id)
        visible = note in " ".join(confirmed.get("work_notes") or []) or note in (confirmed.get("work_notes_raw") or "")
        return {"verified": visible, "sys_id": sys_id}

    def update_state(self, incident_id: str, state: str, resolution: dict | None = None) -> None:
        current = self.get_incident(incident_id)
        payload: dict[str, Any] = {"state": state}
        if resolution:
            payload.update(resolution)
        self._send(
            "PATCH",
            f"/api/now/table/{self.tables['incident']}/{current.get('sys_id') or incident_id}",
            json=payload,
        )

    def health(self) -> dict:
        self._page(self.tables["incident"], "active=true", limit=1)
        return {"status": "ok", "capabilities": {"table_api": True, "oauth": self.settings.servicenow_auth_mode == "oauth"}}


def _normalize_incident(row: dict) -> dict:
    notes = _value(row.get("work_notes"))
    return {
        "number": _value(row.get("number")),
        "sys_id": _value(row.get("sys_id")),
        "title": _value(row.get("short_description")),
        "description": _value(row.get("description")),
        "state": _value(row.get("state")),
        "priority": _value(row.get("priority")),
        "ci_sys_id": _value(row.get("cmdb_ci")),
        "opened_at": _value(row.get("opened_at")),
        "work_notes": [line for line in notes.splitlines() if line.strip()],
        "work_notes_raw": notes,
    }


def _normalize_ci(row: dict) -> dict:
    return {
        "sys_id": _value(row.get("sys_id")),
        "name": _value(row.get("name")),
        "class": _value(row.get("sys_class_name")),
        "environment": _value(row.get("u_environment") or row.get("environment")),
        "criticality": _value(row.get("busines_criticality") or row.get("u_criticality")),
    }


def _normalize_change(row: dict) -> dict:
    return {
        "number": _value(row.get("number")),
        "sys_id": _value(row.get("sys_id")),
        "state": _value(row.get("state")),
        "summary": _value(row.get("short_description")),
        "opened_at": _value(row.get("opened_at") or row.get("sys_created_on")),
    }


def _normalize_history(row: dict) -> dict:
    return {
        "number": _value(row.get("number")),
        "title": _value(row.get("short_description")),
        "resolution_summary": _value(row.get("close_notes")),
        "similarity_reason": "same configuration item",
        "opened_at": _value(row.get("opened_at")),
    }
