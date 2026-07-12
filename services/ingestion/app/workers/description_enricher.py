import asyncio
import logging
import typing

import app.config
import app.models
import app.utils
import httpx
import redis
import sqlalchemy
import sqlalchemy.engine
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"


async def fetch_wikipedia_description(
    search_term: str, client: httpx.AsyncClient
) -> typing.Optional[str]:
    try:
        search_response = await client.get(
            _WIKIPEDIA_API_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": search_term,
                "srlimit": 1,
                "format": "json",
            },
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
                "exsentences": 5,
                "explaintext": True,
                "format": "json",
            },
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


async def _run_wikipedia_enrichment(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    entity_ids: list,
    search_terms: list[str],
    update_sql: str,
    mark_attempted_sql: str,
    id_param: str,
    min_length: int,
    request_delay: float,
) -> int:
    await session.execute(
        sqlalchemy.text(mark_attempted_sql),
        {"ids": entity_ids},
    )
    await session.commit()

    updated = 0
    async with httpx.AsyncClient(
        timeout=10.0, headers={"User-Agent": "Minsik/1.0 (contact@minsik.app)"}
    ) as client:
        for entity_id, search_term in zip(entity_ids, search_terms):
            description = await fetch_wikipedia_description(search_term, client)
            if description and len(description) >= min_length:
                result = await session.execute(
                    sqlalchemy.text(update_sql),
                    {"desc": description, id_param: entity_id},
                )
                if typing.cast(sqlalchemy.engine.CursorResult, result).rowcount:
                    updated += 1
            await asyncio.sleep(request_delay)
    if updated > 0:
        await session.commit()
    return updated


async def enrich_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    batch_size: int,
    min_length: int,
    cooldown_days: int,
    request_delay: float,
) -> int:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT b.book_id, b.title, a.name as author_name "
            "FROM books.books b "
            "LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id "
            "LEFT JOIN books.authors a ON ba.author_id = a.author_id "
            "WHERE (b.description IS NULL OR LENGTH(b.description) < :min_len) "
            "AND (b.enrichment_attempted_at IS NULL "
            "OR b.enrichment_attempted_at < NOW() - make_interval(days => :cooldown)) "
            "ORDER BY COALESCE(b.ol_already_read_count, 0) + COALESCE(b.ol_want_to_read_count, 0) "
            "+ b.view_count + b.rating_count DESC "
            "LIMIT :limit"
        ),
        {"min_len": min_length, "cooldown": cooldown_days, "limit": batch_size},
    )
    rows = result.fetchall()
    if not rows:
        return 0

    entity_ids = [row.book_id for row in rows]
    search_terms = [
        (
            f"{row.title} {row.author_name} novel"
            if row.author_name
            else f"{row.title} novel"
        )
        for row in rows
    ]
    return await _run_wikipedia_enrichment(
        session,
        entity_ids,
        search_terms,
        "UPDATE books.books SET description = :desc, updated_at = NOW() "
        "WHERE book_id = :book_id "
        "AND (description IS NULL OR LENGTH(description) < LENGTH(:desc))",
        "UPDATE books.books SET enrichment_attempted_at = NOW() WHERE book_id = ANY(:ids)",
        "book_id",
        min_length,
        request_delay,
    )


async def enrich_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    batch_size: int,
    min_length: int,
    cooldown_days: int,
    request_delay: float,
) -> int:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT author_id, name FROM books.authors "
            "WHERE (bio IS NULL OR LENGTH(bio) < :min_len) "
            "AND (enrichment_attempted_at IS NULL "
            "OR enrichment_attempted_at < NOW() - make_interval(days => :cooldown)) "
            "ORDER BY view_count DESC "
            "LIMIT :limit"
        ),
        {"min_len": min_length, "cooldown": cooldown_days, "limit": batch_size},
    )
    rows = result.fetchall()
    if not rows:
        return 0

    entity_ids = [row.author_id for row in rows]
    search_terms = [f"{row.name} author" for row in rows]
    return await _run_wikipedia_enrichment(
        session,
        entity_ids,
        search_terms,
        "UPDATE books.authors SET bio = :desc, updated_at = NOW() "
        "WHERE author_id = :author_id "
        "AND (bio IS NULL OR LENGTH(bio) < LENGTH(:desc))",
        "UPDATE books.authors SET enrichment_attempted_at = NOW() WHERE author_id = ANY(:ids)",
        "author_id",
        min_length,
        request_delay,
    )


async def enrich_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    batch_size: int,
    min_length: int,
    cooldown_days: int,
    request_delay: float,
) -> int:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT s.series_id, s.name FROM books.series s "
            "WHERE (s.description IS NULL OR LENGTH(s.description) < :min_len) "
            "AND (s.enrichment_attempted_at IS NULL "
            "OR s.enrichment_attempted_at < NOW() - make_interval(days => :cooldown)) "
            "ORDER BY s.view_count DESC "
            "LIMIT :limit"
        ),
        {"min_len": min_length, "cooldown": cooldown_days, "limit": batch_size},
    )
    rows = result.fetchall()
    if not rows:
        return 0

    entity_ids = [row.series_id for row in rows]
    search_terms = [f"{row.name} book series" for row in rows]
    return await _run_wikipedia_enrichment(
        session,
        entity_ids,
        search_terms,
        "UPDATE books.series SET description = :desc, updated_at = NOW() "
        "WHERE series_id = :series_id "
        "AND (description IS NULL OR LENGTH(description) < LENGTH(:desc))",
        "UPDATE books.series SET enrichment_attempted_at = NOW() WHERE series_id = ANY(:ids)",
        "series_id",
        min_length,
        request_delay,
    )


async def run_description_enrichment() -> None:
    if not app.config.settings.description_enrich_enabled:
        return

    try:
        _rc = redis.Redis(
            host=app.config.settings.redis_host,
            port=app.config.settings.redis_port,
            db=app.config.settings.redis_db,
            password=(
                app.config.settings.redis_password
                if app.config.settings.redis_password
                else None
            ),
        )
        dump_running = bool(_rc.get("dump_import_running"))
        _rc.close()
        if dump_running:
            logger.info("Skipping description enrichment: dump import in progress")
            return
    except Exception:
        pass

    try:
        batch_size = app.config.settings.description_enrich_batch_size
        min_length = app.config.settings.description_min_length
        cooldown_days = app.config.settings.description_enrich_cooldown_days
        request_delay = app.config.settings.description_enrich_request_delay

        async with app.models.AsyncSessionLocal() as session:
            books_updated = await enrich_books(
                session, batch_size, min_length, cooldown_days, request_delay
            )
            authors_updated = await enrich_authors(
                session, batch_size, min_length, cooldown_days, request_delay
            )
            series_updated = await enrich_series(
                session, batch_size, min_length, cooldown_days, request_delay
            )

        logger.info(
            f"Description enrichment done: {books_updated} books, "
            f"{authors_updated} authors, {series_updated} series updated"
        )

    except Exception as e:
        logger.error(f"Description enrichment failed: {str(e)}")
