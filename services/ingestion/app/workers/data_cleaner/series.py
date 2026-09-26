import logging
import typing

import app.models.series
import app.utils
import app.workers.data_cleaner.rules as rules
import app.workers.data_cleaner.runtime as runtime
import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.engine
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_CLEAR_SERIES_SQL = """
    UPDATE books.books
    SET series_id = NULL, series_slug = NULL, series_name = NULL, series_position = NULL
    WHERE book_id = ANY(:book_ids)
"""


def _clear_junk_descriptors_step(
    batch_size: int,
) -> runtime.BatchStep:
    cursor = 0
    query = sqlalchemy.text(
        """
        SELECT book_id FROM books.books
        WHERE book_id > :cursor
          AND series_slug IS NOT NULL
          AND (
            series_name IS NULL
            OR btrim(series_name, :junk_chars) !~ '[A-Za-z]'
            OR """
        + rules.outside_parentheses("series_name")
        + """ ~* :collection_pattern
          )
        ORDER BY book_id
        LIMIT :batch_size
        """
    )

    async def step(
        session: sqlalchemy.ext.asyncio.AsyncSession,
    ) -> typing.Tuple[int, bool]:
        nonlocal cursor
        result = await session.execute(
            query,
            {
                "cursor": cursor,
                "junk_chars": rules.NAME_JUNK_CHARS,
                "collection_pattern": rules.COLLECTION_NAME_PATTERN,
                "batch_size": batch_size,
            },
        )
        book_ids = [row[0] for row in result.fetchall()]
        if not book_ids:
            return 0, False

        cursor = book_ids[-1]
        await session.execute(sqlalchemy.text(_CLEAR_SERIES_SQL), {"book_ids": book_ids})
        return len(book_ids), True

    return step


def _renormalize_step(batch_size: int) -> runtime.BatchStep:
    cursor = ""
    query = sqlalchemy.text(
        """
        SELECT DISTINCT series_slug, series_name
        FROM books.books
        WHERE series_slug IS NOT NULL AND series_name IS NOT NULL AND series_slug > :cursor
        ORDER BY series_slug
        LIMIT :batch_size
        """
    )
    update = sqlalchemy.text(
        """
        UPDATE books.books
        SET series_slug = :new_slug,
            series_name = :new_name,
            series_position = COALESCE(series_position, :parsed_pos)
        WHERE series_slug = :old_slug AND series_name = :old_name
        """
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
        renamed = 0
        for old_slug, old_name in rows:
            parsed = app.utils.parse_series_descriptor(old_name)
            if not parsed:
                continue
            canonical_name = parsed["name"]
            canonical_slug = app.utils.slugify(canonical_name)
            if canonical_slug == old_slug and canonical_name == old_name:
                continue
            await session.execute(
                update,
                {
                    "new_slug": canonical_slug,
                    "new_name": canonical_name,
                    "old_slug": old_slug,
                    "old_name": old_name,
                    "parsed_pos": parsed.get("position"),
                },
            )
            renamed += 1

        return renamed, True

    return step


async def _upsert_series_rows(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    groups: typing.List[typing.Dict[str, typing.Any]],
) -> typing.Tuple[typing.Dict[typing.Tuple[str, str], int], int]:
    if not groups:
        return {}, 0

    values = sorted(
        (
            {"name": g["name"], "slug": g["slug"], "language": g["language"]}
            for g in groups
        ),
        key=lambda row: (row["slug"], row["language"]),
    )
    stmt = sqlalchemy.dialects.postgresql.insert(app.models.series.Series).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["slug", "language"], set_={"name": stmt.excluded.name}
    )
    stmt = stmt.returning(
        app.models.series.Series.slug,
        app.models.series.Series.language,
        app.models.series.Series.series_id,
        (sqlalchemy.column("xmax") == 0).label("inserted"),
    )
    result = await session.execute(stmt)

    pair_to_id: typing.Dict[typing.Tuple[str, str], int] = {}
    created = 0
    for row in result:
        pair_to_id[(row.slug, row.language)] = row.series_id
        if row.inserted:
            created += 1
    return pair_to_id, created


