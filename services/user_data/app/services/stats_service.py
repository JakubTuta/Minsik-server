import typing
import sqlalchemy
import sqlalchemy.ext.asyncio
import app.models.user_stats


async def recalculate_bookshelf_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int
) -> None:
    await session.execute(sqlalchemy.text("""
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
    """), {"user_id": user_id})


async def recalculate_rating_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int
) -> None:
    await session.execute(sqlalchemy.text("""
        INSERT INTO user_data.user_stats (user_id, ratings_count)
        SELECT :user_id, COUNT(*) FROM user_data.ratings WHERE user_id = :user_id
        ON CONFLICT (user_id) DO UPDATE SET ratings_count = EXCLUDED.ratings_count
    """), {"user_id": user_id})


async def recalculate_comment_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int
) -> None:
    await session.execute(sqlalchemy.text("""
        INSERT INTO user_data.user_stats (user_id, comments_count)
        SELECT :user_id, COUNT(*) FROM user_data.comments
        WHERE user_id = :user_id
        ON CONFLICT (user_id) DO UPDATE SET comments_count = EXCLUDED.comments_count
    """), {"user_id": user_id})


async def get_user_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int
) -> typing.Optional[app.models.user_stats.UserStats]:
    stmt = sqlalchemy.select(app.models.user_stats.UserStats).where(
        app.models.user_stats.UserStats.user_id == user_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
