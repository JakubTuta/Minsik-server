import grpc
import logging
import uuid
import asyncio
import json
import concurrent.futures
import httpx
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio

import app.config
import app.models
import app.fetchers.open_library
import app.fetchers.google_books
import app.services.book_service
import app.workers.ingestion_worker
import app.workers.dump_importer
import app.proto.ingestion_pb2 as ingestion_pb2
import app.proto.ingestion_pb2_grpc as ingestion_pb2_grpc

logger = logging.getLogger(__name__)

redis_client = redis.Redis(
    host=app.config.settings.redis_host,
    port=app.config.settings.redis_port,
    db=app.config.settings.redis_db,
    password=app.config.settings.redis_password if app.config.settings.redis_password else None,
    decode_responses=True
)

_COVERAGE_CACHE_KEY = "coverage_stats"
_COVERAGE_CACHE_TTL = 3600


class IngestionService(ingestion_pb2_grpc.IngestionServiceServicer):
    async def TriggerIngestion(self, request, context):
        try:
            total_books = request.total_books
            source = request.source or "both"
            language = request.language or "en"

            if total_books <= 0:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("total_books must be greater than 0")
                return ingestion_pb2.TriggerIngestionResponse()

            if source not in ["open_library", "google_books", "both"]:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("source must be one of: open_library, google_books, both")
                return ingestion_pb2.TriggerIngestionResponse()

            job_id = str(uuid.uuid4())

            logger.info(f"Starting synchronous ingestion job {job_id}: {total_books} books from {source} ({language})")

            result = await app.workers.ingestion_worker.process_ingestion_job(job_id, total_books, source, language)

            return ingestion_pb2.TriggerIngestionResponse(
                job_id=job_id,
                status="failed" if result["error"] else "completed",
                total_books=total_books,
                processed=result["processed"],
                successful=result["successful"],
                failed=result["failed"],
                error_message=result["error"] or ""
            )

        except Exception as e:
            logger.error(f"Error triggering ingestion: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.TriggerIngestionResponse()

    async def SearchBook(self, request, context):
        try:
            title = request.title
            author = request.author or ""
            source = request.source or "both"
            limit = request.limit or 10

            if not title:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("title is required")
                return ingestion_pb2.SearchBookResponse()

            if source not in ["open_library", "google_books", "both"]:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("source must be one of: open_library, google_books, both")
                return ingestion_pb2.SearchBookResponse()

            all_books = []

            if source in ["open_library", "both"]:
                async with app.fetchers.open_library.OpenLibraryFetcher() as fetcher:
                    ol_books = await fetcher.search_book(title, author, limit)
                    all_books.extend(ol_books)

            if source in ["google_books", "both"]:
                async with app.fetchers.google_books.GoogleBooksFetcher() as fetcher:
                    gb_books = await fetcher.search_book(title, author, limit)
                    all_books.extend(gb_books)

            book_results = []
            books_to_insert = []

            for book in all_books[:limit]:
                book_result = ingestion_pb2.BookResult(
                    title=book.get("title", ""),
                    authors=book.get("authors", []),
                    description=book.get("description") or "",
                    publication_year=book.get("publication_year") or 0,
                    language=book.get("language", ""),
                    page_count=book.get("page_count") or 0,
                    cover_url=book.get("cover_url") or "",
                    isbn=book.get("isbn", []),
                    publisher=book.get("publisher") or "",
                    genres=book.get("genres", []),
                    open_library_id=book.get("open_library_id") or "",
                    google_books_id=book.get("google_books_id") or "",
                    source=book.get("source", "")
                )
                book_results.append(book_result)

                book_for_db = {
                    "title": book.get("title", ""),
                    "language": book.get("language", "en"),
                    "description": book.get("description"),
                    "original_publication_year": book.get("publication_year"),
                    "primary_cover_url": book.get("cover_url"),
                    "open_library_id": book.get("open_library_id"),
                    "google_books_id": book.get("google_books_id"),
                    "authors": [
                        {"name": author_name, "slug": None, "bio": None, "birth_date": None, "death_date": None, "photo_url": None, "open_library_id": None}
                        for author_name in book.get("authors", [])
                    ],
                    "genres": [
                        {"name": genre_name, "slug": None}
                        for genre_name in book.get("genres", [])
                    ],
                    "formats": [],
                    "cover_history": [
                        {
                            "year": book.get("publication_year") or 2024,
                            "cover_url": book.get("cover_url"),
                            "publisher": book.get("publisher", "Unknown")
                        }
                    ] if book.get("cover_url") else []
                }
                books_to_insert.append(book_for_db)

            if books_to_insert:
                try:
                    insert_result = await app.services.book_service.insert_books(books_to_insert)
                    logger.info(f"Inserted {insert_result['successful']} books, {insert_result['failed']} failed")
                except Exception as e:
                    logger.error(f"Error inserting books into database: {str(e)}")

            logger.info(f"Search for '{title}' by '{author}' returned {len(book_results)} results from {source}")

            return ingestion_pb2.SearchBookResponse(
                total_results=len(book_results),
                books=book_results
            )

        except Exception as e:
            logger.error(f"Error searching for book: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.SearchBookResponse()

    async def GetDataCoverage(self, request, context):
        try:
            cached = redis_client.get(_COVERAGE_CACHE_KEY)
            if cached:
                data = json.loads(cached)
                return ingestion_pb2.GetDataCoverageResponse(
                    db_books_count=data["db_books_count"],
                    db_authors_count=data["db_authors_count"],
                    db_series_count=data["db_series_count"],
                    ol_english_total=data["ol_english_total"],
                    coverage_percent=data["coverage_percent"],
                    cached=True
                )

            async with app.models.AsyncSessionLocal() as session:
                books_result = await session.execute(
                    sqlalchemy.text("SELECT COUNT(*) FROM books.books WHERE language = 'en'")
                )
                db_books_count = books_result.scalar_one()

                authors_result = await session.execute(
                    sqlalchemy.text("SELECT COUNT(*) FROM books.authors")
                )
                db_authors_count = authors_result.scalar_one()

                series_result = await session.execute(
                    sqlalchemy.text("SELECT COUNT(*) FROM books.series")
                )
                db_series_count = series_result.scalar_one()

            ol_english_total = await _fetch_ol_english_total()

            coverage_percent = 0.0
            if ol_english_total > 0:
                coverage_percent = (db_books_count / ol_english_total) * 100

            cache_data = {
                "db_books_count": db_books_count,
                "db_authors_count": db_authors_count,
                "db_series_count": db_series_count,
                "ol_english_total": ol_english_total,
                "coverage_percent": coverage_percent
            }
            redis_client.setex(_COVERAGE_CACHE_KEY, _COVERAGE_CACHE_TTL, json.dumps(cache_data))

            logger.info(f"Data coverage: {db_books_count} books, {ol_english_total} OL total, {coverage_percent:.4f}%")

            return ingestion_pb2.GetDataCoverageResponse(
                db_books_count=db_books_count,
                db_authors_count=db_authors_count,
                db_series_count=db_series_count,
                ol_english_total=ol_english_total,
                coverage_percent=coverage_percent,
                cached=False
            )

        except Exception as e:
            logger.error(f"Error getting data coverage: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.GetDataCoverageResponse()

    async def ImportDump(self, request, context):
        try:
            is_running = redis_client.exists("dump_import_running")
            if is_running:
                return ingestion_pb2.ImportDumpResponse(
                    status="already_running",
                    message="Dump import is already in progress"
                )

            job_id = str(uuid.uuid4())
            asyncio.create_task(app.workers.dump_importer.run_import_dump(job_id, redis_client))

            return ingestion_pb2.ImportDumpResponse(
                status="started",
                message=f"Dump import started (job_id: {job_id}). Check service logs for progress."
            )

        except Exception as e:
            logger.error(f"Error starting dump import: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.ImportDumpResponse()


async def _fetch_ol_english_total() -> int:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{app.config.settings.open_library_api_url}/search.json",
                params={"language": "eng", "limit": 0},
                headers={"User-Agent": "Minsik/1.0 (contact@minsik.app)"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("numFound", 0)
    except Exception as e:
        logger.error(f"Failed to fetch OL English total: {str(e)}")
        return 0


async def serve():
    server = grpc.aio.server(concurrent.futures.ThreadPoolExecutor(max_workers=10))
    ingestion_pb2_grpc.add_IngestionServiceServicer_to_server(IngestionService(), server)

    listen_addr = f"{app.config.settings.ingestion_service_host}:{app.config.settings.ingestion_grpc_port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting Ingestion gRPC server on {listen_addr}")
    await server.start()
    await server.wait_for_termination()
