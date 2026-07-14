"""drop stray unique-on-slug constraint left over from initial schema

The series table was created in 001 with an inline ``slug ... UNIQUE`` column
constraint (``series_slug_key``), enforcing uniqueness on slug alone. Migration
017 moved series to per-language uniqueness via ``idx_series_slug_language`` but
only dropped the separate ``idx_series_slug`` index, leaving ``series_slug_key``
in place. That stray constraint makes per-language series impossible: inserting
a second language for an existing slug violates it, crashing series
consolidation and any backfill.

Revision ID: 019
Revises: 018
Create Date: 2026-07-14
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE books.series DROP CONSTRAINT IF EXISTS series_slug_key")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE books.series ADD CONSTRAINT series_slug_key UNIQUE (slug)"
    )
