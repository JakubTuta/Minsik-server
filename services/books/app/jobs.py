import logging

import app.db
import app.services.author_service
import app.services.book_service
import app.services.category_service
import app.services.es_sync_service
import app.services.work_shelf_counts

logger = logging.getLogger(__name__)


async def flush_view_counts_job() -> None:
    try:
        async with app.db.async_session_maker() as session:
            await app.services.book_service.flush_view_counts_to_db(session)
            await app.services.author_service.flush_view_counts_to_db(session)
    except Exception as e:
        logger.error(f"[books] View count flush error: {str(e)}")


async def flush_view_counts_final() -> None:
    async with app.db.async_session_maker() as session:
        await app.services.book_service.flush_view_counts_to_db(session)
        await app.services.author_service.flush_view_counts_to_db(session)


async def reindex_job() -> None:
    try:
        await app.services.es_sync_service.reindex_all_to_es(full=False)
    except Exception as e:
        logger.error(f"[books] ES reindex error: {str(e)}")


async def work_shelf_counts_refresh_job() -> None:
    await app.services.work_shelf_counts.rebuild_job()


async def category_cache_refresh_job() -> None:
    try:
        await app.services.category_service.category_service.setup()
        await app.services.category_service.category_service.populate_category_top_books_cache()
        await app.services.category_service.category_service.populate_popular_categories_cache()
    except Exception as e:
        logger.error(f"[books] Category cache refresh error: {str(e)}")
