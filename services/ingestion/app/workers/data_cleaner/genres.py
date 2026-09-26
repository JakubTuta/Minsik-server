import typing

import app.utils
import app.workers.data_cleaner.rules as rules
import app.workers.data_cleaner.runtime as runtime
import sqlalchemy
import sqlalchemy.engine
import sqlalchemy.ext.asyncio

_MERGE_BOOK_GENRES_SQL = """
    INSERT INTO books.book_genres (book_id, genre_id)
    SELECT book_id, :canonical_id FROM books.book_genres WHERE genre_id = :old_id
    ON CONFLICT DO NOTHING
"""


def _delete_step(
    predicate_sql: str,
    params: typing.Dict[str, typing.Any],
    batch_size: int,
) -> runtime.BatchStep:
    query = sqlalchemy.text(
        "DELETE FROM books.genres WHERE genre_id IN ("
        " SELECT g.genre_id FROM books.genres g WHERE "
        + predicate_sql
        + " LIMIT :batch_size)"
    )

    async def step(
        session: sqlalchemy.ext.asyncio.AsyncSession,
    ) -> typing.Tuple[int, bool]:
        result = await session.execute(query, {**params, "batch_size": batch_size})
        deleted = typing.cast(sqlalchemy.engine.CursorResult, result).rowcount
        return deleted, deleted > 0

    return step


def _normalize_step(batch_size: int) -> runtime.BatchStep:
    cursor = 0
    query = sqlalchemy.text(
        "SELECT genre_id, name, slug FROM books.genres WHERE genre_id > :cursor"
        " ORDER BY genre_id LIMIT :batch_size"
    )

    async def step(
        session: sqlalchemy.ext.asyncio.AsyncSession,
    ) -> typing.Tuple[int, bool]:
        nonlocal cursor
        result = await session.execute(
            query, {"cursor": cursor, "batch_size": batch_size}
        )
        rows = result.fetchall()
        if not rows:
            return 0, False

        cursor = rows[-1][0]
        merged = 0
        for genre_id, name, slug in rows:
            canonical_name, canonical_slug = app.utils.canonicalize_genre_name(name)
            if canonical_slug == slug:
                continue

            canonical_result = await session.execute(
                sqlalchemy.text(
                    "SELECT genre_id FROM books.genres WHERE slug = :slug"
                ),
                {"slug": canonical_slug},
            )
            canonical_row = canonical_result.fetchone()

            if canonical_row is None:
                await session.execute(
                    sqlalchemy.text(
                        "UPDATE books.genres SET name = :name, slug = :slug WHERE genre_id = :genre_id"
                    ),
                    {
                        "name": canonical_name[:100],
                        "slug": canonical_slug[:150],
                        "genre_id": genre_id,
                    },
                )
            elif canonical_row[0] != genre_id:
                await session.execute(
                    sqlalchemy.text(_MERGE_BOOK_GENRES_SQL),
                    {"canonical_id": canonical_row[0], "old_id": genre_id},
                )
                await session.execute(
                    sqlalchemy.text(
                        "DELETE FROM books.genres WHERE genre_id = :genre_id"
                    ),
                    {"genre_id": genre_id},
                )
            else:
                continue

            merged += 1

        return merged, True

    return step


async def normalize_and_merge_genres(
    session_factory: runtime.SessionFactory,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> int:
    return await runtime.run_batches(
        session_factory,
        "genres normalized",
        _normalize_step(batch_size),
        stop_check,
    )


async def cleanup_orphan_genres(
    session_factory: runtime.SessionFactory,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> int:
    predicate = (
        "NOT EXISTS (SELECT 1 FROM books.book_genres bg WHERE bg.genre_id = g.genre_id)"
    )
    return await runtime.run_batches(
        session_factory,
        "orphan genres deleted",
        _delete_step(predicate, {}, batch_size),
        stop_check,
    )


async def cleanup_underrepresented_genres(
    session_factory: runtime.SessionFactory,
    min_book_count: int,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> int:
    predicate = (
        "(SELECT COUNT(*) FROM books.book_genres bg WHERE bg.genre_id = g.genre_id)"
        " <= :min_book_count"
    )
    return await runtime.run_batches(
        session_factory,
        "underrepresented genres deleted",
        _delete_step(predicate, {"min_book_count": min_book_count}, batch_size),
        stop_check,
    )


async def cleanup_invalid_genre_names(
    session_factory: runtime.SessionFactory,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> int:
    predicate = (
        "g.name ~ '[^a-zA-Z0-9 -]' OR g.name ~ '^[0-9]+$' OR char_length(g.name) > 40"
    )
    return await runtime.run_batches(
        session_factory,
        "invalid-name genres deleted",
        _delete_step(predicate, {}, batch_size),
        stop_check,
    )


async def cleanup_junk_genres(
    session_factory: runtime.SessionFactory,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> int:
    return await runtime.run_batches(
        session_factory,
        "junk genres deleted",
        _delete_step(
            "g.name ~* :junk_pattern",
            {"junk_pattern": rules.JUNK_GENRE_NAME_PATTERN},
            batch_size,
        ),
        stop_check,
    )
