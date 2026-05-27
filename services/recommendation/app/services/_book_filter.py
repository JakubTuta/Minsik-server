import typing


def dedupe_books_by_slug(
    books: typing.List[typing.Dict[str, typing.Any]],
) -> typing.List[typing.Dict[str, typing.Any]]:
    seen: typing.Set[str] = set()
    out: typing.List[typing.Dict[str, typing.Any]] = []
    for b in books:
        slug = b.get("slug") or ""
        if slug:
            if slug in seen:
                continue
            seen.add(slug)
        out.append(b)
    return out


def exclude_books(
    books: typing.List[typing.Dict[str, typing.Any]],
    excluded_ids: typing.Iterable[int],
    excluded_slugs: typing.Optional[typing.Iterable[str]] = None,
) -> typing.List[typing.Dict[str, typing.Any]]:
    id_set: typing.Set[int] = set(excluded_ids)
    slug_set: typing.Set[str] = set(excluded_slugs) if excluded_slugs else set()
    if not id_set and not slug_set:
        return books
    return [
        b for b in books
        if b.get("book_id") not in id_set
        and (not slug_set or (b.get("slug") or "") not in slug_set)
    ]
