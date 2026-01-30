from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
import re

from ..models.compliance import (
    BusinessLocation,
    ComplianceRequirement,
    ComplianceAlert,
    LocationCreate,
    LocationUpdate,
    RequirementResponse,
    AlertResponse,
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


def _compute_requirement_key(req) -> str:
    cat = req.get("category") if isinstance(req, dict) else req.category
    title = req.get("title") if isinstance(req, dict) else req.title
    jname = req.get("jurisdiction_name") if isinstance(req, dict) else getattr(req, "jurisdiction_name", None)
    level = req.get("jurisdiction_level") if isinstance(req, dict) else req.jurisdiction_level
    cat_key = _normalize_category(cat) or ""
    base_title = _base_title(title or "", jname)
    base_key = _normalize_title_key(base_title)
    return f"{cat_key}:{level}:{base_key}"

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

async def run_compliance_check(location_id: UUID, company_id: UUID):
    """
    Runs a compliance check for a specific location using Gemini.
    Updates requirements and creates alerts for changes.
    """
    from ...database import get_connection
    from .gemini_compliance import get_gemini_compliance_service

    location = await get_location(location_id, company_id)
    if not location:
        print(f"[Compliance Check] Location {location_id} not found")
        return

    location_name = location.name or f"{location.city}, {location.state}"
    print(f"[Compliance Check] Starting check for {location_name}...")

    service = get_gemini_compliance_service()
    requirements = await service.research_location_compliance(
        city=location.city,
        state=location.state,
        county=location.county
    )

    if not requirements:
        print(f"[Compliance Check] No requirements found for {location_name}")
        # Still update the last check timestamp
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id
            )
        return

    print(f"[Compliance Check] Processing {len(requirements)} requirements for {location_name}")

    async with get_connection() as conn:
        existing_rows = await conn.fetch(
            "SELECT * FROM compliance_requirements WHERE location_id = $1",
            location_id,
        )
        existing_by_key = {}
        duplicates = []
        for row in existing_rows:
            row_dict = dict(row)
            key = row_dict.get("requirement_key") or _compute_requirement_key(row_dict)
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
                await conn.execute(
                    """
                    INSERT INTO compliance_requirement_history
                    (requirement_id, location_id, category, jurisdiction_level, jurisdiction_name,
                     title, description, current_value, numeric_value, source_url, source_name, effective_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    dup["id"], location_id, dup.get("category"),
                    dup.get("jurisdiction_level"), dup.get("jurisdiction_name"),
                    dup.get("title"), dup.get("description"),
                    dup.get("current_value"), dup.get("numeric_value"),
                    dup.get("source_url"), dup.get("source_name"),
                    dup.get("effective_date"),
                )
                await conn.execute(
                    "DELETE FROM compliance_requirements WHERE id = $1",
                    dup["id"],
                )

        for req in requirements:
            # Normalize category + build requirement key
            req["category"] = _normalize_category(req.get("category")) or req.get("category")
            requirement_key = _compute_requirement_key(req)
            existing = existing_by_key.get(requirement_key)

            if existing:
                old_value = existing.get("current_value")
                new_value = req.get("current_value")
                old_num = existing.get("numeric_value")
                new_num = req.get("numeric_value")
                if old_num is None:
                    old_num = _extract_numeric_value(old_value)
                if new_num is None:
                    new_num = _extract_numeric_value(new_value)

                normalized_same = _normalize_value_text(old_value, req.get("category")) == _normalize_value_text(
                    new_value, req.get("category")
                )
                numeric_changed = (
                    old_num is not None
                    and new_num is not None
                    and float(old_num) != float(new_num)
                )
                text_changed = (old_value != new_value)

                material_change = False
                if numeric_changed:
                    material_change = True
                elif text_changed and not normalized_same:
                    # Ask Gemini only when local normalization can't confirm equivalence
                    material_change = await service.is_material_change(
                        req.get("category"), old_value, new_value
                    )

                # Record history if anything about the requirement changed
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
                    await conn.execute(
                        """
                        INSERT INTO compliance_requirement_history
                        (requirement_id, location_id, category, jurisdiction_level, jurisdiction_name,
                         title, description, current_value, numeric_value, source_url, source_name, effective_date)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        """,
                        existing["id"], location_id, existing.get("category"),
                        existing.get("jurisdiction_level"), existing.get("jurisdiction_name"),
                        existing.get("title"), existing.get("description"),
                        existing.get("current_value"), existing.get("numeric_value"),
                        existing.get("source_url"), existing.get("source_name"),
                        existing.get("effective_date"),
                    )

                    if material_change:
                        source_hint = req.get("source_url") or req.get("source_name") or "N/A"
                        await conn.execute(
                            """
                            INSERT INTO compliance_alerts
                            (location_id, company_id, requirement_id, title, message, severity, status, category, action_required, source_url, source_name)
                            VALUES ($1, $2, $3, $4, $5, $6, 'unread', $7, 'Review new requirement', $8, $9)
                            """,
                            location_id, company_id, existing['id'],
                            f"Compliance Change: {req.get('title')}",
                            f"Value changed from {old_value} to {new_value}. Source: {source_hint}",
                            "warning", req.get('category'),
                            req.get("source_url"), req.get("source_name")
                        )

                # Update the requirement row
                previous_value = existing.get("previous_value")
                last_changed_at = existing.get("last_changed_at")
                if material_change:
                    previous_value = old_value
                    last_changed_at = datetime.utcnow()

                await conn.execute(
                    """
                    UPDATE compliance_requirements
                    SET requirement_key = $1,
                        category = $2,
                        jurisdiction_name = $3,
                        title = $4,
                        current_value = $5,
                        numeric_value = $6,
                        previous_value = $7,
                        last_changed_at = $8,
                        description = $9,
                        source_url = $10,
                        source_name = $11,
                        effective_date = $12,
                        updated_at = NOW()
                    WHERE id = $13
                    """,
                    requirement_key,
                    req.get("category"),
                    req.get("jurisdiction_name"),
                    req.get("title"),
                    req.get("current_value"),
                    req.get("numeric_value"),
                    previous_value,
                    last_changed_at,
                    req.get("description"),
                    req.get("source_url"),
                    req.get("source_name"),
                    parse_date(req.get("effective_date")),
                    existing["id"],
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
                # Insert new requirement
                req_id = await conn.fetchval(
                    """
                    INSERT INTO compliance_requirements
                    (location_id, requirement_key, category, jurisdiction_level, jurisdiction_name, title, description,
                     current_value, numeric_value, source_url, source_name, effective_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    RETURNING id
                    """,
                    location_id, requirement_key, req.get("category"), req.get("jurisdiction_level"), req.get("jurisdiction_name"),
                    req.get("title"), req.get("description"), req.get("current_value"), req.get("numeric_value"),
                    req.get("source_url"), req.get("source_name"), parse_date(req.get("effective_date"))
                )

                # Create alert for new requirement
                source_hint = req.get("source_url") or req.get("source_name") or "N/A"
                await conn.execute(
                    """
                    INSERT INTO compliance_alerts 
                    (location_id, company_id, requirement_id, title, message, severity, status, category, action_required, source_url, source_name)
                    VALUES ($1, $2, $3, $4, $5, $6, 'unread', $7, 'Review new requirement', $8, $9)
                    """,
                    location_id, company_id, req_id,
                    f"New Requirement: {req.get('title')}",
                    f"New compliance requirement identified. Source: {source_hint}",
                    "info", req.get("category"),
                    req.get("source_url"), req.get("source_name")
                )
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

        # Update last check timestamp
        await conn.execute(
            "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
            location_id
        )

    print(f"[Compliance Check] Completed check for {location_name}")


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
                   COALESCE(a.source_url, r.source_url) AS source_url,
                   COALESCE(a.source_name, r.source_name) AS source_name
            FROM compliance_alerts a
            LEFT JOIN compliance_requirements r ON a.requirement_id = r.id
            WHERE a.company_id = $1
        """
        params = [company_id]

        if status:
            query += f" AND status = ${len(params) + 1}"
            params.append(status)
        if severity:
            query += f" AND severity = ${len(params) + 1}"
            params.append(severity)

        query += f" ORDER BY created_at DESC LIMIT {limit}"

        rows = await conn.fetch(query, *params)
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
                source_url=row["source_url"],
                source_name=row["source_name"],
                deadline=row["deadline"].isoformat() if row["deadline"] else None,
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

        for loc in locations:
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

        return ComplianceSummary(
            total_locations=len(locations),
            total_requirements=total_requirements,
            unread_alerts=unread_alerts,
            critical_alerts=critical_alerts,
            recent_changes=recent_changes,
        )
