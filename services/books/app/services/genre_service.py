import logging
import typing

import app.cache
import app.config
import app.db
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_GENRE_BUBBLE_CACHE_KEY = "genre:bubble:{slug}:{limit}"


async def get_genre_bubble(
    slug: str,
    limit: int = 10,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    limit = max(1, min(limit, 50))

    cache_key = _GENRE_BUBBLE_CACHE_KEY.format(slug=slug, limit=limit)
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    result = await _fetch_genre_bubble_from_db(slug, limit)

    if result is not None:
        await app.cache.set_cached(
            cache_key, result, app.config.settings.cache_genre_bubble_ttl
        )

    return result


async def _fetch_genre_bubble_from_db(
    slug: str,
    limit: int,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    try:
        async with app.db.async_session_maker() as session:
            source_result = await session.execute(
                sqlalchemy.text(
                    "SELECT genre_id, name, slug FROM books.genres WHERE slug = :slug"
                ),
                {"slug": slug},
            )
            source_row = source_result.fetchone()

            if source_row is None:
                return None

            source_id: int = source_row[0]
            source_name: str = source_row[1]
            source_slug: str = source_row[2]

            related_result = await session.execute(
                sqlalchemy.text(
                    """
                    SELECT
                        g.genre_id,
                        g.name,
                        g.slug,
                        gco.co_occurrence_count,
                        gco.strength
                    FROM books.genre_co_occurrences gco
                    JOIN books.genres g ON (
                        CASE
                            WHEN gco.genre_id_a = :source_id THEN gco.genre_id_b
                            ELSE gco.genre_id_a
                        END = g.genre_id
                    )
                    WHERE gco.genre_id_a = :source_id OR gco.genre_id_b = :source_id
                    ORDER BY gco.strength DESC
                    LIMIT :limit
                    """
                ),
                {"source_id": source_id, "limit": limit},
            )
            related_rows = related_result.fetchall()

            related = [
                {
                    "genre_id": row[0],
                    "name": row[1],
                    "slug": row[2],
                    "co_occurrence_count": row[3],
                    "strength": row[4],
                }
                for row in related_rows
            ]

            return {
                "source": {
                    "genre_id": source_id,
                    "name": source_name,
                    "slug": source_slug,
                },
                "related": related,
            }

    except Exception as e:
        logger.error(f"[genre_service] get_genre_bubble DB error for slug={slug}: {e}")
        return None
