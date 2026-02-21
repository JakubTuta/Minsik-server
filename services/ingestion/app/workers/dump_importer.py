import asyncio
import datetime
import gc
import gzip
import json
import logging
import re
import typing
from pathlib import Path

import app.config
import app.models
import app.utils
import httpx
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

logger = logging.getLogger(__name__)

_OL_COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
_OL_AUTHOR_PHOTO_URL = "https://covers.openlibrary.org/a/id/{photo_id}-L.jpg"

_OL_LANG_TO_ISO: dict[str, str] = {
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


_DOWNLOAD_MAX_RETRIES = 5
_DOWNLOAD_READ_TIMEOUT = 300
_DOWNLOAD_CONNECT_TIMEOUT = 60
_DOWNLOAD_LOG_EVERY_MB = 100


async def download_file(url: str, dest_path: str) -> None:
    logger.info(f"[dump] Downloading {url}")
    timeout = httpx.Timeout(
        connect=_DOWNLOAD_CONNECT_TIMEOUT,
        read=_DOWNLOAD_READ_TIMEOUT,
        write=30.0,
        pool=60.0,
    )

    downloaded = 0
    total_size: typing.Optional[int] = None
    last_logged_mb = 0

    for attempt in range(1, _DOWNLOAD_MAX_RETRIES + 1):
        headers: dict[str, str] = {}
        file_mode = "wb"

        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"
            file_mode = "ab"
            logger.info(
                f"[dump] Resuming download from {downloaded / (1024 * 1024):.0f} MB "
                f"(attempt {attempt}/{_DOWNLOAD_MAX_RETRIES})"
            )

        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True
            ) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code == 416:
                        logger.info("[dump] Download already complete (416 response)")
                        break

                    response.raise_for_status()

                    if total_size is None:
                        content_length = response.headers.get("content-length")
                        if content_length:
                            total_size = int(content_length) + downloaded

                    with open(dest_path, file_mode) as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            current_mb = downloaded / (1024 * 1024)
                            if current_mb - last_logged_mb >= _DOWNLOAD_LOG_EVERY_MB:
                                last_logged_mb = current_mb
                                total_mb = (
                                    total_size / (1024 * 1024) if total_size else None
                                )
                                if total_mb:
                                    pct = (downloaded / total_size) * 100
                                    logger.info(
                                        f"[dump] Download progress: "
                                        f"{current_mb:.0f}/{total_mb:.0f} MB "
                                        f"({pct:.1f}%)"
                                    )
                                else:
                                    logger.info(
                                        f"[dump] Download progress: "
                                        f"{current_mb:.0f} MB"
                                    )

            logger.info(
                f"[dump] Downloaded to {dest_path} "
                f"({downloaded / (1024 * 1024):.0f} MB)"
            )
            return

        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
            httpx.ReadError,
            httpx.ConnectError,
        ) as e:
            if attempt == _DOWNLOAD_MAX_RETRIES:
                logger.error(
                    f"[dump] Download failed after {_DOWNLOAD_MAX_RETRIES} attempts: {e}"
                )
                raise

            wait_seconds = min(30 * (2 ** (attempt - 1)), 300)
            logger.warning(
                f"[dump] Download interrupted ({type(e).__name__}), "
                f"downloaded {downloaded / (1024 * 1024):.0f} MB so far. "
                f"Retrying in {wait_seconds}s (attempt {attempt}/{_DOWNLOAD_MAX_RETRIES})"
            )
            await asyncio.sleep(wait_seconds)


async def _stream_parse_dump(
    file_path: str,
    record_type: str,
    queue: asyncio.Queue[typing.Optional[typing.List[dict]]],
    batch_size: int,
) -> None:
    loop = asyncio.get_running_loop()

    def _sync_reader() -> None:
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            batch: list[dict] = []
            for line in f:
                try:
                    parts = line.rstrip("\n").split("\t", 4)
                    if len(parts) != 5:
                        continue
                    if parts[0] != record_type:
                        continue

                    data = json.loads(parts[4])
                    batch.append(data)
                    if len(batch) >= batch_size:
                        asyncio.run_coroutine_threadsafe(
                            queue.put(batch[:]), loop
                        ).result()
                        batch = []
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue

            if batch:
                asyncio.run_coroutine_threadsafe(queue.put(batch), loop).result()

        asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    await asyncio.to_thread(_sync_reader)


def _extract_text_value(field: typing.Any) -> typing.Optional[str]:
    if isinstance(field, dict):
        return field.get("value")
    if isinstance(field, str):
        return field
    return None


def _extract_description(data: typing.Any) -> typing.Optional[str]:
    raw = _extract_text_value(data)
    if raw:
        return app.utils.clean_description(raw)
    return None


def _extract_cover_url(covers: typing.Optional[list]) -> typing.Optional[str]:
    if not covers or not isinstance(covers, list):
        return None
    for cover_id in covers:
        if isinstance(cover_id, int) and cover_id > 0:
            return _OL_COVER_URL.format(cover_id=cover_id)
    return None


def _parse_free_date(
    date_string: typing.Optional[str],
) -> typing.Optional[datetime.date]:
    if not date_string:
        return None
    return app.utils.parse_date(str(date_string).strip())


def _extract_remote_ids(author_data: dict) -> dict[str, str]:
    remote_ids: dict[str, str] = {}
    raw = author_data.get("remote_ids")
    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, str) and val:
                remote_ids[key] = val
    return remote_ids


def _extract_ol_lang(lang_ref: typing.Any) -> typing.Optional[str]:
    if isinstance(lang_ref, dict):
        key = lang_ref.get("key", "")
        code = key.replace("/languages/", "")
        return _OL_LANG_TO_ISO.get(code)
    if isinstance(lang_ref, str):
        code = lang_ref.replace("/languages/", "")
        return _OL_LANG_TO_ISO.get(code)
    return None


def _parse_series_string(series_strs: typing.Optional[list]) -> typing.Optional[dict]:
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


def _ol_id_to_int(ol_id: str) -> typing.Optional[int]:
    if len(ol_id) >= 3 and ol_id[:2] == "OL" and ol_id[-1].isalpha():
        try:
            return int(ol_id[2:-1])
        except ValueError:
            return None
    return None


