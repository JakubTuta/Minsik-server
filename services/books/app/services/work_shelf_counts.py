import logging

import app.db
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

# Shelf counts pooled per work rather than per edition: a reader who shelved
# two translations is one reader of one work. Computing this inline made every
# list query aggregate the whole of user_data.bookshelves, so it lives in
# books.work_shelf_counts and every list joins it by work_id instead.
#
# Rebuilt wholesale rather than maintained incrementally: the full rebuild is
# a single pass costing about as much as one of the queries it replaced, and a
# rebuild can never drift, so no reconciliation path is needed.
_REBUILD_SQL = """
    INSERT INTO books.work_shelf_counts
        (work_id, want_to_read_count, reading_count, read_count, abandoned_count,
         readers, updated_at)
    SELECT
        wb.work_id,
        COUNT(DISTINCT bsh.user_id) FILTER (WHERE bsh.status = 'want_to_read'),
        COUNT(DISTINCT bsh.user_id) FILTER (WHERE bsh.status = 'reading'),
        COUNT(DISTINCT bsh.user_id) FILTER (WHERE bsh.status = 'read'),
        COUNT(DISTINCT bsh.user_id) FILTER (WHERE bsh.status = 'abandoned'),
        COUNT(DISTINCT bsh.user_id),
        NOW()
    FROM user_data.bookshelves bsh
    JOIN books.books wb ON wb.book_id = bsh.book_id
    GROUP BY wb.work_id
    ON CONFLICT (work_id) DO UPDATE SET
        want_to_read_count = EXCLUDED.want_to_read_count,
        reading_count      = EXCLUDED.reading_count,
        read_count         = EXCLUDED.read_count,
        abandoned_count    = EXCLUDED.abandoned_count,
        readers            = EXCLUDED.readers,
        updated_at         = EXCLUDED.updated_at
"""

# Works whose last shelf row was removed keep a stale non-zero count unless
# they are cleared; the rebuild only visits works that still have shelf rows.
_ZERO_EMPTIED_SQL = """
    UPDATE books.work_shelf_counts w
    SET want_to_read_count = 0, reading_count = 0, read_count = 0,
        abandoned_count = 0, readers = 0, updated_at = NOW()
    WHERE w.readers <> 0
      AND NOT EXISTS (
          SELECT 1
          FROM books.books b
          JOIN user_data.bookshelves bsh ON bsh.book_id = b.book_id
          WHERE b.work_id = w.work_id
      )
"""


async def rebuild(session: sqlalchemy.ext.asyncio.AsyncSession) -> int:
    result = await session.execute(sqlalchemy.text(_REBUILD_SQL))
    rebuilt = result.rowcount or 0
    await session.execute(sqlalchemy.text(_ZERO_EMPTIED_SQL))
    await session.commit()
    return rebuilt


async def rebuild_job() -> None:
    try:
        async with app.db.async_session_maker() as session:
            rebuilt = await rebuild(session)
        logger.info(f"[books] Rebuilt work shelf counts for {rebuilt} works")
    except Exception as e:
        logger.error(f"[books] Work shelf counts rebuild error: {str(e)}")


async def populate_if_empty() -> None:
    """First fill after the table is created, so lists don't show zero readers
    until the first scheduled rebuild."""
    try:
        async with app.db.async_session_maker() as session:
            existing = await session.execute(
                sqlalchemy.text("SELECT 1 FROM books.work_shelf_counts LIMIT 1")
            )
            if existing.first() is not None:
                return
            rebuilt = await rebuild(session)
        logger.info(f"[books] Initial work shelf counts built for {rebuilt} works")
    except Exception as e:
        logger.error(f"[books] Initial work shelf counts build error: {str(e)}")
