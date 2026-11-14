import datetime
import types
import typing

import app.grpc.server
import app.proto.user_data_pb2


def rating_row(**overrides: typing.Any) -> types.SimpleNamespace:
    row = types.SimpleNamespace(
        rating_id=1,
        user_id=2,
        book_id=3,
        overall_rating=4.5,
        review_text="",
        pacing=None,
        emotional_impact=None,
        intellectual_depth=None,
        writing_quality=None,
        rereadability=None,
        readability=None,
        plot_complexity=None,
        humor=None,
        created_at=datetime.datetime(2026, 1, 1),
        updated_at=datetime.datetime(2026, 1, 1),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_rating_leaves_missing_sub_ratings_and_review_unset() -> None:
    message = app.grpc.server._rating_to_proto(rating_row(humor=0))

    assert message.HasField("humor")
    assert message.humor == 0.0
    assert not message.HasField("pacing")
    assert not message.HasField("review_text")
    assert not message.HasField("book_series_name")


def test_rating_carries_set_optional_values() -> None:
    message = app.grpc.server._rating_to_proto(
        rating_row(review_text="Great", pacing=3.5), series_name="Dune"
    )

    assert message.review_text == "Great"
    assert message.pacing == 3.5
    assert message.book_series_name == "Dune"


def test_bookshelf_and_comment_leave_empty_metadata_unset() -> None:
    comment = app.grpc.server._comment_to_proto(
        types.SimpleNamespace(
            comment_id=1,
            user_id=2,
            book_id=3,
            body="x",
            is_spoiler=False,
            created_at=None,
            updated_at=None,
        )
    )

    for field in ("book_title", "book_cover_url", "book_series_name", "book_series_slug"):
        assert not comment.HasField(field), field


def test_cached_entries_written_before_the_proto_change_still_read_as_null() -> None:
    entry = {
        "bookshelf_id": 1,
        "book_slug": "dune",
        "book_series_name": "",
        "book_series_slug": "",
    }

    bookshelf = app.grpc.server._bookshelf_from_entry(entry)

    assert bookshelf.book_slug == "dune"
    assert not bookshelf.HasField("book_series_name")
    assert not bookshelf.HasField("book_series_slug")


def test_cached_comment_entries_null_their_empty_metadata() -> None:
    comment = app.grpc.server._comment_from_entry(
        {"comment_id": 1, "body": "x", "book_title": "", "book_cover_url": "u"}
    )

    assert not comment.HasField("book_title")
    assert comment.book_cover_url == "u"


def test_comment_with_rating_nests_the_rating_only_when_the_author_rated() -> None:
    base = {
        "comment_id": 1,
        "user_id": 2,
        "book_id": 3,
        "body": "x",
        "is_spoiler": False,
        "created_at": None,
        "updated_at": None,
        "username": "alice",
        "review_text": None,
        "pacing": None,
        "emotional_impact": None,
        "intellectual_depth": None,
        "writing_quality": None,
        "rereadability": None,
        "readability": None,
        "plot_complexity": None,
        "humor": 3.0,
    }

    unrated = app.grpc.server._row_to_comment_with_rating(
        types.SimpleNamespace(overall_rating=None, **base), "dune"
    )
    rated = app.grpc.server._row_to_comment_with_rating(
        types.SimpleNamespace(overall_rating=4.5, **base), "dune"
    )

    assert not unrated.HasField("rating")
    assert rated.HasField("rating")
    assert rated.rating.overall_rating == 4.5
    assert rated.rating.humor == 3.0
    assert not rated.rating.HasField("pacing")


def test_profile_overview_sets_reading_now_only_when_present() -> None:
    absent = app.grpc.server._profile_overview_to_proto({"user": {"user_id": 1}})
    present = app.grpc.server._profile_overview_to_proto(
        {"user": {"user_id": 1}, "reading_now": {"book_slug": "dune"}}
    )

    assert not absent.HasField("reading_now")
    assert present.reading_now.book_slug == "dune"


def test_year_in_review_marks_books_and_ratings_by_presence() -> None:
    review = app.grpc.server._year_in_review_to_proto(
        {
            "year": 2026,
            "longest_book": {"book_slug": "dune", "my_rating": 0.0},
            "shortest_book": {"book_slug": "ubik"},
            "rating_distribution_json": '{"4.5": 2}',
        }
    )

    assert review.HasField("longest_book")
    assert not review.HasField("first_finished")
    assert review.longest_book.HasField("my_rating")
    assert not review.shortest_book.HasField("my_rating")
    assert dict(review.rating_distribution) == {"4.5": 2}


def test_rating_distribution_tolerates_missing_or_broken_json() -> None:
    assert app.grpc.server._rating_distribution(None) == {}
    assert app.grpc.server._rating_distribution("not json") == {}
    assert app.grpc.server._rating_distribution('{"5.0": 1}') == {"5.0": 1}
