"""add series support

Revision ID: 003
Revises: 002
Create Date: 2026-02-03

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.series (
            series_id BIGSERIAL PRIMARY KEY,
            name VARCHAR(500) NOT NULL,
            slug VARCHAR(550) NOT NULL UNIQUE,
            description TEXT,
            total_books INT,
            view_count INTEGER NOT NULL DEFAULT 0,
            last_viewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_series_slug
        ON books.series(slug)
    """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_series_view_count
        ON books.series(view_count DESC)
    """
    )

    op.execute(
        """
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS series_id BIGINT
    """
    )
    op.execute(
        """
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS series_position DECIMAL(5, 2)
    """
    )

    op.execute(
        """
        ALTER TABLE books.books
        DROP CONSTRAINT IF EXISTS fk_books_series
    """
    )
    op.execute(
        """
        ALTER TABLE books.books
        ADD CONSTRAINT fk_books_series
        FOREIGN KEY (series_id) REFERENCES books.series(series_id) ON DELETE SET NULL
    """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_books_series
        ON books.books(series_id, series_position)
    """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_books_series")
    op.execute("ALTER TABLE books.books DROP CONSTRAINT IF EXISTS fk_books_series")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS series_position")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS series_id")

    op.execute("DROP INDEX IF EXISTS books.idx_series_view_count")
    op.execute("DROP INDEX IF EXISTS books.idx_series_slug")
    op.execute("DROP TABLE IF EXISTS books.series CASCADE")
