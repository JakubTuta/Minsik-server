import types
from unittest.mock import AsyncMock, MagicMock

import app.db as db
import app.services.es_reconcile_service as reconcile
import pytest


def _session_returning(scalar=None, rows=()):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = scalar
    result.fetchall.return_value = list(rows)
    session.execute.return_value = result
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    return session, MagicMock(return_value=manager)


@pytest.mark.asyncio
async def test_author_ids_are_compared_as_numbers(monkeypatch) -> None:
    session, _ = _session_returning(rows=[types.SimpleNamespace(identity=7)])

    stale = await reconcile._find_stale_ids(session, "authors", ["author:7", "author:8", "author:oops"])

    assert stale == {"author:8", "author:oops"}
    assert session.execute.call_args.args[1] == {"ids": [7, 8]}
    assert "::text" not in str(session.execute.call_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize(("es_count", "expected", "skip"), [(100, 100, True), (90, 100, True), (101, 100, False)])
async def test_scan_is_skipped_only_when_no_surplus_documents(monkeypatch, es_count, expected, skip) -> None:
    _, maker = _session_returning(scalar=expected)
    monkeypatch.setattr(db, "async_session_maker", maker)
    es = MagicMock()
    es.count = AsyncMock(return_value={"count": es_count})

    assert await reconcile._has_no_surplus_documents(es, "catalog", "books") is skip


@pytest.mark.asyncio
async def test_failed_count_check_falls_back_to_the_scan(monkeypatch) -> None:
    es = MagicMock()
    es.count = AsyncMock(side_effect=RuntimeError("es down"))

    assert await reconcile._has_no_surplus_documents(es, "catalog", "books") is False
