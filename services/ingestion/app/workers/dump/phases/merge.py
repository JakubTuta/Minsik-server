"""Turn the staged OpenLibrary works and editions into one row per (work, language).

Rules the plan below enforces, each of which was a bug in the old importer:

* A row exists for every language an edition is written in, plus the language of
  the work's own title/description (English when that cannot be told).
* Text is never copied from one language row to another. An edition's title and
  description go to its own language row; the work-level text goes to the work's
  language row only.
* Existing rows keep their book_id, so every shelf, rating and comment pointing at
  them stays valid. Text that is already there is kept unless it is recognisably in
  the wrong language, and fields an admin edited are never touched.
* Slugs are unique per language; a collision with another work gets the work's
  OpenLibrary id as a suffix instead of overwriting that work's row.
* A work's authors are exactly the authors OpenLibrary lists for it (when any of
  them is known), which undoes the author lists that title-slug merges piled up.
"""

import dataclasses
import json
import logging
import typing

import app.models
import app.utils
import app.workers.dump.language_detect
import app.workers.dump.phases.editions
import app.workers.dump.runtime
import sqlalchemy

logger = logging.getLogger(__name__)

DEFAULT_WORK_LANGUAGE = "en"
CHUNK_SIZE = 2000

MANUAL = "manual"


def work_language(work: dict) -> str:
    return work.get("description_language") or work.get("title_language") or DEFAULT_WORK_LANGUAGE


@dataclasses.dataclass
class RowPlan:
    work_ol_id: str
    language: str
    book_id: typing.Optional[int]
    title: str
    description: typing.Optional[str]
    first_sentence: typing.Optional[str]
    original_publication_year: typing.Optional[int]
    primary_cover_url: typing.Optional[str]
    isbn: list[str]
    publisher: typing.Optional[str]
    number_of_pages: typing.Optional[int]
    formats: list[str]
    external_ids: dict[str, str]
    open_library_id: typing.Optional[str]
    google_books_id: typing.Optional[str]
    series_name: typing.Optional[str]
    series_position: typing.Optional[float]
    edition_source: str
    previous_title: typing.Optional[str] = None
    previous_slug: typing.Optional[str] = None
    previous_language: typing.Optional[str] = None
    slug: typing.Optional[str] = None


def _manual(existing: typing.Optional[dict]) -> frozenset[str]:
    return frozenset((existing or {}).get("manually_edited_fields") or [])


def _keep_or(existing_value: typing.Optional[str], language: str, new_value: typing.Optional[str]) -> typing.Optional[str]:
    """Existing text stays unless it is recognisably another language; then the new text, if any."""
    if existing_value and existing_value.strip():
        if app.workers.dump.language_detect.fits_language(existing_value, language):
            return existing_value
        return new_value
    return new_value


