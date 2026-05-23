"""add genre co-occurrences table for genre bubble feature

Revision ID: 008
Revises: 007
Create Date: 2026-05-23
"""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.genre_co_occurrences (
            genre_id_a          BIGINT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,
            genre_id_b          BIGINT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,
            co_occurrence_count INT    NOT NULL,
            strength            REAL   NOT NULL,
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (genre_id_a, genre_id_b),
            CHECK (genre_id_a < genre_id_b)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gco_a_strength "
        "ON books.genre_co_occurrences (genre_id_a, strength DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gco_b_strength "
        "ON books.genre_co_occurrences (genre_id_b, strength DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_gco_b_strength")
    op.execute("DROP INDEX IF EXISTS books.idx_gco_a_strength")
    op.execute("DROP TABLE IF EXISTS books.genre_co_occurrences")
