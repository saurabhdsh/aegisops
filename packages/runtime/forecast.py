"""Deterministic capacity math. Results follow the measurements passed in."""

from __future__ import annotations

from datetime import datetime, timedelta


def slope_per_hour(points: list[tuple[datetime, float]]) -> float | None:
    if len(points) < 2:
        return None
    ordered = sorted(points, key=lambda item: item[0])
    elapsed = (ordered[-1][0] - ordered[0][0]).total_seconds() / 3600
    if elapsed <= 0:
        return None
    return (ordered[-1][1] - ordered[0][1]) / elapsed


def linear_hours_to_capacity(current: float, rate_per_hour: float, capacity: float = 100.0) -> float | None:
    if rate_per_hour <= 0:
        return None
    remaining = capacity - current
    if remaining <= 0:
        return 0.0
    return remaining / rate_per_hour


def exhaustion_at(now: datetime, hours: float | None) -> datetime | None:
    if hours is None:
        return None
    return now + timedelta(hours=hours)


def utilization_after_cleanup(
    current: float,
    log_share_of_disk: float,
    deleted_bytes: int,
    log_bytes_before: int,
) -> float:
    if log_bytes_before <= 0 or deleted_bytes <= 0 or log_share_of_disk <= 0:
        return current
    ratio = min(1.0, deleted_bytes / log_bytes_before)
    recovered = current * log_share_of_disk * ratio
    return max(0.0, current - recovered)
