"""add readability, plot_complexity, humor to ratings

Revision ID: 002
Revises: 001
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'ratings',
        sa.Column('readability', sa.Numeric(2, 1), nullable=True),
        schema='user_data'
    )
    op.add_column(
        'ratings',
        sa.Column('plot_complexity', sa.Numeric(2, 1), nullable=True),
        schema='user_data'
    )
    op.add_column(
        'ratings',
        sa.Column('humor', sa.Numeric(2, 1), nullable=True),
        schema='user_data'
    )


def downgrade() -> None:
    op.drop_column('ratings', 'humor', schema='user_data')
    op.drop_column('ratings', 'plot_complexity', schema='user_data')
    op.drop_column('ratings', 'readability', schema='user_data')
