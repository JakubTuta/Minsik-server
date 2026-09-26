import typing

import app.workers.data_cleaner.rules as rules
import app.workers.data_cleaner.runtime as runtime
import app.workers.data_cleaner.user_data as user_data
import sqlalchemy
import sqlalchemy.engine
import sqlalchemy.ext.asyncio

_DUPLICATE_PARTITIONS: typing.Dict[str, typing.Tuple[str, str]] = {
    "title": (
        """lower(btrim(b.title)),
           b.language,
           (SELECT MIN(ba.author_id) FROM books.book_authors ba WHERE ba.book_id = b.book_id)""",
        "WHERE EXISTS (SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id)",
    ),
    "work": ("b.work_id, b.language", ""),
}


async def delete_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_ids: typing.List[int],
) -> int:
    if not book_ids:
        return 0

    affected_user_ids = await user_data.delete_book_user_data(
        session, book_ids
    )
    result = await session.execute(
        sqlalchemy.text("DELETE FROM books.books WHERE book_id = ANY(:book_ids)"),
        {"book_ids": book_ids},
    )
    await user_data.recompute_user_stats(
        session, affected_user_ids
    )
    return typing.cast(sqlalchemy.engine.CursorResult, result).rowcount


def _delete_step(
    predicate_sql: str,
    params: typing.Dict[str, typing.Any],
    batch_size: int,
) -> runtime.BatchStep:
    cursor = 0
    query = sqlalchemy.text(
        "SELECT b.book_id FROM books.books b WHERE b.book_id > :cursor AND "
        + rules.BOOK_DELETABLE_SQL
        + " AND ("
        + predicate_sql
        + ") ORDER BY b.book_id LIMIT :batch_size"
    )

    async def step(
        session: sqlalchemy.ext.asyncio.AsyncSession,
    ) -> typing.Tuple[int, bool]:
        nonlocal cursor
        result = await session.execute(
            query, {**params, "cursor": cursor, "batch_size": batch_size}
        )
        book_ids = [row[0] for row in result.fetchall()]
        if not book_ids:
            return 0, False
        cursor = book_ids[-1]
        return await delete_books(session, book_ids), True

    return step


async def cleanup_low_quality_books(
    session_factory: runtime.SessionFactory,
    min_quality_score: int,
    engagement_threshold: int,
    min_publication_year: int,
    max_title_length: int,
    ol_min_rating_count: int,
    ol_min_avg_rating: float,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    step = _delete_step(
        rules.LOW_QUALITY_BOOK_SQL,
        {
            "min_score": min_quality_score,
            "engagement": engagement_threshold,
            "min_year": min_publication_year,
            "max_title_length": max_title_length,
            "placeholder_titles": rules.PLACEHOLDER_TITLES,
            "non_book_pattern": rules.NON_BOOK_TITLE_PATTERN,
            "ol_min_rating_count": ol_min_rating_count,
            "ol_min_avg_rating": ol_min_avg_rating,
        },
        batch_size,
    )
    deleted = await runtime.run_batches(
        session_factory, "low-quality books deleted", step, stop_check
    )
    return {"deleted": deleted}


async def cleanup_low_engagement_books(
    session_factory: runtime.SessionFactory,
    min_ol_engagement: int,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    step = _delete_step(
        rules.LOW_ENGAGEMENT_BOOK_SQL,
        {"min_engagement": min_ol_engagement},
        batch_size,
    )
    deleted = await runtime.run_batches(
        session_factory, "low-engagement books deleted", step, stop_check
    )
    return {"deleted": deleted}


async def cleanup_collection_books(
    session_factory: runtime.SessionFactory,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    step = _delete_step(
        rules.COLLECTION_BOOK_SQL,
        {"collection_pattern": rules.COLLECTION_NAME_PATTERN},
        batch_size,
    )
    deleted = await runtime.run_batches(
        session_factory, "collection/omnibus books deleted", step, stop_check
    )
    return {"deleted": deleted}


async def cleanup_multi_author_books(
    session_factory: runtime.SessionFactory,
    max_authors: int,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    step = _delete_step(
        rules.MULTI_AUTHOR_BOOK_SQL,
        {"max_authors": max_authors},
        batch_size,
    )
    deleted = await runtime.run_batches(
        session_factory, "multi-author books deleted", step, stop_check
    )
    return {"deleted": deleted}


def _duplicate_step(
    partition_sql: str,
    extra_where: str,
    batch_size: int,
) -> runtime.BatchStep:
    query = sqlalchemy.text(
        f"""
        WITH ranked AS (
            SELECT
                b.book_id,
                FIRST_VALUE(b.book_id) OVER duplicates AS winner_book_id,
                ROW_NUMBER() OVER duplicates AS rn
            FROM books.books b
            {extra_where}
            WINDOW duplicates AS (
                PARTITION BY {partition_sql}
                ORDER BY
                    (b.view_count + b.rating_count + COALESCE(b.ol_rating_count, 0)) DESC,
                    b.book_id ASC
            )
        )
        SELECT book_id, winner_book_id FROM ranked WHERE rn > 1 LIMIT :batch_size
        """
    )

    async def step(
        session: sqlalchemy.ext.asyncio.AsyncSession,
    ) -> typing.Tuple[int, bool]:
        result = await session.execute(query, {"batch_size": batch_size})
        pairs = [(row[0], row[1]) for row in result.fetchall()]
        if not pairs:
            return 0, False

        affected_user_ids: typing.Set[int] = set()
        for loser_id, winner_id in pairs:
            remapped = await user_data.remap_book_user_data(
                session, loser_id, winner_id
            )
            affected_user_ids.update(remapped)

        delete_result = await session.execute(
            sqlalchemy.text("DELETE FROM books.books WHERE book_id = ANY(:book_ids)"),
            {"book_ids": [loser_id for loser_id, _ in pairs]},
        )
        await user_data.recompute_user_stats(
            session, list(affected_user_ids)
        )
        return typing.cast(sqlalchemy.engine.CursorResult, delete_result).rowcount, True

    return step


async def cleanup_duplicate_books(
    session_factory: runtime.SessionFactory,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    total_deleted = 0
    for label, (partition_sql, extra_where) in _DUPLICATE_PARTITIONS.items():
        total_deleted += await runtime.run_batches(
            session_factory,
            f"duplicate books deleted ({label})",
            _duplicate_step(partition_sql, extra_where, batch_size),
            stop_check,
        )
    return {"deleted": total_deleted}
