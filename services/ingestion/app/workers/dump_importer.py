import asyncio
import datetime
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


async def download_file(url: str, dest_path: str) -> None:
    logger.info(f"[dump] Downloading {url}")
    async with httpx.AsyncClient(timeout=3600, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
    logger.info(f"[dump] Downloaded to {dest_path}")


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


async def _build_author_map(
    session: sqlalchemy.ext.asyncio.AsyncSession,
) -> dict[str, dict]:
    author_map: dict[str, dict] = {}
    result = await session.execute(
        sqlalchemy.text(
            "SELECT author_id, name, slug, open_library_id "
            "FROM books.authors WHERE open_library_id IS NOT NULL"
        )
    )
    for row in result:
        author_map[row.open_library_id] = {
            "author_id": row.author_id,
            "name": row.name,
            "slug": row.slug,
            "open_library_id": row.open_library_id,
        }
    logger.info(f"[dump] Built author map with {len(author_map)} entries")
    return author_map


async def _build_book_ol_map(
    session: sqlalchemy.ext.asyncio.AsyncSession,
) -> dict[str, list[dict]]:
    book_map: dict[str, list[dict]] = {}
    result = await session.execute(
        sqlalchemy.text(
            "SELECT book_id, language, slug, open_library_id "
            "FROM books.books WHERE open_library_id IS NOT NULL"
        )
    )
    for row in result:
        entry = {
            "book_id": row.book_id,
            "language": row.language,
            "slug": row.slug,
        }
        if row.open_library_id not in book_map:
            book_map[row.open_library_id] = []
        book_map[row.open_library_id].append(entry)
    logger.info(f"[dump] Built book OL map with {len(book_map)} work entries")
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

_WIKIDATA_NATIONALITY_PROP = "P27"
_WIKIDATA_BIRTHPLACE_PROP = "P19"


def _extract_wikidata_label(claims: dict, prop: str) -> typing.Optional[str]:
    claim_list = claims.get(prop, [])
    if not claim_list:
        return None
    for claim in claim_list:
        mainsnak = claim.get("mainsnak", {})
        datavalue = mainsnak.get("datavalue", {})
        value = datavalue.get("value", {})
        label = value.get("label")
        if label and isinstance(label, str):
            return label[:200]
    return None


def _extract_wikipedia_url_from_sitelinks(entity: dict) -> typing.Optional[str]:
    sitelinks = entity.get("sitelinks", {})
    enwiki = sitelinks.get("enwiki", {})
    title = enwiki.get("title")
    if title:
        return f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
    return None


async def process_wikidata_dump(file_path: str) -> int:
    updated_count = 0
    last_committed = 0
    batch_size = app.config.settings.dump_batch_size
    commit_interval = app.config.settings.dump_commit_interval

    async with app.models.AsyncSessionLocal() as session:
        try:
            updates: list[dict] = []

            with gzip.open(file_path, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        parts = line.rstrip("\n").split("\t", 1)
                        if len(parts) != 2:
                            continue

                        wikidata_id = parts[0].strip()
                        entity = json.loads(parts[1])

                        claims = entity.get("claims", {})
                        nationality = _extract_wikidata_label(
                            claims, _WIKIDATA_NATIONALITY_PROP
                        )
                        birth_place = _extract_wikidata_label(
                            claims, _WIKIDATA_BIRTHPLACE_PROP
                        )
                        wikipedia_url = _extract_wikipedia_url_from_sitelinks(entity)

                        if not nationality and not birth_place and not wikipedia_url:
                            continue

                        updates.append(
                            {
                                "wikidata_id": wikidata_id,
                                "nationality": nationality,
                                "birth_place": birth_place,
                                "wikipedia_url": wikipedia_url,
                            }
                        )

                        if len(updates) >= batch_size:
                            updated_count += await _flush_wikidata_updates(
                                session, updates
                            )
                            updates = []
                            if updated_count - last_committed >= commit_interval:
                                await session.commit()
                                last_committed = updated_count
                                logger.info(
                                    f"[dump] Wikidata enriched: {updated_count} authors"
                                )

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.debug(f"Error parsing wikidata entry: {e}")
                        continue

            if updates:
                updated_count += await _flush_wikidata_updates(session, updates)

            await session.commit()
            logger.info(
                f"[dump] Phase 2 complete: {updated_count} authors enriched via Wikidata"
            )
            return updated_count

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_wikidata_dump: {e}")
            raise


async def _flush_wikidata_updates(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    updates: list[dict],
) -> int:
    count = 0
    for update in updates:
        set_clauses: dict[str, str] = {}
        params: dict[str, typing.Any] = {"wid": update["wikidata_id"]}
        if update["nationality"]:
            set_clauses["nationality"] = "COALESCE(nationality, :nat)"
            params["nat"] = update["nationality"]
        if update["birth_place"]:
            set_clauses["birth_place"] = "COALESCE(birth_place, :bp)"
            params["bp"] = update["birth_place"]
        if update["wikipedia_url"]:
            set_clauses["wikipedia_url"] = "COALESCE(wikipedia_url, :wurl)"
            params["wurl"] = update["wikipedia_url"]

        if set_clauses:
            set_sql = ", ".join(f"{col} = {expr}" for col, expr in set_clauses.items())
            await session.execute(
                sqlalchemy.text(
                    f"UPDATE books.authors SET {set_sql} WHERE wikidata_id = :wid"
                ),
                params,
            )
            count += 1
    return count


# ---------------------------------------------------------------------------
# Phase 3: Works
# ---------------------------------------------------------------------------


async def process_works_dump(file_path: str, author_map: dict[str, dict]) -> int:
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
                            if ol_id and ol_id in author_map:
                                mapped = author_map[ol_id]
                                authors_list.append(
                                    {
                                        "name": mapped["name"],
                                        "slug": mapped["slug"],
                                        "open_library_id": mapped["open_library_id"],
                                    }
                                )

                        subjects = work_data.get("subjects", [])
                        genres_list = []
                        for subject in subjects[:5]:
                            if isinstance(subject, str):
                                genre_name = subject.lower()[:100]
                                genres_list.append(
                                    {
                                        "name": genre_name,
                                        "slug": app.utils.slugify(genre_name),
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
                        import app.services.book_service

                        result = await app.services.book_service.insert_books_batch(
                            session, books_to_insert, commit=False
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
    book_ol_map: dict[str, list[dict]],
    author_map: dict[str, dict],
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
    commit_interval = app.config.settings.dump_commit_interval

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
                        if not work_ol_id or work_ol_id not in book_ol_map:
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

                if total_processed - last_logged >= commit_interval * 4:
                    last_logged = total_processed
                    logger.info(
                        f"[dump] Editions scanned: {total_processed}, "
                        f"best-of candidates: {len(best_editions)}, "
                        f"skipped: {skipped}"
                    )

            logger.info(
                f"[dump] Edition scanning complete: {total_processed} scanned, "
                f"{len(best_editions)} best-of candidates"
            )

            batch_updates: list[dict] = []
            for ed in best_editions.values():
                work_ol_id = ed["work_ol_id"]
                lang_code = ed["lang_code"]
                book_rows = book_ol_map.get(work_ol_id, [])

                matching_row = None
                en_row = None
                for row in book_rows:
                    if row["language"] == lang_code:
                        matching_row = row
                        break
                    if row["language"] == "en":
                        en_row = row

                if matching_row:
                    batch_updates.append(
                        {
                            "book_id": matching_row["book_id"],
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
                elif lang_code != "en" and en_row:
                    batch_updates.append(
                        {
                            "book_id": None,
                            "source_book_id": en_row["book_id"],
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
                    await _flush_edition_updates(session, batch_updates, book_ol_map)
                    batch_updates = []
                    await session.commit()

            if batch_updates:
                await _flush_edition_updates(session, batch_updates, book_ol_map)
            await session.commit()

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


async def _flush_edition_updates(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    updates: list[dict],
    book_ol_map: dict[str, list[dict]],
) -> None:
    for update in updates:
        try:
            if update.get("book_id") is not None:
                set_parts: list[str] = []
                params: dict[str, typing.Any] = {"bid": update["book_id"]}

                if update["isbn"]:
                    set_parts.append("isbn = :isbn")
                    params["isbn"] = json.dumps(update["isbn"])
                if update["number_of_pages"]:
                    set_parts.append(
                        "number_of_pages = COALESCE(number_of_pages, :pages)"
                    )
                    params["pages"] = update["number_of_pages"]
                if update["publisher"]:
                    set_parts.append("publisher = COALESCE(publisher, :pub)")
                    params["pub"] = update["publisher"]
                if update["external_ids"]:
                    set_parts.append("external_ids = :ext_ids")
                    params["ext_ids"] = json.dumps(update["external_ids"])
                if update["cover_url"]:
                    set_parts.append(
                        "primary_cover_url = COALESCE(primary_cover_url, :cover)"
                    )
                    params["cover"] = update["cover_url"]
                if update["description"]:
                    set_parts.append("description = COALESCE(description, :desc)")
                    params["desc"] = update["description"]
                if update["physical_format"]:
                    set_parts.append(
                        "formats = CASE WHEN NOT formats @> :fmt::jsonb "
                        "THEN formats || :fmt::jsonb ELSE formats END"
                    )
                    params["fmt"] = json.dumps([update["physical_format"]])

                if set_parts:
                    sql = (
                        f"UPDATE books.books SET {', '.join(set_parts)} "
                        f"WHERE book_id = :bid"
                    )
                    await session.execute(sqlalchemy.text(sql), params)
            else:
                await _insert_new_language_row(session, update, book_ol_map)
        except Exception as e:
            logger.debug(f"Error applying edition update: {e}")


async def _insert_new_language_row(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    update: dict,
    book_ol_map: dict[str, list[dict]],
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

    insert_data = {
        "title": source.title,
        "language": lang,
        "slug": slug,
        "description": update["description"] or source.description,
        "original_publication_year": source.original_publication_year,
        "primary_cover_url": update["cover_url"] or source.primary_cover_url,
        "open_library_id": work_ol_id,
        "isbn": update["isbn"] or [],
        "publisher": update["publisher"],
        "number_of_pages": update["number_of_pages"],
        "external_ids": update["external_ids"] or {},
        "formats": ([update["physical_format"]] if update["physical_format"] else []),
        "series_id": source.series_id,
        "series_position": source.series_position,
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
    await session.execute(stmt)

    new_book_result = await session.execute(
        sqlalchemy.text(
            "SELECT book_id FROM books.books " "WHERE language = :lang AND slug = :slug"
        ),
        {"lang": lang, "slug": slug},
    )
    new_row = new_book_result.first()
    if not new_row:
        return

    entry = {"book_id": new_row.book_id, "language": lang, "slug": slug}
    if work_ol_id in book_ol_map:
        book_ol_map[work_ol_id].append(entry)
    else:
        book_ol_map[work_ol_id] = [entry]

    source_rels = await session.execute(
        sqlalchemy.text(
            "SELECT author_id FROM books.book_authors WHERE book_id = :sid"
        ),
        {"sid": source_id},
    )
    for rel_row in source_rels:
        await session.execute(
            sqlalchemy.text(
                "INSERT INTO books.book_authors (book_id, author_id) "
                "VALUES (:bid, :aid) ON CONFLICT DO NOTHING"
            ),
            {"bid": new_row.book_id, "aid": rel_row.author_id},
        )

    source_genres = await session.execute(
        sqlalchemy.text("SELECT genre_id FROM books.book_genres WHERE book_id = :sid"),
        {"sid": source_id},
    )
    for genre_row in source_genres:
        await session.execute(
            sqlalchemy.text(
                "INSERT INTO books.book_genres (book_id, genre_id) "
                "VALUES (:bid, :gid) ON CONFLICT DO NOTHING"
            ),
            {"bid": new_row.book_id, "gid": genre_row.genre_id},
        )


# ---------------------------------------------------------------------------
# Phase 5: Ratings
# ---------------------------------------------------------------------------


async def process_ratings_dump(
    file_path: str, book_ol_map: dict[str, list[dict]]
) -> int:
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

    logger.info(f"[dump] Parsed {len(rating_agg)} works with ratings")

    updated = 0
    async with app.models.AsyncSessionLocal() as session:
        try:
            batch_params: list[dict] = []
            for work_ol_id, agg in rating_agg.items():
                book_rows = book_ol_map.get(work_ol_id)
                if not book_rows:
                    continue

                avg = round(agg["total"] / agg["count"], 2)
                for row in book_rows:
                    batch_params.append(
                        {
                            "bid": row["book_id"],
                            "cnt": agg["count"],
                            "avg": avg,
                        }
                    )

                if len(batch_params) >= 1000:
                    for p in batch_params:
                        await session.execute(
                            sqlalchemy.text(
                                "UPDATE books.books SET "
                                "ol_rating_count = :cnt, ol_avg_rating = :avg "
                                "WHERE book_id = :bid"
                            ),
                            p,
                        )
                    updated += len(batch_params)
                    batch_params = []
                    await session.commit()

            for p in batch_params:
                await session.execute(
                    sqlalchemy.text(
                        "UPDATE books.books SET "
                        "ol_rating_count = :cnt, ol_avg_rating = :avg "
                        "WHERE book_id = :bid"
                    ),
                    p,
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


async def process_reading_log_dump(
    file_path: str, book_ol_map: dict[str, list[dict]]
) -> int:
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

    logger.info(f"[dump] Parsed {len(shelf_agg)} works with reading log data")

    updated = 0
    async with app.models.AsyncSessionLocal() as session:
        try:
            batch_params: list[dict] = []
            for work_ol_id, counts in shelf_agg.items():
                book_rows = book_ol_map.get(work_ol_id)
                if not book_rows:
                    continue

                for row in book_rows:
                    batch_params.append(
                        {
                            "bid": row["book_id"],
                            "want": counts["want"],
                            "reading": counts["reading"],
                            "read": counts["read"],
                        }
                    )

                if len(batch_params) >= 1000:
                    for p in batch_params:
                        await session.execute(
                            sqlalchemy.text(
                                "UPDATE books.books SET "
                                "ol_want_to_read_count = :want, "
                                "ol_currently_reading_count = :reading, "
                                "ol_already_read_count = :read "
                                "WHERE book_id = :bid"
                            ),
                            p,
                        )
                    updated += len(batch_params)
                    batch_params = []
                    await session.commit()

            for p in batch_params:
                await session.execute(
                    sqlalchemy.text(
                        "UPDATE books.books SET "
                        "ol_want_to_read_count = :want, "
                        "ol_currently_reading_count = :reading, "
                        "ol_already_read_count = :read "
                        "WHERE book_id = :bid"
                    ),
                    p,
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


async def run_import_dump(job_id: str, redis_client: redis.Redis) -> None:
    tmp_dir = Path(app.config.settings.dump_tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    base_url = app.config.settings.ol_dump_base_url

    authors_file = tmp_dir / "ol_dump_authors.txt.gz"
    wikidata_file = tmp_dir / "ol_dump_wikidata.txt.gz"
    works_file = tmp_dir / "ol_dump_works.txt.gz"
    editions_file = tmp_dir / "ol_dump_editions.txt.gz"
    ratings_file = tmp_dir / "ol_dump_ratings.txt.gz"
    reading_log_file = tmp_dir / "ol_dump_reading_log.txt.gz"

    all_files = [
        authors_file,
        wikidata_file,
        works_file,
        editions_file,
        ratings_file,
        reading_log_file,
    ]

    def _set_status(msg: str) -> None:
        try:
            redis_client.set(f"dump_import_{job_id}_status", msg, ex=86400)
        except Exception:
            pass

    try:
        logger.info(f"[dump] Starting enhanced dump import (job_id: {job_id})")
        try:
            redis_client.set("dump_import_running", 1, ex=86400)
        except Exception:
            pass

        # --- Phase 1: Authors ---
        _set_status("Phase 1/6: downloading authors dump")
        await download_file(
            f"{base_url}/ol_dump_authors_latest.txt.gz", str(authors_file)
        )

        _set_status("Phase 1/6: processing authors")
        authors_count = await process_authors_dump(str(authors_file))
        authors_file.unlink(missing_ok=True)

        # Build author in-memory map
        _set_status("Building author lookup map")
        async with app.models.AsyncSessionLocal() as session:
            author_map = await _build_author_map(session)

        # --- Phase 2: Wikidata ---
        wikidata_count = 0
        if app.config.settings.dump_wikidata_enabled:
            _set_status("Phase 2/6: downloading wikidata dump")
            await download_file(
                f"{base_url}/ol_dump_wikidata_latest.txt.gz",
                str(wikidata_file),
            )

            _set_status("Phase 2/6: processing wikidata enrichment")
            wikidata_count = await process_wikidata_dump(str(wikidata_file))
            wikidata_file.unlink(missing_ok=True)
        else:
            logger.info("[dump] Phase 2 skipped (wikidata disabled)")

        # --- Phase 3: Works ---
        _set_status("Phase 3/6: downloading works dump")
        await download_file(f"{base_url}/ol_dump_works_latest.txt.gz", str(works_file))

        _set_status("Phase 3/6: processing works")
        works_count = await process_works_dump(str(works_file), author_map)
        works_file.unlink(missing_ok=True)

        # Build book OL map for editions/ratings/reading-log
        _set_status("Building book lookup map")
        async with app.models.AsyncSessionLocal() as session:
            book_ol_map = await _build_book_ol_map(session)

        # --- Phase 4: Editions ---
        editions_stats: dict[str, int] = {
            "processed": 0,
            "enriched": 0,
            "new_lang_rows": 0,
            "skipped": 0,
        }
        if app.config.settings.dump_editions_enabled:
            _set_status("Phase 4/6: downloading editions dump")
            await download_file(
                f"{base_url}/ol_dump_editions_latest.txt.gz",
                str(editions_file),
            )

            _set_status("Phase 4/6: processing editions")
            editions_stats = await process_editions_dump(
                str(editions_file), book_ol_map, author_map
            )
            editions_file.unlink(missing_ok=True)
        else:
            logger.info("[dump] Phase 4 skipped (editions disabled)")

        # --- Phase 5: Ratings ---
        ratings_count = 0
        if app.config.settings.dump_ratings_enabled:
            _set_status("Phase 5/6: downloading ratings dump")
            await download_file(
                f"{base_url}/ol_dump_ratings_latest.txt.gz",
                str(ratings_file),
            )

            _set_status("Phase 5/6: processing ratings")
            ratings_count = await process_ratings_dump(str(ratings_file), book_ol_map)
            ratings_file.unlink(missing_ok=True)
        else:
            logger.info("[dump] Phase 5 skipped (ratings disabled)")

        # --- Phase 6: Reading Log ---
        reading_log_count = 0
        if app.config.settings.dump_reading_log_enabled:
            _set_status("Phase 6/6: downloading reading log dump")
            await download_file(
                f"{base_url}/ol_dump_reading-log_latest.txt.gz",
                str(reading_log_file),
            )

            _set_status("Phase 6/6: processing reading log")
            reading_log_count = await process_reading_log_dump(
                str(reading_log_file), book_ol_map
            )
            reading_log_file.unlink(missing_ok=True)
        else:
            logger.info("[dump] Phase 6 skipped (reading log disabled)")

        summary = (
            f"Complete: {authors_count} authors, "
            f"{wikidata_count} wikidata enriched, "
            f"{works_count} works, "
            f"{editions_stats['enriched']} editions enriched, "
            f"{editions_stats['new_lang_rows']} new language rows, "
            f"{ratings_count} ratings applied, "
            f"{reading_log_count} reading log applied"
        )
        logger.info(f"[dump] {summary}")
        _set_status(summary)

    except Exception as e:
        logger.error(f"[dump] Dump import failed: {e}")
        _set_status(f"Failed: {e}")
        raise

    finally:
        for f in all_files:
            f.unlink(missing_ok=True)
        try:
            redis_client.delete("dump_import_running")
        except Exception:
            pass
