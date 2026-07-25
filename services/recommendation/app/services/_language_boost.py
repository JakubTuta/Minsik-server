import typing

LANGUAGE_BOOST_WEIGHT = 100.0


def lang_boost_weight(book_language: str, user_language: str) -> float:
    return LANGUAGE_BOOST_WEIGHT if book_language == user_language else 1.0


def dedupe_by_work(
    items: typing.List[typing.Dict[str, typing.Any]], language: str
) -> typing.List[typing.Dict[str, typing.Any]]:
    """Collapse translations of the same work into one entry.

    Grouped by work_id (falling back to slug when absent, e.g. author/series
    items which carry no work_id). Within a group, the entry matching the
    requested language wins by score; otherwise the entry with the most
    readers wins, and reader counts are summed across the group.
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

        matched = [g for g in group if g.get("language") == language]
        if matched:
            winner = max(matched, key=lambda g: g.get("score", 0))
            out.append(winner)
            continue

        combined_readers = sum(g.get("readers") or 0 for g in group)
        winner = max(group, key=lambda g: g.get("readers") or 0)
        winner = dict(winner)
        winner["readers"] = combined_readers
        out.append(winner)

    return out
