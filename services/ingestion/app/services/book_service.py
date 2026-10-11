import logging
import typing

import app.config
import app.models
import app.models.author
import app.models.book
import app.models.book_author
import app.models.book_genre
import app.models.genre
import app.services.author_store
import app.utils
import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


async def insert_books_batch(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    books_data: typing.List[typing.Dict[str, typing.Any]],
    commit: bool = True,
    genre_id_cache: typing.Optional[typing.Dict[str, int]] = None,
) -> typing.Dict[str, int]:
    if not books_data:
        return {"successful": 0, "failed": 0, "updated": 0}

    successful = 0
    failed = 0
    updated = 0

    try:
        cleaned_books = []
        for book_data in books_data:
            try:
                cleaned = _validate_and_clean_book(book_data)
                if cleaned:
                    cleaned_books.append(cleaned)
            except Exception as e:
                logger.debug(
                    f"Error cleaning book '{book_data.get('title')}': {str(e)}"
                )
                failed += 1

        if not cleaned_books:
            if commit:
                await session.commit()
            return {"successful": 0, "failed": failed, "updated": 0}

        await _adopt_existing_works(session, cleaned_books)
        dedup_cache = _build_dedup_cache(cleaned_books)

        author_id_map = await _bulk_insert_authors(session, dedup_cache)
        genre_id_map = await _bulk_insert_genres(
            session, cleaned_books, dedup_cache, genre_id_cache
        )

        book_results = await _bulk_insert_books(session, cleaned_books)
        successful = book_results["inserted"]
        updated = book_results["updated"]

        await _bulk_insert_relationships(
            session,
            cleaned_books,
            dedup_cache,
            book_results["book_id_map"],
            author_id_map,
            genre_id_map,
        )

        await session.flush()

        if commit:
            await session.commit()

        return {"successful": successful, "failed": failed, "updated": updated}

    except Exception as e:
        logger.error(
            f"Error in insert_books_batch ({type(e).__name__}): {e}",
            exc_info=True,
        )
        await session.rollback()
        raise


def _validate_and_clean_book(book_data: typing.Dict[str, typing.Any]) -> typing.Optional[typing.Dict[str, typing.Any]]:
    title = book_data.get("title")
    if not title or not isinstance(title, str):
        return None

    language = book_data.get("language", "en")
    if isinstance(language, str):
        language = language.lower()

    title = app.utils.clean_name(title) or title
    description = app.utils.clean_description(book_data.get("description"))
    slug = app.utils.slugify(title)

    series_name = None
    series_slug = None
    series_position = None

    series_data = book_data.get("series")
    if series_data:
        series_name = app.utils.clean_name(series_data.get("name"))
        if series_name:
            series_slug = app.utils.slugify(series_name)
        series_position = series_data.get("position")
        series_position = app.utils.clamp_series_position(series_position)

    title = title[:500]

    formats = book_data.get("formats", [])
    formats = [fmt.lower() if isinstance(fmt, str) else fmt for fmt in formats]

    isbn = book_data.get("isbn", [])
    if not isinstance(isbn, list):
        isbn = []

    primary_cover_url = book_data.get("primary_cover_url")
    if isinstance(primary_cover_url, str):
        primary_cover_url = primary_cover_url[:1000]
    else:
        primary_cover_url = None

    publisher = book_data.get("publisher")
    if isinstance(publisher, str):
        publisher = publisher[:500]
    else:
        publisher = None

    number_of_pages = book_data.get("number_of_pages")
    if not isinstance(number_of_pages, int) or number_of_pages <= 0:
        number_of_pages = None

    external_ids = book_data.get("external_ids", {})
    if not isinstance(external_ids, dict):
        external_ids = {}

    work_id = app.utils.resolve_work_id(
        external_ids, book_data.get("open_library_id"), slug, book_data.get("google_books_id")
    )

    return {
        "title": title,
        "language": language,
        "slug": slug,
        "work_id": work_id,
        "description": description,
        "first_sentence": book_data.get("first_sentence"),
        "original_publication_year": book_data.get("original_publication_year"),
        "primary_cover_url": primary_cover_url,
        "open_library_id": book_data.get("open_library_id"),
        "google_books_id": book_data.get("google_books_id"),
        "series_slug": series_slug,
        "series_name": series_name,
        "series_position": series_position,
        "formats": formats,
        "isbn": isbn,
        "publisher": publisher,
        "number_of_pages": number_of_pages,
        "external_ids": external_ids,
        "authors": book_data.get("authors", []),
        "genres": book_data.get("genres", []),
    }


def _build_dedup_cache(cleaned_books: typing.List[typing.Dict[str, typing.Any]]) -> typing.Dict[str, typing.Any]:
    cache: typing.Dict[str, typing.Any] = {"authors": {}, "genres": {}}

    for book in cleaned_books:
        for author_data in book.get("authors", []):
            key = app.services.author_store.author_key(author_data)
            if key and key not in cache["authors"]:
                cache["authors"][key] = author_data

        for genre_data in book.get("genres", []):
            genre_name = genre_data.get("name", "")
            if isinstance(genre_name, str):
                genre_name = genre_name.lower()[:100]
            genre_slug = app.utils.slugify(genre_name)[:150]
            if genre_slug and genre_slug not in cache["genres"]:
                cache["genres"][genre_slug] = {"name": genre_name, "slug": genre_slug}

    return cache


