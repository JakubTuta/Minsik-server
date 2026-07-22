import datetime
import re
import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

DEFAULT_BOOK_MAX_AUTHORS = 5
DEFAULT_BOOK_MAX_GENRES = 10
DEFAULT_AUTHOR_MIN_BOOKS = 1
DEFAULT_AUTHOR_MAX_BOOKS = 50
DEFAULT_SERIES_MIN_BOOKS = 2
DEFAULT_SERIES_MAX_BOOKS = 30

_MIN_PLAUSIBLE_YEAR = 1400
_PLACEHOLDER_TITLES = ["untitled", "unknown", "no title", "n/a", "tbd", "test"]
_JUNK_PUBLISHER_NAME_PATTERN = r"\m(publishing|publishers|press|editions|verlag|editorial)\M\s*$"

_TITLE_BLANK_RE = re.compile(r"^[\s\W]*$")
_TITLE_NUMERIC_PUNCT_RE = re.compile(r"^[0-9\s\W]+$")
_TITLE_URL_RE = re.compile(r"(https?://|www\.)", re.IGNORECASE)
_NAME_HAS_LETTER_RE = re.compile(r"[A-Za-z]")
_JUNK_PUBLISHER_NAME_RE = re.compile(_JUNK_PUBLISHER_NAME_PATTERN, re.IGNORECASE)


def _is_suspicious_title(title: str) -> bool:
    stripped = title.strip()
    return bool(
        _TITLE_BLANK_RE.match(title)
        or len(stripped) < 2
        or _TITLE_NUMERIC_PUNCT_RE.match(title)
        or _TITLE_URL_RE.search(title)
        or stripped.lower() in _PLACEHOLDER_TITLES
    )


def _is_junk_author_name(name: str) -> bool:
    stripped = name.strip()
    return bool(
        not _NAME_HAS_LETTER_RE.search(name)
        or len(stripped) < 2
        or _JUNK_PUBLISHER_NAME_RE.search(name)
    )


async def audit_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    limit: int,
    max_authors: int,
    max_genres: int,
    language: typing.Optional[str] = None,
) -> typing.List[typing.Dict[str, typing.Any]]:
    current_year = datetime.datetime.now(datetime.timezone.utc).year

    result = await session.execute(
        sqlalchemy.text(
            """
            WITH book_stats AS (
                SELECT
                    b.book_id,
                    b.title,
                    b.slug,
                    b.language,
                    b.primary_cover_url,
                    b.description,
                    b.original_publication_year,
                    (SELECT COUNT(*) FROM books.book_authors ba WHERE ba.book_id = b.book_id) AS author_count,
                    (SELECT COUNT(*) FROM books.book_genres bg WHERE bg.book_id = b.book_id) AS genre_count
                FROM books.books b
                WHERE (:language IS NULL OR b.language = :language)
            )
            SELECT * FROM book_stats
            WHERE author_count > :max_authors
               OR genre_count > :max_genres
               OR author_count = 0
               OR genre_count = 0
               OR description IS NULL OR description = ''
               OR primary_cover_url IS NULL
               OR original_publication_year > :max_year
               OR original_publication_year < :min_year
               OR title ~ '^[\\s\\W]*$'
               OR char_length(btrim(title)) < 2
               OR title ~* '(https?://|www\\.)'
               OR lower(btrim(title)) = ANY(:placeholder_titles)
            ORDER BY RANDOM()
            LIMIT :limit
            """
        ),
        {
            "language": language,
            "max_authors": max_authors,
            "max_genres": max_genres,
            "max_year": current_year + 1,
            "min_year": _MIN_PLAUSIBLE_YEAR,
            "placeholder_titles": _PLACEHOLDER_TITLES,
            "limit": limit,
        },
    )

    items = []
    for row in result.mappings():
        issues = []
        if row["author_count"] > max_authors:
            issues.append("too_many_authors")
        if row["author_count"] == 0:
            issues.append("no_authors")
        if row["genre_count"] > max_genres:
            issues.append("too_many_genres")
        if row["genre_count"] == 0:
            issues.append("no_genres")
        if not row["description"]:
            issues.append("missing_description")
        if not row["primary_cover_url"]:
            issues.append("missing_cover")
        year = row["original_publication_year"]
        if year is not None and (year > current_year + 1 or year < _MIN_PLAUSIBLE_YEAR):
            issues.append("implausible_year")
        if _is_suspicious_title(row["title"]):
            issues.append("suspicious_title")

        items.append(
            {
                "book_id": row["book_id"],
                "title": row["title"],
                "slug": row["slug"],
                "language": row["language"],
                "primary_cover_url": row["primary_cover_url"] or "",
                "author_count": row["author_count"],
                "genre_count": row["genre_count"],
                "original_publication_year": year or 0,
                "issues": issues,
            }
        )

    return items


