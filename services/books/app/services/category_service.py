import logging
from typing import Dict, List, Optional, Set, Tuple

from app.categories_config import CATEGORIES
from app.db import async_session_maker
from app.models.book import Book
from app.models.book_genre import BookGenre
from app.models.genre import Genre
from sqlalchemy import select, text

logger = logging.getLogger(__name__)


class CategoryService:
    def __init__(self):
        # Maps category_slug -> set of genre_ids
        self._category_genre_ids: Dict[str, Set[int]] = {}
        # Maps (category_slug, sub_genre_slug) -> set of genre_ids
        self._sub_genre_ids: Dict[Tuple[str, str], Set[int]] = {}
        self._is_ready = False

    async def setup(self):
        """Pre-calculate genre mappings on startup to ensure fast lookups later."""
        logger.info("Initializing CategoryService mappings...")

        async with async_session_maker() as session:
            # Fetch all genres (could be large, but acceptable for startup cache)
            stmt = select(Genre.genre_id, Genre.name, Genre.slug)
            result = await session.execute(stmt)
            all_genres = result.all()

            # Reset caches
            self._category_genre_ids.clear()
            self._sub_genre_ids.clear()

            for cat_slug, config in CATEGORIES.items():
                cat_genre_ids = set()

                # Match main category
                for genre_id, name, slug in all_genres:
                    name_lower = name.lower()
                    if slug in config.exact_slugs or any(
                        kw in name_lower for kw in config.keywords
                    ):
                        cat_genre_ids.add(genre_id)

                self._category_genre_ids[cat_slug] = cat_genre_ids

                # Match sub-genres
                for sub_genre in config.sub_genres:
                    sub_genre_ids = set()
                    for genre_id, name, slug in all_genres:
                        name_lower = name.lower()
                        if slug in sub_genre.exact_slugs or any(
                            kw in name_lower for kw in sub_genre.keywords
                        ):
                            sub_genre_ids.add(genre_id)

                    self._sub_genre_ids[(cat_slug, sub_genre.slug)] = sub_genre_ids

            self._is_ready = True
            logger.info(
                f"CategoryService mappings initialized. Cached {len(self._category_genre_ids)} categories."
            )

    def get_categories(self) -> List[dict]:
        """Return all categories with their basic info."""
        return [
            {
                "slug": cat.slug,
                "name": cat.name,
                "icon": cat.icon,
                "sub_genres": [
                    {"slug": sg.slug, "name": sg.name} for sg in cat.sub_genres
                ],
            }
            for cat in CATEGORIES.values()
        ]

    def get_category(self, slug: str) -> Optional[dict]:
        if slug not in CATEGORIES:
            return None

        cat = CATEGORIES[slug]
        return {
            "slug": cat.slug,
            "name": cat.name,
            "icon": cat.icon,
            "sub_genres": [{"slug": sg.slug, "name": sg.name} for sg in cat.sub_genres],
        }

    async def get_category_books(
        self,
        category_slug: str,
        sub_genre_slug: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        language: str = "en",
        sort_by: str = "popularity",
        order: str = "desc",
    ) -> Tuple[List[dict], int]:
        if not self._is_ready:
            # Fallback if not initialized
            await self.setup()

        if category_slug not in CATEGORIES:
            return [], 0

        # Determine which set of genre IDs to use
        genre_ids = set()
        if sub_genre_slug:
            genre_ids = self._sub_genre_ids.get((category_slug, sub_genre_slug), set())
        else:
            genre_ids = self._category_genre_ids.get(category_slug, set())

        if not genre_ids:
            return [], 0

        # Ensure array format for SQL IN clause
        genre_ids_list = list(genre_ids)

        # Determine sort column
        sort_col = "b.rating_count"
        if sort_by == "popularity":
            # Approximation of popularity using total ratings
            sort_col = "b.rating_count + b.ol_rating_count"
        elif sort_by == "rating":
            sort_col = "b.avg_rating"

        order_dir = "DESC" if order.lower() == "desc" else "ASC"

        books_query = text(
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
            AND EXISTS (
                SELECT 1 FROM books.book_genres bg 
                WHERE bg.book_id = b.book_id AND bg.genre_id = ANY(:genre_ids)
            )
            ORDER BY {{sort_col}} {{order_dir}} NULLS LAST
            LIMIT :limit OFFSET :offset
            """.replace(
                "{sort_col}", sort_col
            ).replace(
                "{order_dir}", order_dir
            )
        )

        count_query = text(
            """
            SELECT COUNT(*) 
            FROM books.books b
            WHERE b.language = :language
            AND EXISTS (
                SELECT 1 FROM books.book_genres bg 
                WHERE bg.book_id = b.book_id AND bg.genre_id = ANY(:genre_ids)
            )
            """
        )

        async with async_session_maker() as session:
            count_result = await session.execute(
                count_query, {"language": language, "genre_ids": genre_ids_list}
            )
            total_count = count_result.scalar() or 0

            books_result = await session.execute(
                books_query,
                {
                    "language": language,
                    "genre_ids": genre_ids_list,
                    "limit": limit,
                    "offset": offset,
                },
            )

            books_data = []
            for row in books_result.fetchall():
                import json

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
                        "ol_currently_reading_count": row.ol_currently_reading_count
                        or 0,
                        "ol_already_read_count": row.ol_already_read_count or 0,
                        "authors": authors_list,
                    }
                )

            return books_data, total_count


category_service = CategoryService()
