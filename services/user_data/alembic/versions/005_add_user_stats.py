"""add user_stats table

Revision ID: 005
Revises: 004
Create Date: 2026-02-16
"""
import sqlalchemy as sa
from alembic import op

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_stats",
        sa.Column("user_id",            sa.BigInteger, primary_key=True),
        sa.Column("want_to_read_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reading_count",      sa.Integer, nullable=False, server_default="0"),
        sa.Column("read_count",         sa.Integer, nullable=False, server_default="0"),
        sa.Column("abandoned_count",    sa.Integer, nullable=False, server_default="0"),
        sa.Column("favourites_count",   sa.Integer, nullable=False, server_default="0"),
        sa.Column("ratings_count",      sa.Integer, nullable=False, server_default="0"),
        sa.Column("comments_count",     sa.Integer, nullable=False, server_default="0"),
        schema="user_data"
    )


def downgrade() -> None:
    op.drop_table("user_stats", schema="user_data")
