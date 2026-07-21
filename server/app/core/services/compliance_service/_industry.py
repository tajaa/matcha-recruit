"""compliance_service.industry — J6 split of compliance_service.py."""
from typing import Optional, List, AsyncGenerator, Dict, Any, Callable, Tuple
from uuid import UUID
from datetime import date, datetime, timedelta
import asyncio
import json
import logging
import re

import asyncpg
import httpx
from fastapi import HTTPException

from app.core.services.scope_registry.codify import codified_sql
from app.core.services.company_contacts import get_company_name_and_contacts
from app.core.services.jurisdiction_context import (
    get_known_sources,
    record_source,
    extract_domain,
    build_context_prompt,
    get_source_reputations,
    update_source_accuracy,
)
from app.core.models.compliance import (
    BusinessLocation,
    ComplianceRequirement,
    ComplianceAlert,
    LocationCreate,
    LocationUpdate,
    AutoCheckSettings,
    RequirementResponse,
    AlertResponse,
    CheckLogEntry,
    UpcomingLegislationResponse,
    VerificationResult,
    ComplianceSummary,
)
from app.core.compliance_registry import (
    LABOR_CATEGORIES as REQUIRED_LABOR_CATEGORIES,
    HEALTHCARE_CATEGORIES,
    ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES,
    LIFE_SCIENCES_CATEGORIES,
    INDUSTRY_TAGS as MEDICAL_COMPLIANCE_INDUSTRY_TAGS,
)

logger = logging.getLogger(__name__)

from app.core.services.compliance_service._normalize import (
    _normalize_category,
    _normalize_rate_type,
)


def _resolve_industry(raw: Optional[str]) -> str:
    """Resolve a free-text industry string to a canonical industry name.

    Thin shim over the scope-registry taxonomy — the module-level
    ``_INDUSTRY_ALIASES`` dict this used to carry now lives (absorbed with the
    six other legacy vocabularies) in
    ``app.core.services.scope_registry.categories``, which is the single
    canonical vocabulary going forward. Same outputs as before for every
    legacy input, with one deliberate change: ``warehouse`` no longer resolves
    to ``manufacturing`` (SCOPE_REGISTRY_PLAN.md §1 — a warehouse is general
    industry, and scoping it as a factory served it RCRA/EPCRA while making
    CA AB 701 unreachable).
    """
    from app.core.services.scope_registry.categories import resolve_legacy_industry

    return resolve_legacy_industry(raw)




async def _get_company_canonical_industry(
    conn, company_id: UUID
) -> Optional[str]:
    """Return the canonical industry key for a company, if resolvable."""
    raw = await conn.fetchval("SELECT industry FROM companies WHERE id = $1", company_id)
    canonical = _resolve_industry(raw)
    return canonical or None




async def _get_company_industry_tags(conn, company_id: UUID) -> set:
    """Return the set of industry tags this company should match against.

    An oncology healthcare company returns: {"healthcare", "healthcare:oncology"}
    A plain healthcare company returns: {"healthcare"}
    A retail company returns: {"retail"}
    """
    row = await conn.fetchrow(
        "SELECT industry, healthcare_specialties FROM companies WHERE id = $1",
        company_id,
    )
    if not row:
        return set()
    canonical = _resolve_industry(row["industry"] or "")
    if not canonical:
        return set()
    tags = {canonical}
    if canonical == "healthcare" and row["healthcare_specialties"]:
        for spec in row["healthcare_specialties"]:
            tags.add(f"healthcare:{spec}")
    if canonical == "biotech":
        tags.add("healthcare")  # Biotech inherits applicable healthcare categories
    return tags




_HEALTHCARE_TEXT_MARKERS = (
    "healthcare worker",
    "health care worker",
    "healthcare employee",
    "health care employee",
    "hospital employee",
    "hospital worker",
    "hospital staff",
    "health facility",
    "medical facility",
    "medical office",
    "nursing facility",
    "patient care staff",
    "registered nurse",
    "licensed vocational nurse",
    "licensed practical nurse",
)



_ONCOLOGY_TEXT_MARKERS = (
    "radiation safety", "radiation therapy", "radiation oncology",
    "chemotherapy", "chemo", "hazardous drug", "antineoplastic",
    "tumor registry", "cancer registry", "oncology",
    "brachytherapy", "linear accelerator", "linac",
)




def _looks_healthcare_specific(req: Dict[str, Any]) -> bool:
    """Infer healthcare-only labor rows that were saved without industry tags."""
    haystack = " ".join(
        str(req.get(field) or "")
        for field in ("title", "description", "current_value", "source_name")
    ).lower()
    if not haystack:
        return False

    if any(marker in haystack for marker in _HEALTHCARE_TEXT_MARKERS):
        return True

    if " sb 525" in f" {haystack}" or "mandatory overtime for nurses" in haystack:
        return True

    return False




def _looks_oncology_specific(req: Dict[str, Any]) -> bool:
    """Infer oncology-only rows that were saved without industry tags."""
    haystack = " ".join(
        str(req.get(field) or "")
        for field in ("title", "description", "current_value", "source_name")
    ).lower()
    if not haystack:
        return False
    return any(marker in haystack for marker in _ONCOLOGY_TEXT_MARKERS)




