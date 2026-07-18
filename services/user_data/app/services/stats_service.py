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
                COUNT(*) FILTER (WHERE bs.finished_at >= :year_start) AS finished_count,
                COALESCE(SUM(b.number_of_pages) FILTER (WHERE bs.finished_at >= :year_start), 0) AS pages_sum_year,
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


def _year_window(year: int) -> typing.Tuple[datetime.datetime, datetime.datetime, int]:
    start = datetime.datetime(year, 1, 1)
    end = datetime.datetime(year + 1, 1, 1)
    today = datetime.date.today()
    months_elapsed = today.month if year == today.year else 12
    return start, end, months_elapsed


def _year_book_row(row: typing.Any) -> typing.Dict[str, typing.Any]:
    names = [n for n in (row.author_names or []) if n]
    slugs = [s for s in (row.author_slugs or []) if s]
    return {
        "book_slug": row.book_slug or "",
        "book_title": row.book_title or "",
        "book_cover_url": row.book_cover_url or "",
        "author_names": names,
        "author_slugs": slugs,
        "number_of_pages": int(row.number_of_pages) if row.number_of_pages else 0,
        "finished_at": row.finished_at.isoformat() if row.finished_at else "",
        "my_rating": float(row.my_rating) if row.my_rating is not None else None,
    }


