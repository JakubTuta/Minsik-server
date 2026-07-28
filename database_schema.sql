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
-- Design: Single database with multiple schemas (auth, books, user_data,
--         recommendation)
-- Reflects: Alembic revision 025
-- ============================================================================

-- Create schemas
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS books;
CREATE SCHEMA IF NOT EXISTS user_data;
CREATE SCHEMA IF NOT EXISTS recommendation;

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
    work_id VARCHAR(600) NOT NULL,           -- Cross-language work identity: external_ids->>'work_ol_id', falls back to slug

    description TEXT,
    first_sentence TEXT,              -- Opening line of the book (from OL works/editions dump)
    original_publication_year INT,

    -- Format availability (JSONB array of strings)
    -- Example: ["hardcover", "paperback", "ebook", "audiobook"]
    formats JSONB NOT NULL DEFAULT '[]',

    primary_cover_url VARCHAR(1000),

    -- Edition metadata (from OpenLibrary dump)
    isbn JSONB NOT NULL DEFAULT '[]',        -- List of ISBNs (ISBN-10 and ISBN-13)
    publisher VARCHAR(500),                  -- Edition publisher
    number_of_pages INTEGER,                 -- Page count

    -- External identifier map
    -- Example: {"goodreads": "123", "librarything": "456"}
    external_ids JSONB NOT NULL DEFAULT '{}',

    -- Denormalized statistics. Pooled per work, not per edition: every language
    -- row of a work carries the same totals (see rating_service._update_work_stats).
    rating_count INT NOT NULL DEFAULT 0,
    avg_rating DECIMAL(3,2),                 -- Average overall rating (0.5-5.0)
    -- Per-dimension aggregated stats. All 8 keys always present (default avg "0", count 0).
    -- Each value: {"avg": "3.5", "count": 12}
    --
    -- Quality dimensions (0.5 = poor, 5 = excellent):
    --   "emotional_impact"    - 0.5: leaves no impression       5: deeply moving
    --   "intellectual_depth"  - 0.5: shallow / surface-level    5: profound / thought-provoking
    --   "writing_quality"     - 0.5: poorly written             5: masterfully crafted prose
    --   "rereadability"       - 0.5: no desire to revisit       5: would gladly reread
    --
    -- Spectrum dimensions (0.5 and 5 are opposite ends, neither is inherently better):
    --   "pacing"              - 0.5: slow, deliberate           5: fast, action-packed
    --   "readability"         - 0.5: dense, challenging         5: light, easy read
    --   "plot_complexity"     - 0.5: simple, straightforward    5: complex, multi-layered
    --   "humor"               - 0.5: serious, no humor          5: very funny, comedic
    sub_rating_stats JSONB NOT NULL DEFAULT '{}',
    rating_distribution JSONB NOT NULL DEFAULT '{}', -- Per-half-star rating counts e.g. {"1.0": 5, "4.5": 12}

    -- OpenLibrary community statistics
    ol_rating_count INT NOT NULL DEFAULT 0,
    ol_avg_rating DECIMAL(3,2),              -- OpenLibrary average rating
    ol_want_to_read_count INT NOT NULL DEFAULT 0,
    ol_currently_reading_count INT NOT NULL DEFAULT 0,
    ol_already_read_count INT NOT NULL DEFAULT 0,

    view_count INT NOT NULL DEFAULT 0,       -- Two-tier: Redis -> PostgreSQL
    last_viewed_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- External IDs
    open_library_id VARCHAR(100),
    google_books_id VARCHAR(100),

    -- Series relationship. series_slug/series_name are denormalised copies kept
    -- so a book card can render its series without joining books.series.
    -- The FK is added after books.series is declared, further down.
    series_id BIGINT,
    series_position DECIMAL(5,2),            -- e.g. 1.00, 1.50 for fractional positions
    series_slug VARCHAR(550),
    series_name VARCHAR(500),

    -- Last time the description enricher tried this row, so a book whose
    -- lookup failed isn't retried on every pass (see description_enricher.py)
    enrichment_attempted_at TIMESTAMPTZ
);

