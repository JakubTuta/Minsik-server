"""indexes for book comment lookups

Revision ID: 007
Revises: 006
Create Date: 2026-05-16
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_slug "
        "ON books.books(slug)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_comments_book_created "
        "ON user_data.comments(book_id, created_at DESC) "
        "WHERE is_deleted = FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ratings_book_user "
        "ON user_data.ratings(book_id, user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS user_data.idx_ratings_book_user")
    op.execute("DROP INDEX IF EXISTS user_data.idx_comments_book_created")
    op.execute("DROP INDEX IF EXISTS books.idx_books_slug")
