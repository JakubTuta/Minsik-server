import asyncio
import logging
import sqlalchemy.ext.asyncio
import sqlalchemy.orm
import app.config

logger = logging.getLogger(__name__)

engine: sqlalchemy.ext.asyncio.AsyncEngine = None
async_session_maker: sqlalchemy.orm.sessionmaker = None


async def run_migrations() -> None:
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


async def init_db() -> None:
    global engine, async_session_maker

    logger.info("Running database migrations")
    await run_migrations()

    engine = sqlalchemy.ext.asyncio.create_async_engine(
        app.config.settings.database_url,
        pool_size=app.config.settings.db_pool_size,
        max_overflow=app.config.settings.db_max_overflow,
        pool_pre_ping=True,
        echo=app.config.settings.debug
    )

    async_session_maker = sqlalchemy.orm.sessionmaker(
        engine,
        class_=sqlalchemy.ext.asyncio.AsyncSession,
        expire_on_commit=False
    )


async def close_db() -> None:
    global engine
    if engine:
        await engine.dispose()


async def get_session() -> sqlalchemy.ext.asyncio.AsyncSession:
    async with async_session_maker() as session:
        yield session
