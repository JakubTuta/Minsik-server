"""index for the Discover count; drop the work_id index the unique one now covers

Discover counts the distinct works that have a cover. COUNT(DISTINCT work_id) over the
whole table took ~285ms at 280k rows, ~170ms as a GROUP BY, and ~36ms as a GROUP BY that
can run off a partial index on exactly the rows it counts (6MB).

idx_books_work_id (14MB) is the leading column of the unique (work_id, language) index
added in 027, which answers every work_id equality lookup the same way (measured: 0.25ms
against 0.42ms for a single-work lookup), so it only costs write time and space now.

Revision ID: 029
Revises: 028
Create Date: 2026-10-10
"""

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_work_id_cover ON books.books(work_id) "
        "WHERE primary_cover_url IS NOT NULL AND primary_cover_url != ''"
    )
    op.execute("DROP INDEX IF EXISTS books.idx_books_work_id")


def downgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_work_id ON books.books(work_id)")
    op.execute("DROP INDEX IF EXISTS books.idx_books_work_id_cover")
