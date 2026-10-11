import asyncio
import gc
import json
import logging
import typing

import app.config
import app.utils
import app.workers.dump.language_detect
import app.workers.dump.parsers
import app.workers.dump.runtime
import redis
import sqlalchemy

logger = logging.getLogger(__name__)

_CHECKPOINT_TTL_SECONDS = 86400 * 2
_STAGE_BATCH = 1000
UNKNOWN_LANGUAGE = ""
_MAX_ISBNS = 20

# The best edition per (work, language) is decided by the database across the
# whole dump, not per chunk: a later chunk's better edition replaces an earlier
# chunk's, and a worse one is ignored.
_STAGE_SQL = sqlalchemy.text(
    """
    INSERT INTO books.edition_staging (work_ol_id, language, score, payload)
    VALUES (:work_ol_id, :language, :score, CAST(:payload AS jsonb))
    ON CONFLICT (work_ol_id, language) DO UPDATE SET
        score = EXCLUDED.score,
        payload = jsonb_set(
            EXCLUDED.payload, '{isbns}',
            (
                SELECT COALESCE(jsonb_agg(isbn), '[]'::jsonb) FROM (
                    SELECT DISTINCT isbn FROM jsonb_array_elements_text(
                        books.edition_staging.payload->'isbns' || EXCLUDED.payload->'isbns'
                    ) AS t(isbn) LIMIT 20
                ) merged
            )
        )
    WHERE EXCLUDED.score > books.edition_staging.score
    """
)

def _checkpoint_key(job_id: str) -> str:
    return f"dump_phase4_checkpoint:{job_id}"


def _load_checkpoint(redis_client: redis.Redis, job_id: str) -> dict:
    try:
        raw = redis_client.get(_checkpoint_key(job_id))
        return json.loads(raw) if raw else {}
    except (redis.RedisError, ValueError):
        return {}


def _save_checkpoint(redis_client: redis.Redis, job_id: str, data: dict) -> None:
    try:
        redis_client.set(_checkpoint_key(job_id), json.dumps(data), ex=_CHECKPOINT_TTL_SECONDS)
    except redis.RedisError:
        logger.warning("[dump] Could not save the phase 4 checkpoint")


def _clear_checkpoint(redis_client: redis.Redis, job_id: str) -> None:
    try:
        redis_client.delete(_checkpoint_key(job_id))
    except redis.RedisError:
        pass


def _first_str(values: typing.Any) -> typing.Optional[str]:
    if isinstance(values, list) and values and isinstance(values[0], str):
        return values[0]
    return None


def _isbns(edition_data: dict) -> list[str]:
    raw = [
        isbn
        for field in ("isbn_10", "isbn_13")
        for isbn in edition_data.get(field) or []
    ]
    return app.utils.normalize_isbns(raw, _MAX_ISBNS)


def _title(edition_data: dict) -> typing.Optional[str]:
    title = edition_data.get("title")
    if not isinstance(title, str) or not title.strip():
        return None
    title = title.strip()
    subtitle = edition_data.get("subtitle")
    if isinstance(subtitle, str) and subtitle.strip() and subtitle.strip().lower() not in title.lower():
        title = f"{title}: {subtitle.strip()}"
    return title[:500]


def resolve_language(tag: typing.Optional[str], title: typing.Optional[str], description: typing.Optional[str]) -> str:
    """The edition's language: its OpenLibrary tag, else what its own text says, else unknown.

    An untagged edition is never assumed to be English: that assumption is how
    foreign-language text used to land on the English row.
    """
    if tag:
        return tag
    detected = app.workers.dump.language_detect.detect(" ".join(part for part in (title, description) if part))
    return detected or UNKNOWN_LANGUAGE


