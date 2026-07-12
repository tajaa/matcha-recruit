"""Cross-cutting helpers for the employees router package.

Pure helpers + column-probe helpers + invitation service + background tasks
shared by multiple submodules in the employees package. Extracted from
`_legacy.py` during the 2026-05-16 package split.
"""
import json
import logging
import secrets
from datetime import datetime, date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks, HTTPException

from app.database import get_connection
from app.core.us_states import US_STATE_CODES
from app.core.services.compliance_service import ensure_location_for_employee
from app.core.services.email import get_email_service
from app.matcha.services.onboarding_orchestrator import (
    PROVIDER_SLACK,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)
from app.matcha.services.risk_assessment_service import (
    compute_risk_assessment,
    generate_recommendations,
    load_risk_weights,
    write_risk_history,
)

logger = logging.getLogger(__name__)

INVITATION_SEND_FAILED_DETAIL = "Invitation email could not be sent. Check email delivery settings and try again."

# `work_state` values (CSV bulk-upload and single-employee create/update) are
# validated against the canonical US jurisdiction set (case-insensitive; full
# state names also normalized) so a typo doesn't silently create an ungrounded
# compliance jurisdiction (Phase D2 stopgap — see COMPLIANCE_REMEDIATION_PLAN.md).
_VALID_WORK_STATE_CODES = US_STATE_CODES

_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "washington dc": "DC", "washington d.c.": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "american samoa": "AS", "guam": "GU", "northern mariana islands": "MP",
    "puerto rico": "PR", "virgin islands": "VI", "us virgin islands": "VI",
}


def _normalize_work_state(raw: Optional[str]) -> tuple[Optional[str], bool]:
    """Normalize a `work_state` value to a 2-letter USPS code.

    Returns `(normalized_code_or_None, is_valid)`. Blank/None input is valid
    (no work location provided — counted separately by callers, e.g. as
    `rows_missing_work_location` in bulk upload). A non-blank value that
    isn't a recognized state/territory abbreviation or full name is invalid.
    """
    s = (raw or "").strip()
    if not s:
        return None, True
    if len(s) == 2 and s.isalpha() and s.upper() in _VALID_WORK_STATE_CODES:
        return s.upper(), True
    mapped = _STATE_NAME_TO_CODE.get(s.lower())
    if mapped:
        return mapped, True
    return None, False


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _coerce_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _exception_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


def _parse_csv_date(val: str) -> Optional[date]:
    """Parse a YYYY-MM-DD date string from a CSV cell; return None if blank or invalid."""
    if not val or not val.strip():
        return None
    try:
        return datetime.strptime(val.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = $1 AND column_name = $2
            )
            """,
            table_name,
            column_name,
        )
    )


async def _employee_compensation_fields_available(conn) -> bool:
    columns = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'employees'
          AND column_name = ANY($1::text[])
        """,
        ["pay_classification", "pay_rate", "work_city"],
    )
    existing = {row["column_name"] for row in columns}
    return {
        "pay_classification",
        "pay_rate",
        "work_city",
    }.issubset(existing)


async def _employee_status_fields_available(conn) -> bool:
    columns = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'employees'
          AND column_name = ANY($1::text[])
        """,
        ["employment_status", "status_changed_at", "status_reason"],
    )
    existing = {row["column_name"] for row in columns}
    return {
        "employment_status",
        "status_changed_at",
        "status_reason",
    }.issubset(existing)


async def _employee_org_fields_available(conn) -> bool:
    columns = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'employees'
          AND column_name = ANY($1::text[])
        """,
        ["job_title", "department"],
    )
    existing = {row["column_name"] for row in columns}
    return {"job_title", "department"}.issubset(existing)


async def _sync_employee_location_for_compliance(
    conn,
    *,
    company_id: UUID,
    employee_id: UUID,
    work_state: Optional[str],
    work_city: Optional[str],
    background_tasks: Optional[BackgroundTasks] = None,
) -> Optional[UUID]:
    normalized_state = work_state.strip().upper() if work_state else None
    normalized_city = work_city.strip() if work_city else None
    if not normalized_state:
        return None

    try:
        return await ensure_location_for_employee(
            conn,
            company_id,
            normalized_city,
            normalized_state,
            background_tasks=background_tasks,
        )
    except Exception:
        logger.exception(
            "Failed to sync compliance location for employee %s in company %s",
            employee_id,
            company_id,
        )
        return None


def _employee_compensation_values(
    row,
    compensation_fields_available: bool,
) -> tuple[Optional[str], Optional[float], Optional[str]]:
    if not compensation_fields_available:
        return None, None, None
    return (
        row["pay_classification"],
        float(row["pay_rate"]) if row["pay_rate"] is not None else None,
        row["work_city"],
    )


