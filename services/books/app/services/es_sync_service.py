import asyncio
import datetime
import json
import logging
import typing

import app.cache
import app.config
import app.db
import app.es_client
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

EPOCH = datetime.datetime(1970, 1, 1)


def _compute_bayesian_score(total_ratings: int, combined_avg: float) -> float:
    return (
        total_ratings * combined_avg + BAYESIAN_MIN_RATINGS * BAYESIAN_PRIOR_MEAN
    ) / (total_ratings + BAYESIAN_MIN_RATINGS)


def _rating_summary(row: typing.Any) -> typing.Dict[str, typing.Any]:
    """Display ratings plus the two rank features, from summed edition counts."""
    app_rating_count = int(row.app_rating_count or 0)
    ol_rating_count = int(row.ol_rating_count or 0)
    app_avg = (
        float(row.app_rating_sum) / app_rating_count if app_rating_count > 0 else 0.0
    )
    ol_avg = float(row.ol_rating_sum) / ol_rating_count if ol_rating_count > 0 else 0.0
    total_ratings = app_rating_count + ol_rating_count
    combined_avg = (
        (app_avg * app_rating_count + ol_avg * ol_rating_count) / total_ratings
        if total_ratings > 0
        else 0.0
    )
    readers = int(row.readers or 0)

    summary: typing.Dict[str, typing.Any] = {
        "app_avg_rating": app_avg if app_rating_count > 0 else None,
        "app_rating_count": app_rating_count,
        "ol_avg_rating": ol_avg if ol_rating_count > 0 else None,
        "ol_rating_count": ol_rating_count,
        "readers": readers,
        "quality": _compute_bayesian_score(total_ratings, combined_avg),
    }

    # Elasticsearch rejects a rank feature that is not strictly positive, so an
    # entity nobody has read yet simply carries no popularity signal.
    popularity = readers + total_ratings
    if popularity > 0:
        summary["popularity"] = float(popularity)

    return summary


def _split_authors(
    raw: typing.Optional[typing.List[typing.Dict[str, typing.Any]]],
) -> typing.Tuple[typing.List[str], typing.List[str]]:
    """Names and slugs as parallel lists, kept aligned.

    Aggregating the two columns separately in SQL sorts each on its own value,
    which silently pairs an author's name with another author's slug whenever
    the two orders differ — so they travel as objects and are split here.
    """
    entries = raw or []
    return (
        [entry["name"] for entry in entries if entry.get("name")],
        [entry["slug"] for entry in entries if entry.get("slug")],
    )


async def _restore_index_refresh(index: str) -> None:
    try:
        await app.es_client.set_index_refresh(index, "1s")
        await app.es_client.refresh_index(index)
    except Exception as e:
        logger.error(f"[ES] Refresh restore failed for {index}: {str(e)}")


async def _bulk_index(es: typing.Any, docs: typing.List[typing.Any]) -> None:
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


async def _sync_index(
    es: typing.Any,
    index: str,
    query: typing.Any,
    params: typing.Dict[str, typing.Any],
    build_doc: typing.Callable[[typing.Any], typing.Optional[typing.Dict[str, typing.Any]]],
) -> int:
    indexed = 0
    batch: typing.List[typing.Dict[str, typing.Any]] = []
    batch_size = app.config.settings.es_reindex_batch_size

    await app.es_client.set_index_refresh(index, ES_INDEXING_REFRESH_INTERVAL)
    try:
        async with app.db.async_session_maker() as session:
            result = await session.stream(query, params)

            async for row in result:
                doc = build_doc(row)
                if doc is None:
                    continue
                batch.append({"_index": index, **doc})

                if len(batch) >= batch_size:
                    await _bulk_index(es, batch)
                    indexed += len(batch)
                    batch = []

            if batch:
                await _bulk_index(es, batch)
                indexed += len(batch)
    finally:
        await _restore_index_refresh(index)

    return indexed


