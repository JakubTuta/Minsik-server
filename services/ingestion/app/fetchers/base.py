import httpx
import asyncio
import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from app.config import settings

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    def __init__(self, api_url: str, rate_limit: int = 100):
        self.api_url = api_url
        self.rate_limit = rate_limit
        self.client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(rate_limit)
        self._retry_delay = settings.ingestion_retry_delay
        self._max_retries = settings.ingestion_max_retries

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=settings.request_timeout,
            follow_redirects=True
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _fetch_with_retry(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
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

    @abstractmethod
    async def fetch_books(self, count: int, language: str = "en") -> list[Dict[str, Any]]:
        pass

    @abstractmethod
    async def parse_book_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass
