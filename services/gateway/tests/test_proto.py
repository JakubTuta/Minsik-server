import app.proto.books_pb2
import app.utils.proto


def test_message_to_dict_keeps_int64_native():
    message = app.proto.books_pb2.AuthorInfo(author_id=2**53 + 1, name="Frank")

    result = app.utils.proto.message_to_dict(message)

    assert result["author_id"] == 2**53 + 1
    assert isinstance(result["author_id"], int)


def test_message_to_dict_unset_optional_is_none_and_set_zero_is_kept():
    unset = app.proto.books_pb2.SeriesInfo(series_id=1)
    zero = app.proto.books_pb2.SeriesInfo(series_id=1, total_books=0)

    assert app.utils.proto.message_to_dict(unset)["total_books"] is None
    assert app.utils.proto.message_to_dict(zero)["total_books"] == 0


def test_message_to_dict_unset_non_optional_scalar_keeps_its_default():
    result = app.utils.proto.message_to_dict(app.proto.books_pb2.AuthorInfo())

    assert result["name"] == ""
    assert result["author_id"] == 0
    assert result["photo_url"] is None


def test_message_to_dict_unset_message_is_none():
    detail = app.proto.books_pb2.BookDetail()

    assert app.utils.proto.message_to_dict(detail)["series"] is None


def test_message_to_dict_recurses_into_repeated_messages_and_maps():
    detail = app.proto.books_pb2.BookDetail(
        authors=[app.proto.books_pb2.AuthorInfo(author_id=1, name="A")],
        series=app.proto.books_pb2.SeriesInfo(series_id=3, total_books=4),
        sub_rating_stats={"pacing": app.proto.books_pb2.SubRatingStat(avg=4.5, count=2)},
        rating_distribution={"4.5": 3},
        external_ids={"goodreads": "9"},
    )

    result = app.utils.proto.message_to_dict(detail)

    assert result["authors"] == [
        {"author_id": 1, "name": "A", "slug": "", "photo_url": None}
    ]
    assert result["series"]["total_books"] == 4
    assert result["sub_rating_stats"] == {"pacing": {"avg": 4.5, "count": 2}}
    assert result["rating_distribution"] == {"4.5": 3}
    assert result["external_ids"] == {"goodreads": "9"}


def test_constructing_a_message_with_none_leaves_the_field_unset():
    message = app.proto.books_pb2.BookDetail(fallback_description=None)

    assert not message.HasField("fallback_description")