-- Indexes for books.books
CREATE UNIQUE INDEX idx_books_language_slug ON books.books(language, slug);
CREATE INDEX idx_books_slug ON books.books(slug);
CREATE INDEX idx_books_work_id ON books.books(work_id);
CREATE INDEX idx_books_work_lang ON books.books(work_id, language);
CREATE INDEX idx_books_work_ol_id ON books.books(((external_ids ->> 'work_ol_id')));
CREATE INDEX idx_books_rating_count ON books.books(rating_count DESC);
CREATE INDEX idx_books_view_count ON books.books(view_count DESC);
CREATE INDEX idx_books_open_library_id ON books.books(open_library_id);
CREATE INDEX idx_books_isbn ON books.books USING gin(isbn);
CREATE INDEX idx_books_ol_rating_count ON books.books(ol_rating_count DESC);
CREATE INDEX idx_books_ol_already_read_count ON books.books(ol_already_read_count DESC);
CREATE INDEX idx_books_series_lang ON books.books(series_id, language, series_position);
CREATE INDEX idx_books_series_slug_lang ON books.books(series_slug, language) WHERE series_slug IS NOT NULL;
-- Feeds the incremental ES sync, which pulls rows changed since the last run
CREATE INDEX idx_books_updated_at ON books.books(updated_at);
-- Feeds the "Recently Added" recommendation list
CREATE INDEX idx_books_created_at ON books.books(created_at DESC);

COMMENT ON TABLE books.books IS 'Main book catalog. One entry per language (English Neuromancer != Spanish Neuromancer)';
COMMENT ON COLUMN books.books.language IS 'ISO 639-1 language code. Each translation is a separate book entry';
COMMENT ON COLUMN books.books.slug IS 'URL-friendly identifier for routing (e.g., /book/neuromancer). Unique per language, NOT globally';
COMMENT ON COLUMN books.books.work_id IS 'Cross-language work identity shared by all translations of the same book. Used to dedup search/recommendation results and to pool ratings, comments, reader counts, and view counts across editions.';
COMMENT ON COLUMN books.books.sub_rating_stats IS 'Aggregated per-dimension rating averages and counts, updated on every rating change';

-- ----------------------------------------------------------------------------
-- books.work_shelf_counts - Per-work bookshelf rollup
-- Source: services/books/app/services/work_shelf_counts.py
-- Rebuilt wholesale by the books service on a cron (WORK_SHELF_COUNTS_REFRESH_CRON,
-- default every 15 min) and once at startup while the table is still empty.
-- ----------------------------------------------------------------------------
-- Every list surface (author page, category page, series page, discovery, case
-- opening, every recommendation list) needs "how many app users shelved this
-- work". Computing that inline made each of those queries aggregate the whole
-- of user_data.bookshelves grouped by work_id, which cost seconds per request
-- once the shelf table grew. This holds the same numbers once.
--
-- Counts are per DISTINCT user and pooled across every language edition, so a
-- reader who shelved two translations counts once. The book detail page still
-- computes its counts live, which is where a reader looks for their own change
-- to appear immediately.
CREATE TABLE books.work_shelf_counts (
    work_id             VARCHAR(600) PRIMARY KEY,
    want_to_read_count  INT NOT NULL DEFAULT 0,
    reading_count       INT NOT NULL DEFAULT 0,
    read_count          INT NOT NULL DEFAULT 0,
    abandoned_count     INT NOT NULL DEFAULT 0,
    readers             INT NOT NULL DEFAULT 0,   -- distinct users, all statuses
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE books.work_shelf_counts IS 'Distinct app users per work per shelf status, pooled across every language edition. Rebuilt wholesale by the books service on a cron; never written incrementally, so a rebuild is always authoritative.';

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

    -- Wikidata enrichment (from Phase 2 of dump pipeline)
    wikidata_id VARCHAR(50),                      -- Wikidata entity ID (e.g., Q42)
    wikipedia_url VARCHAR(1000),                  -- English Wikipedia URL
    remote_ids JSONB NOT NULL DEFAULT '{}',       -- Third-party IDs (goodreads, librarything, etc.)
    alternate_names JSONB NOT NULL DEFAULT '[]',  -- Known aliases and alternate spellings

    view_count INT NOT NULL DEFAULT 0,
    last_viewed_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    open_library_id VARCHAR(100),
    enrichment_attempted_at TIMESTAMPTZ           -- See books.enrichment_attempted_at
);

