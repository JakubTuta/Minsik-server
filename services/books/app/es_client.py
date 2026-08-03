import asyncio
import hashlib
import json
import logging
import typing

import app.config
import elasticsearch
import elasticsearch.helpers

logger = logging.getLogger(__name__)

_es_client: typing.Optional[elasticsearch.AsyncElasticsearch] = None

# Analysis plugins detected on the connected cluster. Everything language-related
# degrades rather than fails when one is missing, so search keeps working on a
# node whose start-up plugin install (see docker-compose.yml) did not go through.
_installed_plugins: typing.Set[str] = set()

ICU_PLUGIN = "analysis-icu"

# Elasticsearch's built-in `language` stemmer covers these out of the box.
_ES_BUILTIN_STEMMER_LANGUAGES: typing.Dict[str, str] = {
    "ar": "arabic", "hy": "armenian", "eu": "basque", "bn": "bengali",
    "pt-br": "brazilian", "bg": "bulgarian", "ca": "catalan", "cs": "czech",
    "da": "danish", "nl": "dutch", "en": "english", "et": "estonian",
    "fi": "finnish", "fr": "french", "gl": "galician", "de": "german",
    "el": "greek", "hi": "hindi", "hu": "hungarian", "id": "indonesian",
    "ga": "irish", "it": "italian", "lv": "latvian", "lt": "lithuanian",
    "no": "norwegian", "fa": "persian", "pt": "portuguese", "ro": "romanian",
    "ru": "russian", "ckb": "sorani", "es": "spanish", "sv": "swedish",
    "tr": "turkish", "th": "thai",
}

# Languages whose stemmer arrives with a plugin instead of the core distribution.
# Without the plugin the language still gets folding and lowercasing through the
# generic analyzer — only stemming is lost.
_PLUGIN_STEMMERS: typing.Dict[str, typing.Tuple[str, typing.Dict[str, str]]] = {
    "pl": ("analysis-stempel", {"type": "polish_stem"}),
}

# Elasticsearch rejects analyzer names beginning with an underscore.
_GENERIC_ANALYZER = "generic_analyzer"
_EDGE_NGRAM_ANALYZER = "edge_ngram_analyzer"
_EDGE_NGRAM_FILTER = "edge_ngram_filter"
_FOLDED_NORMALIZER = "folded_normalizer"


def _available_languages() -> typing.List[str]:
    raw = app.config.settings.available_languages or "en"
    return [lang.strip() for lang in raw.split(",") if lang.strip()] or ["en"]


def _folding_filter() -> str:
    """Diacritic folding, ICU when the plugin is there.

    `asciifolding` silently passes through the letters that matter most outside
    western europe — Polish 'ł' stays 'ł', so "wladca" never matches "Władca".
    `icu_folding` folds it, which is the difference between a query typed
    without diacritics finding a book and finding nothing.
    """
    return "icu_folding" if ICU_PLUGIN in _installed_plugins else "asciifolding"


def _stemmer_filter(language: str) -> typing.Optional[typing.Dict[str, typing.Any]]:
    plugin_stemmer = _PLUGIN_STEMMERS.get(language)
    if plugin_stemmer is not None:
        plugin, definition = plugin_stemmer
        return dict(definition) if plugin in _installed_plugins else None

    builtin = _ES_BUILTIN_STEMMER_LANGUAGES.get(language)
    return {"type": "stemmer", "language": builtin} if builtin else None


def stemmed_languages() -> typing.List[str]:
    """Configured languages that get a dedicated analyzed field of their own.

    A language with no stemmer available would produce a field identical to the
    generic one — same tokens, same scores, twice the index size — so it is left
    out and served by the generic analyzer alone.
    """
    return [
        language
        for language in _available_languages()
        if _stemmer_filter(language) is not None
    ]


def language_field(base: str, language: str) -> str:
    """Name of the per-language analyzed field for `base` (e.g. `titles_pl`).

    A real field, not a multi-field: multi-fields re-analyze whatever the parent
    field holds, which would run every language's stemmer over every language's
    text. Separate fields let the indexer put a title only into the analyzer
    that belongs to its own language.
    """
    return f"{base}_{language}"


def _analyzer_name(language: str) -> str:
    return f"text_analyzer_{language}"


def _analysis_settings() -> typing.Dict[str, typing.Any]:
    folding = _folding_filter()

    analyzers: typing.Dict[str, typing.Any] = {
        _GENERIC_ANALYZER: {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", folding],
        },
        # Index-time only (fields using this set a plain `generic_analyzer`
        # search_analyzer): a title like "The Hobbit" is indexed as the grams
        # "th", "the", "the h", ... "the hobbit", so a query for "hobbi" finds
        # it via the "the hobbi" gram without the query itself being ngrammed.
        _EDGE_NGRAM_ANALYZER: {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", folding, _EDGE_NGRAM_FILTER],
        },
    }
    filters: typing.Dict[str, typing.Any] = {
        _EDGE_NGRAM_FILTER: {"type": "edge_ngram", "min_gram": 2, "max_gram": 20},
    }
    normalizers: typing.Dict[str, typing.Any] = {
        # Applied automatically to `term`/`terms` queries against a keyword
        # field that declares it, so a `name.exact` lookup needs no manual
        # case/diacritic folding of the query string.
        _FOLDED_NORMALIZER: {"type": "custom", "filter": ["lowercase", folding]},
    }

    for language in stemmed_languages():
        stemmer = _stemmer_filter(language)
        filter_name = f"{language}_stemmer"
        filters[filter_name] = stemmer
        analyzers[_analyzer_name(language)] = {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", folding, filter_name],
        }

    return {
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": analyzers,
            "filter": filters,
            "normalizer": normalizers,
        },
    }


