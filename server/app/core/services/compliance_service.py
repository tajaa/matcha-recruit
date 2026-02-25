from typing import Optional, List, AsyncGenerator, Dict, Any, Callable
from uuid import UUID
from datetime import date, datetime, timedelta
import asyncio
import json
import re

import asyncpg

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


# Threshold for numeric material changes (e.g. $0.25 for wages)
MATERIAL_CHANGE_THRESHOLDS = {
    'minimum_wage': 0.25,
    'default': 0.10,
}

JURISDICTION_PRIORITY = {'city': 1, 'county': 2, 'state': 3, 'federal': 4}

VALID_LEGISLATION_STATUSES = {
    "proposed",
    "passed",
    "signed",
    "effective_soon",
    "effective",
    "dismissed",
}

REQUIRED_LABOR_CATEGORIES = {
    "minimum_wage",
    "overtime",
    "sick_leave",
    "meal_breaks",
    "pay_frequency",
    "final_pay",
    "minor_work_permit",
    "scheduling_reporting",
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
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District Of Columbia",
}


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
        jl = r.get("jurisdiction_level") if isinstance(r, dict) else getattr(r, "jurisdiction_level", None)
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
        print(f"[Compliance] Stripped {stripped} city-level req(s), promoted {len(promoted)} to state-level")

    return non_city + promoted
# Valid rate_types for minimum_wage requirements
VALID_RATE_TYPES = {
    "general",
    "tipped",
    "exempt_salary",
    "hotel",
    "fast_food",
    "healthcare",
    "large_employer",
    "small_employer",
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
            s = s[len(prefix):].strip()
    for suffix in (" city", " county"):
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
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

    text = " ".join(
        str(req.get(k) or "")
        for k in ("title", "description", "current_value")
    ).lower()

    if any(token in text for token in ("exempt", "salary threshold", "salary basis", "annual salary")):
        return "exempt_salary"
    if any(token in text for token in ("tipped", "tip credit", "cash wage", "tips")):
        return "tipped"
    return "general"


def _normalize_requirement_categories(requirements: list[dict]) -> None:
    """Normalize category names and minimum_wage rate_type in-place."""
    for req in requirements:
        req["category"] = _normalize_category(req.get("category")) or req.get("category")
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
            stripped = title[match.end():].lstrip(" -:,")
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
        freq_tokens = {"semimonthly", "biweekly", "weekly", "monthly", "yearly", "daily"}
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


def _is_special_min_wage(base_key: str, title: Optional[str], description: Optional[str]) -> bool:
    """DEPRECATED: Use rate_type field instead. Kept for backwards compatibility."""
    if not base_key:
        return False
    if base_key in _MIN_WAGE_GENERAL_KEYS:
        return False
    text = " ".join(filter(None, [base_key, title or "", description or ""])).lower()
    return any(keyword in text for keyword in _MIN_WAGE_SPECIAL_KEYWORDS)


def _is_material_numeric_change(old_num: Optional[float], new_num: Optional[float], category: Optional[str]) -> bool:
    """Deterministic check: is the numeric difference above our threshold?"""
    if old_num is None or new_num is None:
        return False
    threshold = MATERIAL_CHANGE_THRESHOLDS.get(
        _normalize_category(category) or '', MATERIAL_CHANGE_THRESHOLDS['default']
    )
    return abs(float(old_num) - float(new_num)) >= threshold


def _is_material_text_change(old_text: Optional[str], new_text: Optional[str], category: Optional[str] = None) -> bool:
    """Deterministic check: do the normalized text values differ?"""
    return _normalize_value_text(old_text, category) != _normalize_value_text(new_text, category)


def _get_numeric_from_req(req) -> Optional[float]:
    val = req.get("numeric_value") if isinstance(req, dict) else getattr(req, "numeric_value", None)
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            pass
    current = req.get("current_value") if isinstance(req, dict) else getattr(req, "current_value", None)
    return _extract_numeric_value(current)


def _pick_best_by_priority(reqs):
    if not reqs:
        return None
    best_priority = min(
        JURISDICTION_PRIORITY.get(
            r['jurisdiction_level'] if isinstance(r, dict) else r.jurisdiction_level, 99
        )
        for r in reqs
    )
    candidates = [
        r for r in reqs
        if JURISDICTION_PRIORITY.get(
            r['jurisdiction_level'] if isinstance(r, dict) else r.jurisdiction_level, 99
        ) == best_priority
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

async def _get_or_create_jurisdiction(conn, city: str, state: str, county: Optional[str] = None) -> UUID:
    """Find or create a jurisdiction row with hierarchy resolution.

    Auto-resolves county from jurisdiction_reference when not provided,
    then links city -> county -> state via parent_id.
    """
    norm_city, ref_county = await _resolve_reference_city(conn, city, state)
    norm_state = state.upper().strip()
    if not county and ref_county:
        county = ref_county

    # 2. Get or create city jurisdiction
    await conn.execute(
        """
        INSERT INTO jurisdictions (city, state, county)
        VALUES ($1, $2, $3)
        ON CONFLICT (city, state) DO NOTHING
        """,
        norm_city, norm_state, county,
    )
    city_row = await conn.fetchrow(
        "SELECT id, county, parent_id FROM jurisdictions WHERE city = $1 AND state = $2",
        norm_city, norm_state,
    )
    city_id = city_row["id"]

    # 3. Get or create state jurisdiction (uses empty-string city convention)
    state_j = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE city = '' AND state = $1",
        norm_state,
    )
    if not state_j:
        await conn.execute(
            "INSERT INTO jurisdictions (city, state) VALUES ('', $1) ON CONFLICT (city, state) DO NOTHING",
            norm_state,
        )
        state_j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE city = '' AND state = $1",
            norm_state,
        )
    state_id = state_j["id"]

    # 4. Link county -> state, city -> county (or city -> state if no county)
    if county:
        # Update city's county field if it was auto-resolved
        if not city_row["county"]:
            await conn.execute(
                "UPDATE jurisdictions SET county = $2 WHERE id = $1",
                city_id, county,
            )

        # Get or create county jurisdiction
        county_norm = county.lower().strip()
        county_j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE city = $1 AND state = $2",
            f"_county_{county_norm}", norm_state,
        )
        if not county_j:
            await conn.execute(
                """
                INSERT INTO jurisdictions (city, state, county, parent_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (city, state) DO NOTHING
                """,
                f"_county_{county_norm}", norm_state, county, state_id,
            )
            county_j = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE city = $1 AND state = $2",
                f"_county_{county_norm}", norm_state,
            )

        county_id = county_j["id"]

        # Ensure county -> state link
        await conn.execute(
            "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1 AND parent_id IS NULL",
            county_id, state_id,
        )

        # Link city -> county (even if previously linked directly to state)
        if not city_row["parent_id"] or city_row["parent_id"] == state_id:
            await conn.execute(
                "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1",
                city_id, county_id,
            )
    else:
        # No county: link city -> state directly
        if not city_row["parent_id"]:
            await conn.execute(
                "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1",
                city_id, state_id,
            )

    return city_id


async def _lookup_has_local_ordinance(conn, city: str, state: str) -> Optional[bool]:
    """Check jurisdiction_reference for whether a city has its own local ordinance."""
    normalized_city = _normalize_city_key(city)
    normalized_state = state.upper().strip()
    lookup_city = _CITY_ALIAS_FALLBACKS.get((normalized_state, normalized_city), normalized_city)

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
        print(f"[Compliance] has_local_ordinance lookup: city={city!r}, state={state!r} → {result}")
        return result
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return None


