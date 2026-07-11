import app.utils
import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Harry Pootter,", "Harry Pootter"),
        ("A song of ice and fire ;", "A song of ice and fire"),
        ("Do Androids Dream of Electric Sheep?", "Do Androids Dream of Electric Sheep?"),
        (".hack", ".hack"),
        ("  The Hobbit  ", "The Hobbit"),
        ("Foo -- Bar", "Foo -- Bar"),
        ("Multiple   internal   spaces", "Multiple internal spaces"),
        (",,,;;;", ",,,;;;"),
        ("", ""),
        (None, None),
    ],
)
def test_clean_name(raw, expected):
    assert app.utils.clean_name(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "Harry Pootter,",
        "A song of ice and fire ;",
        "Do Androids Dream of Electric Sheep?",
        ".hack",
        "  The Hobbit  ",
        "Café society",
    ],
)
def test_clean_name_preserves_slug(raw):
    cleaned = app.utils.clean_name(raw) or raw
    assert app.utils.slugify(cleaned) == app.utils.slugify(raw)


@pytest.mark.unit
def test_clean_name_max_length():
    assert app.utils.clean_name("Harry Pootter,", max_length=5) == "Harry"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected_name,expected_position",
    [
        ("Foo (3)", "Foo", 3.0),
        ("Foo #3", "Foo", 3.0),
        ("Foo, 3", "Foo", 3.0),
        ("Foo Book 3", "Foo", 3.0),
        ("Harry Pootter,", "Harry Pootter", None),
        ("A song of ice and fire ;", "A song of ice and fire", None),
    ],
)
def test_parse_series_descriptor_cleans_name(raw, expected_name, expected_position):
    result = app.utils.parse_series_descriptor(raw)
    assert result["name"] == expected_name
    assert result["position"] == expected_position
