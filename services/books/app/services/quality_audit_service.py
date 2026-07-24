import datetime
import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

_MIN_PLAUSIBLE_YEAR = 1400
_PLACEHOLDER_TITLES = ["untitled", "unknown", "no title", "n/a", "tbd", "test"]
_JUNK_PUBLISHER_NAME_PATTERN = r"\m(publishing|publishers|press|editions|verlag|editorial)\M\s*$"

_SUSPICIOUS_TITLE_CONDITION = (
    "(title ~ '^[\\s\\W]*$'"
    " OR char_length(btrim(title)) < 2"
    " OR title ~* '(https?://|www\\.)'"
    " OR lower(btrim(title)) = ANY(:placeholder_titles))"
)

_JUNK_NAME_CONDITION = (
    "(name !~ '[A-Za-z]'"
    " OR char_length(btrim(name)) < 2"
    " OR name ~* :junk_publisher_pattern)"
)


async def audit_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    limit: int,
    min_authors: int,
    max_authors: int,
    min_genres: int,
    max_genres: int,
    language: typing.Optional[str] = None,
    check_missing_description: bool = False,
    check_missing_cover: bool = False,
    check_implausible_year: bool = False,
    check_suspicious_title: bool = False,
) -> typing.List[typing.Dict[str, typing.Any]]:
    current_year = datetime.datetime.now(datetime.timezone.utc).year

    params: typing.Dict[str, typing.Any] = {
        "language": language,
        "min_authors": min_authors,
        "max_authors": max_authors,
        "min_genres": min_genres,
        "max_genres": max_genres,
        "limit": limit,
    }

    conditions = [
        "author_count BETWEEN :min_authors AND :max_authors",
        "genre_count BETWEEN :min_genres AND :max_genres",
    ]
    issues: typing.List[str] = []

    if check_missing_description:
        conditions.append("is_missing_description")
        issues.append("missing_description")

    if check_missing_cover:
        conditions.append("is_missing_cover")
        issues.append("missing_cover")

    if check_implausible_year:
        conditions.append(
            "(original_publication_year IS NOT NULL"
            " AND (original_publication_year > :max_year"
            " OR original_publication_year < :min_year))"
        )
        params["max_year"] = current_year + 1
        params["min_year"] = _MIN_PLAUSIBLE_YEAR
        issues.append("implausible_year")

    if check_suspicious_title:
        conditions.append(_SUSPICIOUS_TITLE_CONDITION)
        params["placeholder_titles"] = _PLACEHOLDER_TITLES
        issues.append("suspicious_title")

    query = f"""
        WITH author_counts AS (
            SELECT book_id, COUNT(*) AS author_count
            FROM books.book_authors
            GROUP BY book_id
        ),
        genre_counts AS (
            SELECT book_id, COUNT(*) AS genre_count
            FROM books.book_genres
            GROUP BY book_id
        ),
        book_stats AS (
            SELECT
                b.book_id,
                b.title,
                b.slug,
                b.language,
                b.primary_cover_url,
                b.original_publication_year,
                (b.description IS NULL OR btrim(b.description) = '') AS is_missing_description,
                (b.primary_cover_url IS NULL OR b.primary_cover_url = '') AS is_missing_cover,
                COALESCE(ac.author_count, 0) AS author_count,
                COALESCE(gc.genre_count, 0) AS genre_count
            FROM books.books b
            LEFT JOIN author_counts ac ON ac.book_id = b.book_id
            LEFT JOIN genre_counts gc ON gc.book_id = b.book_id
            WHERE (CAST(:language AS text) IS NULL OR b.language = CAST(:language AS text))
        )
        SELECT * FROM book_stats
        WHERE {" AND ".join(conditions)}
        ORDER BY RANDOM()
        LIMIT :limit
    """

    result = await session.execute(sqlalchemy.text(query), params)

    return [
        {
            "book_id": row["book_id"],
            "title": row["title"],
            "slug": row["slug"],
            "language": row["language"],
            "primary_cover_url": row["primary_cover_url"] or "",
            "author_count": row["author_count"],
            "genre_count": row["genre_count"],
            "original_publication_year": row["original_publication_year"] or 0,
            "issues": list(issues),
        }
        for row in result.mappings()
    ]


