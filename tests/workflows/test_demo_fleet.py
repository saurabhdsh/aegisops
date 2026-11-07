"""The settings demo switch loads a ServiceNow and Dynatrace fleet and can hide it."""

from __future__ import annotations

from sqlalchemy import func, select

from aegisops.persistence.models import Event, Incident, MetricObservation
from aegisops.runtime.demo import fleet_size
from tests.conftest import auth_header


def test_demo_switch_loads_fifty_incidents_and_hides_them(api) -> None:
    assert fleet_size() >= 50
    headers = auth_header(api)
    enabled = api.put("/api/v1/settings/connections/demo", headers=headers, json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["incident_count"] >= 50

    listed = api.get("/api/v1/incidents?limit=100", headers=headers)
    numbers = {item["number"] for item in listed.json()["items"]}
    assert len([number for number in numbers if number.startswith("INC1")]) >= 50

    session = api.app.state.sessions()
    try:
        problems = session.scalar(
            select(func.count()).select_from(Event).where(Event.source == "dynatrace", Event.event_type == "problem")
        )
        samples = session.scalar(
            select(func.count()).select_from(MetricObservation).where(MetricObservation.entity_id.like("DEMO-%"))
        )
        assert problems >= 50
        assert samples >= 50
    finally:
        session.close()

    hidden = api.put("/api/v1/settings/connections/demo", headers=headers, json={"enabled": False})
    assert hidden.status_code == 200
    after = api.get("/api/v1/incidents?limit=100", headers=headers)
    assert all(item["number"] != "INC10001" for item in after.json()["items"])
    session = api.app.state.sessions()
    try:
        stored = session.scalar(select(func.count()).select_from(Incident).where(Incident.source == "demo"))
        assert stored >= 50
    finally:
        session.close()
