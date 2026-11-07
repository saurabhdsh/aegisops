"""Tenant bootstrap. Passwords are hashed before insert. No default password exists in code."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aegisops.core.identifiers import new_id
from aegisops.core.security import DEFAULT_ROLES, hash_password
from aegisops.persistence.models import OperationalControl, Role, Tenant, User, UserRole


def create_tenant_with_admin(
    session: Session,
    *,
    slug: str,
    name: str,
    email: str,
    password: str,
    display_name: str = "Administrator",
    autonomy_level: str = "L3",
) -> User:
    tenant = Tenant(id=new_id("ten"), name=name, slug=slug)
    session.add(tenant)
    session.flush()
    roles = {
        role_name: Role(
            id=new_id("rol"),
            tenant_id=tenant.id,
            name=role_name,
            description=f"{role_name} role",
        )
        for role_name in DEFAULT_ROLES
    }
    session.add_all(roles.values())
    user = User(
        id=new_id("usr"),
        tenant_id=tenant.id,
        email=email.strip().lower(),
        display_name=display_name,
        password_hash=hash_password(password),
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(
        UserRole(id=new_id("url"), tenant_id=tenant.id, user_id=user.id, role_id=roles["admin"].id)
    )
    session.add(
        OperationalControl(
            id=new_id("ctl"),
            tenant_id=tenant.id,
            emergency_stop=False,
            autonomy_level=autonomy_level,
        )
    )
    session.flush()
    return user


def add_user(
    session: Session,
    *,
    tenant_id: str,
    email: str,
    password: str,
    role_name: str,
    display_name: str = "User",
) -> User:
    role = session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name))
    if role is None:
        raise ValueError(f"Role {role_name} is not configured for this tenant")
    user = User(
        id=new_id("usr"),
        tenant_id=tenant_id,
        email=email.strip().lower(),
        display_name=display_name,
        password_hash=hash_password(password),
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(id=new_id("url"), tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    session.flush()
    return user


def user_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(User)) or 0)