-- Indexes for books.authors
-- (slug is covered by the authors_slug_key UNIQUE constraint above)
CREATE INDEX idx_authors_name ON books.authors(name);
CREATE INDEX idx_authors_view_count ON books.authors(view_count DESC);
CREATE INDEX idx_authors_open_library_id ON books.authors(open_library_id);
CREATE INDEX idx_authors_wikidata_id ON books.authors(wikidata_id);
CREATE INDEX idx_authors_updated_at ON books.authors(updated_at);  -- incremental ES sync

COMMENT ON TABLE books.authors IS 'Author catalog. Authors are language-agnostic (same author for all translations)';

-- ----------------------------------------------------------------------------
-- books.series - Book series (one row per series slug per language)
-- Source: services/books/app/models/series.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.series (
    series_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    slug VARCHAR(550) NOT NULL,
    language VARCHAR(10) NOT NULL,
    description TEXT,
    total_books INT,

    view_count INT NOT NULL DEFAULT 0,
    last_viewed_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    enrichment_attempted_at TIMESTAMPTZ           -- See books.enrichment_attempted_at
);

-- Indexes for books.series
-- Slug is shared across languages (copied from the source book's series_name,
-- not translated), so only (slug, language) is unique. consolidate_series only
-- creates a language row once enough qualifying books exist in that language,
-- so a lookup may have to fall back to another language's row for the same slug.
CREATE UNIQUE INDEX idx_series_slug_language ON books.series(slug, language);
CREATE INDEX idx_series_view_count ON books.series(view_count DESC);
CREATE INDEX idx_series_updated_at ON books.series(updated_at);    -- incremental ES sync

COMMENT ON TABLE books.series IS 'Book series, one row per (slug, language). Positions tracked via books.series_position';

-- Declared here rather than inline on books.books, which is defined first.
-- SET NULL rather than CASCADE: deleting a series unshelves its books, it does
-- not delete them.
ALTER TABLE books.books
    ADD CONSTRAINT books_series_id_fkey
    FOREIGN KEY (series_id) REFERENCES books.series(series_id) ON DELETE SET NULL;

-- ----------------------------------------------------------------------------
-- books.book_authors - Many-to-many relationship (books <-> authors)
-- Source: services/books/app/models/book_author.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.book_authors (
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
    author_id BIGINT NOT NULL REFERENCES books.authors(author_id) ON DELETE CASCADE,

    CONSTRAINT uq_book_author PRIMARY KEY (book_id, author_id)
);

-- The primary key already serves book_id lookups; this covers the other direction.
CREATE INDEX idx_book_authors_author_book ON books.book_authors(author_id, book_id);

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

COMMENT ON TABLE books.genres IS 'Genre taxonomy for book categorization';

-- ----------------------------------------------------------------------------
-- books.book_genres - Many-to-many relationship (books <-> genres)
-- Source: services/books/app/models/book_genre.py
-- ----------------------------------------------------------------------------
CREATE TABLE books.book_genres (
    book_id BIGINT NOT NULL REFERENCES books.books(book_id) ON DELETE CASCADE,
    genre_id BIGINT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,

    CONSTRAINT uq_book_genre PRIMARY KEY (book_id, genre_id)
);

-- The primary key already serves book_id lookups; this covers the other direction.
CREATE INDEX idx_book_genres_genre_book ON books.book_genres(genre_id, book_id);

COMMENT ON TABLE books.book_genres IS 'Many-to-many: books <-> genres. Books can have multiple genres';

-- ----------------------------------------------------------------------------
-- books.genre_co_occurrences - Precomputed genre co-occurrence graph
-- Source: services/books/app/models/genre_co_occurrence.py
-- Rebuilt weekly by genre_bubble_builder worker (ingestion service)
-- ----------------------------------------------------------------------------
CREATE TABLE books.genre_co_occurrences (
    genre_id_a          BIGINT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,
    genre_id_b          BIGINT NOT NULL REFERENCES books.genres(genre_id) ON DELETE CASCADE,
    co_occurrence_count INT    NOT NULL,           -- Number of works sharing both genres
    strength            REAL   NOT NULL,           -- Jaccard coefficient: |A∩B| / |A∪B|
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (genre_id_a, genre_id_b),
    CHECK (genre_id_a < genre_id_b)               -- Canonical ordering, no duplicate pairs
);

