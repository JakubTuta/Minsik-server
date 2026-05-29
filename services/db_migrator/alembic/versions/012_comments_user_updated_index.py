"""index for comment list sort by updated_at per user

Revision ID: 012
Revises: 011
Create Date: 2026-05-29
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_comments_user_updated "
        "ON user_data.comments (user_id, updated_at DESC) WHERE is_deleted = FALSE"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS user_data.idx_comments_user_updated"
    )
