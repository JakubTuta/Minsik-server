import typing

import app.cache
import app.config
import app.services.list_builder


async def get_list(
    category: str,
    limit: int,
    offset: int,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
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


async def get_home_page(
    items_per_category: int,
    user_id: int = 0,
) -> typing.List[typing.Dict[str, typing.Any]]:
    if user_id > 0:
        return await _get_personal_home_page(user_id, items_per_category)

    settings = app.config.settings
    book_keys = [k.strip() for k in settings.home_book_categories.split(",") if k.strip()]
    author_keys = [k.strip() for k in settings.home_author_categories.split(",") if k.strip()]

    sections = []
    for key in book_keys + author_keys:
        entry = await get_list(key, items_per_category, 0)
        if entry is not None:
            sections.append(entry)

    return sections


async def _get_personal_home_page(
    user_id: int,
    items_per_section: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    import app.services.personal_provider
    import app.services.taste_profile

    profile = await app.services.taste_profile.get_taste_profile(user_id)
    if profile is None or profile.get("is_cold_start"):
        return []

    return await app.services.personal_provider.get_personal_home_sections(
        user_id, items_per_section
    )


def get_available_categories() -> typing.List[typing.Dict[str, str]]:
    return [
        {
            "category": c["key"],
            "display_name": c["display_name"],
            "item_type": c["item_type"],
        }
        for c in app.services.list_builder.CATEGORIES
    ]
