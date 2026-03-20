"""eCFR (Code of Federal Regulations) API integration.

Fetches authoritative federal regulatory text for all 40 compliance categories.
API is free, no key required. Confirmed working as of 2026-03.

Endpoints used:
  GET /titles                                   → latest issue dates per title
  GET /structure/{date}/title-{N}.json?part={P} → TOC: part label, subparts, sections
  GET /versions/title-{N}?part={P}              → amendment history
"""

import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from ...compliance_registry import CATEGORY_FEDERAL_REGISTER_AGENCIES
from ._base import (
    _ECFR_BASE,
    _SEMAPHORE,
    _TIMEOUT,
    dedup_by_key,
    get_with_retry,
)

logger = logging.getLogger(__name__)

# Cache latest issue dates so we only call /titles once per run
_title_dates_cache: Dict[int, str] = {}


async def _fetch_title_dates(client: httpx.AsyncClient) -> Dict[int, str]:
    """Fetch latest issue dates for all CFR titles. Cached for the process lifetime."""
    global _title_dates_cache
    if _title_dates_cache:
        return _title_dates_cache

    async with _SEMAPHORE:
        resp = await get_with_retry(client, f"{_ECFR_BASE}/titles")
    titles = resp.json().get("titles", [])
    dates: Dict[int, str] = {}
    for t in titles:
        num = t.get("number")
        latest = t.get("latest_issue_date") or t.get("up_to_date_as_of")
        if num and latest:
            dates[int(num)] = latest

    _title_dates_cache = dates
    return dates


async def _fetch_part_structure(
    client: httpx.AsyncClient,
    title_num: int,
    part_num: int,
    issue_date: str,
) -> Optional[dict]:
    """Fetch structure JSON for a single CFR title/part."""
    url = f"{_ECFR_BASE}/structure/{issue_date}/title-{title_num}.json?part={part_num}"
    try:
        async with _SEMAPHORE:
            resp = await get_with_retry(client, url)
        return resp.json()
    except Exception:
        logger.warning("eCFR structure fetch failed: title=%d part=%d", title_num, part_num)
        return None


async def _fetch_part_versions(
    client: httpx.AsyncClient,
    title_num: int,
    part_num: int,
) -> Optional[str]:
    """Return the most recent amendment date for a CFR part."""
    url = f"{_ECFR_BASE}/versions/title-{title_num}?part={part_num}"
    try:
        async with _SEMAPHORE:
            resp = await get_with_retry(client, url)
        versions = resp.json().get("content_versions", [])
        if not versions:
            return None
        # Versions are newest-first per eCFR convention; take first date field
        for v in versions:
            d = v.get("date") or v.get("amendment_date")
            if d:
                return d[:10]
        return None
    except Exception:
        logger.debug("eCFR versions fetch failed: title=%d part=%d", title_num, part_num)
        return None


def _parse_structure(data: dict, title_num: int, part_num: int) -> Tuple[str, List[str], int, int]:
    """Extract part label, subpart names, subpart count, section count from structure JSON.

    Returns (part_label, subpart_labels, subpart_count, section_count).
    """
    # The structure JSON has a nested tree. The top level is a title node;
    # we need to find the part node matching part_num.
    def find_part(node: dict) -> Optional[dict]:
        node_type = node.get("type", "")
        if node_type == "part":
            # identifier may be "541" or "Part 541"
            identifier = str(node.get("identifier", "")).lstrip("0")
            if identifier == str(part_num) or identifier == f"part {part_num}":
                return node
        for child in node.get("children", []):
            result = find_part(child)
            if result:
                return result
        return None

    part_node = find_part(data) or data

    part_label = (
        part_node.get("label_level")
        or part_node.get("label")
        or part_node.get("heading")
        or f"Part {part_num}"
    )

    subpart_labels: List[str] = []
    section_count = 0

    def count_sections(node: dict) -> None:
        nonlocal section_count
        if node.get("type") == "section":
            section_count += 1
        for child in node.get("children", []):
            count_sections(child)

    for child in part_node.get("children", []):
        child_type = child.get("type", "")
        if child_type == "subpart":
            label = child.get("label_level") or child.get("heading") or child.get("label", "")
            if label:
                subpart_labels.append(label)
        count_sections(child)

    # If no subparts, count sections at the part level directly
    if section_count == 0:
        count_sections(part_node)

    return part_label, subpart_labels, len(subpart_labels), section_count


