"""add external_ids work_ol_id index

Revision ID: 004
Revises: 003
Create Date: 2026-03-23
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_work_ol_id "
        "ON books.books ((external_ids->>'work_ol_id'))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_books_work_ol_id")
