import datetime
import html
import re
import typing
import unicodedata
import uuid

import app.data.genre_synonyms
import dateutil.parser
import text_unidecode


def resolve_work_id(
    external_ids: typing.Optional[typing.Dict[str, typing.Any]],
    open_library_id: typing.Optional[str],
    slug: str,
    google_books_id: typing.Optional[str] = None,
) -> str:
    """Identity shared by every language edition of one book.

    The OpenLibrary work id when the book has one. Otherwise the Google Books id,
    which at least never merges two different books that happen to share a title;
    the title slug is the last resort.
    """
    work_ol_id = (external_ids or {}).get("work_ol_id")
    if work_ol_id or open_library_id:
        return work_ol_id or open_library_id
    if google_books_id:
        return f"gb:{google_books_id}"
    return slug


def slugify(text: str, max_length: int = 200) -> str:
    if not text:
        return ""

    text = text_unidecode.unidecode(text)

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = text.lower()

    text = re.sub(r"[^\w\s-]", "", text)

    text = re.sub(r"[-\s]+", "-", text)

    text = text.strip("-")

    if not text:
        return uuid.uuid4().hex[:16]

    return text[:max_length]


_NAME_EDGE_JUNK = re.compile(
    r"^[\s,;:|/\\=*^<>\-–—·•]+"
    r"|[\s,;:|/\\=*^<>\-–—·•]+$"
)
_NAME_INTERNAL_SPACES = re.compile(r"\s{2,}")


def clean_name(value: typing.Optional[str], max_length: typing.Optional[int] = None) -> typing.Optional[str]:
    if not value or not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped:
        return value

    cleaned = _NAME_EDGE_JUNK.sub("", stripped)
    cleaned = _NAME_INTERNAL_SPACES.sub(" ", cleaned).strip()

    if not cleaned:
        cleaned = stripped

    if max_length is not None:
        cleaned = cleaned[:max_length]

    return cleaned


def parse_date(date_string: typing.Optional[str]) -> typing.Optional[datetime.date]:
    if not date_string or not isinstance(date_string, str):
        return None

    date_string = date_string.strip()

    if not date_string or date_string.lower() in ["unknown", "n/a", "none"]:
        return None

    try:
        if re.match(r"^\d{4}$", date_string):
            return datetime.date(int(date_string), 1, 1)

        # dateutil fills whatever the text lacks from `default`. Parsing twice with
        # different default years tells a real year from one it made up, so "March 5"
        # is rejected instead of becoming March 5 of the current year.
        first = dateutil.parser.parse(
            date_string, fuzzy=True, default=datetime.datetime(2001, 1, 1)
        )
        second = dateutil.parser.parse(
            date_string, fuzzy=True, default=datetime.datetime(2002, 1, 1)
        )
        if first.year != second.year or not 1000 <= first.year <= 2100:
            return None

        return first.date()

    except (ValueError, TypeError, OverflowError, dateutil.parser.ParserError):
        return None


def clean_description(description: typing.Optional[str]) -> typing.Optional[str]:
    if not description or not isinstance(description, str):
        return None

    description = description.strip()

    if not description:
        return None

    description = html.unescape(description)

    description = re.sub(r"<[^>]+>", "", description)

    description = re.sub(r"\[http[s]?://[^\]]+\]", "", description)

    description = re.sub(r"https?://[^\s]+", "", description)

    description = re.sub(r"\(https?://[^\)]+\)", "", description)

    description = re.sub(r"\[\d+\]\s*", "", description)

    description = re.sub(r"\(\[Source\][^)]*\)", "", description)

    description = re.sub(r"[\(\[\{]{2}[^\)\]\}\n]*[\)\]\}]{2}", "", description)

    separators = [r"-{5,}", r"={5,}", r"\*{5,}", r"_{5,}"]

    for separator in separators:
        if re.search(separator, description):
            parts = re.split(separator, description)
            description = parts[0].strip()
            break

    metadata_patterns = [
        r"\n\*\*Also contained in:\*\*.*$",
        r"\n\*\*From the publisher:\*\*.*$",
        r"\n\*\*About the Author:\*\*.*$",
        r"\n\*\*Source:\*\*.*$",
        r"\n--+\s*\n.*$",
        r"\[1\]:\s*https?://.*$",
        r"^From Wikipedia.*$",
        r"^See also:.*$",
        r"^References:.*$",
        r"\n\nCopyright.*$",
        r"Preceded by:.*$",
        r"Followed by:.*$",
    ]

    for pattern in metadata_patterns:
        description = re.sub(
            pattern, "", description, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE
        )

    # Emphasis markers are stripped only after the patterns above ran: they match
    # the literal **bold** headings, which no longer exist once the markers are gone.
    # Single markers need a word boundary so snake_case and "2 * 3 * 4" survive.
    description = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", description)

    description = re.sub(r"(?<!\w)__([^_\n]+)__(?!\w)", r"\1", description)

    description = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", description)

    description = re.sub(r"(?<!\w)_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)", r"\1", description)

    description = re.sub(r"^#+\s+", "", description, flags=re.MULTILINE)

    description = re.sub(r"\n{3,}", "\n\n", description)

    description = re.sub(r"[ \t]{2,}", " ", description)

    description = description.strip().rstrip(":")

    description = description.strip()

    return description if description else None


