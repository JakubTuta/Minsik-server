"""add staging tables for OL reading-log and ratings dump import

process_reading_log_dump used to zero every book's OL reading counts up
front, then spend potentially hours streaming the dump file and refilling
them in batches. Any interruption in that window (container restart,
redeploy, crash) left every not-yet-reached book stuck at zero permanently,
with no way to tell "genuinely zero" from "we never got back to it".
process_ratings_dump has no upfront reset, but the same long streaming
write means an interruption leaves a mix of books already updated from the
new dump and books still holding the previous dump's values.

These tables let both imports accumulate their new totals somewhere inert
and only overwrite books.books in one final swap once the whole file has
been parsed, so an interrupted run leaves the previous good data untouched
instead of half-applied.

Revision ID: 024
Revises: 023
Create Date: 2026-07-28
"""

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.reading_log_staging (
            book_id                     BIGINT PRIMARY KEY,
            ol_want_to_read_count       INTEGER NOT NULL DEFAULT 0,
            ol_currently_reading_count  INTEGER NOT NULL DEFAULT 0,
            ol_already_read_count       INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.ratings_staging (
            book_id          BIGINT PRIMARY KEY,
            ol_rating_count  INTEGER NOT NULL DEFAULT 0,
            ol_avg_rating    NUMERIC NOT NULL DEFAULT 0
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS books.ratings_staging")
    op.execute("DROP TABLE IF EXISTS books.reading_log_staging")
