"""The shadow→authoritative cutover gate (SCOPE_REGISTRY_PLAN.md commit 5,
the deferred step — see COMPLIANCE_SYSTEM_GAP_REVIEW.md §2).

``expand_scope → map_to_bank`` stays the sole writer everywhere except the
allowlisted (state, industry) pairs below, where the engine is proven enough
(federal+CA, dense corpus) to union its codified keys into the bank
projection alongside the category-grab — additive only, never a replacement:
a coordinate the engine misses still gets whatever expand_scope found.

Allowlist is a code constant, not an admin-toggleable DB flag, on purpose:
turning a coordinate on here is a reviewed code change, not a click — the
`scope_shadow_log` agreement rate (surfaced in the Scope Studio shadow-log
panel) is the evidence that justifies widening this list, and a self-serve
toggle would let someone flip it before that evidence exists.
"""
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# (state, industry) pairs where the engine is trusted to add to the
# projection. industry=None matches any industry for that state.
CUTOVER_ALLOWLIST = {("CA", None)}


def is_cutover_active(state: Optional[str], industry: Optional[str]) -> bool:
    if not state:
        return False
    state = state.upper()
    return (state, None) in CUTOVER_ALLOWLIST or (state, industry) in CUTOVER_ALLOWLIST


async def engine_sourced_scope_items(
    conn, company_id: UUID, *, industry: Optional[str],
) -> List[Dict[str, Any]]:
    """Engine-definitive codified keys for this company, translated into
    ``existing_items``-shaped dicts (``_write_compliance_scope_rows``'
    input shape) — additive to whatever ``map_to_bank`` already resolved.

    Company-wide gate (not per-location): only proceeds when
    ``resolve_company_scope``'s aggregate reports ``coverage_source ==
    "engine"``, i.e. EVERY one of the company's locations resolved
    definitively — stricter than a per-coordinate gate, deliberately, since
    a split-brained "some locations trust the engine, some don't" adds
    complexity without proportionate benefit for a first cutover. Returns
    ``[]`` (safe no-op) on any failure or non-definitive result — the
    category-grab already covers this company either way.
    """
    from .gap_surfaces import resolve_company_scope
    from .jurisdiction_chain import resolve_jurisdiction_chain

    try:
        locs = await conn.fetch(
            """
            SELECT DISTINCT state FROM business_locations
            WHERE company_id = $1 AND COALESCE(is_active, true)
              AND state IS NOT NULL AND NOT COALESCE(is_company_wide, false)
            """,
            company_id,
        )
        states = {r["state"].upper() for r in locs if r["state"]}
        if not states or not all(is_cutover_active(s, industry) for s in states):
            return []

        agg = await resolve_company_scope(conn, company_id, industry=industry)
        if agg.get("coverage_source") != "engine" or not agg.get("codified_keys"):
            return []

        chain_ids: set = set()
        for state in states:
            chain = await resolve_jurisdiction_chain(conn, state, None)
            chain_ids.update(chain.get("ids") or [])
        if not chain_ids:
            return []

        rows = await conn.fetch(
            """
            SELECT id, regulation_key, jurisdiction_level
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = ANY($1::uuid[])
              AND regulation_key = ANY($2::text[])
              AND COALESCE(status, 'active') = 'active'
            """,
            list(chain_ids), agg["codified_keys"],
        )
        # state/county/city deliberately left unset — _write_compliance_scope_rows
        # falls back to the company's first real location for non-federal
        # items, which is correct for the single-state case this allowlist
        # targets today. Revisit if the allowlist widens to multi-state
        # companies before per-location precision is threaded through.
        return [
            {"requirement_id": r["id"], "scope_level": (r["jurisdiction_level"] or "federal").lower()}
            for r in rows
        ]
    except Exception:
        logger.exception("cutover: engine_sourced_scope_items failed for company %s", company_id)
        return []
