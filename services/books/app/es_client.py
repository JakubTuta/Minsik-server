import asyncio
import logging
import typing

import app.services._language_boost
import elasticsearch
import elasticsearch.helpers

logger = logging.getLogger(__name__)

_es_client: typing.Optional[elasticsearch.AsyncElasticsearch] = None

# Elasticsearch's built-in `language` stemmer/stopwords cover these out of the
# box. A configured language outside this set (e.g. Polish, which needs the
# analysis-stempel plugin) falls back to 'generic_analyzer' — lowercasing and
# accent-folding with no stemming, which is still far better than running the
# wrong language's stemmer over it (matching "biegać"/"biega" as different
# words is correct; matching them as the same word via English rules is not).
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

# Elasticsearch rejects analyzer names beginning with an underscore.
_GENERIC_ANALYZER = "generic_analyzer"


def _configured_languages() -> typing.List[str]:
    return app.services._language_boost.available_languages()


def _analyzer_name(language: str) -> str:
    return f"book_analyzer_{language}" if language in _ES_BUILTIN_STEMMER_LANGUAGES else _GENERIC_ANALYZER


def has_language_subfield(language: str) -> bool:
    """Whether `{field}.lang_{language}` exists in the index mapping — see _searchable_text_field."""
    return language in _ES_BUILTIN_STEMMER_LANGUAGES


def _analysis_settings() -> typing.Dict[str, typing.Any]:
    analyzers: typing.Dict[str, typing.Any] = {
        _GENERIC_ANALYZER: {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", "asciifolding"],
        }
    }
    filters: typing.Dict[str, typing.Any] = {}

    for language in _configured_languages():
        stemmer_language = _ES_BUILTIN_STEMMER_LANGUAGES.get(language)
        if stemmer_language is None:
            continue
        filter_name = f"{language}_stemmer"
        filters[filter_name] = {"type": "stemmer", "language": stemmer_language}
        analyzers[_analyzer_name(language)] = {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", "asciifolding", filter_name],
        }

    return {
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": analyzers,
            "filter": filters,
            "normalizer": {
                "lowercase_normalizer": {
                    "type": "custom",
                    "filter": ["lowercase", "asciifolding"],
                }
            },
        },
    }


def _searchable_text_field() -> typing.Dict[str, typing.Any]:
    """A text field indexed once per configured language, plus a language-agnostic base copy.

    Elasticsearch multi-fields re-analyze the same input independently per
    subfield, so no indexing-side change is needed when a language is added —
    only this mapping and the query-side field list (search_service.py) need it.
    """
    per_language_fields = {
        f"lang_{language}": {"type": "text", "analyzer": _analyzer_name(language)}
        for language in _configured_languages()
    }
    return {
        "type": "text",
        "analyzer": _GENERIC_ANALYZER,
        "fields": {
            "exact": {"type": "keyword", "normalizer": "lowercase_normalizer"},
            "suggest": {"type": "search_as_you_type"},
            **per_language_fields,
        },
    }


def books_index_mapping() -> typing.Dict[str, typing.Any]:
    return {
        "settings": _analysis_settings(),
        "mappings": {
            "properties": {
                "book_id": {"type": "long", "index": False},
                "title": _searchable_text_field(),
                "language": {"type": "keyword"},
                "slug": {"type": "keyword"},
                "work_id": {"type": "keyword"},
                "primary_cover_url": {"type": "keyword", "index": False},
                "authors_names": _searchable_text_field(),
                "author_slugs": {"type": "keyword", "index": False},
                "series_name": _searchable_text_field(),
                "series_slug": {"type": "keyword", "index": False},
                "app_avg_rating": {"type": "float", "index": False},
                "app_rating_count": {"type": "integer", "index": False},
                "ol_avg_rating": {"type": "float", "index": False},
                "ol_rating_count": {"type": "integer", "index": False},
                "readers": {"type": "integer", "index": False},
                "bayesian_score": {"type": "float"},
            }
        },
    }


