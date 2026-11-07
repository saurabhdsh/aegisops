from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

from aegisops.core.config import Settings
from aegisops.core.logging import redact_text
from aegisops.core.security import hash_password, minimize_for_model, redact_mapping, verify_password


def test_live_mode_rejects_missing_credentials(monkeypatch) -> None:
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./unused.db")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", "")
    monkeypatch.setenv("SERVICENOW_INSTANCE_URL", "")
    monkeypatch.setenv("DYNATRACE_ENVIRONMENT_URL", "")
    monkeypatch.setenv("DYNATRACE_API_TOKEN", "")
    with pytest.raises(ValidationError, match="LIVE mode"):
        Settings(_env_file=None)


def test_production_rejects_sqlite(monkeypatch) -> None:
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./unused.db")
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(_env_file=None)


def test_secret_is_not_rendered_in_database_target(monkeypatch) -> None:
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EXECUTION_MODE", "SIMULATOR")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://aegis:super-secret@db.internal/aegis")
    settings = Settings(_env_file=None)
    assert "super-secret" not in settings.database_target
    assert "postgresql" in settings.database_target


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("wrong", None)
    assert "correct-horse-battery" not in encoded


def test_redaction() -> None:
    assert "[redacted]" in redact_text("api_key=abcd1234 token")
    cleaned = redact_mapping({"access_token": "secret", "title": "disk"})
    assert cleaned["access_token"] == "[redacted]"
    assert cleaned["title"] == "disk"


def test_model_minimization() -> None:
    payload = {"title": "claims", "description": "customer ssn 123", "priority": "2"}
    visible = minimize_for_model(payload, {"title", "priority"})
    assert visible == {"title": "claims", "priority": "2"}


def test_l4_default_requires_flag(monkeypatch) -> None:
    monkeypatch.setenv("APP_SECRET", "x" * 40)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EXECUTION_MODE", "SIMULATOR")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./unused.db")
    monkeypatch.setenv("AUTONOMY_DEFAULT_LEVEL", "L4")
    monkeypatch.setenv("AUTONOMY_L4_ENABLED", "false")
    with pytest.raises(ValidationError, match="L4"):
        Settings(_env_file=None)


class _Sample(BaseModel):
    at: datetime


def test_contract_rejects_naive_use_in_callers() -> None:
    model = _Sample(at=datetime.now(timezone.utc) + timedelta(minutes=1))
    assert model.at.tzinfo is not None
