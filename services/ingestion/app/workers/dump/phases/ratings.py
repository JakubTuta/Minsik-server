import asyncio
import gzip
import logging
import typing

import app.models
import sqlalchemy
from app.workers.dump import parsers

logger = logging.getLogger(__name__)


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
                book_lookup = await parsers.batch_lookup_books(session, chunk_ids)

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
                            f"(CAST(:bid_{k} AS bigint), CAST(:cnt_{k} AS int), CAST(:avg_{k} AS numeric))"
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
