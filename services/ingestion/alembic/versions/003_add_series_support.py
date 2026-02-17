"""add series support

Revision ID: 003
Revises: 002
Create Date: 2026-02-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS books.series (
            series_id BIGSERIAL PRIMARY KEY,
            name VARCHAR(500) NOT NULL,
            slug VARCHAR(550) NOT NULL UNIQUE,
            description TEXT,
            total_books INT,
            ts_vector tsvector,
            view_count INTEGER NOT NULL DEFAULT 0,
            last_viewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_series_slug
        ON books.series(slug)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_series_ts_vector
        ON books.series USING GIN(ts_vector)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_series_view_count
        ON books.series(view_count DESC)
    """)

    op.execute("""
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS series_id BIGINT
    """)
    op.execute("""
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS series_position DECIMAL(5, 2)
    """)

    op.execute("""
        ALTER TABLE books.books
        DROP CONSTRAINT IF EXISTS fk_books_series
    """)
    op.execute("""
        ALTER TABLE books.books
        ADD CONSTRAINT fk_books_series
        FOREIGN KEY (series_id) REFERENCES books.series(series_id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_books_series
        ON books.books(series_id, series_position)
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_series_ts_vector()
        RETURNS trigger AS $$
        BEGIN
            NEW.ts_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trig_update_series_ts_vector ON books.series
    """)

    op.execute("""
        CREATE TRIGGER trig_update_series_ts_vector
        BEFORE INSERT OR UPDATE ON books.series
        FOR EACH ROW
        EXECUTE FUNCTION books.update_series_ts_vector();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_update_series_ts_vector ON books.series CASCADE")
    op.execute("DROP FUNCTION IF EXISTS books.update_series_ts_vector() CASCADE")

    op.execute("DROP INDEX IF EXISTS books.idx_books_series")
    op.execute("ALTER TABLE books.books DROP CONSTRAINT IF EXISTS fk_books_series")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS series_position")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS series_id")

    op.execute("DROP INDEX IF EXISTS books.idx_series_view_count")
    op.execute("DROP INDEX IF EXISTS books.idx_series_ts_vector")
    op.execute("DROP INDEX IF EXISTS books.idx_series_slug")
    op.execute("DROP TABLE IF EXISTS books.series CASCADE")
