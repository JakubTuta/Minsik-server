"""create recommendation schema with contextual_recs table

Revision ID: 005
Revises: 004
Create Date: 2026-05-06
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS recommendation")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation.contextual_recs (
            entity_type  TEXT        NOT NULL,
            entity_id    INTEGER     NOT NULL,
            section_key  TEXT        NOT NULL,
            display_name TEXT        NOT NULL,
            similar_ids  INTEGER[]   NOT NULL,
            computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (entity_type, entity_id, section_key)
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_contextual_recs_lookup "
        "ON recommendation.contextual_recs (entity_type, entity_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recommendation.contextual_recs")
    op.execute("DROP SCHEMA IF EXISTS recommendation CASCADE")
