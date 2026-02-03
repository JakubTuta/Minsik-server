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

    op.add_column('books', sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'), schema='books')
    op.add_column('books', sa.Column('last_viewed_at', sa.TIMESTAMP(), nullable=True), schema='books')
    op.create_index('idx_books_view_count', 'books', ['view_count'], schema='books', postgresql_ops={'view_count': 'DESC'})

    op.add_column('authors', sa.Column('ts_vector', postgresql.TSVECTOR(), nullable=True), schema='books')
    op.add_column('authors', sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'), schema='books')
    op.add_column('authors', sa.Column('last_viewed_at', sa.TIMESTAMP(), nullable=True), schema='books')
    op.create_index('idx_authors_ts_vector', 'authors', ['ts_vector'], schema='books', postgresql_using='gin')
    op.create_index('idx_authors_view_count', 'authors', ['view_count'], schema='books', postgresql_ops={'view_count': 'DESC'})

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

    op.execute("UPDATE books.authors SET name = name")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_update_author_ts_vector ON books.authors")
    op.execute("DROP FUNCTION IF EXISTS books.update_author_ts_vector()")

    op.drop_index('idx_authors_view_count', table_name='authors', schema='books')
    op.drop_index('idx_authors_ts_vector', table_name='authors', schema='books')
    op.drop_column('authors', 'last_viewed_at', schema='books')
    op.drop_column('authors', 'view_count', schema='books')
    op.drop_column('authors', 'ts_vector', schema='books')

    op.drop_index('idx_books_view_count', table_name='books', schema='books')
    op.drop_column('books', 'last_viewed_at', schema='books')
    op.drop_column('books', 'view_count', schema='books')
