"""Wikipedia and Wikidata lookups for descriptions, in the language of the row being filled.

A description is only ever taken from the Wikipedia of the row's own language, and
only from a page that is demonstrably about the entity: either reached through the
entity's Wikidata sitelinks, or found by search and then checked (the page title
must match the entity's name and, for books, the text must mention the author).
The first fuzzy search hit is not trusted: "The Hobbit" must not end up with the
article of a 1977 film.
"""

import difflib
import logging
import re
import typing
import unicodedata

import app.utils
import httpx

logger = logging.getLogger(__name__)

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API_URL = "https://{language}.wikipedia.org/w/api.php"
TITLE_MATCH_RATIO = 0.85
WIKIDATA_BATCH = 50

_PARENTHETICAL = re.compile(r"\s*\([^)]*\)\s*")
# A "(1984 film)" or "(video game)" page shares the book's name but is not about the book.
_NON_BOOK_QUALIFIER = re.compile(
    r"\([^)]*\b(film|movie|tv|television|miniseries|album|song|band|game|musical|opera|comics?|anime|manga|"
    r"película|cinéma|spiel|gra)\b[^)]*\)",
    re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_LEADING_ARTICLE = re.compile(r"^(the|a|an|der|die|das|le|la|les|el|los|las)\s+")


def normalise_title(value: str) -> str:
    """Comparable form of a title: no accents, case, punctuation, disambiguation or leading article."""
    text = unicodedata.normalize("NFKD", _PARENTHETICAL.sub(" ", value))
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    text = _NON_WORD.sub(" ", text)
    text = " ".join(text.split())
    return _LEADING_ARTICLE.sub("", text)


def title_matches(page_title: str, expected: str) -> bool:
    page, wanted = normalise_title(page_title), normalise_title(expected)
    if not page or not wanted or _NON_BOOK_QUALIFIER.search(page_title):
        return False
    return page == wanted or difflib.SequenceMatcher(None, page, wanted).ratio() >= TITLE_MATCH_RATIO


def mentions_author(extract: str, author_name: typing.Optional[str]) -> bool:
    """True when the text names the author (by surname), or when there is no author to check."""
    if not author_name:
        return True
    surname = normalise_title(author_name).split()[-1:] or [""]
    return len(surname[0]) >= 3 and surname[0] in normalise_title(extract)


class WikipediaClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _get(self, url: str, params: dict) -> dict:
        response = await self._client.get(url, params={**params, "format": "json"})
        response.raise_for_status()
        return response.json()

    async def wikidata_entities(self, wikidata_ids: list[str], languages: list[str]) -> dict[str, dict]:
        """`{Qid: {"titles": {lang: wikipedia title}, "labels": {lang: label}}}` for up to 50 ids."""
        if not wikidata_ids:
            return {}
        data = await self._get(
            WIKIDATA_API_URL,
            {
                "action": "wbgetentities",
                "ids": "|".join(wikidata_ids[:WIKIDATA_BATCH]),
                "props": "sitelinks|labels",
                "sitefilter": "|".join(f"{language}wiki" for language in languages),
                "languages": "|".join(languages),
            },
        )
        entities: dict[str, dict] = {}
        for qid, entity in (data.get("entities") or {}).items():
            sitelinks = entity.get("sitelinks") or {}
            labels = entity.get("labels") or {}
            entities[qid] = {
                "titles": {
                    language: sitelinks[f"{language}wiki"]["title"]
                    for language in languages
                    if f"{language}wiki" in sitelinks
                },
                "labels": {language: labels[language]["value"] for language in languages if language in labels},
            }
        return entities

    async def search_title(self, language: str, term: str) -> typing.Optional[str]:
        data = await self._get(
            WIKIPEDIA_API_URL.format(language=language),
            {"action": "query", "list": "search", "srsearch": term, "srlimit": 3},
        )
        results = (data.get("query") or {}).get("search") or []
        return results[0]["title"] if results else None

    async def intro_extract(self, language: str, title: str) -> typing.Optional[str]:
        data = await self._get(
            WIKIPEDIA_API_URL.format(language=language),
            {
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "exintro": True,
                "exsentences": 5,
                "explaintext": True,
                "redirects": 1,
            },
        )
        for page in ((data.get("query") or {}).get("pages") or {}).values():
            extract = (page.get("extract") or "").strip()
            if extract:
                return app.utils.clean_description(extract)
        return None

    async def verified_extract(
        self,
        language: str,
        expected_title: str,
        search_term: str,
        author_name: typing.Optional[str] = None,
        known_title: typing.Optional[str] = None,
    ) -> typing.Optional[str]:
        """The intro of the page that is about `expected_title`, or None when nothing verifiable is found.

        `known_title` is a page already tied to the entity (a Wikidata sitelink) and is
        trusted as is; a searched page has to pass the title and author checks.
        """
        try:
            if known_title:
                return await self.intro_extract(language, known_title)
            found = await self.search_title(language, search_term)
            if not found or not title_matches(found, expected_title):
                return None
            extract = await self.intro_extract(language, found)
            if extract and mentions_author(extract, author_name):
                return extract
        except (httpx.HTTPError, ValueError) as error:
            logger.debug(f"Wikipedia lookup failed for '{search_term}' ({language}): {error}")
        return None