def canonicalize_genre_name(name: str) -> tuple[str, str]:
    cleaned = app.data.genre_synonyms.strip_genre_noise(name)
    base_slug = slugify(cleaned, max_length=150)
    canonical_slug = app.data.genre_synonyms.GENRE_SYNONYMS.get(base_slug, base_slug)
    if canonical_slug != base_slug:
        canonical_name = canonical_slug.replace("-", " ")
    else:
        canonical_name = cleaned.lower()[:100] if cleaned else name.lower()[:100]
    return canonical_name, canonical_slug


def clamp_series_position(value: typing.Any) -> typing.Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0 or numeric > 999.99:
        return None
    return numeric


_SERIES_NUMBER_WORDS: typing.Dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}  # fmt: skip

# "Book 3" in the languages the site serves, plus the neighbouring ones OL data mixes in
_SERIES_POSITION_WORDS = (
    r"(?:Book|Volume|Vol\.?|Part|No\.?|Number|Tome?|Tomo|Band|Bd\.?|Teil|Buch|Livre|Libro|Livro"
    r"|Volumen|Cz\.?|Część|Czesc|Księga|Ksiega|Tom)"
)

_SERIES_POSITION_PATTERNS: typing.List[re.Pattern] = [
    re.compile(r"^(.+?)\s*\((\d+(?:\.\d+)?)\)\s*$"),
    re.compile(r"^(.+?)\s*#\s*(\d+(?:\.\d+)?)\s*$"),
    re.compile(r"^(.+?),\s*(\d+(?:\.\d+)?)\s*$"),
    re.compile(
        rf"^(.+?)[\s,]+{_SERIES_POSITION_WORDS}\s+(\d+(?:\.\d+)?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^(.+?)[\s,]+{_SERIES_POSITION_WORDS}\s+({'|'.join(_SERIES_NUMBER_WORDS)})\s*$",
        re.IGNORECASE,
    ),
]


def parse_series_descriptor(value: typing.Optional[str]) -> typing.Optional[typing.Dict[str, typing.Any]]:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    for pattern in _SERIES_POSITION_PATTERNS:
        m = pattern.match(value)
        if m:
            name = clean_name(m.group(1).strip().rstrip(",:").strip())
            if not name:
                continue
            position = clamp_series_position(
                _SERIES_NUMBER_WORDS.get(m.group(2).lower(), m.group(2))
            )
            return {"name": name, "position": position}
    return {"name": clean_name(value), "position": None}


_NON_ISBN_CHARACTERS = re.compile(r"[^0-9Xx]")


def normalize_isbn(raw: typing.Any) -> typing.Optional[str]:
    """Digits-only ISBN-10 or ISBN-13 with a valid check digit, or None.

    Catalogue data carries hyphens, prefixes and typos; storing only checksummed
    values keeps the ISBN lookup from matching one book to another's mistyped number.
    """
    if not isinstance(raw, str):
        return None

    cleaned = _NON_ISBN_CHARACTERS.sub("", raw).upper()
    if len(cleaned) == 10 and cleaned[:9].isdigit():
        total = sum(
            (10 - position) * (10 if char == "X" else int(char))
            for position, char in enumerate(cleaned)
        )
        return cleaned if total % 11 == 0 else None
    if len(cleaned) == 13 and cleaned.isdigit():
        total = sum(
            int(char) * (1 if position % 2 == 0 else 3)
            for position, char in enumerate(cleaned)
        )
        return cleaned if total % 10 == 0 else None
    return None


def normalize_isbns(values: typing.Iterable[typing.Any], limit: int = 20) -> list[str]:
    found: list[str] = []
    for value in values:
        isbn = normalize_isbn(value)
        if isbn and isbn not in found:
            found.append(isbn)
    return found[:limit]
