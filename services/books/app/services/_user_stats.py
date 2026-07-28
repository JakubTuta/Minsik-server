import typing

import sqlalchemy
import sqlalchemy.ext.asyncio


async def recalculate(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_ids: typing.Iterable[int],
) -> None:
    """Refresh user_data.user_stats for users whose bookshelves/ratings/comments changed underneath them.

    Used after a cascading delete (book or author removal) rather than being
    incremental, since the rows behind the count were just deleted in bulk.
    """
    for user_id in user_ids:
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, want_to_read_count, reading_count, read_count, abandoned_count, favourites_count)
                SELECT
                    :user_id,
                    COUNT(CASE WHEN status = 'want_to_read' THEN 1 END),
                    COUNT(CASE WHEN status = 'reading'      THEN 1 END),
                    COUNT(CASE WHEN status = 'read'         THEN 1 END),
                    COUNT(CASE WHEN status = 'abandoned'    THEN 1 END),
                    COUNT(CASE WHEN is_favorite             THEN 1 END)
                FROM user_data.bookshelves
                WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET
                    want_to_read_count = EXCLUDED.want_to_read_count,
                    reading_count      = EXCLUDED.reading_count,
                    read_count         = EXCLUDED.read_count,
                    abandoned_count    = EXCLUDED.abandoned_count,
                    favourites_count   = EXCLUDED.favourites_count
                """
            ),
            {"user_id": user_id},
        )
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, ratings_count)
                SELECT :user_id, COUNT(*) FROM user_data.ratings WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET ratings_count = EXCLUDED.ratings_count
                """
            ),
            {"user_id": user_id},
        )
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, comments_count)
                SELECT :user_id, COUNT(*) FROM user_data.comments WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET comments_count = EXCLUDED.comments_count
                """
            ),
            {"user_id": user_id},
        )
