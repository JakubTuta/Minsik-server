"""query statistics

pg_stat_statements is how a slow query gets noticed and then judged before and after a
change. The prod compose file now preloads the library; this makes its view available.

Revision ID: 031
Revises: 030
Create Date: 2026-10-10
"""

from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