def _prefix_subfield() -> typing.Dict[str, typing.Any]:
    return {
        "type": "text",
        "analyzer": _EDGE_NGRAM_ANALYZER,
        "search_analyzer": _GENERIC_ANALYZER,
    }


def _name_field(exact: bool = True) -> typing.Dict[str, typing.Any]:
    """The canonical display name for an entity: a book's title, an author's
    name, a series' name. Norms stay on — a short, single-valued field is
    exactly where length norms should matter.
    """
    fields: typing.Dict[str, typing.Any] = {"prefix": _prefix_subfield()}
    if exact:
        fields["exact"] = {"type": "keyword", "normalizer": _FOLDED_NORMALIZER}

    return {"type": "text", "analyzer": _GENERIC_ANALYZER, "fields": fields}


def _alt_name_field() -> typing.Dict[str, typing.Any]:
    """Every other title/name an entity is known by (other editions, other
    language rows). Recall only: `norms: false` so a work with many editions
    never scores worse than one with a single, short title.
    """
    return {
        "type": "text",
        "analyzer": _GENERIC_ANALYZER,
        "norms": False,
        "fields": {
            "prefix": {**_prefix_subfield(), "norms": False},
        },
    }


def _language_text_fields(base: str) -> typing.Dict[str, typing.Any]:
    return {
        language_field(base, language): {
            "type": "text",
            "analyzer": _analyzer_name(language),
            "fields": {"prefix": _prefix_subfield()},
        }
        for language in stemmed_languages()
    }


# Popularity and quality ride as rank features rather than a script in a
# function_score: `saturation` is additive and bounded, so a perfect title match
# on an obscure book still outranks a weak match on a famous one, and the
# scoring stays prunable by Lucene instead of running a script per candidate.
_RANK_FEATURES = {
    "popularity": {"type": "rank_feature"},
    "quality": {"type": "rank_feature"},
}

_DISPLAY_RATING_FIELDS = {
    "app_avg_rating": {"type": "float", "index": False},
    "app_rating_count": {"type": "integer", "index": False},
    "ol_avg_rating": {"type": "float", "index": False},
    "ol_rating_count": {"type": "integer", "index": False},
    "readers": {"type": "integer", "index": False},
}


def catalog_index_mapping() -> typing.Dict[str, typing.Any]:
    """One document per entity — book (by work), author, or series — sharing
    one field vocabulary and discriminated by `kind`.

    A book document holds one document per *work*, not per edition: the
    alternative makes translations of one book compete with each other for
    the same query, forces a de-duplication pass after the result window has
    already been cut, and counts one work's popularity once per translation.

    A single index for all three kinds means one query produces one
    comparable score space across books, authors and series — the three-index
    design this replaced could only compare them by an arbitrary per-type
    rescale, which is what let a fuzzy author match outrank an exact title.
    """
    return {
        "settings": _analysis_settings(),
        "mappings": {
            "properties": {
                "kind": {"type": "keyword"},
                "work_id": {"type": "keyword", "index": False},
                "author_id": {"type": "long", "index": False},
                "slug": {"type": "keyword", "index": False},
                "name": _name_field(),
                **_language_text_fields("name"),
                "alt_names": _alt_name_field(),
                "authors_names": _name_field(exact=False),
                "author_slugs": {"type": "keyword", "index": False},
                "series_name": {"type": "text", "analyzer": _GENERIC_ANALYZER, "norms": False},
                "series_slug": {"type": "keyword", "index": False},
                "photo_url": {"type": "keyword", "index": False},
                "book_count": {"type": "integer", "index": False},
                "languages": {"type": "keyword"},
                **_RANK_FEATURES,
                **_DISPLAY_RATING_FIELDS,
                # Rendering payload: which edition/row to show is decided per
                # request from the reader's language, not at index time.
                "editions": {"type": "object", "enabled": False},
                "rows": {"type": "object", "enabled": False},
            }
        },
    }


def index_specs() -> typing.Dict[str, typing.Dict[str, typing.Any]]:
    settings = app.config.settings
    return {settings.es_index_catalog: catalog_index_mapping()}


def _fingerprint(mapping: typing.Dict[str, typing.Any]) -> str:
    encoded = json.dumps(mapping, sort_keys=True).encode()
    return hashlib.sha1(encoded).hexdigest()[:10]


def versioned_index_name(alias: str, mapping: typing.Dict[str, typing.Any]) -> str:
    return f"{alias}-{_fingerprint(mapping)}"


