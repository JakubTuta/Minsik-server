"""performance indexes for recommendation/cleanup background jobs

Revision ID: 006
Revises: 005
Create Date: 2026-05-16
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_genres_genre_book "
        "ON books.book_genres(genre_id, book_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_series_id_partial "
        "ON books.books(series_id) WHERE series_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_authors_view_count_created "
        "ON books.authors(view_count, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_authors_author_book "
        "ON books.book_authors(author_id, book_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_lang_cover "
        "ON books.books(language) WHERE primary_cover_url IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_books_lang_cover")
    op.execute("DROP INDEX IF EXISTS books.idx_book_authors_author_book")
    op.execute("DROP INDEX IF EXISTS books.idx_authors_view_count_created")
    op.execute("DROP INDEX IF EXISTS books.idx_books_series_id_partial")
    op.execute("DROP INDEX IF EXISTS books.idx_book_genres_genre_book")
