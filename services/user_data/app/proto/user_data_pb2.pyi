from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetBookshelfRequest(_message.Message):
    __slots__ = ("user_id", "book_slug")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ...) -> None: ...

class UpsertBookshelfRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "status")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    status: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., status: _Optional[str] = ...) -> None: ...

class DeleteBookshelfRequest(_message.Message):
    __slots__ = ("user_id", "book_slug")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ...) -> None: ...

class GetUserBookshelvesRequest(_message.Message):
    __slots__ = ("user_id", "limit", "offset", "status_filter", "favourites_only", "sort_by", "order")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    STATUS_FILTER_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_ONLY_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    limit: int
    offset: int
    status_filter: str
    favourites_only: bool
    sort_by: str
    order: str
    def __init__(self, user_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., status_filter: _Optional[str] = ..., favourites_only: bool = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ...) -> None: ...

class GetPublicBookshelvesRequest(_message.Message):
    __slots__ = ("username", "limit", "offset", "status_filter", "favourites_only", "sort_by", "order")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    STATUS_FILTER_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_ONLY_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    username: str
    limit: int
    offset: int
    status_filter: str
    favourites_only: bool
    sort_by: str
    order: str
    def __init__(self, username: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., status_filter: _Optional[str] = ..., favourites_only: bool = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ...) -> None: ...

class Bookshelf(_message.Message):
    __slots__ = ("bookshelf_id", "user_id", "book_id", "book_slug", "book_title", "book_cover_url", "status", "is_favorite", "created_at", "updated_at", "book_author_names", "book_author_slugs", "book_series_name", "book_series_slug")
    BOOKSHELF_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    BOOK_TITLE_FIELD_NUMBER: _ClassVar[int]
    BOOK_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    IS_FAVORITE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    BOOK_AUTHOR_NAMES_FIELD_NUMBER: _ClassVar[int]
    BOOK_AUTHOR_SLUGS_FIELD_NUMBER: _ClassVar[int]
    BOOK_SERIES_NAME_FIELD_NUMBER: _ClassVar[int]
    BOOK_SERIES_SLUG_FIELD_NUMBER: _ClassVar[int]
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
    book_author_names: _containers.RepeatedScalarFieldContainer[str]
    book_author_slugs: _containers.RepeatedScalarFieldContainer[str]
    book_series_name: str
    book_series_slug: str
    def __init__(self, bookshelf_id: _Optional[int] = ..., user_id: _Optional[int] = ..., book_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., book_title: _Optional[str] = ..., book_cover_url: _Optional[str] = ..., status: _Optional[str] = ..., is_favorite: bool = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., book_author_names: _Optional[_Iterable[str]] = ..., book_author_slugs: _Optional[_Iterable[str]] = ..., book_series_name: _Optional[str] = ..., book_series_slug: _Optional[str] = ...) -> None: ...

class BookshelfResponse(_message.Message):
    __slots__ = ("bookshelf",)
    BOOKSHELF_FIELD_NUMBER: _ClassVar[int]
    bookshelf: Bookshelf
    def __init__(self, bookshelf: _Optional[_Union[Bookshelf, _Mapping]] = ...) -> None: ...

class BookshelvesListResponse(_message.Message):
    __slots__ = ("bookshelves", "total_count")
    BOOKSHELVES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    bookshelves: _containers.RepeatedCompositeFieldContainer[Bookshelf]
    total_count: int
    def __init__(self, bookshelves: _Optional[_Iterable[_Union[Bookshelf, _Mapping]]] = ..., total_count: _Optional[int] = ...) -> None: ...

class GetRatingRequest(_message.Message):
    __slots__ = ("user_id", "book_slug")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ...) -> None: ...

class UpsertRatingRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "overall_rating", "review_text", "pacing", "has_pacing", "emotional_impact", "has_emotional_impact", "intellectual_depth", "has_intellectual_depth", "writing_quality", "has_writing_quality", "rereadability", "has_rereadability", "readability", "has_readability", "plot_complexity", "has_plot_complexity", "humor", "has_humor")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    OVERALL_RATING_FIELD_NUMBER: _ClassVar[int]
    REVIEW_TEXT_FIELD_NUMBER: _ClassVar[int]
    PACING_FIELD_NUMBER: _ClassVar[int]
    HAS_PACING_FIELD_NUMBER: _ClassVar[int]
    EMOTIONAL_IMPACT_FIELD_NUMBER: _ClassVar[int]
    HAS_EMOTIONAL_IMPACT_FIELD_NUMBER: _ClassVar[int]
    INTELLECTUAL_DEPTH_FIELD_NUMBER: _ClassVar[int]
    HAS_INTELLECTUAL_DEPTH_FIELD_NUMBER: _ClassVar[int]
    WRITING_QUALITY_FIELD_NUMBER: _ClassVar[int]
    HAS_WRITING_QUALITY_FIELD_NUMBER: _ClassVar[int]
    REREADABILITY_FIELD_NUMBER: _ClassVar[int]
    HAS_REREADABILITY_FIELD_NUMBER: _ClassVar[int]
    READABILITY_FIELD_NUMBER: _ClassVar[int]
    HAS_READABILITY_FIELD_NUMBER: _ClassVar[int]
    PLOT_COMPLEXITY_FIELD_NUMBER: _ClassVar[int]
    HAS_PLOT_COMPLEXITY_FIELD_NUMBER: _ClassVar[int]
    HUMOR_FIELD_NUMBER: _ClassVar[int]
    HAS_HUMOR_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    overall_rating: float
    review_text: str
    pacing: float
    has_pacing: bool
    emotional_impact: float
    has_emotional_impact: bool
    intellectual_depth: float
    has_intellectual_depth: bool
    writing_quality: float
    has_writing_quality: bool
    rereadability: float
    has_rereadability: bool
    readability: float
    has_readability: bool
    plot_complexity: float
    has_plot_complexity: bool
    humor: float
    has_humor: bool
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., overall_rating: _Optional[float] = ..., review_text: _Optional[str] = ..., pacing: _Optional[float] = ..., has_pacing: bool = ..., emotional_impact: _Optional[float] = ..., has_emotional_impact: bool = ..., intellectual_depth: _Optional[float] = ..., has_intellectual_depth: bool = ..., writing_quality: _Optional[float] = ..., has_writing_quality: bool = ..., rereadability: _Optional[float] = ..., has_rereadability: bool = ..., readability: _Optional[float] = ..., has_readability: bool = ..., plot_complexity: _Optional[float] = ..., has_plot_complexity: bool = ..., humor: _Optional[float] = ..., has_humor: bool = ...) -> None: ...

class DeleteRatingRequest(_message.Message):
    __slots__ = ("user_id", "book_slug")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ...) -> None: ...

class GetUserRatingsRequest(_message.Message):
    __slots__ = ("user_id", "limit", "offset", "sort_by", "order", "min_rating", "max_rating")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    MIN_RATING_FIELD_NUMBER: _ClassVar[int]
    MAX_RATING_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    limit: int
    offset: int
    sort_by: str
    order: str
    min_rating: float
    max_rating: float
    def __init__(self, user_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ..., min_rating: _Optional[float] = ..., max_rating: _Optional[float] = ...) -> None: ...

