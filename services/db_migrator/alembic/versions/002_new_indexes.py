"""new indexes for bookshelf and series queries

Revision ID: 002
Revises: 001
Create Date: 2026-06-01
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _drop_redundant_indexes()
    _create_new_indexes()


def downgrade() -> None:
    _drop_new_indexes()
    _restore_redundant_indexes()


def _drop_redundant_indexes() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_books_series")
    op.execute("DROP INDEX IF EXISTS books.idx_book_authors_book_id")
    op.execute("DROP INDEX IF EXISTS books.idx_book_genres_book_id")
    op.execute("DROP INDEX IF EXISTS user_data.idx_bookshelves_book_id")


def _create_new_indexes() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_series_lang "
        "ON books.books(series_id, language, series_position)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_book_status "
        "ON user_data.bookshelves(book_id, status)"
    )


def _drop_new_indexes() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_books_series_lang")
    op.execute("DROP INDEX IF EXISTS user_data.idx_bookshelves_book_status")


def _restore_redundant_indexes() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_series ON books.books(series_id, series_position)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_authors_book_id ON books.book_authors(book_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_genres_book_id ON books.book_genres(book_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_book_id ON user_data.bookshelves(book_id)"
    )