def _requirement_applicable_industries(req: Dict[str, Any]) -> set:
    """Return canonical industries a requirement applies to."""
    raw_industries = req.get("applicable_industries")
    if isinstance(raw_industries, str):
        raw_industries = [raw_industries]

    normalized = set()
    for industry in raw_industries or []:
        tag = str(industry).strip().lower()
        if ":" in tag:
            # Hierarchical tag like "healthcare:oncology" — keep as-is
            normalized.add(tag)
        else:
            canonical = _resolve_industry(tag)
            normalized.add(canonical or tag)

    if normalized:
        return normalized

    # Older healthcare rows may have missed the explicit tag. Infer them here
    # so retail/company syncs still drop those rows on the next resync/read.
    category = _normalize_category(req.get("category"))
    rate_type = _normalize_rate_type(req.get("rate_type"))

    if category in ONCOLOGY_CATEGORIES or _looks_oncology_specific(req):
        return {"healthcare:oncology"}

    if category in MEDICAL_COMPLIANCE_CATEGORIES:
        return {MEDICAL_COMPLIANCE_INDUSTRY_TAGS.get(category, "healthcare")}

    if (
        category in HEALTHCARE_CATEGORIES
        or rate_type == "healthcare"
        or _looks_healthcare_specific(req)
    ):
        return {"healthcare"}

    return set()



# Industry-specific context strings injected into Gemini research prompts.
_INDUSTRY_RESEARCH_CONTEXT: Dict[str, str] = {
    "healthcare": (
        "\n\nINDUSTRY CONTEXT — HEALTHCARE EMPLOYER:\n"
        "This business operates in the HEALTHCARE industry (hospitals, clinics, "
        "medical offices, nursing facilities, or similar). In addition to standard "
        "requirements, you MUST research healthcare-specific variants:\n"
        "- Healthcare worker minimum wage laws (e.g., CA SB 525 — $25/hr for healthcare workers)\n"
        "- Hospital/healthcare 8/80 overtime rules (FLSA Section 7(j))\n"
        "- Mandatory overtime bans or restrictions for nurses/healthcare workers "
        "(e.g., OR HB 2800, NJ Mandatory Overtime for Healthcare Workers Act)\n"
        "- Nurse staffing ratio requirements (CA, MA, NY)\n"
        "- Healthcare-specific scheduling and mandatory rest period rules "
        "(e.g., minimum hours between shifts for nurses)\n"
        "- Healthcare worker meal/rest break exceptions and penalty pay\n"
        "- Enhanced sick leave provisions for healthcare workers\n"
        "Return these as SEPARATE requirements with rate_type='healthcare' where applicable.\n"
        'For each healthcare-specific requirement, include "applicable_industries": ["healthcare"] in the returned JSON.'
    ),
    "healthcare:oncology": (
        "\n\nINDUSTRY CONTEXT — ONCOLOGY PRACTICE:\n"
        "This is an ONCOLOGY healthcare employer (cancer treatment center, radiation "
        "oncology clinic, medical oncology practice, or similar). In addition to standard "
        "healthcare requirements, you MUST research oncology-specific regulations:\n"
        "- NRC 10 CFR 35 / state radiation safety licensing and machine QA\n"
        "- USP <800> hazardous drug handling (chemotherapy compounding, spill kits, PPE)\n"
        "- OSHA chemotherapy exposure limits and monitoring\n"
        "- State tumor/cancer registry reporting mandates\n"
        "- Clinical trial regulations (21 CFR 50/56 informed consent, IRB oversight)\n"
        "- Oncology patient rights (treatment refusal, second opinion, palliative care access)\n"
        'Tag each oncology-specific requirement with "applicable_industries": ["healthcare:oncology"].'
    ),
}




async def _get_industry_profile(
    conn, company_id: UUID
) -> Optional[Dict[str, Any]]:
    """Look up the industry compliance profile for a company.

    Returns a dict with focused_categories, rate_types, category_order,
    category_evidence, and industry_context (prompt string), or None.
    """
    canonical = await _get_company_canonical_industry(conn, company_id)
    if not canonical:
        return None

    # industry_compliance_profiles was dropped as "unused" in migration
    # zzh8i9j0k1l2 (2026-04-07) while this lookup still referenced it — it went
    # unnoticed because no self-serve company had an industry set until signup
    # started collecting one. This call sits OUTSIDE the try blocks in both
    # run_compliance_check_stream/_background, so an unguarded UndefinedTableError
    # here kills the entire compliance check. Fall back to the code-level
    # industry context so industry-aware prompts survive without the table
    # (a real profile table returns with the E2 industry overhaul).
    profile_row = None
    try:
        profile_row = await conn.fetchrow(
            "SELECT * FROM industry_compliance_profiles WHERE LOWER(name) LIKE $1",
            f"%{canonical}%",
        )
    except asyncpg.UndefinedTableError:
        logger.warning(
            "industry_compliance_profiles table missing (dropped in zzh8i9j0k1l2); "
            "using code-level industry context for %s", canonical,
        )
    except Exception:
        logger.warning(
            "industry profile lookup failed for %s; using code-level context",
            canonical, exc_info=True,
        )

    industry_context = _INDUSTRY_RESEARCH_CONTEXT.get(canonical, "")
    if not profile_row:
        if not industry_context:
            return None
        return {
            "id": None,
            "name": canonical,
            "canonical_industry": canonical,
            "focused_categories": [],
            "rate_types": [],
            "category_order": [],
            "category_evidence": None,
            "industry_context": industry_context,
        }

    return {
        "id": str(profile_row["id"]),
        "name": profile_row["name"],
        "canonical_industry": canonical,
        "focused_categories": profile_row["focused_categories"] or [],
        "rate_types": profile_row["rate_types"] or [],
        "category_order": profile_row["category_order"] or [],
        "category_evidence": profile_row.get("category_evidence"),
        "industry_context": industry_context,
    }
