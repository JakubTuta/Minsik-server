"""Safety net around a full OpenLibrary re-import.

    docker exec <ingestion-container> python -m app.workers.dump.reimport_tools snapshot
    ... run the import ...
    docker exec <ingestion-container> python -m app.workers.dump.reimport_tools verify

`snapshot` records every book row (id, work, language, slug) and every reader's
shelf/rating/comment counts. `verify` fails loudly when the import broke a promise:
no row a reader points at may disappear, no reader's rows may change count, no old
URL may stop resolving, and the pooled rating figures must still match the ratings
themselves. A failed verification means: restore the backup taken before the import.
"""

import asyncio
import logging
import sys

import app.models
import sqlalchemy

logger = logging.getLogger(__name__)

_SNAPSHOT_STATEMENTS = [
    "TRUNCATE books.reimport_anchor, books.reimport_user_counts",
    "INSERT INTO books.reimport_anchor (book_id, work_id, language, slug) "
    "SELECT book_id, work_id, language, slug FROM books.books",
    """
    INSERT INTO books.reimport_user_counts (user_id, shelves, ratings, comments, shelf_works)
    SELECT u.user_id,
           (SELECT COUNT(*) FROM user_data.bookshelves s WHERE s.user_id = u.user_id),
           (SELECT COUNT(*) FROM user_data.ratings r WHERE r.user_id = u.user_id),
           (SELECT COUNT(*) FROM user_data.comments c WHERE c.user_id = u.user_id),
           (SELECT COUNT(DISTINCT b.work_id) FROM user_data.bookshelves s
              JOIN books.books b ON b.book_id = s.book_id WHERE s.user_id = u.user_id)
    FROM (
        SELECT user_id FROM user_data.bookshelves
        UNION SELECT user_id FROM user_data.ratings
        UNION SELECT user_id FROM user_data.comments
    ) u
    """,
]

# Each check selects the offending rows; any row is a failure.
_CHECKS: list[tuple[str, str]] = [
    (
        "book rows that existed before the import and are gone",
        "SELECT a.book_id FROM books.reimport_anchor a "
        "WHERE NOT EXISTS (SELECT 1 FROM books.books b WHERE b.book_id = a.book_id)",
    ),
    (
        "book rows whose OpenLibrary work changed",
        "SELECT a.book_id FROM books.reimport_anchor a "
        "JOIN books.books b ON b.book_id = a.book_id WHERE a.work_id ~ '^OL[0-9]+W$' AND b.work_id <> a.work_id",
    ),
    (
        "readers whose shelf, rating or comment count changed",
        "SELECT c.user_id FROM books.reimport_user_counts c WHERE "
        "(SELECT COUNT(*) FROM user_data.bookshelves s WHERE s.user_id = c.user_id) <> c.shelves "
        "OR (SELECT COUNT(*) FROM user_data.ratings r WHERE r.user_id = c.user_id) <> c.ratings "
        "OR (SELECT COUNT(*) FROM user_data.comments m WHERE m.user_id = c.user_id) <> c.comments",
    ),
    (
        "readers whose shelved works changed",
        "SELECT c.user_id FROM books.reimport_user_counts c WHERE "
        "(SELECT COUNT(DISTINCT b.work_id) FROM user_data.bookshelves s "
        "JOIN books.books b ON b.book_id = s.book_id WHERE s.user_id = c.user_id) <> c.shelf_works",
    ),
    (
        "shelf, rating or comment rows pointing at a missing book",
        "SELECT s.book_id FROM user_data.bookshelves s WHERE NOT EXISTS (SELECT 1 FROM books.books b WHERE b.book_id = s.book_id) "
        "UNION ALL SELECT r.book_id FROM user_data.ratings r WHERE NOT EXISTS (SELECT 1 FROM books.books b WHERE b.book_id = r.book_id) "
        "UNION ALL SELECT m.book_id FROM user_data.comments m WHERE NOT EXISTS (SELECT 1 FROM books.books b WHERE b.book_id = m.book_id)",
    ),
    (
        "old book URLs that no longer resolve",
        "SELECT a.book_id FROM books.reimport_anchor a "
        "JOIN books.books b ON b.book_id = a.book_id "
        "WHERE (b.slug <> a.slug OR b.language <> a.language) "
        "AND NOT EXISTS (SELECT 1 FROM books.slug_history h WHERE h.entity_type = 'book' "
        "AND h.language = a.language AND h.old_slug = a.slug AND h.entity_id = a.book_id)",
    ),
    (
        "works whose pooled rating count differs from the ratings themselves",
        "SELECT b.book_id FROM books.books b JOIN ("
        "SELECT bb.work_id, COUNT(*) AS n FROM user_data.ratings r "
        "JOIN books.books bb ON bb.book_id = r.book_id GROUP BY bb.work_id) x ON x.work_id = b.work_id "
        "WHERE b.rating_count <> x.n",
    ),
    (
        "translated rows still carrying the English row's description",
        "SELECT b.book_id FROM books.books b JOIN books.books e "
        "ON e.work_id = b.work_id AND e.language = 'en' "
        "WHERE b.language <> 'en' AND b.description IS NOT NULL AND b.description = e.description",
    ),
]

