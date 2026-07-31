import json
import logging
import typing

import app.cache
import app.config
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

BOW_TTL = 7 * 24 * 3600 + 3600
BOW_HISTORY_SIZE = 12

# A book of the week needs a cover and a usable first sentence, and both are
# per-edition. The same test gates the draw and the edition lookup, so a reader
# can never be shown an edition the draw would have rejected.
_RENDERABLE_EDITION = (
    "{alias}.primary_cover_url IS NOT NULL "
    "AND {alias}.first_sentence IS NOT NULL "
    "AND length({alias}.first_sentence) > 10"
)

_WEIGHTED_RATING_SQL = """
    CASE
        WHEN (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) > 0
        THEN ROUND(
            (COALESCE(b.avg_rating::numeric, 0) * COALESCE(b.rating_count, 0)
             + COALESCE(b.ol_avg_rating::numeric, 0) * COALESCE(b.ol_rating_count, 0))
            / (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)), 2
        )
        ELSE 0
    END
"""


def bow_selection_key(language: str) -> str:
    return f"bow:selection:{language}"


def bow_rendered_key(language: str) -> str:
    return f"bow:current:{language}"


def bow_history_key(language: str) -> str:
    return f"bow:history:{language}"


def available_languages() -> typing.List[str]:
    raw = app.config.settings.available_languages or "en"
    langs = [lang.strip() for lang in raw.split(",") if lang.strip()]
    return langs or ["en"]


async def _get_recent_work_ids(language: str) -> typing.List[str]:
    try:
        history = await app.cache.redis_client.lrange(bow_history_key(language), 0, -1)
        return [work_id for work_id in history if work_id]
    except Exception as e:
        logger.error(f"[bow] Error reading history ({language}): {str(e)}")
        return []


async def _push_history(language: str, work_id: str) -> None:
    try:
        key = bow_history_key(language)
        await app.cache.redis_client.lpush(key, work_id)
        await app.cache.redis_client.ltrim(key, 0, BOW_HISTORY_SIZE - 1)
    except Exception as e:
        logger.error(f"[bow] Error pushing history ({language}): {str(e)}")


async def _selected_work_ids(languages: typing.List[str]) -> typing.List[str]:
    """Works already holding a slot, so a fresh draw does not collide with them."""
    selections = [
        await app.cache.get_cached(bow_selection_key(language))
        for language in languages
    ]

    return [
        selection["work_id"]
        for selection in selections
        if selection and selection.get("work_id")
    ]


