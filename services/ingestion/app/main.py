import asyncio
import logging
import signal
import sys

import app.config
import app.grpc
import app.models
import app.workers.continuous_fetcher
import app.workers.description_enricher

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()


async def run_migrations():
    import os

    alembic_ini = os.path.join(os.path.dirname(__file__), '..', 'alembic.ini')

    # Skip migrations if alembic.ini doesn't exist
    if not os.path.exists(alembic_ini):
        logger.debug("No alembic.ini found, skipping migrations")
        return

    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config(alembic_ini)
        alembic_cfg.set_main_option("sqlalchemy.url", app.config.settings.database_url)

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: command.upgrade(alembic_cfg, "head")
        )
        logger.info("Database migrations completed successfully")
    except ImportError:
        logger.debug("Alembic not available, skipping migrations")
    except Exception as e:
        logger.warning(f"Migration error (service will continue): {str(e)}")


async def init_db():
    logger.info("Running database migrations")
    await run_migrations()

    try:
        async with app.models.engine.begin() as conn:
            await conn.run_sync(app.models.Base.metadata.create_all)
    except Exception as e:
        logger.warning(f"Schema creation error (service will continue): {str(e)}")


async def shutdown(signal_received=None):
    shutdown_event.set()
    await app.models.engine.dispose()


async def main():
    try:
        await init_db()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(s))
            )

        asyncio.create_task(app.workers.continuous_fetcher.run_continuous_ol_fetch(shutdown_event))
        asyncio.create_task(app.workers.continuous_fetcher.run_continuous_gb_fetch(shutdown_event))
        asyncio.create_task(app.workers.description_enricher.run_description_enrichment_loop(shutdown_event))

        await app.grpc.serve()

    except KeyboardInterrupt:
        await shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        await shutdown()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