def plan_row(work: dict, language: str, edition: typing.Optional[dict], neutral: typing.Optional[dict], existing: typing.Optional[dict]) -> RowPlan:
    is_work_language = language == work_language(work)
    manual = _manual(existing)
    ed = edition or {}
    neutral_ed = neutral if is_work_language else None
    nd = neutral_ed or {}

    existing_title = (existing or {}).get("title")
    if "title" in manual and existing_title:
        title = existing_title
    elif is_work_language:
        title = work["title"]
    elif ed.get("title"):
        # A copied original title (the old importer's placeholder) gives way to the edition's own.
        title = ed["title"] if not existing_title or existing_title == work["title"] else existing_title
    else:
        title = existing_title or work["title"]

    description_candidate = ed.get("description")
    if not description_candidate and is_work_language and work.get("description_language") in (None, language):
        description_candidate = work.get("description")
    description = (existing or {}).get("description") if "description" in manual else _keep_or(
        (existing or {}).get("description"), language, description_candidate
    )

    first_sentence_candidate = ed.get("first_sentence")
    if not first_sentence_candidate and is_work_language and app.workers.dump.language_detect.fits_language(work.get("first_sentence"), language):
        first_sentence_candidate = work.get("first_sentence")
    first_sentence = (existing or {}).get("first_sentence") if "first_sentence" in manual else _keep_or(
        (existing or {}).get("first_sentence"), language, first_sentence_candidate
    )

    series = ed.get("series") or nd.get("series") or {}
    physical_format = ed.get("physical_format") or nd.get("physical_format")
    existing_source = (existing or {}).get("edition_source")

    return RowPlan(
        work_ol_id=work["work_ol_id"],
        language=language,
        book_id=(existing or {}).get("book_id"),
        title=title,
        description=description,
        first_sentence=first_sentence,
        original_publication_year=work.get("first_publish_year") or (existing or {}).get("original_publication_year"),
        primary_cover_url=(existing or {}).get("primary_cover_url") or ed.get("cover_url") or nd.get("cover_url") or work.get("cover_url"),
        isbn=((existing or {}).get("isbn") or []) or ed.get("isbns") or nd.get("isbns") or [],
        publisher=(existing or {}).get("publisher") or ed.get("publisher") or nd.get("publisher"),
        number_of_pages=(existing or {}).get("number_of_pages") or ed.get("number_of_pages") or nd.get("number_of_pages"),
        formats=[physical_format] if physical_format else [],
        external_ids={**((existing or {}).get("external_ids") or {}), **(nd.get("external_ids") or {}), **(ed.get("external_ids") or {}), "work_ol_id": work["work_ol_id"]},
        open_library_id=(existing or {}).get("open_library_id") or ed.get("open_library_id") or nd.get("open_library_id") or work["work_ol_id"],
        google_books_id=(existing or {}).get("google_books_id") or ed.get("google_books_id") or nd.get("google_books_id"),
        series_name=series.get("name"),
        series_position=series.get("position"),
        edition_source=MANUAL if existing_source == MANUAL else ("edition" if edition else "work"),
        previous_title=existing_title,
        previous_slug=(existing or {}).get("slug"),
        previous_language=(existing or {}).get("relabelled_from") or (existing or {}).get("language"),
    )


def _relabel_placeholder(work: dict, editions: dict[str, dict], existing_rows: dict[str, dict]) -> dict[str, dict]:
    """The old importer filed every work under `en`. When the work is recognisably in
    another language, nothing in English backs that row, and no row of the real language
    exists yet, the `en` row is that work's row with the wrong label: move it, keeping
    its book_id so the readers' shelves, ratings and comments follow."""
    language = work_language(work)
    placeholder = existing_rows.get(DEFAULT_WORK_LANGUAGE)
    if (
        language == DEFAULT_WORK_LANGUAGE
        or placeholder is None
        or language in existing_rows
        or DEFAULT_WORK_LANGUAGE in editions
        or placeholder.get("edition_source") != "legacy"
        or "language" in _manual(placeholder)
    ):
        return existing_rows
    relabeled = {key: row for key, row in existing_rows.items() if key != DEFAULT_WORK_LANGUAGE}
    relabeled[language] = {**placeholder, "language": language, "relabelled_from": DEFAULT_WORK_LANGUAGE}
    return relabeled


def plan_work(work: dict, editions: dict[str, dict], existing_rows: dict[str, dict]) -> list[RowPlan]:
    existing_rows = _relabel_placeholder(work, editions, existing_rows)
    languages = {language for language in editions if language != app.workers.dump.phases.editions.UNKNOWN_LANGUAGE}
    languages.add(work_language(work))
    languages.update(language for language, row in existing_rows.items() if row.get("relabelled_from"))
    neutral = editions.get(app.workers.dump.phases.editions.UNKNOWN_LANGUAGE)
    return [
        plan_row(work, language, editions.get(language), neutral, existing_rows.get(language))
        for language in sorted(languages)
    ]