async def _is_jurisdiction_fresh(conn, jurisdiction_id: UUID, threshold_days: int) -> bool:
    """Check if jurisdiction was verified recently enough to skip Gemini."""
    row = await conn.fetchrow(
        "SELECT last_verified_at FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not row or not row["last_verified_at"]:
        return False
    age = datetime.utcnow() - row["last_verified_at"]
    return age < timedelta(days=threshold_days)


async def _load_jurisdiction_requirements(conn, jurisdiction_id: UUID) -> List[Dict]:
    """Read requirements from the jurisdiction repository."""
    rows = await conn.fetch(
        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    return [dict(r) for r in rows]


async def _load_jurisdiction_legislation(conn, jurisdiction_id: UUID) -> List[Dict]:
    """Read legislation from the jurisdiction repository."""
    rows = await conn.fetch(
        "SELECT * FROM jurisdiction_legislation WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    return [dict(r) for r in rows]


def _jurisdiction_row_to_dict(jr: dict) -> dict:
    """Convert a jurisdiction_requirements row to a dict compatible with sync functions."""
    return {
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
        "effective_date": jr["effective_date"].isoformat() if jr.get("effective_date") else None,
        "expiration_date": jr["expiration_date"].isoformat() if jr.get("expiration_date") else None,
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
    if not county_row or not county_row["city"] or not county_row["city"].startswith("_county_"):
        return None

    if not await _is_jurisdiction_fresh(conn, county_id, threshold_days):
        return None

    j_reqs = await _load_jurisdiction_requirements(conn, county_id)
    if not j_reqs:
        return None

    print(f"[Compliance] Reusing county jurisdiction data ({len(j_reqs)} reqs) for city jurisdiction {city_jurisdiction_id}")
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
                
            print(f"[Compliance] Reusing state jurisdiction data ({len(j_reqs)} reqs) for jurisdiction {jurisdiction_id}")
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
    
    # Try county
    county_reqs = await _try_load_county_requirements(conn, jurisdiction_id, threshold_days)
    if county_reqs:
        target_set = {_normalize_category(c) or c for c in missing}
        fill = [r for r in county_reqs if (_normalize_category(r.get("category")) or r.get("category")) in target_set]
        if fill:
            requirements.extend(fill)
            filled_any = True
            missing = _missing_required_categories(requirements)
            if not missing:
                return True
                
    # Try state
    state_reqs = await _try_load_state_requirements(conn, jurisdiction_id, threshold_days)
    if state_reqs:
        target_set = {_normalize_category(c) or c for c in missing}
        fill = [r for r in state_reqs if (_normalize_category(r.get("category")) or r.get("category")) in target_set]
        if fill:
            requirements.extend(fill)
            filled_any = True
            
    return filled_any


async def _get_county_jurisdiction_id(conn, city_jurisdiction_id: UUID) -> Optional[UUID]:
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
) -> List[Dict[str, Any]]:
    """Refresh missing categories, merge with current requirements, and upsert source-of-truth."""
    if not missing_categories:
        return list(current_requirements)

    known_sources = await get_known_sources(conn, jurisdiction_id)
    if not known_sources:
        discovered = await service.discover_jurisdiction_sources(
            city=city, state=state, county=county,
        )
        for src in discovered:
            domain = (src.get("domain") or "").lower()
            if domain:
                for cat in src.get("categories", []):
                    await record_source(conn, jurisdiction_id, domain, src.get("name"), cat)
        known_sources = await get_known_sources(conn, jurisdiction_id)

    source_context = build_context_prompt(known_sources)
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
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
    )
    refreshed_requirements = refreshed_requirements or []

    if not refreshed_requirements:
        return list(current_requirements)

    target_set = {_normalize_category(cat) or cat for cat in missing_categories}
    preserved = [
        req for req in current_requirements
        if (_normalize_category(req.get("category")) or req.get("category")) not in target_set
    ]
    merged_requirements = preserved + refreshed_requirements

    if has_local_ordinance is False:
        merged_requirements = _filter_city_level_requirements(merged_requirements, state)

    _normalize_requirement_categories(merged_requirements)
    merged_requirements = await _filter_with_preemption(conn, merged_requirements, state)
    for req in merged_requirements:
        _clamp_varchar_fields(req)

    await _upsert_jurisdiction_requirements(conn, jurisdiction_id, merged_requirements)

    if has_local_ordinance is False:
        county_jid = await _get_county_jurisdiction_id(conn, jurisdiction_id)
        if county_jid:
            await _upsert_jurisdiction_requirements(conn, county_jid, merged_requirements)
            print(f"[Compliance] Also cached refreshed coverage to county jurisdiction {county_jid}")

    for req in refreshed_requirements:
        source_url = req.get("source_url", "")
        if source_url:
            domain = extract_domain(source_url)
            if domain:
                await record_source(
                    conn, jurisdiction_id, domain,
                    req.get("source_name"), req.get("category", "")
                )

    return merged_requirements


async def _upsert_jurisdiction_requirements(conn, jurisdiction_id: UUID, reqs: List[Dict]):
    """Write Gemini results into the jurisdiction repository. Remove stale rows."""
    new_keys = set()
    for req in reqs:
        requirement_key = _compute_requirement_key(req)
        new_keys.add(requirement_key)
        await conn.execute(
            """
            INSERT INTO jurisdiction_requirements
                (jurisdiction_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                 title, description, current_value, numeric_value, source_url, source_name,
                 effective_date, expiration_date, last_verified_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                category = EXCLUDED.category,
                rate_type = EXCLUDED.rate_type,
                jurisdiction_level = EXCLUDED.jurisdiction_level,
                jurisdiction_name = EXCLUDED.jurisdiction_name,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                previous_value = jurisdiction_requirements.current_value,
                current_value = EXCLUDED.current_value,
                numeric_value = EXCLUDED.numeric_value,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                effective_date = EXCLUDED.effective_date,
                expiration_date = EXCLUDED.expiration_date,
                last_verified_at = NOW(),
                last_changed_at = CASE
                    WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                    THEN NOW() ELSE jurisdiction_requirements.last_changed_at END,
                updated_at = NOW()
            """,
            jurisdiction_id, requirement_key,
            req.get("category"), req.get("rate_type"), req.get("jurisdiction_level"),
            req.get("jurisdiction_name"), req.get("title"), req.get("description"),
            req.get("current_value"), req.get("numeric_value"),
            req.get("source_url"), req.get("source_name"),
            parse_date(req.get("effective_date")), parse_date(req.get("expiration_date")),
        )

    # Remove jurisdiction rows not in new result set
    if new_keys:
        existing_rows = await conn.fetch(
            "SELECT id, requirement_key FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
            jurisdiction_id,
        )
        for row in existing_rows:
            if row["requirement_key"] not in new_keys:
                await conn.execute(
                    "DELETE FROM jurisdiction_requirements WHERE id = $1", row["id"]
                )

    # Update jurisdiction counts and timestamp
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    await conn.execute(
        "UPDATE jurisdictions SET last_verified_at = NOW(), requirement_count = $1, updated_at = NOW() WHERE id = $2",
        count, jurisdiction_id,
    )


async def _upsert_jurisdiction_legislation(conn, jurisdiction_id: UUID, items: List[Dict]):
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
            jurisdiction_id, leg_key, item.get("category"), item.get("title"),
            item.get("description"), item.get("current_status", "proposed"),
            eff_date, item.get("impact_summary"),
            item.get("source_url"), item.get("source_name"), confidence,
        )

    # Update legislation count
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM jurisdiction_legislation WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    await conn.execute(
        "UPDATE jurisdictions SET legislation_count = $1, updated_at = NOW() WHERE id = $2",
        count, jurisdiction_id,
    )


async def _sync_requirements_to_location(
    conn, location_id: UUID, company_id: UUID, reqs: List[Dict],
    create_alerts: bool = True, service=None,
) -> Dict[str, int]:
    """Sync a list of requirement dicts to a location's compliance_requirements.

    Runs the existing change-detection logic (upsert, history snapshot, alerts).
    Returns {"new": N, "updated": N, "alerts": N, "changes_to_verify": [...]}.
    """
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
        normalized_category = _normalize_category(row_dict.get("category")) or row_dict.get("category")

        if key and (row_dict.get("requirement_key") != key or row_dict.get("category") != normalized_category):
            await conn.execute(
                "UPDATE compliance_requirements SET requirement_key = $1, category = $2, updated_at = NOW() WHERE id = $3",
                key, normalized_category, row_dict["id"],
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
        await conn.execute("DELETE FROM compliance_requirements WHERE id = $1", dup["id"])

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
                    if ekey.startswith(norm_cat + ":") and ekey not in new_requirement_keys
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

            numeric_changed = old_num is not None and new_num is not None and abs(float(old_num) - float(new_num)) > 0.001
            text_changed = old_value != new_value
            metadata_changed = any([
                existing.get("title") != req.get("title"),
                existing.get("description") != req.get("description"),
                existing.get("source_url") != req.get("source_url"),
                existing.get("source_name") != req.get("source_name"),
                existing.get("effective_date") != parse_date(req.get("effective_date")),
                text_changed, numeric_changed,
            ])

            if metadata_changed:
                updated_count += 1
                await _snapshot_to_history(conn, existing, location_id)
                if material_change and create_alerts:
                    changes_to_verify.append({
                        "req": req, "existing": existing,
                        "old_value": old_value, "new_value": new_value,
                        "requirement_key": requirement_key,
                    })

            previous_value = existing.get("previous_value")
            last_changed_at = existing.get("last_changed_at")
            if material_change:
                previous_value = old_value
                last_changed_at = datetime.utcnow()

            await _update_requirement(conn, existing["id"], requirement_key, req, previous_value, last_changed_at)
            existing_by_key[requirement_key] = {**existing, "id": existing["id"]}
        else:
            # Guard: don't insert a min-wage decrease that bypassed the
            # matched-existing path due to key drift (title changed).
            # Only compare against entries with the SAME rate_type to avoid
            # rejecting legitimate lower variants (tipped, hotel, etc.).
            if _normalize_category(req.get("category")) == "minimum_wage":
                new_num_val = req.get("numeric_value") or _extract_numeric_value(req.get("current_value"))
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
                        e_num = erow.get("numeric_value") or _extract_numeric_value(erow.get("current_value"))
                        if e_num is not None and (float(e_num) - float(new_num_val)) > 0.005:
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
                    conn, location_id, company_id, req_id,
                    f"New Requirement: {req.get('title')}",
                    req.get("description") or "New compliance requirement identified.",
                    "info", req.get("category"),
                    source_url=req.get("source_url"), source_name=req.get("source_name"),
                    alert_type="new_requirement",
                )
            existing_by_key[requirement_key] = {"id": req_id}

    # Stale requirements cleanup
    stale_keys = set(existing_by_key.keys()) - new_requirement_keys
    for stale_key in stale_keys:
        stale = existing_by_key[stale_key]
        stale_id = stale.get("id")
        if stale_id:
            await _snapshot_to_history(conn, stale, location_id)
            await conn.execute("DELETE FROM compliance_requirements WHERE id = $1", stale_id)

    return {
        "new": new_count,
        "updated": updated_count,
        "alerts": alert_count,
        "changes_to_verify": changes_to_verify,
        "existing_by_key": existing_by_key,
    }


def _compute_requirement_key(req) -> str:
    cat = req.get("category") if isinstance(req, dict) else req.category
    title = req.get("title") if isinstance(req, dict) else req.title
    jname = req.get("jurisdiction_name") if isinstance(req, dict) else getattr(req, "jurisdiction_name", None)
    rate_type = req.get("rate_type") if isinstance(req, dict) else getattr(req, "rate_type", None)
    cat_key = _normalize_category(cat) or ""
    base_title = _base_title(title or "", jname)
    base_key = _normalize_title_key(base_title)

    # Include rate_type in key for minimum_wage to allow multiple entries per jurisdiction.
    # Always emit a rate_type key for minimum_wage to keep keys stable.
    if cat_key == "minimum_wage":
        normalized_rate_type = (
            _coerce_minimum_wage_rate_type(req)
            if isinstance(req, dict)
            else (_normalize_rate_type(rate_type) or "general")
        )
        return f"{cat_key}:{normalized_rate_type}"

    return f"{cat_key}:{base_key}"


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


async def _create_check_log(conn, location_id: UUID, company_id: UUID, check_type: str = "manual") -> UUID:
    """Create a check log entry and return its ID."""
    return await conn.fetchval(
        """
        INSERT INTO compliance_check_log (location_id, company_id, check_type, status, started_at)
        VALUES ($1, $2, $3, 'running', NOW())
        RETURNING id
        """,
        location_id, company_id, check_type,
    )


async def _complete_check_log(conn, log_id: UUID, new_count: int, updated_count: int, alert_count: int, error: Optional[str] = None):
    """Mark a check log entry as completed or failed."""
    status = "failed" if error else "completed"
    await conn.execute(
        """
        UPDATE compliance_check_log
        SET status = $1, completed_at = NOW(), new_count = $2, updated_count = $3, alert_count = $4, error_message = $5
        WHERE id = $6
        """,
        status, new_count, updated_count, alert_count, error, log_id,
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
) -> UUID:
    """Create a compliance alert with extended fields. Returns alert ID."""
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
        location_id, company_id, requirement_id, title, message, severity,
        category, source_url, source_name,
        alert_type, confidence_score,
        json.dumps(verification_sources) if verification_sources else None,
        effective_date,
        json.dumps(metadata) if metadata else None,
    )

    # Best-effort email notification for every newly created alert.
    try:
        from .email import get_email_service

        email_service = get_email_service()
        if email_service.is_configured():
            company_name = await conn.fetchval(
                "SELECT name FROM companies WHERE id = $1",
                company_id,
            ) or "Your company"

            location_row = await conn.fetchrow(
                "SELECT name, city, state FROM business_locations WHERE id = $1",
                location_id,
            )
            if location_row:
                location_name = location_row["name"] or f"{location_row['city']}, {location_row['state']}"
            else:
                location_name = "your location"

            contact_rows = await conn.fetch(
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
                {"email": row["email"], "name": row["name"] or row["email"]}
                for row in contact_rows
            ]
            if contacts:
                jurisdictions: list[str] = []
                if metadata and isinstance(metadata, dict):
                    if metadata.get("jurisdiction_name"):
                        jurisdictions.append(str(metadata["jurisdiction_name"]))
                    elif metadata.get("jurisdiction_id"):
                        jurisdiction_row = await conn.fetchrow(
                            "SELECT city, state FROM jurisdictions WHERE id = $1",
                            metadata["jurisdiction_id"],
                        )
                        if jurisdiction_row:
                            jurisdictions.append(f"{jurisdiction_row['city']}, {jurisdiction_row['state']}")

                send_tasks = [
                    email_service.send_compliance_change_notification_email(
                        to_email=contact["email"],
                        to_name=contact.get("name"),
                        company_name=company_name,
                        location_name=location_name,
                        changed_requirements_count=1,
                        jurisdictions=jurisdictions or None,
                    )
                    for contact in contacts
                ]
                await asyncio.gather(*send_tasks, return_exceptions=True)
    except Exception as email_error:
        print(f"[Compliance] Failed to send alert notification email for alert {alert_id}: {email_error}")

    return alert_id


