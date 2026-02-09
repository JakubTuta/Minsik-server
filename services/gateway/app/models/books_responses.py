import typing
import pydantic
import app.models.responses


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


class SearchResultsData(pydantic.BaseModel):
    results: typing.List[SearchResultSchema]
    total_count: int
    limit: int
    offset: int


class SearchResponse(pydantic.BaseModel):
    success: bool = True
    data: SearchResultsData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


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
