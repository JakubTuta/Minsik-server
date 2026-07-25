import typing


def exclude_books(
    books: typing.List[typing.Dict[str, typing.Any]],
    excluded_ids: typing.Iterable[int],
) -> typing.List[typing.Dict[str, typing.Any]]:
    id_set: typing.Set[int] = set(excluded_ids)
    if not id_set:
        return books
    return [b for b in books if b.get("book_id") not in id_set]
