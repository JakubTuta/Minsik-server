"""add sub_rating_stats to books

Revision ID: 004
Revises: 003
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE books.books
        ADD COLUMN IF NOT EXISTS sub_rating_stats JSONB NOT NULL DEFAULT '{}'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS sub_rating_stats")
