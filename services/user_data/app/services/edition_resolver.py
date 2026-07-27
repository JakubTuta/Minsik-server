import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

# The order every language-dependent pick in the app follows: the reader's
# language, then English, then the edition the most people rated, then a stable
# id so the answer never depends on the planner.
EDITION_PREFERENCE = (
    "(%(alias)s.language = :language) DESC, (%(alias)s.language = 'en') DESC, "
    "(COALESCE(%(alias)s.rating_count, 0) + COALESCE(%(alias)s.ol_rating_count, 0)) DESC, "
    "%(alias)s.book_id ASC"
)


def edition_preference(alias: str = "b") -> str:
    return EDITION_PREFERENCE % {"alias": alias}


_SLUG_ROW_QUERY = f"""
    SELECT b.book_id, b.work_id, b.slug, b.title, b.primary_cover_url,
           s.name AS series_name, s.slug AS series_slug
    FROM books.books b
    LEFT JOIN books.series s ON s.series_id = b.series_id
    WHERE b.slug = :slug
    ORDER BY {edition_preference()}
    LIMIT 1
"""

# For a list, the row's own edition is an accident of which page the user was on
# when they shelved or rated it, so each entry is re-resolved to the edition of
# the same work that this reader should see.
_WORK_EDITION_QUERY = f"""
    WITH requested AS (
        SELECT book_id AS requested_id, work_id
        FROM books.books
        WHERE book_id = ANY(:ids)
    )
    SELECT
        r.requested_id,
        e.book_id, e.slug, e.title, e.primary_cover_url,
        s.name AS series_name, s.slug AS series_slug
    FROM requested r
    JOIN LATERAL (
        SELECT b.book_id, b.slug, b.title, b.primary_cover_url, b.series_id
        FROM books.books b
        WHERE b.work_id = r.work_id
        ORDER BY {edition_preference()}
        LIMIT 1
    ) e ON TRUE
    LEFT JOIN books.series s ON s.series_id = e.series_id
"""

# Inline form of the same pick, for queries that already have a shelved/rated
# row in scope. Requires an outer `books.books sb` alias to hang the work off
# and a `:language` parameter.
PREFERRED_EDITION_LATERAL = f"""
    SELECT b.book_id, b.slug, b.title, b.primary_cover_url,
           b.number_of_pages, b.series_id
    FROM books.books b
    WHERE b.work_id = sb.work_id
    ORDER BY {edition_preference()}
    LIMIT 1
"""

_AUTHORS_QUERY = """
    SELECT ba.book_id, a.name, a.slug
    FROM books.book_authors ba
    JOIN books.authors a ON a.author_id = ba.author_id
    WHERE ba.book_id = ANY(:ids)
    ORDER BY ba.book_id
"""


def _row_to_meta(row: typing.Any) -> typing.Dict[str, typing.Any]:
    return {
        "book_id": row.book_id,
        "slug": row.slug or "",
        "title": row.title or "",
        "cover_url": row.primary_cover_url or "",
        "series_name": row.series_name or "",
        "series_slug": row.series_slug or "",
        "author_names": [],
        "author_slugs": [],
    }


async def _attach_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    metas: typing.Iterable[typing.Dict[str, typing.Any]],
) -> None:
    by_book: typing.Dict[int, typing.List[typing.Dict[str, typing.Any]]] = {}
    for meta in metas:
        by_book.setdefault(meta["book_id"], []).append(meta)

    if not by_book:
        return

    result = await session.execute(
        sqlalchemy.text(_AUTHORS_QUERY), {"ids": list(by_book)}
    )
    for row in result.fetchall():
        for meta in by_book.get(row.book_id, []):
            meta["author_names"].append(row.name)
            meta["author_slugs"].append(row.slug)


async def resolve_book(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, language: str
) -> typing.Dict[str, typing.Any]:
    """The edition a slug names, with the language only breaking ties.

    A slug is unique per language, not globally, so two unrelated editions can
    carry the same one. This stays on the edition the reader is actually
    looking at rather than hopping to another translation of the same work.
    """
    result = await session.execute(
        sqlalchemy.text(_SLUG_ROW_QUERY), {"slug": slug, "language": language}
    )
    row = result.fetchone()
    if row is None:
        raise ValueError("book_not_found")

    meta = _row_to_meta(row)
    meta["work_id"] = row.work_id
    await _attach_authors(session, [meta])

    return meta


async def resolve_work_id(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, language: str
) -> typing.Optional[str]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT work_id FROM books.books b
            WHERE b.slug = :slug
            ORDER BY {edition_preference()}
            LIMIT 1
            """
        ),
        {"slug": slug, "language": language},
    )
    row = result.fetchone()

    return row.work_id if row else None


async def book_meta_map(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_ids: typing.List[int],
    language: str,
) -> typing.Dict[int, typing.Dict[str, typing.Any]]:
    """Per stored book_id, the edition of that work this reader should see."""
    if not book_ids:
        return {}

    result = await session.execute(
        sqlalchemy.text(_WORK_EDITION_QUERY),
        {"ids": list(set(book_ids)), "language": language},
    )

    metas = {row.requested_id: _row_to_meta(row) for row in result.fetchall()}
    await _attach_authors(session, metas.values())

    return metas
