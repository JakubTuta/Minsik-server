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
    op.add_column(
        'books',
        sa.Column(
            'sub_rating_stats',
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb")
        ),
        schema='books'
    )


def downgrade() -> None:
    op.drop_column('books', 'sub_rating_stats', schema='books')
