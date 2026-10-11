"""Author upsert shared by the OpenLibrary dump import and the continuous fetchers.

An author is identified by its OpenLibrary id when it has one, never by its name:
two different people called "John Smith" are two rows. Authors without an id
(Google Books) can only be matched by name. Existing values win over incoming ones
(fill-if-empty), and a field an admin edited is never touched.
"""

import json
import typing

import app.utils
import sqlalchemy

_MAX_ALTERNATE_NAMES = 30
_FREE = object()

_FILL_IF_EMPTY_COLUMNS = ("bio", "birth_date", "death_date", "photo_url", "wikidata_id", "wikipedia_url")


def _fill_if_empty(column: str) -> str:
    return (
        f"{column} = CASE WHEN '{column}' = ANY(authors.manually_edited_fields) THEN authors.{column} "
        f"ELSE COALESCE(authors.{column}, EXCLUDED.{column}) END"
    )


_CONFLICT_UPDATE = ",\n        ".join(
    [_fill_if_empty(column) for column in _FILL_IF_EMPTY_COLUMNS]
    + [
        "remote_ids = authors.remote_ids || EXCLUDED.remote_ids",
        f"""alternate_names = (
            SELECT COALESCE(jsonb_agg(name), '[]'::jsonb) FROM (
                SELECT DISTINCT name FROM jsonb_array_elements(authors.alternate_names || EXCLUDED.alternate_names) AS t(name)
                LIMIT {_MAX_ALTERNATE_NAMES}
            ) merged
        )""",
    ]
)

_INSERT_PREFIX = """
    INSERT INTO books.authors (
        name, slug, bio, birth_date, death_date, photo_url, open_library_id,
        wikidata_id, wikipedia_url, remote_ids, alternate_names
    ) VALUES (
        :name, :slug, :bio, :birth_date, :death_date, :photo_url, :open_library_id,
        :wikidata_id, :wikipedia_url, CAST(:remote_ids AS jsonb), CAST(:alternate_names AS jsonb)
    )
"""
_UPSERT_BY_OPENLIBRARY_ID_SQL = sqlalchemy.text(
    _INSERT_PREFIX + f"ON CONFLICT (open_library_id) WHERE open_library_id IS NOT NULL DO UPDATE SET\n        {_CONFLICT_UPDATE}"
)
_UPSERT_BY_SLUG_SQL = sqlalchemy.text(_INSERT_PREFIX + f"ON CONFLICT (slug) DO UPDATE SET\n        {_CONFLICT_UPDATE}")
_FETCH_SLUG_OWNERS_SQL = sqlalchemy.text("SELECT slug, open_library_id FROM books.authors WHERE slug = ANY(:slugs)")
_ADOPT_SQL = sqlalchemy.text(
    """
    UPDATE books.authors SET open_library_id = :open_library_id
    WHERE slug = :slug AND open_library_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM books.authors x WHERE x.open_library_id = :open_library_id)
    """
)
_FETCH_IDS_BY_OPENLIBRARY_ID_SQL = sqlalchemy.text(
    "SELECT open_library_id AS key, author_id FROM books.authors WHERE open_library_id = ANY(:keys)"
)
_FETCH_IDS_BY_SLUG_SQL = sqlalchemy.text("SELECT slug AS key, author_id FROM books.authors WHERE slug = ANY(:keys)")


def author_key(author: dict) -> str:
    """The key `upsert_authors` returns this author's id under."""
    return author.get("open_library_id") or app.utils.slugify(author.get("name") or "")


def assign_slugs(entries: list[dict], owners: dict[str, typing.Optional[str]]) -> list[dict]:
    """Slug per author, unique across the table.

    `owners` maps a slug already in the table to the OpenLibrary id of the author
    holding it (None for an author that has no id yet). The first holder keeps the
    plain slug; a different person with the same name gets their OpenLibrary id
    appended. Mutates `owners` so authors later in the same batch see the claims.
    """
    resolved: list[dict] = []
    for entry in entries:
        slug = entry["base_slug"]
        ol_id = entry["open_library_id"]
        holder = owners.get(slug, _FREE)
        if holder is _FREE or holder is None:
            owners[slug] = ol_id
        elif holder != ol_id:
            slug = f"{slug}-{ol_id.lower()}"[:350]
            owners.setdefault(slug, ol_id)
        resolved.append({**entry, "slug": slug})
    return resolved


def _row(entry: dict) -> dict:
    return {
        "name": entry["name"],
        "slug": entry["slug"],
        "bio": entry.get("bio"),
        "birth_date": entry.get("birth_date"),
        "death_date": entry.get("death_date"),
        "photo_url": entry.get("photo_url"),
        "open_library_id": entry.get("open_library_id"),
        "wikidata_id": entry.get("wikidata_id"),
        "wikipedia_url": entry.get("wikipedia_url"),
        "remote_ids": json.dumps(entry.get("remote_ids") or {}),
        "alternate_names": json.dumps(entry.get("alternate_names") or []),
    }


async def upsert_authors(session, authors: list[dict]) -> dict[str, int]:
    """Create or update authors and return `{author_key: author_id}` for all of them.

    Each entry needs `name`; `open_library_id` is optional but is the identity when present.
    """
    entries = [{**author, "base_slug": app.utils.slugify(author["name"])} for author in authors if author.get("name")]
    entries = [entry for entry in entries if entry["base_slug"]]
    with_id = [entry for entry in entries if entry.get("open_library_id")]
    without_id = [{**entry, "slug": entry["base_slug"]} for entry in entries if not entry.get("open_library_id")]

    if with_id:
        owners = {
            row.slug: row.open_library_id
            for row in await session.execute(_FETCH_SLUG_OWNERS_SQL, {"slugs": sorted({e["base_slug"] for e in with_id})})
        }
        adoptions = [
            {"slug": entry["base_slug"], "open_library_id": entry["open_library_id"]}
            for entry in with_id
            if owners.get(entry["base_slug"], _FREE) is None
        ]
        if adoptions:
            await session.execute(_ADOPT_SQL, adoptions)
        await session.execute(_UPSERT_BY_OPENLIBRARY_ID_SQL, [_row(e) for e in assign_slugs(with_id, owners)])
    if without_id:
        unique_by_slug = list({entry["slug"]: entry for entry in without_id}.values())
        await session.execute(_UPSERT_BY_SLUG_SQL, [_row(entry) for entry in unique_by_slug])

    ids: dict[str, int] = {}
    if with_id:
        keys = sorted({entry["open_library_id"] for entry in with_id})
        ids.update({row.key: row.author_id for row in await session.execute(_FETCH_IDS_BY_OPENLIBRARY_ID_SQL, {"keys": keys})})
    if without_id:
        keys = sorted({entry["slug"] for entry in without_id})
        ids.update({row.key: row.author_id for row in await session.execute(_FETCH_IDS_BY_SLUG_SQL, {"keys": keys})})
    return ids
