import asyncio
import typing

import app.config
import app.es_client
import pytest


class FakeIndices:
    def __init__(self, live: typing.Dict[str, typing.Any]) -> None:
        self.live = live
        self.calls: typing.List[typing.Tuple[typing.Any, ...]] = []

    async def exists(self, index: str) -> bool:
        return index in self.live

    async def create(self, index: str, body: typing.Dict[str, typing.Any]) -> None:
        self.calls.append(("create", index))
        self.live[index] = body["mappings"]

    async def get_mapping(self, index: str) -> typing.Dict[str, typing.Any]:
        return {index: {"mappings": self.live[index]}}

    async def close(self, index: str) -> None:
        self.calls.append(("close", index))

    async def open(self, index: str) -> None:
        self.calls.append(("open", index))

    async def put_settings(
        self, index: str, settings: typing.Dict[str, typing.Any]
    ) -> None:
        self.calls.append(("put_settings", index, sorted(settings["analysis"]["analyzer"])))

    async def put_mapping(
        self, index: str, properties: typing.Dict[str, typing.Any]
    ) -> None:
        self.calls.append(("put_mapping", index, sorted(properties)))
        self.live[index]["properties"].update(properties)


class FakeClient:
    def __init__(self, live: typing.Dict[str, typing.Any]) -> None:
        self.indices = FakeIndices(live)


@pytest.fixture
def es_state(monkeypatch: pytest.MonkeyPatch):
    live: typing.Dict[str, typing.Any] = {}

    def run(languages: str) -> typing.Tuple[bool, typing.List[typing.Any]]:
        monkeypatch.setattr(
            app.config.settings, "available_languages", languages, raising=False
        )
        client = FakeClient(live)
        monkeypatch.setattr(app.es_client, "_es_client", client, raising=False)
        changed = asyncio.run(
            app.es_client.create_indexes("books", "authors", "series")
        )

        return changed, client.indices.calls

    return live, run


def test_create_indexes_creates_missing_indexes(es_state):
    _live, run = es_state
    changed, calls = run("en")

    assert changed is True
    assert [c[1] for c in calls if c[0] == "create"] == ["books", "authors", "series"]


def test_create_indexes_is_a_noop_when_up_to_date(es_state):
    _live, run = es_state
    run("en")
    changed, calls = run("en")

    assert changed is False
    assert calls == []


def test_added_language_updates_analysis_then_mapping(es_state):
    live, run = es_state
    run("en")
    changed, calls = run("en,de")

    assert changed is True

    kinds = [c[0] for c in calls]
    assert kinds.index("close") < kinds.index("put_settings") < kinds.index("open")
    assert kinds.index("open") < kinds.index("put_mapping")

    analyzers = next(c[2] for c in calls if c[0] == "put_settings")
    assert "book_analyzer_de" in analyzers

    title_fields = live["books"]["properties"]["title"]["fields"]
    assert title_fields["lang_de"]["analyzer"] == "book_analyzer_de"


def test_only_lagging_text_fields_are_resent(es_state):
    _live, run = es_state
    run("en")
    _changed, calls = run("en,de")

    resent = next(c[2] for c in calls if c[0] == "put_mapping" and c[1] == "books")
    assert resent == ["authors_names", "series_name", "title"]


def test_language_without_builtin_stemmer_uses_generic_analyzer(es_state):
    live, run = es_state
    run("en")
    _changed, calls = run("en,pl")

    analyzers = next(c[2] for c in calls if c[0] == "put_settings")
    assert "book_analyzer_pl" not in analyzers

    title_fields = live["books"]["properties"]["title"]["fields"]
    assert title_fields["lang_pl"]["analyzer"] == "generic_analyzer"


def test_reconciled_index_is_stable(es_state):
    _live, run = es_state
    run("en")
    run("en,de")
    changed, calls = run("en,de")

    assert changed is False
    assert calls == []


def test_index_is_reopened_when_settings_update_fails(es_state, monkeypatch):
    live, run = es_state
    run("en")

    class ExplodingIndices(FakeIndices):
        async def put_settings(self, index, settings):
            raise RuntimeError("mapper conflict")

    monkeypatch.setattr(
        app.config.settings, "available_languages", "en,de", raising=False
    )
    client = FakeClient(live)
    client.indices = ExplodingIndices(live)
    monkeypatch.setattr(app.es_client, "_es_client", client, raising=False)

    with pytest.raises(RuntimeError):
        asyncio.run(app.es_client.create_indexes("books", "authors", "series"))

    kinds = [c[0] for c in client.indices.calls]
    assert kinds.count("open") == kinds.count("close")
