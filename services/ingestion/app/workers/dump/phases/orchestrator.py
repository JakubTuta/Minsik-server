import ctypes
import datetime
import gc
import logging

import app.config
import app.models
import redis
from app.workers.dump import downloader, parsers
from app.workers.dump import state as job_state
from app.workers.dump.phases import (
    authors,
    editions,
    ratings,
    reading_log,
    wikidata,
    works,
)

logger = logging.getLogger(__name__)


def _trim_heap() -> None:
    try:
        ctypes.cdll.LoadLibrary("libc.so.6").malloc_trim(0)
    except Exception:
        pass


async def run_import_dump(job_id: str, redis_client: redis.Redis) -> None:
    import pathlib

    tmp_dir = pathlib.Path(app.config.settings.dump_tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    base_url = app.config.settings.ol_dump_base_url

    phase_files: dict[int, pathlib.Path] = {
        1: tmp_dir / "ol_dump_authors.txt.gz",
        2: tmp_dir / "ol_dump_wikidata.txt.gz",
        3: tmp_dir / "ol_dump_works.txt.gz",
        4: tmp_dir / "ol_dump_editions.txt.gz",
        5: tmp_dir / "ol_dump_ratings.txt.gz",
        6: tmp_dir / "ol_dump_reading_log.txt.gz",
    }

    saved_state = job_state.get_job_state(redis_client)
    if saved_state and saved_state.get("job_id") == job_id:
        completed: set[int] = set(saved_state.get("completed_phases", []))
        phase_results: dict = saved_state.get("phase_results", {})
    else:
        completed = set()
        phase_results = {}
        saved_state = {
            "job_id": job_id,
            "completed_phases": [],
            "started_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "phase_results": {},
        }
        job_state.save_job_state(redis_client, saved_state)

    def _set_status(msg: str) -> None:
        try:
            redis_client.set(f"dump_import_{job_id}_status", msg, ex=86400)
            redis_client.set(
                "dump_import_status", msg, ex=job_state._REDIS_JOB_STATE_TTL
            )
        except Exception:
            pass

    def _finish_phase(phase: int, result=None) -> None:
        completed.add(phase)
        if result is not None:
            phase_results[str(phase)] = result
        phase_files[phase].unlink(missing_ok=True)
        saved_state["completed_phases"] = sorted(completed)
        saved_state["phase_results"] = phase_results
        job_state.save_job_state(redis_client, saved_state)
        gc.collect()
        _trim_heap()

    if completed:
        logger.info(
            f"[dump] Resuming dump import (job_id: {job_id}), "
            f"phases already completed: {sorted(completed)}"
        )
    else:
        logger.info(f"[dump] Starting dump import (job_id: {job_id})")

    try:
        try:
            redis_client.set("dump_import_running", 1)
        except Exception:
            pass

        if 1 not in completed:
            _set_status("Phase 1/6: downloading authors dump")
            await downloader.download_file(
                f"{base_url}/ol_dump_authors_latest.txt.gz",
                str(phase_files[1]),
            )
            _set_status("Phase 1/6: processing authors")
            authors_count = await authors.process_authors_dump(str(phase_files[1]))
            _finish_phase(1, {"count": authors_count})
        else:
            logger.info("[dump] Phase 1 (authors) already completed, skipping")

        if 2 not in completed:
            if app.config.settings.dump_wikidata_enabled:
                _set_status("Phase 2/6: enriching authors via Wikidata API")
                wikidata_count = await wikidata.process_wikidata_enrichment()
                _finish_phase(2, {"count": wikidata_count})
            else:
                logger.info("[dump] Phase 2 skipped (wikidata disabled)")
                _finish_phase(2, {"skipped": True})
        else:
            logger.info("[dump] Phase 2 (wikidata) already completed, skipping")

        if 3 not in completed:
            _set_status("Phase 3/6: downloading works dump")
            await downloader.download_file(
                f"{base_url}/ol_dump_works_latest.txt.gz",
                str(phase_files[3]),
            )
            _set_status("Phase 3/6: processing works")
            works_count = await works.process_works_dump(str(phase_files[3]))
            _finish_phase(3, {"count": works_count})
        else:
            logger.info("[dump] Phase 3 (works) already completed, skipping")

        if 4 not in completed:
            if app.config.settings.dump_editions_enabled:
                _set_status("Phase 4/6: building known-works filter")
                async with app.models.AsyncSessionLocal() as session:
                    known_works_filter = await parsers.build_known_works_filter(session)

                gc.collect()
                _trim_heap()

                _set_status("Phase 4/6: downloading editions dump")
                await downloader.download_file(
                    f"{base_url}/ol_dump_editions_latest.txt.gz",
                    str(phase_files[4]),
                )
                gc.collect()
                _trim_heap()

                _set_status("Phase 4/6: processing editions")
                editions_stats = await editions.process_editions_dump(
                    str(phase_files[4]), known_works_filter
                )
                del known_works_filter
                _finish_phase(4, editions_stats)
            else:
                logger.info("[dump] Phase 4 skipped (editions disabled)")
                _finish_phase(4, {"skipped": True})
        else:
            logger.info("[dump] Phase 4 (editions) already completed, skipping")

        if 5 not in completed:
            if app.config.settings.dump_ratings_enabled:
                _set_status("Phase 5/6: downloading ratings dump")
                await downloader.download_file(
                    f"{base_url}/ol_dump_ratings_latest.txt.gz",
                    str(phase_files[5]),
                )
                _set_status("Phase 5/6: processing ratings")
                ratings_count = await ratings.process_ratings_dump(str(phase_files[5]))
                _finish_phase(5, {"count": ratings_count})
            else:
                logger.info("[dump] Phase 5 skipped (ratings disabled)")
                _finish_phase(5, {"skipped": True})
        else:
            logger.info("[dump] Phase 5 (ratings) already completed, skipping")

        if 6 not in completed:
            if app.config.settings.dump_reading_log_enabled:
                _set_status("Phase 6/6: downloading reading log dump")
                await downloader.download_file(
                    f"{base_url}/ol_dump_reading-log_latest.txt.gz",
                    str(phase_files[6]),
                )
                _set_status("Phase 6/6: processing reading log")
                reading_log_count = await reading_log.process_reading_log_dump(
                    str(phase_files[6])
                )
                _finish_phase(6, {"count": reading_log_count})
            else:
                logger.info("[dump] Phase 6 skipped (reading log disabled)")
                _finish_phase(6, {"skipped": True})
        else:
            logger.info("[dump] Phase 6 (reading log) already completed, skipping")

        p = phase_results
        summary = (
            f"Complete: "
            f"{p.get('1', {}).get('count', 0)} authors, "
            f"{p.get('2', {}).get('count', 0)} wikidata enriched, "
            f"{p.get('3', {}).get('count', 0)} works, "
            f"{p.get('4', {}).get('enriched', 0)} editions enriched, "
            f"{p.get('4', {}).get('new_lang_rows', 0)} new language rows, "
            f"{p.get('5', {}).get('count', 0)} ratings applied, "
            f"{p.get('6', {}).get('count', 0)} reading log applied"
        )
        logger.info(f"[dump] {summary}")
        _set_status(summary)

    except Exception as e:
        logger.error(f"[dump] Dump import failed: {e}")
        _set_status(f"Failed: {e}")
        raise

    finally:
        for f in phase_files.values():
            f.unlink(missing_ok=True)
        try:
            redis_client.delete("dump_import_running")
            if completed == {1, 2, 3, 4, 5, 6}:
                job_state.clear_job_state(redis_client)
        except Exception:
            pass
