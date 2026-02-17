"""add book ts_vector trigger

Revision ID: 002
Revises: 001
Create Date: 2026-02-03

"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_book_ts_vector()
        RETURNS trigger AS $$
        BEGIN
            NEW.ts_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trig_update_book_ts_vector ON books.books
    """)

    op.execute("""
        CREATE TRIGGER trig_update_book_ts_vector
        BEFORE INSERT OR UPDATE ON books.books
        FOR EACH ROW
        EXECUTE FUNCTION books.update_book_ts_vector();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_update_book_ts_vector ON books.books")
    op.execute("DROP FUNCTION IF EXISTS books.update_book_ts_vector()")