-- Lookups are "everything adjacent to genre X", which can match either column,
-- so both directions are indexed.
CREATE INDEX idx_gco_a_strength ON books.genre_co_occurrences (genre_id_a, strength DESC);
CREATE INDEX idx_gco_b_strength ON books.genre_co_occurrences (genre_id_b, strength DESC);

COMMENT ON TABLE books.genre_co_occurrences IS 'Precomputed genre co-occurrence pairs with Jaccard strength. Powers genre bubble UI and adjacent-genre recommendations. Rebuilt weekly via TRUNCATE + bulk INSERT. Counted per work, not per edition, so a heavily-translated work does not inflate a pair.';

-- ----------------------------------------------------------------------------
-- books.reading_log_staging / books.ratings_staging - Dump import staging
-- Source: services/ingestion/app/workers/dump/phases/
-- ----------------------------------------------------------------------------
-- Both OpenLibrary dump phases stream a multi-GB file for potentially hours.
-- Writing straight into books.books meant an interruption (restart, redeploy,
-- crash) left a mix of books updated from the new dump and books still holding
-- the previous one, with no way to tell which. These accumulate the new totals
-- somewhere inert and are swapped into books.books once in a single statement
-- after the whole file has been parsed, so an interrupted run leaves the
-- previous good data untouched instead of half-applied.
CREATE TABLE books.reading_log_staging (
    book_id                     BIGINT PRIMARY KEY,
    ol_want_to_read_count       INTEGER NOT NULL DEFAULT 0,
    ol_currently_reading_count  INTEGER NOT NULL DEFAULT 0,
    ol_already_read_count       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE books.ratings_staging (
    book_id          BIGINT PRIMARY KEY,
    ol_rating_count  INTEGER NOT NULL DEFAULT 0,
    ol_avg_rating    NUMERIC NOT NULL DEFAULT 0
);

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
    password_hash VARCHAR(255),                -- bcrypt with cost 12 (NULL for Google-only accounts)
    google_id VARCHAR(255) UNIQUE,             -- Google OAuth subject ID

    role VARCHAR(10) NOT NULL DEFAULT 'user', -- 'user' or 'admin'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    avatar_url VARCHAR(1000),
    bio TEXT,

    last_login TIMESTAMP,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Drives which edition a reader is shown and which language the personal
    -- recommendation lists are built in
    preferred_language VARCHAR(8) NOT NULL DEFAULT 'en',

    CONSTRAINT check_user_role CHECK (role IN ('user', 'admin'))
);

-- email, username and google_id are covered by their UNIQUE constraints.
CREATE INDEX idx_users_is_active ON auth.users(is_active);

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

-- token_hash is covered by its UNIQUE constraint (the refresh path looks up by
-- it on every token rotation). expires_at feeds purge_stale_refresh_tokens.
CREATE INDEX idx_refresh_tokens_user_id ON auth.refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires_at ON auth.refresh_tokens(expires_at);

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

    -- Set when the status first becomes 'reading' / 'read'. Preserved when a
    -- shelf entry is re-pointed at a sibling edition, so a reader who finished
    -- one translation and then shelves another keeps their reading history.
    started_at TIMESTAMP,
    finished_at TIMESTAMP,

    PRIMARY KEY (bookshelf_id, user_id),
    CONSTRAINT check_bookshelf_status CHECK (status IN ('want_to_read', 'reading', 'read', 'abandoned')),
    CONSTRAINT uq_bookshelves_user_book UNIQUE (user_id, book_id)
) PARTITION BY HASH (user_id);

CREATE TABLE user_data.bookshelves_p0 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE user_data.bookshelves_p1 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE user_data.bookshelves_p2 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE user_data.bookshelves_p3 PARTITION OF user_data.bookshelves FOR VALUES WITH (MODULUS 4, REMAINDER 3);

-- Indexes for user_data.bookshelves
-- Every query here should carry user_id so the planner can prune to one
-- partition; a predicate on bookshelf_id alone touches all four.
CREATE INDEX idx_bookshelves_user_status_date ON user_data.bookshelves(user_id, status, created_at DESC);
CREATE INDEX idx_bookshelves_user_status_updated ON user_data.bookshelves(user_id, status, updated_at DESC);
CREATE INDEX idx_bookshelves_user_updated_date ON user_data.bookshelves(user_id, updated_at DESC);
CREATE INDEX idx_bookshelves_user_fav ON user_data.bookshelves(user_id, created_at DESC) WHERE is_favorite = TRUE;
CREATE INDEX idx_bookshelves_user_finished ON user_data.bookshelves(user_id, finished_at DESC) WHERE finished_at IS NOT NULL;
CREATE INDEX idx_bookshelves_book_status ON user_data.bookshelves(book_id, status);
-- Lets the books.work_shelf_counts rebuild read shelf rows index-only
CREATE INDEX idx_bookshelves_book_status_user ON user_data.bookshelves(book_id, status, user_id);

