"""Stored Dynatrace samples can be ranked without opening a workflow."""

from __future__ import annotations

from tests.conftest import auth_header


def test_each_demo_incident_has_its_own_samples(api) -> None:
    headers = auth_header(api)
    enabled = api.put("/api/v1/settings/connections/demo", headers=headers, json={"enabled": True})
    assert enabled.status_code == 200, enabled.text

    listed = api.get("/api/v1/incidents?limit=200", headers=headers)
    assert listed.status_code == 200, listed.text
    by_number = {item["number"]: item for item in listed.json()["items"]}
    rising = by_number["INC10001"]
    quiet = by_number["INC10002"]

    rising_body = api.get(f"/api/v1/incidents/{rising['id']}/analysis", headers=headers)
    quiet_body = api.get(f"/api/v1/incidents/{quiet['id']}/analysis", headers=headers)
    assert rising_body.status_code == 200, rising_body.text
    assert quiet_body.status_code == 200, quiet_body.text
    rising_json = rising_body.json()
    quiet_json = quiet_body.json()

    assert rising_json["entity_id"] == "DEMO-HOST-01"
    assert len(rising_json["series"]["cpu"]) == 4
    assert rising_json["series"]["cpu"][-1]["value"] == 46
    assert rising_json["signals"]["cpu_slope_per_hour"] == 6
    assert rising_json["hypotheses"]
    assert rising_json["hypotheses"][0]["cause"].startswith("CPU utilization")
    assert rising_json["workflow_id"] is None

    assert quiet_json["entity_id"] == "DEMO-HOST-02"
    assert quiet_json["signals"]["cpu_slope_per_hour"] == 2
    assert quiet_json["hypotheses"] == []
    assert quiet_json["series"]["cpu"][0]["timestamp"] != rising_json["series"]["cpu"][0]["timestamp"]


def test_demo_hosts_stay_on_stored_samples_when_dynatrace_is_saved(api) -> None:
    headers = auth_header(api)
    enabled = api.put("/api/v1/settings/connections/demo", headers=headers, json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    saved = api.put(
        "/api/v1/settings/connections/dynatrace",
        headers=headers,
        json={"environment_url": "http://127.0.0.1:9", "api_token": "dt-token-hidden"},
    )
    assert saved.status_code == 200, saved.text
    listed = api.get("/api/v1/incidents?limit=200", headers=headers)
    incident = next(item for item in listed.json()["items"] if item["number"] == "INC10001")
    body = api.get(f"/api/v1/incidents/{incident['id']}/analysis", headers=headers)
    assert body.status_code == 200, body.text
    assert body.json()["source"] == "stored-samples"
    assert body.json()["series"]["cpu"][-1]["value"] == 46
    assert "dt-token-hidden" not in body.text
