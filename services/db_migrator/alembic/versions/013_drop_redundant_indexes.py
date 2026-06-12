"""drop redundant indexes and reset corrupted last_viewed_at values

Revision ID: 013
Revises: 012
Create Date: 2026-06-12
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS auth.idx_users_email")
    op.execute("DROP INDEX IF EXISTS auth.idx_users_username")
    op.execute("DROP INDEX IF EXISTS auth.idx_refresh_tokens_token_hash")
    op.execute("DROP INDEX IF EXISTS user_data.ix_comments_book_id_is_deleted")

    op.execute(
        "UPDATE books.books SET last_viewed_at = NULL "
        "WHERE last_viewed_at < '2000-01-01'"
    )
    op.execute(
        "UPDATE books.authors SET last_viewed_at = NULL "
        "WHERE last_viewed_at < '2000-01-01'"
    )
    op.execute(
        "UPDATE books.series SET last_viewed_at = NULL "
        "WHERE last_viewed_at < '2000-01-01'"
    )


def downgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON auth.users (email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON auth.users (username)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash "
        "ON auth.refresh_tokens (token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_comments_book_id_is_deleted "
        "ON user_data.comments (book_id, is_deleted)"
    )
