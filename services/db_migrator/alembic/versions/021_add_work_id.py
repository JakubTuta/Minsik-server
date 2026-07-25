"""add work_id to books.books for cross-language work identity

books.books stores one row per (work, language) — every translation is a
separate row. Business logic across search, recommendations, and rating
aggregation needs a stable key to group those translations back into one
"work" (dedup, pooled ratings, pooled reader counts). That key was being
improvised from slug, which is slugify(localized_title) and only matches
when translations happen to share a title.

A correct identity already existed — external_ids->>'work_ol_id', or for
rows ingested straight from the OpenLibrary works dump, open_library_id
itself (see migration 004) — but was never used for grouping. This promotes
it to a real indexed column, falling back to slug only for books with
neither (manually created / non-dump entries).

Ratings were previously pooled by slug (rating_service._update_book_stats),
which only ever grouped same-titled editions. Once work_id exists, this
migration immediately recomputes avg_rating/rating_count/rating_distribution/
sub_rating_stats grouped by work_id, so existing rating data is correct
under the new grouping the moment this migration runs — no separate backfill
script or manual step required.

Revision ID: 021
Revises: 020
Create Date: 2026-07-25
"""

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None

_REPOOL_RATING_STATS_SQL = """
    WITH stats AS (
        SELECT
            b.work_id,
            ROUND(AVG(r.overall_rating)::NUMERIC, 2)     AS avg_overall,
            COUNT(*)                                      AS total_count,
            ROUND(AVG(r.pacing)::NUMERIC, 2)             AS avg_pacing,
            COUNT(r.pacing)                               AS pacing_count,
            ROUND(AVG(r.emotional_impact)::NUMERIC, 2)   AS avg_emotional_impact,
            COUNT(r.emotional_impact)                     AS emotional_impact_count,
            ROUND(AVG(r.intellectual_depth)::NUMERIC, 2) AS avg_intellectual_depth,
            COUNT(r.intellectual_depth)                   AS intellectual_depth_count,
            ROUND(AVG(r.writing_quality)::NUMERIC, 2)    AS avg_writing_quality,
            COUNT(r.writing_quality)                      AS writing_quality_count,
            ROUND(AVG(r.rereadability)::NUMERIC, 2)      AS avg_rereadability,
            COUNT(r.rereadability)                        AS rereadability_count,
            ROUND(AVG(r.readability)::NUMERIC, 2)        AS avg_readability,
            COUNT(r.readability)                          AS readability_count,
            ROUND(AVG(r.plot_complexity)::NUMERIC, 2)    AS avg_plot_complexity,
            COUNT(r.plot_complexity)                      AS plot_complexity_count,
            ROUND(AVG(r.humor)::NUMERIC, 2)              AS avg_humor,
            COUNT(r.humor)                                AS humor_count
        FROM books.books b
        JOIN user_data.ratings r ON r.book_id = b.book_id
        GROUP BY b.work_id
    ),
    dist AS (
        SELECT work_id, jsonb_object_agg(overall_rating::text, cnt) AS distribution
        FROM (
            SELECT b.work_id, r.overall_rating, COUNT(*) AS cnt
            FROM books.books b
            JOIN user_data.ratings r ON r.book_id = b.book_id
            GROUP BY b.work_id, r.overall_rating
        ) t
        GROUP BY work_id
    )
    UPDATE books.books b
    SET
        avg_rating          = stats.avg_overall,
        rating_count         = stats.total_count,
        rating_distribution  = COALESCE(dist.distribution, '{}'),
        sub_rating_stats = (
            SELECT jsonb_object_agg(key, value)
            FROM (VALUES
                ('pacing',             jsonb_build_object('avg', COALESCE(stats.avg_pacing, 0)::text,             'count', stats.pacing_count)),
                ('emotional_impact',   jsonb_build_object('avg', COALESCE(stats.avg_emotional_impact, 0)::text,   'count', stats.emotional_impact_count)),
                ('intellectual_depth', jsonb_build_object('avg', COALESCE(stats.avg_intellectual_depth, 0)::text, 'count', stats.intellectual_depth_count)),
                ('writing_quality',    jsonb_build_object('avg', COALESCE(stats.avg_writing_quality, 0)::text,    'count', stats.writing_quality_count)),
                ('rereadability',      jsonb_build_object('avg', COALESCE(stats.avg_rereadability, 0)::text,      'count', stats.rereadability_count)),
                ('readability',        jsonb_build_object('avg', COALESCE(stats.avg_readability, 0)::text,        'count', stats.readability_count)),
                ('plot_complexity',    jsonb_build_object('avg', COALESCE(stats.avg_plot_complexity, 0)::text,    'count', stats.plot_complexity_count)),
                ('humor',              jsonb_build_object('avg', COALESCE(stats.avg_humor, 0)::text,              'count', stats.humor_count))
            ) AS t(key, value)
        )
    FROM stats
    LEFT JOIN dist ON dist.work_id = stats.work_id
    WHERE b.work_id = stats.work_id
"""


def upgrade() -> None:
    # VARCHAR(600) to match books.slug's width — the fallback value when no
    # external_ids->>'work_ol_id' / open_library_id exists is the slug itself,
    # and a VARCHAR(150) cap truncation-errored on slugs longer than that.
    op.execute("ALTER TABLE books.books ADD COLUMN IF NOT EXISTS work_id VARCHAR(600)")

    op.execute(
        "UPDATE books.books SET work_id = "
        "COALESCE(external_ids->>'work_ol_id', open_library_id, slug) "
        "WHERE work_id IS NULL"
    )

    op.execute("ALTER TABLE books.books ALTER COLUMN work_id SET NOT NULL")

    op.execute("CREATE INDEX IF NOT EXISTS idx_books_work_id ON books.books(work_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_work_lang ON books.books(work_id, language)"
    )

    op.execute(_REPOOL_RATING_STATS_SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS books.idx_books_work_lang")
    op.execute("DROP INDEX IF EXISTS books.idx_books_work_id")
    op.execute("ALTER TABLE books.books DROP COLUMN IF EXISTS work_id")
