"""compliance_service.alerts — J6 split of compliance_service.py."""
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
    parse_date,
)
from app.core.services.compliance_service._normalize import (
    _normalize_legislation_status,
    _normalize_title_key,
)



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
    from app.config import get_settings as _get_settings
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
    from app.config import get_settings as _get_settings
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
    from app.core.services.email import get_email_service

    email_service = get_email_service()
    if not email_service.is_configured():
        return

    company_name, contacts = await _get_company_admin_contacts(company_id)
    if not contacts:
        return

    from app.database import get_connection
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
    """Company name + admin contacts. Delegates to the shared helper."""
    return await get_company_name_and_contacts(company_id)




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

    from app.core.services.email import get_email_service

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




async def get_company_alerts(
    company_id: UUID,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    location_id: Optional[UUID] = None,
) -> List[AlertResponse]:
    from app.database import get_connection

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
    from app.database import get_connection
    from app.core.models.compliance import CalendarItem
    from app.core.services.compliance_baseline import get_baseline_calendar_items
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
    from app.database import get_connection
    from datetime import datetime

    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE compliance_alerts SET status = 'read', read_at = NOW() WHERE id = $1 AND company_id = $2",
            alert_id,
            company_id,
        )
        return result == "UPDATE 1"




async def dismiss_alert(alert_id: UUID, company_id: UUID) -> bool:
    from app.database import get_connection
    from datetime import datetime

    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE compliance_alerts SET status = 'dismissed', dismissed_at = NOW() WHERE id = $1 AND company_id = $2",
            alert_id,
            company_id,
        )
        return result == "UPDATE 1"




async def update_alert_action_plan(
    alert_id: UUID,
    company_id: UUID,
    updates: Dict[str, Any],
    actor_user_id: Optional[UUID] = None,
) -> Optional[dict]:
    """Update alert action-plan metadata and optionally mark the alert as actioned."""
    from app.database import get_connection

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




async def get_upcoming_legislation(
    location_id: UUID, company_id: UUID
) -> List[UpcomingLegislationResponse]:
    """Get upcoming legislation for a location."""
    from app.database import get_connection

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
