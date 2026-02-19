"""placeholder - ingestion service does not own any database tables

The books schema is managed entirely by the books service.
This migration exists only to maintain a valid Alembic version chain.

Revision ID: 001
Revises:
Create Date: 2026-02-19
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS books")


def downgrade() -> None:
    pass
