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
) -> str:
    work_ol_id = (external_ids or {}).get("work_ol_id")
    return work_ol_id or open_library_id or slug


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

        parsed = dateutil.parser.parse(date_string, fuzzy=True)
        return parsed.date()

    except (ValueError, TypeError, dateutil.parser.ParserError):
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

    description = re.sub(r"\*\*([^*]+)\*\*", r"\1", description)

    description = re.sub(r"__([^_]+)__", r"\1", description)

    description = re.sub(r"\*([^*]+)\*", r"\1", description)

    description = re.sub(r"_([^_]+)_", r"\1", description)

    description = re.sub(r"^#+\s+", "", description, flags=re.MULTILINE)

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


_SERIES_POSITION_PATTERNS: typing.List[re.Pattern] = [
    re.compile(r"^(.+?)\s*\((\d+(?:\.\d+)?)\)\s*$"),
    re.compile(r"^(.+?)\s*#\s*(\d+(?:\.\d+)?)\s*$"),
    re.compile(r"^(.+?),\s*(\d+(?:\.\d+)?)\s*$"),
    re.compile(
        r"^(.+?)\s+(?:Book|Volume|Vol\.|Part|No\.)\s+(\d+(?:\.\d+)?)\s*$",
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
            position = clamp_series_position(m.group(2))
            return {"name": name, "position": position}
    return {"name": clean_name(value), "position": None}
