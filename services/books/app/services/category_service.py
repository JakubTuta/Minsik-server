import json
import logging
import re
from typing import Dict, List, Optional, Set, Tuple

import app.cache
import app.categories_config
import app.config
import app.db
import app.models.genre
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

CATEGORY_TOP_BOOKS_CACHE_KEY = "category:top20:{category_slug}:{sort_by}:desc:{language}"
CATEGORY_TOP_BOOKS_LANGUAGES = ["en"]
CATEGORY_TOP_BOOKS_SORT_OPTIONS = ["popularity", "rating"]
POPULAR_CATEGORIES_CACHE_KEY = "categories:popular:v2"
POPULAR_CATEGORIES_CACHE_TTL = 172800


class CategoryService:
    def __init__(self):
        self._category_genre_ids: Dict[str, Set[int]] = {}
        self._is_ready = False

    async def setup(self):
        logger.info("Initializing CategoryService mappings...")

        async with app.db.async_session_maker() as session:
            stmt = sqlalchemy.select(
                app.models.genre.Genre.genre_id,
                app.models.genre.Genre.name,
                app.models.genre.Genre.slug,
            )
            result = await session.execute(stmt)
            all_genres = result.all()

            self._category_genre_ids.clear()

            for cat_slug, config in app.categories_config.CATEGORIES.items():
                cat_genre_ids = set()

                for genre_id, name, slug in all_genres:
                    name_lower = name.lower()
                    if slug in config.exact_slugs or any(
                        re.search(r"\b" + re.escape(kw) + r"\b", name_lower)
                        for kw in config.keywords
                    ):
                        cat_genre_ids.add(genre_id)

                self._category_genre_ids[cat_slug] = cat_genre_ids

            self._is_ready = True
            logger.info(
                f"CategoryService mappings initialized. Cached {len(self._category_genre_ids)} categories."
            )

    def get_categories(self) -> List[dict]:
        return [
            {"slug": cat.slug, "name": cat.name}
            for cat in app.categories_config.CATEGORIES.values()
        ]

    def get_category(self, slug: str) -> Optional[dict]:
        if slug not in app.categories_config.CATEGORIES:
            return None

        cat = app.categories_config.CATEGORIES[slug]
        return {"slug": cat.slug, "name": cat.name}

    async def populate_category_top_books_cache(self) -> None:
        logger.info("Populating category top books cache...")

        for category_slug in app.categories_config.CATEGORIES:
            for language in CATEGORY_TOP_BOOKS_LANGUAGES:
                for sort_by in CATEGORY_TOP_BOOKS_SORT_OPTIONS:
                    try:
                        books, total_count = await self._fetch_category_books_from_db(
                            category_slug=category_slug,
                            limit=20,
                            offset=0,
                            language=language,
                            sort_by=sort_by,
                            order="desc",
                        )
                        cache_key = CATEGORY_TOP_BOOKS_CACHE_KEY.format(
                            category_slug=category_slug,
                            sort_by=sort_by,
                            language=language,
                        )
                        await app.cache.set_cached(
                            cache_key,
                            {"books": books, "total_count": total_count},
                            app.config.settings.cache_category_top_books_ttl,
                        )
                    except Exception as e:
                        logger.error(
                            f"Error caching top books for category {category_slug} "
                            f"sort={sort_by} lang={language}: {str(e)}"
                        )

        logger.info("Category top books cache populated.")

    async def get_category_books(
        self,
        category_slug: str,
        limit: int = 20,
        offset: int = 0,
        language: str = "en",
        sort_by: str = "popularity",
        order: str = "desc",
    ) -> Tuple[List[dict], int]:
        if not self._is_ready:
            await self.setup()

        if category_slug not in app.categories_config.CATEGORIES:
            return [], 0

        if offset == 0 and limit <= 20 and order == "desc":
            cache_key = CATEGORY_TOP_BOOKS_CACHE_KEY.format(
                category_slug=category_slug,
                sort_by=sort_by,
                language=language,
            )
            cached = await app.cache.get_cached(cache_key)
            if cached is not None:
                return cached["books"][:limit], cached["total_count"]

        return await self._fetch_category_books_from_db(
            category_slug=category_slug,
            limit=limit,
            offset=offset,
            language=language,
            sort_by=sort_by,
            order=order,
        )

    async def _fetch_category_books_from_db(
        self,
        category_slug: str,
        limit: int,
        offset: int,
        language: str,
        sort_by: str,
        order: str,
    ) -> Tuple[List[dict], int]:
        genre_ids = self._category_genre_ids.get(category_slug, set())

        if not genre_ids:
            return [], 0

        if sort_by not in {"popularity", "rating"}:
            sort_by = "popularity"

        genre_ids_list = list(genre_ids)

        if sort_by == "popularity":
            sort_col = (
                "COALESCE(b.rating_count, 0)"
                " + COALESCE(b.ol_rating_count, 0)"
                " + COALESCE(b.ol_want_to_read_count, 0)"
                " + COALESCE(b.ol_currently_reading_count, 0)"
                " + COALESCE(b.ol_already_read_count, 0)"
            )
        else:
            sort_col = (
                "CASE"
                " WHEN COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0) = 0 THEN 0"
                " ELSE ("
                "   COALESCE(b.avg_rating, 0) * COALESCE(b.rating_count, 0)"
                "   + COALESCE(b.ol_avg_rating, 0) * COALESCE(b.ol_rating_count, 0)"
                " ) / (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0))"
                " END"
            )

        order_dir = "DESC" if order.lower() == "desc" else "ASC"

        books_query = sqlalchemy.text(
            f"""
            SELECT
                b.book_id,
                b.title,
                b.slug,
                b.description,
                b.original_publication_year,
                b.primary_cover_url,
                b.rating_count,
                b.avg_rating,
                b.ol_rating_count,
                b.ol_avg_rating,
                b.ol_want_to_read_count,
                b.ol_currently_reading_count,
                b.ol_already_read_count,
                (
                    SELECT COALESCE(json_agg(json_build_object(
                        'author_id', a2.author_id,
                        'name', a2.name,
                        'slug', a2.slug,
                        'photo_url', a2.photo_url
                    )), '[]'::json)
                    FROM books.book_authors ba2
                    JOIN books.authors a2 ON ba2.author_id = a2.author_id
                    WHERE ba2.book_id = b.book_id
                ) AS authors
            FROM books.books b
            WHERE b.language = :language
              AND b.primary_cover_url IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM books.book_genres bg
                WHERE bg.book_id = b.book_id AND bg.genre_id = ANY(:genre_ids)
            )
            ORDER BY {sort_col} {order_dir} NULLS LAST, b.book_id DESC
            LIMIT :limit OFFSET :offset
            """
        )

        count_query = sqlalchemy.text(
            """
            SELECT COUNT(*)
            FROM books.books b
            WHERE b.language = :language
              AND b.primary_cover_url IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM books.book_genres bg
                WHERE bg.book_id = b.book_id AND bg.genre_id = ANY(:genre_ids)
            )
            """
        )

        base_params = {"language": language, "genre_ids": genre_ids_list}

        async with app.db.async_session_maker() as session:
            async with session.begin():
                count_result = await session.execute(count_query, base_params)
                total_count = count_result.scalar() or 0

                books_result = await session.execute(
                    books_query,
                    {**base_params, "limit": limit, "offset": offset},
                )
                raw_rows = books_result.fetchall()

        books_data = []
        for row in raw_rows:
            authors_raw = row.authors
            if isinstance(authors_raw, str):
                authors_list = json.loads(authors_raw)
            elif authors_raw is None:
                authors_list = []
            else:
                authors_list = authors_raw

            books_data.append(
                {
                    "book_id": row.book_id,
                    "title": row.title,
                    "slug": row.slug,
                    "description": row.description or "",
                    "original_publication_year": int(
                        row.original_publication_year or 0
                    ),
                    "primary_cover_url": row.primary_cover_url or "",
                    "rating_count": row.rating_count or 0,
                    "avg_rating": str(row.avg_rating) if row.avg_rating else "0.00",
                    "ol_rating_count": row.ol_rating_count or 0,
                    "ol_avg_rating": (
                        str(row.ol_avg_rating) if row.ol_avg_rating else "0.00"
                    ),
                    "ol_want_to_read_count": row.ol_want_to_read_count or 0,
                    "ol_currently_reading_count": row.ol_currently_reading_count or 0,
                    "ol_already_read_count": row.ol_already_read_count or 0,
                    "authors": authors_list,
                }
            )

        return books_data, total_count


    async def _compute_popular_categories(self) -> List[dict]:
        slug_to_genre_ids: Dict[str, List[int]] = {
            slug: list(genre_ids)
            for slug, genre_ids in self._category_genre_ids.items()
            if genre_ids and slug in app.categories_config.CATEGORIES
        }

        if not slug_to_genre_ids:
            return []

        mapping_rows: List[Tuple[str, int]] = []
        for slug, genre_ids in slug_to_genre_ids.items():
            for gid in genre_ids:
                mapping_rows.append((slug, gid))

        if not mapping_rows:
            return []

        slugs_array = [row[0] for row in mapping_rows]
        gids_array = [row[1] for row in mapping_rows]

        query = sqlalchemy.text(
            """
            WITH cat_map AS (
                SELECT t.slug, t.genre_id
                FROM UNNEST(CAST(:slugs AS text[]), CAST(:gids AS int[])) AS t(slug, genre_id)
            )
            SELECT cm.slug, COUNT(DISTINCT b.book_id) AS book_count
            FROM cat_map cm
            JOIN books.book_genres bg ON bg.genre_id = cm.genre_id
            JOIN books.books b ON b.book_id = bg.book_id
            WHERE b.primary_cover_url IS NOT NULL
            GROUP BY cm.slug
            """
        )

        async with app.db.async_session_maker() as session:
            result = await session.execute(
                query, {"slugs": slugs_array, "gids": gids_array}
            )
            counts: Dict[str, int] = {row.slug: int(row.book_count) for row in result.fetchall()}

        results: List[dict] = []
        for slug in slug_to_genre_ids:
            cat = app.categories_config.CATEGORIES[slug]
            results.append({
                "slug": slug,
                "name": cat.name,
                "book_count": counts.get(slug, 0),
            })

        results.sort(key=lambda x: x["book_count"], reverse=True)
        return results

    async def populate_popular_categories_cache(self) -> None:
        logger.info("Populating popular categories cache...")
        if not self._is_ready:
            await self.setup()
        try:
            results = await self._compute_popular_categories()
            await app.cache.set_cached(
                POPULAR_CATEGORIES_CACHE_KEY, results, POPULAR_CATEGORIES_CACHE_TTL
            )
            logger.info(f"Popular categories cache populated ({len(results)} entries).")
        except Exception as e:
            logger.error(f"Error populating popular categories cache: {str(e)}")
            raise

    async def get_popular_categories(self, limit: int = 12) -> List[dict]:
        if not self._is_ready:
            await self.setup()

        cached = await app.cache.get_cached(POPULAR_CATEGORIES_CACHE_KEY)
        if cached is not None:
            return cached[:limit]

        logger.warning("Popular categories cache miss - computing on demand")
        results = await self._compute_popular_categories()
        await app.cache.set_cached(
            POPULAR_CATEGORIES_CACHE_KEY, results, POPULAR_CATEGORIES_CACHE_TTL
        )
        return results[:limit]


category_service = CategoryService()
