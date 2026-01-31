from typing import Optional, List, AsyncGenerator, Dict, Any
from uuid import UUID
from datetime import date, datetime, timedelta
import json
import re

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
MIN_WAGE_GENERAL_KEYS = {"minimum wage", "minimum wage rate", "general minimum wage"}
MIN_WAGE_SPECIAL_KEYWORDS = {
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


def _normalize_category(category: Optional[str]) -> Optional[str]:
    if not category:
        return category
    s = category.strip().lower()
    s = re.sub(r"[\s\-]+", "_", s)
    return s


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
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _is_special_min_wage(base_key: str, title: Optional[str], description: Optional[str]) -> bool:
    if not base_key:
        return False
    if base_key in MIN_WAGE_GENERAL_KEYS:
        return False
    text = " ".join(filter(None, [base_key, title or "", description or ""])).lower()
    return any(keyword in text for keyword in MIN_WAGE_SPECIAL_KEYWORDS)


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
    if not reqs:
        return None
    with_nums = [(r, _get_numeric_from_req(r)) for r in reqs]
    with_nums = [pair for pair in with_nums if pair[1] is not None]
    if with_nums:
        return max(with_nums, key=lambda x: x[1])[0]
    return _pick_best_by_priority(reqs)


MAX_VERIFICATIONS_PER_CHECK = 3


def _compute_requirement_key(req) -> str:
    cat = req.get("category") if isinstance(req, dict) else req.category
    title = req.get("title") if isinstance(req, dict) else req.title
    jname = req.get("jurisdiction_name") if isinstance(req, dict) else getattr(req, "jurisdiction_name", None)
    level = req.get("jurisdiction_level") if isinstance(req, dict) else req.jurisdiction_level
    cat_key = _normalize_category(cat) or ""
    base_title = _base_title(title or "", jname)
    base_key = _normalize_title_key(base_title)
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
    return await conn.fetchval(
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


async def _upsert_requirement(
    conn, location_id: UUID, requirement_key: str, req: dict
) -> UUID:
    """Insert a new compliance requirement. Returns the new ID."""
    return await conn.fetchval(
        """
        INSERT INTO compliance_requirements
        (location_id, requirement_key, category, jurisdiction_level, jurisdiction_name, title, description,
         current_value, numeric_value, source_url, source_name, effective_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        RETURNING id
        """,
        location_id, requirement_key, req.get("category"), req.get("jurisdiction_level"),
        req.get("jurisdiction_name"), req.get("title"), req.get("description"),
        req.get("current_value"), req.get("numeric_value"),
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
        SET requirement_key = $1, category = $2, jurisdiction_name = $3, title = $4,
            current_value = $5, numeric_value = $6, previous_value = $7, last_changed_at = $8,
            description = $9, source_url = $10, source_name = $11, effective_date = $12,
            updated_at = NOW()
        WHERE id = $13
        """,
        requirement_key, req.get("category"), req.get("jurisdiction_name"), req.get("title"),
        req.get("current_value"), req.get("numeric_value"), previous_value, last_changed_at,
        req.get("description"), req.get("source_url"), req.get("source_name"),
        parse_date(req.get("effective_date")), existing_id,
    )


async def _snapshot_to_history(conn, row_dict: dict, location_id: UUID):
    """Insert a snapshot of a requirement into the history table."""
    await conn.execute(
        """
        INSERT INTO compliance_requirement_history
        (requirement_id, location_id, category, jurisdiction_level, jurisdiction_name,
         title, description, current_value, numeric_value, source_url, source_name, effective_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
        row_dict["id"], location_id, row_dict.get("category"),
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

        if existing:
            new_status = item.get("current_status", existing["current_status"])
            await conn.execute(
                """
                UPDATE upcoming_legislation
                SET current_status = $1, expected_effective_date = $2, impact_summary = $3,
                    source_url = $4, source_name = $5, confidence = $6, description = $7,
                    updated_at = NOW()
                WHERE id = $8
                """,
                new_status, eff_date, item.get("impact_summary"),
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
                item.get("current_status", "proposed"),
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
            new_status = "effective_soon"
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
    """For each distinct requirement within a category, keep only the most
    specific jurisdiction level.

    Titles are compared after stripping jurisdiction-name prefixes so that
    e.g. "California Minimum Wage" (state) and "West Hollywood Minimum Wage"
    (city) are recognised as the same rule, while genuinely different
    requirements (e.g. separate meal / rest break entries) within one category
    are preserved.
    """
    by_key = {}
    min_wage_general = []
    for req in requirements:
        cat = req['category'] if isinstance(req, dict) else req.category
        title = req['title'] if isinstance(req, dict) else req.title
        jname = (req['jurisdiction_name'] if isinstance(req, dict)
                 else getattr(req, 'jurisdiction_name', None))
        base = _base_title(title, jname)
        base_key = _normalize_title_key(base)
        cat_key = _normalize_category(cat)

        if cat_key == "minimum_wage":
            desc = req.get("description") if isinstance(req, dict) else getattr(req, "description", None)
            if _is_special_min_wage(base_key, title, desc):
                by_key.setdefault((cat_key, base_key), []).append(req)
            else:
                min_wage_general.append(req)
        else:
            by_key.setdefault((cat_key, base_key), []).append(req)

    filtered = []

    # General minimum wage: pick single most restrictive option
    if min_wage_general:
        best_general = _pick_most_restrictive_wage(min_wage_general)
        if best_general:
            filtered.append(best_general)

    # Special minimum wage + other categories: keep one per base title
    for reqs in by_key.values():
        best_req = _pick_best_by_priority(reqs)
        if best_req:
            filtered.append(best_req)

    return filtered


async def create_location(company_id: UUID, data: LocationCreate) -> BusinessLocation:
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
            data.zipcode,
        )
        row = await conn.fetchrow("SELECT * FROM business_locations WHERE id = $1", location_id)
        location = BusinessLocation(**dict(row))
        
        # Trigger async compliance check (fire and forget for now, or use background tasks)
        # For simplicity in this function, we will call it but typically this should be backgrounded
        # To avoid blocking response, we might need BackgroundTasks passed from route
        return location

async def run_compliance_check_stream(
    location_id: UUID, company_id: UUID
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs a compliance check for a specific location using Gemini.
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
    yield {"type": "researching", "message": f"Researching requirements for {location_name}..."}

    requirements = await service.research_location_compliance(
        city=location.city,
        state=location.state,
        county=location.county
    )

    if not requirements:
        async with get_connection() as conn:
            log_id = await _create_check_log(conn, location_id, company_id, "manual")
            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id
            )
            await _complete_check_log(conn, log_id, 0, 0, 0)
        yield {"type": "completed", "location": location_name, "new": 0, "updated": 0, "alerts": 0}
        return

    # Filter by jurisdiction priority BEFORE saving to DB
    for req in requirements:
        req["category"] = _normalize_category(req.get("category")) or req.get("category")
    requirements = _filter_by_jurisdiction_priority(requirements)

    yield {"type": "processing", "message": f"Processing {len(requirements)} requirements..."}

    new_count = 0
    updated_count = 0
    alert_count = 0

    async with get_connection() as conn:
        log_id = await _create_check_log(conn, location_id, company_id, "manual")

        try:
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
                        """
                        UPDATE compliance_requirements
                        SET requirement_key = $1, category = $2, updated_at = NOW()
                        WHERE id = $3
                        """,
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

            if duplicates:
                for dup in duplicates:
                    await _snapshot_to_history(conn, dup, location_id)
                    await conn.execute(
                        "DELETE FROM compliance_requirements WHERE id = $1",
                        dup["id"],
                    )

            # Dismiss orphaned alerts (NULL requirement_id) left by old key-mismatch bug
            await conn.execute(
                """
                UPDATE compliance_alerts
                SET status = 'dismissed', dismissed_at = NOW()
                WHERE location_id = $1 AND requirement_id IS NULL
                  AND status IN ('unread', 'read')
                """,
                location_id,
            )

            # Track which keys are in the new result set
            new_requirement_keys = set()

            # Track material changes for verification
            changes_to_verify = []

            for req in requirements:
                requirement_key = _compute_requirement_key(req)
                new_requirement_keys.add(requirement_key)
                existing = existing_by_key.get(requirement_key)

                req_title = req.get("title", "")

                if existing:
                    # Auto-dismiss stale alerts for this requirement before re-check creates fresh ones
                    await conn.execute(
                        """
                        UPDATE compliance_alerts
                        SET status = 'dismissed', dismissed_at = NOW()
                        WHERE requirement_id = $1 AND status IN ('unread', 'read')
                        """,
                        existing["id"],
                    )

                    old_value = existing.get("current_value")
                    new_value = req.get("current_value")
                    old_num = existing.get("numeric_value")
                    new_num = req.get("numeric_value")
                    if old_num is None:
                        old_num = _extract_numeric_value(old_value)
                    if new_num is None:
                        new_num = _extract_numeric_value(new_value)

                    # Deterministic material change detection
                    material_change = False
                    if _is_material_numeric_change(old_num, new_num, req.get("category")):
                        material_change = True
                    elif _is_material_text_change(old_value, new_value, req.get("category")):
                        material_change = True

                    numeric_changed = (
                        old_num is not None
                        and new_num is not None
                        and abs(float(old_num) - float(new_num)) > 0.001
                    )
                    text_changed = (old_value != new_value)

                    metadata_changed = any(
                        [
                            existing.get("title") != req.get("title"),
                            existing.get("description") != req.get("description"),
                            existing.get("source_url") != req.get("source_url"),
                            existing.get("source_name") != req.get("source_name"),
                            existing.get("effective_date") != parse_date(req.get("effective_date")),
                            text_changed,
                            numeric_changed,
                        ]
                    )
                    if metadata_changed:
                        updated_count += 1
                        await _snapshot_to_history(conn, existing, location_id)

                        if material_change:
                            # Queue for verification instead of creating alert immediately
                            changes_to_verify.append({
                                "req": req,
                                "existing": existing,
                                "old_value": old_value,
                                "new_value": new_value,
                                "requirement_key": requirement_key,
                            })
                        change_detail = f" ({old_value} → {new_value})" if material_change else ""
                        yield {"type": "result", "status": "updated", "message": req_title + change_detail}
                    else:
                        yield {"type": "result", "status": "unchanged", "message": req_title}

                    previous_value = existing.get("previous_value")
                    last_changed_at = existing.get("last_changed_at")
                    if material_change:
                        previous_value = old_value
                        last_changed_at = datetime.utcnow()

                    await _update_requirement(
                        conn, existing["id"], requirement_key, req,
                        previous_value, last_changed_at,
                    )
                    existing_by_key[requirement_key] = {
                        **existing,
                        "requirement_key": requirement_key,
                        "category": req.get("category"),
                        "jurisdiction_name": req.get("jurisdiction_name"),
                        "title": req.get("title"),
                        "current_value": req.get("current_value"),
                        "numeric_value": req.get("numeric_value"),
                        "description": req.get("description"),
                        "source_url": req.get("source_url"),
                        "source_name": req.get("source_name"),
                        "effective_date": parse_date(req.get("effective_date")),
                    }
                else:
                    new_count += 1
                    req_id = await _upsert_requirement(conn, location_id, requirement_key, req)

                    alert_count += 1
                    await _create_alert(
                        conn, location_id, company_id, req_id,
                        f"New Requirement: {req.get('title')}",
                        req.get("description") or "New compliance requirement identified.",
                        "info", req.get("category"),
                        source_url=req.get("source_url"),
                        source_name=req.get("source_name"),
                        alert_type="new_requirement",
                    )
                    yield {"type": "result", "status": "new", "message": req_title}
                    existing_by_key[requirement_key] = {
                        "id": req_id,
                        "requirement_key": requirement_key,
                        "category": req.get("category"),
                        "jurisdiction_level": req.get("jurisdiction_level"),
                        "jurisdiction_name": req.get("jurisdiction_name"),
                        "title": req.get("title"),
                        "current_value": req.get("current_value"),
                        "numeric_value": req.get("numeric_value"),
                        "description": req.get("description"),
                        "source_url": req.get("source_url"),
                        "source_name": req.get("source_name"),
                        "effective_date": parse_date(req.get("effective_date")),
                    }

            # Verify material changes with Gemini (Sprint 2)
            if changes_to_verify:
                yield {"type": "verifying", "message": f"Verifying {min(len(changes_to_verify), MAX_VERIFICATIONS_PER_CHECK)} change(s)..."}
                verification_count = 0
                for change_info in changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK]:
                    req = change_info["req"]
                    existing = change_info["existing"]

                    try:
                        verification = await service.verify_compliance_change(
                            category=req.get("category", ""),
                            title=req.get("title", ""),
                            jurisdiction_name=req.get("jurisdiction_name", ""),
                            old_value=change_info["old_value"],
                            new_value=change_info["new_value"],
                        )
                        confidence = score_verification_confidence(verification.sources)
                        confidence = max(confidence, verification.confidence)
                    except Exception as e:
                        print(f"[Compliance] Verification failed: {e}")
                        verification = VerificationResult(confirmed=False, confidence=0.0, sources=[], explanation="Verification unavailable")
                        confidence = 0.5  # Treat as unverified

                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    description = req.get("description")
                    if description:
                        change_msg += f" {description}"

                    # Gate alert creation by confidence
                    if confidence >= 0.6:
                        alert_count += 1
                        await _create_alert(
                            conn, location_id, company_id, existing["id"],
                            f"Compliance Change: {req.get('title')}",
                            change_msg,
                            "warning", req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={"verification_explanation": verification.explanation},
                        )
                        verification_count += 1
                    elif confidence >= 0.3:
                        alert_count += 1
                        await _create_alert(
                            conn, location_id, company_id, existing["id"],
                            f"Unverified: {req.get('title')}",
                            change_msg,
                            "info", req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={"verification_explanation": verification.explanation, "unverified": True},
                        )
                        verification_count += 1
                    else:
                        # Low confidence: log only, no alert
                        print(f"[Compliance] Low confidence ({confidence:.2f}) for change: {req.get('title')}, skipping alert")

                # Create alerts for unverified changes (beyond MAX_VERIFICATIONS_PER_CHECK)
                for change_info in changes_to_verify[MAX_VERIFICATIONS_PER_CHECK:]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    description = req.get("description")
                    if description:
                        change_msg += f" {description}"
                    alert_count += 1
                    await _create_alert(
                        conn, location_id, company_id, existing["id"],
                        f"Compliance Change: {req.get('title')}",
                        change_msg,
                        "warning", req.get("category"),
                        source_url=req.get("source_url"),
                        source_name=req.get("source_name"),
                        alert_type="change",
                    )

                if verification_count > 0:
                    yield {"type": "verified", "message": f"Verified {verification_count} change(s)"}

            # Delete stale requirements not in the new result set
            stale_keys = set(existing_by_key.keys()) - new_requirement_keys
            for stale_key in stale_keys:
                stale = existing_by_key[stale_key]
                stale_id = stale.get("id")
                if stale_id:
                    await _snapshot_to_history(conn, stale, location_id)
                    await conn.execute(
                        "DELETE FROM compliance_requirements WHERE id = $1",
                        stale_id,
                    )

            # Scan for upcoming legislation (Sprint 3)
            yield {"type": "scanning", "message": "Scanning for upcoming legislation..."}
            try:
                current_reqs = [dict(r) for r in existing_by_key.values() if r.get("id")]
                legislation_items = await service.scan_upcoming_legislation(
                    city=location.city,
                    state=location.state,
                    county=location.county,
                    current_requirements=current_reqs,
                )
                leg_count = await process_upcoming_legislation(conn, location_id, company_id, legislation_items)
                if leg_count > 0:
                    alert_count += leg_count
                    yield {"type": "legislation", "message": f"Found {leg_count} upcoming legislative change(s)"}
            except Exception as e:
                print(f"[Compliance] Legislation scan error: {e}")

            # Run deadline escalation
            try:
                escalated = await escalate_upcoming_deadlines(conn, company_id)
                if escalated > 0:
                    yield {"type": "escalation", "message": f"Escalated {escalated} deadline(s)"}
            except Exception as e:
                print(f"[Compliance] Deadline escalation error: {e}")

            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id
            )
            await _complete_check_log(conn, log_id, new_count, updated_count, alert_count)
        except Exception as e:
            await _complete_check_log(conn, log_id, new_count, updated_count, alert_count, error=str(e))
            raise

    yield {
        "type": "completed",
        "location": location_name,
        "new": new_count,
        "updated": updated_count,
        "alerts": alert_count,
    }


async def run_compliance_check(location_id: UUID, company_id: UUID):
    """Non-streaming wrapper for backward compatibility (e.g. background tasks on location create)."""
    async for _ in run_compliance_check_stream(location_id, company_id):
        pass


async def get_location_counts(location_id: UUID) -> dict:
    """Get requirements count and unread alerts count for a location."""
    from ...database import get_connection
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT category, jurisdiction_level, title, jurisdiction_name FROM compliance_requirements WHERE location_id = $1",
            location_id,
        )
        filtered = _filter_by_jurisdiction_priority([dict(r) for r in rows])
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
            "SELECT * FROM business_locations WHERE company_id = $1 ORDER BY created_at DESC",
            company_id,
        )
        return [BusinessLocation(**dict(row)) for row in rows]


