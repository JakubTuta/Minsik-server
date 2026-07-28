import asyncio
import datetime
import json
import logging
import typing

import app.cache
import app.db
import app.proto.books_pb2
import app.proto.books_pb2_grpc
import app.services.author_service
import app.services.book_service
import app.services.case_service
import app.services.discovery_service
import app.services.genre_service
import app.services.pack_service
import app.services.search_service
import app.services.series_service
import app.services.sitemap_service
import app.services.es_sync_service
import app.services.slots_service
import app.services.category_service
import app.services.quality_audit_service
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
    series_info = None
    if book.get("series"):
        series_info = app.proto.books_pb2.SeriesInfo(
            series_id=book["series"]["series_id"],
            name=book["series"]["name"],
            slug=book["series"]["slug"],
            total_books=int(book["series"].get("total_books") or 0),
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
        work_id=book.get("work_id", "") or "",
        title=book["title"],
        slug=book["slug"],
        description=book["description"],
        language=book["language"],
        original_publication_year=book["original_publication_year"],
        formats=book["formats"],
        primary_cover_url=book["primary_cover_url"],
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
        rating_distribution=book.get("rating_distribution", {}),
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
        work_id=item.get("work_id", "") or "",
        title=item["title"],
        slug=item["slug"],
        description=item.get("description", ""),
        original_publication_year=item.get("original_publication_year", 0),
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
        language=item.get("language", "") or "",
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
                        request.type_filter or "all",
                        request.language or "en",
                    )
                )

                search_results = []
                for result in results:
                    search_results.append(
                        app.proto.books_pb2.SearchResult(
                            type=result["type"],
                            id=int(result["id"]),
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
                            app_rating_count=int(result.get("app_rating_count") or 0),
                            ol_avg_rating=(
                                str(result["ol_avg_rating"])
                                if result.get("ol_avg_rating") is not None
                                else ""
                            ),
                            ol_rating_count=int(result.get("ol_rating_count") or 0),
                            book_count=int(result.get("book_count") or 0),
                            readers=int(result.get("readers") or 0),
                            work_id=result.get("work_id") or "",
                            language=result.get("language") or "",
                        )
                    )

                return app.proto.books_pb2.SearchResponse(
                    results=search_results, total_count=total
                )
        except Exception as e:
            logger.error(f"Error in SearchBooksAndAuthors: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Search failed: {str(e)}")

    async def SuggestSearch(
        self,
        request: app.proto.books_pb2.SuggestSearchRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.SuggestSearchResponse:
        try:
            results = await app.services.search_service.suggest(
                request.query,
                request.limit or 8,
                request.language or "en",
            )

            items = [
                app.proto.books_pb2.SuggestionItem(
                    type=result["type"],
                    id=int(result["id"]),
                    title=result["title"],
                    slug=result["slug"],
                    cover_url=result["cover_url"],
                    authors=result["authors"],
                    score=result["relevance_score"],
                    readers=int(result.get("readers") or 0),
                    app_avg_rating=(
                        str(result["app_avg_rating"])
                        if result.get("app_avg_rating") is not None
                        else ""
                    ),
                    app_rating_count=int(result.get("app_rating_count") or 0),
                    ol_avg_rating=(
                        str(result["ol_avg_rating"])
                        if result.get("ol_avg_rating") is not None
                        else ""
                    ),
                    ol_rating_count=int(result.get("ol_rating_count") or 0),
                    work_id=result.get("work_id") or "",
                    language=result.get("language") or "",
                )
                for result in results
            ]

            return app.proto.books_pb2.SuggestSearchResponse(items=items)
        except Exception as e:
            logger.error(f"Error in SuggestSearch: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Suggest failed: {str(e)}")

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
        except Exception as e:
            logger.error(f"Error in GetBook: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get book failed: {str(e)}")
            return

        if not book:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"Book not found: {request.slug}"
            )
            return

        return app.proto.books_pb2.BookDetailResponse(
            book=_build_book_detail_proto(book)
        )

    async def GetBookLanguageVariants(
        self,
        request: app.proto.books_pb2.GetBookLanguageVariantsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.BookLanguageVariantsResponse:
        try:
            async with app.db.async_session_maker() as session:
                variants = await app.services.book_service.get_language_variants(
                    session, request.slug, request.exclude_language or "en"
                )
        except Exception as e:
            logger.error(f"Error in GetBookLanguageVariants: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get language variants failed: {str(e)}")
            return

        items = [
            app.proto.books_pb2.BookLanguageVariant(
                book_id=v["book_id"],
                slug=v["slug"],
                language=v["language"],
                title=v["title"],
                primary_cover_url=v["primary_cover_url"],
            )
            for v in variants
        ]
        return app.proto.books_pb2.BookLanguageVariantsResponse(items=items)

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
        except Exception as e:
            logger.error(f"Error in GetAuthor: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get author failed: {str(e)}"
            )
            return

        if not author:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"Author not found: {request.slug}"
            )
            return

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
        except Exception as e:
            logger.error(f"Error in GetSeries: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get series failed: {str(e)}"
            )
            return

        if not series:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"Series not found: {request.slug}"
            )
            return

        primary_author_proto = None
        if series.get("primary_author"):
            pa = series["primary_author"]
            primary_author_proto = app.proto.books_pb2.AuthorInfo(
                author_id=pa["author_id"],
                name=pa["name"],
                slug=pa["slug"],
                photo_url=pa.get("photo_url") or "",
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
            total_pages=series.get("total_pages", 0),
            primary_author=primary_author_proto,
        )

        return app.proto.books_pb2.SeriesDetailResponse(series=series_detail)

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

                if request.HasField("remove_author_id"):
                    book = await app.services.book_service.remove_book_author(
                        session, request.book_id, request.remove_author_id
                    )
                else:
                    book = await app.services.book_service.update_book(
                        session, request.book_id, updates
                    )
        except ValueError as e:
            if str(e) == "author_not_on_book":
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Author {request.remove_author_id} not found on book {request.book_id}",
                )
            else:
                await context.abort(grpc.StatusCode.INTERNAL, str(e))
            return
        except Exception as e:
            logger.error(f"Error in UpdateBook: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Update book failed: {str(e)}"
            )
            return

        if not book:
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Book with id {request.book_id} not found",
            )
            return

        book_detail = _build_book_detail_proto(book)

        return app.proto.books_pb2.BookDetailResponse(book=book_detail)

    async def UpdateAuthor(
        self,
        request: app.proto.books_pb2.UpdateAuthorRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.AuthorDetailResponse:
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
        except Exception as e:
            logger.error(f"Error in UpdateAuthor: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Update author failed: {str(e)}"
            )
            return

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

    async def UpdateSeries(
        self,
        request: app.proto.books_pb2.UpdateSeriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.SeriesDetailResponse:
        try:
            async with app.db.async_session_maker() as session:
                if request.HasField("remove_author_id"):
                    await app.services.series_service.remove_series_author(
                        session, request.series_id, request.remove_author_id
                    )

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
        except Exception as e:
            logger.error(f"Error in UpdateSeries: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Update series failed: {str(e)}"
            )
            return

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

                return app.proto.books_pb2.OpenCaseResponse(
                    winner=_build_book_summary_proto(result["winner"]),
                )
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except Exception as e:
            logger.error(f"Error in OpenCase: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Open case failed: {str(e)}")

    async def OpenPack(
        self,
        request: app.proto.books_pb2.OpenPackRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.OpenPackResponse:
        try:
            async with app.db.async_session_maker() as session:
                items = await app.services.pack_service.open_pack(
                    session,
                    request.language or "en",
                    request.length or app.services.pack_service.DEFAULT_PACK_LENGTH,
                )
                return app.proto.books_pb2.OpenPackResponse(
                    items=[_build_book_summary_proto(item) for item in items],
                )
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except Exception as e:
            logger.error(f"Error in OpenPack: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Open pack failed: {str(e)}")

    async def SpinSlots(
        self,
        request: app.proto.books_pb2.SpinSlotsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.SpinSlotsResponse:
        try:
            async with app.db.async_session_maker() as session:
                items, winner = await app.services.slots_service.spin_slots(
                    session,
                    request.language or "en",
                )
                return app.proto.books_pb2.SpinSlotsResponse(
                    items=items,
                    winner=_build_book_summary_proto(winner),
                )
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except Exception as e:
            logger.error(f"Error in SpinSlots: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Spin slots failed: {str(e)}"
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

        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
            return
        except Exception as e:
            logger.error(f"Error in DiscoverBook: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Discover book failed: {str(e)}"
            )
            return

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

    async def ListCategories(
        self,
        request: app.proto.books_pb2.ListCategoriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.ListCategoriesResponse:
        try:
            categories = app.services.category_service.category_service.get_categories()

            category_protos = [
                app.proto.books_pb2.Category(slug=cat["slug"], name=cat["name"])
                for cat in categories
            ]

            return app.proto.books_pb2.ListCategoriesResponse(categories=category_protos)
        except Exception as e:
            logger.error(f"Error in ListCategories: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"List categories failed: {str(e)}"
            )

    async def GetCategory(
        self,
        request: app.proto.books_pb2.GetCategoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.CategoryResponse:
        try:
            cat = app.services.category_service.category_service.get_category(request.category_slug)
        except Exception as e:
            logger.error(f"Error in GetCategory: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get category failed: {str(e)}"
            )
            return

        if not cat:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Category not found")
            return

        return app.proto.books_pb2.CategoryResponse(
            category=app.proto.books_pb2.Category(
                slug=cat["slug"],
                name=cat["name"],
            )
        )

    async def GetCategoryBooks(
        self,
        request: app.proto.books_pb2.GetCategoryBooksRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.BooksListResponse:
        try:
            books, total = await app.services.category_service.category_service.get_category_books(
                category_slug=request.category_slug,
                limit=request.limit or 20,
                offset=request.offset or 0,
                language=request.language or "en",
                sort_by=request.sort_by or "popularity",
                order=request.order or "desc",
            )

            book_summaries = [_build_book_summary_proto(book) for book in books]
            return app.proto.books_pb2.BooksListResponse(
                books=book_summaries, total_count=total
            )
        except Exception as e:
            logger.error(f"Error in GetCategoryBooks: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get category books failed: {str(e)}"
            )

    async def GetPopularCategories(
        self,
        request: app.proto.books_pb2.GetPopularCategoriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.PopularCategoriesResponse:
        try:
            limit = request.limit if request.limit > 0 else 12
            categories = await app.services.category_service.category_service.get_popular_categories(limit=limit)
            response = app.proto.books_pb2.PopularCategoriesResponse()
            for cat in categories:
                response.categories.append(
                    app.proto.books_pb2.PopularCategoryItem(
                        slug=cat["slug"],
                        name=cat["name"],
                        book_count=cat["book_count"],
                    )
                )
            return response
        except Exception as e:
            logger.error(f"Error in GetPopularCategories: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"Get popular categories failed: {str(e)}"
            )

    async def ListSitemapSlugs(
        self,
        request: app.proto.books_pb2.ListSitemapSlugsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.books_pb2.ListSitemapSlugsResponse:
        entity = request.entity or "books"
        if entity not in app.services.sitemap_service.SITEMAP_ENTITIES:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(f"Invalid entity: {entity}")
            return app.proto.books_pb2.ListSitemapSlugsResponse()

        try:
            limit = (
                request.limit
                if 0 < request.limit <= app.services.sitemap_service.MAX_LIMIT
                else app.services.sitemap_service.DEFAULT_LIMIT
            )
            offset = max(request.offset, 0)

            async with app.db.async_session_maker() as session:
                items, total_count = (
                    await app.services.sitemap_service.list_sitemap_slugs(
                        session, entity, limit, offset
                    )
                )

            item_protos = [
                app.proto.books_pb2.SitemapSlugItem(
                    slug=item["slug"],
                    updated_at=item["updated_at"],
                    language=item.get("language") or "",
                    work_id=item.get("work_id") or "",
                )
                for item in items
            ]
            return app.proto.books_pb2.ListSitemapSlugsResponse(
                items=item_protos, total_count=total_count
            )
        except Exception as e:
            logger.error(f"Error in ListSitemapSlugs: {str(e)}")
            await context.abort(
                grpc.StatusCode.INTERNAL, f"List sitemap slugs failed: {str(e)}"
            )

    async def GetGenreBubble(self, request, context):
        try:
            limit = request.limit if request.limit > 0 else 10
            result = await app.services.genre_service.get_genre_bubble(
                slug=request.slug,
                limit=limit,
            )

            if result is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Genre '{request.slug}' not found")
                return app.proto.books_pb2.GetGenreBubbleResponse()

            source = app.proto.books_pb2.GenreInfo(
                genre_id=result["source"]["genre_id"],
                name=result["source"]["name"],
                slug=result["source"]["slug"],
            )
            related = [
                app.proto.books_pb2.GenreCoOccurrence(
                    genre=app.proto.books_pb2.GenreInfo(
                        genre_id=r["genre_id"],
                        name=r["name"],
                        slug=r["slug"],
                    ),
                    co_occurrence_count=r["co_occurrence_count"],
                    strength=r["strength"],
                )
                for r in result["related"]
            ]
            return app.proto.books_pb2.GetGenreBubbleResponse(
                source=source,
                related=related,
            )
        except Exception as e:
            logger.error(f"Error in GetGenreBubble: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return app.proto.books_pb2.GetGenreBubbleResponse()

    async def ReindexAll(self, request, context):
        try:
            flag = await app.cache.redis_client.get("es_reindex_running")
            if flag:
                return app.proto.books_pb2.ReindexAllResponse(
                    status="already_running",
                    message="Reindex is already in progress",
                )

            asyncio.create_task(app.services.es_sync_service.reindex_all_to_es(full=True))

            return app.proto.books_pb2.ReindexAllResponse(
                status="started",
                message="Full reindex started. Check service logs for progress.",
            )
        except Exception as e:
            logger.error(f"Error triggering reindex: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))

    async def AuditBooks(self, request, context):
        try:
            async with app.db.async_session_maker() as session:
                items = await app.services.quality_audit_service.audit_books(
                    session,
                    request.limit or 20,
                    request.min_authors,
                    request.max_authors,
                    request.min_genres,
                    request.max_genres,
                    request.language or None,
                    request.check_missing_description,
                    request.check_missing_cover,
                    request.check_implausible_year,
                    request.check_suspicious_title,
                )

            item_protos = [
                app.proto.books_pb2.AuditBookItem(
                    book_id=item["book_id"],
                    title=item["title"],
                    slug=item["slug"],
                    language=item["language"],
                    primary_cover_url=item["primary_cover_url"],
                    author_count=item["author_count"],
                    genre_count=item["genre_count"],
                    original_publication_year=item["original_publication_year"],
                    issues=item["issues"],
                )
                for item in items
            ]
            return app.proto.books_pb2.AuditBooksResponse(items=item_protos)
        except Exception as e:
            logger.error(f"Error in AuditBooks: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Audit books failed: {str(e)}")

    async def AuditAuthors(self, request, context):
        try:
            async with app.db.async_session_maker() as session:
                items = await app.services.quality_audit_service.audit_authors(
                    session,
                    request.limit or 20,
                    request.min_books,
                    request.max_books,
                    request.check_missing_bio,
                    request.check_junk_name,
                )

            item_protos = [
                app.proto.books_pb2.AuditAuthorItem(
                    author_id=item["author_id"],
                    name=item["name"],
                    slug=item["slug"],
                    book_count=item["book_count"],
                    issues=item["issues"],
                )
                for item in items
            ]
            return app.proto.books_pb2.AuditAuthorsResponse(items=item_protos)
        except Exception as e:
            logger.error(f"Error in AuditAuthors: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Audit authors failed: {str(e)}")

    async def AuditSeries(self, request, context):
        try:
            async with app.db.async_session_maker() as session:
                items = await app.services.quality_audit_service.audit_series(
                    session,
                    request.limit or 20,
                    request.min_books,
                    request.max_books,
                    request.language or None,
                    request.check_missing_description,
                    request.check_count_drift,
                )

            item_protos = [
                app.proto.books_pb2.AuditSeriesItem(
                    series_id=item["series_id"],
                    name=item["name"],
                    slug=item["slug"],
                    language=item["language"],
                    book_count=item["book_count"],
                    total_books=item["total_books"],
                    issues=item["issues"],
                )
                for item in items
            ]
            return app.proto.books_pb2.AuditSeriesResponse(items=item_protos)
        except Exception as e:
            logger.error(f"Error in AuditSeries: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Audit series failed: {str(e)}")
