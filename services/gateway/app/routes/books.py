import logging
import typing

import app.config
import app.grpc_clients
import app.middleware.auth
import app.middleware.rate_limit as rate_limit_middleware
import app.models.books_responses
import fastapi
import grpc
from fastapi import Path, Query

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(prefix="/api/v1", tags=["Books"])

limiter = rate_limit_middleware.limiter


@router.get(
    "/search",
    response_model=app.models.books_responses.SearchResponse,
    summary="Search books and authors",
    description="""
    Search for books and authors by text query.

    The search uses Elasticsearch with popularity ranking.
    When searching for an author with high relevance, their most popular books are also included.

    **Type Filter Options:**
    - `all`: Search books, authors, and series (default)
    - `books`: Search only books
    - `authors`: Search only authors
    - `series`: Search only series

    **Language Filter (`language`):**
    Filters book results to the specified language edition (default: `en`).
    Author and series results are always returned regardless of language.
    Book expansions shown under author/series results also respect this filter.

    **Examples:**
    - `/api/v1/search?q=lord of the rings`
    - `/api/v1/search?q=tolkien&type=authors`
    - `/api/v1/search?q=harry potter&type=series`
    - `/api/v1/search?q=python programming&limit=20&offset=0`
    - `/api/v1/search?q=hobbit&language=pl`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def search_books_and_authors(
    request: fastapi.Request,
    q: str = Query(..., min_length=1, description="Search query"),
    type: str = Query(
        "all", regex="^(all|books|authors|series)$", description="Filter by type"
    ),
    limit: int = Query(10, ge=1, le=100, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    language: str = Query(
        "en", min_length=2, max_length=10, description="Language code (e.g. en, pl, de)"
    ),
):
    try:
        response = await app.grpc_clients.books_client.search_books_and_authors(
            query=q, limit=limit, offset=offset, type_filter=type, language=language
        )

        results = []
        for result in response.results:
            results.append(
                {
                    "type": result.type,
                    "id": result.id,
                    "title": result.title,
                    "slug": result.slug,
                    "cover_url": result.cover_url,
                    "authors": list(result.authors),
                    "relevance_score": result.relevance_score,
                    "view_count": result.view_count,
                    "author_slugs": list(result.author_slugs),
                    "series_slug": result.series_slug,
                    "avg_rating": result.avg_rating or None,
                    "rating_count": result.rating_count,
                    "book_count": result.book_count,
                }
            )

        return {
            "success": True,
            "data": {
                "results": results,
                "total_count": response.total_count,
                "limit": limit,
                "offset": offset,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        logger.error(f"gRPC error in search: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Search failed: {e.details()}",
        )


@router.get(
    "/books/{slug}",
    response_model=app.models.books_responses.BookDetailResponse,
    summary="Get book details",
    description="""
    Get full details of a book by slug.

    Returns comprehensive information including:
    - Title, description, language, publication year
    - Authors and genres
    - Cover images and formats
    - Overall rating, rating count, and per-dimension rating stats (`sub_rating_stats`)
    - View count and external IDs (Open Library, Google Books)

    **Language (`language`):**
    The same slug may exist in multiple language editions (e.g. `en`, `pl`, `de`).
    Use this parameter to select the desired edition (default: `en`).
    Returns 404 if no edition exists for the requested language.

    **`sub_rating_stats`** - All 8 keys are always present (default `avg: "0"`, `count: 0`).
    Each value: `{"avg": "3.50", "count": 12}`.

    Quality dimensions (1 = poor, 5 = excellent):
    - `emotional_impact` - 1: leaves no impression / 5: deeply moving
    - `intellectual_depth` - 1: shallow, surface-level / 5: profound, thought-provoking
    - `writing_quality` - 1: poorly written / 5: masterfully crafted prose
    - `rereadability` - 1: no desire to revisit / 5: would gladly reread

    Spectrum dimensions (1 and 5 are opposite ends, neither is inherently better):
    - `pacing` - 1: slow, deliberate / 5: fast, action-packed
    - `readability` - 1: dense, challenging / 5: light, easy read
    - `plot_complexity` - 1: simple, straightforward / 5: complex, multi-layered
    - `humor` - 1: serious, no humor / 5: very funny, comedic

    **Examples:**
    - `/api/v1/books/the-lord-of-the-rings`
    - `/api/v1/books/the-lord-of-the-rings?language=pl`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_book(
    request: fastapi.Request,
    slug: str = Path(..., description="Book slug"),
    language: str = Query(
        "en", min_length=2, max_length=10, description="Language code (e.g. en, pl, de)"
    ),
):
    try:
        response = await app.grpc_clients.books_client.get_book(slug, language=language)

        book = response.book

        return {
            "success": True,
            "data": {
                "book_id": book.book_id,
                "title": book.title,
                "slug": book.slug,
                "description": book.description,
                "language": book.language,
                "original_publication_year": book.original_publication_year,
                "formats": list(book.formats),
                "primary_cover_url": book.primary_cover_url,
                "cover_history": [
                    {"url": cover.url, "width": cover.width, "size": cover.size}
                    for cover in book.cover_history
                ],
                "rating_count": book.rating_count,
                "avg_rating": book.avg_rating,
                "sub_rating_stats": {
                    key: {"avg": stat.avg, "count": stat.count}
                    for key, stat in book.sub_rating_stats.items()
                },
                "view_count": book.view_count,
                "last_viewed_at": book.last_viewed_at,
                "authors": [
                    {
                        "author_id": author.author_id,
                        "name": author.name,
                        "slug": author.slug,
                        "photo_url": author.photo_url,
                    }
                    for author in book.authors
                ],
                "genres": [
                    {"genre_id": genre.genre_id, "name": genre.name, "slug": genre.slug}
                    for genre in book.genres
                ],
                "series": (
                    {
                        "series_id": book.series.series_id,
                        "name": book.series.name,
                        "slug": book.series.slug,
                        "total_books": book.series.total_books,
                    }
                    if book.HasField("series")
                    else None
                ),
                "series_position": (
                    book.series_position if book.series_position else None
                ),
                "open_library_id": book.open_library_id,
                "google_books_id": book.google_books_id,
                "created_at": book.created_at,
                "updated_at": book.updated_at,
                "isbn": list(book.isbn),
                "publisher": book.publisher,
                "number_of_pages": book.number_of_pages,
                "external_ids": dict(book.external_ids),
                "ol_rating_count": book.ol_rating_count,
                "ol_avg_rating": book.ol_avg_rating,
                "ol_want_to_read_count": book.ol_want_to_read_count,
                "ol_currently_reading_count": book.ol_currently_reading_count,
                "ol_already_read_count": book.ol_already_read_count,
                "first_sentence": book.first_sentence or None,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        logger.error(f"gRPC error getting book: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404, detail=f"Book not found: {slug}"
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get book failed: {e.details()}",
        )


@router.get(
    "/authors/{slug}",
    response_model=app.models.books_responses.AuthorDetailResponse,
    summary="Get author details",
    description="""
    Get full details of an author by slug.

    Returns:
    - Name, biography, photo
    - Birth and death dates
    - View count and book count
    - External IDs
    - Aggregate stats: `books_count`, `books_avg_rating`, `books_total_ratings`,
      `books_total_views`, `book_categories`

    **Language (`language`):**
    Filters all book-derived aggregate stats to the specified language edition (default: `en`).
    Only books in that language are counted towards `books_count`, `books_avg_rating`,
    `books_total_ratings`, `books_total_views`, and `book_categories`.
    The author record itself (name, bio, etc.) is always returned regardless of language.

    **Examples:**
    - `/api/v1/authors/j-r-r-tolkien`
    - `/api/v1/authors/j-r-r-tolkien?language=pl`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_author(
    request: fastapi.Request,
    slug: str = Path(..., description="Author slug"),
    language: str = Query(
        "en", min_length=2, max_length=10, description="Language code (e.g. en, pl, de)"
    ),
):
    try:
        response = await app.grpc_clients.books_client.get_author(
            slug, language=language
        )

        author = response.author

        return {
            "success": True,
            "data": {
                "author_id": author.author_id,
                "name": author.name,
                "slug": author.slug,
                "bio": author.bio or None,
                "birth_date": author.birth_date or None,
                "death_date": author.death_date or None,
                "birth_place": author.birth_place or None,
                "nationality": author.nationality or None,
                "photo_url": author.photo_url or None,
                "view_count": author.view_count,
                "last_viewed_at": author.last_viewed_at or None,
                "books_count": author.books_count,
                "book_categories": list(author.book_categories),
                "books_avg_rating": float(author.books_avg_rating),
                "books_total_ratings": author.books_total_ratings,
                "books_total_views": author.books_total_views,
                "books_ol_avg_rating": author.books_ol_avg_rating or None,
                "books_ol_total_ratings": author.books_ol_total_ratings,
                "app_want_to_read_count": author.app_want_to_read_count,
                "app_reading_count": author.app_reading_count,
                "app_read_count": author.app_read_count,
                "ol_want_to_read_count": author.ol_want_to_read_count,
                "ol_currently_reading_count": author.ol_currently_reading_count,
                "ol_already_read_count": author.ol_already_read_count,
                "open_library_id": author.open_library_id or None,
                "created_at": author.created_at,
                "updated_at": author.updated_at,
                "wikidata_id": author.wikidata_id or None,
                "wikipedia_url": author.wikipedia_url or None,
                "remote_ids": dict(author.remote_ids),
                "alternate_names": list(author.alternate_names),
            },
            "error": None,
        }
    except grpc.RpcError as e:
        logger.error(f"gRPC error getting author: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404, detail=f"Author not found: {slug}"
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get author failed: {e.details()}",
        )


@router.get(
    "/authors/{slug}/books",
    response_model=app.models.books_responses.AuthorBooksResponse,
    summary="Get author's books",
    description="""
    Get all books by an author, paginated and sorted.

    **Sort Options (sort_by):**
    - `publication_year` - Original publication year
    - `combined_rating` - Combined weighted rating (app + OL) (default)
    - `readers_count` - Total readers across app and OL bookshelves

    **Order Options:**
    - `asc` - Ascending order
    - `desc` - Descending order (default)

    **Language (`language`):**
    Filters the book list to the specified language edition (default: `en`).
    Only books in that language are returned. `total_count` reflects the filtered count.

    **Examples:**
    - `/api/v1/authors/j-r-r-tolkien/books?sort_by=publication_year&order=asc`
    - `/api/v1/authors/j-r-r-tolkien/books?sort_by=combined_rating&order=desc`
    - `/api/v1/authors/j-r-r-tolkien/books?limit=10&offset=0`
    - `/api/v1/authors/j-r-r-tolkien/books?language=pl`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_author_books(
    request: fastapi.Request,
    slug: str = Path(..., description="Author slug"),
    limit: int = Query(10, ge=1, le=100, description="Number of books per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_by: str = Query(
        "combined_rating",
        regex="^(publication_year|combined_rating|readers_count)$",
        description="Sort field",
    ),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    language: str = Query(
        "en", min_length=2, max_length=10, description="Language code (e.g. en, pl, de)"
    ),
):
    try:
        response = await app.grpc_clients.books_client.get_author_books(
            author_slug=slug,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            language=language,
        )

        books = []
        for book in response.books:
            books.append(
                {
                    "book_id": book.book_id,
                    "title": book.title,
                    "slug": book.slug,
                    "description": book.description,
                    "original_publication_year": book.original_publication_year,
                    "primary_cover_url": book.primary_cover_url,
                    "rating_count": book.rating_count,
                    "avg_rating": book.avg_rating,
                    "view_count": book.view_count,
                    "ol_rating_count": book.ol_rating_count,
                    "ol_avg_rating": book.ol_avg_rating or None,
                    "ol_want_to_read_count": book.ol_want_to_read_count,
                    "ol_currently_reading_count": book.ol_currently_reading_count,
                    "ol_already_read_count": book.ol_already_read_count,
                    "app_want_to_read_count": book.app_want_to_read_count,
                    "app_reading_count": book.app_reading_count,
                    "app_read_count": book.app_read_count,
                    "genres": [
                        {
                            "genre_id": genre.genre_id,
                            "name": genre.name,
                            "slug": genre.slug,
                        }
                        for genre in book.genres
                    ],
                }
            )

        return {
            "success": True,
            "data": {
                "books": books,
                "total_count": response.total_count,
                "limit": limit,
                "offset": offset,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        logger.error(f"gRPC error getting author books: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get author books failed: {e.details()}",
        )


@router.get(
    "/series/{slug}",
    response_model=app.models.books_responses.SeriesDetailResponse,
    summary="Get series details",
    description="""
    Get full details of a series by slug.

    Returns:
    - Series name, description
    - Aggregate stats computed from books in the series: `total_books`, `avg_rating`,
      `rating_count`, `ol_avg_rating`, `ol_rating_count`, `total_views`

    **Language (`language`):**
    Filters all book-derived aggregate stats to the specified language edition (default: `en`).
    Only books in that language are counted towards `total_books`, `avg_rating`, `rating_count`,
    `ol_avg_rating`, `ol_rating_count`, and `total_views`.
    The series record itself (name, description, etc.) is always returned regardless of language.

    **Examples:**
    - `/api/v1/series/harry-potter`
    - `/api/v1/series/harry-potter?language=pl`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_series(
    request: fastapi.Request,
    slug: str = Path(..., description="Series slug"),
    language: str = Query(
        "en", min_length=2, max_length=10, description="Language code (e.g. en, pl, de)"
    ),
):
    try:
        response = await app.grpc_clients.books_client.get_series(
            slug, language=language
        )

        series = response.series

        return {
            "success": True,
            "data": {
                "series_id": series.series_id,
                "name": series.name,
                "slug": series.slug,
                "description": series.description,
                "total_books": series.total_books,
                "view_count": series.view_count,
                "last_viewed_at": series.last_viewed_at,
                "created_at": series.created_at,
                "updated_at": series.updated_at,
                "avg_rating": series.avg_rating or None,
                "rating_count": series.rating_count,
                "ol_avg_rating": series.ol_avg_rating or None,
                "ol_rating_count": series.ol_rating_count,
                "total_views": series.total_views,
                "app_want_to_read_count": series.app_want_to_read_count,
                "app_reading_count": series.app_reading_count,
                "app_read_count": series.app_read_count,
                "ol_want_to_read_count": series.ol_want_to_read_count,
                "ol_currently_reading_count": series.ol_currently_reading_count,
                "ol_already_read_count": series.ol_already_read_count,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        logger.error(f"gRPC error getting series: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404, detail=f"Series not found: {slug}"
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get series failed: {e.details()}",
        )


def _comment_with_rating_to_dict(c) -> typing.Dict[str, typing.Any]:
    return {
        "comment_id": c.comment_id,
        "user_id": c.user_id,
        "username": c.username,
        "book_id": c.book_id,
        "book_slug": c.book_slug,
        "body": c.body,
        "is_spoiler": c.is_spoiler,
        "comment_created_at": c.comment_created_at,
        "comment_updated_at": c.comment_updated_at,
        "rating": (
            {
                "overall_rating": c.overall_rating,
                "review_text": c.review_text or None,
                "pacing": c.pacing if c.has_pacing else None,
                "emotional_impact": (
                    c.emotional_impact if c.has_emotional_impact else None
                ),
                "intellectual_depth": (
                    c.intellectual_depth if c.has_intellectual_depth else None
                ),
                "writing_quality": c.writing_quality if c.has_writing_quality else None,
                "rereadability": c.rereadability if c.has_rereadability else None,
                "readability": c.readability if c.has_readability else None,
                "plot_complexity": c.plot_complexity if c.has_plot_complexity else None,
                "humor": c.humor if c.has_humor else None,
            }
            if c.has_rating
            else None
        ),
    }


@router.get(
    "/books/{slug}/comments",
    response_model=app.models.books_responses.BookCommentsResponse,
    summary="Get comments for a book",
    description="""
    Retrieve public comments for a book. No authentication required.

    Each item includes `comment_id`, `user_id`, `username`, `body`, `is_spoiler`,
    `comment_created_at`, `comment_updated_at`, and an optional `rating` object.
    The `rating` field is `null` when the commenter has not rated the book.

    **Sort Options (sort_by):**
    - `created_at` - Newest/oldest first (default)
    - `overall_rating` - By commenter's overall rating
    - Quality dimensions (1 = poor, 5 = excellent):
      `emotional_impact`, `intellectual_depth`, `writing_quality`, `rereadability`
    - Spectrum dimensions (opposite ends, neither better):
      `pacing` (slow-fast), `readability` (dense-light), `plot_complexity` (simple-complex),
      `humor` (serious-funny)

    When authenticated, the requesting user's own comment is returned in `my_entry`
    regardless of the current page, so the frontend can pin it at the top.

    **Examples:**
    - `/api/v1/books/the-hobbit/comments?sort_by=overall_rating&order=desc`
    - `/api/v1/books/the-hobbit/comments?include_spoilers=true&limit=20`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_book_comments(
    request: fastapi.Request,
    slug: str = Path(..., description="Book slug"),
    limit: int = Query(10, ge=1, le=100, description="Number of comments per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    include_spoilers: bool = Query(False, description="Include spoiler comments"),
    sort_by: str = Query(
        "created_at",
        regex="^(created_at|overall_rating|pacing|emotional_impact|intellectual_depth|writing_quality|rereadability|readability|plot_complexity|humor)$",
        description="Sort field",
    ),
    user: typing.Optional[typing.Dict[str, typing.Any]] = fastapi.Depends(
        app.middleware.auth.get_current_user_optional
    ),
):
    requesting_user_id = user["user_id"] if user else 0
    try:
        response = await app.grpc_clients.user_data_client.get_book_comments(
            book_slug=slug,
            limit=limit,
            offset=offset,
            order=order,
            include_spoilers=include_spoilers,
            sort_by=sort_by,
            requesting_user_id=requesting_user_id,
        )
        my_entry = (
            _comment_with_rating_to_dict(response.my_entry)
            if response.HasField("my_entry")
            else None
        )
        return {
            "success": True,
            "data": {
                "items": [_comment_with_rating_to_dict(c) for c in response.comments],
                "total_count": response.total_count,
                "limit": limit,
                "offset": offset,
                "my_entry": my_entry,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        logger.error(f"gRPC error getting book comments: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404, detail=f"Book not found: {slug}"
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get book comments failed: {e.details()}",
        )


@router.get(
    "/series/{slug}/books",
    response_model=app.models.books_responses.SeriesBooksResponse,
    summary="Get series books",
    description="""
    Get all books in a series, paginated and sorted.

    **Sort Options (sort_by):**
    - `series_position` - Position in the series (default)
    - `publication_year` - Original publication year
    - `combined_rating` - Combined weighted rating (app + OL)
    - `readers_count` - Total readers across app and OL bookshelves

    **Order Options:**
    - `asc` - Ascending order (default)
    - `desc` - Descending order

    **Language (`language`):**
    Filters the book list to the specified language edition (default: `en`).
    Only books in that language are returned. `total_count` reflects the filtered count.

    **Examples:**
    - `/api/v1/series/harry-potter/books?limit=10&offset=0`
    - `/api/v1/series/harry-potter/books?language=pl`
    - `/api/v1/series/harry-potter/books?sort_by=combined_rating&order=desc`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_series_books(
    request: fastapi.Request,
    slug: str = Path(..., description="Series slug"),
    limit: int = Query(10, ge=1, le=100, description="Number of books per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    language: str = Query(
        "en", min_length=2, max_length=10, description="Language code (e.g. en, pl, de)"
    ),
    sort_by: str = Query(
        "series_position",
        regex="^(series_position|publication_year|combined_rating|readers_count)$",
        description="Sort field",
    ),
    order: str = Query("asc", regex="^(asc|desc)$", description="Sort order"),
):
    try:
        response = await app.grpc_clients.books_client.get_series_books(
            series_slug=slug,
            limit=limit,
            offset=offset,
            language=language,
            sort_by=sort_by,
            order=order,
        )

        books = []
        for book in response.books:
            books.append(
                {
                    "book_id": book.book_id,
                    "title": book.title,
                    "slug": book.slug,
                    "description": book.description,
                    "original_publication_year": book.original_publication_year,
                    "primary_cover_url": book.primary_cover_url,
                    "rating_count": book.rating_count,
                    "avg_rating": float(book.avg_rating),
                    "view_count": book.view_count,
                    "series_position": (
                        book.series_position if book.series_position else None
                    ),
                    "ol_rating_count": book.ol_rating_count,
                    "ol_avg_rating": book.ol_avg_rating or None,
                    "ol_want_to_read_count": book.ol_want_to_read_count,
                    "ol_currently_reading_count": book.ol_currently_reading_count,
                    "ol_already_read_count": book.ol_already_read_count,
                    "app_want_to_read_count": book.app_want_to_read_count,
                    "app_reading_count": book.app_reading_count,
                    "app_read_count": book.app_read_count,
                    "genres": [
                        {
                            "genre_id": genre.genre_id,
                            "name": genre.name,
                            "slug": genre.slug,
                        }
                        for genre in book.genres
                    ],
                }
            )

        return {
            "success": True,
            "data": {
                "books": books,
                "total_count": response.total_count,
                "limit": limit,
                "offset": offset,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        logger.error(f"gRPC error getting series books: {e.code()} - {e.details()}")
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get series books failed: {e.details()}",
        )
