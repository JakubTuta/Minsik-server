import typing
import sqlalchemy
import sqlalchemy.ext.asyncio
import app.models.comment


_COMMENT_SORT_COLUMNS: typing.Dict[str, typing.Any] = {
    "created_at": app.models.comment.Comment.created_at,
    "updated_at": app.models.comment.Comment.updated_at,
}


async def create_comment(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    body: str,
    is_spoiler: bool
) -> app.models.comment.Comment:
    row = app.models.comment.Comment(
        user_id=user_id,
        book_id=book_id,
        body=body,
        is_spoiler=is_spoiler
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_comment(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    comment_id: int,
    user_id: int,
    body: str,
    is_spoiler: bool
) -> app.models.comment.Comment:
    stmt = sqlalchemy.select(app.models.comment.Comment).where(
        app.models.comment.Comment.comment_id == comment_id,
        app.models.comment.Comment.user_id == user_id,
        app.models.comment.Comment.is_deleted == False
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise ValueError("not_found")

    row.body = body
    row.is_spoiler = is_spoiler
    await session.commit()
    await session.refresh(row)
    return row


async def delete_comment(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    comment_id: int,
    user_id: int
) -> None:
    stmt = sqlalchemy.select(app.models.comment.Comment).where(
        app.models.comment.Comment.comment_id == comment_id,
        app.models.comment.Comment.user_id == user_id,
        app.models.comment.Comment.is_deleted == False
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise ValueError("not_found")

    row.is_deleted = True
    await session.commit()


async def get_book_comments(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    limit: int,
    offset: int,
    order: str,
    include_spoilers: bool
) -> typing.Tuple[typing.List[app.models.comment.Comment], int]:
    base_conditions = [
        app.models.comment.Comment.book_id == book_id,
        app.models.comment.Comment.is_deleted == False
    ]
    if not include_spoilers:
        base_conditions.append(app.models.comment.Comment.is_spoiler == False)

    order_expr = (
        app.models.comment.Comment.created_at.desc()
        if order == "desc"
        else app.models.comment.Comment.created_at.asc()
    )

    count_stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(
        app.models.comment.Comment
    ).where(*base_conditions)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    stmt = sqlalchemy.select(app.models.comment.Comment).where(
        *base_conditions
    ).order_by(order_expr).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all(), total_count


async def get_user_comments(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    limit: int,
    offset: int,
    sort_by: str,
    order: str,
    book_id: typing.Optional[int]
) -> typing.Tuple[typing.List[app.models.comment.Comment], int]:
    sort_col = _COMMENT_SORT_COLUMNS.get(sort_by, app.models.comment.Comment.created_at)
    order_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    base_conditions = [
        app.models.comment.Comment.user_id == user_id,
        app.models.comment.Comment.is_deleted == False
    ]
    if book_id is not None:
        base_conditions.append(app.models.comment.Comment.book_id == book_id)

    count_stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(
        app.models.comment.Comment
    ).where(*base_conditions)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    stmt = sqlalchemy.select(app.models.comment.Comment).where(
        *base_conditions
    ).order_by(order_expr).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all(), total_count
