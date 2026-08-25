import typing

import app.models.bookshelf
import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.ext.asyncio

_BOOKSHELF_SORT_COLUMNS: typing.Dict[str, typing.Any] = {
    "created_at": app.models.bookshelf.Bookshelf.created_at,
    "updated_at": app.models.bookshelf.Bookshelf.updated_at,
}

_VALID_STATUSES = {"want_to_read", "reading", "read", "abandoned"}


async def _move_sibling_edition_shelf_entry(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
) -> None:
    """Move this user's bookshelf row from another edition of the same work onto this one.

    `uq_bookshelves_user_book` is keyed on (user_id, book_id), which is per-edition —
    shelving two language editions of the same work would otherwise create two rows,
    double-counting the user in work-level stats and personal shelf counts.

    The sibling row is re-pointed rather than deleted so status, is_favorite and the
    started_at/finished_at reading history survive the move: a reader who finished the
    Polish edition and then favourites the English one must not silently lose the
    'read' status and its finish date. Only when a row already exists for this edition
    (nothing to preserve into) are leftover siblings dropped.
    """
    params = {"user_id": user_id, "book_id": book_id}

    await session.execute(
        sqlalchemy.text(
            """
            UPDATE user_data.bookshelves
            SET book_id = :book_id, updated_at = now()
            -- user_id is repeated here purely so the planner can prune to the
            -- one hash partition instead of touching all four.
            WHERE user_id = :user_id
            AND bookshelf_id = (
                SELECT bsh.bookshelf_id
                FROM user_data.bookshelves bsh
                JOIN books.books b ON b.book_id = bsh.book_id
                WHERE bsh.user_id = :user_id
                  AND bsh.book_id != :book_id
                  AND b.work_id = (SELECT work_id FROM books.books WHERE book_id = :book_id)
                ORDER BY bsh.updated_at DESC
                LIMIT 1
            )
            AND NOT EXISTS (
                SELECT 1 FROM user_data.bookshelves existing
                WHERE existing.user_id = :user_id AND existing.book_id = :book_id
            )
            """
        ),
        params,
    )

    await session.execute(
        sqlalchemy.text(
            """
            DELETE FROM user_data.bookshelves
            WHERE user_id = :user_id
              AND book_id != :book_id
              AND book_id IN (
                  SELECT b.book_id FROM books.books b
                  WHERE b.work_id = (SELECT work_id FROM books.books WHERE book_id = :book_id)
              )
            """
        ),
        params,
    )


async def upsert_bookshelf(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    status: str,
) -> app.models.bookshelf.Bookshelf:
    if status not in _VALID_STATUSES:
        raise ValueError("invalid_status")

    await _move_sibling_edition_shelf_entry(session, user_id, book_id)

    insert_stmt = sqlalchemy.dialects.postgresql.insert(app.models.bookshelf.Bookshelf)

    stmt = (
        insert_stmt.values(
            user_id=user_id,
            book_id=book_id,
            status=status,
            finished_at=sqlalchemy.func.now() if status == "read" else None,
            started_at=sqlalchemy.func.now() if status == "reading" else None,
        )
        .on_conflict_do_update(
            constraint="uq_bookshelves_user_book",
            set_={
                "status": status,
                "updated_at": sqlalchemy.func.now(),
                "finished_at": sqlalchemy.case(
                    (
                        sqlalchemy.and_(
                            insert_stmt.excluded.status == "read",
                            app.models.bookshelf.Bookshelf.status != "read",
                        ),
                        sqlalchemy.func.now(),
                    ),
                    (insert_stmt.excluded.status == "read", app.models.bookshelf.Bookshelf.finished_at),
                    else_=None,
                ),
                "started_at": sqlalchemy.case(
                    (
                        sqlalchemy.and_(
                            insert_stmt.excluded.status == "reading",
                            app.models.bookshelf.Bookshelf.status != "reading",
                        ),
                        sqlalchemy.func.now(),
                    ),
                    else_=app.models.bookshelf.Bookshelf.started_at,
                ),
            },
        )
        .returning(app.models.bookshelf.Bookshelf)
    )

    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


async def delete_bookshelf(
    session: sqlalchemy.ext.asyncio.AsyncSession, user_id: int, book_id: int
) -> None:
    """Take the work the given edition belongs to off this reader's shelf.

    Shelving is per-edition but every read path resolves it per-work, so a row
    created against one translation has to be removable from the page of
    another — otherwise the shelf entry the reader is looking at cannot be
    deleted from where they are standing.
    """
    result = await session.execute(
        sqlalchemy.text(
            """
            DELETE FROM user_data.bookshelves
            WHERE user_id = :user_id
              AND book_id IN (
                  SELECT b.book_id FROM books.books b
                  WHERE b.work_id = (SELECT work_id FROM books.books WHERE book_id = :book_id)
              )
            RETURNING bookshelf_id
            """
        ),
        {"user_id": user_id, "book_id": book_id},
    )
    if not result.fetchall():
        raise ValueError("not_found")
    await session.commit()


async def get_bookshelf(
    session: sqlalchemy.ext.asyncio.AsyncSession, user_id: int, book_id: int
) -> app.models.bookshelf.Bookshelf:
    stmt = sqlalchemy.select(app.models.bookshelf.Bookshelf).where(
        app.models.bookshelf.Bookshelf.user_id == user_id,
        app.models.bookshelf.Bookshelf.book_id == book_id,
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise ValueError("not_found")
    return row


async def get_user_bookshelves(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    limit: int,
    offset: int,
    status_filter: str,
    favourites_only: bool,
    sort_by: str,
    order: str,
) -> typing.Tuple[typing.List[app.models.bookshelf.Bookshelf], int]:
    sort_col = _BOOKSHELF_SORT_COLUMNS.get(
        sort_by, app.models.bookshelf.Bookshelf.created_at
    )
    order_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    base_conditions = [app.models.bookshelf.Bookshelf.user_id == user_id]
    if status_filter:
        base_conditions.append(app.models.bookshelf.Bookshelf.status == status_filter)
    if favourites_only:
        base_conditions.append(app.models.bookshelf.Bookshelf.is_favorite == True)

    count_stmt = (
        sqlalchemy.select(sqlalchemy.func.count())
        .select_from(app.models.bookshelf.Bookshelf)
        .where(*base_conditions)
    )
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    stmt = (
        sqlalchemy.select(app.models.bookshelf.Bookshelf)
        .where(*base_conditions)
        .order_by(order_expr)
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(stmt)
    return result.scalars().all(), total_count


async def toggle_favourite(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    is_favorite: bool,
) -> app.models.bookshelf.Bookshelf:
    await _move_sibling_edition_shelf_entry(session, user_id, book_id)

    stmt = (
        sqlalchemy.dialects.postgresql.insert(app.models.bookshelf.Bookshelf)
        .values(
            user_id=user_id,
            book_id=book_id,
            status="want_to_read",
            is_favorite=is_favorite,
        )
        .on_conflict_do_update(
            constraint="uq_bookshelves_user_book",
            set_={"is_favorite": is_favorite, "updated_at": sqlalchemy.func.now()},
        )
        .returning(app.models.bookshelf.Bookshelf)
    )

    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


async def delete_user_bookshelves(
    session: sqlalchemy.ext.asyncio.AsyncSession, user_id: int
) -> None:
    await session.execute(
        sqlalchemy.delete(app.models.bookshelf.Bookshelf).where(
            app.models.bookshelf.Bookshelf.user_id == user_id
        )
    )
