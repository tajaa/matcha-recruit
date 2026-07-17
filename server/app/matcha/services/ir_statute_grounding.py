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
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

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
    haystack = " ".join(
        str(incident.get(k) or "").lower()
        for k in ("incident_type", "category", "type", "title", "description")
    )
    hit: set[str] = set()
    for keyword, cats in _INCIDENT_CATEGORY_HINTS.items():
        if keyword in haystack:
            hit |= set(cats)
    return frozenset(hit) if hit else IR_SAFETY_CATEGORIES


async def get_incident_statutes(incident: dict, company_id) -> list[dict[str, Any]]:
    """Codified safety requirements for the incident's establishment.

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
        from app.core.services import compliance_service

        reqs = await compliance_service.get_location_requirements(
            location_id, company_uuid, category=None
        )
    except Exception:
        logger.exception("ir_statute_grounding: requirement fetch failed")
        return []

    out: list[dict[str, Any]] = []
    for r in reqs:
        category = (getattr(r, "category", "") or "").strip().lower()
        if category not in IR_SAFETY_CATEGORIES:
            continue
        out.append({
            "requirement_id": str(getattr(r, "id", "") or ""),
            "state": getattr(r, "jurisdiction_name", None) or "",
            "category": category,
            "title": getattr(r, "title", None) or "Requirement",
            "description": getattr(r, "description", None) or "",
            "statute_citation": getattr(r, "statute_citation", None),
            "source_url": getattr(r, "source_url", None),
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
    itype = str(incident.get("incident_type") or incident.get("category") or "this incident").strip()
    out: list[dict[str, Any]] = []
    for s in statutes:
        if s.get("category") not in cats:
            continue
        cat_label = str(s.get("category") or "").replace("_", " ")
        out.append({
            "requirement_id": s.get("requirement_id"),
            "state": s.get("state") or "",
            "category": s.get("category") or "",
            "title": s.get("title") or "Requirement",
            "statute_citation": s.get("statute_citation"),
            "source_url": s.get("source_url"),
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
