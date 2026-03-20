"""Congress.gov API integration.

Extracted from federal_sources.py — logic unchanged.
Requires CONGRESS_API_KEY environment variable.
"""

import logging
import os
from typing import AsyncGenerator, List, Optional
from uuid import UUID

import httpx

from ._base import _SEMAPHORE, _TIMEOUT, get_with_retry

logger = logging.getLogger(__name__)

# Keywords that indicate employment/labor/healthcare relevance
_LABOR_KEYWORDS = {
    "wage", "labor", "employment", "worker", "OSHA", "safety",
    "discrimination", "leave", "overtime", "healthcare", "health",
    "medicare", "medicaid", "HIPAA", "pharmacy", "drug",
}

_BILL_KEYWORD_TO_CATEGORY = {
    "minimum wage": "minimum_wage",
    "overtime": "overtime",
    "paid leave": "leave",
    "family leave": "leave",
    "fmla": "leave",
    "sick leave": "sick_leave",
    "child labor": "minor_work_permit",
    "workplace safety": "workplace_safety",
    "osha": "workplace_safety",
    "discrimination": "anti_discrimination",
    "equal employment": "anti_discrimination",
    "hipaa": "hipaa_privacy",
    "privacy": "hipaa_privacy",
    "medicare": "billing_integrity",
    "medicaid": "billing_integrity",
    "telehealth": "telehealth",
    "pharmacy": "pharmacy_drugs",
    "drug pricing": "pharmacy_drugs",
    "medical device": "medical_devices",
    "cybersecurity": "cybersecurity",
    "health information": "health_it",
    "workers comp": "workers_comp",
}


async def fetch_congress_requirements(
    jurisdiction_id: UUID,
) -> AsyncGenerator[dict, None]:
    """Fetch Congress.gov bill requirements. No-op if no API key. Yields SSE events."""
    api_key = os.environ.get("CONGRESS_API_KEY", "")
    if not api_key:
        yield {"type": "status", "message": "Skipping Congress.gov (no CONGRESS_API_KEY configured)"}
        yield {"type": "congress_done", "results": [], "count": 0}
        return

    yield {"type": "status", "message": "Fetching Congress.gov bills..."}
    try:
        requirements = await _fetch_congress_bills(api_key)
        yield {"type": "progress", "message": f"Congress.gov: {len(requirements)} relevant bills"}
        yield {"type": "congress_done", "results": requirements, "count": len(requirements)}
    except Exception:
        logger.error("Congress.gov fetch failed", exc_info=True)
        yield {"type": "warning", "message": "Congress.gov fetch failed"}
        yield {"type": "congress_done", "results": [], "count": 0}


async def _fetch_congress_bills(api_key: str) -> List[dict]:
    """Fetch recent employment/labor bills from Congress.gov."""
    url = (
        f"https://api.congress.gov/v3/bill"
        f"?limit=20&sort=updateDate+desc&api_key={api_key}"
    )

    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await get_with_retry(client, url)
            data = resp.json()

    bills = data.get("bills", [])
    requirements = []

    for bill in bills:
        title = bill.get("title", "")
        title_lower = title.lower()
        if not any(kw.lower() in title_lower for kw in _LABOR_KEYWORDS):
            continue

        category = _match_bill_to_category(title_lower)
        if not category:
            continue

        congress = bill.get("congress", "")
        number = bill.get("number", "")
        bill_type = bill.get("type", "")
        bill_url = (
            f"https://www.congress.gov/bill/{congress}th-congress"
            f"/{bill_type.lower()}-bill/{number}"
        )
        latest_action = bill.get("latestAction", {}).get("text", "N/A")
        update_date = bill.get("updateDate", "")

        requirements.append({
            "category": category,
            "jurisdiction_level": "federal",
            "jurisdiction_name": "Federal",
            "title": f"[Bill] {title[:200]}",
            "description": (
                f"Congress {congress}, {bill_type} {number}. "
                f"Latest action: {latest_action}"
            ),
            "current_value": f"Status: {latest_action}",
            "source_url": bill_url,
            "source_name": "Congress.gov",
            "effective_date": update_date[:10] if update_date else None,
        })

    return requirements


def _match_bill_to_category(title_lower: str) -> Optional[str]:
    """Best-effort mapping of a bill title to a compliance category."""
    for kw, cat in _BILL_KEYWORD_TO_CATEGORY.items():
        if kw in title_lower:
            return cat
    return None
