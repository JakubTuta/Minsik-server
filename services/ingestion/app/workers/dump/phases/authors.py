import asyncio
import gc
import logging
import typing

import app.config
import app.services.author_store
import app.utils
import app.workers.dump.downloader
import app.workers.dump.parsers
import app.workers.dump.runtime

logger = logging.getLogger(__name__)



def parse_author(author_data: dict) -> typing.Optional[dict]:
    name = author_data.get("name")
    if not name:
        return None
    name = app.utils.clean_name(name, max_length=300) or name[:300]

    bio_raw = author_data.get("bio")
    bio = app.workers.dump.parsers.extract_description(bio_raw) if bio_raw else None

    photo_url = None
    for photo_id in author_data.get("photos") or []:
        if isinstance(photo_id, int) and photo_id > 0:
            photo_url = app.workers.dump.parsers.OL_AUTHOR_PHOTO_URL.format(photo_id=photo_id)
            break

    remote_ids = app.workers.dump.parsers.extract_remote_ids(author_data)
    wikipedia_url = author_data.get("wikipedia")
    if not (isinstance(wikipedia_url, str) and wikipedia_url.startswith("http")):
        wikipedia_url = None

    alternate_names = author_data.get("alternate_names", [])
    if not isinstance(alternate_names, list):
        alternate_names = []
    alternate_names = [n for n in alternate_names if isinstance(n, str) and n][:20]

    ol_id = author_data.get("key", "").replace("/authors/", "")
    base_slug = app.utils.slugify(name)
    if not ol_id or not base_slug:
        return None

    entry = {
        "name": name,
        "base_slug": base_slug,
        "bio": bio,
        "birth_date": app.workers.dump.parsers.parse_free_date(author_data.get("birth_date")),
        "death_date": app.workers.dump.parsers.parse_free_date(author_data.get("death_date")),
        "photo_url": photo_url,
        "open_library_id": ol_id,
        "wikidata_id": remote_ids.get("wikidata"),
        "wikipedia_url": wikipedia_url,
        "remote_ids": remote_ids,
        "alternate_names": alternate_names,
    }
    if app.workers.dump.parsers.score_author(entry) < app.config.settings.dump_author_min_quality_score:
        return None
    return entry


async def process_authors_dump(file_path: str) -> int:
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    parse_task = asyncio.create_task(
        app.workers.dump.downloader.stream_parse_dump(
            file_path, "/type/author", queue, app.config.settings.dump_batch_size
        )
    )

    total_count = 0
    last_logged = 0
    log_interval = app.config.settings.dump_commit_interval

    session = await app.workers.dump.runtime.open_session()
    try:
        while True:
            batch = await queue.get()
            if batch is None:
                break

            entries = []
            for author_data in batch:
                try:
                    entry = parse_author(author_data)
                except Exception as e:
                    logger.debug(f"Error preparing author: {e}")
                    continue
                if entry:
                    entries.append(entry)

            if entries:
                try:
                    await app.services.author_store.upsert_authors(session, entries)
                    await session.commit()
                    total_count += len(entries)
                except Exception as e:
                    logger.warning(f"Error writing author batch: {e}")
                    await session.rollback()

            if total_count - last_logged >= log_interval:
                last_logged = total_count
                gc.collect()
                logger.info(f"[dump] Authors processed: {total_count}")

        logger.info(f"[dump] Phase 1 complete: {total_count} authors upserted")
        return total_count

    except Exception as e:
        await session.rollback()
        logger.error(f"[dump] Error in process_authors_dump: {e}")
        raise
    finally:
        await session.close()
        await parse_task