_KNOWN_WORKS_MAX_ID = 60_000_000


async def _build_known_works_filter(
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
        num = _ol_id_to_int(row.open_library_id)
        if num is not None and num < _KNOWN_WORKS_MAX_ID:
            filter_array[num // 8] |= 1 << (num % 8)
            count += 1
    logger.info(
        f"[dump] Built known-works filter with {count} entries "
        f"({len(filter_array) // 1024}KB)"
    )
    return filter_array


def _is_known_work(filter_array: bytearray, ol_id: str) -> bool:
    num = _ol_id_to_int(ol_id)
    if num is None or num >= _KNOWN_WORKS_MAX_ID:
        return False
    return bool(filter_array[num // 8] & (1 << (num % 8)))


async def _batch_lookup_authors(
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


async def _batch_lookup_books(
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


# ---------------------------------------------------------------------------
# Phase 1: Authors
# ---------------------------------------------------------------------------


async def process_authors_dump(file_path: str) -> int:
    queue: asyncio.Queue[typing.Optional[typing.List[dict]]] = asyncio.Queue(
        maxsize=100
    )

    parse_task = asyncio.create_task(
        _stream_parse_dump(
            file_path, "/type/author", queue, app.config.settings.dump_batch_size
        )
    )

    total_count = 0
    last_committed = 0
    commit_interval = app.config.settings.dump_commit_interval

    async with app.models.AsyncSessionLocal() as session:
        try:
            while True:
                batch = await queue.get()
                if batch is None:
                    break

                insert_data = []
                for author_data in batch:
                    try:
                        name = author_data.get("name")
                        if not name:
                            continue
                        name = name[:300]

                        bio_raw = author_data.get("bio")
                        bio = _extract_description(bio_raw) if bio_raw else None

                        photo_url = None
                        photos = author_data.get("photos")
                        if photos and isinstance(photos, list):
                            for photo_id in photos:
                                if isinstance(photo_id, int) and photo_id > 0:
                                    photo_url = _OL_AUTHOR_PHOTO_URL.format(
                                        photo_id=photo_id
                                    )
                                    break

                        remote_ids = _extract_remote_ids(author_data)
                        wikidata_id = remote_ids.get("wikidata")
                        wikipedia_url = author_data.get("wikipedia")
                        if isinstance(
                            wikipedia_url, str
                        ) and not wikipedia_url.startswith("http"):
                            wikipedia_url = None

                        alternate_names = author_data.get("alternate_names", [])
                        if not isinstance(alternate_names, list):
                            alternate_names = []
                        alternate_names = [
                            n for n in alternate_names if isinstance(n, str) and n
                        ][:20]

                        ol_id = author_data.get("key", "").replace("/authors/", "")

                        insert_data.append(
                            {
                                "name": name,
                                "slug": app.utils.slugify(name),
                                "bio": bio,
                                "birth_date": _parse_free_date(
                                    author_data.get("birth_date")
                                ),
                                "death_date": _parse_free_date(
                                    author_data.get("death_date")
                                ),
                                "photo_url": photo_url,
                                "open_library_id": ol_id,
                                "wikidata_id": wikidata_id,
                                "wikipedia_url": wikipedia_url,
                                "remote_ids": remote_ids,
                                "alternate_names": alternate_names,
                            }
                        )
                        total_count += 1
                    except Exception as e:
                        logger.debug(f"Error preparing author: {e}")
                        continue

                seen_slugs: dict[str, int] = {}
                for idx, row in enumerate(insert_data):
                    seen_slugs[row["slug"]] = idx
                insert_data = [insert_data[i] for i in sorted(seen_slugs.values())]

                if insert_data:
                    try:
                        stmt = postgresql_insert(app.models.Author).values(insert_data)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["slug"],
                            set_={
                                "bio": sqlalchemy.case(
                                    (
                                        app.models.Author.bio.is_(None),
                                        stmt.excluded.bio,
                                    ),
                                    else_=app.models.Author.bio,
                                ),
                                "birth_date": sqlalchemy.case(
                                    (
                                        app.models.Author.birth_date.is_(None),
                                        stmt.excluded.birth_date,
                                    ),
                                    else_=app.models.Author.birth_date,
                                ),
                                "death_date": sqlalchemy.case(
                                    (
                                        app.models.Author.death_date.is_(None),
                                        stmt.excluded.death_date,
                                    ),
                                    else_=app.models.Author.death_date,
                                ),
                                "photo_url": sqlalchemy.case(
                                    (
                                        app.models.Author.photo_url.is_(None),
                                        stmt.excluded.photo_url,
                                    ),
                                    else_=app.models.Author.photo_url,
                                ),
                                "open_library_id": stmt.excluded.open_library_id,
                                "wikidata_id": sqlalchemy.case(
                                    (
                                        app.models.Author.wikidata_id.is_(None),
                                        stmt.excluded.wikidata_id,
                                    ),
                                    else_=app.models.Author.wikidata_id,
                                ),
                                "wikipedia_url": sqlalchemy.case(
                                    (
                                        app.models.Author.wikipedia_url.is_(None),
                                        stmt.excluded.wikipedia_url,
                                    ),
                                    else_=app.models.Author.wikipedia_url,
                                ),
                                "remote_ids": stmt.excluded.remote_ids,
                                "alternate_names": stmt.excluded.alternate_names,
                            },
                        )
                        await session.execute(stmt)

                        if total_count - last_committed >= commit_interval:
                            await session.commit()
                            last_committed = total_count
                            logger.info(f"[dump] Authors processed: {total_count}")
                    except Exception as e:
                        logger.warning(f"Error bulk inserting authors: {e}")
                        await session.rollback()

            await session.commit()
            logger.info(f"[dump] Phase 1 complete: {total_count} authors upserted")
            return total_count

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_authors_dump: {e}")
            raise
        finally:
            await parse_task


# ---------------------------------------------------------------------------
# Phase 2: Wikidata enrichment
# ---------------------------------------------------------------------------

_WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
_WIKIDATA_SPARQL_BATCH = 200
_WIKIDATA_REQUEST_DELAY = 1.5
_WIKIDATA_MAX_RETRIES = 3
_WIKIDATA_LOG_INTERVAL = 100


async def process_wikidata_enrichment() -> int:
    async with app.models.AsyncSessionLocal() as session:
        result = await session.execute(
            sqlalchemy.text(
                "SELECT wikidata_id FROM books.authors "
                "WHERE wikidata_id IS NOT NULL "
                "AND (nationality IS NULL OR birth_place IS NULL)"
            )
        )
        wikidata_ids = [row.wikidata_id for row in result]

    if not wikidata_ids:
        logger.info("[dump] No authors need Wikidata enrichment")
        return 0

    logger.info(f"[dump] Found {len(wikidata_ids)} authors needing Wikidata enrichment")

    updated_count = 0
    batch_count = 0
    timeout = httpx.Timeout(connect=30, read=90, write=30, pool=60)
    headers = {
        "User-Agent": "MinsikBot/1.0 (book-catalog; https://github.com/minsik)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        async with app.models.AsyncSessionLocal() as session:
            for i in range(0, len(wikidata_ids), _WIKIDATA_SPARQL_BATCH):
                batch_ids = wikidata_ids[i : i + _WIKIDATA_SPARQL_BATCH]
                batch_count += 1

                try:
                    enrichment = await _fetch_wikidata_sparql_batch(client, batch_ids)
                    if enrichment:
                        updated_count += await _flush_wikidata_updates(
                            session, enrichment
                        )
                except Exception as e:
                    logger.debug(f"Error fetching Wikidata batch: {e}")

                if batch_count % _WIKIDATA_LOG_INTERVAL == 0:
                    await session.commit()
                    logger.info(
                        f"[dump] Wikidata enrichment: "
                        f"{i + len(batch_ids)}/{len(wikidata_ids)}, "
                        f"updated: {updated_count}"
                    )

                await asyncio.sleep(_WIKIDATA_REQUEST_DELAY)

            await session.commit()

    logger.info(
        f"[dump] Phase 2 complete: {updated_count} authors enriched via Wikidata"
    )
    return updated_count


async def _fetch_wikidata_sparql_batch(
    client: httpx.AsyncClient,
    wikidata_ids: list[str],
) -> list[dict]:
    values_str = " ".join(f"wd:{wid}" for wid in wikidata_ids)
    query = (
        "SELECT ?item ?nationalityLabel ?birthPlaceLabel ?article WHERE { "
        f"VALUES ?item {{ {values_str} }} "
        "OPTIONAL { ?item wdt:P27 ?nationality } "
        "OPTIONAL { ?item wdt:P19 ?birthPlace } "
        "OPTIONAL { "
        "?article schema:about ?item ; "
        "schema:isPartOf <https://en.wikipedia.org/> . "
        "} "
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . } '
        "}"
    )

    for attempt in range(1, _WIKIDATA_MAX_RETRIES + 1):
        try:
            response = await client.get(
                _WIKIDATA_SPARQL_URL,
                params={"query": query, "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
            break
        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.HTTPStatusError,
            httpx.ConnectError,
        ) as e:
            if attempt == _WIKIDATA_MAX_RETRIES:
                logger.debug(
                    f"Wikidata SPARQL failed after {_WIKIDATA_MAX_RETRIES} "
                    f"attempts: {e}"
                )
                return []
            await asyncio.sleep(attempt * 3)

    enrichment_map: dict[str, dict] = {}
    for binding in data.get("results", {}).get("bindings", []):
        item_uri = binding.get("item", {}).get("value", "")
        wikidata_id = item_uri.rsplit("/", 1)[-1]
        if not wikidata_id:
            continue

        if wikidata_id not in enrichment_map:
            enrichment_map[wikidata_id] = {
                "wikidata_id": wikidata_id,
                "nationality": None,
                "birth_place": None,
                "wikipedia_url": None,
            }

        nat_label = binding.get("nationalityLabel", {}).get("value")
        bp_label = binding.get("birthPlaceLabel", {}).get("value")
        article_url = binding.get("article", {}).get("value")

        entry = enrichment_map[wikidata_id]
        if nat_label and not _is_wikidata_qid(nat_label) and not entry["nationality"]:
            entry["nationality"] = nat_label[:200]
        if bp_label and not _is_wikidata_qid(bp_label) and not entry["birth_place"]:
            entry["birth_place"] = bp_label[:500]
        if article_url and not entry["wikipedia_url"]:
            entry["wikipedia_url"] = article_url[:1000]

    return [
        v
        for v in enrichment_map.values()
        if v["nationality"] or v["birth_place"] or v["wikipedia_url"]
    ]


def _is_wikidata_qid(value: str) -> bool:
    return len(value) >= 2 and value[0] == "Q" and value[1:].isdigit()


async def _flush_wikidata_updates(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    updates: list[dict],
) -> int:
    if not updates:
        return 0

    count = 0
    batch_size = 500
    for i in range(0, len(updates), batch_size):
        sub_batch = updates[i : i + batch_size]
        values_parts: list[str] = []
        params: dict[str, typing.Any] = {}
        for k, update in enumerate(sub_batch):
            values_parts.append(f"(:wid_{k}, :nat_{k}, :bp_{k}, :wurl_{k})")
            params[f"wid_{k}"] = update["wikidata_id"]
            params[f"nat_{k}"] = update["nationality"]
            params[f"bp_{k}"] = update["birth_place"]
            params[f"wurl_{k}"] = update["wikipedia_url"]

        await session.execute(
            sqlalchemy.text(
                "UPDATE books.authors AS a SET "
                "nationality = COALESCE(a.nationality, v.nat), "
                "birth_place = COALESCE(a.birth_place, v.bp), "
                "wikipedia_url = COALESCE(a.wikipedia_url, v.wurl) "
                f"FROM (VALUES {', '.join(values_parts)}) "
                "AS v(wid, nat, bp, wurl) "
                "WHERE a.wikidata_id = v.wid"
            ),
            params,
        )
        count += len(sub_batch)
    return count


# ---------------------------------------------------------------------------
# Phase 3: Works
# ---------------------------------------------------------------------------


async def process_works_dump(file_path: str) -> int:
    queue: asyncio.Queue[typing.Optional[typing.List[dict]]] = asyncio.Queue(
        maxsize=100
    )

    parse_task = asyncio.create_task(
        _stream_parse_dump(
            file_path,
            "/type/work",
            queue,
            app.config.settings.dump_batch_size,
        )
    )

    total_count = 0
    successful = 0
    failed = 0
    last_committed = 0
    commit_interval = app.config.settings.dump_commit_interval

    async with app.models.AsyncSessionLocal() as session:
        try:
            while True:
                batch = await queue.get()
                if batch is None:
                    break

                batch_author_ol_ids: set[str] = set()
                for work_data in batch:
                    for author_ref in work_data.get("authors", []):
                        if not isinstance(author_ref, dict):
                            continue
                        author_obj = author_ref.get("author")
                        if not isinstance(author_obj, dict):
                            continue
                        ol_id = author_obj.get("key", "").replace("/authors/", "")
                        if ol_id:
                            batch_author_ol_ids.add(ol_id)

                author_lookup = await _batch_lookup_authors(
                    session, list(batch_author_ol_ids)
                )

                books_to_insert: list[dict] = []
                for work_data in batch:
                    total_count += 1
                    try:
                        title = work_data.get("title")
                        if not title:
                            failed += 1
                            continue

                        authors_list = []
                        for author_ref in work_data.get("authors", []):
                            if not isinstance(author_ref, dict):
                                continue
                            author_obj = author_ref.get("author")
                            if not isinstance(author_obj, dict):
                                continue
                            author_key = author_obj.get("key", "")
                            ol_id = author_key.replace("/authors/", "")
                            if ol_id and ol_id in author_lookup:
                                _aid, name, slug = author_lookup[ol_id]
                                authors_list.append(
                                    {
                                        "name": name,
                                        "slug": slug,
                                        "open_library_id": ol_id,
                                    }
                                )

                        subjects = work_data.get("subjects", [])
                        genres_list = []
                        for subject in subjects[:5]:
                            if isinstance(subject, str):
                                genre_name = subject.lower()[:100]
                                genre_slug = app.utils.slugify(genre_name)[:150]
                                if not genre_slug:
                                    continue
                                genres_list.append(
                                    {
                                        "name": genre_name,
                                        "slug": genre_slug,
                                    }
                                )

                        description = _extract_description(work_data.get("description"))
                        pub_date = _parse_free_date(work_data.get("first_publish_date"))
                        pub_year = pub_date.year if pub_date else None
                        cover_url = _extract_cover_url(work_data.get("covers"))
                        work_ol_id = work_data.get("key", "").replace("/works/", "")

                        books_to_insert.append(
                            {
                                "title": title,
                                "language": "en",
                                "description": description,
                                "original_publication_year": pub_year,
                                "primary_cover_url": cover_url,
                                "open_library_id": work_ol_id,
                                "google_books_id": None,
                                "authors": authors_list,
                                "genres": genres_list,
                                "formats": [],
                                "cover_history": [],
                                "series": None,
                            }
                        )

                    except Exception as e:
                        logger.debug(f"Error preparing work: {e}")
                        failed += 1

                if books_to_insert:
                    try:
                        from app.services import book_service

                        prebuilt_author_id_map = {
                            slug: aid for aid, _name, slug in author_lookup.values()
                        }
                        result = await book_service.insert_books_batch(
                            session,
                            books_to_insert,
                            commit=False,
                            author_id_map=prebuilt_author_id_map,
                        )
                        successful += result["successful"]
                        failed += result["failed"]
                    except Exception as e:
                        logger.error(f"[dump] Error batch inserting works: {e}")
                        await session.rollback()
                        failed += len(books_to_insert)
                        continue

                if total_count - last_committed >= commit_interval:
                    await session.commit()
                    last_committed = total_count
                    logger.info(
                        f"[dump] Works processed: {total_count}, "
                        f"successful: {successful}, failed: {failed}"
                    )

            await session.commit()
            logger.info(
                f"[dump] Phase 3 complete: {total_count} processed, "
                f"{successful} successful, {failed} failed"
            )
            return successful

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_works_dump: {e}")
            raise
        finally:
            await parse_task


# ---------------------------------------------------------------------------
# Phase 4: Editions
# ---------------------------------------------------------------------------


def _score_edition(edition: dict) -> int:
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


async def process_editions_dump(
    file_path: str,
    known_works_filter: bytearray,
) -> dict[str, int]:
    queue: asyncio.Queue[typing.Optional[typing.List[dict]]] = asyncio.Queue(
        maxsize=100
    )
    parse_task = asyncio.create_task(
        _stream_parse_dump(
            file_path,
            "/type/edition",
            queue,
            app.config.settings.dump_edition_batch_size,
        )
    )

    total_processed = 0
    enriched = 0
    new_lang_rows = 0
    skipped = 0
    last_logged = 0
    last_flushed = 0
    commit_interval = app.config.settings.dump_commit_interval
    flush_interval = app.config.settings.dump_edition_flush_interval

    best_editions: dict[str, dict] = {}

    async with app.models.AsyncSessionLocal() as session:
        try:
            while True:
                batch = await queue.get()
                if batch is None:
                    break

                for edition_data in batch:
                    total_processed += 1
                    try:
                        works_ref = edition_data.get("works", [])
                        if not works_ref or not isinstance(works_ref, list):
                            skipped += 1
                            continue
                        first_work = works_ref[0]
                        work_key = (
                            first_work.get("key", "")
                            if isinstance(first_work, dict)
                            else ""
                        )
                        work_ol_id = work_key.replace("/works/", "")
                        if not work_ol_id or not _is_known_work(
                            known_works_filter, work_ol_id
                        ):
                            skipped += 1
                            continue

                        languages = edition_data.get("languages", [])
                        lang_code = "en"
                        if languages and isinstance(languages, list):
                            detected = _extract_ol_lang(languages[0])
                            if detected:
                                lang_code = detected

                        isbns: list[str] = []
                        for isbn10 in edition_data.get("isbn_10") or []:
                            if isinstance(isbn10, str) and isbn10:
                                isbns.append(isbn10)
                        for isbn13 in edition_data.get("isbn_13") or []:
                            if isinstance(isbn13, str) and isbn13:
                                isbns.append(isbn13)

                        page_count = edition_data.get("number_of_pages")
                        if not isinstance(page_count, int) or page_count <= 0:
                            page_count = None

                        publishers = edition_data.get("publishers", [])
                        publisher = None
                        if (
                            publishers
                            and isinstance(publishers, list)
                            and isinstance(publishers[0], str)
                        ):
                            publisher = publishers[0][:500]

                        physical_format = edition_data.get("physical_format")
                        if isinstance(physical_format, str):
                            physical_format = physical_format.lower().strip()
                        else:
                            physical_format = None

                        ext_ids: dict[str, str] = {}
                        identifiers = edition_data.get("identifiers", {})
                        if isinstance(identifiers, dict):
                            for id_key, id_vals in identifiers.items():
                                if (
                                    isinstance(id_vals, list)
                                    and id_vals
                                    and isinstance(id_vals[0], str)
                                ):
                                    ext_ids[id_key] = id_vals[0]

                        cover_url = _extract_cover_url(edition_data.get("covers"))
                        description = _extract_description(
                            edition_data.get("description")
                        )

                        series_data = _parse_series_string(edition_data.get("series"))

                        score = _score_edition(edition_data)

                        edition_key = f"{work_ol_id}:{lang_code}"
                        existing = best_editions.get(edition_key)
                        if existing is None or score > existing.get("_score", 0):
                            best_editions[edition_key] = {
                                "work_ol_id": work_ol_id,
                                "lang_code": lang_code,
                                "isbns": isbns,
                                "page_count": page_count,
                                "publisher": publisher,
                                "physical_format": physical_format,
                                "external_ids": ext_ids,
                                "cover_url": cover_url,
                                "description": description,
                                "series": series_data,
                                "_score": score,
                            }
                        else:
                            if existing and isbns:
                                existing_isbns = set(existing.get("isbns", []))
                                for isbn in isbns:
                                    if isbn not in existing_isbns:
                                        existing["isbns"].append(isbn)

                    except Exception as e:
                        logger.debug(f"Error parsing edition: {e}")
                        skipped += 1

                if total_processed - last_flushed >= flush_interval:
                    e, n = await _flush_best_editions_chunk(session, best_editions)
                    enriched += e
                    new_lang_rows += n
                    best_editions.clear()
                    last_flushed = total_processed
                    gc.collect()
                    logger.info(
                        f"[dump] Editions chunk flushed at {total_processed}, "
                        f"enriched so far: {enriched}, "
                        f"new lang rows: {new_lang_rows}"
                    )

                if total_processed - last_logged >= commit_interval * 4:
                    last_logged = total_processed
                    logger.info(
                        f"[dump] Editions scanned: {total_processed}, "
                        f"best-of candidates: {len(best_editions)}, "
                        f"skipped: {skipped}"
                    )

            logger.info(
                f"[dump] Edition scanning complete: {total_processed} scanned, "
                f"{len(best_editions)} remaining best-of candidates"
            )

            e, n = await _flush_best_editions_chunk(session, best_editions)
            enriched += e
            new_lang_rows += n
            best_editions.clear()

            logger.info(
                f"[dump] Phase 4 complete: {total_processed} editions scanned, "
                f"{enriched} books enriched, {new_lang_rows} new language rows"
            )
            return {
                "processed": total_processed,
                "enriched": enriched,
                "new_lang_rows": new_lang_rows,
                "skipped": skipped,
            }

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_editions_dump: {e}")
            raise
        finally:
            await parse_task


async def _flush_best_editions_chunk(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    best_editions: dict[str, dict],
) -> tuple[int, int]:
    if not best_editions:
        return 0, 0

    work_ol_ids = list({ed["work_ol_id"] for ed in best_editions.values()})
    book_lookup = await _batch_lookup_books(session, work_ol_ids)

    enriched = 0
    new_lang_rows = 0
    batch_updates: list[dict] = []

    for ed in best_editions.values():
        work_ol_id = ed["work_ol_id"]
        lang_code = ed["lang_code"]
        book_rows = book_lookup.get(work_ol_id, [])

        matching_book_id = None
        en_book_id = None
        for book_id, language in book_rows:
            if language == lang_code:
                matching_book_id = book_id
                break
            if language == "en":
                en_book_id = book_id

        if matching_book_id is not None:
            batch_updates.append(
                {
                    "book_id": matching_book_id,
                    "isbn": ed["isbns"][:20],
                    "number_of_pages": ed["page_count"],
                    "publisher": ed["publisher"],
                    "external_ids": ed["external_ids"],
                    "cover_url": ed["cover_url"],
                    "description": ed["description"],
                    "physical_format": ed["physical_format"],
                    "series": ed["series"],
                }
            )
            enriched += 1
        elif lang_code != "en" and en_book_id is not None:
            batch_updates.append(
                {
                    "book_id": None,
                    "source_book_id": en_book_id,
                    "work_ol_id": work_ol_id,
                    "lang_code": lang_code,
                    "isbn": ed["isbns"][:20],
                    "number_of_pages": ed["page_count"],
                    "publisher": ed["publisher"],
                    "external_ids": ed["external_ids"],
                    "cover_url": ed["cover_url"],
                    "description": ed["description"],
                    "physical_format": ed["physical_format"],
                    "series": ed["series"],
                }
            )
            new_lang_rows += 1

        if len(batch_updates) >= 500:
            await _flush_edition_updates(session, batch_updates)
            batch_updates = []
            await session.commit()

    if batch_updates:
        await _flush_edition_updates(session, batch_updates)
    await session.commit()

    return enriched, new_lang_rows


async def _flush_edition_updates(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    updates: list[dict],
) -> None:
    existing_updates: list[dict] = []
    new_lang_updates: list[dict] = []
    for update in updates:
        if update.get("book_id") is not None:
            existing_updates.append(update)
        else:
            new_lang_updates.append(update)

    batch_size = 500
    for i in range(0, len(existing_updates), batch_size):
        sub = existing_updates[i : i + batch_size]
        values_parts: list[str] = []
        params: dict[str, typing.Any] = {}
        for k, u in enumerate(sub):
            values_parts.append(
                f"(:bid_{k}::bigint, :isbn_{k}::jsonb, :pages_{k}::int, "
                f":pub_{k}, :ext_{k}::jsonb, :cover_{k}, :desc_{k}, :fmt_{k}::jsonb)"
            )
            params[f"bid_{k}"] = u["book_id"]
            params[f"isbn_{k}"] = json.dumps(u["isbn"]) if u["isbn"] else None
            params[f"pages_{k}"] = u["number_of_pages"]
            params[f"pub_{k}"] = u["publisher"][:500] if u["publisher"] else None
            params[f"ext_{k}"] = (
                json.dumps(u["external_ids"]) if u["external_ids"] else None
            )
            params[f"cover_{k}"] = u["cover_url"][:1000] if u["cover_url"] else None
            params[f"desc_{k}"] = u["description"]
            params[f"fmt_{k}"] = (
                json.dumps([u["physical_format"]]) if u["physical_format"] else None
            )

        try:
            await session.execute(
                sqlalchemy.text(
                    "UPDATE books.books AS b SET "
                    "isbn = CASE WHEN v.isbn IS NOT NULL THEN v.isbn ELSE b.isbn END, "
                    "number_of_pages = COALESCE(b.number_of_pages, v.pages), "
                    "publisher = COALESCE(b.publisher, v.pub), "
                    "external_ids = CASE WHEN v.ext IS NOT NULL "
                    "THEN v.ext ELSE b.external_ids END, "
                    "primary_cover_url = COALESCE(b.primary_cover_url, v.cover), "
                    "description = COALESCE(b.description, v.descr), "
                    "formats = CASE "
                    "WHEN v.fmt IS NOT NULL AND NOT b.formats @> v.fmt "
                    "THEN b.formats || v.fmt ELSE b.formats END "
                    f"FROM (VALUES {', '.join(values_parts)}) "
                    "AS v(bid, isbn, pages, pub, ext, cover, descr, fmt) "
                    "WHERE b.book_id = v.bid"
                ),
                params,
            )
        except Exception as e:
            logger.debug(f"Error batch updating editions: {e}")

    for update in new_lang_updates:
        try:
            await _insert_new_language_row(session, update)
        except Exception as e:
            logger.debug(f"Error inserting new language row: {e}")


async def _insert_new_language_row(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    update: dict,
) -> None:
    source_id = update["source_book_id"]
    lang = update["lang_code"]
    work_ol_id = update["work_ol_id"]

    source_result = await session.execute(
        sqlalchemy.text(
            "SELECT title, slug, description, original_publication_year, "
            "primary_cover_url, open_library_id, series_id, series_position "
            "FROM books.books WHERE book_id = :sid"
        ),
        {"sid": source_id},
    )
    source = source_result.first()
    if not source:
        return

    slug = app.utils.slugify(source.title)

    title = source.title[:500] if source.title else source.title
    cover_url = update["cover_url"] or source.primary_cover_url
    if isinstance(cover_url, str):
        cover_url = cover_url[:1000]
    publisher = update["publisher"]
    if isinstance(publisher, str):
        publisher = publisher[:500]
    series_position = source.series_position
    if isinstance(series_position, (int, float)) and series_position > 999.99:
        series_position = None

    insert_data = {
        "title": title,
        "language": lang,
        "slug": slug,
        "description": update["description"] or source.description,
        "original_publication_year": source.original_publication_year,
        "primary_cover_url": cover_url,
        "open_library_id": work_ol_id,
        "isbn": update["isbn"] or [],
        "publisher": publisher,
        "number_of_pages": update["number_of_pages"],
        "external_ids": update["external_ids"] or {},
        "formats": ([update["physical_format"]] if update["physical_format"] else []),
        "series_id": source.series_id,
        "series_position": series_position,
    }

    stmt = postgresql_insert(app.models.Book).values(insert_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["language", "slug"],
        set_={
            "isbn": stmt.excluded.isbn,
            "publisher": stmt.excluded.publisher,
            "number_of_pages": stmt.excluded.number_of_pages,
            "external_ids": stmt.excluded.external_ids,
        },
    )
    stmt = stmt.returning(app.models.Book.book_id)
    result = await session.execute(stmt)
    new_row = result.first()
    if not new_row:
        return

    await session.execute(
        sqlalchemy.text(
            "INSERT INTO books.book_authors (book_id, author_id) "
            "SELECT :new_bid, author_id FROM books.book_authors "
            "WHERE book_id = :sid ON CONFLICT DO NOTHING"
        ),
        {"new_bid": new_row.book_id, "sid": source_id},
    )

    await session.execute(
        sqlalchemy.text(
            "INSERT INTO books.book_genres (book_id, genre_id) "
            "SELECT :new_bid, genre_id FROM books.book_genres "
            "WHERE book_id = :sid ON CONFLICT DO NOTHING"
        ),
        {"new_bid": new_row.book_id, "sid": source_id},
    )


# ---------------------------------------------------------------------------
# Phase 5: Ratings
# ---------------------------------------------------------------------------


async def process_ratings_dump(file_path: str) -> int:
    def _parse_ratings_file() -> dict[str, dict[str, typing.Any]]:
        rating_agg: dict[str, dict[str, typing.Any]] = {}
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        continue
                    work_key = parts[0].strip().replace("/works/", "")
                    rating_val = int(parts[2].strip())
                    if rating_val < 1 or rating_val > 5:
                        continue

                    if work_key not in rating_agg:
                        rating_agg[work_key] = {"count": 0, "total": 0}
                    rating_agg[work_key]["count"] += 1
                    rating_agg[work_key]["total"] += rating_val
                except (ValueError, IndexError):
                    continue
        return rating_agg

    rating_agg = await asyncio.to_thread(_parse_ratings_file)
    logger.info(f"[dump] Parsed {len(rating_agg)} works with ratings")

    updated = 0
    async with app.models.AsyncSessionLocal() as session:
        try:
            work_ol_ids = list(rating_agg.keys())
            chunk_size = 1000
            for i in range(0, len(work_ol_ids), chunk_size):
                chunk_ids = work_ol_ids[i : i + chunk_size]
                book_lookup = await _batch_lookup_books(session, chunk_ids)

                batch_params: list[dict] = []
                for work_ol_id in chunk_ids:
                    book_rows = book_lookup.get(work_ol_id)
                    if not book_rows:
                        continue
                    agg = rating_agg[work_ol_id]
                    avg = round(agg["total"] / agg["count"], 2)
                    for book_id, _language in book_rows:
                        batch_params.append(
                            {"bid": book_id, "cnt": agg["count"], "avg": avg}
                        )

                for j in range(0, len(batch_params), 500):
                    sub = batch_params[j : j + 500]
                    values_parts: list[str] = []
                    params: dict[str, typing.Any] = {}
                    for k, p in enumerate(sub):
                        values_parts.append(
                            f"(:bid_{k}::bigint, :cnt_{k}::int, :avg_{k}::numeric)"
                        )
                        params[f"bid_{k}"] = p["bid"]
                        params[f"cnt_{k}"] = p["cnt"]
                        params[f"avg_{k}"] = p["avg"]
                    await session.execute(
                        sqlalchemy.text(
                            "UPDATE books.books AS b SET "
                            "ol_rating_count = v.cnt, ol_avg_rating = v.avg "
                            f"FROM (VALUES {', '.join(values_parts)}) "
                            "AS v(bid, cnt, avg) "
                            "WHERE b.book_id = v.bid"
                        ),
                        params,
                    )
                updated += len(batch_params)
                await session.commit()

            logger.info(
                f"[dump] Phase 5 complete: {updated} book rows updated with ratings"
            )
            return updated

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_ratings_dump: {e}")
            raise


# ---------------------------------------------------------------------------
# Phase 6: Reading Log
# ---------------------------------------------------------------------------


async def process_reading_log_dump(file_path: str) -> int:
    def _parse_reading_log_file() -> dict[str, dict[str, int]]:
        shelf_agg: dict[str, dict[str, int]] = {}
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        continue
                    work_key = parts[0].strip().replace("/works/", "")
                    shelf = parts[2].strip()

                    if work_key not in shelf_agg:
                        shelf_agg[work_key] = {"want": 0, "reading": 0, "read": 0}

                    if shelf == "Want to Read":
                        shelf_agg[work_key]["want"] += 1
                    elif shelf == "Currently Reading":
                        shelf_agg[work_key]["reading"] += 1
                    elif shelf == "Already Read":
                        shelf_agg[work_key]["read"] += 1
                except (ValueError, IndexError):
                    continue
        return shelf_agg

    shelf_agg = await asyncio.to_thread(_parse_reading_log_file)
    logger.info(f"[dump] Parsed {len(shelf_agg)} works with reading log data")

    updated = 0
    async with app.models.AsyncSessionLocal() as session:
        try:
            work_ol_ids = list(shelf_agg.keys())
            chunk_size = 1000
            for i in range(0, len(work_ol_ids), chunk_size):
                chunk_ids = work_ol_ids[i : i + chunk_size]
                book_lookup = await _batch_lookup_books(session, chunk_ids)

                batch_params: list[dict] = []
                for work_ol_id in chunk_ids:
                    book_rows = book_lookup.get(work_ol_id)
                    if not book_rows:
                        continue
                    counts = shelf_agg[work_ol_id]
                    for book_id, _language in book_rows:
                        batch_params.append(
                            {
                                "bid": book_id,
                                "want": counts["want"],
                                "reading": counts["reading"],
                                "read": counts["read"],
                            }
                        )

                for j in range(0, len(batch_params), 500):
                    sub = batch_params[j : j + 500]
                    values_parts: list[str] = []
                    params: dict[str, typing.Any] = {}
                    for k, p in enumerate(sub):
                        values_parts.append(
                            f"(:bid_{k}::bigint, :want_{k}::int, "
                            f":reading_{k}::int, :read_{k}::int)"
                        )
                        params[f"bid_{k}"] = p["bid"]
                        params[f"want_{k}"] = p["want"]
                        params[f"reading_{k}"] = p["reading"]
                        params[f"read_{k}"] = p["read"]
                    await session.execute(
                        sqlalchemy.text(
                            "UPDATE books.books AS b SET "
                            "ol_want_to_read_count = v.want, "
                            "ol_currently_reading_count = v.reading, "
                            "ol_already_read_count = v.already_read "
                            f"FROM (VALUES {', '.join(values_parts)}) "
                            "AS v(bid, want, reading, already_read) "
                            "WHERE b.book_id = v.bid"
                        ),
                        params,
                    )
                updated += len(batch_params)
                await session.commit()

            logger.info(
                f"[dump] Phase 6 complete: {updated} book rows updated with reading log"
            )
            return updated

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_reading_log_dump: {e}")
            raise


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


_REDIS_JOB_STATE_KEY = "dump_import_state"
_REDIS_JOB_STATE_TTL = 604800


def _get_job_state(redis_client: redis.Redis) -> typing.Optional[dict]:
    try:
        data = redis_client.get(_REDIS_JOB_STATE_KEY)
        if data:
            decoded = data.decode("utf-8") if isinstance(data, bytes) else str(data)
            return json.loads(decoded)
    except Exception:
        pass
    return None


def _save_job_state(redis_client: redis.Redis, state: dict) -> None:
    try:
        redis_client.set(
            _REDIS_JOB_STATE_KEY,
            json.dumps(state),
            ex=_REDIS_JOB_STATE_TTL,
        )
    except Exception:
        pass


def _clear_job_state(redis_client: redis.Redis) -> None:
    try:
        redis_client.delete(_REDIS_JOB_STATE_KEY)
    except Exception:
        pass


async def run_import_dump(job_id: str, redis_client: redis.Redis) -> None:
    tmp_dir = Path(app.config.settings.dump_tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    base_url = app.config.settings.ol_dump_base_url

    phase_files: dict[int, Path] = {
        1: tmp_dir / "ol_dump_authors.txt.gz",
        2: tmp_dir / "ol_dump_wikidata.txt.gz",
        3: tmp_dir / "ol_dump_works.txt.gz",
        4: tmp_dir / "ol_dump_editions.txt.gz",
        5: tmp_dir / "ol_dump_ratings.txt.gz",
        6: tmp_dir / "ol_dump_reading_log.txt.gz",
    }

    state = _get_job_state(redis_client)
    if state and state.get("job_id") == job_id:
        completed: set[int] = set(state.get("completed_phases", []))
        phase_results: dict[str, typing.Any] = state.get("phase_results", {})
    else:
        completed = set()
        phase_results = {}
        state = {
            "job_id": job_id,
            "completed_phases": [],
            "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "phase_results": {},
        }
        _save_job_state(redis_client, state)

    def _set_status(msg: str) -> None:
        try:
            redis_client.set(f"dump_import_{job_id}_status", msg, ex=86400)
            redis_client.set("dump_import_status", msg, ex=_REDIS_JOB_STATE_TTL)
        except Exception:
            pass

    def _finish_phase(phase: int, result: typing.Any = None) -> None:
        completed.add(phase)
        if result is not None:
            phase_results[str(phase)] = result
        phase_files[phase].unlink(missing_ok=True)
        state["completed_phases"] = sorted(completed)
        state["phase_results"] = phase_results
        _save_job_state(redis_client, state)
        gc.collect()

    if completed:
        logger.info(
            f"[dump] Resuming dump import (job_id: {job_id}), "
            f"phases already completed: {sorted(completed)}"
        )
    else:
        logger.info(f"[dump] Starting dump import (job_id: {job_id})")

    try:
        try:
            redis_client.set("dump_import_running", 1, ex=86400)
        except Exception:
            pass

        # --- Phase 1: Authors ---
        if 1 not in completed:
            _set_status("Phase 1/6: downloading authors dump")
            await download_file(
                f"{base_url}/ol_dump_authors_latest.txt.gz",
                str(phase_files[1]),
            )

            _set_status("Phase 1/6: processing authors")
            authors_count = await process_authors_dump(str(phase_files[1]))
            _finish_phase(1, {"count": authors_count})
        else:
            logger.info("[dump] Phase 1 (authors) already completed, skipping")

        # --- Phase 2: Wikidata ---
        if 2 not in completed:
            if app.config.settings.dump_wikidata_enabled:
                _set_status("Phase 2/6: enriching authors via Wikidata API")
                wikidata_count = await process_wikidata_enrichment()
                _finish_phase(2, {"count": wikidata_count})
            else:
                logger.info("[dump] Phase 2 skipped (wikidata disabled)")
                _finish_phase(2, {"skipped": True})
        else:
            logger.info("[dump] Phase 2 (wikidata) already completed, skipping")

        # --- Phase 3: Works ---
        if 3 not in completed:
            _set_status("Phase 3/6: downloading works dump")
            await download_file(
                f"{base_url}/ol_dump_works_latest.txt.gz",
                str(phase_files[3]),
            )

            _set_status("Phase 3/6: processing works")
            works_count = await process_works_dump(str(phase_files[3]))
            _finish_phase(3, {"count": works_count})
        else:
            logger.info("[dump] Phase 3 (works) already completed, skipping")

        # --- Phase 4: Editions ---
        if 4 not in completed:
            if app.config.settings.dump_editions_enabled:
                _set_status("Phase 4/6: building known-works filter")
                async with app.models.AsyncSessionLocal() as session:
                    known_works_filter = await _build_known_works_filter(session)

                _set_status("Phase 4/6: downloading editions dump")
                await download_file(
                    f"{base_url}/ol_dump_editions_latest.txt.gz",
                    str(phase_files[4]),
                )

                _set_status("Phase 4/6: processing editions")
                editions_stats = await process_editions_dump(
                    str(phase_files[4]), known_works_filter
                )
                del known_works_filter
                _finish_phase(4, editions_stats)
            else:
                logger.info("[dump] Phase 4 skipped (editions disabled)")
                _finish_phase(4, {"skipped": True})
        else:
            logger.info("[dump] Phase 4 (editions) already completed, skipping")

        # --- Phase 5: Ratings ---
        if 5 not in completed:
            if app.config.settings.dump_ratings_enabled:
                _set_status("Phase 5/6: downloading ratings dump")
                await download_file(
                    f"{base_url}/ol_dump_ratings_latest.txt.gz",
                    str(phase_files[5]),
                )

                _set_status("Phase 5/6: processing ratings")
                ratings_count = await process_ratings_dump(str(phase_files[5]))
                _finish_phase(5, {"count": ratings_count})
            else:
                logger.info("[dump] Phase 5 skipped (ratings disabled)")
                _finish_phase(5, {"skipped": True})
        else:
            logger.info("[dump] Phase 5 (ratings) already completed, skipping")

        # --- Phase 6: Reading Log ---
        if 6 not in completed:
            if app.config.settings.dump_reading_log_enabled:
                _set_status("Phase 6/6: downloading reading log dump")
                await download_file(
                    f"{base_url}/ol_dump_reading-log_latest.txt.gz",
                    str(phase_files[6]),
                )

                _set_status("Phase 6/6: processing reading log")
                reading_log_count = await process_reading_log_dump(str(phase_files[6]))
                _finish_phase(6, {"count": reading_log_count})
            else:
                logger.info("[dump] Phase 6 skipped (reading log disabled)")
                _finish_phase(6, {"skipped": True})
        else:
            logger.info("[dump] Phase 6 (reading log) already completed, skipping")

        p = phase_results
        summary = (
            f"Complete: "
            f"{p.get('1', {}).get('count', 0)} authors, "
            f"{p.get('2', {}).get('count', 0)} wikidata enriched, "
            f"{p.get('3', {}).get('count', 0)} works, "
            f"{p.get('4', {}).get('enriched', 0)} editions enriched, "
            f"{p.get('4', {}).get('new_lang_rows', 0)} new language rows, "
            f"{p.get('5', {}).get('count', 0)} ratings applied, "
            f"{p.get('6', {}).get('count', 0)} reading log applied"
        )
        logger.info(f"[dump] {summary}")
        _set_status(summary)

    except Exception as e:
        logger.error(f"[dump] Dump import failed: {e}")
        _set_status(f"Failed: {e}")
        raise

    finally:
        for f in phase_files.values():
            f.unlink(missing_ok=True)
        try:
            redis_client.delete("dump_import_running")
            if completed == {1, 2, 3, 4, 5, 6}:
                _clear_job_state(redis_client)
        except Exception:
            pass