def _record_change_notification_item(
    change_items: List[Dict[str, str]],
    req: dict,
    change_info: dict,
):
    """Capture lightweight change details for post-check admin email notifications."""
    change_items.append(
        {
            "title": req.get("title") or "",
            "jurisdiction_name": req.get("jurisdiction_name") or "",
            "old_value": str(change_info.get("old_value") or ""),
            "new_value": str(change_info.get("new_value") or ""),
        }
    )


async def _get_company_admin_contacts(company_id: UUID) -> tuple[str, List[Dict[str, str]]]:
    """Get company name and business admin/client email contacts."""
    from ...database import get_connection

    async with get_connection() as conn:
        company_name = await conn.fetchval(
            "SELECT name FROM companies WHERE id = $1",
            company_id,
        ) or "Your company"

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
        {"email": row["email"], "name": row["name"] or row["email"]}
        for row in rows
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
        print("[Compliance] Email service not configured, skipping admin change notifications")
        return 0

    company_name, contacts = await _get_company_admin_contacts(company_id)
    if not contacts:
        print(f"[Compliance] No business admin contacts found for company {company_id}")
        return 0

    jurisdictions = sorted(
        {
            jurisdiction
            for _, jurisdiction, _, _ in unique_changes
            if jurisdiction
        }
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
            print(f"[Compliance] Failed to send change notification to {contact['email']}: {result}")
            continue
        if result:
            sent_count += 1

    if sent_count:
        print(f"[Compliance] Sent compliance change notifications to {sent_count}/{len(contacts)} admin(s)")

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
        jurisdiction_id, alert_id, requirement_key, category,
        round(predicted_confidence, 2), predicted_is_change,
        json.dumps(verification_sources) if verification_sources else None,
    )