_FIND_WORKS_BY_ISBN_SQL = sqlalchemy.text(
    "SELECT isbn_value, work_id FROM ("
    "  SELECT jsonb_array_elements_text(isbn) AS isbn_value, work_id FROM books.books WHERE isbn ?| CAST(:isbns AS text[])"
    ") matched WHERE isbn_value = ANY(CAST(:isbns AS text[]))"
)


async def _adopt_existing_works(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: typing.List[typing.Dict[str, typing.Any]],
) -> None:
    """A book with no OpenLibrary work id joins the work that already owns one of its ISBNs.

    Without this a Google Books record would become a second, separate work for a
    book the catalogue already has, and split its ratings, shelves and comments.
    """
    anonymous = [
        book for book in cleaned_books
        if book["isbn"] and not (book["external_ids"].get("work_ol_id") or book.get("open_library_id"))
    ]
    if not anonymous:
        return
    isbns = sorted({isbn for book in anonymous for isbn in book["isbn"] if isinstance(isbn, str)})
    work_by_isbn = {
        row.isbn_value: row.work_id
        for row in await session.execute(_FIND_WORKS_BY_ISBN_SQL, {"isbns": isbns})
    }
    for book in anonymous:
        known = next((work_by_isbn[isbn] for isbn in book["isbn"] if isbn in work_by_isbn), None)
        if known:
            book["work_id"] = known


async def _bulk_insert_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    dedup_cache: typing.Dict[str, typing.Any],
) -> typing.Dict[str, int]:
    authors = []
    for author_data in dedup_cache["authors"].values():
        authors.append(
            {
                "name": app.utils.clean_name(author_data.get("name")) or author_data.get("name"),
                "bio": app.utils.clean_description(author_data.get("bio")),
                "birth_date": app.utils.parse_date(author_data.get("birth_date")),
                "death_date": app.utils.parse_date(author_data.get("death_date")),
                "photo_url": author_data.get("photo_url"),
                "open_library_id": author_data.get("open_library_id"),
                "wikidata_id": author_data.get("wikidata_id"),
                "wikipedia_url": author_data.get("wikipedia_url"),
                "remote_ids": author_data.get("remote_ids", {}),
                "alternate_names": author_data.get("alternate_names", []),
            }
        )
    if not authors:
        return {}
    return await app.services.author_store.upsert_authors(session, authors)


async def _bulk_insert_genres(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: typing.List[typing.Dict[str, typing.Any]],
    dedup_cache: typing.Dict[str, typing.Any],
    genre_id_cache: typing.Optional[typing.Dict[str, int]] = None,
) -> typing.Dict[str, int]:
    if not dedup_cache["genres"]:
        return genre_id_cache or {}

    if genre_id_cache is None:
        genre_id_cache = {}

    new_slugs = [s for s in dedup_cache["genres"] if s not in genre_id_cache]
    if new_slugs:
        insert_data = [dedup_cache["genres"][s] for s in new_slugs]
        insert_data.sort(key=lambda r: r["slug"])
        stmt = sqlalchemy.dialects.postgresql.insert(app.models.genre.Genre).values(insert_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["slug"],
            set_={"name": stmt.excluded.name},
        )
        stmt = stmt.returning(
            app.models.genre.Genre.slug,
            app.models.genre.Genre.genre_id,
        )
        result = await session.execute(stmt)
        for row in result:
            genre_id_cache[row.slug] = row.genre_id

    return {s: genre_id_cache[s] for s in dedup_cache["genres"] if s in genre_id_cache}


_FIND_TAKEN_SLUGS_SQL = sqlalchemy.text("SELECT work_id, language, slug FROM books.books WHERE slug = ANY(:slugs)")

_FILL_IF_NULL_COLUMNS = (
    "first_sentence", "open_library_id", "google_books_id", "publisher",
    "series_slug", "series_name", "series_position",
)
_FILL_IF_EMPTY_COLUMNS = (("isbn", "'[]'::jsonb"), ("external_ids", "'{}'::jsonb"), ("formats", "'[]'::jsonb"))


