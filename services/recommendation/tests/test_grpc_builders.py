import typing

import app.grpc.server


def book_item(**overrides: typing.Any) -> typing.Dict[str, typing.Any]:
    item: typing.Dict[str, typing.Any] = {
        "book_id": 1,
        "title": "Dune",
        "slug": "dune",
        "language": "en",
        "primary_cover_url": "",
        "author_names": [],
        "author_slugs": [],
        "avg_rating": "4.50",
        "rating_count": 3,
        "score": 1.0,
    }
    item.update(overrides)
    return item


def test_book_item_leaves_empty_optional_fields_unset() -> None:
    message = app.grpc.server._dict_to_book_item(book_item(work_id=""))

    assert not message.HasField("work_id")
    assert not message.HasField("primary_cover_url")


def test_book_item_carries_set_optional_fields_and_a_numeric_rating() -> None:
    message = app.grpc.server._dict_to_book_item(
        book_item(work_id="OL1W", primary_cover_url="https://example.com/c.jpg")
    )

    assert message.work_id == "OL1W"
    assert message.primary_cover_url == "https://example.com/c.jpg"
    assert message.avg_rating == 4.5


def test_author_item_leaves_a_missing_photo_unset_and_defaults_the_rating() -> None:
    message = app.grpc.server._dict_to_author_item(
        {
            "author_id": 1,
            "name": "Frank",
            "slug": "frank",
            "photo_url": None,
            "book_count": 2,
            "score": 1.0,
        }
    )

    assert not message.HasField("photo_url")
    assert message.avg_rating == 0.0


def test_section_and_list_response_use_the_shared_key_field() -> None:
    section = app.grpc.server._dict_to_section(
        {"section_key": "similar", "display_name": "Similar", "total": 0}
    )
    listing = app.grpc.server._dict_to_list_response(
        {"category": "most_read", "display_name": "Most read", "total": 0}
    )

    assert section.key == "similar"
    assert listing.key == "most_read"
