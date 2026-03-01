import asyncio
import ctypes
import gc
import logging

import app.config
import app.models
import app.utils
import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.ext.asyncio
from app.workers.dump import parsers

logger = logging.getLogger(__name__)

_SESSION_RECYCLE_AFTER_COMMITS = 2
_DEADLOCK_MAX_RETRIES = 3
_DEADLOCK_RETRY_DELAY = 2.0


def _trim_heap() -> None:
    try:
        ctypes.cdll.LoadLibrary("libc.so.6").malloc_trim(0)
    except Exception:
        pass


async def _open_session() -> sqlalchemy.ext.asyncio.AsyncSession:
    session = app.models.AsyncSessionLocal()
    await session.execute(sqlalchemy.text("SET synchronous_commit = off"))
    return session


async def process_works_dump(file_path: str) -> int:
    from app.services import book_service
    from app.workers.dump import downloader

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    parse_task = asyncio.create_task(
        downloader.stream_parse_dump(
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
    commits_since_recycle = 0
    commit_interval = app.config.settings.dump_commit_interval

    genre_id_cache: dict[str, int] = {}
    series_id_cache: dict[str, int] = {}

    session = await _open_session()
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

            author_lookup = await parsers.batch_lookup_authors(
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

                    description = parsers.extract_description(
                        work_data.get("description")
                    )
                    pub_date = parsers.parse_free_date(
                        work_data.get("first_publish_date")
                    )
                    pub_year = pub_date.year if pub_date else None
                    cover_url = parsers.extract_cover_url(work_data.get("covers"))
                    work_ol_id = work_data.get("key", "").replace("/works/", "")

                    if not authors_list:
                        failed += 1
                        continue

                    work_entry = {
                        "title": title,
                        "language": "en",
                        "description": description,
                        "first_sentence": parsers.extract_description(
                            work_data.get("first_sentence")
                        ),
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
                    if (
                        parsers.score_work(work_entry)
                        < app.config.settings.dump_work_min_quality_score
                    ):
                        logger.debug(f"Skipping low-quality work: {title}")
                        failed += 1
                        continue
                    books_to_insert.append(work_entry)

                except Exception as e:
                    logger.debug(f"Error preparing work: {e}")
                    failed += 1

            if books_to_insert:
                retries = 0
                while True:
                    try:
                        prebuilt_author_id_map = {
                            slug: aid for aid, _name, slug in author_lookup.values()
                        }
                        result = await book_service.insert_books_batch(
                            session,
                            books_to_insert,
                            commit=False,
                            author_id_map=prebuilt_author_id_map,
                            genre_id_cache=genre_id_cache,
                            series_id_cache=series_id_cache,
                        )
                        successful += result["successful"]
                        failed += result["failed"]
                        break
                    except sqlalchemy.exc.DBAPIError as e:
                        is_deadlock = "deadlock" in str(e).lower()
                        if is_deadlock and retries < _DEADLOCK_MAX_RETRIES:
                            retries += 1
                            logger.warning(
                                f"[dump] Deadlock on genre/author upsert, "
                                f"retry {retries}/{_DEADLOCK_MAX_RETRIES}"
                            )
                            await asyncio.sleep(_DEADLOCK_RETRY_DELAY * retries)
                            continue
                        logger.error(f"[dump] Error batch inserting works: {e}")
                        failed += len(books_to_insert)
                        break
                    except Exception as e:
                        logger.error(f"[dump] Error batch inserting works: {e}")
                        failed += len(books_to_insert)
                        break

            if total_count - last_committed >= commit_interval:
                await session.commit()
                commits_since_recycle += 1
                last_committed = total_count
                gc.collect()

                if commits_since_recycle >= _SESSION_RECYCLE_AFTER_COMMITS:
                    await session.close()
                    genre_id_cache.clear()
                    series_id_cache.clear()
                    gc.collect()
                    _trim_heap()
                    session = await _open_session()
                    commits_since_recycle = 0
                else:
                    session.expunge_all()

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
        await session.close()
        await parse_task
