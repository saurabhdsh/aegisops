"""Fixture-backed ServiceNow adapter. Used only when execution mode is SIMULATOR."""

from __future__ import annotations

import json
from pathlib import Path

from aegisops.core.exceptions import IntegrationError

_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "incident_scenario" / "catalog.json"
_CAPACITY = Path(__file__).resolve().parents[3] / "fixtures" / "capacity_scenario" / "catalog.json"


class ServiceNowSimulator:
    def __init__(self, catalog_path: Path | None = None) -> None:
        path = catalog_path or _ROOT
        self.catalog = json.loads(path.read_text())
        self.capacity = json.loads(_CAPACITY.read_text())
        self.notes: dict[str, list[str]] = {}
        self.changes: dict[str, dict] = {}

    def get_incident(self, incident_id: str) -> dict:
        incident = self.catalog["incident"]
        if incident_id not in {incident["number"], incident["sys_id"]}:
            raise IntegrationError("Simulator catalog has no incident with that id", {"id": incident_id})
        notes = list(incident.get("work_notes") or []) + self.notes.get(incident["sys_id"], [])
        return {**incident, "work_notes": notes}

    def get_ci(self, ci_id: str) -> dict:
        ci = self.catalog["ci"]
        if ci_id in {ci["external_id"], ci["name"]}:
            return ci
        host = self.capacity["host"]
        if ci_id in {host["external_id"], host["name"]}:
            return host
        raise IntegrationError("Simulator catalog has no configuration item with that id", {"id": ci_id})

    def get_related_changes(self, ci_id: str) -> list[dict]:
        ci = self.catalog["ci"]
        if ci_id in {ci["external_id"], ci["name"]}:
            return list(self.catalog.get("changes") or [])
        host = self.capacity["host"]
        if ci_id in {host["external_id"], host["name"]}:
            return list(self.capacity.get("changes") or [])
        return []

    def search_similar_fixes(self, ci_id: str, limit: int = 3) -> list[dict]:
        host = self.capacity["host"]
        if ci_id not in {host["external_id"], host["name"]}:
            return []
        return list(self.capacity.get("similar_fixes") or [])[:limit]

    def create_standard_change(self, *, ci_id: str, summary: str) -> dict:
        host = self.capacity["host"]
        if ci_id not in {host["external_id"], host["name"]}:
            raise IntegrationError("Simulator catalog cannot open a change for that configuration item", {"id": ci_id})
        record = {
            "number": "CHG0044101",
            "sys_id": "chg4101claimsdb01",
            "state": "implement",
            "type": "standard",
            "summary": summary,
            "ci_id": ci_id,
            "work_notes": [],
        }
        self.changes[record["number"]] = record
        return dict(record)

    def add_change_note(self, number: str, note: str) -> dict:
        record = self.changes.get(number)
        if record is None:
            raise IntegrationError("Simulator catalog has no change with that number", {"number": number})
        record["work_notes"].append(note)
        return {"verified": note in record["work_notes"], "sys_id": record["sys_id"]}

    def close_change(self, number: str, note: str) -> dict:
        record = self.changes.get(number)
        if record is None:
            raise IntegrationError("Simulator catalog has no change with that number", {"number": number})
        record["state"] = "closed"
        record["close_notes"] = note
        record["work_notes"].append(note)
        if record["state"] != "closed":
            raise IntegrationError("Simulator change closure failed read-after-write")
        return dict(record)

    def search_similar_incidents(self, incident: dict, limit: int = 3) -> list[dict]:
        number = incident.get("number") or incident.get("external_number")
        if number != self.catalog["incident"]["number"]:
            return []
        return list(self.catalog.get("similar") or [])[:limit]

    def add_work_note(self, incident_id: str, note: str) -> dict:
        current = self.get_incident(incident_id)
        self.notes.setdefault(current["sys_id"], []).append(note)
        echoed = self.get_incident(current["sys_id"])
        if note not in echoed["work_notes"]:
            raise IntegrationError("Simulator work note failed read-after-write")
        return {"verified": True, "sys_id": current["sys_id"]}

    def update_state(self, incident_id: str, state: str, resolution: dict | None = None) -> None:
        current = self.get_incident(incident_id)
        self.catalog["incident"]["state"] = state
        if resolution:
            self.catalog["incident"]["resolution"] = resolution
        if self.get_incident(current["sys_id"])["state"] != state:
            raise IntegrationError("Simulator state update failed read-after-write")

    def health(self) -> dict:
        return {"status": "ok", "mode": "SIMULATOR", "capabilities": {"table_api": True, "fixtures": True}}
