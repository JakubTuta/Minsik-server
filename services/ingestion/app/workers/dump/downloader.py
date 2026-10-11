import asyncio
import gzip
import json
import logging
import os
import random
import typing

import app.config
import httpx

logger = logging.getLogger(__name__)

_DOWNLOAD_MAX_RETRIES = 10
_DOWNLOAD_READ_TIMEOUT = 60
_DOWNLOAD_CONNECT_TIMEOUT = 60
_DOWNLOAD_LOG_EVERY_MB = 100


async def _head(url: str, timeout: httpx.Timeout) -> typing.Optional[httpx.Response]:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            return await client.head(url)
    except httpx.HTTPError:
        return None


def _validator(response: typing.Optional[httpx.Response]) -> typing.Optional[str]:
    """Identity of the remote file. `latest` URLs are replaced monthly, so a partial
    download is only worth resuming while the file behind the URL is still the same."""
    if response is None:
        return None
    return response.headers.get("etag") or response.headers.get("last-modified")


def _read_validator(dest_path: str) -> typing.Optional[str]:
    try:
        with open(f"{dest_path}.validator", encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _write_validator(dest_path: str, validator: typing.Optional[str]) -> None:
    if validator:
        with open(f"{dest_path}.validator", "w", encoding="utf-8") as f:
            f.write(validator)


def _discard(dest_path: str) -> None:
    for path in (dest_path, f"{dest_path}.validator"):
        if os.path.exists(path):
            os.remove(path)


async def download_file(url: str, dest_path: str) -> None:
    timeout = httpx.Timeout(
        connect=_DOWNLOAD_CONNECT_TIMEOUT,
        read=_DOWNLOAD_READ_TIMEOUT,
        write=30.0,
        pool=60.0,
    )

    local_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0

    head = await _head(url, timeout)
    remote_validator = _validator(head)
    remote_length = head.headers.get("content-length") if head is not None else None
    remote_size = int(remote_length) if remote_length else None

    if local_size > 0:
        if remote_validator and _read_validator(dest_path) != remote_validator:
            logger.warning(f"[dump] {dest_path} is from a different dump than the one at {url}; discarding it")
            _discard(dest_path)
            local_size = 0
        elif remote_size is None:
            logger.warning(f"[dump] Cannot verify remote size for {url}, re-downloading to be safe")
            _discard(dest_path)
            local_size = 0
        elif local_size == remote_size:
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
            _discard(dest_path)
            local_size = 0
        else:
            logger.info(
                f"[dump] Resuming download from {local_size / (1024 * 1024):.0f} MB "
                f"of {remote_size / (1024 * 1024):.0f} MB total: {url}"
            )

    _write_validator(dest_path, remote_validator)
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

                    if "Range" in headers and response.status_code != 206:
                        logger.warning(
                            f"[dump] Server returned {response.status_code} instead of 206 "
                            f"for Range request — resume not supported, restarting download"
                        )
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        downloaded = 0
                        total_size = None
                        file_mode = "wb"

                    if total_size is None:
                        content_length = response.headers.get("content-length")
                        if content_length:
                            offset = downloaded if response.status_code == 206 else 0
                            total_size = int(content_length) + offset

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
    skip_records: int = 0,
) -> None:
    loop = asyncio.get_running_loop()

    is_dev = app.config.settings.env == "development"

    def _sync_reader() -> None:
        skipped_so_far = 0
        try:
            with gzip.open(file_path, "rt", encoding="utf-8") as f:
                batch: list[dict] = []
                for line in f:
                    parts = line.rstrip("\n").split("\t", 4)
                    if len(parts) != 5 or parts[0] != record_type:
                        continue
                    if is_dev and random.random() >= 0.1:
                        continue
                    if skipped_so_far < skip_records:
                        skipped_so_far += 1
                        continue
                    try:
                        batch.append(json.loads(parts[4]))
                    except json.JSONDecodeError:
                        continue
                    if len(batch) >= batch_size:
                        asyncio.run_coroutine_threadsafe(queue.put(batch), loop).result()
                        batch = []

                if batch:
                    asyncio.run_coroutine_threadsafe(queue.put(batch), loop).result()
        finally:
            # Always release the consumer. A truncated or corrupt file raises out of
            # the loop above; without the sentinel the consumer would wait forever.
            asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

    await asyncio.to_thread(_sync_reader)