async def _upsert_requirement(
    conn, location_id: UUID, requirement_key: str, req: dict
) -> UUID:
    """Insert a new compliance requirement. Returns the new ID."""
    return await conn.fetchval(
        """
        INSERT INTO compliance_requirements
        (location_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name, title, description,
         current_value, numeric_value, source_url, source_name, effective_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        RETURNING id
        """,
        location_id, requirement_key, req.get("category"), req.get("rate_type"),
        req.get("jurisdiction_level"), req.get("jurisdiction_name"), req.get("title"),
        req.get("description"), req.get("current_value"), req.get("numeric_value"),
        req.get("source_url"), req.get("source_name"), parse_date(req.get("effective_date")),
    )


async def _update_requirement(
    conn, existing_id: UUID, requirement_key: str, req: dict,
    previous_value: Optional[str], last_changed_at: Optional[datetime]
):
    """Update an existing compliance requirement."""
    await conn.execute(
        """
        UPDATE compliance_requirements
        SET requirement_key = $1, category = $2, rate_type = $3, jurisdiction_name = $4, title = $5,
            current_value = $6, numeric_value = $7, previous_value = $8, last_changed_at = $9,
            description = $10, source_url = $11, source_name = $12, effective_date = $13,
            updated_at = NOW()
        WHERE id = $14
        """,
        requirement_key, req.get("category"), req.get("rate_type"), req.get("jurisdiction_name"),
        req.get("title"), req.get("current_value"), req.get("numeric_value"), previous_value,
        last_changed_at, req.get("description"), req.get("source_url"), req.get("source_name"),
        parse_date(req.get("effective_date")), existing_id,
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
        row_dict["id"], location_id, row_dict.get("category"), row_dict.get("rate_type"),
        row_dict.get("jurisdiction_level"), row_dict.get("jurisdiction_name"),
        row_dict.get("title"), row_dict.get("description"),
        row_dict.get("current_value"), row_dict.get("numeric_value"),
        row_dict.get("source_url"), row_dict.get("source_name"),
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
            location_id, leg_key,
        )

        eff_date = parse_date(item.get("expected_effective_date"))
        confidence = item.get("confidence")
        if confidence is not None:
            confidence = float(confidence)

        normalized_status = _normalize_legislation_status(
            item.get("current_status", existing["current_status"] if existing else None),
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
                normalized_status, eff_date, item.get("impact_summary"),
                item.get("source_url"), item.get("source_name"),
                confidence, item.get("description"),
                existing["id"],
            )
        else:
            alert_id = await _create_alert(
                conn, location_id, company_id, None,
                f"Upcoming: {item.get('title', 'Unknown')}",
                item.get("impact_summary") or item.get("description") or "New legislation detected.",
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
                location_id, company_id, item.get("category"),
                item.get("title"), item.get("description"),
                normalized_status,
                eff_date, item.get("impact_summary"),
                item.get("source_url"), item.get("source_name"),
                confidence, leg_key, alert_id,
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
                new_status, row["id"],
            )

        # Escalate alert severity if needed
        alert_id = row["alert_id"]
        if alert_id and row["alert_severity"] != new_severity:
            old_severity_rank = {"info": 0, "warning": 1, "critical": 2}.get(row["alert_severity"], 0)
            new_severity_rank = {"info": 0, "warning": 1, "critical": 2}.get(new_severity, 0)

            if new_severity_rank > old_severity_rank:
                await conn.execute(
                    "UPDATE compliance_alerts SET severity = $1 WHERE id = $2",
                    new_severity, alert_id,
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
        cat = req['category'] if isinstance(req, dict) else req.category
        rate_type = req.get('rate_type') if isinstance(req, dict) else getattr(req, 'rate_type', None)
        cat_key = _normalize_category(cat)

        # For minimum_wage, group by rate_type to allow multiple entries
        if cat_key == "minimum_wage":
            key = ("minimum_wage", rate_type or "general")
        else:
            # For other categories, use existing logic based on title
            title = req['title'] if isinstance(req, dict) else req.title
            jname = (req['jurisdiction_name'] if isinstance(req, dict)
                     else getattr(req, 'jurisdiction_name', None))
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


async def _filter_with_preemption(conn, requirements, state: str):
    """Preemption-aware jurisdiction filter.

    For each category group:
    1. Check state_preemption_rules to see if local override is allowed.
    2. If preempted: keep only state-level requirements.
    3. If allowed (or no rule): apply most-beneficial-to-employee for wage
       categories, or most-local for others (existing behavior).
    """
    norm_state = state.upper().strip()
    state_name = _CODE_TO_STATE_NAME.get(norm_state, norm_state)

    # Load all preemption rules for this state in one query
    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            norm_state,
        )
        preemption_map = {row["category"]: row["allows_local_override"] for row in preemption_rows}
    except asyncpg.UndefinedTableError:
        preemption_map = {}

    # Group requirements the same way as _filter_by_jurisdiction_priority
    by_key = {}
    for req in requirements:
        cat = req['category'] if isinstance(req, dict) else req.category
        rate_type = req.get('rate_type') if isinstance(req, dict) else getattr(req, 'rate_type', None)
        cat_key = _normalize_category(cat)

        if cat_key == "minimum_wage":
            key = ("minimum_wage", rate_type or "general")
        else:
            title = req['title'] if isinstance(req, dict) else req.title
            jname = (req['jurisdiction_name'] if isinstance(req, dict)
                     else getattr(req, 'jurisdiction_name', None))
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
                r for r in reqs
                if (r['jurisdiction_level'] if isinstance(r, dict) else r.jurisdiction_level) == 'state'
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
                    if isinstance(fallback, dict):
                        fallback["jurisdiction_level"] = "state"
                        fallback["jurisdiction_name"] = state_name
                    else:
                        fallback.jurisdiction_level = "state"
                        fallback.jurisdiction_name = state_name
                    filtered.append(fallback)
                    print(
                        f"[Compliance] WARNING: Category '{category}' is preempted in {norm_state} "
                        f"but had no state-level requirement — promoting local fallback to state."
                    )
            continue

        # Not preempted (allows_local is True or None/unknown)
        # For wage categories: most-beneficial-to-employee (highest numeric value)
        if category == "minimum_wage":
            # Among all jurisdiction levels, pick the one with the highest rate
            reqs_with_num = [(r, _get_numeric_from_req(r)) for r in reqs]
            reqs_with_num_valid = [pair for pair in reqs_with_num if pair[1] is not None]
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


