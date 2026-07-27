"""add title_params to recommendation.contextual_recs

The precomputed contextual sections (more_by_author, more_from_series, ...)
store a pre-baked English display_name with no way for the frontend to
re-translate it. Adding a JSONB column of interpolation values (e.g.
{"author": "Ursula K. Le Guin"}) lets the frontend build the title from an
i18n key + params instead, matching the plain gRPC section payloads.

Revision ID: 023
Revises: 022
Create Date: 2026-07-26
"""

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE recommendation.contextual_recs "
        "ADD COLUMN IF NOT EXISTS title_params JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE recommendation.contextual_recs DROP COLUMN IF EXISTS title_params")
