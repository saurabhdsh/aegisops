"""Environment configuration. Secrets stay in the environment and are never logged."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url

ExecutionMode = Literal["LIVE", "SANDBOX", "SIMULATOR"]
AppEnv = Literal["development", "test", "production"]
AuthMode = Literal["oauth", "token", "basic"]
OpenAiProvider = Literal["openai", "azure"]
AutonomyLevel = Literal["L3", "L4"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AegisOps"
    app_env: AppEnv = "development"
    execution_mode: ExecutionMode = "SANDBOX"
    app_secret: str = ""
    database_url: str = "sqlite:///./aegisops.db"

    bootstrap_tenant_slug: str = "default"
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    openai_provider: OpenAiProvider = "openai"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str = ""
    openai_api_version: str = "2024-10-21"

    servicenow_instance_url: str = ""
    servicenow_auth_mode: AuthMode = "oauth"
    servicenow_client_id: str = ""
    servicenow_client_secret: str = ""
    servicenow_access_token: str = ""
    servicenow_username: str = ""
    servicenow_password: str = ""
    servicenow_webhook_secret: str = ""
    servicenow_table_incident: str = "incident"
    servicenow_table_ci: str = "cmdb_ci"
    servicenow_table_change: str = "change_request"
    servicenow_table_service: str = "cmdb_ci_service"

    dynatrace_environment_url: str = ""
    dynatrace_api_token: str = ""
    dynatrace_webhook_secret: str = ""

    ansible_inventory_path: str = ""
    ansible_runbook_path: str = "runbooks"
    ansible_automation_endpoint: str = ""
    ansible_use_cli: bool = False
    incident_auto_resolve: bool = False
    change_auto_close: bool = False

    autonomy_default_level: AutonomyLevel = "L3"
    autonomy_l4_enabled: bool = False

    audit_enabled: bool = True
    otel_enabled: bool = True

    cors_origins: str = "http://localhost:5173"
    session_ttl_seconds: int = 43_200
    rate_limit_per_minute: int = 120
    sse_poll_seconds: float = 1.0
    sse_max_polls: int = 0
    log_level: str = "INFO"

    http_timeout_seconds: float = Field(default=20.0)

    @field_validator("bootstrap_admin_email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("servicenow_instance_url", "dynatrace_environment_url", "openai_base_url")
    @classmethod
    def _strip_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if len(self.app_secret) < 32:
            raise ValueError("APP_SECRET must be at least 32 characters")
        if self.app_env == "production" and self.database_url.startswith("sqlite"):
            raise ValueError("APP_ENV=production requires a PostgreSQL DATABASE_URL")
        if self.autonomy_default_level == "L4" and not self.autonomy_l4_enabled:
            raise ValueError("AUTONOMY_DEFAULT_LEVEL=L4 requires AUTONOMY_L4_ENABLED=true")
        if self.execution_mode == "LIVE":
            missing = self._missing_live_credentials()
            if missing:
                raise ValueError(
                    "LIVE mode is missing required configuration: " + ", ".join(missing)
                )
        if bool(self.bootstrap_admin_email) ^ bool(self.bootstrap_admin_password):
            raise ValueError(
                "BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD must both be set or both be empty"
            )
        return self

    def _missing_live_credentials(self) -> list[str]:
        missing: list[str] = []
        if not self.servicenow_instance_url:
            missing.append("SERVICENOW_INSTANCE_URL")
        if self.servicenow_auth_mode == "oauth":
            has_client = bool(self.servicenow_client_id and self.servicenow_client_secret)
            if not has_client and not self.servicenow_access_token:
                missing.append("SERVICENOW_CLIENT_ID and SERVICENOW_CLIENT_SECRET, or SERVICENOW_ACCESS_TOKEN")
        elif self.servicenow_auth_mode == "token":
            if not self.servicenow_access_token:
                missing.append("SERVICENOW_ACCESS_TOKEN")
        elif self.servicenow_auth_mode == "basic":
            if not (self.servicenow_username and self.servicenow_password):
                missing.append("SERVICENOW_USERNAME and SERVICENOW_PASSWORD")
        if not self.dynatrace_environment_url:
            missing.append("DYNATRACE_ENVIRONMENT_URL")
        if not self.dynatrace_api_token:
            missing.append("DYNATRACE_API_TOKEN")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.openai_model:
            missing.append("OPENAI_MODEL" if self.openai_provider == "openai" else "AZURE_OPENAI_DEPLOYMENT")
        if self.openai_provider == "azure" and not self.openai_base_url:
            missing.append("AZURE_OPENAI_ENDPOINT")
        return missing

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def database_target(self) -> str:
        """Dialect and host only. Passwords are hidden."""
        rendered = make_url(self.database_url).render_as_string(hide_password=True)
        parts = urlsplit(rendered)
        if parts.password:
            netloc = parts.netloc.replace(f":{parts.password}", ":****")
            return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
        return rendered


@lru_cache
def get_settings() -> Settings:
    return Settings()
