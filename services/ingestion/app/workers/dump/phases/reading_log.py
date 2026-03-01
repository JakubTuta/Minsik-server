import asyncio
import gzip
import logging
import typing

import app.models
import sqlalchemy
from app.workers.dump import parsers

logger = logging.getLogger(__name__)


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
                book_lookup = await parsers.batch_lookup_books(session, chunk_ids)

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
                            f"(CAST(:bid_{k} AS bigint), CAST(:want_{k} AS int), "
                            f"CAST(:reading_{k} AS int), CAST(:read_{k} AS int))"
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