async def _draw_work(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    excluded_work_ids: typing.List[str],
    edition_language: typing.Optional[str],
) -> typing.Optional[str]:
    """Pick a work at random, optionally only from works published in a language.

    Only `work_id` is projected: a `RANDOM()` draw sorts every candidate row, so
    anything in the select list is computed for the whole candidate set rather
    than for the one row that survives `LIMIT`. Author and genre aggregation
    therefore lives in `_fetch_edition`, which runs against a single work.
    `DISTINCT` keeps the draw uniform over works rather than over editions,
    which would favour whatever has been translated the most.
    """
    language_filter = "AND b.language = :edition_language" if edition_language else ""

    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT candidate.work_id
            FROM (
                SELECT DISTINCT b.work_id
                FROM books.books b
                WHERE {_RENDERABLE_EDITION.format(alias="b")}
                  {language_filter}
                  AND EXISTS (SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id)
                  AND EXISTS (SELECT 1 FROM books.book_genres bg WHERE bg.book_id = b.book_id)
                  AND (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) >= 100
                  AND ({_WEIGHTED_RATING_SQL}) >= 4.0
                  AND b.work_id <> ALL(:excluded_work_ids)
            ) AS candidate
            ORDER BY RANDOM()
            LIMIT 1
            """
        ),
        {
            "excluded_work_ids": excluded_work_ids or [""],
            "edition_language": edition_language,
        },
    )
    row = result.fetchone()

    return row.work_id if row else None


async def _draw_for_language(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    taken_work_ids: typing.List[str],
) -> typing.Optional[str]:
    """Draw this language's own work, preferring one it can show in its own words.

    A translated edition rarely carries its own ratings or first sentence, so the
    language-scoped draw comes up empty for most of the catalogue outside
    English. Falling through to a language-agnostic draw is what makes the slot
    reliable: the reader still gets a book nobody else's slot is showing, just
    rendered in the closest edition `_fetch_edition` can find.
    """
    history = await _get_recent_work_ids(language)
    excluded = list(dict.fromkeys(taken_work_ids + history))

    for candidate_language in (language, None):
        work_id = await _draw_work(session, excluded, candidate_language)
        if work_id:
            return work_id

    # Every eligible work is in this language's own history: reuse is better
    # than an empty slot, but never at the cost of colliding with another
    # language's pick.
    return await _draw_work(session, taken_work_ids, None)


async def _fetch_edition(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    work_id: str,
    language: str,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    """Render a drawn work in the reader's language, English otherwise."""
    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT
                b.book_id,
                b.title,
                b.slug,
                b.language,
                b.primary_cover_url,
                b.first_sentence,
                ({_WEIGHTED_RATING_SQL}) AS weighted_avg_rating,
                COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0) AS total_rating_count,
                (
                    SELECT COALESCE(json_agg(json_build_object(
                        'author_id', a.author_id,
                        'name', a.name,
                        'slug', a.slug
                    ) ORDER BY a.name), '[]'::json)
                    FROM books.book_authors ba
                    JOIN books.authors a ON ba.author_id = a.author_id
                    WHERE ba.book_id = b.book_id
                ) AS authors,
                (
                    SELECT COALESCE(json_agg(json_build_object(
                        'genre_id', g.genre_id,
                        'name', g.name,
                        'slug', g.slug
                    ) ORDER BY g.name), '[]'::json)
                    FROM books.book_genres bg
                    JOIN books.genres g ON bg.genre_id = g.genre_id
                    WHERE bg.book_id = b.book_id
                ) AS categories
            FROM books.books b
            WHERE b.work_id = :work_id
              AND {_RENDERABLE_EDITION.format(alias="b")}
            ORDER BY (b.language = :language) DESC, (b.language = 'en') DESC, b.book_id ASC
            LIMIT 1
            """
        ),
        {"work_id": work_id, "language": language},
    )
    row = result.fetchone()
    if not row:
        return None

    authors = json.loads(row.authors) if isinstance(row.authors, str) else row.authors
    categories = (
        json.loads(row.categories)
        if isinstance(row.categories, str)
        else row.categories
    )

    return {
        "book_id": row.book_id,
        "title": row.title or "",
        "slug": row.slug or "",
        "language": row.language or language,
        "primary_cover_url": row.primary_cover_url or "",
        "first_sentence": row.first_sentence or "",
        "weighted_avg_rating": float(row.weighted_avg_rating or 0),
        "rating_count": int(row.total_rating_count or 0),
        "authors": authors or [],
        "categories": categories or [],
    }


async def _store_selection(language: str, work_id: str) -> None:
    await app.cache.set_cached(
        bow_selection_key(language), {"work_id": work_id}, BOW_TTL
    )
    await app.cache.delete_keys(bow_rendered_key(language))
    await _push_history(language, work_id)


async def _draw_languages(
    session_maker: typing.Callable,
    languages: typing.List[str],
    taken_work_ids: typing.List[str],
) -> typing.Dict[str, str]:
    drawn: typing.Dict[str, str] = {}

    async with session_maker() as session:
        for language in languages:
            work_id = await _draw_for_language(session, language, taken_work_ids)
            if not work_id:
                logger.error(f"[bow] No eligible work found for language={language}")
                continue

            taken_work_ids.append(work_id)
            drawn[language] = work_id

    for language, work_id in drawn.items():
        await _store_selection(language, work_id)
        logger.info(f"[bow] Work of the week for {language}: {work_id}")

    return drawn


async def refresh_book_of_the_week(
    session_maker: typing.Callable,
) -> typing.Dict[str, str]:
    """Draw a distinct work for every language.

    Each language gets a slot of its own and no two slots hold the same work, so
    switching language shows a different book rather than the same one in
    another edition.
    """
    logger.info("[bow] Drawing work of the week for every language")

    return await _draw_languages(session_maker, available_languages(), [])


async def ensure_book_of_the_week(session_maker: typing.Callable) -> None:
    """Fill only the slots that have no work drawn, leaving the others alone."""
    languages = available_languages()
    missing = [
        language
        for language in languages
        if not await app.cache.get_cached(bow_selection_key(language))
    ]

    if not missing:
        return

    logger.info(f"[bow] No selection cached for {', '.join(missing)}, drawing")
    await _draw_languages(session_maker, missing, await _selected_work_ids(languages))


async def get_book_of_the_week(
    session_maker: typing.Callable,
    language: str,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    """Serve this language's current work, or None when no work is drawn yet.

    Never draws: the draw scans the whole catalogue and would blow the caller's
    gRPC deadline, so a missing selection is reported rather than rebuilt inline
    and the weekly job (or an admin refresh) is left to fill it.
    """
    rendered_key = bow_rendered_key(language)
    cached = await app.cache.get_cached(rendered_key)
    if cached:
        return cached

    selection = await app.cache.get_cached(bow_selection_key(language))
    if not selection:
        return None

    async with session_maker() as session:
        book = await _fetch_edition(session, selection["work_id"], language)

    if not book:
        logger.error(
            f"[bow] Drawn work {selection['work_id']} has no renderable edition"
        )
        return None

    await app.cache.set_cached(rendered_key, book, BOW_TTL)

    return book
