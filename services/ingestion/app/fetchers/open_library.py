import logging
import typing # Dict, Any, Optional
from datetime import datetime
from app.fetchers.base import BaseFetcher
import app.config
from app.utils import slugify

logger = logging.getLogger(__name__)


class OpenLibraryFetcher(BaseFetcher):
    def __init__(self):
        super().__init__(
            api_url=app.config.settings.open_library_api_url,
            rate_limit=app.config.settings.open_library_rate_limit
        )
        self.subjects = [
            "science_fiction",
            "fantasy",
            "mystery",
            "thriller",
            "romance",
            "historical_fiction",
            "biography",
            "history",
            "philosophy",
            "psychology"
        ]

    async def fetch_books(self, count: int, language: str = "en") -> list[typing.Dict[str, Any]]:
        books = []
        per_subject = max(count // len(self.subjects), 10)

        for subject in self.subjects:
            if len(books) >= count:
                break

            url = f"{self.api_url}/subjects/{subject}.json"
            params = {"limit": per_subject, "offset": 0}

            data = await self._fetch_with_retry(url, params)
            if not data or "works" not in data:
                continue

            for work in data["works"]:
                if len(books) >= count:
                    break

                parsed = await self.parse_book_data(work, language)
                if parsed:
                    books.append(parsed)

        return books[:count]

    async def parse_book_data(self, raw_data: typing.typing.Dict[str, Any], language: str = "en") -> typing.Optional[typing.Dict[str, Any]]:
        try:
            work_key = raw_data.get("key")
            if not work_key:
                return None

            work_data = await self._fetch_work_details(work_key)
            if not work_data:
                return None

            title = work_data.get("title") or raw_data.get("title")
            if not title:
                return None

            authors = []
            for author_ref in raw_data.get("authors", []):
                author_key = author_ref.get("key")
                if author_key:
                    author_data = await self._fetch_author_details(author_key)
                    if author_data:
                        authors.append({
                            "name": author_data.get("name"),
                            "slug": slugify(author_data.get("name")),
                            "bio": author_data.get("bio", {}).get("value") if isinstance(author_data.get("bio"), dict) else author_data.get("bio"),
                            "birth_date": author_data.get("birth_date"),
                            "death_date": author_data.get("death_date"),
                            "photo_url": self._get_author_photo_url(author_data),
                            "open_library_id": author_key.split("/")[-1]
                        })

            cover_id = raw_data.get("cover_id") or work_data.get("covers", [None])[0]
            primary_cover_url = self._get_cover_url(cover_id) if cover_id else None

            genres = []
            for subject in work_data.get("subjects", [])[:5]:
                genres.append({
                    "name": subject,
                    "slug": slugify(subject)
                })

            formats = self._extract_formats(work_data)
            cover_history = self._extract_cover_history(work_data, cover_id)

            return {
                "title": title,
                "language": language,
                "slug": slugify(title),
                "description": self._extract_description(work_data),
                "original_publication_year": self._extract_publication_year(work_data),
                "formats": formats,
                "cover_history": cover_history,
                "primary_cover_url": primary_cover_url,
                "open_library_id": work_key.split("/")[-1],
                "authors": authors,
                "genres": genres
            }

        except Exception as e:
            logger.error(f"Error parsing Open Library book data: {str(e)}")
            return None

    async def _fetch_work_details(self, work_key: str) -> typing.Optional[typing.Dict[str, Any]]:
        url = f"{self.api_url}{work_key}.json"
        return await self._fetch_with_retry(url)

    async def _fetch_author_details(self, author_key: str) -> typing.Optional[typing.Dict[str, Any]]:
        url = f"{self.api_url}{author_key}.json"
        return await self._fetch_with_retry(url)

    def _get_cover_url(self, cover_id: int, size: str = "L") -> str:
        return f"https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg"

    def _get_author_photo_url(self, author_data: typing.typing.Dict[str, Any]) -> typing.Optional[str]:
        photos = author_data.get("photos")
        if photos and len(photos) > 0:
            return f"https://covers.openlibrary.org/a/id/{photos[0]}-L.jpg"
        return None

    def _extract_description(self, work_data: typing.typing.Dict[str, Any]) -> typing.Optional[str]:
        description = work_data.get("description")
        if isinstance(description, dict):
            return description.get("value")
        return description

    def _extract_publication_year(self, work_data: typing.typing.Dict[str, Any]) -> typing.Optional[int]:
        first_publish = work_data.get("first_publish_date")
        if first_publish:
            try:
                if len(first_publish) >= 4 and first_publish[:4].isdigit():
                    return int(first_publish[:4])
            except (ValueError, TypeError):
                pass
        return None

    def _extract_formats(self, work_data: typing.typing.Dict[str, Any]) -> list[str]:
        formats = set()

        editions = work_data.get("editions", {}).get("entries", [])
        for edition in editions[:10]:
            format_type = edition.get("physical_format", "").lower()
            if "hardcover" in format_type:
                formats.add("hardcover")
            elif "paperback" in format_type or "softcover" in format_type:
                formats.add("paperback")
            elif "ebook" in format_type or "kindle" in format_type:
                formats.add("ebook")
            elif "audiobook" in format_type or "audio" in format_type:
                formats.add("audiobook")

        if not formats:
            formats.add("paperback")

        return list(formats)

    def _extract_cover_history(self, work_data: typing.typing.Dict[str, Any], primary_cover_id: typing.typing.Optional[int]) -> list[typing.Dict[str, Any]]:
        cover_history = []

        if primary_cover_id:
            year = self._extract_publication_year(work_data) or datetime.now().year
            cover_history.append({
                "year": year,
                "cover_url": self._get_cover_url(primary_cover_id),
                "publisher": "Unknown"
            })

        editions = work_data.get("editions", {}).get("entries", [])
        for edition in editions[:5]:
            covers = edition.get("covers", [])
            if covers and covers[0]:
                year = self._extract_publication_year(edition) or datetime.now().year
                cover_history.append({
                    "year": year,
                    "cover_url": self._get_cover_url(covers[0]),
                    "publisher": ", ".join(edition.get("publishers", ["Unknown"]))
                })

        cover_history.sort(key=lambda x: x["year"])

        return cover_history
