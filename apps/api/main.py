"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aegisops.core.config import Settings, get_settings
from aegisops.core.exceptions import AegisError
from aegisops.core.logging import configure_logging
from aegisops.observability.metrics import metrics
from aegisops.persistence.seed import create_tenant_with_admin, user_count
from aegisops.persistence.session import create_db_engine, create_session_factory
from apps.api.middleware import CorrelationMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from apps.api.routers import agents, approvals, audit, auth, capacity, health, incidents, integrations, operations, runbooks, settings as settings_router, simulator, telemetry, topology, webhooks, workflows

log = logging.getLogger("aegisops.api")


def _error_body(request: Request, code: str, message: str, details: dict | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": getattr(request.state, "correlation_id", None),
            "details": details or {},
        }
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_db_engine(settings)
        sessions = create_session_factory(engine)
        app.state.engine = engine
        app.state.sessions = sessions
        _bootstrap(settings, sessions)
        log.info(
            "api started app=%s env=%s mode=%s database=%s",
            settings.app_name,
            settings.app_env,
            settings.execution_mode,
            settings.database_target,
        )
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    # First added runs closest to the app. CORS stays outermost so preflight is answered first.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, limit=settings.rate_limit_per_minute)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Correlation-ID", "Last-Event-ID"],
    )

    for module in (
        health,
        auth,
        incidents,
        workflows,
        agents,
        approvals,
        capacity,
        topology,
        runbooks,
        integrations,
        telemetry,
        audit,
        operations,
        webhooks,
        simulator,
        settings_router,
    ):
        app.include_router(module.router)

    @app.exception_handler(AegisError)
    async def handle_aegis(request: Request, exc: AegisError) -> JSONResponse:
        metrics.inc(f"error.{exc.code}")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body(request, "validation_error", "Request validation failed", {"errors": exc.errors()}),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error correlation=%s", getattr(request.state, "correlation_id", ""))
        metrics.inc("error.internal")
        return JSONResponse(
            status_code=500,
            content=_error_body(request, "internal_error", "Internal error"),
        )

    return app


def _bootstrap(settings: Settings, sessions) -> None:  # type: ignore[no-untyped-def]
    if not settings.bootstrap_admin_email:
        return
    session = sessions()
    try:
        if user_count(session) > 0:
            return
        create_tenant_with_admin(
            session,
            slug=settings.bootstrap_tenant_slug,
            name=settings.bootstrap_tenant_slug,
            email=settings.bootstrap_admin_email,
            password=settings.bootstrap_admin_password,
            autonomy_level=settings.autonomy_default_level,
        )
        session.commit()
        log.info("bootstrapped tenant slug=%s", settings.bootstrap_tenant_slug)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


app = create_app()
