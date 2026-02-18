import asyncio
import datetime
import gzip
import json
import logging
import os
import typing
from pathlib import Path

import httpx
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

import app.config
import app.models
import app.services.book_service
import app.utils

logger = logging.getLogger(__name__)

_OPENLIBRARY_COVER_URL_TEMPLATE = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"


async def download_file(url: str, dest_path: str) -> None:
    logger.info(f"[dump] Downloading {url}")
    async with httpx.AsyncClient(timeout=3600, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
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
            batch = []
            for line in f:
                try:
                    parts = line.rstrip("\n").split("\t", 4)
                    if len(parts) != 5:
                        continue
                    if parts[0] != record_type:
                        continue

                    try:
                        data = json.loads(parts[4])
                        batch.append(data)
                        if len(batch) >= batch_size:
                            loop.call_soon_threadsafe(queue.put_nowait, batch[:])
                            batch = []
                    except json.JSONDecodeError:
                        continue
                except Exception as e:
                    logger.debug(f"Error parsing line: {str(e)}")
                    continue

            if batch:
                loop.call_soon_threadsafe(queue.put_nowait, batch)

        loop.call_soon_threadsafe(queue.put_nowait, None)

    await asyncio.to_thread(_sync_reader)


def _extract_description(data: dict) -> typing.Optional[str]:
    description = data.get("description")
    if isinstance(description, dict):
        description = description.get("value")
    if isinstance(description, str):
        return app.utils.clean_description(description)
    return None


def _parse_date(date_string: typing.Optional[str]) -> typing.Optional[datetime.date]:
    if not date_string:
        return None
    try:
        date_str = str(date_string).strip()
        if not date_str:
            return None
        if len(date_str) == 4:
            return datetime.date(int(date_str), 1, 1)
        elif len(date_str) == 7:
            year, month = date_str.split("-")
            return datetime.date(int(year), int(month), 1)
        else:
            return datetime.datetime.fromisoformat(date_str[:10]).date()
    except (ValueError, TypeError, AttributeError):
        return None


def _extract_cover_url(covers: typing.Optional[list]) -> typing.Optional[str]:
    if not covers or not isinstance(covers, list):
        return None
    for cover_id in covers:
        if isinstance(cover_id, int):
            return _OPENLIBRARY_COVER_URL_TEMPLATE.format(cover_id=cover_id)
    return None


async def process_authors_dump(file_path: str) -> int:
    queue: asyncio.Queue[typing.Optional[typing.List[dict]]] = asyncio.Queue(maxsize=100)

    parse_task = asyncio.create_task(
        _stream_parse_dump(file_path, "/type/author", queue, app.config.settings.dump_batch_size)
    )

    async with app.models.AsyncSessionLocal() as session:
        try:
            total_count = 0

            while True:
                batch = await queue.get()
                if batch is None:
                    break

                # Build bulk insert data
                insert_data = []
                for author_data in batch:
                    try:
                        name = author_data.get("name")
                        if not name:
                            continue

                        bio = _extract_description(author_data.get("bio")) if author_data.get("bio") else None

                        photo_url = None
                        photos = author_data.get("photos")
                        if photos and isinstance(photos, list) and len(photos) > 0:
                            photo_id = photos[0]
                            if isinstance(photo_id, int):
                                photo_url = f"https://covers.openlibrary.org/a/id/{photo_id}-L.jpg"

                        insert_data.append({
                            "name": name,
                            "slug": app.utils.slugify(name),
                            "bio": bio,
                            "birth_date": _parse_date(author_data.get("birth_date")),
                            "death_date": _parse_date(author_data.get("death_date")),
                            "photo_url": photo_url,
                            "open_library_id": author_data.get("key", "").replace("/authors/", ""),
                        })
                        total_count += 1

                    except Exception as e:
                        logger.debug(f"Error preparing author: {str(e)}")
                        continue

                # Bulk upsert
                if insert_data:
                    try:
                        stmt = postgresql_insert(app.models.Author).values(insert_data)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["slug"],
                            set_={"open_library_id": stmt.excluded.open_library_id}
                        )
                        await session.execute(stmt)
                        await session.commit()

                        if total_count % 10000 == 0:
                            logger.info(f"[dump] Authors processed: {total_count}")
                    except Exception as e:
                        logger.warning(f"Error bulk inserting authors: {str(e)}")
                        await session.rollback()
                        continue


            logger.info(f"[dump] Phase 1 complete: {total_count} authors upserted")
            return total_count

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_authors_dump: {str(e)}")
            raise
        finally:
            await parse_task


