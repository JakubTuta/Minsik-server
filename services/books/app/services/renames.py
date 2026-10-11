import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

_RECORD_OLD_SLUG_SQL = sqlalchemy.text(
    """
    INSERT INTO books.slug_history (entity_type, language, old_slug, entity_id)
    VALUES (:entity_type, :language, :old_slug, :entity_id)
    ON CONFLICT (entity_type, language, old_slug) DO UPDATE SET entity_id = EXCLUDED.entity_id
    """
)
_FORGET_RECLAIMED_SLUG_SQL = sqlalchemy.text(
    "DELETE FROM books.slug_history "
    "WHERE entity_type = :entity_type AND language = :language AND old_slug = :slug"
)
_RENAME_SERIES_ON_BOOKS_SQL = sqlalchemy.text(
    """
    UPDATE books.books SET series_slug = :slug, series_name = :name
    WHERE series_id = :series_id
      AND (series_slug IS DISTINCT FROM :slug OR series_name IS DISTINCT FROM :name)
    """
)
# Setting updated_at explicitly is what marks the rows as changed for the Elasticsearch
# sync and the sitemap: the trigger honours an explicit touch.
_TOUCH_AUTHOR_BOOKS_SQL = sqlalchemy.text(
    """
    UPDATE books.books SET updated_at = NOW()
    WHERE book_id IN (SELECT book_id FROM books.book_authors WHERE author_id = :author_id)
    """
)


async def record_slug_change(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    entity_type: str,
    entity_id: int,
    old_slug: typing.Optional[str],
    new_slug: typing.Optional[str],
    language: str = "",
) -> None:
    """Keep links to the previous slug working: it resolves through slug_history to the entity."""
    if not old_slug or not new_slug or old_slug == new_slug:
        return

    await session.execute(
        _RECORD_OLD_SLUG_SQL,
        {"entity_type": entity_type, "language": language, "old_slug": old_slug, "entity_id": entity_id},
    )
    await session.execute(
        _FORGET_RECLAIMED_SLUG_SQL,
        {"entity_type": entity_type, "language": language, "slug": new_slug},
    )


async def propagate_series_rename(
    session: sqlalchemy.ext.asyncio.AsyncSession, series_id: int, slug: str, name: str
) -> None:
    """Books carry a copy of their series' slug and name; a rename has to reach them."""
    await session.execute(
        _RENAME_SERIES_ON_BOOKS_SQL, {"series_id": series_id, "slug": slug, "name": name}
    )


async def propagate_author_rename(session: sqlalchemy.ext.asyncio.AsyncSession, author_id: int) -> None:
    """Search documents of an author's books hold the author's name; mark them for re-sync."""
    await session.execute(_TOUCH_AUTHOR_BOOKS_SQL, {"author_id": author_id})
