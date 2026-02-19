"""add popularity tracking

Revision ID: 001
Revises:
Create Date: 2026-02-03

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS books")

    op.execute(
        """
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS view_count INTEGER NOT NULL DEFAULT 0
    """
    )
    op.execute(
        """
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS last_viewed_at TIMESTAMP
    """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_books_view_count
        ON books.books(view_count DESC)
    """
    )

    op.execute(
        """
        ALTER TABLE books.authors
        ADD COLUMN IF NOT EXISTS view_count INTEGER NOT NULL DEFAULT 0
    """
    )
    op.execute(
        """
        ALTER TABLE books.authors
        ADD COLUMN IF NOT EXISTS last_viewed_at TIMESTAMP
    """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_authors_view_count
        ON books.authors(view_count DESC)
    """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_authors_view_count")
    op.execute("ALTER TABLE books.authors DROP COLUMN IF EXISTS last_viewed_at")
    op.execute("ALTER TABLE books.authors DROP COLUMN IF EXISTS view_count")

    op.execute("DROP INDEX IF EXISTS books.idx_books_view_count")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS last_viewed_at")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS view_count")
