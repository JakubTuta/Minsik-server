import sqlalchemy.ext.asyncio
import sqlalchemy.orm
import app.config


engine: sqlalchemy.ext.asyncio.AsyncEngine = None
async_session_maker: sqlalchemy.orm.sessionmaker = None


async def init_db() -> None:
    global engine, async_session_maker

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