async def get_year_in_review(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    year: int,
) -> typing.Dict[str, typing.Any]:
    start, end, months_elapsed = _year_window(year)

    finished_result = await session.execute(
        sqlalchemy.text("""
            SELECT
                bs.book_id,
                b.slug AS book_slug,
                b.title AS book_title,
                b.primary_cover_url AS book_cover_url,
                b.number_of_pages,
                bs.finished_at,
                bs.started_at,
                r.overall_rating AS my_rating,
                ARRAY_AGG(a.name ORDER BY a.name) AS author_names,
                ARRAY_AGG(a.slug ORDER BY a.name) AS author_slugs
            FROM user_data.bookshelves bs
            JOIN books.books b ON b.book_id = bs.book_id
            LEFT JOIN books.book_authors ba ON ba.book_id = b.book_id
            LEFT JOIN books.authors a ON a.author_id = ba.author_id
            LEFT JOIN user_data.ratings r ON r.user_id = bs.user_id AND r.book_id = bs.book_id
            WHERE bs.user_id = :uid
              AND bs.status = 'read'
              AND bs.finished_at >= :start
              AND bs.finished_at < :end
            GROUP BY bs.book_id, b.slug, b.title, b.primary_cover_url, b.number_of_pages,
                     bs.finished_at, bs.started_at, r.overall_rating
            ORDER BY bs.finished_at ASC
        """),
        {"uid": user_id, "start": start, "end": end},
    )
    finished_rows = finished_result.fetchall()

    monthly: typing.Dict[int, typing.Dict[str, int]] = {
        month: {"books_finished": 0, "pages_read": 0, "ratings_given": 0}
        for month in range(1, months_elapsed + 1)
    }

    total_pages_read = 0
    pages_book_count = 0
    finished_cover_urls: typing.List[str] = []
    longest_book_row = None
    shortest_book_row = None
    highest_rated_row = None
    days_to_finish: typing.List[int] = []

    for row in finished_rows:
        month = row.finished_at.month
        if month in monthly:
            monthly[month]["books_finished"] += 1
            pages = int(row.number_of_pages) if row.number_of_pages else 0
            monthly[month]["pages_read"] += pages

        pages = int(row.number_of_pages) if row.number_of_pages else 0
        if pages > 0:
            total_pages_read += pages
            pages_book_count += 1
            if longest_book_row is None or pages > (longest_book_row.number_of_pages or 0):
                longest_book_row = row
            if shortest_book_row is None or pages < (shortest_book_row.number_of_pages or 0):
                shortest_book_row = row

        if row.book_cover_url and len(finished_cover_urls) < 12:
            finished_cover_urls.append(row.book_cover_url)

        if row.my_rating is not None and (
            highest_rated_row is None or row.my_rating > highest_rated_row.my_rating
        ):
            highest_rated_row = row

        if row.started_at is not None and row.finished_at >= row.started_at:
            days_to_finish.append((row.finished_at - row.started_at).days)

    first_finished_row = finished_rows[0] if finished_rows else None

    busiest_month = 0
    busiest_month_count = 0
    for month, bucket in monthly.items():
        if bucket["books_finished"] > busiest_month_count:
            busiest_month = month
            busiest_month_count = bucket["books_finished"]

    average_pages_per_book = (
        round(total_pages_read / pages_book_count, 1) if pages_book_count > 0 else 0.0
    )
    average_days_to_finish = (
        round(sum(days_to_finish) / len(days_to_finish), 1) if days_to_finish else 0.0
    )

    ratings_result = await session.execute(
        sqlalchemy.text("""
            SELECT EXTRACT(MONTH FROM created_at)::int AS month, overall_rating, COUNT(*) AS cnt
            FROM user_data.ratings
            WHERE user_id = :uid AND created_at >= :start AND created_at < :end
            GROUP BY month, overall_rating
        """),
        {"uid": user_id, "start": start, "end": end},
    )
    rating_rows = ratings_result.fetchall()

    ratings_given = 0
    rating_weighted_sum = 0.0
    distribution: typing.Dict[str, int] = {}
    for r in rating_rows:
        cnt = int(r.cnt)
        ratings_given += cnt
        rating_weighted_sum += float(r.overall_rating) * cnt
        month = int(r.month)
        if month in monthly:
            monthly[month]["ratings_given"] += cnt
        key = str(float(r.overall_rating))
        distribution[key] = distribution.get(key, 0) + cnt
    average_rating_given = (
        round(rating_weighted_sum / ratings_given, 2) if ratings_given > 0 else 0.0
    )

    genre_rows = (await session.execute(
        sqlalchemy.text("""
            WITH genre_counts AS (
                SELECT g.name, g.slug, COUNT(*) AS cnt
                FROM user_data.bookshelves bs
                JOIN books.book_genres bg ON bg.book_id = bs.book_id
                JOIN books.genres g ON g.genre_id = bg.genre_id
                WHERE bs.user_id = :uid
                  AND bs.status = 'read'
                  AND bs.finished_at >= :start
                  AND bs.finished_at < :end
                GROUP BY g.genre_id, g.name, g.slug
            ),
            total AS (SELECT COALESCE(SUM(cnt), 0) AS total_cnt FROM genre_counts)
            SELECT gc.name, gc.slug, gc.cnt, ROUND(gc.cnt::numeric / NULLIF(t.total_cnt, 0) * 100, 1) AS pct
            FROM genre_counts gc, total t
            ORDER BY gc.cnt DESC
            LIMIT 5
        """),
        {"uid": user_id, "start": start, "end": end},
    )).fetchall()

    author_rows = (await session.execute(
        sqlalchemy.text("""
            SELECT a.name, a.slug, a.photo_url, COUNT(*) AS cnt
            FROM user_data.bookshelves bs
            JOIN books.book_authors ba ON ba.book_id = bs.book_id
            JOIN books.authors a ON a.author_id = ba.author_id
            WHERE bs.user_id = :uid
              AND bs.status = 'read'
              AND bs.finished_at >= :start
              AND bs.finished_at < :end
            GROUP BY a.author_id, a.name, a.slug, a.photo_url
            ORDER BY cnt DESC
            LIMIT 5
        """),
        {"uid": user_id, "start": start, "end": end},
    )).fetchall()

    misc_result = await session.execute(
        sqlalchemy.text("""
            SELECT
                (SELECT COUNT(*) FROM user_data.bookshelves
                    WHERE user_id = :uid AND is_favorite = TRUE
                      AND created_at >= :start AND created_at < :end) AS favourites_added,
                (SELECT COUNT(*) FROM user_data.bookshelves
                    WHERE user_id = :uid
                      AND created_at >= :start AND created_at < :end) AS added_to_shelf,
                (SELECT COUNT(*) FROM user_data.comments
                    WHERE user_id = :uid AND is_deleted = FALSE
                      AND created_at >= :start AND created_at < :end) AS comments_written,
                (SELECT COUNT(*) FROM user_data.ratings
                    WHERE user_id = :uid AND created_at >= :start AND created_at < :end
                      AND review_text IS NOT NULL AND btrim(review_text) <> '') AS reviews_written,
                (SELECT COUNT(*) FROM user_data.bookshelves
                    WHERE user_id = :uid AND status = 'reading') AS currently_reading
        """),
        {"uid": user_id, "start": start, "end": end},
    )
    misc = misc_result.fetchone()

    return {
        "year": year,
        "months_elapsed": months_elapsed,
        "monthly": [
            {"month": month, **bucket} for month, bucket in sorted(monthly.items())
        ],
        "total_books_finished": len(finished_rows),
        "total_pages_read": total_pages_read,
        "total_hours_read": total_pages_read // 60,
        "ratings_given": ratings_given,
        "reviews_written": int(misc.reviews_written) if misc else 0,
        "comments_written": int(misc.comments_written) if misc else 0,
        "favourites_added": int(misc.favourites_added) if misc else 0,
        "average_rating_given": average_rating_given,
        "rating_distribution_json": json.dumps(distribution),
        "top_genres": [
            {"name": g.name, "slug": g.slug, "count": int(g.cnt), "percent": float(g.pct or 0)}
            for g in genre_rows
        ],
        "top_authors": [
            {"name": a.name, "slug": a.slug, "count": int(a.cnt), "photo_url": a.photo_url or ""}
            for a in author_rows
        ],
        "longest_book": _year_book_row(longest_book_row) if longest_book_row is not None else None,
        "shortest_book": _year_book_row(shortest_book_row) if shortest_book_row is not None else None,
        "first_finished": _year_book_row(first_finished_row) if first_finished_row is not None else None,
        "highest_rated": _year_book_row(highest_rated_row) if highest_rated_row is not None else None,
        "average_pages_per_book": average_pages_per_book,
        "busiest_month": busiest_month,
        "busiest_month_count": busiest_month_count,
        "average_days_to_finish": average_days_to_finish,
        "currently_reading_count": int(misc.currently_reading) if misc else 0,
        "added_to_shelf_count": int(misc.added_to_shelf) if misc else 0,
        "finished_cover_urls": finished_cover_urls,
    }
