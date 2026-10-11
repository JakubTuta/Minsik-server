import json
import types
from unittest.mock import AsyncMock, MagicMock

import app.cache as cache
import app.services.case_pool_builder as case_pool_builder
import app.services.contextual_provider as contextual_provider
import app.services.personal_refresher as personal_refresher
import app.services.taste_profile as taste_profile
import pytest


def _pool_row(authors):
    return types.SimpleNamespace(
        book_id=1, work_id="OL1W", title="T", slug="t", description=None, primary_cover_url=None,
        language="en", rarity_name="common", avg_rating=None, rating_count=0, ol_rating_count=0,
        ol_avg_rating=None, ol_want_to_read_count=0, ol_currently_reading_count=0,
        ol_already_read_count=0, app_want_to_read_count=0, app_reading_count=0, app_read_count=0,
        authors=authors,
    )


def test_pool_authors_keep_their_own_photo() -> None:
    authors = [
        {"author_id": 1, "name": "No Photo", "slug": "no-photo", "photo_url": ""},
        {"author_id": 2, "name": "Has Photo", "slug": "has-photo", "photo_url": "https://x/p.jpg"},
    ]

    item = case_pool_builder._row_to_pool_item(_pool_row(authors))

    assert [(a["name"], a["photo_url"]) for a in item["authors"]] == [
        ("No Photo", ""),
        ("Has Photo", "https://x/p.jpg"),
    ]


def test_pool_authors_accept_unparsed_json_text() -> None:
    raw = json.dumps([{"author_id": 3, "name": "A", "slug": "a", "photo_url": ""}])

    assert case_pool_builder._row_to_pool_item(_pool_row(raw))["authors"][0]["author_id"] == 3


def test_pool_item_without_authors_has_an_empty_list() -> None:
    assert case_pool_builder._row_to_pool_item(_pool_row(None))["authors"] == []


@pytest.mark.asyncio
async def test_partial_profile_is_not_kept_for_a_day(monkeypatch) -> None:
    monkeypatch.setattr(cache, "get_cached", AsyncMock(return_value=None))
    set_cached = AsyncMock()
    monkeypatch.setattr(cache, "set_cached", set_cached)
    monkeypatch.setattr(
        taste_profile, "build_taste_profile", AsyncMock(return_value={"degraded": True, "is_cold_start": True})
    )

    await taste_profile.get_taste_profile(7)

    assert set_cached.call_args.args[2] == taste_profile._DEGRADED_PROFILE_TTL


@pytest.mark.asyncio
async def test_refresh_keeps_previous_data_when_the_profile_is_partial(monkeypatch) -> None:
    set_cached = AsyncMock()
    monkeypatch.setattr(cache, "set_cached", set_cached)
    monkeypatch.setattr(taste_profile, "build_taste_profile", AsyncMock(return_value={"degraded": True}))

    with pytest.raises(RuntimeError):
        await personal_refresher.refresh_user_personal(MagicMock(), 7, "en")

    set_cached.assert_not_awaited()


def test_trimming_cached_sections_serves_a_smaller_request_from_a_larger_payload() -> None:
    sections = [
        {"item_type": "book", "book_items": [{"book_id": i} for i in range(20)], "total": 20},
        {"item_type": "author", "author_items": [{"author_id": i} for i in range(20)], "total": 20},
    ]

    trimmed = contextual_provider._trim_sections(sections, 5)

    assert [len(trimmed[0]["book_items"]), trimmed[0]["total"]] == [5, 5]
    assert [len(trimmed[1]["author_items"]), trimmed[1]["total"]] == [5, 5]
    assert len(sections[0]["book_items"]) == 20


@pytest.mark.asyncio
async def test_empty_contextual_result_is_cached_briefly(monkeypatch) -> None:
    monkeypatch.setattr(cache, "get_cached", AsyncMock(return_value=None))
    set_cached = AsyncMock()
    monkeypatch.setattr(cache, "set_cached", set_cached)
    monkeypatch.setattr(contextual_provider, "_read_precomputed", AsyncMock(return_value=None))

    result = await contextual_provider._cached_sections("book", 9, 15, AsyncMock(return_value=[]))

    assert result == []
    assert set_cached.call_args.args[2] == contextual_provider._EMPTY_TTL


@pytest.mark.asyncio
async def test_missing_pool_tier_triggers_a_build(monkeypatch) -> None:
    redis_client = MagicMock()
    redis_client.exists = AsyncMock(return_value=len(case_pool_builder.RARITY_TIERS) - 1)
    monkeypatch.setattr(cache, "redis_client", redis_client)
    refresh = AsyncMock()
    monkeypatch.setattr(case_pool_builder, "refresh_case_pools", refresh)

    await case_pool_builder.ensure_case_pools(MagicMock())

    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_pools_are_left_alone(monkeypatch) -> None:
    redis_client = MagicMock()
    redis_client.exists = AsyncMock(return_value=len(case_pool_builder.RARITY_TIERS))
    monkeypatch.setattr(cache, "redis_client", redis_client)
    refresh = AsyncMock()
    monkeypatch.setattr(case_pool_builder, "refresh_case_pools", refresh)

    await case_pool_builder.ensure_case_pools(MagicMock())

    refresh.assert_not_awaited()
