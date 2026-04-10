import asyncio
import logging
import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


async def _get_author_metadata(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT a.author_id, a.name FROM books.authors a WHERE a.author_id = :author_id"
        ),
        {"author_id": author_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return {"author_id": row.author_id, "name": row.name or ""}


def _row_to_author_item(row: typing.Any, score: float) -> typing.Dict[str, typing.Any]:
    return {
        "author_id": row.author_id,
        "name": row.name or "",
        "slug": row.slug or "",
        "photo_url": row.photo_url or "",
        "book_count": int(row.book_count or 0),
        "avg_rating": str(row.avg_rating) if row.avg_rating else "",
        "rating_count": int(row.rating_count or 0),
        "readers": int(row.readers or 0),
        "score": score,
    }


async def _build_similar_authors_by_genre(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            WITH author_genres AS (
                SELECT DISTINCT bg.genre_id
                FROM books.book_genres bg
                JOIN books.book_authors ba ON bg.book_id = ba.book_id
                WHERE ba.author_id = :author_id
            ),
            author_genre_count AS (
                SELECT COUNT(*) AS cnt FROM author_genres
            ),
            candidate_authors AS (
                SELECT
                    ba.author_id,
                    COUNT(DISTINCT bg.genre_id) AS shared
                FROM books.book_authors ba
                JOIN books.book_genres bg ON ba.book_id = bg.book_id
                JOIN author_genres ag ON bg.genre_id = ag.genre_id
                WHERE ba.author_id != :author_id
                GROUP BY ba.author_id
            ),
            candidate_genre_totals AS (
                SELECT ba2.author_id, COUNT(DISTINCT bg2.genre_id) AS candidate_cnt
                FROM books.book_authors ba2
                JOIN books.book_genres bg2 ON ba2.book_id = bg2.book_id
                JOIN candidate_authors ca2 ON ca2.author_id = ba2.author_id
                GROUP BY ba2.author_id
            ),
            author_app_readers AS (
                SELECT ba_r.author_id, COUNT(*) AS app_readers
                FROM user_data.bookshelves bs_a
                JOIN books.book_authors ba_r ON bs_a.book_id = ba_r.book_id
                JOIN books.books b_r ON ba_r.book_id = b_r.book_id
                WHERE b_r.language = 'en'
                  AND bs_a.status IN ('want_to_read', 'reading', 'read')
                GROUP BY ba_r.author_id
            )
            SELECT
                a.author_id,
                a.name,
                a.slug,
                COALESCE(a.photo_url, '') AS photo_url,
                COUNT(DISTINCT b.book_id) FILTER (WHERE b.language = 'en') AS book_count,
                COALESCE(
                    SUM(
                        COALESCE(b.avg_rating::numeric, 0) * b.rating_count
                        + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
                    ) FILTER (WHERE b.language = 'en')
                    / NULLIF(SUM(b.rating_count + b.ol_rating_count) FILTER (WHERE b.language = 'en'), 0),
                    0
                ) AS avg_rating,
                COALESCE(SUM(
                    COALESCE(b.ol_want_to_read_count, 0) +
                    COALESCE(b.ol_currently_reading_count, 0) +
                    COALESCE(b.ol_already_read_count, 0)
                ) FILTER (WHERE b.language = 'en'), 0) + COALESCE(aar.app_readers, 0) AS readers,
                COALESCE(SUM(b.rating_count + b.ol_rating_count) FILTER (WHERE b.language = 'en'), 0) AS rating_count,
                ca.shared::float / NULLIF(
                    (SELECT cnt FROM author_genre_count) + cgt.candidate_cnt - ca.shared, 0
                ) AS score
            FROM candidate_authors ca
            JOIN candidate_genre_totals cgt ON cgt.author_id = ca.author_id
            JOIN books.authors a ON ca.author_id = a.author_id
            LEFT JOIN books.book_authors ba ON a.author_id = ba.author_id
            LEFT JOIN books.books b ON ba.book_id = b.book_id
            LEFT JOIN author_app_readers aar ON aar.author_id = a.author_id
            WHERE ca.shared > 0
                    GROUP BY a.author_id, a.name, a.slug, a.photo_url, ca.shared, ca.author_id, cgt.candidate_cnt, aar.app_readers
            ORDER BY score DESC NULLS LAST, book_count DESC
            LIMIT :limit
        """
        ),
        {"author_id": author_id, "limit": limit},
    )
    return [_row_to_author_item(row, float(row.score or 0)) for row in result]


async def _build_fans_also_read(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            WITH author_readers AS (
                SELECT DISTINCT bs.user_id
                FROM user_data.bookshelves bs
                JOIN books.book_authors ba ON bs.book_id = ba.book_id
                WHERE ba.author_id = :author_id AND bs.status IN ('read', 'reading')
                LIMIT 500
            ),
            co_authors AS (
                SELECT
                    ba.author_id,
                    COUNT(DISTINCT bs.user_id) AS co_count
                FROM user_data.bookshelves bs
                JOIN author_readers ar ON bs.user_id = ar.user_id
                JOIN books.book_authors ba ON bs.book_id = ba.book_id
                WHERE ba.author_id != :author_id
                  AND bs.status IN ('read', 'reading')
                GROUP BY ba.author_id
                HAVING COUNT(DISTINCT bs.user_id) >= 2
            ),
            author_app_readers AS (
                SELECT ba_r.author_id, COUNT(*) AS app_readers
                FROM user_data.bookshelves bs_a
                JOIN books.book_authors ba_r ON bs_a.book_id = ba_r.book_id
                JOIN books.books b_r ON ba_r.book_id = b_r.book_id
                WHERE b_r.language = 'en'
                  AND bs_a.status IN ('want_to_read', 'reading', 'read')
                GROUP BY ba_r.author_id
            )
            SELECT
                a.author_id,
                a.name,
                a.slug,
                COALESCE(a.photo_url, '') AS photo_url,
                COUNT(DISTINCT b.book_id) FILTER (WHERE b.language = 'en') AS book_count,
                COALESCE(
                    SUM(
                        COALESCE(b.avg_rating::numeric, 0) * b.rating_count
                        + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
                    ) FILTER (WHERE b.language = 'en')
                    / NULLIF(SUM(b.rating_count + b.ol_rating_count) FILTER (WHERE b.language = 'en'), 0),
                    0
                ) AS avg_rating,
                COALESCE(SUM(
                    COALESCE(b.ol_want_to_read_count, 0) +
                    COALESCE(b.ol_currently_reading_count, 0) +
                    COALESCE(b.ol_already_read_count, 0)
                ) FILTER (WHERE b.language = 'en'), 0) + COALESCE(aar.app_readers, 0) AS readers,
                COALESCE(SUM(b.rating_count + b.ol_rating_count) FILTER (WHERE b.language = 'en'), 0) AS rating_count,
                ca.co_count AS score
            FROM co_authors ca
            JOIN books.authors a ON ca.author_id = a.author_id
            LEFT JOIN books.book_authors ba ON a.author_id = ba.author_id
            LEFT JOIN books.books b ON ba.book_id = b.book_id
            LEFT JOIN author_app_readers aar ON aar.author_id = a.author_id
            GROUP BY a.author_id, a.name, a.slug, a.photo_url, ca.co_count, aar.app_readers
            ORDER BY ca.co_count DESC, book_count DESC
            LIMIT :limit
        """
        ),
        {"author_id": author_id, "limit": limit},
    )
    return [_row_to_author_item(row, float(row.score or 0)) for row in result]


