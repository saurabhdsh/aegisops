import os

os.environ.setdefault("APP_SECRET", "test-secret-key-must-be-at-least-32-characters")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("EXECUTION_MODE", "SIMULATOR")
os.environ.setdefault("DATABASE_URL", "sqlite:///./.pytest-aegisops.db")
os.environ.setdefault("SSE_MAX_POLLS", "1")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")
os.environ.setdefault("AUTONOMY_L4_ENABLED", "false")
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "")

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from aegisops.core.config import get_settings
from aegisops.persistence.seed import create_tenant_with_admin
from aegisops.persistence.session import create_db_engine, create_session_factory


@pytest.fixture
def api(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database = tmp_path / "aegisops.db"
    url = "sqlite:///" + database.as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_SECRET", "test-secret-key-must-be-at-least-32-characters")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EXECUTION_MODE", "SIMULATOR")
    monkeypatch.setenv("SSE_MAX_POLLS", "1")
    monkeypatch.setenv("SSE_POLL_SECONDS", "0.01")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.setenv("AUTONOMY_L4_ENABLED", "false")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setenv("DYNATRACE_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("SERVICENOW_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", "")
    monkeypatch.setenv("OPENAI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    get_settings.cache_clear()

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    engine = create_db_engine(get_settings())
    sessions = create_session_factory(engine)
    session = sessions()
    try:
        create_tenant_with_admin(
            session,
            slug="default",
            name="Default",
            email="sre@example.com",
            password="correct-horse-battery",
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    from apps.api.main import create_app

    application = create_app()
    with TestClient(application) as client:
        client.password = "correct-horse-battery"  # type: ignore[attr-defined]
        client.email = "sre@example.com"  # type: ignore[attr-defined]
        client.tenant = "default"  # type: ignore[attr-defined]
        yield client
    get_settings.cache_clear()


def auth_header(client: TestClient, email: str | None = None, password: str | None = None, tenant: str = "default") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": tenant,
            "email": email or client.email,  # type: ignore[attr-defined]
            "password": password or client.password,  # type: ignore[attr-defined]
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
