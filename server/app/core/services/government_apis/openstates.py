"""OpenStates API integration — state legislative bill tracking.

Provides early warning for state-level law changes. Rows use
source_tier="tier_2_official_secondary" (aggregator of official state records).

Requires OPENSTATES_API_KEY. Free registration at openstates.org/account/profile/
Rate limit: 6 requests/minute → 0.5s sleep between requests.
"""

import asyncio
import logging
from typing import AsyncGenerator, Dict, List, Optional
from uuid import UUID

import httpx

from ...compliance_registry import CATEGORY_OPENSTATES_SUBJECTS
from ._base import _OPENSTATES_BASE, _SEMAPHORE, _TIMEOUT, dedup_by_key, get_with_retry

logger = logging.getLogger(__name__)

_OPENSTATES_RATE_SLEEP = 0.5  # seconds between requests to respect 6 req/min


async def fetch_openstates_for_jurisdiction(
    jurisdiction_id: UUID,
    state_code: str,
    state_name: str,
    api_key: str,
) -> AsyncGenerator[dict, None]:
    """Fetch state bills from OpenStates. Yields SSE events.

    Args:
        jurisdiction_id: Jurisdiction UUID (unused in requests, kept for interface consistency)
        state_code: Two-letter state code (e.g. "CA")
        state_name: Full state name for display (e.g. "California")
        api_key: OpenStates API key
    """
    if not api_key:
        yield {
            "type": "status",
            "message": "Skipping OpenStates (no OPENSTATES_API_KEY configured)",
        }
        yield {"type": "openstates_done", "results": [], "count": 0}
        return

    yield {
        "type": "status",
        "message": f"Fetching OpenStates legislative bills for {state_name}...",
    }

    # OpenStates jurisdiction ID format: "ocd-jurisdiction/country:us/state:{code}/government"
    jurisdiction_slug = f"ocd-jurisdiction/country:us/state:{state_code.lower()}/government"

    all_requirements: List[dict] = []

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for cat, keywords in CATEGORY_OPENSTATES_SUBJECTS.items():
            for keyword in keywords[:2]:  # max 2 keywords per category to limit calls
                bills = await _fetch_bills(client, jurisdiction_slug, keyword, api_key)
                for bill in bills:
                    req = _map_bill_to_requirement(bill, cat, state_name, state_code)
                    if req:
                        all_requirements.append(req)
                await asyncio.sleep(_OPENSTATES_RATE_SLEEP)

    # Dedup by bill identifier + category
    all_requirements = dedup_by_key(
        all_requirements,
        key_fn=lambda r: f"{r.get('category')}:{r.get('_bill_id', r.get('title', ''))[:80]}",
    )

    # Remove internal dedup field
    for req in all_requirements:
        req.pop("_bill_id", None)

    yield {
        "type": "progress",
        "message": f"OpenStates: {len(all_requirements)} bills for {state_name}",
    }
    yield {
        "type": "openstates_done",
        "results": all_requirements,
        "count": len(all_requirements),
    }


async def _fetch_bills(
    client: httpx.AsyncClient,
    jurisdiction_slug: str,
    keyword: str,
    api_key: str,
    per_page: int = 10,
) -> List[dict]:
    """Fetch bills matching a keyword for a jurisdiction."""
    url = (
        f"{_OPENSTATES_BASE}/bills"
        f"?jurisdiction={jurisdiction_slug}"
        f"&q={keyword}"
        f"&sort=updated_desc"
        f"&per_page={per_page}"
    )
    headers = {"X-API-KEY": api_key}

    try:
        async with _SEMAPHORE:
            resp = await client.get(url, headers=headers, timeout=_TIMEOUT)
            if resp.status_code == 401:
                logger.error("OpenStates API key invalid or expired")
                return []
            if resp.status_code == 429:
                logger.warning("OpenStates rate limit hit, sleeping 10s")
                await asyncio.sleep(10)
                return []
            resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        logger.warning("OpenStates fetch failed for keyword=%s", keyword, exc_info=True)
        return []


def _map_bill_to_requirement(
    bill: dict,
    category: str,
    state_name: str,
    state_code: str,
) -> Optional[dict]:
    """Map an OpenStates bill dict to a requirement dict."""
    identifier = bill.get("identifier", "")
    title = bill.get("title", "")
    if not title:
        return None

    bill_id = bill.get("id", "")
    openstates_url = bill.get("openstates_url", f"https://openstates.org/")

    # Latest action
    actions = bill.get("actions", [])
    latest_action_text = ""
    if actions:
        latest = actions[-1]
        latest_action_text = latest.get("description", "")

    status = latest_action_text or bill.get("status", "In progress")
    updated = bill.get("updated_at", "")
    effective_date = updated[:10] if updated else None

    return {
        "category": category,
        "jurisdiction_level": "state",
        "jurisdiction_name": state_name,
        "title": f"[State Bill] {state_code} {identifier} \u2013 {title[:160]}",
        "description": (
            f"State bill {identifier} in {state_name}. "
            f"Latest: {latest_action_text[:300]}" if latest_action_text
            else f"State bill {identifier} in {state_name}."
        ),
        "current_value": f"Status: {status[:200]}",
        "source_url": openstates_url,
        "source_name": "OpenStates",
        # source_tier handled by orchestrator/apply step (tier_2_official_secondary)
        "effective_date": effective_date,
        "_bill_id": bill_id or identifier,
    }
