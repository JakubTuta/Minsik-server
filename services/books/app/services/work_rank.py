import logging

import app.services._language_boost
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

# Popularity per work (every shelf status plus every rating), ranked 1..N. Taken per
# edition and reduced with MAX because a work's Open Library counts sit on whichever
# edition Open Library recorded them against. Rebuilt wholesale, never maintained
# incrementally, like books.work_shelf_counts that it reads.
_REBUILD_SQL = f"""
    INSERT INTO books.work_rank (work_id, popularity, rank, updated_at)
    SELECT work_id, popularity, ROW_NUMBER() OVER (ORDER BY popularity DESC, anchor_id ASC), NOW()
    FROM (
        SELECT
            b.work_id,
            MAX({app.services._language_boost.work_popularity_sql()}) AS popularity,
            MIN(b.book_id) AS anchor_id
        FROM books.books b
        {app.services._language_boost.work_shelf_counts_join()}
        GROUP BY b.work_id
    ) works
"""


async def rebuild(session: sqlalchemy.ext.asyncio.AsyncSession) -> int:
    """Replace the ranking in one transaction, so readers see the old one or the new one."""
    await session.execute(sqlalchemy.text("TRUNCATE books.work_rank"))
    result = await session.execute(sqlalchemy.text(_REBUILD_SQL))
    await session.commit()
    return result.rowcount or 0
