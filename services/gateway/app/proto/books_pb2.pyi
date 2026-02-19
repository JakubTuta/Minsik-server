from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

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
    __slots__ = ("type", "id", "title", "slug", "cover_url", "authors", "relevance_score", "view_count", "author_slugs", "series_slug")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    COVER_URL_FIELD_NUMBER: _ClassVar[int]
    AUTHORS_FIELD_NUMBER: _ClassVar[int]
    RELEVANCE_SCORE_FIELD_NUMBER: _ClassVar[int]
    VIEW_COUNT_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_SLUGS_FIELD_NUMBER: _ClassVar[int]
    SERIES_SLUG_FIELD_NUMBER: _ClassVar[int]
    type: str
    id: int
    title: str
    slug: str
    cover_url: str
    authors: _containers.RepeatedScalarFieldContainer[str]
    relevance_score: float
    view_count: int
    author_slugs: _containers.RepeatedScalarFieldContainer[str]
    series_slug: str
    def __init__(self, type: _Optional[str] = ..., id: _Optional[int] = ..., title: _Optional[str] = ..., slug: _Optional[str] = ..., cover_url: _Optional[str] = ..., authors: _Optional[_Iterable[str]] = ..., relevance_score: _Optional[float] = ..., view_count: _Optional[int] = ..., author_slugs: _Optional[_Iterable[str]] = ..., series_slug: _Optional[str] = ...) -> None: ...

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

class SubRatingStat(_message.Message):
    __slots__ = ("avg", "count")
    AVG_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    avg: str
    count: int
    def __init__(self, avg: _Optional[str] = ..., count: _Optional[int] = ...) -> None: ...

class BookDetail(_message.Message):
    __slots__ = ("book_id", "title", "slug", "description", "language", "original_publication_year", "formats", "primary_cover_url", "cover_history", "rating_count", "avg_rating", "view_count", "last_viewed_at", "authors", "genres", "open_library_id", "google_books_id", "created_at", "updated_at", "series", "series_position", "sub_rating_stats", "isbn", "publisher", "number_of_pages", "external_ids", "ol_rating_count", "ol_avg_rating", "ol_want_to_read_count", "ol_currently_reading_count", "ol_already_read_count")
    class SubRatingStatsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubRatingStat
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[SubRatingStat, _Mapping]] = ...) -> None: ...
    class ExternalIdsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
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
    SERIES_FIELD_NUMBER: _ClassVar[int]
    SERIES_POSITION_FIELD_NUMBER: _ClassVar[int]
    SUB_RATING_STATS_FIELD_NUMBER: _ClassVar[int]
    ISBN_FIELD_NUMBER: _ClassVar[int]
    PUBLISHER_FIELD_NUMBER: _ClassVar[int]
    NUMBER_OF_PAGES_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_IDS_FIELD_NUMBER: _ClassVar[int]
    OL_RATING_COUNT_FIELD_NUMBER: _ClassVar[int]
    OL_AVG_RATING_FIELD_NUMBER: _ClassVar[int]
    OL_WANT_TO_READ_COUNT_FIELD_NUMBER: _ClassVar[int]
    OL_CURRENTLY_READING_COUNT_FIELD_NUMBER: _ClassVar[int]
    OL_ALREADY_READ_COUNT_FIELD_NUMBER: _ClassVar[int]
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
    series: SeriesInfo
    series_position: str
    sub_rating_stats: _containers.MessageMap[str, SubRatingStat]
    isbn: _containers.RepeatedScalarFieldContainer[str]
    publisher: str
    number_of_pages: int
    external_ids: _containers.ScalarMap[str, str]
    ol_rating_count: int
    ol_avg_rating: str
    ol_want_to_read_count: int
    ol_currently_reading_count: int
    ol_already_read_count: int
    def __init__(self, book_id: _Optional[int] = ..., title: _Optional[str] = ..., slug: _Optional[str] = ..., description: _Optional[str] = ..., language: _Optional[str] = ..., original_publication_year: _Optional[int] = ..., formats: _Optional[_Iterable[str]] = ..., primary_cover_url: _Optional[str] = ..., cover_history: _Optional[_Iterable[_Union[CoverHistory, _Mapping]]] = ..., rating_count: _Optional[int] = ..., avg_rating: _Optional[str] = ..., view_count: _Optional[int] = ..., last_viewed_at: _Optional[str] = ..., authors: _Optional[_Iterable[_Union[AuthorInfo, _Mapping]]] = ..., genres: _Optional[_Iterable[_Union[GenreInfo, _Mapping]]] = ..., open_library_id: _Optional[str] = ..., google_books_id: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., series: _Optional[_Union[SeriesInfo, _Mapping]] = ..., series_position: _Optional[str] = ..., sub_rating_stats: _Optional[_Mapping[str, SubRatingStat]] = ..., isbn: _Optional[_Iterable[str]] = ..., publisher: _Optional[str] = ..., number_of_pages: _Optional[int] = ..., external_ids: _Optional[_Mapping[str, str]] = ..., ol_rating_count: _Optional[int] = ..., ol_avg_rating: _Optional[str] = ..., ol_want_to_read_count: _Optional[int] = ..., ol_currently_reading_count: _Optional[int] = ..., ol_already_read_count: _Optional[int] = ...) -> None: ...

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

