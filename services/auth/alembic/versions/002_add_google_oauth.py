"""add google oauth support

Revision ID: 002
Revises: 001
Create Date: 2026-02-28

"""
from alembic import op

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE auth.users ADD COLUMN google_id VARCHAR(255) UNIQUE")
    op.execute("ALTER TABLE auth.users ALTER COLUMN password_hash DROP NOT NULL")
    op.execute("""
        CREATE INDEX idx_users_google_id ON auth.users (google_id)
        WHERE google_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_google_id")
    op.execute("ALTER TABLE auth.users ALTER COLUMN password_hash SET NOT NULL")
    op.execute("ALTER TABLE auth.users DROP COLUMN IF EXISTS google_id")
