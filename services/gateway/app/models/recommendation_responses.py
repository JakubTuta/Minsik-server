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
    avg_rating: typing.Optional[str] = None
    rating_count: int
    score: float


class RecommendationAuthorItemSchema(pydantic.BaseModel):
    author_id: int
    name: str
    slug: str
    photo_url: typing.Optional[str] = None
    book_count: int
    score: float


class RecommendationListData(pydantic.BaseModel):
    category: str = pydantic.Field(description="Category key (e.g. 'most_read')")
    display_name: str = pydantic.Field(description="Human-readable category name")
    item_type: str = pydantic.Field(description="'book' or 'author'")
    book_items: typing.Optional[typing.List[RecommendationBookItemSchema]] = None
    author_items: typing.Optional[typing.List[RecommendationAuthorItemSchema]] = None
    total: int = pydantic.Field(description="Total items in the full cached list (before pagination)")


class RecommendationListResponse(pydantic.BaseModel):
    success: bool = True
    data: RecommendationListData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class HomePageData(pydantic.BaseModel):
    categories: typing.List[RecommendationListData]


class HomePageResponse(pydantic.BaseModel):
    success: bool = True
    data: HomePageData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class CategoryInfoSchema(pydantic.BaseModel):
    category: str
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
