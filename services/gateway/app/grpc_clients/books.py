import logging
import typing

import app.config
import app.proto.books_pb2 as books_pb2
import app.proto.books_pb2_grpc as books_pb2_grpc
import grpc

logger = logging.getLogger(__name__)


class BooksClient:
    def __init__(self):
        self.channel: typing.Optional[grpc.aio.Channel] = None
        self.stub: typing.Optional[books_pb2_grpc.BooksServiceStub] = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        self.channel = grpc.aio.insecure_channel(
            app.config.settings.books_service_url,
            options=[
                ("grpc.keepalive_time_ms", app.config.settings.grpc_keepalive_time_ms),
                (
                    "grpc.keepalive_timeout_ms",
                    app.config.settings.grpc_keepalive_timeout_ms,
                ),
                ("grpc.keepalive_permit_without_calls", 0),
                ("grpc.http2.max_pings_without_data", 0),
            ],
        )
        self.stub = books_pb2_grpc.BooksServiceStub(self.channel)
        logger.info(
            f"Connected to books service at {app.config.settings.books_service_url}"
        )

    async def close(self):
        if self.channel:
            await self.channel.close()
            logger.info("Closed books service connection")

    async def search_books_and_authors(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        type_filter: str = "both",
        language: str = "en",
    ) -> books_pb2.SearchResponse:
        request = books_pb2.SearchRequest(
            query=query,
            limit=limit,
            offset=offset,
            type_filter=type_filter,
            language=language,
        )

        try:
            response = await self.stub.SearchBooksAndAuthors(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error searching books and authors: {e.code()} - {e.details()}"
            )
            raise

    async def get_book(
        self, slug: str, language: str = "en"
    ) -> books_pb2.BookDetailResponse:
        request = books_pb2.GetBookRequest(slug=slug, language=language)

        try:
            response = await self.stub.GetBook(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting book: {e.code()} - {e.details()}")
            raise

    async def get_author(
        self, slug: str, language: str = "en"
    ) -> books_pb2.AuthorDetailResponse:
        request = books_pb2.GetAuthorRequest(slug=slug, language=language)

        try:
            response = await self.stub.GetAuthor(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting author: {e.code()} - {e.details()}")
            raise

    async def get_author_books(
        self,
        author_slug: str,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "view_count",
        order: str = "desc",
        language: str = "en",
    ) -> books_pb2.BooksListResponse:
        request = books_pb2.GetAuthorBooksRequest(
            author_slug=author_slug,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            language=language,
        )

        try:
            response = await self.stub.GetAuthorBooks(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting author books: {e.code()} - {e.details()}")
            raise

    async def get_series(
        self, slug: str, language: str = "en"
    ) -> books_pb2.SeriesDetailResponse:
        request = books_pb2.GetSeriesRequest(slug=slug, language=language)

        try:
            response = await self.stub.GetSeries(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting series: {e.code()} - {e.details()}")
            raise

    async def get_series_books(
        self,
        series_slug: str,
        limit: int = 10,
        offset: int = 0,
        language: str = "en",
        sort_by: str = "series_position",
        order: str = "asc",
    ) -> books_pb2.BooksListResponse:
        request = books_pb2.GetSeriesBooksRequest(
            series_slug=series_slug,
            limit=limit,
            offset=offset,
            language=language,
            sort_by=sort_by,
            order=order,
        )

        try:
            response = await self.stub.GetSeriesBooks(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting series books: {e.code()} - {e.details()}")
            raise

    async def update_book(
        self,
        book_id: int,
        fields: typing.Dict[str, typing.Any],
    ) -> books_pb2.BookDetailResponse:
        request = books_pb2.UpdateBookRequest(book_id=book_id)

        for field, value in fields.items():
            setattr(request, field, value)

        try:
            response = await self.stub.UpdateBook(
                request, timeout=app.config.settings.grpc_admin_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error updating book: {e.code()} - {e.details()}")
            raise

    async def update_author(
        self,
        author_id: int,
        fields: typing.Dict[str, typing.Any],
    ) -> books_pb2.AuthorDetailResponse:
        request = books_pb2.UpdateAuthorRequest(author_id=author_id)

        for field, value in fields.items():
            setattr(request, field, value)

        try:
            response = await self.stub.UpdateAuthor(
                request, timeout=app.config.settings.grpc_admin_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error updating author: {e.code()} - {e.details()}")
            raise

    async def update_series(
        self,
        series_id: int,
        fields: typing.Dict[str, typing.Any],
    ) -> books_pb2.SeriesDetailResponse:
        request = books_pb2.UpdateSeriesRequest(series_id=series_id)

        for field, value in fields.items():
            setattr(request, field, value)

        try:
            response = await self.stub.UpdateSeries(
                request, timeout=app.config.settings.grpc_admin_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error updating series: {e.code()} - {e.details()}")
            raise

    async def delete_book(self, book_id: int) -> books_pb2.DeleteEntityResponse:
        request = books_pb2.DeleteBookRequest(book_id=book_id)
        try:
            return await self.stub.DeleteBook(
                request, timeout=app.config.settings.grpc_admin_timeout
            )
        except grpc.RpcError as e:
            logger.error(f"gRPC error deleting book: {e.code()} - {e.details()}")
            raise

    async def delete_author(self, author_id: int) -> books_pb2.DeleteEntityResponse:
        request = books_pb2.DeleteAuthorRequest(author_id=author_id)
        try:
            return await self.stub.DeleteAuthor(
                request, timeout=app.config.settings.grpc_admin_timeout
            )
        except grpc.RpcError as e:
            logger.error(f"gRPC error deleting author: {e.code()} - {e.details()}")
            raise

    async def delete_series(self, series_id: int) -> books_pb2.DeleteEntityResponse:
        request = books_pb2.DeleteSeriesRequest(series_id=series_id)
        try:
            return await self.stub.DeleteSeries(
                request, timeout=app.config.settings.grpc_admin_timeout
            )
        except grpc.RpcError as e:
            logger.error(f"gRPC error deleting series: {e.code()} - {e.details()}")
            raise

    async def spin_slots(self, language: str = "en") -> books_pb2.SpinSlotsResponse:
        request = books_pb2.SpinSlotsRequest(language=language)

        try:
            response = await self.stub.SpinSlots(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error spinning slots: {e.code()} - {e.details()}")
            raise

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
    ) -> books_pb2.DiscoverBookResponse:
        request = books_pb2.DiscoverBookRequest(
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

        try:
            response = await self.stub.DiscoverBook(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error discovering book: {e.code()} - {e.details()}")
            raise

    async def open_case(self, language: str = "en") -> books_pb2.OpenCaseResponse:
        request = books_pb2.OpenCaseRequest(language=language)

        try:
            response = await self.stub.OpenCase(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error opening case: {e.code()} - {e.details()}")
            raise

    async def open_pack(
        self, language: str = "en", length: int = 8
    ) -> books_pb2.OpenPackResponse:
        request = books_pb2.OpenPackRequest(language=language, length=length)

        try:
            response = await self.stub.OpenPack(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error opening pack: {e.code()} - {e.details()}")
            raise

    async def list_categories(self) -> typing.Dict[str, typing.Any]:
        request = books_pb2.ListCategoriesRequest()
        try:
            response = await self.stub.ListCategories(
                request, timeout=app.config.settings.grpc_timeout
            )
            from google.protobuf.json_format import MessageToDict

            return MessageToDict(response, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            logger.error(f"gRPC error listing categories: {e.code()} - {e.details()}")
            raise

    async def get_category(self, category_slug: str) -> typing.Dict[str, typing.Any]:
        request = books_pb2.GetCategoryRequest(category_slug=category_slug)
        try:
            response = await self.stub.GetCategory(
                request, timeout=app.config.settings.grpc_timeout
            )
            from google.protobuf.json_format import MessageToDict

            return MessageToDict(response, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting category: {e.code()} - {e.details()}")
            raise

    async def get_category_books(
        self,
        category_slug: str,
        sub_genre_slug: typing.Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "popularity",
        order: str = "desc",
        language: str = "en",
    ) -> books_pb2.BooksListResponse:
        request = books_pb2.GetCategoryBooksRequest(
            category_slug=category_slug,
            sub_genre_slug=sub_genre_slug or "",
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            language=language,
        )

        try:
            response = await self.stub.GetCategoryBooks(
                request, timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error getting category books: {e.code()} - {e.details()}"
            )
            raise


books_client = BooksClient()