COMMENT ON TABLE user_data.bookshelves IS 'User reading lists and status. Partitioned by user_id (4 HASH partitions). One row per (user, edition); shelving a second translation re-points the existing row rather than adding one.';

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
    CONSTRAINT check_overall_rating CHECK (overall_rating >= 0.5 AND overall_rating <= 5.0)
);

-- Indexes for user_data.ratings
CREATE INDEX idx_ratings_user_date ON user_data.ratings(user_id, created_at DESC);
CREATE INDEX idx_ratings_user_score ON user_data.ratings(user_id, overall_rating DESC);
CREATE INDEX idx_ratings_book_overall ON user_data.ratings(book_id, overall_rating DESC);
CREATE INDEX idx_ratings_book_user ON user_data.ratings(book_id, user_id);
CREATE INDEX idx_ratings_created ON user_data.ratings USING BRIN(created_at);

COMMENT ON TABLE user_data.ratings IS 'Multi-dimensional book ratings (9 dimensions). One row per (user, edition); rating a second translation re-points the existing row so a reader is not counted twice in a work''s pooled average.';
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

-- Indexes for user_data.comments. Every read path filters is_deleted = FALSE,
-- so these are partial rather than carrying is_deleted as a column.
CREATE INDEX idx_comments_book_date ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE;
CREATE INDEX idx_comments_book_no_spoiler ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE AND is_spoiler = FALSE;
CREATE INDEX idx_comments_user_date ON user_data.comments(user_id, created_at DESC) WHERE is_deleted = FALSE;
CREATE INDEX idx_comments_user_updated ON user_data.comments(user_id, updated_at DESC) WHERE is_deleted = FALSE;

COMMENT ON TABLE user_data.comments IS 'Public book reviews. One comment per user per book. Joined with ratings for display.';

-- NOTE: user_data.notes table has been REMOVED from scope (dropped in migration 003)

