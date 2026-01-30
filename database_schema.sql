-- ============================================================================
-- Minsik Database Schema Documentation
-- ============================================================================
-- This file serves as DOCUMENTATION ONLY - actual schema will be managed by
-- SQLAlchemy models. This provides a reference for the complete schema design
-- with all tables, indexes, constraints, and rationale.
--
-- Database: PostgreSQL 15+
-- Design: Single database with multiple schemas (auth, books, user_data, recommendations)
-- Philosophy: Production-quality schema from day 1, designed for scale
-- ============================================================================

-- Create schemas
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS books;
CREATE SCHEMA IF NOT EXISTS user_data;
CREATE SCHEMA IF NOT EXISTS recommendations;

-- ============================================================================
-- BOOKS SCHEMA - Core book catalog
-- ============================================================================

-- ----------------------------------------------------------------------------
-- books.books - Main book table (hybrid model: one entry per language)
-- ----------------------------------------------------------------------------
CREATE TABLE books.books (
    -- Primary identification
    book_id BIGSERIAL PRIMARY KEY,

    -- Core metadata
    title VARCHAR(500) NOT NULL,
    language VARCHAR(10) NOT NULL,  -- ISO 639-1 code (en, es, fr, de, etc.)
    slug VARCHAR(600) NOT NULL,     -- URL-friendly: "neuromancer", "1984-george-orwell"

    -- Content
    description TEXT,
    original_publication_year INT,
    page_count INT,  -- Typical page count across editions

    -- Format availability (JSONB array of strings)
    -- Example: ["hardcover", "paperback", "ebook", "audiobook"]
    formats JSONB NOT NULL DEFAULT '[]',

    -- Cover history timeline (JSONB array of objects)
    -- Example: [
    --   {"year": 1984, "cover_url": "https://...", "publisher": "Ace"},
    --   {"year": 2004, "cover_url": "https://...", "publisher": "Ace"},
    --   {"year": 2016, "cover_url": "https://...", "publisher": "Penguin"}
    -- ]
    cover_history JSONB NOT NULL DEFAULT '[]',

    -- Primary cover (latest or most iconic)
    primary_cover_url VARCHAR(1000),

    -- Additional flexible metadata
    metadata JSONB DEFAULT '{}',

    -- Full-text search vector (auto-updated by trigger)
    ts_vector tsvector,

    -- Denormalized statistics (for sorting/filtering)
    rating_count INT NOT NULL DEFAULT 0,
    avg_rating DECIMAL(3,2),  -- Average overall rating (0.00-5.00)

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT books_rating_count_positive CHECK (rating_count >= 0),
    CONSTRAINT books_avg_rating_range CHECK (avg_rating >= 0 AND avg_rating <= 5),
    CONSTRAINT books_year_reasonable CHECK (original_publication_year >= -3000 AND original_publication_year <= 2100)
);

-- Indexes for books.books

-- Use Case 1: Text search in specific language
-- Query: WHERE language='en' AND ts_vector @@ query
CREATE INDEX idx_books_language ON books.books(language);
CREATE INDEX idx_books_ts_vector ON books.books USING GIN(ts_vector);

-- Use Case 3: Book detail page by slug
-- Query: WHERE slug='neuromancer' AND language='en'
CREATE UNIQUE INDEX idx_books_language_slug ON books.books(language, slug);

-- Use Case 5: Popular books sorting
-- Query: WHERE rating_count > 50 ORDER BY rating_count DESC
CREATE INDEX idx_books_rating_count ON books.books(rating_count DESC)
WHERE rating_count > 50;  -- Partial index for popular books only

-- Composite for language-specific sorting (trending, popular, etc.)
CREATE INDEX idx_books_language_rating ON books.books(language, rating_count DESC);

-- For updated_at-based queries (recently added books)
CREATE INDEX idx_books_created_at ON books.books(created_at DESC);

-- Comments
COMMENT ON TABLE books.books IS 'Main book catalog. One entry per language (English Neuromancer ≠ Spanish Neuromancer)';
COMMENT ON COLUMN books.books.language IS 'ISO 639-1 language code. Each translation is a separate book entry';
COMMENT ON COLUMN books.books.slug IS 'URL-friendly identifier for routing (e.g., /book/neuromancer)';
COMMENT ON COLUMN books.books.cover_history IS 'Timeline of cover art changes across years for visual history feature';
COMMENT ON COLUMN books.books.formats IS 'Available formats array for "Buy this book in..." feature';

