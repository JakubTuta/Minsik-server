import asyncio
import gzip
import json
import logging
import os
import typing

import httpx

logger = logging.getLogger(__name__)

_DOWNLOAD_MAX_RETRIES = 5
_DOWNLOAD_READ_TIMEOUT = 300
_DOWNLOAD_CONNECT_TIMEOUT = 60
_DOWNLOAD_LOG_EVERY_MB = 100


async def _get_remote_size(url: str, timeout: httpx.Timeout) -> typing.Optional[int]:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.head(url)
            content_length = response.headers.get("content-length")
            if content_length:
                return int(content_length)
    except Exception:
        pass
    return None


async def download_file(url: str, dest_path: str) -> None:
    timeout = httpx.Timeout(
        connect=_DOWNLOAD_CONNECT_TIMEOUT,
        read=_DOWNLOAD_READ_TIMEOUT,
        write=30.0,
        pool=60.0,
    )

    local_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0

    if local_size > 0:
        remote_size = await _get_remote_size(url, timeout)
        if remote_size is not None:
            if local_size == remote_size:
                logger.info(
                    f"[dump] Skipping download, file already complete: {dest_path} "
                    f"({local_size / (1024 * 1024):.0f} MB)"
                )
                return
            elif local_size > remote_size:
                logger.warning(
                    f"[dump] Local file larger than remote ({local_size} > {remote_size}), "
                    f"deleting and re-downloading: {dest_path}"
                )
                os.remove(dest_path)
                local_size = 0
            else:
                logger.info(
                    f"[dump] Resuming download from {local_size / (1024 * 1024):.0f} MB "
                    f"of {remote_size / (1024 * 1024):.0f} MB total: {url}"
                )
        else:
            logger.warning(
                f"[dump] Cannot verify remote size for {url}, "
                f"re-downloading to be safe"
            )
            os.remove(dest_path)
            local_size = 0

    logger.info(f"[dump] Downloading {url}")

    downloaded = local_size
    total_size: typing.Optional[int] = None
    last_logged_mb = downloaded / (1024 * 1024)

    for attempt in range(1, _DOWNLOAD_MAX_RETRIES + 1):
        headers: dict[str, str] = {}
        file_mode = "wb"

        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"
            file_mode = "ab"
            if attempt > 1:
                logger.info(
                    f"[dump] Resuming download from {downloaded / (1024 * 1024):.0f} MB "
                    f"(attempt {attempt}/{_DOWNLOAD_MAX_RETRIES})"
                )

        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True
            ) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code == 416:
                        logger.info("[dump] Download already complete (416 response)")
                        break

                    response.raise_for_status()

                    if total_size is None:
                        content_length = response.headers.get("content-length")
                        if content_length:
                            total_size = int(content_length) + downloaded

                    with open(dest_path, file_mode) as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            current_mb = downloaded / (1024 * 1024)
                            if current_mb - last_logged_mb >= _DOWNLOAD_LOG_EVERY_MB:
                                last_logged_mb = current_mb
                                total_mb = (
                                    total_size / (1024 * 1024) if total_size else None
                                )
                                if total_mb:
                                    pct = (downloaded / total_size) * 100
                                    logger.info(
                                        f"[dump] Download progress: "
                                        f"{current_mb:.0f}/{total_mb:.0f} MB "
                                        f"({pct:.1f}%)"
                                    )
                                else:
                                    logger.info(
                                        f"[dump] Download progress: "
                                        f"{current_mb:.0f} MB"
                                    )

            logger.info(
                f"[dump] Downloaded to {dest_path} "
                f"({downloaded / (1024 * 1024):.0f} MB)"
            )
            return

        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
            httpx.ReadError,
            httpx.ConnectError,
        ) as e:
            if attempt == _DOWNLOAD_MAX_RETRIES:
                logger.error(
                    f"[dump] Download failed after {_DOWNLOAD_MAX_RETRIES} attempts: {e}"
                )
                raise

            wait_seconds = min(30 * (2 ** (attempt - 1)), 300)
            logger.warning(
                f"[dump] Download interrupted ({type(e).__name__}), "
                f"downloaded {downloaded / (1024 * 1024):.0f} MB so far. "
                f"Retrying in {wait_seconds}s (attempt {attempt}/{_DOWNLOAD_MAX_RETRIES})"
            )
            await asyncio.sleep(wait_seconds)

        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise

            if attempt == _DOWNLOAD_MAX_RETRIES:
                logger.error(
                    f"[dump] Download failed after {_DOWNLOAD_MAX_RETRIES} attempts: {e}"
                )
                raise

            wait_seconds = min(60 * (2 ** (attempt - 1)), 600)
            logger.warning(
                f"[dump] Server returned {e.response.status_code}, "
                f"retrying in {wait_seconds}s (attempt {attempt}/{_DOWNLOAD_MAX_RETRIES})"
            )
            await asyncio.sleep(wait_seconds)


async def stream_parse_dump(
    file_path: str,
    record_type: str,
    queue: asyncio.Queue[typing.Optional[typing.List[dict]]],
    batch_size: int,
) -> None:
    loop = asyncio.get_running_loop()

    def _sync_reader() -> None:
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            batch: list[dict] = []
            for line in f:
                try:
                    parts = line.rstrip("\n").split("\t", 4)
                    if len(parts) != 5:
                        continue
                    if parts[0] != record_type:
                        continue

                    data = json.loads(parts[4])
                    batch.append(data)
                    if len(batch) >= batch_size:
                        asyncio.run_coroutine_threadsafe(
                            queue.put(batch[:]), loop
                        ).result()
                        batch = []
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue

            if batch:
                asyncio.run_coroutine_threadsafe(queue.put(batch), loop).result()

        asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    await asyncio.to_thread(_sync_reader)
