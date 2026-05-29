import datetime
import logging
import typing

import app.config
import app.fetcher_base
import app.utils

logger = logging.getLogger(__name__)


class GoogleBooksFetcher(app.fetcher_base.BaseFetcher):
    def __init__(self):
        super().__init__(
            api_url=app.config.settings.google_books_api_url,
            rate_limit=app.config.settings.open_library_rate_limit,
        )
        self.search_queries = [
            "science fiction",
            "fantasy novels",
            "mystery thriller",
            "romance",
            "historical fiction",
            "biography",
            "philosophy",
            "psychology",
            "business",
            "technology",
        ]

    async def fetch_books(
        self, count: int, language: str = "en", offset: int = 0
    ) -> list[typing.Dict[str, typing.Any]]:
        books = []
        per_query = max(count // len(self.search_queries), 10)
        query_offset = offset // len(self.search_queries)

        for query in self.search_queries:
            if len(books) >= count:
                break

            url = f"{self.api_url}/volumes"
            params = {
                "q": query,
                "langRestrict": language,
                "maxResults": min(per_query, 40),
                "startIndex": query_offset,
                "orderBy": "relevance",
            }

            if app.config.settings.google_books_api_key:
                params["key"] = app.config.settings.google_books_api_key

            data = await self._fetch_with_retry(url, params)
            if not data or "items" not in data:
                continue

            for item in data["items"]:
                if len(books) >= count:
                    break

                parsed = await self.parse_book_data(item, language)
                if parsed:
                    books.append(parsed)

        return books[:count]

    async def parse_book_data(
        self, raw_data: typing.Dict[str, typing.Any], language: str = "en"
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        try:
            volume_info = raw_data.get("volumeInfo", {})

            title = volume_info.get("title")
            if not title:
                return None

            authors = []
            for author_name in volume_info.get("authors", []):
                authors.append(
                    {
                        "name": author_name,
                        "slug": app.utils.slugify(author_name),
                        "bio": None,
                        "birth_date": None,
                        "death_date": None,
                        "photo_url": None,
                        "open_library_id": None,
                    }
                )

            image_links = volume_info.get("imageLinks", {})
            primary_cover_url = (
                image_links.get("extraLarge")
                or image_links.get("large")
                or image_links.get("medium")
                or image_links.get("thumbnail")
            )

            genres = []
            for category in volume_info.get("categories", [])[:5]:
                canonical_name, canonical_slug = app.utils.canonicalize_genre_name(category)
                genres.append({"name": canonical_name, "slug": canonical_slug})

            formats = self._extract_formats(raw_data)

            published_date = volume_info.get("publishedDate", "")
            publication_year = None
            if published_date:
                try:
                    if len(published_date) >= 4 and published_date[:4].isdigit():
                        publication_year = int(published_date[:4])
                except (ValueError, TypeError):
                    pass

            isbn_list: list[str] = []
            for identifier in volume_info.get("industryIdentifiers", []):
                if identifier.get("type") in ("ISBN_10", "ISBN_13"):
                    isbn_val = identifier.get("identifier")
                    if isinstance(isbn_val, str) and isbn_val:
                        isbn_list.append(isbn_val)

            publisher = volume_info.get("publisher")
            if isinstance(publisher, str):
                publisher = publisher[:500]
            else:
                publisher = None

            page_count = volume_info.get("pageCount")
            if not isinstance(page_count, int) or page_count <= 0:
                page_count = None

            external_ids: dict[str, str] = {}
            for identifier in volume_info.get("industryIdentifiers", []):
                id_type = identifier.get("type")
                id_val = identifier.get("identifier")
                if id_type and id_val and id_type not in ("ISBN_10", "ISBN_13"):
                    external_ids[id_type] = id_val

            return {
                "title": title,
                "language": language,
                "slug": app.utils.slugify(title),
                "description": volume_info.get("description"),
                "original_publication_year": publication_year,
                "formats": formats,
                "primary_cover_url": primary_cover_url,
                "google_books_id": raw_data.get("id"),
                "authors": authors,
                "genres": genres,
                "isbn": isbn_list,
                "publisher": publisher,
                "number_of_pages": page_count,
                "external_ids": external_ids,
            }

        except Exception as e:
            logger.error(f"Error parsing Google Books data: {str(e)}")
            return None

    def _extract_formats(self, raw_data: typing.Dict[str, typing.Any]) -> list[str]:
        formats = set()

        access_info = raw_data.get("accessInfo", {})
        epub_available = access_info.get("epub", {}).get("isAvailable", False)
        pdf_available = access_info.get("pdf", {}).get("isAvailable", False)

        if epub_available or pdf_available:
            formats.add("ebook")

        volume_info = raw_data.get("volumeInfo", {})
        print_type = volume_info.get("printType", "").lower()

        if print_type == "book":
            formats.add("paperback")

        if not formats:
            formats.add("paperback")

        return list(formats)

