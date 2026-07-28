import typing


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


def work_view_count_sql(book_alias: str = "b", view_alias: str = "vb") -> str:
    """View count pooled across every language edition of the same work."""
    return (
        f"(SELECT COALESCE(SUM({view_alias}.view_count), 0) FROM books.books {view_alias} "
        f"WHERE {view_alias}.work_id = {book_alias}.work_id)"
    )


def dedupe_by_work(
    items: typing.List[typing.Dict[str, typing.Any]], language: str
) -> typing.List[typing.Dict[str, typing.Any]]:
    """Collapse translations of the same work into one entry.

    Grouped by work_id (falling back to slug when absent, e.g. author/series
    items which carry no work_id). Within a group the reader's language wins,
    then English, then the most-read edition — the same order every other
    edition-picking path in the app uses, so a book looks the same whether it
    was reached through a recommendation row or its own page. Reader counts are
    already pooled per work upstream, so the winner's count needs no adjustment.
    """
    groups: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]] = {}
    order: typing.List[str] = []
    passthrough: typing.List[typing.Dict[str, typing.Any]] = []

    for item in items:
        key = item.get("work_id") or item.get("slug") or ""
        if not key:
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
                winner = max(matched, key=lambda g: g.get("score", 0))
                break

        out.append(winner or max(group, key=lambda g: g.get("readers") or 0))

    return out
