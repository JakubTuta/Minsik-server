import asyncio
import logging
import signal
import sys

import app.config
import app.grpc
import app.models

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


async def init_db():
    async with app.models.engine.begin() as conn:
        await conn.run_sync(app.models.Base.metadata.create_all)


async def shutdown(signal_received=None):
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

        await app.grpc.serve()

    except KeyboardInterrupt:
        await shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        await shutdown()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
