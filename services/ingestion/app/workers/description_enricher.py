import asyncio
import logging
import typing

import app.config
import app.models
import app.workers.dump.language_detect
import app.workers.wikipedia
import httpx
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_USER_AGENT = "Minsik/1.0 (contact@minsik.app)"

# One candidate query per entity kind. Every one is limited to the languages the
# site serves, skips what an admin edited, and returns the language of the row so the
# description is fetched from that language's Wikipedia and checked to be in it.
_BOOK_CANDIDATES_SQL = sqlalchemy.text(
    """
    SELECT b.book_id AS entity_id, b.title AS name, b.language, first_author.name AS author_name
    FROM books.books b
    LEFT JOIN LATERAL (
        SELECT a.name FROM books.book_authors ba
        JOIN books.authors a ON a.author_id = ba.author_id
        WHERE ba.book_id = b.book_id ORDER BY a.author_id LIMIT 1
    ) first_author ON TRUE
    WHERE b.language = ANY(:languages)
      AND (b.description IS NULL OR LENGTH(b.description) < :min_len)
      AND NOT ('description' = ANY(b.manually_edited_fields))
      AND (b.enrichment_attempted_at IS NULL
           OR b.enrichment_attempted_at < NOW() - make_interval(days => :cooldown))
    ORDER BY COALESCE(b.ol_already_read_count, 0) + COALESCE(b.ol_want_to_read_count, 0)
             + b.view_count + b.rating_count DESC
    LIMIT :limit
    """
)
_SERIES_CANDIDATES_SQL = sqlalchemy.text(
    """
    SELECT s.series_id AS entity_id, s.name, s.language, NULL AS author_name
    FROM books.series s
    WHERE s.language = ANY(:languages)
      AND (s.description IS NULL OR LENGTH(s.description) < :min_len)
      AND NOT ('description' = ANY(s.manually_edited_fields))
      AND (s.enrichment_attempted_at IS NULL
           OR s.enrichment_attempted_at < NOW() - make_interval(days => :cooldown))
    ORDER BY s.view_count DESC
    LIMIT :limit
    """
)
_AUTHOR_CANDIDATES_SQL = sqlalchemy.text(
    """
    SELECT a.author_id, a.name, a.wikidata_id
    FROM books.authors a
    WHERE NOT ('bio' = ANY(a.manually_edited_fields))
      AND NOT EXISTS (
          SELECT 1 FROM books.author_localizations al
          WHERE al.author_id = a.author_id AND al.language = :language
            AND (al.bio IS NOT NULL OR al.updated_at > NOW() - make_interval(days => :cooldown))
      )
    ORDER BY a.view_count DESC
    LIMIT :limit
    """
)
_UPDATE_BOOK_SQL = sqlalchemy.text(
    "UPDATE books.books SET description = :description WHERE book_id = :entity_id "
    "AND (description IS NULL OR LENGTH(description) < :min_len)"
)
_UPDATE_SERIES_SQL = sqlalchemy.text(
    "UPDATE books.series SET description = :description WHERE series_id = :entity_id "
    "AND (description IS NULL OR LENGTH(description) < :min_len)"
)
_MARK_BOOKS_SQL = sqlalchemy.text("UPDATE books.books SET enrichment_attempted_at = NOW() WHERE book_id = ANY(:ids)")
_MARK_SERIES_SQL = sqlalchemy.text("UPDATE books.series SET enrichment_attempted_at = NOW() WHERE series_id = ANY(:ids)")
_UPSERT_LOCALIZATION_SQL = sqlalchemy.text(
    """
    INSERT INTO books.author_localizations AS al (author_id, language, name, bio, wikipedia_url, source, updated_at)
    VALUES (:author_id, :language, :name, :bio, :wikipedia_url, 'wikipedia', NOW())
    ON CONFLICT (author_id, language) DO UPDATE SET
        name = COALESCE(EXCLUDED.name, al.name),
        bio = COALESCE(EXCLUDED.bio, al.bio),
        wikipedia_url = COALESCE(EXCLUDED.wikipedia_url, al.wikipedia_url),
        updated_at = NOW()
    """
)
_FILL_CANONICAL_BIO_SQL = sqlalchemy.text(
    "UPDATE books.authors SET bio = :bio WHERE author_id = :author_id "
    "AND (bio IS NULL OR LENGTH(bio) < :min_len) AND NOT ('bio' = ANY(manually_edited_fields))"
)


def _accept(extract: typing.Optional[str], language: str, min_length: int) -> typing.Optional[str]:
    """The extract if it is long enough and written in `language`; a page in another language is dropped."""
    if extract and len(extract) >= min_length and app.workers.dump.language_detect.fits_language(extract, language):
        return extract
    return None


