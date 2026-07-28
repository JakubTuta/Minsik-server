import asyncio
import ctypes
import gc
import gzip
import logging
import typing

import app.models
import app.workers.dump.parsers
import sqlalchemy

logger = logging.getLogger(__name__)

_STREAM_BATCH_WORKS = 50_000


def _trim_heap() -> None:
    try:
        ctypes.cdll.LoadLibrary("libc.so.6").malloc_trim(0)
    except Exception:
        pass


async def process_reading_log_dump(file_path: str) -> int:
    # Accumulate into a staging table rather than books.books directly: the
    # parse can run for hours, and an interruption partway through must leave
    # the previous good counts in place, not zeroed. books.books is only
    # touched once, in _apply_staged_counts, after the whole file has parsed.
    async with app.models.AsyncSessionLocal() as staging_session:
        await staging_session.execute(sqlalchemy.text("TRUNCATE books.reading_log_staging"))
        await staging_session.commit()
    logger.info("[dump] Phase 6: cleared reading-log staging, starting streaming parse")

    queue: asyncio.Queue = asyncio.Queue(maxsize=4)
    loop = asyncio.get_running_loop()

    def _stream_batches() -> None:
        batch: dict[str, dict[str, int]] = {}
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        continue
                    work_key = (
                        parts[0].strip().replace("/works/", "").replace("/books/", "")
                    )
                    shelf = parts[2].strip()

                    if work_key not in batch:
                        batch[work_key] = {"want": 0, "reading": 0, "read": 0}

                    if shelf == "Want to Read":
                        batch[work_key]["want"] += 1
                    elif shelf == "Currently Reading":
                        batch[work_key]["reading"] += 1
                    elif shelf == "Already Read":
                        batch[work_key]["read"] += 1

                    if len(batch) >= _STREAM_BATCH_WORKS:
                        asyncio.run_coroutine_threadsafe(
                            queue.put(batch), loop
                        ).result()
                        batch = {}
                except (ValueError, IndexError):
                    continue

        if batch:
            asyncio.run_coroutine_threadsafe(queue.put(batch), loop).result()
        asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    read_task = asyncio.create_task(asyncio.to_thread(_stream_batches))

    updated = 0
    batches_done = 0

    async with app.models.AsyncSessionLocal() as session:
        try:
            while True:
                batch = await queue.get()
                if batch is None:
                    break

                updated += await _flush_reading_log_batch(session, batch)
                batches_done += 1
                gc.collect()
                _trim_heap()
                logger.info(
                    f"[dump] Phase 6: batch {batches_done} done "
                    f"({batches_done * _STREAM_BATCH_WORKS:,} works processed), "
                    f"{updated} book rows updated so far"
                )

            logger.info(
                f"[dump] Phase 6: parse complete, {updated} staged rows, "
                "applying to books.books"
            )
            applied = await _apply_staged_counts(session)
            logger.info(f"[dump] Phase 6 complete: {applied} book rows updated with reading log")
            return applied

        except Exception as e:
            await session.rollback()
            logger.error(f"[dump] Error in process_reading_log_dump: {e}")
            raise
        finally:
            await read_task


async def _flush_reading_log_batch(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    batch: dict[str, dict[str, int]],
) -> int:
    work_ol_ids = list(batch.keys())
    updated = 0

    chunk_size = 1000
    for i in range(0, len(work_ol_ids), chunk_size):
        chunk_ids = work_ol_ids[i : i + chunk_size]
        book_lookup = await app.workers.dump.parsers.batch_lookup_books(session, chunk_ids)

        batch_params: list[dict] = []
        for work_ol_id in chunk_ids:
            book_rows = book_lookup.get(work_ol_id)
            if not book_rows:
                continue
            counts = batch[work_ol_id]
            for book_id, _language in book_rows:
                batch_params.append(
                    {
                        "bid": book_id,
                        "want": counts["want"],
                        "reading": counts["reading"],
                        "read": counts["read"],
                    }
                )

        batch_params.sort(key=lambda x: x["bid"])

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
            # Same work can straddle two streamed batches, so this accumulates
            # onto the staging row rather than overwriting it.
            await session.execute(
                sqlalchemy.text(
                    "INSERT INTO books.reading_log_staging AS s "
                    "(book_id, ol_want_to_read_count, ol_currently_reading_count, ol_already_read_count) "
                    f"SELECT * FROM (VALUES {', '.join(values_parts)}) "
                    "AS v(bid, want, reading, already_read) "
                    "ON CONFLICT (book_id) DO UPDATE SET "
                    "ol_want_to_read_count = s.ol_want_to_read_count + EXCLUDED.ol_want_to_read_count, "
                    "ol_currently_reading_count = s.ol_currently_reading_count + EXCLUDED.ol_currently_reading_count, "
                    "ol_already_read_count = s.ol_already_read_count + EXCLUDED.ol_already_read_count"
                ),
                params,
            )
            updated += len(sub)

    await session.commit()
    return updated


async def _apply_staged_counts(session: sqlalchemy.ext.asyncio.AsyncSession) -> int:
    # Only now, with the full dump file parsed, do we touch books.books —
    # in one shot, so a crash before this point leaves the last good data
    # untouched instead of half-reset.
    applied_result = await session.execute(
        sqlalchemy.text(
            "UPDATE books.books AS b SET "
            "ol_want_to_read_count = s.ol_want_to_read_count, "
            "ol_currently_reading_count = s.ol_currently_reading_count, "
            "ol_already_read_count = s.ol_already_read_count "
            "FROM books.reading_log_staging AS s "
            "WHERE b.book_id = s.book_id"
        )
    )
    applied = applied_result.rowcount or 0

    await session.execute(
        sqlalchemy.text(
            "UPDATE books.books SET "
            "ol_want_to_read_count = 0, ol_currently_reading_count = 0, ol_already_read_count = 0 "
            "WHERE open_library_id IS NOT NULL "
            "AND book_id NOT IN (SELECT book_id FROM books.reading_log_staging)"
        )
    )

    await session.commit()
    return applied
