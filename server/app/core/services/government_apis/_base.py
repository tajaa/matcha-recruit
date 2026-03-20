"""Shared infrastructure for all government API modules."""

import asyncio
import logging
from typing import Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Shared rate limiting — max concurrent requests to any single external API
_SEMAPHORE = asyncio.Semaphore(3)
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_RETRIES = 2

_FEDERAL_REGISTER_BASE = "https://www.federalregister.gov/api/v1"
_ECFR_BASE = "https://www.ecfr.gov/api/versioner/v1"
_ECFR_SEARCH_BASE = "https://www.ecfr.gov/api/search/v1"
_OPENSTATES_BASE = "https://v3.openstates.org"


async def get_with_retry(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET with exponential backoff on timeout."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt == _MAX_RETRIES:
                raise
            wait = 2 * (attempt + 1)
            logger.warning("Timeout attempt %d for %s, retrying in %ds...", attempt + 1, url[:100], wait)
            await asyncio.sleep(wait)


def dedup_by_key(reqs: List[Dict], key_fn: Callable[[Dict], Optional[str]]) -> List[Dict]:
    """Deduplicate requirements by a stable key function. First occurrence wins."""
    seen: set = set()
    result: List[Dict] = []
    for req in reqs:
        k = key_fn(req)
        if k and k not in seen:
            seen.add(k)
            result.append(req)
        elif not k:
            result.append(req)  # No key → always include
    return result