def _build_requirement(
    category: str,
    title_num: int,
    part_num: int,
    part_label: str,
    subpart_labels: List[str],
    subpart_count: int,
    section_count: int,
    amendment_date: Optional[str],
) -> dict:
    """Build a requirement dict for an eCFR part."""
    title = f"{title_num} CFR Part {part_num} \u2013 {part_label}"

    if subpart_labels:
        subpart_preview = "; ".join(subpart_labels[:4])
        if len(subpart_labels) > 4:
            subpart_preview += f"; and {len(subpart_labels) - 4} more subparts"
        description = f"Subparts: {subpart_preview}."
    else:
        description = f"Federal regulation covering {part_label}."

    counts = []
    if subpart_count:
        counts.append(f"{subpart_count} subparts")
    if section_count:
        counts.append(f"{section_count} sections")
    counts_str = ", ".join(counts) if counts else "see full text"
    last_amended = f" Last amended: {amendment_date}." if amendment_date else ""
    current_value = f"Part {part_num}, {counts_str}.{last_amended}"

    source_url = f"https://www.ecfr.gov/current/title-{title_num}/part-{part_num}"

    return {
        "category": category,
        "jurisdiction_level": "federal",
        "jurisdiction_name": "Federal",
        "title": title,
        "description": description,
        "current_value": current_value,
        "source_url": source_url,
        "source_name": "eCFR (Code of Federal Regulations)",
        "effective_date": amendment_date,
        # Note: no regulation_key — _compute_requirement_key will produce a stable
        # title-based key like "overtime:29 cfr part 541 ..."
    }


async def fetch_ecfr_requirements(
    jurisdiction_id,  # UUID, unused here but kept for orchestrator interface consistency
) -> AsyncGenerator[dict, None]:
    """Fetch eCFR requirements for all categories. Yields SSE-style event dicts."""
    yield {"type": "status", "message": "Fetching eCFR regulatory text..."}

    requirements: List[dict] = []

    # Collect all (category, title, part) triples from registry
    triples: List[Tuple[str, int, int]] = []
    for cat, cfg in CATEGORY_FEDERAL_REGISTER_AGENCIES.items():
        cfr_parts_map: Dict[int, List[int]] = cfg.get("cfr_parts", {})
        for title_num, parts in cfr_parts_map.items():
            for part_num in parts:
                triples.append((cat, title_num, part_num))

    yield {"type": "progress", "message": f"Querying eCFR for {len(triples)} part/category combinations..."}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # Fetch title dates once
        try:
            title_dates = await _fetch_title_dates(client)
        except Exception:
            logger.error("Failed to fetch eCFR title dates", exc_info=True)
            yield {"type": "warning", "message": "eCFR: could not fetch title dates, skipping"}
            return

        # Track seen (title_num, part_num) to deduplicate across categories
        # (Same CFR part might appear in two categories — keep first, different category)
        seen_title_part: Dict[Tuple[int, int], str] = {}  # → category
        fetched = 0
        skipped = 0

        for cat, title_num, part_num in triples:
            issue_date = title_dates.get(title_num)
            if not issue_date:
                logger.warning("No issue date for CFR title %d, skipping part %d", title_num, part_num)
                skipped += 1
                continue

            # Fetch structure + versions concurrently
            try:
                structure_data, amendment_date = await asyncio.gather(
                    _fetch_part_structure(client, title_num, part_num, issue_date),
                    _fetch_part_versions(client, title_num, part_num),
                )
            except Exception:
                logger.warning("eCFR fetch error for %d CFR %d", title_num, part_num, exc_info=True)
                skipped += 1
                await asyncio.sleep(0.3)
                continue

            if structure_data is None:
                skipped += 1
                await asyncio.sleep(0.3)
                continue

            part_label, subpart_labels, subpart_count, section_count = _parse_structure(
                structure_data, title_num, part_num
            )

            req = _build_requirement(
                category=cat,
                title_num=title_num,
                part_num=part_num,
                part_label=part_label,
                subpart_labels=subpart_labels,
                subpart_count=subpart_count,
                section_count=section_count,
                amendment_date=amendment_date,
            )
            requirements.append(req)
            fetched += 1

            # Be a good API citizen
            await asyncio.sleep(0.3)

    # Dedup by (title, part) slug within each category — first occurrence wins
    requirements = dedup_by_key(
        requirements,
        key_fn=lambda r: r.get("title", "").lower()[:120],
    )

    yield {
        "type": "progress",
        "message": f"eCFR: {fetched} parts fetched, {skipped} skipped, {len(requirements)} unique requirements",
    }
    yield {"type": "ecfr_done", "results": requirements, "count": len(requirements)}
