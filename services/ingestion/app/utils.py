import re
import unicodedata
import datetime
import typing
import html as html_module
from dateutil import parser as date_parser


def slugify(text: str, max_length: int = 200) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = text.lower()

    text = re.sub(r"[^\w\s-]", "", text)

    text = re.sub(r"[-\s]+", "-", text)

    text = text.strip("-")

    return text[:max_length]


def parse_date(date_string: typing.Optional[str]) -> typing.Optional[datetime.date]:
    if not date_string or not isinstance(date_string, str):
        return None

    date_string = date_string.strip()

    if not date_string or date_string.lower() in ["unknown", "n/a", "none"]:
        return None

    try:
        if re.match(r"^\d{4}$", date_string):
            return datetime.date(int(date_string), 1, 1)

        parsed = date_parser.parse(date_string, fuzzy=True)
        return parsed.date()

    except (ValueError, TypeError, date_parser.ParserError):
        return None


def clean_description(description: typing.Optional[str]) -> typing.Optional[str]:
    if not description or not isinstance(description, str):
        return None

    description = description.strip()

    if not description:
        return None

    description = html_module.unescape(description)

    description = re.sub(r'<[^>]+>', '', description)

    description = re.sub(r'\[http[s]?://[^\]]+\]', '', description)

    description = re.sub(r'https?://[^\s]+', '', description)

    description = re.sub(r'\(https?://[^\)]+\)', '', description)

    description = re.sub(r'\[\d+\]\s*', '', description)

    description = re.sub(r'\*\*([^*]+)\*\*', r'\1', description)

    description = re.sub(r'__([^_]+)__', r'\1', description)

    description = re.sub(r'\*([^*]+)\*', r'\1', description)

    description = re.sub(r'_([^_]+)_', r'\1', description)

    description = re.sub(r'^#+\s+', '', description, flags=re.MULTILINE)

    separators = [
        r"-{5,}",
        r"={5,}",
        r"\*{5,}",
        r"_{5,}"
    ]

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
        r"\n\nCopyright.*$"
    ]

    for pattern in metadata_patterns:
        description = re.sub(pattern, "", description, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE)

    description = re.sub(r'\n{3,}', '\n\n', description)

    description = re.sub(r'[ \t]{2,}', ' ', description)

    description = description.strip()

    return description if description else None


def format_title_with_series(title: str, series_name: typing.Optional[str]) -> str:
    if not title:
        return ""

    if not series_name:
        return title

    title_lower = title.lower()
    series_lower = series_name.lower()

    series_core = re.sub(r'^the\s+', '', series_lower).strip()

    if series_lower in title_lower or series_core in title_lower:
        return title

    return f"{series_name}: {title}"
