import grpc
import logging
import typing
import app.config
import app.proto.books_pb2 as books_pb2
import app.proto.books_pb2_grpc as books_pb2_grpc

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
                ("grpc.keepalive_timeout_ms", app.config.settings.grpc_keepalive_timeout_ms),
                ("grpc.keepalive_permit_without_calls", 1),
                ("grpc.http2.max_pings_without_data", 0),
            ]
        )
        self.stub = books_pb2_grpc.BooksServiceStub(self.channel)
        logger.info(f"Connected to books service at {app.config.settings.books_service_url}")

    async def close(self):
        if self.channel:
            await self.channel.close()
            logger.info("Closed books service connection")

    async def search_books_and_authors(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        type_filter: str = "both"
    ) -> books_pb2.SearchResponse:
        request = books_pb2.SearchRequest(
            query=query,
            limit=limit,
            offset=offset,
            type_filter=type_filter
        )

        try:
            response = await self.stub.SearchBooksAndAuthors(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error searching books and authors: {e.code()} - {e.details()}")
            raise

    async def get_book(self, slug: str) -> books_pb2.BookDetailResponse:
        request = books_pb2.GetBookRequest(slug=slug)

        try:
            response = await self.stub.GetBook(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting book: {e.code()} - {e.details()}")
            raise

    async def get_author(self, slug: str) -> books_pb2.AuthorDetailResponse:
        request = books_pb2.GetAuthorRequest(slug=slug)

        try:
            response = await self.stub.GetAuthor(
                request,
                timeout=app.config.settings.grpc_timeout
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
        order: str = "desc"
    ) -> books_pb2.BooksListResponse:
        request = books_pb2.GetAuthorBooksRequest(
            author_slug=author_slug,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order
        )

        try:
            response = await self.stub.GetAuthorBooks(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting author books: {e.code()} - {e.details()}")
            raise

    async def get_series(self, slug: str) -> books_pb2.SeriesDetailResponse:
        request = books_pb2.GetSeriesRequest(slug=slug)

        try:
            response = await self.stub.GetSeries(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting series: {e.code()} - {e.details()}")
            raise

    async def get_series_books(
        self,
        series_slug: str,
        limit: int = 10,
        offset: int = 0
    ) -> books_pb2.BooksListResponse:
        request = books_pb2.GetSeriesBooksRequest(
            series_slug=series_slug,
            limit=limit,
            offset=offset
        )

        try:
            response = await self.stub.GetSeriesBooks(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting series books: {e.code()} - {e.details()}")
            raise


books_client = BooksClient()
