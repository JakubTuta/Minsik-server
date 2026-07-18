"""add finished_at/started_at to bookshelves for year-in-review reporting

bookshelves had no dedicated "date finished" signal — the existing this-year
stats proxied on updated_at, which also bumps on favourite toggles and status
re-saves, mis-attributing books to years they were not actually finished in.
This adds finished_at/started_at, backfilled from updated_at for existing
rows. The updated_at trigger is disabled during backfill so the backfill
UPDATE does not itself bump updated_at to now().

Revision ID: 020
Revises: 019
Create Date: 2026-07-18
"""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_data.bookshelves ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE user_data.bookshelves ADD COLUMN IF NOT EXISTS started_at TIMESTAMP"
    )

    op.execute(
        "ALTER TABLE user_data.bookshelves DISABLE TRIGGER trig_bookshelves_updated_at"
    )

    op.execute(
        "UPDATE user_data.bookshelves SET finished_at = updated_at "
        "WHERE status = 'read' AND finished_at IS NULL"
    )
    op.execute(
        "UPDATE user_data.bookshelves SET started_at = updated_at "
        "WHERE status = 'reading' AND started_at IS NULL"
    )

    op.execute(
        "ALTER TABLE user_data.bookshelves ENABLE TRIGGER trig_bookshelves_updated_at"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_user_finished "
        "ON user_data.bookshelves (user_id, finished_at DESC) "
        "WHERE finished_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS user_data.idx_bookshelves_user_finished")
    op.execute("ALTER TABLE user_data.bookshelves DROP COLUMN IF EXISTS started_at")
    op.execute("ALTER TABLE user_data.bookshelves DROP COLUMN IF EXISTS finished_at")
