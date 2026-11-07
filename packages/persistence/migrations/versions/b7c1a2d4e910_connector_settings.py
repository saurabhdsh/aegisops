"""connector settings

Revision ID: b7c1a2d4e910
Revises: 804efed4e223
Create Date: 2026-11-07 07:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import aegisops.persistence.models  # noqa: F401

revision: str = "b7c1a2d4e910"
down_revision: Union[str, Sequence[str], None] = "804efed4e223"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connector_settings",
        sa.Column("id", sa.String(length=48), nullable=False),
        sa.Column("tenant_id", sa.String(length=48), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("auth_mode", sa.String(length=32), nullable=False),
        sa.Column("public_config", sa.JSON(), nullable=True),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", aegisops.persistence.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", aegisops.persistence.models.UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "kind", name="uq_connector_settings_kind"),
    )
    op.create_index("ix_connector_settings_tenant_id", "connector_settings", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_connector_settings_tenant_id", table_name="connector_settings")
    op.drop_table("connector_settings")
