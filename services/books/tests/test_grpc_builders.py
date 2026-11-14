import typing

import app.grpc.server
import app.proto.books_pb2


def book_row(**overrides: typing.Any) -> typing.Dict[str, typing.Any]:
    row: typing.Dict[str, typing.Any] = {
        "book_id": 1,
        "title": "Dune",
        "slug": "dune",
        "description": "",
        "language": "en",
        "original_publication_year": 1965,
        "formats": [],
        "primary_cover_url": "",
        "rating_count": 3,
        "avg_rating": "4.25",
        "view_count": 0,
        "last_viewed_at": "",
        "authors": [{"author_id": 7, "name": "Frank", "slug": "frank", "photo_url": None}],
        "genres": [],
        "open_library_id": "",
        "google_books_id": "",
        "created_at": "2020-01-01",
        "updated_at": "2020-01-01",
    }
    row.update(overrides)
    return row


def test_detail_leaves_empty_optional_text_unset() -> None:
    detail = app.grpc.server._build_book_detail_proto(
        book_row(first_sentence="", fallback_description=None, fallback_language="")
    )

    assert not detail.HasField("first_sentence")
    assert not detail.HasField("fallback_description")
    assert not detail.HasField("fallback_language")


def test_detail_keeps_a_missing_author_photo_as_an_empty_string() -> None:
    detail = app.grpc.server._build_book_detail_proto(book_row())

    assert detail.authors[0].HasField("photo_url")
    assert detail.authors[0].photo_url == ""


def test_detail_ratings_are_numbers_and_series_position_is_optional() -> None:
    unset = app.grpc.server._build_book_detail_proto(book_row())
    zero = app.grpc.server._build_book_detail_proto(book_row(series_position="0.0"))

    assert unset.avg_rating == 4.25
    assert not unset.HasField("series_position")
    assert zero.HasField("series_position")
    assert zero.series_position == 0.0


def test_detail_rating_distribution_always_has_every_bucket() -> None:
    detail = app.grpc.server._build_book_detail_proto(
        book_row(rating_distribution={"4.5": 3})
    )

    assert set(detail.rating_distribution) == set(app.grpc.server.RATING_BUCKETS)
    assert detail.rating_distribution["4.5"] == 3
    assert detail.rating_distribution["1.0"] == 0


def test_summary_leaves_empty_values_unset_so_they_serialize_as_null() -> None:
    summary = app.grpc.server._build_book_summary_proto(
        {
            "book_id": 1,
            "title": "Dune",
            "slug": "dune",
            "rating_count": 0,
            "description": "",
            "original_publication_year": 0,
            "number_of_pages": 0,
            "series_position": "",
            "rarity": "",
            "authors": [{"author_id": 7, "name": "Frank", "slug": "frank", "photo_url": ""}],
        }
    )

    for field in (
        "description",
        "original_publication_year",
        "primary_cover_url",
        "number_of_pages",
        "series_position",
        "rarity",
        "language",
    ):
        assert not summary.HasField(field), field
    assert not summary.authors[0].HasField("photo_url")
    assert summary.avg_rating == 0.0


def test_summary_series_omits_the_total_book_count() -> None:
    summary = app.grpc.server._build_book_summary_proto(
        {
            "book_id": 1,
            "title": "Dune",
            "slug": "dune",
            "rating_count": 0,
            "series": {"series_id": 4, "name": "Dune", "slug": "dune"},
        }
    )

    assert summary.series.series_id == 4
    assert not summary.series.HasField("total_books")


def test_rating_helpers() -> None:
    assert app.grpc.server._rating(None) == 0.0
    assert app.grpc.server._rating("") == 0.0
    assert app.grpc.server._rating("4.50") == 4.5
    assert app.grpc.server._optional_rating(None) is None
    assert app.grpc.server._optional_rating("") is None
    assert app.grpc.server._optional_rating("0.0") == 0.0