def authors_index_mapping() -> typing.Dict[str, typing.Any]:
    return {
        "settings": _analysis_settings(),
        "mappings": {
            "properties": {
                "author_id": {"type": "long", "index": False},
                "language": {"type": "keyword"},
                "name": _searchable_text_field(),
                "slug": {"type": "keyword"},
                "photo_url": {"type": "keyword", "index": False},
                "book_count": {"type": "integer", "index": False},
                "app_avg_rating": {"type": "float", "index": False},
                "app_rating_count": {"type": "integer", "index": False},
                "ol_avg_rating": {"type": "float", "index": False},
                "ol_rating_count": {"type": "integer", "index": False},
                "readers": {"type": "integer", "index": False},
                "bayesian_score": {"type": "float"},
            }
        },
    }


def series_index_mapping() -> typing.Dict[str, typing.Any]:
    return {
        "settings": _analysis_settings(),
        "mappings": {
            "properties": {
                "series_id": {"type": "long", "index": False},
                "language": {"type": "keyword"},
                "name": _searchable_text_field(),
                "slug": {"type": "keyword"},
                "book_count": {"type": "integer", "index": False},
                "app_avg_rating": {"type": "float", "index": False},
                "app_rating_count": {"type": "integer", "index": False},
                "ol_avg_rating": {"type": "float", "index": False},
                "ol_rating_count": {"type": "integer", "index": False},
                "readers": {"type": "integer", "index": False},
                "bayesian_score": {"type": "float"},
            }
        },
    }


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


async def _fields_missing_subfields(
    index: str, mapping: typing.Dict[str, typing.Any]
) -> typing.Dict[str, typing.Any]:
    """Text fields in a live index whose multi-fields lag the configured mapping.

    Adding a language adds a `lang_{code}` subfield to every searchable text
    field. An index created before that language existed keeps the old
    multi-fields forever, so search silently falls back to the generic
    analyzer for it.
    """
    live = await _es_client.indices.get_mapping(index=index)
    live_properties = live[index]["mappings"].get("properties", {})
    desired_properties = mapping["mappings"]["properties"]

    outdated = {}
    for name, definition in desired_properties.items():
        if definition.get("type") != "text":
            continue
        desired_subfields = set(definition.get("fields", {}))
        live_subfields = set(live_properties.get(name, {}).get("fields", {}))
        if desired_subfields - live_subfields:
            outdated[name] = definition

    return outdated


async def _add_language_subfields(
    index: str,
    mapping: typing.Dict[str, typing.Any],
    properties: typing.Dict[str, typing.Any],
) -> None:
    # A new analyzer can only be defined on a closed index, so the analysis
    # settings go in behind a close/open before the mapping that references
    # them. Reopening in `finally` matters: a rejected settings update (which
    # is what changing an *existing* analyzer's definition produces) must not
    # leave the index closed and the whole search surface down.
    await _es_client.indices.close(index=index)
    try:
        await _es_client.indices.put_settings(
            index=index, settings={"analysis": mapping["settings"]["analysis"]}
        )
    finally:
        await _es_client.indices.open(index=index)

    # Only the lagging fields are resent — replaying the full property set
    # would fail on any unrelated field whose mapping has since diverged.
    await _es_client.indices.put_mapping(index=index, properties=properties)
    logger.info(
        f"[ES] Added language subfields to {index}: {sorted(properties.keys())}"
    )


async def create_indexes(
    index_books: str, index_authors: str, index_series: str
) -> bool:
    """Create or update the search indexes. True when documents must be re-pushed.

    A brand-new index is empty, and a newly added multi-field stays empty on
    documents indexed before it existed — both cases need every document
    rewritten, not just the ones changed since the last sync.
    """
    needs_full_sync = False
    try:
        for index, mapping in [
            (index_books, books_index_mapping()),
            (index_authors, authors_index_mapping()),
            (index_series, series_index_mapping()),
        ]:
            try:
                exists = await _es_client.indices.exists(index=index)
                if not exists:
                    await _es_client.indices.create(index=index, body=mapping)
                    logger.info(f"[ES] Created index: {index}")
                    needs_full_sync = True
                    continue

                outdated = await _fields_missing_subfields(index, mapping)
                if not outdated:
                    logger.info(f"[ES] Index mapping up to date: {index}")
                    continue

                await _add_language_subfields(index, mapping, outdated)
                needs_full_sync = True
            except Exception as e:
                logger.error(f"[ES] Error preparing index {index}: {e}")
                raise
    except Exception as e:
        logger.error(f"[ES] Failed to prepare indexes: {e}")
        raise

    return needs_full_sync


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
