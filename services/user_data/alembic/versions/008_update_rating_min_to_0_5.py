"""update rating minimum from 1.0 to 0.5

Revision ID: 008
Revises: 007
Create Date: 2026-02-17

"""
from alembic import op


revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_data.ratings
        DROP CONSTRAINT IF EXISTS check_overall_rating
    """)
    op.execute("""
        ALTER TABLE user_data.ratings
        ADD CONSTRAINT check_overall_rating
        CHECK (overall_rating >= 0.5 AND overall_rating <= 5.0)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_data.ratings
        DROP CONSTRAINT IF EXISTS check_overall_rating
    """)
    op.execute("""
        ALTER TABLE user_data.ratings
        ADD CONSTRAINT check_overall_rating
        CHECK (overall_rating >= 1.0 AND overall_rating <= 5.0)
    """)
