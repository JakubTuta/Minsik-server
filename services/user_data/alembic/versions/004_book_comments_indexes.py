"""add indexes for book comments query

Revision ID: 004
Revises: 003
Create Date: 2026-02-12
"""
from alembic import op

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_comments_book_id_is_deleted",
        "comments",
        ["book_id", "is_deleted"],
        schema="user_data"
    )
    op.create_index(
        "ix_comments_book_id_is_deleted_created_at",
        "comments",
        ["book_id", "is_deleted", "created_at"],
        schema="user_data"
    )


def downgrade() -> None:
    op.drop_index("ix_comments_book_id_is_deleted_created_at", table_name="comments", schema="user_data")
    op.drop_index("ix_comments_book_id_is_deleted", table_name="comments", schema="user_data")
