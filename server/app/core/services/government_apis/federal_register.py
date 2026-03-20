"""Federal Register API integration — per-category fetch with quality fixes.

Fixes vs original federal_sources.py:
1. Per-category fetch with keyword filter — stops category mismatches (e.g., DOJ
   immigration docs appearing in "antitrust")
2. Dedup by document_number — stable FR doc ID instead of title[:100]
3. Pagination — follows next_page_url up to max_docs total
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import AsyncGenerator, Dict, List, Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx

from ...compliance_registry import CATEGORY_FEDERAL_REGISTER_AGENCIES
from ._base import (
    _FEDERAL_REGISTER_BASE,
    _SEMAPHORE,
    _TIMEOUT,
    dedup_by_key,
    get_with_retry,
)

logger = logging.getLogger(__name__)

_MAX_DOCS_PER_RUN = 200  # cap total documents across all categories


async def _fetch_category_documents(
    client: httpx.AsyncClient,
    cat: str,
    cfg: dict,
    doc_type: str,
    one_year_ago: str,
    max_per_cat: int = 20,
) -> List[dict]:
    """Fetch Federal Register documents for a single category using both agency + keyword filters."""
    agencies = cfg.get("agencies", [])
    keywords = cfg.get("keywords", [])

    if not agencies:
        return []

    params = urlencode({
        "per_page": max_per_cat,
        "order": "newest",
        "conditions[type][]": doc_type,
        "conditions[publication_date][gte]": one_year_ago,
        # Use up to 3 keywords as an OR filter to narrow results
        "conditions[term]": " OR ".join(f'"{kw}"' for kw in keywords[:3]),
    })
    agency_params = "&".join(f"conditions[agencies][]={a}" for a in agencies)
    url = f"{_FEDERAL_REGISTER_BASE}/documents.json?{params}&{agency_params}"

    results: List[dict] = []
    fetched_urls = set()

    while url and len(results) < max_per_cat:
        if url in fetched_urls:
            break
        fetched_urls.add(url)

        try:
            async with _SEMAPHORE:
                resp = await get_with_retry(client, url)
            data = resp.json()
        except Exception:
            logger.warning("FR fetch failed for cat=%s type=%s", cat, doc_type)
            break

        page_results = data.get("results", [])
        results.extend(page_results)

        # Pagination
        url = data.get("next_page_url")
        if url:
            await asyncio.sleep(0.2)

    return results


async def _fetch_public_inspection(
    client: httpx.AsyncClient,
    all_agencies: set,
) -> List[dict]:
    """Fetch public inspection documents filtered to relevant agencies."""
    url = f"{_FEDERAL_REGISTER_BASE}/public-inspection-documents/current.json"
    try:
        async with _SEMAPHORE:
            resp = await get_with_retry(client, url)
        data = resp.json()
    except Exception:
        logger.warning("FR public inspection fetch failed")
        return []

    results = []
    for doc in data.get("results", []):
        doc_agencies = {a.get("slug", "") for a in doc.get("agencies", [])}
        if doc_agencies & all_agencies:
            results.append(doc)
    return results


def _map_doc_to_requirement(doc: dict, source_label: str, category: str) -> Optional[dict]:
    """Convert a Federal Register document dict to a requirement dict."""
    title = doc.get("title", "")
    if not title:
        return None

    abstract = doc.get("abstract") or ""
    effective = doc.get("effective_on") or doc.get("publication_date") or ""
    html_url = doc.get("html_url") or doc.get("pdf_url") or ""
    doc_number = doc.get("document_number", "")

    cfr_refs = doc.get("cfr_references", [])
    cfr_text = ""
    if cfr_refs:
        parts = []
        for ref in cfr_refs[:3]:
            if isinstance(ref, dict):
                parts.append(f"{ref.get('title', '')} CFR {ref.get('part', '')}")
            else:
                parts.append(str(ref))
        cfr_text = f" CFR: {', '.join(parts)}."

    description = (
        f"{abstract[:400]}{cfr_text}"
        if abstract
        else f"Federal Register document {doc_number}.{cfr_text}"
    )

    agency_names = [
        a.get("name") or a.get("raw_name", "")
        for a in doc.get("agencies", [])
    ]

    return {
        "category": category,
        "jurisdiction_level": "federal",
        "jurisdiction_name": "Federal",
        "title": f"[{source_label}] {title[:200]}",
        "description": description[:500],
        "current_value": (
            f"Published by {', '.join(agency_names[:2])}. "
            f"Type: {doc.get('type', 'N/A')}"
        ),
        "source_url": html_url,
        "source_name": source_label,
        "effective_date": effective[:10] if effective else None,
        # Store document_number for dedup key — not persisted to DB, used transiently
        "_document_number": doc_number,
    }


async def fetch_federal_register_requirements(
    jurisdiction_id: UUID,
) -> AsyncGenerator[dict, None]:
    """Fetch Federal Register requirements for all categories. Yields SSE events."""
    yield {"type": "status", "message": "Fetching Federal Register documents..."}

    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%m/%d/%Y")
    all_agencies = set()
    for cfg in CATEGORY_FEDERAL_REGISTER_AGENCIES.values():
        all_agencies.update(cfg.get("agencies", []))

    all_requirements: List[dict] = []

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # --- Final rules per category ---
        yield {"type": "status", "message": "Fetching Federal Register final rules (per category)..."}
        for cat, cfg in CATEGORY_FEDERAL_REGISTER_AGENCIES.items():
            docs = await _fetch_category_documents(client, cat, cfg, "RULE", one_year_ago)
            for doc in docs:
                req = _map_doc_to_requirement(doc, "Federal Register (Final Rule)", cat)
                if req:
                    all_requirements.append(req)
            await asyncio.sleep(0.1)

        rule_count = len(all_requirements)
        yield {"type": "progress", "message": f"Federal Register: {rule_count} final rules"}

        # --- Proposed rules per category ---
        yield {"type": "status", "message": "Fetching Federal Register proposed rules (per category)..."}
        proposed_start = len(all_requirements)
        for cat, cfg in CATEGORY_FEDERAL_REGISTER_AGENCIES.items():
            docs = await _fetch_category_documents(client, cat, cfg, "PRORULE", one_year_ago)
            for doc in docs:
                req = _map_doc_to_requirement(doc, "Federal Register (Proposed Rule)", cat)
                if req:
                    all_requirements.append(req)
            await asyncio.sleep(0.1)

        proposed_count = len(all_requirements) - proposed_start
        yield {"type": "progress", "message": f"Federal Register: {proposed_count} proposed rules"}

        # --- Public inspection ---
        yield {"type": "status", "message": "Fetching Federal Register public inspection documents..."}
        inspection_docs = await _fetch_public_inspection(client, all_agencies)

        # Map public inspection docs to categories using agency slug + keyword scoring
        for doc in inspection_docs:
            doc_agencies = [a.get("slug", "") for a in doc.get("agencies", [])]
            title_lower = doc.get("title", "").lower()
            cat = _match_doc_to_category(doc_agencies, title_lower)
            if cat:
                req = _map_doc_to_requirement(doc, "Federal Register (Public Inspection)", cat)
                if req:
                    all_requirements.append(req)

        yield {
            "type": "progress",
            "message": f"Federal Register: {len(inspection_docs)} public inspection docs scanned",
        }

    # Dedup by document_number (stable FR doc ID), fallback to title
    all_requirements = dedup_by_key(
        all_requirements,
        key_fn=lambda r: r.get("_document_number") or r.get("title", "").lower()[:100],
    )

    # Remove internal dedup field before returning
    for req in all_requirements:
        req.pop("_document_number", None)

    # Enforce total cap
    if len(all_requirements) > _MAX_DOCS_PER_RUN:
        all_requirements = all_requirements[:_MAX_DOCS_PER_RUN]

    yield {
        "type": "progress",
        "message": f"Federal Register: {len(all_requirements)} unique requirements after dedup",
    }
    yield {
        "type": "federal_register_done",
        "results": all_requirements,
        "count": len(all_requirements),
    }


def _match_doc_to_category(agency_slugs: List[str], title_lower: str) -> Optional[str]:
    """Match a document to a category via agency overlap + keyword scoring."""
    best_cat = None
    best_score = 0

    for cat, cfg in CATEGORY_FEDERAL_REGISTER_AGENCIES.items():
        cat_agencies = set(cfg.get("agencies", []))
        overlap = len(cat_agencies & set(agency_slugs))
        if overlap == 0:
            continue
        keyword_hits = sum(1 for kw in cfg.get("keywords", []) if kw.lower() in title_lower)
        score = overlap + keyword_hits * 2
        if score > best_score:
            best_score = score
            best_cat = cat

    return best_cat
