"""add series_slug/series_name columns to books for durable series membership

Revision ID: 014
Revises: 013
Create Date: 2026-06-13
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE books.books ADD COLUMN IF NOT EXISTS series_slug VARCHAR(550)")
    op.execute("ALTER TABLE books.books ADD COLUMN IF NOT EXISTS series_name VARCHAR(500)")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_series_slug_lang "
        "ON books.books (series_slug, language) WHERE series_slug IS NOT NULL"
    )

    op.execute(
        """
        UPDATE books.books b
        SET series_slug = s.slug,
            series_name = s.name
        FROM books.series s
        WHERE b.series_id = s.series_id
          AND b.series_slug IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_books_series_slug_lang")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS series_slug")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS series_name")
