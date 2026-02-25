import asyncio
import logging
import typing

import app.models
import httpx
import sqlalchemy
from app.workers.dump import parsers

logger = logging.getLogger(__name__)

_WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
_WIKIDATA_SPARQL_BATCH = 200
_WIKIDATA_REQUEST_DELAY = 1.5
_WIKIDATA_MAX_RETRIES = 3
_WIKIDATA_LOG_INTERVAL = 100


async def process_wikidata_enrichment() -> int:
    async with app.models.AsyncSessionLocal() as session:
        result = await session.execute(
            sqlalchemy.text(
                "SELECT wikidata_id FROM books.authors "
                "WHERE wikidata_id IS NOT NULL "
                "AND (nationality IS NULL OR birth_place IS NULL)"
            )
        )
        wikidata_ids = [row.wikidata_id for row in result]

    if not wikidata_ids:
        logger.info("[dump] No authors need Wikidata enrichment")
        return 0

    logger.info(f"[dump] Found {len(wikidata_ids)} authors needing Wikidata enrichment")

    updated_count = 0
    batch_count = 0
    timeout = httpx.Timeout(connect=30, read=90, write=30, pool=60)
    headers = {
        "User-Agent": "MinsikBot/1.0 (book-catalog; https://github.com/minsik)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        async with app.models.AsyncSessionLocal() as session:
            for i in range(0, len(wikidata_ids), _WIKIDATA_SPARQL_BATCH):
                batch_ids = wikidata_ids[i : i + _WIKIDATA_SPARQL_BATCH]
                batch_count += 1

                try:
                    enrichment = await _fetch_wikidata_sparql_batch(client, batch_ids)
                    if enrichment:
                        updated_count += await _flush_wikidata_updates(
                            session, enrichment
                        )
                except Exception as e:
                    logger.debug(f"Error fetching Wikidata batch: {e}")

                if batch_count % _WIKIDATA_LOG_INTERVAL == 0:
                    await session.commit()
                    logger.info(
                        f"[dump] Wikidata enrichment: "
                        f"{i + len(batch_ids)}/{len(wikidata_ids)}, "
                        f"updated: {updated_count}"
                    )

                await asyncio.sleep(_WIKIDATA_REQUEST_DELAY)

            await session.commit()

    logger.info(
        f"[dump] Phase 2 complete: {updated_count} authors enriched via Wikidata"
    )
    return updated_count


async def _fetch_wikidata_sparql_batch(
    client: httpx.AsyncClient,
    wikidata_ids: list[str],
) -> list[dict]:
    values_str = " ".join(f"wd:{wid}" for wid in wikidata_ids)
    query = (
        "SELECT ?item ?nationalityLabel ?birthPlaceLabel ?article WHERE { "
        f"VALUES ?item {{ {values_str} }} "
        "OPTIONAL { ?item wdt:P27 ?nationality } "
        "OPTIONAL { ?item wdt:P19 ?birthPlace } "
        "OPTIONAL { "
        "?article schema:about ?item ; "
        "schema:isPartOf <https://en.wikipedia.org/> . "
        "} "
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . } '
        "}"
    )

    for attempt in range(1, _WIKIDATA_MAX_RETRIES + 1):
        try:
            response = await client.get(
                _WIKIDATA_SPARQL_URL,
                params={"query": query, "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
            break
        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.HTTPStatusError,
            httpx.ConnectError,
        ) as e:
            if attempt == _WIKIDATA_MAX_RETRIES:
                logger.debug(
                    f"Wikidata SPARQL failed after {_WIKIDATA_MAX_RETRIES} "
                    f"attempts: {e}"
                )
                return []
            await asyncio.sleep(attempt * 3)

    enrichment_map: dict[str, dict] = {}
    for binding in data.get("results", {}).get("bindings", []):
        item_uri = binding.get("item", {}).get("value", "")
        wikidata_id = item_uri.rsplit("/", 1)[-1]
        if not wikidata_id:
            continue

        if wikidata_id not in enrichment_map:
            enrichment_map[wikidata_id] = {
                "wikidata_id": wikidata_id,
                "nationality": None,
                "birth_place": None,
                "wikipedia_url": None,
            }

        nat_label = binding.get("nationalityLabel", {}).get("value")
        bp_label = binding.get("birthPlaceLabel", {}).get("value")
        article_url = binding.get("article", {}).get("value")

        entry = enrichment_map[wikidata_id]
        if (
            nat_label
            and not parsers.is_wikidata_qid(nat_label)
            and not entry["nationality"]
        ):
            entry["nationality"] = nat_label[:200]
        if (
            bp_label
            and not parsers.is_wikidata_qid(bp_label)
            and not entry["birth_place"]
        ):
            entry["birth_place"] = bp_label[:500]
        if article_url and not entry["wikipedia_url"]:
            entry["wikipedia_url"] = article_url[:1000]

    return [
        v
        for v in enrichment_map.values()
        if v["nationality"] or v["birth_place"] or v["wikipedia_url"]
    ]


async def _flush_wikidata_updates(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    updates: list[dict],
) -> int:
    if not updates:
        return 0

    count = 0
    batch_size = 500
    for i in range(0, len(updates), batch_size):
        sub_batch = updates[i : i + batch_size]
        values_parts: list[str] = []
        params: dict[str, typing.Any] = {}
        for k, update in enumerate(sub_batch):
            values_parts.append(f"(:wid_{k}, :nat_{k}, :bp_{k}, :wurl_{k})")
            params[f"wid_{k}"] = update["wikidata_id"]
            params[f"nat_{k}"] = update["nationality"]
            params[f"bp_{k}"] = update["birth_place"]
            params[f"wurl_{k}"] = update["wikipedia_url"]

        await session.execute(
            sqlalchemy.text(
                "UPDATE books.authors AS a SET "
                "nationality = COALESCE(a.nationality, v.nat), "
                "birth_place = COALESCE(a.birth_place, v.bp), "
                "wikipedia_url = COALESCE(a.wikipedia_url, v.wurl) "
                f"FROM (VALUES {', '.join(values_parts)}) "
                "AS v(wid, nat, bp, wurl) "
                "WHERE a.wikidata_id = v.wid"
            ),
            params,
        )
        count += len(sub_batch)
    return count
