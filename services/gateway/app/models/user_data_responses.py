import typing
import pydantic
import app.models.responses


class BookshelfSchema(pydantic.BaseModel):
    bookshelf_id: int
    user_id: int
    book_id: int
    book_slug: str
    book_title: str
    book_cover_url: str
    status: str
    is_favorite: bool
    created_at: str
    updated_at: str
    book_author_names: typing.List[str] = []
    book_author_slugs: typing.List[str] = []
    book_series_name: typing.Optional[str] = None
    book_series_slug: typing.Optional[str] = None


class RatingSchema(pydantic.BaseModel):
    rating_id: int
    user_id: int
    book_id: int
    book_slug: str
    book_title: str
    book_cover_url: str
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
    created_at: str
    updated_at: str
    book_author_names: typing.List[str] = []
    book_author_slugs: typing.List[str] = []
    book_series_name: typing.Optional[str] = None
    book_series_slug: typing.Optional[str] = None
    book_avg_rating: float = 0.0
    book_rating_count: int = 0


class CommentSchema(pydantic.BaseModel):
    comment_id: int
    user_id: int
    username: str
    book_id: int
    book_slug: str
    book_title: str = ""
    body: str
    is_spoiler: bool
    created_at: str
    updated_at: str
    book_cover_url: str = ""
    book_author_names: typing.List[str] = []
    book_author_slugs: typing.List[str] = []
    book_series_name: typing.Optional[str] = None
    book_series_slug: typing.Optional[str] = None


class FavouriteResponseData(pydantic.BaseModel):
    is_favorite: bool
    book_id: int
    book_slug: str


class BookshelfData(pydantic.BaseModel):
    bookshelf: BookshelfSchema


class BookshelfListData(pydantic.BaseModel):
    items: typing.List[BookshelfSchema]
    total_count: int
    limit: int
    offset: int


class RatingData(pydantic.BaseModel):
    rating: RatingSchema


class RatingListData(pydantic.BaseModel):
    items: typing.List[RatingSchema]
    total_count: int
    limit: int
    offset: int


class CommentData(pydantic.BaseModel):
    comment: CommentSchema


class CommentListData(pydantic.BaseModel):
    items: typing.List[CommentSchema]
    total_count: int
    limit: int
    offset: int


class BookshelfResponse(pydantic.BaseModel):
    success: bool = True
    data: BookshelfData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class BookshelfListResponse(pydantic.BaseModel):
    success: bool = True
    data: BookshelfListData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class RatingResponse(pydantic.BaseModel):
    success: bool = True
    data: RatingData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class RatingListResponse(pydantic.BaseModel):
    success: bool = True
    data: RatingListData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class FavouriteResponse(pydantic.BaseModel):
    success: bool = True
    data: FavouriteResponseData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class CommentResponse(pydantic.BaseModel):
    success: bool = True
    data: CommentData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class CommentListResponse(pydantic.BaseModel):
    success: bool = True
    data: CommentListData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class UserBookInfoData(pydantic.BaseModel):
    bookshelf: typing.Optional[BookshelfSchema] = None
    rating: typing.Optional[RatingSchema] = None
    comment: typing.Optional[CommentSchema] = None


class UserBookInfoResponse(pydantic.BaseModel):
    success: bool = True
    data: UserBookInfoData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class BookStatusSchema(pydantic.BaseModel):
    book_id: int
    status: str
    is_favorite: bool


class BookStatusesData(pydantic.BaseModel):
    statuses: typing.List[BookStatusSchema] = []


class BookStatusesResponse(pydantic.BaseModel):
    success: bool = True
    data: BookStatusesData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class BookStatusesRequest(pydantic.BaseModel):
    book_ids: typing.List[int] = pydantic.Field(min_length=1, max_length=200)

    model_config = pydantic.ConfigDict(
        json_schema_extra={"example": {"book_ids": [12, 34, 56]}}
    )


class ProfileStatsSchema(pydantic.BaseModel):
    want_to_read_count: int = 0
    reading_count: int = 0
    read_count: int = 0
    abandoned_count: int = 0
    favourites_count: int = 0
    ratings_count: int = 0
    comments_count: int = 0
    finished_this_year_count: int = 0
    pages_read_this_year: int = 0
    hours_read_this_year: int = 0
    bookshelf_updated_at: str = ""
    favourites_updated_at: str = ""
    comments_updated_at: str = ""
    ratings_updated_at: str = ""
    average_rating: float = 0.0
    rating_distribution: typing.Dict[str, int] = {}
    pages_read_total: int = 0
    reviews_count: int = 0


class OverviewBookSchema(pydantic.BaseModel):
    book_slug: str = ""
    book_title: str = ""
    book_cover_url: str = ""
    book_author_names: typing.List[str] = []
    book_author_slugs: typing.List[str] = []


class TopGenreSchema(pydantic.BaseModel):
    name: str
    slug: str
    count: int
    percent: float


class FavouriteAuthorSchema(pydantic.BaseModel):
    name: str
    slug: str
    count: int
    photo_url: str = ""


class PublicUserSchema(pydantic.BaseModel):
    user_id: int
    username: str
    display_name: str = ""
    avatar_url: str = ""
    bio: str = ""


