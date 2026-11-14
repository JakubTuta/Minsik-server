import datetime
import types

import app.grpc.server


def user(**overrides: object) -> types.SimpleNamespace:
    row = types.SimpleNamespace(
        user_id=1,
        email="a@example.com",
        username="alice",
        display_name="",
        avatar_url=None,
        bio="",
        role="user",
        is_active=True,
        created_at=datetime.datetime(2026, 1, 1),
        preferred_language="",
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_empty_profile_fields_are_left_unset() -> None:
    message = app.grpc.server._build_user_message(user())

    for field in ("display_name", "avatar_url", "bio"):
        assert not message.HasField(field), field


def test_set_profile_fields_are_carried() -> None:
    message = app.grpc.server._build_user_message(user(display_name="Alice", bio="Hi"))

    assert message.display_name == "Alice"
    assert message.bio == "Hi"
    assert not message.HasField("avatar_url")


def test_preferred_language_defaults_to_english() -> None:
    assert app.grpc.server._build_user_message(user()).preferred_language == "en"
