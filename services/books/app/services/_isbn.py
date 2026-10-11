import re
import typing

_NON_ISBN_CHARACTERS = re.compile(r"[^0-9Xx]")


def _ten_checksum_ok(digits: str) -> bool:
    total = sum((10 - position) * (10 if char in "Xx" else int(char)) for position, char in enumerate(digits))
    return total % 11 == 0


def _thirteen_checksum_ok(digits: str) -> bool:
    total = sum(int(char) * (1 if position % 2 == 0 else 3) for position, char in enumerate(digits))
    return total % 10 == 0


def _thirteen_from_ten(isbn10: str) -> str:
    body = "978" + isbn10[:9]
    check = (10 - sum(int(char) * (1 if position % 2 == 0 else 3) for position, char in enumerate(body)) % 10) % 10
    return body + str(check)


def _ten_from_thirteen(isbn13: str) -> typing.Optional[str]:
    if not isbn13.startswith("978"):
        return None
    body = isbn13[3:12]
    remainder = sum((10 - position) * int(char) for position, char in enumerate(body)) % 11
    check = (11 - remainder) % 11
    return body + ("X" if check == 10 else str(check))


def normalise(raw: str) -> typing.Optional[str]:
    """Digits-only ISBN-10 or ISBN-13 with a valid check digit, or None.

    Hyphens and spaces are ignored. Anything else, or a checksum that does not add up,
    is not an ISBN: a typo must not match a different book.
    """
    cleaned = _NON_ISBN_CHARACTERS.sub("", raw or "").upper()
    if len(cleaned) == 10 and cleaned[:9].isdigit() and _ten_checksum_ok(cleaned):
        return cleaned
    if len(cleaned) == 13 and cleaned.isdigit() and _thirteen_checksum_ok(cleaned):
        return cleaned
    return None


def variants(isbn: str) -> list[str]:
    """Both forms of the same ISBN, since the catalogue holds whichever the edition printed."""
    if len(isbn) == 10:
        return [isbn, _thirteen_from_ten(isbn)]
    other = _ten_from_thirteen(isbn)
    return [isbn, other] if other else [isbn]
