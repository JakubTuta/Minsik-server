"""one row per (work, language), per-language text, and the tables the re-import needs

Until now nothing stopped two rows of the same work from sharing a language, the
OpenLibrary import labelled every work `en`, and a new language row was created
by copying the English row's title, slug and description. A Polish page showed
the English blurb; two editions of one work could split a reader's ratings.

This migration

* merges existing (work_id, language) duplicates into the lowest book_id. User
  shelves, ratings and comments move with them; when a reader has a row on both
  duplicates the most recently updated one wins. Every move is written to
  books.merge_log, the old slugs to books.slug_history so old URLs keep resolving,
  and the pooled rating stats of each affected work are recomputed;
* merges authors that share an OpenLibrary id the same way;
* clears descriptions that are byte-for-byte copies of the same work's English
  description. The text is not lost (it lives on the English row) and the page
  shows it labelled as English instead of passing it off as the reader's language;
* adds UNIQUE (work_id, language) and a unique OpenLibrary id on authors;
* adds edition_source / manually_edited_fields so a re-import knows what it may
  overwrite, author_localizations for per-language names and bios, series.group_id
  to link the per-language rows of one series, and the staging and snapshot
  tables used by the dump import.

Revision ID: 027
Revises: 026
Create Date: 2026-10-10
"""

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


_REPOOL_RATINGS_SQL = """
WITH canonical AS (
    SELECT work_id FROM _merged_works
),
work_ratings AS (
    SELECT b.work_id, r.*
    FROM books.books b
    JOIN canonical c ON c.work_id = b.work_id
    JOIN user_data.ratings r ON r.book_id = b.book_id
),
stats AS (
    SELECT
        work_id,
        ROUND(AVG(overall_rating)::NUMERIC, 2)     AS avg_overall,
        COUNT(*)                                    AS total_count,
        ROUND(AVG(pacing)::NUMERIC, 2)             AS avg_pacing,
        COUNT(pacing)                               AS pacing_count,
        ROUND(AVG(emotional_impact)::NUMERIC, 2)   AS avg_emotional_impact,
        COUNT(emotional_impact)                     AS emotional_impact_count,
        ROUND(AVG(intellectual_depth)::NUMERIC, 2) AS avg_intellectual_depth,
        COUNT(intellectual_depth)                   AS intellectual_depth_count,
        ROUND(AVG(writing_quality)::NUMERIC, 2)    AS avg_writing_quality,
        COUNT(writing_quality)                      AS writing_quality_count,
        ROUND(AVG(rereadability)::NUMERIC, 2)      AS avg_rereadability,
        COUNT(rereadability)                        AS rereadability_count,
        ROUND(AVG(readability)::NUMERIC, 2)        AS avg_readability,
        COUNT(readability)                          AS readability_count,
        ROUND(AVG(plot_complexity)::NUMERIC, 2)    AS avg_plot_complexity,
        COUNT(plot_complexity)                      AS plot_complexity_count,
        ROUND(AVG(humor)::NUMERIC, 2)              AS avg_humor,
        COUNT(humor)                                AS humor_count
    FROM work_ratings
    GROUP BY work_id
),
dist AS (
    SELECT work_id, jsonb_object_agg(overall_rating::text, cnt) AS distribution
    FROM (
        SELECT work_id, overall_rating, COUNT(*) AS cnt
        FROM work_ratings
        GROUP BY work_id, overall_rating
    ) t
    GROUP BY work_id
)
UPDATE books.books
SET
    avg_rating          = stats.avg_overall,
    rating_count        = COALESCE(stats.total_count, 0),
    rating_distribution = COALESCE(dist.distribution, '{}'::jsonb),
    sub_rating_stats = (
        SELECT jsonb_object_agg(key, value)
        FROM (VALUES
            ('pacing',             jsonb_build_object('avg', COALESCE(stats.avg_pacing, 0)::text,             'count', COALESCE(stats.pacing_count, 0))),
            ('emotional_impact',   jsonb_build_object('avg', COALESCE(stats.avg_emotional_impact, 0)::text,   'count', COALESCE(stats.emotional_impact_count, 0))),
            ('intellectual_depth', jsonb_build_object('avg', COALESCE(stats.avg_intellectual_depth, 0)::text, 'count', COALESCE(stats.intellectual_depth_count, 0))),
            ('writing_quality',    jsonb_build_object('avg', COALESCE(stats.avg_writing_quality, 0)::text,    'count', COALESCE(stats.writing_quality_count, 0))),
            ('rereadability',      jsonb_build_object('avg', COALESCE(stats.avg_rereadability, 0)::text,      'count', COALESCE(stats.rereadability_count, 0))),
            ('readability',        jsonb_build_object('avg', COALESCE(stats.avg_readability, 0)::text,        'count', COALESCE(stats.readability_count, 0))),
            ('plot_complexity',    jsonb_build_object('avg', COALESCE(stats.avg_plot_complexity, 0)::text,    'count', COALESCE(stats.plot_complexity_count, 0))),
            ('humor',              jsonb_build_object('avg', COALESCE(stats.avg_humor, 0)::text,              'count', COALESCE(stats.humor_count, 0)))
        ) AS t(key, value)
    )
FROM canonical
LEFT JOIN stats ON stats.work_id = canonical.work_id
LEFT JOIN dist ON dist.work_id = canonical.work_id
WHERE books.books.work_id = canonical.work_id
"""