class ProfileOverviewData(pydantic.BaseModel):
    user: PublicUserSchema
    reading_now: typing.Optional[OverviewBookSchema] = None
    top_genres: typing.List[TopGenreSchema] = []
    favourite_authors: typing.List[FavouriteAuthorSchema] = []
    favourites_this_year: typing.List[OverviewBookSchema] = []


class ProfileOverviewResponse(pydantic.BaseModel):
    success: bool = True
    data: ProfileOverviewData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class YearBookSchema(pydantic.BaseModel):
    book_slug: str = ""
    book_title: str = ""
    book_cover_url: str = ""
    author_names: typing.List[str] = []
    author_slugs: typing.List[str] = []
    number_of_pages: int = 0
    finished_at: str = ""
    my_rating: typing.Optional[float] = None


class MonthlyBucketSchema(pydantic.BaseModel):
    month: int
    books_finished: int = 0
    pages_read: int = 0
    ratings_given: int = 0
    books: typing.List[YearBookSchema] = []


class YearInReviewSchema(pydantic.BaseModel):
    year: int
    months_elapsed: int
    monthly: typing.List[MonthlyBucketSchema] = []
    total_books_finished: int = 0
    total_pages_read: int = 0
    total_hours_read: int = 0
    ratings_given: int = 0
    reviews_written: int = 0
    comments_written: int = 0
    favourites_added: int = 0
    average_rating_given: float = 0.0
    rating_distribution: typing.Dict[str, int] = {}
    top_genres: typing.List[TopGenreSchema] = []
    top_authors: typing.List[FavouriteAuthorSchema] = []
    longest_book: typing.Optional[YearBookSchema] = None
    shortest_book: typing.Optional[YearBookSchema] = None
    first_finished: typing.Optional[YearBookSchema] = None
    highest_rated: typing.Optional[YearBookSchema] = None
    average_pages_per_book: float = 0.0
    busiest_month: int = 0
    busiest_month_count: int = 0
    average_days_to_finish: float = 0.0
    currently_reading_count: int = 0
    added_to_shelf_count: int = 0
    finished_cover_urls: typing.List[str] = []


class YearInReviewData(pydantic.BaseModel):
    review: YearInReviewSchema


class YearInReviewResponse(pydantic.BaseModel):
    success: bool = True
    data: YearInReviewData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class ProfileStatsData(pydantic.BaseModel):
    stats: ProfileStatsSchema


class ProfileStatsResponse(pydantic.BaseModel):
    success: bool = True
    data: ProfileStatsData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class UpsertBookshelfRequest(pydantic.BaseModel):
    status: typing.Literal["want_to_read", "reading", "read", "abandoned"]

    model_config = pydantic.ConfigDict(
        json_schema_extra={"example": {"status": "reading"}}
    )


class UpsertRatingRequest(pydantic.BaseModel):
    overall_rating: float = pydantic.Field(ge=0.5, le=5.0)
    review_text: typing.Optional[str] = pydantic.Field(default=None, max_length=5000)
    pacing: typing.Optional[float] = pydantic.Field(default=None, ge=0.5, le=5.0, description="1: slow, deliberate / 5: fast, action-packed")
    emotional_impact: typing.Optional[float] = pydantic.Field(default=None, ge=0.5, le=5.0, description="1: leaves no impression / 5: deeply moving")
    intellectual_depth: typing.Optional[float] = pydantic.Field(default=None, ge=0.5, le=5.0, description="1: shallow, surface-level / 5: profound, thought-provoking")
    writing_quality: typing.Optional[float] = pydantic.Field(default=None, ge=0.5, le=5.0, description="1: poorly written / 5: masterfully crafted prose")
    rereadability: typing.Optional[float] = pydantic.Field(default=None, ge=0.5, le=5.0, description="1: no desire to revisit / 5: would gladly reread")
    readability: typing.Optional[float] = pydantic.Field(default=None, ge=0.5, le=5.0, description="1: dense, challenging / 5: light, easy read")
    plot_complexity: typing.Optional[float] = pydantic.Field(default=None, ge=0.5, le=5.0, description="1: simple, straightforward / 5: complex, multi-layered")
    humor: typing.Optional[float] = pydantic.Field(default=None, ge=0.5, le=5.0, description="1: serious, no humor / 5: very funny, comedic")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "overall_rating": 4.5,
                "review_text": "A wonderful read!",
                "pacing": 4.0,
                "writing_quality": 5.0,
                "humor": 3.0
            }
        }
    )


class CreateCommentRequest(pydantic.BaseModel):
    body: str = pydantic.Field(min_length=1, max_length=5000)
    is_spoiler: bool = False

    model_config = pydantic.ConfigDict(
        json_schema_extra={"example": {"body": "Loved this book!", "is_spoiler": False}}
    )


class UpdateCommentRequest(pydantic.BaseModel):
    body: str = pydantic.Field(min_length=1, max_length=5000)
    is_spoiler: bool = False

    model_config = pydantic.ConfigDict(
        json_schema_extra={"example": {"body": "Updated review text.", "is_spoiler": False}}
    )
