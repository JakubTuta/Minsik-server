"""index for this-year finished books query

Revision ID: 010
Revises: 009
Create Date: 2026-05-28
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_user_status_updated "
        "ON user_data.bookshelves (user_id, status, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS user_data.idx_bookshelves_user_status_updated"
    )
