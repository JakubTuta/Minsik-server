"""add composite index on ratings(book_id, overall_rating DESC) for ranking queries

Revision ID: 007
Revises: 006
Create Date: 2026-02-16
"""
from alembic import op

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX idx_ratings_book_overall "
        "ON user_data.ratings (book_id, overall_rating DESC)"
    )


def downgrade() -> None:
    op.drop_index("idx_ratings_book_overall", table_name="ratings", schema="user_data")
