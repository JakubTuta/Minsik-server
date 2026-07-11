"""add updated_at triggers for books.books, books.authors, books.series

Revision ID: 016
Revises: 015
Create Date: 2026-07-10
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

_TABLES = ["books", "authors", "series"]


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION books.update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    for table in _TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trig_{table}_updated_at') THEN
                    CREATE TRIGGER trig_{table}_updated_at
                        BEFORE UPDATE ON books.{table}
                        FOR EACH ROW
                        WHEN (OLD.* IS DISTINCT FROM NEW.*)
                        EXECUTE FUNCTION books.update_updated_at();
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trig_{table}_updated_at ON books.{table}")
    op.execute("DROP FUNCTION IF EXISTS books.update_updated_at()")