# (table, primary-key column, updated_at column) of the user tables that carry a
# book_id and a (user_id, book_id) uniqueness constraint.
_USER_TABLES = [
    ("user_data.bookshelves", "bookshelf_id", "bookshelf"),
    ("user_data.ratings", "rating_id", "rating"),
    ("user_data.comments", "comment_id", "comment"),
]


def _create_support_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.merge_log (
            log_id     BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            entity     VARCHAR(20) NOT NULL,
            action     VARCHAR(40) NOT NULL,
            old_id     BIGINT,
            new_id     BIGINT,
            user_id    BIGINT,
            detail     JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.slug_history (
            entity_type VARCHAR(10) NOT NULL,
            language    VARCHAR(10) NOT NULL DEFAULT '',
            old_slug    VARCHAR(600) NOT NULL,
            entity_id   BIGINT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (entity_type, language, old_slug)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_slug_history_entity "
        "ON books.slug_history(entity_type, entity_id)"
    )


def _merge_duplicate_authors() -> None:
    op.execute("DROP TABLE IF EXISTS _author_dup")
    op.execute(
        """
        CREATE TEMP TABLE _author_dup AS
        SELECT a.author_id AS old_id, k.keep_id, a.slug AS old_slug
        FROM books.authors a
        JOIN (
            SELECT open_library_id, MIN(author_id) AS keep_id
            FROM books.authors
            WHERE open_library_id IS NOT NULL
            GROUP BY open_library_id
            HAVING COUNT(*) > 1
        ) k ON k.open_library_id = a.open_library_id
        WHERE a.author_id <> k.keep_id
        """
    )
    op.execute(
        """
        INSERT INTO books.book_authors (book_id, author_id)
        SELECT ba.book_id, d.keep_id
        FROM books.book_authors ba
        JOIN _author_dup d ON d.old_id = ba.author_id
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO books.slug_history (entity_type, language, old_slug, entity_id)
        SELECT 'author', '', old_slug, keep_id FROM _author_dup
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO books.merge_log (entity, action, old_id, new_id)
        SELECT 'author', 'merged_same_openlibrary_id', old_id, keep_id FROM _author_dup
        """
    )
    op.execute("DELETE FROM books.authors WHERE author_id IN (SELECT old_id FROM _author_dup)")
    op.execute("DROP TABLE _author_dup")


def _merge_user_rows(table: str, pk: str, entity: str) -> None:
    # Where a reader has a row on the duplicate and on the keeper (or on two
    # duplicates), the most recently updated one survives.
    op.execute(
        f"""
        WITH ranked AS (
            SELECT x.{pk} AS pk, x.user_id, x.book_id AS old_book,
                   COALESCE(m.keep_id, x.book_id) AS target,
                   ROW_NUMBER() OVER (
                       PARTITION BY x.user_id, COALESCE(m.keep_id, x.book_id)
                       ORDER BY x.updated_at DESC, x.{pk} DESC
                   ) AS rn
            FROM {table} x
            LEFT JOIN _dup_map m ON m.old_id = x.book_id
            WHERE x.book_id IN (SELECT old_id FROM _dup_map)
               OR x.book_id IN (SELECT keep_id FROM _dup_map)
        ),
        dropped AS (
            DELETE FROM {table} t
            USING ranked r
            WHERE t.{pk} = r.pk AND t.user_id = r.user_id AND r.rn > 1
            RETURNING r.user_id, r.old_book, r.target
        )
        INSERT INTO books.merge_log (entity, action, old_id, new_id, user_id)
        SELECT '{entity}', 'dropped_older_duplicate', old_book, target, user_id FROM dropped
        """
    )
    op.execute(
        f"""
        WITH moved AS (
            UPDATE {table} t
            SET book_id = m.keep_id
            FROM _dup_map m
            WHERE t.book_id = m.old_id
            RETURNING t.user_id, m.old_id, m.keep_id
        )
        INSERT INTO books.merge_log (entity, action, old_id, new_id, user_id)
        SELECT '{entity}', 'moved_to_kept_edition', old_id, keep_id, user_id FROM moved
        """
    )


def _recount_user_stats() -> None:
    op.execute(
        """
        INSERT INTO user_data.user_stats
            (user_id, want_to_read_count, reading_count, read_count, abandoned_count,
             favourites_count, ratings_count, comments_count)
        SELECT u.user_id,
               COUNT(*) FILTER (WHERE s.status = 'want_to_read'),
               COUNT(*) FILTER (WHERE s.status = 'reading'),
               COUNT(*) FILTER (WHERE s.status = 'read'),
               COUNT(*) FILTER (WHERE s.status = 'abandoned'),
               COUNT(*) FILTER (WHERE s.is_favorite),
               (SELECT COUNT(*) FROM user_data.ratings r WHERE r.user_id = u.user_id),
               (SELECT COUNT(*) FROM user_data.comments c WHERE c.user_id = u.user_id)
        FROM (SELECT DISTINCT user_id FROM books.merge_log
              WHERE user_id IS NOT NULL AND action IN ('dropped_older_duplicate', 'moved_to_kept_edition')
                AND created_at >= NOW() - INTERVAL '1 hour') u
        LEFT JOIN user_data.bookshelves s ON s.user_id = u.user_id
        GROUP BY u.user_id
        ON CONFLICT (user_id) DO UPDATE SET
            want_to_read_count = EXCLUDED.want_to_read_count,
            reading_count      = EXCLUDED.reading_count,
            read_count         = EXCLUDED.read_count,
            abandoned_count    = EXCLUDED.abandoned_count,
            favourites_count   = EXCLUDED.favourites_count,
            ratings_count      = EXCLUDED.ratings_count,
            comments_count     = EXCLUDED.comments_count
        """
    )


def _merge_duplicate_editions() -> None:
    op.execute("DROP TABLE IF EXISTS _dup_map")
    op.execute("DROP TABLE IF EXISTS _merged_works")
    op.execute(
        """
        CREATE TEMP TABLE _dup_map AS
        SELECT b.book_id AS old_id, k.keep_id, b.language, b.slug AS old_slug, b.work_id
        FROM books.books b
        JOIN (
            SELECT work_id, language, MIN(book_id) AS keep_id
            FROM books.books
            GROUP BY work_id, language
            HAVING COUNT(*) > 1
        ) k ON k.work_id = b.work_id AND k.language = b.language
        WHERE b.book_id <> k.keep_id
        """
    )
    op.execute("CREATE TEMP TABLE _merged_works AS SELECT DISTINCT work_id FROM _dup_map")

    for table, pk, entity in _USER_TABLES:
        _merge_user_rows(table, pk, entity)

    op.execute(
        """
        INSERT INTO books.book_authors (book_id, author_id)
        SELECT m.keep_id, ba.author_id
        FROM books.book_authors ba
        JOIN _dup_map m ON m.old_id = ba.book_id
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO books.book_genres (book_id, genre_id)
        SELECT m.keep_id, bg.genre_id
        FROM books.book_genres bg
        JOIN _dup_map m ON m.old_id = bg.book_id
        ON CONFLICT DO NOTHING
        """
    )
    # The kept row inherits what the duplicates knew that it did not.
    op.execute(
        """
        UPDATE books.books k
        SET view_count = k.view_count + o.views,
            ol_want_to_read_count = GREATEST(k.ol_want_to_read_count, o.want),
            ol_currently_reading_count = GREATEST(k.ol_currently_reading_count, o.reading),
            ol_already_read_count = GREATEST(k.ol_already_read_count, o.already),
            ol_rating_count = GREATEST(k.ol_rating_count, o.ol_ratings),
            description = COALESCE(NULLIF(btrim(k.description), ''), o.description),
            first_sentence = COALESCE(NULLIF(btrim(k.first_sentence), ''), o.first_sentence),
            primary_cover_url = COALESCE(k.primary_cover_url, o.cover),
            publisher = COALESCE(k.publisher, o.publisher),
            number_of_pages = COALESCE(k.number_of_pages, o.pages),
            series_id = COALESCE(k.series_id, o.series_id),
            series_position = COALESCE(k.series_position, o.series_position),
            series_slug = COALESCE(k.series_slug, o.series_slug),
            series_name = COALESCE(k.series_name, o.series_name)
        FROM (
            SELECT m.keep_id,
                   SUM(d.view_count) AS views,
                   MAX(d.ol_want_to_read_count) AS want,
                   MAX(d.ol_currently_reading_count) AS reading,
                   MAX(d.ol_already_read_count) AS already,
                   MAX(d.ol_rating_count) AS ol_ratings,
                   (ARRAY_AGG(NULLIF(btrim(d.description), '') ORDER BY d.book_id)
                       FILTER (WHERE NULLIF(btrim(d.description), '') IS NOT NULL))[1] AS description,
                   (ARRAY_AGG(NULLIF(btrim(d.first_sentence), '') ORDER BY d.book_id)
                       FILTER (WHERE NULLIF(btrim(d.first_sentence), '') IS NOT NULL))[1] AS first_sentence,
                   (ARRAY_AGG(d.primary_cover_url ORDER BY d.book_id)
                       FILTER (WHERE d.primary_cover_url IS NOT NULL))[1] AS cover,
                   (ARRAY_AGG(d.publisher ORDER BY d.book_id) FILTER (WHERE d.publisher IS NOT NULL))[1] AS publisher,
                   (ARRAY_AGG(d.number_of_pages ORDER BY d.book_id)
                       FILTER (WHERE d.number_of_pages IS NOT NULL))[1] AS pages,
                   (ARRAY_AGG(d.series_id ORDER BY d.book_id) FILTER (WHERE d.series_id IS NOT NULL))[1] AS series_id,
                   (ARRAY_AGG(d.series_position ORDER BY d.book_id)
                       FILTER (WHERE d.series_id IS NOT NULL))[1] AS series_position,
                   (ARRAY_AGG(d.series_slug ORDER BY d.book_id) FILTER (WHERE d.series_id IS NOT NULL))[1] AS series_slug,
                   (ARRAY_AGG(d.series_name ORDER BY d.book_id) FILTER (WHERE d.series_id IS NOT NULL))[1] AS series_name
            FROM _dup_map m
            JOIN books.books d ON d.book_id = m.old_id
            GROUP BY m.keep_id
        ) o
        WHERE k.book_id = o.keep_id
        """
    )
    op.execute(
        """
        INSERT INTO books.slug_history (entity_type, language, old_slug, entity_id)
        SELECT 'book', language, old_slug, keep_id FROM _dup_map
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO books.merge_log (entity, action, old_id, new_id)
        SELECT 'book', 'merged_same_work_and_language', old_id, keep_id FROM _dup_map
        """
    )
    op.execute("DELETE FROM books.books WHERE book_id IN (SELECT old_id FROM _dup_map)")
    op.execute(_REPOOL_RATINGS_SQL)
    _recount_user_stats()
    op.execute("DROP TABLE _merged_works")
    op.execute("DROP TABLE _dup_map")


def _clear_copied_descriptions() -> None:
    op.execute(
        """
        WITH cleared AS (
            UPDATE books.books b
            SET description = NULL, enrichment_attempted_at = NULL
            FROM books.books e
            WHERE e.work_id = b.work_id
              AND e.language = 'en'
              AND b.language <> 'en'
              AND b.description IS NOT NULL
              AND b.description = e.description
            RETURNING b.book_id, e.book_id AS english_book_id
        )
        INSERT INTO books.merge_log (entity, action, old_id, new_id)
        SELECT 'book', 'cleared_copied_description', book_id, english_book_id FROM cleared
        """
    )


def _add_columns_tables_and_indexes() -> None:
    op.execute(
        "ALTER TABLE books.books "
        "ADD COLUMN IF NOT EXISTS edition_source VARCHAR(10) NOT NULL DEFAULT 'legacy', "
        "ADD COLUMN IF NOT EXISTS manually_edited_fields TEXT[] NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE books.books ADD CONSTRAINT check_books_edition_source "
        "CHECK (edition_source IN ('legacy', 'edition', 'work', 'manual'))"
    )
    op.execute(
        "ALTER TABLE books.authors "
        "ADD COLUMN IF NOT EXISTS manually_edited_fields TEXT[] NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE books.series "
        "ADD COLUMN IF NOT EXISTS manually_edited_fields TEXT[] NOT NULL DEFAULT '{}', "
        "ADD COLUMN IF NOT EXISTS group_id BIGINT"
    )
    # Rows that share a slug are the same series in different languages. Nullable:
    # a row the importer has not grouped yet is its own group.
    op.execute(
        "UPDATE books.series s SET group_id = g.group_id "
        "FROM (SELECT slug, MIN(series_id) AS group_id FROM books.series GROUP BY slug) g "
        "WHERE g.slug = s.slug AND s.group_id IS NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_series_group_id ON books.series(group_id)")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_books_work_language "
        "ON books.books(work_id, language)"
    )
    # (work_id, language) is now the unique index's own key.
    op.execute("DROP INDEX IF EXISTS books.idx_books_work_lang")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_authors_open_library_id "
        "ON books.authors(open_library_id) WHERE open_library_id IS NOT NULL"
    )
    op.execute("DROP INDEX IF EXISTS books.idx_authors_open_library_id")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.author_localizations (
            author_id     BIGINT NOT NULL REFERENCES books.authors(author_id) ON DELETE CASCADE,
            language      VARCHAR(10) NOT NULL,
            name          VARCHAR(300),
            bio           TEXT,
            wikipedia_url VARCHAR(1000),
            source        VARCHAR(20) NOT NULL DEFAULT 'wikidata',
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (author_id, language)
        )
        """
    )

    # Import staging. Unlogged: rebuilt by every run, so crash safety buys nothing.
    op.execute(
        """
        CREATE UNLOGGED TABLE IF NOT EXISTS books.work_staging (
            work_ol_id           VARCHAR(100) PRIMARY KEY,
            title                VARCHAR(500) NOT NULL,
            title_language       VARCHAR(10),
            description          TEXT,
            description_language VARCHAR(10),
            first_sentence       TEXT,
            first_publish_year   INTEGER,
            cover_url            VARCHAR(1000),
            author_ol_ids        JSONB NOT NULL DEFAULT '[]'::jsonb,
            genres               JSONB NOT NULL DEFAULT '[]'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE UNLOGGED TABLE IF NOT EXISTS books.edition_staging (
            work_ol_id VARCHAR(100) NOT NULL,
            language   VARCHAR(10) NOT NULL,
            score      INTEGER NOT NULL,
            payload    JSONB NOT NULL,
            PRIMARY KEY (work_ol_id, language)
        )
        """
    )

    # Taken before a re-import and compared after: no row a reader points at may vanish.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.reimport_anchor (
            book_id  BIGINT PRIMARY KEY,
            work_id  VARCHAR(600) NOT NULL,
            language VARCHAR(10) NOT NULL,
            slug     VARCHAR(600) NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.reimport_user_counts (
            user_id BIGINT PRIMARY KEY,
            shelves INTEGER NOT NULL,
            ratings INTEGER NOT NULL,
            comments INTEGER NOT NULL,
            shelf_works INTEGER NOT NULL
        )
        """
    )


