import typing

import app.models.responses
import pydantic


class GenreSchema(pydantic.BaseModel):
    genre_id: int
    name: str
    slug: str


class AuthorMinimalSchema(pydantic.BaseModel):
    author_id: int
    name: str
    slug: str
    photo_url: typing.Optional[str] = None


class SeriesMinimalSchema(pydantic.BaseModel):
    series_id: int
    name: str
    slug: str
    total_books: typing.Optional[int] = None


class SearchResultSchema(pydantic.BaseModel):
    type: str
    id: int
    title: str
    slug: str
    cover_url: typing.Optional[str] = None
    authors: typing.List[str]
    relevance_score: float
    author_slugs: typing.List[str]
    series_slug: typing.Optional[str] = None
    app_avg_rating: float = 0.0
    app_rating_count: int = 0
    ol_avg_rating: float = 0.0
    ol_rating_count: int = 0
    book_count: int = 0


class SearchResultsData(pydantic.BaseModel):
    results: typing.List[SearchResultSchema]
    total_count: int
    limit: int
    offset: int


class SearchResponse(pydantic.BaseModel):
    success: bool = True
    data: SearchResultsData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class SubRatingStatSchema(pydantic.BaseModel):
    avg: float = 0.0
    count: int = pydantic.Field(
        default=0, description="Number of ratings for this dimension"
    )


class BookDetailData(pydantic.BaseModel):
    book_id: int
    title: str
    slug: str
    description: typing.Optional[str] = None
    first_sentence: typing.Optional[str] = None
    language: str
    original_publication_year: typing.Optional[int] = None
    formats: typing.List[str]
    primary_cover_url: typing.Optional[str] = None
    rating_count: int
    avg_rating: float = 0.0
    sub_rating_stats: typing.Dict[str, SubRatingStatSchema] = {}
    view_count: int
    last_viewed_at: typing.Optional[str] = None
    authors: typing.List[AuthorMinimalSchema]
    genres: typing.List[GenreSchema]
    series: typing.Optional[SeriesMinimalSchema] = None
    series_position: typing.Optional[float] = None
    open_library_id: typing.Optional[str] = None
    google_books_id: typing.Optional[str] = None
    created_at: str
    updated_at: str
    isbn: typing.List[str] = []
    publisher: typing.Optional[str] = None
    number_of_pages: int = 0
    external_ids: typing.Dict[str, str] = {}
    ol_rating_count: int = 0
    ol_avg_rating: float = 0.0
    ol_want_to_read_count: int = 0
    ol_currently_reading_count: int = 0
    ol_already_read_count: int = 0
    app_want_to_read_count: int = 0
    app_reading_count: int = 0
    app_read_count: int = 0
    rating_distribution: typing.Dict[str, int] = {}


class BookDetailResponse(pydantic.BaseModel):
    success: bool = True
    data: BookDetailData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class AuthorDetailData(pydantic.BaseModel):
    author_id: int
    name: str
    slug: str
    bio: typing.Optional[str] = None
    birth_date: typing.Optional[str] = None
    death_date: typing.Optional[str] = None
    birth_place: typing.Optional[str] = None
    nationality: typing.Optional[str] = None
    photo_url: typing.Optional[str] = None
    view_count: int
    last_viewed_at: typing.Optional[str] = None
    books_count: int
    book_categories: typing.List[str] = []
    books_avg_rating: float = 0.0
    books_total_ratings: int
    books_ol_avg_rating: float = 0.0
    books_ol_total_ratings: int = 0
    app_want_to_read_count: int = 0
    app_reading_count: int = 0
    app_read_count: int = 0
    ol_want_to_read_count: int = 0
    ol_currently_reading_count: int = 0
    ol_already_read_count: int = 0
    open_library_id: typing.Optional[str] = None
    created_at: str
    updated_at: str
    wikidata_id: typing.Optional[str] = None
    wikipedia_url: typing.Optional[str] = None
    remote_ids: typing.Dict[str, str] = {}
    alternate_names: typing.List[str] = []


class AuthorDetailResponse(pydantic.BaseModel):
    success: bool = True
    data: AuthorDetailData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class BookSummarySchema(pydantic.BaseModel):
    book_id: int
    title: str
    slug: str
    description: typing.Optional[str] = None
    original_publication_year: typing.Optional[int] = None
    primary_cover_url: typing.Optional[str] = None
    authors: typing.List[AuthorMinimalSchema] = []
    rating_count: int = 0
    avg_rating: float = 0.0
    ol_rating_count: int = 0
    ol_avg_rating: float = 0.0
    ol_want_to_read_count: int = 0
    ol_currently_reading_count: int = 0
    ol_already_read_count: int = 0
    app_want_to_read_count: int = 0
    app_reading_count: int = 0
    app_read_count: int = 0
    series_position: typing.Optional[float] = None
    rarity: typing.Optional[str] = None


