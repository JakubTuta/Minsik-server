import logging
import typing

import app.config
from app.grpc_clients import base
import app.proto.books_pb2
import app.proto.books_pb2_grpc

logger = logging.getLogger(__name__)


class BooksClient(base.GrpcClientBase):
    service_label = "books"

    def _target(self) -> str:
        return app.config.settings.books_service_url

    def _create_stub(self, channel):
        return app.proto.books_pb2_grpc.BooksServiceStub(channel)


    async def search_books_and_authors(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        type_filter: str = "both",
        language: str = "en",
    ) -> app.proto.books_pb2.SearchResponse:
        request = app.proto.books_pb2.SearchRequest(
            query=query,
            limit=limit,
            offset=offset,
            type_filter=type_filter,
            language=language,
        )

        return await self._call("SearchBooksAndAuthors", request)

    async def get_book(
        self, slug: str, language: str = "en"
    ) -> app.proto.books_pb2.BookDetailResponse:
        request = app.proto.books_pb2.GetBookRequest(slug=slug, language=language)

        return await self._call("GetBook", request)

    async def get_book_language_variants(
        self, slug: str, exclude_language: str = "en"
    ) -> app.proto.books_pb2.BookLanguageVariantsResponse:
        request = app.proto.books_pb2.GetBookLanguageVariantsRequest(
            slug=slug, exclude_language=exclude_language
        )

        return await self._call("GetBookLanguageVariants", request)

    async def get_author(
        self, slug: str, language: str = "en"
    ) -> app.proto.books_pb2.AuthorDetailResponse:
        request = app.proto.books_pb2.GetAuthorRequest(slug=slug, language=language)

        return await self._call("GetAuthor", request)

    async def get_author_books(
        self,
        author_slug: str,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "view_count",
        order: str = "desc",
        language: str = "en",
    ) -> app.proto.books_pb2.BooksListResponse:
        request = app.proto.books_pb2.GetAuthorBooksRequest(
            author_slug=author_slug,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            language=language,
        )

        return await self._call("GetAuthorBooks", request)

    async def get_series(
        self, slug: str, language: str = "en"
    ) -> app.proto.books_pb2.SeriesDetailResponse:
        request = app.proto.books_pb2.GetSeriesRequest(slug=slug, language=language)

        return await self._call("GetSeries", request)

    async def get_series_books(
        self,
        series_slug: str,
        limit: int = 10,
        offset: int = 0,
        language: str = "en",
        sort_by: str = "series_position",
        order: str = "asc",
    ) -> app.proto.books_pb2.BooksListResponse:
        request = app.proto.books_pb2.GetSeriesBooksRequest(
            series_slug=series_slug,
            limit=limit,
            offset=offset,
            language=language,
            sort_by=sort_by,
            order=order,
        )

        return await self._call("GetSeriesBooks", request)

    async def update_book(
        self,
        book_id: int,
        fields: typing.Dict[str, typing.Any],
    ) -> app.proto.books_pb2.BookDetailResponse:
        request = app.proto.books_pb2.UpdateBookRequest(book_id=book_id)

        for field, value in fields.items():
            setattr(request, field, value)

        return await self._call("UpdateBook", request, timeout=app.config.settings.grpc_admin_timeout)

    async def update_author(
        self,
        author_id: int,
        fields: typing.Dict[str, typing.Any],
    ) -> app.proto.books_pb2.AuthorDetailResponse:
        request = app.proto.books_pb2.UpdateAuthorRequest(author_id=author_id)

        for field, value in fields.items():
            setattr(request, field, value)

        return await self._call("UpdateAuthor", request, timeout=app.config.settings.grpc_admin_timeout)

    async def update_series(
        self,
        series_id: int,
        fields: typing.Dict[str, typing.Any],
    ) -> app.proto.books_pb2.SeriesDetailResponse:
        request = app.proto.books_pb2.UpdateSeriesRequest(series_id=series_id)

        for field, value in fields.items():
            setattr(request, field, value)

        return await self._call("UpdateSeries", request, timeout=app.config.settings.grpc_admin_timeout)

    async def remove_book_author(
        self, book_id: int, author_id: int
    ) -> app.proto.books_pb2.BookDetailResponse:
        request = app.proto.books_pb2.UpdateBookRequest(
            book_id=book_id, remove_author_id=author_id
        )
        return await self._call("UpdateBook", request, timeout=app.config.settings.grpc_admin_timeout)

    async def remove_series_author(
        self, series_id: int, author_id: int
    ) -> app.proto.books_pb2.SeriesDetailResponse:
        request = app.proto.books_pb2.UpdateSeriesRequest(
            series_id=series_id, remove_author_id=author_id
        )
        return await self._call("UpdateSeries", request, timeout=app.config.settings.grpc_admin_timeout)

    async def delete_book(self, book_id: int) -> app.proto.books_pb2.DeleteEntityResponse:
        request = app.proto.books_pb2.DeleteBookRequest(book_id=book_id)
        return await self._call("DeleteBook", request, timeout=app.config.settings.grpc_admin_timeout)

    async def delete_author(self, author_id: int) -> app.proto.books_pb2.DeleteEntityResponse:
        request = app.proto.books_pb2.DeleteAuthorRequest(author_id=author_id)
        return await self._call("DeleteAuthor", request, timeout=app.config.settings.grpc_admin_timeout)

    async def delete_series(self, series_id: int) -> app.proto.books_pb2.DeleteEntityResponse:
        request = app.proto.books_pb2.DeleteSeriesRequest(series_id=series_id)
        return await self._call("DeleteSeries", request, timeout=app.config.settings.grpc_admin_timeout)

    async def spin_slots(self, language: str = "en") -> app.proto.books_pb2.SpinSlotsResponse:
        request = app.proto.books_pb2.SpinSlotsRequest(language=language)

        return await self._call("SpinSlots", request)

    async def discover_book(
        self,
        language: str = "en",
        genre_slugs: typing.Optional[typing.List[str]] = None,
        book_length: str = "",
        quality: str = "",
        moods: typing.Optional[typing.List[str]] = None,
        era: str = "",
        series_filter: str = "",
        popularity: str = "",
        exclude_ids: typing.Optional[typing.List[int]] = None,
    ) -> app.proto.books_pb2.DiscoverBookResponse:
        request = app.proto.books_pb2.DiscoverBookRequest(
            language=language,
            genre_slugs=genre_slugs or [],
            book_length=book_length,
            quality=quality,
            moods=moods or [],
            era=era,
            series_filter=series_filter,
            popularity=popularity,
            exclude_ids=exclude_ids or [],
        )

        return await self._call("DiscoverBook", request)

    async def count_matching_books(
        self,
        language: str = "en",
        genre_slugs: typing.Optional[typing.List[str]] = None,
        book_length: str = "",
        quality: str = "",
        moods: typing.Optional[typing.List[str]] = None,
        era: str = "",
        series_filter: str = "",
        popularity: str = "",
        exclude_ids: typing.Optional[typing.List[int]] = None,
    ) -> app.proto.books_pb2.CountMatchingBooksResponse:
        request = app.proto.books_pb2.DiscoverBookRequest(
            language=language,
            genre_slugs=genre_slugs or [],
            book_length=book_length,
            quality=quality,
            moods=moods or [],
            era=era,
            series_filter=series_filter,
            popularity=popularity,
            exclude_ids=exclude_ids or [],
        )

        return await self._call("CountMatchingBooks", request)

    async def open_case(self, language: str = "en") -> app.proto.books_pb2.OpenCaseResponse:
        request = app.proto.books_pb2.OpenCaseRequest(language=language)

        return await self._call("OpenCase", request)

    async def open_pack(
        self, language: str = "en", length: int = 8
    ) -> app.proto.books_pb2.OpenPackResponse:
        request = app.proto.books_pb2.OpenPackRequest(language=language, length=length)

        return await self._call("OpenPack", request)

    async def list_categories(self) -> app.proto.books_pb2.ListCategoriesResponse:
        request = app.proto.books_pb2.ListCategoriesRequest()
        return await self._call("ListCategories", request)

    async def get_category(self, category_slug: str) -> app.proto.books_pb2.CategoryResponse:
        request = app.proto.books_pb2.GetCategoryRequest(category_slug=category_slug)
        return await self._call("GetCategory", request)

    async def get_category_books(
        self,
        category_slug: str,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "popularity",
        order: str = "desc",
        language: str = "en",
    ) -> app.proto.books_pb2.BooksListResponse:
        request = app.proto.books_pb2.GetCategoryBooksRequest(
            category_slug=category_slug,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            language=language,
        )

        return await self._call("GetCategoryBooks", request)

    async def suggest_search(
        self,
        query: str,
        limit: int = 8,
        language: str = "en",
    ) -> app.proto.books_pb2.SuggestSearchResponse:
        request = app.proto.books_pb2.SuggestSearchRequest(
            query=query,
            limit=limit,
            language=language,
        )
        return await self._call("SuggestSearch", request)

    async def get_popular_categories(
        self, limit: int = 12
    ) -> app.proto.books_pb2.PopularCategoriesResponse:
        request = app.proto.books_pb2.GetPopularCategoriesRequest(limit=limit)
        return await self._call("GetPopularCategories", request)

    async def trigger_reindex(self) -> app.proto.books_pb2.ReindexAllResponse:
        request = app.proto.books_pb2.ReindexAllRequest()
        return await self._call("ReindexAll", request, timeout=app.config.settings.grpc_admin_timeout)

    async def get_genre_bubble(
        self,
        slug: str,
        limit: int = 10,
    ) -> app.proto.books_pb2.GetGenreBubbleResponse:
        request = app.proto.books_pb2.GetGenreBubbleRequest(slug=slug, limit=limit)
        return await self._call("GetGenreBubble", request)


    async def list_sitemap_slugs(
        self,
        entity: str,
        limit: int = 1000,
        offset: int = 0,
        languages: typing.Optional[typing.Sequence[str]] = None,
    ) -> app.proto.books_pb2.ListSitemapSlugsResponse:
        request = app.proto.books_pb2.ListSitemapSlugsRequest(
            entity=entity, limit=limit, offset=offset, languages=languages or []
        )
        return await self._call(
            "ListSitemapSlugs",
            request,
            timeout=app.config.settings.grpc_sitemap_timeout,
        )

    async def audit_books(
        self,
        limit: int = 20,
        min_authors: int = 0,
        max_authors: int = 0,
        min_genres: int = 0,
        max_genres: int = 0,
        language: str = "",
        check_missing_description: bool = False,
        check_missing_cover: bool = False,
        check_implausible_year: bool = False,
        check_suspicious_title: bool = False,
    ) -> app.proto.books_pb2.AuditBooksResponse:
        request = app.proto.books_pb2.AuditBooksRequest(
            limit=limit,
            min_authors=min_authors,
            max_authors=max_authors,
            min_genres=min_genres,
            max_genres=max_genres,
            language=language,
            check_missing_description=check_missing_description,
            check_missing_cover=check_missing_cover,
            check_implausible_year=check_implausible_year,
            check_suspicious_title=check_suspicious_title,
        )
        return await self._call("AuditBooks", request, timeout=app.config.settings.grpc_admin_timeout)

    async def audit_authors(
        self,
        limit: int = 20,
        min_books: int = 0,
        max_books: int = 0,
        check_missing_bio: bool = False,
        check_junk_name: bool = False,
    ) -> app.proto.books_pb2.AuditAuthorsResponse:
        request = app.proto.books_pb2.AuditAuthorsRequest(
            limit=limit,
            min_books=min_books,
            max_books=max_books,
            check_missing_bio=check_missing_bio,
            check_junk_name=check_junk_name,
        )
        return await self._call("AuditAuthors", request, timeout=app.config.settings.grpc_admin_timeout)

    async def audit_series(
        self,
        limit: int = 20,
        min_books: int = 0,
        max_books: int = 0,
        language: str = "",
        check_missing_description: bool = False,
        check_count_drift: bool = False,
    ) -> app.proto.books_pb2.AuditSeriesResponse:
        request = app.proto.books_pb2.AuditSeriesRequest(
            limit=limit,
            min_books=min_books,
            max_books=max_books,
            language=language,
            check_missing_description=check_missing_description,
            check_count_drift=check_count_drift,
        )
        return await self._call("AuditSeries", request, timeout=app.config.settings.grpc_admin_timeout)


books_client = BooksClient()
