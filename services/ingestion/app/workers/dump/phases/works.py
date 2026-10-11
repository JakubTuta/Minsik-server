import asyncio
import gc
import json
import logging
import typing

import app.config
import app.models
import app.utils
import app.workers.dump.language_detect
import app.workers.dump.parsers
import app.workers.dump.runtime
import sqlalchemy

logger = logging.getLogger(__name__)

# Staging keeps the work exactly as OpenLibrary describes it. Nothing here
# creates a book row: which language rows a work gets is decided in the merge
# step, once the editions have been seen.
_UPSERT_SQL = sqlalchemy.text(
    """
    INSERT INTO books.work_staging (
        work_ol_id, title, title_language, description, description_language,
        first_sentence, first_publish_year, cover_url, author_ol_ids, genres
    ) VALUES (
        :work_ol_id, :title, :title_language, :description, :description_language,
        :first_sentence, :first_publish_year, :cover_url,
        CAST(:author_ol_ids AS jsonb), CAST(:genres AS jsonb)
    )
    ON CONFLICT (work_ol_id) DO UPDATE SET
        title = EXCLUDED.title,
        title_language = EXCLUDED.title_language,
        description = EXCLUDED.description,
        description_language = EXCLUDED.description_language,
        first_sentence = EXCLUDED.first_sentence,
        first_publish_year = EXCLUDED.first_publish_year,
        cover_url = EXCLUDED.cover_url,
        author_ol_ids = EXCLUDED.author_ol_ids,
        genres = EXCLUDED.genres
    """
)


def _author_ol_ids(work_data: dict) -> list[str]:
    ids: list[str] = []
    for author_ref in work_data.get("authors", []):
        if not isinstance(author_ref, dict):
            continue
        author_obj = author_ref.get("author")
        if not isinstance(author_obj, dict):
            continue
        ol_id = author_obj.get("key", "").replace("/authors/", "")
        if ol_id and ol_id not in ids:
            ids.append(ol_id)
    return ids


def _genres(work_data: dict) -> list[dict[str, str]]:
    genres: list[dict[str, str]] = []
    for subject in work_data.get("subjects", [])[:5]:
        if not isinstance(subject, str):
            continue
        canonical_name, canonical_slug = app.utils.canonicalize_genre_name(subject)
        if canonical_slug:
            genres.append({"name": canonical_name, "slug": canonical_slug})
    return genres


def stage_work(work_data: dict) -> typing.Optional[dict]:
    """The staging row for one OpenLibrary work, or None when it should not be imported."""
    title = work_data.get("title")
    if not title:
        return None

    author_ol_ids = _author_ol_ids(work_data)
    if not author_ol_ids or len(author_ol_ids) >= app.config.settings.cleanup_book_max_authors:
        return None

    description = app.workers.dump.parsers.extract_description(work_data.get("description"))
    pub_date = app.workers.dump.parsers.parse_free_date(work_data.get("first_publish_date"))
    cover_url = app.workers.dump.parsers.extract_cover_url(work_data.get("covers"))
    genres = _genres(work_data)

    quality_view = {"description": description, "primary_cover_url": cover_url, "genres": genres}
    if app.workers.dump.parsers.score_work(quality_view) < app.config.settings.dump_work_min_quality_score:
        return None

    return {
        "work_ol_id": work_data.get("key", "").replace("/works/", ""),
        "title": title[:500],
        "title_language": app.workers.dump.language_detect.detect(title),
        "description": description,
        "description_language": app.workers.dump.language_detect.detect(description),
        "first_sentence": app.workers.dump.parsers.extract_description(work_data.get("first_sentence")),
        "first_publish_year": pub_date.year if pub_date else None,
        "cover_url": cover_url,
        "author_ol_ids": json.dumps(author_ol_ids),
        "genres": json.dumps(genres),
    }


async def process_works_dump(file_path: str) -> int:
    from app.workers.dump import downloader

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    parse_task = asyncio.create_task(
        downloader.stream_parse_dump(
            file_path, "/type/work", queue, app.config.settings.dump_batch_size
        )
    )

    total_count = 0
    staged = 0
    last_logged = 0
    log_interval = app.config.settings.dump_commit_interval

    session = await app.workers.dump.runtime.open_session()
    try:
        await session.execute(sqlalchemy.text("TRUNCATE books.work_staging, books.edition_staging"))
        await session.commit()

        while True:
            batch = await queue.get()
            if batch is None:
                break

            rows: list[dict] = []
            for work_data in batch:
                total_count += 1
                try:
                    row = stage_work(work_data)
                except Exception as e:
                    logger.debug(f"Error preparing work: {e}")
                    continue
                if row and row["work_ol_id"]:
                    rows.append(row)

            if rows:
                await app.workers.dump.runtime.execute_batch(session, _UPSERT_SQL, rows)
                staged += len(rows)

            if total_count - last_logged >= log_interval:
                last_logged = total_count
                gc.collect()
                logger.info(f"[dump] Works scanned: {total_count}, staged: {staged}")

        logger.info(f"[dump] Phase 3 complete: {total_count} scanned, {staged} staged")
        return staged

    except Exception as e:
        await session.rollback()
        logger.error(f"[dump] Error in process_works_dump: {e}")
        raise
    finally:
        await session.close()
        await parse_task
