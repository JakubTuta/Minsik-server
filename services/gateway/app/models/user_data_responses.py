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
    created_at: str
    updated_at: str


class CommentSchema(pydantic.BaseModel):
    comment_id: int
    user_id: int
    book_id: int
    book_slug: str
    body: str
    is_spoiler: bool
    created_at: str
    updated_at: str


class NoteSchema(pydantic.BaseModel):
    note_id: int
    user_id: int
    book_id: int
    book_slug: str
    note_text: str
    page_number: typing.Optional[int] = None
    is_spoiler: bool
    created_at: str
    updated_at: str


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


class NoteData(pydantic.BaseModel):
    note: NoteSchema


class NoteListData(pydantic.BaseModel):
    items: typing.List[NoteSchema]
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


class NoteResponse(pydantic.BaseModel):
    success: bool = True
    data: NoteData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class NoteListResponse(pydantic.BaseModel):
    success: bool = True
    data: NoteListData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class UpsertBookshelfRequest(pydantic.BaseModel):
    status: typing.Literal["want_to_read", "reading", "read", "abandoned"]

    model_config = pydantic.ConfigDict(
        json_schema_extra={"example": {"status": "reading"}}
    )


class UpsertRatingRequest(pydantic.BaseModel):
    overall_rating: float = pydantic.Field(ge=1.0, le=5.0)
    review_text: typing.Optional[str] = pydantic.Field(default=None, max_length=5000)
    pacing: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0)
    emotional_impact: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0)
    intellectual_depth: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0)
    writing_quality: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0)
    rereadability: typing.Optional[float] = pydantic.Field(default=None, ge=1.0, le=5.0)

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "overall_rating": 4.5,
                "review_text": "A wonderful read!",
                "pacing": 4.0,
                "writing_quality": 5.0
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


class CreateNoteRequest(pydantic.BaseModel):
    note_text: str = pydantic.Field(min_length=1, max_length=10000)
    page_number: typing.Optional[int] = pydantic.Field(default=None, ge=1)
    is_spoiler: bool = False

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "note_text": "Important quote here.",
                "page_number": 42,
                "is_spoiler": False
            }
        }
    )


class UpdateNoteRequest(pydantic.BaseModel):
    note_text: str = pydantic.Field(min_length=1, max_length=10000)
    page_number: typing.Optional[int] = pydantic.Field(default=None, ge=1)
    is_spoiler: bool = False

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "note_text": "Updated note text.",
                "page_number": 55,
                "is_spoiler": False
            }
        }
    )
