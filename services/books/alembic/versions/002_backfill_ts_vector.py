"""backfill ts_vector and add series trigger

Revision ID: 002
Revises: 001
Create Date: 2026-02-17

"""
from alembic import op

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_series_ts_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.ts_vector := to_tsvector('english', COALESCE(NEW.name, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER series_ts_vector_update
            BEFORE INSERT OR UPDATE ON books.series
            FOR EACH ROW
            EXECUTE FUNCTION books.update_series_ts_vector()
    """)

    op.execute("""
        UPDATE books.books
        SET ts_vector =
            setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(description, '')), 'B')
        WHERE ts_vector IS NULL
    """)

    op.execute("""
        UPDATE books.authors
        SET ts_vector =
            setweight(to_tsvector('english', COALESCE(name, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(bio, '')), 'B')
        WHERE ts_vector IS NULL
    """)

    op.execute("""
        UPDATE books.series
        SET ts_vector = to_tsvector('english', COALESCE(name, ''))
        WHERE ts_vector IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS series_ts_vector_update ON books.series")
    op.execute("DROP FUNCTION IF EXISTS books.update_series_ts_vector()")