async def _enrich_described(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    wikipedia: app.workers.wikipedia.WikipediaClient,
    candidates_sql: sqlalchemy.TextClause,
    update_sql: sqlalchemy.TextClause,
    mark_sql: sqlalchemy.TextClause,
    batch_size: int,
    min_length: int,
    cooldown_days: int,
    request_delay: float,
    languages: list[str],
) -> int:
    rows = (await session.execute(
        candidates_sql,
        {"languages": languages, "min_len": min_length, "cooldown": cooldown_days, "limit": batch_size},
    )).fetchall()
    if not rows:
        return 0

    # The lookups below take minutes; do not sit in an open transaction meanwhile.
    await session.commit()

    updated = 0
    try:
        for row in rows:
            term = f"{row.name} {row.author_name}" if row.author_name else row.name
            extract = _accept(
                await wikipedia.verified_extract(row.language, row.name, term, row.author_name), row.language, min_length
            )
            if extract:
                result = await session.execute(
                    update_sql, {"description": extract, "entity_id": row.entity_id, "min_len": min_length}
                )
                updated += result.rowcount or 0
            await asyncio.sleep(request_delay)
    finally:
        await session.execute(mark_sql, {"ids": [row.entity_id for row in rows]})
        await session.commit()
    return updated


async def enrich_books(session, wikipedia, languages, batch_size, min_length, cooldown_days, request_delay) -> int:
    return await _enrich_described(
        session, wikipedia, _BOOK_CANDIDATES_SQL, _UPDATE_BOOK_SQL, _MARK_BOOKS_SQL,
        batch_size, min_length, cooldown_days, request_delay, languages,
    )


async def enrich_series(session, wikipedia, languages, batch_size, min_length, cooldown_days, request_delay) -> int:
    return await _enrich_described(
        session, wikipedia, _SERIES_CANDIDATES_SQL, _UPDATE_SERIES_SQL, _MARK_SERIES_SQL,
        batch_size, min_length, cooldown_days, request_delay, languages,
    )


async def enrich_authors(session, wikipedia, languages, batch_size, min_length, cooldown_days, request_delay) -> int:
    """Per-language author names and bios from Wikidata sitelinks, falling back to a verified search."""
    updated = 0
    for language in languages:
        rows = (await session.execute(
            _AUTHOR_CANDIDATES_SQL, {"language": language, "cooldown": cooldown_days, "limit": batch_size}
        )).fetchall()
        if not rows:
            continue
        await session.commit()

        try:
            entities = await wikipedia.wikidata_entities(
                [row.wikidata_id for row in rows if row.wikidata_id], [language]
            )
        except (httpx.HTTPError, ValueError) as error:
            logger.debug(f"Wikidata lookup failed ({language}): {error}")
            entities = {}

        for row in rows:
            entity = entities.get(row.wikidata_id) or {"titles": {}, "labels": {}}
            title = entity["titles"].get(language)
            bio = _accept(
                await wikipedia.verified_extract(language, row.name, row.name, known_title=title), language, min_length
            )
            await session.execute(
                _UPSERT_LOCALIZATION_SQL,
                {
                    "author_id": row.author_id,
                    "language": language,
                    "name": entity["labels"].get(language),
                    "bio": bio,
                    "wikipedia_url": f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}" if title else None,
                },
            )
            if bio and language == "en":
                await session.execute(_FILL_CANONICAL_BIO_SQL, {"bio": bio, "author_id": row.author_id, "min_len": min_length})
            updated += 1 if bio else 0
            await asyncio.sleep(request_delay)
        await session.commit()
    return updated


async def run_description_enrichment() -> None:
    settings = app.config.settings
    if not settings.description_enrich_enabled:
        return

    try:
        redis_client = redis.Redis(
            host=settings.redis_host, port=settings.redis_port, db=settings.redis_db,
            password=settings.redis_password or None,
        )
        dump_running = bool(redis_client.get("dump_import_running"))
        redis_client.close()
        if dump_running:
            logger.info("Skipping description enrichment: dump import in progress")
            return
    except redis.RedisError:
        pass

    languages = [language.strip() for language in settings.description_enrich_languages.split(",") if language.strip()]
    arguments = (
        languages, settings.description_enrich_batch_size, settings.description_min_length,
        settings.description_enrich_cooldown_days, settings.description_enrich_request_delay,
    )
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _USER_AGENT}) as client:
            wikipedia = app.workers.wikipedia.WikipediaClient(client)
            async with app.models.AsyncSessionLocal() as session:
                books = await enrich_books(session, wikipedia, *arguments)
                authors = await enrich_authors(session, wikipedia, *arguments)
                series = await enrich_series(session, wikipedia, *arguments)
        logger.info(f"Description enrichment done: {books} books, {authors} author bios, {series} series updated")
    except Exception as error:
        logger.error(f"Description enrichment failed: {error}")
