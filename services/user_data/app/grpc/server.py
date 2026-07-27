import asyncio
import logging
import time
import typing

import app.cache
import app.database
import app.proto.user_data_pb2
import app.proto.user_data_pb2_grpc
import app.services.bookshelf_service
import app.services.comment_service
import app.services.rating_service
import app.services.stats_service
import grpc
import sqlalchemy

logger = logging.getLogger(__name__)

_NOT_FOUND_ERRORS = {"not_found", "book_not_found", "user_not_found"}
_PERMISSION_ERRORS = {"not_owner"}
_ALREADY_EXISTS_ERRORS = {"already_exists"}

_VALID_SORT_COLS: typing.Dict[str, str] = {
    "created_at": "c.created_at",
    "overall_rating": "r.overall_rating",
    "pacing": "r.pacing",
    "emotional_impact": "r.emotional_impact",
    "intellectual_depth": "r.intellectual_depth",
    "writing_quality": "r.writing_quality",
    "rereadability": "r.rereadability",
    "readability": "r.readability",
    "plot_complexity": "r.plot_complexity",
    "humor": "r.humor",
}


class _TtlCache:
    def __init__(self, ttl_seconds: int = 120) -> None:
        self._ttl = ttl_seconds
        self._store: typing.Dict[str, typing.Tuple[float, typing.Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> typing.Optional[typing.Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: typing.Any) -> None:
        async with self._lock:
            self._store[key] = (time.monotonic(), value)

    async def invalidate_by_book(self, book_id: int) -> None:
        prefix = f"{book_id}:"
        async with self._lock:
            for k in [k for k in self._store if k.startswith(prefix)]:
                del self._store[k]


_book_comments_cache = _TtlCache(ttl_seconds=120)


async def _resolve_user(session, username: str) -> int:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT user_id FROM auth.users WHERE username = :username AND is_active = TRUE"
        ),
        {"username": username},
    )
    row = result.fetchone()
    if row is None:
        raise ValueError("user_not_found")
    return row.user_id


async def _resolve_book(session, book_slug: str) -> typing.Tuple[int, str, str]:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT book_id, title, primary_cover_url FROM books.books WHERE slug = :slug"
            " ORDER BY book_id ASC LIMIT 1"
        ),
        {"slug": book_slug},
    )
    row = result.fetchone()
    if row is None:
        raise ValueError("book_not_found")
    return row.book_id, row.title or "", row.primary_cover_url or ""


async def _work_edition_slugs(session, book_slug: str) -> typing.List[str]:
    """Every edition slug belonging to the same work as `book_slug`.

    slug alone is not unique — only (language, slug) is — so the work is
    resolved from a single deterministic row before fanning back out.
    """
    result = await session.execute(
        sqlalchemy.text(
            "SELECT slug FROM books.books WHERE work_id = ("
            "  SELECT work_id FROM books.books WHERE slug = :slug"
            "  ORDER BY (language = 'en') DESC, book_id ASC LIMIT 1"
            ")"
        ),
        {"slug": book_slug},
    )
    slugs = [row.slug for row in result.fetchall()]

    return slugs or [book_slug]


async def _resolve_book_meta(session, book_slug: str) -> typing.Dict[str, typing.Any]:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT b.book_id, b.work_id, b.title, b.primary_cover_url, "
            "s.name AS series_name, s.slug AS series_slug "
            "FROM books.books b "
            "LEFT JOIN books.series s ON s.series_id = b.series_id "
            "WHERE b.slug = :slug ORDER BY b.book_id ASC LIMIT 1"
        ),
        {"slug": book_slug},
    )
    row = result.fetchone()
    if row is None:
        raise ValueError("book_not_found")

    authors_result = await session.execute(
        sqlalchemy.text(
            "SELECT a.name, a.slug FROM books.book_authors ba "
            "JOIN books.authors a ON a.author_id = ba.author_id "
            "WHERE ba.book_id = :book_id "
            "ORDER BY ba.book_id"
        ),
        {"book_id": row.book_id},
    )
    authors = authors_result.fetchall()

    return {
        "book_id": row.book_id,
        "work_id": row.work_id,
        "title": row.title or "",
        "cover_url": row.primary_cover_url or "",
        "series_name": row.series_name or "",
        "series_slug": row.series_slug or "",
        "author_names": [a.name for a in authors],
        "author_slugs": [a.slug for a in authors],
    }


async def _resolve_work_id(session, book_id: int) -> typing.Optional[str]:
    result = await session.execute(
        sqlalchemy.text("SELECT work_id FROM books.books WHERE book_id = :book_id"),
        {"book_id": book_id},
    )
    row = result.fetchone()
    return row.work_id if row else None


