import asyncio
import typing

import app.cache
import app.config
import app.services._book_filter
import app.services._language_boost
import app.services.list_builder
import app.services.personal_provider
import app.services.taste_profile


async def get_list(
    category: str,
    limit: int,
    offset: int,
    language: str = "en",
    user_id: int = 0,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cached = await app.cache.get_cached(f"rec:{category}")
    if not cached:
        return None

    item_type = cached.get("item_type", "book")
    items_key = "book_items" if item_type == "book" else "author_items"
    all_items = cached.get(items_key, [])

    if item_type == "book":
        all_items = sorted(
            all_items,
            key=lambda b: b.get("score", 0)
            * app.services._language_boost.lang_boost_weight(
                b.get("language", ""), language
            ),
            reverse=True,
        )
        all_items = app.services._book_filter.dedupe_books_by_slug(all_items)
        if user_id > 0:
            profile = await app.services.taste_profile.get_taste_profile(user_id)
            if profile:
                excluded_ids = profile.get("excluded_book_ids", [])
                excluded_slugs = {
                    b["slug"]
                    for b in all_items
                    if b.get("book_id") in set(excluded_ids) and b.get("slug")
                }
                all_items = app.services._book_filter.exclude_books(
                    all_items, excluded_ids, excluded_slugs
                )

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
    language: str = "en",
) -> typing.List[typing.Dict[str, typing.Any]]:
    if user_id > 0:
        return await _get_personal_home_page(
            user_id,
            items_per_category,
            cache_only=personal_cache_only,
            force_refresh=force_personal_refresh,
        )

    settings = app.config.settings
    book_keys = [
        k.strip() for k in settings.home_book_categories.split(",") if k.strip()
    ]
    author_keys = [
        k.strip() for k in settings.home_author_categories.split(",") if k.strip()
    ]
    all_keys = book_keys + author_keys

    results = await asyncio.gather(
        *[get_list(key, items_per_category, 0, language, user_id=0) for key in all_keys]
    )
    return [r for r in results if r is not None]


async def _get_personal_home_page(
    user_id: int,
    items_per_section: int,
    cache_only: bool,
    force_refresh: bool,
) -> typing.List[typing.Dict[str, typing.Any]]:
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
