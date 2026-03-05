import asyncio
import logging
import signal
import sys

import app.config
import app.grpc
import app.models
import app.workers.continuous_fetcher
import app.workers.data_cleaner
import app.workers.description_enricher
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()
scheduler: AsyncScheduler = None


async def clear_stale_import_flag() -> bool:
    try:
        import redis as redis_lib

        r = redis_lib.Redis(
            host=app.config.settings.redis_host,
            port=app.config.settings.redis_port,
            db=app.config.settings.redis_db,
            password=app.config.settings.redis_password or None,
        )
        if r.exists("dump_import_running"):
            r.delete("dump_import_running")
            logger.info("Cleared stale dump_import_running flag from previous run")

        from app.workers import dump

        state = dump.get_job_state(r)
        r.close()

        if state and len(state.get("completed_phases", [])) < 6:
            logger.info(
                f"Resumable dump job detected (job_id: {state['job_id']}), "
                f"completed phases: {state['completed_phases']}. "
                f"Auto-resuming."
            )
            return True
        return False
    except Exception:
        return False


async def shutdown(signal_received=None):
    shutdown_event.set()
    global scheduler
    current_scheduler = scheduler
    scheduler = None
    if current_scheduler:
        try:
            await current_scheduler.__aexit__(None, None, None)
        except BaseException:
            pass
    await app.models.engine.dispose()


async def main():
    try:
        should_resume = await clear_stale_import_flag()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

        asyncio.create_task(
            asyncio.sleep(0)  # yield to event loop before serve() blocks
        )

        scheduler = AsyncScheduler()
        await scheduler.__aenter__()

        if app.config.settings.continuous_fetch_enabled:
            await scheduler.add_schedule(
                app.workers.continuous_fetcher.run_continuous_ol_fetch,
                CronTrigger.from_crontab(app.config.settings.continuous_ol_cron),
            )
            await scheduler.add_schedule(
                app.workers.continuous_fetcher.run_continuous_gb_fetch,
                CronTrigger.from_crontab(app.config.settings.continuous_gb_cron),
            )
            logger.info(
                f"[ingestion] OL fetch scheduled (cron: '{app.config.settings.continuous_ol_cron}')"
            )
            logger.info(
                f"[ingestion] GB fetch scheduled (cron: '{app.config.settings.continuous_gb_cron}')"
            )

        if app.config.settings.description_enrich_enabled:
            await scheduler.add_schedule(
                app.workers.description_enricher.run_description_enrichment,
                CronTrigger.from_crontab(app.config.settings.description_enrich_cron),
            )
            logger.info(
                f"[ingestion] Description enrichment scheduled (cron: '{app.config.settings.description_enrich_cron}')"
            )

        if app.config.settings.cleanup_enabled:
            await scheduler.add_schedule(
                app.workers.data_cleaner.run_cleanup_job,
                CronTrigger.from_crontab(app.config.settings.cleanup_cron),
            )
            logger.info(
                f"[ingestion] Cleanup scheduled (cron: '{app.config.settings.cleanup_cron}')"
            )

        await scheduler.start_in_background()

        if should_resume:
            import redis as redis_lib
            from app.workers import dump

            resume_redis = redis_lib.Redis(
                host=app.config.settings.redis_host,
                port=app.config.settings.redis_port,
                db=app.config.settings.redis_db,
                password=app.config.settings.redis_password or None,
                decode_responses=True,
            )
            state = dump.get_job_state(resume_redis)
            if state:
                asyncio.create_task(dump.run_import_dump(state["job_id"], resume_redis))

        await app.grpc.serve()

    except KeyboardInterrupt:
        await shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        await shutdown()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
