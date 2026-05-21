import logging
import typing

import app.cache
import app.db
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

BOW_CACHE_KEY = "bow:current"
BOW_HISTORY_KEY = "bow:history"
BOW_TTL = 7 * 24 * 3600 + 3600
BOW_HISTORY_SIZE = 12


async def _get_recent_book_ids() -> typing.List[int]:
    try:
        history = await app.cache.redis_client.lrange(BOW_HISTORY_KEY, 0, -1)
        return [int(bid) for bid in history if bid]
    except Exception as e:
        logger.error(f"[bow] Error reading history: {str(e)}")
        return []


async def _push_history(book_id: int) -> None:
    try:
        await app.cache.redis_client.lpush(BOW_HISTORY_KEY, book_id)
        await app.cache.redis_client.ltrim(BOW_HISTORY_KEY, 0, BOW_HISTORY_SIZE - 1)
    except Exception as e:
        logger.error(f"[bow] Error pushing history: {str(e)}")


async def _select_candidate(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    excluded_ids: typing.List[int],
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT
                b.book_id,
                b.title,
                b.slug,
                b.language,
                b.primary_cover_url,
                b.first_sentence,
                CASE
                    WHEN (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) > 0
                    THEN ROUND(
                        (COALESCE(b.avg_rating::numeric, 0) * COALESCE(b.rating_count, 0)
                         + COALESCE(b.ol_avg_rating::numeric, 0) * COALESCE(b.ol_rating_count, 0))
                        / (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)), 2
                    )
                    ELSE 0
                END AS weighted_avg_rating,
                COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0) AS total_rating_count,
                (
                    SELECT COALESCE(json_agg(json_build_object(
                        'author_id', a.author_id,
                        'name', a.name,
                        'slug', a.slug
                    ) ORDER BY a.name), '[]'::json)
                    FROM books.book_authors ba
                    JOIN books.authors a ON ba.author_id = a.author_id
                    WHERE ba.book_id = b.book_id
                ) AS authors,
                (
                    SELECT COALESCE(json_agg(json_build_object(
                        'genre_id', g.genre_id,
                        'name', g.name,
                        'slug', g.slug
                    ) ORDER BY g.name), '[]'::json)
                    FROM books.book_genres bg
                    JOIN books.genres g ON bg.genre_id = g.genre_id
                    WHERE bg.book_id = b.book_id
                    LIMIT 4
                ) AS categories
            FROM books.books b
            WHERE b.primary_cover_url IS NOT NULL
              AND b.first_sentence IS NOT NULL
              AND length(b.first_sentence) > 10
              AND b.language = 'en'
              AND EXISTS (SELECT 1 FROM books.book_authors ba2 WHERE ba2.book_id = b.book_id)
              AND EXISTS (SELECT 1 FROM books.book_genres bg2 WHERE bg2.book_id = b.book_id)
              AND (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) >= 100
              AND (
                  CASE
                      WHEN (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) > 0
                      THEN (COALESCE(b.avg_rating::numeric, 0) * COALESCE(b.rating_count, 0)
                            + COALESCE(b.ol_avg_rating::numeric, 0) * COALESCE(b.ol_rating_count, 0))
                           / (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0))
                      ELSE 0
                  END
              ) >= 4.0
              AND b.book_id <> ALL(:excluded_ids)
            ORDER BY RANDOM()
            LIMIT 1
            """
        ),
        {"excluded_ids": excluded_ids or [-1]},
    )
    row = result.first()
    if not row:
        return None

    import json

    authors_raw = row.authors
    if isinstance(authors_raw, str):
        authors = json.loads(authors_raw)
    else:
        authors = authors_raw or []

    categories_raw = row.categories
    if isinstance(categories_raw, str):
        categories = json.loads(categories_raw)
    else:
        categories = categories_raw or []

    return {
        "book_id": row.book_id,
        "title": row.title or "",
        "slug": row.slug or "",
        "language": row.language or "en",
        "primary_cover_url": row.primary_cover_url or "",
        "first_sentence": row.first_sentence or "",
        "weighted_avg_rating": float(row.weighted_avg_rating or 0),
        "rating_count": int(row.total_rating_count or 0),
        "authors": authors,
        "categories": categories,
    }


async def refresh_book_of_the_week(
    session_maker: typing.Callable,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    logger.info("[bow] Selecting book of the week")

    excluded_ids = await _get_recent_book_ids()

    async with session_maker() as session:
        book = await _select_candidate(session, excluded_ids)

    if not book:
        logger.warning("[bow] No eligible candidates excluding history, retrying without exclusion")
        async with session_maker() as session:
            book = await _select_candidate(session, [])

    if not book:
        logger.error("[bow] No eligible books found for book of the week")
        return None

    await app.cache.set_cached(BOW_CACHE_KEY, book, BOW_TTL)
    await _push_history(book["book_id"])
    logger.info(f"[bow] Cached book of the week: '{book['title']}' (id={book['book_id']}, TTL={BOW_TTL}s)")
    return book
