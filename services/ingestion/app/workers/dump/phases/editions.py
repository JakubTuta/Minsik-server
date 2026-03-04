import asyncio
import ctypes
import gc
import json
import logging
import typing

import app.config
import app.models
import app.utils
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio
import sqlalchemy.pool
from app.workers.dump import parsers
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

logger = logging.getLogger(__name__)

_dump_engine: sqlalchemy.ext.asyncio.AsyncEngine | None = None
_dump_sessionmaker: sqlalchemy.ext.asyncio.async_sessionmaker | None = None

_CHECKPOINT_TTL_SECONDS = 86400 * 2


def _checkpoint_key(job_id: str) -> str:
    return f"dump_phase4_checkpoint:{job_id}"


def _load_checkpoint(redis_client: redis.Redis, job_id: str) -> dict:
    try:
        raw = redis_client.get(_checkpoint_key(job_id))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


def _save_checkpoint(redis_client: redis.Redis, job_id: str, data: dict) -> None:
    try:
        redis_client.set(
            _checkpoint_key(job_id),
            json.dumps(data),
            ex=_CHECKPOINT_TTL_SECONDS,
        )
    except Exception:
        pass


def _clear_checkpoint(redis_client: redis.Redis, job_id: str) -> None:
    try:
        redis_client.delete(_checkpoint_key(job_id))
    except Exception:
        pass


