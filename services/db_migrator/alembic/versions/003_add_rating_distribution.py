"""add rating_distribution column to books.books

Revision ID: 003
Revises: 002
Create Date: 2026-03-11
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _add_column()
    _backfill_existing_books()


def downgrade() -> None:
    _drop_column()


def _add_column() -> None:
    op.execute(
        "ALTER TABLE books.books "
        "ADD COLUMN IF NOT EXISTS rating_distribution JSONB NOT NULL DEFAULT '{}'"
    )


def _backfill_existing_books() -> None:
    op.execute(
        """
        WITH per_book AS (
            SELECT
                book_id,
                jsonb_object_agg(overall_rating::text, cnt) AS distribution
            FROM (
                SELECT book_id, overall_rating, COUNT(*) AS cnt
                FROM user_data.ratings
                GROUP BY book_id, overall_rating
            ) t
            GROUP BY book_id
        )
        UPDATE books.books
        SET rating_distribution = per_book.distribution
        FROM per_book
        WHERE books.books.book_id = per_book.book_id
        """
    )


def _drop_column() -> None:
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS rating_distribution")