class Rating(_message.Message):
    __slots__ = ("rating_id", "user_id", "book_id", "book_slug", "book_title", "book_cover_url", "overall_rating", "review_text", "pacing", "has_pacing", "emotional_impact", "has_emotional_impact", "intellectual_depth", "has_intellectual_depth", "writing_quality", "has_writing_quality", "rereadability", "has_rereadability", "readability", "has_readability", "plot_complexity", "has_plot_complexity", "humor", "has_humor", "created_at", "updated_at", "book_author_names", "book_author_slugs", "book_series_name", "book_series_slug")
    RATING_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    BOOK_TITLE_FIELD_NUMBER: _ClassVar[int]
    BOOK_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    OVERALL_RATING_FIELD_NUMBER: _ClassVar[int]
    REVIEW_TEXT_FIELD_NUMBER: _ClassVar[int]
    PACING_FIELD_NUMBER: _ClassVar[int]
    HAS_PACING_FIELD_NUMBER: _ClassVar[int]
    EMOTIONAL_IMPACT_FIELD_NUMBER: _ClassVar[int]
    HAS_EMOTIONAL_IMPACT_FIELD_NUMBER: _ClassVar[int]
    INTELLECTUAL_DEPTH_FIELD_NUMBER: _ClassVar[int]
    HAS_INTELLECTUAL_DEPTH_FIELD_NUMBER: _ClassVar[int]
    WRITING_QUALITY_FIELD_NUMBER: _ClassVar[int]
    HAS_WRITING_QUALITY_FIELD_NUMBER: _ClassVar[int]
    REREADABILITY_FIELD_NUMBER: _ClassVar[int]
    HAS_REREADABILITY_FIELD_NUMBER: _ClassVar[int]
    READABILITY_FIELD_NUMBER: _ClassVar[int]
    HAS_READABILITY_FIELD_NUMBER: _ClassVar[int]
    PLOT_COMPLEXITY_FIELD_NUMBER: _ClassVar[int]
    HAS_PLOT_COMPLEXITY_FIELD_NUMBER: _ClassVar[int]
    HUMOR_FIELD_NUMBER: _ClassVar[int]
    HAS_HUMOR_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    BOOK_AUTHOR_NAMES_FIELD_NUMBER: _ClassVar[int]
    BOOK_AUTHOR_SLUGS_FIELD_NUMBER: _ClassVar[int]
    BOOK_SERIES_NAME_FIELD_NUMBER: _ClassVar[int]
    BOOK_SERIES_SLUG_FIELD_NUMBER: _ClassVar[int]
    rating_id: int
    user_id: int
    book_id: int
    book_slug: str
    book_title: str
    book_cover_url: str
    overall_rating: float
    review_text: str
    pacing: float
    has_pacing: bool
    emotional_impact: float
    has_emotional_impact: bool
    intellectual_depth: float
    has_intellectual_depth: bool
    writing_quality: float
    has_writing_quality: bool
    rereadability: float
    has_rereadability: bool
    readability: float
    has_readability: bool
    plot_complexity: float
    has_plot_complexity: bool
    humor: float
    has_humor: bool
    created_at: str
    updated_at: str
    book_author_names: _containers.RepeatedScalarFieldContainer[str]
    book_author_slugs: _containers.RepeatedScalarFieldContainer[str]
    book_series_name: str
    book_series_slug: str
    def __init__(self, rating_id: _Optional[int] = ..., user_id: _Optional[int] = ..., book_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., book_title: _Optional[str] = ..., book_cover_url: _Optional[str] = ..., overall_rating: _Optional[float] = ..., review_text: _Optional[str] = ..., pacing: _Optional[float] = ..., has_pacing: bool = ..., emotional_impact: _Optional[float] = ..., has_emotional_impact: bool = ..., intellectual_depth: _Optional[float] = ..., has_intellectual_depth: bool = ..., writing_quality: _Optional[float] = ..., has_writing_quality: bool = ..., rereadability: _Optional[float] = ..., has_rereadability: bool = ..., readability: _Optional[float] = ..., has_readability: bool = ..., plot_complexity: _Optional[float] = ..., has_plot_complexity: bool = ..., humor: _Optional[float] = ..., has_humor: bool = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., book_author_names: _Optional[_Iterable[str]] = ..., book_author_slugs: _Optional[_Iterable[str]] = ..., book_series_name: _Optional[str] = ..., book_series_slug: _Optional[str] = ...) -> None: ...

class RatingResponse(_message.Message):
    __slots__ = ("rating",)
    RATING_FIELD_NUMBER: _ClassVar[int]
    rating: Rating
    def __init__(self, rating: _Optional[_Union[Rating, _Mapping]] = ...) -> None: ...

class RatingsListResponse(_message.Message):
    __slots__ = ("ratings", "total_count")
    RATINGS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    ratings: _containers.RepeatedCompositeFieldContainer[Rating]
    total_count: int
    def __init__(self, ratings: _Optional[_Iterable[_Union[Rating, _Mapping]]] = ..., total_count: _Optional[int] = ...) -> None: ...

class ToggleFavouriteRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "is_favorite")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    IS_FAVORITE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    is_favorite: bool
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., is_favorite: bool = ...) -> None: ...

class FavouriteResponse(_message.Message):
    __slots__ = ("is_favorite", "book_id", "book_slug")
    IS_FAVORITE_FIELD_NUMBER: _ClassVar[int]
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    is_favorite: bool
    book_id: int
    book_slug: str
    def __init__(self, is_favorite: bool = ..., book_id: _Optional[int] = ..., book_slug: _Optional[str] = ...) -> None: ...

class GetUserFavouritesRequest(_message.Message):
    __slots__ = ("user_id", "limit", "offset")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    limit: int
    offset: int
    def __init__(self, user_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class CreateCommentRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "body", "is_spoiler")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    IS_SPOILER_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    body: str
    is_spoiler: bool
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., body: _Optional[str] = ..., is_spoiler: bool = ...) -> None: ...

class UpdateCommentRequest(_message.Message):
    __slots__ = ("comment_id", "user_id", "body", "is_spoiler")
    COMMENT_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    IS_SPOILER_FIELD_NUMBER: _ClassVar[int]
    comment_id: int
    user_id: int
    body: str
    is_spoiler: bool
    def __init__(self, comment_id: _Optional[int] = ..., user_id: _Optional[int] = ..., body: _Optional[str] = ..., is_spoiler: bool = ...) -> None: ...

class DeleteCommentRequest(_message.Message):
    __slots__ = ("comment_id", "user_id")
    COMMENT_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    comment_id: int
    user_id: int
    def __init__(self, comment_id: _Optional[int] = ..., user_id: _Optional[int] = ...) -> None: ...

class GetUserCommentsRequest(_message.Message):
    __slots__ = ("user_id", "limit", "offset", "sort_by", "order", "book_slug")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    limit: int
    offset: int
    sort_by: str
    order: str
    book_slug: str
    def __init__(self, user_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ..., book_slug: _Optional[str] = ...) -> None: ...

class Comment(_message.Message):
    __slots__ = ("comment_id", "user_id", "book_id", "book_slug", "body", "is_spoiler", "created_at", "updated_at", "username", "book_author_names", "book_author_slugs", "book_series_name", "book_series_slug", "book_cover_url", "book_title")
    COMMENT_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    IS_SPOILER_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    BOOK_AUTHOR_NAMES_FIELD_NUMBER: _ClassVar[int]
    BOOK_AUTHOR_SLUGS_FIELD_NUMBER: _ClassVar[int]
    BOOK_SERIES_NAME_FIELD_NUMBER: _ClassVar[int]
    BOOK_SERIES_SLUG_FIELD_NUMBER: _ClassVar[int]
    BOOK_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    BOOK_TITLE_FIELD_NUMBER: _ClassVar[int]
    comment_id: int
    user_id: int
    book_id: int
    book_slug: str
    body: str
    is_spoiler: bool
    created_at: str
    updated_at: str
    username: str
    book_author_names: _containers.RepeatedScalarFieldContainer[str]
    book_author_slugs: _containers.RepeatedScalarFieldContainer[str]
    book_series_name: str
    book_series_slug: str
    book_cover_url: str
    book_title: str
    def __init__(self, comment_id: _Optional[int] = ..., user_id: _Optional[int] = ..., book_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., body: _Optional[str] = ..., is_spoiler: bool = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., username: _Optional[str] = ..., book_author_names: _Optional[_Iterable[str]] = ..., book_author_slugs: _Optional[_Iterable[str]] = ..., book_series_name: _Optional[str] = ..., book_series_slug: _Optional[str] = ..., book_cover_url: _Optional[str] = ..., book_title: _Optional[str] = ...) -> None: ...

class CommentResponse(_message.Message):
    __slots__ = ("comment",)
    COMMENT_FIELD_NUMBER: _ClassVar[int]
    comment: Comment
    def __init__(self, comment: _Optional[_Union[Comment, _Mapping]] = ...) -> None: ...