async def send_single_invitation(
    employee_id: UUID,
    org_id: UUID,
    invited_by: UUID,
    conn=None,
    raise_on_email_failure: bool = True,
) -> dict:
    """
    Shared function to send invitation to a single employee.
    Used by both individual invite endpoint and bulk invite endpoint.

    Args:
        raise_on_email_failure: If False, keep invitation pending when email
            fails instead of cancelling it (used by bulk flows so admins can resend).

    Returns: {"invitation_id": UUID, "token": str, "expires_at": datetime}
    """
    if conn is None:
        async with get_connection() as own_conn:
            return await _send_invitation_with_conn(employee_id, org_id, invited_by, own_conn, raise_on_email_failure=raise_on_email_failure)
    return await _send_invitation_with_conn(employee_id, org_id, invited_by, conn, raise_on_email_failure=raise_on_email_failure)


async def _send_invitation_with_conn(
    employee_id: UUID,
    org_id: UUID,
    invited_by: UUID,
    conn,
    raise_on_email_failure: bool = True,
) -> dict:
    async with conn.transaction():
        # Lock the employee row to serialize concurrent invite/resend calls so
        # only one active invitation per employee can be created at a time.
        employee = await conn.fetchrow(
            "SELECT * FROM employees WHERE id = $1 AND org_id = $2 FOR UPDATE",
            employee_id, org_id
        )

        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        if employee["user_id"]:
            raise HTTPException(status_code=400, detail="Employee already has an account")

        # Cancel all existing pending invitations for this employee
        await conn.execute(
            """
            UPDATE employee_invitations SET status = 'cancelled'
            WHERE employee_id = $1 AND status = 'pending'
            """,
            employee_id
        )

        # Generate new invitation token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)

        # Create invitation record
        invitation = await conn.fetchrow(
            """
            INSERT INTO employee_invitations (org_id, employee_id, invited_by, token, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, employee_id, token, status, expires_at, created_at
            """,
            org_id, employee_id, invited_by, token, expires_at
        )

    # Get company name for email (outside transaction — read-only)
    company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", org_id)
    company_name = company["name"] if company else "Your Company"

    await _sync_employee_location_for_compliance(
        conn,
        company_id=org_id,
        employee_id=employee_id,
        work_state=employee.get("work_state"),
        work_city=employee.get("work_city"),
    )

    # Send invitation email
    email_service = get_email_service()
    sent = await email_service.send_employee_invitation_email(
        to_email=employee["email"],
        to_name=f"{employee['first_name']} {employee['last_name']}",
        company_name=company_name,
        token=token,
        expires_at=expires_at,
    )
    if not sent:
        if raise_on_email_failure:
            logger.warning(
                "Employee invitation email failed for employee %s in company %s; cancelling invitation %s",
                employee_id,
                org_id,
                invitation["id"],
            )
            await conn.execute(
                "UPDATE employee_invitations SET status = 'cancelled' WHERE id = $1",
                invitation["id"],
            )
            raise HTTPException(status_code=503, detail=INVITATION_SEND_FAILED_DETAIL)
        else:
            # Bulk mode: keep invitation pending so admin can resend later,
            # but raise so the caller records an error row for this employee.
            logger.warning(
                "Employee invitation email failed for employee %s in company %s; invitation %s kept pending for retry",
                employee_id,
                org_id,
                invitation["id"],
            )
            raise RuntimeError(INVITATION_SEND_FAILED_DETAIL)

    return {
        "invitation_id": invitation["id"],
        "token": invitation["token"],
        "expires_at": invitation["expires_at"]
    }


async def _auto_send_invitation(
    *,
    employee_id: UUID,
    org_id: UUID,
    invited_by: UUID,
) -> None:
    """Background task: auto-send invitation to a newly created employee."""
    try:
        await send_single_invitation(employee_id, org_id, invited_by)
    except Exception:
        logger.exception("Auto-invite background task failed for employee %s", employee_id)


