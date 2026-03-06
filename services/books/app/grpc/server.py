import logging
import typing

import app.db
import app.proto.books_pb2
import app.proto.books_pb2_grpc
import app.services.author_service
import app.services.book_service
import app.services.case_service
import app.services.discovery_service
import app.services.search_service
import app.services.series_service
import grpc

logger = logging.getLogger(__name__)


def _build_book_detail_proto(
    book: typing.Dict[str, typing.Any],
) -> app.proto.books_pb2.BookDetail:
    authors = [
        app.proto.books_pb2.AuthorInfo(
            author_id=author["author_id"],
            name=author["name"],
            slug=author["slug"],
            photo_url=author["photo_url"],
        )
        for author in book["authors"]
    ]
    genres = [
        app.proto.books_pb2.GenreInfo(
            genre_id=genre["genre_id"],
            name=genre["name"],
            slug=genre["slug"],
        )
        for genre in book["genres"]
    ]
    cover_history = [
        app.proto.books_pb2.CoverHistory(
            url=cover.get("url", ""),
            width=cover.get("width", 0),
            size=cover.get("size", ""),
        )
        for cover in book["cover_history"]
    ]
    series_info = None
    if book.get("series"):
        series_info = app.proto.books_pb2.SeriesInfo(
            series_id=book["series"]["series_id"],
            name=book["series"]["name"],
            slug=book["series"]["slug"],
            total_books=book["series"].get("total_books", 0),
        )
    sub_rating_stats = {
        key: app.proto.books_pb2.SubRatingStat(
            avg=str(val.get("avg")) if val.get("avg") is not None else "",
            count=val.get("count", 0),
        )
        for key, val in book.get("sub_rating_stats", {}).items()
    }
    return app.proto.books_pb2.BookDetail(
        book_id=book["book_id"],
        title=book["title"],
        slug=book["slug"],
        description=book["description"],
        language=book["language"],
        original_publication_year=book["original_publication_year"],
        formats=book["formats"],
        primary_cover_url=book["primary_cover_url"],
        cover_history=cover_history,
        rating_count=book["rating_count"],
        avg_rating=book["avg_rating"],
        view_count=book["view_count"],
        last_viewed_at=book["last_viewed_at"],
        authors=authors,
        genres=genres,
        open_library_id=book["open_library_id"],
        google_books_id=book["google_books_id"],
        created_at=book["created_at"],
        updated_at=book["updated_at"],
        series=series_info,
        series_position=book.get("series_position", ""),
        sub_rating_stats=sub_rating_stats,
        isbn=book.get("isbn", []),
        publisher=book.get("publisher", ""),
        number_of_pages=book.get("number_of_pages", 0),
        external_ids=book.get("external_ids", {}),
        ol_rating_count=book.get("ol_rating_count", 0),
        ol_avg_rating=book.get("ol_avg_rating", "0.00"),
        ol_want_to_read_count=book.get("ol_want_to_read_count", 0),
        ol_currently_reading_count=book.get("ol_currently_reading_count", 0),
        ol_already_read_count=book.get("ol_already_read_count", 0),
        first_sentence=book.get("first_sentence", ""),
        app_want_to_read_count=book.get("app_want_to_read_count", 0),
        app_reading_count=book.get("app_reading_count", 0),
        app_read_count=book.get("app_read_count", 0),
    )


def _build_book_summary_proto(
    item: typing.Dict[str, typing.Any],
) -> app.proto.books_pb2.BookSummary:
    authors = [
        app.proto.books_pb2.AuthorInfo(
            author_id=a["author_id"],
            name=a["name"],
            slug=a["slug"],
            photo_url=a.get("photo_url", ""),
        )
        for a in item.get("authors", [])
    ]
    return app.proto.books_pb2.BookSummary(
        book_id=item["book_id"],
        title=item["title"],
        slug=item["slug"],
        description=item.get("description", ""),
        primary_cover_url=item.get("primary_cover_url", ""),
        authors=authors,
        rating_count=item["rating_count"],
        avg_rating=item.get("avg_rating", "0.00"),
        ol_rating_count=item.get("ol_rating_count", 0),
        ol_avg_rating=item.get("ol_avg_rating", "0.00"),
        ol_want_to_read_count=item.get("ol_want_to_read_count", 0),
        ol_currently_reading_count=item.get("ol_currently_reading_count", 0),
        ol_already_read_count=item.get("ol_already_read_count", 0),
        app_want_to_read_count=item.get("app_want_to_read_count", 0),
        app_reading_count=item.get("app_reading_count", 0),
        app_read_count=item.get("app_read_count", 0),
        series_position=item.get("series_position", "") or "",
        rarity=item.get("rarity", "") or "",
    )


