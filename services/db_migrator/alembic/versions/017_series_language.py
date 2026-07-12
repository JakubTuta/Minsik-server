"""add language column to books.series, make series rows per-language

Revision ID: 017
Revises: 016
Create Date: 2026-07-12
"""

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE books.series ADD COLUMN IF NOT EXISTS language VARCHAR(10)")

    op.execute(
        """
        UPDATE books.series s
        SET language = COALESCE(
            (
                SELECT b.language
                FROM books.books b
                WHERE b.series_id = s.series_id
                GROUP BY b.language
                ORDER BY COUNT(*) DESC, b.language ASC
                LIMIT 1
            ),
            'en'
        )
        WHERE s.language IS NULL
        """
    )

    op.execute(
        """
        UPDATE books.books b
        SET series_id = NULL
        FROM books.series s
        WHERE b.series_id = s.series_id
          AND b.language <> s.language
        """
    )

    op.execute("ALTER TABLE books.series ALTER COLUMN language SET NOT NULL")

    op.execute("DROP INDEX IF EXISTS books.idx_series_slug")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_series_slug_language "
        "ON books.series (slug, language)"
    )

    op.execute(
        """
        UPDATE books.series s
        SET total_books = (
            SELECT COUNT(*) FROM books.books b WHERE b.series_id = s.series_id
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_series_slug_language")

    op.execute(
        """
        WITH keep AS (
            SELECT DISTINCT ON (slug) series_id
            FROM books.series
            ORDER BY slug, total_books DESC NULLS LAST, series_id ASC
        )
        UPDATE books.books b
        SET series_id = (SELECT series_id FROM keep k JOIN books.series s ON s.series_id = k.series_id WHERE s.slug = (
            SELECT slug FROM books.series WHERE series_id = b.series_id
        ))
        WHERE b.series_id IS NOT NULL
          AND b.series_id NOT IN (SELECT series_id FROM keep)
        """
    )

    op.execute(
        """
        DELETE FROM books.series s
        WHERE s.series_id NOT IN (
            SELECT DISTINCT ON (slug) series_id
            FROM books.series
            ORDER BY slug, total_books DESC NULLS LAST, series_id ASC
        )
        """
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_series_slug ON books.series (slug)"
    )

    op.execute("ALTER TABLE books.series DROP COLUMN IF EXISTS language")
