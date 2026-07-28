import logging
import typing

import app.config
import app.models
import app.models.author
import app.models.book
import app.models.book_author
import app.models.book_genre
import app.models.genre
import app.utils
import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


async def insert_books_batch(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    books_data: typing.List[typing.Dict[str, typing.Any]],
    commit: bool = True,
    author_id_map: typing.Optional[typing.Dict[str, int]] = None,
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

        dedup_cache = _build_dedup_cache(cleaned_books)

        if author_id_map is None:
            author_id_map = await _bulk_insert_authors(
                session, cleaned_books, dedup_cache
            )
        genre_id_map = await _bulk_insert_genres(
            session, cleaned_books, dedup_cache, genre_id_cache
        )

        book_results = await _bulk_insert_books(
            session, cleaned_books, dedup_cache
        )
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
        external_ids, book_data.get("open_library_id"), slug
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
            author_slug = app.utils.slugify(author_data.get("name", ""))
            if author_slug and author_slug not in cache["authors"]:
                cache["authors"][author_slug] = author_data

        for genre_data in book.get("genres", []):
            genre_name = genre_data.get("name", "")
            if isinstance(genre_name, str):
                genre_name = genre_name.lower()[:100]
            genre_slug = app.utils.slugify(genre_name)[:150]
            if genre_slug and genre_slug not in cache["genres"]:
                cache["genres"][genre_slug] = {"name": genre_name, "slug": genre_slug}

    return cache


async def _bulk_insert_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: typing.List[typing.Dict[str, typing.Any]],
    dedup_cache: typing.Dict[str, typing.Any],
) -> typing.Dict[str, int]:
    if not dedup_cache["authors"]:
        return {}

    insert_data = []
    for author_slug, author_data in dedup_cache["authors"].items():
        name = app.utils.clean_name(author_data.get("name")) or author_data.get("name")
        insert_data.append(
            {
                "name": name,
                "slug": author_slug,
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

    insert_data.sort(key=lambda r: r["slug"])

    stmt = sqlalchemy.dialects.postgresql.insert(app.models.author.Author).values(insert_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["slug"],
        set_={
            "bio": sqlalchemy.case(
                (
                    app.models.author.Author.bio.is_(None),
                    stmt.excluded.bio,
                ),
                else_=app.models.author.Author.bio,
            ),
            "birth_date": sqlalchemy.case(
                (
                    app.models.author.Author.birth_date.is_(None),
                    stmt.excluded.birth_date,
                ),
                else_=app.models.author.Author.birth_date,
            ),
            "death_date": sqlalchemy.case(
                (
                    app.models.author.Author.death_date.is_(None),
                    stmt.excluded.death_date,
                ),
                else_=app.models.author.Author.death_date,
            ),
            "photo_url": sqlalchemy.case(
                (
                    app.models.author.Author.photo_url.is_(None),
                    stmt.excluded.photo_url,
                ),
                else_=app.models.author.Author.photo_url,
            ),
            "open_library_id": sqlalchemy.case(
                (
                    app.models.author.Author.open_library_id.is_(None),
                    stmt.excluded.open_library_id,
                ),
                else_=app.models.author.Author.open_library_id,
            ),
            "wikidata_id": sqlalchemy.case(
                (
                    app.models.author.Author.wikidata_id.is_(None),
                    stmt.excluded.wikidata_id,
                ),
                else_=app.models.author.Author.wikidata_id,
            ),
            "wikipedia_url": sqlalchemy.case(
                (
                    app.models.author.Author.wikipedia_url.is_(None),
                    stmt.excluded.wikipedia_url,
                ),
                else_=app.models.author.Author.wikipedia_url,
            ),
            "remote_ids": stmt.excluded.remote_ids.op("||")(app.models.author.Author.remote_ids),
            "alternate_names": sqlalchemy.case(
                (
                    sqlalchemy.or_(
                        app.models.author.Author.alternate_names.is_(None),
                        app.models.author.Author.alternate_names == sqlalchemy.text("'[]'::jsonb"),
                    ),
                    stmt.excluded.alternate_names,
                ),
                else_=app.models.author.Author.alternate_names,
            ),
        },
    )

    stmt = stmt.returning(
        app.models.author.Author.slug,
        app.models.author.Author.author_id,
    )
    result = await session.execute(stmt)
    return {row.slug: row.author_id for row in result}


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


async def _bulk_insert_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: typing.List[typing.Dict[str, typing.Any]],
    dedup_cache: typing.Dict[str, typing.Any],
) -> typing.Dict[str, typing.Any]:
    seen_slugs: dict[str, int] = {}
    for idx, book in enumerate(cleaned_books):
        key = (book["language"], book["slug"])
        seen_slugs[key] = idx
    cleaned_books = [cleaned_books[i] for i in sorted(seen_slugs.values())]

    insert_data = []

    for book in cleaned_books:
        book_entry = {
            "title": book["title"],
            "language": book["language"],
            "slug": book["slug"],
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
        }

        insert_data.append(book_entry)

    stmt = sqlalchemy.dialects.postgresql.insert(app.models.book.Book).values(insert_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["language", "slug"],
        set_={
            "description": sqlalchemy.case(
                (
                    stmt.excluded.description.is_(None),
                    app.models.book.Book.description,
                ),
                (
                    app.models.book.Book.description.is_(None),
                    stmt.excluded.description,
                ),
                (
                    sqlalchemy.func.length(stmt.excluded.description)
                    > sqlalchemy.func.length(app.models.book.Book.description),
                    stmt.excluded.description,
                ),
                else_=app.models.book.Book.description,
            ),
            "first_sentence": sqlalchemy.case(
                (
                    app.models.book.Book.first_sentence.is_(None),
                    stmt.excluded.first_sentence,
                ),
                else_=app.models.book.Book.first_sentence,
            ),
            "open_library_id": sqlalchemy.case(
                (
                    app.models.book.Book.open_library_id.is_(None),
                    stmt.excluded.open_library_id,
                ),
                else_=app.models.book.Book.open_library_id,
            ),
            "google_books_id": sqlalchemy.case(
                (
                    app.models.book.Book.google_books_id.is_(None),
                    stmt.excluded.google_books_id,
                ),
                else_=app.models.book.Book.google_books_id,
            ),
            "isbn": sqlalchemy.case(
                (
                    sqlalchemy.or_(
                        app.models.book.Book.isbn.is_(None),
                        app.models.book.Book.isbn == sqlalchemy.text("'[]'::jsonb"),
                    ),
                    stmt.excluded.isbn,
                ),
                else_=app.models.book.Book.isbn,
            ),
            "publisher": sqlalchemy.case(
                (
                    app.models.book.Book.publisher.is_(None),
                    stmt.excluded.publisher,
                ),
                else_=app.models.book.Book.publisher,
            ),
            "number_of_pages": sqlalchemy.case(
                (
                    sqlalchemy.or_(
                        app.models.book.Book.number_of_pages.is_(None),
                        app.models.book.Book.number_of_pages <= 0,
                    ),
                    stmt.excluded.number_of_pages,
                ),
                else_=app.models.book.Book.number_of_pages,
            ),
            "external_ids": sqlalchemy.case(
                (
                    sqlalchemy.or_(
                        app.models.book.Book.external_ids.is_(None),
                        app.models.book.Book.external_ids == sqlalchemy.text("'{}'::jsonb"),
                    ),
                    stmt.excluded.external_ids,
                ),
                else_=app.models.book.Book.external_ids,
            ),
            "formats": sqlalchemy.case(
                (
                    sqlalchemy.or_(
                        app.models.book.Book.formats.is_(None),
                        app.models.book.Book.formats == sqlalchemy.text("'[]'::jsonb"),
                    ),
                    stmt.excluded.formats,
                ),
                else_=app.models.book.Book.formats,
            ),
            "series_slug": sqlalchemy.case(
                (
                    app.models.book.Book.series_slug.is_(None),
                    stmt.excluded.series_slug,
                ),
                else_=app.models.book.Book.series_slug,
            ),
            "series_name": sqlalchemy.case(
                (
                    app.models.book.Book.series_name.is_(None),
                    stmt.excluded.series_name,
                ),
                else_=app.models.book.Book.series_name,
            ),
            "series_position": sqlalchemy.case(
                (
                    app.models.book.Book.series_position.is_(None),
                    stmt.excluded.series_position,
                ),
                else_=app.models.book.Book.series_position,
            ),
        },
    )

    stmt = stmt.returning(
        app.models.book.Book.slug,
        app.models.book.Book.book_id,
    )
    result = await session.execute(stmt)
    rows = result.all()

    book_id_map = {row.slug: row.book_id for row in rows}
    inserted_count = len(rows)
    updated_count = len(cleaned_books) - inserted_count

    return {
        "book_id_map": book_id_map,
        "inserted": inserted_count,
        "updated": updated_count,
    }


async def _bulk_insert_relationships(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: typing.List[typing.Dict[str, typing.Any]],
    dedup_cache: typing.Dict[str, typing.Any],
    book_id_map: typing.Dict[str, int],
    author_id_map: typing.Dict[str, int],
    genre_id_map: typing.Dict[str, int],
) -> None:
    book_authors_data = []
    book_genres_data = []

    for book in cleaned_books:
        book_id = book_id_map.get(book["slug"])
        if not book_id:
            continue

        for author_data in book.get("authors", []):
            author_slug = app.utils.slugify(author_data.get("name", ""))
            author_id = author_id_map.get(author_slug)
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