class CommentsListResponse(_message.Message):
    __slots__ = ("comments", "total_count")
    COMMENTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    comments: _containers.RepeatedCompositeFieldContainer[Comment]
    total_count: int
    def __init__(self, comments: _Optional[_Iterable[_Union[Comment, _Mapping]]] = ..., total_count: _Optional[int] = ...) -> None: ...

class EmptyResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetBookCommentsRequest(_message.Message):
    __slots__ = ("book_slug", "limit", "offset", "order", "include_spoilers", "sort_by", "requesting_user_id")
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_SPOILERS_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    REQUESTING_USER_ID_FIELD_NUMBER: _ClassVar[int]
    book_slug: str
    limit: int
    offset: int
    order: str
    include_spoilers: bool
    sort_by: str
    requesting_user_id: int
    def __init__(self, book_slug: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., order: _Optional[str] = ..., include_spoilers: bool = ..., sort_by: _Optional[str] = ..., requesting_user_id: _Optional[int] = ...) -> None: ...

class BookCommentWithRating(_message.Message):
    __slots__ = ("comment_id", "user_id", "book_id", "book_slug", "body", "is_spoiler", "comment_created_at", "comment_updated_at", "has_rating", "overall_rating", "review_text", "pacing", "has_pacing", "emotional_impact", "has_emotional_impact", "intellectual_depth", "has_intellectual_depth", "writing_quality", "has_writing_quality", "rereadability", "has_rereadability", "readability", "has_readability", "plot_complexity", "has_plot_complexity", "humor", "has_humor", "username")
    COMMENT_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    IS_SPOILER_FIELD_NUMBER: _ClassVar[int]
    COMMENT_CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    COMMENT_UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    HAS_RATING_FIELD_NUMBER: _ClassVar[int]
    OVERALL_RATING_FIELD_NUMBER: _ClassVar[int]
    REVIEW_TEXT_FIELD_NUMBER: _ClassVar[int]
    PACING_FIELD_NUMBER: _ClassVar[int]
    HAS_PACING_FIELD_NUMBER: _ClassVar[int]
    EMOTIONAL_IMPACT_FIELD_NUMBER: _ClassVar[int]
    HAS_EMOTIONAL_IMPACT_FIELD_NUMBER: _ClassVar[int]
    INTELLECTUAL_DEPTH_FIELD_NUMBER: _ClassVar[int]
    HAS_INTELLECTUAL_DEPTH_FIELD_NUMBER: _ClassVar[int]
    WRITING_QUALITY_FIELD_NUMBER: _ClassVar[int]
    HAS_WRITING_QUALITY_FIELD_NUMBER: _ClassVar[int]
    REREADABILITY_FIELD_NUMBER: _ClassVar[int]
    HAS_REREADABILITY_FIELD_NUMBER: _ClassVar[int]
    READABILITY_FIELD_NUMBER: _ClassVar[int]
    HAS_READABILITY_FIELD_NUMBER: _ClassVar[int]
    PLOT_COMPLEXITY_FIELD_NUMBER: _ClassVar[int]
    HAS_PLOT_COMPLEXITY_FIELD_NUMBER: _ClassVar[int]
    HUMOR_FIELD_NUMBER: _ClassVar[int]
    HAS_HUMOR_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    comment_id: int
    user_id: int
    book_id: int
    book_slug: str
    body: str
    is_spoiler: bool
    comment_created_at: str
    comment_updated_at: str
    has_rating: bool
    overall_rating: float
    review_text: str
    pacing: float
    has_pacing: bool
    emotional_impact: float
    has_emotional_impact: bool
    intellectual_depth: float
    has_intellectual_depth: bool
    writing_quality: float
    has_writing_quality: bool
    rereadability: float
    has_rereadability: bool
    readability: float
    has_readability: bool
    plot_complexity: float
    has_plot_complexity: bool
    humor: float
    has_humor: bool
    username: str
    def __init__(self, comment_id: _Optional[int] = ..., user_id: _Optional[int] = ..., book_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., body: _Optional[str] = ..., is_spoiler: bool = ..., comment_created_at: _Optional[str] = ..., comment_updated_at: _Optional[str] = ..., has_rating: bool = ..., overall_rating: _Optional[float] = ..., review_text: _Optional[str] = ..., pacing: _Optional[float] = ..., has_pacing: bool = ..., emotional_impact: _Optional[float] = ..., has_emotional_impact: bool = ..., intellectual_depth: _Optional[float] = ..., has_intellectual_depth: bool = ..., writing_quality: _Optional[float] = ..., has_writing_quality: bool = ..., rereadability: _Optional[float] = ..., has_rereadability: bool = ..., readability: _Optional[float] = ..., has_readability: bool = ..., plot_complexity: _Optional[float] = ..., has_plot_complexity: bool = ..., humor: _Optional[float] = ..., has_humor: bool = ..., username: _Optional[str] = ...) -> None: ...