def _get_dump_sessionmaker() -> sqlalchemy.ext.asyncio.async_sessionmaker:
    global _dump_engine, _dump_sessionmaker
    if _dump_sessionmaker is None:
        _dump_engine = sqlalchemy.ext.asyncio.create_async_engine(
            app.config.settings.database_url,
            poolclass=sqlalchemy.pool.NullPool,
            echo=False,
        )
        _dump_sessionmaker = sqlalchemy.ext.asyncio.async_sessionmaker(
            _dump_engine,
            class_=sqlalchemy.ext.asyncio.AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _dump_sessionmaker


def _trim_heap() -> None:
    try:
        ctypes.cdll.LoadLibrary("libc.so.6").malloc_trim(0)
    except Exception:
        pass


async def _open_session() -> sqlalchemy.ext.asyncio.AsyncSession:
    session = _get_dump_sessionmaker()()
    await session.execute(sqlalchemy.text("SET synchronous_commit = off"))
    return session


async def process_editions_dump(
    file_path: str,
    known_works_filter: bytearray,
    job_id: str,
    redis_client: redis.Redis,
) -> dict[str, int]:
    from app.workers.dump import downloader

    checkpoint = _load_checkpoint(redis_client, job_id)
    checkpoint_processed = checkpoint.get("processed", 0)
    if checkpoint_processed > 0:
        logger.info(
            f"[dump] Phase 4 resuming from checkpoint: "
            f"{checkpoint_processed} editions already processed, skipping ahead"
        )

    queue: asyncio.Queue = asyncio.Queue(maxsize=5)
    parse_task = asyncio.create_task(
        downloader.stream_parse_dump(
            file_path,
            "/type/edition",
            queue,
            app.config.settings.dump_edition_batch_size,
            skip_records=checkpoint_processed,
        )
    )

    total_processed = checkpoint_processed
    enriched = checkpoint.get("enriched", 0)
    new_lang_rows = checkpoint.get("new_lang_rows", 0)
    skipped = checkpoint.get("skipped", 0)
    last_logged = total_processed
    last_flushed = total_processed
    commit_interval = app.config.settings.dump_commit_interval
    flush_interval = app.config.settings.dump_edition_flush_interval

    best_editions: dict[str, dict] = {}

    session = await _open_session()
    try:
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
                        if not work_ol_id or not parsers.is_known_work(
                            known_works_filter, work_ol_id
                        ):
                            skipped += 1
                            continue

                        languages = edition_data.get("languages", [])
                        lang_code = "en"
                        if languages and isinstance(languages, list):
                            detected = parsers.extract_ol_lang(languages[0])
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

                        cover_url = parsers.extract_cover_url(
                            edition_data.get("covers")
                        )
                        description = parsers.extract_description(
                            edition_data.get("description")
                        )

                        series_data = parsers.parse_series_string(
                            edition_data.get("series")
                        )
                        first_sentence = parsers.extract_description(
                            edition_data.get("first_sentence")
                        )

                        score = parsers.score_edition(edition_data)

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
                                "first_sentence": first_sentence,
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
                    _save_checkpoint(
                        redis_client,
                        job_id,
                        {
                            "processed": total_processed,
                            "enriched": enriched,
                            "new_lang_rows": new_lang_rows,
                            "skipped": skipped,
                        },
                    )
                    gc.collect()
                    await session.close()
                    session = await _open_session()
                    _trim_heap()
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

            del known_works_filter
            gc.collect()
            _trim_heap()

            e, n = await _flush_best_editions_chunk(session, best_editions)
            enriched += e
            new_lang_rows += n
            best_editions.clear()

            _clear_checkpoint(redis_client, job_id)
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
    finally:
        await session.close()
        global _dump_engine, _dump_sessionmaker
        if _dump_engine is not None:
            _dump_engine.dispose()
            _dump_engine = None
            _dump_sessionmaker = None


async def _flush_best_editions_chunk(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    best_editions: dict[str, dict],
) -> tuple[int, int]:
    if not best_editions:
        return 0, 0

    work_ol_ids = list({ed["work_ol_id"] for ed in best_editions.values()})
    book_lookup = await parsers.batch_lookup_books(session, work_ol_ids)

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
                    "first_sentence": ed.get("first_sentence"),
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
                    "first_sentence": ed.get("first_sentence"),
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

    series_name_to_id: dict[str, int] = {}
    unique_series: dict[str, dict] = {}
    for u in existing_updates + new_lang_updates:
        series = u.get("series")
        if series and series.get("name"):
            slug = app.utils.slugify(series["name"])
            if slug and slug not in unique_series:
                unique_series[slug] = {"name": series["name"][:500], "slug": slug}

    if unique_series:
        stmt = postgresql_insert(app.models.Series).values(list(unique_series.values()))
        stmt = stmt.on_conflict_do_update(
            index_elements=["slug"],
            set_={"name": stmt.excluded.name},
        )
        stmt = stmt.returning(app.models.Series.slug, app.models.Series.series_id)
        result = await session.execute(stmt)
        for row in result:
            series_name_to_id[row.slug] = row.series_id

    batch_size = 500
    for i in range(0, len(existing_updates), batch_size):
        sub = existing_updates[i : i + batch_size]
        values_parts: list[str] = []
        params: dict[str, typing.Any] = {}
        for k, u in enumerate(sub):
            series = u.get("series")
            series_id = None
            series_pos = None
            if series and series.get("name"):
                series_slug = app.utils.slugify(series["name"])
                series_id = series_name_to_id.get(series_slug)
                series_pos = app.utils.clamp_series_position(series.get("position"))

            values_parts.append(
                f"(CAST(:bid_{k} AS bigint), CAST(:isbn_{k} AS jsonb), CAST(:pages_{k} AS int), "
                f":pub_{k}, CAST(:ext_{k} AS jsonb), :cover_{k}, :desc_{k}, :fsen_{k}, CAST(:fmt_{k} AS jsonb), "
                f"CAST(:sid_{k} AS bigint), CAST(:spos_{k} AS numeric))"
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
            params[f"fsen_{k}"] = u.get("first_sentence")
            params[f"fmt_{k}"] = (
                json.dumps([u["physical_format"]]) if u["physical_format"] else None
            )
            params[f"sid_{k}"] = series_id
            params[f"spos_{k}"] = series_pos

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
                "first_sentence = COALESCE(b.first_sentence, v.fsen), "
                "formats = CASE "
                "WHEN v.fmt IS NOT NULL AND NOT b.formats @> v.fmt "
                "THEN b.formats || v.fmt ELSE b.formats END, "
                "series_id = CASE WHEN b.series_id IS NULL AND v.sid IS NOT NULL "
                "THEN v.sid ELSE b.series_id END, "
                "series_position = CASE WHEN b.series_position IS NULL "
                "AND v.spos IS NOT NULL THEN v.spos ELSE b.series_position END "
                f"FROM (VALUES {', '.join(values_parts)}) "
                "AS v(bid, isbn, pages, pub, ext, cover, descr, fsen, fmt, sid, spos) "
                "WHERE b.book_id = v.bid"
            ),
            params,
        )

    for update in new_lang_updates:
        try:
            await _insert_new_language_row(session, update, series_name_to_id)
        except Exception as e:
            logger.debug(f"Error inserting new language row: {e}")


async def _insert_new_language_row(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    update: dict,
    series_name_to_id: dict[str, int],
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

    edition_series = update.get("series")
    if edition_series and edition_series.get("name"):
        series_slug = app.utils.slugify(edition_series["name"])
        series_id = series_name_to_id.get(series_slug)
        series_position = edition_series.get("position")
    else:
        series_id = source.series_id
        series_position = source.series_position

    series_position = app.utils.clamp_series_position(series_position)

    insert_data = {
        "title": title,
        "language": lang,
        "slug": slug,
        "description": update["description"] or source.description,
        "first_sentence": update.get("first_sentence"),
        "original_publication_year": source.original_publication_year,
        "primary_cover_url": cover_url,
        "open_library_id": work_ol_id,
        "isbn": update["isbn"] or [],
        "publisher": publisher,
        "number_of_pages": update["number_of_pages"],
        "external_ids": update["external_ids"] or {},
        "formats": ([update["physical_format"]] if update["physical_format"] else []),
        "series_id": series_id,
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
