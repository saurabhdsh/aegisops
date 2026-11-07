"""Database-backed worker leases. Acquisition uses a savepoint so a lost race is not fatal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aegisops.core.identifiers import new_id
from aegisops.persistence.models import WorkerLease


class LeaseManager:
    def __init__(self, session: Session) -> None:
        self.session = session

    def acquire(
        self,
        *,
        worker_id: str,
        resource_type: str,
        resource_id: str,
        ttl_seconds: int,
        tenant_id: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        self.session.execute(
            delete(WorkerLease).where(
                WorkerLease.resource_type == resource_type,
                WorkerLease.resource_id == resource_id,
                WorkerLease.expires_at < now,
            )
        )
        self.session.flush()
        existing = self.session.scalar(
            select(WorkerLease).where(
                WorkerLease.resource_type == resource_type,
                WorkerLease.resource_id == resource_id,
            )
        )
        if existing is not None:
            if existing.worker_id != worker_id:
                return False
            existing.expires_at = now + timedelta(seconds=ttl_seconds)
            existing.heartbeat_at = now
            self.session.flush()
            return True
        try:
            with self.session.begin_nested():
                self.session.add(
                    WorkerLease(
                        id=new_id("lse"),
                        tenant_id=tenant_id,
                        worker_id=worker_id,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        acquired_at=now,
                        expires_at=now + timedelta(seconds=ttl_seconds),
                        heartbeat_at=now,
                    )
                )
                self.session.flush()
        except IntegrityError:
            return False
        return True

    def heartbeat(self, *, worker_id: str, resource_type: str, resource_id: str, ttl_seconds: int) -> bool:
        now = datetime.now(timezone.utc)
        lease = self.session.scalar(
            select(WorkerLease).where(
                WorkerLease.resource_type == resource_type,
                WorkerLease.resource_id == resource_id,
                WorkerLease.worker_id == worker_id,
                WorkerLease.expires_at >= now,
            )
        )
        if lease is None:
            return False
        lease.heartbeat_at = now
        lease.expires_at = now + timedelta(seconds=ttl_seconds)
        self.session.flush()
        return True

    def release(self, *, worker_id: str, resource_type: str, resource_id: str) -> None:
        self.session.execute(
            delete(WorkerLease).where(
                WorkerLease.worker_id == worker_id,
                WorkerLease.resource_type == resource_type,
                WorkerLease.resource_id == resource_id,
            )
        )
        self.session.flush()
