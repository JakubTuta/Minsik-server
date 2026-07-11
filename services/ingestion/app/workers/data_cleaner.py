import asyncio
import logging
import typing

import app.config
import app.models
import app.models.series
import app.utils
import redis
import sqlalchemy
import sqlalchemy.dialects.postgresql
import sqlalchemy.engine
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_DUMP_RUNNING_KEY = "dump_import_running"
_SOLE_BOOK_SUB_BATCH = 100
_NAME_JUNK_CHARS = " \t\r\n,;:|/\\=*^<>-–—·•"

SessionFactory = sqlalchemy.ext.asyncio.async_sessionmaker


def _create_redis_client() -> redis.Redis:
    return redis.Redis(
        host=app.config.settings.redis_host,
        port=app.config.settings.redis_port,
        db=app.config.settings.redis_db,
        password=app.config.settings.redis_password or None,
        decode_responses=True,
    )


async def _delete_book_user_data(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_ids: typing.List[int],
) -> typing.List[int]:
    if not book_ids:
        return []

    affected_users_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT DISTINCT user_id FROM user_data.bookshelves WHERE book_id = ANY(:book_ids)
            UNION
            SELECT DISTINCT user_id FROM user_data.ratings WHERE book_id = ANY(:book_ids)
            UNION
            SELECT DISTINCT user_id FROM user_data.comments WHERE book_id = ANY(:book_ids)
            """
        ),
        {"book_ids": book_ids},
    )
    affected_user_ids = [row[0] for row in affected_users_result.fetchall()]

    await session.execute(
        sqlalchemy.text("DELETE FROM user_data.comments WHERE book_id = ANY(:book_ids)"),
        {"book_ids": book_ids},
    )
    await session.execute(
        sqlalchemy.text("DELETE FROM user_data.ratings WHERE book_id = ANY(:book_ids)"),
        {"book_ids": book_ids},
    )
    await session.execute(
        sqlalchemy.text("DELETE FROM user_data.bookshelves WHERE book_id = ANY(:book_ids)"),
        {"book_ids": book_ids},
    )

    return affected_user_ids


async def _remap_book_user_data(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    loser_book_id: int,
    winner_book_id: int,
) -> typing.List[int]:
    affected_users_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT DISTINCT user_id FROM user_data.bookshelves WHERE book_id = :loser_id
            UNION
            SELECT DISTINCT user_id FROM user_data.ratings WHERE book_id = :loser_id
            UNION
            SELECT DISTINCT user_id FROM user_data.comments WHERE book_id = :loser_id
            """
        ),
        {"loser_id": loser_book_id},
    )
    affected_user_ids = [row[0] for row in affected_users_result.fetchall()]

    for table in ("bookshelves", "ratings", "comments"):
        await session.execute(
            sqlalchemy.text(
                f"""
                DELETE FROM user_data.{table} loser
                WHERE loser.book_id = :loser_id
                  AND EXISTS (
                      SELECT 1 FROM user_data.{table} winner
                      WHERE winner.user_id = loser.user_id
                        AND winner.book_id = :winner_id
                  )
                """
            ),
            {"loser_id": loser_book_id, "winner_id": winner_book_id},
        )
        await session.execute(
            sqlalchemy.text(
                f"UPDATE user_data.{table} SET book_id = :winner_id WHERE book_id = :loser_id"
            ),
            {"loser_id": loser_book_id, "winner_id": winner_book_id},
        )

    return affected_user_ids