class BookCommentsResponse(_message.Message):
    __slots__ = ("comments", "total_count", "my_entry")
    COMMENTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    MY_ENTRY_FIELD_NUMBER: _ClassVar[int]
    comments: _containers.RepeatedCompositeFieldContainer[BookCommentWithRating]
    total_count: int
    my_entry: BookCommentWithRating
    def __init__(self, comments: _Optional[_Iterable[_Union[BookCommentWithRating, _Mapping]]] = ..., total_count: _Optional[int] = ..., my_entry: _Optional[_Union[BookCommentWithRating, _Mapping]] = ...) -> None: ...

class GetUserBookInfoRequest(_message.Message):
    __slots__ = ("user_id", "book_slug")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ...) -> None: ...

class UserBookInfoResponse(_message.Message):
    __slots__ = ("bookshelf", "rating", "comment")
    BOOKSHELF_FIELD_NUMBER: _ClassVar[int]
    RATING_FIELD_NUMBER: _ClassVar[int]
    COMMENT_FIELD_NUMBER: _ClassVar[int]
    bookshelf: Bookshelf
    rating: Rating
    comment: Comment
    def __init__(self, bookshelf: _Optional[_Union[Bookshelf, _Mapping]] = ..., rating: _Optional[_Union[Rating, _Mapping]] = ..., comment: _Optional[_Union[Comment, _Mapping]] = ...) -> None: ...

class GetPublicProfileStatsRequest(_message.Message):
    __slots__ = ("username",)
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    username: str
    def __init__(self, username: _Optional[str] = ...) -> None: ...

class ProfileStats(_message.Message):
    __slots__ = ("want_to_read_count", "reading_count", "read_count", "abandoned_count", "favourites_count", "ratings_count", "comments_count")
    WANT_TO_READ_COUNT_FIELD_NUMBER: _ClassVar[int]
    READING_COUNT_FIELD_NUMBER: _ClassVar[int]
    READ_COUNT_FIELD_NUMBER: _ClassVar[int]
    ABANDONED_COUNT_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_COUNT_FIELD_NUMBER: _ClassVar[int]
    RATINGS_COUNT_FIELD_NUMBER: _ClassVar[int]
    COMMENTS_COUNT_FIELD_NUMBER: _ClassVar[int]
    want_to_read_count: int
    reading_count: int
    read_count: int
    abandoned_count: int
    favourites_count: int
    ratings_count: int
    comments_count: int
    def __init__(self, want_to_read_count: _Optional[int] = ..., reading_count: _Optional[int] = ..., read_count: _Optional[int] = ..., abandoned_count: _Optional[int] = ..., favourites_count: _Optional[int] = ..., ratings_count: _Optional[int] = ..., comments_count: _Optional[int] = ...) -> None: ...

class ProfileStatsResponse(_message.Message):
    __slots__ = ("stats",)
    STATS_FIELD_NUMBER: _ClassVar[int]
    stats: ProfileStats
    def __init__(self, stats: _Optional[_Union[ProfileStats, _Mapping]] = ...) -> None: ...

class DeleteUserDataRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...