def stale_text_book_ids(existing_rows: dict[str, dict], planned_languages: set[str]) -> dict[str, list[int]]:
    """Rows the import has no data for, whose text is recognisably another language.

    These are the rows the old importer filled by copying the English text: an Italian
    row that shows an English blurb. The text is not moved anywhere (the English row
    has it); it is removed so the page falls back to a labelled sibling description.
    """
    stale: dict[str, list[int]] = {"description": [], "first_sentence": []}
    for language, row in existing_rows.items():
        if language in planned_languages or row.get("relabelled_from"):
            continue
        manual = _manual(row)
        for column in stale:
            text = row.get(column)
            if column not in manual and text and not app.workers.dump.language_detect.fits_language(text, language):
                stale[column].append(row["book_id"])
    return stale


def assign_slugs(plans: list[RowPlan], taken: set[tuple[str, str]]) -> None:
    """Give every plan a slug unique within its language.

    `taken` holds the (language, slug) pairs already used by other rows; it is
    extended as slugs are handed out. An existing row keeps its slug unless the
    slug followed a title that has since changed.
    """
    for plan in plans:
        if plan.book_id and plan.previous_slug:
            slug_followed_title = plan.previous_slug == app.utils.slugify(plan.previous_title or "")
            relabelled = plan.previous_language != plan.language
            if (plan.title == plan.previous_title or not slug_followed_title) and not (
                relabelled and (plan.language, plan.previous_slug) in taken
            ):
                plan.slug = plan.previous_slug
                continue
        base = app.utils.slugify(plan.title) or plan.work_ol_id.lower()
        slug = base
        if (plan.language, slug) in taken:
            slug = f"{base}-{plan.work_ol_id.lower()}"[:600]
        taken.add((plan.language, slug))
        plan.slug = slug


_FETCH_STAGED_SQL = sqlalchemy.text(
    "SELECT work_ol_id, title, title_language, description, description_language, first_sentence, "
    "first_publish_year, cover_url, author_ol_ids, genres FROM books.work_staging "
    "WHERE work_ol_id > :after ORDER BY work_ol_id LIMIT :limit"
)
_FETCH_EDITIONS_SQL = sqlalchemy.text(
    "SELECT work_ol_id, language, payload FROM books.edition_staging WHERE work_ol_id = ANY(:ids)"
)
_FETCH_EXISTING_SQL = sqlalchemy.text(
    """
    SELECT book_id, work_id, language, slug, title, description, first_sentence, edition_source,
           manually_edited_fields, original_publication_year, primary_cover_url, isbn, publisher,
           number_of_pages, external_ids, open_library_id, google_books_id
    FROM books.books WHERE work_id = ANY(:ids) OR external_ids->>'work_ol_id' = ANY(:ids)
    """
)
# A row filed under a title slug or a Google Books id (no OpenLibrary work id) joins
# its OpenLibrary work, so its readers' figures pool with the rest of the work. A
# row is skipped when the work already has a row in that language under the proper
# id: the unique (work_id, language) index would refuse it.
_ADOPT_WORK_ID_SQL = sqlalchemy.text(
    """
    UPDATE books.books b SET work_id = x.work_ol_id
    FROM unnest(CAST(:book_ids AS bigint[]), CAST(:work_ol_ids AS text[])) AS x(book_id, work_ol_id)
    WHERE b.book_id = x.book_id
      AND NOT EXISTS (SELECT 1 FROM books.books o WHERE o.work_id = x.work_ol_id AND o.language = b.language)
    RETURNING b.book_id
    """
)
_CLEAR_DESCRIPTION_SQL = sqlalchemy.text(
    "UPDATE books.books SET description = NULL, enrichment_attempted_at = NULL WHERE book_id = ANY(:book_ids)"
)
_CLEAR_FIRST_SENTENCE_SQL = sqlalchemy.text("UPDATE books.books SET first_sentence = NULL WHERE book_id = ANY(:book_ids)")
_FETCH_AUTHORS_SQL = sqlalchemy.text(
    "SELECT open_library_id, author_id FROM books.authors WHERE open_library_id = ANY(:ids)"
)
_FETCH_SLUGS_SQL = sqlalchemy.text("SELECT language, slug FROM books.books WHERE slug = ANY(:slugs)")