# Every edition of a work in one document: titles routed to their own language's
# analyzed field, the rest of the editions kept as an inert payload so the
# reader's language decides at query time which one gets rendered.
_WORKS_QUERY = sqlalchemy.text(
    """
    WITH changed AS (
        SELECT DISTINCT work_id
        FROM books.books
        WHERE updated_at > :last_sync AND work_id IS NOT NULL
    ),
    work_shelves AS (
        SELECT wsc.work_id, wsc.readers AS app_readers
        FROM books.work_shelf_counts wsc
        JOIN changed c ON c.work_id = wsc.work_id
    ),
    work_authors AS (
        SELECT
            b.work_id,
            JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT('name', a.name, 'slug', a.slug)) AS authors
        FROM books.books b
        JOIN changed c ON c.work_id = b.work_id
        JOIN books.book_authors ba ON ba.book_id = b.book_id
        JOIN books.authors a ON a.author_id = ba.author_id
        GROUP BY b.work_id
    )
    SELECT
        b.work_id,
        ARRAY_AGG(DISTINCT b.language) FILTER (WHERE b.language IS NOT NULL) AS languages,
        ARRAY_AGG(DISTINCT s.name) FILTER (WHERE s.name IS NOT NULL) AS series_names,
        COALESCE(SUM(b.rating_count), 0) AS app_rating_count,
        COALESCE(SUM(COALESCE(b.avg_rating, 0) * COALESCE(b.rating_count, 0)), 0) AS app_rating_sum,
        COALESCE(SUM(b.ol_rating_count), 0) AS ol_rating_count,
        COALESCE(SUM(COALESCE(b.ol_avg_rating, 0) * COALESCE(b.ol_rating_count, 0)), 0) AS ol_rating_sum,
        COALESCE(SUM(
            COALESCE(b.ol_want_to_read_count, 0)
            + COALESCE(b.ol_currently_reading_count, 0)
            + COALESCE(b.ol_already_read_count, 0)
        ), 0) + COALESCE(MAX(ws.app_readers), 0) AS readers,
        wa.authors AS authors,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'book_id', b.book_id,
                'slug', b.slug,
                'language', b.language,
                'title', b.title,
                'cover_url', COALESCE(b.primary_cover_url, ''),
                'series_slug', COALESCE(s.slug, ''),
                'series_name', COALESCE(s.name, ''),
                'ratings', COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)
            )
            ORDER BY (b.language = 'en') DESC, b.book_id ASC
        ) AS editions
    FROM books.books b
    JOIN changed c ON c.work_id = b.work_id
    LEFT JOIN books.series s ON s.series_id = b.series_id
    LEFT JOIN work_shelves ws ON ws.work_id = b.work_id
    LEFT JOIN work_authors wa ON wa.work_id = b.work_id
    GROUP BY b.work_id, wa.authors
    ORDER BY b.work_id
"""
)


def _build_work_doc(row: typing.Any) -> typing.Optional[typing.Dict[str, typing.Any]]:
    editions = row.editions or []
    if isinstance(editions, str):
        editions = json.loads(editions)
    if not editions:
        return None

    raw_authors = row.authors
    if isinstance(raw_authors, str):
        raw_authors = json.loads(raw_authors)
    author_names, author_slugs = _split_authors(raw_authors)

    # `editions` is already ordered (language = 'en') DESC, book_id ASC, so
    # the first title is the canonical one; the rest are recall-only aliases
    # (other translations/printings) that must not compete with it for norms.
    titles = [edition["title"] for edition in editions if edition.get("title")]
    canonical_title = titles[0] if titles else ""
    alt_titles = list(dict.fromkeys(titles[1:]))

    source: typing.Dict[str, typing.Any] = {
        "kind": "book",
        "work_id": row.work_id,
        "name": canonical_title,
        "alt_names": alt_titles,
        "authors_names": author_names,
        "author_slugs": author_slugs,
        "series_name": list(row.series_names or []),
        "languages": list(row.languages or []),
        "editions": editions,
        **_rating_summary(row),
    }

    for language in app.es_client.stemmed_languages():
        localized = [
            edition["title"]
            for edition in editions
            if edition.get("title") and edition.get("language") == language
        ]
        if localized:
            source[app.es_client.language_field("name", language)] = localized

    return {"_id": f"book:{row.work_id}", "_source": source}


