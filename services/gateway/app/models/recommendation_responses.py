import typing

import app.models.responses
import pydantic


class RecommendationBookItemSchema(pydantic.BaseModel):
    book_id: int
    title: str
    slug: str
    language: str
    primary_cover_url: typing.Optional[str] = None
    author_names: typing.List[str]
    author_slugs: typing.List[str]
    avg_rating: float = 0.0
    rating_count: int
    readers: int = 0
    score: float


class RecommendationAuthorItemSchema(pydantic.BaseModel):
    author_id: int
    name: str
    slug: str
    photo_url: typing.Optional[str] = None
    book_count: int
    avg_rating: float = 0.0
    readers: int = 0
    score: float


class RecommendationSectionData(pydantic.BaseModel):
    key: str = pydantic.Field(
        description="Section key (e.g. 'most_read', 'more_by_author')"
    )
    display_name: str = pydantic.Field(description="Human-readable label")
    item_type: str = pydantic.Field(description="'book' or 'author'")
    book_items: typing.Optional[typing.List[RecommendationBookItemSchema]] = None
    author_items: typing.Optional[typing.List[RecommendationAuthorItemSchema]] = None
    total: int = pydantic.Field(
        description="Total items in the full cached list (before pagination)"
    )


class RecommendationSectionResponse(pydantic.BaseModel):
    success: bool = True
    data: RecommendationSectionData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class HomePageData(pydantic.BaseModel):
    sections: typing.List[RecommendationSectionData]


class HomePageResponse(pydantic.BaseModel):
    success: bool = True
    data: HomePageData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class CategoryInfoSchema(pydantic.BaseModel):
    key: str
    display_name: str
    item_type: str


class AvailableCategoriesData(pydantic.BaseModel):
    categories: typing.List[CategoryInfoSchema]


class AvailableCategoriesResponse(pydantic.BaseModel):
    success: bool = True
    data: AvailableCategoriesData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class RefreshRecommendationsData(pydantic.BaseModel):
    success: bool
    message: str


class RefreshRecommendationsResponse(pydantic.BaseModel):
    success: bool = True
    data: RefreshRecommendationsData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class BookRecommendationsData(pydantic.BaseModel):
    book_id: int
    sections: typing.List[RecommendationSectionData]


class BookRecommendationsResponse(pydantic.BaseModel):
    success: bool = True
    data: BookRecommendationsData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class AuthorRecommendationsData(pydantic.BaseModel):
    author_id: int
    sections: typing.List[RecommendationSectionData]


class AuthorRecommendationsResponse(pydantic.BaseModel):
    success: bool = True
    data: AuthorRecommendationsData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class SeriesRecommendationsData(pydantic.BaseModel):
    series_id: int
    sections: typing.List[RecommendationSectionData]


class SeriesRecommendationsResponse(pydantic.BaseModel):
    success: bool = True
    data: SeriesRecommendationsData
    error: typing.Optional[app.models.responses.ErrorDetail] = None
