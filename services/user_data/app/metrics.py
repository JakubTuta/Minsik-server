import opentelemetry.metrics as metrics_api

_meter = metrics_api.get_meter(__name__)
_ratings_upserted = _meter.create_counter(
    "ratings_upserted",
    description="Ratings created or updated, tagged by whether a review text was submitted",
)
_bookshelf_upserted = _meter.create_counter(
    "bookshelf_upserted",
    description="Bookshelf entries created or updated, tagged by target status",
)
_comments_created = _meter.create_counter(
    "comments_created",
    description="Comments posted, tagged by spoiler flag",
)


def _flag(value: bool) -> str:
    return "true" if value else "false"


def record_rating(has_review: bool) -> None:
    _ratings_upserted.add(1, {"has_review": _flag(has_review)})


def record_bookshelf(status: str) -> None:
    _bookshelf_upserted.add(1, {"status": status})


def record_comment(is_spoiler: bool) -> None:
    _comments_created.add(1, {"is_spoiler": _flag(is_spoiler)})
