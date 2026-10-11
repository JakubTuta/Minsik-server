import datetime

import app.data.genre_synonyms
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
        ("Foo Tom 3", "Foo", 3.0),
        ("Foo, Tome 2", "Foo", 2.0),
        ("Foo Band 4", "Foo", 4.0),
        ("Foo Bd. 5", "Foo", 5.0),
        ("Foo, Book One", "Foo", 1.0),
        ("Foo Księga 7", "Foo", 7.0),
        ("Harry Pootter,", "Harry Pootter", None),
        ("A song of ice and fire ;", "A song of ice and fire", None),
    ],
)
def test_parse_series_descriptor_cleans_name(raw, expected_name, expected_position):
    result = app.utils.parse_series_descriptor(raw)
    assert result["name"] == expected_name
    assert result["position"] == expected_position


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1937", datetime.date(1937, 1, 1)),
        ("September 21, 1937", datetime.date(1937, 9, 21)),
        ("Sep 1937", datetime.date(1937, 9, 1)),
        ("1937-09-21", datetime.date(1937, 9, 21)),
        ("March 5", None),
        ("12:30", None),
        ("unknown", None),
        ("not a date", None),
        ("", None),
    ],
)
def test_parse_date_never_invents_a_year(raw, expected):
    assert app.utils.parse_date(raw) == expected


def test_clean_description_strips_trailing_metadata_headings():
    raw = "A hobbit leaves home.\n**Also contained in:** The Lord of the Rings\nmore"

    assert app.utils.clean_description(raw) == "A hobbit leaves home."


def test_clean_description_removes_emphasis_markers_but_keeps_identifiers():
    raw = "A **bold** and _slanted_ tale; set in snake_case_land, 2 * 3 * 4."

    assert (
        app.utils.clean_description(raw)
        == "A bold and slanted tale; set in snake_case_land, 2 * 3 * 4."
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("978-0-261-10235-4", "9780261102354"),
        ("0306406152", "0306406152"),
        ("080442957x", "080442957X"),
        ("9780261102355", None),
        ("0261102358", None),
        ("12345", None),
        (None, None),
        (9780261102354, None),
    ],
)
def test_normalize_isbn_keeps_only_valid_checksums(raw, expected):
    assert app.utils.normalize_isbn(raw) == expected


def test_normalize_isbns_deduplicates_and_drops_invalid():
    values = ["0306406152", "0-306-40615-2", "bad", "9780306406157"]

    assert app.utils.normalize_isbns(values) == ["0306406152", "9780306406157"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("English literature", "literature"),
        ("American novels", "novels"),
        ("Fiction, Fantasy", "Fantasy"),
        ("Science fiction -- Fiction", "Science fiction"),
        ("Fantasy (genre)", "Fantasy"),
        ("Novels", "Novels"),
    ],
)
def test_strip_genre_noise_handles_chained_qualifiers(raw, expected):
    assert app.data.genre_synonyms.strip_genre_noise(raw) == expected
