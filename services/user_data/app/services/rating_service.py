import typing
import sqlalchemy
import sqlalchemy.ext.asyncio
import sqlalchemy.dialects.postgresql
import app.models.rating


_RATING_SORT_COLUMNS: typing.Dict[str, typing.Any] = {
    "created_at": app.models.rating.Rating.created_at,
    "overall_rating": app.models.rating.Rating.overall_rating,
}


async def _update_book_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int
) -> None:
    await session.execute(sqlalchemy.text("""
        WITH stats AS (
            SELECT
                ROUND(AVG(overall_rating)::NUMERIC, 2)    AS avg_overall,
                COUNT(*)                                   AS total_count,
                ROUND(AVG(pacing)::NUMERIC, 2)            AS avg_pacing,
                COUNT(pacing)                              AS pacing_count,
                ROUND(AVG(emotional_impact)::NUMERIC, 2)  AS avg_emotional_impact,
                COUNT(emotional_impact)                    AS emotional_impact_count,
                ROUND(AVG(intellectual_depth)::NUMERIC, 2) AS avg_intellectual_depth,
                COUNT(intellectual_depth)                  AS intellectual_depth_count,
                ROUND(AVG(writing_quality)::NUMERIC, 2)   AS avg_writing_quality,
                COUNT(writing_quality)                     AS writing_quality_count,
                ROUND(AVG(rereadability)::NUMERIC, 2)     AS avg_rereadability,
                COUNT(rereadability)                       AS rereadability_count,
                ROUND(AVG(readability)::NUMERIC, 2)       AS avg_readability,
                COUNT(readability)                         AS readability_count,
                ROUND(AVG(plot_complexity)::NUMERIC, 2)   AS avg_plot_complexity,
                COUNT(plot_complexity)                     AS plot_complexity_count,
                ROUND(AVG(humor)::NUMERIC, 2)             AS avg_humor,
                COUNT(humor)                               AS humor_count
            FROM user_data.ratings
            WHERE book_id = :book_id
        )
        UPDATE books.books
        SET
            avg_rating       = stats.avg_overall,
            rating_count     = stats.total_count,
            sub_rating_stats = (
                SELECT jsonb_object_agg(key, value)
                FROM (VALUES
                    ('pacing',            jsonb_build_object('avg', COALESCE(stats.avg_pacing, 0)::text,            'count', stats.pacing_count)),
                    ('emotional_impact',  jsonb_build_object('avg', COALESCE(stats.avg_emotional_impact, 0)::text,  'count', stats.emotional_impact_count)),
                    ('intellectual_depth',jsonb_build_object('avg', COALESCE(stats.avg_intellectual_depth, 0)::text,'count', stats.intellectual_depth_count)),
                    ('writing_quality',   jsonb_build_object('avg', COALESCE(stats.avg_writing_quality, 0)::text,   'count', stats.writing_quality_count)),
                    ('rereadability',     jsonb_build_object('avg', COALESCE(stats.avg_rereadability, 0)::text,     'count', stats.rereadability_count)),
                    ('readability',       jsonb_build_object('avg', COALESCE(stats.avg_readability, 0)::text,       'count', stats.readability_count)),
                    ('plot_complexity',   jsonb_build_object('avg', COALESCE(stats.avg_plot_complexity, 0)::text,   'count', stats.plot_complexity_count)),
                    ('humor',             jsonb_build_object('avg', COALESCE(stats.avg_humor, 0)::text,             'count', stats.humor_count))
                ) AS t(key, value)
            )
        FROM stats
        WHERE books.books.book_id = :book_id
    """), {"book_id": book_id})


async def upsert_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    overall_rating: float,
    sub_ratings: typing.Dict[str, float],
    review_text: typing.Optional[str]
) -> app.models.rating.Rating:
    insert_values: typing.Dict[str, typing.Any] = {
        "user_id": user_id,
        "book_id": book_id,
        "overall_rating": overall_rating,
        "review_text": review_text,
    }
    insert_values.update(sub_ratings)

    update_values: typing.Dict[str, typing.Any] = {
        "overall_rating": overall_rating,
        "review_text": review_text,
        "updated_at": sqlalchemy.func.now()
    }
    update_values.update(sub_ratings)

    stmt = sqlalchemy.dialects.postgresql.insert(app.models.rating.Rating).values(
        **insert_values
    ).on_conflict_do_update(
        constraint="uq_ratings_user_book",
        set_=update_values
    ).returning(app.models.rating.Rating)

    result = await session.execute(stmt)
    row = result.scalar_one()
    await _update_book_stats(session, book_id)
    await session.commit()
    return row


async def delete_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int
) -> None:
    stmt = sqlalchemy.delete(app.models.rating.Rating).where(
        app.models.rating.Rating.user_id == user_id,
        app.models.rating.Rating.book_id == book_id
    ).returning(app.models.rating.Rating.rating_id)

    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise ValueError("not_found")

    await _update_book_stats(session, book_id)
    await session.commit()


async def get_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int
) -> typing.Optional[app.models.rating.Rating]:
    stmt = sqlalchemy.select(app.models.rating.Rating).where(
        app.models.rating.Rating.user_id == user_id,
        app.models.rating.Rating.book_id == book_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_ratings(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    limit: int,
    offset: int,
    sort_by: str,
    order: str,
    min_rating: float,
    max_rating: float
) -> typing.Tuple[typing.List[app.models.rating.Rating], int]:
    sort_col = _RATING_SORT_COLUMNS.get(sort_by, app.models.rating.Rating.created_at)
    order_expr = sort_col.desc() if order == "desc" else sort_col.asc()

    base_conditions = [app.models.rating.Rating.user_id == user_id]
    if min_rating > 0.0:
        base_conditions.append(app.models.rating.Rating.overall_rating >= min_rating)
    if max_rating > 0.0:
        base_conditions.append(app.models.rating.Rating.overall_rating <= max_rating)

    count_stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(
        app.models.rating.Rating
    ).where(*base_conditions)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    stmt = sqlalchemy.select(app.models.rating.Rating).where(
        *base_conditions
    ).order_by(order_expr).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all(), total_count
