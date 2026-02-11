"""create user_data schema

Revision ID: 001
Revises:
Create Date: 2026-02-11

"""
from alembic import op

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS user_data')

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_data.bookshelves (
            bookshelf_id    BIGSERIAL,
            user_id         BIGINT NOT NULL,
            book_id         BIGINT NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'want_to_read',
            is_favorite     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (bookshelf_id, user_id),
            CONSTRAINT check_bookshelf_status
                CHECK (status IN ('want_to_read', 'reading', 'read', 'abandoned')),
            CONSTRAINT uq_bookshelves_user_book UNIQUE (user_id, book_id)
        ) PARTITION BY HASH (user_id)
    """)

    op.execute("CREATE TABLE user_data.bookshelves_p0 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 0)")
    op.execute("CREATE TABLE user_data.bookshelves_p1 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 1)")
    op.execute("CREATE TABLE user_data.bookshelves_p2 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 2)")
    op.execute("CREATE TABLE user_data.bookshelves_p3 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 3)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_data.ratings (
            rating_id           BIGSERIAL PRIMARY KEY,
            user_id             BIGINT NOT NULL,
            book_id             BIGINT NOT NULL,
            overall_rating      DECIMAL(2,1) NOT NULL,
            review_text         TEXT,
            pacing              DECIMAL(2,1),
            emotional_impact    DECIMAL(2,1),
            intellectual_depth  DECIMAL(2,1),
            writing_quality     DECIMAL(2,1),
            rereadability       DECIMAL(2,1),
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ratings_user_book UNIQUE (user_id, book_id),
            CONSTRAINT check_overall_rating CHECK (overall_rating >= 1.0 AND overall_rating <= 5.0)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_data.comments (
            comment_id  BIGSERIAL PRIMARY KEY,
            user_id     BIGINT NOT NULL,
            book_id     BIGINT NOT NULL,
            body        TEXT NOT NULL,
            is_spoiler  BOOLEAN NOT NULL DEFAULT FALSE,
            is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_data.notes (
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

    op.execute("CREATE INDEX idx_bookshelves_user_status_date ON user_data.bookshelves(user_id, status, created_at DESC)")
    op.execute("CREATE INDEX idx_bookshelves_user_fav ON user_data.bookshelves(user_id, created_at DESC) WHERE is_favorite = TRUE")
    op.execute("CREATE INDEX idx_bookshelves_book_id ON user_data.bookshelves(book_id)")

    op.execute("CREATE INDEX idx_ratings_user_date ON user_data.ratings(user_id, created_at DESC)")
    op.execute("CREATE INDEX idx_ratings_user_score ON user_data.ratings(user_id, overall_rating DESC)")
    op.execute("CREATE INDEX idx_ratings_book_id ON user_data.ratings(book_id)")
    op.execute("CREATE INDEX idx_ratings_created ON user_data.ratings USING BRIN (created_at)")

    op.execute("CREATE INDEX idx_comments_book_date ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE")
    op.execute("CREATE INDEX idx_comments_book_no_spoiler ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE AND is_spoiler = FALSE")
    op.execute("CREATE INDEX idx_comments_user_date ON user_data.comments(user_id, created_at DESC) WHERE is_deleted = FALSE")

    op.execute("CREATE INDEX idx_notes_user_book_page ON user_data.notes(user_id, book_id, page_number ASC NULLS LAST)")
    op.execute("CREATE INDEX idx_notes_user_date ON user_data.notes(user_id, created_at DESC)")

    op.execute("""
        CREATE OR REPLACE FUNCTION user_data.update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trig_bookshelves_updated_at
            BEFORE UPDATE ON user_data.bookshelves
            FOR EACH ROW
            EXECUTE FUNCTION user_data.update_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER trig_ratings_updated_at
            BEFORE UPDATE ON user_data.ratings
            FOR EACH ROW
            EXECUTE FUNCTION user_data.update_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER trig_comments_updated_at
            BEFORE UPDATE ON user_data.comments
            FOR EACH ROW
            EXECUTE FUNCTION user_data.update_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER trig_notes_updated_at
            BEFORE UPDATE ON user_data.notes
            FOR EACH ROW
            EXECUTE FUNCTION user_data.update_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_notes_updated_at ON user_data.notes")
    op.execute("DROP TRIGGER IF EXISTS trig_comments_updated_at ON user_data.comments")
    op.execute("DROP TRIGGER IF EXISTS trig_ratings_updated_at ON user_data.ratings")
    op.execute("DROP TRIGGER IF EXISTS trig_bookshelves_updated_at ON user_data.bookshelves")
    op.execute("DROP FUNCTION IF EXISTS user_data.update_updated_at()")

    op.execute("DROP TABLE IF EXISTS user_data.notes CASCADE")
    op.execute("DROP TABLE IF EXISTS user_data.comments CASCADE")
    op.execute("DROP TABLE IF EXISTS user_data.ratings CASCADE")
    op.execute("DROP TABLE IF EXISTS user_data.bookshelves CASCADE")
    op.execute("DROP SCHEMA IF EXISTS user_data")