class SeriesInfo(_message.Message):
    __slots__ = ("series_id", "name", "slug", "total_books")
    SERIES_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    TOTAL_BOOKS_FIELD_NUMBER: _ClassVar[int]
    series_id: int
    name: str
    slug: str
    total_books: int
    def __init__(self, series_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., total_books: _Optional[int] = ...) -> None: ...

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
    __slots__ = ("author_id", "name", "slug", "bio", "birth_date", "death_date", "photo_url", "view_count", "last_viewed_at", "books_count", "open_library_id", "created_at", "updated_at", "birth_place", "nationality", "book_categories", "books_avg_rating", "books_total_ratings", "books_total_views", "wikidata_id", "wikipedia_url", "remote_ids", "alternate_names")
    class RemoteIdsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
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
    BIRTH_PLACE_FIELD_NUMBER: _ClassVar[int]
    NATIONALITY_FIELD_NUMBER: _ClassVar[int]
    BOOK_CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    BOOKS_AVG_RATING_FIELD_NUMBER: _ClassVar[int]
    BOOKS_TOTAL_RATINGS_FIELD_NUMBER: _ClassVar[int]
    BOOKS_TOTAL_VIEWS_FIELD_NUMBER: _ClassVar[int]
    WIKIDATA_ID_FIELD_NUMBER: _ClassVar[int]
    WIKIPEDIA_URL_FIELD_NUMBER: _ClassVar[int]
    REMOTE_IDS_FIELD_NUMBER: _ClassVar[int]
    ALTERNATE_NAMES_FIELD_NUMBER: _ClassVar[int]
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
    birth_place: str
    nationality: str
    book_categories: _containers.RepeatedScalarFieldContainer[str]
    books_avg_rating: str
    books_total_ratings: int
    books_total_views: int
    wikidata_id: str
    wikipedia_url: str
    remote_ids: _containers.ScalarMap[str, str]
    alternate_names: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, author_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., bio: _Optional[str] = ..., birth_date: _Optional[str] = ..., death_date: _Optional[str] = ..., photo_url: _Optional[str] = ..., view_count: _Optional[int] = ..., last_viewed_at: _Optional[str] = ..., books_count: _Optional[int] = ..., open_library_id: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., birth_place: _Optional[str] = ..., nationality: _Optional[str] = ..., book_categories: _Optional[_Iterable[str]] = ..., books_avg_rating: _Optional[str] = ..., books_total_ratings: _Optional[int] = ..., books_total_views: _Optional[int] = ..., wikidata_id: _Optional[str] = ..., wikipedia_url: _Optional[str] = ..., remote_ids: _Optional[_Mapping[str, str]] = ..., alternate_names: _Optional[_Iterable[str]] = ...) -> None: ...

