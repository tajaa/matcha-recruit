"""HTTP utilities with retry logic for Tier 1 structured data fetching."""

import asyncio
from typing import Optional

import httpx


# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def fetch_with_retry(
    url: str,
    timeout: float = 60.0,
    headers: Optional[dict] = None,
    max_retries: int = MAX_RETRIES,
) -> httpx.Response:
    """
    Fetch a URL with automatic retry on transient failures.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        headers: Optional headers dict
        max_retries: Maximum number of retry attempts

    Returns:
        httpx.Response on success

    Raises:
        httpx.HTTPError: After all retries exhausted
    """
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers=headers or {},
                )

                # Check for retryable status codes
                if response.status_code in RETRYABLE_STATUS_CODES:
                    # Handle rate limiting with Retry-After header
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait_time = min(int(retry_after), 60)  # Cap at 60s
                            except ValueError:
                                wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                        else:
                            wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    else:
                        wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]

                    print(f"[HTTP] Retryable status {response.status_code}, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")

                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        continue

                # Raise for non-retryable errors
                response.raise_for_status()
                return response

        except httpx.TimeoutException as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                print(f"[HTTP] Timeout, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                raise

        except httpx.HTTPStatusError as e:
            # Don't retry client errors (4xx except 429)
            if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                raise
            last_error = e
            if attempt < max_retries - 1:
                wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                print(f"[HTTP] Error {e.response.status_code}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                raise

        except httpx.RequestError as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                print(f"[HTTP] Request error, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                raise

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise httpx.HTTPError(f"Failed to fetch {url} after {max_retries} attempts")
