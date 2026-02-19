"""initial books schema

Revision ID: 001
Revises:
Create Date: 2026-02-19
"""
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS books")

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
            wikidata_id VARCHAR(50),
            wikipedia_url VARCHAR(1000),
            remote_ids JSONB NOT NULL DEFAULT '{}',
            alternate_names JSONB NOT NULL DEFAULT '[]',
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
            isbn JSONB NOT NULL DEFAULT '[]',
            publisher VARCHAR(500),
            number_of_pages INTEGER,
            external_ids JSONB NOT NULL DEFAULT '{}',
            rating_count INTEGER NOT NULL DEFAULT 0,
            avg_rating DECIMAL(3,2),
            sub_rating_stats JSONB NOT NULL DEFAULT '{}',
            ol_rating_count INTEGER NOT NULL DEFAULT 0,
            ol_avg_rating DECIMAL(3,2),
            ol_want_to_read_count INTEGER NOT NULL DEFAULT 0,
            ol_currently_reading_count INTEGER NOT NULL DEFAULT 0,
            ol_already_read_count INTEGER NOT NULL DEFAULT 0,
            view_count INTEGER NOT NULL DEFAULT 0,
            last_viewed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            open_library_id VARCHAR(100),
            google_books_id VARCHAR(100),
            series_id BIGINT REFERENCES books.series(series_id) ON DELETE SET NULL,
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

    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_books_language_slug ON books.books(language, slug)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_language ON books.books(language)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_rating_count ON books.books(rating_count DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_view_count ON books.books(view_count DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_open_library_id ON books.books(open_library_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_isbn ON books.books USING GIN(isbn)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_ol_rating_count ON books.books(ol_rating_count DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_ol_already_read_count ON books.books(ol_already_read_count DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_series ON books.books(series_id, series_position)")

    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_authors_slug ON books.authors(slug)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_authors_name ON books.authors(name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_authors_view_count ON books.authors(view_count DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_authors_open_library_id ON books.authors(open_library_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_authors_wikidata_id ON books.authors(wikidata_id)")

    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_series_slug ON books.series(slug)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_series_view_count ON books.series(view_count DESC)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_book_authors_book_id ON books.book_authors(book_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_book_authors_author_id ON books.book_authors(author_id)")

    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_genres_slug ON books.genres(slug)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_book_genres_book_id ON books.book_genres(book_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_book_genres_genre_id ON books.book_genres(genre_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS books.book_genres CASCADE")
    op.execute("DROP TABLE IF EXISTS books.genres CASCADE")
    op.execute("DROP TABLE IF EXISTS books.book_authors CASCADE")
    op.execute("DROP TABLE IF EXISTS books.books CASCADE")
    op.execute("DROP TABLE IF EXISTS books.series CASCADE")
    op.execute("DROP TABLE IF EXISTS books.authors CASCADE")
    op.execute("DROP SCHEMA IF EXISTS books")