async def process_works_dump(file_path: str) -> typing.Dict[str, int]:
    queue: asyncio.Queue[typing.Optional[typing.List[dict]]] = asyncio.Queue(maxsize=100)

    parse_task = asyncio.create_task(
        _stream_parse_dump(file_path, "/type/work", queue, app.config.settings.dump_batch_size)
    )

    async with app.models.AsyncSessionLocal() as session:
        try:
            processed = 0
            successful = 0
            failed = 0

            while True:
                batch = await queue.get()
                if batch is None:
                    break

                for work_data in batch:
                    processed += 1
                    try:
                        title = work_data.get("title")
                        if not title:
                            failed += 1
                            continue

                        authors_list = []
                        authors_raw = work_data.get("authors", [])
                        for author_ref in authors_raw:
                            if isinstance(author_ref, dict):
                                author_key = author_ref.get("author", {}).get("key", "")
                                ol_id = author_key.replace("/authors/", "")
                                if ol_id:
                                    author = await app.services.book_service.get_author_by_ol_id(session, ol_id)
                                    if author:
                                        authors_list.append(
                                            {
                                                "name": author.name,
                                                "slug": author.slug,
                                                "open_library_id": author.open_library_id,
                                            }
                                        )

                        subjects = work_data.get("subjects", [])
                        genres_list = []
                        for subject in subjects[:5]:
                            if isinstance(subject, str):
                                genres_list.append({"name": subject.lower(), "slug": app.utils.slugify(subject)})

                        description = _extract_description(work_data.get("description"))
                        publication_date = _parse_date(work_data.get("first_publish_date"))
                        cover_url = _extract_cover_url(work_data.get("covers"))

                        book_data = {
                            "title": title,
                            "language": "en",
                            "description": description,
                            "original_publication_year": publication_date,
                            "primary_cover_url": cover_url,
                            "open_library_id": work_data.get("key", "").replace("/works/", ""),
                            "google_books_id": None,
                            "authors": authors_list,
                            "genres": genres_list,
                            "formats": [],
                            "cover_history": [],
                            "series": None,
                        }

                        await app.services.book_service.process_single_book(session, book_data)
                        successful += 1

                        if processed % 1000 == 0:
                            logger.info(f"[dump] Works processed: {processed}, successful: {successful}, failed: {failed}")
                            await session.commit()

                    except Exception as e:
                        logger.debug(f"Error processing work: {str(e)}")
                        failed += 1
                        continue

            await session.commit()
            logger.info(f"[dump] Phase 2 complete: {processed} processed, {successful} successful, {failed} failed")
            return {"processed": processed, "successful": successful, "failed": failed}

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_works_dump: {str(e)}")
            raise
        finally:
            await parse_task


async def run_import_dump(job_id: str, redis_client: redis.Redis) -> None:
    tmp_dir = Path(app.config.settings.dump_tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    authors_file = tmp_dir / "ol_dump_authors.txt.gz"
    works_file = tmp_dir / "ol_dump_works.txt.gz"

    try:
        logger.info(f"[dump] Starting dump import (job_id: {job_id})")

        try:
            redis_client.set("dump_import_running", 1, ex=86400)
        except Exception as e:
            logger.warning(f"[dump] Could not set Redis flag: {str(e)}")

        redis_client.set(f"dump_import_{job_id}_status", "Phase 1: downloading authors")

        await download_file(f"{app.config.settings.ol_dump_base_url}/ol_dump_authors_latest.txt.gz", str(authors_file))

        redis_client.set(f"dump_import_{job_id}_status", "Phase 1: processing authors")
        authors_count = await process_authors_dump(str(authors_file))
        authors_file.unlink(missing_ok=True)

        redis_client.set(f"dump_import_{job_id}_status", "Phase 2: downloading works")
        await download_file(f"{app.config.settings.ol_dump_base_url}/ol_dump_works_latest.txt.gz", str(works_file))

        redis_client.set(f"dump_import_{job_id}_status", "Phase 2: processing works")
        works_stats = await process_works_dump(str(works_file))
        works_file.unlink(missing_ok=True)

        logger.info(
            f"[dump] Dump import complete: {authors_count} authors, "
            f"{works_stats['successful']} works successfully ingested"
        )

        redis_client.set(
            f"dump_import_{job_id}_status",
            f"Complete: {authors_count} authors, {works_stats['successful']} works",
            ex=3600,
        )

    except Exception as e:
        logger.error(f"[dump] Dump import failed: {str(e)}")
        redis_client.set(f"dump_import_{job_id}_status", f"Failed: {str(e)}", ex=3600)
        raise

    finally:
        authors_file.unlink(missing_ok=True)
        works_file.unlink(missing_ok=True)

        try:
            redis_client.delete("dump_import_running")
        except Exception as e:
            logger.warning(f"[dump] Could not clear Redis flag: {str(e)}")
