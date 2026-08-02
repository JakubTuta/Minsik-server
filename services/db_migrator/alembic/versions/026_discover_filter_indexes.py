"""indexes for the Discover page's most common filters

discovery_service builds book_length and era filters as unindexed range
predicates on books.books(number_of_pages) and
books.books(original_publication_year) — both are applied to the whole
catalog on every /discover and /discover/count request, forcing a sequential
scan. Adding the two most-selected filters (page-count and era buckets) an
index each turns that into an index scan.

Revision ID: 026
Revises: 025
Create Date: 2026-08-02
"""

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_number_of_pages "
        "ON books.books(number_of_pages) WHERE number_of_pages IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_original_publication_year "
        "ON books.books(original_publication_year) "
        "WHERE original_publication_year IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_books_original_publication_year")
    op.execute("DROP INDEX IF EXISTS books.idx_books_number_of_pages")
