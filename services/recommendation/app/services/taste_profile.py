import asyncio
import logging
import typing

import app.cache
import app.config
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


async def _query_bookshelves(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
) -> typing.Dict[str, typing.Any]:
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT
                bs.book_id,
                bs.status,
                bs.is_favorite,
                ba.author_id
            FROM user_data.bookshelves bs
            LEFT JOIN books.book_authors ba ON bs.book_id = ba.book_id
            WHERE bs.user_id = :user_id
        """
        ),
        {"user_id": user_id},
    )
    rows = result.fetchall()

    read_book_ids: typing.Set[int] = set()
    want_to_read_book_ids: typing.Set[int] = set()
    favorite_book_ids: typing.Set[int] = set()
    author_ids_read: typing.Set[int] = set()
    all_book_ids: typing.Set[int] = set()

    for row in rows:
        all_book_ids.add(row.book_id)
        if row.status in ("read", "reading", "abandoned"):
            read_book_ids.add(row.book_id)
        if row.status == "want_to_read":
            want_to_read_book_ids.add(row.book_id)
        if row.is_favorite:
            favorite_book_ids.add(row.book_id)
        if row.author_id and row.status in ("read", "reading"):
            author_ids_read.add(row.author_id)

    return {
        "read_book_ids": list(read_book_ids),
        "want_to_read_book_ids": list(want_to_read_book_ids),
        "favorite_book_ids": list(favorite_book_ids),
        "author_ids_read": list(author_ids_read),
        "shelved_book_count": len(all_book_ids),
    }


async def _query_genre_scores(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
) -> typing.Tuple[typing.Dict[str, float], typing.List[str]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            WITH user_interactions AS (
                SELECT
                    bs.book_id,
                    bs.is_favorite,
                    bs.status,
                    r.overall_rating
                FROM user_data.bookshelves bs
                LEFT JOIN user_data.ratings r
                    ON bs.user_id = r.user_id AND bs.book_id = r.book_id
                WHERE bs.user_id = :user_id
            ),
            weighted AS (
                SELECT
                    bg.genre_id,
                    SUM(
                        CASE
                            WHEN ui.status = 'read' AND ui.overall_rating >= 4.0 THEN 3.0
                            WHEN ui.status = 'read' AND ui.overall_rating < 4.0 THEN 1.0
                            WHEN ui.status = 'read' AND ui.overall_rating IS NULL THEN 1.5
                            WHEN ui.status = 'reading' THEN 1.5
                            WHEN ui.status = 'want_to_read' THEN 0.5
                            WHEN ui.status = 'abandoned' THEN -1.0
                            ELSE 0
                        END +
                        CASE WHEN ui.is_favorite THEN 2.0 ELSE 0 END
                    ) AS raw_weight
                FROM user_interactions ui
                JOIN books.book_genres bg ON ui.book_id = bg.book_id
                GROUP BY bg.genre_id
            )
            SELECT g.slug, GREATEST(w.raw_weight, 0) AS raw_weight
            FROM weighted w
            JOIN books.genres g ON w.genre_id = g.genre_id
            WHERE w.raw_weight > 0
            ORDER BY w.raw_weight DESC
        """
        ),
        {"user_id": user_id},
    )
    rows = result.fetchall()
    if not rows:
        return {}, []

    raw_scores = {row.slug: float(row.raw_weight) for row in rows}
    total = sum(raw_scores.values())
    if total == 0:
        return {}, []

    genre_scores = {slug: w / total for slug, w in raw_scores.items()}
    top_genre_slugs = [
        slug for slug, _ in sorted(genre_scores.items(), key=lambda x: -x[1])[:3]
    ]
    return genre_scores, top_genre_slugs


