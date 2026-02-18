"""remove full-text search: ts_vector columns, GIN indexes, triggers

Revision ID: 003
Revises: 002
Create Date: 2026-02-18
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS books_ts_vector_update ON books.books")
    op.execute("DROP TRIGGER IF EXISTS trig_update_books_ts_vector ON books.books")
    op.execute("DROP TRIGGER IF EXISTS authors_ts_vector_update ON books.authors")
    op.execute("DROP TRIGGER IF EXISTS trig_update_authors_ts_vector ON books.authors")
    op.execute("DROP TRIGGER IF EXISTS series_ts_vector_update ON books.series")
    op.execute("DROP TRIGGER IF EXISTS trig_update_series_ts_vector ON books.series")

    op.execute("DROP FUNCTION IF EXISTS books.update_books_ts_vector() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS books.update_authors_ts_vector() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS books.update_series_ts_vector() CASCADE")

    op.execute("DROP INDEX IF EXISTS books.idx_books_ts_vector")
    op.execute("DROP INDEX IF EXISTS books.idx_authors_ts_vector")
    op.execute("DROP INDEX IF EXISTS books.idx_series_ts_vector")

    op.drop_column("books", "ts_vector", schema="books")
    op.drop_column("authors", "ts_vector", schema="books")
    op.drop_column("series", "ts_vector", schema="books")


def downgrade() -> None:
    op.add_column("books", sa.Column("ts_vector", postgresql.TSVECTOR()), schema="books")
    op.add_column("authors", sa.Column("ts_vector", postgresql.TSVECTOR()), schema="books")
    op.add_column("series", sa.Column("ts_vector", postgresql.TSVECTOR()), schema="books")

    op.execute("CREATE INDEX idx_books_ts_vector ON books.books USING GIN(ts_vector)")
    op.execute("CREATE INDEX idx_authors_ts_vector ON books.authors USING GIN(ts_vector)")
    op.execute("CREATE INDEX idx_series_ts_vector ON books.series USING GIN(ts_vector)")

    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_books_ts_vector() RETURNS trigger AS $$
        BEGIN
            NEW.ts_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER books_ts_vector_update
        BEFORE INSERT OR UPDATE ON books.books
        FOR EACH ROW EXECUTE FUNCTION books.update_books_ts_vector()
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_authors_ts_vector() RETURNS trigger AS $$
        BEGIN
            NEW.ts_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.bio, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER authors_ts_vector_update
        BEFORE INSERT OR UPDATE ON books.authors
        FOR EACH ROW EXECUTE FUNCTION books.update_authors_ts_vector()
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_series_ts_vector() RETURNS trigger AS $$
        BEGIN
            NEW.ts_vector := to_tsvector('english', COALESCE(NEW.name, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER series_ts_vector_update
        BEFORE INSERT OR UPDATE ON books.series
        FOR EACH ROW EXECUTE FUNCTION books.update_series_ts_vector()
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
