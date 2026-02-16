"""add created_at and updated_at to user_stats

Revision ID: 006
Revises: 005
Create Date: 2026-02-16
"""
import sqlalchemy as sa
from alembic import op

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_stats",
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        schema="user_data"
    )
    op.add_column(
        "user_stats",
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        schema="user_data"
    )


def downgrade() -> None:
    op.drop_column("user_stats", "updated_at", schema="user_data")
    op.drop_column("user_stats", "created_at", schema="user_data")
