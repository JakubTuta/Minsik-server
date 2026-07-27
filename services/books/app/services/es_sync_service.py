import asyncio
import datetime
import logging

import app.cache
import app.config
import app.db
import app.es_client
import app.services._language_boost
import app.services.es_reconcile_service
import elasticsearch.helpers
import sqlalchemy

logger = logging.getLogger(__name__)

ES_LAST_SYNC_KEY = "es:last_sync_ts"
ES_LAST_SYNC_KEY_AUTHORS = "es:last_sync_ts:authors"
ES_LAST_SYNC_KEY_SERIES = "es:last_sync_ts:series"
ES_REINDEX_RUNNING_KEY = "es_reindex_running"
ES_REINDEX_RUNNING_TTL = 86400
ES_BULK_THROTTLE_SECONDS = 0.5
ES_INDEXING_REFRESH_INTERVAL = "30s"
ES_BULK_CHUNK_SIZE = 100

BAYESIAN_PRIOR_MEAN = 3.0
BAYESIAN_MIN_RATINGS = 10


def _compute_bayesian_score(total_ratings: int, combined_avg: float) -> float:
    return (
        total_ratings * combined_avg + BAYESIAN_MIN_RATINGS * BAYESIAN_PRIOR_MEAN
    ) / (total_ratings + BAYESIAN_MIN_RATINGS)


async def _restore_index_refresh(index: str) -> None:
    try:
        await app.es_client.set_index_refresh(index, "1s")
        await app.es_client.refresh_index(index)
    except Exception as e:
        logger.error(f"[ES] Refresh restore failed for {index}: {str(e)}")


async def _bulk_index(es: object, docs: list) -> None:
    try:
        await elasticsearch.helpers.async_bulk(
            es.options(request_timeout=120),
            docs,
            chunk_size=ES_BULK_CHUNK_SIZE,
            max_retries=3,
            initial_backoff=2,
        )
        await asyncio.sleep(ES_BULK_THROTTLE_SECONDS)
    except Exception as e:
        logger.error(f"[ES] Bulk index error: {str(e)}")
        raise