class AuthorDetailResponse(_message.Message):
    __slots__ = ("author",)
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    author: AuthorDetail
    def __init__(self, author: _Optional[_Union[AuthorDetail, _Mapping]] = ...) -> None: ...

class GetAuthorBooksRequest(_message.Message):
    __slots__ = ("author_slug", "limit", "offset", "sort_by", "order")
    AUTHOR_SLUG_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    SORT_BY_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    author_slug: str
    limit: int
    offset: int
    sort_by: str
    order: str
    def __init__(self, author_slug: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ..., sort_by: _Optional[str] = ..., order: _Optional[str] = ...) -> None: ...

class BookSummary(_message.Message):
    __slots__ = ("book_id", "title", "slug", "description", "original_publication_year", "primary_cover_url", "rating_count", "avg_rating", "view_count", "genres", "series", "series_position")
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
    SERIES_FIELD_NUMBER: _ClassVar[int]
    SERIES_POSITION_FIELD_NUMBER: _ClassVar[int]
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
    series: SeriesInfo
    series_position: str
    def __init__(self, book_id: _Optional[int] = ..., title: _Optional[str] = ..., slug: _Optional[str] = ..., description: _Optional[str] = ..., original_publication_year: _Optional[int] = ..., primary_cover_url: _Optional[str] = ..., rating_count: _Optional[int] = ..., avg_rating: _Optional[str] = ..., view_count: _Optional[int] = ..., genres: _Optional[_Iterable[_Union[GenreInfo, _Mapping]]] = ..., series: _Optional[_Union[SeriesInfo, _Mapping]] = ..., series_position: _Optional[str] = ...) -> None: ...

class BooksListResponse(_message.Message):
    __slots__ = ("books", "total_count")
    BOOKS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    books: _containers.RepeatedCompositeFieldContainer[BookSummary]
    total_count: int
    def __init__(self, books: _Optional[_Iterable[_Union[BookSummary, _Mapping]]] = ..., total_count: _Optional[int] = ...) -> None: ...

class GetSeriesRequest(_message.Message):
    __slots__ = ("slug",)
    SLUG_FIELD_NUMBER: _ClassVar[int]
    slug: str
    def __init__(self, slug: _Optional[str] = ...) -> None: ...

class SeriesDetail(_message.Message):
    __slots__ = ("series_id", "name", "slug", "description", "total_books", "view_count", "last_viewed_at", "created_at", "updated_at")
    SERIES_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    TOTAL_BOOKS_FIELD_NUMBER: _ClassVar[int]
    VIEW_COUNT_FIELD_NUMBER: _ClassVar[int]
    LAST_VIEWED_AT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    series_id: int
    name: str
    slug: str
    description: str
    total_books: int
    view_count: int
    last_viewed_at: str
    created_at: str
    updated_at: str
    def __init__(self, series_id: _Optional[int] = ..., name: _Optional[str] = ..., slug: _Optional[str] = ..., description: _Optional[str] = ..., total_books: _Optional[int] = ..., view_count: _Optional[int] = ..., last_viewed_at: _Optional[str] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ...) -> None: ...

class SeriesDetailResponse(_message.Message):
    __slots__ = ("series",)
    SERIES_FIELD_NUMBER: _ClassVar[int]
    series: SeriesDetail
    def __init__(self, series: _Optional[_Union[SeriesDetail, _Mapping]] = ...) -> None: ...

class GetSeriesBooksRequest(_message.Message):
    __slots__ = ("series_slug", "limit", "offset")
    SERIES_SLUG_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    series_slug: str
    limit: int
    offset: int
    def __init__(self, series_slug: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...
