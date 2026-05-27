from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetRecommendationListRequest(_message.Message):
    __slots__ = ("category", "limit", "offset", "language", "user_id")
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    category: str
    limit: int
    offset: int
    language: str
    user_id: int
    def __init__(self, category: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., language: _Optional[str] = ..., user_id: _Optional[int] = ...) -> None: ...

class RecommendationListResponse(_message.Message):
    __slots__ = ("category", "display_name", "item_type", "book_items", "author_items", "total")
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    ITEM_TYPE_FIELD_NUMBER: _ClassVar[int]
    BOOK_ITEMS_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_ITEMS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    category: str
    display_name: str
    item_type: str
    book_items: _containers.RepeatedCompositeFieldContainer[RecommendationBookItem]
    author_items: _containers.RepeatedCompositeFieldContainer[RecommendationAuthorItem]
    total: int
    def __init__(self, category: _Optional[str] = ..., display_name: _Optional[str] = ..., item_type: _Optional[str] = ..., book_items: _Optional[_Iterable[_Union[RecommendationBookItem, _Mapping]]] = ..., author_items: _Optional[_Iterable[_Union[RecommendationAuthorItem, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class RecommendationBookItem(_message.Message):
    __slots__ = ("book_id", "title", "slug", "language", "primary_cover_url", "author_names", "author_slugs", "avg_rating", "rating_count", "score", "readers")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    PRIMARY_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_NAMES_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_SLUGS_FIELD_NUMBER: _ClassVar[int]
    AVG_RATING_FIELD_NUMBER: _ClassVar[int]
    RATING_COUNT_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    READERS_FIELD_NUMBER: _ClassVar[int]
    book_id: int
    title: str
    slug: str
    language: str
    primary_cover_url: str
    author_names: _containers.RepeatedScalarFieldContainer[str]
    author_slugs: _containers.RepeatedScalarFieldContainer[str]
    avg_rating: str
    rating_count: int
    score: float
    readers: int
    def __init__(self, book_id: _Optional[int] = ..., title: _Optional[str] = ..., slug: _Optional[str] = ..., language: _Optional[str] = ..., primary_cover_url: _Optional[str] = ..., author_names: _Optional[_Iterable[str]] = ..., author_slugs: _Optional[_Iterable[str]] = ..., avg_rating: _Optional[str] = ..., rating_count: _Optional[int] = ..., score: _Optional[float] = ..., readers: _Optional[int] = ...) -> None: ...

class RecommendationAuthorItem(_message.Message):
    __slots__ = ("author_id", "name", "slug", "photo_url", "book_count", "score", "avg_rating", "readers", "rating_count")
    AUTHOR_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    PHOTO_URL_FIELD_NUMBER: _ClassVar[int]
    BOOK_COUNT_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    AVG_RATING_FIELD_NUMBER: _ClassVar[int]
    READERS_FIELD_NUMBER: _ClassVar[int]
    RATING_COUNT_FIELD_NUMBER: _ClassVar[int]
    author_id: int
    name: str
    slug: str
    photo_url: str
    book_count: int
    score: float
    avg_rating: str
    readers: int
    rating_count: int
    def __init__(self, author_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., photo_url: _Optional[str] = ..., book_count: _Optional[int] = ..., score: _Optional[float] = ..., avg_rating: _Optional[str] = ..., readers: _Optional[int] = ..., rating_count: _Optional[int] = ...) -> None: ...

class GetHomePageRequest(_message.Message):
    __slots__ = ("items_per_category", "user_id", "language")
    ITEMS_PER_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    items_per_category: int
    user_id: int
    language: str
    def __init__(self, items_per_category: _Optional[int] = ..., user_id: _Optional[int] = ..., language: _Optional[str] = ...) -> None: ...

class HomePageResponse(_message.Message):
    __slots__ = ("categories",)
    CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    categories: _containers.RepeatedCompositeFieldContainer[RecommendationListResponse]
    def __init__(self, categories: _Optional[_Iterable[_Union[RecommendationListResponse, _Mapping]]] = ...) -> None: ...

class GetAvailableCategoriesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AvailableCategoriesResponse(_message.Message):
    __slots__ = ("categories",)
    CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    categories: _containers.RepeatedCompositeFieldContainer[CategoryInfo]
    def __init__(self, categories: _Optional[_Iterable[_Union[CategoryInfo, _Mapping]]] = ...) -> None: ...

class CategoryInfo(_message.Message):
    __slots__ = ("category", "display_name", "item_type")
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    ITEM_TYPE_FIELD_NUMBER: _ClassVar[int]
    category: str
    display_name: str
    item_type: str
    def __init__(self, category: _Optional[str] = ..., display_name: _Optional[str] = ..., item_type: _Optional[str] = ...) -> None: ...

class RefreshRecommendationsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class RefreshRecommendationsResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class RefreshBookOfTheWeekRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class RefreshBookOfTheWeekResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class RefreshPersonalRecommendationsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class RefreshPersonalRecommendationsResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class RefreshUserPersonalRecommendationsRequest(_message.Message):
    __slots__ = ("username",)
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    username: str
    def __init__(self, username: _Optional[str] = ...) -> None: ...

class RefreshUserPersonalRecommendationsResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class RefreshContextualRecommendationsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class RefreshContextualRecommendationsResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class InvalidateContextualCacheRequest(_message.Message):
    __slots__ = ("entity_type", "slug")
    ENTITY_TYPE_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    entity_type: str
    slug: str
    def __init__(self, entity_type: _Optional[str] = ..., slug: _Optional[str] = ...) -> None: ...

class InvalidateContextualCacheResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class GetBookRecommendationsRequest(_message.Message):
    __slots__ = ("book_id", "limit_per_section", "user_id")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_PER_SECTION_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    book_id: int
    limit_per_section: int
    user_id: int
    def __init__(self, book_id: _Optional[int] = ..., limit_per_section: _Optional[int] = ..., user_id: _Optional[int] = ...) -> None: ...

class GetAuthorRecommendationsRequest(_message.Message):
    __slots__ = ("author_id", "limit_per_section", "user_id")
    AUTHOR_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_PER_SECTION_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    author_id: int
    limit_per_section: int
    user_id: int
    def __init__(self, author_id: _Optional[int] = ..., limit_per_section: _Optional[int] = ..., user_id: _Optional[int] = ...) -> None: ...

class RecommendationSection(_message.Message):
    __slots__ = ("section_key", "display_name", "item_type", "book_items", "author_items", "total")
    SECTION_KEY_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    ITEM_TYPE_FIELD_NUMBER: _ClassVar[int]
    BOOK_ITEMS_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_ITEMS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    section_key: str
    display_name: str
    item_type: str
    book_items: _containers.RepeatedCompositeFieldContainer[RecommendationBookItem]
    author_items: _containers.RepeatedCompositeFieldContainer[RecommendationAuthorItem]
    total: int
    def __init__(self, section_key: _Optional[str] = ..., display_name: _Optional[str] = ..., item_type: _Optional[str] = ..., book_items: _Optional[_Iterable[_Union[RecommendationBookItem, _Mapping]]] = ..., author_items: _Optional[_Iterable[_Union[RecommendationAuthorItem, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class BookRecommendationsResponse(_message.Message):
    __slots__ = ("book_id", "sections")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    SECTIONS_FIELD_NUMBER: _ClassVar[int]
    book_id: int
    sections: _containers.RepeatedCompositeFieldContainer[RecommendationSection]
    def __init__(self, book_id: _Optional[int] = ..., sections: _Optional[_Iterable[_Union[RecommendationSection, _Mapping]]] = ...) -> None: ...

class AuthorRecommendationsResponse(_message.Message):
    __slots__ = ("author_id", "sections")
    AUTHOR_ID_FIELD_NUMBER: _ClassVar[int]
    SECTIONS_FIELD_NUMBER: _ClassVar[int]
    author_id: int
    sections: _containers.RepeatedCompositeFieldContainer[RecommendationSection]
    def __init__(self, author_id: _Optional[int] = ..., sections: _Optional[_Iterable[_Union[RecommendationSection, _Mapping]]] = ...) -> None: ...

class GetSeriesRecommendationsRequest(_message.Message):
    __slots__ = ("series_id", "limit_per_section")
    SERIES_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_PER_SECTION_FIELD_NUMBER: _ClassVar[int]
    series_id: int
    limit_per_section: int
    def __init__(self, series_id: _Optional[int] = ..., limit_per_section: _Optional[int] = ...) -> None: ...

class SeriesRecommendationsResponse(_message.Message):
    __slots__ = ("series_id", "sections")
    SERIES_ID_FIELD_NUMBER: _ClassVar[int]
    SECTIONS_FIELD_NUMBER: _ClassVar[int]
    series_id: int
    sections: _containers.RepeatedCompositeFieldContainer[RecommendationSection]
    def __init__(self, series_id: _Optional[int] = ..., sections: _Optional[_Iterable[_Union[RecommendationSection, _Mapping]]] = ...) -> None: ...

class GetBookOfTheWeekRequest(_message.Message):
    __slots__ = ("language",)
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    language: str
    def __init__(self, language: _Optional[str] = ...) -> None: ...

class BookOfTheWeekAuthor(_message.Message):
    __slots__ = ("author_id", "name", "slug")
    AUTHOR_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    author_id: int
    name: str
    slug: str
    def __init__(self, author_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ...) -> None: ...

class BookOfTheWeekCategory(_message.Message):
    __slots__ = ("genre_id", "name", "slug")
    GENRE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    genre_id: int
    name: str
    slug: str
    def __init__(self, genre_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ...) -> None: ...

class BookOfTheWeekResponse(_message.Message):
    __slots__ = ("book_id", "title", "slug", "language", "primary_cover_url", "first_sentence", "weighted_avg_rating", "rating_count", "authors", "categories")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    PRIMARY_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    FIRST_SENTENCE_FIELD_NUMBER: _ClassVar[int]
    WEIGHTED_AVG_RATING_FIELD_NUMBER: _ClassVar[int]
    RATING_COUNT_FIELD_NUMBER: _ClassVar[int]
    AUTHORS_FIELD_NUMBER: _ClassVar[int]
    CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    book_id: int
    title: str
    slug: str
    language: str
    primary_cover_url: str
    first_sentence: str
    weighted_avg_rating: float
    rating_count: int
    authors: _containers.RepeatedCompositeFieldContainer[BookOfTheWeekAuthor]
    categories: _containers.RepeatedCompositeFieldContainer[BookOfTheWeekCategory]
    def __init__(self, book_id: _Optional[int] = ..., title: _Optional[str] = ..., slug: _Optional[str] = ..., language: _Optional[str] = ..., primary_cover_url: _Optional[str] = ..., first_sentence: _Optional[str] = ..., weighted_avg_rating: _Optional[float] = ..., rating_count: _Optional[int] = ..., authors: _Optional[_Iterable[_Union[BookOfTheWeekAuthor, _Mapping]]] = ..., categories: _Optional[_Iterable[_Union[BookOfTheWeekCategory, _Mapping]]] = ...) -> None: ...
