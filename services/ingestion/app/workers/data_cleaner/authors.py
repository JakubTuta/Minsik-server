import typing

import app.workers.data_cleaner.books as books
import app.workers.data_cleaner.rules as rules
import app.workers.data_cleaner.runtime as runtime
import sqlalchemy
import sqlalchemy.engine
import sqlalchemy.ext.asyncio

_SOLE_BOOK_SUB_BATCH = 100

_AUTHOR_BOOK_COUNT_SQL = (
    "(SELECT COUNT(*) FROM books.book_authors ba WHERE ba.author_id = a.author_id)"
)


async def delete_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_ids: typing.List[int],
) -> int:
    if not author_ids:
        return 0

    sole_book_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT ba.book_id
            FROM books.book_authors ba
            JOIN books.books b ON b.book_id = ba.book_id
            WHERE ba.author_id = ANY(:author_ids)
              AND (SELECT COUNT(*) FROM books.book_authors ba2 WHERE ba2.book_id = ba.book_id) = 1
              AND """
            + rules.BOOK_UNTOUCHED_BY_USERS_SQL
        ),
        {"author_ids": author_ids},
    )
    sole_book_ids = [row[0] for row in sole_book_result.fetchall()]

    for i in range(0, len(sole_book_ids), _SOLE_BOOK_SUB_BATCH):
        await books.delete_books(
            session, sole_book_ids[i : i + _SOLE_BOOK_SUB_BATCH]
        )

    result = await session.execute(
        sqlalchemy.text("DELETE FROM books.authors WHERE author_id = ANY(:author_ids)"),
        {"author_ids": author_ids},
    )
    return typing.cast(sqlalchemy.engine.CursorResult, result).rowcount


def _delete_step(
    predicate_sql: str,
    params: typing.Dict[str, typing.Any],
    batch_size: int,
) -> runtime.BatchStep:
    cursor = 0
    query = sqlalchemy.text(
        "SELECT a.author_id FROM books.authors a WHERE a.author_id > :cursor AND ("
        + predicate_sql
        + ") ORDER BY a.author_id LIMIT :batch_size"
    )

    async def step(
        session: sqlalchemy.ext.asyncio.AsyncSession,
    ) -> typing.Tuple[int, bool]:
        nonlocal cursor
        result = await session.execute(
            query, {**params, "cursor": cursor, "batch_size": batch_size}
        )
        author_ids = [row[0] for row in result.fetchall()]
        if not author_ids:
            return 0, False
        cursor = author_ids[-1]
        return await delete_authors(session, author_ids), True

    return step


async def cleanup_orphan_authors(
    session_factory: runtime.SessionFactory,
    min_books: int,
    max_books: int,
    batch_size: int,
    junk_publisher_names: bool,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    predicate = (
        _AUTHOR_BOOK_COUNT_SQL
        + " < :min_books OR "
        + _AUTHOR_BOOK_COUNT_SQL
        + " > :max_books OR "
        + rules.AUTHOR_JUNK_NAME_SQL
        + " OR (:junk_publisher_names AND a.name ~* :junk_publisher_pattern)"
    )
    step = _delete_step(
        predicate,
        {
            "min_books": min_books,
            "max_books": max_books,
            "junk_publisher_names": junk_publisher_names,
            "junk_publisher_pattern": rules.JUNK_PUBLISHER_NAME_PATTERN,
        },
        batch_size,
    )
    deleted = await runtime.run_batches(
        session_factory, "low-relevance authors deleted", step, stop_check
    )
    return {"deleted": deleted}


async def cleanup_collection_authors(
    session_factory: runtime.SessionFactory,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    predicate = (
        rules.COLLECTIVE_AUTHOR_SQL
        + " OR "
        + rules.outside_parentheses("a.name")
        + " ~* :collection_pattern"
    )
    step = _delete_step(
        predicate,
        {
            "collective_pattern": rules.COLLECTIVE_AUTHOR_PATTERN,
            "merged_entry_pattern": rules.MERGED_AUTHOR_ENTRY_PATTERN,
            "collection_pattern": rules.COLLECTION_NAME_PATTERN,
        },
        batch_size,
    )
    deleted = await runtime.run_batches(
        session_factory, "collective/collection authors deleted", step, stop_check
    )
    return {"deleted": deleted}


async def cleanup_low_engagement_authors(
    session_factory: runtime.SessionFactory,
    min_ol_engagement: int,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    predicate = (
        rules.AUTHOR_DELETABLE_SQL
        + " AND "
        + rules.LOW_ENGAGEMENT_AUTHOR_SQL
    )
    step = _delete_step(predicate, {"min_engagement": min_ol_engagement}, batch_size)
    deleted = await runtime.run_batches(
        session_factory, "low-engagement authors deleted", step, stop_check
    )
    return {"deleted": deleted}
