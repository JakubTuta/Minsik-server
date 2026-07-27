from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetBookshelfRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class UpsertBookshelfRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "status", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    status: str
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., status: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class DeleteBookshelfRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class GetUserBookshelvesRequest(_message.Message):
    __slots__ = ("user_id", "limit", "offset", "status_filter", "favourites_only", "sort_by", "order", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    STATUS_FILTER_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_ONLY_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    limit: int
    offset: int
    status_filter: str
    favourites_only: bool
    sort_by: str
    order: str
    language: str
    def __init__(self, user_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., status_filter: _Optional[str] = ..., favourites_only: bool = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class GetPublicBookshelvesRequest(_message.Message):
    __slots__ = ("username", "limit", "offset", "status_filter", "favourites_only", "sort_by", "order", "language")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    STATUS_FILTER_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_ONLY_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    username: str
    limit: int
    offset: int
    status_filter: str
    favourites_only: bool
    sort_by: str
    order: str
    language: str
    def __init__(self, username: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., status_filter: _Optional[str] = ..., favourites_only: bool = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("user_id", "book_slug", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class UpsertRatingRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "overall_rating", "review_text", "pacing", "has_pacing", "emotional_impact", "has_emotional_impact", "intellectual_depth", "has_intellectual_depth", "writing_quality", "has_writing_quality", "rereadability", "has_rereadability", "readability", "has_readability", "plot_complexity", "has_plot_complexity", "humor", "has_humor", "language")
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
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
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
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., overall_rating: _Optional[float] = ..., review_text: _Optional[str] = ..., pacing: _Optional[float] = ..., has_pacing: bool = ..., emotional_impact: _Optional[float] = ..., has_emotional_impact: bool = ..., intellectual_depth: _Optional[float] = ..., has_intellectual_depth: bool = ..., writing_quality: _Optional[float] = ..., has_writing_quality: bool = ..., rereadability: _Optional[float] = ..., has_rereadability: bool = ..., readability: _Optional[float] = ..., has_readability: bool = ..., plot_complexity: _Optional[float] = ..., has_plot_complexity: bool = ..., humor: _Optional[float] = ..., has_humor: bool = ..., language: _Optional[str] = ...) -> None: ...

class DeleteRatingRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class GetUserRatingsRequest(_message.Message):
    __slots__ = ("user_id", "limit", "offset", "sort_by", "order", "min_rating", "max_rating", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    MIN_RATING_FIELD_NUMBER: _ClassVar[int]
    MAX_RATING_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    limit: int
    offset: int
    sort_by: str
    order: str
    min_rating: float
    max_rating: float
    language: str
    def __init__(self, user_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ..., min_rating: _Optional[float] = ..., max_rating: _Optional[float] = ..., language: _Optional[str] = ...) -> None: ...

class Rating(_message.Message):
    __slots__ = ("rating_id", "user_id", "book_id", "book_slug", "book_title", "book_cover_url", "overall_rating", "review_text", "pacing", "has_pacing", "emotional_impact", "has_emotional_impact", "intellectual_depth", "has_intellectual_depth", "writing_quality", "has_writing_quality", "rereadability", "has_rereadability", "readability", "has_readability", "plot_complexity", "has_plot_complexity", "humor", "has_humor", "created_at", "updated_at", "book_author_names", "book_author_slugs", "book_series_name", "book_series_slug", "book_avg_rating", "book_rating_count")
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
    BOOK_AVG_RATING_FIELD_NUMBER: _ClassVar[int]
    BOOK_RATING_COUNT_FIELD_NUMBER: _ClassVar[int]
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
    book_avg_rating: float
    book_rating_count: int
    def __init__(self, rating_id: _Optional[int] = ..., user_id: _Optional[int] = ..., book_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., book_title: _Optional[str] = ..., book_cover_url: _Optional[str] = ..., overall_rating: _Optional[float] = ..., review_text: _Optional[str] = ..., pacing: _Optional[float] = ..., has_pacing: bool = ..., emotional_impact: _Optional[float] = ..., has_emotional_impact: bool = ..., intellectual_depth: _Optional[float] = ..., has_intellectual_depth: bool = ..., writing_quality: _Optional[float] = ..., has_writing_quality: bool = ..., rereadability: _Optional[float] = ..., has_rereadability: bool = ..., readability: _Optional[float] = ..., has_readability: bool = ..., plot_complexity: _Optional[float] = ..., has_plot_complexity: bool = ..., humor: _Optional[float] = ..., has_humor: bool = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., book_author_names: _Optional[_Iterable[str]] = ..., book_author_slugs: _Optional[_Iterable[str]] = ..., book_series_name: _Optional[str] = ..., book_series_slug: _Optional[str] = ..., book_avg_rating: _Optional[float] = ..., book_rating_count: _Optional[int] = ...) -> None: ...

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
    __slots__ = ("user_id", "book_slug", "is_favorite", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    IS_FAVORITE_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    is_favorite: bool
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., is_favorite: bool = ..., language: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("user_id", "limit", "offset", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    limit: int
    offset: int
    language: str
    def __init__(self, user_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., language: _Optional[str] = ...) -> None: ...

class CreateCommentRequest(_message.Message):
    __slots__ = ("user_id", "book_slug", "body", "is_spoiler", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    IS_SPOILER_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    body: str
    is_spoiler: bool
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., body: _Optional[str] = ..., is_spoiler: bool = ..., language: _Optional[str] = ...) -> None: ...

class UpdateCommentRequest(_message.Message):
    __slots__ = ("comment_id", "user_id", "body", "is_spoiler", "language")
    COMMENT_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    IS_SPOILER_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    comment_id: int
    user_id: int
    body: str
    is_spoiler: bool
    language: str
    def __init__(self, comment_id: _Optional[int] = ..., user_id: _Optional[int] = ..., body: _Optional[str] = ..., is_spoiler: bool = ..., language: _Optional[str] = ...) -> None: ...

class DeleteCommentRequest(_message.Message):
    __slots__ = ("comment_id", "user_id")
    COMMENT_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    comment_id: int
    user_id: int
    def __init__(self, comment_id: _Optional[int] = ..., user_id: _Optional[int] = ...) -> None: ...

class GetUserCommentsRequest(_message.Message):
    __slots__ = ("user_id", "limit", "offset", "sort_by", "order", "book_slug", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    limit: int
    offset: int
    sort_by: str
    order: str
    book_slug: str
    language: str
    def __init__(self, user_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ..., book_slug: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("book_slug", "limit", "offset", "order", "include_spoilers", "sort_by", "requesting_user_id", "rating_filters", "language")
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_SPOILERS_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    REQUESTING_USER_ID_FIELD_NUMBER: _ClassVar[int]
    RATING_FILTERS_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    book_slug: str
    limit: int
    offset: int
    order: str
    include_spoilers: bool
    sort_by: str
    requesting_user_id: int
    rating_filters: _containers.RepeatedScalarFieldContainer[float]
    language: str
    def __init__(self, book_slug: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., order: _Optional[str] = ..., include_spoilers: bool = ..., sort_by: _Optional[str] = ..., requesting_user_id: _Optional[int] = ..., rating_filters: _Optional[_Iterable[float]] = ..., language: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("user_id", "book_slug", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_slug: str
    language: str
    def __init__(self, user_id: _Optional[int] = ..., book_slug: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class UserBookInfoResponse(_message.Message):
    __slots__ = ("bookshelf", "rating", "comment")
    BOOKSHELF_FIELD_NUMBER: _ClassVar[int]
    RATING_FIELD_NUMBER: _ClassVar[int]
    COMMENT_FIELD_NUMBER: _ClassVar[int]
    bookshelf: Bookshelf
    rating: Rating
    comment: Comment
    def __init__(self, bookshelf: _Optional[_Union[Bookshelf, _Mapping]] = ..., rating: _Optional[_Union[Rating, _Mapping]] = ..., comment: _Optional[_Union[Comment, _Mapping]] = ...) -> None: ...

class GetBookStatusesRequest(_message.Message):
    __slots__ = ("user_id", "book_ids")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_IDS_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    book_ids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, user_id: _Optional[int] = ..., book_ids: _Optional[_Iterable[int]] = ...) -> None: ...

class BookStatus(_message.Message):
    __slots__ = ("book_id", "status", "is_favorite")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    IS_FAVORITE_FIELD_NUMBER: _ClassVar[int]
    book_id: int
    status: str
    is_favorite: bool
    def __init__(self, book_id: _Optional[int] = ..., status: _Optional[str] = ..., is_favorite: bool = ...) -> None: ...

class BookStatusesResponse(_message.Message):
    __slots__ = ("statuses",)
    STATUSES_FIELD_NUMBER: _ClassVar[int]
    statuses: _containers.RepeatedCompositeFieldContainer[BookStatus]
    def __init__(self, statuses: _Optional[_Iterable[_Union[BookStatus, _Mapping]]] = ...) -> None: ...

class GetPublicProfileStatsRequest(_message.Message):
    __slots__ = ("username",)
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    username: str
    def __init__(self, username: _Optional[str] = ...) -> None: ...

class ProfileStats(_message.Message):
    __slots__ = ("want_to_read_count", "reading_count", "read_count", "abandoned_count", "favourites_count", "ratings_count", "comments_count", "finished_this_year_count", "pages_read_this_year", "hours_read_this_year", "bookshelf_updated_at", "favourites_updated_at", "comments_updated_at", "ratings_updated_at", "average_rating", "rating_distribution_json", "pages_read_total", "reviews_count")
    WANT_TO_READ_COUNT_FIELD_NUMBER: _ClassVar[int]
    READING_COUNT_FIELD_NUMBER: _ClassVar[int]
    READ_COUNT_FIELD_NUMBER: _ClassVar[int]
    ABANDONED_COUNT_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_COUNT_FIELD_NUMBER: _ClassVar[int]
    RATINGS_COUNT_FIELD_NUMBER: _ClassVar[int]
    COMMENTS_COUNT_FIELD_NUMBER: _ClassVar[int]
    FINISHED_THIS_YEAR_COUNT_FIELD_NUMBER: _ClassVar[int]
    PAGES_READ_THIS_YEAR_FIELD_NUMBER: _ClassVar[int]
    HOURS_READ_THIS_YEAR_FIELD_NUMBER: _ClassVar[int]
    BOOKSHELF_UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    COMMENTS_UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    RATINGS_UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    AVERAGE_RATING_FIELD_NUMBER: _ClassVar[int]
    RATING_DISTRIBUTION_JSON_FIELD_NUMBER: _ClassVar[int]
    PAGES_READ_TOTAL_FIELD_NUMBER: _ClassVar[int]
    REVIEWS_COUNT_FIELD_NUMBER: _ClassVar[int]
    want_to_read_count: int
    reading_count: int
    read_count: int
    abandoned_count: int
    favourites_count: int
    ratings_count: int
    comments_count: int
    finished_this_year_count: int
    pages_read_this_year: int
    hours_read_this_year: int
    bookshelf_updated_at: str
    favourites_updated_at: str
    comments_updated_at: str
    ratings_updated_at: str
    average_rating: float
    rating_distribution_json: str
    pages_read_total: int
    reviews_count: int
    def __init__(self, want_to_read_count: _Optional[int] = ..., reading_count: _Optional[int] = ..., read_count: _Optional[int] = ..., abandoned_count: _Optional[int] = ..., favourites_count: _Optional[int] = ..., ratings_count: _Optional[int] = ..., comments_count: _Optional[int] = ..., finished_this_year_count: _Optional[int] = ..., pages_read_this_year: _Optional[int] = ..., hours_read_this_year: _Optional[int] = ..., bookshelf_updated_at: _Optional[str] = ..., favourites_updated_at: _Optional[str] = ..., comments_updated_at: _Optional[str] = ..., ratings_updated_at: _Optional[str] = ..., average_rating: _Optional[float] = ..., rating_distribution_json: _Optional[str] = ..., pages_read_total: _Optional[int] = ..., reviews_count: _Optional[int] = ...) -> None: ...

class ProfileStatsResponse(_message.Message):
    __slots__ = ("stats",)
    STATS_FIELD_NUMBER: _ClassVar[int]
    stats: ProfileStats
    def __init__(self, stats: _Optional[_Union[ProfileStats, _Mapping]] = ...) -> None: ...

class GetProfileOverviewRequest(_message.Message):
    __slots__ = ("username", "language")
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    username: str
    language: str
    def __init__(self, username: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class PublicUser(_message.Message):
    __slots__ = ("user_id", "username", "display_name", "avatar_url", "bio")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    AVATAR_URL_FIELD_NUMBER: _ClassVar[int]
    BIO_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    username: str
    display_name: str
    avatar_url: str
    bio: str
    def __init__(self, user_id: _Optional[int] = ..., username: _Optional[str] = ..., display_name: _Optional[str] = ..., avatar_url: _Optional[str] = ..., bio: _Optional[str] = ...) -> None: ...

class OverviewBook(_message.Message):
    __slots__ = ("book_slug", "book_title", "book_cover_url", "book_author_names", "book_author_slugs")
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    BOOK_TITLE_FIELD_NUMBER: _ClassVar[int]
    BOOK_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    BOOK_AUTHOR_NAMES_FIELD_NUMBER: _ClassVar[int]
    BOOK_AUTHOR_SLUGS_FIELD_NUMBER: _ClassVar[int]
    book_slug: str
    book_title: str
    book_cover_url: str
    book_author_names: _containers.RepeatedScalarFieldContainer[str]
    book_author_slugs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, book_slug: _Optional[str] = ..., book_title: _Optional[str] = ..., book_cover_url: _Optional[str] = ..., book_author_names: _Optional[_Iterable[str]] = ..., book_author_slugs: _Optional[_Iterable[str]] = ...) -> None: ...

class TopGenre(_message.Message):
    __slots__ = ("name", "slug", "count", "percent")
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    PERCENT_FIELD_NUMBER: _ClassVar[int]
    name: str
    slug: str
    count: int
    percent: float
    def __init__(self, name: _Optional[str] = ..., slug: _Optional[str] = ..., count: _Optional[int] = ..., percent: _Optional[float] = ...) -> None: ...

class FavouriteAuthor(_message.Message):
    __slots__ = ("name", "slug", "count", "photo_url")
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    PHOTO_URL_FIELD_NUMBER: _ClassVar[int]
    name: str
    slug: str
    count: int
    photo_url: str
    def __init__(self, name: _Optional[str] = ..., slug: _Optional[str] = ..., count: _Optional[int] = ..., photo_url: _Optional[str] = ...) -> None: ...

class ProfileOverviewResponse(_message.Message):
    __slots__ = ("user", "reading_now", "top_genres", "favourite_authors", "favourites_this_year", "reading_now_present")
    USER_FIELD_NUMBER: _ClassVar[int]
    READING_NOW_FIELD_NUMBER: _ClassVar[int]
    TOP_GENRES_FIELD_NUMBER: _ClassVar[int]
    FAVOURITE_AUTHORS_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_THIS_YEAR_FIELD_NUMBER: _ClassVar[int]
    READING_NOW_PRESENT_FIELD_NUMBER: _ClassVar[int]
    user: PublicUser
    reading_now: OverviewBook
    top_genres: _containers.RepeatedCompositeFieldContainer[TopGenre]
    favourite_authors: _containers.RepeatedCompositeFieldContainer[FavouriteAuthor]
    favourites_this_year: _containers.RepeatedCompositeFieldContainer[OverviewBook]
    reading_now_present: bool
    def __init__(self, user: _Optional[_Union[PublicUser, _Mapping]] = ..., reading_now: _Optional[_Union[OverviewBook, _Mapping]] = ..., top_genres: _Optional[_Iterable[_Union[TopGenre, _Mapping]]] = ..., favourite_authors: _Optional[_Iterable[_Union[FavouriteAuthor, _Mapping]]] = ..., favourites_this_year: _Optional[_Iterable[_Union[OverviewBook, _Mapping]]] = ..., reading_now_present: bool = ...) -> None: ...

class GetYearInReviewRequest(_message.Message):
    __slots__ = ("user_id", "year", "language")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    YEAR_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    year: int
    language: str
    def __init__(self, user_id: _Optional[int] = ..., year: _Optional[int] = ..., language: _Optional[str] = ...) -> None: ...

class MonthlyBucket(_message.Message):
    __slots__ = ("month", "books_finished", "pages_read", "ratings_given", "books")
    MONTH_FIELD_NUMBER: _ClassVar[int]
    BOOKS_FINISHED_FIELD_NUMBER: _ClassVar[int]
    PAGES_READ_FIELD_NUMBER: _ClassVar[int]
    RATINGS_GIVEN_FIELD_NUMBER: _ClassVar[int]
    BOOKS_FIELD_NUMBER: _ClassVar[int]
    month: int
    books_finished: int
    pages_read: int
    ratings_given: int
    books: _containers.RepeatedCompositeFieldContainer[YearBook]
    def __init__(self, month: _Optional[int] = ..., books_finished: _Optional[int] = ..., pages_read: _Optional[int] = ..., ratings_given: _Optional[int] = ..., books: _Optional[_Iterable[_Union[YearBook, _Mapping]]] = ...) -> None: ...

class YearBook(_message.Message):
    __slots__ = ("book_slug", "book_title", "book_cover_url", "author_names", "author_slugs", "number_of_pages", "finished_at", "my_rating", "has_my_rating")
    BOOK_SLUG_FIELD_NUMBER: _ClassVar[int]
    BOOK_TITLE_FIELD_NUMBER: _ClassVar[int]
    BOOK_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_NAMES_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_SLUGS_FIELD_NUMBER: _ClassVar[int]
    NUMBER_OF_PAGES_FIELD_NUMBER: _ClassVar[int]
    FINISHED_AT_FIELD_NUMBER: _ClassVar[int]
    MY_RATING_FIELD_NUMBER: _ClassVar[int]
    HAS_MY_RATING_FIELD_NUMBER: _ClassVar[int]
    book_slug: str
    book_title: str
    book_cover_url: str
    author_names: _containers.RepeatedScalarFieldContainer[str]
    author_slugs: _containers.RepeatedScalarFieldContainer[str]
    number_of_pages: int
    finished_at: str
    my_rating: float
    has_my_rating: bool
    def __init__(self, book_slug: _Optional[str] = ..., book_title: _Optional[str] = ..., book_cover_url: _Optional[str] = ..., author_names: _Optional[_Iterable[str]] = ..., author_slugs: _Optional[_Iterable[str]] = ..., number_of_pages: _Optional[int] = ..., finished_at: _Optional[str] = ..., my_rating: _Optional[float] = ..., has_my_rating: bool = ...) -> None: ...

class YearInReview(_message.Message):
    __slots__ = ("year", "months_elapsed", "monthly", "total_books_finished", "total_pages_read", "total_hours_read", "ratings_given", "reviews_written", "comments_written", "favourites_added", "average_rating_given", "rating_distribution_json", "top_genres", "top_authors", "longest_book", "has_longest_book", "shortest_book", "has_shortest_book", "first_finished", "has_first_finished", "highest_rated", "has_highest_rated", "average_pages_per_book", "busiest_month", "busiest_month_count", "average_days_to_finish", "currently_reading_count", "added_to_shelf_count", "finished_cover_urls")
    YEAR_FIELD_NUMBER: _ClassVar[int]
    MONTHS_ELAPSED_FIELD_NUMBER: _ClassVar[int]
    MONTHLY_FIELD_NUMBER: _ClassVar[int]
    TOTAL_BOOKS_FINISHED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PAGES_READ_FIELD_NUMBER: _ClassVar[int]
    TOTAL_HOURS_READ_FIELD_NUMBER: _ClassVar[int]
    RATINGS_GIVEN_FIELD_NUMBER: _ClassVar[int]
    REVIEWS_WRITTEN_FIELD_NUMBER: _ClassVar[int]
    COMMENTS_WRITTEN_FIELD_NUMBER: _ClassVar[int]
    FAVOURITES_ADDED_FIELD_NUMBER: _ClassVar[int]
    AVERAGE_RATING_GIVEN_FIELD_NUMBER: _ClassVar[int]
    RATING_DISTRIBUTION_JSON_FIELD_NUMBER: _ClassVar[int]
    TOP_GENRES_FIELD_NUMBER: _ClassVar[int]
    TOP_AUTHORS_FIELD_NUMBER: _ClassVar[int]
    LONGEST_BOOK_FIELD_NUMBER: _ClassVar[int]
    HAS_LONGEST_BOOK_FIELD_NUMBER: _ClassVar[int]
    SHORTEST_BOOK_FIELD_NUMBER: _ClassVar[int]
    HAS_SHORTEST_BOOK_FIELD_NUMBER: _ClassVar[int]
    FIRST_FINISHED_FIELD_NUMBER: _ClassVar[int]
    HAS_FIRST_FINISHED_FIELD_NUMBER: _ClassVar[int]
    HIGHEST_RATED_FIELD_NUMBER: _ClassVar[int]
    HAS_HIGHEST_RATED_FIELD_NUMBER: _ClassVar[int]
    AVERAGE_PAGES_PER_BOOK_FIELD_NUMBER: _ClassVar[int]
    BUSIEST_MONTH_FIELD_NUMBER: _ClassVar[int]
    BUSIEST_MONTH_COUNT_FIELD_NUMBER: _ClassVar[int]
    AVERAGE_DAYS_TO_FINISH_FIELD_NUMBER: _ClassVar[int]
    CURRENTLY_READING_COUNT_FIELD_NUMBER: _ClassVar[int]
    ADDED_TO_SHELF_COUNT_FIELD_NUMBER: _ClassVar[int]
    FINISHED_COVER_URLS_FIELD_NUMBER: _ClassVar[int]
    year: int
    months_elapsed: int
    monthly: _containers.RepeatedCompositeFieldContainer[MonthlyBucket]
    total_books_finished: int
    total_pages_read: int
    total_hours_read: int
    ratings_given: int
    reviews_written: int
    comments_written: int
    favourites_added: int
    average_rating_given: float
    rating_distribution_json: str
    top_genres: _containers.RepeatedCompositeFieldContainer[TopGenre]
    top_authors: _containers.RepeatedCompositeFieldContainer[FavouriteAuthor]
    longest_book: YearBook
    has_longest_book: bool
    shortest_book: YearBook
    has_shortest_book: bool
    first_finished: YearBook
    has_first_finished: bool
    highest_rated: YearBook
    has_highest_rated: bool
    average_pages_per_book: float
    busiest_month: int
    busiest_month_count: int
    average_days_to_finish: float
    currently_reading_count: int
    added_to_shelf_count: int
    finished_cover_urls: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, year: _Optional[int] = ..., months_elapsed: _Optional[int] = ..., monthly: _Optional[_Iterable[_Union[MonthlyBucket, _Mapping]]] = ..., total_books_finished: _Optional[int] = ..., total_pages_read: _Optional[int] = ..., total_hours_read: _Optional[int] = ..., ratings_given: _Optional[int] = ..., reviews_written: _Optional[int] = ..., comments_written: _Optional[int] = ..., favourites_added: _Optional[int] = ..., average_rating_given: _Optional[float] = ..., rating_distribution_json: _Optional[str] = ..., top_genres: _Optional[_Iterable[_Union[TopGenre, _Mapping]]] = ..., top_authors: _Optional[_Iterable[_Union[FavouriteAuthor, _Mapping]]] = ..., longest_book: _Optional[_Union[YearBook, _Mapping]] = ..., has_longest_book: bool = ..., shortest_book: _Optional[_Union[YearBook, _Mapping]] = ..., has_shortest_book: bool = ..., first_finished: _Optional[_Union[YearBook, _Mapping]] = ..., has_first_finished: bool = ..., highest_rated: _Optional[_Union[YearBook, _Mapping]] = ..., has_highest_rated: bool = ..., average_pages_per_book: _Optional[float] = ..., busiest_month: _Optional[int] = ..., busiest_month_count: _Optional[int] = ..., average_days_to_finish: _Optional[float] = ..., currently_reading_count: _Optional[int] = ..., added_to_shelf_count: _Optional[int] = ..., finished_cover_urls: _Optional[_Iterable[str]] = ...) -> None: ...

class YearInReviewResponse(_message.Message):
    __slots__ = ("review",)
    REVIEW_FIELD_NUMBER: _ClassVar[int]
    review: YearInReview
    def __init__(self, review: _Optional[_Union[YearInReview, _Mapping]] = ...) -> None: ...

class DeleteUserDataRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...
