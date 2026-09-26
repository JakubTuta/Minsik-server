import typing

import sqlalchemy
import sqlalchemy.ext.asyncio


async def delete_book_user_data(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_ids: typing.List[int],
) -> typing.List[int]:
    if not book_ids:
        return []

    affected_users_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT DISTINCT user_id FROM user_data.bookshelves WHERE book_id = ANY(:book_ids)
            UNION
            SELECT DISTINCT user_id FROM user_data.ratings WHERE book_id = ANY(:book_ids)
            UNION
            SELECT DISTINCT user_id FROM user_data.comments WHERE book_id = ANY(:book_ids)
            """
        ),
        {"book_ids": book_ids},
    )
    affected_user_ids = [row[0] for row in affected_users_result.fetchall()]

    for table in ("comments", "ratings", "bookshelves"):
        await session.execute(
            sqlalchemy.text(
                f"DELETE FROM user_data.{table} WHERE book_id = ANY(:book_ids)"
            ),
            {"book_ids": book_ids},
        )

    return affected_user_ids


async def remap_book_user_data(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    loser_book_id: int,
    winner_book_id: int,
) -> typing.List[int]:
    affected_users_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT DISTINCT user_id FROM user_data.bookshelves WHERE book_id = :loser_id
            UNION
            SELECT DISTINCT user_id FROM user_data.ratings WHERE book_id = :loser_id
            UNION
            SELECT DISTINCT user_id FROM user_data.comments WHERE book_id = :loser_id
            """
        ),
        {"loser_id": loser_book_id},
    )
    affected_user_ids = [row[0] for row in affected_users_result.fetchall()]

    for table in ("bookshelves", "ratings", "comments"):
        await session.execute(
            sqlalchemy.text(
                f"""
                DELETE FROM user_data.{table} loser
                WHERE loser.book_id = :loser_id
                  AND EXISTS (
                      SELECT 1 FROM user_data.{table} winner
                      WHERE winner.user_id = loser.user_id
                        AND winner.book_id = :winner_id
                  )
                """
            ),
            {"loser_id": loser_book_id, "winner_id": winner_book_id},
        )
        await session.execute(
            sqlalchemy.text(
                f"UPDATE user_data.{table} SET book_id = :winner_id WHERE book_id = :loser_id"
            ),
            {"loser_id": loser_book_id, "winner_id": winner_book_id},
        )

    return affected_user_ids


async def recompute_user_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_ids: typing.List[int],
) -> None:
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
