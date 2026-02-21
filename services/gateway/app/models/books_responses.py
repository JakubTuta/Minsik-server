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


class CoverHistorySchema(pydantic.BaseModel):
    url: str
    width: int
    size: str


class SearchResultSchema(pydantic.BaseModel):
    type: str
    id: int
    title: str
    slug: str
    cover_url: typing.Optional[str] = None
    authors: typing.List[str]
    relevance_score: float
    view_count: int
    author_slugs: typing.List[str]
    series_slug: typing.Optional[str] = None
    avg_rating: typing.Optional[str] = None
    rating_count: int = 0
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
    avg: typing.Optional[str] = pydantic.Field(
        default=None,
        description="Average score as string (e.g. '3.50'), '0' when no ratings",
    )
    count: int = pydantic.Field(
        default=0, description="Number of ratings for this dimension"
    )


class BookDetailData(pydantic.BaseModel):
    book_id: int
    title: str
    slug: str
    description: typing.Optional[str] = None
    language: str
    original_publication_year: typing.Optional[int] = None
    formats: typing.List[str]
    primary_cover_url: typing.Optional[str] = None
    cover_history: typing.List[CoverHistorySchema]
    rating_count: int
    avg_rating: float
    sub_rating_stats: typing.Dict[str, SubRatingStatSchema] = {}
    view_count: int
    last_viewed_at: typing.Optional[str] = None
    authors: typing.List[AuthorMinimalSchema]
    genres: typing.List[GenreSchema]
    series: typing.Optional[SeriesMinimalSchema] = None
    series_position: typing.Optional[str] = None
    open_library_id: typing.Optional[str] = None
    google_books_id: typing.Optional[str] = None
    created_at: str
    updated_at: str
    isbn: typing.List[str] = []
    publisher: typing.Optional[str] = None
    number_of_pages: int = 0
    external_ids: typing.Dict[str, str] = {}
    ol_rating_count: int = 0
    ol_avg_rating: typing.Optional[str] = None
    ol_want_to_read_count: int = 0
    ol_currently_reading_count: int = 0
    ol_already_read_count: int = 0


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
    books_avg_rating: float
    books_total_ratings: int
    books_total_views: int
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


class BookListItemSchema(pydantic.BaseModel):
    book_id: int
    title: str
    slug: str
    description: typing.Optional[str] = None
    original_publication_year: typing.Optional[int] = None
    primary_cover_url: typing.Optional[str] = None
    rating_count: int
    avg_rating: float
    view_count: int
    genres: typing.List[GenreSchema]


class AuthorBooksData(pydantic.BaseModel):
    books: typing.List[BookListItemSchema]
    total_count: int
    limit: int
    offset: int


class AuthorBooksResponse(pydantic.BaseModel):
    success: bool = True
    data: AuthorBooksData
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
    avg_rating: typing.Optional[str] = None
    rating_count: int = 0
    ol_avg_rating: typing.Optional[str] = None
    ol_rating_count: int = 0
    total_views: int = 0


class SeriesDetailResponse(pydantic.BaseModel):
    success: bool = True
    data: SeriesDetailData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class SeriesBookListItemSchema(pydantic.BaseModel):
    book_id: int
    title: str
    slug: str
    description: typing.Optional[str] = None
    original_publication_year: typing.Optional[int] = None
    primary_cover_url: typing.Optional[str] = None
    rating_count: int
    avg_rating: float
    view_count: int
    series_position: typing.Optional[str] = None
    genres: typing.List[GenreSchema]


class SeriesBooksData(pydantic.BaseModel):
    books: typing.List[SeriesBookListItemSchema]
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