class IndexPlan:
    """Where this sync run must write, and whether it has to write everything.

    Analyzers cannot be redefined on a live index and a new analyzed field stays
    empty on documents indexed before it existed, so a mapping change means a
    fresh index rather than an in-place edit. Each mapping fingerprints to its
    own index name behind a stable alias; a rebuild fills the new index while
    the old one keeps serving, and `promote` swaps the alias atomically.
    """

    def __init__(
        self, targets: typing.Dict[str, str], rebuild: bool
    ) -> None:
        self.targets = targets
        self.rebuild = rebuild

    def write_index(self, alias: str) -> str:
        return self.targets[alias] if self.rebuild else alias


async def _aliased_indices(alias: str) -> typing.List[str]:
    try:
        response = await _es_client.indices.get_alias(name=alias)
    except elasticsearch.NotFoundError:
        return []
    return list(response.keys())


async def plan_indexes() -> IndexPlan:
    """Create any missing versioned index and report whether a full sync is due.

    A rebuild of one index upgrades the whole run to a full sync: adding a
    language changes every mapping anyway, and one bookkeeping path is easier to
    reason about than three that can disagree.
    """
    targets: typing.Dict[str, str] = {}
    rebuild = False

    for alias, mapping in index_specs().items():
        target = versioned_index_name(alias, mapping)
        targets[alias] = target

        live = await _aliased_indices(alias)
        if target in live:
            continue

        # Reachable when a previous rebuild died before promoting. The index is
        # rebuilt from Postgres either way, so start from an empty one rather
        # than inheriting a half-written index nobody has verified.
        if await _es_client.indices.exists(index=target):
            await _es_client.indices.delete(index=target)

        await _es_client.indices.create(
            index=target,
            settings=mapping["settings"],
            mappings=mapping["mappings"],
        )
        logger.info(f"[ES] Created index {target} for alias '{alias}'")
        rebuild = True

    return IndexPlan(targets, rebuild)


async def promote(plan: IndexPlan) -> None:
    """Point each alias at its freshly built index and drop the superseded ones."""
    if not plan.rebuild:
        return

    for alias, target in plan.targets.items():
        # An install that predates aliasing has a concrete index sitting on the
        # name the alias needs. Elasticsearch refuses an alias that collides
        # with an index name, so the old index goes first; the new one is
        # already populated, so the gap is a single request wide.
        if not await _es_client.indices.exists_alias(name=alias):
            if await _es_client.indices.exists(index=alias):
                await _es_client.indices.delete(index=alias)
                logger.info(f"[ES] Removed pre-alias index '{alias}'")

        actions: typing.List[typing.Dict[str, typing.Any]] = [
            {"remove": {"index": index, "alias": alias}}
            for index in await _aliased_indices(alias)
            if index != target
        ]
        actions.append({"add": {"index": target, "alias": alias}})
        await _es_client.indices.update_aliases(actions=actions)

        for action in actions:
            retired = action.get("remove", {}).get("index")
            if retired:
                await _es_client.indices.delete(index=retired, ignore_unavailable=True)

        logger.info(f"[ES] Alias '{alias}' now serves {target}")


async def _detect_plugins() -> None:
    global _installed_plugins
    try:
        response = await _es_client.nodes.info(metric="plugins")
        names = {
            plugin.get("name")
            for node in response.get("nodes", {}).values()
            for plugin in node.get("plugins", [])
        }
        _installed_plugins = {name for name in names if name}
    except Exception as e:
        _installed_plugins = set()
        logger.warning(f"[ES] Plugin detection failed, assuming none: {e}")

    missing_stemmers = [
        language
        for language in _available_languages()
        if _stemmer_filter(language) is None
    ]
    logger.info(
        f"[ES] Plugins: {sorted(_installed_plugins) or 'none'}; "
        f"folding: {_folding_filter()}; "
        f"stemmed languages: {stemmed_languages()}"
        + (f"; no stemmer for: {missing_stemmers}" if missing_stemmers else "")
    )


async def init_es(host: str, port: int, max_retries: int = 10) -> None:
    global _es_client
    es_url = f"http://{host}:{port}"
    _es_client = elasticsearch.AsyncElasticsearch(
        [es_url],
        request_timeout=120,
        retry_on_timeout=True,
        max_retries=3,
    )

    for attempt in range(max_retries):
        try:
            health = await _es_client.cluster.health()
            logger.info(
                f"Elasticsearch connected: {host}:{port}, cluster status: {health.get('status')}"
            )
            await _detect_plugins()
            return
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = min(2**attempt, 30)
                logger.warning(
                    f"Elasticsearch connection attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    f"Elasticsearch connection failed after {max_retries} attempts: {e}"
                )
                raise


async def set_index_refresh(index: str, interval: str) -> None:
    await _es_client.indices.put_settings(
        index=index, settings={"refresh_interval": interval}
    )


async def refresh_index(index: str) -> None:
    await _es_client.indices.refresh(index=index)


async def close_es() -> None:
    if _es_client:
        await _es_client.close()
        logger.info("Elasticsearch client closed")


def get_es() -> elasticsearch.AsyncElasticsearch:
    return _es_client
