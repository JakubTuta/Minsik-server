-- ============================================================================
-- Minsik Database Schema Documentation
-- ============================================================================
-- This file serves as DOCUMENTATION ONLY - actual schema is managed by
-- SQLAlchemy models + Alembic migrations. This provides a reference for the
-- complete schema design with all tables, indexes, constraints, and rationale.
--
-- Source of truth: SQLAlchemy model files in services/*/app/models/
--
-- Database: PostgreSQL 15+
-- Design: Single database with multiple schemas (auth, books, user_data)
-- ============================================================================

-- Create schemas
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS books;
CREATE SCHEMA IF NOT EXISTS user_data;

-- ============================================================================
-- BOOKS SCHEMA - Core book catalog
-- ============================================================================

-- ----------------------------------------------------------------------------
-- books.books - Main book table (hybrid model: one entry per language)
-- Source: services/books/app/models/book.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.books (
    book_id BIGSERIAL PRIMARY KEY,

    title VARCHAR(500) NOT NULL,
    language VARCHAR(10) NOT NULL,           -- ISO 639-1 code (en, es, fr, de, etc.)
    slug VARCHAR(600) NOT NULL,              -- URL-friendly: "neuromancer", "1984-george-orwell"

    description TEXT,
    original_publication_year INT,

    -- Format availability (JSONB array of strings)
    -- Example: ["hardcover", "paperback", "ebook", "audiobook"]
    formats JSONB NOT NULL DEFAULT '[]',

    -- Cover history timeline (JSONB array of objects)
    -- Example: [
    --   {"year": 1984, "cover_url": "https://...", "publisher": "Ace"},
    --   {"year": 2016, "cover_url": "https://...", "publisher": "Penguin"}
    -- ]
    cover_history JSONB NOT NULL DEFAULT '[]',

    primary_cover_url VARCHAR(1000),

    ts_vector tsvector,                      -- Full-text search (auto-updated by trigger)

    -- Denormalized statistics
    rating_count INT NOT NULL DEFAULT 0,
    avg_rating DECIMAL(3,2),                 -- Average overall rating (0.00-5.00)
    sub_rating_stats JSONB NOT NULL DEFAULT '{}',  -- Per-dimension {avg, count} map

    view_count INT NOT NULL DEFAULT 0,       -- Two-tier: Redis -> PostgreSQL
    last_viewed_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- External IDs
    open_library_id VARCHAR(100),
    google_books_id VARCHAR(100),

    -- Series relationship
    series_id BIGINT REFERENCES books.series(series_id),
    series_position DECIMAL(5,2)             -- e.g. 1.00, 1.50 for fractional positions
);

-- Indexes for books.books
CREATE INDEX idx_books_language ON books.books(language);
CREATE INDEX idx_books_ts_vector ON books.books USING GIN(ts_vector);
CREATE UNIQUE INDEX idx_books_language_slug ON books.books(language, slug);
CREATE INDEX idx_books_rating_count ON books.books(rating_count DESC);
CREATE INDEX idx_books_view_count ON books.books(view_count DESC);

COMMENT ON TABLE books.books IS 'Main book catalog. One entry per language (English Neuromancer != Spanish Neuromancer)';
COMMENT ON COLUMN books.books.language IS 'ISO 639-1 language code. Each translation is a separate book entry';
COMMENT ON COLUMN books.books.slug IS 'URL-friendly identifier for routing (e.g., /book/neuromancer)';
COMMENT ON COLUMN books.books.sub_rating_stats IS 'Aggregated per-dimension rating averages and counts, updated on every rating change';

-- ----------------------------------------------------------------------------
-- books.authors - Author catalog
-- Source: services/books/app/models/author.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.authors (
    author_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(300) NOT NULL,
    slug VARCHAR(350) NOT NULL UNIQUE,       -- URL-friendly: "william-gibson"

    bio TEXT,
    birth_date DATE,
    death_date DATE,
    birth_place VARCHAR(500),
    nationality VARCHAR(200),
    photo_url VARCHAR(1000),

    ts_vector tsvector,                      -- For author name search

    view_count INT NOT NULL DEFAULT 0,
    last_viewed_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    open_library_id VARCHAR(100)
);

-- Indexes for books.authors
CREATE UNIQUE INDEX idx_authors_slug ON books.authors(slug);
CREATE INDEX idx_authors_name ON books.authors(name);
CREATE INDEX idx_authors_ts_vector ON books.authors USING GIN(ts_vector);
CREATE INDEX idx_authors_view_count ON books.authors(view_count DESC);

COMMENT ON TABLE books.authors IS 'Author catalog. Authors are language-agnostic (same author for all translations)';

-- ----------------------------------------------------------------------------
-- books.series - Book series
-- Source: services/books/app/models/series.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.series (
    series_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    slug VARCHAR(550) NOT NULL UNIQUE,
    description TEXT,
    total_books INT,

    ts_vector tsvector,                      -- For series name search

    view_count INT NOT NULL DEFAULT 0,
    last_viewed_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for books.series
CREATE UNIQUE INDEX idx_series_slug ON books.series(slug);
CREATE INDEX idx_series_ts_vector ON books.series USING GIN(ts_vector);
CREATE INDEX idx_series_view_count ON books.series(view_count DESC);

COMMENT ON TABLE books.series IS 'Book series with full-text search. Positions tracked via books.series_position';

-- ----------------------------------------------------------------------------
-- books.book_authors - Many-to-many relationship (books <-> authors)
-- Source: services/books/app/models/book_author.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.book_authors (
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES books.authors(author_id) ON DELETE CASCADE,

    PRIMARY KEY (book_id, author_id),
    CONSTRAINT uq_book_author UNIQUE (book_id, author_id)
);

CREATE INDEX idx_book_authors_book_id ON books.book_authors(book_id);
CREATE INDEX idx_book_authors_author_id ON books.book_authors(author_id);

COMMENT ON TABLE books.book_authors IS 'Many-to-many: books <-> authors';

-- ----------------------------------------------------------------------------
-- books.genres - Genre/tag taxonomy
-- Source: services/books/app/models/genre.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.genres (
    genre_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(150) NOT NULL UNIQUE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_genres_slug ON books.genres(slug);

COMMENT ON TABLE books.genres IS 'Genre taxonomy for book categorization';

-- ----------------------------------------------------------------------------
-- books.book_genres - Many-to-many relationship (books <-> genres)
-- Source: services/books/app/models/book_genre.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.book_genres (
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
    genre_id BIGINT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,

    PRIMARY KEY (book_id, genre_id),
    CONSTRAINT uq_book_genre UNIQUE (book_id, genre_id)
);

CREATE INDEX idx_book_genres_book_id ON books.book_genres(book_id);
CREATE INDEX idx_book_genres_genre_id ON books.book_genres(genre_id);

COMMENT ON TABLE books.book_genres IS 'Many-to-many: books <-> genres. Books can have multiple genres';

-- ============================================================================
-- AUTH SCHEMA - Authentication and user management
-- ============================================================================

-- ----------------------------------------------------------------------------
-- auth.users - User accounts
-- Source: services/auth/app/models/user.py
-- ----------------------------------------------------------------------------
CREATE TABLE auth.users (
    user_id BIGSERIAL PRIMARY KEY,

    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(200),
    password_hash VARCHAR(255) NOT NULL,      -- bcrypt with cost 12

    role VARCHAR(10) NOT NULL DEFAULT 'user', -- 'user' or 'admin'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    avatar_url VARCHAR(1000),
    bio TEXT,

    last_login TIMESTAMP,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT check_user_role CHECK (role IN ('user', 'admin'))
);

COMMENT ON TABLE auth.users IS 'User accounts. Passwords hashed with bcrypt cost 12. Admins assigned via DB';

-- ----------------------------------------------------------------------------
-- auth.refresh_tokens - JWT refresh token tracking
-- Source: services/auth/app/models/refresh_token.py
-- ----------------------------------------------------------------------------
CREATE TABLE auth.refresh_tokens (
    token_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,

    token_hash VARCHAR(255) NOT NULL UNIQUE,  -- SHA-256 hash of refresh token
    expires_at TIMESTAMP NOT NULL,

    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMP,
    replaced_by_token_id BIGINT,             -- Tracks token rotation chain

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE auth.refresh_tokens IS 'JWT refresh tokens. Supports token rotation and revocation';

-- ============================================================================
-- USER_DATA SCHEMA - User-generated content
-- ============================================================================

-- ----------------------------------------------------------------------------
-- user_data.bookshelves - User reading status and lists
-- Source: services/user_data/app/models/bookshelf.py
-- Partitioned: HASH by user_id (4 partitions)
-- ----------------------------------------------------------------------------
CREATE TABLE user_data.bookshelves (
    bookshelf_id BIGSERIAL,
    user_id BIGINT NOT NULL,
    book_id BIGINT NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'want_to_read',
    is_favorite BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (bookshelf_id, user_id),
    CONSTRAINT check_bookshelf_status CHECK (status IN ('want_to_read', 'reading', 'read', 'abandoned')),
    CONSTRAINT uq_bookshelves_user_book UNIQUE (user_id, book_id)
) PARTITION BY HASH (user_id);

CREATE TABLE user_data.bookshelves_p0 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE user_data.bookshelves_p1 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE user_data.bookshelves_p2 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE user_data.bookshelves_p3 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 3);

-- Indexes for user_data.bookshelves
CREATE INDEX idx_bookshelves_user_status_date ON user_data.bookshelves(user_id, status, created_at DESC);
CREATE INDEX idx_bookshelves_user_fav ON user_data.bookshelves(user_id, created_at DESC) WHERE is_favorite = TRUE;
CREATE INDEX idx_bookshelves_book_id ON user_data.bookshelves(book_id);

COMMENT ON TABLE user_data.bookshelves IS 'User reading lists and status. Partitioned by user_id (4 HASH partitions)';

-- ----------------------------------------------------------------------------
-- user_data.ratings - Multi-dimensional book ratings (9 dimensions)
-- Source: services/user_data/app/models/rating.py
-- ----------------------------------------------------------------------------
CREATE TABLE user_data.ratings (
    rating_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    book_id BIGINT NOT NULL,

    -- Required
    overall_rating DECIMAL(2,1) NOT NULL,
    review_text TEXT,

    -- Quality dimensions (higher = better)
    emotional_impact DECIMAL(2,1),           -- Emotional resonance
    intellectual_depth DECIMAL(2,1),          -- Thought-provoking
    writing_quality DECIMAL(2,1),            -- Prose quality
    rereadability DECIMAL(2,1),              -- Would read again

    -- Spectrum dimensions (labeled endpoints)
    pacing DECIMAL(2,1),                     -- Slow burn <-> fast-paced
    readability DECIMAL(2,1),                -- Easy <-> challenging
    plot_complexity DECIMAL(2,1),            -- Simple <-> complex
    humor DECIMAL(2,1),                      -- Serious <-> humorous

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ratings_user_book UNIQUE (user_id, book_id),
    CONSTRAINT check_overall_rating CHECK (overall_rating >= 1.0 AND overall_rating <= 5.0)
);

-- Indexes for user_data.ratings
CREATE INDEX idx_ratings_user_date ON user_data.ratings(user_id, created_at DESC);
CREATE INDEX idx_ratings_user_score ON user_data.ratings(user_id, overall_rating DESC);
CREATE INDEX idx_ratings_book_id ON user_data.ratings(book_id);
CREATE INDEX idx_ratings_created ON user_data.ratings USING BRIN(created_at);

COMMENT ON TABLE user_data.ratings IS 'Multi-dimensional book ratings (9 dimensions)';
COMMENT ON COLUMN user_data.ratings.pacing IS '1=Slow burn, 5=Fast-paced';
COMMENT ON COLUMN user_data.ratings.readability IS '1=Easy, 5=Challenging';
COMMENT ON COLUMN user_data.ratings.plot_complexity IS '1=Simple, 5=Complex';
COMMENT ON COLUMN user_data.ratings.humor IS '1=Serious, 5=Humorous';

-- ----------------------------------------------------------------------------
-- user_data.comments - Public book reviews (one per user per book)
-- Source: services/user_data/app/models/comment.py
-- ----------------------------------------------------------------------------
CREATE TABLE user_data.comments (
    comment_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    book_id BIGINT NOT NULL,

    body TEXT NOT NULL,
    is_spoiler BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_comments_user_book UNIQUE (user_id, book_id)
);

-- Indexes for user_data.comments
CREATE INDEX idx_comments_book_date ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE;
CREATE INDEX idx_comments_book_no_spoiler ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE AND is_spoiler = FALSE;
CREATE INDEX idx_comments_user_date ON user_data.comments(user_id, created_at DESC) WHERE is_deleted = FALSE;
CREATE INDEX ix_comments_book_id_is_deleted ON user_data.comments(book_id, is_deleted);
CREATE INDEX ix_comments_book_id_is_deleted_created_at ON user_data.comments(book_id, is_deleted, created_at);

COMMENT ON TABLE user_data.comments IS 'Public book reviews. One comment per user per book. Joined with ratings for display.';

-- NOTE: user_data.notes table has been REMOVED from scope (dropped in migration 003)

-- ============================================================================
-- PLANNED TABLES (not yet implemented as SQLAlchemy models)
-- ============================================================================

-- user_data.reading_profiles - Reading DNA (planned, not yet implemented)
-- recommendations.book_similarities - Pre-computed similarities (planned)
-- recommendations.user_recommendations - Pre-computed recommendations (planned)
-- recommendations.book_influences - Book lineage graph (planned)

-- ============================================================================
-- TRIGGERS - Automated field updates
-- ============================================================================

-- Full-text search trigger for books.books
CREATE OR REPLACE FUNCTION books.update_books_ts_vector() RETURNS trigger AS $$
BEGIN
    NEW.ts_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER books_ts_vector_update
BEFORE INSERT OR UPDATE ON books.books
FOR EACH ROW EXECUTE FUNCTION books.update_books_ts_vector();

-- Full-text search trigger for books.authors
CREATE OR REPLACE FUNCTION books.update_authors_ts_vector() RETURNS trigger AS $$
BEGIN
    NEW.ts_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.bio, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER authors_ts_vector_update
BEFORE INSERT OR UPDATE ON books.authors
FOR EACH ROW EXECUTE FUNCTION books.update_authors_ts_vector();

-- Updated_at triggers (user_data schema uses its own function)
CREATE OR REPLACE FUNCTION user_data.update_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trig_bookshelves_updated_at BEFORE UPDATE ON user_data.bookshelves
    FOR EACH ROW EXECUTE FUNCTION user_data.update_updated_at();

CREATE TRIGGER trig_ratings_updated_at BEFORE UPDATE ON user_data.ratings
    FOR EACH ROW EXECUTE FUNCTION user_data.update_updated_at();

CREATE TRIGGER trig_comments_updated_at BEFORE UPDATE ON user_data.comments
    FOR EACH ROW EXECUTE FUNCTION user_data.update_updated_at();

-- ============================================================================
-- PERFORMANCE NOTES
-- ============================================================================

-- Partitioning:
-- - user_data.bookshelves: HASH partition by user_id (4 partitions, active)
--
-- Future partitioning (not yet implemented):
-- - user_data.ratings: RANGE partition by created_at (when ratings accumulate)

-- Index Maintenance:
-- - REINDEX monthly for heavily updated indexes
-- - VACUUM ANALYZE after bulk imports
-- - Monitor index bloat with pg_stat_user_indexes

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