class AuthorBooksData(pydantic.BaseModel):
    books: typing.List[BookSummarySchema]
    total_count: int
    limit: int
    offset: int


class AuthorBooksResponse(pydantic.BaseModel):
    success: bool = True
    data: AuthorBooksData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class CategorySchema(pydantic.BaseModel):
    slug: str
    name: str


class ListCategoriesData(pydantic.BaseModel):
    categories: typing.List[CategorySchema]


class ListCategoriesResponse(pydantic.BaseModel):
    success: bool
    data: ListCategoriesData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class CategoryResponse(pydantic.BaseModel):
    success: bool
    data: CategorySchema
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class CategoryBooksData(pydantic.BaseModel):
    books: typing.List[BookSummarySchema]
    total_count: int


class CategoryBooksResponse(pydantic.BaseModel):
    success: bool
    data: CategoryBooksData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class SeriesDetailData(pydantic.BaseModel):
    series_id: int
    name: str
    slug: str
    description: typing.Optional[str] = None
    total_books: typing.Optional[int] = None
    view_count: int
    last_viewed_at: typing.Optional[str] = None
    created_at: str
    updated_at: str
    avg_rating: float = 0.0
    rating_count: int = 0
    ol_avg_rating: float = 0.0
    ol_rating_count: int = 0
    app_want_to_read_count: int = 0
    app_reading_count: int = 0
    app_read_count: int = 0
    ol_want_to_read_count: int = 0
    ol_currently_reading_count: int = 0
    ol_already_read_count: int = 0


class SeriesDetailResponse(pydantic.BaseModel):
    success: bool = True
    data: SeriesDetailData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class SeriesBooksData(pydantic.BaseModel):
    books: typing.List[BookSummarySchema]
    total_count: int
    limit: int
    offset: int


class SeriesBooksResponse(pydantic.BaseModel):
    success: bool = True
    data: SeriesBooksData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class RatingDataSchema(pydantic.BaseModel):
    overall_rating: float
    review_text: typing.Optional[str] = None
    pacing: typing.Optional[float] = None
    emotional_impact: typing.Optional[float] = None
    intellectual_depth: typing.Optional[float] = None
    writing_quality: typing.Optional[float] = None
    rereadability: typing.Optional[float] = None
    readability: typing.Optional[float] = None
    plot_complexity: typing.Optional[float] = None
    humor: typing.Optional[float] = None


class BookCommentWithRatingSchema(pydantic.BaseModel):
    comment_id: int
    user_id: int
    username: str
    book_id: int
    book_slug: str
    body: str
    is_spoiler: bool
    comment_created_at: str
    comment_updated_at: str
    rating: typing.Optional[RatingDataSchema] = None


class BookCommentsListData(pydantic.BaseModel):
    items: typing.List[BookCommentWithRatingSchema]
    total_count: int
    limit: int
    offset: int
    my_entry: typing.Optional[BookCommentWithRatingSchema] = None


class BookCommentsResponse(pydantic.BaseModel):
    success: bool = True
    data: BookCommentsListData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class AdminUpdateBookRequest(pydantic.BaseModel):
    title: typing.Optional[str] = pydantic.Field(None, description="Book title")
    slug: typing.Optional[str] = pydantic.Field(
        None, description="URL slug — must be unique per language edition"
    )
    description: typing.Optional[str] = pydantic.Field(
        None, description="Book synopsis / description"
    )
    first_sentence: typing.Optional[str] = pydantic.Field(
        None, description="Opening sentence of the book"
    )
    language: typing.Optional[str] = pydantic.Field(
        None, description="ISO language code (e.g. 'en', 'pl', 'de')"
    )
    original_publication_year: typing.Optional[int] = pydantic.Field(
        None, description="Year the book was first published"
    )
    primary_cover_url: typing.Optional[str] = pydantic.Field(
        None, description="URL of the primary cover image"
    )
    formats: typing.Optional[typing.List[str]] = pydantic.Field(
        None, description="Available formats, e.g. ['ebook', 'paperback', 'hardcover']"
    )
    isbn: typing.Optional[typing.List[str]] = pydantic.Field(
        None, description="ISBN-10 or ISBN-13 identifiers"
    )
    publisher: typing.Optional[str] = pydantic.Field(None, description="Publisher name")
    number_of_pages: typing.Optional[int] = pydantic.Field(
        None, description="Total page count"
    )
    external_ids: typing.Optional[typing.Dict[str, str]] = pydantic.Field(
        None,
        description="Map of arbitrary external identifiers (e.g. {'goodreads': '123'})",
    )
    open_library_id: typing.Optional[str] = pydantic.Field(
        None, description="Open Library work ID (e.g. 'OL27448W')"
    )
    google_books_id: typing.Optional[str] = pydantic.Field(
        None, description="Google Books volume ID"
    )
    series_id: typing.Optional[int] = pydantic.Field(
        None,
        description="ID of the series this book belongs to; set to null to remove the book from its series",
    )
    series_position: typing.Optional[float] = pydantic.Field(
        None, description="Position within the series (e.g. 1, 2.5)"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "title": "The Fellowship of the Ring",
                "slug": "the-fellowship-of-the-ring",
                "language": "en",
                "original_publication_year": 1954,
                "number_of_pages": 423,
                "series_id": 12,
                "series_position": 1,
            }
        }
    )