_UPDATE_SQL = sqlalchemy.text(
    """
    UPDATE books.books SET
        language = :language, title = :title, slug = :slug, description = :description, first_sentence = :first_sentence,
        original_publication_year = :year, primary_cover_url = :cover, isbn = CAST(:isbn AS jsonb),
        publisher = :publisher, number_of_pages = :pages,
        formats = CASE WHEN formats @> CAST(:formats AS jsonb) THEN formats ELSE formats || CAST(:formats AS jsonb) END,
        external_ids = CAST(:external_ids AS jsonb), open_library_id = :open_library_id,
        google_books_id = :google_books_id,
        series_slug = COALESCE(:series_slug, series_slug), series_name = COALESCE(:series_name, series_name),
        series_position = COALESCE(series_position, :series_position),
        edition_source = :edition_source
    WHERE book_id = :book_id
    """
)
_LINK_AUTHORS_SQL = sqlalchemy.text(
    """
    WITH desired(book_id, author_id) AS (
        SELECT * FROM unnest(CAST(:book_ids AS bigint[]), CAST(:author_ids AS bigint[]))
    ),
    removed AS (
        DELETE FROM books.book_authors ba
        USING (SELECT DISTINCT book_id FROM desired) d
        WHERE ba.book_id = d.book_id
          AND NOT EXISTS (SELECT 1 FROM desired x WHERE x.book_id = ba.book_id AND x.author_id = ba.author_id)
    )
    INSERT INTO books.book_authors (book_id, author_id) SELECT book_id, author_id FROM desired
    ON CONFLICT DO NOTHING
    """
)
_UPSERT_GENRES_SQL = sqlalchemy.text(
    "INSERT INTO books.genres (name, slug) VALUES (:name, :slug) ON CONFLICT (slug) DO NOTHING"
)
_FETCH_GENRES_SQL = sqlalchemy.text("SELECT slug, genre_id FROM books.genres WHERE slug = ANY(:slugs)")
_LINK_GENRES_SQL = sqlalchemy.text(
    """
    INSERT INTO books.book_genres (book_id, genre_id)
    SELECT * FROM unnest(CAST(:book_ids AS bigint[]), CAST(:genre_ids AS bigint[]))
    ON CONFLICT DO NOTHING
    """
)
_RECORD_SLUG_CHANGE_SQL = sqlalchemy.text(
    """
    INSERT INTO books.slug_history (entity_type, language, old_slug, entity_id)
    VALUES ('book', :language, :old_slug, :book_id) ON CONFLICT DO NOTHING
    """
)


def _json(value: typing.Any) -> typing.Any:
    return json.loads(value) if isinstance(value, str) else value


async def _existing_by_work(session, ids: list[str]) -> dict[str, dict[str, dict]]:
    by_work: dict[str, dict[str, dict]] = {}
    for row in (await session.execute(_FETCH_EXISTING_SQL, {"ids": ids})).mappings():
        existing = dict(row)
        existing["isbn"] = _json(existing["isbn"]) or []
        existing["external_ids"] = _json(existing["external_ids"]) or {}
        work_ol_id = existing["external_ids"].get("work_ol_id") or existing["work_id"]
        by_work.setdefault(work_ol_id, {})[existing["language"]] = existing
    return by_work


async def _adopt_openlibrary_work_ids(session, existing_by_work: dict[str, dict[str, dict]]) -> None:
    pending = [
        (row["book_id"], work_ol_id)
        for work_ol_id, rows in existing_by_work.items()
        for row in rows.values()
        if row["work_id"] != work_ol_id
    ]
    if not pending:
        return
    adopted = {
        row.book_id
        for row in await session.execute(
            _ADOPT_WORK_ID_SQL,
            {"book_ids": [book_id for book_id, _ in pending], "work_ol_ids": [work for _, work in pending]},
        )
    }
    for work_ol_id, rows in existing_by_work.items():
        for row in rows.values():
            if row["book_id"] in adopted:
                row["work_id"] = work_ol_id


