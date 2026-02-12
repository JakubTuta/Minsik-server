"""add unique constraint to comments, drop notes table

Revision ID: 003
Revises: 002
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM user_data.comments c1 "
        "WHERE comment_id NOT IN ("
        "  SELECT MIN(comment_id) FROM user_data.comments "
        "  GROUP BY user_id, book_id"
        ")"
    )
    op.create_unique_constraint(
        'uq_comments_user_book',
        'comments',
        ['user_id', 'book_id'],
        schema='user_data'
    )
    op.execute("DROP TABLE IF EXISTS user_data.notes CASCADE")


def downgrade() -> None:
    op.drop_constraint('uq_comments_user_book', 'comments', schema='user_data', type_='unique')
    op.execute("""
        CREATE TABLE user_data.notes (
            note_id     BIGSERIAL,
            user_id     BIGINT NOT NULL,
            book_id     BIGINT NOT NULL,
            note_text   TEXT NOT NULL,
            page_number INTEGER,
            is_spoiler  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (note_id, user_id)
        ) PARTITION BY HASH (user_id)
    """)
    op.execute("CREATE TABLE user_data.notes_p0 PARTITION OF user_data.notes FOR VALUES WITH (MODULUS 4, REMAINDER 0)")
    op.execute("CREATE TABLE user_data.notes_p1 PARTITION OF user_data.notes FOR VALUES WITH (MODULUS 4, REMAINDER 1)")
    op.execute("CREATE TABLE user_data.notes_p2 PARTITION OF user_data.notes FOR VALUES WITH (MODULUS 4, REMAINDER 2)")
    op.execute("CREATE TABLE user_data.notes_p3 PARTITION OF user_data.notes FOR VALUES WITH (MODULUS 4, REMAINDER 3)")
