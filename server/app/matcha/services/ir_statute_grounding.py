"""IR jurisdiction-aware statute grounding.

Two consumers, both additive and both degrade to today's behavior on an empty
result:

1. **Statute-level policy mapping** — alongside the existing incident→handbook
   policy mapping, surface which *safety statutes* an incident implicates, pulled
   from the shared `jurisdiction_requirements` catalog for the incident's
   establishment (`incident.location_id`).
2. **Copilot context** — a compact statute block injected into the IR copilot
   prompt so guidance is location-aware (never to compute reporting deadlines —
   those stay in the deterministic OSHA gate, `ir_flow` / `osha.py`).

Resolution reuses `compliance_service.get_location_requirements`, which is the
correct tenant-projection read: codified-gated internally, with preemption /
company / city-ordinance filtering already applied, and authority resolved
through the catalog FK (not the untrustworthy denormalized `jurisdiction_level`
/`_name` free-text columns).

The incident→category mapping is a **deterministic heuristic** — no second LLM
call. A model scoring statute relevance is a v1.1 candidate (same shapes + the
shared `legal_defense.validate_citations` gate); v1 is honest and cheap, which
matters while the codified corpus is thin (federal + CA mostly).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# incident_type vocabulary is IRIncidentType = Literal["safety", "behavioral",
# "property", "near_miss", "other"] (models/ir_incident.py). Only these two are
# workplace-safety events; a behavioral/harassment incident implicates ER law,
# not OSHA. So a keyword-less incident defaults to "all safety categories" ONLY
# when it is genuinely a safety-typed report — otherwise it grounds on nothing.
_SAFETY_INCIDENT_TYPES: frozenset[str] = frozenset({"safety", "near_miss"})

# Safety / workers-comp category slugs that exist in the catalog taxonomy
# (core labor + manufacturing industry keysets). Everything else is out of scope
# for an incident-report grounding.
IR_SAFETY_CATEGORIES: frozenset[str] = frozenset({
    "workplace_safety",
    "workers_comp",
    "machine_safety",
    "chemical_safety",
    "process_safety",
    "industrial_hygiene",
})

# Which safety categories a given incident flavor implicates. Matched against the
# incident's type/category and a keyword scan of its description; the union of
# every hit is the implicated set. No hit → all safety categories (generic
# "these safety obligations apply here", honestly un-narrowed).
_INCIDENT_CATEGORY_HINTS: dict[str, frozenset[str]] = {
    "injury": frozenset({"workplace_safety", "workers_comp"}),
    "illness": frozenset({"workplace_safety", "workers_comp", "industrial_hygiene"}),
    "chemical": frozenset({"chemical_safety", "industrial_hygiene", "workplace_safety"}),
    "exposure": frozenset({"chemical_safety", "industrial_hygiene"}),
    "spill": frozenset({"chemical_safety", "process_safety"}),
    "equipment": frozenset({"machine_safety", "workplace_safety"}),
    "machine": frozenset({"machine_safety", "workplace_safety"}),
    "lockout": frozenset({"machine_safety"}),
    "fall": frozenset({"workplace_safety"}),
    "ergonomic": frozenset({"industrial_hygiene", "workplace_safety"}),
    "noise": frozenset({"industrial_hygiene"}),
    "explosion": frozenset({"process_safety", "chemical_safety"}),
    "fire": frozenset({"process_safety", "workplace_safety"}),
}

_MAX_CONTEXT_ITEMS = 15


def _implicated_categories(incident: dict) -> frozenset[str]:
    """Which safety categories this incident implicates.

    Keyword hints are scanned over the incident's free text AND the structured
    `category_data` values (incident_type is a coarse 5-value enum the keywords
    can't match, so it only gates the no-hit fallback). No keyword hit → all
    safety categories for a safety/near-miss incident, nothing for anything else.
    """
    parts = [str(incident.get(k) or "").lower() for k in ("title", "description")]
    cd = incident.get("category_data")
    if isinstance(cd, dict):
        parts.extend(str(v).lower() for v in cd.values())
    haystack = " ".join(parts)

    hit: set[str] = set()
    for keyword, cats in _INCIDENT_CATEGORY_HINTS.items():
        if keyword in haystack:
            hit |= set(cats)
    if hit:
        return frozenset(hit)

    itype = str(incident.get("incident_type") or "").strip().lower()
    return IR_SAFETY_CATEGORIES if itype in _SAFETY_INCIDENT_TYPES else frozenset()


async def get_incident_statutes(incident: dict, company_id) -> list[dict[str, Any]]:
    """Codified safety requirements for the incident's establishment.

    A dedicated codified-gated read over the catalog — deliberately NOT
    `get_location_requirements`, which runs the full tenant projection
    (employee-impact aggregation, preemption, min-wage counts) only to have all
    but the 6 safety categories discarded here, on the hot path of incident
    analysis. Resolves state from the incident's establishment, adds federal
    ('US'), and labels each row from the FK-resolved `authority_name` — never the
    documented-corrupt denormalized `jurisdiction_name`.

    Returns ``[]`` when the incident has no ``location_id`` or nothing resolves —
    callers hide the statute surface entirely in that case."""
    raw_loc = incident.get("location_id")
    if not raw_loc:
        return []
    try:
        location_id = raw_loc if isinstance(raw_loc, UUID) else UUID(str(raw_loc))
        company_uuid = company_id if isinstance(company_id, UUID) else UUID(str(company_id))
    except (ValueError, TypeError):
        return []

    try:
        from app.database import get_connection
        from app.core.services.compliance_service import codified_gate_sql

        async with get_connection() as conn:
            loc = await conn.fetchrow(
                "SELECT state FROM business_locations WHERE id = $1 AND company_id = $2",
                location_id,
                company_uuid,
            )
            if not loc or not loc["state"]:
                return []
            state = (loc["state"] or "").strip().upper()
            gate = await codified_gate_sql("jr", conn=conn)
            rows = await conn.fetch(
                f"""
                SELECT jr.id, j.state, jr.category, jr.title, jr.description,
                       jr.statute_citation, jr.source_url,
                       j.display_name AS authority_name, j.level::text AS authority_level
                FROM jurisdiction_requirements jr
                JOIN jurisdictions j ON j.id = jr.jurisdiction_id
                WHERE j.state = ANY($1::varchar[])
                  AND jr.status = 'active'
                  AND (jr.expiration_date IS NULL OR jr.expiration_date >= CURRENT_DATE)
                  AND jr.category = ANY($2::varchar[])
                  {gate}
                ORDER BY (j.state = 'US') ASC, jr.category
                LIMIT 40
                """,
                sorted({state, "US"}),
                list(IR_SAFETY_CATEGORIES),
            )
    except Exception:
        logger.exception("ir_statute_grounding: requirement fetch failed")
        return []

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "requirement_id": str(r["id"]),
            "state": r["authority_name"] or r["state"] or "",
            "category": (r["category"] or "").strip().lower(),
            "title": r["title"] or "Requirement",
            "description": r["description"] or "",
            "statute_citation": r["statute_citation"],
            "source_url": r["source_url"],
        })
    return out


def map_incident_to_statutes(
    incident: dict, statutes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pure: narrow the location's safety statutes to those this incident type
    implicates, each tagged with a templated ``relevance_reason``."""
    if not statutes:
        return []
    cats = _implicated_categories(incident)
    if not cats:
        return []
    itype = str(incident.get("incident_type") or "this incident").strip()
    out: list[dict[str, Any]] = []
    for s in statutes:
        if s.get("category") not in cats:
            continue
        cat_label = str(s.get("category") or "").replace("_", " ")
        # Spread the source row and add the reason — one shape, not a hand-copied
        # field list. StatuteMatch ignores the extra `description` key on parse.
        out.append({
            **s,
            "relevance_reason": f"Incident type “{itype}” implicates {cat_label} requirements at this location.",
        })
    return out


def serialize_statute_context(
    statutes: list[dict[str, Any]], max_items: int = _MAX_CONTEXT_ITEMS
) -> str:
    """Compact prompt block for the copilot. ``''`` when empty."""
    if not statutes:
        return ""
    lines: list[str] = []
    for s in statutes[:max_items]:
        state = s.get("state") or ""
        category = s.get("category") or ""
        title = s.get("title") or "Requirement"
        citation = s.get("statute_citation")
        tail = f" [{citation}]" if citation else ""
        lines.append(f"- ({state} — {category}) {title}{tail}")
    return "\n".join(lines)
