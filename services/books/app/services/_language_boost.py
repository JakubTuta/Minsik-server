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


def work_shelf_count_sql(book_alias: str = "b", bookshelf_alias: str = "bsh") -> str:
    """Distinct app users who shelved any language edition of the same work.

    Counts every status: shelving a book at all is the engagement signal, and
    counting users rather than rows keeps a user who shelved two translations
    from being counted twice.

    `book_alias` must be a `books.books` row in scope (for its `work_id`).
    `bookshelf_alias` must not collide with another alias in the query.
    """
    return (
        f"(SELECT COUNT(DISTINCT {bookshelf_alias}.user_id) FROM user_data.bookshelves {bookshelf_alias} "
        f"JOIN books.books {bookshelf_alias}_wb ON {bookshelf_alias}_wb.book_id = {bookshelf_alias}.book_id "
        f"WHERE {bookshelf_alias}_wb.work_id = {book_alias}.work_id)"
    )


def preferred_edition_sql(
    book_alias: str = "b",
    edition_alias: str = "pe",
    language_param: str = "language",
    require_cover: bool = True,
    extra_where: str = "",
) -> str:
    """Keep one edition per work: the reader's language when such an edition exists.

    Candidate selection stays language-agnostic so a reader whose language has a
    thin catalog still sees the globally best works instead of a near-empty
    list; language only decides which edition gets rendered. Collapsing to one
    edition per work also stops a heavily-translated book from taking several
    slots in the same list.

    `extra_where` must repeat any outer condition that an edition has to satisfy
    to be renderable (already qualified with `edition_alias`); otherwise this
    can elect an edition the outer query then rejects, dropping the whole work.
    """
    conditions = [f"{edition_alias}.work_id = {book_alias}.work_id"]
    if require_cover:
        conditions.append(f"{edition_alias}.primary_cover_url IS NOT NULL")
    if extra_where:
        conditions.append(extra_where)
    return (
        f"{book_alias}.book_id = ("
        f"SELECT {edition_alias}.book_id FROM books.books {edition_alias} "
        f"WHERE {' AND '.join(conditions)} "
        f"ORDER BY ({edition_alias}.language = :{language_param}) DESC, "
        f"({edition_alias}.language = 'en') DESC, {edition_alias}.book_id ASC "
        f"LIMIT 1)"
    )


def work_readers_sql(book_alias: str = "b", bookshelf_alias: str = "bsh") -> str:
    """Everyone who shelved the work here or on Open Library, all statuses."""
    return (
        f"(COALESCE({book_alias}.ol_want_to_read_count, 0)"
        f" + COALESCE({book_alias}.ol_currently_reading_count, 0)"
        f" + COALESCE({book_alias}.ol_already_read_count, 0)"
        f" + {work_shelf_count_sql(book_alias, bookshelf_alias)})"
    )


def work_popularity_sql(book_alias: str = "b", bookshelf_alias: str = "bsh") -> str:
    """Single popularity signal: every shelf status plus every rating."""
    return (
        f"({work_readers_sql(book_alias, bookshelf_alias)}"
        f" + COALESCE({book_alias}.rating_count, 0)"
        f" + COALESCE({book_alias}.ol_rating_count, 0))"
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
    Author/series entries are grouped by slug, same as before. Within a group
    the reader's language wins (highest relevance if several editions share
    it), then English, then the most-read edition — the same order every other
    edition-picking path in the app uses, so a book looks the same whether it
    was reached through search or its own page. Reader counts are already
    pooled per work upstream, so the winner's count needs no adjustment.
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

        winner = None
        for candidate_language in (language, "en"):
            matched = [g for g in group if g.get("language") == candidate_language]
            if matched:
                winner = max(matched, key=lambda g: g.get("relevance_score", 0))
                break

        out.append(winner or max(group, key=lambda g: g.get("readers") or 0))

    return out