async def reindex_all_to_es(full: bool = False) -> None:
    await app.cache.redis_client.set(ES_REINDEX_RUNNING_KEY, "1", ex=ES_REINDEX_RUNNING_TTL)
    es = app.es_client.get_es()
    settings = app.config.settings
    epoch = datetime.datetime(1970, 1, 1)

    index_changed = await app.es_client.create_indexes(
        settings.es_index_books,
        settings.es_index_authors,
        settings.es_index_series,
    )
    if index_changed and not full:
        logger.info("[ES] Index mapping changed, upgrading to a full reindex")
        full = True

    if full:
        last_sync_books = epoch
        last_sync_authors = epoch
        last_sync_series = epoch
        logger.info("[ES] Starting full reindex")
    else:
        raw_ts = await app.cache.redis_client.get(ES_LAST_SYNC_KEY)
        last_sync_books = (
            datetime.datetime.fromisoformat(raw_ts).replace(tzinfo=None)
            if raw_ts
            else epoch
        )
        raw_ts_authors = await app.cache.redis_client.get(ES_LAST_SYNC_KEY_AUTHORS)
        last_sync_authors = (
            datetime.datetime.fromisoformat(raw_ts_authors).replace(tzinfo=None)
            if raw_ts_authors
            else epoch
        )
        raw_ts_series = await app.cache.redis_client.get(ES_LAST_SYNC_KEY_SERIES)
        last_sync_series = (
            datetime.datetime.fromisoformat(raw_ts_series).replace(tzinfo=None)
            if raw_ts_series
            else epoch
        )
        logger.info(
            f"[ES] Starting incremental reindex. last_sync books={last_sync_books.isoformat()} "
            f"authors={last_sync_authors.isoformat()} series={last_sync_series.isoformat()}"
        )

    books_indexed = 0
    authors_indexed = 0
    series_indexed = 0

    now_ts = datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat()

    books_query = sqlalchemy.text(
        f"""
        SELECT
            b.book_id, b.title, b.language, b.slug, b.work_id,
            b.primary_cover_url,
            b.rating_count AS app_rating_count, b.avg_rating AS app_avg_rating,
            b.ol_rating_count, b.ol_avg_rating,
            {app.services._language_boost.work_readers_sql()} AS readers,
            ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) as authors_names,
            ARRAY_AGG(DISTINCT a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.name as series_name, s.slug as series_slug
        FROM books.books b
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE b.updated_at > :last_sync
        GROUP BY b.book_id, s.name, s.slug
        ORDER BY b.book_id
    """
    )

    try:
        await app.es_client.set_index_refresh(
            settings.es_index_books, ES_INDEXING_REFRESH_INTERVAL
        )
        try:
            async with app.db.async_session_maker() as session:
                result = await session.stream(
                    books_query, {"last_sync": last_sync_books}
                )
                batch: list = []

                async for row in result:
                    app_rating_count = row.app_rating_count or 0
                    ol_rating_count = row.ol_rating_count or 0
                    app_avg = (
                        float(row.app_avg_rating) if row.app_avg_rating else 0.0
                    )
                    ol_avg = float(row.ol_avg_rating) if row.ol_avg_rating else 0.0
                    total_ratings = app_rating_count + ol_rating_count
                    combined_avg = (
                        (app_avg * app_rating_count + ol_avg * ol_rating_count)
                        / total_ratings
                        if total_ratings > 0
                        else 0.0
                    )
                    doc = {
                        "_index": settings.es_index_books,
                        "_id": str(row.book_id),
                        "_source": {
                            "book_id": row.book_id,
                            "title": row.title or "",
                            "language": row.language or "",
                            "slug": row.slug or "",
                            "work_id": row.work_id or "",
                            "primary_cover_url": row.primary_cover_url or "",
                            "authors_names": list(row.authors_names or []),
                            "author_slugs": list(row.author_slugs or []),
                            "series_name": row.series_name or "",
                            "series_slug": row.series_slug or "",
                            "app_avg_rating": (
                                app_avg if app_rating_count > 0 else None
                            ),
                            "app_rating_count": app_rating_count,
                            "ol_avg_rating": (
                                ol_avg if ol_rating_count > 0 else None
                            ),
                            "ol_rating_count": ol_rating_count,
                            "readers": row.readers or 0,
                            "bayesian_score": _compute_bayesian_score(
                                total_ratings, combined_avg
                            ),
                        },
                    }
                    batch.append(doc)

                    if len(batch) >= settings.es_reindex_batch_size:
                        await _bulk_index(es, batch)
                        books_indexed += len(batch)
                        batch = []

                if batch:
                    await _bulk_index(es, batch)
                    books_indexed += len(batch)
        finally:
            await _restore_index_refresh(settings.es_index_books)

        await app.cache.redis_client.set(ES_LAST_SYNC_KEY, now_ts)
    except Exception as e:
        logger.error(f"[ES] Books reindex failed: {str(e)}")

    # One document per (author, language), but the aggregates behind it are
    # work-level and language-agnostic: counting every edition would multiply an
    # author's ratings and readers by how many translations they happen to have.
    authors_query = sqlalchemy.text(
        """
        WITH synced_authors AS (
            SELECT author_id FROM books.authors WHERE updated_at > :last_sync
        ),
        author_works AS (
            SELECT DISTINCT ON (ba.author_id, b.work_id)
                ba.author_id, b.rating_count, b.avg_rating,
                b.ol_rating_count, b.ol_avg_rating,
                b.ol_want_to_read_count, b.ol_currently_reading_count,
                b.ol_already_read_count
            FROM books.book_authors ba
            JOIN books.books b ON ba.book_id = b.book_id
            JOIN synced_authors sa ON sa.author_id = ba.author_id
            ORDER BY ba.author_id, b.work_id,
                     (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) DESC
        ),
        author_app_readers AS (
            SELECT ba.author_id, COUNT(DISTINCT bs.user_id) AS app_readers
            FROM user_data.bookshelves bs
            JOIN books.book_authors ba ON ba.book_id = bs.book_id
            JOIN synced_authors sa ON sa.author_id = ba.author_id
            GROUP BY ba.author_id
        ),
        author_stats AS (
            SELECT
                aw.author_id,
                COUNT(*) AS book_count,
                COALESCE(SUM(aw.rating_count), 0) AS app_rating_count,
                CASE WHEN SUM(aw.rating_count) > 0
                     THEN SUM(aw.avg_rating * aw.rating_count) / SUM(aw.rating_count)
                     ELSE NULL END AS app_avg_rating,
                COALESCE(SUM(aw.ol_rating_count), 0) AS ol_rating_count,
                CASE WHEN SUM(aw.ol_rating_count) > 0
                     THEN SUM(aw.ol_avg_rating * aw.ol_rating_count) / SUM(aw.ol_rating_count)
                     ELSE NULL END AS ol_avg_rating,
                COALESCE(SUM(
                    aw.ol_want_to_read_count + aw.ol_currently_reading_count
                    + aw.ol_already_read_count
                ), 0) AS ol_readers
            FROM author_works aw
            GROUP BY aw.author_id
        )
        SELECT DISTINCT
            a.author_id, a.name, a.slug, a.photo_url,
            b.language,
            ast.book_count,
            ast.app_rating_count,
            ast.app_avg_rating,
            ast.ol_rating_count,
            ast.ol_avg_rating,
            ast.ol_readers + COALESCE(aar.app_readers, 0) AS readers
        FROM books.authors a
        JOIN books.book_authors ba ON a.author_id = ba.author_id
        JOIN books.books b ON ba.book_id = b.book_id
        JOIN author_stats ast ON ast.author_id = a.author_id
        LEFT JOIN author_app_readers aar ON aar.author_id = a.author_id
        WHERE a.updated_at > :last_sync AND b.language IS NOT NULL
        ORDER BY a.author_id, b.language
    """
    )

    try:
        await app.es_client.set_index_refresh(
            settings.es_index_authors, ES_INDEXING_REFRESH_INTERVAL
        )
        try:
            async with app.db.async_session_maker() as session:
                result = await session.stream(
                    authors_query, {"last_sync": last_sync_authors}
                )
                batch = []

                async for row in result:
                    app_rating_count = row.app_rating_count or 0
                    ol_rating_count = row.ol_rating_count or 0
                    app_avg = (
                        float(row.app_avg_rating) if row.app_avg_rating else 0.0
                    )
                    ol_avg = float(row.ol_avg_rating) if row.ol_avg_rating else 0.0
                    total_ratings = app_rating_count + ol_rating_count
                    combined_avg = (
                        (app_avg * app_rating_count + ol_avg * ol_rating_count)
                        / total_ratings
                        if total_ratings > 0
                        else 0.0
                    )
                    doc = {
                        "_index": settings.es_index_authors,
                        "_id": f"{row.author_id}_{row.language}",
                        "_source": {
                            "author_id": row.author_id,
                            "language": row.language,
                            "name": row.name or "",
                            "slug": row.slug or "",
                            "photo_url": row.photo_url or "",
                            "book_count": row.book_count or 0,
                            "app_avg_rating": (
                                app_avg if app_rating_count > 0 else None
                            ),
                            "app_rating_count": app_rating_count,
                            "ol_avg_rating": (
                                ol_avg if ol_rating_count > 0 else None
                            ),
                            "ol_rating_count": ol_rating_count,
                            "readers": row.readers or 0,
                            "bayesian_score": _compute_bayesian_score(
                                total_ratings, combined_avg
                            ),
                        },
                    }
                    batch.append(doc)

                    if len(batch) >= settings.es_reindex_batch_size:
                        await _bulk_index(es, batch)
                        authors_indexed += len(batch)
                        batch = []

                if batch:
                    await _bulk_index(es, batch)
                    authors_indexed += len(batch)
        finally:
            await _restore_index_refresh(settings.es_index_authors)

        await app.cache.redis_client.set(ES_LAST_SYNC_KEY_AUTHORS, now_ts)
    except Exception as e:
        logger.error(f"[ES] Authors reindex failed: {str(e)}")

    series_query = sqlalchemy.text(
        """
        SELECT
            s.series_id, s.name, s.slug,
            b.language,
            COUNT(DISTINCT b.book_id) as book_count,
            COALESCE(SUM(b.rating_count), 0) as app_rating_count,
            CASE WHEN SUM(b.rating_count) > 0
                 THEN SUM(b.avg_rating * b.rating_count) / SUM(b.rating_count)
                 ELSE NULL END as app_avg_rating,
            COALESCE(SUM(b.ol_rating_count), 0) as ol_rating_count,
            CASE WHEN SUM(b.ol_rating_count) > 0
                 THEN SUM(b.ol_avg_rating * b.ol_rating_count) / SUM(b.ol_rating_count)
                 ELSE NULL END as ol_avg_rating,
            COALESCE(SUM(
                b.ol_want_to_read_count + b.ol_currently_reading_count
                + b.ol_already_read_count + COALESCE(bs.bookshelf_count, 0)
            ), 0) as readers
        FROM books.series s
        JOIN books.books b ON s.series_id = b.series_id
        LEFT JOIN (
            SELECT wb.work_id, COUNT(DISTINCT bsh.user_id) AS bookshelf_count
            FROM user_data.bookshelves bsh
            JOIN books.books wb ON wb.book_id = bsh.book_id
            GROUP BY wb.work_id
        ) bs ON b.work_id = bs.work_id
        WHERE s.updated_at > :last_sync AND b.language IS NOT NULL
        GROUP BY s.series_id, s.name, s.slug, b.language
        ORDER BY s.series_id, b.language
    """
    )

    try:
        await app.es_client.set_index_refresh(
            settings.es_index_series, ES_INDEXING_REFRESH_INTERVAL
        )
        try:
            async with app.db.async_session_maker() as session:
                result = await session.stream(
                    series_query, {"last_sync": last_sync_series}
                )
                batch = []

                async for row in result:
                    app_rating_count = row.app_rating_count or 0
                    ol_rating_count = row.ol_rating_count or 0
                    app_avg = (
                        float(row.app_avg_rating) if row.app_avg_rating else 0.0
                    )
                    ol_avg = float(row.ol_avg_rating) if row.ol_avg_rating else 0.0
                    total_ratings = app_rating_count + ol_rating_count
                    combined_avg = (
                        (app_avg * app_rating_count + ol_avg * ol_rating_count)
                        / total_ratings
                        if total_ratings > 0
                        else 0.0
                    )
                    doc = {
                        "_index": settings.es_index_series,
                        "_id": f"{row.series_id}_{row.language}",
                        "_source": {
                            "series_id": row.series_id,
                            "language": row.language,
                            "name": row.name or "",
                            "slug": row.slug or "",
                            "book_count": row.book_count or 0,
                            "app_avg_rating": (
                                app_avg if app_rating_count > 0 else None
                            ),
                            "app_rating_count": app_rating_count,
                            "ol_avg_rating": (
                                ol_avg if ol_rating_count > 0 else None
                            ),
                            "ol_rating_count": ol_rating_count,
                            "readers": row.readers or 0,
                            "bayesian_score": _compute_bayesian_score(
                                total_ratings, combined_avg
                            ),
                        },
                    }
                    batch.append(doc)

                    if len(batch) >= settings.es_reindex_batch_size:
                        await _bulk_index(es, batch)
                        series_indexed += len(batch)
                        batch = []

                if batch:
                    await _bulk_index(es, batch)
                    series_indexed += len(batch)
        finally:
            await _restore_index_refresh(settings.es_index_series)

        await app.cache.redis_client.set(ES_LAST_SYNC_KEY_SERIES, now_ts)
    except Exception as e:
        logger.error(f"[ES] Series reindex failed: {str(e)}")

    logger.info(
        f"[ES] Reindex complete. books={books_indexed}, authors={authors_indexed}, series={series_indexed}"
    )

    try:
        await app.services.es_reconcile_service.reconcile_deleted_docs()
    except Exception as e:
        logger.error(f"[ES] Ghost reconciliation failed: {str(e)}")

    try:
        await app.cache.redis_client.delete(ES_REINDEX_RUNNING_KEY)
    except Exception:
        pass
