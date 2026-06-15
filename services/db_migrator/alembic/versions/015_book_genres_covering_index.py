"""add covering index on book_genres(genre_id, book_id) for category queries

Revision ID: 015
Revises: 014
Create Date: 2026-06-14
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_genres_genre_id_book_id "
        "ON books.book_genres (genre_id, book_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_book_genres_genre_id_book_id")
