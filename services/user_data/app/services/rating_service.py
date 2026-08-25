import typing

import app.models.rating
import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.ext.asyncio


async def _update_book_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession, book_id: int
) -> None:
    await _update_work_stats(session, [book_id])


async def _update_work_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession, book_ids: typing.List[int]
) -> None:
    """Recompute pooled rating stats for every work the given books belong to.

    Takes a list because a bulk delete leaves many books stale at once, and the
    per-work aggregate is the same shape whether it covers one work or all of
    them — running it once per book meant one full statement per rating.
    """
    if not book_ids:
        return

    await session.execute(
        sqlalchemy.text(
            """
        WITH canonical AS (
            SELECT DISTINCT work_id FROM books.books WHERE book_id = ANY(:book_ids)
        ),
        work_ratings AS (
            SELECT b.work_id, r.*
            FROM books.books b
            JOIN canonical c ON c.work_id = b.work_id
            JOIN user_data.ratings r ON r.book_id = b.book_id
        ),
        stats AS (
            SELECT
                work_id,
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
            FROM work_ratings
            GROUP BY work_id
        ),
        dist AS (
            SELECT work_id, jsonb_object_agg(overall_rating::text, cnt) AS distribution
            FROM (
                SELECT work_id, overall_rating, COUNT(*) AS cnt
                FROM work_ratings
                GROUP BY work_id, overall_rating
            ) t
            GROUP BY work_id
        )
        UPDATE books.books
        SET
            avg_rating           = stats.avg_overall,
            rating_count         = COALESCE(stats.total_count, 0),
            rating_distribution  = COALESCE(dist.distribution, '{}'::jsonb),
            sub_rating_stats = (
                SELECT jsonb_object_agg(key, value)
                FROM (VALUES
                    ('pacing',            jsonb_build_object('avg', COALESCE(stats.avg_pacing, 0)::text,            'count', COALESCE(stats.pacing_count, 0))),
                    ('emotional_impact',  jsonb_build_object('avg', COALESCE(stats.avg_emotional_impact, 0)::text,  'count', COALESCE(stats.emotional_impact_count, 0))),
                    ('intellectual_depth',jsonb_build_object('avg', COALESCE(stats.avg_intellectual_depth, 0)::text,'count', COALESCE(stats.intellectual_depth_count, 0))),
                    ('writing_quality',   jsonb_build_object('avg', COALESCE(stats.avg_writing_quality, 0)::text,   'count', COALESCE(stats.writing_quality_count, 0))),
                    ('rereadability',     jsonb_build_object('avg', COALESCE(stats.avg_rereadability, 0)::text,     'count', COALESCE(stats.rereadability_count, 0))),
                    ('readability',       jsonb_build_object('avg', COALESCE(stats.avg_readability, 0)::text,       'count', COALESCE(stats.readability_count, 0))),
                    ('plot_complexity',   jsonb_build_object('avg', COALESCE(stats.avg_plot_complexity, 0)::text,   'count', COALESCE(stats.plot_complexity_count, 0))),
                    ('humor',             jsonb_build_object('avg', COALESCE(stats.avg_humor, 0)::text,             'count', COALESCE(stats.humor_count, 0)))
                ) AS t(key, value)
            )
        FROM canonical
        LEFT JOIN stats ON stats.work_id = canonical.work_id
        LEFT JOIN dist ON dist.work_id = canonical.work_id
        WHERE books.books.work_id = canonical.work_id
    """
        ),
        {"book_ids": list({int(book_id) for book_id in book_ids})},
    )


async def _move_sibling_edition_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
) -> None:
    """Move this user's rating from another edition of the same work onto this one.

    `uq_ratings_user_book` is keyed on (user_id, book_id), which is per-edition —
    rating two language editions of the same work would otherwise count this one
    user twice in _update_book_stats' pooled average.

    The sibling row is re-pointed rather than deleted so the original created_at (and
    any sub-rating dimensions the incoming payload leaves untouched) survive the move.
    Only when a rating already exists for this edition are leftover siblings dropped.
    """
    params = {"user_id": user_id, "book_id": book_id}

    await session.execute(
        sqlalchemy.text(
            """
            UPDATE user_data.ratings
            SET book_id = :book_id
            WHERE rating_id = (
                SELECT r.rating_id
                FROM user_data.ratings r
                JOIN books.books b ON b.book_id = r.book_id
                WHERE r.user_id = :user_id
                  AND r.book_id != :book_id
                  AND b.work_id = (SELECT work_id FROM books.books WHERE book_id = :book_id)
                ORDER BY r.updated_at DESC
                LIMIT 1
            )
            AND NOT EXISTS (
                SELECT 1 FROM user_data.ratings existing
                WHERE existing.user_id = :user_id AND existing.book_id = :book_id
            )
            """
        ),
        params,
    )

    await session.execute(
        sqlalchemy.text(
            """
            DELETE FROM user_data.ratings
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


async def upsert_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    book_id: int,
    overall_rating: float,
    sub_ratings: typing.Dict[str, float],
    review_text: typing.Optional[str],
) -> app.models.rating.Rating:
    await _move_sibling_edition_rating(session, user_id, book_id)

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
    await session.commit()
    return row


async def delete_rating(
    session: sqlalchemy.ext.asyncio.AsyncSession, user_id: int, book_id: int
) -> None:
    """Drop this reader's rating of the work the given edition belongs to.

    The rating is recorded against whichever translation they happened to be
    reading, while the book page finds it across every edition of the work.
    Deleting only the edition in the URL therefore answers not_found for a
    rating the reader can plainly see.
    """
    result = await session.execute(
        sqlalchemy.text(
            """
            DELETE FROM user_data.ratings
            WHERE user_id = :user_id
              AND book_id IN (
                  SELECT b.book_id FROM books.books b
                  WHERE b.work_id = (SELECT work_id FROM books.books WHERE book_id = :book_id)
              )
            RETURNING book_id
            """
        ),
        {"user_id": user_id, "book_id": book_id},
    )
    if not result.fetchall():
        raise ValueError("not_found")

    await _update_book_stats(session, book_id)
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

    await _update_work_stats(session, affected_book_ids)
