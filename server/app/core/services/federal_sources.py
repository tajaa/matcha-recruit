"""Fetch compliance data directly from government APIs (no Gemini).

Sources:
- Federal Register API (final rules, proposed rules, public inspection)
- CMS datasets (healthcare categories)
- Congress.gov bills (if CONGRESS_API_KEY is set)
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import AsyncGenerator, Dict, List, Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx

from ..compliance_registry import (
    CATEGORY_FEDERAL_REGISTER_AGENCIES,
    CMS_CATEGORIES,
    CATEGORY_LABELS,
)
from ..services.compliance_service import _upsert_requirements_additive
from ...database import get_connection

logger = logging.getLogger(__name__)

# Rate limit: max concurrent requests to any single API
_SEMAPHORE = asyncio.Semaphore(3)
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_RETRIES = 2
_FEDERAL_REGISTER_BASE = "https://www.federalregister.gov/api/v1"


async def _get_with_retry(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET with retry on timeout."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt == _MAX_RETRIES:
                raise
            logger.warning("Timeout on attempt %d for %s, retrying...", attempt + 1, url[:100])
            await asyncio.sleep(2 * (attempt + 1))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def fetch_federal_sources(
    jurisdiction_id: UUID,
) -> AsyncGenerator[dict, None]:
    """Fetch from government APIs and upsert results. Yields SSE events."""

    async with get_connection() as conn:
        j = await conn.fetchrow(
            "SELECT id, city, state FROM jurisdictions WHERE id = $1",
            jurisdiction_id,
        )
        if not j:
            yield {"type": "error", "message": "Jurisdiction not found"}
            return

        state = j["state"]
        city = j["city"]
        location_label = f"{city}, {state}" if city else state

        # Determine which categories this jurisdiction has
        existing = await conn.fetch(
            "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
            jurisdiction_id,
        )
        existing_cats = {r["category"] for r in existing}
        # Fetch for all mapped categories (not just existing ones)
        target_cats = set(CATEGORY_FEDERAL_REGISTER_AGENCIES.keys())

        yield {"type": "started", "message": f"Starting federal sources check for {location_label}..."}

        all_requirements: List[Dict] = []

        # --- Federal Register: final rules ---
        yield {"type": "status", "message": "Fetching Federal Register final rules..."}
        try:
            all_agencies = set()
            all_keywords = []
            for cat in target_cats:
                cfg = CATEGORY_FEDERAL_REGISTER_AGENCIES[cat]
                all_agencies.update(cfg["agencies"])
                all_keywords.extend(cfg["keywords"])

            final_docs = await _fetch_federal_register(
                list(all_agencies), doc_type="RULE",
            )
            yield {"type": "progress", "message": f"Found {len(final_docs)} final rules from Federal Register"}

            mapped = _map_documents_to_requirements(final_docs, "Federal Register (Final Rule)")
            all_requirements.extend(mapped)
        except Exception:
            logger.error("Federal Register final rules fetch failed", exc_info=True)
            yield {"type": "warning", "message": "Federal Register final rules fetch failed"}

        # --- Federal Register: proposed rules ---
        yield {"type": "status", "message": "Fetching Federal Register proposed rules..."}
        try:
            proposed_docs = await _fetch_federal_register(
                list(all_agencies), doc_type="PRORULE",
            )
            yield {"type": "progress", "message": f"Found {len(proposed_docs)} proposed rules"}

            mapped = _map_documents_to_requirements(proposed_docs, "Federal Register (Proposed Rule)")
            all_requirements.extend(mapped)
        except Exception:
            logger.error("Federal Register proposed rules fetch failed", exc_info=True)
            yield {"type": "warning", "message": "Federal Register proposed rules fetch failed"}

        # --- Federal Register: public inspection ---
        yield {"type": "status", "message": "Fetching public inspection documents..."}
        try:
            inspection_docs = await _fetch_public_inspection(list(all_agencies))
            yield {"type": "progress", "message": f"Found {len(inspection_docs)} public inspection documents"}

            mapped = _map_documents_to_requirements(inspection_docs, "Federal Register (Public Inspection)")
            all_requirements.extend(mapped)
        except Exception:
            logger.error("Public inspection fetch failed", exc_info=True)
            yield {"type": "warning", "message": "Public inspection fetch failed"}

        # --- CMS data (healthcare categories only) ---
        healthcare_cats = target_cats & CMS_CATEGORIES
        if healthcare_cats:
            yield {"type": "status", "message": f"Fetching CMS data for {len(healthcare_cats)} healthcare categories..."}
            try:
                cms_reqs = await _fetch_cms_data(healthcare_cats)
                yield {"type": "progress", "message": f"Found {len(cms_reqs)} CMS records"}
                all_requirements.extend(cms_reqs)
            except Exception:
                logger.error("CMS data fetch failed", exc_info=True)
                yield {"type": "warning", "message": "CMS data fetch failed"}

        # --- Congress.gov (if API key available) ---
        congress_key = os.environ.get("CONGRESS_API_KEY", "")
        if congress_key:
            yield {"type": "status", "message": "Fetching Congress.gov bills..."}
            try:
                bill_reqs = await _fetch_congress_bills(congress_key)
                yield {"type": "progress", "message": f"Found {len(bill_reqs)} relevant bills"}
                all_requirements.extend(bill_reqs)
            except Exception:
                logger.error("Congress.gov fetch failed", exc_info=True)
                yield {"type": "warning", "message": "Congress.gov fetch failed"}
        else:
            yield {"type": "status", "message": "Skipping Congress.gov (no API key)"}

        # --- Deduplicate by title ---
        seen_titles = set()
        unique_reqs = []
        for req in all_requirements:
            title_key = req.get("title", "").strip().lower()[:100]
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_reqs.append(req)

        yield {"type": "progress", "message": f"Mapped {len(unique_reqs)} unique requirements across {len(target_cats)} categories"}

        # --- Send preview (no upsert yet) ---
        # Group by category for display
        by_category: Dict[str, list] = {}
        for req in unique_reqs:
            cat = req.get("category", "unknown")
            by_category.setdefault(cat, []).append({
                "title": req.get("title", ""),
                "source_name": req.get("source_name", ""),
                "source_url": req.get("source_url", ""),
                "effective_date": req.get("effective_date"),
                "description": (req.get("description") or "")[:200],
            })

        yield {
            "type": "preview",
            "message": f"Found {len(unique_reqs)} requirements from government APIs. Review below.",
            "results": unique_reqs,
            "by_category": by_category,
            "total": len(unique_reqs),
            "category_count": len(by_category),
        }


async def apply_federal_sources(
    jurisdiction_id: UUID,
    requirements: List[Dict],
) -> Dict[str, int]:
    """Upsert previously fetched federal source requirements."""
    async with get_connection() as conn:
        result = await _upsert_requirements_additive(
            conn, jurisdiction_id, requirements,
            research_source="official_api",
        )

        # Update requirement_count
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
            jurisdiction_id,
        )
        await conn.execute(
            "UPDATE jurisdictions SET last_verified_at = NOW(), requirement_count = $1, updated_at = NOW() WHERE id = $2",
            count, jurisdiction_id,
        )
        return result


# ---------------------------------------------------------------------------
# Federal Register API
# ---------------------------------------------------------------------------

async def _fetch_federal_register(
    agencies: List[str],
    doc_type: str = "RULE",
    per_page: int = 50,
) -> List[dict]:
    """Fetch documents from Federal Register API filtered by agencies."""
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%m/%d/%Y")

    params = urlencode({
        "per_page": per_page,
        "order": "newest",
        "conditions[type][]": doc_type,
        "conditions[publication_date][gte]": one_year_ago,
    })
    agency_params = "&".join(
        f"conditions[agencies][]={a}" for a in agencies
    )
    url = f"{_FEDERAL_REGISTER_BASE}/documents.json?{params}&{agency_params}"

    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await _get_with_retry(client, url)
            data = resp.json()

    return data.get("results", [])


async def _fetch_public_inspection(agencies: List[str]) -> List[dict]:
    """Fetch current public inspection documents, filtered to relevant agencies."""
    url = f"{_FEDERAL_REGISTER_BASE}/public-inspection-documents/current.json"

    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await _get_with_retry(client, url)
            data = resp.json()

    agency_set = set(agencies)
    results = []
    for doc in data.get("results", []):
        doc_agencies = [a.get("slug", "") for a in doc.get("agencies", [])]
        if any(a in agency_set for a in doc_agencies):
            results.append(doc)

    return results


# ---------------------------------------------------------------------------
# Congress.gov API
# ---------------------------------------------------------------------------

async def _fetch_congress_bills(api_key: str) -> List[dict]:
    """Fetch recent employment/labor bills from Congress.gov."""
    url = (
        f"https://api.congress.gov/v3/bill"
        f"?limit=20&sort=updateDate+desc&api_key={api_key}"
    )

    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await _get_with_retry(client, url)
            data = resp.json()

    bills = data.get("bills", [])
    requirements = []

    # Keywords that indicate employment/labor relevance
    labor_keywords = {
        "wage", "labor", "employment", "worker", "OSHA", "safety",
        "discrimination", "leave", "overtime", "healthcare", "health",
        "medicare", "medicaid", "HIPAA", "pharmacy", "drug",
    }

    for bill in bills:
        title = bill.get("title", "")
        title_lower = title.lower()
        if not any(kw.lower() in title_lower for kw in labor_keywords):
            continue

        # Try to map to a category
        category = _match_bill_to_category(title_lower)
        if not category:
            continue

        congress = bill.get("congress", "")
        number = bill.get("number", "")
        bill_type = bill.get("type", "")
        bill_url = f"https://www.congress.gov/bill/{congress}th-congress/{bill_type.lower()}-bill/{number}"

        requirements.append({
            "category": category,
            "jurisdiction_level": "federal",
            "jurisdiction_name": "Federal",
            "title": f"[Bill] {title[:200]}",
            "description": f"Congress {congress}, {bill_type} {number}. Latest action: {bill.get('latestAction', {}).get('text', 'N/A')}",
            "current_value": f"Status: {bill.get('latestAction', {}).get('text', 'Pending')}",
            "source_url": bill_url,
            "source_name": "Congress.gov",
            "effective_date": bill.get("updateDate", "")[:10] if bill.get("updateDate") else None,
        })

    return requirements


def _match_bill_to_category(title_lower: str) -> Optional[str]:
    """Best-effort mapping of a bill title to a compliance category."""
    keyword_to_category = {
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
    for kw, cat in keyword_to_category.items():
        if kw in title_lower:
            return cat
    return None


# ---------------------------------------------------------------------------
# CMS data
# ---------------------------------------------------------------------------

async def _fetch_cms_data(categories: set) -> List[dict]:
    """Fetch CMS dataset summaries relevant to healthcare compliance."""
    requirements = []

    # CMS Provider Data catalog — recent dataset updates
    url = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items?limit=20"
    try:
        async with _SEMAPHORE:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await _get_with_retry(client, url)
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
                "source_url": f"https://data.cms.gov/provider-data/",
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


# ---------------------------------------------------------------------------
# Document → requirement mapping
# ---------------------------------------------------------------------------

def _map_documents_to_requirements(
    docs: List[dict],
    source_label: str,
) -> List[dict]:
    """Map Federal Register documents to requirement dicts."""
    requirements = []

    for doc in docs:
        doc_agencies = [a.get("slug", "") for a in doc.get("agencies", [])]
        title = doc.get("title", "")
        if not title:
            continue

        # Match to category via agency slugs
        category = _match_doc_to_category(doc_agencies, title.lower())
        if not category:
            continue

        abstract = doc.get("abstract") or ""
        effective = doc.get("effective_on") or doc.get("publication_date") or ""
        html_url = doc.get("html_url") or doc.get("pdf_url") or ""
        doc_number = doc.get("document_number", "")

        # Build description from abstract + CFR references
        cfr_refs = doc.get("cfr_references", [])
        cfr_text = ""
        if cfr_refs:
            cfr_parts = []
            for ref in cfr_refs[:3]:
                if isinstance(ref, dict):
                    cfr_parts.append(f"{ref.get('title', '')} CFR {ref.get('part', '')}")
                else:
                    cfr_parts.append(str(ref))
            cfr_text = f" CFR: {', '.join(cfr_parts)}."

        description = f"{abstract[:400]}{cfr_text}" if abstract else f"Federal Register document {doc_number}.{cfr_text}"

        agency_names = [a.get("name", a.get("raw_name", "")) for a in doc.get("agencies", [])]

        requirements.append({
            "category": category,
            "jurisdiction_level": "federal",
            "jurisdiction_name": "Federal",
            "title": f"[{source_label}] {title[:200]}",
            "description": description[:500],
            "current_value": f"Published by {', '.join(agency_names[:2])}. Type: {doc.get('type', 'N/A')}",
            "source_url": html_url,
            "source_name": source_label,
            "effective_date": effective[:10] if effective else None,
        })

    return requirements


def _match_doc_to_category(
    agency_slugs: List[str],
    title_lower: str,
) -> Optional[str]:
    """Match a Federal Register document to a compliance category.

    Uses agency slug overlap + keyword matching for disambiguation.
    """
    best_cat = None
    best_score = 0

    for cat, cfg in CATEGORY_FEDERAL_REGISTER_AGENCIES.items():
        cat_agencies = set(cfg["agencies"])
        agency_overlap = len(cat_agencies & set(agency_slugs))
        if agency_overlap == 0:
            continue

        # Keyword bonus
        keyword_hits = sum(
            1 for kw in cfg["keywords"] if kw.lower() in title_lower
        )

        score = agency_overlap + (keyword_hits * 2)
        if score > best_score:
            best_score = score
            best_cat = cat

    return best_cat
