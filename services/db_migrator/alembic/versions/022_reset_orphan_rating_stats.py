"""reset rating stats for work_id groups with no actual ratings

021's repool only UPDATEs work_id groups that have at least one row in
user_data.ratings (it INNER JOINs ratings). A work_id group backfilled from
COALESCE(work_ol_id, open_library_id, slug) that happens to have zero
ratings today still carries whatever avg_rating/rating_count/rating_distribution/
sub_rating_stats it accumulated under the old slug-based pooling — including
figures inherited from an unrelated book that only coincidentally shared a
slug. This resets any book with no ratings under the real work_id grouping
back to a clean zero state.

Revision ID: 022
Revises: 021
Create Date: 2026-07-25
"""

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE books.books b
        SET
            avg_rating = NULL,
            rating_count = 0,
            rating_distribution = '{}',
            sub_rating_stats = '{}'
        WHERE NOT EXISTS (
            SELECT 1
            FROM books.books sib
            JOIN user_data.ratings r ON r.book_id = sib.book_id
            WHERE sib.work_id = b.work_id
        )
        AND (b.rating_count != 0 OR b.avg_rating IS NOT NULL)
    """)


def downgrade() -> None:
    pass
