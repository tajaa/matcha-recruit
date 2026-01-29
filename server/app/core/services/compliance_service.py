from typing import Optional, List
from uuid import UUID
from datetime import date

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


def _filter_by_jurisdiction_priority(requirements):
    """For each (category, title), keep only the most specific jurisdiction level.

    This ensures that a city-level "Minimum Wage" supersedes a state-level
    "Minimum Wage", but a state-level "Overtime Pay" in the same category is
    preserved because no more-specific entry exists for that title.
    """
    by_key = {}
    for req in requirements:
        cat = req['category'] if isinstance(req, dict) else req.category
        title = req['title'] if isinstance(req, dict) else req.title
        by_key.setdefault((cat, title), []).append(req)

    filtered = []
    for reqs in by_key.values():
        best = min(
            JURISDICTION_PRIORITY.get(
                r['jurisdiction_level'] if isinstance(r, dict) else r.jurisdiction_level, 99
            )
            for r in reqs
        )
        for r in reqs:
            level = r['jurisdiction_level'] if isinstance(r, dict) else r.jurisdiction_level
            if JURISDICTION_PRIORITY.get(level, 99) == best:
                filtered.append(r)
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
        for req in requirements:
            # Check if requirement exists
            existing = await conn.fetchrow(
                """
                SELECT * FROM compliance_requirements 
                WHERE location_id = $1 AND category = $2 AND jurisdiction_level = $3 AND title = $4
                """,
                location_id, req['category'], req['jurisdiction_level'], req['title']
            )

            if existing:
                # Update if value changed
                if existing['current_value'] != req['current_value']:
                    # Create alert
                    await conn.execute(
                        """
                        INSERT INTO compliance_alerts 
                        (location_id, company_id, requirement_id, title, message, severity, status, category, action_required)
                        VALUES ($1, $2, $3, $4, $5, $6, 'unread', $7, 'Review new requirement')
                        """,
                        location_id, company_id, existing['id'],
                        f"Compliance Change: {req['title']}",
                        f"Value changed from {existing['current_value']} to {req['current_value']}",
                        "warning", req['category']
                    )

                    # Update requirement
                    await conn.execute(
                        """
                        UPDATE compliance_requirements
                        SET current_value = $1, numeric_value = $2, previous_value = $3,
                            last_changed_at = NOW(), description = $4, source_url = $5,
                            effective_date = $6, updated_at = NOW()
                        WHERE id = $7
                        """,
                        req['current_value'], req.get('numeric_value'), existing['current_value'],
                        req['description'], req.get('source_url'),
                        parse_date(req.get('effective_date')), existing['id']
                    )
            else:
                # Insert new requirement
                req_id = await conn.fetchval(
                    """
                    INSERT INTO compliance_requirements
                    (location_id, category, jurisdiction_level, jurisdiction_name, title, description,
                     current_value, numeric_value, source_url, source_name, effective_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING id
                    """,
                    location_id, req['category'], req['jurisdiction_level'], req['jurisdiction_name'],
                    req['title'], req['description'], req['current_value'], req.get('numeric_value'),
                    req.get('source_url'), req.get('source_name'), parse_date(req.get('effective_date'))
                )
                
                # Create alert for new requirement
                await conn.execute(
                    """
                    INSERT INTO compliance_alerts 
                    (location_id, company_id, requirement_id, title, message, severity, status, category, action_required)
                    VALUES ($1, $2, $3, $4, $5, $6, 'unread', $7, 'Review new requirement')
                    """,
                    location_id, company_id, req_id,
                    f"New Requirement: {req['title']}",
                    f"New compliance requirement identified: {req['description']}",
                    "info", req['category']
                )

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
            "SELECT category, jurisdiction_level, title FROM compliance_requirements WHERE location_id = $1",
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
        query = "SELECT * FROM compliance_alerts WHERE company_id = $1"
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
