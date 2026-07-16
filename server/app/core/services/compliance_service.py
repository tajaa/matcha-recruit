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

from .scope_registry.codify import codified_sql

logger = logging.getLogger(__name__)

from .jurisdiction_context import (
    get_known_sources,
    record_source,
    extract_domain,
    build_context_prompt,
    get_source_reputations,
    update_source_accuracy,
)
from ..models.compliance import (
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


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse ISO date string to Python date object."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, AttributeError):
        return None


# Library permanence (B5): stored requirements are treated as truth until a
# future diff-scheduler exists to selectively re-check them (see
# COMPLIANCE_REMEDIATION_PLAN.md B5/E6). While settings.repository_ttl_enabled
# is False, _is_jurisdiction_fresh ignores age and reports "fresh" whenever a
# jurisdiction has any data at all; gap-driven research (missing required
# categories) still fires regardless. Config-backed (REPOSITORY_TTL_ENABLED
# env var, config.py) rather than a module constant so it can flip without a
# redeploy.

# Threshold for numeric material changes (e.g. $0.25 for wages)
MATERIAL_CHANGE_THRESHOLDS = {
    "minimum_wage": 0.25,
    "default": 0.10,
}

JURISDICTION_PRIORITY = {
    "city": 1, "county": 2,
    "state": 3, "province": 3, "region": 3,
    "federal": 4, "national": 4,
}

VALID_LEGISLATION_STATUSES = {
    "proposed",
    "passed",
    "signed",
    "effective_soon",
    "effective",
    "dismissed",
}

from ..compliance_registry import (
    LABOR_CATEGORIES as REQUIRED_LABOR_CATEGORIES,
    HEALTHCARE_CATEGORIES,
    ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES,
    LIFE_SCIENCES_CATEGORIES,
    INDUSTRY_TAGS as MEDICAL_COMPLIANCE_INDUSTRY_TAGS,
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

_CATEGORY_ALIASES = {
    "meal_rest_breaks": "meal_breaks",
    "meal_and_rest_breaks": "meal_breaks",
    "meal_periods": "meal_breaks",
    "rest_breaks": "meal_breaks",
    "payday_frequency": "pay_frequency",
    "pay_day_frequency": "pay_frequency",
    "final_wage": "final_pay",
    "final_wages": "final_pay",
    "final_paycheck": "final_pay",
    "final_paychecks": "final_pay",
    "minor_work_permits": "minor_work_permit",
    "work_permit": "minor_work_permit",
    "work_permits": "minor_work_permit",
    "youth_employment": "minor_work_permit",
    "youth_work_permit": "minor_work_permit",
    "scheduling_and_reporting_time": "scheduling_reporting",
    "reporting_time": "scheduling_reporting",
    "predictive_scheduling": "scheduling_reporting",
    "fair_workweek": "scheduling_reporting",
    "leave_of_absence": "leave",
    "family_leave": "leave",
    "medical_leave": "leave",
    "paid_leave": "leave",
    "fmla": "leave",
    "pfml": "leave",
}


def _normalize_legislation_status(
    status: Optional[str],
    expected_effective_date: Optional[date],
) -> str:
    """Normalize legislation status and prevent stale future statuses."""
    normalized = (status or "proposed").strip().lower().replace("-", "_")
    if normalized not in VALID_LEGISLATION_STATUSES:
        normalized = "proposed"

    today = datetime.utcnow().date()
    if expected_effective_date and expected_effective_date <= today:
        return "effective"

    return normalized


# State code → state name mapping for jurisdiction relabeling
_CODE_TO_STATE_NAME = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District Of Columbia",
}


def is_codified_row(row: Dict[str, Any]) -> bool:
    """The trio, in Python — for callers holding CATALOG rows, not SQL.

    Mirrors `codified_sql`; kept beside the gate so the two can't drift.
    """
    return bool(
        row.get("statute_citation")
        and row.get("citation_verified_at")
        and row.get("citation_item_id")
    )


async def codified_gate_sql(alias: str = "cat", *, conn=None) -> str:
    """`AND <trio>` when tenants are gated to codified rows, else empty string.

    Every tenant-facing read of requirement CONTENT appends this. The alias is
    the joined CATALOG row (`jurisdiction_requirements`), not the per-location
    projection: codification is a property of the law we researched once, not of
    each tenant's copy. Projection rows with a NULL `jurisdiction_requirement_id`
    (~6% — written before the SSOT link existed, or by a path that never set it)
    fail a LEFT JOIN's trio and drop out, which is the honest outcome: with no
    catalog row there is nothing to have verified.

    Returns SQL with no placeholders, so callers can concatenate it into a query
    without disturbing their `$n` numbering.
    """
    from .platform_settings import get_tenant_codified_only

    if not await get_tenant_codified_only(conn=conn):
        return ""
    return f" AND {codified_sql(alias)}"


def _filter_city_level_requirements(reqs: list, state: str) -> list:
    """Filter city-level requirements for locations without local ordinances.

    Instead of blindly stripping all city-level requirements (which can lose
    categories like minimum_wage entirely), this promotes city-level entries
    to state-level when no state-level entry exists for that category.
    A city with no local ordinance inherits state rules, so any "city-level"
    data is really the state requirement mislabeled by the research source.
    """
    state_name = _CODE_TO_STATE_NAME.get(state.upper().strip(), state)

    # Separate city-level from non-city-level
    non_city = []
    city_level = []
    for r in reqs:
        jl = (
            r.get("jurisdiction_level")
            if isinstance(r, dict)
            else getattr(r, "jurisdiction_level", None)
        )
        if jl == "city":
            city_level.append(r)
        else:
            non_city.append(r)

    if not city_level:
        return reqs

    # Find categories already covered by non-city (state/county/federal) requirements
    covered_categories = set()
    for r in non_city:
        cat = r.get("category") if isinstance(r, dict) else getattr(r, "category", None)
        norm = _normalize_category(cat) or cat
        covered_categories.add(norm)

    # Promote city-level entries for categories with no state/county fallback
    promoted = []
    for r in city_level:
        cat = r.get("category") if isinstance(r, dict) else getattr(r, "category", None)
        norm = _normalize_category(cat) or cat
        if norm not in covered_categories:
            # Promote to state-level — the city has no local ordinance so this
            # data actually represents the inherited state requirement.
            if isinstance(r, dict):
                r["jurisdiction_level"] = "state"
                r["jurisdiction_name"] = state_name
            else:
                r.jurisdiction_level = "state"
                r.jurisdiction_name = state_name
            promoted.append(r)
            covered_categories.add(norm)

    stripped = len(city_level) - len(promoted)
    if stripped:
        print(
            f"[Compliance] Stripped {stripped} city-level req(s), promoted {len(promoted)} to state-level"
        )

    return non_city + promoted


# Valid rate_types for minimum_wage requirements
VALID_RATE_TYPES = {
    "general",
    "tipped",
    "exempt_salary",
    # A sub-state REGION's own exempt threshold (NY downstate: NYC + Nassau /
    # Suffolk / Westchester carry a higher figure than the rest of the state).
    # minimum_wage derives its write identity from rate_type, not from
    # regulation_key (see _compute_key_parts), so without a distinct rate_type
    # the regional row and the statewide row collapse onto ONE identity — two
    # live obligations wearing one tag, which is exactly the polymorphy the
    # anti-polymorphy work forbids.
    "exempt_salary_regional",
    "hotel",
    "fast_food",
    "healthcare",
    "large_employer",
    "small_employer",
}

# Rate types that are industry-specific. Used at sync time to filter
# requirements that don't apply to a company's industry.
_INDUSTRY_SPECIFIC_RATE_TYPES: Dict[str, str] = {
    "healthcare": "healthcare",
}

# Legacy constants kept for backwards compatibility during transition
# TODO: Remove after migration is complete
_MIN_WAGE_GENERAL_KEYS = {"minimum wage", "minimum wage rate", "general minimum wage"}
_MIN_WAGE_SPECIAL_KEYWORDS = {
    "tipped",
    "tip credit",
    "subminimum",
    "student",
    "youth",
    "training",
    "trainee",
    "apprentice",
    "learner",
    "disabled",
    "fast food",
    "fast-food",
    "hotel",
    "hospitality",
    "resort",
    "healthcare",
    "airport",
    "government",
    "seasonal",
    "agricultural",
    "farm",
    "farmworker",
    "small employer",
    "large employer",
    "employer size",
    "employees",
    "franchise",
    "collective bargaining",
    "union",
}


def _normalize_jurisdiction_name(name: Optional[str]) -> str:
    if not name:
        return ""
    s = " ".join(name.lower().strip().split())
    for prefix in ("city of ", "county of "):
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
    for suffix in (" city", " county"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def _normalize_city_key(city: str) -> str:
    normalized = (city or "").lower().strip()
    normalized = normalized.replace(".", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


_CITY_ALIAS_FALLBACKS = {
    ("NY", "new york city"): "new york",
    ("NY", "nyc"): "new york",
    ("UT", "salt lake"): "salt lake city",
}


async def _resolve_county_from_zip(conn, zipcode: str, state: str) -> Optional[str]:
    """Look up county from zip code. Returns None if zip not in reference."""
    if not zipcode:
        return None
    try:
        row = await conn.fetchrow(
            "SELECT county FROM zip_county_reference WHERE zipcode = $1 AND state = $2",
            zipcode.strip()[:5],
            state.upper(),
        )
        return row["county"] if row else None
    except asyncpg.UndefinedTableError:
        return None


async def _resolve_reference_city(
    conn,
    city: str,
    state: str,
) -> tuple[str, Optional[str]]:
    """Resolve input city to canonical jurisdiction_reference city + county."""
    norm_city = _normalize_city_key(city)
    norm_state = state.upper().strip()
    lookup_city = _CITY_ALIAS_FALLBACKS.get((norm_state, norm_city), norm_city)

    try:
        row = await conn.fetchrow(
            """
            SELECT city, county
            FROM jurisdiction_reference
            WHERE state = $2
              AND (
                city = $1
                OR EXISTS (
                  SELECT 1
                  FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS alias
                  WHERE LOWER(alias) = $1
                )
              )
            LIMIT 1
            """,
            lookup_city,
            norm_state,
        )
    except asyncpg.UndefinedTableError:
        row = None

    if row:
        return row["city"], row["county"]

    return lookup_city, None


_VARCHAR_100_FIELDS = ("jurisdiction_name", "current_value", "source_name")


def _clamp_varchar_fields(req: dict) -> dict:
    for field in _VARCHAR_100_FIELDS:
        val = req.get(field)
        if val and len(val) > 100:
            req[field] = val[:100]
    return req


async def _validate_source_urls(reqs: List[Dict]) -> List[Dict]:
    """Liveness-check source_url via HEAD requests and FLAG the result.

    A dead link is the pointer back to the authority — it's how a stale policy
    gets re-verified once the URL is fixed — so a 404/timeout must NOT erase it.
    Instead we stamp ``source_url_status`` ('ok' | 'dead') on the req dict; the
    jurisdiction_requirements upsert persists it (and ``source_checked_at``) so
    admins can see which sources need attention without losing the URL. Reqs
    without a source_url are left untouched (column default 'unchecked').
    """
    url_map: Dict[str, List[Dict]] = {}
    for req in reqs:
        url = req.get("source_url")
        if url:
            url_map.setdefault(url, []).append(req)

    if not url_map:
        return reqs

    sem = asyncio.Semaphore(10)

    async def _check(url: str) -> tuple:
        try:
            async with sem:
                async with httpx.AsyncClient(
                    follow_redirects=True, timeout=5.0
                ) as client:
                    resp = await client.head(url)
                    return (url, resp.status_code)
        except Exception:
            return (url, None)

    results = await asyncio.gather(*[_check(u) for u in url_map])

    for url, status in results:
        alive = status is not None and status < 400
        if not alive:
            label = f"status {status}" if status else "connection error"
            print(f"[Compliance] Flagged dead source URL (retained): {url} ({label})")
        for req in url_map[url]:
            # Preserve source_url/source_name; only record liveness.
            req["source_url_status"] = "ok" if alive else "dead"

    return reqs


def _normalize_category(category: Optional[str]) -> Optional[str]:
    if not category:
        return category
    s = category.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    return _CATEGORY_ALIASES.get(s, s)


def _normalize_rate_type(rate_type: Optional[str]) -> Optional[str]:
    if not rate_type:
        return None
    s = rate_type.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    return s


def _coerce_minimum_wage_rate_type(req: dict) -> str:
    """Normalize/infer minimum_wage rate_type for stable grouping and keys."""
    normalized = _normalize_rate_type(req.get("rate_type"))
    if normalized in VALID_RATE_TYPES:
        return normalized

    # For minimum_wage the rate_type IS the write identity (_compute_key_parts
    # keys off it and ignores regulation_key entirely), so a regulation_key that
    # names a specific tier must decide the rate_type — otherwise a producer that
    # correctly emits `exempt_salary_threshold_regional` still gets keyed as the
    # STATEWIDE threshold and overwrites that row. The key→rate_type direction is
    # deterministic; this is the inverse of keys._RATE_TYPE_TO_KEY.
    from app.core.services.compliance_evals.keys import _RATE_TYPE_TO_KEY

    reg_key = (req.get("regulation_key") or "").strip()
    if reg_key:
        for rate_type, key in _RATE_TYPE_TO_KEY.items():
            if key == reg_key and rate_type in VALID_RATE_TYPES:
                return rate_type

    text = " ".join(
        str(req.get(k) or "") for k in ("title", "description", "current_value")
    ).lower()

    # Region-qualified exempt thresholds before the generic exempt tokens: a
    # "(Downstate)" title must not collapse into the statewide tier.
    if any(token in text for token in ("downstate", "regional tier")):
        return "exempt_salary_regional"

    if any(
        token in text
        for token in ("exempt", "salary threshold", "salary basis", "annual salary")
    ):
        return "exempt_salary"
    if any(token in text for token in ("tipped", "tip credit", "cash wage", "tips")):
        return "tipped"
    return "general"


def _normalize_requirement_categories(requirements: list[dict]) -> None:
    """Normalize category names and minimum_wage rate_type in-place."""
    for req in requirements:
        req["category"] = _normalize_category(req.get("category")) or req.get(
            "category"
        )
        if req.get("category") == "minimum_wage":
            req["rate_type"] = _coerce_minimum_wage_rate_type(req)


def _missing_required_categories(requirements: list[dict]) -> list[str]:
    """Return required labor categories that are missing from the requirement set."""
    present = {
        _normalize_category((req or {}).get("category"))
        for req in requirements
        if isinstance(req, dict) and (req or {}).get("category")
    }
    return sorted(cat for cat in REQUIRED_LABOR_CATEGORIES if cat not in present)


# Reduced category set for the Matcha-X self-serve onboarding finale: basic
# federal + labor + common state-specific law. Passed as ``categories`` to
# run_compliance_check_stream so the live build researches ~9 categories instead
# of the full required-labor sweep — faster and cheaper for self-serve. All keys
# are valid entries in compliance_registry.
MATCHA_X_LITE_CATEGORIES: List[str] = [
    "minimum_wage",
    "overtime",
    "sick_leave",
    "meal_breaks",
    "pay_frequency",
    "final_pay",
    "anti_discrimination",
    "workplace_safety",
    "i9_everify",
]


def _normalize_title_key(title: Optional[str]) -> str:
    if not title:
        return ""
    s = title.lower().strip()
    s = s.replace("‑", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"[()\[\]{}]", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Maps category → list of (keywords_set, canonical_key).
# Order matters — first match wins, so more specific patterns come first.
_TITLE_CANONICAL_MAP: dict[str, list[tuple[frozenset[str], str]]] = {
    "meal_breaks": [
        (frozenset({"healthcare", "waiver"}), "healthcare_meal_waiver"),
        (frozenset({"healthcare", "exception"}), "healthcare_meal_waiver"),
        (frozenset({"healthcare", "meal"}), "healthcare_meal_waiver"),
        (frozenset({"missed", "break", "penalty"}), "missed_break_penalty"),
        (frozenset({"missed", "penalty"}), "missed_break_penalty"),
        (frozenset({"lactation"}), "lactation_break"),
        (frozenset({"on", "duty", "meal"}), "on_duty_meal_agreement"),
        (frozenset({"on", "duty", "agreement"}), "on_duty_meal_agreement"),
        # "meal" + anything → meal_break (must come BEFORE rest_break to win ties)
        (frozenset({"meal", "rest"}), "meal_break"),
        (frozenset({"meal", "break", "waiver"}), "meal_break"),
        (frozenset({"meal", "waiver"}), "meal_break"),
        (frozenset({"meal", "break"}), "meal_break"),
        (frozenset({"meal", "period"}), "meal_break"),
        # rest-only → rest_break
        (frozenset({"rest", "break"}), "rest_break"),
        (frozenset({"rest", "period"}), "rest_break"),
    ],
    "overtime": [
        (frozenset({"daily", "weekly"}), "daily_weekly_overtime"),
        (frozenset({"double", "time"}), "double_time"),
        (frozenset({"seventh", "day"}), "seventh_day_overtime"),
        (frozenset({"alternative", "workweek"}), "alternative_workweek"),
        (frozenset({"healthcare", "overtime"}), "healthcare_overtime"),
        (frozenset({"mandatory", "overtime"}), "mandatory_overtime_restrictions"),
        (frozenset({"comp", "time"}), "comp_time"),
        (frozenset({"exempt", "salary"}), "exempt_salary_threshold"),
    ],
    "sick_leave": [
        (frozenset({"accrual", "cap"}), "accrual_and_usage_caps"),
        (frozenset({"accrual", "usage"}), "accrual_and_usage_caps"),
        (frozenset({"local", "sick"}), "local_sick_leave"),
        (frozenset({"paid", "sick"}), "state_paid_sick_leave"),
        (frozenset({"sick", "leave"}), "state_paid_sick_leave"),
    ],
    "leave": [
        (frozenset({"family", "medical", "leave"}), "fmla"),
        (frozenset({"fmla"}), "fmla"),
        (frozenset({"paid", "family"}), "state_paid_family_leave"),
        (frozenset({"family", "leave"}), "state_family_leave"),
        (frozenset({"disability", "insurance"}), "state_disability_insurance"),
        (frozenset({"disability", "benefits"}), "state_disability_insurance"),
        (frozenset({"pregnancy", "disability"}), "pregnancy_disability_leave"),
        (frozenset({"paid", "sick", "leave"}), "paid_sick_leave"),
        (frozenset({"sick", "leave"}), "paid_sick_leave"),
        (frozenset({"bereavement"}), "bereavement_leave"),
        (frozenset({"domestic", "violence"}), "domestic_violence_leave"),
        (frozenset({"jury", "duty"}), "jury_duty_leave"),
        (frozenset({"military", "leave"}), "military_leave"),
        (frozenset({"voting", "leave"}), "voting_leave"),
        (frozenset({"school", "activity"}), "school_activity_leave"),
        (frozenset({"reproductive", "loss"}), "reproductive_loss_leave"),
        (frozenset({"bone", "marrow"}), "bone_marrow_donor_leave"),
        (frozenset({"organ", "donor"}), "organ_donor_leave"),
    ],
    "pay_frequency": [
        (frozenset({"final", "pay", "termination"}), "final_pay_termination"),
        (frozenset({"final", "pay", "resignation"}), "final_pay_resignation"),
        (frozenset({"exempt", "monthly"}), "exempt_monthly_pay"),
        (frozenset({"payday", "posting"}), "payday_posting"),
        (frozenset({"wage", "notice"}), "wage_notice"),
        (frozenset({"pay", "frequency"}), "standard_pay_frequency"),
        (frozenset({"pay", "schedule"}), "standard_pay_frequency"),
    ],
    "final_pay": [
        (frozenset({"termination"}), "final_pay_termination"),
        (frozenset({"resignation"}), "final_pay_resignation"),
        (frozenset({"layoff"}), "final_pay_layoff"),
        (frozenset({"waiting", "time", "penalty"}), "waiting_time_penalty"),
    ],
}


def _match_title_to_canonical_key(normalized_title: str, category: str) -> Optional[str]:
    """Map a normalized title to a canonical regulation key via keyword matching.

    Bridges the gap when Gemini doesn't provide a regulation_key: instead of
    using the raw title as the dedup key (which causes semantic duplicates),
    match the title's words against known patterns for the category.
    """
    patterns = _TITLE_CANONICAL_MAP.get(category)
    if not patterns:
        return None
    title_words = set(normalized_title.split())
    for keywords, canonical in patterns:
        if keywords <= title_words:
            return canonical
    return None


def _extract_numeric_value(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        match = re.search(r"(\d+(?:\.\d+)?)", value.replace(",", ""))
        if match:
            return float(match.group(1))
    except (ValueError, TypeError):
        return None
    return None


def _base_title(title, jurisdiction_name):
    """Strip jurisdiction-name prefix from a title for grouping.

    "California Minimum Wage" with jurisdiction_name "California"
    → "Minimum Wage", so it matches "West Hollywood Minimum Wage".
    Also handles "City of …" / "County of …" prefixes that Gemini
    may prepend to the jurisdiction name in the title.
    """
    if not jurisdiction_name:
        return title
    t_lower = title.lower()
    jn_norm = _normalize_jurisdiction_name(jurisdiction_name)
    if not jn_norm:
        return title

    # Match optional "city/county of" prefix and optional "city/county" suffix.
    jn_parts = [re.escape(p) for p in jn_norm.split()]
    if jn_parts:
        jn_pattern = r"\s+".join(jn_parts)
        pattern = rf"^(?:city|county)\s+of\s+{jn_pattern}\b|^{jn_pattern}\s+(?:city|county)\b|^{jn_pattern}\b"
        match = re.match(pattern, t_lower)
        if match:
            stripped = title[match.end() :].lstrip(" -:,")
            if stripped:
                return stripped
    return title


def _normalize_value_text(value: Optional[str], category: Optional[str] = None) -> str:
    if not value:
        return ""
    s = value.lower().strip()
    s = s.replace("‑", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"[$,]", "", s)
    # Normalize hyphens between numbers and unit words (e.g. "30-min" → "30 min")
    s = re.sub(r"(\d)-(\w)", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s)
    cat_key = _normalize_category(category)
    is_pay_frequency = cat_key == "pay_frequency"

    if is_pay_frequency:
        s = re.sub(r"\bor\s+at\s+least\b", "or", s)
        s = re.sub(r"\bat\s+least\s+\b", "", s)
        phrase_map = [
            (r"\bevery\s+2\s+weeks\b", "biweekly"),
            (r"\bevery\s+two\s+weeks\b", "biweekly"),
            (r"\bevery\s+other\s+week\b", "biweekly"),
            (r"\bbi[-\s]?weekly\b", "biweekly"),
            (r"\bat\s+least\s+twice\s+(?:a|per)\s+month\b", "semimonthly"),
            (r"\bat\s+least\s+2\s+times?\s+(?:a|per)\s+month\b", "semimonthly"),
            (r"\btwice\s+(?:a|per)\s+month\b", "semimonthly"),
            (r"\bsemi[-\s]?monthly\b", "semimonthly"),
            (r"\bevery\s+week\b", "weekly"),
            (r"\bevery\s+month\b", "monthly"),
            (r"\bevery\s+year\b", "yearly"),
            (r"\bannually\b", "yearly"),
            (r"\bevery\s+day\b", "daily"),
        ]
        for pattern, repl in phrase_map:
            s = re.sub(pattern, repl, s)

    unit_map = [
        (r"\bper\s+hour\b", "/hr"),
        (r"\bper\s+hr\b", "/hr"),
        (r"\bper\s+week\b", "/wk"),
        (r"\bper\s+month\b", "/mo"),
        (r"\bper\s+year\b", "/yr"),
        (r"\bper\s+annum\b", "/yr"),
        (r"\bhourly\b", "/hr"),
        (r"\bweekly\b", "/wk"),
        (r"\bmonthly\b", "/mo"),
        (r"\byearly\b", "/yr"),
        (r"\bdaily\b", "/day"),
    ]
    for pattern, repl in unit_map:
        s = re.sub(pattern, repl, s)

    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"/hour\b", "/hr", s)
    s = re.sub(r"/week\b", "/wk", s)
    s = re.sub(r"/month\b", "/mo", s)
    s = re.sub(r"/year\b", "/yr", s)
    s = re.sub(r"/annum\b", "/yr", s)

    if cat_key == "minimum_wage":
        if re.fullmatch(r"\d+(?:\.\d+)?", s):
            s = f"{s}/hr"

    if is_pay_frequency:
        s = re.sub(
            r"\b(semimonthly|biweekly|weekly|monthly|yearly|daily)\b(?:\s+or\s+\1\b)+",
            r"\1",
            s,
        )
        # Normalize "X or Y" alternative forms to sorted canonical tokens
        # e.g. "semimonthly or biweekly" and "biweekly or semimonthly" → "biweekly semimonthly"
        freq_tokens = {
            "semimonthly",
            "biweekly",
            "weekly",
            "monthly",
            "yearly",
            "daily",
        }
        or_parts = [p.strip() for p in s.split(" or ")]
        if len(or_parts) > 1 and all(p in freq_tokens for p in or_parts):
            s = " ".join(sorted(set(or_parts)))

    # Decimal multiplier normalization: "2.0x" → "2x"
    s = re.sub(r"(\d+)\.0x\b", r"\1x", s)
    # Trailing decimal zeros: "2.0" → "2" (but not "2.05")
    s = re.sub(r"(\d+)\.0\b", r"\1", s)
    # Ordinal suffix removal: "1st" → "1", "26th" → "26"
    s = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", s)
    # Synonym normalization for leave categories
    s = re.sub(r"\bcompensated\b", "paid", s)
    s = re.sub(r"\buncompensated\b", "unpaid", s)

    # Strip parenthetical annotations (e.g., "(unpaid)", "(paid)", "(per shift)")
    # These are clarifying notes, not part of the actual requirement value
    s = re.sub(r"\s*\([^)]*\)", "", s)

    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _is_special_min_wage(
    base_key: str, title: Optional[str], description: Optional[str]
) -> bool:
    """DEPRECATED: Use rate_type field instead. Kept for backwards compatibility."""
    if not base_key:
        return False
    if base_key in _MIN_WAGE_GENERAL_KEYS:
        return False
    text = " ".join(filter(None, [base_key, title or "", description or ""])).lower()
    return any(keyword in text for keyword in _MIN_WAGE_SPECIAL_KEYWORDS)


def _is_material_numeric_change(
    old_num: Optional[float], new_num: Optional[float], category: Optional[str]
) -> bool:
    """Deterministic check: is the numeric difference above our threshold?"""
    if old_num is None or new_num is None:
        return False
    threshold = MATERIAL_CHANGE_THRESHOLDS.get(
        _normalize_category(category) or "", MATERIAL_CHANGE_THRESHOLDS["default"]
    )
    return abs(float(old_num) - float(new_num)) >= threshold


def _is_material_text_change(
    old_text: Optional[str], new_text: Optional[str], category: Optional[str] = None
) -> bool:
    """Deterministic check: do the normalized text values differ?"""
    return _normalize_value_text(old_text, category) != _normalize_value_text(
        new_text, category
    )


def _get_numeric_from_req(req) -> Optional[float]:
    val = (
        req.get("numeric_value")
        if isinstance(req, dict)
        else getattr(req, "numeric_value", None)
    )
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            pass
    current = (
        req.get("current_value")
        if isinstance(req, dict)
        else getattr(req, "current_value", None)
    )
    return _extract_numeric_value(current)


def _pick_best_by_priority(reqs):
    if not reqs:
        return None
    best_priority = min(
        JURISDICTION_PRIORITY.get(
            r["jurisdiction_level"] if isinstance(r, dict) else r.jurisdiction_level, 99
        )
        for r in reqs
    )
    candidates = [
        r
        for r in reqs
        if JURISDICTION_PRIORITY.get(
            r["jurisdiction_level"] if isinstance(r, dict) else r.jurisdiction_level, 99
        )
        == best_priority
    ]
    if len(candidates) == 1:
        return candidates[0]
    # Break ties by highest numeric value if available
    candidates_with_num = [(r, _get_numeric_from_req(r)) for r in candidates]
    candidates_with_num = [c for c in candidates_with_num if c[1] is not None]
    if candidates_with_num:
        return max(candidates_with_num, key=lambda x: x[1])[0]
    return candidates[0]


def _pick_most_restrictive_wage(reqs):
    """DEPRECATED: Use rate_type-based grouping instead. Kept for backwards compatibility."""
    if not reqs:
        return None
    with_nums = [(r, _get_numeric_from_req(r)) for r in reqs]
    with_nums = [pair for pair in with_nums if pair[1] is not None]
    if with_nums:
        return max(with_nums, key=lambda x: x[1])[0]
    return _pick_best_by_priority(reqs)


MAX_VERIFICATIONS_PER_CHECK = 3
HEARTBEAT_INTERVAL = 8


async def _heartbeat_while(task, *, queue=None, interval=HEARTBEAT_INTERVAL):
    """Yield progress events from queue and heartbeat dicts while a task runs."""
    try:
        while not task.done():
            if queue is not None:
                while not queue.empty():
                    yield queue.get_nowait()
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done:
                break
            yield {"type": "heartbeat"}
    except asyncio.CancelledError:
        if not task.done():
            task.cancel()
        raise
    # Final drain
    if queue is not None:
        while not queue.empty():
            yield queue.get_nowait()


# ── Jurisdiction Repository Helpers ──────────────────────────────────────


async def _get_or_create_jurisdiction(
    conn, city: str, state: str, county: Optional[str] = None, zipcode: Optional[str] = None
) -> UUID:
    """Find or create a jurisdiction row with hierarchy resolution.

    Auto-resolves county from jurisdiction_reference when not provided; if
    that city-name match doesn't find one either and ``zipcode`` is given,
    falls back to `_resolve_county_from_zip` (D3.3 — zip was collected at
    onboarding but previously only used by one unrelated endpoint). Then
    links city -> county -> state via parent_id.
    """
    norm_state = state.upper().strip()

    # 1b. State-only shortcut — no city means we just need the state jurisdiction
    if not city or not city.strip():
        state_j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE COALESCE(city, '') = '' AND state = $1",
            norm_state,
        )
        if not state_j:
            await conn.execute(
                "INSERT INTO jurisdictions (city, state, display_name, level) VALUES ('', $1, $2, 'state') ON CONFLICT DO NOTHING",
                norm_state,
                norm_state,
            )
            state_j = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE COALESCE(city, '') = '' AND state = $1",
                norm_state,
            )
        return state_j["id"]

    norm_city, ref_county = await _resolve_reference_city(conn, city, state)
    if not county and ref_county:
        county = ref_county
    if not county and zipcode:
        county = await _resolve_county_from_zip(conn, zipcode, norm_state)

    # 2. Get or create city jurisdiction
    city_display = f"{city.strip()}, {norm_state}"
    await conn.execute(
        """
        INSERT INTO jurisdictions (city, state, county, display_name, level)
        VALUES ($1, $2, $3, $4, 'city')
        ON CONFLICT DO NOTHING
        """,
        norm_city,
        norm_state,
        county,
        city_display,
    )
    city_row = await conn.fetchrow(
        "SELECT id, county, parent_id FROM jurisdictions WHERE city = $1 AND state = $2",
        norm_city,
        norm_state,
    )
    city_id = city_row["id"]

    # 3. Get or create state jurisdiction (uses empty-string city convention)
    state_j = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE COALESCE(city, '') = '' AND state = $1",
        norm_state,
    )
    if not state_j:
        await conn.execute(
            "INSERT INTO jurisdictions (city, state, display_name, level) VALUES ('', $1, $2, 'state') ON CONFLICT DO NOTHING",
            norm_state,
            norm_state,
        )
        state_j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE COALESCE(city, '') = '' AND state = $1",
            norm_state,
        )
    state_id = state_j["id"]

    # 4. Link county -> state, city -> county (or city -> state if no county)
    if county:
        # Update city's county field if it was auto-resolved
        if not city_row["county"]:
            await conn.execute(
                "UPDATE jurisdictions SET county = $2 WHERE id = $1",
                city_id,
                county,
            )

        # Get or create county jurisdiction
        county_norm = county.lower().strip()
        county_j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE city = $1 AND state = $2",
            f"_county_{county_norm}",
            norm_state,
        )
        if not county_j:
            await conn.execute(
                """
                INSERT INTO jurisdictions (city, state, county, parent_id, display_name, level)
                VALUES ($1, $2, $3, $4, $5, 'county')
                ON CONFLICT DO NOTHING
                """,
                f"_county_{county_norm}",
                norm_state,
                county,
                state_id,
                f"{county}, {norm_state}",
            )
            county_j = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE city = $1 AND state = $2",
                f"_county_{county_norm}",
                norm_state,
            )

        county_id = county_j["id"]

        # Ensure county -> state link
        await conn.execute(
            "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1 AND parent_id IS NULL",
            county_id,
            state_id,
        )

        # Link city -> county (even if previously linked directly to state)
        if not city_row["parent_id"] or city_row["parent_id"] == state_id:
            await conn.execute(
                "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1",
                city_id,
                county_id,
            )
    else:
        # No county: link city -> state directly
        if not city_row["parent_id"]:
            await conn.execute(
                "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1",
                city_id,
                state_id,
            )

    return city_id


async def _lookup_has_local_ordinance(conn, city: str, state: str) -> Optional[bool]:
    """Check jurisdiction_reference for whether a city has its own local ordinance."""
    normalized_city = _normalize_city_key(city)
    normalized_state = state.upper().strip()
    lookup_city = _CITY_ALIAS_FALLBACKS.get(
        (normalized_state, normalized_city), normalized_city
    )

    try:
        ref = await conn.fetchrow(
            """
            SELECT has_local_ordinance
            FROM jurisdiction_reference
            WHERE state = $2
              AND (
                city = $1
                OR EXISTS (
                  SELECT 1
                  FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS alias
                  WHERE LOWER(alias) = $1
                )
              )
            LIMIT 1
            """,
            lookup_city,
            normalized_state,
        )
        result = ref["has_local_ordinance"] if ref else None
        print(
            f"[Compliance] has_local_ordinance lookup: city={city!r}, state={state!r} → {result}"
        )
        return result
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return None


async def _is_jurisdiction_fresh(
    conn, jurisdiction_id: UUID, threshold_days: int
) -> bool:
    """Check if jurisdiction data is trusted enough to skip Gemini.

    Library permanence (B5, settings.repository_ttl_enabled=False by default):
    once a jurisdiction has been verified at all, it stays "fresh" regardless
    of age — stored data is truth until a future diff-scheduler selectively
    re-checks it. Missing data (no last_verified_at) still returns False so
    gap-driven research (via _missing_required_categories) keeps firing. The
    age comparison is kept dormant here so re-enabling REPOSITORY_TTL_ENABLED
    restores selective re-checks without re-plumbing callers.
    """
    row = await conn.fetchrow(
        "SELECT last_verified_at FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not row or not row["last_verified_at"]:
        return False

    from ...config import get_settings as _get_settings
    if not _get_settings().repository_ttl_enabled:
        return True
    age = datetime.utcnow() - row["last_verified_at"]
    return age < timedelta(days=threshold_days)


def _authority_label(level: Optional[str], display_name: Optional[str]) -> Optional[str]:
    """A display label for an issuing jurisdiction, from its `jurisdictions` row.

    `display_name` is authored inconsistently ("los angeles, CA" for the city,
    "Los Angeles, CA" for the county that contains it), so title-case the place
    while preserving a trailing 2-letter state code, and disambiguate a county
    from the identically-named city inside it.
    """
    if not display_name:
        return None
    name = display_name.strip()
    if not name:
        return None

    place, _, region = name.partition(",")
    place = place.strip()
    region = region.strip()
    # Only re-case an all-lower place; a name that already carries capitals may
    # hold something .title() would mangle ("City of Los Angeles" is fine, but
    # so is a hyphenated or apostrophed name).
    if place.islower():
        place = place.title()
    if level == "county" and "county" not in place.lower():
        place = f"{place} County"
    if not region:
        return place
    return f"{place}, {region.upper() if len(region) == 2 else region}"


def _basis_from_metadata(metadata: Any) -> Optional[List[Dict]]:
    """The floor relations recorded on a catalog row's metadata by codify.py.

    A row whose value is its OWN (CA's $70,304 threshold) carries no
    statute_citation for the federal reg it sits on top of — citing it would be
    false provenance — so the relation lives here instead. Surfacing it is what
    makes a demotion legible rather than a citation silently disappearing.
    """
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            return None
    if not isinstance(metadata, dict):
        return None
    basis = metadata.get("jurisdictional_basis")
    return basis if isinstance(basis, list) else None


def _parse_jsonb_list(value: Any) -> Optional[List[Dict]]:
    """asyncpg hands JSONB back as a str on this pool — the API must not leak
    strings where a list of objects belongs."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return value if isinstance(value, list) else None


async def _load_jurisdiction_requirements(conn, jurisdiction_id: UUID) -> List[Dict]:
    """Read requirements from the jurisdiction repository.

    Excludes 'under_review' (grounding-quarantined), 'repealed' (an admin
    reviewed the quarantined value and confirmed it WRONG), and 'pending'
    (admin-queued research staged for review — not yet approved) rows — the
    single choke point every tenant-sync and gap-detection caller goes through.
    A quarantined row reads as a gap (triggers re-research, and a re-research
    that passes grounding promotes it back to active) rather than as
    served/covered — never silently surfaced to a tenant, never silently
    treated as permanently missing either. A rejected row must obviously never
    be served: it is a known-wrong value kept only as an audit trail. A pending
    row reads as a gap too, on purpose — it exists, but nobody approved it yet.
    """
    rows = await conn.fetch(
        "SELECT * FROM jurisdiction_requirements "
        "WHERE jurisdiction_id = $1 AND status NOT IN ('under_review', 'repealed', 'pending')",
        jurisdiction_id,
    )
    # Carry the catalog row id under an explicit key so the per-location sync can
    # stamp compliance_requirements.jurisdiction_requirement_id (the SSOT link /
    # dedup identity). `id` is already present from dict(r); the explicit alias is
    # unambiguous for the writers below.
    return [{**dict(r), "jurisdiction_requirement_id": r["id"]} for r in rows]


async def _load_chain_requirements(conn, leaf_jurisdiction_id: UUID) -> List[Dict]:
    """Every active requirement across a location's WHOLE jurisdiction chain.

    What a business is liable for is the union of city + county + state + federal
    law that reaches it — not whatever the last research pass happened to return.

    The check used to build a tenant's set from the LEAF jurisdiction's rows plus
    ``_fill_missing_categories_from_parents``, which only backfills categories the
    leaf lacks *entirely*. So a federal obligation never arrived if the leaf
    already held some row in the same category. That is how a Los Angeles dental
    practice was served no OSHA Bloodborne Pathogens standard, no infection
    control, no hazardous-waste generator rules and no radiation-machine
    registration — every one of them sitting in the catalog, in its chain, the
    whole time.

    Research fills gaps in the CATALOG. It does not decide what a tenant sees.
    Callers still apply the industry filter, facility triggers and preemption on
    top of this — this is the candidate set, not the final one.
    """
    rows = await conn.fetch(
        # `depth` bounds the recursion. The tree is at most city→county→state→
        # federal, but a parent_id cycle (a bad merge, a hand-edited row — the junk
        # `ca, CA` / `FL, FL` nodes are still live) would otherwise spin this CTE
        # forever, hanging the connection and every compliance check behind it.
        #
        # status = 'active' only. requirement_status_enum also has 'superseded' and
        # 'pending': a superseded row would be served next to the row that replaced
        # it (the same obligation twice, one with a stale value), and 'pending' is
        # the grounding-quarantine state — not something a tenant should be told
        # they are liable for.
        """
        WITH RECURSIVE chain AS (
            SELECT id, parent_id, 0 AS depth FROM jurisdictions WHERE id = $1
            UNION ALL
            SELECT j.id, j.parent_id, c.depth + 1
            FROM jurisdictions j
            JOIN chain c ON j.id = c.parent_id
            WHERE c.depth < 8
        )
        SELECT r.* FROM jurisdiction_requirements r
        JOIN chain c ON c.id = r.jurisdiction_id
        WHERE r.status = 'active'
        """,
        leaf_jurisdiction_id,
    )
    return [{**dict(r), "jurisdiction_requirement_id": r["id"]} for r in rows]


def _is_no_rule_placeholder(req: Dict) -> bool:
    """Is this row here only to say that no rule applies?

    The research prompt deliberately asks for such a row rather than an empty list
    (an empty list reads downstream as a FAILED category), so they are load-bearing
    in the CATALOG — `skip_existing` callers use their presence as "this category
    was researched". They are pure noise on a TENANT'S TAB, whose whole job is
    answering "what am I responsible for".

    Keyed ONLY on the model's own `metadata.no_rule_applies` flag. There is no safe
    heuristic: `no_surprises_act` is the regulation_key of a real federal statute,
    and "Daily Overtime Threshold: this state has none" is a genuinely useful
    answer — guessing from titles or null values would hide real obligations.
    Rows written before the flag existed simply aren't matched, and are left alone.

    Reads BOTH shapes on purpose: a row loaded from the catalog carries the flag
    inside `metadata` (where _upsert_requirements_additive puts it), while a dict
    straight off a research pass still carries it top-level — and the research set
    is exactly what the stream syncs on its fallback path.
    """
    if req.get("no_rule_applies"):
        return True
    meta = _decode_jsonb(req.get("metadata"))
    return bool(meta.get("no_rule_applies")) if isinstance(meta, dict) else False


def _drop_no_rule_placeholders(reqs: List[Dict]) -> List[Dict]:
    kept = [r for r in reqs if not _is_no_rule_placeholder(r)]
    dropped = len(reqs) - len(kept)
    if dropped:
        logger.info("compliance: hid %d 'no rule applies' placeholder(s) from the tab", dropped)
    return kept


async def _project_chain_to_location(
    conn, company_id: UUID, location, leaf_jurisdiction_id: UUID
) -> List[Dict]:
    """The requirement set a location is actually liable for.

    Chain union -> normalize -> industry filter -> FACILITY TRIGGERS -> preemption.

    The trigger pass is what keeps "exhaustive" from becoming "everything".
    Catalog rows carry conditions like ``{"type": "entity_type", "value":
    "behavioral_health"}`` (SAMHSA opioid-treatment certification) or
    ``{"key": "payer_contracts", "operator": "contains", "value": "medicare"}``
    (Hospital IQR). Nothing in the tenant read path ever evaluated them — only
    the hierarchical view did, and the Compliance tab doesn't use it — so a
    dental practice was served hospital and opioid-clinic obligations.
    """
    requirements = await _load_chain_requirements(conn, leaf_jurisdiction_id)
    requirements = [_jurisdiction_row_to_dict(r) for r in requirements]

    _normalize_requirement_categories(requirements)
    requirements = await _filter_requirements_for_company(conn, company_id, requirements)
    requirements = _drop_no_rule_placeholders(requirements)

    facility_attributes = _decode_jsonb(getattr(location, "facility_attributes", None))
    if not isinstance(facility_attributes, dict):
        facility_attributes = {}
    kept: List[Dict] = []
    for req in requirements:
        trigger = _decode_jsonb(req.get("trigger_conditions"))
        # `isinstance(dict)`, not just truthiness. _decode_jsonb returns an
        # unparseable value AS-IS (and jsonfix01 deliberately leaves such rows in
        # the DB rather than guessing at them), so a garbage string is truthy,
        # reaches _eval_condition, and dies on `cond.get("type")` —
        # AttributeError: 'str' object has no attribute 'get'. One bad catalog row
        # would take down the projection for every tenant whose chain contains it.
        # A trigger we cannot read is not a trigger we can enforce: treat it as
        # unconditional, which is how a row with no trigger already behaves.
        if isinstance(trigger, dict) and not evaluate_trigger_conditions(
            trigger, facility_attributes
        ):
            continue
        if trigger is not None and not isinstance(trigger, dict):
            logger.warning(
                "compliance: unreadable trigger_conditions on requirement %s — "
                "serving it unconditionally",
                req.get("jurisdiction_requirement_id"),
            )
        kept.append(req)
    requirements = kept

    requirements = await _filter_with_preemption(conn, requirements, location.state)
    return requirements


async def _load_jurisdiction_legislation(conn, jurisdiction_id: UUID) -> List[Dict]:
    """Read legislation from the jurisdiction repository."""
    rows = await conn.fetch(
        "SELECT * FROM jurisdiction_legislation WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    return [dict(r) for r in rows]


def _as_jsonb(value: Any) -> Optional[str]:
    """Serialize a value for a JSONB column — WITHOUT re-encoding an encoded one.

    asyncpg hands JSONB back as a `str`. So a row that is read out of the catalog
    and written back (which is every research pass: catalog -> dict -> upsert)
    used to hit `json.dumps(already_a_json_string)` and gain another layer of
    escaping. Each pass added one:

        {"type": "entity_type", ...}
        "{\\"type\\": \\"entity_type\\", ...}"
        "\\"{\\\\\\"type\\\\\\": ...}\\""

    trigger_conditions then no longer parses as an object, the evaluator can't
    read it, and the requirement fails OPEN — which is how "SAMHSA Opioid
    Treatment Program Certification" (trigger: entity_type == behavioral_health)
    was served to a dental practice.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        # Already JSON text. Trust it only if it parses; a bare string that isn't
        # JSON is a caller bug we shouldn't silently persist as garbage.
        try:
            json.loads(value)
            return value
        except (TypeError, ValueError):
            return json.dumps(value)
    return json.dumps(value)


def _decode_jsonb(value: Any) -> Any:
    """Read a JSONB value that may have been multi-encoded by the bug above."""
    seen = 0
    while isinstance(value, str) and seen < 5:
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return value
        seen += 1
    return value


def _jurisdiction_row_to_dict(jr: dict) -> dict:
    """Convert a jurisdiction_requirements row to a dict compatible with sync functions."""
    return {
        "jurisdiction_requirement_id": jr.get("id"),
        "category": jr["category"],
        "rate_type": jr.get("rate_type"),
        "jurisdiction_level": jr["jurisdiction_level"],
        "jurisdiction_name": jr["jurisdiction_name"],
        "title": jr["title"],
        "description": jr["description"],
        "current_value": jr["current_value"],
        "numeric_value": jr["numeric_value"],
        "source_url": jr["source_url"],
        "source_name": jr["source_name"],
        "effective_date": jr["effective_date"].isoformat()
        if jr.get("effective_date")
        else None,
        "expiration_date": jr["expiration_date"].isoformat()
        if jr.get("expiration_date")
        else None,
        "applicable_industries": jr.get("applicable_industries"),
        "trigger_conditions": jr.get("trigger_conditions"),
        "applicable_entity_types": jr.get("applicable_entity_types"),
    }


async def _try_load_county_requirements(
    conn, city_jurisdiction_id: UUID, threshold_days: int
) -> Optional[List[Dict]]:
    """Walk up parent_id to the county jurisdiction and load cached reqs if fresh."""
    row = await conn.fetchrow(
        "SELECT parent_id FROM jurisdictions WHERE id = $1", city_jurisdiction_id
    )
    if not row or not row["parent_id"]:
        return None
    county_id = row["parent_id"]

    # Verify it's actually a county (not state)
    county_row = await conn.fetchrow(
        "SELECT city FROM jurisdictions WHERE id = $1", county_id
    )
    if (
        not county_row
        or not county_row["city"]
        or not county_row["city"].startswith("_county_")
    ):
        return None

    if not await _is_jurisdiction_fresh(conn, county_id, threshold_days):
        return None

    j_reqs = await _load_jurisdiction_requirements(conn, county_id)
    if not j_reqs:
        return None

    print(
        f"[Compliance] Reusing county jurisdiction data ({len(j_reqs)} reqs) for city jurisdiction {city_jurisdiction_id}"
    )
    return [_jurisdiction_row_to_dict(jr) for jr in j_reqs]


async def _try_load_state_requirements(
    conn, jurisdiction_id: UUID, threshold_days: int
) -> Optional[List[Dict]]:
    """Walk up parent_id chain to the state jurisdiction and load cached reqs if fresh."""
    current_id = jurisdiction_id
    for _ in range(3):  # Walk up to 3 levels (city -> county -> state)
        row = await conn.fetchrow(
            "SELECT parent_id FROM jurisdictions WHERE id = $1", current_id
        )
        if not row or not row["parent_id"]:
            return None
        current_id = row["parent_id"]

        j_row = await conn.fetchrow(
            "SELECT id, city, state FROM jurisdictions WHERE id = $1", current_id
        )
        if j_row and j_row["city"] == "":  # State jurisdictions have empty city
            state_id = j_row["id"]
            if not await _is_jurisdiction_fresh(conn, state_id, threshold_days):
                return None

            j_reqs = await _load_jurisdiction_requirements(conn, state_id)
            if not j_reqs:
                return None

            print(
                f"[Compliance] Reusing state jurisdiction data ({len(j_reqs)} reqs) for jurisdiction {jurisdiction_id}"
            )
            return [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
    return None


async def _fill_missing_categories_from_parents(
    conn, jurisdiction_id: UUID, requirements: List[Dict], threshold_days: int
) -> bool:
    """Attempt to fill missing categories from county or state caches. Returns True if any gaps were filled."""
    missing = _missing_required_categories(requirements)
    if not missing:
        return False

    filled_any = False

    # Try county — county ordinances change slowly, use lenient threshold
    county_reqs = await _try_load_county_requirements(
        conn, jurisdiction_id, max(threshold_days, 30)
    )
    if county_reqs:
        target_set = {_normalize_category(c) or c for c in missing}
        fill = [
            r
            for r in county_reqs
            if (_normalize_category(r.get("category")) or r.get("category"))
            in target_set
        ]
        if fill:
            requirements.extend(fill)
            filled_any = True
            missing = _missing_required_categories(requirements)
            if not missing:
                return True

    # Try state — state law changes slowly, use a much more lenient threshold
    state_reqs = await _try_load_state_requirements(
        conn, jurisdiction_id, max(threshold_days, 90)
    )
    if state_reqs:
        target_set = {_normalize_category(c) or c for c in missing}
        fill = [
            r
            for r in state_reqs
            if (_normalize_category(r.get("category")) or r.get("category"))
            in target_set
        ]
        if fill:
            requirements.extend(fill)
            filled_any = True

    return filled_any


async def _get_county_jurisdiction_id(
    conn, city_jurisdiction_id: UUID
) -> Optional[UUID]:
    """Get the county jurisdiction ID from parent_id chain."""
    row = await conn.fetchrow(
        "SELECT parent_id FROM jurisdictions WHERE id = $1", city_jurisdiction_id
    )
    if not row or not row["parent_id"]:
        return None
    county_row = await conn.fetchrow(
        "SELECT id, city FROM jurisdictions WHERE id = $1", row["parent_id"]
    )
    if county_row and county_row["city"] and county_row["city"].startswith("_county_"):
        return county_row["id"]
    return None


async def _get_state_jurisdiction_id(conn, jurisdiction_id: UUID) -> Optional[UUID]:
    """Walk the parent chain to the state node.

    Keys on ``level``, not on a city-string heuristic. The previous version
    tested ``city == ""`` — but 27 of 28 state rows carry city NULL, so the test
    was always false, this returned None, and the caller silently filed state law
    under the LEAF CITY. That single mismatch misparented 1,157 rows and is why a
    Los Angeles tenant was served no California minimum wage (migration jparent01).
    """
    current_id = jurisdiction_id
    for _ in range(4):  # city -> county -> state -> federal
        row = await conn.fetchrow(
            "SELECT id, level, parent_id FROM jurisdictions WHERE id = $1", current_id
        )
        if not row:
            return None
        if row["level"] == "state":
            return row["id"]
        if not row["parent_id"]:
            return None
        current_id = row["parent_id"]
    return None


async def _get_or_create_state_jurisdiction_id(
    conn, leaf_jurisdiction_id: UUID
) -> Optional[UUID]:
    """The state node for a leaf, creating it if the tree simply lacks one.

    Falling back to the leaf (what this code used to do) is never acceptable for
    a state-level obligation: it makes the row invisible to every other city in
    the same state. If the walk finds nothing, look the state up by code, and
    create the node as a last resort.
    """
    state_id = await _get_state_jurisdiction_id(conn, leaf_jurisdiction_id)
    if state_id:
        return state_id

    leaf = await conn.fetchrow(
        "SELECT state, country_code FROM jurisdictions WHERE id = $1", leaf_jurisdiction_id
    )
    if not leaf or not leaf["state"]:
        return None

    existing = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE level = 'state' AND state = $1 LIMIT 1",
        leaf["state"],
    )
    if existing:
        return existing

    federal_id = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' LIMIT 1"
    )
    return await conn.fetchval(
        """
        INSERT INTO jurisdictions (display_name, level, state, country_code, parent_id, authority_type)
        VALUES ($1, 'state', $1, $2, $3, 'geographic')
        RETURNING id
        """,
        leaf["state"],
        leaf["country_code"] or "US",
        federal_id,
    )


async def _resolve_jurisdiction_id_for_level(
    conn, leaf_jurisdiction_id: UUID, jurisdiction_level: str
) -> Optional[UUID]:
    """Resolve the jurisdiction a requirement belongs on, from its stamped level.

    Returns None when the level is known but no home for it can be resolved.
    **Never falls back to the leaf.** That fallback is what corrupted 63% of the
    catalog (jparent01): chain resolution walks jurisdiction_id, so a state law
    filed under a city is invisible to every other city in that state — while
    still *displaying* as "California / state", so nothing looked wrong. Dropping
    the row is loud; misfiling it is silent. Callers park the None rows.
    """
    level = (jurisdiction_level or "").lower().strip()

    # If the node we were handed already IS the requested level, it is its own
    # home. The per-level helpers below assume a CITY leaf and walk the parent
    # chain — handed a county node, _get_county_jurisdiction_id inspects the
    # county's PARENT (the state) and returns None, so every county-stamped row
    # researched *at* a county node was silently skipped while the caller counted
    # it as written.
    own = await conn.fetchrow(
        "SELECT level FROM jurisdictions WHERE id = $1", leaf_jurisdiction_id
    )
    own_level = str(own["level"]) if own else None
    if own_level == level or (
        {own_level, level} <= {"federal", "national"} and own_level and level
    ):
        return leaf_jurisdiction_id

    if level == "city" or not level:
        return leaf_jurisdiction_id

    if level == "county":
        return await _get_county_jurisdiction_id(conn, leaf_jurisdiction_id)

    if level == "state":
        return await _get_or_create_state_jurisdiction_id(conn, leaf_jurisdiction_id)

    # 'national' is the same tier as 'federal' — a country's own law. It had no
    # case at all here, so it fell through to "unknown level, treat as city" and
    # 232 national rows were filed under cities.
    if level in ("federal", "national"):
        leaf = await conn.fetchrow(
            "SELECT country_code FROM jurisdictions WHERE id = $1", leaf_jurisdiction_id
        )
        country = (leaf["country_code"] if leaf else None) or "US"
        if country == "US":
            return await conn.fetchval(
                "SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' LIMIT 1"
            )
        return await conn.fetchval(
            "SELECT id FROM jurisdictions WHERE level = 'national' AND country_code = $1 LIMIT 1",
            country,
        )

    return None


async def _upsert_jurisdiction_requirements_routed(
    conn, leaf_jurisdiction_id: UUID, reqs: List[Dict], *, research_source: Optional[str] = None
) -> Dict[str, int]:
    """Route requirements to their proper jurisdiction level, then upsert.

    Instead of storing all requirements (federal, state, county, city) on
    the leaf city jurisdiction, this routes each requirement to the
    jurisdiction it actually belongs to. The resolve_jurisdiction_stack CTE
    already walks city→county→state→federal, so storing each requirement
    once at its source level eliminates duplication.
    """
    from collections import defaultdict

    # Group requirements by their jurisdiction level
    level_groups: Dict[str, List[Dict]] = defaultdict(list)
    for req in reqs:
        level = (req.get("jurisdiction_level") or "city").lower().strip()
        level_groups[level].append(req)

    # Resolve target jurisdiction for each level and upsert
    affected_jurisdictions: set = set()
    city_keys: set = set()  # Track city-level keys for cleanup

    unroutable = 0
    for level, group_reqs in level_groups.items():
        target_jid = await _resolve_jurisdiction_id_for_level(
            conn, leaf_jurisdiction_id, level
        )
        if target_jid is None:
            # No home for this level. Writing it to the leaf anyway is what broke
            # the catalog (jparent01) — the row would render as "state law" while
            # being reachable only from this one city. Skip and count it.
            unroutable += len(group_reqs)
            logger.warning(
                "compliance: cannot route %d %r-level requirement(s) from leaf %s — skipped",
                len(group_reqs), level, leaf_jurisdiction_id,
            )
            continue

        affected_jurisdictions.add(target_jid)

        await _upsert_requirements_additive(conn, target_jid, group_reqs, research_source=research_source)

        if target_jid == leaf_jurisdiction_id and level == "city":
            for req in group_reqs:
                city_keys.add(_compute_requirement_key(req))

    # Level-scoped cleanup: only delete stale CITY-level rows from the leaf
    # (preserves inherited requirements; only cleans up local ones).
    #
    # Scoped to `city` AND to this leaf on purpose. The sibling non-routed upsert
    # deletes any row of ANY level whose key this run didn't re-emit — against the
    # SHARED catalog, so one tenant's research pass can delete rows every other
    # tenant reads. See _upsert_jurisdiction_requirements.
    if city_keys:
        existing_rows = await conn.fetch(
            """SELECT id, requirement_key FROM jurisdiction_requirements
               WHERE jurisdiction_id = $1 AND jurisdiction_level = 'city'""",
            leaf_jurisdiction_id,
        )
        for row in existing_rows:
            if row["requirement_key"] not in city_keys:
                await conn.execute(
                    "DELETE FROM jurisdiction_requirements WHERE id = $1", row["id"]
                )

    # Update requirement_count + last_verified_at on all affected jurisdictions
    for jid in affected_jurisdictions:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
            jid,
        )
        await conn.execute(
            "UPDATE jurisdictions SET last_verified_at = NOW(), requirement_count = $1, updated_at = NOW() WHERE id = $2",
            count,
            jid,
        )

    # Always touch last_verified_at on the leaf even if no city-level requirements
    if leaf_jurisdiction_id not in affected_jurisdictions:
        await conn.execute(
            "UPDATE jurisdictions SET last_verified_at = NOW(), updated_at = NOW() WHERE id = $1",
            leaf_jurisdiction_id,
        )

    return {
        "total": len(reqs),
        "levels_routed": {level: len(group) for level, group in level_groups.items()},
        "jurisdictions_affected": len(affected_jurisdictions),
    }


async def _upsert_requirements_routed_additive(
    conn, leaf_jurisdiction_id: UUID, reqs: List[Dict], *,
    research_source: Optional[str] = None, initial_status: str = "active",
) -> Dict[str, Dict[str, Any]]:
    """Route each requirement to the jurisdiction its stamped level belongs on.

    Like ``_upsert_jurisdiction_requirements_routed`` but with NO delete pass, so
    it is safe for a research run that covers only one slice of a jurisdiction
    (a single industry's categories). That sibling's city-cleanup deletes leaf
    city rows whose key the run didn't re-emit — for a dental-only pass that would
    delete every OTHER industry's city rows. It also deliberately does NOT stamp
    ``last_verified_at`` on the affected jurisdictions: a one-industry pass has
    not verified the jurisdiction, and stamping it would make
    ``_is_jurisdiction_fresh`` suppress the *generic* research the jurisdiction
    may still need.

    Without routing, a specialty pass writes state- and federal-stamped rows onto
    the LEAF CITY (this is what `_upsert_requirements_additive` does — it takes
    the jurisdiction it is handed). That is precisely the corruption migration
    jparent01 exists to undo: the row renders as "California / state" while being
    reachable only from the one city it was researched from, so no other city in
    the state can ever see it.

    Returns ``{level: {"jurisdiction_id": UUID|None, "written": int}}`` — what
    actually LANDED, per stamped level. Callers recording coverage must read this,
    not the input list: a row whose level cannot be routed is skipped, and a
    ledger that counts skipped rows as written marks a hole in the catalog as
    "covered", permanently.
    """
    from collections import defaultdict

    level_groups: Dict[str, List[Dict]] = defaultdict(list)
    for req in reqs:
        level = (req.get("jurisdiction_level") or "city").lower().strip()
        level_groups[level].append(req)

    outcome: Dict[str, Dict[str, Any]] = {}
    affected: set = set()
    for level, group_reqs in level_groups.items():
        target_jid = await _resolve_jurisdiction_id_for_level(
            conn, leaf_jurisdiction_id, level
        )
        if target_jid is None:
            logger.warning(
                "compliance: cannot route %d %r-level requirement(s) from %s — skipped",
                len(group_reqs), level, leaf_jurisdiction_id,
            )
            outcome[level] = {"jurisdiction_id": None, "written": 0}
            continue
        await _upsert_requirements_additive(
            conn, target_jid, group_reqs, research_source=research_source,
            initial_status=initial_status,
        )
        affected.add(target_jid)
        prev = outcome.get(level)
        outcome[level] = {
            "jurisdiction_id": target_jid,
            "written": (prev["written"] if prev else 0) + len(group_reqs),
        }

    for jid in affected:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1", jid
        )
        await conn.execute(
            "UPDATE jurisdictions SET requirement_count = $1, updated_at = NOW() WHERE id = $2",
            count, jid,
        )
    return outcome


async def _upsert_requirements_additive(
    conn, jurisdiction_id: UUID, reqs: List[Dict], *, research_source: Optional[str] = None,
    source_tier: Optional[str] = None, initial_status: str = "active",
):
    """Upsert requirements to a jurisdiction without deleting existing rows.

    research_source: optional tag stored in metadata.research_source to track
    where data came from.  Known values:
        "gemini"       – Gemini AI research
        "official_api" – Government APIs (Federal Register, CMS, Congress.gov)
        "claude_skill" – Claude compliance skill
        "structured"   – Tier-1 structured data (CSV/scrape)
        "manual"       – Admin manual edit

    initial_status: status a brand-new row is INSERTed with — 'active' (default,
    every existing caller) or 'pending' (admin-queued research staged for
    review; invisible to tenants until POST /admin/research-review/approve).
    Only affects the INSERT branch. The ON CONFLICT UPDATE's status CASE is
    untouched: a staged write must never demote an already-active row, and a
    grounding failure still wins over staging (lands 'under_review', the
    existing quarantine surface) — simpler than a three-way state machine.
    """
    # ── Data integrity pipeline ──
    for req in reqs:
        _clamp_varchar_fields(req)
        cat = _normalize_category(req.get("category"))
        if cat:
            req["category"] = cat
    await _validate_source_urls(reqs)

    category_ids = {r["slug"]: r["id"] for r in await conn.fetch(
        "SELECT id, slug FROM compliance_categories"
    )}
    # Registry↔seed drift fallback: the code registry has repeatedly gained
    # categories before their compliance_categories seed migration landed
    # (baseline01, mfgcat01, catseed01 — each fixed a prior instance). A row
    # in such a category must still be WRITTEN (the `category` text column is
    # what nearly every read path filters on) — parked on `uncategorized`
    # rather than dropped, and never on an arbitrary row (the old LIMIT-1
    # bug). catseed01's backfill re-homes parked rows once the seed exists.
    uncategorized_id = category_ids.get("uncategorized")

    for req in reqs:
        category_id = category_ids.get(req.get("category"))
        if category_id is None:
            logger.warning(
                "compliance_service: category %r has no compliance_categories row "
                "(registry/seed drift) — parking %r on 'uncategorized' for "
                "jurisdiction %s (author a seed migration; see catseed01)",
                req.get("category"), req.get("title"), jurisdiction_id,
            )
            category_id = uncategorized_id
            if category_id is None:
                logger.error(
                    "compliance_service: no 'uncategorized' fallback row either — "
                    "dropping requirement %r", req.get("title"),
                )
                continue

        # Build per-requirement metadata (research_source + penalties if present)
        meta_dict: dict = {}
        # Carry any caller-set metadata (e.g. grounding marker from grounded
        # extraction) — but never let it override research_source below.
        req_meta = req.get("metadata")
        if isinstance(req_meta, dict):
            meta_dict.update(req_meta)
        if research_source:
            meta_dict["research_source"] = research_source
        # Sink-side guard for EVERY research path, mirroring the penalty guard
        # below: a caller that never validated against a grounded corpus (e.g.
        # the legacy specialty-research path) previously left this key absent
        # entirely, indistinguishable from pre-grounding-era rows. Default to
        # "ungrounded" so provenance is always queryable.
        meta_dict["grounding"] = req.get("grounding") or "ungrounded"
        if req.get("grounded_citations"):
            meta_dict["grounded_citations"] = req["grounded_citations"]
        # Candidate legal citation the model returned (primary-source prompt). Kept
        # in metadata only — the statute_citation COLUMN stays reconcile-owned; this
        # is the value the pilot's codify step confirms into that trio.
        rc = req.get("statute_citation")
        if rc and str(rc).strip():
            meta_dict["research_citation"] = str(rc).strip()[:500]
        # Sink-side penalty guard for EVERY research path (grounded or not): drop
        # the run-local cited_sources transport key and any insubstantive shell,
        # so ungrounded runs can't persist corpus-local S-ids or inflate the
        # penalty-coverage counter with an empty block.
        from .scope_registry.grounded import sanitize_penalties_for_persist
        penalties = sanitize_penalties_for_persist(req.get("penalties"))
        if penalties is not None:
            meta_dict["penalties"] = penalties
        # "No rule applies here" placeholder — kept in the catalog (the research
        # prompt asks for one instead of an empty list, which downstream reads as a
        # FAILED category), but filtered out of the tenant's tab by
        # _project_chain_to_location. Only ever set from the model's own flag: no
        # text heuristic can tell these apart from real law (`no_surprises_act` is
        # a real statute; "Daily Overtime: none" is a real answer).
        if req.get("no_rule_applies"):
            meta_dict["no_rule_applies"] = True
        meta_fragment = json.dumps(meta_dict) if meta_dict else None

        requirement_key, regulation_key = _compute_key_parts(req)
        # RKD is keyed on the NORMALIZED category (same form as the bare key);
        # the raw req category may be cased/aliased ('Meal-Breaks').
        normalized_category = _normalize_category(req.get("category"))
        # _as_jsonb, not json.dumps: these values often come straight off a JSONB
        # read (asyncpg returns them as str), and dumps() would add another layer
        # of escaping on every research pass. See _as_jsonb.
        tc_json = _as_jsonb(req.get("trigger_conditions"))
        aet = _as_jsonb(req.get("applicable_entity_types"))
        steps_raw = req.get("implementation_steps")
        steps_json = json.dumps(steps_raw) if isinstance(steps_raw, list) and steps_raw else None
        # Grounding verdict → status intent (tri-state, consumed by the INSERT
        # VALUES and the ON CONFLICT status CASE below). req["grounded"] is an
        # explicit True/False ONLY when this req was actually checked against a
        # fetched corpus (validate_requirement_citations) — never set at all on
        # the legacy ungrounded-by-design research paths, which pass 'none' and
        # leave status alone. False ⇒ quarantine ('under_review'); True ⇒
        # 'promote' (un-quarantines a previously-failed row — without this,
        # under_review was terminal and the row looped on the research worklist
        # forever). Narrower than "any ungrounded row" by design.
        grounded = req.get("grounded")
        if grounded is False:
            req_status = "under_review"
        elif grounded is True:
            req_status = "promote"
        else:
            req_status = "none"
        await conn.execute(
            """
            INSERT INTO jurisdiction_requirements
                (jurisdiction_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                 title, description, current_value, numeric_value, source_url, source_name,
                 effective_date, expiration_date, last_verified_at, requires_written_policy,
                 applicable_industries, trigger_conditions, applicable_entity_types,
                 implementation_steps, category_id, metadata, source_tier,
                 regulation_key, key_definition_id, source_url_status, source_checked_at, status)
            VALUES ($1, $2, $3::text, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW(), $15, $16, $17, $18,
                    $22::jsonb,
                    $19,
                    CASE WHEN $20::text IS NOT NULL THEN $20::jsonb ELSE '{}'::jsonb END,
                    $21::source_tier_enum,
                    $23,
                    (SELECT id FROM regulation_key_definitions
                     WHERE key = $23::text AND category_slug = $24::text LIMIT 1),
                    COALESCE($25::text, 'unchecked'),
                    CASE WHEN $25::text IS NOT NULL THEN NOW() ELSE NULL END,
                    CASE WHEN $26::text = 'under_review'
                         THEN 'under_review'::requirement_status_enum
                         ELSE $28::requirement_status_enum END)
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                category = EXCLUDED.category,
                rate_type = EXCLUDED.rate_type,
                jurisdiction_level = EXCLUDED.jurisdiction_level,
                jurisdiction_name = EXCLUDED.jurisdiction_name,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                previous_value = LEFT(jurisdiction_requirements.current_value, 100),
                current_value = EXCLUDED.current_value,
                numeric_value = EXCLUDED.numeric_value,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                requires_written_policy = EXCLUDED.requires_written_policy,
                applicable_industries = (
                    SELECT array_agg(DISTINCT val) FROM unnest(
                        COALESCE(jurisdiction_requirements.applicable_industries, '{}')
                        || COALESCE(EXCLUDED.applicable_industries, '{}')
                    ) AS val
                ),
                trigger_conditions = EXCLUDED.trigger_conditions,
                applicable_entity_types = EXCLUDED.applicable_entity_types,
                effective_date = EXCLUDED.effective_date,
                expiration_date = EXCLUDED.expiration_date,
                last_verified_at = NOW(),
                last_changed_at = CASE
                    WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                    THEN NOW() ELSE jurisdiction_requirements.last_changed_at END,
                implementation_steps = EXCLUDED.implementation_steps,
                -- A re-research pass IS "we re-read the law", so it clears a
                -- drift-raised needs_review: recompute the status from the value
                -- diff and drop the metadata.drift breadcrumb. Other statuses are
                -- left untouched (this upsert has never owned change_status).
                change_status = CASE
                    WHEN jurisdiction_requirements.change_status = 'needs_review'
                    THEN (CASE
                        WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                        THEN 'changed' ELSE 'unchanged' END)
                    ELSE jurisdiction_requirements.change_status END,
                metadata = (
                    CASE
                        WHEN jurisdiction_requirements.change_status = 'needs_review'
                        THEN (COALESCE(jurisdiction_requirements.metadata, '{}'::jsonb) - 'drift') || EXCLUDED.metadata
                        ELSE COALESCE(jurisdiction_requirements.metadata, '{}'::jsonb) || EXCLUDED.metadata END
                    -- jsonb || is a SHALLOW merge, so a new penalties block would
                    -- wholesale-replace an existing one and drop keys the new block
                    -- omits (e.g. a skill-written source_url that grounded
                    -- re-research never sets). Deep-merge the penalties sub-object:
                    -- old penalties overlaid by new (new wins per key, old keys kept).
                    || CASE WHEN EXCLUDED.metadata ? 'penalties'
                        THEN jsonb_build_object('penalties',
                            COALESCE(jurisdiction_requirements.metadata->'penalties', '{}'::jsonb)
                            || (EXCLUDED.metadata->'penalties'))
                        ELSE '{}'::jsonb END
                ),
                source_tier = CASE
                    WHEN EXCLUDED.source_tier IS NOT NULL
                     AND (jurisdiction_requirements.source_tier IS NULL
                          OR EXCLUDED.source_tier < jurisdiction_requirements.source_tier)
                    THEN EXCLUDED.source_tier
                    ELSE jurisdiction_requirements.source_tier
                END,
                regulation_key = COALESCE(EXCLUDED.regulation_key, jurisdiction_requirements.regulation_key),
                key_definition_id = COALESCE(EXCLUDED.key_definition_id, jurisdiction_requirements.key_definition_id),
                -- Forward-repair: a re-research with a properly-resolved category
                -- corrects a historically mis-tagged row (the old LIMIT-1 bug).
                -- NULLIF keeps a drift-parked 'uncategorized' write ($27) from
                -- downgrading an already-correct tag.
                category_id = COALESCE(
                    NULLIF(EXCLUDED.category_id, $27::uuid),
                    jurisdiction_requirements.category_id),
                source_url_status = CASE
                    WHEN $25::text IS NOT NULL THEN $25::text
                    ELSE jurisdiction_requirements.source_url_status END,
                source_checked_at = CASE
                    WHEN $25::text IS NOT NULL THEN NOW()
                    ELSE jurisdiction_requirements.source_checked_at END,
                -- Grounding verdicts move status BOTH ways: a write that failed
                -- grounding quarantines the row; a write that PASSED grounding
                -- promotes a quarantined row back to active (without this,
                -- under_review was terminal — the row stayed off the served
                -- surface forever while staying ON the research worklist,
                -- re-burning Gemini every scheduled cycle). A write with no
                -- verdict (the ordinary ungrounded path) never touches status.
                status = CASE
                    WHEN $26::text = 'under_review' THEN 'under_review'::requirement_status_enum
                    WHEN $26::text = 'promote'
                         AND jurisdiction_requirements.status = 'under_review'
                    THEN 'active'::requirement_status_enum
                    ELSE jurisdiction_requirements.status END,
                updated_at = NOW()
            -- 'repealed' is an admin's explicit "this value is WRONG" verdict
            -- (POST /under-review/decide) and the row survives only as an audit
            -- trail. Re-research must not silently overwrite it back into
            -- existence — leave the row frozen until a human un-rejects it.
            WHERE jurisdiction_requirements.status <> 'repealed'
            """,
            jurisdiction_id,
            requirement_key,
            req.get("category"),
            req.get("rate_type"),
            req.get("jurisdiction_level"),
            req.get("jurisdiction_name"),
            req.get("title"),
            req.get("description"),
            req.get("current_value"),
            req.get("numeric_value"),
            req.get("source_url"),
            req.get("source_name"),
            parse_date(req.get("effective_date")),
            parse_date(req.get("expiration_date")),
            req.get("requires_written_policy"),
            req.get("applicable_industries"),
            tc_json,
            aet,
            category_id,           # $19: resolved above — never an arbitrary fallback row
            meta_fragment,         # $20: research_source metadata
            source_tier,           # $21: source_tier enum value
            steps_json,            # $22: implementation_steps JSONB
            regulation_key,        # $23: bare regulation_key (store↔scope join key)
            normalized_category,   # $24: normalized category for the RKD FK lookup
            req.get("source_url_status"),  # $25: liveness flag from _validate_source_urls
            req_status,             # $26: grounding verdict — 'under_review' | 'promote' | 'none'
            uncategorized_id,       # $27: drift-park sentinel — never downgrades an existing tag
            initial_status,         # $28: INSERT-only status for brand-new rows — 'active' | 'pending'
        )


async def _research_healthcare_requirements_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Research missing healthcare-only categories inline for a jurisdiction."""
    from .gemini_compliance import get_gemini_compliance_service
    from .jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    location_name = f"{city}, {state}"

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(list(HEALTHCARE_CATEGORIES))
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    existing = await conn.fetch(
        "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in HEALTHCARE_CATEGORIES if cat not in existing_cats)

    if not missing:
        print(f"[Healthcare Research] All healthcare categories already present for {location_name}")
        return {
            "new": 0,
            "location": location_name,
            "categories": [],
            "failed": [],
            "requirements": [],
            "skipped": True,
        }

    print(
        f"[Healthcare Research] Researching {len(missing)} healthcare categories "
        f"for {location_name}: {', '.join(missing)}"
    )

    service = get_gemini_compliance_service()
    total_new = 0
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []

    for idx, category in enumerate(missing, start=1):
        print(
            f"[Healthcare Research] [{idx}/{len(missing)}] Researching {category} "
            f"for {location_name}..."
        )
        if progress_callback:
            progress_callback(
                idx,
                len(missing),
                f"Researching {category.replace('_', ' ')} for {location_name}...",
            )

        try:
            reqs = await service.research_location_compliance(
                city=city,
                state=state,
                county=county,
                categories=[category],
                source_context=source_context,
                corrections_context=corrections_context,
                preemption_rules=preemption_rules,
                has_local_ordinance=has_local_ordinance,
            )
            reqs = reqs or []

            for req in reqs:
                _clamp_varchar_fields(req)
                if not req.get("applicable_industries"):
                    req["applicable_industries"] = ["healthcare"]

            if reqs:
                await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
                total_new += len(reqs)
                added_requirements.extend(reqs)
                print(
                    f"[Healthcare Research]   -> {len(reqs)} requirements saved "
                    f"for {category}"
                )
            else:
                print(f"[Healthcare Research]   -> No results for {category}")
        except Exception as e:
            failed_categories.append(category)
            print(f"[Healthcare Research]   -> Error researching {category}: {e}")

    print(
        f"[Healthcare Research] Complete for {location_name}: {total_new} new, "
        f"{len(failed_categories)} failed"
    )

    if failed_categories and total_new == 0:
        raise RuntimeError(
            f"All healthcare categories failed for {location_name}: "
            f"{', '.join(failed_categories)}"
        )

    # ── Phase 2: Triggered research based on facility attributes ──
    from ..compliance_registry import get_activated_profiles

    try:
        loc_rows = await conn.fetch(
            "SELECT facility_attributes FROM business_locations WHERE jurisdiction_id = $1",
            jurisdiction_id,
        )
        all_facility_attrs = set()
        for lr in loc_rows:
            fa = lr["facility_attributes"]
            if isinstance(fa, str):
                try:
                    fa = json.loads(fa)
                except (json.JSONDecodeError, TypeError):
                    continue
            if fa:
                # Collect unique profiles across all linked locations
                for profile in get_activated_profiles(fa):
                    all_facility_attrs.add(profile.key)
    except Exception as e:
        print(f"[Healthcare Research] Error loading facility attributes: {e}")
        all_facility_attrs = set()

    if all_facility_attrs:
        from ..compliance_registry import TRIGGER_PROFILES

        activated_profiles = [p for p in TRIGGER_PROFILES if p.key in all_facility_attrs]
        for profile in activated_profiles:
            trigger_cats = [
                c for c in profile.applicable_categories
                if c in HEALTHCARE_CATEGORIES or c in MEDICAL_COMPLIANCE_CATEGORIES
            ]
            if not trigger_cats:
                continue

            print(
                f"[Healthcare Research] Phase 2: Triggered research for "
                f"{profile.label} ({len(trigger_cats)} categories)"
            )
            if progress_callback:
                progress_callback(
                    0, 0,
                    f"Researching {profile.label}-specific requirements...",
                )

            try:
                triggered_reqs = await service.research_triggered_requirements(
                    city=city,
                    state=state,
                    county=county,
                    profile_key=profile.key,
                    profile_label=profile.label,
                    trigger_condition=profile.trigger_condition,
                    research_instruction=profile.research_instruction,
                    categories=trigger_cats,
                    source_context=source_context,
                )

                for req in triggered_reqs:
                    _clamp_varchar_fields(req)
                    if not req.get("applicable_industries"):
                        req["applicable_industries"] = ["healthcare"]

                if triggered_reqs:
                    await _upsert_requirements_additive(conn, jurisdiction_id, triggered_reqs, research_source="gemini")
                    total_new += len(triggered_reqs)
                    added_requirements.extend(triggered_reqs)
                    print(
                        f"[Healthcare Research]   -> {len(triggered_reqs)} "
                        f"{profile.label}-specific requirements saved"
                    )
            except Exception as e:
                print(f"[Healthcare Research]   -> Error in triggered research for {profile.key}: {e}")

    return {
        "new": total_new,
        "location": location_name,
        "categories": missing,
        "failed": failed_categories,
        "requirements": added_requirements,
    }


async def _research_oncology_requirements_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Research missing oncology-only categories for a jurisdiction."""
    from .gemini_compliance import get_gemini_compliance_service
    from .jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    location_name = f"{city}, {state}"

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(list(ONCOLOGY_CATEGORIES))
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    existing = await conn.fetch(
        "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in ONCOLOGY_CATEGORIES if cat not in existing_cats)

    if not missing:
        print(f"[Oncology Research] All oncology categories already present for {location_name}")
        return {
            "new": 0,
            "location": location_name,
            "categories": [],
            "failed": [],
            "requirements": [],
            "skipped": True,
        }

    print(
        f"[Oncology Research] Researching {len(missing)} oncology categories "
        f"for {location_name}: {', '.join(missing)}"
    )

    service = get_gemini_compliance_service()
    total_new = 0
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []

    if progress_callback:
        progress_callback(1, 1, f"Researching {len(missing)} oncology categories for {location_name}...")

    try:
        reqs = await service.research_location_compliance(
            city=city,
            state=state,
            county=county,
            categories=missing,
            source_context=source_context,
            corrections_context=corrections_context,
            preemption_rules=preemption_rules,
            has_local_ordinance=has_local_ordinance,
        )
        reqs = reqs or []

        for req in reqs:
            _clamp_varchar_fields(req)
            if not req.get("applicable_industries"):
                req["applicable_industries"] = ["healthcare:oncology"]

        if reqs:
            await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
            total_new = len(reqs)
            added_requirements.extend(reqs)
            # Log per-category breakdown
            by_cat: Dict[str, int] = {}
            for r in reqs:
                by_cat[r.get("category", "unknown")] = by_cat.get(r.get("category", "unknown"), 0) + 1
            for cat, count in sorted(by_cat.items()):
                print(f"[Oncology Research]   -> {count} requirements saved for {cat}")
        else:
            print(f"[Oncology Research]   -> No results returned")
            failed_categories = list(missing)
    except Exception as e:
        failed_categories = list(missing)
        print(f"[Oncology Research]   -> Error: {e}")

    print(
        f"[Oncology Research] Complete for {location_name}: {total_new} new, "
        f"{len(failed_categories)} failed"
    )

    if failed_categories and total_new == 0:
        raise RuntimeError(
            f"All oncology categories failed for {location_name}: "
            f"{', '.join(failed_categories)}"
        )

    return {
        "new": total_new,
        "location": location_name,
        "categories": missing,
        "failed": failed_categories,
        "requirements": added_requirements,
    }


async def _research_life_sciences_requirements_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Research missing life-sciences-only categories for a jurisdiction."""
    from .gemini_compliance import get_gemini_compliance_service
    from .jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    location_name = f"{city}, {state}"

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(list(LIFE_SCIENCES_CATEGORIES))
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    existing = await conn.fetch(
        "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in LIFE_SCIENCES_CATEGORIES if cat not in existing_cats)

    if not missing:
        print(f"[Life Sciences Research] All life sciences categories already present for {location_name}")
        return {
            "new": 0,
            "location": location_name,
            "categories": [],
            "failed": [],
            "requirements": [],
            "skipped": True,
        }

    print(
        f"[Life Sciences Research] Researching {len(missing)} life sciences categories "
        f"for {location_name}: {', '.join(missing)}"
    )

    service = get_gemini_compliance_service()
    total_new = 0
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []

    if progress_callback:
        progress_callback(1, 1, f"Researching {len(missing)} life sciences categories for {location_name}...")

    try:
        reqs = await service.research_location_compliance(
            city=city,
            state=state,
            county=county,
            categories=missing,
            source_context=source_context,
            corrections_context=corrections_context,
            preemption_rules=preemption_rules,
            has_local_ordinance=has_local_ordinance,
        )
        reqs = reqs or []

        for req in reqs:
            _clamp_varchar_fields(req)
            if not req.get("applicable_industries"):
                req["applicable_industries"] = ["biotech"]

        if reqs:
            await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
            total_new = len(reqs)
            added_requirements.extend(reqs)
            by_cat: Dict[str, int] = {}
            for r in reqs:
                by_cat[r.get("category", "unknown")] = by_cat.get(r.get("category", "unknown"), 0) + 1
            for cat, count in sorted(by_cat.items()):
                print(f"[Life Sciences Research]   -> {count} requirements saved for {cat}")
        else:
            print(f"[Life Sciences Research]   -> No results returned")
            failed_categories = list(missing)
    except Exception as e:
        failed_categories = list(missing)
        print(f"[Life Sciences Research]   -> Error: {e}")

    print(
        f"[Life Sciences Research] Complete for {location_name}: {total_new} new, "
        f"{len(failed_categories)} failed"
    )

    if failed_categories and total_new == 0:
        raise RuntimeError(
            f"All life sciences categories failed for {location_name}: "
            f"{', '.join(failed_categories)}"
        )

    return {
        "new": total_new,
        "location": location_name,
        "categories": missing,
        "failed": failed_categories,
        "requirements": added_requirements,
    }


async def _research_medical_compliance_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Research missing medical compliance categories for a jurisdiction.

    Covers 17 categories from the US Medical Compliance Policy Reference
    (health IT, cybersecurity, pharmacy, telehealth, devices, etc.).
    """
    from .gemini_compliance import get_gemini_compliance_service
    from .jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    location_name = f"{city}, {state}"

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(list(MEDICAL_COMPLIANCE_CATEGORIES))
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    existing = await conn.fetch(
        "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in MEDICAL_COMPLIANCE_CATEGORIES if cat not in existing_cats)

    if not missing:
        print(f"[Medical Compliance] All medical compliance categories already present for {location_name}")
        return {
            "new": 0,
            "location": location_name,
            "categories": [],
            "failed": [],
            "requirements": [],
            "skipped": True,
        }

    print(
        f"[Medical Compliance] Researching {len(missing)} categories "
        f"for {location_name}: {', '.join(missing)}"
    )

    service = get_gemini_compliance_service()
    total_new = 0
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []

    # Batch categories into groups of 4 to reduce Gemini calls (4-5 calls
    # instead of 17) while keeping each prompt small enough for accuracy.
    batch_size = 4
    batches = [missing[i:i + batch_size] for i in range(0, len(missing), batch_size)]

    for batch_idx, batch in enumerate(batches, start=1):
        batch_label = ", ".join(c.replace("_", " ") for c in batch)
        print(
            f"[Medical Compliance] [batch {batch_idx}/{len(batches)}] Researching "
            f"{batch_label} for {location_name}..."
        )
        if progress_callback:
            progress_callback(
                batch_idx,
                len(batches),
                f"Researching {batch_label} for {location_name}...",
            )

        try:
            reqs = await service.research_location_compliance(
                city=city,
                state=state,
                county=county,
                categories=batch,
                source_context=source_context,
                corrections_context=corrections_context,
                preemption_rules=preemption_rules,
                has_local_ordinance=has_local_ordinance,
            )
            reqs = reqs or []

            for req in reqs:
                _clamp_varchar_fields(req)
                cat = req.get("category", "")
                if not req.get("applicable_industries"):
                    tag = MEDICAL_COMPLIANCE_INDUSTRY_TAGS.get(cat, "healthcare")
                    req["applicable_industries"] = [tag]

            if reqs:
                await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
                total_new += len(reqs)
                added_requirements.extend(reqs)
                by_cat: Dict[str, int] = {}
                for r in reqs:
                    by_cat[r.get("category", "unknown")] = by_cat.get(r.get("category", "unknown"), 0) + 1
                for cat, count in sorted(by_cat.items()):
                    print(f"[Medical Compliance]   -> {count} requirements saved for {cat}")
            else:
                print(f"[Medical Compliance]   -> No results for batch")
                failed_categories.extend(batch)
        except Exception as e:
            failed_categories.extend(batch)
            print(f"[Medical Compliance]   -> Error researching batch: {e}")

    print(
        f"[Medical Compliance] Complete for {location_name}: {total_new} new, "
        f"{len(failed_categories)} failed"
    )

    if failed_categories and total_new == 0:
        raise RuntimeError(
            f"All medical compliance categories failed for {location_name}: "
            f"{', '.join(failed_categories)}"
        )

    return {
        "new": total_new,
        "location": location_name,
        "categories": missing,
        "failed": failed_categories,
        "requirements": added_requirements,
    }


async def _fill_from_state_fallback(
    conn,
    service,
    jurisdiction_id: UUID,
    city: str,
    state: str,
    county: Optional[str],
    has_local_ordinance: Optional[bool],
    requirements: List[Dict],
    still_missing: List[str],
    threshold_days: int,
) -> List[Dict]:
    """For categories still missing after Tier 3, try state cache then Gemini state research."""
    state_name = _CODE_TO_STATE_NAME.get(state.upper(), state)

    # 1. Try state cache with lenient threshold
    state_reqs = await _try_load_state_requirements(
        conn, jurisdiction_id, threshold_days
    )
    if state_reqs:
        target_set = set(still_missing)
        fill = [
            r
            for r in state_reqs
            if (_normalize_category(r.get("category")) or r.get("category"))
            in target_set
        ]
        if fill:
            print(
                f"[Compliance] State-level fallback filled {len(fill)} missing categories for {city}: {still_missing}"
            )
            return requirements + fill

    # 2. State cache empty or stale — research at state level via Gemini
    print(
        f"[Compliance] Researching {still_missing} at state level ({state}) for {city}"
    )
    state_researched = await service.research_location_compliance(
        city="",
        state=state,
        county="",
        categories=still_missing,
        source_context="",
        corrections_context="",
        preemption_rules={},
        has_local_ordinance=None,
        on_retry=None,
    )
    if state_researched:
        # Annotate as state-level and note city follows state law for this category
        for r in state_researched:
            r["jurisdiction_level"] = "state"
            r["jurisdiction_name"] = state_name
            desc = r.get("description") or ""
            note = f" [Applies via {state_name} state law; {city} has no local ordinance for this category.]"
            if note not in desc:
                r["description"] = desc + note

        _normalize_requirement_categories(state_researched)
        # Cache to state jurisdiction additively (don't delete existing state rows)
        state_jid = await _get_state_jurisdiction_id(conn, jurisdiction_id)
        if state_jid:
            await _upsert_requirements_additive(conn, state_jid, state_researched, research_source="gemini")
            print(
                f"[Compliance] Cached {len(state_researched)} state-level reqs to jurisdiction {state_jid}"
            )

        return requirements + state_researched

    return requirements


async def _refresh_repository_missing_categories(
    conn,
    service,
    *,
    jurisdiction_id: UUID,
    city: str,
    state: str,
    county: Optional[str],
    has_local_ordinance: Optional[bool],
    current_requirements: List[Dict[str, Any]],
    missing_categories: List[str],
    on_retry: Optional[Callable[[int, str], Any]] = None,
    industry_context: str = "",
) -> List[Dict[str, Any]]:
    """Refresh missing categories, merge with current requirements, and upsert source-of-truth."""
    if not missing_categories:
        return list(current_requirements)

    known_sources = await get_known_sources(conn, jurisdiction_id)
    if not known_sources:
        discovered = await service.discover_jurisdiction_sources(
            city=city,
            state=state,
            county=county,
        )
        for src in discovered:
            domain = (src.get("domain") or "").lower()
            if domain:
                for cat in src.get("categories", []):
                    await record_source(
                        conn, jurisdiction_id, domain, src.get("name"), cat
                    )
        known_sources = await get_known_sources(conn, jurisdiction_id)

    source_context = build_context_prompt(known_sources)
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}

    refreshed_requirements = await service.research_location_compliance(
        city=city,
        state=state,
        county=county,
        categories=missing_categories,
        source_context=source_context,
        corrections_context=corrections_context,
        preemption_rules=preemption_rules,
        has_local_ordinance=has_local_ordinance,
        on_retry=on_retry,
        industry_context=industry_context,
    )
    refreshed_requirements = refreshed_requirements or []

    if not refreshed_requirements:
        return list(current_requirements)

    target_set = {_normalize_category(cat) or cat for cat in missing_categories}
    preserved = [
        req
        for req in current_requirements
        if (_normalize_category(req.get("category")) or req.get("category"))
        not in target_set
    ]
    merged_requirements = preserved + refreshed_requirements

    if has_local_ordinance is False:
        merged_requirements = _filter_city_level_requirements(
            merged_requirements, state
        )

    _normalize_requirement_categories(merged_requirements)
    merged_requirements = await _filter_with_preemption(
        conn, merged_requirements, state
    )
    await _upsert_jurisdiction_requirements_routed(conn, jurisdiction_id, merged_requirements, research_source="structured")

    for req in refreshed_requirements:
        source_url = req.get("source_url", "")
        if source_url:
            domain = extract_domain(source_url)
            if domain:
                await record_source(
                    conn,
                    jurisdiction_id,
                    domain,
                    req.get("source_name"),
                    req.get("category", ""),
                )

    return merged_requirements


async def _upsert_jurisdiction_requirements(
    conn, jurisdiction_id: UUID, reqs: List[Dict]
):
    """Write Gemini results into the jurisdiction repository. Remove stale rows."""
    # ── Data integrity pipeline ──
    for req in reqs:
        _clamp_varchar_fields(req)
        cat = _normalize_category(req.get("category"))
        if cat:
            req["category"] = cat
    await _validate_source_urls(reqs)

    category_ids = {r["slug"]: r["id"] for r in await conn.fetch(
        "SELECT id, slug FROM compliance_categories"
    )}
    # Registry↔seed drift fallback — park on 'uncategorized', never drop and
    # never an arbitrary row. See the twin comment in
    # _upsert_requirements_additive; catseed01's backfill re-homes these.
    uncategorized_id = category_ids.get("uncategorized")

    new_keys = set()
    for req in reqs:
        # Computed + retained in new_keys even on a category-resolution miss
        # below, so an unresolvable category doesn't ALSO purge whatever
        # this jurisdiction already has stored under the same key via the
        # stale-row cleanup at the bottom of this function.
        requirement_key = _compute_requirement_key(req)
        new_keys.add(requirement_key)

        category_id = category_ids.get(req.get("category"))
        if category_id is None:
            logger.warning(
                "compliance_service: category %r has no compliance_categories row "
                "(registry/seed drift) — parking %r on 'uncategorized' for "
                "jurisdiction %s (author a seed migration; see catseed01)",
                req.get("category"), req.get("title"), jurisdiction_id,
            )
            category_id = uncategorized_id
            if category_id is None:
                logger.error(
                    "compliance_service: no 'uncategorized' fallback row either — "
                    "dropping requirement %r", req.get("title"),
                )
                continue

        # _as_jsonb, not json.dumps: these values often come straight off a JSONB
        # read (asyncpg returns them as str), and dumps() would add another layer
        # of escaping on every research pass. See _as_jsonb.
        tc_json = _as_jsonb(req.get("trigger_conditions"))
        aet = _as_jsonb(req.get("applicable_entity_types"))
        await conn.execute(
            """
            INSERT INTO jurisdiction_requirements
                (jurisdiction_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                 title, description, current_value, numeric_value, source_url, source_name,
                 effective_date, expiration_date, last_verified_at, requires_written_policy,
                 applicable_industries, trigger_conditions, applicable_entity_types,
                 category_id, source_url_status, source_checked_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW(), $15, $16, $17, $18,
                    $19,
                    COALESCE($20::text, 'unchecked'),
                    CASE WHEN $20::text IS NOT NULL THEN NOW() ELSE NULL END)
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                category = EXCLUDED.category,
                rate_type = EXCLUDED.rate_type,
                jurisdiction_level = EXCLUDED.jurisdiction_level,
                jurisdiction_name = EXCLUDED.jurisdiction_name,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                previous_value = LEFT(jurisdiction_requirements.current_value, 100),
                current_value = EXCLUDED.current_value,
                numeric_value = EXCLUDED.numeric_value,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                requires_written_policy = EXCLUDED.requires_written_policy,
                applicable_industries = (
                    SELECT array_agg(DISTINCT val) FROM unnest(
                        COALESCE(jurisdiction_requirements.applicable_industries, '{}')
                        || COALESCE(EXCLUDED.applicable_industries, '{}')
                    ) AS val
                ),
                trigger_conditions = EXCLUDED.trigger_conditions,
                applicable_entity_types = EXCLUDED.applicable_entity_types,
                effective_date = EXCLUDED.effective_date,
                expiration_date = EXCLUDED.expiration_date,
                last_verified_at = NOW(),
                last_changed_at = CASE
                    WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                    THEN NOW() ELSE jurisdiction_requirements.last_changed_at END,
                -- Forward-repair a historically mis-tagged category_id (the old
                -- LIMIT-1 bug); NULLIF keeps a drift-parked 'uncategorized'
                -- write ($21) from downgrading an already-correct tag.
                category_id = COALESCE(
                    NULLIF(EXCLUDED.category_id, $21::uuid),
                    jurisdiction_requirements.category_id),
                source_url_status = CASE
                    WHEN $20::text IS NOT NULL THEN $20::text
                    ELSE jurisdiction_requirements.source_url_status END,
                source_checked_at = CASE
                    WHEN $20::text IS NOT NULL THEN NOW()
                    ELSE jurisdiction_requirements.source_checked_at END,
                updated_at = NOW()
            """,
            jurisdiction_id,
            requirement_key,
            req.get("category"),
            req.get("rate_type"),
            req.get("jurisdiction_level"),
            req.get("jurisdiction_name"),
            req.get("title"),
            req.get("description"),
            req.get("current_value"),
            req.get("numeric_value"),
            req.get("source_url"),
            req.get("source_name"),
            parse_date(req.get("effective_date")),
            parse_date(req.get("expiration_date")),
            req.get("requires_written_policy"),
            req.get("applicable_industries"),
            tc_json,
            aet,
            category_id,           # $19: resolved above — never an arbitrary fallback row
            req.get("source_url_status"),  # $20: liveness flag from _validate_source_urls
            uncategorized_id,      # $21: drift-park sentinel — never downgrades an existing tag
        )

    # NO DELETE HERE — deliberately.
    #
    # This used to be: "Remove jurisdiction rows not in new result set" — every
    # row on this jurisdiction whose key THIS ONE RUN didn't re-emit was deleted.
    # jurisdiction_requirements is the SHARED catalog, so one tenant's research
    # pass (a single Gemini call, which returns a different slice every time)
    # deleted obligations every other tenant reads. It also destroyed rows whose
    # ids were still held by the caller's in-flight list, which then FK-aborted
    # the location sync mid-write (see _refresh_catalog_links).
    #
    # A row leaves the catalog by being *repealed* (status='repealed', which the
    # read path already excludes) or superseded — never by being absent from one
    # non-deterministic research result. Staleness is what last_verified_at and
    # the drift sweep are for.

    # Update jurisdiction counts and timestamp
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    await conn.execute(
        "UPDATE jurisdictions SET last_verified_at = NOW(), requirement_count = $1, updated_at = NOW() WHERE id = $2",
        count,
        jurisdiction_id,
    )


async def _upsert_jurisdiction_legislation(
    conn, jurisdiction_id: UUID, items: List[Dict]
):
    """Write legislation results into the jurisdiction repository."""
    new_keys = set()
    for item in items:
        leg_key = item.get("legislation_key")
        if not leg_key:
            leg_key = _normalize_title_key(item.get("title", ""))
        if not leg_key:
            continue
        new_keys.add(leg_key)

        eff_date = parse_date(item.get("expected_effective_date"))
        confidence = item.get("confidence")
        if confidence is not None:
            confidence = float(confidence)

        await conn.execute(
            """
            INSERT INTO jurisdiction_legislation
                (jurisdiction_id, legislation_key, category, title, description,
                 current_status, expected_effective_date, impact_summary,
                 source_url, source_name, confidence, last_verified_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
            ON CONFLICT (jurisdiction_id, legislation_key) DO UPDATE SET
                category = EXCLUDED.category,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                current_status = EXCLUDED.current_status,
                expected_effective_date = EXCLUDED.expected_effective_date,
                impact_summary = EXCLUDED.impact_summary,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                confidence = EXCLUDED.confidence,
                last_verified_at = NOW(),
                updated_at = NOW()
            """,
            jurisdiction_id,
            leg_key,
            item.get("category"),
            item.get("title"),
            item.get("description"),
            item.get("current_status", "proposed"),
            eff_date,
            item.get("impact_summary"),
            item.get("source_url"),
            item.get("source_name"),
            confidence,
        )

    # Update legislation count
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM jurisdiction_legislation WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    await conn.execute(
        "UPDATE jurisdictions SET legislation_count = $1, updated_at = NOW() WHERE id = $2",
        count,
        jurisdiction_id,
    )


async def _filter_requirements_for_company(
    conn, company_id: UUID, requirements: List[Dict]
) -> List[Dict]:
    """Filter out industry-specific requirements that don't apply to this company."""
    if not any(_requirement_applicable_industries(r) for r in requirements):
        return requirements

    company_tags = await _get_company_industry_tags(conn, company_id)

    filtered = []
    for req in requirements:
        req_industries = _requirement_applicable_industries(req)
        if not req_industries:
            filtered.append(req)  # Generic requirement — always include
        elif not company_tags:
            continue  # Company has no industry — skip industry-specific reqs
        elif req_industries & company_tags:
            filtered.append(req)  # Direct match (set intersection)
    return filtered


async def _refresh_catalog_links(conn, reqs: List[Dict]) -> None:
    """Drop ``jurisdiction_requirement_id`` values the catalog no longer has.

    The in-flight requirement dicts are loaded from the catalog BEFORE the upsert
    runs (``_jurisdiction_row_to_dict`` stamps the id), and the upsert can delete
    or merge rows out from under them. The next call — this sync — then inserts a
    compliance_requirements row FK'd to a dead id and the whole location's sync
    aborts on ``compliance_requirements_jurisdiction_requirement_id_fkey``. That
    is what made a real onboarding build report "your compliance baseline is
    live" while having written only part of it.

    A stale link is dropped to NULL rather than raising: the requirement itself is
    still real and the tenant should see it. The FK is an enrichment link, not the
    row's identity.
    """
    ids = {
        req["jurisdiction_requirement_id"]
        for req in reqs
        if req.get("jurisdiction_requirement_id")
    }
    if not ids:
        return

    live = {
        row["id"]
        for row in await conn.fetch(
            "SELECT id FROM jurisdiction_requirements WHERE id = ANY($1::uuid[])",
            [UUID(str(i)) for i in ids],
        )
    }
    stale = {str(i) for i in ids} - {str(i) for i in live}
    if not stale:
        return

    for req in reqs:
        if str(req.get("jurisdiction_requirement_id") or "") in stale:
            req["jurisdiction_requirement_id"] = None
    logger.warning(
        "compliance: dropped %d stale catalog link(s) before location sync", len(stale)
    )


async def _sync_requirements_to_location(
    conn,
    location_id: UUID,
    company_id: UUID,
    reqs: List[Dict],
    create_alerts: bool = True,
    service=None,
    validate_source_urls: bool = True,
) -> Dict[str, int]:
    """Sync a list of requirement dicts to a location's compliance_requirements.

    Runs the existing change-detection logic (upsert, history snapshot, alerts).
    Returns {"new": N, "updated": N, "alerts": N, "changes_to_verify": [...]}.

    ``validate_source_urls``: HEAD-checks every requirement's source_url for
    liveness (outbound HTTP to gov sites). That's catalog-quality maintenance —
    already done on the two research/write paths (``_upsert_requirements_additive``,
    ``_upsert_jurisdiction_requirements``) when a row is written. Repeating it
    per tenant, per sync, against the SAME urls every other tenant in the
    jurisdiction already validated is pure waste. Defaults True so existing
    callers are unaffected; the catalog-only projection path passes False.
    """
    # ── Data integrity pipeline ──
    for req in reqs:
        _clamp_varchar_fields(req)
        cat = _normalize_category(req.get("category"))
        if cat:
            req["category"] = cat
    if validate_source_urls:
        await _validate_source_urls(reqs)
    await _refresh_catalog_links(conn, reqs)

    new_count = 0
    updated_count = 0
    alert_count = 0

    existing_rows = await conn.fetch(
        "SELECT * FROM compliance_requirements WHERE location_id = $1",
        location_id,
    )
    existing_by_key = {}
    duplicates = []
    for row in existing_rows:
        row_dict = dict(row)
        key = _compute_requirement_key(row_dict)
        normalized_category = _normalize_category(
            row_dict.get("category")
        ) or row_dict.get("category")

        if key and (
            row_dict.get("requirement_key") != key
            or row_dict.get("category") != normalized_category
        ):
            await conn.execute(
                "UPDATE compliance_requirements SET requirement_key = $1, category = $2, updated_at = NOW() WHERE id = $3",
                key,
                normalized_category,
                row_dict["id"],
            )
            row_dict["requirement_key"] = key
            row_dict["category"] = normalized_category

        if not key:
            continue
        current = existing_by_key.get(key)
        if not current:
            existing_by_key[key] = row_dict
        else:
            current_updated = current.get("updated_at")
            row_updated = row_dict.get("updated_at")
            if current_updated and row_updated and row_updated > current_updated:
                duplicates.append(current)
                existing_by_key[key] = row_dict
            else:
                duplicates.append(row_dict)

    for dup in duplicates:
        await _snapshot_to_history(conn, dup, location_id)
        await conn.execute(
            "DELETE FROM compliance_requirements WHERE id = $1", dup["id"]
        )

    # Dismiss orphaned alerts
    await conn.execute(
        """
        UPDATE compliance_alerts SET status = 'dismissed', dismissed_at = NOW()
        WHERE location_id = $1 AND requirement_id IS NULL AND status IN ('unread', 'read')
        """,
        location_id,
    )

    new_requirement_keys = set()
    changes_to_verify = []

    for req in reqs:
        requirement_key = _compute_requirement_key(req)
        new_requirement_keys.add(requirement_key)
        existing = existing_by_key.get(requirement_key)

        # Fallback: match by category when the title-based key differs.
        # Only safe when exactly one unclaimed existing row shares the
        # category — multiple matches means we can't disambiguate and
        # must let the normal new-insert / stale-delete paths handle it.
        if not existing:
            norm_cat = _normalize_category(req.get("category"))
            if norm_cat:
                candidates = [
                    (ekey, erow)
                    for ekey, erow in existing_by_key.items()
                    if ekey.startswith(norm_cat + ":")
                    and ekey not in new_requirement_keys
                ]
                if len(candidates) == 1:
                    ekey, erow = candidates[0]
                    existing = erow
                    new_requirement_keys.add(ekey)  # prevent stale deletion

        if existing:
            old_value = existing.get("current_value")
            new_value = req.get("current_value")
            old_num = existing.get("numeric_value")
            new_num = req.get("numeric_value")
            if old_num is None:
                old_num = _extract_numeric_value(old_value)
            if new_num is None:
                new_num = _extract_numeric_value(new_value)

            # Minimum wages virtually never decrease — reject as likely
            # Gemini hallucination / stale data.  Use `continue` to skip
            # the entire update (including _update_requirement) so the
            # bad rate is never persisted.  The requirement_key is already
            # in new_requirement_keys so it won't be deleted.
            # Reject BEFORE dismissing alerts so existing alerts survive.
            if (
                _normalize_category(req.get("category")) == "minimum_wage"
                and old_num is not None
                and new_num is not None
                and (float(old_num) - float(new_num)) > 0.005
            ):
                print(
                    f"[Compliance] WARNING: Rejecting minimum wage decrease "
                    f"{old_num} → {new_num} for {req.get('jurisdiction_name')}"
                )
                continue

            # Dismiss stale alerts for this requirement (only reached
            # for non-rejected updates)
            await conn.execute(
                "UPDATE compliance_alerts SET status = 'dismissed', dismissed_at = NOW() WHERE requirement_id = $1 AND status IN ('unread', 'read')",
                existing["id"],
            )

            material_change = False
            if _is_material_numeric_change(old_num, new_num, req.get("category")):
                material_change = True
            elif old_num is None or new_num is None:
                # Only fall back to text comparison when we don't have
                # numeric values on both sides — avoids false alerts when
                # Gemini rephrases text but numeric value is unchanged.
                if _is_material_text_change(old_value, new_value, req.get("category")):
                    material_change = True
            # When numerics match for non-wage categories, trust the numeric comparison.
            # Text-only differences (after normalization) are usually just Gemini rephrasing
            # (e.g., "(unpaid)" annotations, word order changes). Don't flag as material.

            numeric_changed = (
                old_num is not None
                and new_num is not None
                and abs(float(old_num) - float(new_num)) > 0.001
            )
            text_changed = old_value != new_value
            metadata_changed = any(
                [
                    existing.get("title") != req.get("title"),
                    existing.get("description") != req.get("description"),
                    existing.get("source_url") != req.get("source_url"),
                    existing.get("source_name") != req.get("source_name"),
                    existing.get("effective_date")
                    != parse_date(req.get("effective_date")),
                    text_changed,
                    numeric_changed,
                ]
            )

            if metadata_changed:
                updated_count += 1
                await _snapshot_to_history(conn, existing, location_id)
                if material_change and create_alerts:
                    changes_to_verify.append(
                        {
                            "req": req,
                            "existing": existing,
                            "old_value": old_value,
                            "new_value": new_value,
                            "requirement_key": requirement_key,
                        }
                    )

            previous_value = existing.get("previous_value")
            last_changed_at = existing.get("last_changed_at")
            if material_change:
                previous_value = old_value
                last_changed_at = datetime.utcnow()
                # Log granular field changes to policy_change_log.
                #
                # requirement_id FKs jurisdiction_requirements (the CATALOG), but
                # `existing` is a compliance_requirements row — the per-location
                # projection. Passing existing["id"] here FK-violated every time,
                # killing the whole check. It stayed invisible because it only
                # fires when a value materially changes, and the sync used to die
                # earlier. An unlinked projection row has no catalog id to log
                # against, so it is skipped rather than faked.
                catalog_id = existing.get("jurisdiction_requirement_id")
                if catalog_id:
                    if old_value != new_value:
                        await _log_policy_change(
                            conn, catalog_id, "current_value",
                            old_value, new_value,
                        )
                    if old_num is not None and new_num is not None and abs(float(old_num) - float(new_num)) > 0.001:
                        await _log_policy_change(
                            conn, catalog_id, "numeric_value",
                            str(old_num), str(new_num),
                        )

            await _update_requirement(
                conn,
                existing["id"],
                requirement_key,
                req,
                previous_value,
                last_changed_at,
            )
            existing_by_key[requirement_key] = {**existing, "id": existing["id"]}
        else:
            # Guard: don't insert a min-wage decrease that bypassed the
            # matched-existing path due to key drift (title changed).
            # Only compare against entries with the SAME rate_type to avoid
            # rejecting legitimate lower variants (tipped, hotel, etc.).
            if _normalize_category(req.get("category")) == "minimum_wage":
                new_num_val = req.get("numeric_value") or _extract_numeric_value(
                    req.get("current_value")
                )
                new_rate_type = req.get("rate_type") or "general"
                if new_num_val is not None:
                    dominated = False
                    for ekey, erow in existing_by_key.items():
                        if not ekey.startswith("minimum_wage:"):
                            continue
                        # Only compare same rate_type (e.g., don't reject tipped $13.80 because general is $16.82)
                        existing_rate_type = erow.get("rate_type") or "general"
                        if existing_rate_type != new_rate_type:
                            continue
                        e_num = erow.get("numeric_value") or _extract_numeric_value(
                            erow.get("current_value")
                        )
                        if (
                            e_num is not None
                            and (float(e_num) - float(new_num_val)) > 0.005
                        ):
                            dominated = True
                            # Preserve old row from stale deletion
                            new_requirement_keys.add(ekey)
                            break
                    if dominated:
                        print(
                            f"[Compliance] WARNING: Rejecting min-wage insert "
                            f"{new_num_val} (lower than existing {e_num}) for "
                            f"{req.get('jurisdiction_name')} rate_type={new_rate_type}"
                        )
                        continue

            new_count += 1
            req_id = await _upsert_requirement(conn, location_id, requirement_key, req)

            if create_alerts:
                alert_count += 1
                await _create_alert(
                    conn,
                    location_id,
                    company_id,
                    req_id,
                    f"New Requirement: {req.get('title')}",
                    req.get("description") or "New compliance requirement identified.",
                    "info",
                    req.get("category"),
                    source_url=req.get("source_url"),
                    source_name=req.get("source_name"),
                    alert_type="new_requirement",
                    skip_email=True,  # bulk — caller sends one summary email
                )
            existing_by_key[requirement_key] = {"id": req_id}

    # Stale requirements cleanup
    stale_keys = set(existing_by_key.keys()) - new_requirement_keys
    for stale_key in stale_keys:
        stale = existing_by_key[stale_key]
        stale_id = stale.get("id")
        if stale_id:
            await _snapshot_to_history(conn, stale, location_id)
            await conn.execute(
                "DELETE FROM compliance_requirements WHERE id = $1", stale_id
            )

    return {
        "new": new_count,
        "updated": updated_count,
        "alerts": alert_count,
        "changes_to_verify": changes_to_verify,
        "existing_by_key": existing_by_key,
    }


async def project_location_from_catalog(
    conn,
    company_id: UUID,
    location_id: UUID,
    *,
    create_alerts: bool = False,
    check_type: str = "manual",
) -> Dict[str, int]:
    """Sync a location's tab from the shared catalog. NO Gemini, structurally.

    This is the tenant "Run check" button and the daily auto-sync's entry point,
    and the guarantee here is stronger than a flag: this function's only calls
    are ``_project_chain_to_location`` (read the catalog chain) and
    ``_sync_requirements_to_location(..., validate_source_urls=False)`` (write the
    projection). Neither imports ``get_gemini_compliance_service``, calls
    ``service.*``, or reaches ``_refresh_repository_missing_categories``. There is
    no code path from here to a Gemini call — not "Gemini is off because a flag
    says so," but "the call simply is not in this function's reachable graph."
    Research-capable checks (``run_compliance_check_stream`` /
    ``run_compliance_check_background``) are a deliberately separate,
    admin/onboarding-only surface.

    ``validate_source_urls=False`` on the sync call: liveness-checking every
    requirement's source_url is catalog-quality maintenance already done when a
    row is researched and written (the two write paths). Every tenant in a
    jurisdiction shares the same catalog rows, so re-validating the same URLs on
    every tenant's own sync is pure waste, not additional safety.

    Writes a ``compliance_check_log`` row and stamps
    ``business_locations.last_compliance_check`` like the full check does, so
    this is a full drop-in for both callers: the History tab shows the sync, and
    the daily dispatcher's ``ORDER BY last_compliance_check ASC NULLS FIRST``
    (``workers/tasks/compliance_checks.py``) still rotates correctly.

    Returns ``{"new": N, "updated": N, "alerts": N}``. Returns all-zero
    (no-op, no log written) if the location has no jurisdiction yet.

    Uses ONLY the passed ``conn`` — never ``get_location`` or any other pool
    accessor. The daily sweep runs in the pool-free Celery worker
    (``celery_app.py`` never calls ``init_pool``), where a pooled
    ``get_connection()`` raises "Database pool not initialized." Every helper
    below already takes ``conn``; this is the one spot that would otherwise reach
    for the pool. Same pattern as ``vertical_coverage.reproject_location``, which
    already runs pool-free in the vertical-coverage sweep worker.
    """
    row = await conn.fetchrow(
        "SELECT * FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    if not row or not row["jurisdiction_id"]:
        return {"new": 0, "updated": 0, "alerts": 0}
    location = BusinessLocation(**dict(row))

    log_id = await _create_check_log(conn, location_id, company_id, check_type)

    requirements = await _project_chain_to_location(
        conn, company_id, location, location.jurisdiction_id
    )
    if not requirements:
        await conn.execute(
            "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
            location_id,
        )
        await _complete_check_log(conn, log_id, 0, 0, 0)
        return {"new": 0, "updated": 0, "alerts": 0}

    sync_result = await _sync_requirements_to_location(
        conn,
        location_id,
        company_id,
        requirements,
        create_alerts=create_alerts,
        validate_source_urls=False,
    )
    await conn.execute(
        "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
        location_id,
    )
    await _complete_check_log(
        conn, log_id, sync_result["new"], sync_result["updated"], sync_result["alerts"]
    )
    return {
        "new": sync_result["new"],
        "updated": sync_result["updated"],
        "alerts": sync_result["alerts"],
    }


def _resolve_regulation_key(raw_key: str, category: str) -> Optional[str]:
    """Validate a Gemini-provided regulation_key against the canonical registry.

    Returns the matched canonical key if found, or None to signal fallback
    to title-based keying. Handles normalization and token-overlap matching
    so Gemini variants like 'california_paid_sick_leave' can resolve to
    'state_paid_sick_leave'.
    """
    from ..compliance_registry import EXPECTED_REGULATION_KEYS

    known_keys = EXPECTED_REGULATION_KEYS.get(category, frozenset())
    norm = _normalize_title_key(raw_key).strip().replace(" ", "_")
    if not norm:
        return None

    # Exact match
    if norm in known_keys:
        return norm

    # No known keys for this category — accept Gemini's key as-is
    if not known_keys:
        return norm

    # Token-overlap match: pick the known key with the highest Jaccard similarity
    norm_tokens = set(norm.split("_"))
    best_key = None
    best_score = 0.0
    for known in known_keys:
        known_tokens = set(known.split("_"))
        intersection = len(norm_tokens & known_tokens)
        union = len(norm_tokens | known_tokens)
        if union == 0:
            continue
        score = intersection / union
        if score > best_score:
            best_score = score
            best_key = known

    # Require >= 50% token overlap to accept the match
    if best_score >= 0.5 and best_key:
        return best_key

    # Gemini invented a key we can't match — accept it as-is so it's still
    # stable across runs (better than title-based), but it won't merge with
    # known keys.
    return norm


def _compute_key_parts(req) -> Tuple[str, Optional[str]]:
    """(composite requirement_key, bare regulation_key in registry vocab). Pure.

    The composite is the ON-CONFLICT identity and is byte-identical to the legacy
    ``_compute_requirement_key`` output. The bare key is the value for the
    ``regulation_key`` column — the store↔scope join key, in registry vocabulary
    (``normalize_key`` maps the minimum_wage rate_type dialect; it is identity for
    every other category, so a resolved regkey passes through unchanged).
    """
    from app.core.services.compliance_evals.keys import normalize_key

    cat = req.get("category") if isinstance(req, dict) else req.category
    title = req.get("title") if isinstance(req, dict) else req.title
    jname = (
        req.get("jurisdiction_name")
        if isinstance(req, dict)
        else getattr(req, "jurisdiction_name", None)
    )
    rate_type = (
        req.get("rate_type")
        if isinstance(req, dict)
        else getattr(req, "rate_type", None)
    )
    jlevel = (
        req.get("jurisdiction_level")
        if isinstance(req, dict)
        else getattr(req, "jurisdiction_level", None)
    )
    country = (
        (req.get("country_code") if isinstance(req, dict) else getattr(req, "country_code", None))
        or "US"
    )
    cat_key = _normalize_category(cat) or ""

    # Include rate_type in key for minimum_wage to allow multiple entries per jurisdiction.
    # This MUST run before the regulation_key path — minimum_wage uses rate_type as the
    # primary discriminator (general vs tipped vs healthcare vs exempt_salary, etc.).
    if cat_key == "minimum_wage":
        normalized_rate_type = (
            _coerce_minimum_wage_rate_type(req)
            if isinstance(req, dict)
            else (_normalize_rate_type(rate_type) or "general")
        )
        # ANTI-POLYMORPHY: the composite (the ON CONFLICT write identity) uses the
        # SAME registry key the column gets — not the rate_type dialect. The catalog
        # spoke two dialects for minimum_wage (keys.py), so a pass keying on
        # rate_type ('minimum_wage:exempt_salary') and one keying on the registry
        # vocabulary ('minimum_wage:exempt_salary_threshold') produced two composites
        # for ONE obligation, both survived ON CONFLICT, and the row forked. Keying
        # both on `bare` collapses the dialects to one identity, so a re-research
        # UPDATEs in place instead of minting a twin.
        bare = normalize_key("minimum_wage", normalized_rate_type, jlevel, country)
        return f"{cat_key}:{bare}", bare

    aet = req.get("applicable_entity_types") if isinstance(req, dict) else getattr(req, "applicable_entity_types", None)
    aet_prefix = f"{aet[0]}:" if aet and isinstance(aet, list) and len(aet) > 0 else ""

    # Prefer Gemini-provided regulation_key when present — but validate it
    # against the known canonical keys. If Gemini invents a key not in the
    # registry, try to match it; if no match, fall back to title-based key.
    reg_key = req.get("regulation_key") if isinstance(req, dict) else getattr(req, "regulation_key", None)
    if reg_key and isinstance(reg_key, str):
        resolved = _resolve_regulation_key(reg_key, cat_key)
        if resolved:
            return f"{aet_prefix}{cat_key}:{resolved}", resolved

    # Fallback: try to match title keywords to a canonical regulation key
    base_title = _base_title(title or "", jname)
    base_key = _normalize_title_key(base_title)

    canonical = _match_title_to_canonical_key(base_key, cat_key)
    if canonical:
        return f"{aet_prefix}{cat_key}:{canonical}", canonical

    # Final fallback: raw normalized title (no canonical match)
    return f"{aet_prefix}{cat_key}:{base_key}", base_key


def _compute_requirement_key(req) -> str:
    return _compute_key_parts(req)[0]


def score_verification_confidence(sources: List[dict]) -> float:
    """Score confidence based on source quality. Pure function."""
    if not sources:
        return 0.0
    score = 0.0
    weights = {"official": 0.5, "news": 0.25, "blog": 0.05, "other": 0.05}
    for source in sources:
        source_type = source.get("type", "other")
        score += weights.get(source_type, 0.05)
    return min(score, 1.0)


async def score_verification_confidence_with_reputation(
    sources: List[dict],
    jurisdiction_id: UUID,
    conn,
) -> float:
    """Score confidence blending type-based scoring (70%) with historical accuracy (30%).

    Phase 3.2: Enhanced confidence scoring that incorporates source reputation.

    Args:
        sources: List of source dicts with 'type' and 'url' fields
        jurisdiction_id: UUID of the jurisdiction for reputation lookup
        conn: Database connection

    Returns:
        Float confidence score between 0.0 and 1.0
    """
    if not sources:
        return 0.0

    # Get base type-based score (existing logic)
    type_score = score_verification_confidence(sources)

    # Extract domains from sources
    domains = []
    for source in sources:
        url = source.get("url", "")
        domain = extract_domain(url)
        if domain:
            domains.append(domain)

    if not domains:
        # No domains to look up, return type-based score only
        return type_score

    # Get historical accuracy for these domains
    reputations = await get_source_reputations(conn, jurisdiction_id, domains)

    if not reputations:
        return type_score

    # Compute weighted average reputation (weight by source type)
    type_weights = {"official": 0.5, "news": 0.25, "blog": 0.1, "other": 0.1}
    total_weight = 0.0
    weighted_reputation = 0.0

    for source in sources:
        url = source.get("url", "")
        domain = extract_domain(url)
        if domain and domain in reputations:
            source_type = source.get("type", "other")
            weight = type_weights.get(source_type, 0.1)
            weighted_reputation += reputations[domain] * weight
            total_weight += weight

    if total_weight == 0:
        return type_score

    avg_reputation = weighted_reputation / total_weight

    # Blend: 70% type-based, 30% historical accuracy
    blended_score = (type_score * 0.7) + (avg_reputation * 0.3)

    return min(blended_score, 1.0)


async def update_source_reputation(
    conn,
    jurisdiction_id: UUID,
    sources: List[dict],
    was_accurate: bool,
):
    """Update accuracy counters for sources based on admin review.

    Phase 3.2: Called when admin marks a verification outcome as correct/incorrect.

    Args:
        conn: Database connection
        jurisdiction_id: UUID of the jurisdiction
        sources: List of source dicts with 'url' field
        was_accurate: True if the sources provided accurate information
    """
    if not sources or not jurisdiction_id:
        return

    for source in sources:
        url = source.get("url", "")
        domain = extract_domain(url)
        if domain:
            await update_source_accuracy(conn, jurisdiction_id, domain, was_accurate)


async def _create_check_log(
    conn, location_id: UUID, company_id: UUID, check_type: str = "manual"
) -> UUID:
    """Create a check log entry and return its ID."""
    return await conn.fetchval(
        """
        INSERT INTO compliance_check_log (location_id, company_id, check_type, status, started_at)
        VALUES ($1, $2, $3, 'running', NOW())
        RETURNING id
        """,
        location_id,
        company_id,
        check_type,
    )


async def _complete_check_log(
    conn,
    log_id: UUID,
    new_count: int,
    updated_count: int,
    alert_count: int,
    error: Optional[str] = None,
):
    """Mark a check log entry as completed or failed."""
    status = "failed" if error else "completed"
    await conn.execute(
        """
        UPDATE compliance_check_log
        SET status = $1, completed_at = NOW(), new_count = $2, updated_count = $3, alert_count = $4, error_message = $5
        WHERE id = $6
        """,
        status,
        new_count,
        updated_count,
        alert_count,
        error,
        log_id,
    )


async def _log_policy_change(
    conn,
    requirement_id: UUID,
    field_changed: str,
    old_value: Optional[str],
    new_value: Optional[str],
    # change_source_enum = (ai_fetch, manual_review, legislative_update,
    # system_migration). The default used to be "compliance_check", which is not
    # a member — so the first time a requirement's value actually CHANGED, the
    # check died with InvalidTextRepresentation. It stayed hidden because the
    # location sync aborted on a dangling FK before it ever got here.
    # A compliance check is an AI fetch.
    change_source: str = "ai_fetch",
    change_reason: Optional[str] = None,
) -> None:
    """Record a granular field-level change in the policy_change_log table."""
    await conn.execute(
        """
        INSERT INTO policy_change_log
            (requirement_id, field_changed, old_value, new_value, change_source, change_reason)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        requirement_id,
        field_changed,
        str(old_value) if old_value is not None else None,
        str(new_value) if new_value is not None else None,
        change_source,
        change_reason,
    )


async def _create_alert(
    conn,
    location_id: UUID,
    company_id: UUID,
    requirement_id: Optional[UUID],
    title: str,
    message: str,
    severity: str,
    category: Optional[str],
    source_url: Optional[str] = None,
    source_name: Optional[str] = None,
    alert_type: str = "change",
    confidence_score: Optional[float] = None,
    verification_sources: Optional[list] = None,
    effective_date: Optional[date] = None,
    metadata: Optional[dict] = None,
    skip_email: bool = False,
) -> UUID:
    """Create a compliance alert with extended fields. Returns alert ID.

    Args:
        skip_email: When True, suppresses per-alert email notification.
            Callers doing bulk operations should set this to True and call
            _send_bulk_alert_email() once after all alerts are created.
    """
    alert_id = await conn.fetchval(
        """
        INSERT INTO compliance_alerts
        (location_id, company_id, requirement_id, title, message, severity, status,
         category, action_required, source_url, source_name,
         alert_type, confidence_score, verification_sources, effective_date, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, 'unread', $7, 'Review new requirement', $8, $9,
                $10, $11, $12::jsonb, $13, $14::jsonb)
        RETURNING id
        """,
        location_id,
        company_id,
        requirement_id,
        title,
        message,
        severity,
        category,
        source_url,
        source_name,
        alert_type,
        confidence_score,
        json.dumps(verification_sources) if verification_sources else None,
        effective_date,
        json.dumps(metadata) if metadata else None,
    )

    if not skip_email:
        await _send_single_alert_email(conn, company_id, location_id)

    return alert_id


async def _send_single_alert_email(
    conn,
    company_id: UUID,
    location_id: UUID,
) -> None:
    """Send a per-alert email for individual (non-bulk) alerts."""
    from ...config import get_settings as _get_settings
    if not _get_settings().compliance_emails_enabled:
        return
    try:
        await _send_alert_email_impl(company_id, location_id, 1)
    except Exception as e:
        print(f"[Compliance] Failed to send single alert email: {e}")


async def _send_bulk_alert_email(
    company_id: UUID,
    location_id: UUID,
    alert_count: int,
) -> None:
    """Send a single summary email for a batch of new compliance alerts.

    Called once after all alerts are created (not per-alert) to avoid spam.
    """
    if alert_count == 0:
        return
    from ...config import get_settings as _get_settings
    if not _get_settings().compliance_emails_enabled:
        return
    try:
        await _send_alert_email_impl(company_id, location_id, alert_count)
    except Exception as e:
        print(f"[Compliance] Failed to send bulk alert email for {alert_count} alerts: {e}")


async def _send_alert_email_impl(
    company_id: UUID,
    location_id: UUID,
    alert_count: int,
) -> None:
    """Shared implementation for alert emails (single or bulk)."""
    from .email import get_email_service

    email_service = get_email_service()
    if not email_service.is_configured():
        return

    company_name, contacts = await _get_company_admin_contacts(company_id)
    if not contacts:
        return

    from ...database import get_connection
    async with get_connection() as conn:
        location_row = await conn.fetchrow(
            "SELECT name, city, state FROM business_locations WHERE id = $1",
            location_id,
        )
    location_name = (
        (location_row["name"] or f"{location_row['city']}, {location_row['state']}")
        if location_row else "your location"
    )

    send_tasks = [
        email_service.send_compliance_change_notification_email(
            to_email=contact["email"],
            to_name=contact.get("name"),
            company_name=company_name,
            location_name=location_name,
            changed_requirements_count=alert_count,
            jurisdictions=None,
        )
        for contact in contacts
    ]
    await asyncio.gather(*send_tasks, return_exceptions=True)


def _record_change_notification_item(
    change_items: List[Dict[str, str]],
    req: dict,
    change_info: dict,
):
    """Capture lightweight change details for post-check admin email notifications."""
    print(
        f"[Compliance] MATERIAL CHANGE: {req.get('title')} | "
        f"{change_info.get('old_value')} → {change_info.get('new_value')}"
    )
    change_items.append(
        {
            "title": req.get("title") or "",
            "jurisdiction_name": req.get("jurisdiction_name") or "",
            "old_value": str(change_info.get("old_value") or ""),
            "new_value": str(change_info.get("new_value") or ""),
        }
    )


async def _get_company_admin_contacts(
    company_id: UUID,
) -> tuple[str, List[Dict[str, str]]]:
    """Get company name and business admin/client email contacts."""
    from ...database import get_connection

    async with get_connection() as conn:
        company_name = (
            await conn.fetchval(
                "SELECT name FROM companies WHERE id = $1",
                company_id,
            )
            or "Your company"
        )

        rows = await conn.fetch(
            """
            SELECT DISTINCT
                u.email,
                COALESCE(NULLIF(c.name, ''), split_part(u.email, '@', 1)) AS name
            FROM clients c
            JOIN users u ON u.id = c.user_id
            WHERE c.company_id = $1
              AND u.is_active = true
              AND u.email IS NOT NULL
            ORDER BY u.email
            """,
            company_id,
        )

    contacts = [
        {"email": row["email"], "name": row["name"] or row["email"]} for row in rows
    ]
    return company_name, contacts


async def _notify_company_admins_of_compliance_changes(
    company_id: UUID,
    location: BusinessLocation,
    change_items: List[Dict[str, str]],
) -> int:
    """
    Send one general compliance-change email per business admin for this check run.
    Returns count of successful sends.
    """
    if not change_items:
        return 0

    from .email import get_email_service

    # Deduplicate repeated writes of the same change during a run.
    unique_changes = {
        (
            (item.get("title") or "").strip(),
            (item.get("jurisdiction_name") or "").strip(),
            (item.get("old_value") or "").strip(),
            (item.get("new_value") or "").strip(),
        )
        for item in change_items
    }
    change_count = len(unique_changes)
    if change_count == 0:
        return 0

    email_service = get_email_service()
    if not email_service.is_configured():
        print(
            "[Compliance] Email service not configured, skipping admin change notifications"
        )
        return 0

    company_name, contacts = await _get_company_admin_contacts(company_id)
    if not contacts:
        print(f"[Compliance] No business admin contacts found for company {company_id}")
        return 0

    jurisdictions = sorted(
        {jurisdiction for _, jurisdiction, _, _ in unique_changes if jurisdiction}
    )
    location_name = location.name or f"{location.city}, {location.state}"

    tasks = [
        email_service.send_compliance_change_notification_email(
            to_email=contact["email"],
            to_name=contact.get("name"),
            company_name=company_name,
            location_name=location_name,
            changed_requirements_count=change_count,
            jurisdictions=jurisdictions,
        )
        for contact in contacts
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    sent_count = 0
    for contact, result in zip(contacts, results):
        if isinstance(result, Exception):
            print(
                f"[Compliance] Failed to send change notification to {contact['email']}: {result}"
            )
            continue
        if result:
            sent_count += 1

    if sent_count:
        print(
            f"[Compliance] Sent compliance change notifications to {sent_count}/{len(contacts)} admin(s)"
        )

    return sent_count


async def _log_verification_outcome(
    conn,
    jurisdiction_id: Optional[UUID],
    alert_id: Optional[UUID],
    requirement_key: str,
    category: Optional[str],
    predicted_confidence: float,
    predicted_is_change: bool,
    verification_sources: Optional[list] = None,
) -> int:
    """Log a verification outcome for confidence calibration analysis.

    Returns the ID of the created record.
    """
    return await conn.fetchval(
        """
        INSERT INTO verification_outcomes
        (jurisdiction_id, alert_id, requirement_key, category,
         predicted_confidence, predicted_is_change, verification_sources)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING id
        """,
        jurisdiction_id,
        alert_id,
        requirement_key,
        category,
        round(predicted_confidence, 2),
        predicted_is_change,
        json.dumps(verification_sources) if verification_sources else None,
    )


async def _upsert_requirement(
    conn, location_id: UUID, requirement_key: str, req: dict
) -> UUID:
    """Insert a new compliance requirement. Returns the new ID.

    ON CONFLICT on the (location_id, jurisdiction_requirement_id) partial unique
    index merges into the existing catalog-linked row instead of erroring. This
    matters because the scan's requirement_key (_compute_requirement_key) can
    differ from the projector's simple key for the same catalog requirement, so a
    key-miss could otherwise try to insert a second row for a jr already projected
    by the wizard at this location. Null-FK (Gemini-fresh) rows don't match the
    partial index, so they insert normally (string-key dedup as before).
    """
    return await conn.fetchval(
        """
        INSERT INTO compliance_requirements
        (location_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name, title, description,
         current_value, numeric_value, source_url, source_name, effective_date, applicable_industries,
         jurisdiction_requirement_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        ON CONFLICT (location_id, jurisdiction_requirement_id)
            WHERE jurisdiction_requirement_id IS NOT NULL
        DO UPDATE SET
            requirement_key = EXCLUDED.requirement_key,
            category = EXCLUDED.category,
            rate_type = EXCLUDED.rate_type,
            jurisdiction_level = EXCLUDED.jurisdiction_level,
            jurisdiction_name = EXCLUDED.jurisdiction_name,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            current_value = EXCLUDED.current_value,
            numeric_value = EXCLUDED.numeric_value,
            source_url = EXCLUDED.source_url,
            source_name = EXCLUDED.source_name,
            effective_date = EXCLUDED.effective_date,
            applicable_industries = EXCLUDED.applicable_industries,
            updated_at = NOW()
        RETURNING id
        """,
        location_id,
        requirement_key,
        req.get("category"),
        req.get("rate_type"),
        req.get("jurisdiction_level"),
        req.get("jurisdiction_name"),
        req.get("title"),
        req.get("description"),
        req.get("current_value"),
        req.get("numeric_value"),
        req.get("source_url"),
        req.get("source_name"),
        parse_date(req.get("effective_date")),
        req.get("applicable_industries"),
        req.get("jurisdiction_requirement_id"),  # SSOT link; null for Gemini-fresh rows
    )


async def _update_requirement(
    conn,
    existing_id: UUID,
    requirement_key: str,
    req: dict,
    previous_value: Optional[str],
    last_changed_at: Optional[datetime],
):
    """Update an existing compliance requirement.

    Deliberately does NOT touch jurisdiction_requirement_id: this row was matched
    by requirement_key, and COALESCE-filling the FK here could collide with a
    different row at the same location that already holds that FK (e.g. a wizard
    projection), violating the (location_id, jurisdiction_requirement_id) unique
    index mid-scan. Go-forward rows get the FK stamped at INSERT time
    (_upsert_requirement); legacy null-FK rows keep string-key dedup.
    """
    await conn.execute(
        """
        UPDATE compliance_requirements
        SET requirement_key = $1, category = $2, rate_type = $3, jurisdiction_name = $4, title = $5,
            current_value = $6, numeric_value = $7, previous_value = $8, last_changed_at = $9,
            description = $10, source_url = $11, source_name = $12, effective_date = $13,
            applicable_industries = $14, updated_at = NOW()
        WHERE id = $15
        """,
        requirement_key,
        req.get("category"),
        req.get("rate_type"),
        req.get("jurisdiction_name"),
        req.get("title"),
        req.get("current_value"),
        req.get("numeric_value"),
        # previous_value is varchar(100) but holds a copy of current_value
        # (varchar 500) — clamp, same overflow as the catalog ON-CONFLICT paths.
        previous_value[:100] if previous_value else previous_value,
        last_changed_at,
        req.get("description"),
        req.get("source_url"),
        req.get("source_name"),
        parse_date(req.get("effective_date")),
        req.get("applicable_industries"),
        existing_id,
    )


async def _snapshot_to_history(conn, row_dict: dict, location_id: UUID):
    """Insert a snapshot of a requirement into the history table."""
    await conn.execute(
        """
        INSERT INTO compliance_requirement_history
        (requirement_id, location_id, category, rate_type, jurisdiction_level, jurisdiction_name,
         title, description, current_value, numeric_value, source_url, source_name, effective_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """,
        row_dict["id"],
        location_id,
        row_dict.get("category"),
        row_dict.get("rate_type"),
        row_dict.get("jurisdiction_level"),
        row_dict.get("jurisdiction_name"),
        row_dict.get("title"),
        row_dict.get("description"),
        row_dict.get("current_value"),
        row_dict.get("numeric_value"),
        row_dict.get("source_url"),
        row_dict.get("source_name"),
        row_dict.get("effective_date"),
    )


async def process_upcoming_legislation(
    conn, location_id: UUID, company_id: UUID, legislation_items: List[Dict]
) -> int:
    """Process upcoming legislation results from Gemini. Returns count of new/updated items."""
    count = 0
    for item in legislation_items:
        leg_key = item.get("legislation_key")
        if not leg_key:
            leg_key = _normalize_title_key(item.get("title", ""))
        if not leg_key:
            continue

        existing = await conn.fetchrow(
            "SELECT * FROM upcoming_legislation WHERE location_id = $1 AND legislation_key = $2",
            location_id,
            leg_key,
        )

        eff_date = parse_date(item.get("expected_effective_date"))
        confidence = item.get("confidence")
        if confidence is not None:
            confidence = float(confidence)

        normalized_status = _normalize_legislation_status(
            item.get(
                "current_status", existing["current_status"] if existing else None
            ),
            eff_date,
        )

        if existing:
            await conn.execute(
                """
                UPDATE upcoming_legislation
                SET current_status = $1, expected_effective_date = $2, impact_summary = $3,
                    source_url = $4, source_name = $5, confidence = $6, description = $7,
                    updated_at = NOW()
                WHERE id = $8
                """,
                normalized_status,
                eff_date,
                item.get("impact_summary"),
                item.get("source_url"),
                item.get("source_name"),
                confidence,
                item.get("description"),
                existing["id"],
            )
        else:
            alert_id = await _create_alert(
                conn,
                location_id,
                company_id,
                None,
                f"Upcoming: {item.get('title', 'Unknown')}",
                item.get("impact_summary")
                or item.get("description")
                or "New legislation detected.",
                "info",
                item.get("category"),
                source_url=item.get("source_url"),
                source_name=item.get("source_name"),
                alert_type="upcoming_legislation",
                confidence_score=confidence,
                effective_date=eff_date,
            )
            await conn.execute(
                """
                INSERT INTO upcoming_legislation
                (location_id, company_id, category, title, description, current_status,
                 expected_effective_date, impact_summary, source_url, source_name,
                 confidence, legislation_key, alert_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                location_id,
                company_id,
                item.get("category"),
                item.get("title"),
                item.get("description"),
                normalized_status,
                eff_date,
                item.get("impact_summary"),
                item.get("source_url"),
                item.get("source_name"),
                confidence,
                leg_key,
                alert_id,
            )
            count += 1

    return count


async def escalate_upcoming_deadlines(conn, company_id: UUID) -> int:
    """Re-evaluate deadline severity for upcoming legislation. No Gemini calls."""
    rows = await conn.fetch(
        """
        SELECT ul.*, ca.id as alert_id, ca.severity as alert_severity, ca.status as alert_status
        FROM upcoming_legislation ul
        LEFT JOIN compliance_alerts ca ON ul.alert_id = ca.id
        WHERE ul.company_id = $1
          AND ul.current_status NOT IN ('effective', 'dismissed')
          AND ul.expected_effective_date IS NOT NULL
        """,
        company_id,
    )

    escalated = 0
    now = datetime.utcnow().date()
    for row in rows:
        eff_date = row["expected_effective_date"]
        days_remaining = (eff_date - now).days

        if days_remaining <= 0:
            new_severity = "critical"
            new_status = "effective"
        elif days_remaining <= 30:
            new_severity = "critical"
            new_status = row["current_status"]
        elif days_remaining <= 90:
            new_severity = "warning"
            new_status = row["current_status"]
        else:
            new_severity = "info"
            new_status = row["current_status"]

        # Update legislation status if nearing effective date
        if new_status != row["current_status"]:
            await conn.execute(
                "UPDATE upcoming_legislation SET current_status = $1, updated_at = NOW() WHERE id = $2",
                new_status,
                row["id"],
            )

        # Escalate alert severity if needed
        alert_id = row["alert_id"]
        if alert_id and row["alert_severity"] != new_severity:
            old_severity_rank = {"info": 0, "warning": 1, "critical": 2}.get(
                row["alert_severity"], 0
            )
            new_severity_rank = {"info": 0, "warning": 1, "critical": 2}.get(
                new_severity, 0
            )

            if new_severity_rank > old_severity_rank:
                await conn.execute(
                    "UPDATE compliance_alerts SET severity = $1 WHERE id = $2",
                    new_severity,
                    alert_id,
                )
                # Re-open dismissed alerts if severity escalates
                if row["alert_status"] == "dismissed":
                    await conn.execute(
                        "UPDATE compliance_alerts SET status = 'unread', dismissed_at = NULL WHERE id = $1",
                        alert_id,
                    )
                escalated += 1

    return escalated


def _filter_by_jurisdiction_priority(requirements):
    """For each distinct requirement key, keep only the most local jurisdiction.

    For minimum_wage, requirements are grouped by rate_type (general, tipped, etc.)
    allowing multiple wage entries per jurisdiction when they have different rate types.

    For other categories, titles are compared after stripping jurisdiction-name prefixes
    so that e.g. "California Overtime" (state) and "San Francisco Overtime" (city)
    are recognized as the same rule, while genuinely different requirements
    (e.g. separate meal / rest break entries) within one category are preserved.
    """
    by_key = {}

    for req in requirements:
        cat = req["category"] if isinstance(req, dict) else req.category
        rate_type = (
            req.get("rate_type")
            if isinstance(req, dict)
            else getattr(req, "rate_type", None)
        )
        cat_key = _normalize_category(cat)

        # For minimum_wage, group by rate_type to allow multiple entries
        if cat_key == "minimum_wage":
            key = ("minimum_wage", rate_type or "general")
        else:
            # For other categories, use existing logic based on title
            title = req["title"] if isinstance(req, dict) else req.title
            jname = (
                req["jurisdiction_name"]
                if isinstance(req, dict)
                else getattr(req, "jurisdiction_name", None)
            )
            base = _base_title(title, jname)
            base_key = _normalize_title_key(base)
            key = (cat_key, base_key)

        by_key.setdefault(key, []).append(req)

    # For each key, keep the most local jurisdiction
    filtered = []
    for reqs in by_key.values():
        best = _pick_best_by_priority(reqs)
        if best:
            filtered.append(best)

    return filtered


async def _filter_with_preemption(conn, requirements, state: Optional[str]):
    """Preemption-aware jurisdiction filter.

    For each category group:
    1. Check state_preemption_rules to see if local override is allowed.
    2. If preempted: keep only state-level requirements.
    3. If allowed (or no rule): apply most-beneficial-to-employee for wage
       categories, or most-local for others (existing behavior).
    """
    # A location with no state (10 live rows on dev) reached `state.upper()` and
    # 500'd the whole compliance page. Preemption is a state-law question — with
    # no state there is no rule to apply, so pass the requirements through
    # unfiltered rather than taking the tenant's page down.
    if not state:
        logger.warning(
            "preemption skipped: location has no state — returning requirements unfiltered"
        )
        return requirements

    norm_state = state.upper().strip()
    state_name = _CODE_TO_STATE_NAME.get(norm_state, norm_state)

    # Load all preemption rules for this state in one query
    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            norm_state,
        )
        preemption_map = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_map = {}

    # Group requirements the same way as _filter_by_jurisdiction_priority
    by_key = {}
    for req in requirements:
        cat = req["category"] if isinstance(req, dict) else req.category
        rate_type = (
            req.get("rate_type")
            if isinstance(req, dict)
            else getattr(req, "rate_type", None)
        )
        cat_key = _normalize_category(cat)

        if cat_key == "minimum_wage":
            key = ("minimum_wage", rate_type or "general")
        else:
            title = req["title"] if isinstance(req, dict) else req.title
            jname = (
                req["jurisdiction_name"]
                if isinstance(req, dict)
                else getattr(req, "jurisdiction_name", None)
            )
            base = _base_title(title, jname)
            base_key = _normalize_title_key(base)
            key = (cat_key, base_key)

        by_key.setdefault(key, []).append(req)

    filtered = []
    for key, reqs in by_key.items():
        category = key[0]
        allows_local = preemption_map.get(category)

        if allows_local is False:
            # State preempts local: only keep state-level requirements
            state_reqs = [
                r
                for r in reqs
                if (
                    r["jurisdiction_level"]
                    if isinstance(r, dict)
                    else r.jurisdiction_level
                )
                == "state"
            ]
            if state_reqs:
                best = _pick_best_by_priority(state_reqs)
                if best:
                    filtered.append(best)
            else:
                # If preempted categories only have local-level rows, treat this as
                # a labeling issue from research and promote the strongest row to state.
                fallback = _pick_best_by_priority(reqs)
                if fallback:
                    original_level = (
                        fallback["jurisdiction_level"]
                        if isinstance(fallback, dict)
                        else getattr(fallback, "jurisdiction_level", None)
                    )
                    if isinstance(fallback, dict):
                        fallback["jurisdiction_level"] = "state"
                        fallback["jurisdiction_name"] = state_name
                        fallback["promoted_from_level"] = original_level
                        fallback["promotion_reason"] = "state_preemption_no_state_row"
                    else:
                        fallback.jurisdiction_level = "state"
                        fallback.jurisdiction_name = state_name
                        fallback.promoted_from_level = original_level
                        fallback.promotion_reason = "state_preemption_no_state_row"
                    filtered.append(fallback)
                    logger.warning(
                        "Category '%s' is preempted in %s but had no state-level "
                        "requirement — promoting local fallback (from '%s') to state.",
                        category, norm_state, original_level,
                    )
            continue

        # Not preempted (allows_local is True or None/unknown)
        # For wage categories: most-beneficial-to-employee (highest numeric value)
        if category == "minimum_wage":
            # Among all jurisdiction levels, pick the one with the highest rate
            reqs_with_num = [(r, _get_numeric_from_req(r)) for r in reqs]
            reqs_with_num_valid = [
                pair for pair in reqs_with_num if pair[1] is not None
            ]
            if reqs_with_num_valid:
                best = max(reqs_with_num_valid, key=lambda x: x[1])[0]
            else:
                best = _pick_best_by_priority(reqs)
            if best:
                filtered.append(best)
        else:
            # Non-wage: most local wins (existing behavior)
            best = _pick_best_by_priority(reqs)
            if best:
                filtered.append(best)

    return filtered


async def ensure_location_for_employee(
    conn,
    company_id: UUID,
    work_city: Optional[str],
    work_state: str,
    background_tasks=None,
    work_zip: Optional[str] = None,
) -> Optional[UUID]:
    """Find or create a business_location for an employee's work address.

    Used during employee create/update to auto-derive compliance locations from
    employee addresses.  Works within the caller's connection (no
    ``get_connection()`` call).

    Returns the ``location_id`` (UUID) or None if ``work_state`` is falsy.
    """
    if not work_state:
        return None

    norm_state = work_state.upper().strip()
    norm_city = _normalize_city_key(work_city) if work_city else None

    # 1. Look for existing location matching (company_id, city, state)
    if norm_city:
        existing = await conn.fetchrow(
            """
            SELECT id, is_active FROM business_locations
            WHERE company_id = $1 AND LOWER(city) = $2 AND UPPER(state) = $3
            """,
            company_id, norm_city, norm_state,
        )
    else:
        # State-only: match locations with empty/null city
        existing = await conn.fetchrow(
            """
            SELECT id, is_active FROM business_locations
            WHERE company_id = $1 AND (city IS NULL OR city = '') AND UPPER(state) = $2
            """,
            company_id, norm_state,
        )

    # 2. Found + active → return id
    if existing and existing["is_active"]:
        return existing["id"]

    # 3. Found + inactive → reactivate
    if existing and not existing["is_active"]:
        await conn.execute(
            "UPDATE business_locations SET is_active = true, updated_at = NOW() WHERE id = $1",
            existing["id"],
        )
        return existing["id"]

    # 4. Not found → create
    # 4a. Check jurisdiction_reference for known jurisdiction
    is_known_jurisdiction = False
    ref_county = None
    if norm_city:
        resolved_city, ref_county = await _resolve_reference_city(conn, norm_city, norm_state)
        # Check if city was actually found in jurisdiction_reference
        # (vs. just returned as-is from _resolve_reference_city)
        try:
            ref_row = await conn.fetchrow(
                """
                SELECT city, county
                FROM jurisdiction_reference
                WHERE state = $2
                  AND (
                    city = $1
                    OR EXISTS (
                      SELECT 1
                      FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS alias
                      WHERE LOWER(alias) = $1
                    )
                  )
                LIMIT 1
                """,
                _normalize_city_key(norm_city),
                norm_state,
            )
            is_known_jurisdiction = ref_row is not None
            if ref_row and ref_row["county"]:
                ref_county = ref_row["county"]
        except asyncpg.UndefinedTableError:
            is_known_jurisdiction = False
    else:
        # State-only: always considered known (states are always covered)
        resolved_city = ""
        is_known_jurisdiction = True

    # Fall back to zip→county lookup if city-based resolution didn't find a county
    if not ref_county and work_zip:
        ref_county = await _resolve_county_from_zip(conn, work_zip, norm_state)

    # Determine source and coverage
    source = "employee_derived"
    coverage_status = "covered" if is_known_jurisdiction else "pending_review"
    display_city = work_city.strip() if work_city else ""

    # Insert the new location
    norm_zip = work_zip.strip() if work_zip else ""
    location_id = await conn.fetchval(
        """
        INSERT INTO business_locations
            (company_id, name, address, city, state, county, zipcode, source, coverage_status)
        VALUES ($1, $2, '', $3, $4, $5, $6, $7, $8)
        ON CONFLICT (company_id, LOWER(city), UPPER(state)) WHERE source = 'employee_derived' DO UPDATE
            SET is_active = true, updated_at = NOW(),
                zipcode = CASE WHEN business_locations.zipcode = '' OR business_locations.zipcode IS NULL
                               THEN EXCLUDED.zipcode ELSE business_locations.zipcode END
        RETURNING id
        """,
        company_id,
        f"{display_city}, {norm_state}" if display_city else norm_state,
        display_city,
        norm_state,
        ref_county,
        norm_zip,
        source,
        coverage_status,
    )

    # Resolve jurisdiction and link
    jurisdiction_id = await _get_or_create_jurisdiction(
        conn, display_city or norm_state, work_state, ref_county
    )
    await conn.execute(
        "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
        jurisdiction_id, location_id,
    )

    if is_known_jurisdiction:
        # 4b. Known jurisdiction → clone repository data + trigger compliance check
        has_local_ordinance = await _lookup_has_local_ordinance(conn, display_city, norm_state)
        j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
        req_dicts = None

        if j_reqs:
            req_dicts = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
            await _fill_missing_categories_from_parents(conn, jurisdiction_id, req_dicts, 7)
        elif not has_local_ordinance:
            # has_local_ordinance is False or None — try county/state fallback
            county_reqs = await _try_load_county_requirements(conn, jurisdiction_id, 7)
            if county_reqs:
                req_dicts = county_reqs
            else:
                state_reqs = await _try_load_state_requirements(conn, jurisdiction_id, 7)
                if state_reqs:
                    req_dicts = state_reqs
            if req_dicts:
                await _fill_missing_categories_from_parents(conn, jurisdiction_id, req_dicts, 7)

        if req_dicts:
            if not has_local_ordinance and display_city:
                req_dicts = _filter_city_level_requirements(req_dicts, norm_state)
            _normalize_requirement_categories(req_dicts)
            req_dicts = await _filter_requirements_for_company(conn, company_id, req_dicts)
            req_dicts = await _filter_with_preemption(conn, req_dicts, norm_state)
            for req in req_dicts:
                _clamp_varchar_fields(req)
            await _sync_requirements_to_location(
                conn, location_id, company_id, req_dicts, create_alerts=False,
            )

        if background_tasks is not None:
            async def _safe_compliance_bg(lid=location_id, cid=company_id):
                try:
                    await run_compliance_check_background(
                        lid, cid, check_type="auto_derive", allow_live_research=True,
                    )
                except Exception:
                    import traceback
                    print(f"[Compliance] Background compliance check failed for location {lid}: {traceback.format_exc()}")
            background_tasks.add_task(_safe_compliance_bg)
    else:
        # 4c. Unknown jurisdiction → queue for admin review, do NOT trigger check
        await conn.execute(
            """
            INSERT INTO jurisdiction_coverage_requests
                (city, state, county, requested_by_company_id, location_id, status)
            VALUES ($1, $2, $3, $4, $5, 'pending')
            ON CONFLICT (city, state) DO UPDATE
                SET location_id = COALESCE(jurisdiction_coverage_requests.location_id, EXCLUDED.location_id)
            """,
            display_city, norm_state, ref_county, company_id, location_id,
        )

    return location_id


async def create_location(company_id: UUID, data: LocationCreate) -> tuple:
    """Create a location, map it to a jurisdiction, and clone repository data if available.

    Returns (location, has_complete_repository_coverage) — callers should skip
    initial background research only when required labor categories are fully covered.
    """
    from ...database import get_connection

    async with get_connection() as conn:
        fa_json = json.dumps(data.facility_attributes) if data.facility_attributes else None
        location_id = await conn.fetchval(
            """
            INSERT INTO business_locations (company_id, name, address, city, state, county, zipcode, facility_attributes,
                                            ein, naics, max_employees, annual_avg_employees)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            company_id,
            data.name,
            data.address,
            data.city,
            data.state.upper(),
            data.county,
            data.zipcode or "",
            fa_json,
            data.ein,
            data.naics,
            data.max_employees,
            data.annual_avg_employees,
        )

        # Resolve county from zip if not provided
        resolved_county = data.county
        if not resolved_county and data.zipcode:
            resolved_county = await _resolve_county_from_zip(conn, data.zipcode, data.state)
            if resolved_county:
                await conn.execute(
                    "UPDATE business_locations SET county = $1 WHERE id = $2",
                    resolved_county, location_id,
                )

        # Map to jurisdiction
        jurisdiction_id = await _get_or_create_jurisdiction(
            conn, data.city, data.state, resolved_county
        )
        await conn.execute(
            "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
            jurisdiction_id,
            location_id,
        )

        has_local_ordinance = await _lookup_has_local_ordinance(
            conn, data.city, data.state
        )

        # Check if jurisdiction already has requirements in the repository
        j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
        has_repository_rows = len(j_reqs) > 0
        has_complete_repository_coverage = False

        # Try county data for cities without local ordinance (or unknown)
        req_dicts = None
        if has_repository_rows:
            req_dicts = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
            await _fill_missing_categories_from_parents(
                conn, jurisdiction_id, req_dicts, 7
            )
        else:
            if not has_local_ordinance:
                county_reqs = await _try_load_county_requirements(
                    conn, jurisdiction_id, 7
                )
                if county_reqs:
                    req_dicts = county_reqs
                else:
                    state_reqs = await _try_load_state_requirements(
                        conn, jurisdiction_id, 7
                    )
                    if state_reqs:
                        req_dicts = state_reqs

                # If we loaded from county or state, fill any remaining gaps from parents
                if req_dicts:
                    await _fill_missing_categories_from_parents(
                        conn, jurisdiction_id, req_dicts, 7
                    )

        if req_dicts:
            # Normalize and filter (with preemption awareness) before cloning.
            # This keeps create-location behavior consistent with the main
            # compliance check pipeline.
            if not has_local_ordinance:
                req_dicts = _filter_city_level_requirements(req_dicts, data.state)
            _normalize_requirement_categories(req_dicts)
            req_dicts = await _filter_requirements_for_company(conn, company_id, req_dicts)
            req_dicts = await _filter_with_preemption(conn, req_dicts, data.state)
            for req in req_dicts:
                _clamp_varchar_fields(req)
            missing_categories = _missing_required_categories(req_dicts)
            has_complete_repository_coverage = len(missing_categories) == 0
            if missing_categories:
                print(
                    "[Compliance] create_location: repository has partial coverage "
                    f"for {data.city}, {data.state}: {', '.join(missing_categories)}"
                )

        if req_dicts:
            # Clone requirements to location — no alerts for initial clone
            await _sync_requirements_to_location(
                conn,
                location_id,
                company_id,
                req_dicts,
                create_alerts=False,
            )

            # Clone legislation to location
            j_legs = await _load_jurisdiction_legislation(conn, jurisdiction_id)
            for item in j_legs:
                leg_key = item["legislation_key"]
                eff_date = item.get("expected_effective_date")
                confidence = (
                    float(item["confidence"])
                    if item.get("confidence") is not None
                    else None
                )
                await conn.execute(
                    """
                    INSERT INTO upcoming_legislation
                    (location_id, company_id, category, title, description, current_status,
                     expected_effective_date, impact_summary, source_url, source_name,
                     confidence, legislation_key)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (location_id, legislation_key) WHERE legislation_key IS NOT NULL DO NOTHING
                    """,
                    location_id,
                    company_id,
                    item.get("category"),
                    item["title"],
                    item.get("description"),
                    item.get("current_status", "proposed"),
                    eff_date,
                    item.get("impact_summary"),
                    item.get("source_url"),
                    item.get("source_name"),
                    confidence,
                    leg_key,
                )

            if has_complete_repository_coverage:
                # Mark as already checked only when core categories are fully covered.
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )

        row = await conn.fetchrow(
            "SELECT * FROM business_locations WHERE id = $1", location_id
        )
        location = BusinessLocation(**dict(row))
        return location, has_complete_repository_coverage


async def run_compliance_check_stream(
    location_id: UUID,
    company_id: UUID,
    allow_live_research: bool = True,
    categories: Optional[List[str]] = None,
    include_vertical_fill: bool = False,
    allow_repository_refresh: bool = True,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs a compliance check for a specific location.
    Checks the jurisdiction repository first; only calls Gemini if stale/missing.

    ``include_vertical_fill``: after the check, research any industry-specific
    (vertical) compliance the shared catalog is still missing for this company —
    dental law for a dental office, hospitality law for a hotel.

    OFF by default, and that default is load-bearing. This generator has five
    callers: the tenant "Run check" route, the Matcha-X onboarding build's
    per-location loop, the roster-jurisdiction union, and two admin onboarding
    flows. An unconditional fill would fire three times in a single Matcha-X build
    (which already runs its own vertical phase, with the reproject-on-mint logic
    this level has no caller context for) and would silently add Gemini spend to
    the admin white-glove flows. Only the tenant-facing "Run check" opts in.
    Yields progress dicts as SSE-friendly events.

    ``categories`` optionally narrows the "required" set this run cares about
    (e.g. the Matcha-X self-serve onboarding finale passes
    ``MATCHA_X_LITE_CATEGORIES`` for a faster, cheaper basic-law sweep). When
    None — every existing caller — behaviour is identical to before.

    ``allow_repository_refresh``: ``allow_live_research=False`` was meant to mean
    "no Gemini, ever" for the tenant-facing route, but it only gated the
    per-company Tier-3 research block. The shared-jurisdiction gap-fill branch
    (search the catalog on miss, store forever) ran regardless — a "read-only"
    caller could still trigger a live research call. This flag closes that:
    False means the run is a pure projection from whatever the catalog already
    has, with zero Gemini calls, full stop. Defaults True so every existing
    caller (admin, onboarding) is unaffected; only the tenant route passes False.
    """
    from ...database import get_connection
    from .gemini_compliance import get_gemini_compliance_service

    # ── Matcha-X lite scope ────────────────────────────────────────────────
    # When the caller passes a reduced ``categories`` set, shadow the
    # module-level ``_missing_required_categories`` with a local that treats
    # those as the required set. Every internal call below (which drives what
    # Tier-3 Gemini research fetches) then narrows automatically — no call-site
    # edits. With categories=None this shadow is identical to the module helper,
    # so the full (Pro) compliance check is byte-for-byte unaffected.
    _required_override = set(categories) if categories else None

    def _missing_required_categories(requirements: list[dict]) -> list[str]:
        present = {
            _normalize_category((req or {}).get("category"))
            for req in requirements
            if isinstance(req, dict) and (req or {}).get("category")
        }
        required = (
            _required_override
            if _required_override is not None
            else REQUIRED_LABOR_CATEGORIES
        )
        return sorted(cat for cat in required if cat not in present)

    location = await get_location(location_id, company_id)
    if not location:
        yield {"type": "error", "message": "Location not found"}
        return

    location_name = location.name or f"{location.city}, {location.state}"
    yield {"type": "started", "location": location_name}

    service = get_gemini_compliance_service()
    used_repository = False
    change_email_items: List[Dict[str, str]] = []
    requirements: List[Dict[str, Any]] = []
    cached_requirements_for_merge: List[Dict[str, Any]] = []
    research_categories: Optional[List[str]] = None
    industry_context: str = ""
    source_context: str = ""
    corrections_context: str = ""
    preemption_rules: Dict[str, bool] = {}
    new_count = 0
    updated_count = 0
    alert_count = 0

    async with get_connection() as conn:
        # Load industry profile for industry-aware research prompts
        industry_profile = await _get_industry_profile(conn, company_id)
        if industry_profile:
            industry_context = industry_profile.get("industry_context", "")

        log_id = await _create_check_log(conn, location_id, company_id, "manual")

        try:
            # Resolve jurisdiction
            jurisdiction_id = location.jurisdiction_id
            if not jurisdiction_id:
                jurisdiction_id = await _get_or_create_jurisdiction(
                    conn, location.city, location.state, location.county, location.zipcode
                )
                await conn.execute(
                    "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
                    jurisdiction_id,
                    location_id,
                )

            # Look up whether this city has its own local ordinance
            has_local_ordinance = await _lookup_has_local_ordinance(
                conn, location.city, location.state
            )

            # ============================================================
            # FACILITY INFERENCE: Auto-populate facility_attributes for healthcare companies
            # ============================================================
            # A Gemini call, so it needs the same gate as the repository refresh
            # below — a projection-only run (tenant "Run check") must not spend
            # here either.
            canonical_industry = industry_profile.get("canonical_industry") if industry_profile else None
            if canonical_industry == "healthcare" and allow_repository_refresh:
                fa = location.facility_attributes
                if isinstance(fa, str):
                    try:
                        fa = json.loads(fa)
                    except (json.JSONDecodeError, TypeError):
                        fa = None
                has_entity_type = fa and fa.get("entity_type")
                if not has_entity_type:
                    try:
                        comp_row = await conn.fetchrow(
                            "SELECT name, industry, healthcare_specialties FROM companies WHERE id = $1",
                            company_id,
                        )
                        if comp_row:
                            inference = await service.infer_facility_profile(
                                company_name=comp_row["name"] or "",
                                industry=comp_row["industry"] or "",
                                healthcare_specialties=comp_row["healthcare_specialties"],
                                city=location.city,
                                state=location.state,
                            )
                            if inference and inference.get("confidence", 0) >= 0.5:
                                inferred_attrs = {
                                    "entity_type": inference["entity_type"],
                                    "payer_contracts": inference.get("likely_payer_contracts", []),
                                }
                                # Inline update to reuse existing connection
                                merged = (fa or {})
                                merged.update(inferred_attrs)
                                await conn.execute(
                                    "UPDATE business_locations SET facility_attributes = $1, updated_at = NOW() WHERE id = $2",
                                    json.dumps(merged), location_id,
                                )
                                # Reload location so Tier 4 sees the new attrs
                                row = await conn.fetchrow(
                                    "SELECT * FROM business_locations WHERE id = $1 AND company_id = $2",
                                    location_id, company_id,
                                )
                                if row:
                                    location = BusinessLocation(**dict(row))
                                yield {
                                    "type": "facility_inference",
                                    "message": f"Detected: {inference['entity_type']}",
                                }
                    except Exception as e:
                        print(f"[Facility Inference] Error during auto-inference: {e}")

            # ============================================================
            # TIER 1: Check for fresh structured data from authoritative sources
            # ============================================================
            from .structured_data import StructuredDataService

            structured_service = StructuredDataService()

            tier1_data = await structured_service.get_tier1_data(
                conn,
                jurisdiction_id,
                city=location.city,
                state=location.state,
                county=location.county,
                categories=["minimum_wage"],
                freshness_hours=168,  # 7 days
                triggered_by="stream_check",
            )

            if tier1_data:
                yield {
                    "type": "tier1",
                    "message": f"Loading verified data for {location_name}...",
                }
                # Tier 1 only covers a subset of categories (minimum_wage).
                # Merge with repository data for other categories so the sync
                # doesn't delete requirements for categories Tier 1 didn't cover.
                tier1_categories = {
                    _normalize_category(r.get("category")) or r.get("category")
                    for r in tier1_data
                }
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                repo_reqs = [
                    _jurisdiction_row_to_dict(jr)
                    for jr in j_reqs
                    if (_normalize_category(jr.get("category")) or jr.get("category"))
                    not in tier1_categories
                ]
                requirements = tier1_data + repo_reqs
                missing_categories = _missing_required_categories(requirements)
                if missing_categories:
                    research_categories = missing_categories
                    cached_requirements_for_merge = list(requirements)
                    yield {
                        "type": "researching",
                        "message": f"Expanding coverage for {location_name}: missing {', '.join(missing_categories)}.",
                    }
                else:
                    used_repository = True  # Skip Gemini and fresh-data logic

            # ============================================================
            # TIER 2: Check if jurisdiction repository is fresh enough
            # ============================================================
            # Use the location's auto_check_interval_days as the freshness threshold
            elif await _is_jurisdiction_fresh(
                conn, jurisdiction_id, location.auto_check_interval_days or 7
            ):
                # Load from repository — skip Gemini
                yield {
                    "type": "repository",
                    "message": f"Loading compliance data for {location_name}...",
                }
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]

                # Fill any gaps from state or county, even if the city has its own local ordinances
                filled = await _fill_missing_categories_from_parents(
                    conn,
                    jurisdiction_id,
                    requirements,
                    location.auto_check_interval_days or 7,
                )
                if filled:
                    yield {
                        "type": "repository",
                        "message": f"Filled missing categories from state/county data...",
                    }

                missing_categories = _missing_required_categories(requirements)
                if missing_categories:
                    research_categories = missing_categories
                    cached_requirements_for_merge = list(requirements)
                    yield {
                        "type": "researching",
                        "message": f"Coverage gap detected ({', '.join(missing_categories)}). Running live research...",
                    }
                else:
                    used_repository = True

            # If repo is fresh but the company has an industry profile (e.g.
            # healthcare), check whether industry-specific requirements
            # (rate_type='healthcare') are already in the company's compliance
            # data.  If not, force Gemini research for the industry's focused
            # categories so the company gets SB 525, nurse-overtime, etc.
            if used_repository and industry_context and industry_profile:
                focused = industry_profile.get("focused_categories") or []
                industry_rt = industry_profile.get("rate_types") or []
                if focused and industry_rt:
                    has_industry_data = await conn.fetchval(
                        """SELECT EXISTS(
                            SELECT 1 FROM compliance_requirements
                            WHERE location_id = $1 AND rate_type = ANY($2::text[])
                        )""",
                        location_id,
                        industry_rt,
                    )
                    if not has_industry_data:
                        # Need to research industry-specific variants
                        used_repository = False
                        research_categories = focused
                        cached_requirements_for_merge = list(requirements)
                        yield {
                            "type": "researching",
                            "message": f"Researching industry-specific requirements for {location_name}...",
                        }

            # ============================================================
            # TIER 2.5: County/State data reuse for no-local-ordinance cities
            # ============================================================
            if not used_repository and has_local_ordinance is False:
                county_reqs = await _try_load_county_requirements(
                    conn, jurisdiction_id, location.auto_check_interval_days or 7
                )
                if county_reqs:
                    yield {
                        "type": "repository",
                        "message": f"Using {location.county or 'county'} data for {location.city}...",
                    }
                    requirements = county_reqs

                    filled = await _fill_missing_categories_from_parents(
                        conn,
                        jurisdiction_id,
                        requirements,
                        location.auto_check_interval_days or 7,
                    )
                    if filled:
                        yield {
                            "type": "repository",
                            "message": f"Filled missing categories from state data...",
                        }

                    missing_categories = _missing_required_categories(requirements)
                    if missing_categories:
                        research_categories = missing_categories
                        cached_requirements_for_merge = list(requirements)
                        yield {
                            "type": "researching",
                            "message": f"Cache missing {', '.join(missing_categories)}. Running live research...",
                        }
                    else:
                        used_repository = True
                else:
                    state_reqs = await _try_load_state_requirements(
                        conn, jurisdiction_id, location.auto_check_interval_days or 7
                    )
                    if state_reqs:
                        yield {
                            "type": "repository",
                            "message": f"Using state data for {location.city}...",
                        }
                        requirements = state_reqs

                        filled = await _fill_missing_categories_from_parents(
                            conn,
                            jurisdiction_id,
                            requirements,
                            location.auto_check_interval_days or 7,
                        )

                        missing_categories = _missing_required_categories(requirements)
                        if missing_categories:
                            research_categories = missing_categories
                            cached_requirements_for_merge = list(requirements)
                            yield {
                                "type": "researching",
                                "message": f"State cache missing {', '.join(missing_categories)}. Running live research...",
                            }
                        else:
                            used_repository = True

            # ============================================================
            # TIER 3: Research with Gemini (stale or missing data)
            # ============================================================
            if not used_repository and allow_live_research:
                # Stale or missing — call Gemini
                # First, get known sources for this jurisdiction (or discover them)
                known_sources = await get_known_sources(conn, jurisdiction_id)

                if not known_sources:
                    # Bootstrap: discover sources for new jurisdiction
                    yield {
                        "type": "discovering_sources",
                        "message": f"Learning about {location_name}...",
                    }
                    discovered = await service.discover_jurisdiction_sources(
                        city=location.city,
                        state=location.state,
                        county=location.county,
                    )
                    for src in discovered:
                        domain = (src.get("domain") or "").lower()
                        if domain:
                            for cat in src.get("categories", []):
                                await record_source(
                                    conn, jurisdiction_id, domain, src.get("name"), cat
                                )
                    known_sources = await get_known_sources(conn, jurisdiction_id)

                # Build context for research prompt
                source_context = build_context_prompt(known_sources)

                # Phase 3.1: Get recent corrections to avoid repeating false positives
                corrections = await get_recent_corrections(jurisdiction_id)
                corrections_context = format_corrections_for_prompt(corrections)

                # Load preemption rules for this state to guide Gemini prompts
                try:
                    preemption_rows = await conn.fetch(
                        "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                        location.state.upper(),
                    )
                    preemption_rules = {
                        row["category"]: row["allows_local_override"]
                        for row in preemption_rows
                    }
                except asyncpg.UndefinedTableError:
                    preemption_rules = {}

                yield {
                    "type": "researching",
                    "message": f"Researching requirements for {location_name}...",
                }

                # Inform the client when a city has no local ordinance
                if has_local_ordinance is False:
                    parent = f"{location.county} County / " if location.county else ""
                    yield {
                        "type": "jurisdiction_info",
                        "message": f"{location.city} does not have its own local ordinances. Using {parent}{location.state} rules.",
                    }

                research_queue = asyncio.Queue()

                def _on_research_retry(attempt: int, error: str):
                    research_queue.put_nowait(
                        {
                            "type": "retrying",
                            "message": f"Retrying research (attempt {attempt + 1})...",
                        }
                    )

                research_task = asyncio.create_task(
                    service.research_location_compliance(
                        city=location.city,
                        state=location.state,
                        county=location.county,
                        categories=research_categories,
                        source_context=source_context,
                        corrections_context=corrections_context,
                        preemption_rules=preemption_rules,
                        has_local_ordinance=has_local_ordinance,
                        on_retry=_on_research_retry,
                        industry_context=industry_context,
                    )
                )
                async for evt in _heartbeat_while(research_task, queue=research_queue):
                    yield evt
                researched_requirements = research_task.result() or []
                if research_categories and cached_requirements_for_merge:
                    target_set = {
                        _normalize_category(cat) or cat for cat in research_categories
                    }
                    preserved = [
                        req
                        for req in cached_requirements_for_merge
                        if (
                            _normalize_category(req.get("category"))
                            or req.get("category")
                        )
                        not in target_set
                    ]
                    requirements = preserved + researched_requirements
                else:
                    requirements = researched_requirements

                # After Tier 3: if some research categories are still missing, fall back to
                # state-level data (e.g., final_pay / minor_work_permit governed by state law).
                still_missing = [
                    cat
                    for cat in (research_categories or [])
                    if cat
                    not in {
                        _normalize_category(r.get("category")) for r in requirements
                    }
                ]
                if still_missing:
                    requirements = await _fill_from_state_fallback(
                        conn,
                        service,
                        jurisdiction_id,
                        location.city,
                        location.state,
                        location.county,
                        has_local_ordinance,
                        requirements,
                        still_missing,
                        threshold_days=max(location.auto_check_interval_days or 7, 90),
                    )
            # Repository-only mode: allow_live_research=False forbids per-company
            # live research, but gap-driven refresh of the SHARED jurisdiction
            # source-of-truth is intentional — it fires only for categories never
            # researched in this jurisdiction and upserts into the shared library
            # (library-permanence model: search on miss, store forever).
            #
            # That refresh is itself a Gemini call, so it needs its own gate.
            # allow_repository_refresh=False (the tenant-facing route) means this
            # run must be a pure projection with ZERO Gemini spend — a customer's
            # button click must never research, even indirectly via "the shared
            # library happened to have a gap." Catalog freshness is our job, on
            # our schedule (legislation_watch / structured_data_fetch / admin
            # refresh); a tenant only ever reads what we've already stored.
            elif not used_repository and not allow_live_research and not allow_repository_refresh:
                # Real gaps only. The tier stages above build `requirements` from
                # a leaf-only or freshness-windowed slice, so a category the FULL
                # chain covers can look "missing" here (false gap → false queue).
                # Recompute against the exact set the tab projects
                # (`_project_chain_to_location`, whole chain, no freshness limit)
                # so we only ever queue jurisdictions we genuinely lack.
                chain_reqs = await _project_chain_to_location(
                    conn, company_id, location, jurisdiction_id
                )
                missing_categories = _missing_required_categories(chain_reqs)
                used_repository = True
                if missing_categories:
                    yield {
                        "type": "repository_only",
                        "jurisdiction_id": str(jurisdiction_id),
                        "missing_categories": missing_categories,
                        "message": (
                            "Some categories aren't in the library yet for "
                            f"{location_name} ({', '.join(missing_categories)}). "
                            "An admin can refresh jurisdiction data to add them."
                        ),
                    }

            elif not used_repository and not allow_live_research and allow_repository_refresh:
                missing_categories = _missing_required_categories(requirements)
                used_repository = True
                if missing_categories:
                    yield {
                        "type": "repository_refresh",
                        "jurisdiction_id": str(jurisdiction_id),
                        "missing_categories": missing_categories,
                        "message": (
                            "Repository coverage is incomplete. Triggering source-of-truth refresh for "
                            f"{location_name} ({', '.join(missing_categories)})."
                        ),
                    }
                    refresh_queue = asyncio.Queue()

                    def _on_refresh_retry(attempt: int, error: str):
                        refresh_queue.put_nowait(
                            {
                                "type": "retrying",
                                "message": f"Retrying repository refresh (attempt {attempt + 1})...",
                            }
                        )

                    refresh_task = asyncio.create_task(
                        _refresh_repository_missing_categories(
                            conn,
                            service,
                            jurisdiction_id=jurisdiction_id,
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            has_local_ordinance=has_local_ordinance,
                            current_requirements=requirements,
                            missing_categories=missing_categories,
                            on_retry=_on_refresh_retry,
                        )
                    )
                    try:
                        async for evt in _heartbeat_while(
                            refresh_task, queue=refresh_queue
                        ):
                            yield evt
                        requirements = refresh_task.result() or requirements
                    except Exception as refresh_error:
                        print(
                            "[Compliance] Repository refresh failed for "
                            f"{location.city}, {location.state}: {refresh_error}"
                        )

                    missing_after_refresh = _missing_required_categories(requirements)
                    if missing_after_refresh:
                        yield {
                            "type": "repository_only",
                            "jurisdiction_id": str(jurisdiction_id),
                            "missing_categories": missing_after_refresh,
                            "message": (
                                "Jurisdiction repository is still missing "
                                f"{', '.join(missing_after_refresh)} after refresh. "
                                "Run Admin > Jurisdictions research refresh for this city."
                            ),
                        }
                    else:
                        yield {
                            "type": "repository_refreshed",
                            "jurisdiction_id": str(jurisdiction_id),
                            "message": (
                                f"Source-of-truth refreshed for {location_name}. Re-syncing from repository."
                            ),
                        }

                    if not requirements:
                        stale_repo_rows = await _load_jurisdiction_requirements(
                            conn, jurisdiction_id
                        )
                        if stale_repo_rows:
                            requirements = [
                                _jurisdiction_row_to_dict(jr) for jr in stale_repo_rows
                            ]
                            yield {
                                "type": "fallback",
                                "message": "Using existing repository data while coverage refresh completes.",
                            }

            # Stale-data fallback: if Gemini returned nothing, try cached data.
            # Set used_repository = True to skip fresh-data logic (upserts, alerts, verification).
            if not requirements and not used_repository:
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                if j_reqs:
                    requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
                    used_repository = True
                    print(
                        f"[Compliance] Falling back to stale repository data ({len(requirements)} cached requirements)"
                    )
                    yield {
                        "type": "fallback",
                        "message": "Using cached data (live research unavailable)",
                    }

            # ============================================================
            # TIER 4: Triggered research based on facility attributes
            # ============================================================
            from ..compliance_registry import get_activated_profiles as _get_activated_profiles

            fa = location.facility_attributes
            if isinstance(fa, str):
                try:
                    fa = json.loads(fa)
                except (json.JSONDecodeError, TypeError):
                    fa = None
            activated_profiles = _get_activated_profiles(fa) if fa else []
            failed_profile_keys: set = set()
            if activated_profiles:
                # Lazy-init Gemini context if Tier 3 didn't run
                if not source_context:
                    known_sources = await get_known_sources(conn, jurisdiction_id)
                    source_context = build_context_prompt(known_sources)

                for profile in activated_profiles:
                    # Check if jurisdiction already has triggered requirements for this profile
                    existing_triggered = await conn.fetchval(
                        """SELECT COUNT(*) FROM jurisdiction_requirements
                           WHERE jurisdiction_id = $1
                             AND applicable_entity_types @> $2::jsonb""",
                        jurisdiction_id,
                        json.dumps([profile.key]),
                    )
                    if existing_triggered and existing_triggered > 0:
                        # Load existing triggered requirements and add to results
                        triggered_rows = await conn.fetch(
                            """SELECT * FROM jurisdiction_requirements
                               WHERE jurisdiction_id = $1
                                 AND applicable_entity_types @> $2::jsonb""",
                            jurisdiction_id,
                            json.dumps([profile.key]),
                        )
                        for tr in triggered_rows:
                            requirements.append(_jurisdiction_row_to_dict(dict(tr)))
                        continue

                    yield {
                        "type": "trigger_research",
                        "message": f"Researching {profile.label}-specific requirements...",
                    }
                    try:
                        trigger_cats = list(profile.applicable_categories)
                        triggered_reqs = await service.research_triggered_requirements(
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            profile_key=profile.key,
                            profile_label=profile.label,
                            trigger_condition=profile.trigger_condition,
                            research_instruction=profile.research_instruction,
                            categories=trigger_cats,
                            source_context=source_context,
                        )
                        if triggered_reqs:
                            await _upsert_requirements_additive(
                                conn, jurisdiction_id, triggered_reqs, research_source="gemini"
                            )
                            requirements.extend(triggered_reqs)
                    except Exception as e:
                        failed_profile_keys.add(profile.key)
                        print(f"[Tier 4] Error researching {profile.key}: {e}")

            # ── Gap detection: flag missing specialty policies for admin ──
            if activated_profiles:
                req_categories = {
                    r.get("category") for r in requirements if r.get("category")
                }
                for profile in activated_profiles:
                    if profile.key in failed_profile_keys:
                        continue
                    for cat in profile.applicable_categories:
                        if cat not in req_categories:
                            # Deduplicate: skip if a missing_specialty alert already exists
                            existing_alert = await conn.fetchval(
                                """SELECT id FROM compliance_alerts
                                   WHERE location_id = $1 AND alert_type = 'missing_specialty'
                                     AND category = $2 AND metadata->>'trigger_profile' = $3
                                     AND status != 'dismissed'""",
                                location_id, cat, profile.key,
                            )
                            if existing_alert:
                                continue
                            try:
                                cat_label = cat.replace("_", " ").title()
                                await _create_alert(
                                    conn,
                                    location_id,
                                    company_id,
                                    None,
                                    f"Missing {cat_label} policies for {profile.label}",
                                    (
                                        f"Facility profile indicates {profile.label} requirements apply "
                                        f"but no {cat_label} policies found. Admin review recommended."
                                    ),
                                    "info",
                                    cat,
                                    alert_type="missing_specialty",
                                    metadata={
                                        "inferred_profile": profile.key,
                                        "missing_category": cat,
                                        "trigger_profile": profile.key,
                                        "source": "gemini_inference",
                                    },
                                )
                            except Exception as e:
                                print(f"[Gap Detection] Error creating alert for {cat}/{profile.key}: {e}")

            if not requirements:
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )
                await _complete_check_log(conn, log_id, 0, 0, 0)
                yield {
                    "type": "completed",
                    "location": location_name,
                    "new": 0,
                    "updated": 0,
                    "alerts": 0,
                }
                return

            # Post-filter: handle city-level results for cities with no local ordinance.
            # Instead of stripping all city-level entries (which can lose entire categories
            # like minimum_wage), promote orphaned city-level entries to state-level.
            if has_local_ordinance is False:
                requirements = _filter_city_level_requirements(
                    requirements, location.state
                )
                # Annotate remaining reqs with inheritance note
                parent = f"{location.county} County / " if location.county else ""
                note = (
                    f" [Note: {location.city} does not have its own local ordinance; "
                    f"this requirement applies via {parent}{location.state} state law.]"
                )
                for r in requirements:
                    desc = r.get("description") or ""
                    if note not in desc:
                        r["description"] = desc + note

            # Normalize and filter (with preemption awareness)
            _normalize_requirement_categories(requirements)
            requirements = await _filter_requirements_for_company(
                conn, company_id, requirements
            )
            requirements = await _filter_with_preemption(
                conn, requirements, location.state
            )

            yield {
                "type": "processing",
                "message": f"Processing {len(requirements)} requirements...",
            }

            # If Gemini was called, contribute results to jurisdiction repository.
            if not used_repository:
                await _upsert_jurisdiction_requirements_routed(
                    conn, jurisdiction_id, requirements, research_source="gemini"
                )

                # Learn from successful research: record any new sources seen
                for req in requirements:
                    source_url = req.get("source_url", "")
                    if source_url:
                        domain = extract_domain(source_url)
                        if domain:
                            await record_source(
                                conn,
                                jurisdiction_id,
                                domain,
                                req.get("source_name"),
                                req.get("category", ""),
                            )

            # Re-project from the CATALOG over the location's whole jurisdiction
            # chain, now that this run's research has been contributed to it.
            #
            # `requirements` up to here is one research pass's result set — the
            # deltas. What the tenant is liable for is the union of every active
            # obligation in its city/county/state/federal chain. Syncing the
            # research result instead of the chain is why an LA dental practice
            # saw no OSHA Bloodborne Pathogens standard, no infection control and
            # no hazardous-waste rules: all three were in the catalog, in its
            # chain, and simply never made it into the projection.
            #
            # Falls back to the research set if the chain projection comes back
            # empty — an empty sync would wipe the tenant's tab.
            chain_requirements = await _project_chain_to_location(
                conn, company_id, location, jurisdiction_id
            )
            if chain_requirements:
                yield {
                    "type": "processing",
                    "message": (
                        f"Applying {len(chain_requirements)} requirements across "
                        f"{location_name}'s full jurisdiction stack..."
                    ),
                }
                requirements = chain_requirements
            else:
                # Fallback path: syncing this run's raw research set. It has NOT
                # been through _project_chain_to_location, so the placeholder
                # filter has to be applied here too — otherwise "no rule applies"
                # rows reach the tab by the one route that skips the projection.
                requirements = _drop_no_rule_placeholders(requirements)

            # Sync requirements to location (change detection, alerts, history)
            # Only create alerts for fresh Gemini data — repository data is cached
            # and shouldn't re-alert on every check.
            sync_result = await _sync_requirements_to_location(
                conn,
                location_id,
                company_id,
                requirements,
                create_alerts=not used_repository,
            )
            new_count = sync_result["new"]
            updated_count = sync_result["updated"]
            alert_count = sync_result["alerts"]
            changes_to_verify = sync_result["changes_to_verify"]
            existing_by_key = sync_result["existing_by_key"]

            # Send ONE summary email for all new requirement alerts (not per-alert)
            if alert_count > 0:
                try:
                    await _send_bulk_alert_email(company_id, location_id, alert_count)
                except Exception as e:
                    print(f"[Compliance] Bulk alert email error: {e}")

            # Auto-embed new/updated jurisdiction requirements for RAG Q&A
            try:
                from .compliance_embedding_pipeline import embed_updated_requirements
                asyncio.create_task(embed_updated_requirements(conn, jurisdiction_id))
            except Exception as e:
                print(f"[Compliance] Embedding update error: {e}")

            # Yield per-requirement status events
            new_keys = {_compute_requirement_key(r) for r in requirements}
            for req in requirements:
                req_title = req.get("title", "")
                rk = _compute_requirement_key(req)
                existing_entry = existing_by_key.get(rk)
                if existing_entry and existing_entry.get("id"):
                    # Could be updated or unchanged — emit generic result
                    yield {"type": "result", "status": "existing", "message": req_title}
                else:
                    yield {"type": "result", "status": "new", "message": req_title}

            # Collect (alert_id, change_info) for batch impact summary generation
            alert_changes_for_summary: list[tuple] = []

            # Verify material changes with Gemini (skip verification when using cached repository data)
            # Phase 2.3: Use batched verification for efficiency
            if changes_to_verify and not used_repository:
                verify_total = min(len(changes_to_verify), MAX_VERIFICATIONS_PER_CHECK)
                yield {
                    "type": "verifying",
                    "message": f"Verifying {verify_total} change(s) in batch...",
                }
                verification_count = 0

                # Prepare batch of changes for verification
                changes_batch = []
                for change_info in changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK]:
                    req = change_info["req"]
                    changes_batch.append(
                        {
                            "category": req.get("category", ""),
                            "title": req.get("title", ""),
                            "old_value": change_info["old_value"],
                            "new_value": change_info["new_value"],
                        }
                    )

                # Get jurisdiction name from first change (all same jurisdiction)
                jurisdiction_name = changes_to_verify[0]["req"].get(
                    "jurisdiction_name", f"{location.city}, {location.state}"
                )

                try:
                    yield {
                        "type": "verifying_item",
                        "message": f"Batch verifying {verify_total} changes...",
                        "current": 1,
                        "total": 1,
                    }
                    verify_task = asyncio.create_task(
                        service.verify_compliance_changes_batch(
                            changes=changes_batch,
                            jurisdiction_name=jurisdiction_name,
                        )
                    )
                    async for evt in _heartbeat_while(verify_task):
                        yield evt
                    verification_results = verify_task.result()
                except Exception as e:
                    print(f"[Compliance] Batch verification failed: {e}")
                    verification_results = [
                        VerificationResult(
                            confirmed=False,
                            confidence=0.5,
                            sources=[],
                            explanation="Batch verification unavailable",
                        )
                    ] * len(changes_batch)

                # Process each verification result
                for idx, (change_info, verification) in enumerate(
                    zip(
                        changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK],
                        verification_results,
                    )
                ):
                    req = change_info["req"]
                    existing = change_info["existing"]

                    confidence = score_verification_confidence(verification.sources)
                    confidence = max(confidence, verification.confidence)

                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    description = req.get("description")
                    if description:
                        change_msg += f" {description}"

                    # Compute requirement key for logging
                    req_key = _compute_requirement_key(req)

                    if confidence >= 0.6:
                        alert_count += 1
                        alert_id = await _create_alert(
                            conn,
                            location_id,
                            company_id,
                            existing["id"],
                            f"Compliance Change: {req.get('title')}",
                            change_msg,
                            "warning",
                            req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={
                                "verification_explanation": verification.explanation
                            },
                        )
                        alert_changes_for_summary.append((alert_id, change_info))
                        # Log verification outcome for calibration
                        await _log_verification_outcome(
                            conn,
                            jurisdiction_id,
                            alert_id,
                            req_key,
                            req.get("category"),
                            confidence,
                            predicted_is_change=True,
                            verification_sources=verification.sources,
                        )
                        _record_change_notification_item(
                            change_email_items, req, change_info
                        )
                        verification_count += 1
                    elif confidence >= 0.3:
                        alert_count += 1
                        alert_id = await _create_alert(
                            conn,
                            location_id,
                            company_id,
                            existing["id"],
                            f"Unverified: {req.get('title')}",
                            change_msg,
                            "info",
                            req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={
                                "verification_explanation": verification.explanation,
                                "unverified": True,
                            },
                        )
                        alert_changes_for_summary.append((alert_id, change_info))
                        # Log verification outcome for calibration
                        await _log_verification_outcome(
                            conn,
                            jurisdiction_id,
                            alert_id,
                            req_key,
                            req.get("category"),
                            confidence,
                            predicted_is_change=True,
                            verification_sources=verification.sources,
                        )
                        _record_change_notification_item(
                            change_email_items, req, change_info
                        )
                        verification_count += 1
                    else:
                        # Log low-confidence rejections too for calibration
                        await _log_verification_outcome(
                            conn,
                            jurisdiction_id,
                            None,
                            req_key,
                            req.get("category"),
                            confidence,
                            predicted_is_change=False,
                            verification_sources=verification.sources,
                        )
                        print(
                            f"[Compliance] Low confidence ({confidence:.2f}) for change: {req.get('title')}, skipping alert"
                        )

                # Handle overflow changes without verification
                for change_info in changes_to_verify[MAX_VERIFICATIONS_PER_CHECK:]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"
                    alert_count += 1
                    overflow_alert_id = await _create_alert(
                        conn,
                        location_id,
                        company_id,
                        existing["id"],
                        f"Compliance Change: {req.get('title')}",
                        change_msg,
                        "warning",
                        req.get("category"),
                        source_url=req.get("source_url"),
                        source_name=req.get("source_name"),
                        alert_type="change",
                    )
                    alert_changes_for_summary.append((overflow_alert_id, change_info))
                    _record_change_notification_item(
                        change_email_items, req, change_info
                    )

                if verification_count > 0:
                    yield {
                        "type": "verified",
                        "message": f"Verified {verification_count} change(s)",
                    }

            # Legislation scan — only via Gemini when not using repository
            if not used_repository:
                yield {
                    "type": "scanning",
                    "message": "Scanning for upcoming legislation...",
                }
                try:
                    current_reqs = [
                        dict(r) for r in existing_by_key.values() if r.get("id")
                    ]
                    leg_task = asyncio.create_task(
                        service.scan_upcoming_legislation(
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            current_requirements=current_reqs,
                        )
                    )
                    async for evt in _heartbeat_while(leg_task):
                        yield evt
                    legislation_items = leg_task.result()
                    # Contribute to jurisdiction repository
                    await _upsert_jurisdiction_legislation(
                        conn, jurisdiction_id, legislation_items
                    )
                    leg_count = await process_upcoming_legislation(
                        conn, location_id, company_id, legislation_items
                    )
                    if leg_count > 0:
                        alert_count += leg_count
                        yield {
                            "type": "legislation",
                            "message": f"Found {leg_count} upcoming legislative change(s)",
                        }
                except Exception as e:
                    print(f"[Compliance] Legislation scan error: {e}")

            # Deadline escalation
            try:
                escalated = await escalate_upcoming_deadlines(conn, company_id)
                if escalated > 0:
                    yield {
                        "type": "escalation",
                        "message": f"Escalated {escalated} deadline(s)",
                    }
            except Exception as e:
                print(f"[Compliance] Deadline escalation error: {e}")

            # Generate plain-English impact summaries for change alerts
            if alert_changes_for_summary:
                yield {
                    "type": "progress",
                    "message": f"Generating impact summaries for {len(alert_changes_for_summary)} alert(s)...",
                }
                try:
                    from .impact_summary import batch_generate_impact_summaries

                    loc_dict = {
                        "id": location_id,
                        "name": getattr(location, "name", None) or location_name,
                        "city": location.city,
                        "state": location.state,
                    }
                    company_row = await conn.fetchrow(
                        "SELECT name, industry FROM companies WHERE id = $1",
                        company_id,
                    )
                    company_ctx = {
                        "company_name": company_row["name"] if company_row else "",
                        "industry": company_row["industry"] if company_row else "",
                    }
                    await batch_generate_impact_summaries(
                        alert_changes_for_summary, loc_dict, company_ctx, conn
                    )
                except Exception as e:
                    print(f"[Compliance] Impact summary generation error: {e}")

            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id,
            )
            await _complete_check_log(
                conn, log_id, new_count, updated_count, alert_count
            )
        except Exception as e:
            await _complete_check_log(
                conn, log_id, new_count, updated_count, alert_count, error=str(e)
            )
            raise

    # Vertical (industry-specific) coverage — research what the shared catalog is
    # still missing for this company's industry, then re-project.
    #
    # Placed HERE, after the `async with get_connection()` block above has exited,
    # on purpose: that block holds ONE pool connection for the entire check, and a
    # fill is many sequential Gemini calls. Splicing it inside would pin that
    # connection for minutes. `vertical_coverage.fill` takes a connection FACTORY
    # for exactly this reason.
    vertical_new = 0
    if include_vertical_fill:
        from ...database import get_connection as _get_conn
        from . import vertical_coverage

        try:
            async with _get_conn() as vconn:
                resolved = await vertical_coverage.resolve_vertical(vconn, company_id)
                if resolved:
                    v_parent, v_slug, v_label, v_tag, v_minted = resolved
                    v_categories, v_context = await vertical_coverage.ensure_specialty(
                        vconn, v_parent, v_slug, v_label
                    )
                    chains = await vertical_coverage.chains_for_leaves(
                        vconn, [jurisdiction_id]
                    )
                    nodes = sorted({j for c in chains.values() for j, _ in c})
                    await vertical_coverage.backfill_ledger(
                        vconn, nodes, v_tag, v_categories
                    )
                    plan, v_deferred = await vertical_coverage.plan_fill(
                        vconn, chains, v_tag, v_categories
                    )
                else:
                    plan, v_deferred, v_minted, v_label = [], 0, False, None

            if resolved and (plan or v_minted):
                if plan:
                    yield {
                        "type": "vertical_researching",
                        "vertical": v_label,
                        "cells": len(plan),
                        "deferred": v_deferred,
                        "message": f"Researching {v_label}-specific requirements…",
                    }
                v_deduped = 0
                async for vev in vertical_coverage.fill(
                    _get_conn, company_id, plan, v_tag, v_context
                ):
                    vertical_new += vev.get("new", 0)
                    v_deduped += vev.get("deduped", 0)

                # Re-project on ANY catalog change, and always when the specialty
                # tag was just minted: every projection before that write filtered
                # this vertical's rows out (the industry filter reads the company's
                # own tag set), so a fully-covered ledger still leaves the tab bare.
                if vertical_new or v_deduped or v_minted:
                    async with _get_conn() as vconn:
                        await vertical_coverage.reproject_location(
                            vconn, company_id, location_id
                        )
                    yield {
                        "type": "vertical_complete",
                        "vertical": v_label,
                        "requirements_added": vertical_new,
                        "message": f"{v_label}: {vertical_new} requirement(s) added.",
                    }
        except Exception as e:
            # Vertical scoping is additive — never fail a check over it.
            print(f"[Compliance] Vertical fill failed for {location_name}: {e}")
            yield {"type": "warning", "message": f"Vertical scoping incomplete: {e}"}

    from ...config import get_settings as _get_settings
    if _get_settings().compliance_emails_enabled:
        try:
            await _notify_company_admins_of_compliance_changes(
                company_id=company_id,
                location=location,
                change_items=change_email_items,
            )
        except Exception as e:
            print(f"[Compliance] Error notifying admins about compliance changes: {e}")

    yield {
        "type": "completed",
        "location": location_name,
        "new": new_count + vertical_new,
        "updated": updated_count,
        "alerts": alert_count,
    }


async def get_location_counts(location_id: UUID) -> dict:
    """Get requirements count and unread alerts count for a location."""
    from ...database import get_connection

    async with get_connection() as conn:
        loc = await conn.fetchrow(
            """SELECT bl.state, bl.company_id, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1""",
            location_id,
        )
        state = (loc["state"] if loc else None) or ""
        company_id = loc["company_id"] if loc else None
        has_local_ordinance = loc["has_local_ordinance"] if loc else None

        rows = await conn.fetch(
            "SELECT r.category, r.jurisdiction_level, r.title, r.jurisdiction_name, r.rate_type "
            "FROM compliance_requirements r "
            "LEFT JOIN jurisdiction_requirements cat ON cat.id = r.jurisdiction_requirement_id "
            "WHERE r.location_id = $1"
            # This tile counts what the Requirements tab lists — the two must
            # agree or the count is just wrong on screen.
            + await codified_gate_sql("cat", conn=conn),
            location_id,
        )
        req_dicts = [dict(r) for r in rows]
        if has_local_ordinance is False:
            req_dicts = _filter_city_level_requirements(req_dicts, state)
        _normalize_requirement_categories(req_dicts)
        if company_id:
            req_dicts = await _filter_requirements_for_company(
                conn, company_id, req_dicts
            )
        filtered = (
            await _filter_with_preemption(conn, req_dicts, state)
            if state
            else _filter_by_jurisdiction_priority(req_dicts)
        )
        unread_alerts_count = await conn.fetchval(
            "SELECT COUNT(*) FROM compliance_alerts WHERE location_id = $1 AND status = 'unread'",
            location_id,
        )
        return {
            "requirements_count": len(filtered),
            "unread_alerts_count": unread_alerts_count or 0,
        }


async def get_locations(company_id: UUID) -> list[dict]:
    """Return locations with employee/requirements/alerts counts in a single query."""
    from ...database import get_connection

    async with get_connection() as conn:
        # `jurisdiction_repo_count` (jrc below) is deliberately NOT gated — it
        # reports what the shared catalog holds for this jurisdiction, which is
        # exactly the number an admin needs to see diverge from the tenant's.
        query = """SELECT bl.*, jr.has_local_ordinance,
                      COALESCE(ec.cnt, 0) AS employee_count,
                      COALESCE(en.names, ARRAY[]::text[]) AS employee_names,
                      COALESCE(rc.cnt, 0) AS requirements_count,
                      COALESCE(rall.cnt, 0) AS projected_count,
                      COALESCE(ac.cnt, 0) AS unread_alerts_count,
                      COALESCE(jrc.cnt, 0) AS jurisdiction_repo_count
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM employees e
                   WHERE e.termination_date IS NULL
                     AND (
                       e.work_location_id = bl.id
                       OR (
                         e.work_location_id IS NULL
                         AND LOWER(e.work_city) = LOWER(bl.city)
                         AND UPPER(e.work_state) = UPPER(bl.state)
                         AND e.org_id = bl.company_id
                       )
                     )
               ) ec ON true
               LEFT JOIN LATERAL (
                   SELECT ARRAY(
                       SELECT e.first_name || ' ' || e.last_name
                       FROM employees e
                       WHERE e.termination_date IS NULL
                         AND (
                           e.work_location_id = bl.id
                           OR (
                             e.work_location_id IS NULL
                             AND LOWER(e.work_city) = LOWER(bl.city)
                             AND UPPER(e.work_state) = UPPER(bl.state)
                             AND e.org_id = bl.company_id
                           )
                         )
                       LIMIT 5
                   ) AS names
               ) en ON true
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM compliance_requirements cr
                   LEFT JOIN jurisdiction_requirements cat
                     ON cat.id = cr.jurisdiction_requirement_id
                   WHERE cr.location_id = bl.id
                   __CODIFIED_GATE__
               ) rc ON true
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM compliance_requirements cr
                   WHERE cr.location_id = bl.id
               ) rall ON true
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM compliance_alerts ca
                   WHERE ca.location_id = bl.id AND ca.status = 'unread'
               ) ac ON true
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM jurisdiction_requirements jreq
                   WHERE jreq.jurisdiction_id = bl.jurisdiction_id
               ) jrc ON true
               WHERE bl.company_id = $1
               ORDER BY bl.created_at DESC"""
        query = query.replace(
            "__CODIFIED_GATE__", await codified_gate_sql("cat", conn=conn)
        )
        rows = await conn.fetch(query, company_id)
        result = []
        for row in rows:
            d = dict(row)
            # data_status answers "has this location been synced from the
            # catalog?" — a pipeline fact. It must read the UNGATED projection
            # count: a fully-synced location whose rows simply aren't codified
            # yet would otherwise report 'needs_research' and invite a pointless
            # (and billable) re-research of data we already hold.
            req_count = d.pop("projected_count", 0)
            repo_count = d.get("jurisdiction_repo_count", 0)
            if req_count > 0:
                d["data_status"] = "synced"
            elif repo_count > 0:
                d["data_status"] = "available"
            else:
                d["data_status"] = "needs_research"
            result.append(d)
        return result


async def verify_location_ownership(conn, location_id: UUID, company_id: UUID) -> bool:
    """Return True iff *location_id* belongs to *company_id*.

    Single source of truth for the ownership check that used to be inlined at
    three call sites (compliance.py's legislation-assign endpoint, and the two
    admin cherry-pick functions below) — future hardening (e.g. soft-delete
    awareness) lands once here instead of three times.
    """
    owns_location = await conn.fetchval(
        "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    return bool(owns_location)


async def get_location(
    location_id: UUID, company_id: UUID
) -> Optional[BusinessLocation]:
    from ...database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT bl.*, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id,
            company_id,
        )
        if row:
            return BusinessLocation(**dict(row))
        return None


async def update_facility_attributes(
    location_id: UUID, company_id: UUID, attrs: dict
) -> Optional[dict]:
    """Merge new facility attributes into existing JSONB and return merged result."""
    from ...database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, facility_attributes FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not row:
            return None

        existing = row["facility_attributes"]
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        existing = existing or {}

        # Merge: new values overwrite, None values remove keys
        for k, v in attrs.items():
            if v is None:
                existing.pop(k, None)
            else:
                existing[k] = v

        await conn.execute(
            "UPDATE business_locations SET facility_attributes = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(existing), location_id,
        )
        return existing


async def get_facility_attributes(
    location_id: UUID, company_id: UUID
) -> Optional[dict]:
    """Return facility_attributes for a location, or None if not found."""
    from ...database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT facility_attributes FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not row:
            return None
        fa = row["facility_attributes"]
        if isinstance(fa, str):
            try:
                return json.loads(fa)
            except (json.JSONDecodeError, TypeError):
                return {}
        return fa or {}


async def update_location(
    location_id: UUID, company_id: UUID, data: LocationUpdate
) -> Optional[BusinessLocation]:
    from ...database import get_connection
    from datetime import datetime

    async with get_connection() as conn:
        updates = []
        params = []
        param_idx = 3

        if data.name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(data.name)
            param_idx += 1
        if data.address is not None:
            updates.append(f"address = ${param_idx}")
            params.append(data.address)
            param_idx += 1
        if data.city is not None:
            updates.append(f"city = ${param_idx}")
            params.append(data.city)
            param_idx += 1
        if data.state is not None:
            updates.append(f"state = ${param_idx}")
            params.append(data.state.upper())
            param_idx += 1
        if data.county is not None:
            updates.append(f"county = ${param_idx}")
            params.append(data.county)
            param_idx += 1
        if data.zipcode is not None:
            updates.append(f"zipcode = ${param_idx}")
            params.append(data.zipcode)
            param_idx += 1
        if data.is_active is not None:
            updates.append(f"is_active = ${param_idx}")
            params.append(data.is_active)
            param_idx += 1
        if data.ein is not None:
            updates.append(f"ein = ${param_idx}")
            params.append(data.ein)
            param_idx += 1
        if data.naics is not None:
            updates.append(f"naics = ${param_idx}")
            params.append(data.naics)
            param_idx += 1
        if data.max_employees is not None:
            updates.append(f"max_employees = ${param_idx}")
            params.append(data.max_employees)
            param_idx += 1
        if data.annual_avg_employees is not None:
            updates.append(f"annual_avg_employees = ${param_idx}")
            params.append(data.annual_avg_employees)
            param_idx += 1

        if not updates:
            return await get_location(location_id, company_id)

        updates.append("updated_at = NOW()")
        params.insert(0, location_id)
        params.insert(1, company_id)

        await conn.execute(
            f"UPDATE business_locations SET {', '.join(updates)} WHERE id = $1 AND company_id = $2",
            *params,
        )
        return await get_location(location_id, company_id)


async def delete_location(location_id: UUID, company_id: UUID) -> bool:
    from ...database import get_connection

    async with get_connection() as conn:
        # Protect locations with active employees
        active_count = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE work_location_id = $1 AND termination_date IS NULL",
            location_id,
        )
        if active_count and active_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete: {active_count} active employee{'s' if active_count != 1 else ''} assigned to this location.",
            )

        result = await conn.execute(
            "DELETE FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id,
            company_id,
        )
        return result == "DELETE 1"


async def get_employee_impact_for_location(
    location_id: UUID, company_id: UUID
) -> Dict[str, Any]:
    """Calculate employee impact for a compliance location.

    Returns total affected employees plus per-rate_type violation details.

    Primary path: query by work_location_id FK (fast, exact).
    Fallback: heuristic matching for employees with work_location_id IS NULL
    (legacy rows that predate the FK linkage).
    """
    from ...database import get_connection

    async with get_connection() as conn:
        # Get location state/city
        loc = await conn.fetchrow(
            "SELECT state, city FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not loc:
            return {"total_affected": 0, "employee_names": [], "violations_by_rate_type": {}}

        loc_state = loc["state"]
        loc_city = loc["city"]

        # Primary path: employees linked via FK
        fk_employees = await conn.fetch(
            """
            SELECT id, first_name, last_name, pay_classification, pay_rate,
                   work_city, work_state
            FROM employees
            WHERE org_id = $1 AND work_location_id = $2 AND termination_date IS NULL
            """,
            company_id, location_id,
        )

        # Fallback: heuristic for legacy employees with work_location_id IS NULL
        if loc_city:
            heuristic_employees = await conn.fetch(
                """
                SELECT id, first_name, last_name, pay_classification, pay_rate,
                       work_city, work_state
                FROM employees
                WHERE org_id = $1
                  AND termination_date IS NULL
                  AND work_location_id IS NULL
                  AND (
                      (LOWER(work_city) = LOWER($2) AND UPPER(work_state) = UPPER($3))
                      OR (work_state IS NULL AND work_city IS NULL
                          AND address IS NOT NULL AND address ILIKE '%' || $2 || '%')
                  )
                """,
                company_id, loc_city, loc_state,
            )
        else:
            heuristic_employees = await conn.fetch(
                """
                SELECT id, first_name, last_name, pay_classification, pay_rate,
                       work_city, work_state
                FROM employees
                WHERE org_id = $1
                  AND termination_date IS NULL
                  AND work_location_id IS NULL
                  AND UPPER(work_state) = UPPER($2)
                  AND (work_city IS NULL OR work_city = '')
                """,
                company_id, loc_state,
            )

        # Deduplicate (in case FK and heuristic overlap during migration)
        seen_ids = {emp["id"] for emp in fk_employees}
        employees = list(fk_employees)
        for emp in heuristic_employees:
            if emp["id"] not in seen_ids:
                employees.append(emp)
                seen_ids.add(emp["id"])

        total_affected = len(employees)

        # Get minimum_wage requirements for this location to check violations
        wage_reqs = await conn.fetch(
            """
            SELECT rate_type, numeric_value, jurisdiction_level
            FROM compliance_requirements
            WHERE location_id = $1 AND category = 'minimum_wage' AND numeric_value IS NOT NULL
            ORDER BY
                CASE jurisdiction_level
                    WHEN 'city' THEN 1
                    WHEN 'county' THEN 2
                    WHEN 'state' THEN 3
                    WHEN 'federal' THEN 4
                    ELSE 5
                END
            """,
            location_id,
        )

        # Build rate_type -> threshold map (first match wins = highest priority jurisdiction)
        thresholds: Dict[str, float] = {}
        for wr in wage_reqs:
            rt = wr["rate_type"] or "general"
            if rt not in thresholds:
                thresholds[rt] = float(wr["numeric_value"])

        # Fallback: check jurisdiction_requirements for missing rate types
        missing_types = {"general", "exempt_salary"} - set(thresholds.keys())
        if missing_types:
            # Try via business_locations.jurisdiction_id first (city-level)
            jr_rows = await conn.fetch(
                """
                SELECT jr.rate_type, jr.numeric_value
                FROM business_locations bl
                JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = bl.jurisdiction_id
                WHERE bl.id = $1
                  AND jr.category = 'minimum_wage'
                  AND jr.numeric_value IS NOT NULL
                  AND jr.rate_type = ANY($2::text[])
                ORDER BY jr.rate_type
                """,
                location_id, list(missing_types),
            )
            for jr in jr_rows:
                rt = jr["rate_type"] or "general"
                if rt not in thresholds:
                    thresholds[rt] = float(jr["numeric_value"])

            # State-level fallback for still-missing types (exempt salary is often state-level)
            still_missing = {"general", "exempt_salary"} - set(thresholds.keys())
            if still_missing and loc_state:
                state_rows = await conn.fetch(
                    """
                    SELECT jr.rate_type, jr.numeric_value
                    FROM jurisdictions j
                    JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
                    WHERE UPPER(j.state) = UPPER($1)
                      AND (j.city IS NULL OR j.city = '' OR LOWER(j.city) = LOWER(j.state))
                      AND jr.category = 'minimum_wage'
                      AND jr.numeric_value IS NOT NULL
                      AND jr.rate_type = ANY($2::text[])
                    ORDER BY jr.numeric_value DESC
                    """,
                    loc_state, list(still_missing),
                )
                for sr in state_rows:
                    rt = sr["rate_type"] or "general"
                    if rt not in thresholds:
                        thresholds[rt] = float(sr["numeric_value"])

            # Final fallback: check compliance_requirements from other same-company
            # same-state locations at jurisdiction_level='state'. This catches exempt_salary
            # thresholds that the AI populated for a different location in the same state.
            still_missing = {"general", "exempt_salary"} - set(thresholds.keys())
            if still_missing and loc_state:
                peer_rows = await conn.fetch(
                    """
                    SELECT cr.rate_type, MAX(cr.numeric_value) AS numeric_value
                    FROM compliance_requirements cr
                    JOIN business_locations bl ON bl.id = cr.location_id
                    WHERE bl.company_id = $1
                      AND UPPER(bl.state) = UPPER($2)
                      AND bl.id != $3
                      AND cr.category = 'minimum_wage'
                      AND cr.jurisdiction_level = 'state'
                      AND cr.numeric_value IS NOT NULL
                      AND cr.rate_type = ANY($4::text[])
                    GROUP BY cr.rate_type
                    """,
                    company_id, loc_state, location_id, list(still_missing),
                )
                for pr in peer_rows:
                    rt = pr["rate_type"] or "general"
                    if rt not in thresholds:
                        thresholds[rt] = float(pr["numeric_value"])

        # Check each employee for wage violations, bucketed by rate_type
        violations_by_rate_type: Dict[str, list] = {}
        for emp in employees:
            if emp["pay_classification"] is None or emp["pay_rate"] is None:
                continue

            rate = float(emp["pay_rate"])
            classification = emp["pay_classification"]

            if classification == "hourly":
                rate_type_key = "general"
            elif classification == "exempt":
                rate_type_key = "exempt_salary"
            else:
                continue

            threshold = thresholds.get(rate_type_key)
            if threshold is not None and rate < threshold:
                violation = {
                    "employee_id": str(emp["id"]),
                    "employee_name": f"{emp['first_name']} {emp['last_name']}",
                    "pay_classification": classification,
                    "pay_rate": rate,
                    "threshold": threshold,
                    "shortfall": round(threshold - rate, 2),
                }
                violations_by_rate_type.setdefault(rate_type_key, []).append(violation)

        employee_names = [
            f"{e['first_name']} {e['last_name']}" for e in employees[:5]
        ]

        return {
            "total_affected": total_affected,
            "employee_names": employee_names,
            "violations_by_rate_type": violations_by_rate_type,
        }


async def get_location_requirements(
    location_id: UUID, company_id: UUID, category: Optional[str] = None
) -> List[RequirementResponse]:
    from ...database import get_connection

    async with get_connection() as conn:
        loc = await conn.fetchrow(
            """SELECT bl.state, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id,
            company_id,
        )
        if not loc:
            return []
        state = loc["state"]
        has_local_ordinance = loc["has_local_ordinance"]

        # source_url_status/statute_citation live on the catalog row
        # (jurisdiction_requirements) and are joined through the SSOT FK at
        # read time — never mirrored, so they can't go stale. Null-FK
        # (Gemini-fresh) rows read as NULL = unchecked / uncited.
        # `authority_*` is the issuing jurisdiction resolved through the catalog
        # FK — the trustworthy answer to "who imposes this?". It is deliberately
        # additive: r.jurisdiction_level / r.jurisdiction_name are free text and
        # several filters below still key on them, so this joins alongside rather
        # than overwriting them.
        query = """
            SELECT r.*, cat.source_url_status, cat.statute_citation, cat.citation_verified_at,
                   cat.metadata -> 'jurisdictional_basis' AS jurisdictional_basis,
                   j.level::text AS authority_level,
                   j.display_name AS authority_display_name
            FROM compliance_requirements r
            JOIN business_locations l ON r.location_id = l.id
            LEFT JOIN jurisdiction_requirements cat
              ON cat.id = r.jurisdiction_requirement_id
            LEFT JOIN jurisdictions j ON j.id = cat.jurisdiction_id
            WHERE l.id = $1 AND l.company_id = $2
        """
        query += await codified_gate_sql("cat", conn=conn)
        params = [location_id, company_id]

        if category:
            query += " AND r.category = $3"
            params.append(category)

        query += " ORDER BY r.category, r.jurisdiction_level"

        rows = await conn.fetch(query, *params)
        row_dicts = [dict(row) for row in rows]
        if has_local_ordinance is False:
            row_dicts = _filter_city_level_requirements(row_dicts, state)
        _normalize_requirement_categories(row_dicts)
        row_dicts = await _filter_requirements_for_company(
            conn, company_id, row_dicts
        )
        filtered = await _filter_with_preemption(conn, row_dicts, state)

        # Enrich with employee impact data
        try:
            impact = await get_employee_impact_for_location(location_id, company_id)
            total_affected = impact["total_affected"]
            employee_names = impact["employee_names"]
            violations_by_rt = impact["violations_by_rate_type"]
        except Exception:
            total_affected = None
            employee_names = []
            violations_by_rt = {}

        def _violation_count_for_row(row: dict) -> Optional[int]:
            if row["category"] != "minimum_wage":
                return None
            rt = row.get("rate_type") or "general"
            return len(violations_by_rt.get(rt, []))

        return [
            RequirementResponse(
                id=str(row["id"]),
                category=row["category"],
                rate_type=row.get("rate_type"),
                applicable_industries=sorted(_requirement_applicable_industries(row))
                or None,
                jurisdiction_level=row["jurisdiction_level"],
                jurisdiction_name=row["jurisdiction_name"],
                title=row["title"],
                description=row["description"],
                current_value=row["current_value"],
                numeric_value=float(row["numeric_value"])
                if row.get("numeric_value") is not None
                else None,
                source_url=row["source_url"],
                source_url_status=row.get("source_url_status"),
                statute_citation=row.get("statute_citation"),
                citation_verified_at=row["citation_verified_at"].isoformat()
                if row.get("citation_verified_at")
                else None,
                jurisdictional_basis=_parse_jsonb_list(row.get("jurisdictional_basis")),
                source_name=row["source_name"],
                effective_date=row["effective_date"].isoformat()
                if row["effective_date"]
                else None,
                previous_value=row["previous_value"],
                last_changed_at=row["last_changed_at"].isoformat()
                if row["last_changed_at"]
                else None,
                affected_employee_count=total_affected,
                affected_employee_names=employee_names or None,
                min_wage_violation_count=_violation_count_for_row(row),
                is_pinned=row.get("is_pinned", False),
                jurisdiction_requirement_id=str(row["jurisdiction_requirement_id"])
                if row.get("jurisdiction_requirement_id")
                else None,
                authority_level=row.get("authority_level"),
                authority_name=_authority_label(
                    row.get("authority_level"), row.get("authority_display_name")
                ),
            )
            for row in filtered
        ]


async def get_company_alerts(
    company_id: UUID,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    location_id: Optional[UUID] = None,
) -> List[AlertResponse]:
    from ...database import get_connection

    async with get_connection() as conn:
        query = """
            SELECT a.*,
                   COALESCE(a.source_url, r.source_url) AS resolved_source_url,
                   COALESCE(a.source_name, r.source_name) AS resolved_source_name
            FROM compliance_alerts a
            LEFT JOIN compliance_requirements r ON a.requirement_id = r.id
            WHERE a.company_id = $1
        """
        params = [company_id]

        if location_id:
            query += f" AND a.location_id = ${len(params) + 1}"
            params.append(location_id)
        if status:
            query += f" AND a.status = ${len(params) + 1}"
            params.append(status)
        if severity:
            query += f" AND a.severity = ${len(params) + 1}"
            params.append(severity)

        query += f" ORDER BY a.created_at DESC LIMIT {limit}"

        rows = await conn.fetch(query, *params)

        def _parse_jsonb(val):
            if val is None:
                return None
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return None
            return val

        # Batch-resolve employee counts per location using precise matching
        location_employee_counts: Dict[str, int] = {}
        if rows:
            location_ids = list({row["location_id"] for row in rows})
            count_rows = await conn.fetch(
                """
                SELECT bl.id AS location_id, COUNT(e.id)::int AS emp_count
                FROM business_locations bl
                LEFT JOIN employees e
                    ON e.org_id = bl.company_id
                    AND e.termination_date IS NULL
                    AND (
                        -- City-level: precise city+state match
                        (bl.city IS NOT NULL AND bl.city != ''
                         AND LOWER(e.work_city) = LOWER(bl.city)
                         AND UPPER(e.work_state) = UPPER(bl.state))
                        -- City-level: office employees matched by address
                        OR (bl.city IS NOT NULL AND bl.city != ''
                            AND e.work_state IS NULL AND e.work_city IS NULL
                            AND e.address IS NOT NULL AND e.address ILIKE '%' || bl.city || '%')
                        -- State-only: employees with state but no specific city
                        OR (bl.city IS NULL OR bl.city = '')
                            AND UPPER(e.work_state) = UPPER(bl.state)
                            AND (e.work_city IS NULL OR e.work_city = '')
                    )
                WHERE bl.id = ANY($1)
                GROUP BY bl.id
                """,
                location_ids,
            )
            for cr in count_rows:
                location_employee_counts[str(cr["location_id"])] = cr["emp_count"]

        return [
            AlertResponse(
                id=str(row["id"]),
                location_id=str(row["location_id"]),
                requirement_id=str(row["requirement_id"])
                if row["requirement_id"]
                else None,
                title=row["title"],
                message=row["message"],
                severity=row["severity"],
                status=row["status"],
                category=row["category"],
                action_required=row["action_required"],
                source_url=row["resolved_source_url"],
                source_name=row["resolved_source_name"],
                deadline=row["deadline"].isoformat() if row["deadline"] else None,
                confidence_score=float(row["confidence_score"])
                if row.get("confidence_score") is not None
                else None,
                verification_sources=_parse_jsonb(row.get("verification_sources")),
                alert_type=row.get("alert_type"),
                effective_date=row["effective_date"].isoformat()
                if row.get("effective_date")
                else None,
                metadata=_parse_jsonb(row.get("metadata")),
                impact_summary=row.get("impact_summary"),
                affected_employee_count=location_employee_counts.get(str(row["location_id"])),
                created_at=row["created_at"].isoformat(),
                read_at=row["read_at"].isoformat() if row["read_at"] else None,
            )
            for row in rows
        ]


async def get_calendar_items(
    company_id: UUID,
    location_id: Optional[UUID] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> List["CalendarItem"]:
    """Compliance-calendar feed: non-dismissed alerts with a deadline,
    plus broad-strokes federal + CA baseline deadlines (W-2, OSHA 300A,
    ACA, EEO-1, Form 5500, CA DE 9 quarters, IIPP, harassment training,
    pay data reporting). Each item has a location context (when known)
    and a derived status bucket the UI groups by. Baseline items have
    synthetic ids prefixed `baseline:` and are read-only — the frontend
    hides dismiss / mark-read on them.
    """
    from ...database import get_connection
    from ..models.compliance import CalendarItem
    from .compliance_baseline import get_baseline_calendar_items
    from datetime import date as _date

    async with get_connection() as conn:
        params: list = [company_id]
        clauses = ["a.company_id = $1", "a.deadline IS NOT NULL", "a.status != 'dismissed'"]

        if location_id is not None:
            params.append(location_id)
            clauses.append(f"a.location_id = ${len(params)}")
        if from_date is not None:
            params.append(from_date)
            clauses.append(f"a.deadline >= ${len(params)}")
        if to_date is not None:
            params.append(to_date)
            clauses.append(f"a.deadline <= ${len(params)}")

        rows = await conn.fetch(
            f"""
            SELECT a.id, a.location_id, a.requirement_id, a.title, a.category,
                   a.severity, a.deadline, a.action_required, a.status,
                   a.created_at,
                   bl.name AS location_name, bl.state AS location_state,
                   COALESCE(r.jurisdiction_name, bl.state) AS jurisdiction_name,
                   (a.deadline - CURRENT_DATE) AS days_until_due
            FROM compliance_alerts a
            LEFT JOIN business_locations bl ON bl.id = a.location_id
            LEFT JOIN compliance_requirements r ON r.id = a.requirement_id
            WHERE {' AND '.join(clauses)}
            ORDER BY a.deadline ASC
            """,
            *params,
        )

        out = []
        for r in rows:
            d = int(r["days_until_due"])
            if d < 0:
                bucket = "overdue"
            elif d <= 30:
                bucket = "due_soon"
            elif d <= 90:
                bucket = "upcoming"
            else:
                bucket = "future"
            out.append(CalendarItem(
                id=str(r["id"]),
                location_id=str(r["location_id"]),
                location_name=r["location_name"],
                location_state=r["location_state"],
                jurisdiction_name=r["jurisdiction_name"],
                requirement_id=str(r["requirement_id"]) if r["requirement_id"] else None,
                title=r["title"],
                category=r["category"],
                severity=r["severity"],
                deadline=r["deadline"].isoformat(),
                derived_status=bucket,
                days_until_due=d,
                action_required=r["action_required"],
                alert_status=r["status"],
                created_at=r["created_at"].isoformat(),
            ))

        # ── Baseline broad-strokes feed.
        # Skip when the caller filters by a specific location: those alerts
        # are scoped, baseline items are company-wide. Also skip if the
        # explicit date window excludes today's lookahead (the from/to
        # filter is rare in practice — the desktop client never sends it).
        if location_id is None:
            employee_count: int = await conn.fetchval(
                """
                SELECT COUNT(*) FROM employees
                WHERE org_id = $1 AND termination_date IS NULL
                """,
                company_id,
            ) or 0
            has_ca = bool(await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE company_id = $1 AND state = 'CA' AND is_active = true LIMIT 1",
                company_id,
            ))
            has_ny = bool(await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE company_id = $1 AND state = 'NY' AND is_active = true LIMIT 1",
                company_id,
            ))
            today = _date.today()
            baseline = get_baseline_calendar_items(
                today=today,
                employee_count=int(employee_count),
                has_ca_location=has_ca,
                has_ny_location=has_ny,
            )
            # Apply the same from/to filter the alert query honors so a
            # caller asking for a specific window isn't surprised by
            # baseline rows outside it.
            if from_date is not None:
                baseline = [b for b in baseline if _date.fromisoformat(b.deadline) >= from_date]
            if to_date is not None:
                baseline = [b for b in baseline if _date.fromisoformat(b.deadline) <= to_date]
            out.extend(baseline)
            out.sort(key=lambda i: i.deadline)

        return out


async def mark_alert_read(alert_id: UUID, company_id: UUID) -> bool:
    from ...database import get_connection
    from datetime import datetime

    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE compliance_alerts SET status = 'read', read_at = NOW() WHERE id = $1 AND company_id = $2",
            alert_id,
            company_id,
        )
        return result == "UPDATE 1"


async def dismiss_alert(alert_id: UUID, company_id: UUID) -> bool:
    from ...database import get_connection
    from datetime import datetime

    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE compliance_alerts SET status = 'dismissed', dismissed_at = NOW() WHERE id = $1 AND company_id = $2",
            alert_id,
            company_id,
        )
        return result == "UPDATE 1"


async def record_verification_feedback(
    alert_id: UUID,
    user_id: UUID,
    actual_is_change: bool,
    admin_notes: Optional[str] = None,
    correction_reason: Optional[str] = None,
    company_id: Optional[UUID] = None,
) -> bool:
    """Record admin feedback on a verification outcome for calibration.

    Args:
        alert_id: The alert being reviewed
        user_id: The admin reviewing
        actual_is_change: Whether the change actually occurred
        admin_notes: Optional notes explaining the decision
        correction_reason: Category of error if prediction was wrong (misread_date, wrong_jurisdiction, hallucination, etc.)
        company_id: The company owning the alert (for security verification)

    Returns:
        True if feedback was recorded, False if no matching outcome found or unauthorized
    """
    from ...database import get_connection

    async with get_connection() as conn:
        # Security: Verify the alert belongs to the caller's company
        if company_id is not None:
            alert_company = await conn.fetchval(
                "SELECT company_id FROM compliance_alerts WHERE id = $1",
                alert_id,
            )
            if alert_company is None or alert_company != company_id:
                print(
                    f"[Compliance] Unauthorized feedback attempt: alert {alert_id} not owned by company {company_id}"
                )
                return False

        # First, fetch the outcome data for reputation update (Phase 3.2)
        outcome_row = await conn.fetchrow(
            """
            SELECT jurisdiction_id, predicted_is_change, verification_sources
            FROM verification_outcomes
            WHERE alert_id = $1
            """,
            alert_id,
        )

        # Update the verification outcome
        result = await conn.execute(
            """
            UPDATE verification_outcomes
            SET actual_is_change = $1,
                reviewed_by = $2,
                reviewed_at = NOW(),
                admin_notes = $3,
                correction_reason = $4
            WHERE alert_id = $5
            """,
            actual_is_change,
            user_id,
            admin_notes,
            correction_reason,
            alert_id,
        )

        updated = "UPDATE 1" in result

        # Phase 3.2: Update source reputation based on accuracy
        if updated and outcome_row:
            jurisdiction_id = outcome_row["jurisdiction_id"]
            predicted_is_change = outcome_row["predicted_is_change"]
            verification_sources = outcome_row["verification_sources"]

            if jurisdiction_id and verification_sources:
                # Determine if the sources were accurate
                # Sources are accurate if the prediction matched reality
                was_accurate = predicted_is_change == actual_is_change

                # Parse sources if stored as JSON string
                sources = verification_sources
                if isinstance(sources, str):
                    try:
                        sources = json.loads(sources)
                    except (json.JSONDecodeError, TypeError):
                        sources = []

                if sources:
                    await update_source_reputation(
                        conn, jurisdiction_id, sources, was_accurate
                    )

        return updated


async def get_calibration_stats(
    category: Optional[str] = None,
    days: int = 30,
) -> dict:
    """Get confidence calibration statistics for analysis.

    Returns aggregated stats on prediction accuracy by confidence bucket.
    """
    from ...database import get_connection

    async with get_connection() as conn:
        query = """
            SELECT
                CASE
                    WHEN predicted_confidence >= 0.8 THEN 'high (0.8+)'
                    WHEN predicted_confidence >= 0.6 THEN 'medium (0.6-0.8)'
                    WHEN predicted_confidence >= 0.3 THEN 'low (0.3-0.6)'
                    ELSE 'very_low (<0.3)'
                END as confidence_bucket,
                COUNT(*) as total,
                COUNT(actual_is_change) as reviewed,
                SUM(CASE WHEN predicted_is_change = actual_is_change THEN 1 ELSE 0 END) as correct,
                AVG(predicted_confidence) as avg_confidence
            FROM verification_outcomes
            WHERE created_at > NOW() - INTERVAL '1 day' * $1
        """
        params = [days]
        if category:
            query += " AND category = $2"
            params.append(category)
        query += " GROUP BY confidence_bucket ORDER BY avg_confidence DESC"

        rows = await conn.fetch(query, *params)
        return {
            "buckets": [dict(r) for r in rows],
            "days": days,
            "category_filter": category,
        }


async def get_recent_corrections(
    jurisdiction_id: UUID,
    category: Optional[str] = None,
    limit: int = 5,
    conn=None,
) -> List[Dict]:
    """Get recent false positive corrections for a jurisdiction.

    Used in Phase 3.1 to inject correction context into future research prompts.

    ``conn``: use this connection instead of borrowing the app pool. Required from
    CELERY WORKERS — they are deliberately pool-free (each task runs its own
    asyncio loop; an asyncpg pool bound to another loop cannot be reused), so
    ``get_connection()`` raises there. Without it, every research call made from
    the vertical-coverage sweep died here, BEFORE reaching Gemini, and the ledger
    recorded the cells as failed.

    Returns:
        List of dicts with: requirement_key, category, correction_reason, admin_notes, created_at
    """
    from ...database import get_connection
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _borrowed():
        yield conn

    holder = _borrowed() if conn is not None else get_connection()

    async with holder as conn:
        query = """
            SELECT
                vo.requirement_key,
                vo.category,
                vo.correction_reason,
                vo.admin_notes,
                vo.created_at,
                ca.title as alert_title
            FROM verification_outcomes vo
            LEFT JOIN compliance_alerts ca ON vo.alert_id = ca.id
            WHERE vo.jurisdiction_id = $1
              AND vo.actual_is_change = false
              AND vo.predicted_is_change = true
              AND vo.reviewed_at IS NOT NULL
        """
        params = [jurisdiction_id]
        if category:
            query += " AND vo.category = $2"
            params.append(category)
        query += " ORDER BY vo.created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]


def format_corrections_for_prompt(corrections: List[Dict]) -> str:
    """Format corrections list into a prompt-friendly string."""
    if not corrections:
        return ""

    lines = ["PREVIOUS ERRORS TO AVOID (false positives from past research):"]
    for c in corrections:
        reason = c.get("correction_reason") or "unspecified"
        title = c.get("alert_title") or c.get("requirement_key", "unknown")
        notes = c.get("admin_notes")
        line = f"- {title}: marked as false positive (reason: {reason})"
        if notes:
            line += f" — Admin note: {notes}"
        lines.append(line)

    return "\n".join(lines)


async def get_compliance_summary(company_id: UUID) -> ComplianceSummary:
    from ...database import get_connection

    async with get_connection() as conn:
        # Resolved once, outside the per-location loop below.
        gate = await codified_gate_sql("cat", conn=conn)
        locations = await conn.fetch(
            """SELECT bl.*, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.company_id = $1""",
            company_id,
        )

        total_requirements = 0
        unread_alerts = 0
        critical_alerts = 0
        recent_changes = []
        auto_check_count = 0

        for loc in locations:
            if loc.get("auto_check_enabled", True):
                auto_check_count += 1

            reqs = await conn.fetch(
                "SELECT r.* FROM compliance_requirements r "
                "LEFT JOIN jurisdiction_requirements cat "
                "  ON cat.id = r.jurisdiction_requirement_id "
                "WHERE r.location_id = $1" + gate,
                loc["id"],
            )
            req_dicts = [dict(r) for r in reqs]
            if loc.get("has_local_ordinance") is False:
                req_dicts = _filter_city_level_requirements(req_dicts, loc["state"])
            _normalize_requirement_categories(req_dicts)
            req_dicts = await _filter_requirements_for_company(
                conn, loc["company_id"], req_dicts
            )
            filtered_reqs = await _filter_with_preemption(conn, req_dicts, loc["state"])
            total_requirements += len(filtered_reqs)

            for req in filtered_reqs:
                if req["last_changed_at"]:
                    recent_changes.append(
                        {
                            "location": loc["name"] or f"{loc['city']}, {loc['state']}",
                            "category": req["category"],
                            "title": req["title"],
                            "old_value": req["previous_value"],
                            "new_value": req["current_value"],
                            "changed_at": req["last_changed_at"].isoformat(),
                        }
                    )

            alerts = await conn.fetch(
                "SELECT * FROM compliance_alerts WHERE location_id = $1",
                loc["id"],
            )
            for alert in alerts:
                if alert["status"] == "unread":
                    unread_alerts += 1
                    if alert["severity"] == "critical":
                        critical_alerts += 1

        recent_changes.sort(key=lambda x: x["changed_at"], reverse=True)
        recent_changes = recent_changes[:10]

        # Get nearest upcoming deadlines
        upcoming_rows = await conn.fetch(
            """
            SELECT ul.title, ul.expected_effective_date, ul.current_status, ul.category,
                   bl.name AS location_name, bl.city, bl.state
            FROM upcoming_legislation ul
            JOIN business_locations bl ON ul.location_id = bl.id
            WHERE ul.company_id = $1
              AND ul.current_status NOT IN ('effective', 'dismissed')
              AND ul.expected_effective_date IS NOT NULL
              AND ul.expected_effective_date > CURRENT_DATE
            ORDER BY ul.expected_effective_date ASC
            LIMIT 3
            """,
            company_id,
        )
        upcoming_deadlines = []
        now = datetime.utcnow().date()
        for row in upcoming_rows:
            days = (row["expected_effective_date"] - now).days
            upcoming_deadlines.append(
                {
                    "title": row["title"],
                    "effective_date": row["expected_effective_date"].isoformat(),
                    "days_until": days,
                    "status": row["current_status"],
                    "category": row["category"],
                    "location": row["location_name"]
                    or f"{row['city']}, {row['state']}",
                }
            )

        return ComplianceSummary(
            total_locations=len(locations),
            total_requirements=total_requirements,
            unread_alerts=unread_alerts,
            critical_alerts=critical_alerts,
            recent_changes=recent_changes,
            auto_check_locations=auto_check_count,
            upcoming_deadlines=upcoming_deadlines,
        )


async def get_compliance_dashboard(company_id: UUID, horizon_days: int = 90) -> dict:
    """
    Return a compliance dashboard with actionable tasks for each upcoming change.
    """
    from ...database import get_connection

    def _parse_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def _parse_iso_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
        return None

    def _derive_sla_state(
        action_status: Optional[str],
        due_date: Optional[date],
        has_owner: bool,
        today: date,
    ) -> str:
        if action_status == "actioned":
            return "completed"
        if due_date and due_date < today:
            return "overdue"
        if due_date and (due_date - today).days <= 7:
            return "due_soon"
        if not has_owner:
            return "unassigned"
        return "on_track"

    default_playbooks = {
        "minimum_wage": "Audit pay bands and update payroll before the effective date.",
        "sick_leave": "Update sick leave policy language and accrual settings.",
        "overtime": "Review exempt/non-exempt classifications and overtime rules.",
        "pay_frequency": "Confirm payroll schedule and notice requirements.",
        "final_pay": "Align offboarding checklist with final pay timing rules.",
        "posting_requirements": "Refresh workplace posting packets and manager notices.",
    }

    async with get_connection() as conn:
        # ── 1. Fetch all company locations ──────────────────────────────────
        locations = await conn.fetch(
            """
            SELECT id, name, city, state, company_id
            FROM business_locations
            WHERE company_id = $1 AND is_active = true
            """,
            company_id,
        )
        location_map: dict[UUID, dict] = {row["id"]: dict(row) for row in locations}

        if not location_map:
            return {
                "kpis": {
                    "total_locations": 0,
                    "unread_alerts": 0,
                    "critical_alerts": 0,
                    "employees_at_risk": 0,
                    "overdue_actions": 0,
                    "assigned_actions": 0,
                    "unassigned_actions": 0,
                },
                "coming_up": [],
            }

        # ── 2. Fetch upcoming legislation within horizon ─────────────────────
        cutoff = datetime.utcnow().date() + timedelta(days=horizon_days)
        legislation_rows = await conn.fetch(
            """
            SELECT ul.id, ul.location_id, ul.title, ul.description, ul.category,
                   ul.current_status, ul.expected_effective_date, ul.impact_summary,
                   ul.source_url, ul.confidence, ul.created_at,
                   ca.id AS alert_id,
                   ca.severity,
                   ca.status AS alert_status,
                   ca.action_required,
                   ca.deadline AS alert_deadline,
                   ca.metadata AS alert_metadata
            FROM upcoming_legislation ul
            LEFT JOIN LATERAL (
                SELECT ca.id, ca.severity, ca.status, ca.action_required, ca.deadline, ca.metadata, ca.created_at
                FROM compliance_alerts ca
                WHERE ca.company_id = ul.company_id
                  AND ca.location_id = ul.location_id
                  AND ca.alert_type = 'upcoming_legislation'
                  AND ca.status <> 'dismissed'
                  AND ca.metadata->>'legislation_id' = ul.id::text
                ORDER BY
                    CASE ca.status
                        WHEN 'unread' THEN 0
                        WHEN 'read' THEN 1
                        WHEN 'actioned' THEN 2
                        ELSE 3
                    END,
                    CASE ca.severity
                        WHEN 'critical' THEN 0
                        WHEN 'warning' THEN 1
                        ELSE 2
                    END,
                    ca.created_at DESC
                LIMIT 1
            ) ca ON true
            WHERE ul.company_id = $1
              AND ul.current_status NOT IN ('effective', 'dismissed')
              AND (
                    ul.expected_effective_date IS NULL
                    OR ul.expected_effective_date <= $2
              )
            ORDER BY ul.expected_effective_date ASC NULLS LAST, ul.created_at DESC
            """,
            company_id,
            cutoff,
        )

        # ── 3. Fetch alert KPIs ──────────────────────────────────────────────
        alert_kpi_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'unread') AS unread_alerts,
                COUNT(*) FILTER (WHERE status = 'unread' AND severity = 'critical') AS critical_alerts
            FROM compliance_alerts
            WHERE company_id = $1
            """,
            company_id,
        )
        unread_alerts = int(alert_kpi_row["unread_alerts"] or 0)
        critical_alerts = int(alert_kpi_row["critical_alerts"] or 0)

        # ── 4. Build state → employees mapping (state_estimate logic) ────────
        # We gather all active employees for the company grouped by work_state.
        employee_rows = await conn.fetch(
            """
            SELECT id, first_name, last_name, work_state
            FROM employees
            WHERE org_id = $1
              AND termination_date IS NULL
              AND work_state IS NOT NULL
            ORDER BY last_name, first_name
            """,
            company_id,
        )

        # state → list of {id, name}
        state_employee_map: dict[str, list[dict]] = {}
        for emp in employee_rows:
            st = (emp["work_state"] or "").upper().strip()
            if not st:
                continue
            state_employee_map.setdefault(st, []).append(
                {
                    "id": str(emp["id"]),
                    "name": f"{emp['first_name']} {emp['last_name']}",
                }
            )

        # Unique states covered by company locations
        location_states = {loc["state"].upper() for loc in locations}
        # Total employees whose state is a company location state
        employees_at_risk: set[str] = set()
        for st in location_states:
            for emp in state_employee_map.get(st, []):
                employees_at_risk.add(emp["id"])

        # Resolve action owner display names for any owner IDs carried in alert metadata.
        owner_ids: set[UUID] = set()
        for row in legislation_rows:
            metadata = _parse_metadata(row.get("alert_metadata"))
            owner_id_raw = metadata.get("action_owner_id")
            if isinstance(owner_id_raw, str) and owner_id_raw.strip():
                try:
                    owner_ids.add(UUID(owner_id_raw))
                except ValueError:
                    continue

        owner_name_map: dict[str, str] = {}
        if owner_ids:
            owner_rows = await conn.fetch(
                """
                SELECT u.id,
                       COALESCE(c.name, a.name, u.email) AS display_name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id AND c.company_id = $2
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id = ANY($1::uuid[])
                """,
                list(owner_ids),
                company_id,
            )
            owner_name_map = {
                str(row["id"]): row["display_name"] for row in owner_rows if row["id"]
            }

        # ── 5. Deduplicate + enrich legislation items ────────────────────────
        now = datetime.utcnow().date()
        seen_leg_ids: set = set()
        coming_up = []

        for row in legislation_rows:
            leg_id = str(row["id"])
            if leg_id in seen_leg_ids:
                continue
            seen_leg_ids.add(leg_id)

            loc = location_map.get(row["location_id"])
            if not loc:
                continue

            loc_state = loc["state"].upper()
            affected = state_employee_map.get(loc_state, [])

            effective_date = row["expected_effective_date"]
            days_until = (effective_date - now).days if effective_date else None

            alert_metadata = _parse_metadata(row.get("alert_metadata"))
            owner_id_raw = alert_metadata.get("action_owner_id")
            owner_id = None
            if isinstance(owner_id_raw, str) and owner_id_raw.strip():
                try:
                    owner_id = str(UUID(owner_id_raw))
                except ValueError:
                    owner_id = None

            owner_name_raw = alert_metadata.get("action_owner_name")
            owner_name = (
                owner_name_raw.strip()
                if isinstance(owner_name_raw, str) and owner_name_raw.strip()
                else (owner_name_map.get(owner_id) if owner_id else None)
            )

            action_due_date = (
                _parse_iso_date(alert_metadata.get("action_due_date"))
                or row.get("alert_deadline")
                or effective_date
            )
            next_action = (
                (alert_metadata.get("next_action") or "").strip()
                if isinstance(alert_metadata.get("next_action"), str)
                else None
            ) or row.get("action_required")
            if not next_action:
                next_action = "Review legal impact and confirm operational changes."

            recommended_playbook = (
                (alert_metadata.get("recommended_playbook") or "").strip()
                if isinstance(alert_metadata.get("recommended_playbook"), str)
                else ""
            )
            if not recommended_playbook:
                recommended_playbook = default_playbooks.get(
                    row["category"], "Review impact, assign owner, and track completion."
                )

            estimated_financial_impact_raw = alert_metadata.get(
                "estimated_financial_impact"
            )
            estimated_financial_impact = None
            if isinstance(estimated_financial_impact_raw, (str, int, float)):
                estimated_financial_impact = str(estimated_financial_impact_raw).strip()
                if not estimated_financial_impact:
                    estimated_financial_impact = None

            action_status = row.get("alert_status") or "untracked"
            sla_state = _derive_sla_state(
                action_status=action_status,
                due_date=action_due_date,
                has_owner=owner_id is not None,
                today=now,
            )
            is_overdue = sla_state == "overdue"

            # Infer severity bucket if no linked alert found
            raw_severity = row["severity"]
            if not raw_severity:
                if days_until is not None and days_until <= 30:
                    raw_severity = "critical"
                elif days_until is not None and days_until <= 60:
                    raw_severity = "warning"
                else:
                    raw_severity = "info"

            coming_up.append(
                {
                    "legislation_id": leg_id,
                    "title": row["title"],
                    "description": row["description"] or row["impact_summary"],
                    "category": row["category"],
                    "severity": raw_severity,
                    "status": row["current_status"],
                    "effective_date": effective_date.isoformat()
                    if effective_date
                    else None,
                    "days_until": days_until,
                    "location_id": str(row["location_id"]),
                    "location_name": loc["name"] or f"{loc['city']}, {loc['state']}",
                    "location_state": loc_state,
                    "alert_id": str(row["alert_id"]) if row.get("alert_id") else None,
                    "action_status": action_status,
                    "next_action": next_action,
                    "action_owner_id": owner_id,
                    "action_owner_name": owner_name,
                    "action_due_date": action_due_date.isoformat()
                    if action_due_date
                    else None,
                    "is_overdue": is_overdue,
                    "sla_state": sla_state,
                    "recommended_playbook": recommended_playbook,
                    "estimated_financial_impact": estimated_financial_impact,
                    "affected_employee_count": len(affected),
                    "affected_employee_sample": [e["name"] for e in affected[:5]],
                    "impact_basis": "state_estimate",
                    "source_url": row["source_url"],
                }
            )

        overdue_actions = 0
        assigned_actions = 0
        unassigned_actions = 0
        for item in coming_up:
            if item.get("action_status") == "actioned":
                continue
            if item.get("is_overdue"):
                overdue_actions += 1
            if item.get("action_owner_id"):
                assigned_actions += 1
            else:
                unassigned_actions += 1

        return {
            "kpis": {
                "total_locations": len(location_map),
                "unread_alerts": unread_alerts,
                "critical_alerts": critical_alerts,
                "employees_at_risk": len(employees_at_risk),
                "overdue_actions": overdue_actions,
                "assigned_actions": assigned_actions,
                "unassigned_actions": unassigned_actions,
            },
            "coming_up": coming_up,
        }


async def update_alert_action_plan(
    alert_id: UUID,
    company_id: UUID,
    updates: Dict[str, Any],
    actor_user_id: Optional[UUID] = None,
) -> Optional[dict]:
    """Update alert action-plan metadata and optionally mark the alert as actioned."""
    from ...database import get_connection

    def _parse_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def _set_metadata_value(target: dict[str, Any], key: str, value: Any) -> None:
        if value is None:
            target.pop(key, None)
            return
        if isinstance(value, str) and not value.strip():
            target.pop(key, None)
            return
        target[key] = value

    if not updates:
        return None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status, metadata, action_required, deadline
            FROM compliance_alerts
            WHERE id = $1 AND company_id = $2
            """,
            alert_id,
            company_id,
        )
        if not row:
            return None

        metadata = _parse_metadata(row.get("metadata"))

        if "action_owner_id" in updates:
            owner = updates.get("action_owner_id")
            _set_metadata_value(
                metadata, "action_owner_id", str(owner) if owner is not None else None
            )

        if "next_action" in updates:
            _set_metadata_value(metadata, "next_action", updates.get("next_action"))

        if "action_due_date" in updates:
            due_date = updates.get("action_due_date")
            _set_metadata_value(
                metadata,
                "action_due_date",
                due_date.isoformat() if isinstance(due_date, date) else None,
            )

        if "recommended_playbook" in updates:
            _set_metadata_value(
                metadata, "recommended_playbook", updates.get("recommended_playbook")
            )

        if "estimated_financial_impact" in updates:
            _set_metadata_value(
                metadata,
                "estimated_financial_impact",
                updates.get("estimated_financial_impact"),
            )

        metadata["action_plan_updated_at"] = datetime.utcnow().isoformat()
        if actor_user_id is not None:
            metadata["action_plan_updated_by"] = str(actor_user_id)

        new_status = row["status"]
        if "mark_actioned" in updates:
            should_mark_actioned = bool(updates.get("mark_actioned"))
            if should_mark_actioned:
                new_status = "actioned"
            elif row["status"] == "actioned":
                new_status = "read"

        next_action_value = row["action_required"]
        if "next_action" in updates:
            raw_next_action = updates.get("next_action")
            if isinstance(raw_next_action, str):
                raw_next_action = raw_next_action.strip()
            next_action_value = raw_next_action or None

        deadline_value = row["deadline"]
        if "action_due_date" in updates:
            action_due_date = updates.get("action_due_date")
            deadline_value = action_due_date if isinstance(action_due_date, date) else None

        updated = await conn.fetchrow(
            """
            UPDATE compliance_alerts
            SET metadata = $3::jsonb,
                status = $4,
                action_required = $5,
                deadline = $6,
                read_at = CASE
                    WHEN $4 IN ('read', 'actioned') THEN COALESCE(read_at, NOW())
                    ELSE read_at
                END
            WHERE id = $1 AND company_id = $2
            RETURNING id, status, action_required, deadline, metadata
            """,
            alert_id,
            company_id,
            json.dumps(metadata),
            new_status,
            next_action_value,
            deadline_value,
        )
        if not updated:
            return None

        updated_metadata = _parse_metadata(updated["metadata"])
        return {
            "alert_id": str(updated["id"]),
            "status": updated["status"],
            "next_action": updated["action_required"],
            "action_due_date": updated["deadline"].isoformat()
            if updated["deadline"]
            else None,
            "metadata": updated_metadata,
        }


async def update_auto_check_settings(
    location_id: UUID, company_id: UUID, settings: AutoCheckSettings
) -> Optional[BusinessLocation]:
    """Update auto-check settings for a location."""
    from ...database import get_connection

    async with get_connection() as conn:
        updates = []
        params = []
        param_idx = 3

        if settings.auto_check_enabled is not None:
            updates.append(f"auto_check_enabled = ${param_idx}")
            params.append(settings.auto_check_enabled)
            param_idx += 1
        if settings.auto_check_interval_days is not None:
            updates.append(f"auto_check_interval_days = ${param_idx}")
            params.append(settings.auto_check_interval_days)
            param_idx += 1

        if not updates:
            return await get_location(location_id, company_id)

        # Recompute next_auto_check
        if settings.auto_check_enabled is not None and not settings.auto_check_enabled:
            updates.append("next_auto_check = NULL")
        else:
            if settings.auto_check_interval_days is not None:
                interval = settings.auto_check_interval_days
            else:
                # Use the persisted interval so re-enabling doesn't reset to 7
                updates.append(
                    f"next_auto_check = NOW() + INTERVAL '1 day' * auto_check_interval_days"
                )
                interval = None
            if interval is not None:
                updates.append(
                    f"next_auto_check = NOW() + INTERVAL '1 day' * ${param_idx}"
                )
                params.append(interval)
                param_idx += 1

        updates.append("updated_at = NOW()")
        params.insert(0, location_id)
        params.insert(1, company_id)

        await conn.execute(
            f"UPDATE business_locations SET {', '.join(updates)} WHERE id = $1 AND company_id = $2",
            *params,
        )
        return await get_location(location_id, company_id)


async def get_check_log(
    location_id: UUID, company_id: UUID, limit: int = 20
) -> List[CheckLogEntry]:
    """Get compliance check history for a location."""
    from ...database import get_connection

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM compliance_check_log
            WHERE location_id = $1 AND company_id = $2
            ORDER BY started_at DESC
            LIMIT $3
            """,
            location_id,
            company_id,
            limit,
        )
        return [
            CheckLogEntry(
                id=str(row["id"]),
                location_id=str(row["location_id"]),
                company_id=str(row["company_id"]),
                check_type=row["check_type"],
                status=row["status"],
                started_at=row["started_at"].isoformat(),
                completed_at=row["completed_at"].isoformat()
                if row["completed_at"]
                else None,
                new_count=row["new_count"] or 0,
                updated_count=row["updated_count"] or 0,
                alert_count=row["alert_count"] or 0,
                error_message=row["error_message"],
            )
            for row in rows
        ]


async def get_upcoming_legislation(
    location_id: UUID, company_id: UUID
) -> List[UpcomingLegislationResponse]:
    """Get upcoming legislation for a location."""
    from ...database import get_connection

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM upcoming_legislation
            WHERE location_id = $1 AND company_id = $2
              AND current_status NOT IN ('effective', 'dismissed')
            ORDER BY expected_effective_date ASC NULLS LAST
            """,
            location_id,
            company_id,
        )
        now = datetime.utcnow().date()

        responses: list[UpcomingLegislationResponse] = []
        for row in rows:
            effective_date = row["expected_effective_date"]
            normalized_status = _normalize_legislation_status(
                row["current_status"], effective_date
            )

            if normalized_status != row["current_status"]:
                await conn.execute(
                    "UPDATE upcoming_legislation SET current_status = $1, updated_at = NOW() WHERE id = $2",
                    normalized_status,
                    row["id"],
                )

            # Keep this endpoint focused on upcoming/not-yet-effective items.
            if normalized_status in {"effective", "dismissed"}:
                continue

            responses.append(
                UpcomingLegislationResponse(
                    id=str(row["id"]),
                    location_id=str(row["location_id"]),
                    category=row["category"],
                    title=row["title"],
                    description=row["description"],
                    current_status=normalized_status,
                    expected_effective_date=effective_date.isoformat()
                    if effective_date
                    else None,
                    impact_summary=row["impact_summary"],
                    source_url=row["source_url"],
                    source_name=row["source_name"],
                    confidence=float(row["confidence"])
                    if row["confidence"] is not None
                    else None,
                    days_until_effective=(effective_date - now).days
                    if effective_date
                    else None,
                    created_at=row["created_at"].isoformat(),
                )
            )

        return responses


async def run_compliance_check_background(
    location_id: UUID,
    company_id: UUID,
    check_type: str = "scheduled",
    allow_live_research: bool = True,
    allow_repository_refresh: bool = True,
) -> Dict[str, Any]:
    """Non-streaming compliance check for Celery tasks.
    Checks the jurisdiction repository first; only calls Gemini if stale/missing.
    Returns summary dict.

    ``allow_repository_refresh=False`` makes this call a pure projection from
    whatever the shared catalog already has — zero Gemini calls, including the
    facility-inference call and the shared-jurisdiction gap-fill (see the
    matching flag on ``run_compliance_check_stream`` for why that gap-fill
    needed its own gate separate from ``allow_live_research``). The daily
    per-tenant sweep (``workers/tasks/compliance_checks.py``) passes False:
    catalog freshness is our job on our own schedule, not a side effect of a
    scheduled tenant sync.
    """
    from ...database import get_connection
    from .gemini_compliance import get_gemini_compliance_service

    location = await get_location(location_id, company_id)
    if not location:
        return {"error": "Location not found", "new": 0, "updated": 0, "alerts": 0}

    service = get_gemini_compliance_service()
    used_repository = False
    change_email_items: List[Dict[str, str]] = []
    requirements: List[Dict[str, Any]] = []
    cached_requirements_for_merge: List[Dict[str, Any]] = []
    research_categories: Optional[List[str]] = None
    industry_context: str = ""
    source_context: str = ""
    corrections_context: str = ""
    preemption_rules: Dict[str, bool] = {}
    new_count = 0
    updated_count = 0
    alert_count = 0

    async with get_connection() as conn:
        # Load industry profile for industry-aware research prompts
        industry_profile = await _get_industry_profile(conn, company_id)
        if industry_profile:
            industry_context = industry_profile.get("industry_context", "")

        log_id = await _create_check_log(conn, location_id, company_id, check_type)

        try:
            # Resolve jurisdiction
            jurisdiction_id = location.jurisdiction_id
            if not jurisdiction_id:
                jurisdiction_id = await _get_or_create_jurisdiction(
                    conn, location.city, location.state, location.county, location.zipcode
                )
                await conn.execute(
                    "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
                    jurisdiction_id,
                    location_id,
                )

            # Look up whether this city has its own local ordinance
            has_local_ordinance = await _lookup_has_local_ordinance(
                conn, location.city, location.state
            )

            # ── Facility Inference for healthcare companies ──
            # This is itself a Gemini call, gated the same as the repository
            # refresh below: a projection-only run must not spend here either.
            canonical_industry = industry_profile.get("canonical_industry") if industry_profile else None
            if canonical_industry == "healthcare" and allow_repository_refresh:
                fa = location.facility_attributes
                if isinstance(fa, str):
                    try:
                        fa = json.loads(fa)
                    except (json.JSONDecodeError, TypeError):
                        fa = None
                has_entity_type = fa and fa.get("entity_type")
                if not has_entity_type:
                    try:
                        comp_row = await conn.fetchrow(
                            "SELECT name, industry, healthcare_specialties FROM companies WHERE id = $1",
                            company_id,
                        )
                        if comp_row:
                            inference = await service.infer_facility_profile(
                                company_name=comp_row["name"] or "",
                                industry=comp_row["industry"] or "",
                                healthcare_specialties=comp_row["healthcare_specialties"],
                                city=location.city,
                                state=location.state,
                            )
                            if inference and inference.get("confidence", 0) >= 0.5:
                                inferred_attrs = {
                                    "entity_type": inference["entity_type"],
                                    "payer_contracts": inference.get("likely_payer_contracts", []),
                                }
                                merged = (fa or {})
                                merged.update(inferred_attrs)
                                await conn.execute(
                                    "UPDATE business_locations SET facility_attributes = $1, updated_at = NOW() WHERE id = $2",
                                    json.dumps(merged), location_id,
                                )
                                row = await conn.fetchrow(
                                    "SELECT * FROM business_locations WHERE id = $1 AND company_id = $2",
                                    location_id, company_id,
                                )
                                if row:
                                    location = BusinessLocation(**dict(row))
                                print(
                                    f"[Facility Inference] Auto-set {inference['entity_type']} "
                                    f"for {location.name or location.city}"
                                )
                    except Exception as e:
                        print(f"[Facility Inference] Error during auto-inference: {e}")

            # TIER 1: Check for fresh structured data from authoritative sources
            from .structured_data import StructuredDataService

            structured_service = StructuredDataService()

            tier1_data = await structured_service.get_tier1_data(
                conn,
                jurisdiction_id,
                city=location.city,
                state=location.state,
                county=location.county,
                categories=["minimum_wage"],
                freshness_hours=168,
                triggered_by="background_check",
            )

            # Check repository freshness threshold
            threshold = location.auto_check_interval_days or 7

            if tier1_data:
                # Tier 1 only covers a subset of categories (minimum_wage).
                # Merge with repository data for other categories.
                tier1_categories = {
                    _normalize_category(r.get("category")) or r.get("category")
                    for r in tier1_data
                }
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                repo_reqs = [
                    _jurisdiction_row_to_dict(jr)
                    for jr in j_reqs
                    if (_normalize_category(jr.get("category")) or jr.get("category"))
                    not in tier1_categories
                ]
                requirements = tier1_data + repo_reqs
                missing_categories = _missing_required_categories(requirements)
                if missing_categories:
                    research_categories = missing_categories
                    cached_requirements_for_merge = list(requirements)
                    print(
                        f"[Compliance] Coverage gap for {location.city}, {location.state} "
                        f"({', '.join(missing_categories)}); running live research."
                    )
                else:
                    used_repository = True
            elif await _is_jurisdiction_fresh(conn, jurisdiction_id, threshold):
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]

                await _fill_missing_categories_from_parents(
                    conn, jurisdiction_id, requirements, threshold
                )

                missing_categories = _missing_required_categories(requirements)
                if missing_categories:
                    research_categories = missing_categories
                    cached_requirements_for_merge = list(requirements)
                    print(
                        f"[Compliance] Fresh cache missing categories for {location.city}, {location.state}: "
                        f"{', '.join(missing_categories)}. Running live research."
                    )
                else:
                    used_repository = True

            # Industry-specific check (same logic as streaming path)
            if used_repository and industry_context and industry_profile:
                focused = industry_profile.get("focused_categories") or []
                industry_rt = industry_profile.get("rate_types") or []
                if focused and industry_rt:
                    has_industry_data = await conn.fetchval(
                        """SELECT EXISTS(
                            SELECT 1 FROM compliance_requirements
                            WHERE location_id = $1 AND rate_type = ANY($2::text[])
                        )""",
                        location_id,
                        industry_rt,
                    )
                    if not has_industry_data:
                        used_repository = False
                        research_categories = focused
                        cached_requirements_for_merge = list(requirements)
                        print(
                            f"[Compliance] Researching industry-specific requirements for "
                            f"{location.city}, {location.state}"
                        )

            # TIER 2.5: County/State data reuse for no-local-ordinance cities
            if not used_repository and has_local_ordinance is False:
                county_reqs = await _try_load_county_requirements(
                    conn, jurisdiction_id, threshold
                )
                if county_reqs:
                    requirements = county_reqs

                    await _fill_missing_categories_from_parents(
                        conn, jurisdiction_id, requirements, threshold
                    )

                    missing_categories = _missing_required_categories(requirements)
                    if missing_categories:
                        research_categories = missing_categories
                        cached_requirements_for_merge = list(requirements)
                        print(
                            f"[Compliance] Cache missing categories for {location.city}, {location.state}: "
                            f"{', '.join(missing_categories)}. Running live research."
                        )
                    else:
                        used_repository = True
                else:
                    state_reqs = await _try_load_state_requirements(
                        conn, jurisdiction_id, threshold
                    )
                    if state_reqs:
                        requirements = state_reqs

                        await _fill_missing_categories_from_parents(
                            conn, jurisdiction_id, requirements, threshold
                        )

                        missing_categories = _missing_required_categories(requirements)
                        if missing_categories:
                            research_categories = missing_categories
                            cached_requirements_for_merge = list(requirements)
                            print(
                                f"[Compliance] State cache missing categories for {location.city}, {location.state}: "
                                f"{', '.join(missing_categories)}. Running live research."
                            )
                        else:
                            used_repository = True

            # TIER 3: Research with Gemini (stale or missing data)
            if not used_repository and allow_live_research:
                # Get known sources for this jurisdiction (or discover them)
                known_sources = await get_known_sources(conn, jurisdiction_id)

                if not known_sources:
                    # Bootstrap: discover sources for new jurisdiction
                    discovered = await service.discover_jurisdiction_sources(
                        city=location.city,
                        state=location.state,
                        county=location.county,
                    )
                    for src in discovered:
                        domain = (src.get("domain") or "").lower()
                        if domain:
                            for cat in src.get("categories", []):
                                await record_source(
                                    conn, jurisdiction_id, domain, src.get("name"), cat
                                )
                    known_sources = await get_known_sources(conn, jurisdiction_id)

                # Build context for research prompt
                source_context = build_context_prompt(known_sources)

                # Phase 3.1: Get recent corrections to avoid repeating false positives
                corrections = await get_recent_corrections(jurisdiction_id)
                corrections_context = format_corrections_for_prompt(corrections)

                # Load preemption rules for this state
                try:
                    preemption_rows = await conn.fetch(
                        "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                        location.state.upper(),
                    )
                    preemption_rules = {
                        row["category"]: row["allows_local_override"]
                        for row in preemption_rows
                    }
                except asyncpg.UndefinedTableError:
                    preemption_rules = {}

                requirements = await service.research_location_compliance(
                    city=location.city,
                    state=location.state,
                    county=location.county,
                    categories=research_categories,
                    source_context=source_context,
                    corrections_context=corrections_context,
                    preemption_rules=preemption_rules,
                    has_local_ordinance=has_local_ordinance,
                    industry_context=industry_context,
                )
                if research_categories and cached_requirements_for_merge:
                    target_set = {
                        _normalize_category(cat) or cat for cat in research_categories
                    }
                    preserved = [
                        req
                        for req in cached_requirements_for_merge
                        if (
                            _normalize_category(req.get("category"))
                            or req.get("category")
                        )
                        not in target_set
                    ]
                    requirements = preserved + requirements
            # Repository-only, no catalog refresh: a pure projection from whatever
            # the shared catalog already has. This is the daily tenant sweep's
            # path (allow_repository_refresh=False) — catalog freshness is our
            # job on our own schedule, never a side effect of syncing a tenant.
            elif not used_repository and not allow_live_research and not allow_repository_refresh:
                # Real gaps only — recompute against the full chain the tab
                # projects, not the tier-stage slice (see the stream twin).
                chain_reqs = await _project_chain_to_location(
                    conn, company_id, location, jurisdiction_id
                )
                missing_categories = _missing_required_categories(chain_reqs)
                used_repository = True
                if missing_categories:
                    print(
                        f"[Compliance] Projection-only: missing categories for {location.city}, {location.state}: "
                        f"{', '.join(missing_categories)}. Not refreshing (allow_repository_refresh=False)."
                    )

            # Repository-only mode — see the twin branch in run_compliance_check_stream for semantics.
            elif not used_repository and not allow_live_research and allow_repository_refresh:
                missing_categories = _missing_required_categories(requirements)
                used_repository = True
                if missing_categories:
                    print(
                        f"[Compliance] Repository-only mode: missing categories for {location.city}, {location.state}: "
                        f"{', '.join(missing_categories)}. Triggering source-of-truth refresh "
                        f"(jurisdiction_id={jurisdiction_id})."
                    )
                    try:
                        requirements = await _refresh_repository_missing_categories(
                            conn,
                            service,
                            jurisdiction_id=jurisdiction_id,
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            has_local_ordinance=has_local_ordinance,
                            current_requirements=requirements,
                            missing_categories=missing_categories,
                        )
                    except Exception as refresh_error:
                        print(
                            f"[Compliance] Source-of-truth refresh failed for {location.city}, {location.state}: "
                            f"{refresh_error}"
                        )

                    missing_after_refresh = _missing_required_categories(requirements)
                    if missing_after_refresh:
                        print(
                            f"[Compliance] Repository still missing categories for {location.city}, {location.state}: "
                            f"{', '.join(missing_after_refresh)} after refresh."
                        )
                    else:
                        print(
                            f"[Compliance] Repository refresh completed for {location.city}, {location.state}."
                        )

                    if not requirements:
                        stale_repo_rows = await _load_jurisdiction_requirements(
                            conn, jurisdiction_id
                        )
                        if stale_repo_rows:
                            requirements = [
                                _jurisdiction_row_to_dict(jr) for jr in stale_repo_rows
                            ]
                            print(
                                f"[Compliance] Using stale repository fallback for {location.city}, {location.state} "
                                f"({len(requirements)} requirement(s))."
                            )

            # Stale-data fallback: if Gemini returned nothing, try cached data.
            # Set used_repository = True to skip fresh-data logic (upserts, alerts, verification).
            if not requirements and not used_repository:
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                if j_reqs:
                    requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
                    used_repository = True
                    print(
                        f"[Compliance] Background: falling back to stale repository data ({len(requirements)} cached requirements)"
                    )

            # ── TIER 4: Triggered research based on facility attributes ──
            from ..compliance_registry import get_activated_profiles as _get_activated_profiles_bg

            fa_bg = location.facility_attributes
            if isinstance(fa_bg, str):
                try:
                    fa_bg = json.loads(fa_bg)
                except (json.JSONDecodeError, TypeError):
                    fa_bg = None
            activated_profiles_bg = _get_activated_profiles_bg(fa_bg) if fa_bg else []
            failed_profile_keys_bg: set = set()
            if activated_profiles_bg:
                if not source_context:
                    known_sources = await get_known_sources(conn, jurisdiction_id)
                    source_context = build_context_prompt(known_sources)

                for profile in activated_profiles_bg:
                    existing_triggered = await conn.fetchval(
                        """SELECT COUNT(*) FROM jurisdiction_requirements
                           WHERE jurisdiction_id = $1
                             AND applicable_entity_types @> $2::jsonb""",
                        jurisdiction_id,
                        json.dumps([profile.key]),
                    )
                    if existing_triggered and existing_triggered > 0:
                        triggered_rows = await conn.fetch(
                            """SELECT * FROM jurisdiction_requirements
                               WHERE jurisdiction_id = $1
                                 AND applicable_entity_types @> $2::jsonb""",
                            jurisdiction_id,
                            json.dumps([profile.key]),
                        )
                        for tr in triggered_rows:
                            requirements.append(_jurisdiction_row_to_dict(dict(tr)))
                        continue

                    print(f"[Tier 4] Researching {profile.label}-specific requirements...")
                    try:
                        trigger_cats = list(profile.applicable_categories)
                        triggered_reqs = await service.research_triggered_requirements(
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            profile_key=profile.key,
                            profile_label=profile.label,
                            trigger_condition=profile.trigger_condition,
                            research_instruction=profile.research_instruction,
                            categories=trigger_cats,
                            source_context=source_context,
                        )
                        if triggered_reqs:
                            await _upsert_requirements_additive(
                                conn, jurisdiction_id, triggered_reqs, research_source="gemini"
                            )
                            requirements.extend(triggered_reqs)
                    except Exception as e:
                        failed_profile_keys_bg.add(profile.key)
                        print(f"[Tier 4] Error researching {profile.key}: {e}")

            # ── Gap detection: flag missing specialty policies for admin ──
            if activated_profiles_bg:
                req_categories = {
                    r.get("category") for r in requirements if r.get("category")
                }
                for profile in activated_profiles_bg:
                    if profile.key in failed_profile_keys_bg:
                        continue
                    for cat in profile.applicable_categories:
                        if cat not in req_categories:
                            existing_alert = await conn.fetchval(
                                """SELECT id FROM compliance_alerts
                                   WHERE location_id = $1 AND alert_type = 'missing_specialty'
                                     AND category = $2 AND metadata->>'trigger_profile' = $3
                                     AND status != 'dismissed'""",
                                location_id, cat, profile.key,
                            )
                            if existing_alert:
                                continue
                            try:
                                cat_label = cat.replace("_", " ").title()
                                await _create_alert(
                                    conn,
                                    location_id,
                                    company_id,
                                    None,
                                    f"Missing {cat_label} policies for {profile.label}",
                                    (
                                        f"Facility profile indicates {profile.label} requirements apply "
                                        f"but no {cat_label} policies found. Admin review recommended."
                                    ),
                                    "info",
                                    cat,
                                    alert_type="missing_specialty",
                                    metadata={
                                        "inferred_profile": profile.key,
                                        "missing_category": cat,
                                        "trigger_profile": profile.key,
                                        "source": "gemini_inference",
                                    },
                                )
                            except Exception as e:
                                print(f"[Gap Detection] Error creating alert for {cat}/{profile.key}: {e}")

            if not requirements:
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )
                await _complete_check_log(conn, log_id, 0, 0, 0)
                return {"new": 0, "updated": 0, "alerts": 0}

            # Post-filter: handle city-level results for cities with no local ordinance
            if has_local_ordinance is False:
                requirements = _filter_city_level_requirements(
                    requirements, location.state
                )
                # Annotate remaining reqs with inheritance note
                parent = f"{location.county} County / " if location.county else ""
                note = (
                    f" [Note: {location.city} does not have its own local ordinance; "
                    f"this requirement applies via {parent}{location.state} state law.]"
                )
                for r in requirements:
                    desc = r.get("description") or ""
                    if note not in desc:
                        r["description"] = desc + note

            _normalize_requirement_categories(requirements)
            requirements = await _filter_requirements_for_company(
                conn, company_id, requirements
            )
            requirements = await _filter_with_preemption(
                conn, requirements, location.state
            )

            # Contribute to repository after Gemini call.
            if not used_repository:
                await _upsert_jurisdiction_requirements_routed(
                    conn, jurisdiction_id, requirements, research_source="gemini"
                )

                # Learn from successful research: record any new sources seen
                for req in requirements:
                    source_url = req.get("source_url", "")
                    if source_url:
                        domain = extract_domain(source_url)
                        if domain:
                            await record_source(
                                conn,
                                jurisdiction_id,
                                domain,
                                req.get("source_name"),
                                req.get("category", ""),
                            )

            # Sync to location
            sync_result = await _sync_requirements_to_location(
                conn,
                location_id,
                company_id,
                requirements,
                create_alerts=True,
            )
            new_count = sync_result["new"]
            updated_count = sync_result["updated"]
            alert_count = sync_result["alerts"]
            changes_to_verify = sync_result["changes_to_verify"]
            existing_by_key = sync_result["existing_by_key"]

            # Send ONE summary email for all new requirement alerts
            if alert_count > 0:
                try:
                    await _send_bulk_alert_email(company_id, location_id, alert_count)
                except Exception as e:
                    print(f"[Compliance] Bulk alert email error: {e}")

            # Collect (alert_id, change_info) for batch impact summary generation
            bg_alert_changes: list[tuple] = []

            # Verify changes (skip when using cached repository data)
            if not used_repository:
                for change_info in changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    try:
                        verification = await service.verify_compliance_change_adaptive(
                            category=req.get("category", ""),
                            title=req.get("title", ""),
                            jurisdiction_name=req.get("jurisdiction_name", ""),
                            old_value=change_info["old_value"],
                            new_value=change_info["new_value"],
                        )
                        confidence = max(
                            score_verification_confidence(verification.sources),
                            verification.confidence,
                        )
                    except Exception:
                        confidence = 0.5
                        verification = VerificationResult(
                            confirmed=False,
                            confidence=0.0,
                            sources=[],
                            explanation="Verification unavailable",
                        )

                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"

                    if confidence >= 0.6:
                        alert_count += 1
                        bg_aid = await _create_alert(
                            conn,
                            location_id,
                            company_id,
                            existing["id"],
                            f"Compliance Change: {req.get('title')}",
                            change_msg,
                            "warning",
                            req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={
                                "verification_explanation": verification.explanation
                            },
                        )
                        bg_alert_changes.append((bg_aid, change_info))
                        _record_change_notification_item(
                            change_email_items, req, change_info
                        )
                    elif confidence >= 0.3:
                        alert_count += 1
                        bg_aid = await _create_alert(
                            conn,
                            location_id,
                            company_id,
                            existing["id"],
                            f"Unverified: {req.get('title')}",
                            change_msg,
                            "info",
                            req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={
                                "verification_explanation": verification.explanation,
                                "unverified": True,
                            },
                        )
                        bg_alert_changes.append((bg_aid, change_info))
                        _record_change_notification_item(
                            change_email_items, req, change_info
                        )

                for change_info in changes_to_verify[MAX_VERIFICATIONS_PER_CHECK:]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"
                    alert_count += 1
                    bg_oid = await _create_alert(
                        conn,
                        location_id,
                        company_id,
                        existing["id"],
                        f"Compliance Change: {req.get('title')}",
                        change_msg,
                        "warning",
                        req.get("category"),
                        source_url=req.get("source_url"),
                        source_name=req.get("source_name"),
                        alert_type="change",
                    )
                    bg_alert_changes.append((bg_oid, change_info))
                    _record_change_notification_item(
                        change_email_items, req, change_info
                    )

            # Legislation scan — only via Gemini when not using repository
            if not used_repository:
                try:
                    current_reqs = [
                        dict(r) for r in existing_by_key.values() if r.get("id")
                    ]
                    legislation_items = await service.scan_upcoming_legislation(
                        city=location.city,
                        state=location.state,
                        county=location.county,
                        current_requirements=current_reqs,
                    )
                    await _upsert_jurisdiction_legislation(
                        conn, jurisdiction_id, legislation_items
                    )
                    leg_count = await process_upcoming_legislation(
                        conn, location_id, company_id, legislation_items
                    )
                    alert_count += leg_count
                except Exception as e:
                    print(f"[Compliance] Background legislation scan error: {e}")

            # Deadline escalation
            try:
                await escalate_upcoming_deadlines(conn, company_id)
            except Exception as e:
                print(f"[Compliance] Background escalation error: {e}")

            # Generate impact summaries for change alerts (background)
            if bg_alert_changes:
                try:
                    from .impact_summary import batch_generate_impact_summaries

                    loc_dict = {
                        "id": location_id,
                        "name": getattr(location, "name", None),
                        "city": location.city,
                        "state": location.state,
                    }
                    company_row = await conn.fetchrow(
                        "SELECT name, industry FROM companies WHERE id = $1",
                        company_id,
                    )
                    company_ctx = {
                        "company_name": company_row["name"] if company_row else "",
                        "industry": company_row["industry"] if company_row else "",
                    }
                    await batch_generate_impact_summaries(
                        bg_alert_changes, loc_dict, company_ctx, conn
                    )
                except Exception as e:
                    print(f"[Compliance] Background impact summary error: {e}")

            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id,
            )
            await _complete_check_log(
                conn, log_id, new_count, updated_count, alert_count
            )

        except Exception as e:
            await _complete_check_log(
                conn, log_id, new_count, updated_count, alert_count, error=str(e)
            )
            raise

    from ...config import get_settings as _get_settings
    if _get_settings().compliance_emails_enabled:
        try:
            await _notify_company_admins_of_compliance_changes(
                company_id=company_id,
                location=location,
                change_items=change_email_items,
            )
        except Exception as e:
            print(f"[Compliance] Error notifying admins about compliance changes: {e}")

    return {"new": new_count, "updated": updated_count, "alerts": alert_count}


async def research_jurisdiction_repo_only(
    jurisdiction_id: UUID,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Populate jurisdiction_requirements for the given jurisdiction via Gemini.

    Unlike run_compliance_check_stream(), this function writes ONLY to
    jurisdiction_requirements (the shared repo). It does NOT touch
    compliance_requirements, compliance_check_logs, or compliance_alerts for
    any tenant. Intended for the admin research queue.
    """
    from ...database import get_connection
    from .gemini_compliance import get_gemini_compliance_service

    async with get_connection() as conn:
        j = await conn.fetchrow(
            "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
            jurisdiction_id,
        )
        if not j:
            yield {"type": "error", "message": "Jurisdiction not found"}
            return

        city = j["city"]
        state = j["state"]
        county = j.get("county")
        location_name = f"{city}, {state}"

        has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)

        yield {"type": "started", "location": location_name}

        service = get_gemini_compliance_service()

        existing_rows = await _load_jurisdiction_requirements(conn, jurisdiction_id)
        current_requirements = [_jurisdiction_row_to_dict(jr) for jr in existing_rows]
        missing_categories = _missing_required_categories(current_requirements)

        refresh_queue: asyncio.Queue = asyncio.Queue()

        def _on_retry(attempt: int, error: str) -> None:
            refresh_queue.put_nowait(
                {
                    "type": "retrying",
                    "message": f"Retrying research (attempt {attempt + 1})...",
                }
            )

        # --- Generic category research phase ---
        updated_requirements = list(current_requirements)
        if missing_categories:
            yield {
                "type": "repository_refresh",
                "jurisdiction_id": str(jurisdiction_id),
                "missing_categories": missing_categories,
                "message": (
                    f"Researching {len(missing_categories)} missing categories for "
                    f"{location_name} ({', '.join(missing_categories)})."
                ),
            }

            try:
                refresh_task = asyncio.create_task(
                    _refresh_repository_missing_categories(
                        conn,
                        service,
                        jurisdiction_id=jurisdiction_id,
                        city=city,
                        state=state,
                        county=county,
                        has_local_ordinance=has_local_ordinance,
                        current_requirements=current_requirements,
                        missing_categories=missing_categories,
                        on_retry=_on_retry,
                    )
                )
                async for evt in _heartbeat_while(refresh_task, queue=refresh_queue):
                    yield evt
                updated_requirements = refresh_task.result() or []
            except Exception as e:
                yield {"type": "error", "message": f"Research failed: {e}"}
                return

            missing_after = _missing_required_categories(updated_requirements)
            if missing_after:
                yield {
                    "type": "repository_only",
                    "jurisdiction_id": str(jurisdiction_id),
                    "missing_categories": missing_after,
                    "message": (
                        f"Repository still missing {', '.join(missing_after)} after research."
                    ),
                }

        # --- Industry-specific research phase ---
        # Call Gemini directly for industry variants and upsert additively
        # (don't use _refresh_repository_missing_categories which replaces categories).
        try:
            profiles = await conn.fetch("SELECT * FROM industry_compliance_profiles")
        except asyncpg.UndefinedTableError:
            profiles = []

        for profile in profiles:
            rate_types = profile.get("rate_types") or []
            relevant_rts = [rt for rt in rate_types if rt in _INDUSTRY_SPECIFIC_RATE_TYPES]
            if not relevant_rts:
                continue

            has_industry = await conn.fetchval(
                """SELECT EXISTS(
                    SELECT 1 FROM jurisdiction_requirements
                    WHERE jurisdiction_id = $1 AND rate_type = ANY($2::text[])
                )""",
                jurisdiction_id,
                relevant_rts,
            )
            if has_industry:
                continue

            focused = profile.get("focused_categories") or []
            if not focused:
                continue

            canonical = profile["name"].lower()
            ctx = _INDUSTRY_RESEARCH_CONTEXT.get(canonical, "")
            if not ctx:
                continue

            yield {
                "type": "repository_refresh",
                "message": f"Researching {canonical}-specific requirements for {location_name}...",
            }

            try:
                industry_task = asyncio.create_task(
                    service.research_location_compliance(
                        city=city,
                        state=state,
                        county=county,
                        categories=focused,
                        industry_context=ctx,
                        on_retry=_on_retry,
                    )
                )
                async for evt in _heartbeat_while(industry_task, queue=refresh_queue):
                    yield evt
                industry_reqs = industry_task.result() or []

                # Keep only industry-specific rows (rate_type matches)
                industry_only = [
                    r for r in industry_reqs
                    if _normalize_rate_type(r.get("rate_type")) in relevant_rts
                ]
                for req in industry_only:
                    _clamp_varchar_fields(req)
                    if not req.get("applicable_industries"):
                        req["applicable_industries"] = [canonical]

                if industry_only:
                    await _upsert_requirements_additive(
                        conn, jurisdiction_id, industry_only, research_source="gemini"
                    )
                    updated_requirements = updated_requirements + industry_only
                    yield {
                        "type": "repository_refresh",
                        "message": f"Added {len(industry_only)} {canonical}-specific requirements.",
                    }
                else:
                    yield {
                        "type": "repository_refresh",
                        "message": f"No {canonical}-specific requirements found for {location_name}.",
                    }
            except Exception as e:
                yield {
                    "type": "warning",
                    "message": f"Industry-specific research failed for {canonical}: {e}",
                }

        # --- Healthcare-specific research phase ---
        try:
            yield {
                "type": "repository_refresh",
                "message": f"Researching healthcare-specific compliance for {location_name}...",
            }
            healthcare_result = await _research_healthcare_requirements_for_jurisdiction(
                conn, jurisdiction_id
            )
            added_healthcare = healthcare_result.get("requirements") or []
            if added_healthcare:
                updated_requirements = updated_requirements + added_healthcare
            yield {
                "type": "repository_refresh",
                "message": (
                    f"Healthcare research completed for {location_name}: "
                    f"{healthcare_result.get('new', 0)} requirement(s) added."
                ),
            }
        except Exception as e:
            yield {
                "type": "warning",
                "message": f"Healthcare-specific research failed for {location_name}: {e}",
            }

        yield {
            "type": "complete",
            "location": location_name,
            "message": f"Research complete for {location_name}.",
            "new": len(updated_requirements),
            "updated": 0,
            "alerts": 0,
        }


async def set_requirement_pinned(
    requirement_id: UUID, company_id: UUID, is_pinned: bool
) -> dict | None:
    from ...database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE compliance_requirements cr
            SET is_pinned = $1
            FROM business_locations bl
            WHERE cr.id = $2
              AND cr.location_id = bl.id
              AND bl.company_id = $3
            RETURNING cr.id, cr.title, cr.is_pinned
            """,
            is_pinned,
            requirement_id,
            company_id,
        )
    if not row:
        return None
    return {"id": str(row["id"]), "title": row["title"], "is_pinned": row["is_pinned"]}


async def get_pinned_requirements(company_id: UUID) -> list[dict]:
    from ...database import get_connection

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT cr.id, cr.category, cr.jurisdiction_level, cr.jurisdiction_name,
                   cr.title, cr.description, cr.current_value, cr.effective_date,
                   cr.source_url, cr.is_pinned,
                   bl.name AS location_name, bl.city, bl.state
            FROM compliance_requirements cr
            JOIN business_locations bl ON cr.location_id = bl.id
            LEFT JOIN jurisdiction_requirements cat
              ON cat.id = cr.jurisdiction_requirement_id
            WHERE bl.company_id = $1
              AND cr.is_pinned = true
              AND bl.is_active = true
            """
            # A pin is a bookmark into the tab. If the row isn't listed there
            # any more, a pin pointing at it is a dead link.
            + await codified_gate_sql("cat", conn=conn)
            + " ORDER BY cr.category, cr.jurisdiction_level",
            company_id,
        )
    return [
        {
            "id": str(row["id"]),
            "category": row["category"],
            "jurisdiction_level": row["jurisdiction_level"],
            "jurisdiction_name": row["jurisdiction_name"],
            "title": row["title"],
            "description": row["description"],
            "current_value": row["current_value"],
            "effective_date": row["effective_date"].isoformat()
            if row["effective_date"]
            else None,
            "source_url": row["source_url"],
            "is_pinned": row["is_pinned"],
            "location_name": row["location_name"],
            "city": row["city"],
            "state": row["state"],
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Hierarchical Resolution — ALL compliance intelligence lives here
# ═══════════════════════════════════════════════════════════════════════════

import hashlib
import unicodedata


def normalize_and_hash(raw_content: str) -> str:
    """Normalize content and return SHA-256 hash.

    Normalization pipeline:
    1. Strip leading/trailing whitespace
    2. Collapse internal whitespace runs to single space
    3. Normalize Unicode to NFC
    4. Strip HTML tags (simple regex)
    5. Lowercase
    """
    if not raw_content:
        return hashlib.sha256(b"").hexdigest()
    text = raw_content.strip()
    text = re.sub(r"<[^>]+>", "", text)  # strip HTML
    text = re.sub(r"\s+", " ", text)  # collapse whitespace
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evaluate_trigger_conditions(
    trigger_json: Optional[Dict[str, Any]],
    facility_attributes: Optional[Dict[str, Any]],
) -> bool:
    """Evaluate a trigger_conditions JSONB document against facility_attributes.

    Returns True if the trigger conditions are met, False otherwise.
    If trigger_json is None, the requirement has no trigger → always applies.
    If facility_attributes is None, treat all attribute checks as False.

    Supports: attribute, entity_type, and/or/not compounds.
    requirement_active / category_active are v2 — passthrough (return True).
    """
    if trigger_json is None:
        return True
    # Not every read path decodes JSONB: the hierarchical resolver's recursive
    # CTE hands `trigger_conditions` back as a str, and indexing it below raised
    # TypeError ("string indices must be integers") — a 500 for the whole view.
    if isinstance(trigger_json, str):
        try:
            trigger_json = json.loads(trigger_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Trigger condition is unparseable JSON — treating as not matched."
            )
            return False
        if trigger_json is None:
            return True
    if not isinstance(trigger_json, dict):
        logger.warning(
            "Trigger condition is %s, expected an object — treating as not matched.",
            type(trigger_json).__name__,
        )
        return False
    if facility_attributes is None:
        facility_attributes = {}

    return _eval_condition(trigger_json, facility_attributes)


def _eval_condition(cond: Dict[str, Any], attrs: Dict[str, Any]) -> bool:
    """Recursively evaluate a single trigger condition node."""
    # Compound conditions
    if "op" in cond:
        op = cond["op"]
        children = cond.get("conditions", [])
        if op == "and":
            return all(_eval_condition(c, attrs) for c in children)
        elif op == "or":
            return any(_eval_condition(c, attrs) for c in children)
        elif op == "not":
            if children:
                return not _eval_condition(children[0], attrs)
            # `not` with nothing to negate is malformed — and it was the last
            # shape still failing OPEN, i.e. silently universalizing a
            # conditional obligation. _condition_shape_error rejects it at write
            # time on the scope-registry side; nothing gates it on the research
            # side, so fail closed here too.
            logger.warning(
                "Trigger condition has an empty 'not' — treating as not matched."
            )
            return False
        # An unrecognized op used to return True — which silently turned a
        # CONDITIONAL obligation into a universal one: every company got it.
        # `trigger_conditions` on jurisdiction_requirements are written by Gemini
        # research with NO shape gate (unlike scope-registry classifications,
        # which validate_proposal rejects), so a plausible model typo
        # ({"op": "greater_than"}, a leaf that says "op" where it means
        # "operator") is enough to serve e.g. the PSM standard to a bakery.
        # Fail closed and say so — the same convention this function already
        # uses for an unevaluable numeric comparison below.
        logger.warning(
            "Trigger condition has unknown op %r — treating as not matched. "
            "This requirement will NOT apply; fix the trigger_conditions JSON.",
            op,
        )
        return False

    # Leaf conditions
    ctype = cond.get("type")

    if ctype == "attribute":
        key = cond.get("key", "")
        operator = cond.get("operator", "eq")
        expected = cond.get("value")
        actual = attrs.get(key)

        if operator == "exists":
            return key in attrs
        if actual is None:
            return False
        if operator == "eq":
            return actual == expected
        if operator == "neq":
            return actual != expected
        if operator in ("gt", "gte", "lt", "lte"):
            # facility_attributes is user-edited JSONB — a numeric trigger vs a
            # string attr ("120" vs 100) must degrade to False, not TypeError
            # the whole compliance context.
            try:
                a = float(actual) if isinstance(actual, str) else actual
                e = float(expected) if isinstance(expected, str) else expected
                if operator == "gt":
                    return a > e
                if operator == "gte":
                    return a >= e
                if operator == "lt":
                    return a < e
                return a <= e
            except (TypeError, ValueError):
                logger.warning(
                    "Trigger comparison failed: %r %s %r (key=%s) — treating as not matched",
                    actual, operator, expected, key,
                )
                return False
        if operator == "in":
            return actual in (expected or [])
        if operator == "contains":
            if isinstance(actual, (list, set)):
                return expected in actual
            return False
        return False

    if ctype == "entity_type":
        value = cond.get("value")
        operator = cond.get("operator", "eq")
        entity = attrs.get("entity_type")
        if operator == "eq":
            return entity == value
        if operator == "in":
            return entity in (value if isinstance(value, list) else [value])
        return False

    # v2 chaining predicates — passthrough for now
    if ctype in ("requirement_active", "category_active"):
        return True

    # Unrecognized node shape. Same reasoning as the unknown-op branch above:
    # returning True here would universalize a conditional obligation on the
    # strength of malformed JSON.
    logger.warning(
        "Trigger condition has unknown type %r — treating as not matched. "
        "This requirement will NOT apply; fix the trigger_conditions JSON.",
        ctype,
    )
    return False


async def resolve_jurisdiction_stacks(
    conn: asyncpg.Connection, jurisdiction_ids: List[UUID]
) -> Dict[UUID, List[Dict[str, Any]]]:
    """Batched variant of resolve_jurisdiction_stack — one round trip for N leaves.

    Walks every hierarchy in one recursive CTE, carrying the leaf id through the
    recursion as root_id so results group cleanly. Precedence rules are scoped
    per-chain (a rule from one leaf's chain never leaks into another's).
    Returns {leaf_jurisdiction_id: rows ordered by category + depth (leaf first)}.
    """
    if not jurisdiction_ids:
        return {}
    # Dedupe while preserving order
    unique_ids = list(dict.fromkeys(jurisdiction_ids))
    query = """
        WITH RECURSIVE jurisdiction_chain AS (
            SELECT id, city, state, country_code, level::text AS level, display_name,
                   parent_id, authority_type, 0 AS depth, id AS root_id
            FROM jurisdictions WHERE id = ANY($1::uuid[])
            UNION ALL
            SELECT j.id, j.city, j.state, j.country_code, j.level::text, j.display_name,
                   j.parent_id, j.authority_type, jc.depth + 1, jc.root_id
            FROM jurisdictions j
            JOIN jurisdiction_chain jc ON j.id = jc.parent_id
            WHERE j.country_code = jc.country_code
        ),
        chain_requirements AS (
            SELECT jr.id, jr.jurisdiction_id, jr.requirement_key, jr.category,
                   jr.jurisdiction_level, jr.jurisdiction_name, jr.title,
                   jr.description, jr.current_value, jr.numeric_value,
                   jr.source_url, jr.source_url_status, jr.source_name, jr.effective_date,
                   jr.last_verified_at, jr.previous_value,
                   jr.previous_description, jr.change_status,
                   jr.last_changed_at, jr.expiration_date,
                   jr.requires_written_policy, jr.metadata,
                   jr.rate_type, jr.canonical_key, jr.statute_citation,
                   -- The other two thirds of the codified trio, so tenant-facing
                   -- callers can apply `is_codified_row` without a second query.
                   jr.citation_verified_at, jr.citation_item_id,
                   jr.status::text AS req_status, jr.category_id,
                   jr.trigger_conditions, jr.applicable_entity_types,
                   jc.level AS jur_level, jc.display_name AS jur_display_name,
                   jc.depth, jc.root_id
            FROM jurisdiction_requirements jr
            JOIN jurisdiction_chain jc ON jr.jurisdiction_id = jc.id
            WHERE jr.status = 'active'
        ),
        chain_precedence AS (
            SELECT jc_h.root_id, pr.id AS rule_id, pr.category_id AS rule_category_id,
                   pr.precedence_type::text AS precedence_type,
                   pr.reasoning_text, pr.legal_citation,
                   pr.trigger_condition, pr.applies_to_all_children,
                   pr.higher_jurisdiction_id, pr.lower_jurisdiction_id
            FROM precedence_rules pr
            JOIN jurisdiction_chain jc_h ON jc_h.id = pr.higher_jurisdiction_id
            WHERE pr.status = 'active'
              AND (
                  pr.applies_to_all_children = true
                  OR pr.lower_jurisdiction_id IN (
                      SELECT jc_l.id FROM jurisdiction_chain jc_l
                      WHERE jc_l.root_id = jc_h.root_id
                  )
              )
        )
        SELECT cr.*,
               cp.rule_id, cp.precedence_type,
               cp.reasoning_text AS rule_reasoning_text,
               cp.legal_citation AS rule_legal_citation,
               cp.trigger_condition AS rule_trigger_condition,
               cp.applies_to_all_children,
               cp.higher_jurisdiction_id AS rule_higher_jurisdiction_id,
               cp.lower_jurisdiction_id AS rule_lower_jurisdiction_id
        FROM chain_requirements cr
        LEFT JOIN chain_precedence cp
            ON cp.rule_category_id = cr.category_id
           AND cp.root_id = cr.root_id
        ORDER BY cr.root_id, cr.category, cr.depth ASC
    """
    rows = await conn.fetch(query, unique_ids)
    grouped: Dict[UUID, List[Dict[str, Any]]] = {jid: [] for jid in unique_ids}
    for row in rows:
        out = dict(row)
        # The pool sets no JSONB codec, so asyncpg hands every JSONB column back
        # as a str. Decode the two trigger columns HERE, at the single producer
        # of these rows, rather than at each consumer: the downstream readers
        # (evaluate_trigger_conditions, _compute_triggered_by) index them as
        # mappings, and raised on the string. `rule_trigger_condition` also goes
        # out verbatim on the hierarchical response, where a JSON-encoded string
        # is not what the shape promises.
        for col in ("trigger_conditions", "rule_trigger_condition"):
            value = out.get(col)
            if not isinstance(value, str):
                continue
            try:
                out[col] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Unparseable trigger — leave the raw value. Callers fail CLOSED
                # on a non-object (the requirement does not apply), which is the
                # convention for a malformed trigger everywhere else here.
                logger.warning(
                    "Requirement %s has unparseable %s.", out.get("id"), col
                )
        grouped[row["root_id"]].append(out)
    return grouped


async def resolve_jurisdiction_stack(
    conn: asyncpg.Connection, jurisdiction_id: UUID
) -> List[Dict[str, Any]]:
    """Walk the jurisdiction hierarchy from leaf to federal via recursive CTE.

    Returns all active requirements at each level in the chain, joined with
    matching precedence rules. Results ordered by category + depth (leaf first).
    Thin wrapper over resolve_jurisdiction_stacks for a single leaf.
    """
    grouped = await resolve_jurisdiction_stacks(conn, [jurisdiction_id])
    return grouped.get(jurisdiction_id, [])


def determine_governing_requirement(
    rows_by_category: Dict[str, List[Dict[str, Any]]],
    facility_attributes: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """For each category, determine the governing requirement based on precedence.

    Returns a list of dicts, one per category, each containing:
    - governing_requirement: the winning row
    - all_levels: all rows for this category
    - precedence_type: floor/ceiling/supersede/additive or None
    - governance_source: precedence_rule / default_local
    - reasoning_text, legal_citation from the matched rule

    ALL compliance intelligence is computed here. Frontend just renders results.
    """
    results = []

    for category, rows in rows_by_category.items():
        if not rows:
            continue

        # Filter by trigger conditions (evaluate against facility attributes).
        # The precedence LEFT JOIN fans out: a requirement matched by N rules
        # appears N times, differing only in rule_* columns. Dedupe requirement
        # rows by id (else all_levels carries duplicates and the single-level
        # render path is defeated), but keep every (row × rule) pairing as a
        # rule candidate so no matching rule is lost.
        active_rows: List[Dict[str, Any]] = []
        rule_candidates: List[Dict[str, Any]] = []
        seen_req_ids: set = set()
        depth_by_jur: Dict[Any, int] = {}
        for row in rows:
            trigger = row.get("trigger_conditions")
            if not evaluate_trigger_conditions(trigger, facility_attributes):
                continue
            if row.get("rule_id") is not None:
                rule_candidates.append(row)
            req_id = row.get("id")
            if req_id is None or req_id not in seen_req_ids:
                if req_id is not None:
                    seen_req_ids.add(req_id)
                active_rows.append(row)
            jur_id = row.get("jurisdiction_id")
            if jur_id is not None:
                depth_by_jur[jur_id] = row.get("depth", 0)

        if not active_rows:
            continue

        # Find the governing precedence rule. Specific (non-blanket) beats
        # blanket; among specific rules, the one pinned to the most local
        # lower jurisdiction (lowest depth) wins; ties resolve to the first
        # candidate in SQL order (deterministic).
        rule_row = None
        precedence_type = None
        best_score = None
        for row in rule_candidates:
            # Check trigger condition on the precedence rule itself
            rule_trigger = row.get("rule_trigger_condition")
            if not evaluate_trigger_conditions(rule_trigger, facility_attributes):
                continue
            is_specific = not row.get("applies_to_all_children")
            lower_depth = depth_by_jur.get(row.get("rule_lower_jurisdiction_id"), 999)
            score = (1 if is_specific else 0, -lower_depth)
            if best_score is None or score > best_score:
                best_score = score
                rule_row = row
                precedence_type = row.get("precedence_type")

        # Sort by depth (0 = leaf/local, higher = more general)
        sorted_rows = sorted(active_rows, key=lambda r: r.get("depth", 0))

        if precedence_type == "floor":
            # Highest value wins (most beneficial — typically min wage)
            rows_with_num = [
                (r, float(r["numeric_value"]))
                for r in sorted_rows
                if r.get("numeric_value") is not None
            ]
            if rows_with_num:
                governing = max(rows_with_num, key=lambda x: x[1])[0]
            else:
                governing = sorted_rows[0]  # most local
            governance_source = "precedence_rule"

        elif precedence_type == "ceiling":
            # The rule's higher jurisdiction caps the lower one — pick the row
            # belonging to that jurisdiction, not blindly the most general row
            # in the chain (a "state caps city" rule must not surface federal).
            target_jur = rule_row.get("rule_higher_jurisdiction_id") if rule_row else None
            governing = next(
                (r for r in sorted_rows if target_jur is not None
                 and r.get("jurisdiction_id") == target_jur),
                None,
            ) or sorted_rows[-1]
            governance_source = "precedence_rule"

        elif precedence_type == "supersede":
            # Lower jurisdiction completely replaces (most local)
            governing = sorted_rows[0]
            governance_source = "precedence_rule"

        elif precedence_type == "additive":
            # All levels apply — use most local as "governing" for display
            # but mark all as active
            governing = sorted_rows[0]
            governance_source = "precedence_rule"

        else:
            # No precedence rule — default to most local
            governing = sorted_rows[0]
            governance_source = "default_local"

        results.append({
            "category": category,
            "category_id": governing.get("category_id"),
            "governing_requirement": governing,
            "governing_level": governing.get("jur_level") or governing.get("jurisdiction_level"),
            "all_levels": sorted_rows,
            "precedence_type": precedence_type,
            "governance_source": governance_source,
            "reasoning_text": rule_row.get("rule_reasoning_text") if rule_row else None,
            "legal_citation": rule_row.get("rule_legal_citation") if rule_row else None,
            "rule_trigger_condition": rule_row.get("rule_trigger_condition") if rule_row else None,
            "rule_id": rule_row.get("rule_id") if rule_row else None,
        })

    return results


def _compute_triggered_by(
    trigger_conditions: Optional[Dict[str, Any]],
    facility_attributes: Optional[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """Walk trigger condition tree and return activation dicts for the response.

    Returns None for universal requirements (no trigger), or a list of
    TriggerActivation-shaped dicts showing which conditions matched.
    """
    if trigger_conditions is None:
        return None

    activations: List[Dict[str, Any]] = []
    _collect_activations(trigger_conditions, facility_attributes or {}, activations)
    return activations or None


def _collect_activations(
    cond: Dict[str, Any],
    attrs: Dict[str, Any],
    out: List[Dict[str, Any]],
) -> None:
    """Recursively collect trigger activation results from a condition tree."""
    # Compound conditions — recurse into children
    if "op" in cond:
        for child in cond.get("conditions", []):
            _collect_activations(child, attrs, out)
        return

    ctype = cond.get("type")

    if ctype == "entity_type":
        value = cond.get("value")
        entity = attrs.get("entity_type")
        out.append({
            "trigger_type": "entity_type",
            "trigger_key": None,
            "trigger_value": value,
            "matched": entity == value,
        })

    elif ctype == "attribute":
        key = cond.get("key", "")
        operator = cond.get("operator", "eq")
        expected = cond.get("value")
        actual = attrs.get(key)
        matched = _eval_condition(cond, attrs)
        out.append({
            "trigger_type": "attribute",
            "trigger_key": key,
            "trigger_value": expected,
            "matched": matched,
        })


async def get_hierarchical_requirements(
    location_id: UUID, company_id: UUID, category: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Fully resolve compliance requirements for a location using hierarchical precedence.

    This is the main entry point for the hierarchical view. It:
    1. Loads the location and its facility_attributes
    2. Resolves the jurisdiction stack via recursive CTE
    3. Groups by category
    4. Evaluates trigger conditions against facility attributes
    5. Determines governing requirement per category via precedence rules
    6. Returns a fully-resolved response dict — frontend just renders it

    Returns None if location not found.
    """
    from ...database import get_connection

    async with get_connection() as conn:
        # 1. Load location
        loc = await conn.fetchrow(
            """SELECT bl.id, bl.city, bl.state, bl.name,
                      bl.jurisdiction_id, bl.facility_attributes
               FROM business_locations bl
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id,
            company_id,
        )
        if not loc:
            return None
        if not loc["jurisdiction_id"]:
            return None

        facility_attrs = loc["facility_attributes"]
        if isinstance(facility_attrs, str):
            try:
                facility_attrs = json.loads(facility_attrs)
            except (json.JSONDecodeError, TypeError):
                facility_attrs = None

        # 2. Resolve jurisdiction stack
        stack_rows = await resolve_jurisdiction_stack(conn, loc["jurisdiction_id"])

        # This view reads the catalog directly rather than the location's
        # projection, so the SQL gate on compliance_requirements never reaches
        # it — filter the rows themselves, or the hierarchical view becomes the
        # hole every uncodified row walks back through.
        from .platform_settings import get_tenant_codified_only

        if await get_tenant_codified_only(conn=conn):
            stack_rows = [r for r in stack_rows if is_codified_row(r)]

        # 3. Group by category
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for row in stack_rows:
            cat = row["category"]
            if category and cat != category:
                continue
            by_category.setdefault(cat, []).append(row)

        # 4-5. Determine governing requirement per category
        resolved = determine_governing_requirement(by_category, facility_attrs)

        # 6. Look up category labels
        cat_labels = {}
        if resolved:
            cat_ids = [r["category_id"] for r in resolved if r.get("category_id")]
            if cat_ids:
                label_rows = await conn.fetch(
                    "SELECT id, slug, name, domain::text, \"group\" FROM compliance_categories WHERE id = ANY($1)",
                    cat_ids,
                )
                for lr in label_rows:
                    cat_labels[str(lr["id"])] = {
                        "name": lr["name"],
                        "domain": lr["domain"],
                        "group": lr["group"],
                        "slug": lr["slug"],
                    }

        # 7. Get employee impact
        try:
            impact = await get_employee_impact_for_location(location_id, company_id)
            total_affected = impact["total_affected"]
        except Exception:
            total_affected = None

        # 8. Build response
        categories_out = []
        total_requirements = 0
        for item in resolved:
            gov = item["governing_requirement"]
            cat_id_str = str(item.get("category_id", ""))
            cat_info = cat_labels.get(cat_id_str, {})

            all_levels = []
            for row in item["all_levels"]:
                all_levels.append({
                    "id": str(row["id"]),
                    "jurisdiction_level": row.get("jur_level") or row.get("jurisdiction_level", ""),
                    "jurisdiction_name": row.get("jur_display_name") or row.get("jurisdiction_name", ""),
                    "title": row.get("title", ""),
                    "description": row.get("description"),
                    "current_value": row.get("current_value"),
                    "previous_value": row.get("previous_value"),
                    "previous_description": row.get("previous_description"),
                    "change_status": row.get("change_status"),
                    "last_changed_at": row["last_changed_at"].isoformat() if row.get("last_changed_at") else None,
                    "numeric_value": float(row["numeric_value"]) if row.get("numeric_value") is not None else None,
                    "source_url": row.get("source_url"),
                    "source_url_status": row.get("source_url_status"),
                    "statute_citation": row.get("statute_citation"),
                    # A row demoted to a floor relation has NO statute_citation
                    # (citing the floor would be false provenance). Without the
                    # basis here the hierarchical view just loses the citation
                    # with nothing explaining why.
                    "jurisdictional_basis": _basis_from_metadata(row.get("metadata")),
                    "status": row.get("req_status", "active"),
                    "canonical_key": row.get("canonical_key"),
                    "triggered_by": _compute_triggered_by(row.get("trigger_conditions"), facility_attrs),
                })
                total_requirements += 1

            precedence = None
            if item.get("precedence_type"):
                precedence = {
                    "precedence_type": item["precedence_type"],
                    "reasoning_text": item.get("reasoning_text"),
                    "legal_citation": item.get("legal_citation"),
                    "trigger_condition": item.get("rule_trigger_condition"),
                }

            categories_out.append({
                "category": item["category"],
                "category_label": cat_info.get("name", item["category"]),
                "domain": cat_info.get("domain"),
                "authority_type": "geographic",  # v2: from jurisdiction row
                "governing_level": item.get("governing_level", ""),
                "governing_requirement": {
                    "id": str(gov["id"]),
                    "jurisdiction_level": gov.get("jur_level") or gov.get("jurisdiction_level", ""),
                    "jurisdiction_name": gov.get("jur_display_name") or gov.get("jurisdiction_name", ""),
                    "title": gov.get("title", ""),
                    "description": gov.get("description"),
                    "current_value": gov.get("current_value"),
                    "previous_value": gov.get("previous_value"),
                    "previous_description": gov.get("previous_description"),
                    "change_status": gov.get("change_status"),
                    "last_changed_at": gov["last_changed_at"].isoformat() if gov.get("last_changed_at") else None,
                    "numeric_value": float(gov["numeric_value"]) if gov.get("numeric_value") is not None else None,
                    "source_url": gov.get("source_url"),
                    "source_url_status": gov.get("source_url_status"),
                    "statute_citation": gov.get("statute_citation"),
                    "jurisdictional_basis": _basis_from_metadata(gov.get("metadata")),
                    "status": gov.get("req_status", "active"),
                    "canonical_key": gov.get("canonical_key"),
                    "triggered_by": _compute_triggered_by(gov.get("trigger_conditions"), facility_attrs),
                },
                "precedence": precedence,
                "all_levels": all_levels,
                "affected_employee_count": total_affected,
            })

        return {
            "location_id": str(loc["id"]),
            "location_name": loc["name"] or "",
            "city": loc["city"],
            "state": loc["state"],
            "facility_attributes": facility_attrs,
            "categories": categories_out,
            "total_categories": len(categories_out),
            "total_requirements": total_requirements,
        }


async def search_company_requirements(
    conn,
    company_id: UUID,
    query: str,
    location_id: UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    """Full-text search across a company's compliance requirements."""
    pattern = f"%{query}%"
    rows = await conn.fetch(
        """
        SELECT cr.*, bl.city, bl.state, bl.name AS location_name
        FROM compliance_requirements cr
        JOIN business_locations bl ON cr.location_id = bl.id
        LEFT JOIN jurisdiction_requirements cat
          ON cat.id = cr.jurisdiction_requirement_id
        WHERE bl.company_id = $1
          AND ($2::uuid IS NULL OR bl.id = $2)
          AND (
            cr.title ILIKE $3 OR cr.description ILIKE $3
            OR cr.current_value ILIKE $3 OR cr.jurisdiction_name ILIKE $3
            OR cr.category ILIKE $3
          )
        """
        # Search must not be a back door to rows the tab won't show.
        + await codified_gate_sql("cat", conn=conn)
        + """
        ORDER BY
          CASE WHEN cr.title ILIKE $3 THEN 0
               WHEN cr.current_value ILIKE $3 THEN 1
               WHEN cr.category ILIKE $3 THEN 2
               ELSE 3
          END,
          cr.category, cr.jurisdiction_level
        LIMIT $4
        """,
        company_id,
        location_id,
        pattern,
        limit,
    )
    return [dict(row) for row in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Specialization Research Wizard
# ──────────────────────────────────────────────────────────────────────────────


async def discover_specialization_categories(
    specialization: str,
    parent_industry: str = "healthcare",
) -> Dict[str, Any]:
    """Use Gemini to discover regulatory categories for a given specialization."""
    from .gemini_compliance import get_gemini_compliance_service
    from ..compliance_registry import CATEGORY_KEYS

    service = get_gemini_compliance_service()
    slug = specialization.lower().replace(" ", "_")
    # The vertical can BE the industry (a hospitality employer has no
    # sub-specialty above hospitality). Then there is no "parent baseline" to
    # research beyond, and the specialization prompt below would be asking the
    # model to exclude the very categories we want.
    top_level = slug == parent_industry
    industry_tag = parent_industry if top_level else f"{parent_industry}:{slug}"

    if top_level:
        prompt = (
            f"You are a compliance expert. For a business operating in the **{specialization}** "
            f"industry in the United States, identify the regulatory compliance categories that "
            f"are SPECIFIC TO THIS INDUSTRY — the obligations a {specialization} employer has that "
            f"a generic employer in another industry does NOT.\n\n"
            f"Return a JSON object with two keys:\n"
            f"1. \"categories\": an array of objects, each with:\n"
            f"   - \"key\": a snake_case slug (e.g., \"food_handler_certification\")\n"
            f"   - \"label\": a human-readable name\n"
            f"   - \"description\": what specific regulations/standards to research for this category\n"
            f"   - \"authority_sources\": array of authoritative domains (e.g., [\"fda.gov\", \"osha.gov\"])\n"
            f"2. \"research_context\": a paragraph describing the key regulatory bodies, federal statutes, "
            f"and common state-level variations for {specialization} compliance. This will be used as "
            f"context for subsequent research calls.\n\n"
            f"Do NOT include generic employment-law categories that apply to EVERY employer regardless "
            f"of industry (minimum wage, overtime, anti-discrimination, I-9, workers' comp, final pay) — "
            f"those are already researched separately. Aim for 5-15 categories."
        )
    else:
        prompt = (
            f"You are a compliance expert. For a **{specialization}** practice under the "
            f"**{parent_industry}** industry, identify the regulatory compliance categories that "
            f"require specific research beyond the general {parent_industry} baseline.\n\n"
            f"Return a JSON object with two keys:\n"
            f"1. \"categories\": an array of objects, each with:\n"
            f"   - \"key\": a snake_case slug (e.g., \"cardiac_catheterization_safety\")\n"
            f"   - \"label\": a human-readable name\n"
            f"   - \"description\": what specific regulations/standards to research for this category\n"
            f"   - \"authority_sources\": array of authoritative domains (e.g., [\"cms.gov\", \"acc.org\"])\n"
            f"2. \"research_context\": a paragraph describing the key regulatory bodies, federal statutes, "
            f"and common state-level variations for {specialization} compliance. This will be used as "
            f"context for subsequent research calls.\n\n"
            f"Focus on categories unique to {specialization} — do NOT include general {parent_industry} "
            f"categories like HIPAA, billing integrity, or clinical safety unless {specialization} has "
            f"specific sub-requirements. Aim for 5-15 categories."
        )

    result = await service._call_with_retry(
        prompt,
        response_key=None,
        max_retries=1,
        label=f"discover_{specialization}_categories",
    )

    categories = result.get("categories", [])
    for cat in categories:
        cat["is_existing"] = cat.get("key", "") in CATEGORY_KEYS

    industry_context = (
        f"\n\nINDUSTRY CONTEXT -- {specialization.upper()} ({parent_industry.upper()}):\n"
        + result.get("research_context", "")
        + f"\n\nTag each requirement with 'applicable_industries': ['{industry_tag}']."
    )

    return {
        "specialization": specialization,
        "industry_tag": industry_tag,
        "categories": categories,
        "industry_context": industry_context,
    }


async def research_specialization_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    categories: List[str],
    industry_tag: str,
    industry_context: str = "",
    batch_size: int = 4,
    progress_callback: Optional[Callable] = None,
    *,
    skip_existing: bool = True,
    grounded_corpus: str = "",
    citation_index: Optional[Dict[str, Any]] = None,
    route_by_level: bool = False,
    only_levels: Optional[set] = None,
    initial_status: str = "active",
) -> Dict[str, Any]:
    """Research specialization-specific categories for a jurisdiction.

    Generalized version of _research_healthcare/_oncology/_medical_compliance functions.

    ``skip_existing=False`` researches every requested category even if the
    jurisdiction already has rows in it — the fetch-queue case, where the
    category exists but a specific key was missed (the missing key is targeted
    via ``industry_context``).

    ``route_by_level=True`` files each returned row on the jurisdiction its
    STAMPED level belongs to, instead of writing everything to the jurisdiction
    passed in. Without it, researching a city hands back federal and state
    obligations and writes them onto the city — the misparenting jparent01 had to
    migrate away. Off by default so the admin specialization flow keeps its
    existing behavior; the vertical-coverage path turns it on. Adds
    ``jurisdictions_written`` and ``written_by_level`` to the result.

    TODO(known-debt): the default-False means the admin specialization flow and
    the scope-registry research paths still write leaf-misparented rows — the
    writer jparent01 migrated the damage of is alive on those paths. Flipping the
    default needs those three flows re-verified (their skip_existing checks read
    per-jurisdiction state that routing relocates); do it as its own change.

    ``only_levels``: keep ONLY rows whose stamped jurisdiction_level is in this
    set, dropping the rest before they are written. Researching a category at every
    node of a chain (which is how the vertical ledger earns its per-state reuse)
    otherwise collects the same state obligation up to four times — the city, county,
    state and federal passes each volunteer California's amalgam rule, and the model
    names it differently every time, so no deterministic key/title dedupe can
    collapse them. Giving each cell sole ownership of ONE level removes the
    duplication at the source: a row this cell doesn't own is not dropped from the
    catalog, it is simply left to the cell that does own it.

    ``grounded_corpus`` (+ ``citation_index``): fetched official statute text the
    model must extract values FROM and cite (see grounded.py). When present, each
    returned req is gated by ``validate_requirement_citations`` — reqs that cite a
    real corpus id upsert as ``research_source='gemini_grounded'``; ungrounded
    ones stay ``'gemini'`` + ``metadata.grounding='ungrounded'``.
    """
    from .scope_registry.grounded import validate_requirement_citations, validate_penalty_citations
    from .gemini_compliance import get_gemini_compliance_service, refresh_dynamic_categories
    from .jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    # A specialty's categories are confirmed into `compliance_categories` at
    # runtime, but the model-output validator gates on a frozen constant compiled
    # from compliance_registry. Without this refresh every dental/hospitality/etc
    # category reads as "invalid", the requested set empties, and the research call
    # silently falls back to the generic labor default — returning wage law that
    # then gets force-tagged with this industry_tag below.
    await refresh_dynamic_categories(conn)

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    # County nodes store their name in `city` under an internal sentinel
    # ('_county_los angeles'). Passed through raw, the Gemini prompt is asked
    # about a city literally named '_county_los angeles' — degraded or nonsense
    # research whose empty result then gets recorded as a terminal 'empty'
    # verdict. Present it as the county it is.
    if city and city.startswith("_county_"):
        county = county or city[len("_county_"):]
        city = ""
        location_name = f"{county.title()} County, {state}"
    else:
        location_name = f"{city}, {state}" if city else state
    # Federal target = the U.S. national baseline itself (state 'US', no city). The
    # research prompt otherwise treats the jurisdiction as a state/local layer ABOVE
    # federal and returns a null "no additional rule" row — degenerate for federal.
    is_federal = (state == "US" and not city)

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(categories)
    # Pass `conn` — this function is reachable from the Celery vertical-coverage
    # sweep, and workers have no pool (get_connection() raises there).
    corrections = await get_recent_corrections(jurisdiction_id, conn=conn)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    # Check which categories this specialization has already researched.
    # If an industry_tag is provided, only skip categories where requirements
    # tagged with this specific specialization already exist — so cardiology
    # and neurology can both research billing_integrity independently.
    existing_cats: set = set()
    if skip_existing:
        if industry_tag:
            existing = await conn.fetch(
                """SELECT DISTINCT category FROM jurisdiction_requirements
                   WHERE jurisdiction_id = $1
                     AND applicable_industries @> ARRAY[$2::text]""",
                jurisdiction_id,
                industry_tag,
            )
        else:
            existing = await conn.fetch(
                "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                jurisdiction_id,
            )
        existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in categories if cat not in existing_cats)

    if not missing:
        return {"new": 0, "location": location_name, "categories": [], "failed": [], "requirements": [], "skipped": True}

    service = get_gemini_compliance_service()
    total_new = 0
    penalties_stripped = 0  # ungrounded penalty blocks dropped in grounded runs
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []
    jurisdictions_written: set = set()
    # level -> rows that actually LANDED (routing can skip a level it can't
    # place). Coverage decisions must read this, never the pre-write count.
    written_by_level: Dict[str, int] = {}

    async def _write(rows: List[Dict[str, Any]], *, research_source: str) -> None:
        if route_by_level:
            outcome = await _upsert_requirements_routed_additive(
                conn, jurisdiction_id, rows, research_source=research_source,
                initial_status=initial_status,
            )
            for level, info in outcome.items():
                written_by_level[level] = written_by_level.get(level, 0) + info["written"]
                if info["jurisdiction_id"]:
                    jurisdictions_written.add(info["jurisdiction_id"])
        else:
            await _upsert_requirements_additive(
                conn, jurisdiction_id, rows, research_source=research_source,
                initial_status=initial_status,
            )
            jurisdictions_written.add(jurisdiction_id)
            for r in rows:
                level = (r.get("jurisdiction_level") or "city").lower().strip()
                written_by_level[level] = written_by_level.get(level, 0) + 1

    # Batch categories
    batches = [missing[i:i + batch_size] for i in range(0, len(missing), batch_size)]
    progress_idx = 0

    for batch in batches:
        batch_label = ", ".join(c.replace("_", " ") for c in batch)
        progress_idx += len(batch)
        if progress_callback:
            progress_callback(progress_idx, len(missing), f"Researching {batch_label} for {location_name}...")

        try:
            reqs = await service.research_location_compliance(
                city=city,
                state=state,
                county=county,
                categories=batch,
                source_context=source_context,
                corrections_context=corrections_context,
                preemption_rules=preemption_rules,
                has_local_ordinance=has_local_ordinance,
                industry_context=industry_context,
                is_federal=is_federal,
                grounded_corpus=grounded_corpus,
            )
            reqs = reqs or []

            if only_levels:
                kept = [
                    r for r in reqs
                    if (r.get("jurisdiction_level") or "city").lower().strip() in only_levels
                ]
                if len(kept) != len(reqs):
                    logger.info(
                        "specialization: %s/%s — dropped %d row(s) outside this cell's level %s "
                        "(owned by another cell in the chain)",
                        location_name, ",".join(batch), len(reqs) - len(kept), sorted(only_levels),
                    )
                reqs = kept

            for req in reqs:
                _clamp_varchar_fields(req)
                if industry_tag and not req.get("applicable_industries"):
                    req["applicable_industries"] = [industry_tag]

            if reqs:
                if grounded_corpus:
                    # Gate on the corpus the model was given. Grounded reqs
                    # (cited a real statute excerpt) upsert as gemini_grounded;
                    # the rest stay gemini + a metadata.grounding marker.
                    validate_requirement_citations(reqs, citation_index)
                    # Penalties are values too: gate them on the same corpus,
                    # independently of the req-level verdict (penalty text often
                    # lives in a different section). Any penalty block that isn't
                    # grounded in the fetched statute is dropped rather than
                    # persisted from recall — the locator invariant — which also
                    # keeps a recall pass from clobbering skill-written penalties
                    # (real source_url/verified_date) via the metadata merge.
                    validate_penalty_citations(
                        reqs, citation_index, verified_date=date.today().isoformat())
                    for r in reqs:
                        p = r.get("penalties")
                        if isinstance(p, dict) and p.get("grounding") != "grounded":
                            r["penalties"] = None
                            penalties_stripped += 1
                    grounded = [r for r in reqs if r.get("grounded")]
                    ungrounded = [r for r in reqs if not r.get("grounded")]
                    for r in grounded:
                        r["grounding"] = "grounded"
                    for r in ungrounded:
                        r["grounding"] = "ungrounded"
                    if grounded:
                        await _write(grounded, research_source="gemini_grounded")
                    if ungrounded:
                        await _write(ungrounded, research_source="gemini")
                else:
                    await _write(reqs, research_source="gemini")
                total_new += len(reqs)
                added_requirements.extend(reqs)
        except Exception as e:
            failed_categories.extend(batch)
            print(f"[Specialization Research] Error researching {batch_label} for {location_name}: {e}")

    if penalties_stripped:
        # Grounded runs drop penalty blocks not backed by the fetched corpus; the
        # corpus is the requirement's own sections, so enforcement-subpart penalties
        # are routinely stripped. Surface it so a coverage dip reads as expected,
        # not as a regression.
        print(f"[Specialization Research] {location_name}: dropped {penalties_stripped} "
              f"ungrounded penalty block(s) (not in the fetched corpus)")

    return {
        "new": total_new,
        "location": location_name,
        "categories": [c for c in missing if c not in failed_categories],
        "failed": failed_categories,
        "requirements": added_requirements,
        "penalties_stripped": penalties_stripped,
        "jurisdictions_written": jurisdictions_written,
        "written_by_level": written_by_level,
    }


async def get_specialization_completeness(
    conn,
    industry_tag: str,
    expected_categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get completeness data for a specialization across jurisdictions."""
    rows = await conn.fetch(
        """
        SELECT j.state, j.city,
               COUNT(DISTINCT jr.category) AS categories_covered,
               COUNT(*) AS total_requirements
        FROM jurisdiction_requirements jr
        JOIN jurisdictions j ON j.id = jr.jurisdiction_id
        WHERE jr.applicable_industries @> ARRAY[$1::text]
        GROUP BY j.state, j.city
        ORDER BY j.state, j.city
        """,
        industry_tag,
    )
    result = []
    for r in rows:
        entry = {
            "state": r["state"],
            "city": r["city"] or "",
            "categories_covered": r["categories_covered"],
            "total_requirements": r["total_requirements"],
        }
        if expected_categories:
            entry["coverage_pct"] = round(r["categories_covered"] / len(expected_categories) * 100, 1)
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Admin: cherry-pick a jurisdiction requirement into a company location
# ---------------------------------------------------------------------------


async def _insert_catalog_requirement(
    conn,
    location_id: UUID,
    jr: dict,
    governance_source: str,
    *,
    on_conflict_nothing: bool,
) -> Optional[dict]:
    """Project one ``jurisdiction_requirements`` row (``jr``) into
    ``compliance_requirements`` for *location_id*, stamping the catalog FK
    (``jurisdiction_requirement_id``) — the SSOT link / dedup identity — and the
    given ``governance_source``.

    When *on_conflict_nothing* is True, a row already linked to this
    (location_id, catalog requirement) is a no-op and returns ``None`` (via the
    ``uq_compliance_requirements_loc_jr`` partial unique index). The conflict
    clause is a static fragment — no user input is interpolated.
    """
    req_key = f"{jr['category']}:{jr['regulation_key'] or jr['title']}"
    conflict = (
        "ON CONFLICT (location_id, jurisdiction_requirement_id) "
        "WHERE jurisdiction_requirement_id IS NOT NULL DO NOTHING"
        if on_conflict_nothing
        else ""
    )
    row = await conn.fetchrow(
        f"""
        INSERT INTO compliance_requirements (
            location_id, category, jurisdiction_level, jurisdiction_name,
            title, description, current_value, numeric_value,
            source_url, source_name, effective_date,
            requirement_key, governance_source, jurisdiction_requirement_id
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        {conflict}
        RETURNING id, category, jurisdiction_level, jurisdiction_name,
                  title, description, current_value, numeric_value,
                  source_url, source_name, effective_date,
                  requirement_key, governance_source, jurisdiction_requirement_id
        """,
        location_id,
        jr["category"],
        jr["jurisdiction_level"],
        jr["jurisdiction_name"],
        jr["title"],
        jr["description"],
        jr["current_value"],
        jr["numeric_value"],
        jr["source_url"],
        jr.get("source_name"),
        jr["effective_date"],
        req_key,
        governance_source,
        jr["id"],
    )
    if row is None:
        return None
    result = dict(row)
    result["id"] = str(result["id"])
    if result.get("jurisdiction_requirement_id") is not None:
        result["jurisdiction_requirement_id"] = str(result["jurisdiction_requirement_id"])
    return result


async def admin_add_requirement_to_location(
    location_id: UUID, company_id: UUID, jurisdiction_requirement_id: UUID,
) -> dict:
    """Copy a single jurisdiction_requirements row into compliance_requirements
    for *location_id*, marking governance_source = 'admin_override'.

    Returns the inserted requirement dict, or raises if duplicate/not found.
    """
    from ...database import get_connection

    async with get_connection() as conn:
        if not await verify_location_ownership(conn, location_id, company_id):
            raise ValueError("Location does not belong to this company")

        # 1. Fetch the source row
        jr = await conn.fetchrow(
            "SELECT * FROM jurisdiction_requirements WHERE id = $1",
            jurisdiction_requirement_id,
        )
        if not jr:
            raise ValueError("Jurisdiction requirement not found")

        req_key = f"{jr['category']}:{jr['regulation_key'] or jr['title']}"

        # 2. Check for duplicate — by catalog FK (exact) OR legacy string key.
        exists = await conn.fetchval(
            """
            SELECT 1 FROM compliance_requirements
            WHERE location_id = $1
              AND (jurisdiction_requirement_id = $2 OR requirement_key = $3)
            """,
            location_id, jurisdiction_requirement_id, req_key,
        )
        if exists:
            raise ValueError("Requirement already exists for this location")

        # 3. Insert (stamps the catalog FK + provenance)
        return await _insert_catalog_requirement(
            conn, location_id, jr, "admin_override", on_conflict_nothing=False
        )


async def admin_add_requirements_to_location_batch(
    conn,
    location_id: UUID,
    company_id: UUID,
    jr_ids: list,
    governance_source: str = "onboarding_wizard",
) -> dict:
    """Project many jurisdiction_requirements rows into compliance_requirements
    for *location_id* on a shared connection (so callers can run inside their own
    transaction — e.g. onboarding finalize).

    Idempotent: a row already linked to a given catalog requirement at this
    location is skipped via the partial unique index. Returns
    ``{written, skipped_existing, missing_jr}``.

    Non-active rows (grounding-quarantined 'under_review', admin-rejected
    'repealed') are counted as ``missing_jr`` and never projected. This is an
    id-keyed path, so it bypasses the ``_load_jurisdiction_requirements`` choke
    point: a session whose resolved scope was computed BEFORE a row was
    quarantined would otherwise still serve it to the tenant at finalize.
    """
    if not await verify_location_ownership(conn, location_id, company_id):
        raise ValueError("Location does not belong to this company")

    written = skipped = missing = 0
    for jr_id in jr_ids:
        jr = await conn.fetchrow(
            "SELECT * FROM jurisdiction_requirements WHERE id = $1 "
            "AND COALESCE(status, 'active') = 'active'",
            jr_id,
        )
        if not jr:
            missing += 1
            continue
        row = await _insert_catalog_requirement(
            conn, location_id, jr, governance_source, on_conflict_nothing=True
        )
        if row is None:
            skipped += 1
        else:
            written += 1
    return {"written": written, "skipped_existing": skipped, "missing_jr": missing}
