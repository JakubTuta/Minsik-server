"""per-work popularity ranking, rebuilt on a cron

The sitemap pages through works ordered by popularity, which meant grouping the whole
of books.books by work, sorting every work and discarding all but one page of it: ~300ms
for the first page and ~440ms for a deep one at 280k rows, on every uncached request.
books.work_rank holds the same ordering once, rebuilt by the books service with the
work shelf counts it depends on, so a page is an index range scan.

Revision ID: 028
Revises: 027
Create Date: 2026-10-10
"""

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.work_rank (
            work_id    VARCHAR(600) PRIMARY KEY,
            popularity BIGINT NOT NULL,
            rank       INTEGER NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_work_rank_rank ON books.work_rank(rank)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS books.work_rank")
