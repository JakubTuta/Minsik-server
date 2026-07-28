"""work-level bookshelf rollup, index cleanup, and missing indexes

Ten query sites (author page, category page, series page, discovery, case
opening, ES series sync, every recommendation list) each aggregated the whole
of user_data.bookshelves joined to the whole of books.books, grouped by
work_id, only to look up a handful of works. On 3.5M shelf rows an author's
book list spent 5.5s and a category page 9.8s doing that, almost all of it in
a 136MB on-disk sort that the outer LIMIT then threw away.

books.work_shelf_counts holds the same aggregate once, refreshed on a cron by
the books service. The full rebuild costs ~5s, which is cheaper than a single
one of the queries it replaces.

The dropped indexes are exact duplicates or leading-column prefixes of other
indexes; migrations 006 and 015 independently created the same
(genre_id, book_id) index under two names. They cost ~194MB at 400k books and
slow down every write to the tables they sit on.

Revision ID: 025
Revises: 024
Create Date: 2026-07-28
"""

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


# Qualified index name -> the statement that recreates it, for downgrade. Each
# is fully served by another index that already exists, so dropping it changes
# no plan.
_REDUNDANT_INDEXES = [
    # exact duplicate of idx_book_genres_genre_book (mig 006 vs mig 015)
    (
        "books.idx_book_genres_genre_id_book_id",
        "CREATE INDEX idx_book_genres_genre_id_book_id "
        "ON books.book_genres(genre_id, book_id)",
    ),
    # leading-column prefix of idx_book_genres_genre_book
    (
        "books.idx_book_genres_genre_id",
        "CREATE INDEX idx_book_genres_genre_id ON books.book_genres(genre_id)",
    ),
    # leading-column prefix of idx_book_authors_author_book
    (
        "books.idx_book_authors_author_id",
        "CREATE INDEX idx_book_authors_author_id ON books.book_authors(author_id)",
    ),
    # duplicate of the authors_slug_key unique constraint
    (
        "books.idx_authors_slug",
        "CREATE UNIQUE INDEX idx_authors_slug ON books.authors(slug)",
    ),
    # duplicate of the genres_slug_key unique constraint
    (
        "books.idx_genres_slug",
        "CREATE UNIQUE INDEX idx_genres_slug ON books.genres(slug)",
    ),
    # leading-column prefix of idx_books_language_slug
    (
        "books.idx_books_language",
        "CREATE INDEX idx_books_language ON books.books(language)",
    ),
    # leading-column prefix of idx_books_series_lang
    (
        "books.idx_books_series_id_partial",
        "CREATE INDEX idx_books_series_id_partial ON books.books(series_id) "
        "WHERE series_id IS NOT NULL",
    ),
    # no query filters on language alone within the covered rows
    (
        "books.idx_books_lang_cover",
        "CREATE INDEX idx_books_lang_cover ON books.books(language) "
        "WHERE primary_cover_url IS NOT NULL",
    ),
    # no query orders by (view_count, created_at); idx_authors_view_count serves
    # the ORDER BY view_count DESC that callers actually use
    (
        "books.idx_authors_view_count_created",
        "CREATE INDEX idx_authors_view_count_created "
        "ON books.authors(view_count, created_at)",
    ),
    # exact duplicate of idx_comments_book_date
    (
        "user_data.idx_comments_book_created",
        "CREATE INDEX idx_comments_book_created "
        "ON user_data.comments(book_id, created_at DESC) WHERE is_deleted = FALSE",
    ),
    # superseded by the is_deleted-partial idx_comments_book_date
    (
        "user_data.ix_comments_book_id_is_deleted_created_at",
        "CREATE INDEX ix_comments_book_id_is_deleted_created_at "
        "ON user_data.comments(book_id, is_deleted, created_at)",
    ),
    # leading-column prefix of idx_ratings_book_overall and idx_ratings_book_user
    (
        "user_data.idx_ratings_book_id",
        "CREATE INDEX idx_ratings_book_id ON user_data.ratings(book_id)",
    ),
    # partial duplicate of the users_google_id_key unique constraint
    (
        "auth.idx_users_google_id",
        "CREATE INDEX idx_users_google_id ON auth.users(google_id) "
        "WHERE google_id IS NOT NULL",
    ),
]


def upgrade() -> None:
    for qualified_name, _ in _REDUNDANT_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {qualified_name}")

    # es_sync_service pulls rows changed since the last sync every 6 hours and
    # was sequentially scanning the whole table to find them.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_updated_at ON books.books(updated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_authors_updated_at ON books.authors(updated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_series_updated_at ON books.series(updated_at)"
    )
    # list_builder's "Recently Added" orders the whole catalog by created_at.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_created_at ON books.books(created_at DESC)"
    )
    # Lets the work_shelf_counts rebuild read shelf rows index-only.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bookshelves_book_status_user "
        "ON user_data.bookshelves(book_id, status, user_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS books.work_shelf_counts (
            work_id             VARCHAR(600) PRIMARY KEY,
            want_to_read_count  INT NOT NULL DEFAULT 0,
            reading_count       INT NOT NULL DEFAULT 0,
            read_count          INT NOT NULL DEFAULT 0,
            abandoned_count     INT NOT NULL DEFAULT 0,
            readers             INT NOT NULL DEFAULT 0,
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE books.work_shelf_counts IS "
        "'Distinct app users per work per shelf status, pooled across every "
        "language edition. Rebuilt wholesale by the books service on a cron; "
        "never written incrementally, so a rebuild is always authoritative.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS books.work_shelf_counts")

    op.execute("DROP INDEX IF EXISTS user_data.idx_bookshelves_book_status_user")
    op.execute("DROP INDEX IF EXISTS books.idx_books_created_at")
    op.execute("DROP INDEX IF EXISTS books.idx_series_updated_at")
    op.execute("DROP INDEX IF EXISTS books.idx_authors_updated_at")
    op.execute("DROP INDEX IF EXISTS books.idx_books_updated_at")

    for _, create_statement in _REDUNDANT_INDEXES:
        op.execute(create_statement)