async def _refresh_risk_assessment(company_id: UUID) -> None:
    """Background task: recompute risk assessment snapshot after a wage change."""
    # Pass 1: save updated dimensions immediately so violations reflect right away
    try:
        async with get_connection() as conn:
            weights = await load_risk_weights(conn)
        result = await compute_risk_assessment(company_id, weights=weights)
        from dataclasses import asdict as _asdict
        dims_json = json.dumps(
            {k: _asdict(v) for k, v in result.dimensions.items()},
            default=str,
        )
        weights_json = json.dumps(weights)
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO risk_assessment_snapshots
                    (company_id, overall_score, overall_band, dimensions, weights, computed_at, computed_by)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, NULL)
                ON CONFLICT (company_id) DO UPDATE SET
                    overall_score = EXCLUDED.overall_score,
                    overall_band  = EXCLUDED.overall_band,
                    dimensions    = EXCLUDED.dimensions,
                    weights       = EXCLUDED.weights,
                    computed_at   = EXCLUDED.computed_at,
                    computed_by   = NULL
                """,
                company_id,
                result.overall_score,
                result.overall_band,
                dims_json,
                weights_json,
                result.computed_at,
            )
            # Record in history so trend / anomaly / correlation views see this
            # recompute (the manual + scheduled writers both do this).
            await write_risk_history(
                conn,
                company_id,
                overall_score=result.overall_score,
                overall_band=result.overall_band,
                dims_json=dims_json,
                weights_json=weights_json,
                computed_at=result.computed_at,
                source="auto",
            )
        logger.info("Risk assessment dimensions refreshed for company %s", company_id)
    except Exception:
        logger.exception("Background risk assessment refresh failed for company %s", company_id)
        return

    # Pass 2: update recommendations (best-effort, won't block violation updates)
    try:
        from app.config import get_settings
        consultation = await generate_recommendations(result, get_settings())
        async with get_connection() as conn:
            await conn.execute(
                """
                UPDATE risk_assessment_snapshots SET
                    report          = $2,
                    recommendations = $3::jsonb
                WHERE company_id = $1
                """,
                company_id,
                consultation.get("report"),
                json.dumps(consultation.get("recommendations", []) or [], default=str),
            )
        logger.info("Risk assessment recommendations updated for company %s", company_id)
    except Exception:
        logger.exception("Background risk assessment recommendations failed for company %s (dimensions already saved)", company_id)


async def _perform_oig_screening(
    *,
    employee_id: UUID,
    org_id: UUID,
    first_name: str,
    last_name: str,
) -> None:
    """Background task: screen employee against OIG LEIE exclusion list."""
    from app.core.services.oig_screening import get_oig_screening_service

    try:
        svc = get_oig_screening_service()
        result = await svc.screen_individual(first_name=first_name, last_name=last_name)

        async with get_connection() as conn:
            # Update credentials table (oig_status + oig_last_checked already exist)
            await conn.execute(
                """
                UPDATE employee_credentials
                SET oig_status = $1, oig_last_checked = CURRENT_DATE
                WHERE employee_id = $2 AND org_id = $3
                """,
                result.status,
                employee_id,
                org_id,
            )
            # If no credentials row yet, insert a minimal one
            if await conn.fetchval(
                "SELECT 1 FROM employee_credentials WHERE employee_id = $1 AND org_id = $2",
                employee_id, org_id,
            ) is None:
                await conn.execute(
                    """
                    INSERT INTO employee_credentials (employee_id, org_id, oig_status, oig_last_checked)
                    VALUES ($1, $2, $3, CURRENT_DATE)
                    """,
                    employee_id, org_id, result.status,
                )

        if result.matched:
            name = f"{first_name} {last_name}".strip()
            logger.warning(
                "OIG LEIE match for employee %s (%s): confidence=%s, %d matches",
                employee_id, name, result.confidence, len(result.matches),
            )
            # Email alert to company admins
            try:
                email_svc = get_email_service()
                if email_svc.is_configured():
                    async with get_connection() as conn:
                        admins = await conn.fetch(
                            """
                            SELECT u.email, cl.name AS first_name
                            FROM users u
                            JOIN clients cl ON cl.user_id = u.id
                            WHERE cl.company_id = $1 AND u.role = 'client'
                            """,
                            org_id,
                        )
                    for admin in admins:
                        await email_svc.send_email(
                            to_email=admin["email"],
                            to_name=admin["first_name"],
                            subject=f"OIG Exclusion Alert: {name}",
                            html_content=f"""
                            <div style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                                <div style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 16px; border-radius: 8px;">
                                    <h2 style="color: #dc2626; margin-top: 0;">OIG Exclusion Match Detected</h2>
                                    <p>Employee <strong>{name}</strong> has been flagged during OIG LEIE screening.</p>
                                    <p><strong>Confidence:</strong> {result.confidence}</p>
                                    <p><strong>Matches found:</strong> {len(result.matches)}</p>
                                    <p style="color: #6b7280; font-size: 14px;">
                                        Please review this match immediately. Employing an excluded individual in a federal
                                        healthcare program can result in Civil Monetary Penalties of $100,000 per item/service.
                                    </p>
                                </div>
                            </div>
                            """,
                            text_content=f"OIG Exclusion Match: {name} — confidence: {result.confidence}, {len(result.matches)} match(es). Review immediately.",
                        )
            except Exception:
                logger.exception("Failed to send OIG alert email for employee %s", employee_id)
        else:
            logger.info("OIG LEIE screening cleared for employee %s", employee_id)

    except Exception:
        logger.exception("OIG screening failed for employee %s", employee_id)


async def _run_provisioning_and_notify(
    *,
    company_id: UUID,
    employee_id: UUID,
    triggered_by: UUID,
    personal_email: str | None,
    employee_name: str,
    work_email: str,
    run_google: bool,
    run_slack: bool,
) -> None:
    """Run provisioning for Google Workspace and/or Slack, then send a combined welcome email."""
    logger.info("[Provisioning] Starting for employee %s (%s) — google=%s, slack=%s",
                employee_id, work_email, run_google, run_slack)
    google_result: dict | None = None
    slack_result: dict | None = None

    if run_google:
        try:
            google_result = await start_google_workspace_onboarding(
                company_id=company_id,
                employee_id=employee_id,
                triggered_by=triggered_by,
                trigger_source="employee_create",
            )
            logger.info("[Provisioning] Google Workspace result for %s: status=%s",
                        work_email, google_result.get("status") if google_result else "None")
        except Exception:
            logger.exception(
                "Failed Google Workspace auto-provisioning for employee %s in company %s",
                employee_id,
                company_id,
            )

    if run_slack:
        try:
            slack_result = await start_slack_onboarding(
                company_id=company_id,
                employee_id=employee_id,
                triggered_by=triggered_by,
                trigger_source="employee_create",
            )
            logger.info("[Provisioning] Slack result for %s: status=%s",
                        work_email, slack_result.get("status") if slack_result else "None")
        except Exception:
            logger.exception(
                "Failed Slack auto-provisioning for employee %s in company %s",
                employee_id,
                company_id,
            )

    logger.info("[Provisioning] Sending welcome email to %s (personal_email=%s)", work_email, personal_email)
    await _send_provisioning_email(
        company_id=company_id,
        personal_email=personal_email,
        employee_name=employee_name,
        work_email=work_email,
        google_result=google_result,
        slack_result=slack_result,
    )
    logger.info("[Provisioning] Complete for %s", work_email)


async def _send_provisioning_email(
    *,
    company_id: UUID,
    personal_email: str | None,
    employee_name: str,
    work_email: str,
    google_result: dict | None,
    slack_result: dict | None,
) -> None:
    """Send a welcome email with provisioning credentials if applicable."""
    if not personal_email:
        return

    # Extract initial_password from Google result (set by orchestrator, not persisted to DB)
    temp_password: str | None = None
    if google_result:
        temp_password = google_result.get("initial_password")

    # Extract Slack invite link and workspace name from Slack result steps + integration config
    slack_invite_link: str | None = None
    slack_workspace_name: str | None = None
    if slack_result:
        for step in slack_result.get("steps") or []:
            resp = step.get("last_response") or {}
            if resp.get("invite_link"):
                slack_invite_link = resp["invite_link"]
                break

    google_succeeded = google_result and google_result.get("status") == "completed"
    slack_succeeded = slack_result and slack_result.get("status") == "completed"

    if not google_succeeded and not slack_succeeded:
        return

    # Fetch company name and Slack workspace name from DB
    try:
        async with get_connection() as conn:
            company_name = await conn.fetchval(
                "SELECT name FROM companies WHERE id = $1", company_id,
            ) or "Your Company"
            if slack_succeeded:
                slack_config_row = await conn.fetchval(
                    "SELECT config FROM integration_connections WHERE company_id = $1 AND provider = $2",
                    company_id, PROVIDER_SLACK,
                )
                if slack_config_row:
                    slack_cfg = json.loads(slack_config_row) if isinstance(slack_config_row, str) else slack_config_row
                    slack_workspace_name = slack_cfg.get("slack_team_name")
    except Exception:
        logger.exception("Failed to fetch company info for provisioning email")
        company_name = "Your Company"

    email_svc = get_email_service()
    try:
        await email_svc.send_provisioning_welcome_email(
            to_email=personal_email,
            to_name=employee_name,
            company_name=company_name,
            work_email=work_email if google_succeeded else None,
            temp_password=temp_password,
            slack_workspace_name=slack_workspace_name,
            slack_invite_link=slack_invite_link,
        )
    except Exception:
        logger.exception("Failed to send provisioning welcome email to %s", personal_email)
