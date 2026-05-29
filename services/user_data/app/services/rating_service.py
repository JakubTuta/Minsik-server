import typing

import app.models.rating
import app.services.stats_service
import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.ext.asyncio


async def _update_book_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession, book_id: int
) -> None:
    await session.execute(
        sqlalchemy.text(
            """
        WITH canonical AS (
            SELECT slug FROM books.books WHERE book_id = :book_id
        ),
        stats AS (
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
        ),
        dist AS (
            SELECT COALESCE(
                jsonb_object_agg(overall_rating::text, cnt),
                '{}'
            ) AS distribution
            FROM (
                SELECT overall_rating, COUNT(*) AS cnt
                FROM user_data.ratings
                WHERE book_id = :book_id
                GROUP BY overall_rating
            ) t
        )
        UPDATE books.books
        SET
            avg_rating           = stats.avg_overall,
            rating_count         = stats.total_count,
            rating_distribution  = dist.distribution,
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
        FROM stats, dist, canonical
        WHERE books.books.slug = canonical.slug
    """
        ),
        {"book_id": book_id},
    )


async def upsert_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    overall_rating: float,
    sub_ratings: typing.Dict[str, float],
    review_text: typing.Optional[str],
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
        "updated_at": sqlalchemy.func.now(),
    }
    update_values.update(sub_ratings)

    stmt = (
        sqlalchemy.dialects.postgresql.insert(app.models.rating.Rating)
        .values(**insert_values)
        .on_conflict_do_update(constraint="uq_ratings_user_book", set_=update_values)
        .returning(app.models.rating.Rating)
    )

    result = await session.execute(stmt)
    row = result.scalar_one()
    await _update_book_stats(session, book_id)
    await app.services.stats_service.recalculate_rating_stats(session, user_id)
    await session.commit()
    return row


async def delete_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession, user_id: int, book_id: int
) -> None:
    stmt = (
        sqlalchemy.delete(app.models.rating.Rating)
        .where(
            app.models.rating.Rating.user_id == user_id,
            app.models.rating.Rating.book_id == book_id,
        )
        .returning(app.models.rating.Rating.rating_id)
    )

    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise ValueError("not_found")

    await _update_book_stats(session, book_id)
    await app.services.stats_service.recalculate_rating_stats(session, user_id)
    await session.commit()


async def get_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession, user_id: int, book_id: int
) -> app.models.rating.Rating:
    stmt = sqlalchemy.select(app.models.rating.Rating).where(
        app.models.rating.Rating.user_id == user_id,
        app.models.rating.Rating.book_id == book_id,
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise ValueError("not_found")
    return row


async def get_user_ratings(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    limit: int,
    offset: int,
    sort_by: str,
    order: str,
    min_rating: float,
    max_rating: float,
) -> typing.Tuple[typing.List[typing.Any], int]:
    order_col = "r.created_at" if sort_by == "created_at" else "r.overall_rating"
    order_dir = "DESC" if order == "desc" else "ASC"

    filter_clauses: typing.List[str] = []
    filter_params: typing.Dict[str, typing.Any] = {"user_id": user_id}
    if min_rating > 0.0:
        filter_clauses.append("AND r.overall_rating >= :min_rating")
        filter_params["min_rating"] = min_rating
    if max_rating > 0.0:
        filter_clauses.append("AND r.overall_rating <= :max_rating")
        filter_params["max_rating"] = max_rating

    where_extra = " ".join(filter_clauses)

    count_result = await session.execute(
        sqlalchemy.text(f"""
            SELECT COUNT(*)
            FROM user_data.ratings r
            WHERE r.user_id = :user_id {where_extra}
        """),
        filter_params,
    )
    total_count = count_result.scalar_one()

    rows = await session.execute(
        sqlalchemy.text(f"""
            SELECT
                r.*,
                COALESCE(
                    (
                        COALESCE(b.avg_rating, 0) * b.rating_count
                        + COALESCE(b.ol_avg_rating, 0) * b.ol_rating_count
                    ) / NULLIF(b.rating_count + b.ol_rating_count, 0),
                    0
                ) AS book_avg_rating,
                COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0) AS book_rating_count
            FROM user_data.ratings r
            JOIN books.books b ON b.book_id = r.book_id
            WHERE r.user_id = :user_id {where_extra}
            ORDER BY {order_col} {order_dir}
            LIMIT :limit OFFSET :offset
        """),
        {**filter_params, "limit": limit, "offset": offset},
    )
    return rows.fetchall(), total_count


async def delete_user_ratings(
    session: sqlalchemy.ext.asyncio.AsyncSession, user_id: int
) -> None:
    book_ids_result = await session.execute(
        sqlalchemy.text(
            "SELECT DISTINCT book_id FROM user_data.ratings WHERE user_id = :user_id"
        ),
        {"user_id": user_id},
    )
    affected_book_ids = [row.book_id for row in book_ids_result.fetchall()]

    await session.execute(
        sqlalchemy.delete(app.models.rating.Rating).where(
            app.models.rating.Rating.user_id == user_id
        )
    )

    for book_id in affected_book_ids:
        await _update_book_stats(session, book_id)
