"""Agent work that is shared by the engine and the agent classes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aegisops.core.exceptions import IntegrationError
from aegisops.runtime.forecast import linear_hours_to_capacity, slope_per_hour, utilization_after_cleanup
from aegisops.runtime.signals import deployment_lag_hours, rank_hypotheses


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _series_points(series: dict) -> list[tuple[datetime, float]]:
    points = []
    for item in series.get("points") or []:
        stamp = _parse(item["timestamp"]) if isinstance(item["timestamp"], str) else item["timestamp"]
        if stamp is not None:
            points.append((stamp, float(item["value"])))
    return points


def triage(payload: dict, snow: object) -> dict:
    number = payload.get("incident_number") or ""
    sys_id = payload.get("incident_sys_id") or ""
    remote = None
    connector_error = ""
    for key in (number, sys_id):
        if not key:
            continue
        try:
            remote = snow.get_incident(key)  # type: ignore[attr-defined]
            break
        except IntegrationError as exc:
            connector_error = exc.message
    changes: list[dict] = []
    similar: list[dict] = []
    ci = None
    if payload.get("ci_external_id"):
        try:
            ci = snow.get_ci(payload["ci_external_id"])  # type: ignore[attr-defined]
            changes = snow.get_related_changes(payload["ci_external_id"])  # type: ignore[attr-defined]
        except IntegrationError as exc:
            connector_error = exc.message
    if remote:
        similar = snow.search_similar_incidents(remote, limit=3)  # type: ignore[attr-defined]
    return {
        "impacted_ci": ci,
        "business_service": (ci or {}).get("business_service"),
        "priority": (remote or {}).get("priority") or payload.get("priority") or "",
        "related_changes": changes,
        "similar": similar[:3],
        "similar_count": len(similar[:3]),
        "connector_error": connector_error,
        "untrusted_notes": (remote or {}).get("work_notes") or payload.get("work_notes") or [],
    }


def analyze(payload: dict, dyna: object, narrative: object | None) -> dict:
    entity_id = payload.get("entity_id") or ""
    evidence_ids = list(payload.get("evidence_ids") or [])
    cpu = dyna.query_metrics(entity_id, "cpu") if entity_id else {"points": []}  # type: ignore[attr-defined]
    memory = dyna.query_metrics(entity_id, "memory") if entity_id else {"points": []}  # type: ignore[attr-defined]
    logs = dyna.logs(entity_id) if entity_id else []  # type: ignore[attr-defined]
    traces: list[dict] = []
    traces_error = ""
    if entity_id and hasattr(dyna, "traces"):
        try:
            traces = list(dyna.traces(entity_id) or [])  # type: ignore[attr-defined]
        except IntegrationError as exc:
            traces_error = exc.message
    cpu_points = _series_points(cpu)
    memory_points = _series_points(memory)
    opened = _parse(payload.get("opened_at"))
    deployed = _parse((payload.get("changes") or [{}])[0].get("opened_at") if payload.get("changes") else None)
    signals = {
        "memory_slope_per_hour": slope_per_hour(memory_points),
        "cpu_slope_per_hour": slope_per_hour(cpu_points),
        "deployment_lag_hours": deployment_lag_hours(deployed, opened),
        "error_rate": payload.get("error_rate"),
        "heap_profile": False,
        "cpu_series": bool(cpu_points),
        "evidence_ids": evidence_ids,
    }
    hypotheses = rank_hypotheses(signals)
    llm_error = ""
    narrative_summary = ""
    model = ""
    token_input = 0
    token_output = 0
    if narrative and hypotheses:
        try:
            written = narrative.summarize(
                hypotheses,
                {
                    "title": payload.get("title", ""),
                    "priority": payload.get("priority", ""),
                    "memory_slope_per_hour": signals["memory_slope_per_hour"],
                    "cpu_slope_per_hour": signals["cpu_slope_per_hour"],
                    "deployment_lag_hours": signals["deployment_lag_hours"],
                    "error_rate": signals["error_rate"],
                    "notes": payload.get("notes") or [],
                },
            )
            narrative_summary = written["summary"]
            model = written["model"]
            token_input = written["token_input"]
            token_output = written["token_output"]
        except IntegrationError as exc:
            llm_error = exc.message
    return {
        "signals": {key: value for key, value in signals.items() if key != "evidence_ids"},
        "hypotheses": hypotheses,
        "logs": logs,
        "traces": traces,
        "traces_error": traces_error,
        "series": {"cpu": cpu, "memory": memory},
        "narrative": narrative_summary,
        "llm_error": llm_error,
        "model": model or "deterministic-ranker",
        "token_input": token_input,
        "token_output": token_output,
        "confidence_note": "Scores are derived from measured slopes and are not calibrated probabilities.",
    }


def assess_capacity(payload: dict, snow: object, dyna: object) -> dict:
    entity_id = payload.get("entity_id") or ""
    points = list(payload.get("points") or [])
    connector_error = ""
    if entity_id:
        try:
            series = dyna.query_metrics(entity_id, "disk")  # type: ignore[attr-defined]
            queried = list(series.get("points") or [])
            if queried:
                points = queried
        except IntegrationError as exc:
            connector_error = exc.message
    forecast = forecast_disk(points)
    ci = None
    changes: list[dict] = []
    fixes: list[dict] = []
    ci_id = payload.get("ci_external_id") or ""
    if ci_id:
        try:
            ci = snow.get_ci(ci_id)  # type: ignore[attr-defined]
            changes = snow.get_related_changes(ci_id)  # type: ignore[attr-defined]
            fixes = snow.search_similar_fixes(ci_id, limit=3)  # type: ignore[attr-defined]
        except IntegrationError as exc:
            connector_error = exc.message
    service = ci.get("business_service") if isinstance(ci, dict) else None
    actions = []
    if not payload.get("legal_hold"):
        actions.append("purge logs older than seven days")
    if payload.get("storage_extension_supported"):
        actions.append("extend the volume")
    current = forecast.get("current_utilization")
    rate = forecast.get("growth_per_hour")
    hours = forecast.get("hours_to_exhaustion")
    name = (ci or {}).get("name") if isinstance(ci, dict) else ""
    name = name or entity_id or "host"
    summary = "Disk forecast from stored samples"
    if current is not None and rate is not None and hours is not None:
        summary = f"{name} disk is {current:g}% and rising {rate:g} points per hour. Exhaustion in {hours:.1f} hours."
    return {
        **forecast,
        "points": points,
        "configuration_item": ci,
        "business_service": service,
        "related_changes": changes,
        "similar_fixes": fixes,
        "recommended_actions": actions,
        "connector_error": connector_error,
        "summary": summary,
    }


def select_runbook(payload: dict) -> dict | None:
    runbooks = payload.get("runbooks") or []
    kind = payload.get("kind")
    if kind == "capacity":
        if payload.get("legal_hold") or payload.get("archive_required"):
            return None
        match = next((item for item in runbooks if item["slug"] == "cleanup-approved-logs"), None)
        if match is None:
            return None
        return {"runbook": match, "parameters": {"min_age_days": max(7, int(payload.get("retention_days") or 7))}}
    hypotheses = payload.get("hypotheses") or []
    if not hypotheses:
        return None
    cause = hypotheses[0]["cause"].lower()
    if "memory" not in cause and "cpu" not in cause:
        return None
    match = next((item for item in runbooks if item["slug"] == "restart-claims-service"), None)
    if match is None:
        return None
    if payload.get("ci_class") and match.get("target_class") not in {"", payload["ci_class"]}:
        return None
    return {
        "runbook": match,
        "parameters": {
            "service_name": "claims-api",
            "node_count": "1",
            "environment": payload.get("environment") or "",
        },
    }


def validate_recovery(payload: dict, dyna: object) -> dict:
    entity_id = payload.get("entity_id") or ""
    kind = payload.get("kind")
    checks: list[dict] = []
    if kind == "capacity":
        new_util = utilization_after_cleanup(
            float(payload["current_utilization"]),
            float(payload["log_share_of_disk"]),
            int(payload["deleted_bytes"]),
            int(payload["log_bytes_before"]),
        )
        before = float(payload["current_utilization"])
        hours = linear_hours_to_capacity(new_util, float(payload["growth_per_hour"]))
        avoided = int(payload.get("incidents_during_window") or 0) == 0 and bool(payload.get("service_healthy"))
        checks.append({"name": "utilization_decreased", "passed": new_util < before - 1})
        checks.append({"name": "exhaustion_beyond_six_hours", "passed": hours is None or hours > 6})
        checks.append({"name": "service_healthy", "passed": bool(payload.get("service_healthy"))})
        checks.append({"name": "no_incident_opened", "passed": int(payload.get("incidents_during_window") or 0) == 0})
        passed = all(item["passed"] for item in checks)
        summary = (
            f"Corrected before an incident or service impact. Utilization {before:.0f}% to {new_util:.1f}%. No incident was opened."
            if passed
            else "Prevention checks failed"
        )
        return {
            "passed": passed,
            "checks": checks,
            "before_utilization": before,
            "utilization": new_util,
            "hours_to_exhaustion": hours,
            "incident_avoided": passed and avoided,
            "summary": summary,
        }
    cpu = dyna.query_metrics(entity_id, "cpu", after_action=True) if entity_id else {"points": []}  # type: ignore[attr-defined]
    memory = dyna.query_metrics(entity_id, "memory", after_action=True) if entity_id else {"points": []}  # type: ignore[attr-defined]
    cpu_points = _series_points(cpu)
    memory_points = _series_points(memory)
    pre_cpu = float(payload.get("pre_cpu") or 0)
    pre_memory = float(payload.get("pre_memory") or 0)
    checks.append({"name": "cpu_recovered", "passed": bool(cpu_points) and cpu_points[-1][1] < pre_cpu - 10})
    checks.append({"name": "memory_recovered", "passed": bool(memory_points) and memory_points[-1][1] < pre_memory - 10})
    checks.append({"name": "error_rate", "passed": float(payload.get("error_rate_after") or 1) < 0.01})
    checks.append({"name": "synthetic", "passed": bool(payload.get("synthetic_ok"))})
    checks.append({"name": "post_samples", "passed": len(cpu_points) >= 2 and len(memory_points) >= 2})
    stable = False
    if len(cpu_points) >= 2:
        stable = abs(cpu_points[-1][1] - cpu_points[-2][1]) <= 15
    checks.append({"name": "stabilizing", "passed": stable})
    passed = all(item["passed"] for item in checks)
    return {
        "passed": passed,
        "checks": checks,
        "summary": "Recovery checks passed" if passed else "Recovery checks failed",
        "series": {"cpu": cpu, "memory": memory},
    }


def forecast_disk(points: list[dict], *, now: datetime | None = None) -> dict:
    parsed = _series_points({"points": points})
    current = parsed[-1][1] if parsed else None
    rate = slope_per_hour(parsed)
    hours = linear_hours_to_capacity(current, rate) if current is not None and rate is not None else None
    stamp = now or datetime.now(timezone.utc)
    exhaustion = stamp + timedelta(hours=hours) if hours is not None else None
    return {
        "current_utilization": current,
        "growth_per_hour": rate,
        "hours_to_exhaustion": hours,
        "estimated_exhaustion_at": exhaustion.isoformat() if exhaustion else None,
        "method": "linear",
        "uncertainty": "Linear slope from the stored samples. No calibrated interval is available.",
    }
