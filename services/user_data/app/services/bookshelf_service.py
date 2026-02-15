import typing
import sqlalchemy
import sqlalchemy.ext.asyncio
import sqlalchemy.dialects.postgresql
import app.models.bookshelf


_BOOKSHELF_SORT_COLUMNS: typing.Dict[str, typing.Any] = {
    "created_at": app.models.bookshelf.Bookshelf.created_at,
    "updated_at": app.models.bookshelf.Bookshelf.updated_at,
}

_VALID_STATUSES = {"want_to_read", "reading", "read", "abandoned"}


async def upsert_bookshelf(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    status: str
) -> app.models.bookshelf.Bookshelf:
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid_status")

    stmt = sqlalchemy.dialects.postgresql.insert(app.models.bookshelf.Bookshelf).values(
        user_id=user_id,
        book_id=book_id,
        status=status
    ).on_conflict_do_update(
        constraint="uq_bookshelves_user_book",
        set_={
            "status": status,
            "updated_at": sqlalchemy.func.now()
        }
    ).returning(app.models.bookshelf.Bookshelf)

    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


async def delete_bookshelf(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int
) -> None:
    stmt = sqlalchemy.delete(app.models.bookshelf.Bookshelf).where(
        app.models.bookshelf.Bookshelf.user_id == user_id,
        app.models.bookshelf.Bookshelf.book_id == book_id
    ).returning(app.models.bookshelf.Bookshelf.bookshelf_id)

    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise ValueError("not_found")
    await session.commit()


async def get_bookshelf(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int
) -> typing.Optional[app.models.bookshelf.Bookshelf]:
    stmt = sqlalchemy.select(app.models.bookshelf.Bookshelf).where(
        app.models.bookshelf.Bookshelf.user_id == user_id,
        app.models.bookshelf.Bookshelf.book_id == book_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_bookshelves(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    limit: int,
    offset: int,
    status_filter: str,
    favourites_only: bool,
    sort_by: str,
    order: str
) -> typing.Tuple[typing.List[app.models.bookshelf.Bookshelf], int]:
    sort_col = _BOOKSHELF_SORT_COLUMNS.get(sort_by, app.models.bookshelf.Bookshelf.created_at)
    order_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    base_conditions = [app.models.bookshelf.Bookshelf.user_id == user_id]
    if status_filter:
        base_conditions.append(app.models.bookshelf.Bookshelf.status == status_filter)
    if favourites_only:
        base_conditions.append(app.models.bookshelf.Bookshelf.is_favorite == True)

    count_stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(
        app.models.bookshelf.Bookshelf
    ).where(*base_conditions)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    stmt = sqlalchemy.select(app.models.bookshelf.Bookshelf).where(
        *base_conditions
    ).order_by(order_expr).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all(), total_count


async def toggle_favourite(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    is_favorite: bool
) -> app.models.bookshelf.Bookshelf:
    stmt = sqlalchemy.dialects.postgresql.insert(app.models.bookshelf.Bookshelf).values(
        user_id=user_id,
        book_id=book_id,
        status="want_to_read",
        is_favorite=is_favorite
    ).on_conflict_do_update(
        constraint="uq_bookshelves_user_book",
        set_={
            "is_favorite": is_favorite,
            "updated_at": sqlalchemy.func.now()
        }
    ).returning(app.models.bookshelf.Bookshelf)

    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()
