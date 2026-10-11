from unittest.mock import AsyncMock, MagicMock

import app.db as db
import app.services.category_service as category_service
import app.services.category_works as category_works
import pytest


def _sql(statement) -> str:
    return " ".join(str(statement).split())


@pytest.mark.parametrize(
    ("sort_by", "order", "expected"),
    [
        ("popularity", "desc", "ORDER BY cw.popularity DESC, cw.work_id DESC"),
        ("rating", "desc", "ORDER BY cw.rating_score DESC, cw.work_id DESC"),
        ("popularity", "asc", "ORDER BY cw.popularity ASC, cw.work_id ASC"),
        ("anything-else", "desc", "ORDER BY cw.popularity DESC, cw.work_id DESC"),
    ],
)
def test_page_follows_the_requested_order_with_a_tiebreaker(sort_by, order, expected) -> None:
    sql = _sql(category_works.page_query(sort_by, order))

    assert expected in sql
    assert "LIMIT :limit OFFSET :offset" in sql
    assert sql.endswith("ORDER BY page.pos")


def test_only_works_on_the_page_go_through_the_edition_lookup() -> None:
    sql = _sql(category_works.page_query("popularity", "desc"))

    assert "JOIN LATERAL" in sql
    assert "e.language = :language" in sql
    assert "primary_cover_url IS NOT NULL" in sql


def _session_maker(session):
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=manager)


@pytest.mark.asyncio
async def test_category_without_rows_falls_back_to_the_full_query(monkeypatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(db, "async_session_maker", _session_maker(session))
    monkeypatch.setattr(category_works, "count", AsyncMock(return_value=0))

    service = category_service.CategoryService()

    assert await service._fetch_from_category_works("fantasy", 20, 0, "en", "popularity", "desc") is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_rebuild_replaces_the_category_in_one_transaction() -> None:
    session = AsyncMock()
    session.execute.return_value = MagicMock(rowcount=7)

    assert await category_works.rebuild(session, "fantasy", [3, 1]) == 7

    statements = [_sql(call.args[0]) for call in session.execute.call_args_list]
    assert statements[0].startswith("DELETE FROM books.category_works")
    assert statements[1].startswith("INSERT INTO books.category_works")
    session.commit.assert_awaited_once()
