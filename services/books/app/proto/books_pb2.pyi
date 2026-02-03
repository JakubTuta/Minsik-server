from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SearchRequest(_message.Message):
    __slots__ = ("query", "limit", "offset", "type_filter")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    TYPE_FILTER_FIELD_NUMBER: _ClassVar[int]
    query: str
    limit: int
    offset: int
    type_filter: str
    def __init__(self, query: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., type_filter: _Optional[str] = ...) -> None: ...

class SearchResult(_message.Message):
    __slots__ = ("type", "id", "title", "slug", "cover_url", "authors", "relevance_score", "view_count")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    COVER_URL_FIELD_NUMBER: _ClassVar[int]
    AUTHORS_FIELD_NUMBER: _ClassVar[int]
    RELEVANCE_SCORE_FIELD_NUMBER: _ClassVar[int]
    VIEW_COUNT_FIELD_NUMBER: _ClassVar[int]
    type: str
    id: int
    title: str
    slug: str
    cover_url: str
    authors: _containers.RepeatedScalarFieldContainer[str]
    relevance_score: float
    view_count: int
    def __init__(self, type: _Optional[str] = ..., id: _Optional[int] = ..., title: _Optional[str] = ..., slug: _Optional[str] = ..., cover_url: _Optional[str] = ..., authors: _Optional[_Iterable[str]] = ..., relevance_score: _Optional[float] = ..., view_count: _Optional[int] = ...) -> None: ...

class SearchResponse(_message.Message):
    __slots__ = ("results", "total_count")
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[SearchResult]
    total_count: int
    def __init__(self, results: _Optional[_Iterable[_Union[SearchResult, _Mapping]]] = ..., total_count: _Optional[int] = ...) -> None: ...

class GetBookRequest(_message.Message):
    __slots__ = ("slug",)
    SLUG_FIELD_NUMBER: _ClassVar[int]
    slug: str
    def __init__(self, slug: _Optional[str] = ...) -> None: ...

class BookDetail(_message.Message):
    __slots__ = ("book_id", "title", "slug", "description", "language", "original_publication_year", "formats", "primary_cover_url", "cover_history", "rating_count", "avg_rating", "view_count", "last_viewed_at", "authors", "genres", "open_library_id", "google_books_id", "created_at", "updated_at")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_PUBLICATION_YEAR_FIELD_NUMBER: _ClassVar[int]
    FORMATS_FIELD_NUMBER: _ClassVar[int]
    PRIMARY_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    COVER_HISTORY_FIELD_NUMBER: _ClassVar[int]
    RATING_COUNT_FIELD_NUMBER: _ClassVar[int]
    AVG_RATING_FIELD_NUMBER: _ClassVar[int]
    VIEW_COUNT_FIELD_NUMBER: _ClassVar[int]
    LAST_VIEWED_AT_FIELD_NUMBER: _ClassVar[int]
    AUTHORS_FIELD_NUMBER: _ClassVar[int]
    GENRES_FIELD_NUMBER: _ClassVar[int]
    OPEN_LIBRARY_ID_FIELD_NUMBER: _ClassVar[int]
    GOOGLE_BOOKS_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    book_id: int
    title: str
    slug: str
    description: str
    language: str
    original_publication_year: int
    formats: _containers.RepeatedScalarFieldContainer[str]
    primary_cover_url: str
    cover_history: _containers.RepeatedCompositeFieldContainer[CoverHistory]
    rating_count: int
    avg_rating: str
    view_count: int
    last_viewed_at: str
    authors: _containers.RepeatedCompositeFieldContainer[AuthorInfo]
    genres: _containers.RepeatedCompositeFieldContainer[GenreInfo]
    open_library_id: str
    google_books_id: str
    created_at: str
    updated_at: str
    def __init__(self, book_id: _Optional[int] = ..., title: _Optional[str] = ..., slug: _Optional[str] = ..., description: _Optional[str] = ..., language: _Optional[str] = ..., original_publication_year: _Optional[int] = ..., formats: _Optional[_Iterable[str]] = ..., primary_cover_url: _Optional[str] = ..., cover_history: _Optional[_Iterable[_Union[CoverHistory, _Mapping]]] = ..., rating_count: _Optional[int] = ..., avg_rating: _Optional[str] = ..., view_count: _Optional[int] = ..., last_viewed_at: _Optional[str] = ..., authors: _Optional[_Iterable[_Union[AuthorInfo, _Mapping]]] = ..., genres: _Optional[_Iterable[_Union[GenreInfo, _Mapping]]] = ..., open_library_id: _Optional[str] = ..., google_books_id: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ...) -> None: ...

class CoverHistory(_message.Message):
    __slots__ = ("url", "width", "size")
    URL_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    url: str
    width: int
    size: str
    def __init__(self, url: _Optional[str] = ..., width: _Optional[int] = ..., size: _Optional[str] = ...) -> None: ...

