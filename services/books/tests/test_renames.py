import types
from unittest.mock import AsyncMock

import app.services.book_service as book_service
import app.services.renames as renames
import pytest


@pytest.mark.asyncio
async def test_unchanged_slug_records_nothing() -> None:
    session = AsyncMock()

    await renames.record_slug_change(session, "book", 1, "dune", "dune", "en")

    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_renamed_slug_is_kept_as_history_and_a_reclaimed_one_is_forgotten() -> None:
    session = AsyncMock()

    await renames.record_slug_change(session, "series", 5, "old", "new", "pl")

    recorded, forgotten = (call.args[1] for call in session.execute.call_args_list)
    assert recorded == {"entity_type": "series", "language": "pl", "old_slug": "old", "entity_id": 5}
    assert forgotten == {"entity_type": "series", "language": "pl", "slug": "new"}


@pytest.mark.asyncio
async def test_series_rename_reaches_the_books_that_copy_its_name() -> None:
    session = AsyncMock()

    await renames.propagate_series_rename(session, 9, "new-slug", "New Name")

    assert session.execute.call_args.args[1] == {"series_id": 9, "slug": "new-slug", "name": "New Name"}


@pytest.mark.asyncio
async def test_author_rename_marks_the_authors_books_for_resync() -> None:
    session = AsyncMock()

    await renames.propagate_author_rename(session, 3)

    assert session.execute.call_args.args[1] == {"author_id": 3}


@pytest.mark.asyncio
async def test_surviving_edition_prefers_english_and_needs_a_work_id() -> None:
    session = AsyncMock()
    result = types.SimpleNamespace(scalar=lambda: 42)
    session.execute.return_value = result

    assert await book_service._surviving_edition_id(
        session, types.SimpleNamespace(work_id="OL1W", book_id=7)
    ) == 42
    assert "language = 'en'" in str(session.execute.call_args.args[0])
    assert await book_service._surviving_edition_id(
        session, types.SimpleNamespace(work_id=None, book_id=7)
    ) is None
