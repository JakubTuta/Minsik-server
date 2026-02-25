import datetime
import logging
import re
import typing

import app.utils
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

OL_COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
OL_AUTHOR_PHOTO_URL = "https://covers.openlibrary.org/a/id/{photo_id}-L.jpg"

OL_LANG_TO_ISO: dict[str, str] = {
    "eng": "en",
    "fre": "fr",
    "fra": "fr",
    "ger": "de",
    "deu": "de",
    "spa": "es",
    "ita": "it",
    "por": "pt",
    "rus": "ru",
    "jpn": "ja",
    "chi": "zh",
    "zho": "zh",
    "kor": "ko",
    "ara": "ar",
    "hin": "hi",
    "tur": "tr",
    "pol": "pl",
    "dut": "nl",
    "nld": "nl",
    "swe": "sv",
    "nor": "no",
    "dan": "da",
    "fin": "fi",
    "gre": "el",
    "ell": "el",
    "heb": "he",
    "tha": "th",
    "vie": "vi",
    "ukr": "uk",
    "ces": "cs",
    "cze": "cs",
    "rum": "ro",
    "ron": "ro",
    "hun": "hu",
    "cat": "ca",
    "bul": "bg",
    "hrv": "hr",
    "srp": "sr",
    "slk": "sk",
    "slo": "sk",
    "slv": "sl",
    "lit": "lt",
    "lav": "lv",
    "est": "et",
    "ind": "id",
    "may": "ms",
    "msa": "ms",
    "per": "fa",
    "fas": "fa",
    "ben": "bn",
    "tam": "ta",
    "tel": "te",
    "mar": "mr",
    "guj": "gu",
    "kan": "kn",
    "mal": "ml",
    "pan": "pa",
    "urd": "ur",
    "lat": "la",
    "glg": "gl",
    "eus": "eu",
    "baq": "eu",
    "wel": "cy",
    "cym": "cy",
    "gle": "ga",
    "iri": "ga",
    "ice": "is",
    "isl": "is",
    "geo": "ka",
    "kat": "ka",
    "arm": "hy",
    "hye": "hy",
    "mac": "mk",
    "mkd": "mk",
    "alb": "sq",
    "sqi": "sq",
    "bos": "bs",
    "afr": "af",
    "swa": "sw",
    "amh": "am",
    "tgl": "tl",
    "fil": "tl",
    "mlt": "mt",
}

_KNOWN_WORKS_MAX_ID = 60_000_000


def extract_text_value(field: typing.Any) -> typing.Optional[str]:
    if isinstance(field, dict):
        return field.get("value")
    if isinstance(field, str):
        return field
    return None


def extract_description(data: typing.Any) -> typing.Optional[str]:
    raw = extract_text_value(data)
    if raw:
        return app.utils.clean_description(raw)
    return None


def extract_cover_url(covers: typing.Optional[list]) -> typing.Optional[str]:
    if not covers or not isinstance(covers, list):
        return None
    for cover_id in covers:
        if isinstance(cover_id, int) and cover_id > 0:
            return OL_COVER_URL.format(cover_id=cover_id)
    return None


def parse_free_date(
    date_string: typing.Optional[str],
) -> typing.Optional[datetime.date]:
    if not date_string:
        return None
    return app.utils.parse_date(str(date_string).strip())


def extract_remote_ids(author_data: dict) -> dict[str, str]:
    remote_ids: dict[str, str] = {}
    raw = author_data.get("remote_ids")
    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, str) and val:
                remote_ids[key] = val
    return remote_ids


def extract_ol_lang(lang_ref: typing.Any) -> typing.Optional[str]:
    if isinstance(lang_ref, dict):
        key = lang_ref.get("key", "")
        code = key.replace("/languages/", "")
        return OL_LANG_TO_ISO.get(code)
    if isinstance(lang_ref, str):
        code = lang_ref.replace("/languages/", "")
        return OL_LANG_TO_ISO.get(code)
    return None


def parse_series_string(series_strs: typing.Optional[list]) -> typing.Optional[dict]:
    if not series_strs or not isinstance(series_strs, list):
        return None
    for s in series_strs:
        if not isinstance(s, str):
            continue
        match = re.match(r"^(.+?)(?:\s*[#,]\s*(\d+(?:\.\d+)?))?$", s.strip())
        if match:
            name = match.group(1).strip()
            position = match.group(2)
            return {
                "name": name,
                "position": float(position) if position else None,
            }
    return None