async def _merge_chunk(session, staged: list[dict]) -> dict[str, int]:
    ids = [work["work_ol_id"] for work in staged]
    editions_by_work: dict[str, dict[str, dict]] = {}
    for row in (await session.execute(_FETCH_EDITIONS_SQL, {"ids": ids})).mappings():
        editions_by_work.setdefault(row["work_ol_id"], {})[row["language"]] = _json(row["payload"])
    existing_by_work = await _existing_by_work(session, ids)
    await _adopt_openlibrary_work_ids(session, existing_by_work)

    author_ol_ids = sorted({ol for work in staged for ol in _json(work["author_ol_ids"])})
    author_ids = {
        row.open_library_id: row.author_id
        for row in await session.execute(_FETCH_AUTHORS_SQL, {"ids": author_ol_ids})
    }

    stale = {"description": [], "first_sentence": []}
    plans_by_work: dict[str, list[RowPlan]] = {}
    for work in staged:
        resolved = [author_ids[ol] for ol in _json(work["author_ol_ids"]) if ol in author_ids]
        if not resolved:
            continue
        work["resolved_author_ids"] = resolved
        editions = editions_by_work.get(work["work_ol_id"], {})
        existing = _relabel_placeholder(work, editions, existing_by_work.get(work["work_ol_id"], {}))
        plans = plan_work(work, editions, existing)
        plans_by_work[work["work_ol_id"]] = plans
        for column, book_ids in stale_text_book_ids(existing, {plan.language for plan in plans}).items():
            stale[column].extend(book_ids)

    candidate_slugs = sorted(
        {app.utils.slugify(plan.title) for plans in plans_by_work.values() for plan in plans}
        | {plan.previous_slug for plans in plans_by_work.values() for plan in plans if plan.previous_slug}
    )
    taken = {
        (row.language, row.slug)
        for row in await session.execute(_FETCH_SLUGS_SQL, {"slugs": candidate_slugs})
    }
    for plans in plans_by_work.values():
        assign_slugs(plans, taken)

    updates, inserts, slug_changes = [], [], []
    for plans in plans_by_work.values():
        for plan in plans:
            series_slug = app.utils.slugify(plan.series_name)[:550] if plan.series_name else None
            values = {
                "language": plan.language, "title": plan.title, "slug": plan.slug, "description": plan.description,
                "first_sentence": plan.first_sentence, "year": plan.original_publication_year,
                "cover": (plan.primary_cover_url or None) and plan.primary_cover_url[:1000],
                "isbn": json.dumps(plan.isbn[:20]), "publisher": plan.publisher, "pages": plan.number_of_pages,
                "formats": json.dumps(plan.formats), "external_ids": json.dumps(plan.external_ids),
                "open_library_id": plan.open_library_id and plan.open_library_id[:100],
                "google_books_id": plan.google_books_id and plan.google_books_id[:100],
                "series_slug": series_slug, "series_name": plan.series_name and plan.series_name[:500],
                "series_position": app.utils.clamp_series_position(plan.series_position),
                "edition_source": plan.edition_source,
            }
            if plan.book_id:
                updates.append({**values, "book_id": plan.book_id})
                if plan.previous_slug and (plan.previous_slug != plan.slug or plan.previous_language != plan.language):
                    slug_changes.append(
                        {"language": plan.previous_language or plan.language, "old_slug": plan.previous_slug, "book_id": plan.book_id}
                    )
            else:
                inserts.append((plan, values))

    if stale["description"]:
        await session.execute(_CLEAR_DESCRIPTION_SQL, {"book_ids": stale["description"]})
    if stale["first_sentence"]:
        await session.execute(_CLEAR_FIRST_SENTENCE_SQL, {"book_ids": stale["first_sentence"]})
    if updates:
        await session.execute(_UPDATE_SQL, updates)
    if slug_changes:
        await session.execute(_RECORD_SLUG_CHANGE_SQL, slug_changes)

    book_ids_by_work: dict[str, list[int]] = {
        work_ol_id: [plan.book_id for plan in plans if plan.book_id] for work_ol_id, plans in plans_by_work.items()
    }
    if inserts:
        statement = sqlalchemy.insert(app.models.Book).returning(
            app.models.Book.book_id, app.models.Book.work_id, app.models.Book.language
        )
        rows = [
            {
                "title": values["title"], "language": plan.language, "slug": values["slug"], "work_id": plan.work_ol_id,
                "description": values["description"], "first_sentence": values["first_sentence"],
                "original_publication_year": values["year"], "primary_cover_url": values["cover"],
                "isbn": plan.isbn[:20], "publisher": values["publisher"], "number_of_pages": values["pages"],
                "formats": plan.formats, "external_ids": plan.external_ids, "open_library_id": values["open_library_id"],
                "google_books_id": values["google_books_id"], "series_slug": values["series_slug"],
                "series_name": values["series_name"], "series_position": values["series_position"],
                "edition_source": values["edition_source"],
            }
            for plan, values in inserts
        ]
        for created in (await session.execute(statement, rows)).all():
            book_ids_by_work[created.work_id].append(created.book_id)

    await _link_authors_and_genres(session, staged, book_ids_by_work)
    return {"updated": len(updates), "inserted": len(inserts), "slug_changes": len(slug_changes)}


