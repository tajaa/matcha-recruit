"""Upcoming deadlines — unified cross-module deadline aggregation."""
import logging
from datetime import date, timedelta
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.core.models.auth import CurrentUser
from app.core.services.compliance_service import codified_gate_sql
from app.core.services.redis_cache import get_redis_cache, cache_get, cache_set, dashboard_upcoming_key
from app.matcha.models.dashboard import UpcomingItem, UpcomingResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _severity_from_days(days: int, *, critical_threshold: int = 14) -> str:
    if days < 0:
        return "critical"
    if days <= critical_threshold:
        return "warning"
    return "info"


# Each source is a (category, sql, date_column_name, link_template) tuple.
# SQL must:
#   - accept $1 = company_id (or None for admin-all), $2 = lookahead date
#   - return: title, subtitle, deadline (date)
# link_template uses {id} placeholder.

_UPCOMING_SOURCES: list[dict] = [
    # Compliance alerts — only those with an explicit deadline (not effective_date,
    # which represents when a law takes effect, not when action is due)
    {
        "category": "compliance",
        "sql": """
            SELECT ca.id::text, ca.title,
                   ca.message AS subtitle,
                   ca.deadline::date AS deadline
            FROM compliance_alerts ca
            WHERE ({company_filter})
              AND ca.status != 'dismissed'
              AND ca.deadline IS NOT NULL
              AND ca.deadline::date <= $2
        """,
        "link": "/app/matcha/compliance",
    },
    # Credential expirations
    {
        "category": "credential",
        "sql": """
            SELECT ec.id::text,
                   e.first_name || ' ' || e.last_name || ' — ' || x.label AS title,
                   x.label AS subtitle,
                   x.expiry_date::date AS deadline
            FROM employees e
            JOIN employee_credentials ec ON ec.employee_id = e.id
            CROSS JOIN LATERAL (VALUES
                ('Medical License',      ec.license_expiration),
                ('DEA Registration',     ec.dea_expiration),
                ('Board Certification',  ec.board_certification_expiration),
                ('Malpractice Insurance', ec.malpractice_expiration)
            ) AS x(label, expiry_date)
            WHERE ({company_filter_emp})
              AND e.termination_date IS NULL
              AND x.expiry_date IS NOT NULL
              AND x.expiry_date::date <= $2
        """,
        "link": "/app/matcha/employees",
    },
    # Training due dates
    {
        "category": "training",
        "sql": """
            SELECT tr.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — ' || tr.title AS title,
                   tr.status AS subtitle,
                   tr.due_date::date AS deadline
            FROM training_records tr
            LEFT JOIN employees e ON e.id = tr.employee_id
            WHERE ({company_filter})
              AND tr.status IN ('assigned', 'in_progress')
              AND tr.due_date IS NOT NULL
              AND tr.due_date::date <= $2
        """,
        "link": "/app/matcha/training",
    },
    # COBRA deadlines
    {
        "category": "cobra",
        "sql": """
            SELECT ce.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — COBRA ' || ce.qualifying_event_type AS title,
                   x.label AS subtitle,
                   x.deadline::date AS deadline
            FROM cobra_events ce
            LEFT JOIN employees e ON e.id = ce.employee_id
            CROSS JOIN LATERAL (VALUES
                ('Employer notice',  ce.employer_notice_deadline),
                ('Election',         ce.election_deadline)
            ) AS x(label, deadline)
            WHERE ({company_filter_cobra})
              AND ce.status NOT IN ('waived', 'expired', 'terminated')
              AND x.deadline IS NOT NULL
              AND x.deadline::date <= $2
        """,
        "link": "/app/matcha/cobra",
    },
    # Stale policies (updated_at older than 180 days → deadline = updated_at + 180d)
    {
        "category": "policy",
        "sql": """
            SELECT p.id::text,
                   p.title,
                   'Last updated ' || to_char(p.updated_at, 'Mon DD, YYYY') AS subtitle,
                   (p.updated_at + INTERVAL '180 days')::date AS deadline
            FROM policies p
            WHERE ({company_filter})
              AND p.status = 'active'
              AND (p.updated_at + INTERVAL '180 days')::date <= $2
        """,
        "link": "/app/matcha/policies/{id}",
    },
    # Open IR incidents (age tracking — deadline = created_at, so days_until is negative = how old)
    {
        "category": "ir",
        "sql": """
            SELECT i.id::text,
                   i.title,
                   i.incident_number || ' — ' || i.status AS subtitle,
                   i.created_at::date AS deadline
            FROM ir_incidents i
            WHERE ({company_filter})
              AND i.status IN ('reported', 'investigating', 'action_required')
        """,
        "link": "/app/ir/incidents/{id}",
    },
    # Open ER cases
    {
        "category": "er",
        "sql": """
            SELECT ec.id::text,
                   ec.title,
                   ec.case_number || ' — ' || ec.status AS subtitle,
                   ec.created_at::date AS deadline
            FROM er_cases ec
            WHERE ({company_filter})
              AND ec.status NOT IN ('closed', 'resolved')
        """,
        "link": "/app/matcha/er-copilot/{id}",
    },
    # I-9 expirations
    {
        "category": "i9",
        "sql": """
            SELECT i9.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — I-9' AS title,
                   x.label AS subtitle,
                   x.expiry::date AS deadline
            FROM i9_records i9
            LEFT JOIN employees e ON e.id = i9.employee_id
            CROSS JOIN LATERAL (VALUES
                ('I-9 expiration',          i9.expiration_date),
                ('I-9 reverification',      i9.reverification_expiration)
            ) AS x(label, expiry)
            WHERE ({company_filter_i9})
              AND x.expiry IS NOT NULL
              AND x.expiry::date <= $2
        """,
        "link": "/app/matcha/i9",
    },
    # Separation agreement deadlines
    {
        "category": "separation",
        "sql": """
            SELECT sa.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — Separation' AS title,
                   x.label AS subtitle,
                   x.deadline::date AS deadline
            FROM separation_agreements sa
            LEFT JOIN employees e ON e.id = sa.employee_id
            CROSS JOIN LATERAL (VALUES
                ('Consideration deadline', sa.consideration_deadline),
                ('Revocation deadline',    sa.revocation_deadline)
            ) AS x(label, deadline)
            WHERE ({company_filter})
              AND sa.status IN ('draft', 'sent', 'pending_signature', 'signed')
              AND x.deadline IS NOT NULL
              AND x.deadline::date <= $2
        """,
        "link": "/app/matcha/separations",
    },
    # Onboarding tasks
    {
        "category": "onboarding",
        "sql": """
            SELECT eot.id::text,
                   COALESCE(e.first_name || ' ' || e.last_name, 'Employee') || ' — ' || eot.task_name AS title,
                   'Onboarding task' AS subtitle,
                   eot.due_date::date AS deadline
            FROM employee_onboarding_tasks eot
            LEFT JOIN employees e ON e.id = eot.employee_id
            WHERE ({company_filter_onboard})
              AND eot.status = 'pending'
              AND eot.due_date IS NOT NULL
              AND eot.due_date::date <= $2
        """,
        "link": "/app/matcha/onboarding",
    },
    # Upcoming legislation — passed/signed laws about to take effect for this company's locations
    {
        "category": "legislation",
        "sql": """
            SELECT ul.id::text,
                   ul.title,
                   ul.impact_summary AS subtitle,
                   ul.expected_effective_date::date AS deadline
            FROM upcoming_legislation ul
            WHERE ({company_filter})
              AND ul.current_status IN ('passed', 'signed', 'effective_soon')
              AND ul.expected_effective_date IS NOT NULL
              AND ul.expected_effective_date::date <= $2
        """,
        "link": "/app/matcha/compliance",
    },
    # Compliance requirement expirations — requirements with an expiration date approaching
    {
        "category": "requirement",
        "sql": """
            SELECT cr.id::text,
                   cr.title,
                   cr.jurisdiction_name || ' — ' || cr.category AS subtitle,
                   cr.expiration_date::date AS deadline
            FROM compliance_requirements cr
            JOIN business_locations bl ON bl.id = cr.location_id
            LEFT JOIN jurisdiction_requirements cat
              ON cat.id = cr.jurisdiction_requirement_id
            WHERE ({company_filter_cr})
              {codified_gate_cr}
              AND cr.expiration_date IS NOT NULL
              AND cr.expiration_date::date <= $2
        """,
        "link": "/app/matcha/compliance",
    },
    # Upcoming compliance requirement effective dates — new rules about to take effect
    {
        "category": "legislation",
        "sql": """
            SELECT cr.id::text,
                   cr.title,
                   cr.jurisdiction_name || ' — effective ' || to_char(cr.effective_date, 'Mon DD, YYYY') AS subtitle,
                   cr.effective_date::date AS deadline
            FROM compliance_requirements cr
            JOIN business_locations bl ON bl.id = cr.location_id
            LEFT JOIN jurisdiction_requirements cat
              ON cat.id = cr.jurisdiction_requirement_id
            WHERE ({company_filter_cr})
              {codified_gate_cr}
              AND cr.effective_date IS NOT NULL
              AND cr.effective_date::date > CURRENT_DATE
              AND cr.effective_date::date <= $2
        """,
        "link": "/app/matcha/compliance",
    },
]


