"""works per category with their ranking, rebuilt on a cron

A category page beyond the cached first 60 books ran the whole category through an edition
pick and a sort for every request: 150-490 ms at 200k works, and it grows with the
catalogue. books.category_works holds each category's works already ranked by popularity
and by rating, so a page is an index range scan plus the edition lookup for the 20 works
shown. The books service rebuilds it with the category cache and falls back to the old query
until a category has rows.

Revision ID: 032
Revises: 031
Create Date: 2026-10-10
"""

from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.category_works (
            category_slug VARCHAR(100) NOT NULL,
            work_id       VARCHAR(600) NOT NULL,
            popularity    BIGINT NOT NULL,
            rating_score  REAL NOT NULL,
            PRIMARY KEY (category_slug, work_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_category_works_popularity "
        "ON books.category_works (category_slug, popularity DESC, work_id DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_category_works_rating "
        "ON books.category_works (category_slug, rating_score DESC, work_id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS books.category_works")
