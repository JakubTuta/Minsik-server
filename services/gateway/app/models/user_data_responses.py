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


class ProfileStatsSchema(pydantic.BaseModel):
    want_to_read_count: int = 0
    reading_count: int = 0
    read_count: int = 0
    abandoned_count: int = 0
    favourites_count: int = 0
    ratings_count: int = 0
    comments_count: int = 0


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
    overall_rating: float = pydantic.Field(ge=1.0, le=5.0)
    review_text: typing.Optional[str] = pydantic.Field(default=None, max_length=5000)
    pacing: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0, description="1: slow, deliberate / 5: fast, action-packed")
    emotional_impact: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0, description="1: leaves no impression / 5: deeply moving")
    intellectual_depth: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0, description="1: shallow, surface-level / 5: profound, thought-provoking")
    writing_quality: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0, description="1: poorly written / 5: masterfully crafted prose")
    rereadability: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0, description="1: no desire to revisit / 5: would gladly reread")
    readability: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0, description="1: dense, challenging / 5: light, easy read")
    plot_complexity: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0, description="1: simple, straightforward / 5: complex, multi-layered")
    humor: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0, description="1: serious, no humor / 5: very funny, comedic")

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