def parse_edition(edition_data: dict, known_works_filter: bytearray) -> typing.Optional[dict]:
    """One OpenLibrary edition as a staging candidate, or None when its work is not being imported."""
    works_ref = edition_data.get("works", [])
    if not works_ref or not isinstance(works_ref, list):
        return None
    first_work = works_ref[0]
    work_key = first_work.get("key", "") if isinstance(first_work, dict) else ""
    work_ol_id = work_key.replace("/works/", "")
    if not work_ol_id or not app.workers.dump.parsers.is_known_work(known_works_filter, work_ol_id):
        return None

    languages = edition_data.get("languages", [])
    tag = app.workers.dump.parsers.extract_ol_lang(languages[0]) if languages and isinstance(languages, list) else None

    title = _title(edition_data)
    description = app.workers.dump.parsers.extract_description(edition_data.get("description"))
    language = resolve_language(tag, title, description)

    # Text only goes to a row whose language it is written in; a recognisable
    # mismatch (an English blurb on a Polish edition) is dropped, not moved.
    if language == UNKNOWN_LANGUAGE or not app.workers.dump.language_detect.fits_language(title, language):
        title = None
    if language == UNKNOWN_LANGUAGE or not app.workers.dump.language_detect.fits_language(description, language):
        description = None
    first_sentence = app.workers.dump.parsers.extract_description(edition_data.get("first_sentence"))
    if language == UNKNOWN_LANGUAGE or not app.workers.dump.language_detect.fits_language(first_sentence, language):
        first_sentence = None

    page_count = edition_data.get("number_of_pages")
    if not isinstance(page_count, int) or page_count <= 0:
        page_count = None

    physical_format = edition_data.get("physical_format")
    physical_format = physical_format.lower().strip() if isinstance(physical_format, str) else None

    external_ids: dict[str, str] = {}
    identifiers = edition_data.get("identifiers", {})
    if isinstance(identifiers, dict):
        for id_key, id_values in identifiers.items():
            first = _first_str(id_values)
            if first:
                external_ids[id_key] = first
    google_books_id = external_ids.pop("google", None)
    external_ids["work_ol_id"] = work_ol_id

    publisher = _first_str(edition_data.get("publishers"))

    series = app.workers.dump.parsers.parse_series_string(edition_data.get("series"))
    score = app.workers.dump.parsers.score_edition(edition_data) + (2 if title else 0)

    return {
        "work_ol_id": work_ol_id,
        "language": language,
        "score": score,
        "payload": {
            "title": title,
            "description": description,
            "first_sentence": first_sentence,
            "isbns": _isbns(edition_data),
            "number_of_pages": page_count,
            "publisher": publisher[:500] if publisher else None,
            "physical_format": physical_format,
            "external_ids": external_ids,
            "open_library_id": edition_data.get("key", "").replace("/books/", "") or None,
            "google_books_id": google_books_id,
            "cover_url": app.workers.dump.parsers.extract_cover_url(edition_data.get("covers")),
            "series": series,
        },
    }


def _keep_best(best: dict[tuple[str, str], dict], candidate: dict) -> None:
    key = (candidate["work_ol_id"], candidate["language"])
    existing = best.get(key)
    if existing is None:
        best[key] = candidate
        return
    merged_isbns = list(dict.fromkeys(existing["payload"]["isbns"] + candidate["payload"]["isbns"]))[:_MAX_ISBNS]
    if candidate["score"] > existing["score"]:
        best[key] = candidate
    best[key]["payload"]["isbns"] = merged_isbns


async def _stage(session, best: dict[tuple[str, str], dict]) -> None:
    rows = [
        {
            "work_ol_id": candidate["work_ol_id"],
            "language": candidate["language"],
            "score": candidate["score"],
            "payload": json.dumps(candidate["payload"]),
        }
        for candidate in best.values()
    ]
    for start in range(0, len(rows), _STAGE_BATCH):
        await app.workers.dump.runtime.execute_batch(session, _STAGE_SQL, rows[start:start + _STAGE_BATCH])


async def process_editions_dump(
    file_path: str,
    known_works_filter: bytearray,
    job_id: str,
    redis_client: redis.Redis,
) -> dict[str, int]:
    from app.workers.dump import downloader

    checkpoint = _load_checkpoint(redis_client, job_id)
    total_processed = checkpoint.get("processed", 0)
    staged = checkpoint.get("staged", 0)
    skipped = checkpoint.get("skipped", 0)
    if total_processed:
        logger.info(f"[dump] Phase 4 resuming from checkpoint: {total_processed} editions already scanned")

    queue: asyncio.Queue = asyncio.Queue(maxsize=5)
    parse_task = asyncio.create_task(
        downloader.stream_parse_dump(
            file_path, "/type/edition", queue, app.config.settings.dump_edition_batch_size,
            skip_records=total_processed,
        )
    )

    flush_interval = app.config.settings.dump_edition_flush_interval
    last_flushed = total_processed
    best: dict[tuple[str, str], dict] = {}

    session = await app.workers.dump.runtime.open_session()
    try:
        while True:
            batch = await queue.get()
            if batch is None:
                break

            for edition_data in batch:
                total_processed += 1
                try:
                    candidate = parse_edition(edition_data, known_works_filter)
                except Exception as e:
                    logger.debug(f"Error parsing edition: {e}")
                    candidate = None
                if candidate is None:
                    skipped += 1
                    continue
                _keep_best(best, candidate)

            if total_processed - last_flushed >= flush_interval:
                await _stage(session, best)
                staged += len(best)
                best.clear()
                last_flushed = total_processed
                _save_checkpoint(
                    redis_client, job_id,
                    {"processed": total_processed, "staged": staged, "skipped": skipped},
                )
                gc.collect()
                app.workers.dump.runtime.trim_heap()
                logger.info(f"[dump] Editions scanned: {total_processed}, staged candidates: {staged}, skipped: {skipped}")

        await _stage(session, best)
        staged += len(best)
        best.clear()
        _clear_checkpoint(redis_client, job_id)
        logger.info(f"[dump] Phase 4 scan complete: {total_processed} editions, {staged} staged, {skipped} skipped")
        return {"processed": total_processed, "staged": staged, "skipped": skipped}

    except Exception as e:
        await session.rollback()
        logger.error(f"[dump] Error in process_editions_dump: {e}")
        raise
    finally:
        await session.close()
        await parse_task