def _make_author_section(
    section_key: str,
    display_name: str,
    items: typing.List[typing.Dict[str, typing.Any]],
) -> typing.Dict[str, typing.Any]:
    return {
        "section_key": section_key,
        "display_name": display_name,
        "item_type": "author",
        "author_items": items,
        "total": len(items),
    }


async def build_author_recommendations(
    session_maker: typing.Any,
    author_id: int,
    limit_per_section: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    async def run(fn: typing.Callable, *args: typing.Any) -> typing.Any:
        async with session_maker() as session:
            return await fn(session, *args)

    async with session_maker() as session:
        metadata = await _get_author_metadata(session, author_id)
    if metadata is None:
        return None

    author_name = metadata["name"]

    similar_items, fans_items = await asyncio.gather(
        run(_build_similar_authors_by_genre, author_id, limit_per_section),
        run(_build_fans_also_read, author_id, limit_per_section),
        return_exceptions=True,
    )

    if isinstance(similar_items, Exception):
        logger.error(
            f"[rec:author:{author_id}] similar_authors failed: {similar_items}"
        )
    if isinstance(fans_items, Exception):
        logger.error(f"[rec:author:{author_id}] fans_also_read failed: {fans_items}")

    sections: typing.List[typing.Dict[str, typing.Any]] = []

    if similar_items and not isinstance(similar_items, Exception):
        sections.append(
            _make_author_section(
                "similar_authors",
                f"Similar to {author_name}",
                similar_items,
            )
        )

    if fans_items and not isinstance(fans_items, Exception):
        sections.append(
            _make_author_section(
                "fans_also_read",
                "Fans also read",
                fans_items,
            )
        )

    return sections
