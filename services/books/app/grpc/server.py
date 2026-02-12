import grpc
import logging
import typing
import app.proto.books_pb2
import app.proto.books_pb2_grpc
import app.db
import app.services.search_service
import app.services.book_service
import app.services.author_service
import app.services.series_service

logger = logging.getLogger(__name__)


class BooksServicer(app.proto.books_pb2_grpc.BooksServiceServicer):
    async def SearchBooksAndAuthors(
        self,
        request: app.proto.books_pb2.SearchRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.books_pb2.SearchResponse:
        try:
            async with app.db.async_session_maker() as session:
                results, total = await app.services.search_service.search_books_and_authors(
                    session,
                    request.query,
                    request.limit or 10,
                    request.offset or 0,
                    request.type_filter or "both"
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
                            view_count=result["view_count"],
                            author_slugs=result["author_slugs"],
                            series_slug=result["series_slug"]
                        )
                    )

                return app.proto.books_pb2.SearchResponse(
                    results=search_results,
                    total_count=total
                )
        except Exception as e:
            logger.error(f"Error in SearchBooksAndAuthors: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Search failed: {str(e)}")

    async def GetBook(
        self,
        request: app.proto.books_pb2.GetBookRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.books_pb2.BookDetailResponse:
        try:
            async with app.db.async_session_maker() as session:
                book = await app.services.book_service.get_book_by_slug(session, request.slug)

                if not book:
                    await context.abort(grpc.StatusCode.NOT_FOUND, f"Book not found: {request.slug}")

                authors = [
                    app.proto.books_pb2.AuthorInfo(
                        author_id=author["author_id"],
                        name=author["name"],
                        slug=author["slug"],
                        photo_url=author["photo_url"]
                    )
                    for author in book["authors"]
                ]

                genres = [
                    app.proto.books_pb2.GenreInfo(
                        genre_id=genre["genre_id"],
                        name=genre["name"],
                        slug=genre["slug"]
                    )
                    for genre in book["genres"]
                ]

                cover_history = [
                    app.proto.books_pb2.CoverHistory(
                        url=cover.get("url", ""),
                        width=cover.get("width", 0),
                        size=cover.get("size", "")
                    )
                    for cover in book["cover_history"]
                ]

                series_info = None
                if book.get("series"):
                    series_info = app.proto.books_pb2.SeriesInfo(
                        series_id=book["series"]["series_id"],
                        name=book["series"]["name"],
                        slug=book["series"]["slug"],
                        total_books=book["series"].get("total_books", 0)
                    )

                sub_rating_stats = {
                    key: app.proto.books_pb2.SubRatingStat(
                        avg=str(val.get("avg")) if val.get("avg") is not None else "",
                        count=val.get("count", 0)
                    )
                    for key, val in book.get("sub_rating_stats", {}).items()
                }

                book_detail = app.proto.books_pb2.BookDetail(
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
                    sub_rating_stats=sub_rating_stats
                )

                return app.proto.books_pb2.BookDetailResponse(book=book_detail)
        except Exception as e:
            logger.error(f"Error in GetBook: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get book failed: {str(e)}")

    async def GetAuthor(
        self,
        request: app.proto.books_pb2.GetAuthorRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.books_pb2.AuthorDetailResponse:
        try:
            async with app.db.async_session_maker() as session:
                author = await app.services.author_service.get_author_by_slug(session, request.slug)

                if not author:
                    await context.abort(grpc.StatusCode.NOT_FOUND, f"Author not found: {request.slug}")

                author_detail = app.proto.books_pb2.AuthorDetail(
                    author_id=author["author_id"],
                    name=author["name"],
                    slug=author["slug"],
                    bio=author["bio"],
                    birth_date=author["birth_date"],
                    death_date=author["death_date"],
                    photo_url=author["photo_url"],
                    view_count=author["view_count"],
                    last_viewed_at=author["last_viewed_at"],
                    books_count=author["books_count"],
                    open_library_id=author["open_library_id"],
                    created_at=author["created_at"],
                    updated_at=author["updated_at"],
                    birth_place=author["birth_place"],
                    nationality=author["nationality"],
                    book_categories=author["book_categories"],
                    books_avg_rating=author["books_avg_rating"],
                    books_total_ratings=author["books_total_ratings"],
                    books_total_views=author["books_total_views"]
                )

                return app.proto.books_pb2.AuthorDetailResponse(author=author_detail)
        except Exception as e:
            logger.error(f"Error in GetAuthor: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get author failed: {str(e)}")

    async def GetAuthorBooks(
        self,
        request: app.proto.books_pb2.GetAuthorBooksRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.books_pb2.BooksListResponse:
        try:
            async with app.db.async_session_maker() as session:
                books, total = await app.services.author_service.get_author_books(
                    session,
                    request.author_slug,
                    request.limit or 10,
                    request.offset or 0,
                    request.sort_by or "view_count",
                    request.order or "desc"
                )

                book_summaries = []
                for book in books:
                    genres = [
                        app.proto.books_pb2.GenreInfo(
                            genre_id=genre["genre_id"],
                            name=genre["name"],
                            slug=genre["slug"]
                        )
                        for genre in book["genres"]
                    ]

                    book_summaries.append(
                        app.proto.books_pb2.BookSummary(
                            book_id=book["book_id"],
                            title=book["title"],
                            slug=book["slug"],
                            description=book["description"],
                            original_publication_year=book["original_publication_year"],
                            primary_cover_url=book["primary_cover_url"],
                            rating_count=book["rating_count"],
                            avg_rating=book["avg_rating"],
                            view_count=book["view_count"],
                            genres=genres
                        )
                    )

                return app.proto.books_pb2.BooksListResponse(
                    books=book_summaries,
                    total_count=total
                )
        except Exception as e:
            logger.error(f"Error in GetAuthorBooks: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get author books failed: {str(e)}")

    async def GetSeries(
        self,
        request: app.proto.books_pb2.GetSeriesRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.books_pb2.SeriesDetailResponse:
        try:
            async with app.db.async_session_maker() as session:
                series = await app.services.series_service.get_series_by_slug(session, request.slug)

                if not series:
                    await context.abort(grpc.StatusCode.NOT_FOUND, f"Series not found: {request.slug}")

                series_detail = app.proto.books_pb2.SeriesDetail(
                    series_id=series["series_id"],
                    name=series["name"],
                    slug=series["slug"],
                    description=series["description"],
                    total_books=series["total_books"],
                    view_count=series["view_count"],
                    last_viewed_at=series["last_viewed_at"],
                    created_at=series["created_at"],
                    updated_at=series["updated_at"]
                )

                return app.proto.books_pb2.SeriesDetailResponse(series=series_detail)
        except Exception as e:
            logger.error(f"Error in GetSeries: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get series failed: {str(e)}")

    async def GetSeriesBooks(
        self,
        request: app.proto.books_pb2.GetSeriesBooksRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.books_pb2.BooksListResponse:
        try:
            async with app.db.async_session_maker() as session:
                books, total = await app.services.series_service.get_series_books(
                    session,
                    request.series_slug,
                    request.limit or 10,
                    request.offset or 0
                )

                book_summaries = []
                for book in books:
                    genres = [
                        app.proto.books_pb2.GenreInfo(
                            genre_id=genre["genre_id"],
                            name=genre["name"],
                            slug=genre["slug"]
                        )
                        for genre in book["genres"]
                    ]

                    book_summaries.append(
                        app.proto.books_pb2.BookSummary(
                            book_id=book["book_id"],
                            title=book["title"],
                            slug=book["slug"],
                            description=book["description"],
                            original_publication_year=book["original_publication_year"],
                            primary_cover_url=book["primary_cover_url"],
                            rating_count=book["rating_count"],
                            avg_rating=book["avg_rating"],
                            view_count=book["view_count"],
                            genres=genres,
                            series_position=book.get("series_position", "")
                        )
                    )

                return app.proto.books_pb2.BooksListResponse(
                    books=book_summaries,
                    total_count=total
                )
        except Exception as e:
            logger.error(f"Error in GetSeriesBooks: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get series books failed: {str(e)}")
