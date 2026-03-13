import asyncio
import logging
import typing

import app.services.list_builder
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


def _make_home_section(
    category_key: str,
    display_name: str,
    item_type: str,
    items: typing.List[typing.Dict[str, typing.Any]],
) -> typing.Dict[str, typing.Any]:
    items_key = "book_items" if item_type == "book" else "author_items"
    return {
        "category": category_key,
        "display_name": display_name,
        "item_type": item_type,
        items_key: items,
        "total": len(items),
    }


def _make_book_page_section(
    section_key: str,
    display_name: str,
    items: typing.List[typing.Dict[str, typing.Any]],
) -> typing.Dict[str, typing.Any]:
    return {
        "section_key": section_key,
        "display_name": display_name,
        "item_type": "book",
        "book_items": items,
        "total": len(items),
    }


async def _build_for_you(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    genre_scores = profile.get("genre_scores", {})
    if not genre_scores:
        return []

    genre_slugs = list(genre_scores.keys())
    genre_weights = [genre_scores[slug] for slug in genre_slugs]
    exclude_ids = profile.get("read_book_ids", []) or [-1]
    read_book_ids = profile.get("read_book_ids", []) or [-1]
    user_id = profile["user_id"]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            WITH user_genres AS (
                SELECT
                    unnest(CAST(:genre_slugs AS text[])) AS slug,
                    unnest(CAST(:genre_weights AS float[])) AS weight
            ),
            user_genre_ids AS (
                SELECT g.genre_id, ug.weight
                FROM user_genres ug
                JOIN books.genres g ON g.slug = ug.slug
            ),
            genre_scored AS (
                SELECT b.book_id, SUM(ugi.weight) AS genre_score
                FROM books.books b
                JOIN books.book_genres bg ON b.book_id = bg.book_id
                JOIN user_genre_ids ugi ON bg.genre_id = ugi.genre_id
                WHERE NOT (b.book_id = ANY(CAST(:exclude_ids AS bigint[])))
                  AND {app.services.list_builder._BOOK_BASE_WHERE}
                GROUP BY b.book_id
            ),
            similar_users AS (
                SELECT bs2.user_id
                FROM user_data.bookshelves bs2
                WHERE bs2.book_id = ANY(CAST(:read_book_ids AS bigint[]))
                  AND bs2.user_id != :user_id
                  AND bs2.status IN ('read', 'reading')
                GROUP BY bs2.user_id
                HAVING COUNT(*) >= 2
                ORDER BY COUNT(*) DESC
                LIMIT 200
            ),
            collab_scored AS (
                SELECT bs.book_id, COUNT(DISTINCT bs.user_id) AS collab_score
                FROM user_data.bookshelves bs
                JOIN similar_users su ON bs.user_id = su.user_id
                WHERE bs.status IN ('read', 'reading')
                  AND NOT (bs.book_id = ANY(CAST(:exclude_ids AS bigint[])))
                GROUP BY bs.book_id
            ),
            max_collab AS (
                SELECT NULLIF(MAX(collab_score), 0)::float AS max_val FROM collab_scored
            )
            SELECT {app.services.list_builder._BOOK_FIELDS},
                (
                    gs.genre_score * 0.6 +
                    COALESCE(cs.collab_score, 0)::float
                        / COALESCE((SELECT max_val FROM max_collab), 1) * 0.25 +
                    COALESCE(b.avg_rating::float, 0) / 5.0 * 0.15
                ) AS score
            FROM genre_scored gs
            JOIN books.books b ON gs.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            LEFT JOIN collab_scored cs ON gs.book_id = cs.book_id
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
            GROUP BY b.book_id, gs.genre_score, cs.collab_score
            ORDER BY score DESC
            LIMIT :limit
            """
        ),
        {
            "genre_slugs": genre_slugs,
            "genre_weights": genre_weights,
            "exclude_ids": exclude_ids,
            "read_book_ids": read_book_ids,
            "user_id": user_id,
            "limit": limit,
        },
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_because_you_liked(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], str]:
    anchor_book = profile.get("anchor_book")
    if not anchor_book:
        return [], ""

    anchor_book_id = anchor_book["book_id"]
    anchor_title = anchor_book["title"]
    exclude_ids = profile.get("read_book_ids", []) or [-1]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            WITH source_genres AS (
                SELECT genre_id FROM books.book_genres WHERE book_id = :anchor_id
            ),
            source_count AS (
                SELECT COUNT(*) AS cnt FROM source_genres
            ),
            genre_similar AS (
                SELECT bg.book_id,
                       COUNT(*) AS shared,
                       (SELECT cnt FROM source_count) AS source_cnt
                FROM books.book_genres bg
                JOIN source_genres sg ON bg.genre_id = sg.genre_id
                WHERE bg.book_id != :anchor_id
                  AND NOT (bg.book_id = ANY(CAST(:exclude_ids AS bigint[])))
                GROUP BY bg.book_id
            ),
            genre_scored AS (
                SELECT book_id,
                       shared::float / NULLIF(
                           source_cnt + (
                               SELECT COUNT(*) FROM books.book_genres bg2
                               WHERE bg2.book_id = genre_similar.book_id
                           ) - shared, 0
                       ) AS genre_score
                FROM genre_similar
            ),
            source_readers AS (
                SELECT DISTINCT user_id
                FROM user_data.bookshelves
                WHERE book_id = :anchor_id AND status IN ('read', 'reading')
                LIMIT 500
            ),
            collab_scored AS (
                SELECT bs.book_id, COUNT(DISTINCT bs.user_id) AS collab_score
                FROM user_data.bookshelves bs
                JOIN source_readers sr ON bs.user_id = sr.user_id
                WHERE bs.book_id != :anchor_id
                  AND bs.status IN ('read', 'reading')
                  AND NOT (bs.book_id = ANY(CAST(:exclude_ids AS bigint[])))
                GROUP BY bs.book_id
                HAVING COUNT(DISTINCT bs.user_id) >= 2
            ),
            max_collab AS (
                SELECT NULLIF(MAX(collab_score), 0)::float AS max_val FROM collab_scored
            ),
            combined AS (
                SELECT
                    COALESCE(gs.book_id, cs.book_id) AS book_id,
                    COALESCE(gs.genre_score, 0) * 0.5 +
                    COALESCE(cs.collab_score, 0)::float
                        / COALESCE((SELECT max_val FROM max_collab), 1) * 0.5 AS score
                FROM genre_scored gs
                FULL OUTER JOIN collab_scored cs ON gs.book_id = cs.book_id
            )
            SELECT {app.services.list_builder._BOOK_FIELDS}, c.score AS score
            FROM combined c
            JOIN books.books b ON c.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
            GROUP BY b.book_id, c.score
            ORDER BY c.score DESC
            LIMIT :limit
            """
        ),
        {"anchor_id": anchor_book_id, "exclude_ids": exclude_ids, "limit": limit},
    )
    items = [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]
    return items, anchor_title