async def get_location(location_id: UUID, company_id: UUID) -> Optional[BusinessLocation]:
    from ...database import get_connection
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM business_locations WHERE id = $1 AND company_id = $2",
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
        filtered = _filter_by_jurisdiction_priority(row_dicts)
        return [
            RequirementResponse(
                id=str(row["id"]),
                category=row["category"],
                jurisdiction_level=row["jurisdiction_level"],
                jurisdiction_name=row["jurisdiction_name"],
                title=row["title"],
                description=row["description"],
                current_value=row["current_value"],
                numeric_value=float(row["numeric_value"]) if row["numeric_value"] else None,
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


async def get_compliance_summary(company_id: UUID) -> ComplianceSummary:
    from ...database import get_connection
    async with get_connection() as conn:
        locations = await conn.fetch(
            "SELECT * FROM business_locations WHERE company_id = $1",
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
            filtered_reqs = _filter_by_jurisdiction_priority([dict(r) for r in reqs])
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
        return [
            UpcomingLegislationResponse(
                id=str(row["id"]),
                location_id=str(row["location_id"]),
                category=row["category"],
                title=row["title"],
                description=row["description"],
                current_status=row["current_status"],
                expected_effective_date=row["expected_effective_date"].isoformat() if row["expected_effective_date"] else None,
                impact_summary=row["impact_summary"],
                source_url=row["source_url"],
                source_name=row["source_name"],
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                days_until_effective=(row["expected_effective_date"] - now).days if row["expected_effective_date"] else None,
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]


async def run_compliance_check_background(
    location_id: UUID, company_id: UUID, check_type: str = "scheduled"
) -> Dict[str, Any]:
    """Non-streaming compliance check for Celery tasks. Returns summary dict."""
    from ...database import get_connection
    from .gemini_compliance import get_gemini_compliance_service

    location = await get_location(location_id, company_id)
    if not location:
        return {"error": "Location not found", "new": 0, "updated": 0, "alerts": 0}

    service = get_gemini_compliance_service()
    requirements = await service.research_location_compliance(
        city=location.city, state=location.state, county=location.county
    )

    if not requirements:
        async with get_connection() as conn:
            log_id = await _create_check_log(conn, location_id, company_id, check_type)
            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id,
            )
            await _complete_check_log(conn, log_id, 0, 0, 0)
        return {"new": 0, "updated": 0, "alerts": 0}

    for req in requirements:
        req["category"] = _normalize_category(req.get("category")) or req.get("category")
    requirements = _filter_by_jurisdiction_priority(requirements)

    new_count = 0
    updated_count = 0
    alert_count = 0

    async with get_connection() as conn:
        log_id = await _create_check_log(conn, location_id, company_id, check_type)

        try:
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

            await conn.execute(
                """
                UPDATE compliance_alerts SET status = 'dismissed', dismissed_at = NOW()
                WHERE location_id = $1 AND requirement_id IS NULL AND status IN ('unread', 'read')
                """,
                location_id,
            )

            new_requirement_keys = set()
            changes_to_verify = []

            for req in requirements:
                requirement_key = _compute_requirement_key(req)
                new_requirement_keys.add(requirement_key)
                existing = existing_by_key.get(requirement_key)

                if existing:
                    await conn.execute(
                        "UPDATE compliance_alerts SET status = 'dismissed', dismissed_at = NOW() WHERE requirement_id = $1 AND status IN ('unread', 'read')",
                        existing["id"],
                    )

                    old_value = existing.get("current_value")
                    new_value = req.get("current_value")
                    old_num = existing.get("numeric_value")
                    new_num = req.get("numeric_value")
                    if old_num is None:
                        old_num = _extract_numeric_value(old_value)
                    if new_num is None:
                        new_num = _extract_numeric_value(new_value)

                    material_change = False
                    if _is_material_numeric_change(old_num, new_num, req.get("category")):
                        material_change = True
                    elif _is_material_text_change(old_value, new_value, req.get("category")):
                        material_change = True

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
                        if material_change:
                            changes_to_verify.append({
                                "req": req, "existing": existing,
                                "old_value": old_value, "new_value": new_value,
                            })

                    previous_value = existing.get("previous_value")
                    last_changed_at = existing.get("last_changed_at")
                    if material_change:
                        previous_value = old_value
                        last_changed_at = datetime.utcnow()

                    await _update_requirement(conn, existing["id"], requirement_key, req, previous_value, last_changed_at)
                    existing_by_key[requirement_key] = {**existing, "id": existing["id"]}
                else:
                    new_count += 1
                    req_id = await _upsert_requirement(conn, location_id, requirement_key, req)
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

            # Verify changes
            for change_info in changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK]:
                req = change_info["req"]
                existing = change_info["existing"]
                try:
                    verification = await service.verify_compliance_change(
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

            # Stale requirements cleanup
            stale_keys = set(existing_by_key.keys()) - new_requirement_keys
            for stale_key in stale_keys:
                stale = existing_by_key[stale_key]
                stale_id = stale.get("id")
                if stale_id:
                    await _snapshot_to_history(conn, stale, location_id)
                    await conn.execute("DELETE FROM compliance_requirements WHERE id = $1", stale_id)

            # Legislation scan
            try:
                current_reqs = [dict(r) for r in existing_by_key.values() if r.get("id")]
                legislation_items = await service.scan_upcoming_legislation(
                    city=location.city, state=location.state, county=location.county,
                    current_requirements=current_reqs,
                )
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

    return {"new": new_count, "updated": updated_count, "alerts": alert_count}
