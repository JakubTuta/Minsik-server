import asyncio
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
    paginated = all_items[offset : offset + limit]

    return {
        **cached,
        items_key: paginated,
        "total": len(all_items),
    }


async def get_home_page(
    items_per_category: int,
    user_id: int = 0,
    personal_cache_only: bool = False,
    force_personal_refresh: bool = False,
) -> typing.List[typing.Dict[str, typing.Any]]:
    settings = app.config.settings
    book_keys = [
        k.strip() for k in settings.home_book_categories.split(",") if k.strip()
    ]
    author_keys = [
        k.strip() for k in settings.home_author_categories.split(",") if k.strip()
    ]
    all_keys = book_keys + author_keys

    results = await asyncio.gather(
        *[get_list(key, items_per_category, 0) for key in all_keys]
    )
    generic_sections = [r for r in results if r is not None]

    if user_id <= 0:
        return generic_sections

    personal_sections = await _get_personal_home_page(
        user_id,
        items_per_category,
        cache_only=personal_cache_only,
        force_refresh=force_personal_refresh,
    )
    if not personal_sections:
        return generic_sections

    return personal_sections + generic_sections


async def _get_personal_home_page(
    user_id: int,
    items_per_section: int,
    cache_only: bool,
    force_refresh: bool,
) -> typing.List[typing.Dict[str, typing.Any]]:
    import app.services.personal_provider

    sections = await app.services.personal_provider.get_personal_home_sections(
        user_id,
        items_per_section,
        cache_only=cache_only,
        force_refresh=force_refresh,
    )
    return sections or []


def get_available_categories() -> typing.List[typing.Dict[str, str]]:
    return [
        {
            "category": c["key"],
            "display_name": c["display_name"],
            "item_type": c["item_type"],
        }
        for c in app.services.list_builder.CATEGORIES
    ]
