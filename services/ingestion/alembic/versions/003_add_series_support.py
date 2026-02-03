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
    op.create_table(
        'series',
        sa.Column('series_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('slug', sa.String(length=550), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('total_books', sa.Integer(), nullable=True),
        sa.Column('ts_vector', postgresql.TSVECTOR(), nullable=True),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_viewed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('series_id'),
        sa.UniqueConstraint('slug'),
        schema='books'
    )

    op.create_index('idx_series_slug', 'series', ['slug'], unique=False, schema='books')
    op.create_index('idx_series_ts_vector', 'series', ['ts_vector'], unique=False, schema='books', postgresql_using='gin')
    op.create_index('idx_series_view_count', 'series', ['view_count'], unique=False, schema='books', postgresql_ops={'view_count': 'DESC'})

    op.add_column('books', sa.Column('series_id', sa.BigInteger(), nullable=True), schema='books')
    op.add_column('books', sa.Column('series_position', sa.DECIMAL(precision=5, scale=2), nullable=True), schema='books')

    op.create_foreign_key('fk_books_series', 'books', 'series', ['series_id'], ['series_id'], source_schema='books', referent_schema='books')
    op.create_index('idx_books_series', 'books', ['series_id', 'series_position'], unique=False, schema='books')

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
        CREATE TRIGGER trig_update_series_ts_vector
        BEFORE INSERT OR UPDATE ON books.series
        FOR EACH ROW
        EXECUTE FUNCTION books.update_series_ts_vector();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_update_series_ts_vector ON books.series")
    op.execute("DROP FUNCTION IF EXISTS books.update_series_ts_vector()")

    op.drop_index('idx_books_series', table_name='books', schema='books')
    op.drop_constraint('fk_books_series', 'books', schema='books', type_='foreignkey')
    op.drop_column('books', 'series_position', schema='books')
    op.drop_column('books', 'series_id', schema='books')

    op.drop_index('idx_series_view_count', table_name='series', schema='books')
    op.drop_index('idx_series_ts_vector', table_name='series', schema='books')
    op.drop_index('idx_series_slug', table_name='series', schema='books')
    op.drop_table('series', schema='books')
