"""Rank hypotheses from measured signals.

A cause is emitted only when its signal is present. Notes are not signals.
Confidence is a score derived from the slope, not a calibrated probability.
"""

from __future__ import annotations

from datetime import datetime


def rank_hypotheses(signals: dict) -> list[dict]:
    found: list[dict] = []
    memory_slope = signals.get("memory_slope_per_hour")
    cpu_slope = signals.get("cpu_slope_per_hour")
    deployment_lag = signals.get("deployment_lag_hours")
    error_rate = signals.get("error_rate")
    evidence_ids = list(signals.get("evidence_ids") or [])
    limitations = []
    if not signals.get("heap_profile"):
        limitations.append("Heap profiling evidence unavailable")

    deployment_near = deployment_lag is not None and deployment_lag >= 0 and deployment_lag <= 6
    if isinstance(memory_slope, (int, float)) and memory_slope >= 5 and deployment_near:
        found.append(
            {
                "cause": "Memory utilization is rising and a deployment falls inside the six-hour correlation window",
                "confidence": round(min(0.9, 0.5 + min(float(memory_slope), 30) / 100), 2),
                "evidence_ids": evidence_ids,
                "limitations": limitations,
                "requires_human_review": True,
            }
        )
    elif isinstance(memory_slope, (int, float)) and memory_slope >= 8:
        found.append(
            {
                "cause": "Memory utilization is rising across the observation window",
                "confidence": round(min(0.75, 0.4 + min(float(memory_slope), 30) / 100), 2),
                "evidence_ids": evidence_ids,
                "limitations": limitations + ["No deployment falls inside the correlation window"],
                "requires_human_review": True,
            }
        )
    if isinstance(cpu_slope, (int, float)) and cpu_slope >= 5:
        found.append(
            {
                "cause": "CPU utilization is rising across the observation window",
                "confidence": round(min(0.8, 0.4 + min(float(cpu_slope), 30) / 120), 2),
                "evidence_ids": evidence_ids,
                "limitations": [] if signals.get("cpu_series") else ["CPU series unavailable"],
                "requires_human_review": True,
            }
        )
    if isinstance(error_rate, (int, float)) and error_rate >= 0.02:
        found.append(
            {
                "cause": "Application error rate is elevated against the service health sample",
                "confidence": round(min(0.7, 0.35 + float(error_rate)), 2),
                "evidence_ids": evidence_ids,
                "limitations": [],
                "requires_human_review": True,
            }
        )
    found.sort(key=lambda item: item["confidence"], reverse=True)
    return found[:3]


def deployment_lag_hours(deployed_at: datetime | None, observed_at: datetime | None) -> float | None:
    if deployed_at is None or observed_at is None:
        return None
    return (observed_at - deployed_at).total_seconds() / 3600