-- ----------------------------------------------------------------------------
-- books.authors - Author catalog
-- ----------------------------------------------------------------------------
CREATE TABLE books.authors (
    author_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(250) NOT NULL UNIQUE,  -- URL-friendly: "william-gibson"

    biography TEXT,
    birth_year INT,
    death_year INT,
    photo_url VARCHAR(1000),

    metadata JSONB DEFAULT '{}',
    ts_vector tsvector,  -- For author name search

    -- Statistics
    book_count INT NOT NULL DEFAULT 0,  -- Denormalized count

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT authors_death_after_birth CHECK (death_year IS NULL OR death_year >= birth_year)
);

-- Indexes for books.authors
CREATE INDEX idx_authors_name ON books.authors(name);
CREATE INDEX idx_authors_ts_vector ON books.authors USING GIN(ts_vector);
CREATE INDEX idx_authors_slug ON books.authors(slug);

COMMENT ON TABLE books.authors IS 'Author catalog. Authors are language-agnostic (same author for all translations)';

-- ----------------------------------------------------------------------------
-- books.book_authors - Many-to-many relationship (books ↔ authors)
-- ----------------------------------------------------------------------------
CREATE TABLE books.book_authors (
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES books.authors(author_id) ON DELETE CASCADE,
    author_order INT NOT NULL DEFAULT 1,  -- For multi-author books (1 = primary author)

    PRIMARY KEY (book_id, author_id)
);

-- Use Case 2: Author's page - show all their books
-- Query: JOIN book_authors WHERE author_id=X
CREATE INDEX idx_book_authors_author ON books.book_authors(author_id, book_id);
CREATE INDEX idx_book_authors_book ON books.book_authors(book_id);

COMMENT ON TABLE books.book_authors IS 'Many-to-many: books ↔ authors. Supports multi-author books';
COMMENT ON COLUMN books.book_authors.author_order IS 'Display order for multi-author books (1=primary)';

