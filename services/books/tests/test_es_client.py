import asyncio
import typing

import app.config
import app.es_client
import elasticsearch
import pytest


class FakeIndices:
    def __init__(self) -> None:
        self.indexes: typing.Dict[str, typing.Any] = {}
        self.aliases: typing.Dict[str, typing.Set[str]] = {}
        self.calls: typing.List[typing.Tuple[str, str]] = []

    async def exists(self, index: str) -> bool:
        return index in self.indexes

    async def create(
        self,
        index: str,
        settings: typing.Dict[str, typing.Any],
        mappings: typing.Dict[str, typing.Any],
    ) -> None:
        self.calls.append(("create", index))
        self.indexes[index] = {"settings": settings, "mappings": mappings}

    async def delete(self, index: str, ignore_unavailable: bool = False) -> None:
        self.calls.append(("delete", index))
        self.indexes.pop(index, None)
        for members in self.aliases.values():
            members.discard(index)

    async def get_alias(self, name: str) -> typing.Dict[str, typing.Any]:
        members = self.aliases.get(name)
        if not members:
            raise elasticsearch.NotFoundError("alias_missing", None, None)
        return {index: {} for index in members}

    async def exists_alias(self, name: str) -> bool:
        return bool(self.aliases.get(name))

    async def update_aliases(
        self, actions: typing.List[typing.Dict[str, typing.Any]]
    ) -> None:
        for action in actions:
            if "remove" in action:
                self.calls.append(("unalias", action["remove"]["index"]))
                self.aliases.setdefault(action["remove"]["alias"], set()).discard(
                    action["remove"]["index"]
                )
            if "add" in action:
                self.calls.append(("alias", action["add"]["index"]))
                self.aliases.setdefault(action["add"]["alias"], set()).add(
                    action["add"]["index"]
                )


class FakeClient:
    def __init__(self, indices: FakeIndices) -> None:
        self.indices = indices


@pytest.fixture
def es_state(monkeypatch: pytest.MonkeyPatch):
    indices = FakeIndices()
    monkeypatch.setattr(
        app.es_client, "_es_client", FakeClient(indices), raising=False
    )

    def configure(languages: str, plugins: typing.Optional[typing.Set[str]] = None) -> None:
        monkeypatch.setattr(
            app.config.settings, "available_languages", languages, raising=False
        )
        monkeypatch.setattr(
            app.es_client, "_installed_plugins", plugins or set(), raising=False
        )

    def plan() -> app.es_client.IndexPlan:
        return asyncio.run(app.es_client.plan_indexes())

    def promote(index_plan: app.es_client.IndexPlan) -> None:
        asyncio.run(app.es_client.promote(index_plan))

    configure("en")

    return indices, configure, plan, promote


def test_first_run_creates_versioned_indexes_and_requires_a_rebuild(es_state):
    indices, _configure, plan, _promote = es_state

    index_plan = plan()

    assert index_plan.rebuild is True
    created = [name for kind, name in indices.calls if kind == "create"]
    assert sorted(created) == sorted(index_plan.targets.values())
    assert all("-" in name for name in index_plan.targets.values())


def test_rebuild_writes_to_the_new_index_while_the_alias_still_serves(es_state):
    _indices, _configure, plan, promote = es_state

    index_plan = plan()

    assert index_plan.write_index("catalog") == index_plan.targets["catalog"]

    promote(index_plan)
    settled = plan()

    assert settled.rebuild is False
    assert settled.write_index("catalog") == "catalog"


def test_promote_swaps_the_alias_and_drops_the_previous_index(es_state):
    indices, configure, plan, promote = es_state

    first = plan()
    promote(first)

    configure("en,de")
    second = plan()
    promote(second)

    assert second.rebuild is True
    assert indices.aliases["catalog"] == {second.targets["catalog"]}
    assert first.targets["catalog"] not in indices.indexes


def test_unchanged_configuration_is_a_noop(es_state):
    indices, _configure, plan, promote = es_state

    promote(plan())
    indices.calls.clear()

    assert plan().rebuild is False
    assert indices.calls == []


def test_pre_alias_index_is_replaced_by_the_alias(es_state):
    indices, _configure, plan, promote = es_state
    indices.indexes["catalog"] = {"legacy": True}

    promote(plan())

    assert "catalog" not in indices.indexes
    assert indices.aliases["catalog"]


def test_half_written_index_from_a_failed_run_is_rebuilt_from_scratch(es_state):
    indices, _configure, plan, _promote = es_state
    first = plan()
    indices.calls.clear()

    second = plan()

    assert second.targets == first.targets
    assert ("delete", first.targets["catalog"]) in indices.calls
    assert ("create", first.targets["catalog"]) in indices.calls


def test_language_without_a_stemmer_gets_no_dedicated_field(es_state):
    _indices, configure, _plan, _promote = es_state
    configure("en,pl")

    assert app.es_client.stemmed_languages() == ["en"]
    assert "name_pl" not in app.es_client.catalog_index_mapping()["mappings"]["properties"]


def test_stempel_plugin_enables_polish_stemming(es_state):
    _indices, configure, _plan, _promote = es_state
    configure("en,pl", plugins={"analysis-stempel"})

    assert app.es_client.stemmed_languages() == ["en", "pl"]
    properties = app.es_client.catalog_index_mapping()["mappings"]["properties"]
    assert properties["name_pl"]["analyzer"] == "text_analyzer_pl"


def test_icu_plugin_upgrades_folding(es_state):
    _indices, configure, _plan, _promote = es_state

    configure("en")
    assert "asciifolding" in app.es_client.catalog_index_mapping()["settings"]["analysis"][
        "analyzer"
    ]["generic_analyzer"]["filter"]

    configure("en", plugins={app.es_client.ICU_PLUGIN})
    assert "icu_folding" in app.es_client.catalog_index_mapping()["settings"]["analysis"][
        "analyzer"
    ]["generic_analyzer"]["filter"]


def test_analysis_changes_produce_a_new_index_name(es_state):
    _indices, configure, plan, promote = es_state

    promote(plan())
    before = plan().targets["catalog"]

    configure("en", plugins={app.es_client.ICU_PLUGIN})

    assert plan().targets["catalog"] != before


def test_catalog_mapping_shares_one_field_vocabulary_across_kinds(es_state):
    _indices, _configure, _plan, _promote = es_state

    properties = app.es_client.catalog_index_mapping()["mappings"]["properties"]

    assert properties["kind"] == {"type": "keyword"}
    assert "prefix" in properties["name"]["fields"]
    assert "exact" in properties["name"]["fields"]
    assert properties["name"]["fields"]["exact"]["normalizer"] == "folded_normalizer"
    # Recall-only aliases must never gain norms-based weight over the
    # canonical name just because a work happens to have many editions.
    assert properties["alt_names"]["norms"] is False
    assert properties["alt_names"]["fields"]["prefix"]["norms"] is False


def test_prefix_field_ngrams_at_index_time_only(es_state):
    _indices, _configure, _plan, _promote = es_state

    properties = app.es_client.catalog_index_mapping()["mappings"]["properties"]
    prefix_field = properties["name"]["fields"]["prefix"]

    assert prefix_field["analyzer"] == "edge_ngram_analyzer"
    assert prefix_field["search_analyzer"] == "generic_analyzer"
