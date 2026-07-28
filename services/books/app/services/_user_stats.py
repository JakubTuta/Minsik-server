import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

# Three set-based statements for the whole batch rather than three per user:
# deleting a popular book touches every reader who shelved it, which was
# thousands of round trips inside one request.
_BOOKSHELF_STATS_SQL = """
    INSERT INTO user_data.user_stats (user_id, want_to_read_count, reading_count, read_count, abandoned_count, favourites_count)
    SELECT
        u.user_id,
        COUNT(*) FILTER (WHERE bs.status = 'want_to_read'),
        COUNT(*) FILTER (WHERE bs.status = 'reading'),
        COUNT(*) FILTER (WHERE bs.status = 'read'),
        COUNT(*) FILTER (WHERE bs.status = 'abandoned'),
        COUNT(*) FILTER (WHERE bs.is_favorite)
    FROM UNNEST(CAST(:user_ids AS bigint[])) AS u(user_id)
    LEFT JOIN user_data.bookshelves bs ON bs.user_id = u.user_id
    GROUP BY u.user_id
    ON CONFLICT (user_id) DO UPDATE SET
        want_to_read_count = EXCLUDED.want_to_read_count,
        reading_count      = EXCLUDED.reading_count,
        read_count         = EXCLUDED.read_count,
        abandoned_count    = EXCLUDED.abandoned_count,
        favourites_count   = EXCLUDED.favourites_count
"""

_RATING_STATS_SQL = """
    INSERT INTO user_data.user_stats (user_id, ratings_count)
    SELECT u.user_id, COUNT(r.rating_id)
    FROM UNNEST(CAST(:user_ids AS bigint[])) AS u(user_id)
    LEFT JOIN user_data.ratings r ON r.user_id = u.user_id
    GROUP BY u.user_id
    ON CONFLICT (user_id) DO UPDATE SET ratings_count = EXCLUDED.ratings_count
"""

_COMMENT_STATS_SQL = """
    INSERT INTO user_data.user_stats (user_id, comments_count)
    SELECT u.user_id, COUNT(c.comment_id)
    FROM UNNEST(CAST(:user_ids AS bigint[])) AS u(user_id)
    LEFT JOIN user_data.comments c ON c.user_id = u.user_id
    GROUP BY u.user_id
    ON CONFLICT (user_id) DO UPDATE SET comments_count = EXCLUDED.comments_count
"""


async def recalculate(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_ids: typing.Iterable[int],
) -> None:
    """Refresh user_data.user_stats for users whose bookshelves/ratings/comments changed underneath them.

    Used after a cascading delete (book or author removal) rather than being
    incremental, since the rows behind the count were just deleted in bulk.
    """
    distinct_user_ids = list({int(user_id) for user_id in user_ids})
    if not distinct_user_ids:
        return

    for statement in (_BOOKSHELF_STATS_SQL, _RATING_STATS_SQL, _COMMENT_STATS_SQL):
        await session.execute(
            sqlalchemy.text(statement), {"user_ids": distinct_user_ids}
        )