def _apply_company_filter(sql: str, company_id: UUID | None) -> str:
    """Replace {company_filter*} placeholders with real WHERE clauses."""
    if company_id is not None:
        return (
            sql
            .replace("{company_filter_emp}", "e.org_id = $1")
            .replace("{company_filter_cobra}", "ce.company_id = $1")
            .replace("{company_filter_i9}", "i9.company_id = $1")
            .replace("{company_filter_onboard}", "eot.company_id = $1")
            .replace("{company_filter_cr}", "bl.company_id = $1")
            .replace("{company_filter}", "company_id = $1")
        )
    # Admin: no company scoping — use TRUE
    return (
        sql
        .replace("{company_filter_emp}", "TRUE")
        .replace("{company_filter_cobra}", "TRUE")
        .replace("{company_filter_i9}", "TRUE")
        .replace("{company_filter_onboard}", "TRUE")
        .replace("{company_filter_cr}", "TRUE")
        .replace("{company_filter}", "TRUE")
    )


@router.get("/upcoming", response_model=UpcomingResponse)
async def get_upcoming_deadlines(
    days: int = Query(90, ge=1, le=365),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Aggregate all time-sensitive items across the platform, sorted by urgency."""
    company_id = await get_client_company_id(current_user)

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, dashboard_upcoming_key(company_id, days))
        if cached is not None:
            return cached

    today = date.today()
    lookahead = today + timedelta(days=days)

    items: list[UpcomingItem] = []

    async with get_connection() as conn:
        gate = await codified_gate_sql("cat", conn=conn)
        for source in _UPCOMING_SOURCES:
            try:
                sql = _apply_company_filter(source["sql"], company_id)
                # A deadline is a claim that a law obliges you by a date. It
                # gets the same gate as the requirement it came from.
                sql = sql.replace("{codified_gate_cr}", gate)
                # Pass only the args the query actually references to avoid asyncpg
                # "N args passed but server expects M" errors.
                uses_p1 = "$1" in sql
                uses_p2 = "$2" in sql
                if uses_p1 and uses_p2:
                    rows = await conn.fetch(sql, company_id, lookahead)
                elif uses_p1:
                    rows = await conn.fetch(sql, company_id)
                elif uses_p2:
                    rows = await conn.fetch(sql, lookahead)
                else:
                    rows = await conn.fetch(sql)
            except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
                logger.debug("Skipping upcoming source %s (table/column missing)", source["category"])
                continue
            except Exception:
                logger.exception("Failed to query upcoming source: %s", source["category"])
                continue

            for row in rows:
                deadline = row["deadline"]
                if deadline is None:
                    continue
                days_until = (deadline - today).days
                link = source["link"]
                row_id = row.get("id")
                if row_id and "{id}" in link:
                    link = link.replace("{id}", row_id)

                items.append(
                    UpcomingItem(
                        category=source["category"],
                        title=row["title"] or source["category"].title(),
                        subtitle=row.get("subtitle"),
                        date=deadline,
                        days_until=days_until,
                        severity=_severity_from_days(days_until),
                        link=link,
                    )
                )

    # Sort by urgency: most overdue / soonest first
    items.sort(key=lambda x: x.days_until)

    result = UpcomingResponse(items=items, total=len(items))

    if redis:
        await cache_set(redis, dashboard_upcoming_key(company_id, days), result.model_dump(), ttl=300)

    return result