async def create_location(company_id: UUID, data: LocationCreate) -> tuple:
    """Create a location, map it to a jurisdiction, and clone repository data if available.

    Returns (location, has_complete_repository_coverage) — callers should skip
    initial background research only when required labor categories are fully covered.
    """
    from ...database import get_connection
    async with get_connection() as conn:
        location_id = await conn.fetchval(
            """
            INSERT INTO business_locations (company_id, name, address, city, state, county, zipcode)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            company_id,
            data.name,
            data.address,
            data.city,
            data.state.upper(),
            data.county,
            data.zipcode or "",
        )

        # Map to jurisdiction
        jurisdiction_id = await _get_or_create_jurisdiction(conn, data.city, data.state, data.county)
        await conn.execute(
            "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
            jurisdiction_id, location_id,
        )

        has_local_ordinance = await _lookup_has_local_ordinance(conn, data.city, data.state)

        # Check if jurisdiction already has requirements in the repository
        j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
        has_repository_rows = len(j_reqs) > 0
        has_complete_repository_coverage = False

        # Try county data for cities without local ordinance
        req_dicts = None
        if has_repository_rows:
            req_dicts = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
            await _fill_missing_categories_from_parents(conn, jurisdiction_id, req_dicts, 7)
        else:
            if has_local_ordinance is False:
                county_reqs = await _try_load_county_requirements(conn, jurisdiction_id, 7)
                if county_reqs:
                    req_dicts = county_reqs
                else:
                    state_reqs = await _try_load_state_requirements(conn, jurisdiction_id, 7)
                    if state_reqs:
                        req_dicts = state_reqs
                
                # If we loaded from county or state, fill any remaining gaps from parents
                if req_dicts:
                    await _fill_missing_categories_from_parents(conn, jurisdiction_id, req_dicts, 7)

        if req_dicts:
            # Normalize and filter (with preemption awareness) before cloning.
            # This keeps create-location behavior consistent with the main
            # compliance check pipeline.
            if has_local_ordinance is False:
                req_dicts = _filter_city_level_requirements(req_dicts, data.state)
            _normalize_requirement_categories(req_dicts)
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
                conn, location_id, company_id, req_dicts, create_alerts=False,
            )

            # Clone legislation to location
            j_legs = await _load_jurisdiction_legislation(conn, jurisdiction_id)
            for item in j_legs:
                leg_key = item["legislation_key"]
                eff_date = item.get("expected_effective_date")
                confidence = float(item["confidence"]) if item.get("confidence") is not None else None
                await conn.execute(
                    """
                    INSERT INTO upcoming_legislation
                    (location_id, company_id, category, title, description, current_status,
                     expected_effective_date, impact_summary, source_url, source_name,
                     confidence, legislation_key)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (location_id, legislation_key) WHERE legislation_key IS NOT NULL DO NOTHING
                    """,
                    location_id, company_id, item.get("category"),
                    item["title"], item.get("description"),
                    item.get("current_status", "proposed"),
                    eff_date, item.get("impact_summary"),
                    item.get("source_url"), item.get("source_name"),
                    confidence, leg_key,
                )

            if has_complete_repository_coverage:
                # Mark as already checked only when core categories are fully covered.
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )

        row = await conn.fetchrow("SELECT * FROM business_locations WHERE id = $1", location_id)
        location = BusinessLocation(**dict(row))
        return location, has_complete_repository_coverage

async def run_compliance_check_stream(
    location_id: UUID,
    company_id: UUID,
    allow_live_research: bool = True,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs a compliance check for a specific location.
    Checks the jurisdiction repository first; only calls Gemini if stale/missing.
    Yields progress dicts as SSE-friendly events.
    """
    from ...database import get_connection
    from .gemini_compliance import get_gemini_compliance_service

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

    async with get_connection() as conn:
        log_id = await _create_check_log(conn, location_id, company_id, "manual")

        try:
            # Resolve jurisdiction
            jurisdiction_id = location.jurisdiction_id
            if not jurisdiction_id:
                jurisdiction_id = await _get_or_create_jurisdiction(conn, location.city, location.state, location.county)
                await conn.execute(
                    "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
                    jurisdiction_id, location_id,
                )

            # Look up whether this city has its own local ordinance
            has_local_ordinance = await _lookup_has_local_ordinance(conn, location.city, location.state)

            # ============================================================
            # TIER 1: Check for fresh structured data from authoritative sources
            # ============================================================
            from .structured_data import StructuredDataService
            structured_service = StructuredDataService()

            tier1_data = await structured_service.get_tier1_data(
                conn, jurisdiction_id,
                city=location.city, state=location.state, county=location.county,
                categories=["minimum_wage"],
                freshness_hours=168,  # 7 days
                triggered_by="stream_check",
            )

            if tier1_data:
                yield {"type": "tier1", "message": f"Loading verified data for {location_name}..."}
                # Tier 1 only covers a subset of categories (minimum_wage).
                # Merge with repository data for other categories so the sync
                # doesn't delete requirements for categories Tier 1 didn't cover.
                tier1_categories = {_normalize_category(r.get("category")) or r.get("category") for r in tier1_data}
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                repo_reqs = [
                    _jurisdiction_row_to_dict(jr) for jr in j_reqs
                    if (_normalize_category(jr.get("category")) or jr.get("category")) not in tier1_categories
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
            elif await _is_jurisdiction_fresh(conn, jurisdiction_id, location.auto_check_interval_days or 7):
                # Load from repository — skip Gemini
                yield {"type": "repository", "message": f"Loading compliance data for {location_name}..."}
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
                
                # Fill any gaps from state or county, even if the city has its own local ordinances
                filled = await _fill_missing_categories_from_parents(conn, jurisdiction_id, requirements, location.auto_check_interval_days or 7)
                if filled:
                    yield {"type": "repository", "message": f"Filled missing categories from state/county data..."}
                    
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

            # ============================================================
            # TIER 2.5: County/State data reuse for no-local-ordinance cities
            # ============================================================
            if not used_repository and has_local_ordinance is False:
                county_reqs = await _try_load_county_requirements(
                    conn, jurisdiction_id, location.auto_check_interval_days or 7
                )
                if county_reqs:
                    yield {"type": "repository", "message": f"Using {location.county or 'county'} data for {location.city}..."}
                    requirements = county_reqs
                    
                    filled = await _fill_missing_categories_from_parents(conn, jurisdiction_id, requirements, location.auto_check_interval_days or 7)
                    if filled:
                        yield {"type": "repository", "message": f"Filled missing categories from state data..."}
                    
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
                        yield {"type": "repository", "message": f"Using state data for {location.city}..."}
                        requirements = state_reqs
                        
                        filled = await _fill_missing_categories_from_parents(conn, jurisdiction_id, requirements, location.auto_check_interval_days or 7)
                        
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
                    yield {"type": "discovering_sources", "message": f"Learning about {location_name}..."}
                    discovered = await service.discover_jurisdiction_sources(
                        city=location.city, state=location.state, county=location.county,
                    )
                    for src in discovered:
                        domain = (src.get("domain") or "").lower()
                        if domain:
                            for cat in src.get("categories", []):
                                await record_source(conn, jurisdiction_id, domain, src.get("name"), cat)
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
                    preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
                except asyncpg.UndefinedTableError:
                    preemption_rules = {}

                yield {"type": "researching", "message": f"Researching requirements for {location_name}..."}

                # Inform the client when a city has no local ordinance
                if has_local_ordinance is False:
                    parent = f"{location.county} County / " if location.county else ""
                    yield {
                        "type": "jurisdiction_info",
                        "message": f"{location.city} does not have its own local ordinances. Using {parent}{location.state} rules.",
                    }

                research_queue = asyncio.Queue()
                def _on_research_retry(attempt: int, error: str):
                    research_queue.put_nowait({"type": "retrying", "message": f"Retrying research (attempt {attempt + 1})..."})
                research_task = asyncio.create_task(
                    service.research_location_compliance(
                        city=location.city, state=location.state, county=location.county,
                        categories=research_categories,
                        source_context=source_context,
                        corrections_context=corrections_context,
                        preemption_rules=preemption_rules,
                        has_local_ordinance=has_local_ordinance,
                        on_retry=_on_research_retry,
                    )
                )
                async for evt in _heartbeat_while(research_task, queue=research_queue):
                    yield evt
                researched_requirements = research_task.result() or []
                if research_categories and cached_requirements_for_merge:
                    target_set = {
                        _normalize_category(cat) or cat
                        for cat in research_categories
                    }
                    preserved = [
                        req for req in cached_requirements_for_merge
                        if (_normalize_category(req.get("category")) or req.get("category")) not in target_set
                    ]
                    requirements = preserved + researched_requirements
                else:
                    requirements = researched_requirements
            elif not used_repository:
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
                            {"type": "retrying", "message": f"Retrying repository refresh (attempt {attempt + 1})..."}
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
                        async for evt in _heartbeat_while(refresh_task, queue=refresh_queue):
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
                        stale_repo_rows = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                        if stale_repo_rows:
                            requirements = [_jurisdiction_row_to_dict(jr) for jr in stale_repo_rows]
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
                    print(f"[Compliance] Falling back to stale repository data ({len(requirements)} cached requirements)")
                    yield {"type": "fallback", "message": "Using cached data (live research unavailable)"}

            if not requirements:
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )
                await _complete_check_log(conn, log_id, 0, 0, 0)
                yield {"type": "completed", "location": location_name, "new": 0, "updated": 0, "alerts": 0}
                return

            # Post-filter: handle city-level results for cities with no local ordinance.
            # Instead of stripping all city-level entries (which can lose entire categories
            # like minimum_wage), promote orphaned city-level entries to state-level.
            if has_local_ordinance is False:
                requirements = _filter_city_level_requirements(requirements, location.state)
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
            requirements = await _filter_with_preemption(conn, requirements, location.state)
            for req in requirements:
                _clamp_varchar_fields(req)

            yield {"type": "processing", "message": f"Processing {len(requirements)} requirements..."}

            # If Gemini was called, contribute results to jurisdiction repository
            if not used_repository:
                await _upsert_jurisdiction_requirements(conn, jurisdiction_id, requirements)

                # Also write to county jurisdiction so other cities in same county can reuse
                if has_local_ordinance is False:
                    county_jid = await _get_county_jurisdiction_id(conn, jurisdiction_id)
                    if county_jid:
                        await _upsert_jurisdiction_requirements(conn, county_jid, requirements)
                        print(f"[Compliance] Also cached to county jurisdiction {county_jid}")

                # Learn from successful research: record any new sources seen
                for req in requirements:
                    source_url = req.get("source_url", "")
                    if source_url:
                        domain = extract_domain(source_url)
                        if domain:
                            await record_source(
                                conn, jurisdiction_id, domain,
                                req.get("source_name"), req.get("category", "")
                            )

            # Sync requirements to location (change detection, alerts, history)
            # Only create alerts for fresh Gemini data — repository data is cached
            # and shouldn't re-alert on every check.
            sync_result = await _sync_requirements_to_location(
                conn, location_id, company_id, requirements,
                create_alerts=not used_repository,
            )
            new_count = sync_result["new"]
            updated_count = sync_result["updated"]
            alert_count = sync_result["alerts"]
            changes_to_verify = sync_result["changes_to_verify"]
            existing_by_key = sync_result["existing_by_key"]

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

            # Verify material changes with Gemini (skip verification when using cached repository data)
            # Phase 2.3: Use batched verification for efficiency
            if changes_to_verify and not used_repository:
                verify_total = min(len(changes_to_verify), MAX_VERIFICATIONS_PER_CHECK)
                yield {"type": "verifying", "message": f"Verifying {verify_total} change(s) in batch..."}
                verification_count = 0

                # Prepare batch of changes for verification
                changes_batch = []
                for change_info in changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK]:
                    req = change_info["req"]
                    changes_batch.append({
                        "category": req.get("category", ""),
                        "title": req.get("title", ""),
                        "old_value": change_info["old_value"],
                        "new_value": change_info["new_value"],
                    })

                # Get jurisdiction name from first change (all same jurisdiction)
                jurisdiction_name = changes_to_verify[0]["req"].get("jurisdiction_name", f"{location.city}, {location.state}")

                try:
                    yield {"type": "verifying_item", "message": f"Batch verifying {verify_total} changes...", "current": 1, "total": 1}
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
                        VerificationResult(confirmed=False, confidence=0.5, sources=[], explanation="Batch verification unavailable")
                    ] * len(changes_batch)

                # Process each verification result
                for idx, (change_info, verification) in enumerate(zip(changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK], verification_results)):
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
                            conn, location_id, company_id, existing["id"],
                            f"Compliance Change: {req.get('title')}",
                            change_msg, "warning", req.get("category"),
                            source_url=req.get("source_url"), source_name=req.get("source_name"),
                            alert_type="change", confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={"verification_explanation": verification.explanation},
                        )
                        # Log verification outcome for calibration
                        await _log_verification_outcome(
                            conn, jurisdiction_id, alert_id, req_key, req.get("category"),
                            confidence, predicted_is_change=True, verification_sources=verification.sources,
                        )
                        _record_change_notification_item(change_email_items, req, change_info)
                        verification_count += 1
                    elif confidence >= 0.3:
                        alert_count += 1
                        alert_id = await _create_alert(
                            conn, location_id, company_id, existing["id"],
                            f"Unverified: {req.get('title')}",
                            change_msg, "info", req.get("category"),
                            source_url=req.get("source_url"), source_name=req.get("source_name"),
                            alert_type="change", confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={"verification_explanation": verification.explanation, "unverified": True},
                        )
                        # Log verification outcome for calibration
                        await _log_verification_outcome(
                            conn, jurisdiction_id, alert_id, req_key, req.get("category"),
                            confidence, predicted_is_change=True, verification_sources=verification.sources,
                        )
                        _record_change_notification_item(change_email_items, req, change_info)
                        verification_count += 1
                    else:
                        # Log low-confidence rejections too for calibration
                        await _log_verification_outcome(
                            conn, jurisdiction_id, None, req_key, req.get("category"),
                            confidence, predicted_is_change=False, verification_sources=verification.sources,
                        )
                        print(f"[Compliance] Low confidence ({confidence:.2f}) for change: {req.get('title')}, skipping alert")

                # Handle overflow changes without verification
                for change_info in changes_to_verify[MAX_VERIFICATIONS_PER_CHECK:]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"
                    alert_count += 1
                    await _create_alert(
                        conn, location_id, company_id, existing["id"],
                        f"Compliance Change: {req.get('title')}", change_msg,
                        "warning", req.get("category"),
                        source_url=req.get("source_url"), source_name=req.get("source_name"),
                        alert_type="change",
                    )
                    _record_change_notification_item(change_email_items, req, change_info)

                if verification_count > 0:
                    yield {"type": "verified", "message": f"Verified {verification_count} change(s)"}

            # Legislation scan — only via Gemini when not using repository
            if not used_repository:
                yield {"type": "scanning", "message": "Scanning for upcoming legislation..."}
                try:
                    current_reqs = [dict(r) for r in existing_by_key.values() if r.get("id")]
                    leg_task = asyncio.create_task(
                        service.scan_upcoming_legislation(
                            city=location.city, state=location.state, county=location.county,
                            current_requirements=current_reqs,
                        )
                    )
                    async for evt in _heartbeat_while(leg_task):
                        yield evt
                    legislation_items = leg_task.result()
                    # Contribute to jurisdiction repository
                    await _upsert_jurisdiction_legislation(conn, jurisdiction_id, legislation_items)
                    leg_count = await process_upcoming_legislation(conn, location_id, company_id, legislation_items)
                    if leg_count > 0:
                        alert_count += leg_count
                        yield {"type": "legislation", "message": f"Found {leg_count} upcoming legislative change(s)"}
                except Exception as e:
                    print(f"[Compliance] Legislation scan error: {e}")

            # Deadline escalation
            try:
                escalated = await escalate_upcoming_deadlines(conn, company_id)
                if escalated > 0:
                    yield {"type": "escalation", "message": f"Escalated {escalated} deadline(s)"}
            except Exception as e:
                print(f"[Compliance] Deadline escalation error: {e}")

            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id,
            )
            await _complete_check_log(conn, log_id, new_count, updated_count, alert_count)
        except Exception as e:
            await _complete_check_log(conn, log_id, new_count, updated_count, alert_count, error=str(e))
            raise

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
        "new": new_count,
        "updated": updated_count,
        "alerts": alert_count,
    }


