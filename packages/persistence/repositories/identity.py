from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from aegisops.core.exceptions import NotFoundError
from aegisops.core.identifiers import new_id
from aegisops.core.security import hash_password, verify_password
from aegisops.persistence.models import AuthSession, Role, User, UserRole


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user_by_email(self, tenant_id: str, email: str) -> User | None:
        return self.session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.email == email.strip().lower())
        )

    def get_user(self, tenant_id: str, user_id: str) -> User:
        user = self.session.scalar(select(User).where(User.tenant_id == tenant_id, User.id == user_id))
        if user is None:
            raise NotFoundError("User not found")
        return user

    def roles_for(self, user_id: str) -> set[str]:
        rows = self.session.execute(
            select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        ).all()
        return {row[0] for row in rows}

    def authenticate(self, tenant_id: str, email: str, password: str) -> User | None:
        user = self.get_user_by_email(tenant_id, email)
        if user is None or not user.is_active:
            verify_password(password, None)
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def add_session(
        self,
        *,
        tenant_id: str,
        user_id: str,
        token_hash: str,
        csrf_hash: str,
        expires_at: datetime,
        user_agent: str,
        ip_address: str,
    ) -> AuthSession:
        record = AuthSession(
            id=new_id("ses"),
            tenant_id=tenant_id,
            user_id=user_id,
            token_hash=token_hash,
            csrf_hash=csrf_hash,
            expires_at=expires_at,
            user_agent=user_agent[:300],
            ip_address=ip_address[:64],
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_session_by_hash(self, token_hash: str) -> AuthSession | None:
        return self.session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))

    def revoke(self, record: AuthSession) -> None:
        record.revoked_at = datetime.now(timezone.utc)

    def set_password(self, user: User, password: str) -> None:
        user.password_hash = hash_password(password)