_SUMMARY_QUERIES: list[tuple[str, str]] = [
    ("rows created", "SELECT COUNT(*) FROM books.books b WHERE NOT EXISTS (SELECT 1 FROM books.reimport_anchor a WHERE a.book_id = b.book_id)"),
    ("rows relabelled to another language", "SELECT COUNT(*) FROM books.reimport_anchor a JOIN books.books b ON b.book_id = a.book_id WHERE b.language <> a.language"),
    ("rows with a new slug", "SELECT COUNT(*) FROM books.reimport_anchor a JOIN books.books b ON b.book_id = a.book_id WHERE b.slug <> a.slug"),
    ("works with more than one language row", "SELECT COUNT(*) FROM (SELECT 1 FROM books.books GROUP BY work_id HAVING COUNT(*) > 1) t"),
    ("authors", "SELECT COUNT(*) FROM books.authors"),
]


async def snapshot() -> None:
    async with app.models.AsyncSessionLocal() as session:
        for statement in _SNAPSHOT_STATEMENTS:
            await session.execute(sqlalchemy.text(statement))
        await session.commit()
        books = (await session.execute(sqlalchemy.text("SELECT COUNT(*) FROM books.reimport_anchor"))).scalar_one()
        readers = (await session.execute(sqlalchemy.text("SELECT COUNT(*) FROM books.reimport_user_counts"))).scalar_one()
    logger.info(f"Snapshot taken: {books} book rows, {readers} readers")


async def verify() -> list[str]:
    failures: list[str] = []
    async with app.models.AsyncSessionLocal() as session:
        taken = (await session.execute(sqlalchemy.text("SELECT COUNT(*) FROM books.reimport_anchor"))).scalar_one()
        if not taken:
            return ["no snapshot found: run `snapshot` before the import"]
        for label, query in _CHECKS:
            offenders = (await session.execute(sqlalchemy.text(f"SELECT COUNT(*) FROM ({query}) offenders"))).scalar_one()
            logger.info(f"{'FAIL' if offenders else 'ok  '} {label}: {offenders}")
            if offenders:
                failures.append(f"{label}: {offenders}")
        for label, query in _SUMMARY_QUERIES:
            logger.info(f"info {label}: {(await session.execute(sqlalchemy.text(query))).scalar_one()}")
    return failures


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "snapshot":
        asyncio.run(snapshot())
    elif command == "verify":
        failures = asyncio.run(verify())
        if failures:
            logger.error(f"VERIFICATION FAILED ({len(failures)}): restore the backup taken before the import")
            sys.exit(1)
        logger.info("Verification passed")
    else:
        sys.stderr.write("usage: python -m app.workers.dump.reimport_tools snapshot|verify\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
