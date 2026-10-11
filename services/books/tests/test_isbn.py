import types
from unittest.mock import AsyncMock, MagicMock

import app.services._isbn as isbn
import app.services.book_service as book_service
import pytest


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("978-0-261-10235-4", "9780261102354"),
        ("0 261 10235 5", None),
        ("0261102358", None),
        ("0-306-40615-2", "0306406152"),
        ("080442957X", "080442957X"),
        ("080442957x", "080442957X"),
        ("9780261102355", None),
        ("12345", None),
        ("", None),
        ("not an isbn", None),
    ],
)
def test_normalise_accepts_only_valid_isbns(raw: str, expected: str | None) -> None:
    assert isbn.normalise(raw) == expected


def test_both_forms_of_an_isbn_are_searched() -> None:
    assert isbn.variants("0306406152") == ["0306406152", "9780306406157"]
    assert isbn.variants("9780306406157") == ["9780306406157", "0306406152"]


def test_an_isbn13_without_a_ten_digit_form_has_one_variant() -> None:
    assert isbn.variants("9791034328000") == ["9791034328000"]


@pytest.mark.asyncio
async def test_lookup_searches_both_forms_and_returns_the_readers_edition() -> None:
    row = types.SimpleNamespace(slug="hobbit-pl", language="pl", title="Hobbit", work_id="OL1W")
    result = MagicMock()
    result.first.return_value = row
    session = AsyncMock()
    session.execute.return_value = result

    found = await book_service.lookup_by_isbn(session, "0-306-40615-2", "pl")

    assert found == {"slug": "hobbit-pl", "language": "pl", "title": "Hobbit", "work_id": "OL1W"}
    params = session.execute.call_args.args[1]
    assert params == {"isbns": ["0306406152", "9780306406157"], "language": "pl"}


@pytest.mark.asyncio
async def test_lookup_of_an_invalid_isbn_never_touches_the_database() -> None:
    session = AsyncMock()

    assert await book_service.lookup_by_isbn(session, "9780306406158", "en") is None
    session.execute.assert_not_called()