async def run_compliance_check(location_id: UUID, company_id: UUID):
    """Repository-sync wrapper for background tasks on company locations."""
    async for _ in run_compliance_check_stream(location_id, company_id, allow_live_research=False):
        pass


async def get_location_counts(location_id: UUID) -> dict:
    """Get requirements count and unread alerts count for a location."""
    from ...database import get_connection
    async with get_connection() as conn:
        loc = await conn.fetchrow(
            """SELECT bl.state, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1""",
            location_id,
        )
        state = (loc["state"] if loc else None) or ""
        has_local_ordinance = loc["has_local_ordinance"] if loc else None

        rows = await conn.fetch(
            "SELECT category, jurisdiction_level, title, jurisdiction_name, rate_type FROM compliance_requirements WHERE location_id = $1",
            location_id,
        )
        req_dicts = [dict(r) for r in rows]
        if has_local_ordinance is False:
            req_dicts = _filter_city_level_requirements(req_dicts, state)
        _normalize_requirement_categories(req_dicts)
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


async def get_locations(company_id: UUID) -> List[BusinessLocation]:
    from ...database import get_connection
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT bl.*, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.company_id = $1
               ORDER BY bl.created_at DESC""",
            company_id,
        )
        return [BusinessLocation(**dict(row)) for row in rows]


async def get_location(location_id: UUID, company_id: UUID) -> Optional[BusinessLocation]:
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


async def update_location(location_id: UUID, company_id: UUID, data: LocationUpdate) -> Optional[BusinessLocation]:
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
        result = await conn.execute(
            "DELETE FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id,
            company_id,
        )
        return result == "DELETE 1"


async def get_location_requirements(location_id: UUID, company_id: UUID, category: Optional[str] = None) -> List[RequirementResponse]:
    from ...database import get_connection
    async with get_connection() as conn:
        loc = await conn.fetchrow(
            """SELECT bl.state, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id, company_id,
        )
        if not loc:
            return []
        state = loc["state"]
        has_local_ordinance = loc["has_local_ordinance"]

        query = """
            SELECT r.* FROM compliance_requirements r
            JOIN business_locations l ON r.location_id = l.id
            WHERE l.id = $1 AND l.company_id = $2
        """
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
        filtered = await _filter_with_preemption(conn, row_dicts, state)
        return [
            RequirementResponse(
                id=str(row["id"]),
                category=row["category"],
                rate_type=row.get("rate_type"),
                jurisdiction_level=row["jurisdiction_level"],
                jurisdiction_name=row["jurisdiction_name"],
                title=row["title"],
                description=row["description"],
                current_value=row["current_value"],
                numeric_value=float(row["numeric_value"]) if row.get("numeric_value") is not None else None,
                source_url=row["source_url"],
                source_name=row["source_name"],
                effective_date=row["effective_date"].isoformat() if row["effective_date"] else None,
                previous_value=row["previous_value"],
                last_changed_at=row["last_changed_at"].isoformat() if row["last_changed_at"] else None,
            )
            for row in filtered
        ]