class AdminUpdateAuthorRequest(pydantic.BaseModel):
    name: typing.Optional[str] = pydantic.Field(None, description="Author's full name")
    slug: typing.Optional[str] = pydantic.Field(
        None, description="URL slug — must be unique"
    )
    bio: typing.Optional[str] = pydantic.Field(None, description="Author biography")
    birth_date: typing.Optional[str] = pydantic.Field(
        None, description="Date of birth in ISO format (YYYY-MM-DD)"
    )
    death_date: typing.Optional[str] = pydantic.Field(
        None, description="Date of death in ISO format (YYYY-MM-DD)"
    )
    birth_place: typing.Optional[str] = pydantic.Field(
        None, description="City or country of birth"
    )
    nationality: typing.Optional[str] = pydantic.Field(
        None, description="Author's nationality"
    )
    photo_url: typing.Optional[str] = pydantic.Field(
        None, description="URL of the author's photo"
    )
    wikidata_id: typing.Optional[str] = pydantic.Field(
        None, description="Wikidata entity ID (e.g. 'Q892')"
    )
    wikipedia_url: typing.Optional[str] = pydantic.Field(
        None, description="Full Wikipedia article URL"
    )
    remote_ids: typing.Optional[typing.Dict[str, str]] = pydantic.Field(
        None, description="Map of external IDs (e.g. {'goodreads': '656983'})"
    )
    alternate_names: typing.Optional[typing.List[str]] = pydantic.Field(
        None, description="List of alternate names or pen names"
    )
    open_library_id: typing.Optional[str] = pydantic.Field(
        None, description="Open Library author ID (e.g. 'OL26320A')"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "name": "J.R.R. Tolkien",
                "bio": "John Ronald Reuel Tolkien was an English author and philologist.",
                "birth_date": "1892-01-03",
                "death_date": "1973-09-02",
                "nationality": "British",
            }
        }
    )


class AdminUpdateSeriesRequest(pydantic.BaseModel):
    name: typing.Optional[str] = pydantic.Field(None, description="Series name")
    slug: typing.Optional[str] = pydantic.Field(
        None, description="URL slug — must be unique"
    )
    description: typing.Optional[str] = pydantic.Field(
        None, description="Series description"
    )
    total_books: typing.Optional[int] = pydantic.Field(
        None, description="Total number of books planned for the series"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "name": "The Lord of the Rings",
                "description": "An epic high-fantasy novel set in Middle-earth.",
                "total_books": 3,
            }
        }
    )


class UpdateSeriesResponse(pydantic.BaseModel):
    success: bool = True
    data: typing.Optional[SeriesDetailData] = None
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class OpenCaseData(pydantic.BaseModel):
    winner: BookSummarySchema = pydantic.Field(description="The winning book item")


class OpenCaseResponse(pydantic.BaseModel):
    success: bool = True
    data: OpenCaseData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class OpenPackData(pydantic.BaseModel):
    items: typing.List[BookSummarySchema] = pydantic.Field(
        description="List of book cards in the pack, each with rarity assigned."
    )


class OpenPackResponse(pydantic.BaseModel):
    success: bool = True
    data: OpenPackData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class SpinSlotsData(pydantic.BaseModel):
    items: typing.List[str] = pydantic.Field(
        description="List of 3 rarity tiers for the slots reels. The lowest rarity matches the winner's rarity."
    )
    winner: BookSummarySchema = pydantic.Field(
        description="The winning book item corresponding to the lowest rarity from the reels."
    )