class BooksServicer(app.proto.books_pb2_grpc.BooksServiceServicer):
    async def SearchBooksAndAuthors(
        self,
        request: app.proto.books_pb2.SearchRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.SearchResponse:
        try:
            async with app.db.async_session_maker() as session:
                results, total = (
                    await app.services.search_service.search_books_and_authors(
                        session,
                        request.query,
                        request.limit or 10,
                        request.offset or 0,
                        request.type_filter or "both",
                        request.language or "en",
                    )
                )

                search_results = []
                for result in results:
                    search_results.append(
                        app.proto.books_pb2.SearchResult(
                            type=result["type"],
                            id=result["id"],
                            title=result["title"],
                            slug=result["slug"],
                            cover_url=result["cover_url"],
                            authors=result["authors"],
                            relevance_score=result["relevance_score"],
                            author_slugs=result["author_slugs"],
                            series_slug=result["series_slug"],
                            app_avg_rating=(
                                str(result["app_avg_rating"])
                                if result.get("app_avg_rating") is not None
                                else ""
                            ),
                            app_rating_count=result.get("app_rating_count", 0),
                            ol_avg_rating=(
                                str(result["ol_avg_rating"])
                                if result.get("ol_avg_rating") is not None
                                else ""
                            ),
                            ol_rating_count=result.get("ol_rating_count", 0),
                            book_count=result.get("book_count", 0),
                        )
                    )

                return app.proto.books_pb2.SearchResponse(
                    results=search_results, total_count=total
                )
        except Exception as e:
            logger.error(f"Error in SearchBooksAndAuthors: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Search failed: {str(e)}")

    async def GetBook(
        self,
        request: app.proto.books_pb2.GetBookRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.BookDetailResponse:
        try:
            async with app.db.async_session_maker() as session:
                book = await app.services.book_service.get_book_by_slug(
                    session, request.slug, request.language or "en"
                )

                if not book:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND, f"Book not found: {request.slug}"
                    )

                return app.proto.books_pb2.BookDetailResponse(
                    book=_build_book_detail_proto(book)
                )
        except Exception as e:
            logger.error(f"Error in GetBook: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get book failed: {str(e)}")

    async def GetAuthor(
        self,
        request: app.proto.books_pb2.GetAuthorRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.AuthorDetailResponse:
        try:
            async with app.db.async_session_maker() as session:
                author = await app.services.author_service.get_author_by_slug(
                    session, request.slug, request.language or "en"
                )

                if not author:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND, f"Author not found: {request.slug}"
                    )

                author_detail = app.proto.books_pb2.AuthorDetail(
                    author_id=author["author_id"],
                    name=author["name"],
                    slug=author["slug"],
                    bio=author["bio"] or "",
                    birth_date=author["birth_date"] or "",
                    death_date=author["death_date"] or "",
                    photo_url=author["photo_url"] or "",
                    view_count=author["view_count"],
                    last_viewed_at=author["last_viewed_at"] or "",
                    books_count=author["books_count"],
                    open_library_id=author["open_library_id"] or "",
                    created_at=author["created_at"],
                    updated_at=author["updated_at"],
                    birth_place=author["birth_place"] or "",
                    nationality=author["nationality"] or "",
                    book_categories=author["book_categories"],
                    books_avg_rating=author["books_avg_rating"],
                    books_total_ratings=author["books_total_ratings"],
                    wikidata_id=author["wikidata_id"] or "",
                    wikipedia_url=author["wikipedia_url"] or "",
                    remote_ids=author.get("remote_ids", {}),
                    alternate_names=author.get("alternate_names", []),
                    books_ol_avg_rating=author["books_ol_avg_rating"],
                    books_ol_total_ratings=author["books_ol_total_ratings"],
                    app_want_to_read_count=author["app_want_to_read_count"],
                    app_reading_count=author["app_reading_count"],
                    app_read_count=author["app_read_count"],
                    ol_want_to_read_count=author["ol_want_to_read_count"],
                    ol_currently_reading_count=author["ol_currently_reading_count"],
                    ol_already_read_count=author["ol_already_read_count"],
                )

                return app.proto.books_pb2.AuthorDetailResponse(author=author_detail)
        except Exception as e:
            logger.error(f"Error in GetAuthor: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get author failed: {str(e)}"
            )

    async def GetAuthorBooks(
        self,
        request: app.proto.books_pb2.GetAuthorBooksRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.BooksListResponse:
        try:
            async with app.db.async_session_maker() as session:
                books, total = await app.services.author_service.get_author_books(
                    session,
                    request.author_slug,
                    request.limit or 10,
                    request.offset or 0,
                    request.sort_by or "view_count",
                    request.order or "desc",
                    request.language or "en",
                )

                book_summaries = [_build_book_summary_proto(book) for book in books]

                return app.proto.books_pb2.BooksListResponse(
                    books=book_summaries, total_count=total
                )
        except Exception as e:
            logger.error(f"Error in GetAuthorBooks: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get author books failed: {str(e)}"
            )

    async def GetSeries(
        self,
        request: app.proto.books_pb2.GetSeriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.SeriesDetailResponse:
        try:
            async with app.db.async_session_maker() as session:
                series = await app.services.series_service.get_series_by_slug(
                    session, request.slug, request.language or "en"
                )

                if not series:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND, f"Series not found: {request.slug}"
                    )

                series_detail = app.proto.books_pb2.SeriesDetail(
                    series_id=series["series_id"],
                    name=series["name"],
                    slug=series["slug"],
                    description=series["description"],
                    total_books=series["total_books"],
                    view_count=series["view_count"],
                    last_viewed_at=series["last_viewed_at"] or "",
                    created_at=series["created_at"] or "",
                    updated_at=series["updated_at"] or "",
                    avg_rating=series["avg_rating"] or "",
                    rating_count=series["rating_count"],
                    ol_avg_rating=series["ol_avg_rating"] or "",
                    ol_rating_count=series["ol_rating_count"],
                    app_want_to_read_count=series["app_want_to_read_count"],
                    app_reading_count=series["app_reading_count"],
                    app_read_count=series["app_read_count"],
                    ol_want_to_read_count=series["ol_want_to_read_count"],
                    ol_currently_reading_count=series["ol_currently_reading_count"],
                    ol_already_read_count=series["ol_already_read_count"],
                )

                return app.proto.books_pb2.SeriesDetailResponse(series=series_detail)
        except Exception as e:
            logger.error(f"Error in GetSeries: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get series failed: {str(e)}"
            )

    async def GetSeriesBooks(
        self,
        request: app.proto.books_pb2.GetSeriesBooksRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.BooksListResponse:
        try:
            async with app.db.async_session_maker() as session:
                books, total = await app.services.series_service.get_series_books(
                    session,
                    request.series_slug,
                    request.limit or 10,
                    request.offset or 0,
                    request.language or "en",
                    request.sort_by or "series_position",
                    request.order or "asc",
                )

                book_summaries = [_build_book_summary_proto(book) for book in books]

                return app.proto.books_pb2.BooksListResponse(
                    books=book_summaries, total_count=total
                )
        except Exception as e:
            logger.error(f"Error in GetSeriesBooks: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get series books failed: {str(e)}"
            )

    async def UpdateBook(
        self,
        request: app.proto.books_pb2.UpdateBookRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.BookDetailResponse:
        import json

        try:
            async with app.db.async_session_maker() as session:
                updates: typing.Dict[str, typing.Any] = {}

                if request.HasField("title"):
                    updates["title"] = request.title
                if request.HasField("slug"):
                    updates["slug"] = request.slug
                if request.HasField("description"):
                    updates["description"] = request.description
                if request.HasField("first_sentence"):
                    updates["first_sentence"] = request.first_sentence
                if request.HasField("language"):
                    updates["language"] = request.language
                if request.HasField("original_publication_year"):
                    updates["original_publication_year"] = (
                        request.original_publication_year
                    )
                if request.HasField("primary_cover_url"):
                    updates["primary_cover_url"] = request.primary_cover_url
                if request.HasField("formats_json"):
                    updates["formats"] = json.loads(request.formats_json)
                if request.HasField("cover_history_json"):
                    updates["cover_history"] = json.loads(request.cover_history_json)
                if request.HasField("isbn_json"):
                    updates["isbn"] = json.loads(request.isbn_json)
                if request.HasField("publisher"):
                    updates["publisher"] = request.publisher
                if request.HasField("number_of_pages"):
                    updates["number_of_pages"] = request.number_of_pages
                if request.HasField("external_ids_json"):
                    updates["external_ids"] = json.loads(request.external_ids_json)
                if request.HasField("open_library_id"):
                    updates["open_library_id"] = request.open_library_id
                if request.HasField("google_books_id"):
                    updates["google_books_id"] = request.google_books_id
                if request.HasField("series_id"):
                    updates["series_id"] = (
                        request.series_id if request.series_id != 0 else None
                    )
                if request.HasField("series_position"):
                    updates["series_position"] = (
                        float(request.series_position)
                        if request.series_position
                        else None
                    )

                book = await app.services.book_service.update_book(
                    session, request.book_id, updates
                )

                if not book:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND,
                        f"Book with id {request.book_id} not found",
                    )
                    return

                authors = [
                    app.proto.books_pb2.AuthorInfo(
                        author_id=a["author_id"],
                        name=a["name"],
                        slug=a["slug"],
                        photo_url=a.get("photo_url", ""),
                    )
                    for a in book.get("authors", [])
                ]
                genres = [
                    app.proto.books_pb2.GenreInfo(
                        genre_id=g["genre_id"], name=g["name"], slug=g["slug"]
                    )
                    for g in book.get("genres", [])
                ]
                series_info = None
                if book.get("series"):
                    s = book["series"]
                    series_info = app.proto.books_pb2.SeriesInfo(
                        series_id=s["series_id"],
                        name=s["name"],
                        slug=s["slug"],
                        total_books=s.get("total_books", 0),
                    )

                cover_history = [
                    app.proto.books_pb2.CoverHistory(
                        url=c.get("url", ""),
                        width=c.get("width", 0),
                        size=c.get("size", ""),
                    )
                    for c in book.get("cover_history", [])
                ]

                sub_rating_stats = {
                    k: app.proto.books_pb2.SubRatingStat(
                        avg=v.get("avg", "0"), count=v.get("count", 0)
                    )
                    for k, v in book.get("sub_rating_stats", {}).items()
                }

                book_detail = app.proto.books_pb2.BookDetail(
                    book_id=book["book_id"],
                    title=book["title"],
                    slug=book["slug"],
                    description=book.get("description", ""),
                    first_sentence=book.get("first_sentence", ""),
                    language=book["language"],
                    original_publication_year=book.get("original_publication_year", 0),
                    formats=book.get("formats", []),
                    primary_cover_url=book.get("primary_cover_url", ""),
                    cover_history=cover_history,
                    rating_count=book.get("rating_count", 0),
                    avg_rating=book.get("avg_rating", "0.00"),
                    sub_rating_stats=sub_rating_stats,
                    view_count=book.get("view_count", 0),
                    last_viewed_at=book.get("last_viewed_at", ""),
                    authors=authors,
                    genres=genres,
                    open_library_id=book.get("open_library_id", ""),
                    google_books_id=book.get("google_books_id", ""),
                    created_at=book.get("created_at", ""),
                    updated_at=book.get("updated_at", ""),
                    series=series_info,
                    series_position=book.get("series_position", ""),
                    isbn=book.get("isbn", []),
                    publisher=book.get("publisher", ""),
                    number_of_pages=book.get("number_of_pages", 0),
                    external_ids=book.get("external_ids", {}),
                    ol_rating_count=book.get("ol_rating_count", 0),
                    ol_avg_rating=book.get("ol_avg_rating", "0.00"),
                    ol_want_to_read_count=book.get("ol_want_to_read_count", 0),
                    ol_currently_reading_count=book.get(
                        "ol_currently_reading_count", 0
                    ),
                    ol_already_read_count=book.get("ol_already_read_count", 0),
                    app_want_to_read_count=book.get("app_want_to_read_count", 0),
                    app_reading_count=book.get("app_reading_count", 0),
                    app_read_count=book.get("app_read_count", 0),
                )

                return app.proto.books_pb2.BookDetailResponse(book=book_detail)
        except Exception as e:
            logger.error(f"Error in UpdateBook: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Update book failed: {str(e)}"
            )

    async def UpdateAuthor(
        self,
        request: app.proto.books_pb2.UpdateAuthorRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.AuthorDetailResponse:
        import datetime
        import json

        try:
            async with app.db.async_session_maker() as session:
                updates: typing.Dict[str, typing.Any] = {}

                if request.HasField("name"):
                    updates["name"] = request.name
                if request.HasField("slug"):
                    updates["slug"] = request.slug
                if request.HasField("bio"):
                    updates["bio"] = request.bio
                if request.HasField("birth_date"):
                    updates["birth_date"] = (
                        datetime.date.fromisoformat(request.birth_date)
                        if request.birth_date
                        else None
                    )
                if request.HasField("death_date"):
                    updates["death_date"] = (
                        datetime.date.fromisoformat(request.death_date)
                        if request.death_date
                        else None
                    )
                if request.HasField("birth_place"):
                    updates["birth_place"] = request.birth_place
                if request.HasField("nationality"):
                    updates["nationality"] = request.nationality
                if request.HasField("photo_url"):
                    updates["photo_url"] = request.photo_url
                if request.HasField("wikidata_id"):
                    updates["wikidata_id"] = request.wikidata_id
                if request.HasField("wikipedia_url"):
                    updates["wikipedia_url"] = request.wikipedia_url
                if request.HasField("remote_ids_json"):
                    updates["remote_ids"] = json.loads(request.remote_ids_json)
                if request.HasField("alternate_names_json"):
                    updates["alternate_names"] = json.loads(
                        request.alternate_names_json
                    )
                if request.HasField("open_library_id"):
                    updates["open_library_id"] = request.open_library_id

                author = await app.services.author_service.update_author(
                    session, request.author_id, updates
                )

                if not author:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND,
                        f"Author with id {request.author_id} not found",
                    )
                    return

                return app.proto.books_pb2.AuthorDetailResponse(
                    author=app.proto.books_pb2.AuthorDetail(
                        author_id=author["author_id"],
                        name=author["name"],
                        slug=author["slug"],
                        bio=author.get("bio") or "",
                        birth_date=author.get("birth_date") or "",
                        death_date=author.get("death_date") or "",
                        birth_place=author.get("birth_place") or "",
                        nationality=author.get("nationality") or "",
                        photo_url=author.get("photo_url") or "",
                        view_count=author.get("view_count", 0),
                        last_viewed_at=author.get("last_viewed_at") or "",
                        books_count=author.get("books_count", 0),
                        open_library_id=author.get("open_library_id") or "",
                        created_at=author.get("created_at", ""),
                        updated_at=author.get("updated_at", ""),
                        book_categories=author.get("book_categories", []),
                        books_avg_rating=author.get("books_avg_rating", "0.00"),
                        books_total_ratings=author.get("books_total_ratings", 0),
                        wikidata_id=author.get("wikidata_id") or "",
                        wikipedia_url=author.get("wikipedia_url") or "",
                        remote_ids=author.get("remote_ids", {}),
                        alternate_names=author.get("alternate_names", []),
                        books_ol_avg_rating=author.get("books_ol_avg_rating") or "",
                        books_ol_total_ratings=author.get("books_ol_total_ratings", 0),
                        app_want_to_read_count=author.get("app_want_to_read_count", 0),
                        app_reading_count=author.get("app_reading_count", 0),
                        app_read_count=author.get("app_read_count", 0),
                        ol_want_to_read_count=author.get("ol_want_to_read_count", 0),
                        ol_currently_reading_count=author.get(
                            "ol_currently_reading_count", 0
                        ),
                        ol_already_read_count=author.get("ol_already_read_count", 0),
                    )
                )
        except Exception as e:
            logger.error(f"Error in UpdateAuthor: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Update author failed: {str(e)}"
            )

    async def UpdateSeries(
        self,
        request: app.proto.books_pb2.UpdateSeriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.SeriesDetailResponse:
        try:
            async with app.db.async_session_maker() as session:
                updates: typing.Dict[str, typing.Any] = {}

                if request.HasField("name"):
                    updates["name"] = request.name
                if request.HasField("slug"):
                    updates["slug"] = request.slug
                if request.HasField("description"):
                    updates["description"] = request.description
                if request.HasField("total_books"):
                    updates["total_books"] = request.total_books

                series = await app.services.series_service.update_series(
                    session, request.series_id, updates
                )

                if not series:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND,
                        f"Series with id {request.series_id} not found",
                    )
                    return

                return app.proto.books_pb2.SeriesDetailResponse(
                    series=app.proto.books_pb2.SeriesDetail(
                        series_id=series["series_id"],
                        name=series["name"],
                        slug=series["slug"],
                        description=series.get("description") or "",
                        total_books=series.get("total_books", 0),
                        view_count=series.get("view_count", 0),
                        last_viewed_at=series.get("last_viewed_at") or "",
                        created_at=series.get("created_at") or "",
                        updated_at=series.get("updated_at") or "",
                        avg_rating=series.get("avg_rating") or "",
                        rating_count=series.get("rating_count", 0),
                        ol_avg_rating=series.get("ol_avg_rating") or "",
                        ol_rating_count=series.get("ol_rating_count", 0),
                        app_want_to_read_count=series.get("app_want_to_read_count", 0),
                        app_reading_count=series.get("app_reading_count", 0),
                        app_read_count=series.get("app_read_count", 0),
                        ol_want_to_read_count=series.get("ol_want_to_read_count", 0),
                        ol_currently_reading_count=series.get(
                            "ol_currently_reading_count", 0
                        ),
                        ol_already_read_count=series.get("ol_already_read_count", 0),
                    )
                )
        except Exception as e:
            logger.error(f"Error in UpdateSeries: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Update series failed: {str(e)}"
            )

    async def DiscoverBook(
        self,
        request: app.proto.books_pb2.DiscoverBookRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.DiscoverBookResponse:
        try:
            async with app.db.async_session_maker() as session:
                result = await app.services.discovery_service.discover_book(
                    session,
                    language=request.language or "en",
                    genre_slugs=list(request.genre_slugs),
                    book_length=request.book_length or "",
                    quality=request.quality or "",
                    moods=list(request.moods),
                    era=request.era or "",
                    series_filter=request.series_filter or "",
                    popularity=request.popularity or "",
                    exclude_ids=list(request.exclude_ids),
                )

                if result is None:
                    await context.abort(
                        grpc.StatusCode.NOT_FOUND,
                        "No books match the provided filters",
                    )
                    return

                return app.proto.books_pb2.DiscoverBookResponse(
                    book=_build_book_summary_proto(result["book"]),
                    matching_count=result["matching_count"],
                )
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error(f"Error in DiscoverBook: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Discover book failed: {str(e)}"
            )

    async def OpenCase(
        self,
        request: app.proto.books_pb2.OpenCaseRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.OpenCaseResponse:
        try:
            async with app.db.async_session_maker() as session:
                result = await app.services.case_service.open_case(
                    session, request.language or "en"
                )

                display_list = [
                    _build_book_summary_proto(item) for item in result["display_list"]
                ]

                return app.proto.books_pb2.OpenCaseResponse(
                    display_list=display_list,
                    winning_index=result["winning_index"],
                    winner=_build_book_summary_proto(result["winner"]),
                )
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except Exception as e:
            logger.error(f"Error in OpenCase: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Open case failed: {str(e)}")

    async def DeleteBook(
        self,
        request: app.proto.books_pb2.DeleteBookRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.DeleteEntityResponse:
        try:
            async with app.db.async_session_maker() as session:
                result = await app.services.book_service.delete_book(
                    session, request.book_id
                )
                return app.proto.books_pb2.DeleteEntityResponse(
                    message=(
                        f"Book {result['book_id']} '{result['title']}' deleted. "
                        f"Cleaned up: {result['bookshelves_deleted']} bookshelf entries, "
                        f"{result['ratings_deleted']} ratings, "
                        f"{result['comments_deleted']} comments. "
                        f"Recalculated stats for {result['users_recalculated']} users."
                    )
                )
        except ValueError:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Book with id {request.book_id} not found",
            )
        except Exception as e:
            logger.error(f"Error in DeleteBook: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Delete book failed: {str(e)}"
            )

    async def DeleteAuthor(
        self,
        request: app.proto.books_pb2.DeleteAuthorRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.DeleteEntityResponse:
        try:
            async with app.db.async_session_maker() as session:
                result = await app.services.author_service.delete_author(
                    session, request.author_id
                )
                return app.proto.books_pb2.DeleteEntityResponse(
                    message=(
                        f"Author {result['author_id']} '{result['name']}' deleted."
                    )
                )
        except ValueError:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Author with id {request.author_id} not found",
            )
        except Exception as e:
            logger.error(f"Error in DeleteAuthor: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Delete author failed: {str(e)}"
            )

    async def DeleteSeries(
        self,
        request: app.proto.books_pb2.DeleteSeriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.DeleteEntityResponse:
        try:
            async with app.db.async_session_maker() as session:
                result = await app.services.series_service.delete_series(
                    session, request.series_id
                )
                return app.proto.books_pb2.DeleteEntityResponse(
                    message=(
                        f"Series {result['series_id']} '{result['name']}' deleted. "
                        f"{result['books_unlinked']} books unlinked."
                    )
                )
        except ValueError:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Series with id {request.series_id} not found",
            )
        except Exception as e:
            logger.error(f"Error in DeleteSeries: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Delete series failed: {str(e)}"
            )
