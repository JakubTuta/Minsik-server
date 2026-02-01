import httpx
import asyncio
import logging
import typing # Optional, Dict, Any
import abc # abc.ABC, abstractmethod
import app.config

logger = logging.getLogger(__name__)


class BaseFetcher(abc.ABC):
    def __init__(self, api_url: str, rate_limit: int = 100):
        self.api_url = api_url
        self.rate_limit = rate_limit
        self.client: typing.typing.Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(rate_limit)
        self._retry_delay = app.config.settings.ingestion_retry_delay
        self._max_retries = app.config.settings.ingestion_max_retries

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=app.config.settings.request_timeout,
            follow_redirects=True
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _fetch_with_retry(self, url: str, params: typing.typing.Optional[typing.Dict[str, Any]] = None) -> typing.Optional[typing.Dict[str, Any]]:
        for attempt in range(self._max_retries):
            try:
                async with self._semaphore:
                    response = await self.client.get(url, params=params)
                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 429:
                        wait_time = self._retry_delay * (attempt + 1)
                        await asyncio.sleep(wait_time)
                    else:
                        return None
            except httpx.TimeoutException:
                await asyncio.sleep(self._retry_delay)
            except Exception as e:
                logger.error(f"Fetch error for {url}: {str(e)}")
                return None

        return None

    @abc.abstractmethod
    async def fetch_books(self, count: int, language: str = "en") -> list[typing.Dict[str, Any]]:
        pass

    @abc.abstractmethod
    async def parse_book_data(self, raw_data: typing.typing.Dict[str, Any]) -> typing.Optional[typing.Dict[str, Any]]:
        pass
