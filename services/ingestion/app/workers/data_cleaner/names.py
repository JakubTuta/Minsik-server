import typing

import app.utils
import app.workers.data_cleaner.rules as rules
import app.workers.data_cleaner.runtime as runtime
import sqlalchemy
import sqlalchemy.ext.asyncio

_HEALED_TABLES = (("books", "book_id", "title"), ("authors", "author_id", "name"))


def _heal_step(
    table: str,
    id_col: str,
    name_col: str,
    batch_size: int,
) -> runtime.BatchStep:
    cursor = 0
    query = sqlalchemy.text(
        f"""
        SELECT {id_col}, {name_col} FROM books.{table}
        WHERE {id_col} > :cursor
          AND ({name_col} <> btrim({name_col}, :junk_chars) OR {name_col} LIKE '%  %')
        ORDER BY {id_col}
        LIMIT :batch_size
        """
    )
    update = sqlalchemy.text(
        f"UPDATE books.{table} SET {name_col} = :cleaned WHERE {id_col} = :row_id"
    )

    async def step(
        session: sqlalchemy.ext.asyncio.AsyncSession,
    ) -> typing.Tuple[int, bool]:
        nonlocal cursor
        result = await session.execute(
            query,
            {
                "cursor": cursor,
                "junk_chars": rules.NAME_JUNK_CHARS,
                "batch_size": batch_size,
            },
        )
        rows = result.fetchall()
        if not rows:
            return 0, False

        cursor = rows[-1][0]
        healed = 0
        for row_id, raw_name in rows:
            cleaned = app.utils.clean_name(raw_name)
            if cleaned and cleaned != raw_name:
                await session.execute(update, {"cleaned": cleaned, "row_id": row_id})
                healed += 1

        return healed, len(rows) == batch_size

    return step


async def heal_entity_names(
    session_factory: runtime.SessionFactory,
    batch_size: int,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, int]:
    stats: typing.Dict[str, int] = {}
    for table, id_col, name_col in _HEALED_TABLES:
        stats[f"{table}_healed"] = await runtime.run_batches(
            session_factory,
            f"{table} names healed",
            _heal_step(table, id_col, name_col, batch_size),
            stop_check,
        )
    return stats
