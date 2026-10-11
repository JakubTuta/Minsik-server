import types
from unittest.mock import AsyncMock, MagicMock

import app.services.author_service as author_service
import app.services.book_service as book_service
import app.services.series_service as series_service
import pytest


def session_returning(row) -> AsyncMock:
    result = MagicMock()
    result.first.return_value = row
    session = AsyncMock()
    session.execute.return_value = result
    return session


@pytest.mark.asyncio
async def test_a_book_with_its_own_description_offers_no_fallback() -> None:
    data = {"description": "Opis po polsku."}
    session = session_returning(None)

    await book_service._attach_description_fallback(session, data, "OL1W", 5)

    assert (data["fallback_description"], data["fallback_language"]) == ("", "")
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_a_book_without_a_description_gets_the_siblings_labelled() -> None:
    data = {"description": "  "}
    sibling = types.SimpleNamespace(description="English blurb.", language="en")

    await book_service._attach_description_fallback(session_returning(sibling), data, "OL1W", 5)

    assert (data["fallback_description"], data["fallback_language"]) == ("English blurb.", "en")


@pytest.mark.asyncio
async def test_a_book_without_any_sibling_description_stays_empty() -> None:
    data = {"description": ""}

    await book_service._attach_description_fallback(session_returning(None), data, "OL1W", 5)

    assert data["fallback_description"] == ""


@pytest.mark.asyncio
async def test_an_author_in_the_canonical_language_gets_no_fallback() -> None:
    data = {"name": "Author", "bio": "English bio", "wikipedia_url": None}

    await author_service._overlay_localization(session_returning(None), data, 1, "en")

    assert data["bio"] == "English bio"
    assert data["fallback_bio"] is None


@pytest.mark.asyncio
async def test_an_author_with_a_localized_bio_uses_it_and_its_name() -> None:
    data = {"name": "Stanislaw Lem", "bio": "English bio", "wikipedia_url": "https://en.wikipedia.org/wiki/Lem"}
    localized = types.SimpleNamespace(name="Stanisław Lem", bio="Polski bio", wikipedia_url="https://pl.wikipedia.org/wiki/Lem")

    await author_service._overlay_localization(session_returning(localized), data, 1, "pl")

    assert (data["name"], data["bio"]) == ("Stanisław Lem", "Polski bio")
    assert data["wikipedia_url"].startswith("https://pl.")
    assert data["fallback_bio"] is None


@pytest.mark.asyncio
async def test_an_author_without_a_localized_bio_offers_the_canonical_one_labelled() -> None:
    data = {"name": "Stanislaw Lem", "bio": "English bio", "wikipedia_url": None}

    await author_service._overlay_localization(session_returning(None), data, 1, "pl")

    assert data["bio"] is None
    assert (data["fallback_bio"], data["fallback_language"]) == ("English bio", "en")


@pytest.mark.asyncio
async def test_a_series_without_a_description_borrows_a_sibling_languages() -> None:
    series = types.SimpleNamespace(group_id=7, series_id=9)
    data = {"description": None}
    sibling = types.SimpleNamespace(description="Opis serii", language="pl")

    await series_service._attach_description_fallback(session_returning(sibling), data, series)

    assert (data["fallback_description"], data["fallback_language"]) == ("Opis serii", "pl")


@pytest.mark.asyncio
async def test_a_described_series_borrows_nothing() -> None:
    session = session_returning(None)
    data = {"description": "Own text"}

    await series_service._attach_description_fallback(session, data, types.SimpleNamespace(group_id=None, series_id=9))

    assert data["fallback_description"] is None
    session.execute.assert_not_called()