class SpinSlotsResponse(pydantic.BaseModel):
    success: bool = True
    data: SpinSlotsData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class DiscoverBookFilters(pydantic.BaseModel):
    language: str = pydantic.Field(
        default="en",
        min_length=2,
        max_length=10,
        description="Language code (e.g. en, pl, de). Default: en",
    )
    genre_slugs: typing.List[str] = pydantic.Field(
        default_factory=list,
        description="Filter by one or more genre slugs (e.g. ['fantasy', 'sci-fi']). Books matching any of the given genres are included.",
    )
    book_length: typing.Optional[str] = pydantic.Field(
        default=None,
        pattern="^(short|medium|long|epic)$",
        description="Filter by page count: short (<200 pages), medium (200-400), long (400-600), epic (600+)",
    )
    quality: typing.Optional[str] = pydantic.Field(
        default=None,
        pattern="^(high|medium|low|very_low)$",
        description="Filter by combined weighted rating: high (>4.0), medium (3.0-4.0), low (2.0-3.0), very_low (<=2.0). Combined rating = (avg_rating * rating_count + ol_avg_rating * ol_rating_count) / (rating_count + ol_rating_count)",
    )
    moods: typing.List[str] = pydantic.Field(
        default_factory=list,
        description=(
            "Filter by sub-rating dimensions (from user sub-ratings). Multiple moods are ANDed. "
            "Valid values: funny, emotional, intellectual, easy_read, complex, fast_paced. "
            "Only books with at least 3 sub-ratings for that dimension and avg >= 3.5 are included."
        ),
    )
    era: typing.Optional[str] = pydantic.Field(
        default=None,
        pattern="^(classic|modern|contemporary)$",
        description="Filter by original publication era: classic (before 1950), modern (1950-2000), contemporary (2000+)",
    )
    series_filter: typing.Optional[str] = pydantic.Field(
        default=None,
        pattern="^(standalone|series)$",
        description="standalone — only books not part of a series; series — only books that belong to a series; omit for any",
    )
    popularity: typing.Optional[str] = pydantic.Field(
        default=None,
        pattern="^(popular|hidden_gem)$",
        description="popular — books with more than 100 total readers; hidden_gem — fewer than 50 readers but combined rating > 3.5",
    )
    exclude_ids: typing.List[int] = pydantic.Field(
        default_factory=list,
        max_length=500,
        description="List of book_ids to exclude from results. Use to avoid repeating previously returned books.",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "language": "en",
                "genre_slugs": ["fantasy"],
                "book_length": "medium",
                "quality": "high",
                "moods": ["emotional"],
                "era": "contemporary",
                "series_filter": "standalone",
                "popularity": "hidden_gem",
                "exclude_ids": [101, 202, 303],
            }
        }
    )


class DiscoverBookData(pydantic.BaseModel):
    book: BookSummarySchema = pydantic.Field(
        description="Partial book data for the discovered book"
    )
    matching_count: int = pydantic.Field(
        description="Total number of books in the database that match the provided filters. Useful for showing 'X books found' and detecting when filters are too narrow."
    )


class DiscoverBookResponse(pydantic.BaseModel):
    success: bool = True
    data: typing.Optional[DiscoverBookData] = None
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class AdminBookUpdateData(pydantic.BaseModel):
    book_id: int
    title: str
    slug: str
    description: typing.Optional[str] = None
    first_sentence: typing.Optional[str] = None
    language: str
    original_publication_year: typing.Optional[int] = None
    primary_cover_url: typing.Optional[str] = None
    formats: typing.List[str] = []
    isbn: typing.List[str] = []
    publisher: typing.Optional[str] = None
    number_of_pages: int = 0
    external_ids: typing.Dict[str, str] = {}
    open_library_id: typing.Optional[str] = None
    google_books_id: typing.Optional[str] = None
    series: typing.Optional[SeriesMinimalSchema] = None
    series_position: typing.Optional[float] = None
    rating_count: int = 0
    avg_rating: float = 0.0
    ol_rating_count: int = 0
    ol_avg_rating: float = 0.0
    updated_at: str


class AdminBookUpdateResponse(pydantic.BaseModel):
    success: bool = True
    data: typing.Optional[AdminBookUpdateData] = None
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class AdminAuthorUpdateData(pydantic.BaseModel):
    author_id: int
    name: str
    slug: str
    bio: typing.Optional[str] = None
    birth_date: typing.Optional[str] = None
    death_date: typing.Optional[str] = None
    birth_place: typing.Optional[str] = None
    nationality: typing.Optional[str] = None
    photo_url: typing.Optional[str] = None
    wikidata_id: typing.Optional[str] = None
    wikipedia_url: typing.Optional[str] = None
    remote_ids: typing.Dict[str, str] = {}
    alternate_names: typing.List[str] = []
    open_library_id: typing.Optional[str] = None
    updated_at: str


class AdminAuthorUpdateResponse(pydantic.BaseModel):
    success: bool = True
    data: typing.Optional[AdminAuthorUpdateData] = None
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class AdminSeriesUpdateData(pydantic.BaseModel):
    series_id: int
    name: str
    slug: str
    description: typing.Optional[str] = None
    total_books: typing.Optional[int] = None
    avg_rating: float = 0.0
    rating_count: int = 0
    ol_avg_rating: float = 0.0
    ol_rating_count: int = 0
    updated_at: str


class AdminSeriesUpdateResponse(pydantic.BaseModel):
    success: bool = True
    data: typing.Optional[AdminSeriesUpdateData] = None
    error: typing.Optional[app.models.responses.ErrorDetail] = None
