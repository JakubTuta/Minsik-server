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


def work_shelf_counts_join(book_alias: str = "b", counts_alias: str = "wsc") -> str:
    """Join the per-work shelf rollup onto a `books.books` row already in scope.

    Aggregating user_data.bookshelves inline made every list query group the
    whole table by work_id just to read a handful of rows; books.work_shelf_counts
    holds the same numbers, refreshed on a cron by the books service.
    """
    return (
        f"LEFT JOIN books.work_shelf_counts {counts_alias} "
        f"ON {counts_alias}.work_id = {book_alias}.work_id"
    )


def work_shelf_count_sql(counts_alias: str = "wsc") -> str:
    """Distinct app users who shelved any language edition of the same work.

    Counts every status: shelving a book at all is the engagement signal, and
    counting users rather than rows keeps a user who shelved two translations
    from being counted twice. Requires `work_shelf_counts_join` in the query.
    """
    return f"COALESCE({counts_alias}.readers, 0)"


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


def canonical_edition_cte(
    select_list: str,
    source: str,
    where: str = "",
    book_alias: str = "b",
    language_param: str = "language",
) -> str:
    """One edition per work, picked the same way `preferred_edition_sql` picks it.

    `preferred_edition_sql` re-runs its subquery once per candidate row, which
    is fine for a handful of rows and quadratic for a whole-catalog list. This
    does the same pick as a single sort, so it is the form to use whenever the
    candidate set isn't already narrow.
    """
    where_clause = f"WHERE {where} " if where else ""
    return (
        f"SELECT DISTINCT ON ({book_alias}.work_id) {select_list} "
        f"FROM {source} {where_clause}"
        f"ORDER BY {book_alias}.work_id, "
        f"({book_alias}.language = :{language_param}) DESC, "
        f"({book_alias}.language = 'en') DESC, {book_alias}.book_id ASC"
    )


def work_readers_sql(book_alias: str = "b", counts_alias: str = "wsc") -> str:
    """Everyone who shelved the work here or on Open Library, all statuses."""
    return (
        f"(COALESCE({book_alias}.ol_want_to_read_count, 0)"
        f" + COALESCE({book_alias}.ol_currently_reading_count, 0)"
        f" + COALESCE({book_alias}.ol_already_read_count, 0)"
        f" + {work_shelf_count_sql(counts_alias)})"
    )


def work_popularity_sql(book_alias: str = "b", counts_alias: str = "wsc") -> str:
    """Single popularity signal: every shelf status plus every rating."""
    return (
        f"({work_readers_sql(book_alias, counts_alias)}"
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
