"""add popularity tracking and author full-text search

Revision ID: 001
Revises:
Create Date: 2026-02-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS books')

    op.execute("""
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS view_count INTEGER NOT NULL DEFAULT 0
    """)
    op.execute("""
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS last_viewed_at TIMESTAMP
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_books_view_count
        ON books.books(view_count DESC)
    """)

    op.execute("""
        ALTER TABLE books.authors
        ADD COLUMN IF NOT EXISTS ts_vector tsvector
    """)
    op.execute("""
        ALTER TABLE books.authors
        ADD COLUMN IF NOT EXISTS view_count INTEGER NOT NULL DEFAULT 0
    """)
    op.execute("""
        ALTER TABLE books.authors
        ADD COLUMN IF NOT EXISTS last_viewed_at TIMESTAMP
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_authors_ts_vector
        ON books.authors USING GIN(ts_vector)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_authors_view_count
        ON books.authors(view_count DESC)
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_author_ts_vector()
        RETURNS trigger AS $$
        BEGIN
            NEW.ts_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.bio, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trig_update_author_ts_vector
        BEFORE INSERT OR UPDATE ON books.authors
        FOR EACH ROW
        EXECUTE FUNCTION books.update_author_ts_vector();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_update_author_ts_vector ON books.authors CASCADE")
    op.execute("DROP FUNCTION IF EXISTS books.update_author_ts_vector() CASCADE")

    op.execute("DROP INDEX IF EXISTS books.idx_authors_view_count")
    op.execute("DROP INDEX IF EXISTS books.idx_authors_ts_vector")
    op.execute("ALTER TABLE books.authors DROP COLUMN IF EXISTS last_viewed_at")
    op.execute("ALTER TABLE books.authors DROP COLUMN IF EXISTS view_count")
    op.execute("ALTER TABLE books.authors DROP COLUMN IF EXISTS ts_vector")

    op.execute("DROP INDEX IF EXISTS books.idx_books_view_count")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS last_viewed_at")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS view_count")