async def audit_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    limit: int,
    min_books: int,
    max_books: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            WITH author_stats AS (
                SELECT
                    a.author_id,
                    a.name,
                    a.slug,
                    a.bio,
                    (SELECT COUNT(*) FROM books.book_authors ba WHERE ba.author_id = a.author_id) AS book_count
                FROM books.authors a
            )
            SELECT * FROM author_stats
            WHERE book_count < :min_books
               OR book_count > :max_books
               OR name !~ '[A-Za-z]'
               OR char_length(btrim(name)) < 2
               OR name ~* :junk_publisher_pattern
               OR bio IS NULL OR bio = ''
            ORDER BY RANDOM()
            LIMIT :limit
            """
        ),
        {
            "min_books": min_books,
            "max_books": max_books,
            "junk_publisher_pattern": _JUNK_PUBLISHER_NAME_PATTERN,
            "limit": limit,
        },
    )

    items = []
    for row in result.mappings():
        issues = []
        if row["book_count"] < min_books:
            issues.append("too_few_books")
        if row["book_count"] > max_books:
            issues.append("too_many_books")
        if _is_junk_author_name(row["name"]):
            issues.append("junk_name")
        if not row["bio"]:
            issues.append("missing_bio")

        items.append(
            {
                "author_id": row["author_id"],
                "name": row["name"],
                "slug": row["slug"],
                "book_count": row["book_count"],
                "issues": issues,
            }
        )

    return items


async def audit_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    limit: int,
    min_books: int,
    max_books: int,
    language: typing.Optional[str] = None,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            WITH series_stats AS (
                SELECT
                    s.series_id,
                    s.name,
                    s.slug,
                    s.language,
                    s.description,
                    s.total_books,
                    (SELECT COUNT(*) FROM books.books b WHERE b.series_id = s.series_id) AS actual_book_count
                FROM books.series s
                WHERE (:language IS NULL OR s.language = :language)
            )
            SELECT * FROM series_stats
            WHERE actual_book_count < :min_books
               OR actual_book_count > :max_books
               OR total_books IS DISTINCT FROM actual_book_count
               OR description IS NULL OR description = ''
            ORDER BY RANDOM()
            LIMIT :limit
            """
        ),
        {
            "language": language,
            "min_books": min_books,
            "max_books": max_books,
            "limit": limit,
        },
    )

    items = []
    for row in result.mappings():
        issues = []
        if row["actual_book_count"] < min_books:
            issues.append("too_few_books")
        if row["actual_book_count"] > max_books:
            issues.append("too_many_books")
        if row["total_books"] != row["actual_book_count"]:
            issues.append("count_drift")
        if not row["description"]:
            issues.append("missing_description")

        items.append(
            {
                "series_id": row["series_id"],
                "name": row["name"],
                "slug": row["slug"],
                "language": row["language"],
                "book_count": row["actual_book_count"],
                "total_books": row["total_books"] or 0,
                "issues": issues,
            }
        )

    return items
