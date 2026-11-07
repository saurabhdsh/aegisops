"""Retry classification.

An execution that already has an external identifier must be reconciled.
It must not be launched again because a worker lease expired.
"""

from __future__ import annotations

import asyncio


def classify_retry(exc: BaseException, *, external_execution_id: str | None) -> str:
    if external_execution_id:
        return "reconcile"
    if isinstance(exc, (TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return "transient"
    return "permanent"


def retry_decision(*, status: str, external_execution_id: str | None) -> str:
    """Decide what a recovered worker may do with an automation row."""
    if external_execution_id:
        return "reconcile"
    if status in {"pending", "prechecking"}:
        return "retry_precheck"
    if status in {"running", "partial"}:
        return "blocked"
    return "blocked"
