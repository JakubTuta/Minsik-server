import typing

import app.config

LANGUAGE_BOOST_WEIGHT = 100.0


def available_languages() -> typing.List[str]:
    raw = app.config.settings.available_languages or "en"
    return [lang.strip() for lang in raw.split(",") if lang.strip()] or ["en"]


def lang_boost_sql(column: str = "b.language", param: str = "language") -> str:
    return f"(CASE WHEN {column} = :{param} THEN {LANGUAGE_BOOST_WEIGHT} ELSE 1 END)"


def lang_boost_weight(book_language: str, user_language: str) -> float:
    return LANGUAGE_BOOST_WEIGHT if book_language == user_language else 1.0


def work_reader_count_sql(book_alias: str = "b", bookshelf_alias: str = "bsh") -> str:
    """Reader count pooled across every language edition of the same work.

    `book_alias` must be a `books.books` row in scope (for its `work_id`).
    `bookshelf_alias` must not collide with another alias in the query.
    """
    return (
        f"(SELECT COUNT(*) FROM user_data.bookshelves {bookshelf_alias} "
        f"JOIN books.books {bookshelf_alias}_wb ON {bookshelf_alias}_wb.book_id = {bookshelf_alias}.book_id "
        f"WHERE {bookshelf_alias}_wb.work_id = {book_alias}.work_id "
        f"AND {bookshelf_alias}.status != 'abandoned')"
    )


def _work_group_key(item: typing.Dict[str, typing.Any]) -> typing.Optional[typing.Tuple[str, str]]:
    item_type = item.get("type", "book")
    if item_type == "book":
        identity = item.get("work_id") or item.get("slug") or ""
    else:
        identity = item.get("slug") or ""
    if not identity:
        return None
    return (item_type, identity)


def dedupe_by_work(
    items: typing.List[typing.Dict[str, typing.Any]], language: str
) -> typing.List[typing.Dict[str, typing.Any]]:
    """Collapse translations of the same work into one entry per surface.

    Books are grouped by work_id (falling back to slug when absent).
    Author/series entries are grouped by slug, same as before. Within a
    group, the entry matching the requested language wins (highest
    relevance if several editions share the language); otherwise the
    entry with the most readers wins, and reader counts are summed across
    the group so popularity isn't lost by picking only one edition.
    """
    groups: typing.Dict[typing.Tuple[str, str], typing.List[typing.Dict[str, typing.Any]]] = {}
    order: typing.List[typing.Tuple[str, str]] = []
    passthrough: typing.List[typing.Dict[str, typing.Any]] = []

    for item in items:
        key = _work_group_key(item)
        if key is None:
            passthrough.append(item)
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)

    out: typing.List[typing.Dict[str, typing.Any]] = list(passthrough)
    for key in order:
        group = groups[key]
        if len(group) == 1:
            out.append(group[0])
            continue

        matched = [g for g in group if g.get("language") == language]
        if matched:
            winner = max(matched, key=lambda g: g.get("relevance_score", 0))
            out.append(winner)
            continue

        combined_readers = sum(g.get("readers") or 0 for g in group)
        winner = max(group, key=lambda g: g.get("readers") or 0)
        winner = dict(winner)
        winner["readers"] = combined_readers
        out.append(winner)

    return out
