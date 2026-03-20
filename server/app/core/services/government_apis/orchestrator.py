"""Government API orchestrator — main entry point for all jurisdictions.

Routes by jurisdiction type:
  Federal (state="US", no city):  eCFR + Federal Register + CMS + Congress.gov
  State   (state!="US", no city): OpenStates legislative tracking
  City    (any city set):          same as state-level (city ordinances not in any API)

Exports:
  fetch_government_sources(jurisdiction_id)  → AsyncGenerator[dict, None]
  apply_government_sources(jurisdiction_id, requirements) → Dict[str, int]
"""

import logging
from typing import AsyncGenerator, Dict, List
from uuid import UUID

from ....database import get_connection
from ..compliance_service import _upsert_requirements_additive
from .cms import fetch_cms_requirements
from .congress import fetch_congress_requirements
from .ecfr import fetch_ecfr_requirements
from .federal_register import fetch_federal_register_requirements
from .openstates import fetch_openstates_for_jurisdiction

logger = logging.getLogger(__name__)


async def fetch_government_sources(
    jurisdiction_id: UUID,
) -> AsyncGenerator[dict, None]:
    """Fetch government API requirements for a jurisdiction. Yields SSE-style events.

    Federal jurisdictions get: eCFR + Federal Register + CMS + Congress.gov
    State/city jurisdictions get: OpenStates legislative tracking
    """
    async with get_connection() as conn:
        j = await conn.fetchrow(
            "SELECT id, city, state, name FROM jurisdictions WHERE id = $1",
            jurisdiction_id,
        )

    if not j:
        yield {"type": "error", "message": "Jurisdiction not found"}
        return

    state = j["state"]
    city = j["city"] or ""
    jname = j["name"] or (f"{city}, {state}" if city else state)
    is_federal = state == "US" and not city

    yield {
        "type": "started",
        "message": f"Starting government sources fetch for {jname}...",
    }

    all_requirements: List[dict] = []

    if is_federal:
        # eCFR — authoritative federal regulatory text
        async for event in fetch_ecfr_requirements(jurisdiction_id):
            if event.get("type") == "ecfr_done":
                all_requirements.extend(event.get("results", []))
            else:
                yield event

        # Federal Register — rules, proposed rules, public inspection
        async for event in fetch_federal_register_requirements(jurisdiction_id):
            if event.get("type") == "federal_register_done":
                all_requirements.extend(event.get("results", []))
            else:
                yield event

        # CMS — healthcare datasets
        async for event in fetch_cms_requirements(jurisdiction_id):
            if event.get("type") == "cms_done":
                all_requirements.extend(event.get("results", []))
            else:
                yield event

        # Congress.gov — bills (no-op if no key)
        async for event in fetch_congress_requirements(jurisdiction_id):
            if event.get("type") == "congress_done":
                all_requirements.extend(event.get("results", []))
            else:
                yield event

        tier = "tier_1_government"

    else:
        # State or city — OpenStates legislative tracking
        from ....config import get_settings
        try:
            settings = get_settings()
            api_key = settings.openstates_api_key or ""
        except Exception:
            api_key = ""

        state_name = jname if not city else state

        async for event in fetch_openstates_for_jurisdiction(
            jurisdiction_id, state, state_name, api_key
        ):
            if event.get("type") == "openstates_done":
                all_requirements.extend(event.get("results", []))
            else:
                yield event

        tier = "tier_2_official_secondary"

    # --- Build preview grouped by category ---
    by_category: Dict[str, list] = {}
    for req in all_requirements:
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
        "message": (
            f"Found {len(all_requirements)} requirements from government APIs. "
            f"Review below."
        ),
        "results": all_requirements,
        "by_category": by_category,
        "total": len(all_requirements),
        "category_count": len(by_category),
        # Pass tier so apply step knows what to use
        "source_tier": tier,
    }


async def apply_government_sources(
    jurisdiction_id: UUID,
    requirements: List[Dict],
    source_tier: str = "tier_1_government",
) -> Dict[str, int]:
    """Upsert government API requirements for a jurisdiction.

    Args:
        jurisdiction_id: Target jurisdiction UUID
        requirements: List of requirement dicts from fetch_government_sources
        source_tier: Tier for this batch. Federal = tier_1_government,
                     OpenStates = tier_2_official_secondary
    """
    async with get_connection() as conn:
        result = await _upsert_requirements_additive(
            conn,
            jurisdiction_id,
            requirements,
            research_source="official_api",
            source_tier=source_tier,
        )

        # When tier_1 rows land, supersede any coexisting Gemini/lower-tier rows
        # in the same categories so they can't pollute authoritative data.
        superseded = 0
        if source_tier == "tier_1_government" and requirements:
            tier1_categories = list({r["category"] for r in requirements if r.get("category")})
            if tier1_categories:
                superseded = await conn.fetchval(
                    """WITH updated AS (
                        UPDATE jurisdiction_requirements
                        SET status = 'superseded', updated_at = NOW()
                        WHERE jurisdiction_id = $1
                          AND category = ANY($2)
                          AND status = 'active'
                          AND (source_tier IS NULL OR source_tier = 'tier_3_aggregator')
                          AND requirement_key NOT IN (
                              SELECT requirement_key FROM jurisdiction_requirements
                              WHERE jurisdiction_id = $1
                                AND category = ANY($2)
                                AND source_tier = 'tier_1_government'
                          )
                        RETURNING 1
                    )
                    SELECT COUNT(*) FROM updated""",
                    jurisdiction_id,
                    tier1_categories,
                )
                if superseded:
                    logger.info(
                        "Superseded %d lower-tier rows for jurisdiction %s (tier_1 applied)",
                        superseded,
                        jurisdiction_id,
                    )
        result["superseded"] = superseded

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
            jurisdiction_id,
        )
        await conn.execute(
            """UPDATE jurisdictions
               SET last_verified_at = NOW(),
                   requirement_count = $1,
                   updated_at = NOW()
               WHERE id = $2""",
            count,
            jurisdiction_id,
        )
        return result
