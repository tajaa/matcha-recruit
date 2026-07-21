"""compliance_service.normalize — J6 split of compliance_service.py."""
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

from app.core.services.compliance_service._shared import (
    JURISDICTION_PRIORITY,
    MATERIAL_CHANGE_THRESHOLDS,
    VALID_LEGISLATION_STATUSES,
)


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
