import asyncio
import logging
import sqlalchemy.ext.asyncio
import sqlalchemy.orm
import app.config

logger = logging.getLogger(__name__)

engine: sqlalchemy.ext.asyncio.AsyncEngine = None
async_session_maker: sqlalchemy.orm.sessionmaker = None


async def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config
    import os

    alembic_ini = os.path.join(os.path.dirname(__file__), '..', 'alembic.ini')
    alembic_cfg = Config(alembic_ini)
    alembic_cfg.set_main_option("sqlalchemy.url", app.config.settings.database_url)

    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: command.upgrade(alembic_cfg, "head")
        )
        logger.info("Database migrations completed successfully")
    except Exception as e:
        logger.error(f"Error running migrations: {str(e)}")
        raise


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
