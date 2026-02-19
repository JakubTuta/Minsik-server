import logging
import typing
from datetime import datetime

import app.config
from app.fetchers.base import BaseFetcher
from app.utils import slugify

logger = logging.getLogger(__name__)


class OpenLibraryFetcher(BaseFetcher):
    def __init__(self):
        super().__init__(
            api_url=app.config.settings.open_library_api_url,
            rate_limit=app.config.settings.open_library_rate_limit,
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
            "psychology",
        ]

    async def fetch_books(
        self, count: int, language: str = "en", offset: int = 0
    ) -> list[typing.Dict[str, typing.Any]]:
        books = []
        per_subject = max(count // len(self.subjects), 10)
        subject_offset = offset // len(self.subjects)

        for subject in self.subjects:
            if len(books) >= count:
                break

            url = f"{self.api_url}/subjects/{subject}.json"
            params = {"limit": per_subject, "offset": subject_offset}

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

    async def search_book(
        self, title: str, author: str, limit: int = 10
    ) -> list[typing.Dict[str, typing.Any]]:
        books = []

        url = f"{self.api_url}/search.json"
        params = {"title": title, "author": author, "limit": limit}

        data = await self._fetch_with_retry(url, params)
        if not data or "docs" not in data:
            return books

        for doc in data["docs"][:limit]:
            try:
                work_key = doc.get("key")
                if not work_key:
                    continue

                book_title = doc.get("title")
                if not book_title:
                    continue

                author_names = doc.get("author_name", [])
                isbn_list = doc.get("isbn", [])

                cover_id = doc.get("cover_i")
                cover_url = self._get_cover_url(cover_id) if cover_id else None

                publication_year = doc.get("first_publish_year")

                page_count = doc.get("number_of_pages_median")

                publishers = doc.get("publisher", [])
                publisher = publishers[0] if publishers else None

                subjects = doc.get("subject", [])[:5]

                languages = doc.get("language", [])
                language = languages[0] if languages else "en"

                books.append(
                    {
                        "title": book_title,
                        "authors": author_names,
                        "description": None,
                        "publication_year": publication_year,
                        "language": language,
                        "page_count": page_count,
                        "cover_url": cover_url,
                        "isbn": isbn_list[:5],
                        "publisher": publisher,
                        "genres": subjects,
                        "open_library_id": (
                            work_key.split("/")[-1] if work_key else None
                        ),
                        "google_books_id": None,
                        "source": "open_library",
                    }
                )

            except Exception as e:
                logger.error(f"Error parsing search result: {str(e)}")
                continue

        return books

    async def parse_book_data(
        self, raw_data: typing.Dict[str, typing.Any], language: str = "en"
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
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
                        remote_ids = {}
                        raw_remote = author_data.get("remote_ids")
                        if isinstance(raw_remote, dict):
                            for k, v in raw_remote.items():
                                if isinstance(v, str) and v:
                                    remote_ids[k] = v

                        wikidata_id = remote_ids.get("wikidata")

                        alt_names = author_data.get("alternate_names", [])
                        if not isinstance(alt_names, list):
                            alt_names = []
                        alt_names = [n for n in alt_names if isinstance(n, str) and n][
                            :20
                        ]

                        wikipedia_url = author_data.get("wikipedia")
                        if isinstance(
                            wikipedia_url, str
                        ) and not wikipedia_url.startswith("http"):
                            wikipedia_url = None

                        authors.append(
                            {
                                "name": author_data.get("name"),
                                "slug": slugify(author_data.get("name")),
                                "bio": (
                                    author_data.get("bio", {}).get("value")
                                    if isinstance(author_data.get("bio"), dict)
                                    else author_data.get("bio")
                                ),
                                "birth_date": author_data.get("birth_date"),
                                "death_date": author_data.get("death_date"),
                                "photo_url": self._get_author_photo_url(author_data),
                                "open_library_id": author_key.split("/")[-1],
                                "wikidata_id": wikidata_id,
                                "wikipedia_url": wikipedia_url,
                                "remote_ids": remote_ids,
                                "alternate_names": alt_names,
                            }
                        )

            cover_id = raw_data.get("cover_id") or work_data.get("covers", [None])[0]
            primary_cover_url = self._get_cover_url(cover_id) if cover_id else None

            genres = []
            for subject in work_data.get("subjects", [])[:5]:
                genres.append({"name": subject, "slug": slugify(subject)})

            formats = self._extract_formats(work_data)
            cover_history = self._extract_cover_history(work_data, cover_id)

            editions_data = await self._fetch_editions(work_key)
            series_info = self._extract_series_from_editions(editions_data)
            edition_metadata = self._extract_best_edition_metadata(editions_data)

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
                "genres": genres,
                "series": series_info,
                "isbn": edition_metadata["isbn"],
                "publisher": edition_metadata["publisher"],
                "number_of_pages": edition_metadata["number_of_pages"],
                "external_ids": edition_metadata["external_ids"],
            }

        except Exception as e:
            logger.error(f"Error parsing Open Library book data: {str(e)}")
            return None

    async def _fetch_work_details(
        self, work_key: str
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        url = f"{self.api_url}{work_key}.json"
        return await self._fetch_with_retry(url)

    async def _fetch_author_details(
        self, author_key: str
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        url = f"{self.api_url}{author_key}.json"
        return await self._fetch_with_retry(url)

    def _get_cover_url(self, cover_id: int, size: str = "L") -> str:
        return f"https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg"

    def _get_author_photo_url(
        self, author_data: typing.Dict[str, typing.Any]
    ) -> typing.Optional[str]:
        photos = author_data.get("photos")
        if photos and len(photos) > 0:
            return f"https://covers.openlibrary.org/a/id/{photos[0]}-L.jpg"
        return None

    def _extract_description(
        self, work_data: typing.Dict[str, typing.Any]
    ) -> typing.Optional[str]:
        description = work_data.get("description")
        if isinstance(description, dict):
            return description.get("value")
        return description

    def _extract_publication_year(
        self, work_data: typing.Dict[str, typing.Any]
    ) -> typing.Optional[int]:
        first_publish = work_data.get("first_publish_date")
        if first_publish:
            try:
                if len(first_publish) >= 4 and first_publish[:4].isdigit():
                    return int(first_publish[:4])
            except (ValueError, TypeError):
                pass
        return None

    def _extract_formats(self, work_data: typing.Dict[str, typing.Any]) -> list[str]:
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

    def _extract_cover_history(
        self,
        work_data: typing.Dict[str, typing.Any],
        primary_cover_id: typing.Optional[int],
    ) -> list[typing.Dict[str, typing.Any]]:
        cover_history = []

        if primary_cover_id:
            year = self._extract_publication_year(work_data) or datetime.now().year
            cover_history.append(
                {
                    "year": year,
                    "cover_url": self._get_cover_url(primary_cover_id),
                    "publisher": "Unknown",
                }
            )

        editions = work_data.get("editions", {}).get("entries", [])
        for edition in editions[:5]:
            covers = edition.get("covers", [])
            if covers and covers[0]:
                year = self._extract_publication_year(edition) or datetime.now().year
                cover_history.append(
                    {
                        "year": year,
                        "cover_url": self._get_cover_url(covers[0]),
                        "publisher": ", ".join(edition.get("publishers", ["Unknown"])),
                    }
                )

        cover_history.sort(key=lambda x: x["year"])

        return cover_history

    async def _fetch_editions(
        self, work_key: str
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        try:
            editions_url = f"{self.api_url}{work_key}/editions.json"
            return await self._fetch_with_retry(editions_url, {"limit": 10})
        except Exception as e:
            logger.debug(f"Error fetching editions for {work_key}: {str(e)}")
            return None

    def _extract_series_from_editions(
        self, editions_data: typing.Optional[typing.Dict[str, typing.Any]]
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        if not editions_data or "entries" not in editions_data:
            return None

        for edition in editions_data["entries"]:
            series_list = edition.get("series")
            if series_list and len(series_list) > 0:
                parsed = self._parse_series_string(series_list[0])
                if parsed:
                    return parsed
        return None

    def _extract_best_edition_metadata(
        self, editions_data: typing.Optional[typing.Dict[str, typing.Any]]
    ) -> typing.Dict[str, typing.Any]:
        result: typing.Dict[str, typing.Any] = {
            "isbn": [],
            "publisher": None,
            "number_of_pages": None,
            "external_ids": {},
        }
        if not editions_data or "entries" not in editions_data:
            return result

        all_isbns: list[str] = []
        best_score = -1
        best_edition: typing.Optional[typing.Dict[str, typing.Any]] = None

        for edition in editions_data["entries"]:
            score = 0
            for isbn10 in edition.get("isbn_10") or []:
                if isinstance(isbn10, str) and isbn10:
                    all_isbns.append(isbn10)
                    score += 1
            for isbn13 in edition.get("isbn_13") or []:
                if isinstance(isbn13, str) and isbn13:
                    all_isbns.append(isbn13)
                    score += 1
            pages = edition.get("number_of_pages")
            if isinstance(pages, int) and pages > 0:
                score += 1
            if edition.get("publishers"):
                score += 1
            if edition.get("covers"):
                score += 1

            if score > best_score:
                best_score = score
                best_edition = edition

        seen: set[str] = set()
        unique_isbns: list[str] = []
        for isbn in all_isbns:
            if isbn not in seen:
                seen.add(isbn)
                unique_isbns.append(isbn)
        result["isbn"] = unique_isbns[:20]

        if best_edition:
            pages = best_edition.get("number_of_pages")
            if isinstance(pages, int) and pages > 0:
                result["number_of_pages"] = pages

            publishers = best_edition.get("publishers", [])
            if (
                publishers
                and isinstance(publishers, list)
                and isinstance(publishers[0], str)
            ):
                result["publisher"] = publishers[0][:500]

            identifiers = best_edition.get("identifiers", {})
            if isinstance(identifiers, dict):
                ext_ids: dict[str, str] = {}
                for id_key, id_vals in identifiers.items():
                    if (
                        isinstance(id_vals, list)
                        and id_vals
                        and isinstance(id_vals[0], str)
                    ):
                        ext_ids[id_key] = id_vals[0]
                if ext_ids:
                    result["external_ids"] = ext_ids

        return result

    def _parse_series_string(
        self, series_str: str
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        try:
            if not series_str or not isinstance(series_str, str):
                return None

            series_str = series_str.strip()

            if "#" in series_str:
                parts = series_str.split("#")
                name = parts[0].strip().rstrip(",").strip()

                position_str = parts[1].strip()
                position = None

                try:
                    if "." in position_str:
                        position = float(position_str)
                    else:
                        position = float(position_str.split()[0])
                except (ValueError, IndexError):
                    position = None

                return {"name": name, "slug": slugify(name), "position": position}
            else:
                return {
                    "name": series_str,
                    "slug": slugify(series_str),
                    "position": None,
                }

        except Exception as e:
            logger.error(f"Error parsing series string '{series_str}': {str(e)}")
            return None