def ol_id_to_int(ol_id: str) -> typing.Optional[int]:
    if len(ol_id) >= 3 and ol_id[:2] == "OL" and ol_id[-1].isalpha():
        try:
            return int(ol_id[2:-1])
        except ValueError:
            return None
    return None


def is_known_work(filter_array: bytearray, ol_id: str) -> bool:
    num = ol_id_to_int(ol_id)
    if num is None or num >= _KNOWN_WORKS_MAX_ID:
        return False
    return bool(filter_array[num // 8] & (1 << (num % 8)))


def is_wikidata_qid(value: str) -> bool:
    return len(value) >= 2 and value[0] == "Q" and value[1:].isdigit()


def score_author(entry: dict) -> int:
    score = 0
    if entry.get("bio"):
        score += 1
    if entry.get("photo_url"):
        score += 1
    if entry.get("wikidata_id"):
        score += 1
    if entry.get("birth_date"):
        score += 1
    if entry.get("alternate_names"):
        score += 1
    return score


def score_work(book_data: dict) -> int:
    score = 0
    if book_data.get("description"):
        score += 1
    if book_data.get("primary_cover_url"):
        score += 1
    if book_data.get("authors"):
        score += 1
    if book_data.get("original_publication_year"):
        score += 1
    if book_data.get("genres"):
        score += 1
    return score


def score_edition(edition: dict) -> int:
    score = 0
    if edition.get("isbn_10") or edition.get("isbn_13"):
        score += 1
    if (
        isinstance(edition.get("number_of_pages"), int)
        and edition["number_of_pages"] > 0
    ):
        score += 1
    if edition.get("publishers"):
        score += 1
    if edition.get("covers"):
        score += 1
    if edition.get("description"):
        score += 1
    if edition.get("physical_format"):
        score += 1
    return score


async def build_known_works_filter(
    session: sqlalchemy.ext.asyncio.AsyncSession,
) -> bytearray:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT open_library_id FROM books.books "
            "WHERE open_library_id IS NOT NULL"
        )
    )
    filter_array = bytearray(_KNOWN_WORKS_MAX_ID // 8 + 1)
    count = 0
    for row in result:
        num = ol_id_to_int(row.open_library_id)
        if num is not None and num < _KNOWN_WORKS_MAX_ID:
            filter_array[num // 8] |= 1 << (num % 8)
            count += 1
    logger.info(
        f"[dump] Built known-works filter with {count} entries "
        f"({len(filter_array) // 1024}KB)"
    )
    return filter_array


async def batch_lookup_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    ol_ids: list[str],
) -> dict[str, tuple[int, str, str]]:
    if not ol_ids:
        return {}
    lookup: dict[str, tuple[int, str, str]] = {}
    chunk_size = 1000
    for i in range(0, len(ol_ids), chunk_size):
        chunk = ol_ids[i : i + chunk_size]
        placeholders = ", ".join(f":id_{j}" for j in range(len(chunk)))
        params = {f"id_{j}": v for j, v in enumerate(chunk)}
        result = await session.execute(
            sqlalchemy.text(
                "SELECT author_id, name, slug, open_library_id "
                f"FROM books.authors WHERE open_library_id IN ({placeholders})"
            ),
            params,
        )
        for row in result:
            lookup[row.open_library_id] = (row.author_id, row.name, row.slug)
    return lookup


async def batch_lookup_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    ol_ids: list[str],
) -> dict[str, list[tuple[int, str]]]:
    if not ol_ids:
        return {}
    book_map: dict[str, list[tuple[int, str]]] = {}
    chunk_size = 1000
    for i in range(0, len(ol_ids), chunk_size):
        chunk = ol_ids[i : i + chunk_size]
        placeholders = ", ".join(f":id_{j}" for j in range(len(chunk)))
        params = {f"id_{j}": v for j, v in enumerate(chunk)}
        result = await session.execute(
            sqlalchemy.text(
                "SELECT book_id, language, open_library_id "
                f"FROM books.books WHERE open_library_id IN ({placeholders})"
            ),
            params,
        )
        for row in result:
            if row.open_library_id not in book_map:
                book_map[row.open_library_id] = []
            book_map[row.open_library_id].append((row.book_id, row.language))
    return book_map