async def _build_continue_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    series_in_progress = profile.get("series_in_progress", [])
    if not series_in_progress:
        return []

    series_ids = [s["series_id"] for s in series_in_progress]
    exclude_ids = profile.get("read_book_ids", []) or [-1]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.series_position AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND b.series_id = ANY(CAST(:series_ids AS bigint[]))
              AND NOT (b.book_id = ANY(CAST(:exclude_ids AS bigint[])))
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.series_position ASC NULLS LAST
            LIMIT :limit
            """
        ),
        {"series_ids": series_ids, "exclude_ids": exclude_ids, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_from_favorite_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    author_ids = profile.get("author_ids_read", [])
    if not author_ids:
        return []

    exclude_ids = profile.get("read_book_ids", []) or [-1]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.avg_rating AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND NOT (b.book_id = ANY(CAST(:exclude_ids AS bigint[])))
              AND EXISTS (
                  SELECT 1 FROM books.book_authors ba2
                  WHERE ba2.book_id = b.book_id
                    AND ba2.author_id = ANY(CAST(:author_ids AS bigint[]))
              )
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"author_ids": author_ids, "exclude_ids": exclude_ids, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_top_in_genre(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], str]:
    top_genre_slugs = profile.get("top_genre_slugs", [])
    if not top_genre_slugs:
        return [], ""

    genre_slug = top_genre_slugs[0]
    exclude_ids = profile.get("read_book_ids", []) or [-1]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.avg_rating AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND NOT (b.book_id = ANY(CAST(:exclude_ids AS bigint[])))
              AND b.avg_rating IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM books.book_genres bg2
                  JOIN books.genres g ON bg2.genre_id = g.genre_id
                  WHERE bg2.book_id = b.book_id AND g.slug = :genre_slug
              )
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.avg_rating DESC NULLS LAST, b.rating_count DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"genre_slug": genre_slug, "exclude_ids": exclude_ids, "limit": limit},
    )
    items = [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]
    return items, genre_slug


async def _build_want_to_read_picks(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    want_to_read_ids = profile.get("want_to_read_book_ids", [])
    if not want_to_read_ids:
        return []

    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.avg_rating AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND b.book_id = ANY(CAST(:want_to_read_ids AS bigint[]))
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.avg_rating DESC NULLS LAST, b.ol_already_read_count DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"want_to_read_ids": want_to_read_ids, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_readers_like_you(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    read_book_ids = profile.get("read_book_ids", [])
    if not read_book_ids:
        return []

    exclude_ids = read_book_ids or [-1]
    user_id = profile["user_id"]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            WITH similar_users AS (
                SELECT bs2.user_id
                FROM user_data.bookshelves bs2
                WHERE bs2.book_id = ANY(CAST(:read_book_ids AS bigint[]))
                  AND bs2.user_id != :user_id
                  AND bs2.status IN ('read', 'reading')
                GROUP BY bs2.user_id
                HAVING COUNT(*) >= 2
                ORDER BY COUNT(*) DESC
                LIMIT 200
            ),
            recommended AS (
                SELECT bs.book_id, COUNT(DISTINCT bs.user_id) AS reader_count
                FROM user_data.bookshelves bs
                JOIN similar_users su ON bs.user_id = su.user_id
                WHERE bs.status IN ('read', 'reading')
                  AND NOT (bs.book_id = ANY(CAST(:exclude_ids AS bigint[])))
                GROUP BY bs.book_id
                HAVING COUNT(DISTINCT bs.user_id) >= 2
            )
            SELECT {app.services.list_builder._BOOK_FIELDS}, r.reader_count AS score
            FROM recommended r
            JOIN books.books b ON r.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
            GROUP BY b.book_id, r.reader_count
            ORDER BY r.reader_count DESC, b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {
            "read_book_ids": read_book_ids,
            "exclude_ids": exclude_ids,
            "user_id": user_id,
            "limit": limit,
        },
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_hidden_gems(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    top_genre_slugs = profile.get("top_genre_slugs", [])
    if not top_genre_slugs:
        return []

    exclude_ids = profile.get("read_book_ids", []) or [-1]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.avg_rating AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND NOT (b.book_id = ANY(CAST(:exclude_ids AS bigint[])))
              AND b.avg_rating >= 4.0
              AND b.rating_count BETWEEN 3 AND 20
              AND COALESCE(b.view_count, 0) < 500
              AND EXISTS (
                  SELECT 1 FROM books.book_genres bg2
                  JOIN books.genres g ON bg2.genre_id = g.genre_id
                  WHERE bg2.book_id = b.book_id AND g.slug = ANY(CAST(:genre_slugs AS text[]))
              )
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.avg_rating DESC, b.rating_count DESC
            LIMIT :limit
            """
        ),
        {"genre_slugs": top_genre_slugs, "exclude_ids": exclude_ids, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_you_might_like(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    genre_scores = profile.get("genre_scores", {})
    if not genre_scores:
        return []

    exclude_ids = list({*profile.get("read_book_ids", []), book_id}) or [-1]
    genre_slugs = list(genre_scores.keys())
    genre_weights = [genre_scores[slug] for slug in genre_slugs]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            WITH book_genre_ids AS (
                SELECT bg.genre_id
                FROM books.book_genres bg
                JOIN books.genres g ON bg.genre_id = g.genre_id
                WHERE bg.book_id = :book_id AND g.slug = ANY(CAST(:genre_slugs AS text[]))
            ),
            user_genres AS (
                SELECT
                    unnest(CAST(:genre_slugs AS text[])) AS slug,
                    unnest(CAST(:genre_weights AS float[])) AS weight
            ),
            user_genre_ids AS (
                SELECT g.genre_id, ug.weight
                FROM user_genres ug
                JOIN books.genres g ON g.slug = ug.slug
            ),
            scored AS (
                SELECT b.book_id,
                       SUM(ugi.weight) AS score
                FROM books.books b
                JOIN books.book_genres bg ON b.book_id = bg.book_id
                JOIN book_genre_ids bgi ON bg.genre_id = bgi.genre_id
                JOIN user_genre_ids ugi ON bg.genre_id = ugi.genre_id
                WHERE NOT (b.book_id = ANY(CAST(:exclude_ids AS bigint[])))
                  AND {app.services.list_builder._BOOK_BASE_WHERE}
                GROUP BY b.book_id
            )
            SELECT {app.services.list_builder._BOOK_FIELDS}, s.score AS score
            FROM scored s
            JOIN books.books b ON s.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
            GROUP BY b.book_id, s.score
            ORDER BY s.score DESC, b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {
            "book_id": book_id,
            "genre_slugs": genre_slugs,
            "genre_weights": genre_weights,
            "exclude_ids": exclude_ids,
            "limit": limit,
        },
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_unread_by_author(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
    profile: typing.Dict[str, typing.Any],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    exclude_ids = profile.get("read_book_ids", [])
    shelved_ids = list(
        {
            *exclude_ids,
            *profile.get("want_to_read_book_ids", []),
        }
    ) or [-1]

    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.avg_rating AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND NOT (b.book_id = ANY(CAST(:shelved_ids AS bigint[])))
              AND EXISTS (
                  SELECT 1 FROM books.book_authors ba2
                  WHERE ba2.book_id = b.book_id AND ba2.author_id = :author_id
              )
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"author_id": author_id, "shelved_ids": shelved_ids, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def build_personal_home_sections(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    profile: typing.Dict[str, typing.Any],
    limit_per_section: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    results = await asyncio.gather(
        _build_for_you(session, profile, limit_per_section),
        _build_because_you_liked(session, profile, limit_per_section),
        _build_continue_series(session, profile, limit_per_section),
        _build_from_favorite_authors(session, profile, limit_per_section),
        _build_top_in_genre(session, profile, limit_per_section),
        _build_want_to_read_picks(session, profile, limit_per_section),
        _build_readers_like_you(session, profile, limit_per_section),
        _build_hidden_gems(session, profile, limit_per_section),
        return_exceptions=True,
    )

    user_id = profile["user_id"]
    section_names = [
        "for_you", "because_you_liked", "continue_series", "from_favorite_authors",
        "top_in_your_genres", "want_to_read_picks", "readers_like_you", "hidden_gems",
    ]
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[rec:personal:{user_id}] {section_names[i]} failed: {result}")

    def safe(result: typing.Any) -> typing.Any:
        return result if not isinstance(result, Exception) else None

    for_you_items = safe(results[0]) or []
    because_result = safe(results[1])
    because_items, anchor_title = because_result if because_result else ([], "")
    continue_items = safe(results[2]) or []
    fav_author_items = safe(results[3]) or []
    top_genre_result = safe(results[4])
    top_genre_items, genre_slug = top_genre_result if top_genre_result else ([], "")
    want_to_read_items = safe(results[5]) or []
    readers_like_items = safe(results[6]) or []
    hidden_gems_items = safe(results[7]) or []

    sections: typing.List[typing.Dict[str, typing.Any]] = []

    if for_you_items:
        sections.append(
            _make_home_section("for_you", "Recommended For You", "book", for_you_items)
        )
    if because_items and anchor_title:
        sections.append(
            _make_home_section(
                "because_you_liked",
                f"Because You Liked {anchor_title}",
                "book",
                because_items,
            )
        )
    if continue_items:
        sections.append(
            _make_home_section(
                "continue_series", "Continue Your Series", "book", continue_items
            )
        )
    if fav_author_items:
        sections.append(
            _make_home_section(
                "from_favorite_authors",
                "From Authors You Love",
                "book",
                fav_author_items,
            )
        )
    if top_genre_items and genre_slug:
        display_genre = genre_slug.replace("-", " ").title()
        sections.append(
            _make_home_section(
                "top_in_your_genres", f"Top in {display_genre}", "book", top_genre_items
            )
        )
    if want_to_read_items:
        sections.append(
            _make_home_section(
                "want_to_read_picks",
                "From Your Want-to-Read",
                "book",
                want_to_read_items,
            )
        )
    if readers_like_items:
        sections.append(
            _make_home_section(
                "readers_like_you",
                "Readers Like You Enjoyed",
                "book",
                readers_like_items,
            )
        )
    if hidden_gems_items:
        sections.append(
            _make_home_section(
                "hidden_gems", "Hidden Gems For You", "book", hidden_gems_items
            )
        )

    return sections


async def build_personal_book_sections(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    profile: typing.Dict[str, typing.Any],
    limit_per_section: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    items = await _build_you_might_like(session, book_id, profile, limit_per_section)
    if not items:
        return []
    return [_make_book_page_section("you_might_like", "You Might Also Like", items)]


async def build_personal_author_sections(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
    profile: typing.Dict[str, typing.Any],
    limit_per_section: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    items = await _build_unread_by_author(
        session, author_id, profile, limit_per_section
    )
    if not items:
        return []
    return [
        _make_book_page_section("unread_by_author", "Books You Haven't Read", items)
    ]