async def get_company_alerts(company_id: UUID, status: Optional[str] = None, severity: Optional[str] = None, limit: int = 50) -> List[AlertResponse]:
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

        return [
            AlertResponse(
                id=str(row["id"]),
                location_id=str(row["location_id"]),
                requirement_id=str(row["requirement_id"]) if row["requirement_id"] else None,
                title=row["title"],
                message=row["message"],
                severity=row["severity"],
                status=row["status"],
                category=row["category"],
                action_required=row["action_required"],
                source_url=row["resolved_source_url"],
                source_name=row["resolved_source_name"],
                deadline=row["deadline"].isoformat() if row["deadline"] else None,
                confidence_score=float(row["confidence_score"]) if row.get("confidence_score") is not None else None,
                verification_sources=_parse_jsonb(row.get("verification_sources")),
                alert_type=row.get("alert_type"),
                effective_date=row["effective_date"].isoformat() if row.get("effective_date") else None,
                metadata=_parse_jsonb(row.get("metadata")),
                created_at=row["created_at"].isoformat(),
                read_at=row["read_at"].isoformat() if row["read_at"] else None,
            )
            for row in rows
        ]


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
                print(f"[Compliance] Unauthorized feedback attempt: alert {alert_id} not owned by company {company_id}")
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
            actual_is_change, user_id, admin_notes, correction_reason, alert_id,
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
                was_accurate = (predicted_is_change == actual_is_change)

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
) -> List[Dict]:
    """Get recent false positive corrections for a jurisdiction.

    Used in Phase 3.1 to inject correction context into future research prompts.

    Returns:
        List of dicts with: requirement_key, category, correction_reason, admin_notes, created_at
    """
    from ...database import get_connection
    async with get_connection() as conn:
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
                "SELECT * FROM compliance_requirements WHERE location_id = $1",
                loc["id"],
            )
            req_dicts = [dict(r) for r in reqs]
            if loc.get("has_local_ordinance") is False:
                req_dicts = _filter_city_level_requirements(req_dicts, loc["state"])
            _normalize_requirement_categories(req_dicts)
            filtered_reqs = await _filter_with_preemption(conn, req_dicts, loc["state"])
            total_requirements += len(filtered_reqs)

            for req in filtered_reqs:
                if req["last_changed_at"]:
                    recent_changes.append({
                        "location": loc["name"] or f"{loc['city']}, {loc['state']}",
                        "category": req["category"],
                        "title": req["title"],
                        "old_value": req["previous_value"],
                        "new_value": req["current_value"],
                        "changed_at": req["last_changed_at"].isoformat(),
                    })

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
            upcoming_deadlines.append({
                "title": row["title"],
                "effective_date": row["expected_effective_date"].isoformat(),
                "days_until": days,
                "status": row["current_status"],
                "category": row["category"],
                "location": row["location_name"] or f"{row['city']}, {row['state']}",
            })

        return ComplianceSummary(
            total_locations=len(locations),
            total_requirements=total_requirements,
            unread_alerts=unread_alerts,
            critical_alerts=critical_alerts,
            recent_changes=recent_changes,
            auto_check_locations=auto_check_count,
            upcoming_deadlines=upcoming_deadlines,
        )


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
                updates.append(f"next_auto_check = NOW() + INTERVAL '1 day' * auto_check_interval_days")
                interval = None
            if interval is not None:
                updates.append(f"next_auto_check = NOW() + INTERVAL '1 day' * ${param_idx}")
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


async def get_check_log(location_id: UUID, company_id: UUID, limit: int = 20) -> List[CheckLogEntry]:
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
            location_id, company_id, limit,
        )
        return [
            CheckLogEntry(
                id=str(row["id"]),
                location_id=str(row["location_id"]),
                company_id=str(row["company_id"]),
                check_type=row["check_type"],
                status=row["status"],
                started_at=row["started_at"].isoformat(),
                completed_at=row["completed_at"].isoformat() if row["completed_at"] else None,
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
            location_id, company_id,
        )
        now = datetime.utcnow().date()

        responses: list[UpcomingLegislationResponse] = []
        for row in rows:
            effective_date = row["expected_effective_date"]
            normalized_status = _normalize_legislation_status(row["current_status"], effective_date)

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
                    expected_effective_date=effective_date.isoformat() if effective_date else None,
                    impact_summary=row["impact_summary"],
                    source_url=row["source_url"],
                    source_name=row["source_name"],
                    confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                    days_until_effective=(effective_date - now).days if effective_date else None,
                    created_at=row["created_at"].isoformat(),
                )
            )

        return responses


