import json
import logging
import typing

import app.cache
import app.config
import app.db
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

BOW_TTL = 7 * 24 * 3600 + 3600
BOW_HISTORY_SIZE = 12
BOW_POOL_SIZE = 1


def bow_pool_cache_key(language: str) -> str:
    return f"bow:pool:current:{language}"


def bow_history_key(language: str) -> str:
    return f"bow:history:{language}"


def available_languages() -> typing.List[str]:
    raw = app.config.settings.available_languages or "en"
    langs = [lang.strip() for lang in raw.split(",") if lang.strip()]
    return langs or ["en"]


async def _get_recent_book_ids(language: str) -> typing.List[int]:
    try:
        history = await app.cache.redis_client.lrange(bow_history_key(language), 0, -1)
        return [int(bid) for bid in history if bid]
    except Exception as e:
        logger.error(f"[bow] Error reading history ({language}): {str(e)}")
        return []


async def _push_history(language: str, book_id: int) -> None:
    try:
        key = bow_history_key(language)
        await app.cache.redis_client.lpush(key, book_id)
        await app.cache.redis_client.ltrim(key, 0, BOW_HISTORY_SIZE - 1)
    except Exception as e:
        logger.error(f"[bow] Error pushing history ({language}): {str(e)}")


async def _fetch_candidate_pool(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    excluded_ids: typing.List[int],
) -> typing.List[typing.Dict[str, typing.Any]]:
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
              AND b.language = :language
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
            LIMIT :pool_size
            """
        ),
        {
            "language": language,
            "excluded_ids": excluded_ids or [-1],
            "pool_size": BOW_POOL_SIZE,
        },
    )
    rows = result.fetchall()

    pool = []
    for row in rows:
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

        pool.append({
            "book_id": row.book_id,
            "title": row.title or "",
            "slug": row.slug or "",
            "language": row.language or language,
            "primary_cover_url": row.primary_cover_url or "",
            "first_sentence": row.first_sentence or "",
            "weighted_avg_rating": float(row.weighted_avg_rating or 0),
            "rating_count": int(row.total_rating_count or 0),
            "authors": authors,
            "categories": categories,
        })

    return pool


async def refresh_book_of_the_week_for_language(
    session_maker: typing.Callable,
    language: str,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    logger.info(f"[bow] Selecting book of the week pool for language={language}")

    excluded_ids = await _get_recent_book_ids(language)

    async with session_maker() as session:
        pool = await _fetch_candidate_pool(session, language, excluded_ids)

    if not pool:
        logger.warning(
            f"[bow] No eligible candidates for language={language} "
            f"excluding history, retrying without exclusion"
        )
        async with session_maker() as session:
            pool = await _fetch_candidate_pool(session, language, [])

    if not pool:
        logger.error(f"[bow] No eligible books found for language={language}")
        return None

    await app.cache.set_cached(bow_pool_cache_key(language), pool, BOW_TTL)
    await _push_history(language, pool[0]["book_id"])
    logger.info(
        f"[bow] Cached book of the week pool for language={language}: "
        f"{len(pool)} candidates (first: '{pool[0]['title']}' id={pool[0]['book_id']}, "
        f"TTL={BOW_TTL}s)"
    )
    return pool


async def refresh_book_of_the_week(
    session_maker: typing.Callable,
) -> typing.Dict[str, typing.Optional[typing.List[typing.Dict[str, typing.Any]]]]:
    results: typing.Dict[str, typing.Optional[typing.List[typing.Dict[str, typing.Any]]]] = {}
    for language in available_languages():
        results[language] = await refresh_book_of_the_week_for_language(
            session_maker, language
        )
    return results
