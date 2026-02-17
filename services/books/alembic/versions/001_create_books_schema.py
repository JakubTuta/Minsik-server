"""create books schema

Revision ID: 001
Revises:
Create Date: 2026-02-17

"""
from alembic import op

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS books')

    op.execute("""
        CREATE TABLE IF NOT EXISTS books.authors (
            author_id BIGSERIAL PRIMARY KEY,
            name VARCHAR(300) NOT NULL,
            slug VARCHAR(350) NOT NULL UNIQUE,
            bio TEXT,
            birth_date DATE,
            death_date DATE,
            birth_place VARCHAR(500),
            nationality VARCHAR(200),
            photo_url VARCHAR(1000),
            ts_vector tsvector,
            view_count INTEGER NOT NULL DEFAULT 0,
            last_viewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            open_library_id VARCHAR(100)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS books.series (
            series_id BIGSERIAL PRIMARY KEY,
            name VARCHAR(500) NOT NULL,
            slug VARCHAR(550) NOT NULL UNIQUE,
            description TEXT,
            total_books INT,
            ts_vector tsvector,
            view_count INTEGER NOT NULL DEFAULT 0,
            last_viewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS books.books (
            book_id BIGSERIAL PRIMARY KEY,
            title VARCHAR(500) NOT NULL,
            language VARCHAR(10) NOT NULL,
            slug VARCHAR(600) NOT NULL,
            description TEXT,
            original_publication_year INT,
            formats JSONB NOT NULL DEFAULT '[]',
            cover_history JSONB NOT NULL DEFAULT '[]',
            primary_cover_url VARCHAR(1000),
            ts_vector tsvector,
            rating_count INTEGER NOT NULL DEFAULT 0,
            avg_rating DECIMAL(3,2),
            sub_rating_stats JSONB NOT NULL DEFAULT '{}',
            view_count INTEGER NOT NULL DEFAULT 0,
            last_viewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            open_library_id VARCHAR(100),
            google_books_id VARCHAR(100),
            series_id BIGINT REFERENCES books.series(series_id),
            series_position DECIMAL(5,2)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS books.book_authors (
            book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
            author_id BIGINT NOT NULL REFERENCES books.authors(author_id) ON DELETE CASCADE,
            PRIMARY KEY (book_id, author_id),
            CONSTRAINT uq_book_author UNIQUE (book_id, author_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS books.genres (
            genre_id BIGSERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(150) NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS books.book_genres (
            book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
            genre_id BIGINT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,
            PRIMARY KEY (book_id, genre_id),
            CONSTRAINT uq_book_genre UNIQUE (book_id, genre_id)
        )
    """)

    op.execute("CREATE UNIQUE INDEX idx_books_language_slug ON books.books(language, slug)")
    op.execute("CREATE INDEX idx_books_language ON books.books(language)")
    op.execute("CREATE INDEX idx_books_ts_vector ON books.books USING GIN(ts_vector)")
    op.execute("CREATE INDEX idx_books_rating_count ON books.books(rating_count DESC)")
    op.execute("CREATE INDEX idx_books_view_count ON books.books(view_count DESC)")

    op.execute("CREATE UNIQUE INDEX idx_authors_slug ON books.authors(slug)")
    op.execute("CREATE INDEX idx_authors_name ON books.authors(name)")
    op.execute("CREATE INDEX idx_authors_ts_vector ON books.authors USING GIN(ts_vector)")
    op.execute("CREATE INDEX idx_authors_view_count ON books.authors(view_count DESC)")

    op.execute("CREATE UNIQUE INDEX idx_series_slug ON books.series(slug)")
    op.execute("CREATE INDEX idx_series_ts_vector ON books.series USING GIN(ts_vector)")
    op.execute("CREATE INDEX idx_series_view_count ON books.series(view_count DESC)")

    op.execute("CREATE INDEX idx_book_authors_book_id ON books.book_authors(book_id)")
    op.execute("CREATE INDEX idx_book_authors_author_id ON books.book_authors(author_id)")

    op.execute("CREATE UNIQUE INDEX idx_genres_slug ON books.genres(slug)")

    op.execute("CREATE INDEX idx_book_genres_book_id ON books.book_genres(book_id)")
    op.execute("CREATE INDEX idx_book_genres_genre_id ON books.book_genres(genre_id)")

    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_books_ts_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.ts_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER books_ts_vector_update
            BEFORE INSERT OR UPDATE ON books.books
            FOR EACH ROW
            EXECUTE FUNCTION books.update_books_ts_vector()
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION books.update_authors_ts_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.ts_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.bio, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER authors_ts_vector_update
            BEFORE INSERT OR UPDATE ON books.authors
            FOR EACH ROW
            EXECUTE FUNCTION books.update_authors_ts_vector()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS authors_ts_vector_update ON books.authors")
    op.execute("DROP TRIGGER IF EXISTS books_ts_vector_update ON books.books")
    op.execute("DROP FUNCTION IF EXISTS books.update_authors_ts_vector()")
    op.execute("DROP FUNCTION IF EXISTS books.update_books_ts_vector()")
    op.execute("DROP TABLE IF EXISTS books.book_genres CASCADE")
    op.execute("DROP TABLE IF EXISTS books.genres CASCADE")
    op.execute("DROP TABLE IF EXISTS books.book_authors CASCADE")
    op.execute("DROP TABLE IF EXISTS books.books CASCADE")
    op.execute("DROP TABLE IF EXISTS books.series CASCADE")
    op.execute("DROP TABLE IF EXISTS books.authors CASCADE")
    op.execute("DROP SCHEMA IF EXISTS books")
