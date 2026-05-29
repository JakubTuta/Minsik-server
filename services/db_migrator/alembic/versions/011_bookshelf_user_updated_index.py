"""index for bookshelf sort by updated_at without status filter

Revision ID: 011
Revises: 010
Create Date: 2026-05-29
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_user_updated_date "
        "ON user_data.bookshelves (user_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS user_data.idx_bookshelves_user_updated_date"
    )
