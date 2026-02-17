import asyncio
import logging
import typing

import httpx
import sqlalchemy
import sqlalchemy.ext.asyncio

import app.config
import app.models
import app.utils

logger = logging.getLogger(__name__)

_WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"


async def fetch_wikipedia_description(search_term: str, client: httpx.AsyncClient) -> typing.Optional[str]:
    try:
        search_response = await client.get(
            _WIKIPEDIA_API_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": search_term,
                "srlimit": 1,
                "format": "json"
            }
        )
        search_response.raise_for_status()
        search_data = search_response.json()

        results = search_data.get("query", {}).get("search", [])
        if not results:
            return None

        page_title = results[0]["title"]

        extract_response = await client.get(
            _WIKIPEDIA_API_URL,
            params={
                "action": "query",
                "titles": page_title,
                "prop": "extracts",
                "exintro": True,
                "exsentences": 3,
                "explaintext": True,
                "format": "json"
            }
        )
        extract_response.raise_for_status()
        extract_data = extract_response.json()

        pages = extract_data.get("query", {}).get("pages", {})
        for page in pages.values():
            extract = page.get("extract", "").strip()
            if extract:
                extract = app.utils.clean_description(extract)
                return extract

        return None

    except Exception as e:
        logger.debug(f"Wikipedia lookup failed for '{search_term}': {str(e)}")
        return None


async def enrich_books(session: sqlalchemy.ext.asyncio.AsyncSession, batch_size: int, min_length: int) -> int:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT b.book_id, b.title, a.name as author_name "
            "FROM books.books b "
            "LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id "
            "LEFT JOIN books.authors a ON ba.author_id = a.author_id "
            "WHERE b.description IS NULL OR LENGTH(b.description) < :min_len "
            "ORDER BY b.book_id "
            "LIMIT :limit"
        ),
        {"min_len": min_length, "limit": batch_size}
    )
    rows = result.fetchall()

    if not rows:
        return 0

    updated = 0
    async with httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "Minsik/1.0 (contact@minsik.app)"}
    ) as client:
        for row in rows:
            book_id = row.book_id
            title = row.title
            author_name = row.author_name

            search_term = f"{title} {author_name} novel" if author_name else f"{title} novel"
            description = await fetch_wikipedia_description(search_term, client)

            if description and len(description) >= min_length:
                await session.execute(
                    sqlalchemy.text(
                        "UPDATE books.books SET description = :desc, updated_at = NOW() "
                        "WHERE book_id = :book_id"
                    ),
                    {"desc": description, "book_id": book_id}
                )
                updated += 1

    if updated > 0:
        await session.commit()

    return updated


async def enrich_authors(session: sqlalchemy.ext.asyncio.AsyncSession, batch_size: int, min_length: int) -> int:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT author_id, name FROM books.authors "
            "WHERE bio IS NULL OR LENGTH(bio) < :min_len "
            "ORDER BY author_id "
            "LIMIT :limit"
        ),
        {"min_len": min_length, "limit": batch_size}
    )
    rows = result.fetchall()

    if not rows:
        return 0

    updated = 0
    async with httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "Minsik/1.0 (contact@minsik.app)"}
    ) as client:
        for row in rows:
            author_id = row.author_id
            name = row.name

            description = await fetch_wikipedia_description(f"{name} author", client)

            if description and len(description) >= min_length:
                await session.execute(
                    sqlalchemy.text(
                        "UPDATE books.authors SET bio = :bio, updated_at = NOW() "
                        "WHERE author_id = :author_id"
                    ),
                    {"bio": description, "author_id": author_id}
                )
                updated += 1

    if updated > 0:
        await session.commit()

    return updated


async def enrich_series(session: sqlalchemy.ext.asyncio.AsyncSession, batch_size: int, min_length: int) -> int:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT series_id, name FROM books.series "
            "WHERE description IS NULL OR LENGTH(description) < :min_len "
            "ORDER BY series_id "
            "LIMIT :limit"
        ),
        {"min_len": min_length, "limit": batch_size}
    )
    rows = result.fetchall()

    if not rows:
        return 0

    updated = 0
    async with httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "Minsik/1.0 (contact@minsik.app)"}
    ) as client:
        for row in rows:
            series_id = row.series_id
            name = row.name

            description = await fetch_wikipedia_description(f"{name} book series", client)

            if description and len(description) >= min_length:
                await session.execute(
                    sqlalchemy.text(
                        "UPDATE books.series SET description = :desc, updated_at = NOW() "
                        "WHERE series_id = :series_id"
                    ),
                    {"desc": description, "series_id": series_id}
                )
                updated += 1

    if updated > 0:
        await session.commit()

    return updated


async def run_description_enrichment_loop(shutdown_event: asyncio.Event) -> None:
    logger.info("Description enrichment task started")
    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(app.config.settings.description_enrich_interval_hours * 3600)
        except asyncio.CancelledError:
            break

        if shutdown_event.is_set() or not app.config.settings.description_enrich_enabled:
            break

        try:
            batch_size = app.config.settings.description_enrich_batch_size
            min_length = app.config.settings.description_min_length

            async with app.models.AsyncSessionLocal() as session:
                books_updated = await enrich_books(session, batch_size, min_length)
                authors_updated = await enrich_authors(session, batch_size, min_length)
                series_updated = await enrich_series(session, batch_size, min_length)

            logger.info(
                f"Description enrichment done: {books_updated} books, "
                f"{authors_updated} authors, {series_updated} series updated"
            )

        except Exception as e:
            logger.error(f"Description enrichment failed: {str(e)}")

    logger.info("Description enrichment task stopped")
