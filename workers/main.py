"""Worker process. Phase 1 keeps a database lease and does not execute agents."""

from __future__ import annotations

import logging
import signal
import threading

from sqlalchemy import inspect, text

from aegisops.core.config import get_settings
from aegisops.core.identifiers import new_id
from aegisops.core.logging import configure_logging
from aegisops.persistence.session import create_db_engine, create_session_factory
from aegisops.runtime.leases import LeaseManager

log = logging.getLogger("aegisops.worker")


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info(
        "worker starting app=%s env=%s mode=%s database=%s",
        settings.app_name,
        settings.app_env,
        settings.execution_mode,
        settings.database_target,
    )
    engine = create_db_engine(settings)
    if not inspect(engine).has_table("worker_leases"):
        log.error("database schema is missing. Run: alembic upgrade head")
        return 1
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    sessions = create_session_factory(engine)
    worker_id = new_id("wrk")
    stop = threading.Event()

    def _stop(signum: int, _frame: object) -> None:
        log.info("worker received signal=%s", signum)
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        while not stop.is_set():
            session = sessions()
            try:
                held = LeaseManager(session).acquire(
                    worker_id=worker_id,
                    resource_type="worker",
                    resource_id=worker_id,
                    ttl_seconds=30,
                )
                session.commit()
            except Exception:
                session.rollback()
                log.exception("worker lease refresh failed")
                return 1
            finally:
                session.close()
            if not held:
                log.error("worker lease is held by another process")
                return 1
            session = sessions()
            try:
                from aegisops.runtime.engine import tick

                tick(session, settings, worker_id)
                session.commit()
            except Exception:
                session.rollback()
                log.exception("workflow tick failed")
            finally:
                session.close()
            stop.wait(5)
    finally:
        session = sessions()
        try:
            LeaseManager(session).release(
                worker_id=worker_id, resource_type="worker", resource_id=worker_id
            )
            session.commit()
        finally:
            session.close()
            engine.dispose()
    log.info("worker stopped id=%s", worker_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
