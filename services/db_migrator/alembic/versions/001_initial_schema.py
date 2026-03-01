"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-01
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    _create_auth_schema()
    _create_books_schema()
    _create_user_data_schema()


def downgrade() -> None:
    _drop_user_data_schema()
    _drop_books_schema()
    _drop_auth_schema()


def _create_auth_schema() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth.users (
            user_id                 BIGSERIAL PRIMARY KEY,
            email                   VARCHAR(255) NOT NULL UNIQUE,
            username                VARCHAR(100) NOT NULL UNIQUE,
            display_name            VARCHAR(200),
            password_hash           VARCHAR(255),
            google_id               VARCHAR(255) UNIQUE,
            role                    VARCHAR(10) NOT NULL DEFAULT 'user',
            is_active               BOOLEAN NOT NULL DEFAULT TRUE,
            avatar_url              VARCHAR(1000),
            bio                     TEXT,
            last_login              TIMESTAMP,
            failed_login_attempts   INTEGER NOT NULL DEFAULT 0,
            locked_until            TIMESTAMP,
            created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at              TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT check_user_role CHECK (role IN ('user', 'admin'))
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth.refresh_tokens (
            token_id                BIGSERIAL PRIMARY KEY,
            user_id                 BIGINT NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,
            token_hash              VARCHAR(255) NOT NULL UNIQUE,
            expires_at              TIMESTAMP NOT NULL,
            is_revoked              BOOLEAN NOT NULL DEFAULT FALSE,
            revoked_at              TIMESTAMP,
            replaced_by_token_id    BIGINT,
            created_at              TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON auth.users (email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON auth.users (username)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_is_active ON auth.users (is_active)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_google_id ON auth.users (google_id) WHERE google_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON auth.refresh_tokens (token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON auth.refresh_tokens (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON auth.refresh_tokens (expires_at)"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION auth.update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trig_users_updated_at') THEN
                CREATE TRIGGER trig_users_updated_at
                    BEFORE UPDATE ON auth.users
                    FOR EACH ROW
                    EXECUTE FUNCTION auth.update_updated_at();
            END IF;
        END
        $$;
    """
    )


def _create_books_schema() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS books")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.authors (
            author_id           BIGSERIAL PRIMARY KEY,
            name                VARCHAR(300) NOT NULL,
            slug                VARCHAR(350) NOT NULL UNIQUE,
            bio                 TEXT,
            birth_date          DATE,
            death_date          DATE,
            birth_place         VARCHAR(500),
            nationality         VARCHAR(200),
            photo_url           VARCHAR(1000),
            wikidata_id         VARCHAR(50),
            wikipedia_url       VARCHAR(1000),
            remote_ids          JSONB NOT NULL DEFAULT '{}',
            alternate_names     JSONB NOT NULL DEFAULT '[]',
            view_count          INTEGER NOT NULL DEFAULT 0,
            last_viewed_at      TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            open_library_id     VARCHAR(100)
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.series (
            series_id       BIGSERIAL PRIMARY KEY,
            name            VARCHAR(500) NOT NULL,
            slug            VARCHAR(550) NOT NULL UNIQUE,
            description     TEXT,
            total_books     INT,
            view_count      INTEGER NOT NULL DEFAULT 0,
            last_viewed_at  TIMESTAMP,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.books (
            book_id                         BIGSERIAL PRIMARY KEY,
            title                           VARCHAR(500) NOT NULL,
            language                        VARCHAR(10) NOT NULL,
            slug                            VARCHAR(600) NOT NULL,
            description                     TEXT,
            first_sentence                  TEXT,
            original_publication_year       INT,
            formats                         JSONB NOT NULL DEFAULT '[]',
            cover_history                   JSONB NOT NULL DEFAULT '[]',
            primary_cover_url               VARCHAR(1000),
            isbn                            JSONB NOT NULL DEFAULT '[]',
            publisher                       VARCHAR(500),
            number_of_pages                 INTEGER,
            external_ids                    JSONB NOT NULL DEFAULT '{}',
            rating_count                    INTEGER NOT NULL DEFAULT 0,
            avg_rating                      DECIMAL(3,2),
            sub_rating_stats                JSONB NOT NULL DEFAULT '{}',
            ol_rating_count                 INTEGER NOT NULL DEFAULT 0,
            ol_avg_rating                   DECIMAL(3,2),
            ol_want_to_read_count           INTEGER NOT NULL DEFAULT 0,
            ol_currently_reading_count      INTEGER NOT NULL DEFAULT 0,
            ol_already_read_count           INTEGER NOT NULL DEFAULT 0,
            view_count                      INTEGER NOT NULL DEFAULT 0,
            last_viewed_at                  TIMESTAMP,
            created_at                      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at                      TIMESTAMP NOT NULL DEFAULT NOW(),
            open_library_id                 VARCHAR(100),
            google_books_id                 VARCHAR(100),
            series_id                       BIGINT REFERENCES books.series(series_id) ON DELETE SET NULL,
            series_position                 DECIMAL(5,2)
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.book_authors (
            book_id     BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
            author_id   BIGINT NOT NULL REFERENCES books.authors(author_id) ON DELETE CASCADE,
            PRIMARY KEY (book_id, author_id),
            CONSTRAINT uq_book_author UNIQUE (book_id, author_id)
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.genres (
            genre_id    BIGSERIAL PRIMARY KEY,
            name        VARCHAR(100) NOT NULL,
            slug        VARCHAR(150) NOT NULL UNIQUE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.book_genres (
            book_id     BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
            genre_id    BIGINT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,
            PRIMARY KEY (book_id, genre_id),
            CONSTRAINT uq_book_genre UNIQUE (book_id, genre_id)
        )
    """
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_books_language_slug ON books.books(language, slug)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_language ON books.books(language)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_rating_count ON books.books(rating_count DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_view_count ON books.books(view_count DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_open_library_id ON books.books(open_library_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_isbn ON books.books USING GIN(isbn)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_ol_rating_count ON books.books(ol_rating_count DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_ol_already_read_count ON books.books(ol_already_read_count DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_series ON books.books(series_id, series_position)"
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_authors_slug ON books.authors(slug)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_authors_name ON books.authors(name)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_authors_view_count ON books.authors(view_count DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_authors_open_library_id ON books.authors(open_library_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_authors_wikidata_id ON books.authors(wikidata_id)"
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_series_slug ON books.series(slug)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_series_view_count ON books.series(view_count DESC)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_authors_book_id ON books.book_authors(book_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_authors_author_id ON books.book_authors(author_id)"
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_genres_slug ON books.genres(slug)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_genres_book_id ON books.book_genres(book_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_book_genres_genre_id ON books.book_genres(genre_id)"
    )


def _create_user_data_schema() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS user_data")

    op.execute(
        """
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
    """
    )

    op.execute(
        "CREATE TABLE IF NOT EXISTS user_data.bookshelves_p0 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 0)"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS user_data.bookshelves_p1 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 1)"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS user_data.bookshelves_p2 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 2)"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS user_data.bookshelves_p3 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 3)"
    )

    op.execute(
        """
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
            readability         DECIMAL(2,1),
            plot_complexity     DECIMAL(2,1),
            humor               DECIMAL(2,1),
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ratings_user_book UNIQUE (user_id, book_id),
            CONSTRAINT check_overall_rating CHECK (overall_rating >= 0.5 AND overall_rating <= 5.0)
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_data.comments (
            comment_id  BIGSERIAL PRIMARY KEY,
            user_id     BIGINT NOT NULL,
            book_id     BIGINT NOT NULL,
            body        TEXT NOT NULL,
            is_spoiler  BOOLEAN NOT NULL DEFAULT FALSE,
            is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_comments_user_book UNIQUE (user_id, book_id)
        )
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_data.user_stats (
            user_id             BIGINT PRIMARY KEY,
            want_to_read_count  INTEGER NOT NULL DEFAULT 0,
            reading_count       INTEGER NOT NULL DEFAULT 0,
            read_count          INTEGER NOT NULL DEFAULT 0,
            abandoned_count     INTEGER NOT NULL DEFAULT 0,
            favourites_count    INTEGER NOT NULL DEFAULT 0,
            ratings_count       INTEGER NOT NULL DEFAULT 0,
            comments_count      INTEGER NOT NULL DEFAULT 0,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_user_status_date ON user_data.bookshelves(user_id, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_user_fav ON user_data.bookshelves(user_id, created_at DESC) WHERE is_favorite = TRUE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_book_id ON user_data.bookshelves(book_id)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ratings_user_date ON user_data.ratings(user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ratings_user_score ON user_data.ratings(user_id, overall_rating DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ratings_book_id ON user_data.ratings(book_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ratings_created ON user_data.ratings USING BRIN (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ratings_book_overall ON user_data.ratings(book_id, overall_rating DESC)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_comments_book_date ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_comments_book_no_spoiler ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE AND is_spoiler = FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_comments_user_date ON user_data.comments(user_id, created_at DESC) WHERE is_deleted = FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_comments_book_id_is_deleted ON user_data.comments(book_id, is_deleted)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_comments_book_id_is_deleted_created_at ON user_data.comments(book_id, is_deleted, created_at)"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION user_data.update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trig_bookshelves_updated_at') THEN
                CREATE TRIGGER trig_bookshelves_updated_at
                    BEFORE UPDATE ON user_data.bookshelves
                    FOR EACH ROW EXECUTE FUNCTION user_data.update_updated_at();
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trig_ratings_updated_at') THEN
                CREATE TRIGGER trig_ratings_updated_at
                    BEFORE UPDATE ON user_data.ratings
                    FOR EACH ROW EXECUTE FUNCTION user_data.update_updated_at();
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trig_comments_updated_at') THEN
                CREATE TRIGGER trig_comments_updated_at
                    BEFORE UPDATE ON user_data.comments
                    FOR EACH ROW EXECUTE FUNCTION user_data.update_updated_at();
            END IF;
        END
        $$;
    """
    )


def _drop_auth_schema() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_users_updated_at ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS auth.update_updated_at()")
    op.execute("DROP INDEX IF EXISTS idx_refresh_tokens_expires_at")
    op.execute("DROP INDEX IF EXISTS idx_refresh_tokens_user_id")
    op.execute("DROP INDEX IF EXISTS idx_refresh_tokens_token_hash")
    op.execute("DROP INDEX IF EXISTS idx_users_google_id")
    op.execute("DROP INDEX IF EXISTS idx_users_is_active")
    op.execute("DROP INDEX IF EXISTS idx_users_username")
    op.execute("DROP INDEX IF EXISTS idx_users_email")
    op.execute("DROP TABLE IF EXISTS auth.refresh_tokens")
    op.execute("DROP TABLE IF EXISTS auth.users")
    op.execute("DROP SCHEMA IF EXISTS auth")


def _drop_books_schema() -> None:
    op.execute("DROP TABLE IF EXISTS books.book_genres CASCADE")
    op.execute("DROP TABLE IF EXISTS books.genres CASCADE")
    op.execute("DROP TABLE IF EXISTS books.book_authors CASCADE")
    op.execute("DROP TABLE IF EXISTS books.books CASCADE")
    op.execute("DROP TABLE IF EXISTS books.series CASCADE")
    op.execute("DROP TABLE IF EXISTS books.authors CASCADE")
    op.execute("DROP SCHEMA IF EXISTS books")


def _drop_user_data_schema() -> None:
    op.execute("DROP TRIGGER IF EXISTS trig_comments_updated_at ON user_data.comments")
    op.execute("DROP TRIGGER IF EXISTS trig_ratings_updated_at ON user_data.ratings")
    op.execute(
        "DROP TRIGGER IF EXISTS trig_bookshelves_updated_at ON user_data.bookshelves"
    )
    op.execute("DROP FUNCTION IF EXISTS user_data.update_updated_at()")
    op.execute("DROP TABLE IF EXISTS user_data.user_stats CASCADE")
    op.execute("DROP TABLE IF EXISTS user_data.comments CASCADE")
    op.execute("DROP TABLE IF EXISTS user_data.ratings CASCADE")
    op.execute("DROP TABLE IF EXISTS user_data.bookshelves CASCADE")
    op.execute("DROP SCHEMA IF EXISTS user_data")
