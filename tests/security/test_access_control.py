from datetime import datetime, timedelta, timezone

import pytest

from aegisops.core.identifiers import new_id
from aegisops.persistence.models import Incident
from aegisops.persistence.seed import add_user, create_tenant_with_admin
from tests.conftest import auth_header


def test_health_ready_and_openapi(api) -> None:
    health = api.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["execution_mode"] == "SIMULATOR"
    assert api.get("/ready").status_code == 200
    spec = api.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    assert "/api/v1/incidents" in paths
    assert "/api/v1/workflows/{workflow_id}/stream" in paths
    assert "super-secret" not in spec.text


def test_login_and_tenant_isolation(api) -> None:
    missing = api.get("/api/v1/incidents")
    assert missing.status_code == 401
    bad = api.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "default", "email": "sre@example.com", "password": "nope"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["message"] == "Invalid credentials"

    session = api.app.state.sessions()
    try:
        from sqlalchemy import select
        from aegisops.persistence.models import Tenant

        tenant = session.scalar(select(Tenant).where(Tenant.slug == "default"))
        other = create_tenant_with_admin(
            session,
            slug="other",
            name="Other",
            email="sre@example.com",
            password="other-password-value",
        )
        own = Incident(
            id=new_id("inc"),
            tenant_id=tenant.id,
            external_number="INC100",
            external_sys_id="own",
            title="Own incident",
            idempotency_key="own",
        )
        foreign = Incident(
            id=new_id("inc"),
            tenant_id=other.tenant_id,
            external_number="INC200",
            external_sys_id="foreign",
            title="Foreign incident",
            idempotency_key="foreign",
        )
        session.add_all([own, foreign])
        add_user(
            session,
            tenant_id=tenant.id,
            email="observer@example.com",
            password="observer-password-value",
            role_name="observer",
        )
        session.commit()
        foreign_id = foreign.id
    finally:
        session.close()

    headers = auth_header(api)
    listing = api.get("/api/v1/incidents", headers=headers)
    assert listing.status_code == 200
    titles = [item["title"] for item in listing.json()["items"]]
    assert titles == ["Own incident"]
    hidden = api.get(f"/api/v1/incidents/{foreign_id}", headers=headers)
    assert hidden.status_code == 404

    observer = auth_header(api, email="observer@example.com", password="observer-password-value")
    audit = api.get("/api/v1/audit", headers=observer)
    assert audit.status_code == 403
    stop = api.post("/api/v1/operations/emergency-stop", headers=observer, json={"reason": "no"})
    assert stop.status_code == 403


def test_webhook_requires_configured_secret(api) -> None:
    denied = api.post("/api/v1/webhooks/dynatrace", json={"problem": "cpu"})
    assert denied.status_code == 401
    forged = api.post(
        "/api/v1/webhooks/dynatrace",
        json={"problem": "cpu"},
        headers={"X-Aegis-Webhook-Token": "guess"},
    )
    assert forged.status_code == 401


def test_l4_cannot_be_enabled_when_flag_is_off(api) -> None:
    headers = auth_header(api)
    response = api.post("/api/v1/operations/autonomy", headers=headers, json={"level": "L4"})
    assert response.status_code == 403
    controls = api.get("/api/v1/operations/controls", headers=headers)
    assert controls.json()["autonomy_level"] == "L3"


def test_cookie_post_requires_csrf(api) -> None:
    login = api.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "default", "email": "sre@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    api.cookies.set("aegisops_session", login.json()["access_token"])
    blocked = api.post("/api/v1/operations/emergency-stop", json={"reason": "csrf"})
    assert blocked.status_code == 403
    allowed = api.post(
        "/api/v1/operations/emergency-stop",
        json={"reason": "csrf-ok"},
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert allowed.status_code == 200


def test_agents_execute_only_inside_the_engine() -> None:
    import asyncio
    from datetime import datetime, timezone

    from aegisops.agents.triage import TriageAgent, TriageInput
    from aegisops.contracts.agent import AgentContext
    from aegisops.core.exceptions import AegisError

    context = AgentContext(
        workflow_id="wf",
        correlation_id="cor",
        tenant_id="ten",
        actor_id="usr",
        execution_mode="SIMULATOR",
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    with pytest.raises(AegisError) as caught:
        asyncio.run(TriageAgent().execute(context, TriageInput()))
    assert caught.value.code == "agent_context"