async def audit_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    limit: int,
    min_books: int,
    max_books: int,
    check_missing_bio: bool = False,
    check_junk_name: bool = False,
) -> typing.List[typing.Dict[str, typing.Any]]:
    params: typing.Dict[str, typing.Any] = {
        "min_books": min_books,
        "max_books": max_books,
        "limit": limit,
    }

    conditions = ["book_count BETWEEN :min_books AND :max_books"]
    issues: typing.List[str] = []

    if check_missing_bio:
        conditions.append("is_missing_bio")
        issues.append("missing_bio")

    if check_junk_name:
        conditions.append(_JUNK_NAME_CONDITION)
        params["junk_publisher_pattern"] = _JUNK_PUBLISHER_NAME_PATTERN
        issues.append("junk_name")

    query = f"""
        WITH author_book_counts AS (
            SELECT author_id, COUNT(*) AS book_count
            FROM books.book_authors
            GROUP BY author_id
        ),
        author_stats AS (
            SELECT
                a.author_id,
                a.name,
                a.slug,
                (a.bio IS NULL OR btrim(a.bio) = '') AS is_missing_bio,
                COALESCE(abc.book_count, 0) AS book_count
            FROM books.authors a
            LEFT JOIN author_book_counts abc ON abc.author_id = a.author_id
        )
        SELECT * FROM author_stats
        WHERE {" AND ".join(conditions)}
        ORDER BY RANDOM()
        LIMIT :limit
    """

    result = await session.execute(sqlalchemy.text(query), params)

    return [
        {
            "author_id": row["author_id"],
            "name": row["name"],
            "slug": row["slug"],
            "book_count": row["book_count"],
            "issues": list(issues),
        }
        for row in result.mappings()
    ]


async def audit_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    limit: int,
    min_books: int,
    max_books: int,
    language: typing.Optional[str] = None,
    check_missing_description: bool = False,
    check_count_drift: bool = False,
) -> typing.List[typing.Dict[str, typing.Any]]:
    params: typing.Dict[str, typing.Any] = {
        "language": language,
        "min_books": min_books,
        "max_books": max_books,
        "limit": limit,
    }

    conditions = ["actual_book_count BETWEEN :min_books AND :max_books"]
    issues: typing.List[str] = []

    if check_missing_description:
        conditions.append("is_missing_description")
        issues.append("missing_description")

    if check_count_drift:
        conditions.append("total_books IS DISTINCT FROM actual_book_count")
        issues.append("count_drift")

    query = f"""
        WITH series_book_counts AS (
            SELECT series_id, COUNT(*) AS actual_book_count
            FROM books.books
            WHERE series_id IS NOT NULL
            GROUP BY series_id
        ),
        series_stats AS (
            SELECT
                s.series_id,
                s.name,
                s.slug,
                s.language,
                s.total_books,
                (s.description IS NULL OR btrim(s.description) = '') AS is_missing_description,
                COALESCE(sbc.actual_book_count, 0) AS actual_book_count
            FROM books.series s
            LEFT JOIN series_book_counts sbc ON sbc.series_id = s.series_id
            WHERE (CAST(:language AS text) IS NULL OR s.language = CAST(:language AS text))
        )
        SELECT * FROM series_stats
        WHERE {" AND ".join(conditions)}
        ORDER BY RANDOM()
        LIMIT :limit
    """

    result = await session.execute(sqlalchemy.text(query), params)

    return [
        {
            "series_id": row["series_id"],
            "name": row["name"],
            "slug": row["slug"],
            "language": row["language"],
            "book_count": row["actual_book_count"],
            "total_books": row["total_books"] or 0,
            "issues": list(issues),
        }
        for row in result.mappings()
    ]
