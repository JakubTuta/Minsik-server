"""add enrichment_attempted_at tracking column to books, authors, series

Revision ID: 018
Revises: 017
Create Date: 2026-07-12
"""

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None

_TABLES = ["books", "authors", "series"]


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE books.{table} ADD COLUMN IF NOT EXISTS "
            f"enrichment_attempted_at TIMESTAMPTZ"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE books.{table} DROP COLUMN IF EXISTS enrichment_attempted_at")
