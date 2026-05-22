"""IR People endpoints — lightweight per-person tracking (matcha-lite).

People named in incidents are auto-indexed into `ir_people` (see
`_shared._sync_incident_people`). These read endpoints expose that index
so the UI can offer name autocomplete (consistent spelling → real dedup)
and a per-person, role-aware incident history. No employee roster needed.

Both routes are 2+ segments on purpose: a bare `/people` GET would be
shadowed by crud's `/{incident_id}`. They inherit the parent mount's
`require_feature("incidents")` gate — matcha-lite has it, so no employees
flag is required.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.ir_incident import (
    IRPersonHistory,
    IRPersonIncidentRef,
    IRPersonRoleCount,
    IRPersonSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/people/search", response_model=list[IRPersonSummary])
async def search_ir_people(
    q: str = Query("", max_length=120),
    limit: int = Query(20, ge=1, le=50),
    current_user=Depends(require_admin_or_client),
):
    """Prefix-search the company's IR people index, ranked by incident count.

    Empty `q` returns the most-active people (good default for the People
    view). Matches on a normalized prefix so "jane" finds "Jane Doe".
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    norm = " ".join(q.strip().split()).casefold()
    params = [str(company_id)]
    where = "p.company_id = $1"
    if norm:
        params.append(f"{norm}%")
        where += " AND p.normalized_name LIKE $2"

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT p.id::text AS id, p.display_name, p.email, p.verified,
                   p.last_seen,
                   COUNT(DISTINCT ip.incident_id) AS incident_count
            FROM ir_people p
            LEFT JOIN ir_incident_people ip ON ip.person_id = p.id
            WHERE {where}
            GROUP BY p.id, p.display_name, p.email, p.verified, p.last_seen
            ORDER BY incident_count DESC, p.last_seen DESC NULLS LAST
            LIMIT {int(limit)}
            """,
            *params,
        )

    return [
        IRPersonSummary(
            id=r["id"],
            display_name=r["display_name"],
            email=r["email"],
            verified=r["verified"],
            incident_count=r["incident_count"] or 0,
            last_seen=r["last_seen"],
        )
        for r in rows
    ]


@router.get("/people/{person_id}/incidents", response_model=IRPersonHistory)
async def get_ir_person_incidents(
    person_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Per-person, role-aware incident history (matcha-lite no-roster path)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Person not found")

    async with get_connection() as conn:
        person = await conn.fetchrow(
            """
            SELECT p.id::text AS id, p.display_name, p.email, p.verified, p.last_seen,
                   COUNT(DISTINCT ip.incident_id) AS incident_count
            FROM ir_people p
            LEFT JOIN ir_incident_people ip ON ip.person_id = p.id
            WHERE p.id = $1 AND p.company_id = $2
            GROUP BY p.id, p.display_name, p.email, p.verified, p.last_seen
            """,
            str(person_id), str(company_id),
        )
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        breakdown_rows = await conn.fetch(
            """
            SELECT ip.role, COUNT(DISTINCT ip.incident_id) AS cnt
            FROM ir_incident_people ip
            JOIN ir_incidents i ON i.id = ip.incident_id
            WHERE ip.person_id = $1 AND i.company_id = $2
            GROUP BY ip.role
            ORDER BY cnt DESC
            """,
            str(person_id), str(company_id),
        )

        incident_rows = await conn.fetch(
            """
            SELECT i.id, i.incident_number, i.title, i.incident_type,
                   i.severity, i.status, i.occurred_at, ip.role
            FROM ir_incident_people ip
            JOIN ir_incidents i ON i.id = ip.incident_id
            WHERE ip.person_id = $1 AND i.company_id = $2
            ORDER BY i.occurred_at DESC NULLS LAST
            """,
            str(person_id), str(company_id),
        )

    return IRPersonHistory(
        person=IRPersonSummary(
            id=person["id"],
            display_name=person["display_name"],
            email=person["email"],
            verified=person["verified"],
            incident_count=person["incident_count"] or 0,
            last_seen=person["last_seen"],
        ),
        role_breakdown=[
            IRPersonRoleCount(role=r["role"], count=r["cnt"]) for r in breakdown_rows
        ],
        incidents=[
            IRPersonIncidentRef(
                id=r["id"],
                incident_number=r["incident_number"],
                title=r["title"],
                incident_type=r["incident_type"],
                severity=r["severity"],
                status=r["status"],
                occurred_at=r["occurred_at"],
                role=r["role"],
            )
            for r in incident_rows
        ],
    )