# One document per author. Aggregates are taken per work rather than per edition
# so a heavily translated author is not credited once per translation.
_AUTHORS_QUERY = sqlalchemy.text(
    """
    WITH changed AS (
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
        JOIN changed c ON c.author_id = ba.author_id
        ORDER BY ba.author_id, b.work_id,
                 (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) DESC
    ),
    author_app_readers AS (
        SELECT ba.author_id, COUNT(DISTINCT bs.user_id) AS app_readers
        FROM user_data.bookshelves bs
        JOIN books.book_authors ba ON ba.book_id = bs.book_id
        JOIN changed c ON c.author_id = ba.author_id
        GROUP BY ba.author_id
    ),
    author_languages AS (
        SELECT ba.author_id, ARRAY_AGG(DISTINCT b.language) AS languages
        FROM books.book_authors ba
        JOIN books.books b ON ba.book_id = b.book_id
        JOIN changed c ON c.author_id = ba.author_id
        WHERE b.language IS NOT NULL
        GROUP BY ba.author_id
    ),
    author_stats AS (
        SELECT
            aw.author_id,
            COUNT(*) AS book_count,
            COALESCE(SUM(aw.rating_count), 0) AS app_rating_count,
            COALESCE(SUM(COALESCE(aw.avg_rating, 0) * COALESCE(aw.rating_count, 0)), 0) AS app_rating_sum,
            COALESCE(SUM(aw.ol_rating_count), 0) AS ol_rating_count,
            COALESCE(SUM(COALESCE(aw.ol_avg_rating, 0) * COALESCE(aw.ol_rating_count, 0)), 0) AS ol_rating_sum,
            COALESCE(SUM(
                COALESCE(aw.ol_want_to_read_count, 0)
                + COALESCE(aw.ol_currently_reading_count, 0)
                + COALESCE(aw.ol_already_read_count, 0)
            ), 0) AS ol_readers
        FROM author_works aw
        GROUP BY aw.author_id
    )
    SELECT
        a.author_id, a.name, a.slug, a.photo_url,
        ast.book_count,
        ast.app_rating_count, ast.app_rating_sum,
        ast.ol_rating_count, ast.ol_rating_sum,
        ast.ol_readers + COALESCE(aar.app_readers, 0) AS readers,
        al.languages AS languages
    FROM books.authors a
    JOIN author_stats ast ON ast.author_id = a.author_id
    LEFT JOIN author_app_readers aar ON aar.author_id = a.author_id
    LEFT JOIN author_languages al ON al.author_id = a.author_id
    ORDER BY a.author_id
"""
)


def _build_author_doc(row: typing.Any) -> typing.Dict[str, typing.Any]:
    return {
        "_id": f"author:{row.author_id}",
        "_source": {
            "kind": "author",
            "author_id": row.author_id,
            "name": row.name or "",
            "slug": row.slug or "",
            "photo_url": row.photo_url or "",
            "book_count": int(row.book_count or 0),
            "languages": list(row.languages or []),
            **_rating_summary(row),
        },
    }


# One document per series slug: the per-language rows behind it are the same
# series as far as the reader and the route are concerned, and the row matching
# their language is chosen at query time.
_SERIES_QUERY = sqlalchemy.text(
    """
    WITH changed AS (
        SELECT DISTINCT slug FROM books.series WHERE updated_at > :last_sync
    ),
    row_stats AS (
        SELECT
            s.series_id, s.slug, s.name, s.language,
            COUNT(DISTINCT b.book_id) AS book_count,
            COALESCE(SUM(b.rating_count), 0) AS app_rating_count,
            COALESCE(SUM(COALESCE(b.avg_rating, 0) * COALESCE(b.rating_count, 0)), 0) AS app_rating_sum,
            COALESCE(SUM(b.ol_rating_count), 0) AS ol_rating_count,
            COALESCE(SUM(COALESCE(b.ol_avg_rating, 0) * COALESCE(b.ol_rating_count, 0)), 0) AS ol_rating_sum,
            COALESCE(SUM(
                COALESCE(b.ol_want_to_read_count, 0)
                + COALESCE(b.ol_currently_reading_count, 0)
                + COALESCE(b.ol_already_read_count, 0)
            ), 0) AS ol_readers,
            COALESCE(SUM(COALESCE(wsc.readers, 0)), 0) AS app_readers
        FROM books.series s
        JOIN changed c ON c.slug = s.slug
        LEFT JOIN books.books b ON b.series_id = s.series_id
        LEFT JOIN books.work_shelf_counts wsc ON wsc.work_id = b.work_id
        GROUP BY s.series_id, s.slug, s.name, s.language
    )
    SELECT
        slug,
        ARRAY_AGG(DISTINCT name) FILTER (WHERE name IS NOT NULL) AS names,
        ARRAY_AGG(DISTINCT language) FILTER (WHERE language IS NOT NULL) AS languages,
        SUM(app_rating_count) AS app_rating_count,
        SUM(app_rating_sum) AS app_rating_sum,
        SUM(ol_rating_count) AS ol_rating_count,
        SUM(ol_rating_sum) AS ol_rating_sum,
        SUM(ol_readers) + SUM(app_readers) AS readers,
        JSONB_AGG(
            JSONB_BUILD_OBJECT(
                'series_id', series_id,
                'language', language,
                'name', name,
                'book_count', book_count
            )
            ORDER BY (language = 'en') DESC, series_id ASC
        ) AS rows
    FROM row_stats
    GROUP BY slug
    ORDER BY slug
"""
)