async def _resolve_username(session, user_id: int) -> str:
    result = await session.execute(
        sqlalchemy.text("SELECT username FROM auth.users WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    row = result.fetchone()
    return row.username if row else ""


async def _fetch_profile_overview(
    session: typing.Any,
    user_id: int,
) -> typing.Dict[str, typing.Any]:
    import datetime

    year_start = datetime.datetime(datetime.date.today().year, 1, 1)

    user_row = (await session.execute(
        sqlalchemy.text(
            "SELECT username, display_name, avatar_url, bio FROM auth.users WHERE user_id = :uid"
        ),
        {"uid": user_id},
    )).fetchone()

    reading_row = (await session.execute(
        sqlalchemy.text("""
            SELECT
                bs.book_id,
                b.slug AS book_slug,
                b.title AS book_title,
                b.primary_cover_url AS book_cover_url,
                ARRAY_AGG(a.name ORDER BY a.name) AS author_names,
                ARRAY_AGG(a.slug ORDER BY a.name) AS author_slugs
            FROM user_data.bookshelves bs
            JOIN books.books b ON b.book_id = bs.book_id
            LEFT JOIN books.book_authors ba ON ba.book_id = b.book_id
            LEFT JOIN books.authors a ON a.author_id = ba.author_id
            WHERE bs.user_id = :uid AND bs.status = 'reading'
            GROUP BY bs.book_id, b.slug, b.title, b.primary_cover_url, bs.updated_at
            ORDER BY bs.updated_at DESC
            LIMIT 1
        """),
        {"uid": user_id},
    )).fetchone()

    genre_rows = (await session.execute(
        sqlalchemy.text("""
            WITH genre_counts AS (
                SELECT
                    g.name,
                    g.slug,
                    COUNT(*) AS cnt
                FROM user_data.bookshelves bs
                JOIN books.book_genres bg ON bg.book_id = bs.book_id
                JOIN books.genres g ON g.genre_id = bg.genre_id
                WHERE bs.user_id = :uid
                  AND bs.status IN ('reading', 'read', 'want_to_read')
                GROUP BY g.genre_id, g.name, g.slug
            ),
            total AS (SELECT COALESCE(SUM(cnt), 0) AS total_cnt FROM genre_counts)
            SELECT gc.name, gc.slug, gc.cnt, ROUND(gc.cnt::numeric / NULLIF(t.total_cnt, 0) * 100, 1) AS pct
            FROM genre_counts gc, total t
            ORDER BY gc.cnt DESC
            LIMIT 5
        """),
        {"uid": user_id},
    )).fetchall()

    author_rows = (await session.execute(
        sqlalchemy.text("""
            SELECT
                a.name,
                a.slug,
                a.photo_url,
                COUNT(*) AS cnt
            FROM user_data.bookshelves bs
            JOIN books.book_authors ba ON ba.book_id = bs.book_id
            JOIN books.authors a ON a.author_id = ba.author_id
            WHERE bs.user_id = :uid
              AND bs.status IN ('reading', 'read', 'want_to_read')
            GROUP BY a.author_id, a.name, a.slug, a.photo_url
            ORDER BY cnt DESC
            LIMIT 5
        """),
        {"uid": user_id},
    )).fetchall()

    fav_rows = (await session.execute(
        sqlalchemy.text("""
            SELECT
                b.slug AS book_slug,
                b.title AS book_title,
                b.primary_cover_url AS book_cover_url,
                ARRAY_AGG(a.name ORDER BY a.name) AS author_names,
                ARRAY_AGG(a.slug ORDER BY a.name) AS author_slugs,
                bs.created_at
            FROM user_data.bookshelves bs
            JOIN books.books b ON b.book_id = bs.book_id
            LEFT JOIN books.book_authors ba ON ba.book_id = b.book_id
            LEFT JOIN books.authors a ON a.author_id = ba.author_id
            WHERE bs.user_id = :uid
              AND bs.is_favorite = TRUE
              AND bs.created_at >= :year_start
            GROUP BY bs.bookshelf_id, b.slug, b.title, b.primary_cover_url, bs.created_at
            ORDER BY bs.created_at DESC
            LIMIT 4
        """),
        {"uid": user_id, "year_start": year_start},
    )).fetchall()

    def _book_row(row: typing.Any) -> typing.Dict[str, typing.Any]:
        names = [n for n in (row.author_names or []) if n]
        slugs = [s for s in (row.author_slugs or []) if s]
        return {
            "book_slug": row.book_slug or "",
            "book_title": row.book_title or "",
            "book_cover_url": row.book_cover_url or "",
            "book_author_names": names,
            "book_author_slugs": slugs,
        }

    return {
        "user": {
            "user_id": user_id,
            "username": user_row.username if user_row else "",
            "display_name": user_row.display_name if user_row else "",
            "avatar_url": user_row.avatar_url if user_row else "",
            "bio": user_row.bio if user_row else "",
        },
        "reading_now": _book_row(reading_row) if reading_row else None,
        "top_genres": [
            {"name": r.name, "slug": r.slug, "count": int(r.cnt), "percent": float(r.pct or 0)}
            for r in genre_rows
        ],
        "favourite_authors": [
            {"name": r.name, "slug": r.slug, "count": int(r.cnt), "photo_url": r.photo_url or ""}
            for r in author_rows
        ],
        "favourites_this_year": [_book_row(r) for r in fav_rows],
    }


def _profile_overview_to_proto(
    data: typing.Dict[str, typing.Any],
) -> app.proto.user_data_pb2.ProfileOverviewResponse:
    def _make_book(d: typing.Optional[typing.Dict]) -> app.proto.user_data_pb2.OverviewBook:
        if not d:
            return app.proto.user_data_pb2.OverviewBook()
        return app.proto.user_data_pb2.OverviewBook(
            book_slug=d.get("book_slug", ""),
            book_title=d.get("book_title", ""),
            book_cover_url=d.get("book_cover_url", ""),
            book_author_names=d.get("book_author_names", []),
            book_author_slugs=d.get("book_author_slugs", []),
        )

    u = data.get("user", {})
    reading_now_data = data.get("reading_now")

    return app.proto.user_data_pb2.ProfileOverviewResponse(
        user=app.proto.user_data_pb2.PublicUser(
            user_id=u.get("user_id", 0),
            username=u.get("username", ""),
            display_name=u.get("display_name", ""),
            avatar_url=u.get("avatar_url", ""),
            bio=u.get("bio", ""),
        ),
        reading_now=_make_book(reading_now_data),
        reading_now_present=reading_now_data is not None,
        top_genres=[
            app.proto.user_data_pb2.TopGenre(
                name=g["name"], slug=g["slug"], count=g["count"], percent=g["percent"]
            )
            for g in data.get("top_genres", [])
        ],
        favourite_authors=[
            app.proto.user_data_pb2.FavouriteAuthor(
                name=a["name"], slug=a["slug"], count=a["count"], photo_url=a.get("photo_url", "")
            )
            for a in data.get("favourite_authors", [])
        ],
        favourites_this_year=[_make_book(b) for b in data.get("favourites_this_year", [])],
    )


def _profile_stats_to_proto(data: typing.Dict[str, typing.Any]) -> app.proto.user_data_pb2.ProfileStats:
    return app.proto.user_data_pb2.ProfileStats(
        want_to_read_count=data.get("want_to_read_count", 0),
        reading_count=data.get("reading_count", 0),
        read_count=data.get("read_count", 0),
        abandoned_count=data.get("abandoned_count", 0),
        favourites_count=data.get("favourites_count", 0),
        ratings_count=data.get("ratings_count", 0),
        comments_count=data.get("comments_count", 0),
        finished_this_year_count=data.get("finished_this_year_count", 0),
        pages_read_this_year=data.get("pages_read_this_year", 0),
        hours_read_this_year=data.get("hours_read_this_year", 0),
        bookshelf_updated_at=data.get("bookshelf_updated_at", ""),
        favourites_updated_at=data.get("favourites_updated_at", ""),
        comments_updated_at=data.get("comments_updated_at", ""),
        ratings_updated_at=data.get("ratings_updated_at", ""),
        average_rating=float(data.get("average_rating", 0.0)),
        rating_distribution_json=data.get("rating_distribution_json", "{}"),
        pages_read_total=data.get("pages_read_total", 0),
        reviews_count=data.get("reviews_count", 0),
    )


def _year_in_review_to_proto(
    data: typing.Dict[str, typing.Any],
) -> app.proto.user_data_pb2.YearInReview:
    def _make_year_book(d: typing.Optional[typing.Dict]) -> app.proto.user_data_pb2.YearBook:
        if not d:
            return app.proto.user_data_pb2.YearBook()
        return app.proto.user_data_pb2.YearBook(
            book_slug=d.get("book_slug", ""),
            book_title=d.get("book_title", ""),
            book_cover_url=d.get("book_cover_url", ""),
            author_names=d.get("author_names", []),
            author_slugs=d.get("author_slugs", []),
            number_of_pages=d.get("number_of_pages", 0),
            finished_at=d.get("finished_at", ""),
            my_rating=d.get("my_rating") or 0.0,
            has_my_rating=d.get("my_rating") is not None,
        )

    longest_book = data.get("longest_book")
    shortest_book = data.get("shortest_book")
    first_finished = data.get("first_finished")
    highest_rated = data.get("highest_rated")

    return app.proto.user_data_pb2.YearInReview(
        year=data.get("year", 0),
        months_elapsed=data.get("months_elapsed", 0),
        monthly=[
            app.proto.user_data_pb2.MonthlyBucket(
                month=m.get("month", 0),
                books_finished=m.get("books_finished", 0),
                pages_read=m.get("pages_read", 0),
                ratings_given=m.get("ratings_given", 0),
                books=[_make_year_book(b) for b in m.get("books", [])],
            )
            for m in data.get("monthly", [])
        ],
        total_books_finished=data.get("total_books_finished", 0),
        total_pages_read=data.get("total_pages_read", 0),
        total_hours_read=data.get("total_hours_read", 0),
        ratings_given=data.get("ratings_given", 0),
        reviews_written=data.get("reviews_written", 0),
        comments_written=data.get("comments_written", 0),
        favourites_added=data.get("favourites_added", 0),
        average_rating_given=data.get("average_rating_given", 0.0),
        rating_distribution_json=data.get("rating_distribution_json", "{}"),
        top_genres=[
            app.proto.user_data_pb2.TopGenre(
                name=g["name"], slug=g["slug"], count=g["count"], percent=g["percent"]
            )
            for g in data.get("top_genres", [])
        ],
        top_authors=[
            app.proto.user_data_pb2.FavouriteAuthor(
                name=a["name"], slug=a["slug"], count=a["count"], photo_url=a.get("photo_url", "")
            )
            for a in data.get("top_authors", [])
        ],
        longest_book=_make_year_book(longest_book),
        has_longest_book=longest_book is not None,
        shortest_book=_make_year_book(shortest_book),
        has_shortest_book=shortest_book is not None,
        first_finished=_make_year_book(first_finished),
        has_first_finished=first_finished is not None,
        highest_rated=_make_year_book(highest_rated),
        has_highest_rated=highest_rated is not None,
        average_pages_per_book=data.get("average_pages_per_book", 0.0),
        busiest_month=data.get("busiest_month", 0),
        busiest_month_count=data.get("busiest_month_count", 0),
        average_days_to_finish=data.get("average_days_to_finish", 0.0),
        currently_reading_count=data.get("currently_reading_count", 0),
        added_to_shelf_count=data.get("added_to_shelf_count", 0),
        finished_cover_urls=data.get("finished_cover_urls", []),
    )


def _bookshelf_to_proto(
    bookshelf,
    book_slug: str = "",
    book_title: str = "",
    book_cover_url: str = "",
    author_names: typing.List[str] = None,
    author_slugs: typing.List[str] = None,
    series_name: str = "",
    series_slug: str = "",
) -> app.proto.user_data_pb2.Bookshelf:
    if author_names is None:
        author_names = []
    if author_slugs is None:
        author_slugs = []
    return app.proto.user_data_pb2.Bookshelf(
        bookshelf_id=bookshelf.bookshelf_id,
        user_id=bookshelf.user_id,
        book_id=bookshelf.book_id,
        book_slug=book_slug,
        book_title=book_title,
        book_cover_url=book_cover_url,
        status=bookshelf.status,
        is_favorite=bookshelf.is_favorite,
        created_at=bookshelf.created_at.isoformat() if bookshelf.created_at else "",
        updated_at=bookshelf.updated_at.isoformat() if bookshelf.updated_at else "",
        book_author_names=author_names,
        book_author_slugs=author_slugs,
        book_series_name=series_name,
        book_series_slug=series_slug,
    )


def _rating_to_proto(
    rating,
    book_slug: str = "",
    book_title: str = "",
    book_cover_url: str = "",
    author_names: typing.List[str] = None,
    author_slugs: typing.List[str] = None,
    series_name: str = "",
    series_slug: str = "",
    book_avg_rating: float = 0.0,
    book_rating_count: int = 0,
) -> app.proto.user_data_pb2.Rating:
    if author_names is None:
        author_names = []
    if author_slugs is None:
        author_slugs = []
    return app.proto.user_data_pb2.Rating(
        rating_id=rating.rating_id,
        user_id=rating.user_id,
        book_id=rating.book_id,
        book_slug=book_slug,
        book_title=book_title,
        book_cover_url=book_cover_url,
        overall_rating=float(rating.overall_rating),
        review_text=rating.review_text or "",
        pacing=float(rating.pacing) if rating.pacing is not None else 0.0,
        has_pacing=rating.pacing is not None,
        emotional_impact=(
            float(rating.emotional_impact)
            if rating.emotional_impact is not None
            else 0.0
        ),
        has_emotional_impact=rating.emotional_impact is not None,
        intellectual_depth=(
            float(rating.intellectual_depth)
            if rating.intellectual_depth is not None
            else 0.0
        ),
        has_intellectual_depth=rating.intellectual_depth is not None,
        writing_quality=(
            float(rating.writing_quality) if rating.writing_quality is not None else 0.0
        ),
        has_writing_quality=rating.writing_quality is not None,
        rereadability=(
            float(rating.rereadability) if rating.rereadability is not None else 0.0
        ),
        has_rereadability=rating.rereadability is not None,
        readability=(
            float(rating.readability) if rating.readability is not None else 0.0
        ),
        has_readability=rating.readability is not None,
        plot_complexity=(
            float(rating.plot_complexity) if rating.plot_complexity is not None else 0.0
        ),
        has_plot_complexity=rating.plot_complexity is not None,
        humor=float(rating.humor) if rating.humor is not None else 0.0,
        has_humor=rating.humor is not None,
        created_at=rating.created_at.isoformat() if rating.created_at else "",
        updated_at=rating.updated_at.isoformat() if rating.updated_at else "",
        book_author_names=author_names,
        book_author_slugs=author_slugs,
        book_series_name=series_name,
        book_series_slug=series_slug,
        book_avg_rating=book_avg_rating,
        book_rating_count=book_rating_count,
    )


def _comment_to_proto(
    comment,
    book_slug: str = "",
    book_title: str = "",
    username: str = "",
    author_names: typing.List[str] = None,
    author_slugs: typing.List[str] = None,
    series_name: str = "",
    series_slug: str = "",
    cover_url: str = "",
) -> app.proto.user_data_pb2.Comment:
    if author_names is None:
        author_names = []
    if author_slugs is None:
        author_slugs = []
    return app.proto.user_data_pb2.Comment(
        comment_id=comment.comment_id,
        user_id=comment.user_id,
        book_id=comment.book_id,
        book_slug=book_slug,
        book_title=book_title,
        body=comment.body,
        is_spoiler=comment.is_spoiler,
        created_at=comment.created_at.isoformat() if comment.created_at else "",
        updated_at=comment.updated_at.isoformat() if comment.updated_at else "",
        username=username,
        book_author_names=author_names,
        book_author_slugs=author_slugs,
        book_series_name=series_name,
        book_series_slug=series_slug,
        book_cover_url=cover_url,
    )


def _row_to_comment_with_rating(
    row, book_slug: str
) -> app.proto.user_data_pb2.BookCommentWithRating:
    has_rating = row.overall_rating is not None
    return app.proto.user_data_pb2.BookCommentWithRating(
        comment_id=row.comment_id,
        user_id=row.user_id,
        book_id=row.book_id,
        book_slug=book_slug,
        body=row.body,
        is_spoiler=row.is_spoiler,
        comment_created_at=row.created_at.isoformat() if row.created_at else "",
        comment_updated_at=row.updated_at.isoformat() if row.updated_at else "",
        has_rating=has_rating,
        overall_rating=float(row.overall_rating) if has_rating else 0.0,
        review_text=row.review_text or "" if has_rating else "",
        pacing=float(row.pacing) if row.pacing is not None else 0.0,
        has_pacing=row.pacing is not None,
        emotional_impact=(
            float(row.emotional_impact) if row.emotional_impact is not None else 0.0
        ),
        has_emotional_impact=row.emotional_impact is not None,
        intellectual_depth=(
            float(row.intellectual_depth) if row.intellectual_depth is not None else 0.0
        ),
        has_intellectual_depth=row.intellectual_depth is not None,
        writing_quality=(
            float(row.writing_quality) if row.writing_quality is not None else 0.0
        ),
        has_writing_quality=row.writing_quality is not None,
        rereadability=(
            float(row.rereadability) if row.rereadability is not None else 0.0
        ),
        has_rereadability=row.rereadability is not None,
        readability=float(row.readability) if row.readability is not None else 0.0,
        has_readability=row.readability is not None,
        plot_complexity=(
            float(row.plot_complexity) if row.plot_complexity is not None else 0.0
        ),
        has_plot_complexity=row.plot_complexity is not None,
        humor=float(row.humor) if row.humor is not None else 0.0,
        has_humor=row.humor is not None,
        username=row.username if hasattr(row, "username") else "",
    )


async def _handle_error(error: Exception, context: grpc.aio.ServicerContext) -> None:
    error_key = str(error)
    if error_key in _NOT_FOUND_ERRORS:
        await context.abort(
            grpc.StatusCode.NOT_FOUND, f"Resource not found: {error_key}"
        )
    elif error_key in _PERMISSION_ERRORS:
        await context.abort(
            grpc.StatusCode.PERMISSION_DENIED, f"Permission denied: {error_key}"
        )
    elif error_key in _ALREADY_EXISTS_ERRORS:
        await context.abort(
            grpc.StatusCode.ALREADY_EXISTS, f"Resource already exists: {error_key}"
        )
    else:
        await context.abort(
            grpc.StatusCode.INVALID_ARGUMENT, f"Invalid argument: {error_key}"
        )


_USER_BOOK_INFO_SQL = """
    SELECT
        b.book_id            AS book_id,
        b.title              AS book_title,
        b.primary_cover_url  AS book_cover_url,
        s.name               AS series_name,
        s.slug               AS series_slug,
        bs.bookshelf_id      AS bs_id,
        bs.status            AS bs_status,
        bs.is_favorite       AS bs_is_favorite,
        bs.created_at        AS bs_created_at,
        bs.updated_at        AS bs_updated_at,
        r.rating_id          AS r_id,
        r.overall_rating     AS r_overall,
        r.review_text        AS r_review,
        r.pacing             AS r_pacing,
        r.emotional_impact   AS r_emotional_impact,
        r.intellectual_depth AS r_intellectual_depth,
        r.writing_quality    AS r_writing_quality,
        r.rereadability      AS r_rereadability,
        r.readability        AS r_readability,
        r.plot_complexity    AS r_plot_complexity,
        r.humor              AS r_humor,
        r.created_at         AS r_created_at,
        r.updated_at         AS r_updated_at,
        c.comment_id         AS c_id,
        c.body               AS c_body,
        c.is_spoiler         AS c_is_spoiler,
        c.created_at         AS c_created_at,
        c.updated_at         AS c_updated_at,
        u.username           AS username
    FROM books.books b
    LEFT JOIN books.series s          ON s.series_id = b.series_id
    LEFT JOIN user_data.bookshelves bs ON bs.book_id = b.book_id AND bs.user_id = :uid
    LEFT JOIN user_data.ratings r      ON r.book_id = b.book_id AND r.user_id = :uid
    LEFT JOIN user_data.comments c     ON c.book_id = b.book_id AND c.user_id = :uid
    LEFT JOIN auth.users u             ON u.user_id = :uid
    WHERE b.slug = :slug
    ORDER BY b.book_id ASC
    LIMIT 1
"""


def _iso_or_empty(value: typing.Any) -> str:
    return value.isoformat() if value is not None else ""


def _sub_rating(value: typing.Any) -> typing.Tuple[float, bool]:
    return (float(value), True) if value is not None else (0.0, False)


def _row_to_user_book_info(
    row: typing.Any, book_slug: str, user_id: int
) -> app.proto.user_data_pb2.UserBookInfoResponse:
    series_name = row.series_name or ""
    series_slug = row.series_slug or ""
    title = row.book_title or ""
    cover = row.book_cover_url or ""

    kwargs: typing.Dict[str, typing.Any] = {}

    if row.bs_id is not None:
        kwargs["bookshelf"] = app.proto.user_data_pb2.Bookshelf(
            bookshelf_id=row.bs_id,
            user_id=user_id,
            book_id=row.book_id,
            book_slug=book_slug,
            book_title=title,
            book_cover_url=cover,
            status=row.bs_status,
            is_favorite=row.bs_is_favorite,
            created_at=_iso_or_empty(row.bs_created_at),
            updated_at=_iso_or_empty(row.bs_updated_at),
            book_series_name=series_name,
            book_series_slug=series_slug,
        )

    if row.r_id is not None:
        pacing, has_pacing = _sub_rating(row.r_pacing)
        emotional_impact, has_emotional_impact = _sub_rating(row.r_emotional_impact)
        intellectual_depth, has_intellectual_depth = _sub_rating(row.r_intellectual_depth)
        writing_quality, has_writing_quality = _sub_rating(row.r_writing_quality)
        rereadability, has_rereadability = _sub_rating(row.r_rereadability)
        readability, has_readability = _sub_rating(row.r_readability)
        plot_complexity, has_plot_complexity = _sub_rating(row.r_plot_complexity)
        humor, has_humor = _sub_rating(row.r_humor)
        kwargs["rating"] = app.proto.user_data_pb2.Rating(
            rating_id=row.r_id,
            user_id=user_id,
            book_id=row.book_id,
            book_slug=book_slug,
            book_title=title,
            book_cover_url=cover,
            overall_rating=float(row.r_overall),
            review_text=row.r_review or "",
            pacing=pacing,
            has_pacing=has_pacing,
            emotional_impact=emotional_impact,
            has_emotional_impact=has_emotional_impact,
            intellectual_depth=intellectual_depth,
            has_intellectual_depth=has_intellectual_depth,
            writing_quality=writing_quality,
            has_writing_quality=has_writing_quality,
            rereadability=rereadability,
            has_rereadability=has_rereadability,
            readability=readability,
            has_readability=has_readability,
            plot_complexity=plot_complexity,
            has_plot_complexity=has_plot_complexity,
            humor=humor,
            has_humor=has_humor,
            created_at=_iso_or_empty(row.r_created_at),
            updated_at=_iso_or_empty(row.r_updated_at),
            book_series_name=series_name,
            book_series_slug=series_slug,
        )

    if row.c_id is not None:
        kwargs["comment"] = app.proto.user_data_pb2.Comment(
            comment_id=row.c_id,
            user_id=user_id,
            book_id=row.book_id,
            book_slug=book_slug,
            book_title=title,
            body=row.c_body,
            is_spoiler=row.c_is_spoiler,
            created_at=_iso_or_empty(row.c_created_at),
            updated_at=_iso_or_empty(row.c_updated_at),
            username=row.username or "",
            book_series_name=series_name,
            book_series_slug=series_slug,
            book_cover_url=cover,
        )

    return app.proto.user_data_pb2.UserBookInfoResponse(**kwargs)


async def _recompute_user_stats_bg(user_id: int, kind: str) -> None:
    try:
        async with app.database.async_session_maker() as session:
            if kind == "bookshelf":
                await app.services.stats_service.recalculate_bookshelf_stats(
                    session, user_id
                )
            elif kind == "rating":
                await app.services.stats_service.recalculate_rating_stats(
                    session, user_id
                )
            elif kind == "comment":
                await app.services.stats_service.recalculate_comment_stats(
                    session, user_id
                )
            await session.commit()
        await app.cache.delete_profile_stats(user_id)
    except Exception as e:
        logger.error(
            "Background %s stats recompute failed for user %s: %s", kind, user_id, e
        )


class UserDataServicer(app.proto.user_data_pb2_grpc.UserDataServiceServicer):

    async def GetBookshelf(
        self,
        request: app.proto.user_data_pb2.GetBookshelfRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.BookshelfResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_meta = await _resolve_book_meta(session, request.book_slug)
                bookshelf = await app.services.bookshelf_service.get_bookshelf(
                    session, request.user_id, book_meta["book_id"]
                )
                if bookshelf is None:
                    raise ValueError("not_found")
                return app.proto.user_data_pb2.BookshelfResponse(
                    bookshelf=_bookshelf_to_proto(
                        bookshelf,
                        request.book_slug,
                        book_meta["title"],
                        book_meta["cover_url"],
                        book_meta["author_names"],
                        book_meta["author_slugs"],
                        book_meta["series_name"],
                        book_meta["series_slug"],
                    )
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookshelf: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def UpsertBookshelf(
        self,
        request: app.proto.user_data_pb2.UpsertBookshelfRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.BookshelfResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_meta = await _resolve_book_meta(session, request.book_slug)
                bookshelf = await app.services.bookshelf_service.upsert_bookshelf(
                    session, request.user_id, book_meta["book_id"], request.status
                )
                await app.cache.delete_book_cache(
                    *await _work_edition_slugs(session, request.book_slug)
                )
                await app.cache.delete_profile_stats(request.user_id)
                await app.cache.delete_profile_overview(request.user_id)
                await app.cache.delete_year_in_review(request.user_id)
                await app.cache.delete_bookshelf_list_cache(request.user_id)
                asyncio.create_task(
                    _recompute_user_stats_bg(request.user_id, "bookshelf")
                )
                return app.proto.user_data_pb2.BookshelfResponse(
                    bookshelf=_bookshelf_to_proto(
                        bookshelf,
                        request.book_slug,
                        book_meta["title"],
                        book_meta["cover_url"],
                        book_meta["author_names"],
                        book_meta["author_slugs"],
                        book_meta["series_name"],
                        book_meta["series_slug"],
                    )
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in UpsertBookshelf: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def DeleteBookshelf(
        self,
        request: app.proto.user_data_pb2.DeleteBookshelfRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                await app.services.bookshelf_service.delete_bookshelf(
                    session, request.user_id, book_id
                )
                await app.cache.delete_book_cache(
                    *await _work_edition_slugs(session, request.book_slug)
                )
                await app.cache.delete_profile_stats(request.user_id)
                await app.cache.delete_profile_overview(request.user_id)
                await app.cache.delete_year_in_review(request.user_id)
                await app.cache.delete_bookshelf_list_cache(request.user_id)
                asyncio.create_task(
                    _recompute_user_stats_bg(request.user_id, "bookshelf")
                )
                return app.proto.user_data_pb2.EmptyResponse()
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteBookshelf: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserBookshelves(
        self,
        request: app.proto.user_data_pb2.GetUserBookshelvesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        try:
            limit = request.limit or 10
            offset = request.offset or 0
            sort_by = request.sort_by or "created_at"
            order = request.order or "desc"
            cache_key = (
                f"bookshelf_list:{request.user_id}:{request.status_filter}:"
                f"{request.favourites_only}:{sort_by}:{order}:{limit}:{offset}"
            )
            cached = await app.cache.get_json(cache_key)
            if cached is not None:
                protos = [
                    app.proto.user_data_pb2.Bookshelf(**entry)
                    for entry in cached["bookshelves"]
                ]
                return app.proto.user_data_pb2.BookshelvesListResponse(
                    bookshelves=protos, total_count=cached["total_count"]
                )

            async with app.database.async_session_maker() as session:
                rows, total_count = (
                    await app.services.bookshelf_service.get_user_bookshelves(
                        session,
                        request.user_id,
                        limit,
                        offset,
                        request.status_filter,
                        request.favourites_only,
                        sort_by,
                        order,
                    )
                )

                meta_map = await _build_book_meta_map(
                    session, [r.book_id for r in rows]
                )
                authors_map = await _build_book_authors_map(
                    session, [r.book_id for r in rows]
                )

                entries = [
                    {
                        "bookshelf_id": r.bookshelf_id,
                        "user_id": r.user_id,
                        "book_id": r.book_id,
                        "book_slug": meta_map.get(r.book_id, {}).get("slug", ""),
                        "book_title": meta_map.get(r.book_id, {}).get("title", ""),
                        "book_cover_url": meta_map.get(r.book_id, {}).get("cover_url", ""),
                        "status": r.status,
                        "is_favorite": r.is_favorite,
                        "created_at": r.created_at.isoformat() if r.created_at else "",
                        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                        "book_author_names": authors_map.get(r.book_id, ([], []))[0],
                        "book_author_slugs": authors_map.get(r.book_id, ([], []))[1],
                        "book_series_name": meta_map.get(r.book_id, {}).get("series_name", ""),
                        "book_series_slug": meta_map.get(r.book_id, {}).get("series_slug", ""),
                    }
                    for r in rows
                ]

            await app.cache.set_json(cache_key, {"total_count": total_count, "bookshelves": entries}, ttl=300)
            protos = [app.proto.user_data_pb2.Bookshelf(**e) for e in entries]
            return app.proto.user_data_pb2.BookshelvesListResponse(
                bookshelves=protos, total_count=total_count
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserBookshelves: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetPublicBookshelves(
        self,
        request: app.proto.user_data_pb2.GetPublicBookshelvesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        try:
            limit = request.limit or 10
            offset = request.offset or 0
            sort_by = request.sort_by or "created_at"
            order = request.order or "desc"

            async with app.database.async_session_maker() as session:
                user_id = await _resolve_user(session, request.username)

                cache_key = (
                    f"bookshelf_list:{user_id}:{request.status_filter}:"
                    f"{request.favourites_only}:{sort_by}:{order}:{limit}:{offset}"
                )
                cached = await app.cache.get_json(cache_key)
                if cached is not None:
                    protos = [
                        app.proto.user_data_pb2.Bookshelf(**entry)
                        for entry in cached["bookshelves"]
                    ]
                    return app.proto.user_data_pb2.BookshelvesListResponse(
                        bookshelves=protos, total_count=cached["total_count"]
                    )

                rows, total_count = (
                    await app.services.bookshelf_service.get_user_bookshelves(
                        session,
                        user_id,
                        limit,
                        offset,
                        request.status_filter,
                        request.favourites_only,
                        sort_by,
                        order,
                    )
                )
                meta_map = await _build_book_meta_map(
                    session, [r.book_id for r in rows]
                )
                authors_map = await _build_book_authors_map(
                    session, [r.book_id for r in rows]
                )

                entries = [
                    {
                        "bookshelf_id": r.bookshelf_id,
                        "user_id": r.user_id,
                        "book_id": r.book_id,
                        "book_slug": meta_map.get(r.book_id, {}).get("slug", ""),
                        "book_title": meta_map.get(r.book_id, {}).get("title", ""),
                        "book_cover_url": meta_map.get(r.book_id, {}).get("cover_url", ""),
                        "status": r.status,
                        "is_favorite": r.is_favorite,
                        "created_at": r.created_at.isoformat() if r.created_at else "",
                        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                        "book_author_names": authors_map.get(r.book_id, ([], []))[0],
                        "book_author_slugs": authors_map.get(r.book_id, ([], []))[1],
                        "book_series_name": meta_map.get(r.book_id, {}).get("series_name", ""),
                        "book_series_slug": meta_map.get(r.book_id, {}).get("series_slug", ""),
                    }
                    for r in rows
                ]

            await app.cache.set_json(cache_key, {"total_count": total_count, "bookshelves": entries}, ttl=300)
            protos = [app.proto.user_data_pb2.Bookshelf(**e) for e in entries]
            return app.proto.user_data_pb2.BookshelvesListResponse(
                bookshelves=protos, total_count=total_count
            )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetPublicBookshelves: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetRating(
        self,
        request: app.proto.user_data_pb2.GetRatingRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.RatingResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_meta = await _resolve_book_meta(session, request.book_slug)
                rating = await app.services.rating_service.get_rating(
                    session, request.user_id, book_meta["book_id"]
                )
                if rating is None:
                    raise ValueError("not_found")
                return app.proto.user_data_pb2.RatingResponse(
                    rating=_rating_to_proto(
                        rating,
                        request.book_slug,
                        book_meta["title"],
                        book_meta["cover_url"],
                        book_meta["author_names"],
                        book_meta["author_slugs"],
                        book_meta["series_name"],
                        book_meta["series_slug"],
                    )
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetRating: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def UpsertRating(
        self,
        request: app.proto.user_data_pb2.UpsertRatingRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.RatingResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_meta = await _resolve_book_meta(session, request.book_slug)

                sub_ratings: typing.Dict[str, float] = {}
                if request.has_pacing:
                    sub_ratings["pacing"] = request.pacing
                if request.has_emotional_impact:
                    sub_ratings["emotional_impact"] = request.emotional_impact
                if request.has_intellectual_depth:
                    sub_ratings["intellectual_depth"] = request.intellectual_depth
                if request.has_writing_quality:
                    sub_ratings["writing_quality"] = request.writing_quality
                if request.has_rereadability:
                    sub_ratings["rereadability"] = request.rereadability
                if request.has_readability:
                    sub_ratings["readability"] = request.readability
                if request.has_plot_complexity:
                    sub_ratings["plot_complexity"] = request.plot_complexity
                if request.has_humor:
                    sub_ratings["humor"] = request.humor

                rating = await app.services.rating_service.upsert_rating(
                    session,
                    request.user_id,
                    book_meta["book_id"],
                    request.overall_rating,
                    sub_ratings,
                    request.review_text or None,
                )
                await app.cache.delete_book_cache(
                    *await _work_edition_slugs(session, request.book_slug)
                )
                await app.cache.delete_profile_stats(request.user_id)
                await app.cache.delete_profile_overview(request.user_id)
                await app.cache.delete_year_in_review(request.user_id)
                asyncio.create_task(
                    _recompute_user_stats_bg(request.user_id, "rating")
                )
                return app.proto.user_data_pb2.RatingResponse(
                    rating=_rating_to_proto(
                        rating,
                        request.book_slug,
                        book_meta["title"],
                        book_meta["cover_url"],
                        book_meta["author_names"],
                        book_meta["author_slugs"],
                        book_meta["series_name"],
                        book_meta["series_slug"],
                    )
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in UpsertRating: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def DeleteRating(
        self,
        request: app.proto.user_data_pb2.DeleteRatingRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                await app.services.rating_service.delete_rating(
                    session, request.user_id, book_id
                )
                await app.cache.delete_book_cache(
                    *await _work_edition_slugs(session, request.book_slug)
                )
                await app.cache.delete_profile_stats(request.user_id)
                await app.cache.delete_profile_overview(request.user_id)
                await app.cache.delete_year_in_review(request.user_id)
                asyncio.create_task(
                    _recompute_user_stats_bg(request.user_id, "rating")
                )
                return app.proto.user_data_pb2.EmptyResponse()
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteRating: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserRatings(
        self,
        request: app.proto.user_data_pb2.GetUserRatingsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.RatingsListResponse:
        try:
            async with app.database.async_session_maker() as session:
                rows, total_count = await app.services.rating_service.get_user_ratings(
                    session,
                    request.user_id,
                    request.limit or 10,
                    request.offset or 0,
                    request.sort_by or "created_at",
                    request.order or "desc",
                    request.min_rating,
                    request.max_rating,
                )

                book_ids = [r.book_id for r in rows]
                meta_map = await _build_book_meta_map(session, book_ids)
                authors_map = await _build_book_authors_map(session, book_ids)

                protos = [
                    _rating_to_proto(
                        r,
                        meta_map.get(r.book_id, {}).get("slug", ""),
                        meta_map.get(r.book_id, {}).get("title", ""),
                        meta_map.get(r.book_id, {}).get("cover_url", ""),
                        authors_map.get(r.book_id, ([], []))[0],
                        authors_map.get(r.book_id, ([], []))[1],
                        meta_map.get(r.book_id, {}).get("series_name", ""),
                        meta_map.get(r.book_id, {}).get("series_slug", ""),
                        float(r.book_avg_rating) if r.book_avg_rating else 0.0,
                        int(r.book_rating_count) if r.book_rating_count else 0,
                    )
                    for r in rows
                ]
                return app.proto.user_data_pb2.RatingsListResponse(
                    ratings=protos, total_count=total_count
                )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserRatings: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def ToggleFavourite(
        self,
        request: app.proto.user_data_pb2.ToggleFavouriteRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.FavouriteResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                bookshelf = await app.services.bookshelf_service.toggle_favourite(
                    session, request.user_id, book_id, request.is_favorite
                )
                await app.cache.delete_book_cache(
                    *await _work_edition_slugs(session, request.book_slug)
                )
                await app.cache.delete_profile_stats(request.user_id)
                await app.cache.delete_profile_overview(request.user_id)
                await app.cache.delete_year_in_review(request.user_id)
                await app.cache.delete_bookshelf_list_cache(request.user_id)
                asyncio.create_task(
                    _recompute_user_stats_bg(request.user_id, "bookshelf")
                )
                return app.proto.user_data_pb2.FavouriteResponse(
                    is_favorite=bookshelf.is_favorite,
                    book_id=bookshelf.book_id,
                    book_slug=request.book_slug,
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in ToggleFavourite: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserFavourites(
        self,
        request: app.proto.user_data_pb2.GetUserFavouritesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        try:
            async with app.database.async_session_maker() as session:
                rows, total_count = (
                    await app.services.bookshelf_service.get_user_bookshelves(
                        session,
                        request.user_id,
                        request.limit or 10,
                        request.offset or 0,
                        status_filter="",
                        favourites_only=True,
                        sort_by="created_at",
                        order="desc",
                    )
                )

                meta_map = await _build_book_meta_map(
                    session, [r.book_id for r in rows]
                )
                authors_map = await _build_book_authors_map(
                    session, [r.book_id for r in rows]
                )

                protos = [
                    _bookshelf_to_proto(
                        r,
                        meta_map.get(r.book_id, {}).get("slug", ""),
                        meta_map.get(r.book_id, {}).get("title", ""),
                        meta_map.get(r.book_id, {}).get("cover_url", ""),
                        authors_map.get(r.book_id, ([], []))[0],
                        authors_map.get(r.book_id, ([], []))[1],
                        meta_map.get(r.book_id, {}).get("series_name", ""),
                        meta_map.get(r.book_id, {}).get("series_slug", ""),
                    )
                    for r in rows
                ]
                return app.proto.user_data_pb2.BookshelvesListResponse(
                    bookshelves=protos, total_count=total_count
                )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserFavourites: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def CreateComment(
        self,
        request: app.proto.user_data_pb2.CreateCommentRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.CommentResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_meta = await _resolve_book_meta(session, request.book_slug)
                comment = await app.services.comment_service.create_comment(
                    session,
                    request.user_id,
                    book_meta["book_id"],
                    request.body,
                    request.is_spoiler,
                )
                await _book_comments_cache.invalidate_by_book(book_meta["work_id"])
                await app.cache.delete_profile_stats(request.user_id)
                await app.cache.delete_profile_overview(request.user_id)
                await app.cache.delete_year_in_review(request.user_id)
                await app.cache.delete_comment_list_cache(request.user_id)
                asyncio.create_task(
                    _recompute_user_stats_bg(request.user_id, "comment")
                )
                username = await _resolve_username(session, request.user_id)
                return app.proto.user_data_pb2.CommentResponse(
                    comment=_comment_to_proto(
                        comment,
                        request.book_slug,
                        book_meta["title"],
                        username,
                        book_meta["author_names"],
                        book_meta["author_slugs"],
                        book_meta["series_name"],
                        book_meta["series_slug"],
                        book_meta["cover_url"],
                    )
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in CreateComment: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def UpdateComment(
        self,
        request: app.proto.user_data_pb2.UpdateCommentRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.CommentResponse:
        try:
            async with app.database.async_session_maker() as session:
                comment = await app.services.comment_service.update_comment(
                    session,
                    request.comment_id,
                    request.user_id,
                    request.body,
                    request.is_spoiler,
                )
                meta_map = await _build_book_meta_map(session, [comment.book_id])
                authors_map = await _build_book_authors_map(session, [comment.book_id])
                work_id = await _resolve_work_id(session, comment.book_id)
                if work_id:
                    await _book_comments_cache.invalidate_by_book(work_id)
                await app.cache.delete_profile_stats(request.user_id)
                await app.cache.delete_profile_overview(request.user_id)
                await app.cache.delete_year_in_review(request.user_id)
                await app.cache.delete_comment_list_cache(request.user_id)
                username = await _resolve_username(session, request.user_id)
                return app.proto.user_data_pb2.CommentResponse(
                    comment=_comment_to_proto(
                        comment,
                        meta_map.get(comment.book_id, {}).get("slug", ""),
                        meta_map.get(comment.book_id, {}).get("title", ""),
                        username,
                        authors_map.get(comment.book_id, ([], []))[0],
                        authors_map.get(comment.book_id, ([], []))[1],
                        meta_map.get(comment.book_id, {}).get("series_name", ""),
                        meta_map.get(comment.book_id, {}).get("series_slug", ""),
                        meta_map.get(comment.book_id, {}).get("cover_url", ""),
                    )
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in UpdateComment: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def DeleteComment(
        self,
        request: app.proto.user_data_pb2.DeleteCommentRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id_result = await session.execute(
                    sqlalchemy.text(
                        "SELECT book_id FROM user_data.comments WHERE comment_id = :id"
                    ),
                    {"id": request.comment_id},
                )
                book_id_row = book_id_result.fetchone()
                await app.services.comment_service.delete_comment(
                    session, request.comment_id, request.user_id
                )
                if book_id_row:
                    work_id = await _resolve_work_id(session, book_id_row.book_id)
                    if work_id:
                        await _book_comments_cache.invalidate_by_book(work_id)
                await app.cache.delete_profile_stats(request.user_id)
                await app.cache.delete_profile_overview(request.user_id)
                await app.cache.delete_year_in_review(request.user_id)
                await app.cache.delete_comment_list_cache(request.user_id)
                asyncio.create_task(
                    _recompute_user_stats_bg(request.user_id, "comment")
                )
                return app.proto.user_data_pb2.EmptyResponse()
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteComment: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserComments(
        self,
        request: app.proto.user_data_pb2.GetUserCommentsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.CommentsListResponse:
        try:
            limit = request.limit or 10
            offset = request.offset or 0
            sort_by = request.sort_by or "created_at"
            order = request.order or "desc"
            book_slug_key = request.book_slug or ""
            cache_key = (
                f"comments_list:{request.user_id}:{book_slug_key}:"
                f"{sort_by}:{order}:{limit}:{offset}"
            )
            cached = await app.cache.get_json(cache_key)
            if cached is not None:
                protos = [
                    app.proto.user_data_pb2.Comment(**entry)
                    for entry in cached["comments"]
                ]
                return app.proto.user_data_pb2.CommentsListResponse(
                    comments=protos, total_count=cached["total_count"]
                )

            async with app.database.async_session_maker() as session:
                filter_book_id: typing.Optional[int] = None
                filter_book_meta: typing.Dict[str, typing.Any] = {}
                if request.book_slug:
                    filter_book_meta = await _resolve_book_meta(
                        session, request.book_slug
                    )
                    filter_book_id = filter_book_meta["book_id"]

                rows, total_count = (
                    await app.services.comment_service.get_user_comments(
                        session,
                        request.user_id,
                        limit,
                        offset,
                        sort_by,
                        order,
                        filter_book_id,
                    )
                )

                if filter_book_meta:
                    meta_map = {r.book_id: filter_book_meta for r in rows}
                    authors_map = {
                        r.book_id: (
                            filter_book_meta["author_names"],
                            filter_book_meta["author_slugs"],
                        )
                        for r in rows
                    }
                else:
                    meta_map = await _build_book_meta_map(
                        session, [r.book_id for r in rows]
                    )
                    authors_map = await _build_book_authors_map(
                        session, [r.book_id for r in rows]
                    )

                username = (
                    await _resolve_username(session, request.user_id) if rows else ""
                )
                entries = [
                    {
                        "comment_id": r.comment_id,
                        "user_id": r.user_id,
                        "book_id": r.book_id,
                        "book_slug": meta_map.get(r.book_id, {}).get("slug", ""),
                        "book_title": meta_map.get(r.book_id, {}).get("title", ""),
                        "body": r.body,
                        "is_spoiler": r.is_spoiler,
                        "created_at": r.created_at.isoformat() if r.created_at else "",
                        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                        "username": username,
                        "book_author_names": authors_map.get(r.book_id, ([], []))[0],
                        "book_author_slugs": authors_map.get(r.book_id, ([], []))[1],
                        "book_series_name": meta_map.get(r.book_id, {}).get("series_name", ""),
                        "book_series_slug": meta_map.get(r.book_id, {}).get("series_slug", ""),
                        "book_cover_url": meta_map.get(r.book_id, {}).get("cover_url", ""),
                    }
                    for r in rows
                ]

            await app.cache.set_json(cache_key, {"total_count": total_count, "comments": entries}, ttl=300)
            protos = [app.proto.user_data_pb2.Comment(**e) for e in entries]
            return app.proto.user_data_pb2.CommentsListResponse(
                comments=protos, total_count=total_count
            )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserComments: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserBookInfo(
        self,
        request: app.proto.user_data_pb2.GetUserBookInfoRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.UserBookInfoResponse:
        try:
            async with app.database.async_session_maker() as session:
                result = await session.execute(
                    sqlalchemy.text(_USER_BOOK_INFO_SQL),
                    {"slug": request.book_slug, "uid": request.user_id},
                )
                row = result.fetchone()
                if row is None:
                    raise ValueError("book_not_found")

                return _row_to_user_book_info(
                    row, request.book_slug, request.user_id
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserBookInfo: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetBookStatuses(
        self,
        request: app.proto.user_data_pb2.GetBookStatusesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.BookStatusesResponse:
        try:
            book_ids = list(request.book_ids)
            if not book_ids:
                return app.proto.user_data_pb2.BookStatusesResponse()
            async with app.database.async_session_maker() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        "SELECT book_id, status, is_favorite "
                        "FROM user_data.bookshelves "
                        "WHERE user_id = :uid AND book_id = ANY(:ids)"
                    ),
                    {"uid": request.user_id, "ids": book_ids},
                )
                statuses = [
                    app.proto.user_data_pb2.BookStatus(
                        book_id=r.book_id,
                        status=r.status,
                        is_favorite=r.is_favorite,
                    )
                    for r in result.fetchall()
                ]
                return app.proto.user_data_pb2.BookStatusesResponse(statuses=statuses)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookStatuses: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetBookComments(
        self,
        request: app.proto.user_data_pb2.GetBookCommentsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.BookCommentsResponse:
        try:
            limit = request.limit or 10
            offset = request.offset or 0
            sort_by = request.sort_by or "created_at"
            order_dir = "ASC" if (request.order or "desc") == "asc" else "DESC"
            include_spoilers = request.include_spoilers
            rating_filters = list(request.rating_filters)
            sort_col = _VALID_SORT_COLS.get(sort_by, "c.created_at")

            async with app.database.async_session_maker() as session:
                book_result = await session.execute(
                    sqlalchemy.text(
                        "SELECT work_id FROM books.books WHERE slug = :slug ORDER BY book_id ASC LIMIT 1"
                    ),
                    {"slug": request.book_slug},
                )
                book_row = book_result.fetchone()
                if book_row is None:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND,
                        f"Book not found: {request.book_slug}",
                    )
                    return
                work_id = book_row.work_id

                cache_key = f"{work_id}:{sort_by}:{order_dir}:{include_spoilers}:{sorted(rating_filters)}:{limit}:{offset}"
                cached = await _book_comments_cache.get(cache_key)

                if cached is None:
                    rating_join = "LEFT JOIN"
                    where = (
                        "c.book_id IN (SELECT book_id FROM books.books WHERE work_id = :work_id) "
                        "AND c.is_deleted = FALSE"
                    )
                    params: typing.Dict[str, typing.Any] = {
                        "work_id": work_id,
                        "limit": limit,
                        "offset": offset,
                    }
                    if not include_spoilers:
                        where += " AND c.is_spoiler = FALSE"
                    if rating_filters:
                        rating_join = "INNER JOIN"
                        placeholders = ", ".join(f":rf_{i}" for i in range(len(rating_filters)))
                        where += f" AND r.overall_rating IN ({placeholders})"
                        for i, v in enumerate(rating_filters):
                            params[f"rf_{i}"] = v

                    count_result = await session.execute(
                        sqlalchemy.text(
                            f"""
                            SELECT COUNT(*)
                            FROM user_data.comments c
                            {rating_join} user_data.ratings r
                                   ON r.user_id = c.user_id AND r.book_id = c.book_id
                            WHERE {where}
                            """
                        ),
                        params,
                    )
                    total_count = count_result.scalar_one()

                    rows_result = await session.execute(
                        sqlalchemy.text(
                            f"""
                            SELECT c.comment_id, c.user_id, c.book_id, c.body, c.is_spoiler,
                                   c.created_at, c.updated_at,
                                   r.overall_rating, r.review_text, r.pacing, r.emotional_impact,
                                   r.intellectual_depth, r.writing_quality, r.rereadability,
                                   r.readability, r.plot_complexity, r.humor,
                                   a.username
                            FROM user_data.comments c
                            {rating_join} user_data.ratings r
                                   ON r.user_id = c.user_id AND r.book_id = c.book_id
                            LEFT JOIN auth.users a ON a.user_id = c.user_id
                            WHERE {where}
                            ORDER BY {sort_col} {order_dir} NULLS LAST, c.created_at DESC
                            LIMIT :limit OFFSET :offset
                        """
                        ),
                        params,
                    )
                    rows = rows_result.fetchall()
                    cached = (total_count, rows)
                    await _book_comments_cache.set(cache_key, cached)

                total_count, rows = cached
                comments = [
                    _row_to_comment_with_rating(row, request.book_slug) for row in rows
                ]

                my_entry = None
                if request.requesting_user_id:
                    my_row_result = await session.execute(
                        sqlalchemy.text(
                            """
                            SELECT c.comment_id, c.user_id, c.book_id, c.body, c.is_spoiler,
                                   c.created_at, c.updated_at,
                                   r.overall_rating, r.review_text, r.pacing, r.emotional_impact,
                                   r.intellectual_depth, r.writing_quality, r.rereadability,
                                   r.readability, r.plot_complexity, r.humor,
                                   a.username
                            FROM user_data.comments c
                            LEFT JOIN user_data.ratings r
                                   ON r.user_id = c.user_id AND r.book_id = c.book_id
                            LEFT JOIN auth.users a ON a.user_id = c.user_id
                            WHERE c.user_id = :user_id
                              AND c.book_id IN (
                                  SELECT book_id FROM books.books WHERE work_id = :work_id
                              )
                              AND c.is_deleted = FALSE
                        """
                        ),
                        {"user_id": request.requesting_user_id, "work_id": work_id},
                    )
                    my_row = my_row_result.fetchone()
                    if my_row:
                        my_entry = _row_to_comment_with_rating(
                            my_row, request.book_slug
                        )

                kwargs: typing.Dict[str, typing.Any] = {
                    "comments": comments,
                    "total_count": total_count,
                }
                if my_entry is not None:
                    kwargs["my_entry"] = my_entry
                return app.proto.user_data_pb2.BookCommentsResponse(**kwargs)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookComments: {e}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get book comments failed: {e}"
            )

    async def GetPublicProfileStats(
        self,
        request: app.proto.user_data_pb2.GetPublicProfileStatsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.ProfileStatsResponse:
        try:
            async with app.database.async_session_maker() as session:
                user_id = await _resolve_user(session, request.username)

                cache_key = f"profile_stats:{user_id}"
                cached = await app.cache.get_json(cache_key)
                if cached is not None:
                    return app.proto.user_data_pb2.ProfileStatsResponse(
                        stats=_profile_stats_to_proto(cached)
                    )

                data = await app.services.stats_service.get_profile_stats(session, user_id)
                await app.cache.set_json(cache_key, data, ttl=300)
                return app.proto.user_data_pb2.ProfileStatsResponse(
                    stats=_profile_stats_to_proto(data)
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetPublicProfileStats: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetProfileOverview(
        self,
        request: app.proto.user_data_pb2.GetProfileOverviewRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.ProfileOverviewResponse:
        try:
            async with app.database.async_session_maker() as session:
                user_id = await _resolve_user(session, request.username)

                cache_key = f"profile_overview:{user_id}"
                cached = await app.cache.get_json(cache_key)
                if cached is not None:
                    return _profile_overview_to_proto(cached)

                data = await _fetch_profile_overview(session, user_id)
                await app.cache.set_json(cache_key, data, ttl=300)
                return _profile_overview_to_proto(data)
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetProfileOverview: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetYearInReview(
        self,
        request: app.proto.user_data_pb2.GetYearInReviewRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.YearInReviewResponse:
        try:
            import datetime

            current_year = datetime.date.today().year
            year = request.year if request.year else current_year
            year = max(2000, min(year, current_year))

            async with app.database.async_session_maker() as session:
                cache_key = f"year_in_review:{request.user_id}:{year}"
                cached = await app.cache.get_json(cache_key)
                if cached is not None:
                    return app.proto.user_data_pb2.YearInReviewResponse(
                        review=_year_in_review_to_proto(cached)
                    )

                data = await app.services.stats_service.get_year_in_review(
                    session, request.user_id, year
                )
                await app.cache.set_json(cache_key, data, ttl=300)
                return app.proto.user_data_pb2.YearInReviewResponse(
                    review=_year_in_review_to_proto(data)
                )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetYearInReview: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def DeleteUserData(
        self,
        request: app.proto.user_data_pb2.DeleteUserDataRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.user_data_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                comment_book_ids = (
                    await app.services.comment_service.delete_user_comments(
                        session, request.user_id
                    )
                )
                await app.services.rating_service.delete_user_ratings(
                    session, request.user_id
                )
                await app.services.bookshelf_service.delete_user_bookshelves(
                    session, request.user_id
                )
                await session.execute(
                    sqlalchemy.text(
                        "DELETE FROM user_data.user_stats WHERE user_id = :user_id"
                    ),
                    {"user_id": request.user_id},
                )

                work_ids: typing.Set[str] = set()
                if comment_book_ids:
                    work_id_result = await session.execute(
                        sqlalchemy.text(
                            "SELECT DISTINCT work_id FROM books.books WHERE book_id = ANY(:ids)"
                        ),
                        {"ids": comment_book_ids},
                    )
                    work_ids = {row.work_id for row in work_id_result}

                await session.commit()

            for work_id in work_ids:
                await _book_comments_cache.invalidate_by_book(work_id)
            await app.cache.delete_profile_stats(request.user_id)
            await app.cache.delete_profile_overview(request.user_id)
            await app.cache.delete_year_in_review(request.user_id)

            return app.proto.user_data_pb2.EmptyResponse()
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteUserData: {e}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Delete user data failed: {e}"
            )


async def _build_book_meta_map(
    session, book_ids: typing.List[int]
) -> typing.Dict[int, typing.Dict[str, typing.Any]]:
    if not book_ids:
        return {}
    unique_ids = list(set(book_ids))
    result = await session.execute(
        sqlalchemy.text(
            "SELECT b.book_id, b.slug, b.title, b.primary_cover_url, "
            "s.name AS series_name, s.slug AS series_slug "
            "FROM books.books b "
            "LEFT JOIN books.series s ON s.series_id = b.series_id "
            "WHERE b.book_id = ANY(:ids)"
        ),
        {"ids": unique_ids},
    )
    return {
        row.book_id: {
            "slug": row.slug,
            "title": row.title or "",
            "cover_url": row.primary_cover_url or "",
            "series_name": row.series_name or "",
            "series_slug": row.series_slug or "",
        }
        for row in result.fetchall()
    }


async def _build_book_authors_map(
    session, book_ids: typing.List[int]
) -> typing.Dict[int, typing.Tuple[typing.List[str], typing.List[str]]]:
    if not book_ids:
        return {}
    unique_ids = list(set(book_ids))
    result = await session.execute(
        sqlalchemy.text(
            "SELECT ba.book_id, a.name, a.slug "
            "FROM books.book_authors ba "
            "JOIN books.authors a ON a.author_id = ba.author_id "
            "WHERE ba.book_id = ANY(:ids) "
            "ORDER BY ba.book_id"
        ),
        {"ids": unique_ids},
    )
    authors_map: typing.Dict[int, typing.Tuple[typing.List[str], typing.List[str]]] = {}
    for row in result.fetchall():
        if row.book_id not in authors_map:
            authors_map[row.book_id] = ([], [])
        authors_map[row.book_id][0].append(row.name)
        authors_map[row.book_id][1].append(row.slug)
    return authors_map


async def _build_book_slug_map(
    session, book_ids: typing.List[int]
) -> typing.Dict[int, str]:
    if not book_ids:
        return {}
    unique_ids = list(set(book_ids))
    result = await session.execute(
        sqlalchemy.text(
            "SELECT book_id, slug FROM books.books WHERE book_id = ANY(:ids)"
        ),
        {"ids": unique_ids},
    )
    return {row.book_id: row.slug for row in result.fetchall()}


async def _build_book_title_map(
    session, book_ids: typing.List[int]
) -> typing.Dict[int, str]:
    if not book_ids:
        return {}
    unique_ids = list(set(book_ids))
    result = await session.execute(
        sqlalchemy.text(
            "SELECT book_id, title FROM books.books WHERE book_id = ANY(:ids)"
        ),
        {"ids": unique_ids},
    )
    return {row.book_id: (row.title or "") for row in result.fetchall()}


async def _build_book_cover_map(
    session, book_ids: typing.List[int]
) -> typing.Dict[int, str]:
    if not book_ids:
        return {}
    unique_ids = list(set(book_ids))
    result = await session.execute(
        sqlalchemy.text(
            "SELECT book_id, primary_cover_url FROM books.books WHERE book_id = ANY(:ids)"
        ),
        {"ids": unique_ids},
    )
    return {row.book_id: (row.primary_cover_url or "") for row in result.fetchall()}
    return {row.book_id: (row.primary_cover_url or "") for row in result.fetchall()}
