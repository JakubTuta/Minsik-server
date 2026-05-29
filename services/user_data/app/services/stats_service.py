import json
import typing
import sqlalchemy
import sqlalchemy.ext.asyncio
import app.models.user_stats
import datetime


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


async def get_profile_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int
) -> typing.Dict[str, typing.Any]:
    base = await get_user_stats(session, user_id)

    year_start = datetime.datetime(datetime.date.today().year, 1, 1)

    year_result = await session.execute(
        sqlalchemy.text("""
            SELECT
                COUNT(*) FILTER (WHERE bs.updated_at >= :year_start) AS finished_count,
                COALESCE(SUM(b.number_of_pages) FILTER (WHERE bs.updated_at >= :year_start), 0) AS pages_sum_year,
                COALESCE(SUM(b.number_of_pages), 0) AS pages_sum_total
            FROM user_data.bookshelves bs
            JOIN books.books b ON b.book_id = bs.book_id
            WHERE bs.user_id = :uid
              AND bs.status = 'read'
        """),
        {"uid": user_id, "year_start": year_start},
    )
    year_row = year_result.fetchone()
    finished_this_year = int(year_row.finished_count) if year_row else 0
    pages_this_year = int(year_row.pages_sum_year) if year_row else 0
    pages_total = int(year_row.pages_sum_total) if year_row else 0

    last_updated_result = await session.execute(
        sqlalchemy.text("""
            SELECT
                (SELECT MAX(updated_at) FROM user_data.bookshelves WHERE user_id = :uid) AS bookshelf_ua,
                (SELECT MAX(updated_at) FROM user_data.bookshelves WHERE user_id = :uid AND is_favorite = TRUE) AS favourites_ua,
                (SELECT MAX(updated_at) FROM user_data.comments WHERE user_id = :uid AND is_deleted = FALSE) AS comments_ua,
                (SELECT MAX(updated_at) FROM user_data.ratings WHERE user_id = :uid) AS ratings_ua
        """),
        {"uid": user_id},
    )
    lu = last_updated_result.fetchone()

    def _iso(val: typing.Optional[datetime.datetime]) -> str:
        return val.isoformat() if val else ""

    reviews_result = await session.execute(
        sqlalchemy.text("""
            SELECT COUNT(*) AS cnt
            FROM user_data.ratings
            WHERE user_id = :uid
              AND review_text IS NOT NULL
              AND btrim(review_text) <> ''
        """),
        {"uid": user_id},
    )
    reviews_row = reviews_result.fetchone()
    reviews_count = int(reviews_row.cnt) if reviews_row else 0

    rating_agg_result = await session.execute(
        sqlalchemy.text("""
            SELECT overall_rating, COUNT(*) AS cnt
            FROM user_data.ratings
            WHERE user_id = :uid
            GROUP BY overall_rating
        """),
        {"uid": user_id},
    )
    rating_rows = rating_agg_result.fetchall()
    average_rating = 0.0
    distribution: typing.Dict[str, int] = {}
    if rating_rows:
        total_cnt = sum(r.cnt for r in rating_rows)
        if total_cnt > 0:
            average_rating = float(
                sum(float(r.overall_rating) * r.cnt for r in rating_rows) / total_cnt
            )
            average_rating = round(average_rating, 2)
        for r in rating_rows:
            distribution[str(float(r.overall_rating))] = int(r.cnt)

    return {
        "want_to_read_count": base.want_to_read_count if base else 0,
        "reading_count": base.reading_count if base else 0,
        "read_count": base.read_count if base else 0,
        "abandoned_count": base.abandoned_count if base else 0,
        "favourites_count": base.favourites_count if base else 0,
        "ratings_count": base.ratings_count if base else 0,
        "comments_count": base.comments_count if base else 0,
        "finished_this_year_count": finished_this_year,
        "pages_read_this_year": pages_this_year,
        "hours_read_this_year": pages_this_year // 60,
        "pages_read_total": pages_total,
        "reviews_count": reviews_count,
        "bookshelf_updated_at": _iso(lu.bookshelf_ua) if lu else "",
        "favourites_updated_at": _iso(lu.favourites_ua) if lu else "",
        "comments_updated_at": _iso(lu.comments_ua) if lu else "",
        "ratings_updated_at": _iso(lu.ratings_ua) if lu else "",
        "average_rating": average_rating,
        "rating_distribution_json": json.dumps(distribution),
    }
