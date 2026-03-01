import typing

import app.cache
import app.config
import app.services.list_builder


async def get_list(category: str, limit: int, offset: int) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cached = await app.cache.get_cached(f"rec:{category}")
    if not cached:
        return None

    item_type = cached.get("item_type", "book")
    items_key = "book_items" if item_type == "book" else "author_items"
    all_items = cached.get(items_key, [])
    paginated = all_items[offset:offset + limit]

    return {
        **cached,
        items_key: paginated,
        "total": len(all_items),
    }


async def get_home_page(items_per_category: int) -> typing.List[typing.Dict[str, typing.Any]]:
    settings = app.config.settings
    book_keys = [k.strip() for k in settings.home_book_categories.split(",") if k.strip()]
    author_keys = [k.strip() for k in settings.home_author_categories.split(",") if k.strip()]

    results = []
    for key in book_keys + author_keys:
        entry = await get_list(key, items_per_category, 0)
        if entry is not None:
            results.append(entry)

    return results


def get_available_categories() -> typing.List[typing.Dict[str, str]]:
    return [
        {
            "category": c["key"],
            "display_name": c["display_name"],
            "item_type": c["item_type"],
        }
        for c in app.services.list_builder.CATEGORIES
    ]
