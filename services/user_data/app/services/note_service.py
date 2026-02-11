import typing
import sqlalchemy
import sqlalchemy.ext.asyncio
import app.models.note


_NOTE_SORT_COLUMNS: typing.Dict[str, typing.Any] = {
    "created_at": app.models.note.Note.created_at,
}


async def create_note(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    note_text: str,
    page_number: typing.Optional[int],
    is_spoiler: bool
) -> app.models.note.Note:
    row = app.models.note.Note(
        user_id=user_id,
        book_id=book_id,
        note_text=note_text,
        page_number=page_number,
        is_spoiler=is_spoiler
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_note(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    note_id: int,
    user_id: int,
    note_text: str,
    page_number: typing.Optional[int],
    is_spoiler: bool
) -> app.models.note.Note:
    stmt = sqlalchemy.select(app.models.note.Note).where(
        app.models.note.Note.note_id == note_id,
        app.models.note.Note.user_id == user_id
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise ValueError("not_found")

    row.note_text = note_text
    row.page_number = page_number
    row.is_spoiler = is_spoiler
    await session.commit()
    await session.refresh(row)
    return row


async def delete_note(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    note_id: int,
    user_id: int
) -> None:
    stmt = sqlalchemy.delete(app.models.note.Note).where(
        app.models.note.Note.note_id == note_id,
        app.models.note.Note.user_id == user_id
    ).returning(app.models.note.Note.note_id)

    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise ValueError("not_found")
    await session.commit()


async def get_book_notes(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    limit: int,
    offset: int,
    sort_by: str,
    order: str
) -> typing.Tuple[typing.List[app.models.note.Note], int]:
    if sort_by == "page_number":
        sort_col = app.models.note.Note.page_number
        order_expr = sort_col.asc().nulls_last() if order == "asc" else sort_col.desc().nulls_last()
    else:
        sort_col = _NOTE_SORT_COLUMNS.get(sort_by, app.models.note.Note.created_at)
        order_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    base_conditions = [
        app.models.note.Note.user_id == user_id,
        app.models.note.Note.book_id == book_id
    ]

    count_stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(
        app.models.note.Note
    ).where(*base_conditions)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    stmt = sqlalchemy.select(app.models.note.Note).where(
        *base_conditions
    ).order_by(order_expr).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all(), total_count


async def get_user_notes(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    limit: int,
    offset: int
) -> typing.Tuple[typing.List[app.models.note.Note], int]:
    base_conditions = [app.models.note.Note.user_id == user_id]

    count_stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(
        app.models.note.Note
    ).where(*base_conditions)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    stmt = sqlalchemy.select(app.models.note.Note).where(
        *base_conditions
    ).order_by(app.models.note.Note.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all(), total_count
