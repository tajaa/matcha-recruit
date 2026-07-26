"""Company profile fetch + cache for AI context injection.

TTL+LRU cache for company profiles — avoids re-fetching on every message.
Bounded size prevents unbounded growth on a long-running server. cachetools
evicts oldest entries when full and drops expired entries on access.
This is the ONLY instantiation of the cache — do not create a second one.
"""
import logging
from collections import defaultdict
from uuid import UUID

from cachetools import TTLCache

from app.database import get_connection
from app.core.services.compliance_service import codified_gate_sql, get_locations

logger = logging.getLogger(__name__)

_PROFILE_CACHE_TTL = 300  # 5 minutes
_PROFILE_CACHE_MAX = 1000  # caps memory at ~companies × profile size
_company_profile_cache: TTLCache = TTLCache(maxsize=_PROFILE_CACHE_MAX, ttl=_PROFILE_CACHE_TTL)


def invalidate_company_profile_cache(company_id: UUID) -> None:
    """Remove a company's cached profile so the next call fetches fresh data."""
    _company_profile_cache.pop(str(company_id), None)


async def get_company_profile_for_ai(company_id: UUID) -> dict:
    """Fetch the company profile fields relevant to AI context."""
    key = str(company_id)
    cached = _company_profile_cache.get(key)
    if cached is not None:
        return dict(cached)  # return a copy so callers can't corrupt cache

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT name, industry, size,
                   headquarters_state, headquarters_city, work_arrangement,
                   default_employment_type, benefits_summary, pto_policy_summary,
                   compensation_notes, company_values, ai_guidance_notes,
                   COALESCE(is_personal, false) AS is_personal
            FROM companies
            WHERE id = $1
            """,
            company_id,
        )
        if row is None:
            _company_profile_cache[key] = {}
            return {}
        profile = {k: v for k, v in dict(row).items() if v is not None}

    # Match the Compliance page's business-specific active locations and filtered requirements.
    try:
        locations = [
            loc for loc in await get_locations(company_id)
            if loc.get("is_active", True)
        ]
    except Exception:
        logger.warning("Failed to load compliance locations for Matcha Work AI context", exc_info=True)
        _company_profile_cache[key] = profile
        return profile

    if not locations:
        _company_profile_cache[key] = profile
        return profile

    def _location_label(loc: dict) -> str:
        city = (loc.get("city") or "").strip()
        state = (loc.get("state") or "").strip()
        return f"{city}, {state}" if city else state

    location_labels = {
        str(loc["id"]): _location_label(loc)
        for loc in locations
        if loc.get("id") and _location_label(loc)
    }
    profile["compliance_locations"] = "; ".join(location_labels.values())

    # Fetch all requirements for all locations in a single query to avoid
    # connection pool exhaustion.  The old approach called get_location_requirements()
    # per location via asyncio.gather — each call held a pool connection while also
    # trying to acquire another for get_employee_impact_for_location(), causing a
    # deadlock when the company had 6+ locations (pool max_size=10).
    location_ids = [loc["id"] for loc in locations if loc.get("id")]
    try:
        async with get_connection() as conn:
            # Same codified gate as the Requirements tab. This profile is injected
            # into EVERY matcha-work AI thread, not just compliance-mode ones, so
            # ungated it is the widest path by which a rule we never tied to a
            # statute reaches a user — stated by the model, with no tab to check
            # it against.
            req_rows = await conn.fetch(
                """
                SELECT r.location_id, r.category, r.jurisdiction_name,
                       r.current_value, r.title
                FROM compliance_requirements r
                LEFT JOIN jurisdiction_requirements cat
                  ON cat.id = r.jurisdiction_requirement_id
                WHERE r.location_id = ANY($1::uuid[])
                """
                + await codified_gate_sql("cat", conn=conn)
                + " ORDER BY r.location_id, r.category, r.jurisdiction_level",
                location_ids,
            )
    except Exception:
        logger.warning("Failed to load compliance requirements for Matcha Work AI context", exc_info=True)
        _company_profile_cache[key] = profile
        return profile

    # Group requirements by location
    reqs_by_location: dict[str, list[dict]] = defaultdict(list)
    for rr in req_rows:
        reqs_by_location[str(rr["location_id"])].append(dict(rr))

    location_lines: list[str] = []
    for loc in locations:
        loc_id_str = str(loc.get("id", ""))
        loc_reqs = reqs_by_location.get(loc_id_str, [])
        if not loc_reqs:
            continue

        entries: list[str] = []
        seen_entries: set[str] = set()
        for req in loc_reqs:
            value = (req.get("current_value") or req.get("title") or "").strip()
            if not value:
                continue
            entry = f"{req['category']} ({req['jurisdiction_name']}: {value})"
            if entry in seen_entries:
                continue
            seen_entries.add(entry)
            entries.append(entry)

        if entries:
            location_lines.append(f"  {location_labels.get(loc_id_str, _location_label(loc))}: {'; '.join(entries)}")

    if location_lines:
        profile["jurisdiction_requirements_summary"] = "\n".join(location_lines)

    _company_profile_cache[key] = profile
    return profile
