"""Client notifications / activity feed."""
import logging

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.models.auth import CurrentUser
from app.core.services.redis_cache import get_redis_cache, cache_get, cache_set, dashboard_notifications_key
from app.matcha.models.dashboard import ClientNotification, ClientNotificationsResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_CLIENT_NOTIFICATION_LINK_MAP: dict[str, str] = {
    "incident": "/app/ir/{id}",
    "employee": "/app/employees/{id}",
    "offer_letter": "/app/policies",
    "er_case": "/app/er-copilot/{id}",
    "handbook": "/app/handbook/{id}",
    "compliance_alert": "/app/compliance",
    "credential_expiry": "/app/credential-templates",
}

# Each sub-query is parameterized with $1 = company_id.
_CLIENT_NOTIFICATION_SUBQUERIES: list[str] = [
    # Incidents
    """SELECT id::text, 'incident' AS type,
            title, incident_number AS subtitle,
            severity, status, created_at
       FROM ir_incidents
       WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'""",
    # Employees
    """SELECT e.id::text, 'employee' AS type,
            e.first_name || ' ' || e.last_name AS title,
            e.job_title AS subtitle,
            NULL AS severity, 'onboarded' AS status, e.created_at
       FROM employees e
       WHERE e.org_id = $1 AND e.created_at > NOW() - INTERVAL '30 days'""",
    # Offer letters
    """SELECT id::text, 'offer_letter' AS type,
            candidate_name || ' - ' || position_title AS title,
            status AS subtitle,
            NULL AS severity, status, created_at
       FROM offer_letters
       WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'""",
    # ER cases
    """SELECT id::text, 'er_case' AS type,
            title, case_number AS subtitle,
            NULL AS severity, status, created_at
       FROM er_cases
       WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'""",
    # Handbooks
    """SELECT id::text, 'handbook' AS type,
            title, status AS subtitle,
            NULL AS severity, status, created_at
       FROM handbooks
       WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'""",
    # Compliance alerts — material changes and new requirements
    """SELECT id::text, 'compliance_alert' AS type,
            title, message AS subtitle,
            severity, status, created_at
       FROM compliance_alerts
       WHERE company_id = $1
         AND created_at > NOW() - INTERVAL '30 days'
         AND alert_type IN ('change', 'new_requirement')
         AND COALESCE(confidence_score, 1.0) >= 0.6""",
    # Credential expirations — healthcare employee licenses expiring within 90 days
    """SELECT ec.id::text, 'credential_expiry' AS type,
            e.first_name || ' ' || e.last_name || ' — ' || x.label AS title,
            'Expires ' || to_char(x.expiry_date, 'Mon DD, YYYY') AS subtitle,
            CASE WHEN x.expiry_date < CURRENT_DATE THEN 'expired'
                 WHEN x.expiry_date <= CURRENT_DATE + INTERVAL '30 days' THEN 'critical'
                 ELSE 'warning' END AS severity,
            CASE WHEN x.expiry_date < CURRENT_DATE THEN 'expired' ELSE 'expiring' END AS status,
            ec.updated_at AS created_at
       FROM employees e
       JOIN employee_credentials ec ON ec.employee_id = e.id
       CROSS JOIN LATERAL (VALUES
           ('Medical License',      ec.license_expiration),
           ('DEA Registration',     ec.dea_expiration),
           ('Board Certification',  ec.board_certification_expiration),
           ('Malpractice Insurance', ec.malpractice_expiration)
       ) AS x(label, expiry_date)
       WHERE e.org_id = $1
         AND e.termination_date IS NULL
         AND x.expiry_date IS NOT NULL
         AND x.expiry_date <= CURRENT_DATE + INTERVAL '90 days'""",
]


@router.get("/notifications", response_model=ClientNotificationsResponse)
async def get_client_notifications(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return a chronological activity feed of recent events for the client's company."""

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return ClientNotificationsResponse(items=[], total=0)

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, dashboard_notifications_key(company_id, limit, offset))
        if cached is not None:
            return cached

    async with get_connection() as conn:
        # Build UNION ALL dynamically, skipping tables that don't exist.
        valid_parts: list[str] = []
        for sq in _CLIENT_NOTIFICATION_SUBQUERIES:
            try:
                await conn.fetch(f"SELECT * FROM ({sq}) _probe LIMIT 0", company_id)
                valid_parts.append(sq)
            except asyncpg.UndefinedTableError:
                logger.debug("Skipping client notification subquery (table missing): %s", sq[:60])
            except asyncpg.UndefinedColumnError:
                logger.debug("Skipping client notification subquery (column missing): %s", sq[:60])

        if not valid_parts:
            return ClientNotificationsResponse(items=[], total=0)

        union_sql = " UNION ALL ".join(valid_parts)

        # Total count
        count_row = await conn.fetchrow(
            f"SELECT COUNT(*) AS total FROM ({union_sql}) AS _all",
            company_id,
        )
        total = count_row["total"] if count_row else 0

        # Paginated rows
        rows = await conn.fetch(
            f"""SELECT *
                FROM ({union_sql}) AS n
                ORDER BY n.created_at DESC
                LIMIT $2 OFFSET $3""",
            company_id,
            limit,
            offset,
        )

    items: list[ClientNotification] = []
    for row in rows:
        row_type = row["type"]
        row_id = row["id"]
        link_template = _CLIENT_NOTIFICATION_LINK_MAP.get(row_type, "")
        link = link_template.replace("{id}", row_id) if link_template else None

        items.append(
            ClientNotification(
                id=row_id,
                type=row_type,
                title=row["title"] or "",
                subtitle=row["subtitle"],
                severity=row["severity"],
                status=row["status"],
                created_at=row["created_at"],
                link=link,
            )
        )

    result = ClientNotificationsResponse(items=items, total=total)

    if redis:
        await cache_set(redis, dashboard_notifications_key(company_id, limit, offset), result.model_dump(), ttl=180)

    return result
