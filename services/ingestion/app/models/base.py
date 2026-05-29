import sqlalchemy.ext.asyncio
import app.config
import app.db_base


Base = app.db_base.Base

engine = sqlalchemy.ext.asyncio.create_async_engine(
    app.config.settings.database_url,
    pool_size=app.config.settings.db_pool_size,
    max_overflow=app.config.settings.db_max_overflow,
    echo=app.config.settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = sqlalchemy.ext.asyncio.async_sessionmaker(
    engine,
    class_=sqlalchemy.ext.asyncio.AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> sqlalchemy.ext.asyncio.AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