async def _query_ratings(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
) -> typing.Tuple[
    typing.Dict[str, float], typing.Optional[typing.Dict[str, typing.Any]]
]:
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT
                r.book_id,
                b.title,
                r.overall_rating,
                r.emotional_impact,
                r.intellectual_depth,
                r.writing_quality,
                r.rereadability,
                r.readability,
                r.plot_complexity,
                r.humor,
                r.pacing
            FROM user_data.ratings r
            JOIN books.books b ON r.book_id = b.book_id
            WHERE r.user_id = :user_id
            ORDER BY r.overall_rating DESC NULLS LAST
        """
        ),
        {"user_id": user_id},
    )
    rows = result.fetchall()
    if not rows:
        return {}, None

    anchor_book = {"book_id": rows[0].book_id, "title": rows[0].title or ""}

    _dimensions = [
        "emotional_impact",
        "intellectual_depth",
        "writing_quality",
        "rereadability",
        "readability",
        "plot_complexity",
        "humor",
        "pacing",
    ]
    totals: typing.Dict[str, float] = {d: 0.0 for d in _dimensions}
    counts: typing.Dict[str, int] = {d: 0 for d in _dimensions}

    for row in rows:
        for dim in _dimensions:
            val = getattr(row, dim, None)
            if val is not None:
                totals[dim] += float(val)
                counts[dim] += 1

    dimension_preferences = {
        dim: totals[dim] / counts[dim] for dim in _dimensions if counts[dim] >= 2
    }
    return dimension_preferences, anchor_book


async def _query_series_in_progress(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            WITH user_series AS (
                SELECT
                    b.series_id,
                    s.name AS series_name,
                    COUNT(DISTINCT bs.book_id) AS read_count
                FROM user_data.bookshelves bs
                JOIN books.books b ON bs.book_id = b.book_id
                JOIN books.series s ON b.series_id = s.series_id
                WHERE bs.user_id = :user_id
                  AND bs.status IN ('read', 'reading')
                  AND b.series_id IS NOT NULL
                GROUP BY b.series_id, s.name
            ),
            total_books AS (
                SELECT b.series_id, COUNT(DISTINCT b.book_id) AS total
                FROM books.books b
                WHERE b.series_id IN (SELECT series_id FROM user_series)
                GROUP BY b.series_id
            )
            SELECT us.series_id, us.series_name, us.read_count, tb.total
            FROM user_series us
            JOIN total_books tb ON us.series_id = tb.series_id
            WHERE us.read_count < tb.total
        """
        ),
        {"user_id": user_id},
    )
    return [
        {
            "series_id": row.series_id,
            "series_name": row.series_name or "",
            "read_count": int(row.read_count),
            "total": int(row.total),
        }
        for row in result.fetchall()
    ]


async def build_taste_profile(
    session_maker: typing.Any,
    user_id: int,
) -> typing.Dict[str, typing.Any]:
    async def run(fn: typing.Callable, *args: typing.Any) -> typing.Any:
        async with session_maker() as session:
            return await fn(session, *args)

    results = await asyncio.gather(
        run(_query_bookshelves, user_id),
        run(_query_genre_scores, user_id),
        run(_query_ratings, user_id),
        run(_query_series_in_progress, user_id),
        return_exceptions=True,
    )

    shelf_data = (
        results[0]
        if not isinstance(results[0], Exception)
        else {
            "read_book_ids": [],
            "want_to_read_book_ids": [],
            "favorite_book_ids": [],
            "author_ids_read": [],
            "shelved_book_count": 0,
        }
    )
    genre_scores, top_genre_slugs = (
        results[1] if not isinstance(results[1], Exception) else ({}, [])
    )
    dimension_preferences, anchor_book = (
        results[2] if not isinstance(results[2], Exception) else ({}, None)
    )
    series_in_progress = results[3] if not isinstance(results[3], Exception) else []

    shelved_book_count = shelf_data["shelved_book_count"]
    is_cold_start = (
        shelved_book_count < app.config.settings.personal_cold_start_threshold
    )

    return {
        "user_id": user_id,
        "read_book_ids": shelf_data["read_book_ids"],
        "shelved_book_count": shelved_book_count,
        "want_to_read_book_ids": shelf_data["want_to_read_book_ids"],
        "favorite_book_ids": shelf_data["favorite_book_ids"],
        "author_ids_read": shelf_data["author_ids_read"],
        "genre_scores": genre_scores,
        "top_genre_slugs": top_genre_slugs,
        "dimension_preferences": dimension_preferences,
        "series_in_progress": series_in_progress,
        "anchor_book": anchor_book,
        "is_cold_start": is_cold_start,
    }


async def get_taste_profile(
    user_id: int,
    force_refresh: bool = False,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    import app.db

    cache_key = f"rec:profile:{user_id}"
    if not force_refresh:
        cached = await app.cache.get_cached(cache_key)
        if cached is not None:
            return cached

    profile = await build_taste_profile(app.db.async_session_maker, user_id)

    await app.cache.set_cached(
        cache_key, profile, app.config.settings.cache_profile_ttl
    )
    return profile