-- ----------------------------------------------------------------------------
-- books.genres - Genre/tag taxonomy
-- ----------------------------------------------------------------------------
CREATE TABLE books.genres (
    genre_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(120) NOT NULL UNIQUE,
    description TEXT,

    -- Hierarchy support (optional)
    parent_genre_id INT REFERENCES books.genres(genre_id) ON DELETE SET NULL,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_genres_parent ON books.genres(parent_genre_id);

COMMENT ON TABLE books.genres IS 'Genre taxonomy. Supports hierarchical genres (e.g., Fiction > Science Fiction > Cyberpunk)';

-- ----------------------------------------------------------------------------
-- books.book_genres - Many-to-many relationship (books ↔ genres)
-- ----------------------------------------------------------------------------
CREATE TABLE books.book_genres (
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
    genre_id INT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,

    PRIMARY KEY (book_id, genre_id)
);

-- Use Case 5b: Popular books in genre
-- Query: JOIN book_genres WHERE genre_id=X
CREATE INDEX idx_book_genres_genre ON books.book_genres(genre_id, book_id);
CREATE INDEX idx_book_genres_book ON books.book_genres(book_id);

COMMENT ON TABLE books.book_genres IS 'Many-to-many: books ↔ genres. Books can have multiple genres';

-- ============================================================================
-- USER_DATA SCHEMA - User-generated content
-- ============================================================================

-- ----------------------------------------------------------------------------
-- user_data.bookshelves - User reading status and lists
-- ----------------------------------------------------------------------------
CREATE TABLE user_data.bookshelves (
    bookshelf_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,  -- References auth.users (added later)
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,

    status VARCHAR(20) NOT NULL,  -- 'want_to_read', 'reading', 'read', 'abandoned'

    -- Reading tracking
    started_reading_at TIMESTAMP,
    finished_reading_at TIMESTAMP,
    progress_percentage INT DEFAULT 0,  -- For currently reading books

    -- Metadata
    is_favorite BOOLEAN DEFAULT FALSE,
    is_owned BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT bookshelves_user_book_unique UNIQUE (user_id, book_id),
    CONSTRAINT bookshelves_progress_range CHECK (progress_percentage >= 0 AND progress_percentage <= 100),
    CONSTRAINT bookshelves_status_valid CHECK (status IN ('want_to_read', 'reading', 'read', 'abandoned'))
) PARTITION BY HASH (user_id);  -- Partitioned for scale (Sprint 3+)

-- Create 8 partitions (implement in Sprint 3+ when users > 100k)
-- CREATE TABLE user_data.bookshelves_0 PARTITION OF user_data.bookshelves
--     FOR VALUES WITH (MODULUS 8, REMAINDER 0);
-- ... create partitions 1-7

-- Indexes for user_data.bookshelves
CREATE INDEX idx_bookshelves_user_status ON user_data.bookshelves(user_id, status);
CREATE INDEX idx_bookshelves_book ON user_data.bookshelves(book_id);

COMMENT ON TABLE user_data.bookshelves IS 'User reading lists and status. Partitioned by user_id for scale';

-- ----------------------------------------------------------------------------
-- user_data.ratings - Multi-dimensional book ratings
-- ----------------------------------------------------------------------------
CREATE TABLE user_data.ratings (
    rating_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,

    -- Multi-dimensional ratings (1-5 scale)
    overall_rating DECIMAL(2,1) NOT NULL,
    pacing DECIMAL(2,1),              -- Slow burn vs fast-paced
    emotional_impact DECIMAL(2,1),     -- Emotional resonance
    intellectual_depth DECIMAL(2,1),   -- Thought-provoking
    writing_quality DECIMAL(2,1),      -- Prose quality
    rereadability DECIMAL(2,1),        -- Would read again

    -- Metadata
    review_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT ratings_user_book_unique UNIQUE (user_id, book_id),
    CONSTRAINT ratings_overall_range CHECK (overall_rating >= 1 AND overall_rating <= 5),
    CONSTRAINT ratings_pacing_range CHECK (pacing IS NULL OR (pacing >= 1 AND pacing <= 5)),
    CONSTRAINT ratings_emotional_range CHECK (emotional_impact IS NULL OR (emotional_impact >= 1 AND emotional_impact <= 5)),
    CONSTRAINT ratings_intellectual_range CHECK (intellectual_depth IS NULL OR (intellectual_depth >= 1 AND intellectual_depth <= 5)),
    CONSTRAINT ratings_writing_range CHECK (writing_quality IS NULL OR (writing_quality >= 1 AND writing_quality <= 5)),
    CONSTRAINT ratings_rereadability_range CHECK (rereadability IS NULL OR (rereadability >= 1 AND rereadability <= 5))
) PARTITION BY RANGE (created_at);  -- Partitioned by year for scale

-- Create yearly partitions (implement in Sprint 2+)
-- CREATE TABLE user_data.ratings_2025 PARTITION OF user_data.ratings
--     FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
-- CREATE TABLE user_data.ratings_2026 PARTITION OF user_data.ratings
--     FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

-- Indexes for user_data.ratings
CREATE INDEX idx_ratings_user ON user_data.ratings(user_id);
CREATE INDEX idx_ratings_book ON user_data.ratings(book_id);
CREATE INDEX idx_ratings_created ON user_data.ratings USING BRIN(created_at);  -- Time-series index

COMMENT ON TABLE user_data.ratings IS 'Multi-dimensional book ratings. Partitioned by created_at for scale';
COMMENT ON COLUMN user_data.ratings.pacing IS '1=Slow burn, 5=Fast-paced';

-- ----------------------------------------------------------------------------
-- user_data.notes - User notes and annotations
-- ----------------------------------------------------------------------------
CREATE TABLE user_data.notes (
    note_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,

    note_text TEXT NOT NULL,
    page_number INT,
    is_spoiler BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
) PARTITION BY HASH (user_id);  -- Partitioned by user_id (Sprint 3+)

-- Indexes for user_data.notes
CREATE INDEX idx_notes_user_book ON user_data.notes(user_id, book_id);

COMMENT ON TABLE user_data.notes IS 'User notes and annotations on books. Partitioned by user_id';

-- ----------------------------------------------------------------------------
-- user_data.reading_profiles - Reading DNA and preferences
-- ----------------------------------------------------------------------------
CREATE TABLE user_data.reading_profiles (
    user_id BIGINT PRIMARY KEY,  -- One profile per user

    -- Reading DNA (JSONB for flexibility)
    -- Example: {
    --   "genre_distribution": {"sci-fi": 0.4, "fantasy": 0.3, "mystery": 0.3},
    --   "pacing_preference": 3.8,
    --   "avg_book_length": 350,
    --   "reading_velocity": 2.5,  -- books per month
    --   "mood_preferences": {"dark": 0.6, "uplifting": 0.2, ...}
    -- }
    reading_dna JSONB DEFAULT '{}',

    -- Preferences
    preferred_genres INT[],  -- Array of genre_ids
    preferred_languages VARCHAR(10)[],  -- Array of language codes

    -- Stats
    total_books_read INT DEFAULT 0,
    total_pages_read INT DEFAULT 0,

    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE user_data.reading_profiles IS 'User Reading DNA and preferences for personalized recommendations';

-- ============================================================================
-- RECOMMENDATIONS SCHEMA - Recommendation engine data
-- ============================================================================

-- ----------------------------------------------------------------------------
-- recommendations.book_similarities - Pre-computed book-to-book similarities
-- ----------------------------------------------------------------------------
CREATE TABLE recommendations.book_similarities (
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
    similar_book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,

    similarity_score DECIMAL(5,4) NOT NULL,  -- 0.0000 to 1.0000
    algorithm VARCHAR(50) NOT NULL,  -- 'collaborative', 'content_based', 'hybrid'

    computed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (book_id, similar_book_id),
    CONSTRAINT book_similarities_score_range CHECK (similarity_score >= 0 AND similarity_score <= 1),
    CONSTRAINT book_similarities_not_self CHECK (book_id != similar_book_id)
);

-- Use Case 4: "Similar books" on book detail page
CREATE INDEX idx_book_similarities_score ON recommendations.book_similarities(book_id, similarity_score DESC);

COMMENT ON TABLE recommendations.book_similarities IS 'Pre-computed book similarities. Refreshed daily via batch job';

-- ----------------------------------------------------------------------------
-- recommendations.user_recommendations - Pre-computed user recommendations
-- ----------------------------------------------------------------------------
CREATE TABLE recommendations.user_recommendations (
    user_id BIGINT NOT NULL,
    recommended_book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,

    score DECIMAL(5,4) NOT NULL,  -- Recommendation strength (0.0000 to 1.0000)
    reason VARCHAR(200),  -- "Because you liked Neuromancer"
    algorithm VARCHAR(50) NOT NULL,

    computed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (user_id, recommended_book_id),
    CONSTRAINT user_recommendations_score_range CHECK (score >= 0 AND score <= 1)
);

-- Use Case 4: User's personalized recommendation page
CREATE INDEX idx_user_recommendations_score ON recommendations.user_recommendations(user_id, score DESC);

COMMENT ON TABLE recommendations.user_recommendations IS 'Pre-computed user recommendations. Refreshed weekly via batch job';

-- ----------------------------------------------------------------------------
-- recommendations.book_influences - Book lineage/influence graph
-- ----------------------------------------------------------------------------
CREATE TABLE recommendations.book_influences (
    influencer_book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
    influenced_book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,

    influence_strength DECIMAL(3,2),  -- 0.00 to 1.00
    influence_type VARCHAR(50),  -- 'thematic', 'stylistic', 'narrative_structure'

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (influencer_book_id, influenced_book_id),
    CONSTRAINT book_influences_not_self CHECK (influencer_book_id != influenced_book_id)
);

CREATE INDEX idx_book_influences_influencer ON recommendations.book_influences(influencer_book_id);
CREATE INDEX idx_book_influences_influenced ON recommendations.book_influences(influenced_book_id);

COMMENT ON TABLE recommendations.book_influences IS 'Book lineage graph for "Influenced by" feature (Sprint 3+)';

-- ============================================================================
-- AUTH SCHEMA - Authentication and user management
-- ============================================================================

-- ----------------------------------------------------------------------------
-- auth.users - User accounts
-- ----------------------------------------------------------------------------
CREATE TABLE auth.users (
    user_id BIGSERIAL PRIMARY KEY,

    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt with cost 12

    -- Profile
    display_name VARCHAR(100),
    avatar_url VARCHAR(1000),
    bio TEXT,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMP,

    -- Security
    last_login TIMESTAMP,
    failed_login_attempts INT DEFAULT 0,
    locked_until TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON auth.users(email);
CREATE INDEX idx_users_username ON auth.users(username);
CREATE INDEX idx_users_active ON auth.users(is_active) WHERE is_active = TRUE;

COMMENT ON TABLE auth.users IS 'User accounts. Passwords hashed with bcrypt cost 12';

-- ----------------------------------------------------------------------------
-- auth.refresh_tokens - JWT refresh token tracking
-- ----------------------------------------------------------------------------
CREATE TABLE auth.refresh_tokens (
    token_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES auth.users(user_id) ON DELETE CASCADE,

    token_hash VARCHAR(255) NOT NULL UNIQUE,  -- SHA-256 hash of refresh token
    expires_at TIMESTAMP NOT NULL,

    -- Token rotation tracking
    is_revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    replaced_by_token_id BIGINT REFERENCES auth.refresh_tokens(token_id) ON DELETE SET NULL,

    -- Metadata
    user_agent VARCHAR(500),
    ip_address INET,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user ON auth.refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_hash ON auth.refresh_tokens(token_hash);
CREATE INDEX idx_refresh_tokens_expires ON auth.refresh_tokens(expires_at);

COMMENT ON TABLE auth.refresh_tokens IS 'JWT refresh tokens. Supports token rotation and revocation';

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
        setweight(to_tsvector('english', COALESCE(NEW.biography, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER authors_ts_vector_update
BEFORE INSERT OR UPDATE ON books.authors
FOR EACH ROW EXECUTE FUNCTION books.update_authors_ts_vector();

-- Updated_at trigger (generic)
CREATE OR REPLACE FUNCTION update_updated_at_column() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to all tables with updated_at column
CREATE TRIGGER update_books_updated_at BEFORE UPDATE ON books.books
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_authors_updated_at BEFORE UPDATE ON books.authors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bookshelves_updated_at BEFORE UPDATE ON user_data.bookshelves
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ratings_updated_at BEFORE UPDATE ON user_data.ratings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_notes_updated_at BEFORE UPDATE ON user_data.notes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- MATERIALIZED VIEWS - Pre-computed aggregations (Sprint 2+)
-- ============================================================================

-- Popular books (refreshed hourly)
CREATE MATERIALIZED VIEW recommendations.popular_books_mv AS
SELECT
    book_id,
    title,
    language,
    primary_cover_url,
    rating_count,
    avg_rating,
    (rating_count * avg_rating) AS popularity_score  -- Simple popularity metric
FROM books.books
WHERE rating_count >= 10  -- Minimum threshold
ORDER BY popularity_score DESC
LIMIT 1000;

CREATE UNIQUE INDEX ON recommendations.popular_books_mv (book_id);
CREATE INDEX ON recommendations.popular_books_mv (language, popularity_score DESC);

COMMENT ON MATERIALIZED VIEW recommendations.popular_books_mv IS 'Top 1000 popular books. Refresh hourly via RQ job';

-- Trending books (time-decay weighted, refreshed hourly)
CREATE MATERIALIZED VIEW recommendations.trending_books_mv AS
SELECT
    b.book_id,
    b.title,
    b.language,
    b.primary_cover_url,
    COUNT(*) as recent_rating_count,
    AVG(r.overall_rating) as avg_rating,
    -- Velocity: ratings per day in last 30 days
    COUNT(*)::DECIMAL / 30 as rating_velocity
FROM books.books b
JOIN user_data.ratings r ON b.book_id = r.book_id
WHERE r.created_at > NOW() - INTERVAL '30 days'
GROUP BY b.book_id, b.title, b.language, b.primary_cover_url
HAVING COUNT(*) >= 5
ORDER BY rating_velocity DESC
LIMIT 1000;

CREATE UNIQUE INDEX ON recommendations.trending_books_mv (book_id);

COMMENT ON MATERIALIZED VIEW recommendations.trending_books_mv IS 'Trending books (last 30 days). Refresh hourly';

-- ============================================================================
-- PERFORMANCE NOTES
-- ============================================================================

-- Partitioning Strategy:
-- - user_data.bookshelves: HASH partition by user_id (Sprint 3+ when users > 100k)
-- - user_data.ratings: RANGE partition by created_at (Sprint 2+ when ratings accumulate)
-- - user_data.notes: HASH partition by user_id (Sprint 3+ when notes > 500k)
--
-- To implement partitioning, uncomment the CREATE TABLE PARTITION statements above.

-- Index Maintenance:
-- - REINDEX monthly for heavily updated indexes
-- - VACUUM ANALYZE after bulk imports
-- - Monitor index bloat with pg_stat_user_indexes

-- Query Optimization:
-- - Use EXPLAIN ANALYZE for slow queries
-- - Consider covering indexes for hot queries
-- - Use partial indexes for filtered queries (rating_count > 50)
-- - BRIN indexes for time-series data (created_at columns)

-- Materialized View Refresh:
-- - Popular books: REFRESH MATERIALIZED VIEW CONCURRENTLY recommendations.popular_books_mv;
-- - Trending books: REFRESH MATERIALIZED VIEW CONCURRENTLY recommendations.trending_books_mv;
-- - Schedule via RQ job hourly

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
