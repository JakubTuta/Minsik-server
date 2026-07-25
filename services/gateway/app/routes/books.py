import logging
import typing

import app.config
import app.grpc_clients
import app.middleware.auth
import app.middleware.rate_limit
import app.models.books_responses
import app.utils.language
import app.utils.responses
import fastapi
import grpc

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(prefix="/api/v1", tags=["Books"])

limiter = app.middleware.rate_limit.limiter


@router.get(
    "/search/suggest",
    response_model=app.models.books_responses.SuggestResponse,
    summary="Typeahead suggestions for app bar search",
    description="""
    Fast prefix-based suggestions for the app bar quick search field.

    Returns a mixed list of books, authors, and series ranked by relevance and popularity.
    Designed for low-latency typeahead — results are cached for 60 seconds.

    **Examples:**
    - `/api/v1/search/suggest?q=har` → Harry Potter books + J.K. Rowling
    - `/api/v1/search/suggest?q=tolkien` → Tolkien author + his books/series
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_suggest_per_minute}/minute")
async def suggest_search(
    request: fastapi.Request,
    q: str = fastapi.Query(..., min_length=1, description="Search query (partial input)"),
    limit: int = fastapi.Query(8, ge=1, le=20, description="Max suggestions to return"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        response = await app.grpc_clients.books_client.suggest_search(
            query=q, limit=limit, language=language
        )

        items = [
            {
                "type": item.type,
                "id": item.id,
                "title": item.title,
                "slug": item.slug,
                "cover_url": item.cover_url or None,
                "authors": list(item.authors),
                "score": item.score,
                "readers": item.readers,
                "app_avg_rating": (
                    float(item.app_avg_rating) if item.app_avg_rating else 0.0
                ),
                "app_rating_count": item.app_rating_count,
                "ol_avg_rating": (
                    float(item.ol_avg_rating) if item.ol_avg_rating else 0.0
                ),
                "ol_rating_count": item.ol_rating_count,
                "work_id": item.work_id or None,
                "language": item.language or None,
            }
            for item in response.items
        ]

        return {
            "success": True,
            "data": {"items": items},
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "in suggest", e)
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Suggest failed: {e.details()}",
        )


@router.get(
    "/search",
    response_model=app.models.books_responses.SearchResponse,
    summary="Search books and authors",
    description="""
    Search for books and authors by text query.

    The search uses Elasticsearch with popularity ranking.
    When searching for an author with high relevance, their most popular books are also included.

    **Type Filter Options:**
    - `all`: Search books, authors, and series (default) — categories are excluded from `all`
    - `books`: Search only books
    - `authors`: Search only authors
    - `series`: Search only series
    - `categories`: Search by genre/category name or slug, returns books belonging to matched genres

    **Language Filter (`language`):**
    Filters book results to the specified language edition (default: `en`).
    Author and series results are always returned regardless of language.
    Book expansions shown under author/series results also respect this filter.
    Category results are also filtered by language.

    **Examples:**
    - `/api/v1/search?q=lord of the rings`
    - `/api/v1/search?q=tolkien&type=authors`
    - `/api/v1/search?q=harry potter&type=series`
    - `/api/v1/search?q=python programming&limit=20&offset=0`
    - `/api/v1/search?q=hobbit&language=pl`
    - `/api/v1/search?q=fantasy&type=categories`
    - `/api/v1/search?q=sci-fi&type=categories&language=en`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def search_books_and_authors(
    request: fastapi.Request,
    q: str = fastapi.Query(..., min_length=1, description="Search query"),
    type: str = fastapi.Query(
        "all",
        regex="^(all|books|authors|series|categories)$",
        description="Filter by type",
    ),
    limit: int = fastapi.Query(10, ge=1, le=100, description="Number of results per page"),
    offset: int = fastapi.Query(0, ge=0, description="Pagination offset"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
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
                    "author_slugs": list(result.author_slugs),
                    "series_slug": result.series_slug,
                    "app_avg_rating": (
                        float(result.app_avg_rating) if result.app_avg_rating else 0.0
                    ),
                    "app_rating_count": result.app_rating_count,
                    "ol_avg_rating": (
                        float(result.ol_avg_rating) if result.ol_avg_rating else 0.0
                    ),
                    "ol_rating_count": result.ol_rating_count,
                    "book_count": result.book_count,
                    "readers": result.readers,
                    "work_id": result.work_id or None,
                    "language": result.language or None,
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
        app.utils.responses.log_grpc_error(logger, "in search", e)
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
    slug: str = fastapi.Path(..., description="Book slug"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        response = await app.grpc_clients.books_client.get_book(slug, language=language)

        return {
            "success": True,
            "data": _book_detail_proto_to_dict(response.book),
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "getting book", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404, detail=f"Book not found: {slug}"
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get book failed: {e.details()}",
        )


@router.get(
    "/books/{slug}/language-variants",
    response_model=app.models.books_responses.BookLanguageVariantsResponse,
    summary="Get language editions for a book",
    description="Returns all editions of a book in languages other than the excluded one.",
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_book_language_variants(
    request: fastapi.Request,
    slug: str = fastapi.Path(..., description="Book slug"),
    exclude_language: str = fastapi.Query(
        "en", min_length=2, max_length=10, description="Language to exclude (currently displayed)"
    ),
):
    try:
        response = await app.grpc_clients.books_client.get_book_language_variants(
            slug, exclude_language=exclude_language
        )

        items = [
            {
                "book_id": item.book_id,
                "slug": item.slug,
                "language": item.language,
                "title": item.title,
                "primary_cover_url": item.primary_cover_url or None,
            }
            for item in response.items
        ]

        return {
            "success": True,
            "data": {"items": items},
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "getting book language variants", e)
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get language variants failed: {e.details()}",
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
    slug: str = fastapi.Path(..., description="Author slug"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
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
                "books_ol_avg_rating": (
                    float(author.books_ol_avg_rating)
                    if author.books_ol_avg_rating
                    else 0.0
                ),
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
        app.utils.responses.log_grpc_error(logger, "getting author", e)
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
    slug: str = fastapi.Path(..., description="Author slug"),
    limit: int = fastapi.Query(10, ge=1, le=100, description="Number of books per page"),
    offset: int = fastapi.Query(0, ge=0, description="Pagination offset"),
    sort_by: str = fastapi.Query(
        "combined_rating",
        regex="^(publication_year|combined_rating|readers_count)$",
        description="Sort field",
    ),
    order: str = fastapi.Query("desc", regex="^(asc|desc)$", description="Sort order"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
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
            books.append(_book_summary_proto_to_dict(book))

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
        app.utils.responses.log_grpc_error(logger, "getting author books", e)
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get author books failed: {e.details()}",
        )


@router.get(
    "/authors/{slug}/quote",
    response_model=app.models.books_responses.AuthorQuoteResponse,
    summary="Get author quote",
    description="""
    Get a representative quote (first sentence) from the author's most-read book.

    Returns the first sentence of the most-read book that has a first_sentence available.
    Returns null data if no book with a first sentence is found.

    **Examples:**
    - `/api/v1/authors/j-r-r-tolkien/quote`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_author_quote(
    request: fastapi.Request,
    slug: str = fastapi.Path(..., description="Author slug"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        books_response = await app.grpc_clients.books_client.get_author_books(
            author_slug=slug,
            limit=20,
            offset=0,
            sort_by="readers_count",
            order="desc",
            language=language,
        )

        for book_summary in books_response.books:
            try:
                book_response = await app.grpc_clients.books_client.get_book(
                    book_summary.slug, language=language
                )
                book = book_response.book
                if book.first_sentence:
                    return {
                        "success": True,
                        "data": {
                            "first_sentence": book.first_sentence,
                            "book_title": book.title,
                            "book_slug": book.slug,
                            "publication_year": (
                                book.original_publication_year
                                if book.original_publication_year
                                else None
                            ),
                        },
                        "error": None,
                    }
            except grpc.RpcError:
                continue

        return {"success": True, "data": None, "error": None}
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "getting author quote", e)
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get author quote failed: {e.details()}",
        )


@router.get(
    "/authors/{slug}/top-books",
    response_model=app.models.books_responses.AuthorTopBooksResponse,
    summary="Get author top books",
    description="""
    Get the top 3 most-read books by an author.

    Returns up to 3 books sorted by combined readers count (descending).

    **Examples:**
    - `/api/v1/authors/j-r-r-tolkien/top-books`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_author_top_books(
    request: fastapi.Request,
    slug: str = fastapi.Path(..., description="Author slug"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        response = await app.grpc_clients.books_client.get_author_books(
            author_slug=slug,
            limit=3,
            offset=0,
            sort_by="readers_count",
            order="desc",
            language=language,
        )

        books = [_book_summary_proto_to_dict(book) for book in response.books]

        return {"success": True, "data": {"books": books}, "error": None}
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "getting author top books", e)
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get author top books failed: {e.details()}",
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
    slug: str = fastapi.Path(..., description="Series slug"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
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
                "avg_rating": float(series.avg_rating) if series.avg_rating else 0.0,
                "rating_count": series.rating_count,
                "ol_avg_rating": (
                    float(series.ol_avg_rating) if series.ol_avg_rating else 0.0
                ),
                "ol_rating_count": series.ol_rating_count,
                "app_want_to_read_count": series.app_want_to_read_count,
                "app_reading_count": series.app_reading_count,
                "app_read_count": series.app_read_count,
                "ol_want_to_read_count": series.ol_want_to_read_count,
                "ol_currently_reading_count": series.ol_currently_reading_count,
                "ol_already_read_count": series.ol_already_read_count,
                "total_pages": series.total_pages,
                "author": {
                    "author_id": series.primary_author.author_id,
                    "name": series.primary_author.name,
                    "slug": series.primary_author.slug,
                    "photo_url": series.primary_author.photo_url or None,
                } if series.HasField("primary_author") else None,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "getting series", e)
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

    **Rating Filter (`rating_filter`):**
    When provided, only returns comments from users who rated the book with one of the given values.
    Accepts half-star increments from 1.0 to 5.0. Repeat the param to filter multiple ratings.
    Omit to return all comments regardless of rating.

    **Examples:**
    - `/api/v1/books/the-hobbit/comments?sort_by=overall_rating&order=desc`
    - `/api/v1/books/the-hobbit/comments?include_spoilers=true&limit=20`
    - `/api/v1/books/the-hobbit/comments?rating_filter=5.0`
    - `/api/v1/books/the-hobbit/comments?rating_filter=4.0&rating_filter=4.5&rating_filter=5.0`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_book_comments(
    request: fastapi.Request,
    slug: str = fastapi.Path(..., description="Book slug"),
    limit: int = fastapi.Query(10, ge=1, le=100, description="Number of comments per page"),
    offset: int = fastapi.Query(0, ge=0, description="Pagination offset"),
    order: str = fastapi.Query("desc", regex="^(asc|desc)$", description="Sort order"),
    include_spoilers: bool = fastapi.Query(False, description="Include spoiler comments"),
    sort_by: str = fastapi.Query(
        "created_at",
        regex="^(created_at|overall_rating|pacing|emotional_impact|intellectual_depth|writing_quality|rereadability|readability|plot_complexity|humor)$",
        description="Sort field",
    ),
    rating_filter: typing.Optional[typing.List[float]] = fastapi.Query(
        None,
        ge=0.0,
        le=5.0,
        description="Filter by overall rating(s) (e.g. 5.0, 4.5). Repeat param to filter multiple ratings.",
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
            rating_filters=rating_filter or [],
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
        app.utils.responses.log_grpc_error(logger, "getting book comments", e)
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
    slug: str = fastapi.Path(..., description="Series slug"),
    limit: int = fastapi.Query(10, ge=1, le=100, description="Number of books per page"),
    offset: int = fastapi.Query(0, ge=0, description="Pagination offset"),
    language: str = fastapi.Depends(app.utils.language.resolve_language),
    sort_by: str = fastapi.Query(
        "series_position",
        regex="^(series_position|publication_year|combined_rating|readers_count)$",
        description="Sort field",
    ),
    order: str = fastapi.Query("asc", regex="^(asc|desc)$", description="Sort order"),
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
            books.append(_book_summary_proto_to_dict(book))

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
        app.utils.responses.log_grpc_error(logger, "getting series books", e)
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Get series books failed: {e.details()}",
        )


def _book_detail_proto_to_dict(book) -> typing.Dict[str, typing.Any]:
    return {
        "book_id": book.book_id,
        "work_id": book.work_id,
        "title": book.title,
        "slug": book.slug,
        "description": book.description,
        "language": book.language,
        "original_publication_year": book.original_publication_year,
        "formats": list(book.formats),
        "primary_cover_url": book.primary_cover_url,
        "rating_count": book.rating_count,
        "avg_rating": book.avg_rating,
        "sub_rating_stats": {
            key: {"avg": float(stat.avg) if stat.avg else 0.0, "count": stat.count}
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
            float(book.series_position) if book.series_position else None
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
        "ol_avg_rating": float(book.ol_avg_rating) if book.ol_avg_rating else 0.0,
        "ol_want_to_read_count": book.ol_want_to_read_count,
        "ol_currently_reading_count": book.ol_currently_reading_count,
        "ol_already_read_count": book.ol_already_read_count,
        "first_sentence": book.first_sentence or None,
        "app_want_to_read_count": book.app_want_to_read_count,
        "app_reading_count": book.app_reading_count,
        "app_read_count": book.app_read_count,
        "rating_distribution": {
            v: dict(book.rating_distribution).get(v, 0)
            for v in ["1.0", "1.5", "2.0", "2.5", "3.0", "3.5", "4.0", "4.5", "5.0"]
        },
    }


def _book_summary_proto_to_dict(item) -> typing.Dict[str, typing.Any]:
    return {
        "book_id": item.book_id,
        "work_id": item.work_id,
        "language": item.language or None,
        "title": item.title,
        "slug": item.slug,
        "description": item.description or None,
        "original_publication_year": (
            item.original_publication_year if item.original_publication_year else None
        ),
        "primary_cover_url": item.primary_cover_url or None,
        "authors": [
            {
                "author_id": a.author_id,
                "name": a.name,
                "slug": a.slug,
                "photo_url": a.photo_url or None,
            }
            for a in item.authors
        ],
        "rating_count": item.rating_count,
        "avg_rating": float(item.avg_rating) if item.avg_rating else 0.0,
        "ol_rating_count": item.ol_rating_count,
        "ol_avg_rating": float(item.ol_avg_rating) if item.ol_avg_rating else 0.0,
        "ol_want_to_read_count": item.ol_want_to_read_count,
        "ol_currently_reading_count": item.ol_currently_reading_count,
        "ol_already_read_count": item.ol_already_read_count,
        "app_want_to_read_count": item.app_want_to_read_count,
        "app_reading_count": item.app_reading_count,
        "app_read_count": item.app_read_count,
        "series_position": (
            float(item.series_position) if item.series_position else None
        ),
        "rarity": item.rarity or None,
    }


@router.get(
    "/case/open",
    response_model=app.models.books_responses.OpenCaseResponse,
    summary="Open a book case",
    description="""
    Open a randomized book case. Returns the winning book with full details.

    Only books with at least one rating (app or OpenLibrary) are eligible.

    **Combined rating formula:**
    `(avg_rating * rating_count + ol_avg_rating * ol_rating_count) / (rating_count + ol_rating_count)`

    **Rarity tiers** (based on combined weighted rating):
    | Rarity | Rating range | Probability |
    |---|---|---|
    | `legendary` | >4.75 | ~1.5% |
    | `ultra_rare` | >4.50 — <=4.75 | ~3.5% |
    | `super_rare` | >4.00 — <=4.50 | ~10% |
    | `rare` | >3.25 — <=4.00 | ~20% |
    | `uncommon` | >2.25 — <=3.25 | ~30% |
    | `common` | <=2.25 | ~35% |

    **Fallback:** if the rolled rarity tier has no eligible books for the requested language,
    the service cascades to the closest adjacent tiers until a winner is found.

    Returns `404` when no rated books exist for the given language.
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def open_case(
    request: fastapi.Request,
    language: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        response = await app.grpc_clients.books_client.open_case(language=language)

        return {
            "success": True,
            "data": {
                "winner": _book_summary_proto_to_dict(response.winner),
            },
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "opening case", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"No eligible books found for language '{language}'",
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Open case failed: {e.details()}",
        )


@router.get(
    "/pack/open",
    response_model=app.models.books_responses.OpenPackResponse,
    summary="Open a book pack",
    description="""
    Open a randomized book pack. Returns a list of `length` book cards (default 8),
    each with a rarity tier assigned. At least one card is guaranteed to be
    `super_rare` or higher.

    Rarity tiers and probabilities match case opening:
    | Rarity | Rating range | Probability |
    |---|---|---|
    | `legendary` | >4.75 | ~1.5% |
    | `ultra_rare` | >4.50 — <=4.75 | ~3.5% |
    | `super_rare` | >4.00 — <=4.50 | ~10% |
    | `rare` | >3.25 — <=4.00 | ~20% |
    | `uncommon` | >2.25 — <=3.25 | ~30% |
    | `common` | <=2.25 | ~35% |

    If no card rolls `super_rare` or higher naturally, the lowest-rarity card
    is replaced with a re-rolled `super_rare+` card.

    Returns `404` when no rated books exist for the given language.
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def open_pack(
    request: fastapi.Request,
    language: str = fastapi.Depends(app.utils.language.resolve_language),
    length: int = fastapi.Query(8, ge=1, le=25, description="Number of cards in the pack"),
):
    try:
        response = await app.grpc_clients.books_client.open_pack(
            language=language, length=length
        )

        return {
            "success": True,
            "data": {
                "items": [_book_summary_proto_to_dict(item) for item in response.items],
            },
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "opening pack", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"No eligible books found for language '{language}'",
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Open pack failed: {e.details()}",
        )


@router.get(
    "/slots/spin",
    response_model=app.models.books_responses.SpinSlotsResponse,
    summary="Spin the books slot machine",
    description="""
    Spin a 3-reel slot machine to win a book. Returns the 3 drawn rarity tiers and the
    winning book. The winner's rarity tier will exactly match the lowest rarity tier
    among the 3 drawn symbols, satisfying the rule that "the lowest tier wins".
    
    The API manages the actual drop rate probabilities similarly to case opening
    and builds the reels to simulate the outcome.

    Rarity tiers and probabilities match case opening:
    | Rarity | Rating range | Probability |
    |---|---|---|
    | `legendary` | >4.75 | ~1.5% |
    | `ultra_rare` | >4.50 — <=4.75 | ~3.5% |
    | `super_rare` | >4.00 — <=4.50 | ~10% |
    | `rare` | >3.25 — <=4.00 | ~20% |
    | `uncommon` | >2.25 — <=3.25 | ~30% |
    | `common` | <=2.25 | ~35% |

    Returns `404` when no rated books exist for the given language.
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def spin_slots(
    request: fastapi.Request,
    language: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        response = await app.grpc_clients.books_client.spin_slots(language=language)

        return {
            "success": True,
            "data": {
                "items": list(response.items),
                "winner": _book_summary_proto_to_dict(response.winner),
            },
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "spinning slots", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"No eligible books found for language '{language}'",
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Spin slots failed: {e.details()}",
        )


@router.post(
    "/discover",
    response_model=app.models.books_responses.DiscoverBookResponse,
    summary="Discover a random book matching filters",
    description="""
    Returns a single random book that matches the provided filter criteria.

    All filters are optional — omitting all filters returns any random book
    that has a cover image.

    Send previously returned `exclude_ids` to avoid getting the same book twice.
    The response includes `matching_count` so you can show "X books match" and
    warn when filters become too narrow.

    **Filter options:**

    | Filter | Values | Description |
    |---|---|---|
    | `language` | `en`, `pl`, … | Language of the book (default: `en`) |
    | `genre_slugs` | `["fantasy", "sci-fi"]` | Books belonging to any of these genres |
    | `book_length` | `short` / `medium` / `long` / `epic` | <200 / 200-400 / 400-600 / 600+ pages |
    | `quality` | `high` / `medium` / `low` / `very_low` | Combined rating >4.0 / 3.0-4.0 / 2.0-3.0 / ≤2.0 |
    | `moods` | see below | Sub-rating dimension filters (ANDed) |
    | `era` | `classic` / `modern` / `contemporary` | Published before 1950 / 1950-2000 / 2000+ |
    | `series_filter` | `standalone` / `series` | Not in a series / part of a series |
    | `popularity` | `popular` / `hidden_gem` | >100 readers / <50 readers with rating >3.5 |
    | `exclude_ids` | `[1, 2, 3]` (max 500) | Book IDs to exclude |

    **Mood values** (based on user sub-ratings, requires avg ≥ 3.5 from at least 3 ratings):
    `funny`, `emotional`, `intellectual`, `easy_read`, `complex`, `fast_paced`

    **Combined rating formula:**
    `(avg_rating * rating_count + ol_avg_rating * ol_rating_count) / (rating_count + ol_rating_count)`

    Returns `data: null` with error code `NO_MATCHING_BOOKS` when no books match the filters.
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def discover_book(
    request: fastapi.Request,
    filters: app.models.books_responses.DiscoverBookFilters,
    language: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        response = await app.grpc_clients.books_client.discover_book(
            language=filters.language or language,
            genre_slugs=filters.genre_slugs,
            book_length=filters.book_length or "",
            quality=filters.quality or "",
            moods=filters.moods,
            era=filters.era or "",
            series_filter=filters.series_filter or "",
            popularity=filters.popularity or "",
            exclude_ids=filters.exclude_ids,
        )

        return {
            "success": True,
            "data": {
                "book": _book_summary_proto_to_dict(response.book),
                "matching_count": response.matching_count,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "discovering book", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return {
                "success": True,
                "data": None,
                "error": {
                    "code": "NO_MATCHING_BOOKS",
                    "message": "No books match the provided filters. Try relaxing some criteria.",
                    "details": {},
                },
            }
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Discover book failed: {e.details()}",
        )


@router.get(
    "/genres/{slug}/bubble",
    summary="Get genres that co-occur with a given genre",
    description="""
    Returns genres that frequently appear together with the requested genre across books.

    Results are ordered by co-occurrence strength (Jaccard coefficient).
    Useful for building genre exploration bubbles / related-genre UI.

    **Example:** `/api/v1/genres/science-fiction/bubble?limit=8`
    """,
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_genre_bubble(
    request: fastapi.Request,
    slug: str = fastapi.Path(..., description="Genre slug"),
    limit: int = fastapi.Query(10, ge=1, le=50, description="Max related genres to return"),
):
    try:
        response = await app.grpc_clients.books_client.get_genre_bubble(
            slug=slug,
            limit=limit,
        )

        source = {
            "genre_id": response.source.genre_id,
            "name": response.source.name,
            "slug": response.source.slug,
        }
        related = [
            {
                "genre_id": r.genre.genre_id,
                "name": r.genre.name,
                "slug": r.genre.slug,
                "co_occurrence_count": r.co_occurrence_count,
                "strength": r.strength,
            }
            for r in response.related
        ]

        return {
            "success": True,
            "data": {
                "source": source,
                "related": related,
            },
            "error": None,
        }
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "getting genre bubble", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"Genre '{slug}' not found",
            )
        raise fastapi.HTTPException(
            status_code=500 if e.code() == grpc.StatusCode.INTERNAL else 400,
            detail=f"Genre bubble failed: {e.details()}",
        )