def _link_step(
    min_books: int,
    max_books: int,
    min_ol_engagement: int,
    batch_size: int,
    stats: typing.Dict[str, int],
) -> runtime.BatchStep:
    cursor = ("", "")
    query = sqlalchemy.text(
        """
        SELECT series_slug, language, COUNT(*) AS book_count, MIN(series_name) AS rep_name,
               COALESCE(SUM(
                   COALESCE(ol_rating_count, 0) + COALESCE(ol_want_to_read_count, 0)
                   + COALESCE(ol_currently_reading_count, 0) + COALESCE(ol_already_read_count, 0)
               ), 0) AS engagement
        FROM books.books
        WHERE series_slug IS NOT NULL AND (series_slug, language) > (:cursor_slug, :cursor_lang)
        GROUP BY series_slug, language
        ORDER BY series_slug, language
        LIMIT :batch_size
        """
    )
    link = sqlalchemy.text(
        """
        UPDATE books.books
        SET series_id = :series_id
        WHERE series_slug = :slug AND language = :language AND series_id IS DISTINCT FROM :series_id
        """
    )
    unlink = sqlalchemy.text(
        """
        UPDATE books.books
        SET series_id = NULL
        WHERE series_slug = :slug AND language = :language AND series_id IS NOT NULL
        """
    )

    async def step(
        session: sqlalchemy.ext.asyncio.AsyncSession,
    ) -> typing.Tuple[int, bool]:
        nonlocal cursor
        result = await session.execute(
            query,
            {
                "cursor_slug": cursor[0],
                "cursor_lang": cursor[1],
                "batch_size": batch_size,
            },
        )
        rows = result.fetchall()
        if not rows:
            return 0, False

        cursor = (rows[-1][0], rows[-1][1])
        qualifying: typing.List[typing.Dict[str, typing.Any]] = []
        disqualifying: typing.List[typing.Dict[str, str]] = []

        for slug, language, book_count, rep_name, engagement in rows:
            if (
                min_books <= book_count <= max_books
                and engagement >= min_ol_engagement
            ):
                qualifying.append(
                    {"slug": slug, "language": language, "name": rep_name or slug}
                )
            else:
                disqualifying.append({"slug": slug, "language": language})

        pair_to_id, created = await _upsert_series_rows(session, qualifying)
        stats["rows_created"] += created

        for group in qualifying:
            series_id = pair_to_id.get((group["slug"], group["language"]))
            if series_id is None:
                continue
            link_result = await session.execute(
                link,
                {
                    "series_id": series_id,
                    "slug": group["slug"],
                    "language": group["language"],
                },
            )
            stats["linked"] += typing.cast(
                sqlalchemy.engine.CursorResult, link_result
            ).rowcount

        for group in disqualifying:
            unlink_result = await session.execute(unlink, group)
            stats["unlinked"] += typing.cast(
                sqlalchemy.engine.CursorResult, unlink_result
            ).rowcount

        return len(rows), True

    return step


async def _prune_series_rows(
    session_factory: runtime.SessionFactory,
) -> int:
    try:
        async with session_factory() as session:
            delete_result = await session.execute(
                sqlalchemy.text(
                    """
                    DELETE FROM books.series
                    WHERE NOT EXISTS (
                        SELECT 1 FROM books.books b WHERE b.series_id = books.series.series_id
                    )
                    """
                )
            )
            await session.execute(
                sqlalchemy.text(
                    """
                    UPDATE books.series s
                    SET total_books = (
                        SELECT COUNT(*) FROM books.books b WHERE b.series_id = s.series_id
                    )
                    WHERE s.total_books IS DISTINCT FROM (
                        SELECT COUNT(*) FROM books.books b WHERE b.series_id = s.series_id
                    )
                    """
                )
            )
            await session.commit()
            return typing.cast(sqlalchemy.engine.CursorResult, delete_result).rowcount
    except Exception as e:
        logger.error(f"[cleanup] Series pruning failed: {e}")
        return 0


async def consolidate_series(
    session_factory: runtime.SessionFactory,
    min_books: int,
    max_books: int,
    batch_size: int,
    min_ol_engagement: int = 0,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    stats = {
        "descriptors_cleared": 0,
        "renamed": 0,
        "linked": 0,
        "unlinked": 0,
        "rows_created": 0,
        "rows_deleted": 0,
    }

    stats["descriptors_cleared"] = await runtime.run_batches(
        session_factory,
        "junk series descriptors cleared",
        _clear_junk_descriptors_step(batch_size),
        stop_check,
    )

    stats["renamed"] = await runtime.run_batches(
        session_factory,
        "series descriptors renormalized",
        _renormalize_step(batch_size),
        stop_check,
    )

    await runtime.run_batches(
        session_factory,
        "series groups evaluated",
        _link_step(min_books, max_books, min_ol_engagement, batch_size, stats),
        stop_check,
    )

    stats["rows_deleted"] = await _prune_series_rows(session_factory)

    logger.info(
        f"[cleanup] Series consolidation complete: linked={stats['linked']}, "
        f"unlinked={stats['unlinked']}, rows_created={stats['rows_created']}, "
        f"rows_deleted={stats['rows_deleted']}, "
        f"descriptors_cleared={stats['descriptors_cleared']}"
    )
    return stats
