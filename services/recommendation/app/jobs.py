import logging

import app.db
import app.services.book_of_week_builder
import app.services.case_pool_builder
import app.services.contextual_precompute
import app.services.list_builder
import app.services.personal_refresher

logger = logging.getLogger(__name__)


async def general_refresh_job() -> None:
    logger.info("[rec] Running general recommendation refresh")
    try:
        await app.services.list_builder.refresh_all(app.db.async_session_maker)
        logger.info("[rec] General refresh complete")
    except Exception:
        logger.exception("[rec] General refresh error")


async def personal_refresh_job() -> None:
    logger.info("[rec:personal] Running personalized recommendation refresh")
    try:
        await app.services.personal_refresher.refresh_all_personal(
            app.db.async_session_maker
        )
        logger.info("[rec:personal] Personal refresh complete")
    except Exception:
        logger.exception("[rec:personal] Personal refresh error")


async def contextual_precompute_job() -> None:
    logger.info("[rec:precompute] Running contextual precompute refresh")
    try:
        await app.services.contextual_precompute.refresh_contextual_recs(
            app.db.async_session_maker
        )
        logger.info("[rec:precompute] Contextual precompute refresh complete")
    except Exception:
        logger.exception("[rec:precompute] Contextual precompute error")


async def case_pool_refresh_job() -> None:
    logger.info("[rec:case] Running case pool refresh")
    try:
        await app.services.case_pool_builder.refresh_case_pools(
            app.db.async_session_maker
        )
        logger.info("[rec:case] Case pool refresh complete")
    except Exception:
        logger.exception("[rec:case] Case pool refresh error")


async def book_of_week_job() -> None:
    logger.info("[rec:bow] Running book of the week refresh")
    try:
        await app.services.book_of_week_builder.refresh_book_of_the_week(
            app.db.async_session_maker
        )
        logger.info("[rec:bow] Book of the week refresh complete")
    except Exception:
        logger.exception("[rec:bow] Book of the week refresh error")


async def ensure_book_of_week_job() -> None:
    try:
        await app.services.book_of_week_builder.ensure_book_of_the_week(
            app.db.async_session_maker
        )
    except Exception:
        logger.exception("[rec:bow] Book of the week ensure error")