-- ----------------------------------------------------------------------------
-- user_data.user_stats - Denormalized per-user counters
-- Source: services/user_data/app/models/user_stats.py
-- ----------------------------------------------------------------------------
CREATE TABLE user_data.user_stats (
    user_id BIGINT PRIMARY KEY,

    want_to_read_count INT NOT NULL DEFAULT 0,
    reading_count INT NOT NULL DEFAULT 0,
    read_count INT NOT NULL DEFAULT 0,
    abandoned_count INT NOT NULL DEFAULT 0,
    favourites_count INT NOT NULL DEFAULT 0,
    ratings_count INT NOT NULL DEFAULT 0,
    comments_count INT NOT NULL DEFAULT 0,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE user_data.user_stats IS 'Denormalized per-user activity counters. Updated on every bookshelf/rating/comment change. One row per user, created on first user action.';

-- ============================================================================
-- RECOMMENDATION SCHEMA
-- ============================================================================

-- ----------------------------------------------------------------------------
-- recommendation.contextual_recs - Precomputed "related to X" sections
-- Source: services/recommendation/app/services/contextual_precompute.py
-- ----------------------------------------------------------------------------
-- The "more by this author / similar by genre / readers also enjoyed" sections
-- are too expensive to build per request, so a background job precomputes them
-- for every sufficiently-rated book, author and series and stores just the
-- ordered id list. The reading path hydrates those ids in one bulk query.
--
-- One row per popular EDITION, not per work: candidates are filtered to the
-- seed's own language, so a work's English and Polish editions get distinct,
-- language-correct sections instead of only English being fast-pathed.
CREATE TABLE recommendation.contextual_recs (
    entity_type  TEXT        NOT NULL,        -- 'book' | 'author' | 'series'
    entity_id    INTEGER     NOT NULL,
    section_key  TEXT        NOT NULL,        -- e.g. 'more_by_author', 'similar_by_genre'
    display_name TEXT        NOT NULL,
    similar_ids  INTEGER[]   NOT NULL,        -- ordered result ids
    title_params JSONB       NOT NULL DEFAULT '{}',  -- interpolation values for a localised title
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (entity_type, entity_id, section_key)
);

CREATE INDEX idx_contextual_recs_lookup ON recommendation.contextual_recs (entity_type, entity_id);

COMMENT ON TABLE recommendation.contextual_recs IS 'Precomputed contextual recommendation sections. Rebuilt by CONTEXTUAL_PRECOMPUTE_CRON; stale rows for deleted entities are purged in the same job.';

-- Non-personalized recommendation LISTS are not stored here: they are built by
-- a background job and cached in Redis with a 24h TTL.
-- Redis key format: rec:{category_key}:{language}  (e.g. rec:most_read:en)
--                   rec:{category_key}             for author lists
--                   rec:book:{id} / rec:author:{id} / rec:series:{id}

-- ============================================================================
-- SEARCH
-- ============================================================================
-- Full-text search via Elasticsearch (removed from PostgreSQL in migration 003)
-- ES indexes: works, authors, series (created and managed by books service on startup)
-- One document per WORK, not per edition: every translation's title is routed
-- to its own language-analyzed field and the remaining editions ride along as
-- an inert payload, so the reader's language decides at query time which one
-- gets rendered.
-- Periodic re-index via ES_REINDEX_CRON (default: '0 5,11,17,23 * * *')
-- Incremental: pulls rows with updated_at > last sync (see idx_books_updated_at)
-- Initial full index on first scheduled run (no es:last_sync_ts in Redis)

-- ============================================================================
-- TRIGGERS - Automated field updates
-- ============================================================================

-- Each schema owns its own updated_at function; the bodies are identical.
CREATE OR REPLACE FUNCTION user_data.update_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION books.update_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION auth.update_updated_at() RETURNS trigger AS $$
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

CREATE TRIGGER trig_users_updated_at BEFORE UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION auth.update_updated_at();

-- books.* guard on `old.* IS DISTINCT FROM new.*` so that a no-op write does not
-- bump updated_at — the incremental ES sync keys off that column, and a
-- rewrite-everything import would otherwise queue the whole catalog for reindex.
CREATE TRIGGER trig_books_updated_at BEFORE UPDATE ON books.books
    FOR EACH ROW WHEN (old.* IS DISTINCT FROM new.*) EXECUTE FUNCTION books.update_updated_at();

CREATE TRIGGER trig_authors_updated_at BEFORE UPDATE ON books.authors
    FOR EACH ROW WHEN (old.* IS DISTINCT FROM new.*) EXECUTE FUNCTION books.update_updated_at();

CREATE TRIGGER trig_series_updated_at BEFORE UPDATE ON books.series
    FOR EACH ROW WHEN (old.* IS DISTINCT FROM new.*) EXECUTE FUNCTION books.update_updated_at();

-- NOTE: user_data.user_stats has no updated_at trigger. Its counters are
-- rewritten wholesale by INSERT ... ON CONFLICT DO UPDATE, which sets the
-- column explicitly.

-- ============================================================================
-- PERFORMANCE NOTES
-- ============================================================================

-- Partitioning:
-- - user_data.bookshelves: HASH partition by user_id (4 partitions, active).
--   Always include user_id in the predicate so only one partition is scanned.

-- Derived tables (never write to these by hand; a rebuild is authoritative):
-- - books.work_shelf_counts  - per-work shelf counts, books service cron (15 min)
-- - books.genre_co_occurrences - genre graph, ingestion weekly job
-- - recommendation.contextual_recs - related-entity sections, recommendation cron

-- Index policy:
-- - Do not add a single-column index whose column is already the leading column
--   of a composite index; the composite serves both. Migration 025 dropped 13
--   such indexes that had accumulated this way, including one (genre_id, book_id)
--   index created twice under different names.
-- - Prefer partial indexes where every read path shares a filter
--   (e.g. comments' is_deleted = FALSE).

-- Index Maintenance:
-- - REINDEX monthly for heavily updated indexes
-- - VACUUM ANALYZE after bulk imports
-- - Monitor index bloat with pg_stat_user_indexes
-- - Check for unused indexes with pg_stat_user_indexes.idx_scan = 0

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