async def _bulk_insert_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: typing.List[typing.Dict[str, typing.Any]],
) -> typing.Dict[str, typing.Any]:
    """Upsert on (work_id, language): one row per edition language of a work.

    An existing row only has gaps filled. A new row keeps its title slug unless
    another work already holds it in that language, in which case the work id is
    appended, so two different books with the same title never overwrite each other.
    """
    latest: dict[tuple[str, str], dict] = {}
    for book in cleaned_books:
        latest[(book["work_id"], book["language"])] = book
    cleaned_books = list(latest.values())

    held_by = {
        (row.language, row.slug): row.work_id
        for row in await session.execute(_FIND_TAKEN_SLUGS_SQL, {"slugs": sorted({b["slug"] for b in cleaned_books})})
    }
    insert_data = []
    for book in cleaned_books:
        slug = book["slug"]
        holder = held_by.get((book["language"], slug))
        if holder is not None and holder != book["work_id"]:
            slug = f"{slug}-{app.utils.slugify(book['work_id'])}"[:600]
        held_by[(book["language"], slug)] = book["work_id"]
        insert_data.append(
            {
                "title": book["title"],
                "language": book["language"],
                "slug": slug,
                "work_id": book["work_id"],
                "description": book["description"],
                "first_sentence": book.get("first_sentence"),
                "original_publication_year": book["original_publication_year"],
                "primary_cover_url": book["primary_cover_url"],
                "open_library_id": book["open_library_id"],
                "google_books_id": book["google_books_id"],
                "series_slug": book.get("series_slug"),
                "series_name": book.get("series_name"),
                "series_position": book.get("series_position"),
                "formats": book["formats"],
                "isbn": book.get("isbn", []),
                "publisher": book.get("publisher"),
                "number_of_pages": book.get("number_of_pages"),
                "external_ids": book.get("external_ids", {}),
                "edition_source": "edition",
            }
        )

    books = app.models.book.Book.__table__.c
    stmt = sqlalchemy.dialects.postgresql.insert(app.models.book.Book).values(insert_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["work_id", "language"],
        set_={
            "description": sqlalchemy.case(
                (sqlalchemy.literal("description") == sqlalchemy.any_(books.manually_edited_fields), books.description),
                (stmt.excluded.description.is_(None), books.description),
                (books.description.is_(None), stmt.excluded.description),
                (sqlalchemy.func.length(stmt.excluded.description) > sqlalchemy.func.length(books.description), stmt.excluded.description),
                else_=books.description,
            ),
            **{
                column: sqlalchemy.case((books[column].is_(None), stmt.excluded[column]), else_=books[column])
                for column in _FILL_IF_NULL_COLUMNS
            },
            **{
                column: sqlalchemy.case(
                    (sqlalchemy.or_(books[column].is_(None), books[column] == sqlalchemy.text(empty)), stmt.excluded[column]),
                    else_=books[column],
                )
                for column, empty in _FILL_IF_EMPTY_COLUMNS
            },
            "number_of_pages": sqlalchemy.case(
                (sqlalchemy.or_(books.number_of_pages.is_(None), books.number_of_pages <= 0), stmt.excluded.number_of_pages),
                else_=books.number_of_pages,
            ),
        },
    )

    stmt = stmt.returning(
        books.work_id,
        books.language,
        books.book_id,
        sqlalchemy.literal_column("(xmax = 0)").label("inserted"),
    )
    rows = (await session.execute(stmt)).all()

    return {
        "book_id_map": {(row.work_id, row.language): row.book_id for row in rows},
        "inserted": sum(1 for row in rows if row.inserted),
        "updated": sum(1 for row in rows if not row.inserted),
    }


async def _bulk_insert_relationships(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: typing.List[typing.Dict[str, typing.Any]],
    dedup_cache: typing.Dict[str, typing.Any],
    book_id_map: typing.Dict[typing.Tuple[str, str], int],
    author_id_map: typing.Dict[str, int],
    genre_id_map: typing.Dict[str, int],
) -> None:
    book_authors_data = []
    book_genres_data = []

    for book in cleaned_books:
        book_id = book_id_map.get((book["work_id"], book["language"]))
        if not book_id:
            continue

        for author_data in book.get("authors", []):
            author_id = author_id_map.get(app.services.author_store.author_key(author_data))
            if author_id:
                book_authors_data.append({"book_id": book_id, "author_id": author_id})

        for genre_data in book.get("genres", []):
            genre_name = genre_data.get("name", "")
            if isinstance(genre_name, str):
                genre_name = genre_name.lower()[:100]
            genre_slug = app.utils.slugify(genre_name)[:150]
            genre_id = genre_id_map.get(genre_slug)
            if genre_id:
                book_genres_data.append({"book_id": book_id, "genre_id": genre_id})

    if book_authors_data:
        stmt = sqlalchemy.dialects.postgresql.insert(app.models.book_author.BookAuthor).values(
            book_authors_data
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["book_id", "author_id"])
        await session.execute(stmt)

    if book_genres_data:
        stmt = sqlalchemy.dialects.postgresql.insert(app.models.book_genre.BookGenre).values(
            book_genres_data
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["book_id", "genre_id"])
        await session.execute(stmt)


async def process_single_book(
    session: sqlalchemy.ext.asyncio.AsyncSession, book_data: typing.Dict[str, typing.Any]
) -> None:
    result = await insert_books_batch(session, [book_data], commit=False)
    if result["failed"] > 0:
        raise ValueError(f"Failed to process book: {book_data.get('title')}")