async def _link_authors_and_genres(session, staged: list[dict], book_ids_by_work: dict[str, list[int]]) -> None:
    author_book_ids: list[int] = []
    author_ids: list[int] = []
    genre_pairs: list[tuple[int, str]] = []
    genre_names: dict[str, str] = {}
    for work in staged:
        book_ids = book_ids_by_work.get(work["work_ol_id"])
        if not book_ids:
            continue
        for book_id in book_ids:
            for author_id in work["resolved_author_ids"]:
                author_book_ids.append(book_id)
                author_ids.append(author_id)
            for genre in _json(work["genres"]):
                genre_pairs.append((book_id, genre["slug"]))
                genre_names[genre["slug"]] = genre["name"]

    if author_ids:
        await session.execute(_LINK_AUTHORS_SQL, {"book_ids": author_book_ids, "author_ids": author_ids})

    if genre_names:
        await session.execute(_UPSERT_GENRES_SQL, [{"name": name[:100], "slug": slug[:150]} for slug, name in genre_names.items()])
        genre_ids = {
            row.slug: row.genre_id
            for row in await session.execute(_FETCH_GENRES_SQL, {"slugs": list(genre_names)})
        }
        linked = [(book_id, genre_ids[slug]) for book_id, slug in genre_pairs if slug in genre_ids]
        if linked:
            await session.execute(
                _LINK_GENRES_SQL,
                {"book_ids": [book_id for book_id, _ in linked], "genre_ids": [genre_id for _, genre_id in linked]},
            )


async def merge_staging_into_books() -> dict[str, int]:
    """Apply every staged work. Idempotent: a second run over the same dump changes nothing."""
    totals = {"works": 0, "updated": 0, "inserted": 0, "slug_changes": 0}
    after = ""
    session = await app.workers.dump.runtime.open_session()
    try:
        while True:
            staged = [dict(row) for row in (await session.execute(_FETCH_STAGED_SQL, {"after": after, "limit": CHUNK_SIZE})).mappings()]
            if not staged:
                break
            after = staged[-1]["work_ol_id"]
            counts = await _merge_chunk(session, staged)
            await session.commit()
            totals["works"] += len(staged)
            for key, value in counts.items():
                totals[key] += value
            if totals["works"] % (CHUNK_SIZE * 10) == 0:
                logger.info(f"[dump] Merged {totals['works']} works: {totals}")
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
    logger.info(f"[dump] Merge complete: {totals}")
    return totals