class AuthorInfo(_message.Message):
    __slots__ = ("author_id", "name", "slug", "photo_url")
    AUTHOR_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    PHOTO_URL_FIELD_NUMBER: _ClassVar[int]
    author_id: int
    name: str
    slug: str
    photo_url: str
    def __init__(self, author_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., photo_url: _Optional[str] = ...) -> None: ...

class GenreInfo(_message.Message):
    __slots__ = ("genre_id", "name", "slug")
    GENRE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    genre_id: int
    name: str
    slug: str
    def __init__(self, genre_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ...) -> None: ...

class BookDetailResponse(_message.Message):
    __slots__ = ("book",)
    BOOK_FIELD_NUMBER: _ClassVar[int]
    book: BookDetail
    def __init__(self, book: _Optional[_Union[BookDetail, _Mapping]] = ...) -> None: ...

class GetAuthorRequest(_message.Message):
    __slots__ = ("slug",)
    SLUG_FIELD_NUMBER: _ClassVar[int]
    slug: str
    def __init__(self, slug: _Optional[str] = ...) -> None: ...

class AuthorDetail(_message.Message):
    __slots__ = ("author_id", "name", "slug", "bio", "birth_date", "death_date", "photo_url", "view_count", "last_viewed_at", "books_count", "open_library_id", "created_at", "updated_at")
    AUTHOR_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    BIO_FIELD_NUMBER: _ClassVar[int]
    BIRTH_DATE_FIELD_NUMBER: _ClassVar[int]
    DEATH_DATE_FIELD_NUMBER: _ClassVar[int]
    PHOTO_URL_FIELD_NUMBER: _ClassVar[int]
    VIEW_COUNT_FIELD_NUMBER: _ClassVar[int]
    LAST_VIEWED_AT_FIELD_NUMBER: _ClassVar[int]
    BOOKS_COUNT_FIELD_NUMBER: _ClassVar[int]
    OPEN_LIBRARY_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    author_id: int
    name: str
    slug: str
    bio: str
    birth_date: str
    death_date: str
    photo_url: str
    view_count: int
    last_viewed_at: str
    books_count: int
    open_library_id: str
    created_at: str
    updated_at: str
    def __init__(self, author_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., bio: _Optional[str] = ..., birth_date: _Optional[str] = ..., death_date: _Optional[str] = ..., photo_url: _Optional[str] = ..., view_count: _Optional[int] = ..., last_viewed_at: _Optional[str] = ..., books_count: _Optional[int] = ..., open_library_id: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ...) -> None: ...

class AuthorDetailResponse(_message.Message):
    __slots__ = ("author",)
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    author: AuthorDetail
    def __init__(self, author: _Optional[_Union[AuthorDetail, _Mapping]] = ...) -> None: ...

class GetAuthorBooksRequest(_message.Message):
    __slots__ = ("author_slug", "limit", "offset")
    AUTHOR_SLUG_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    author_slug: str
    limit: int
    offset: int
    def __init__(self, author_slug: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class BookSummary(_message.Message):
    __slots__ = ("book_id", "title", "slug", "description", "original_publication_year", "primary_cover_url", "rating_count", "avg_rating", "view_count", "genres")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_PUBLICATION_YEAR_FIELD_NUMBER: _ClassVar[int]
    PRIMARY_COVER_URL_FIELD_NUMBER: _ClassVar[int]
    RATING_COUNT_FIELD_NUMBER: _ClassVar[int]
    AVG_RATING_FIELD_NUMBER: _ClassVar[int]
    VIEW_COUNT_FIELD_NUMBER: _ClassVar[int]
    GENRES_FIELD_NUMBER: _ClassVar[int]
    book_id: int
    title: str
    slug: str
    description: str
    original_publication_year: int
    primary_cover_url: str
    rating_count: int
    avg_rating: str
    view_count: int
    genres: _containers.RepeatedCompositeFieldContainer[GenreInfo]
    def __init__(self, book_id: _Optional[int] = ..., title: _Optional[str] = ..., slug: _Optional[str] = ..., description: _Optional[str] = ..., original_publication_year: _Optional[int] = ..., primary_cover_url: _Optional[str] = ..., rating_count: _Optional[int] = ..., avg_rating: _Optional[str] = ..., view_count: _Optional[int] = ..., genres: _Optional[_Iterable[_Union[GenreInfo, _Mapping]]] = ...) -> None: ...

class BooksListResponse(_message.Message):
    __slots__ = ("books", "total_count")
    BOOKS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    books: _containers.RepeatedCompositeFieldContainer[BookSummary]
    total_count: int
    def __init__(self, books: _Optional[_Iterable[_Union[BookSummary, _Mapping]]] = ..., total_count: _Optional[int] = ...) -> None: ...
