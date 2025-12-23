"""Jina AI Reader API client for fetching web pages as markdown."""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class JinaReaderResponse:
    """Response from Jina Reader API."""

    url: str
    markdown: str
    title: Optional[str] = None
    error: Optional[str] = None


class JinaReaderClient:
    """Async client for Jina AI Reader API."""

    BASE_URL = "https://r.jina.ai"

    def __init__(
        self,
        api_key: str,
        max_concurrent: int = 10,
        requests_per_minute: int = 400,
    ):
        """
        Initialize the Jina Reader client.

        Args:
            api_key: Jina AI API key for authentication
            max_concurrent: Maximum concurrent requests
            requests_per_minute: Rate limit (default 400, max 500 with API key)
        """
        self.api_key = api_key
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._request_interval = 60.0 / requests_per_minute
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._request_interval:
                await asyncio.sleep(self._request_interval - elapsed)
            self._last_request_time = time.monotonic()

    async def fetch_as_markdown(
        self,
        url: str,
        timeout: float = 30.0,
    ) -> JinaReaderResponse:
        """
        Fetch a URL and return its content as clean markdown.

        Args:
            url: The URL to fetch
            timeout: Request timeout in seconds

        Returns:
            JinaReaderResponse with markdown content or error
        """
        async with self._semaphore:
            await self._rate_limit()

            jina_url = f"{self.BASE_URL}/{url}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "text/markdown",
            }

            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(jina_url, headers=headers)
                    response.raise_for_status()

                    return JinaReaderResponse(
                        url=url,
                        markdown=response.text,
                        title=response.headers.get("X-Title"),
                    )
            except httpx.TimeoutException:
                return JinaReaderResponse(
                    url=url,
                    markdown="",
                    error="Request timed out",
                )
            except httpx.HTTPStatusError as e:
                error_text = e.response.text[:200] if e.response.text else "No details"
                return JinaReaderResponse(
                    url=url,
                    markdown="",
                    error=f"HTTP {e.response.status_code}: {error_text}",
                )
            except Exception as e:
                return JinaReaderResponse(
                    url=url,
                    markdown="",
                    error=str(e),
                )

    async def fetch_many(
        self,
        urls: list[str],
        timeout: float = 30.0,
    ) -> list[JinaReaderResponse]:
        """
        Fetch multiple URLs concurrently with rate limiting.

        Args:
            urls: List of URLs to fetch
            timeout: Request timeout in seconds for each URL

        Returns:
            List of JinaReaderResponse objects
        """
        tasks = [self.fetch_as_markdown(url, timeout) for url in urls]
        return await asyncio.gather(*tasks)
