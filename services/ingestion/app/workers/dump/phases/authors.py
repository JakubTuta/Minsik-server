import asyncio
import logging

import app.config
import app.models
import app.utils
import sqlalchemy
from app.workers.dump import parsers
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

logger = logging.getLogger(__name__)


async def process_authors_dump(file_path: str) -> int:
    from app.workers.dump import downloader

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    parse_task = asyncio.create_task(
        downloader.stream_parse_dump(
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
                        bio = parsers.extract_description(bio_raw) if bio_raw else None

                        photo_url = None
                        photos = author_data.get("photos")
                        if photos and isinstance(photos, list):
                            for photo_id in photos:
                                if isinstance(photo_id, int) and photo_id > 0:
                                    photo_url = parsers.OL_AUTHOR_PHOTO_URL.format(
                                        photo_id=photo_id
                                    )
                                    break

                        remote_ids = parsers.extract_remote_ids(author_data)
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

                        author_entry = {
                            "name": name,
                            "slug": app.utils.slugify(name),
                            "bio": bio,
                            "birth_date": parsers.parse_free_date(
                                author_data.get("birth_date")
                            ),
                            "death_date": parsers.parse_free_date(
                                author_data.get("death_date")
                            ),
                            "photo_url": photo_url,
                            "open_library_id": ol_id,
                            "wikidata_id": wikidata_id,
                            "wikipedia_url": wikipedia_url,
                            "remote_ids": remote_ids,
                            "alternate_names": alternate_names,
                        }
                        if (
                            parsers.score_author(author_entry)
                            < app.config.settings.dump_author_min_quality_score
                        ):
                            logger.debug(f"Skipping low-quality author: {name}")
                            continue
                        insert_data.append(author_entry)
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
                            session.expunge_all()
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
