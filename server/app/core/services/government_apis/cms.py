"""CMS (Centers for Medicare & Medicaid Services) data integration.

Extracted from federal_sources.py — logic unchanged.
"""

import logging
from typing import AsyncGenerator, List, Optional
from uuid import UUID

import httpx

from ...compliance_registry import CMS_CATEGORIES, CATEGORY_FEDERAL_REGISTER_AGENCIES
from ._base import _SEMAPHORE, _TIMEOUT, get_with_retry

logger = logging.getLogger(__name__)


async def fetch_cms_requirements(
    jurisdiction_id: UUID,
) -> AsyncGenerator[dict, None]:
    """Fetch CMS dataset requirements for healthcare categories. Yields SSE events."""
    healthcare_cats = set(CATEGORY_FEDERAL_REGISTER_AGENCIES.keys()) & CMS_CATEGORIES
    if not healthcare_cats:
        return

    yield {
        "type": "status",
        "message": f"Fetching CMS data for {len(healthcare_cats)} healthcare categories...",
    }

    try:
        requirements = await _fetch_cms_data(healthcare_cats)
        yield {"type": "progress", "message": f"CMS: {len(requirements)} records found"}
        yield {"type": "cms_done", "results": requirements, "count": len(requirements)}
    except Exception:
        logger.error("CMS data fetch failed", exc_info=True)
        yield {"type": "warning", "message": "CMS data fetch failed"}
        yield {"type": "cms_done", "results": [], "count": 0}


async def _fetch_cms_data(categories: set) -> List[dict]:
    """Fetch CMS dataset summaries relevant to healthcare compliance."""
    requirements = []

    url = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items?limit=20"
    try:
        async with _SEMAPHORE:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await get_with_retry(client, url)
                datasets = resp.json()

        for ds in datasets:
            title = ds.get("title", "")
            if not title:
                continue
            category = _match_cms_to_category(title.lower(), categories)
            if not category:
                continue

            desc = ds.get("description", "")
            if isinstance(desc, str):
                desc = desc[:500]
            else:
                desc = str(desc)[:500]

            modified = ds.get("modified", "")

            requirements.append({
                "category": category,
                "jurisdiction_level": "federal",
                "jurisdiction_name": "Federal",
                "title": f"[CMS Data] {title[:200]}",
                "description": desc,
                "current_value": f"Dataset last modified: {modified}" if modified else None,
                "source_url": "https://data.cms.gov/provider-data/",
                "source_name": "CMS Provider Data",
                "effective_date": modified[:10] if modified else None,
            })
    except Exception:
        logger.error("CMS provider data fetch failed", exc_info=True)

    return requirements


def _match_cms_to_category(title_lower: str, target_categories: set) -> Optional[str]:
    """Map CMS dataset title to a compliance category."""
    mappings = {
        "quality": "quality_reporting",
        "patient safety": "clinical_safety",
        "staffing": "healthcare_workforce",
        "nursing": "healthcare_workforce",
        "hospital compare": "quality_reporting",
        "readmission": "quality_reporting",
        "infection": "clinical_safety",
        "telehealth": "telehealth",
        "hospice": "clinical_safety",
        "dialysis": "clinical_safety",
        "home health": "clinical_safety",
        "emergency": "emergency_preparedness",
        "drug": "pharmacy_drugs",
        "physician": "billing_integrity",
        "supplier": "medical_devices",
    }
    for kw, cat in mappings.items():
        if kw in title_lower and cat in target_categories:
            return cat
    return None