def _build_series_doc(row: typing.Any) -> typing.Optional[typing.Dict[str, typing.Any]]:
    rows = row.rows or []
    if isinstance(rows, str):
        rows = json.loads(rows)
    if not rows:
        return None

    # `rows` is already ordered (language = 'en') DESC, series_id ASC (unlike
    # the unordered `names` aggregate), so the first name is the canonical one.
    row_names = [entry["name"] for entry in rows if entry.get("name")]
    canonical_name = row_names[0] if row_names else ""
    alt_names = list(dict.fromkeys(row_names[1:]))

    source: typing.Dict[str, typing.Any] = {
        "kind": "series",
        "slug": row.slug,
        "name": canonical_name,
        "alt_names": alt_names,
        "languages": list(row.languages or []),
        "rows": rows,
        "book_count": max((entry.get("book_count") or 0) for entry in rows),
        **_rating_summary(row),
    }

    for language in app.es_client.stemmed_languages():
        localized = [
            entry["name"]
            for entry in rows
            if entry.get("name") and entry.get("language") == language
        ]
        if localized:
            source[app.es_client.language_field("name", language)] = localized

    return {"_id": f"series:{row.slug}", "_source": source}


async def _read_last_sync(key: str) -> datetime.datetime:
    raw = await app.cache.redis_client.get(key)
    if not raw:
        return EPOCH
    return datetime.datetime.fromisoformat(raw).replace(tzinfo=None)


async def reindex_all_to_es(full: bool = False) -> None:
    await app.cache.redis_client.set(
        ES_REINDEX_RUNNING_KEY, "1", ex=ES_REINDEX_RUNNING_TTL
    )
    es = app.es_client.get_es()
    settings = app.config.settings
    alias = settings.es_index_catalog

    plan = await app.es_client.plan_indexes()
    if plan.rebuild and not full:
        logger.info("[ES] Index mapping changed, upgrading to a full reindex")
        full = True

    if full:
        last_sync = {
            ES_LAST_SYNC_KEY: EPOCH,
            ES_LAST_SYNC_KEY_AUTHORS: EPOCH,
            ES_LAST_SYNC_KEY_SERIES: EPOCH,
        }
        logger.info("[ES] Starting full reindex")
    else:
        last_sync = {
            ES_LAST_SYNC_KEY: await _read_last_sync(ES_LAST_SYNC_KEY),
            ES_LAST_SYNC_KEY_AUTHORS: await _read_last_sync(ES_LAST_SYNC_KEY_AUTHORS),
            ES_LAST_SYNC_KEY_SERIES: await _read_last_sync(ES_LAST_SYNC_KEY_SERIES),
        }
        logger.info(
            "[ES] Starting incremental reindex. last_sync "
            + ", ".join(f"{key}={ts.isoformat()}" for key, ts in last_sync.items())
        )

    now_ts = datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat()
    counts: typing.Dict[str, int] = {}
    write_index = plan.write_index(alias)

    # All three jobs write into the same target index — they key their docs
    # by kind-prefixed _id (`book:`/`author:`/`series:`), so one job's bulk
    # upserts never touch another's documents.
    jobs = (
        ("books", _WORKS_QUERY, _build_work_doc, ES_LAST_SYNC_KEY),
        ("authors", _AUTHORS_QUERY, _build_author_doc, ES_LAST_SYNC_KEY_AUTHORS),
        ("series", _SERIES_QUERY, _build_series_doc, ES_LAST_SYNC_KEY_SERIES),
    )

    succeeded = True
    for entity, query, build_doc, sync_key in jobs:
        try:
            counts[entity] = await _sync_index(
                es,
                write_index,
                query,
                {"last_sync": last_sync[sync_key]},
                build_doc,
            )
            await app.cache.redis_client.set(sync_key, now_ts)
        except Exception as e:
            succeeded = False
            counts[entity] = 0
            logger.error(f"[ES] Reindex failed for '{entity}': {str(e)}")

    logger.info(
        "[ES] Reindex complete. "
        + ", ".join(f"{entity}={count}" for entity, count in counts.items())
    )

    if plan.rebuild:
        # A half-filled index must not take over the alias — the old one is
        # still serving and stale beats empty.
        if succeeded:
            await app.es_client.promote(plan)
        else:
            logger.error("[ES] Rebuild incomplete, keeping the previous indexes live")
    else:
        try:
            await app.services.es_reconcile_service.reconcile_deleted_docs()
        except Exception as e:
            logger.error(f"[ES] Ghost reconciliation failed: {str(e)}")

    try:
        await app.cache.redis_client.delete(ES_REINDEX_RUNNING_KEY)
    except Exception:
        pass
