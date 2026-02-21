import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from app.config import settings
from app.models.base import Base
from redis import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = f"postgresql+asyncpg://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/test_minsik_db"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    default_db_url = f"postgresql+asyncpg://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/postgres"
    default_engine = create_async_engine(
        default_db_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )

    async with default_engine.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS test_minsik_db"))
        await conn.execute(text("CREATE DATABASE test_minsik_db"))

    await default_engine.dispose()

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS books"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS user_data"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS user_data.bookshelves (
                bookshelf_id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                book_id BIGINT NOT NULL
            )
        """
            )
        )

    yield engine

    await engine.dispose()

    default_engine = create_async_engine(
        default_db_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with default_engine.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS test_minsik_db"))
    await default_engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def commit_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.execute(
            text(
                "TRUNCATE books.book_authors, books.book_genres, books.books, "
                "books.authors, books.genres, books.series, user_data.bookshelves CASCADE"
            )
        )
        await session.commit()


@pytest.fixture
def redis_client():
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=1,
        password=settings.redis_password if settings.redis_password else None,
        decode_responses=True,
    )

    yield client

    client.flushdb()
    client.close()


@pytest.fixture
def mock_open_library_response():
    return {
        "works": [
            {
                "key": "/works/OL123W",
                "title": "Neuromancer",
                "authors": [{"key": "/authors/OL456A"}],
                "cover_id": 12345,
                "first_publish_year": 1984,
            }
        ]
    }


@pytest.fixture
def mock_open_library_work():
    return {
        "key": "/works/OL123W",
        "title": "Neuromancer",
        "description": "A science fiction novel",
        "subjects": ["Science Fiction", "Cyberpunk"],
        "covers": [12345],
        "first_publish_date": "1984",
        "editions": {
            "entries": [
                {
                    "physical_format": "Hardcover",
                    "covers": [12345],
                    "publishers": ["Ace Books"],
                }
            ]
        },
    }


@pytest.fixture
def mock_open_library_author():
    return {
        "key": "/authors/OL456A",
        "name": "William Gibson",
        "bio": "Canadian-American science fiction writer",
        "birth_date": "1948-03-17",
        "photos": [67890],
    }


@pytest.fixture
def mock_google_books_response():
    return {
        "items": [
            {
                "id": "gb123",
                "volumeInfo": {
                    "title": "Neuromancer",
                    "authors": ["William Gibson"],
                    "description": "A science fiction novel",
                    "categories": ["Fiction", "Science Fiction"],
                    "publishedDate": "1984",
                    "publisher": "Ace Books",
                    "imageLinks": {"thumbnail": "http://example.com/cover.jpg"},
                },
                "accessInfo": {"epub": {"isAvailable": True}},
            }
        ]
    }


@pytest.fixture
def sample_book_data():
    return {
        "title": "Neuromancer",
        "language": "en",
        "slug": "neuromancer",
        "description": "A science fiction novel",
        "original_publication_year": 1984,
        "formats": ["hardcover", "ebook"],
        "cover_history": [
            {
                "year": 1984,
                "cover_url": "http://example.com/cover1.jpg",
                "publisher": "Ace Books",
            }
        ],
        "primary_cover_url": "http://example.com/cover1.jpg",
        "open_library_id": "OL123W",
        "google_books_id": "gb123",
        "authors": [
            {
                "name": "William Gibson",
                "slug": "william-gibson",
                "bio": "Canadian-American science fiction writer",
                "birth_date": None,
                "death_date": None,
                "photo_url": None,
                "open_library_id": "OL456A",
            }
        ],
        "genres": [
            {"name": "Science Fiction", "slug": "science-fiction"},
            {"name": "Cyberpunk", "slug": "cyberpunk"},
        ],
    }