async def run_compliance_check_background(
    location_id: UUID,
    company_id: UUID,
    check_type: str = "scheduled",
    allow_live_research: bool = True,
) -> Dict[str, Any]:
    """Non-streaming compliance check for Celery tasks.
    Checks the jurisdiction repository first; only calls Gemini if stale/missing.
    Returns summary dict.
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

    async with get_connection() as conn:
        log_id = await _create_check_log(conn, location_id, company_id, check_type)

        try:
            # Resolve jurisdiction
            jurisdiction_id = location.jurisdiction_id
            if not jurisdiction_id:
                jurisdiction_id = await _get_or_create_jurisdiction(conn, location.city, location.state, location.county)
                await conn.execute(
                    "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
                    jurisdiction_id, location_id,
                )

            # Look up whether this city has its own local ordinance
            has_local_ordinance = await _lookup_has_local_ordinance(conn, location.city, location.state)

            # TIER 1: Check for fresh structured data from authoritative sources
            from .structured_data import StructuredDataService
            structured_service = StructuredDataService()

            tier1_data = await structured_service.get_tier1_data(
                conn, jurisdiction_id,
                city=location.city, state=location.state, county=location.county,
                categories=["minimum_wage"],
                freshness_hours=168,
                triggered_by="background_check",
            )

            # Check repository freshness threshold
            threshold = location.auto_check_interval_days or 7

            if tier1_data:
                # Tier 1 only covers a subset of categories (minimum_wage).
                # Merge with repository data for other categories.
                tier1_categories = {_normalize_category(r.get("category")) or r.get("category") for r in tier1_data}
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                repo_reqs = [
                    _jurisdiction_row_to_dict(jr) for jr in j_reqs
                    if (_normalize_category(jr.get("category")) or jr.get("category")) not in tier1_categories
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
                
                await _fill_missing_categories_from_parents(conn, jurisdiction_id, requirements, threshold)
                
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

            # TIER 2.5: County/State data reuse for no-local-ordinance cities
            if not used_repository and has_local_ordinance is False:
                county_reqs = await _try_load_county_requirements(conn, jurisdiction_id, threshold)
                if county_reqs:
                    requirements = county_reqs
                    
                    await _fill_missing_categories_from_parents(conn, jurisdiction_id, requirements, threshold)
                    
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
                    state_reqs = await _try_load_state_requirements(conn, jurisdiction_id, threshold)
                    if state_reqs:
                        requirements = state_reqs
                        
                        await _fill_missing_categories_from_parents(conn, jurisdiction_id, requirements, threshold)
                        
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
                        city=location.city, state=location.state, county=location.county,
                    )
                    for src in discovered:
                        domain = (src.get("domain") or "").lower()
                        if domain:
                            for cat in src.get("categories", []):
                                await record_source(conn, jurisdiction_id, domain, src.get("name"), cat)
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
                    preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
                except asyncpg.UndefinedTableError:
                    preemption_rules = {}

                requirements = await service.research_location_compliance(
                    city=location.city, state=location.state, county=location.county,
                    categories=research_categories,
                    source_context=source_context,
                    corrections_context=corrections_context,
                    preemption_rules=preemption_rules,
                    has_local_ordinance=has_local_ordinance,
                )
                if research_categories and cached_requirements_for_merge:
                    target_set = {
                        _normalize_category(cat) or cat
                        for cat in research_categories
                    }
                    preserved = [
                        req for req in cached_requirements_for_merge
                        if (_normalize_category(req.get("category")) or req.get("category")) not in target_set
                    ]
                    requirements = preserved + requirements
            elif not used_repository:
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
                        stale_repo_rows = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                        if stale_repo_rows:
                            requirements = [_jurisdiction_row_to_dict(jr) for jr in stale_repo_rows]
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
                    print(f"[Compliance] Background: falling back to stale repository data ({len(requirements)} cached requirements)")

            if not requirements:
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )
                await _complete_check_log(conn, log_id, 0, 0, 0)
                return {"new": 0, "updated": 0, "alerts": 0}

            # Post-filter: handle city-level results for cities with no local ordinance
            if has_local_ordinance is False:
                requirements = _filter_city_level_requirements(requirements, location.state)
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
            requirements = await _filter_with_preemption(conn, requirements, location.state)
            for req in requirements:
                _clamp_varchar_fields(req)

            # Contribute to repository after Gemini call
            if not used_repository:
                await _upsert_jurisdiction_requirements(conn, jurisdiction_id, requirements)

                # Also write to county jurisdiction so other cities in same county can reuse
                if has_local_ordinance is False:
                    county_jid = await _get_county_jurisdiction_id(conn, jurisdiction_id)
                    if county_jid:
                        await _upsert_jurisdiction_requirements(conn, county_jid, requirements)
                        print(f"[Compliance] Also cached to county jurisdiction {county_jid}")

                # Learn from successful research: record any new sources seen
                for req in requirements:
                    source_url = req.get("source_url", "")
                    if source_url:
                        domain = extract_domain(source_url)
                        if domain:
                            await record_source(
                                conn, jurisdiction_id, domain,
                                req.get("source_name"), req.get("category", "")
                            )

            # Sync to location
            sync_result = await _sync_requirements_to_location(
                conn, location_id, company_id, requirements, create_alerts=True,
            )
            new_count = sync_result["new"]
            updated_count = sync_result["updated"]
            alert_count = sync_result["alerts"]
            changes_to_verify = sync_result["changes_to_verify"]
            existing_by_key = sync_result["existing_by_key"]

            # Verify changes (skip when using cached repository data)
            if not used_repository:
                for change_info in changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    try:
                        verification = await service.verify_compliance_change_adaptive(
                            category=req.get("category", ""), title=req.get("title", ""),
                            jurisdiction_name=req.get("jurisdiction_name", ""),
                            old_value=change_info["old_value"], new_value=change_info["new_value"],
                        )
                        confidence = max(score_verification_confidence(verification.sources), verification.confidence)
                    except Exception:
                        confidence = 0.5
                        verification = VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation="Verification unavailable")

                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"

                    if confidence >= 0.6:
                        alert_count += 1
                        await _create_alert(
                            conn, location_id, company_id, existing["id"],
                            f"Compliance Change: {req.get('title')}", change_msg,
                            "warning", req.get("category"),
                            source_url=req.get("source_url"), source_name=req.get("source_name"),
                            alert_type="change", confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={"verification_explanation": verification.explanation},
                        )
                        _record_change_notification_item(change_email_items, req, change_info)
                    elif confidence >= 0.3:
                        alert_count += 1
                        await _create_alert(
                            conn, location_id, company_id, existing["id"],
                            f"Unverified: {req.get('title')}", change_msg,
                            "info", req.get("category"),
                            source_url=req.get("source_url"), source_name=req.get("source_name"),
                            alert_type="change", confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={"verification_explanation": verification.explanation, "unverified": True},
                        )
                        _record_change_notification_item(change_email_items, req, change_info)

                for change_info in changes_to_verify[MAX_VERIFICATIONS_PER_CHECK:]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"
                    alert_count += 1
                    await _create_alert(
                        conn, location_id, company_id, existing["id"],
                        f"Compliance Change: {req.get('title')}", change_msg,
                        "warning", req.get("category"),
                        source_url=req.get("source_url"), source_name=req.get("source_name"),
                        alert_type="change",
                    )
                    _record_change_notification_item(change_email_items, req, change_info)

            # Legislation scan — only via Gemini when not using repository
            if not used_repository:
                try:
                    current_reqs = [dict(r) for r in existing_by_key.values() if r.get("id")]
                    legislation_items = await service.scan_upcoming_legislation(
                        city=location.city, state=location.state, county=location.county,
                        current_requirements=current_reqs,
                    )
                    await _upsert_jurisdiction_legislation(conn, jurisdiction_id, legislation_items)
                    leg_count = await process_upcoming_legislation(conn, location_id, company_id, legislation_items)
                    alert_count += leg_count
                except Exception as e:
                    print(f"[Compliance] Background legislation scan error: {e}")

            # Deadline escalation
            try:
                await escalate_upcoming_deadlines(conn, company_id)
            except Exception as e:
                print(f"[Compliance] Background escalation error: {e}")

            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id,
            )
            await _complete_check_log(conn, log_id, new_count, updated_count, alert_count)

        except Exception as e:
            await _complete_check_log(conn, log_id, new_count, updated_count, alert_count, error=str(e))
            raise

    try:
        await _notify_company_admins_of_compliance_changes(
            company_id=company_id,
            location=location,
            change_items=change_email_items,
        )
    except Exception as e:
        print(f"[Compliance] Error notifying admins about compliance changes: {e}")

    return {"new": new_count, "updated": updated_count, "alerts": alert_count}
