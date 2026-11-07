"""demo enabled flag

Revision ID: c3d8e1f0a21b
Revises: b7c1a2d4e910
Create Date: 2026-11-07 07:55:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d8e1f0a21b"
down_revision: Union[str, Sequence[str], None] = "b7c1a2d4e910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "operational_controls",
        sa.Column("demo_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("operational_controls", "demo_enabled")