async def _recompute_user_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_ids: typing.List[int],
) -> None:
    for user_id in user_ids:
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, want_to_read_count, reading_count, read_count, abandoned_count, favourites_count)
                SELECT
                    :user_id,
                    COUNT(CASE WHEN status = 'want_to_read' THEN 1 END),
                    COUNT(CASE WHEN status = 'reading'      THEN 1 END),
                    COUNT(CASE WHEN status = 'read'         THEN 1 END),
                    COUNT(CASE WHEN status = 'abandoned'    THEN 1 END),
                    COUNT(CASE WHEN is_favorite             THEN 1 END)
                FROM user_data.bookshelves
                WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET
                    want_to_read_count = EXCLUDED.want_to_read_count,
                    reading_count      = EXCLUDED.reading_count,
                    read_count         = EXCLUDED.read_count,
                    abandoned_count    = EXCLUDED.abandoned_count,
                    favourites_count   = EXCLUDED.favourites_count
                """
            ),
            {"user_id": user_id},
        )
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, ratings_count)
                SELECT :user_id, COUNT(*) FROM user_data.ratings WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET ratings_count = EXCLUDED.ratings_count
                """
            ),
            {"user_id": user_id},
        )
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, comments_count)
                SELECT :user_id, COUNT(*) FROM user_data.comments WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET comments_count = EXCLUDED.comments_count
                """
            ),
            {"user_id": user_id},
        )


async def cleanup_low_quality_books(
    session_factory: SessionFactory,
    min_quality_score: int,
    engagement_threshold: int,
    min_publication_year: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    quality_score_sql = """
        (CASE WHEN b.description IS NOT NULL AND b.description != '' THEN 1 ELSE 0 END) +
        (CASE WHEN b.primary_cover_url IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN EXISTS (SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id) THEN 1 ELSE 0 END) +
        (CASE WHEN EXISTS (SELECT 1 FROM books.book_genres bg WHERE bg.book_id = b.book_id) THEN 1 ELSE 0 END) +
        (CASE WHEN b.original_publication_year IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN b.isbn IS NOT NULL AND b.isbn != '[]'::jsonb THEN 1 ELSE 0 END) +
        (CASE WHEN b.number_of_pages IS NOT NULL AND b.number_of_pages > 0 THEN 1 ELSE 0 END) +
        (CASE WHEN b.publisher IS NOT NULL AND b.publisher != '' THEN 1 ELSE 0 END)
    """

    total_deleted = 0
    consecutive_failures = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping book cleanup: dump import started")
            break
        deleted = 0
        try:
            async with session_factory() as session:
                id_result = await session.execute(
                    sqlalchemy.text(
                        f"""
                        SELECT b.book_id FROM books.books b
                        WHERE b.created_at < NOW() - INTERVAL '1 day'
                          AND b.view_count <= 2
                          AND (
                            (
                              ({quality_score_sql}) < :min_score
                              AND (b.rating_count + COALESCE(b.ol_rating_count, 0)) < :engagement
                              AND (
                                COALESCE(b.ol_already_read_count, 0) +
                                (SELECT COUNT(*) FROM user_data.bookshelves bs WHERE bs.book_id = b.book_id)
                              ) < :engagement
                            )
                            OR NOT EXISTS (SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id)
                            OR b.title ~ '^[\\s\\W]*$'
                            OR char_length(btrim(b.title)) < 2
                            OR b.original_publication_year > EXTRACT(YEAR FROM NOW())::int + 1
                            OR b.original_publication_year < :min_year
                            OR (
                              NOT EXISTS (SELECT 1 FROM books.book_genres bg WHERE bg.book_id = b.book_id)
                              AND ({quality_score_sql}) < 5
                            )
                          )
                          AND NOT EXISTS (SELECT 1 FROM user_data.bookshelves ub WHERE ub.book_id = b.book_id)
                          AND NOT EXISTS (SELECT 1 FROM user_data.ratings ur WHERE ur.book_id = b.book_id)
                          AND NOT EXISTS (SELECT 1 FROM user_data.comments uc WHERE uc.book_id = b.book_id)
                        LIMIT :batch_size
                        """
                    ),
                    {
                        "min_score": min_quality_score,
                        "engagement": engagement_threshold,
                        "min_year": min_publication_year,
                        "batch_size": batch_size,
                    },
                )
                book_ids = [row[0] for row in id_result.fetchall()]

                if not book_ids:
                    break

                affected_user_ids = await _delete_book_user_data(session, book_ids)
                result = await session.execute(
                    sqlalchemy.text("DELETE FROM books.books WHERE book_id = ANY(:book_ids)"),
                    {"book_ids": book_ids},
                )
                deleted = typing.cast(sqlalchemy.engine.CursorResult, result).rowcount
                await _recompute_user_stats(session, affected_user_ids)
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Book cleanup batch failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break
            await asyncio.sleep(5)
            continue

        consecutive_failures = 0
        if deleted == 0:
            break

        total_deleted += deleted
        logger.info(f"[cleanup] Deleted {total_deleted} low-quality books so far")
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted}


async def cleanup_duplicate_books(
    session_factory: SessionFactory,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    total_deleted = 0
    consecutive_failures = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping duplicate book cleanup: dump import started")
            break
        deleted = 0
        try:
            async with session_factory() as session:
                id_result = await session.execute(
                    sqlalchemy.text(
                        """
                        WITH ranked AS (
                            SELECT
                                b.book_id,
                                FIRST_VALUE(b.book_id) OVER (
                                    PARTITION BY
                                        lower(btrim(b.title)),
                                        b.language,
                                        (SELECT MIN(ba.author_id)
                                         FROM books.book_authors ba
                                         WHERE ba.book_id = b.book_id)
                                    ORDER BY
                                        (b.view_count + b.rating_count + COALESCE(b.ol_rating_count, 0)) DESC,
                                        b.book_id ASC
                                ) AS winner_book_id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY
                                        lower(btrim(b.title)),
                                        b.language,
                                        (SELECT MIN(ba.author_id)
                                         FROM books.book_authors ba
                                         WHERE ba.book_id = b.book_id)
                                    ORDER BY
                                        (b.view_count + b.rating_count + COALESCE(b.ol_rating_count, 0)) DESC,
                                        b.book_id ASC
                                ) AS rn
                            FROM books.books b
                            WHERE EXISTS (
                                SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id
                            )
                        )
                        SELECT book_id, winner_book_id FROM ranked WHERE rn > 1
                        LIMIT :batch_size
                        """
                    ),
                    {"batch_size": batch_size},
                )
                dup_pairs = [(row[0], row[1]) for row in id_result.fetchall()]

                if not dup_pairs:
                    break

                book_ids = [loser_id for loser_id, _ in dup_pairs]

                affected_user_ids: typing.Set[int] = set()
                for loser_id, winner_id in dup_pairs:
                    remapped_users = await _remap_book_user_data(
                        session, loser_id, winner_id
                    )
                    affected_user_ids.update(remapped_users)

                result = await session.execute(
                    sqlalchemy.text("DELETE FROM books.books WHERE book_id = ANY(:book_ids)"),
                    {"book_ids": book_ids},
                )
                deleted = typing.cast(sqlalchemy.engine.CursorResult, result).rowcount
                await _recompute_user_stats(session, list(affected_user_ids))
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Duplicate book cleanup batch failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break
            await asyncio.sleep(5)
            continue

        consecutive_failures = 0
        if deleted == 0:
            break

        total_deleted += deleted
        logger.info(f"[cleanup] Deleted {total_deleted} duplicate books so far")
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted}


async def cleanup_orphan_authors(
    session_factory: SessionFactory,
    min_books: int,
    max_books: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    total_deleted = 0
    consecutive_failures = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping author cleanup: dump import started")
            break

        deleted = 0
        try:
            async with session_factory() as session:
                author_id_result = await session.execute(
                    sqlalchemy.text(
                        """
                        SELECT a.author_id FROM books.authors a
                        LEFT JOIN (
                            SELECT author_id, COUNT(*) AS book_count
                            FROM books.book_authors
                            GROUP BY author_id
                        ) ba ON ba.author_id = a.author_id
                        WHERE COALESCE(ba.book_count, 0) < :min_books
                           OR COALESCE(ba.book_count, 0) > :max_books
                           OR a.name !~ '[A-Za-z]'
                           OR char_length(btrim(a.name)) < 2
                        LIMIT :batch_size
                        """
                    ),
                    {"min_books": min_books, "max_books": max_books, "batch_size": batch_size},
                )
                author_ids = [row[0] for row in author_id_result.fetchall()]

                if not author_ids:
                    break

                book_id_result = await session.execute(
                    sqlalchemy.text(
                        """
                        SELECT ba.book_id,
                               (SELECT COUNT(*) FROM books.book_authors ba2 WHERE ba2.book_id = ba.book_id) AS author_count
                        FROM books.book_authors ba
                        WHERE ba.author_id = ANY(:author_ids)
                        """
                    ),
                    {"author_ids": author_ids},
                )
                candidate_sole_book_ids = [
                    row[0] for row in book_id_result.fetchall() if row[1] == 1
                ]

                sole_book_ids = candidate_sole_book_ids
                if candidate_sole_book_ids:
                    engaged_result = await session.execute(
                        sqlalchemy.text(
                            """
                            SELECT DISTINCT book_id FROM user_data.bookshelves WHERE book_id = ANY(:book_ids)
                            UNION
                            SELECT DISTINCT book_id FROM user_data.ratings WHERE book_id = ANY(:book_ids)
                            UNION
                            SELECT DISTINCT book_id FROM user_data.comments WHERE book_id = ANY(:book_ids)
                            """
                        ),
                        {"book_ids": candidate_sole_book_ids},
                    )
                    engaged_book_ids = {row[0] for row in engaged_result.fetchall()}
                    sole_book_ids = [
                        book_id
                        for book_id in candidate_sole_book_ids
                        if book_id not in engaged_book_ids
                    ]

                for i in range(0, len(sole_book_ids), _SOLE_BOOK_SUB_BATCH):
                    sub_batch = sole_book_ids[i : i + _SOLE_BOOK_SUB_BATCH]
                    affected_user_ids = await _delete_book_user_data(session, sub_batch)
                    await session.execute(
                        sqlalchemy.text(
                            "DELETE FROM books.books WHERE book_id = ANY(:book_ids)"
                        ),
                        {"book_ids": sub_batch},
                    )
                    await _recompute_user_stats(session, affected_user_ids)

                result = await session.execute(
                    sqlalchemy.text(
                        "DELETE FROM books.authors WHERE author_id = ANY(:author_ids)"
                    ),
                    {"author_ids": author_ids},
                )
                deleted = typing.cast(sqlalchemy.engine.CursorResult, result).rowcount
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Author cleanup batch failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break
            await asyncio.sleep(5)
            continue

        consecutive_failures = 0
        total_deleted += deleted
        logger.info(f"[cleanup] Deleted {total_deleted} low-relevance authors so far")
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted}


async def _heal_table_names(
    session_factory: SessionFactory,
    table: str,
    id_col: str,
    name_col: str,
    batch_size: int,
    stop_check: typing.Callable[[], bool],
) -> int:
    total_healed = 0
    last_id = 0
    while True:
        if stop_check():
            logger.info(f"[cleanup] Stopping {table} name healing: dump import started")
            break
        try:
            async with session_factory() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        f"""
                        SELECT {id_col}, {name_col} FROM books.{table}
                        WHERE {id_col} > :last_id
                          AND ({name_col} <> btrim({name_col}, :junk_chars) OR {name_col} LIKE '%  %')
                        ORDER BY {id_col}
                        LIMIT :batch_size
                        """
                    ),
                    {"last_id": last_id, "junk_chars": _NAME_JUNK_CHARS, "batch_size": batch_size},
                )
                rows = result.fetchall()

                if not rows:
                    break

                for row_id, raw_name in rows:
                    cleaned = app.utils.clean_name(raw_name)
                    if cleaned and cleaned != raw_name:
                        await session.execute(
                            sqlalchemy.text(
                                f"UPDATE books.{table} SET {name_col} = :cleaned WHERE {id_col} = :row_id"
                            ),
                            {"cleaned": cleaned, "row_id": row_id},
                        )
                        total_healed += 1

                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] {table} name healing batch failed: {e}")
            break

        last_id = rows[-1][0]
        if len(rows) < batch_size:
            break
        await asyncio.sleep(0.5)

    return total_healed


async def heal_entity_names(
    session_factory: SessionFactory,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    stats = {"books_healed": 0, "authors_healed": 0}

    stats["books_healed"] = await _heal_table_names(
        session_factory, "books", "book_id", "title", batch_size, stop_check
    )
    if stop_check():
        return stats

    stats["authors_healed"] = await _heal_table_names(
        session_factory, "authors", "author_id", "name", batch_size, stop_check
    )

    logger.info(
        f"[cleanup] Name healing complete: books_healed={stats['books_healed']}, "
        f"authors_healed={stats['authors_healed']}"
    )
    return stats


async def consolidate_series(
    session_factory: SessionFactory,
    min_books: int,
    max_books: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    stats = {"linked": 0, "unlinked": 0, "rows_created": 0, "rows_deleted": 0}

    # Phase A: renormalize legacy series_slug values that contain position suffixes.
    # Works in batches over distinct (series_name, series_slug) pairs.
    offset = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping series renormalize: dump import started")
            return stats
        try:
            async with session_factory() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        """
                        SELECT DISTINCT series_name, series_slug
                        FROM books.books
                        WHERE series_slug IS NOT NULL AND series_name IS NOT NULL
                        ORDER BY series_slug
                        LIMIT :batch_size OFFSET :offset
                        """
                    ),
                    {"batch_size": batch_size, "offset": offset},
                )
                rows = result.fetchall()
        except Exception as e:
            logger.error(f"[cleanup] Series renormalize fetch failed: {e}")
            break

        if not rows:
            break

        for row in rows:
            old_name: str = row[0]
            old_slug: str = row[1]
            parsed = app.utils.parse_series_descriptor(old_name)
            if not parsed:
                continue
            canonical_name: str = parsed["name"]
            canonical_slug: str = app.utils.slugify(canonical_name)
            parsed_pos: typing.Optional[float] = parsed.get("position")

            if canonical_slug == old_slug and canonical_name == old_name:
                continue

            try:
                async with session_factory() as session:
                    await session.execute(
                        sqlalchemy.text(
                            """
                            UPDATE books.books
                            SET series_slug = :new_slug,
                                series_name = :new_name,
                                series_position = COALESCE(series_position, :parsed_pos)
                            WHERE series_slug = :old_slug AND series_name = :old_name
                            """
                        ),
                        {
                            "new_slug": canonical_slug,
                            "new_name": canonical_name,
                            "old_slug": old_slug,
                            "old_name": old_name,
                            "parsed_pos": parsed_pos,
                        },
                    )
                    await session.commit()
            except Exception as e:
                logger.error(
                    f"[cleanup] Series renormalize update failed for slug={old_slug}: {e}"
                )

        offset += batch_size
        await asyncio.sleep(0.1)

    logger.info("[cleanup] Series renormalize complete")

    # Phase B: build/link series rows per (slug, language); unlink out-of-range pairs.
    b_offset = 0
    consecutive_failures = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping series consolidation: dump import started")
            break

        try:
            async with session_factory() as session:
                counts_result = await session.execute(
                    sqlalchemy.text(
                        """
                        SELECT series_slug, language, COUNT(*) AS c,
                               MIN(series_name) AS rep_name
                        FROM books.books
                        WHERE series_slug IS NOT NULL
                        GROUP BY series_slug, language
                        ORDER BY series_slug, language
                        LIMIT :batch_size OFFSET :offset
                        """
                    ),
                    {"batch_size": batch_size, "offset": b_offset},
                )
                count_rows = counts_result.fetchall()

                if not count_rows:
                    break

                qualifying: list[dict] = []
                disqualifying: list[dict] = []
                slug_to_name: dict[str, str] = {}

                for row in count_rows:
                    s_slug, lang, c, rep_name = row
                    if rep_name:
                        slug_to_name[s_slug] = rep_name
                    if min_books <= c <= max_books:
                        qualifying.append({"slug": s_slug, "lang": lang})
                    else:
                        disqualifying.append({"slug": s_slug, "lang": lang})

                qualifying_slugs = list({q["slug"] for q in qualifying})
                slug_to_id: dict[str, int] = {}

                if qualifying_slugs:
                    series_data = [
                        {"name": slug_to_name.get(s, s), "slug": s}
                        for s in qualifying_slugs
                    ]
                    series_data.sort(key=lambda r: r["slug"])
                    stmt = sqlalchemy.dialects.postgresql.insert(
                        app.models.series.Series
                    ).values(series_data)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["slug"],
                        set_={"name": stmt.excluded.name},
                    )
                    stmt = stmt.returning(
                        app.models.series.Series.slug,
                        app.models.series.Series.series_id,
                    )
                    result = await session.execute(stmt)
                    for r in result:
                        slug_to_id[r.slug] = r.series_id
                    stats["rows_created"] += len(qualifying_slugs)

                for q in qualifying:
                    s_id = slug_to_id.get(q["slug"])
                    if s_id is None:
                        continue
                    link_result = await session.execute(
                        sqlalchemy.text(
                            """
                            UPDATE books.books
                            SET series_id = :sid
                            WHERE series_slug = :slug
                              AND language = :lang
                              AND series_id IS DISTINCT FROM :sid
                            """
                        ),
                        {"sid": s_id, "slug": q["slug"], "lang": q["lang"]},
                    )
                    stats["linked"] += typing.cast(
                        sqlalchemy.engine.CursorResult, link_result
                    ).rowcount

                for dq in disqualifying:
                    unlink_result = await session.execute(
                        sqlalchemy.text(
                            """
                            UPDATE books.books
                            SET series_id = NULL
                            WHERE series_slug = :slug
                              AND language = :lang
                              AND series_id IS NOT NULL
                            """
                        ),
                        {"slug": dq["slug"], "lang": dq["lang"]},
                    )
                    stats["unlinked"] += typing.cast(
                        sqlalchemy.engine.CursorResult, unlink_result
                    ).rowcount

                await session.commit()

        except Exception as e:
            logger.error(f"[cleanup] Series consolidation batch failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break
            await asyncio.sleep(5)
            continue

        consecutive_failures = 0
        b_offset += batch_size
        await asyncio.sleep(0.5)

    # Clean up orphan series rows and refresh total_books in a final pass.
    try:
        async with session_factory() as session:
            del_result = await session.execute(
                sqlalchemy.text(
                    """
                    DELETE FROM books.series
                    WHERE NOT EXISTS (
                        SELECT 1 FROM books.books b WHERE b.series_id = books.series.series_id
                    )
                    """
                )
            )
            stats["rows_deleted"] += typing.cast(
                sqlalchemy.engine.CursorResult, del_result
            ).rowcount
            await session.execute(
                sqlalchemy.text(
                    """
                    UPDATE books.series s
                    SET total_books = (
                        SELECT COUNT(*) FROM books.books b WHERE b.series_id = s.series_id
                    )
                    WHERE s.total_books IS DISTINCT FROM (
                        SELECT COUNT(*) FROM books.books b WHERE b.series_id = s.series_id
                    )
                    """
                )
            )
            await session.commit()
    except Exception as e:
        logger.error(f"[cleanup] Series post-consolidation cleanup failed: {e}")

    logger.info(
        f"[cleanup] Series consolidation complete: linked={stats['linked']}, "
        f"unlinked={stats['unlinked']}, rows_created={stats['rows_created']}, "
        f"rows_deleted={stats['rows_deleted']}"
    )
    return stats


async def normalize_and_merge_genres(
    session_factory: SessionFactory,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_merged = 0
    offset = 0

    while True:
        if stop_check():
            logger.info("[cleanup] Stopping genre normalization: dump import started")
            break

        try:
            async with session_factory() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        "SELECT genre_id, name, slug FROM books.genres ORDER BY genre_id LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": batch_size, "offset": offset},
                )
                rows = result.fetchall()
        except Exception as e:
            logger.error(f"[cleanup] Genre normalization fetch failed: {e}")
            break

        if not rows:
            break

        for row in rows:
            old_id: int = row[0]
            current_name: str = row[1]
            current_slug: str = row[2]

            canonical_name, canonical_slug = app.utils.canonicalize_genre_name(
                current_name
            )

            if canonical_slug == current_slug:
                continue

            try:
                async with session_factory() as session:
                    canonical_result = await session.execute(
                        sqlalchemy.text(
                            "SELECT genre_id FROM books.genres WHERE slug = :slug"
                        ),
                        {"slug": canonical_slug},
                    )
                    canonical_row = canonical_result.fetchone()

                    if canonical_row:
                        canonical_id = canonical_row[0]
                        if canonical_id == old_id:
                            continue
                        await session.execute(
                            sqlalchemy.text(
                                """
                                INSERT INTO books.book_genres (book_id, genre_id)
                                SELECT book_id, :canonical_id FROM books.book_genres
                                WHERE genre_id = :old_id
                                ON CONFLICT DO NOTHING
                                """
                            ),
                            {"canonical_id": canonical_id, "old_id": old_id},
                        )
                        await session.execute(
                            sqlalchemy.text(
                                "DELETE FROM books.book_genres WHERE genre_id = :old_id"
                            ),
                            {"old_id": old_id},
                        )
                        await session.execute(
                            sqlalchemy.text(
                                "DELETE FROM books.genres WHERE genre_id = :old_id"
                            ),
                            {"old_id": old_id},
                        )
                    else:
                        await session.execute(
                            sqlalchemy.text(
                                "UPDATE books.genres SET name = :name, slug = :slug WHERE genre_id = :id"
                            ),
                            {
                                "name": canonical_name[:100],
                                "slug": canonical_slug[:150],
                                "id": old_id,
                            },
                        )

                    await session.commit()
                    total_merged += 1
            except Exception as e:
                logger.error(
                    f"[cleanup] Genre normalization merge failed for genre_id={old_id}: {e}"
                )

        offset += batch_size
        await asyncio.sleep(0.1)

    logger.info(f"[cleanup] Genre normalization complete. Merged/renamed: {total_merged}")
    return total_merged


async def cleanup_orphan_genres(
    session_factory: SessionFactory,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    consecutive_failures = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping genre cleanup: dump import started")
            break
        deleted = 0
        try:
            async with session_factory() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        """
                        DELETE FROM books.genres
                        WHERE genre_id IN (
                            SELECT g.genre_id FROM books.genres g
                            WHERE NOT EXISTS (
                                SELECT 1 FROM books.book_genres bg WHERE bg.genre_id = g.genre_id
                            )
                            LIMIT :batch_size
                        )
                        """
                    ),
                    {"batch_size": batch_size},
                )
                deleted = typing.cast(sqlalchemy.engine.CursorResult, result).rowcount
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Orphan genre cleanup batch failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break
            await asyncio.sleep(5)
            continue

        consecutive_failures = 0
        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def cleanup_underrepresented_genres(
    session_factory: SessionFactory,
    min_book_count: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    consecutive_failures = 0
    while True:
        if stop_check():
            logger.info(
                "[cleanup] Stopping underrepresented genre cleanup: dump import started"
            )
            break
        deleted = 0
        try:
            async with session_factory() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        """
                        DELETE FROM books.genres
                        WHERE genre_id IN (
                            SELECT g.genre_id FROM books.genres g
                            LEFT JOIN (
                                SELECT genre_id, COUNT(*) AS book_count
                                FROM books.book_genres
                                GROUP BY genre_id
                            ) bg ON bg.genre_id = g.genre_id
                            WHERE COALESCE(bg.book_count, 0) <= :min_book_count
                            LIMIT :batch_size
                        )
                        """
                    ),
                    {"min_book_count": min_book_count, "batch_size": batch_size},
                )
                deleted = typing.cast(sqlalchemy.engine.CursorResult, result).rowcount
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Underrepresented genre cleanup batch failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break
            await asyncio.sleep(5)
            continue

        consecutive_failures = 0
        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def cleanup_invalid_genre_names(
    session_factory: SessionFactory,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    consecutive_failures = 0
    while True:
        if stop_check():
            logger.info(
                "[cleanup] Stopping invalid genre name cleanup: dump import started"
            )
            break
        deleted = 0
        try:
            async with session_factory() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        """
                        DELETE FROM books.genres
                        WHERE genre_id IN (
                            SELECT g.genre_id FROM books.genres g
                            WHERE g.name ~ '[^a-zA-Z0-9 -]'
                               OR g.name ~ '^[0-9]+$'
                               OR char_length(g.name) > 40
                            LIMIT :batch_size
                        )
                        """
                    ),
                    {"batch_size": batch_size},
                )
                deleted = typing.cast(sqlalchemy.engine.CursorResult, result).rowcount
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Invalid genre name cleanup batch failed: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break
            await asyncio.sleep(5)
            continue

        consecutive_failures = 0
        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def run_cleanup_cycle(
    session_factory: SessionFactory,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, typing.Any]:
    book_batch = app.config.settings.cleanup_book_batch_size
    author_batch = app.config.settings.cleanup_author_batch_size
    series_batch = app.config.settings.cleanup_series_batch_size
    genre_batch = app.config.settings.cleanup_genre_batch_size
    min_quality = app.config.settings.cleanup_book_min_quality_score
    engagement_threshold = app.config.settings.cleanup_book_engagement_threshold
    min_publication_year = app.config.settings.cleanup_book_min_publication_year
    genre_min_book_count = app.config.settings.cleanup_genre_min_book_count
    min_author_books = app.config.settings.cleanup_author_min_books
    max_author_books = app.config.settings.cleanup_author_max_books
    min_series_books = app.config.settings.cleanup_series_min_books
    max_series_books = app.config.settings.cleanup_series_max_books

    stats: typing.Dict[str, typing.Any] = {
        "names_healed": {"books_healed": 0, "authors_healed": 0},
        "books": {"deleted": 0},
        "duplicates": {"deleted": 0},
        "authors": {"deleted": 0},
        "series": {"linked": 0, "unlinked": 0, "rows_created": 0, "rows_deleted": 0},
        "genres_normalized": 0,
        "genres_deleted": 0,
        "underrepresented_genres_deleted": 0,
        "invalid_name_genres_deleted": 0,
    }

    stats["names_healed"] = await heal_entity_names(
        session_factory, book_batch, stop_check
    )
    if stop_check():
        return stats

    stats["books"] = await cleanup_low_quality_books(
        session_factory,
        min_quality,
        engagement_threshold,
        min_publication_year,
        book_batch,
        stop_check,
    )
    if stop_check():
        return stats

    stats["duplicates"] = await cleanup_duplicate_books(
        session_factory, book_batch, stop_check
    )
    if stop_check():
        return stats

    stats["authors"] = await cleanup_orphan_authors(
        session_factory, min_author_books, max_author_books, author_batch, stop_check
    )
    if stop_check():
        return stats

    stats["series"] = await consolidate_series(
        session_factory, min_series_books, max_series_books, series_batch, stop_check
    )
    if stop_check():
        return stats

    stats["genres_normalized"] = await normalize_and_merge_genres(
        session_factory, genre_batch, stop_check
    )
    if stop_check():
        return stats

    stats["genres_deleted"] = await cleanup_orphan_genres(
        session_factory, genre_batch, stop_check
    )
    if stop_check():
        return stats

    stats["underrepresented_genres_deleted"] = await cleanup_underrepresented_genres(
        session_factory, genre_min_book_count, genre_batch, stop_check
    )
    if stop_check():
        return stats

    stats["invalid_name_genres_deleted"] = await cleanup_invalid_genre_names(
        session_factory, genre_batch, stop_check
    )

    return stats


_CLEANUP_RUNNING_KEY = "cleanup_running"
_CLEANUP_RUNNING_TTL = 7200


async def run_cleanup_job(force: bool = False) -> None:
    if not force and not app.config.settings.cleanup_enabled:
        return

    redis_client: typing.Optional[redis.Redis] = None
    try:
        redis_client = _create_redis_client()
    except Exception as e:
        logger.warning(f"[cleanup] Failed to connect to Redis: {e}")

    try:
        if redis_client is not None and redis_client.get(_DUMP_RUNNING_KEY):
            logger.info("Skipping cleanup cycle: dump import in progress")
            return

        if redis_client is not None:
            redis_client.set(_CLEANUP_RUNNING_KEY, "1", ex=_CLEANUP_RUNNING_TTL)

        def stop_check() -> bool:
            if redis_client is None:
                return False
            try:
                return bool(redis_client.get(_DUMP_RUNNING_KEY))
            except Exception:
                return False

        stats = await run_cleanup_cycle(app.models.AsyncSessionLocal, stop_check)

        logger.info(
            f"[cleanup] Cycle complete: "
            f"{stats['books']['deleted']} books, "
            f"{stats['duplicates']['deleted']} duplicate books, "
            f"{stats['authors']['deleted']} authors, "
            f"series linked={stats['series']['linked']} unlinked={stats['series']['unlinked']} "
            f"rows_created={stats['series']['rows_created']} rows_deleted={stats['series']['rows_deleted']}, "
            f"{stats['genres_normalized']} genres normalized, "
            f"{stats['genres_deleted']} orphan genres, "
            f"{stats['underrepresented_genres_deleted']} underrepresented genres, "
            f"{stats['invalid_name_genres_deleted']} invalid name genres deleted"
        )

    except Exception as e:
        logger.error(f"[cleanup] Cleanup cycle failed: {str(e)}")
    finally:
        if redis_client is not None:
            try:
                redis_client.delete(_CLEANUP_RUNNING_KEY)
            except Exception:
                pass
            redis_client.close()
