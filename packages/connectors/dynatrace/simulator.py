"""Fixture-backed Dynatrace adapter. Used only when execution mode is SIMULATOR."""

from __future__ import annotations

import json
from pathlib import Path

_INCIDENT = Path(__file__).resolve().parents[3] / "fixtures" / "incident_scenario" / "catalog.json"
_CAPACITY = Path(__file__).resolve().parents[3] / "fixtures" / "capacity_scenario" / "catalog.json"


class DynatraceSimulator:
    def __init__(self) -> None:
        self.incident = json.loads(_INCIDENT.read_text())
        self.capacity = json.loads(_CAPACITY.read_text())

    def query_metrics(self, entity_id: str, metric_key: str, *, after_action: bool = False) -> dict:
        series = self._series(entity_id, metric_key, after_action=after_action)
        return {
            "entity_id": entity_id,
            "metric_key": metric_key,
            "points": series,
            "source": "dynatrace-simulator",
            "query_reference": f"fixture:{entity_id}:{metric_key}:{'after' if after_action else 'before'}",
        }

    def logs(self, entity_id: str) -> list[dict]:
        if entity_id == self.incident["metrics"]["entity_id"]:
            return list(self.incident.get("logs") or [])
        return []

    def traces(self, entity_id: str) -> list[dict]:
        if entity_id == self.incident["metrics"]["entity_id"]:
            return list(self.incident.get("traces") or [])
        return []

    def problems(self) -> list[dict]:
        return [{"problemId": "SIM-CPU", "title": self.incident["incident"]["title"]}]

    def health(self) -> dict:
        return {
            "status": "ok",
            "mode": "SIMULATOR",
            "capabilities": {
                "metrics": "available",
                "problems": "available",
                "logs": "available",
                "traces": "available" if self.incident.get("traces") else "unavailable",
            },
        }

    def _series(self, entity_id: str, metric_key: str, *, after_action: bool) -> list[dict]:
        if entity_id == self.incident["metrics"]["entity_id"]:
            if after_action:
                series = self.incident["after_restart"].get(metric_key)
                return list(series) if isinstance(series, list) else []
            return list(self.incident["metrics"].get(metric_key) or [])
        if entity_id == self.capacity["host"]["entity_id"] and metric_key == "disk":
            if after_action:
                return []
            return list(self.capacity.get("disk_series") or [])
        return []
