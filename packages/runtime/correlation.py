"""Group events that share an entity, a symptom, and a time window."""

from __future__ import annotations

from datetime import datetime, timedelta


def correlate(events: list[dict], *, window_minutes: int = 30) -> list[dict]:
    """Return groups. The input list is not padded and not invented."""
    remaining = sorted(events, key=lambda item: item["received_at"])
    groups: list[dict] = []
    while remaining:
        seed = remaining.pop(0)
        window_end = seed["received_at"] + timedelta(minutes=window_minutes)
        members = [seed]
        rest = []
        for event in remaining:
            same_entity = event.get("entity_ref") == seed.get("entity_ref")
            same_symptom = event.get("symptom") == seed.get("symptom")
            inside = event["received_at"] <= window_end
            if same_entity and same_symptom and inside:
                members.append(event)
            else:
                rest.append(event)
        remaining = rest
        groups.append(
            {
                "entity_ref": seed.get("entity_ref", ""),
                "symptom": seed.get("symptom", ""),
                "alert_count": len(members),
                "event_ids": [item["id"] for item in members],
                "opened_at": members[0]["received_at"],
                "summary": f"{len(members)} {seed.get('symptom') or 'alert'} events on {seed.get('entity_ref') or 'unknown'}",
            }
        )
    return groups