def upgrade() -> None:
    _create_support_tables()
    _merge_duplicate_authors()
    _merge_duplicate_editions()
    _clear_copied_descriptions()
    _add_columns_tables_and_indexes()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS books.reimport_user_counts")
    op.execute("DROP TABLE IF EXISTS books.reimport_anchor")
    op.execute("DROP TABLE IF EXISTS books.edition_staging")
    op.execute("DROP TABLE IF EXISTS books.work_staging")
    op.execute("DROP TABLE IF EXISTS books.author_localizations")
    op.execute("CREATE INDEX IF NOT EXISTS idx_authors_open_library_id ON books.authors(open_library_id)")
    op.execute("DROP INDEX IF EXISTS books.uq_authors_open_library_id")
    op.execute("CREATE INDEX IF NOT EXISTS idx_books_work_lang ON books.books(work_id, language)")
    op.execute("DROP INDEX IF EXISTS books.uq_books_work_language")
    op.execute("DROP INDEX IF EXISTS books.idx_series_group_id")
    op.execute(
        "ALTER TABLE books.series DROP COLUMN IF EXISTS group_id, "
        "DROP COLUMN IF EXISTS manually_edited_fields"
    )
    op.execute("ALTER TABLE books.authors DROP COLUMN IF EXISTS manually_edited_fields")
    op.execute("ALTER TABLE books.books DROP CONSTRAINT IF EXISTS check_books_edition_source")
    op.execute(
        "ALTER TABLE books.books DROP COLUMN IF EXISTS manually_edited_fields, "
        "DROP COLUMN IF EXISTS edition_source"
    )
    # Merged rows and cleared descriptions are not restored; books.merge_log and
    # books.slug_history are kept as the record of what was done.
