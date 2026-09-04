"""Schedule-blocking eligibility checks and manager-decision case creation."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from .shift_writes import remove_assignment_core
from .job_credential_requirements import job_restriction_starts_on


def _basis(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


# A blocking credential has one of two independent sources of authority:
# a tenant-authored template (crt.schedule_blocking, gated on human review —
# _validate_schedule_blocking already requires a legal-basis citation before
# a template can set this), OR a curated system credential type
# (ct.schedule_blocking, set by migration for e.g. food_handler_card) that
# needs no per-tenant setup. Either alone is sufficient. crt is a LEFT JOIN
# so a requirement created with no template (credential_type_id is NOT NULL
# on the table, so ct itself is always resolvable) still participates.
#
# The curated authority is a company-wide opt-OUT, not opt-in: a tenant that
# doesn't want a curated type (e.g. food_handler_card) to hard-block
# scheduling can create (or edit) any of their own approved templates for
# that credential_type with schedule_blocking=false (no legal-basis citation
# required to turn a block off — only to turn one on) via the existing
# POST/PUT /templates routes. Its presence is treated as a deliberate,
# reviewed decision and suppresses the curated fallback for that credential
# type company-wide, independent of the state/role that template names.
_BLOCKING_AUTHORITY_EXPR = """
(
        (crt.schedule_blocking = true AND crt.review_status IN ('approved', 'auto_approved'))
        OR (
            COALESCE(ct.schedule_blocking, false) = true
            AND NOT EXISTS (
                SELECT 1 FROM credential_requirement_templates opt_out
                WHERE opt_out.company_id = e.org_id
                  AND opt_out.credential_type_id = ct.id
                  AND opt_out.is_active = true
                  AND opt_out.review_status IN ('approved', 'auto_approved')
                  AND opt_out.schedule_blocking = false
            )
        )
)
"""

_BLOCKING_AUTHORITY_SQL = f"AND {_BLOCKING_AUTHORITY_EXPR}"

# credential_requirement_templates.warning_days is NOT NULL DEFAULT 14, so a
# blind COALESCE(crt.warning_days, ct.warning_days, 14) always picks crt's
# default the moment any template is joined — silently shadowing a curated
# type's real warning_days (e.g. 30) even when that template isn't the
# active blocking authority. Pick the value from whichever side actually
# governs the block, matching _BLOCKING_AUTHORITY_SQL's precedence.
#
# Public because the Compliance employee-expiry roster
# (core/routes/compliance/credentials.py) resolves the same per-type window;
# a second hand-rolled copy would re-introduce the shadowing bug above.
# Requires `ecr` LEFT JOINed to `credential_requirement_templates crt` on
# ecr.template_id, and `scoped_credential_types ct`.
WARNING_DAYS_SQL = """
    CASE
        WHEN crt.schedule_blocking = true AND crt.review_status IN ('approved', 'auto_approved')
            THEN crt.warning_days
        ELSE COALESCE(ct.warning_days, 14)
    END
"""


async def _schedule_blocking_requirements(conn, company_id: UUID, employee_ids: list[UUID]):
    if not employee_ids:
        return []
    return await conn.fetch(
        f"""
        SELECT ecr.id, ecr.employee_id, ecr.status, ecr.expires_at,
               ct.label, ct.has_expiration,
               {WARNING_DAYS_SQL} AS warning_days,
               crt.legal_basis
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id
        LEFT JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        LEFT JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
        WHERE e.org_id = $1 AND ecr.employee_id = ANY($2::uuid[])
          AND ecr.is_required = true AND ecr.applies_company_wide = true
          {_BLOCKING_AUTHORITY_SQL}
        """,
        company_id, employee_ids,
    )


def _credential_problem(row, *, as_of: date) -> tuple[str, str] | None:
    """Return a stable reason code/message when a required credential is invalid."""
    label = row["label"] or "Required credential"
    if row["status"] == "waived":
        return None
    if row["status"] != "verified":
        return "credential_missing", f"{label} requires an approved credential document before scheduling."
    if row["has_expiration"] and row["expires_at"] is None:
        return "credential_expiration_unconfirmed", f"{label} requires a confirmed expiration date before scheduling."
    if row["expires_at"] is not None and row["expires_at"] < as_of:
        return "credential_expired", f"{label} expired {row['expires_at'].isoformat()} and blocks new scheduling."
    return None


def _requires_automatic_expiry_unassignment(row, *, as_of: date) -> bool:
    """A removed/rejected document must not erase a known enforcement date.

    Pending renewal evidence still blocks as ``credential_missing`` for new
    writes, but a curated auto-unassign policy uses the last confirmed expiry
    to remove future assignments when that date passes.
    """
    return bool(row.get("auto_unassign_on_expiry", False)) and (
        row.get("expires_at") is not None
        and row["expires_at"] < as_of
        and row.get("status") != "waived"
    )


async def _job_credential_rows(
    conn, *, company_id: UUID, employee_id: UUID, job_id: UUID,
) -> list:
    """Live job rules are authoritative; materialized ECR rows supply evidence."""
    return await conn.fetch(
        """SELECT jr.id AS job_requirement_id, jr.schedule_blocking, jr.is_required,
                  jr.effective_from, ct.label, ct.has_expiration,
                  COALESCE(ecr.status, 'pending') AS status, ecr.expires_at,
                  e.start_date AS employee_start_date, e.created_at::date AS employee_created_on,
                  COALESCE(j.credential_grace_days, c.default_credential_grace_days) AS grace_days
             FROM schedule_job_credential_requirements jr
             JOIN schedule_jobs j ON j.id=jr.job_id AND j.company_id=jr.company_id
             JOIN companies c ON c.id=jr.company_id
             JOIN employees e ON e.id=$2 AND e.org_id=jr.company_id
             JOIN scoped_credential_types ct ON ct.id=jr.credential_type_id
             LEFT JOIN employee_credential_requirements ecr
               ON ecr.employee_id=e.id AND ecr.credential_type_id=jr.credential_type_id
            WHERE jr.company_id=$1 AND jr.job_id=$3 AND jr.is_required AND jr.schedule_blocking""",
        company_id, employee_id, job_id,
    )


def _job_credential_problem(row, *, as_of: date) -> tuple[str, str] | None:
    problem = _credential_problem(row, as_of=as_of)
    if problem is None:
        return None
    code, message = problem
    # Grace only defers an absent/pending document. A known expired credential
    # or an unconfirmed expiry is never made valid by a new-hire grace period.
    if code == "credential_missing" and as_of < job_restriction_starts_on(
        row, employee_start_date=row["employee_start_date"],
    ):
        return None
    return code, message


def local_date_at(instant: datetime, timezone_name: str | None) -> date:
    """Return an operational date in a business location's timezone."""
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except (KeyError, ValueError):
        zone = timezone.utc
    return instant.astimezone(zone).date()


async def _attach_case_assignment(
    conn, *, case_id: UUID, company_id: UUID, employee_id: UUID, assignment, auto_unassign: bool,
) -> None:
    """Attach a future assignment to a case and, for a hard expiry policy,
    remove it in the same reconciliation pass.  The case-assignment row is
    retained as the audit trail even though the live assignment is deleted."""
    await conn.execute(
        """INSERT INTO schedule_eligibility_case_assignments(case_id, shift_id, employee_id, shift_starts_at)
           VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING""",
        case_id, assignment["shift_id"], employee_id, assignment["starts_at"],
    )
    if not auto_unassign:
        return
    deleted = await remove_assignment_core(
        conn, company_id,
        shift_id=assignment["shift_id"], employee_id=employee_id,
        actor_user_id=None, shift_row=assignment,
        audit_details={
            "source": "schedule_eligibility_case",
            "case_id": str(case_id),
            "automatic": True,
        },
    )
    action = "removed" if deleted else "no_longer_assigned"
    await conn.execute(
        """UPDATE schedule_eligibility_case_assignments
           SET action_status=$1, acted_at=NOW()
           WHERE case_id=$2 AND shift_id=$3 AND employee_id=$4""",
        action, case_id, assignment["shift_id"], employee_id,
    )


async def schedule_eligibility_violations(
    conn,
    company_id: UUID,
    *,
    employee_id: UUID,
    shift_date: date,
    location_id: UUID | None = None,
    job_id: UUID | None = None,
    employee_age: int | None = None,
) -> list[dict]:
    """A blocking requirement — tenant-approved template OR curated system
    credential type — cannot be bypassed."""
    rows = await conn.fetch(
        f"""
        SELECT ecr.id, ecr.status, ecr.expires_at, ct.label, ct.has_expiration, crt.legal_basis
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id
        LEFT JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        LEFT JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
        WHERE e.org_id = $1 AND ecr.employee_id = $2
          AND ecr.is_required = true AND ecr.applies_company_wide = true
          {_BLOCKING_AUTHORITY_SQL}
        """, company_id, employee_id,
    )
    permits = await conn.fetch(
        """SELECT id, location_id, issued_at, expires_at, legal_basis FROM employee_work_permits
           WHERE company_id = $1 AND employee_id = $2 AND schedule_blocking = true
             AND status = 'active' AND confirmed_on_file = true
             AND ($3::uuid IS NULL OR location_id = $3)""",
        company_id, employee_id, location_id,
    )
    out = []
    for row in rows:
        problem = _credential_problem(row, as_of=shift_date)
        if problem:
            code, message = problem
            out.append({"check": "schedule_eligibility", "severity": "block", "code": code,
                        "message": message,
                        "statute": _basis(row['legal_basis']).get('citation'), "state": ""})
    if job_id is not None:
        for row in await _job_credential_rows(
            conn, company_id=company_id, employee_id=employee_id, job_id=job_id,
        ):
            problem = _job_credential_problem(row, as_of=shift_date)
            if problem:
                code, message = problem
                out.append({"check": "schedule_eligibility", "severity": "block", "code": code,
                            "message": message, "statute": None, "state": ""})
    # Old direct callers do not provide an age. Preserve their expired-permit
    # behavior while write paths supply age and apply the rule only to minors.
    if employee_age is None:
        expired_permits = [row for row in permits if row["expires_at"] < shift_date]
        for row in expired_permits:
            out.append({"check": "schedule_eligibility", "severity": "block", "code": "minor_work_permit_expired",
                        "message": f"Work permit expired {row['expires_at'].isoformat()} and blocks new scheduling.",
                        "statute": _basis(row['legal_basis']).get('citation'), "state": ""})
    elif employee_age < 18 and location_id is not None:
        valid_permit = next(
            (
                row for row in permits
                if (row.get("issued_at") is None or row["issued_at"] <= shift_date)
                and row["expires_at"] >= shift_date
            ),
            None,
        )
        if valid_permit is None:
            expired = next((row for row in permits if row["expires_at"] < shift_date), None)
            if expired:
                code = "minor_work_permit_expired"
                message = f"Work permit expired {expired['expires_at'].isoformat()} and blocks new scheduling."
                statute = _basis(expired["legal_basis"]).get("citation")
            else:
                code = "minor_work_permit_missing"
                message = "A confirmed work permit is required before scheduling this minor at this location."
                statute = None
            out.append({"check": "schedule_eligibility", "severity": "block", "code": code,
                        "message": message, "statute": statute, "state": ""})
    return out


async def schedule_eligibility_roster_flags(
    conn, company_id: UUID, employee_ids: list[UUID], *, as_of: date,
) -> dict[str, dict[str, list[Any]]]:
    """Blocking and near-expiry credential details for the schedule roster."""
    result: dict[str, dict[str, list[Any]]] = defaultdict(
        lambda: {"blocking_credentials": [], "credential_warnings": [], "credential_expirations": []}
    )
    for row in await _schedule_blocking_requirements(conn, company_id, employee_ids):
        employee_id = str(row["employee_id"])
        problem = _credential_problem(row, as_of=as_of)
        if problem:
            result[employee_id]["blocking_credentials"].append(problem[1])
            continue
        if row["expires_at"] is not None:
            result[employee_id]["credential_expirations"].append({
                "label": row["label"] or "Credential",
                "expires_at": row["expires_at"].isoformat(),
            })
            warning_days = row["warning_days"] or 0
            if row["expires_at"] <= as_of + timedelta(days=warning_days):
                result[employee_id]["credential_warnings"].append(
                    f"{row['label'] or 'Credential'} expires {row['expires_at'].isoformat()}"
                )
    return result


async def open_expiring_eligibility_warnings(
    conn, company_id: UUID, *, now: datetime | None = None, as_of: date | None = None,
) -> list[UUID]:
    """Idempotently open warning_open cases for blocking credentials inside
    their warning window but not yet expired. Never blocks scheduling — the
    block itself starts at expiry, via open_expired_eligibility_cases."""
    # ``as_of`` remains for deterministic legacy callers/tests. Production
    # passes one timezone-aware instant and evaluates it per case location.
    instant = now or datetime.combine(as_of or date.today(), datetime.min.time(), tzinfo=timezone.utc)
    rows = await conn.fetch(
        f"""
        SELECT ecr.id AS requirement_id, ecr.employee_id, ecr.expires_at, crt.legal_basis,
               COALESCE(future.location_id, e.work_location_id) AS location_id,
               scope_location.timezone,
               {WARNING_DAYS_SQL} AS warning_days
        FROM employee_credential_requirements ecr JOIN employees e ON e.id = ecr.employee_id
        LEFT JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        LEFT JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
        LEFT JOIN LATERAL (
            SELECT DISTINCT s.location_id
              FROM schedule_shift_assignments a
              JOIN schedule_shifts s ON s.id=a.shift_id
             WHERE a.employee_id=ecr.employee_id AND s.company_id=e.org_id
               AND s.status <> 'cancelled' AND s.location_id IS NOT NULL
               AND s.starts_at > NOW()
        ) future ON true
        LEFT JOIN business_locations scope_location
          ON scope_location.id=COALESCE(future.location_id, e.work_location_id)
        WHERE e.org_id = $1 AND ecr.is_required = true AND ecr.applies_company_wide = true
          AND ecr.status <> 'waived' AND ecr.expires_at IS NOT NULL
          {_BLOCKING_AUTHORITY_SQL}
        """, company_id,
    )
    opened: list[UUID] = []
    for row in rows:
        location_id = row.get("location_id", row.get("work_location_id"))
        local_as_of = local_date_at(instant, row.get("timezone"))
        if row["expires_at"] < local_as_of:
            continue
        if row["expires_at"] > local_as_of + timedelta(days=row["warning_days"]):
            continue
        case_id = await conn.fetchval(
            """
            INSERT INTO schedule_eligibility_cases
                (company_id, employee_id, location_id, requirement_type, requirement_id, blocking_reason_code, status, expires_at, legal_basis)
            VALUES ($1,$2,$3,'credential',$4,'credential_expiring','warning_open',$5,$6::jsonb)
            ON CONFLICT DO NOTHING RETURNING id
            """, company_id, row['employee_id'], location_id, row['requirement_id'], row['expires_at'],
            json.dumps(_basis(row['legal_basis'])),
        )
        if case_id:
            opened.append(case_id)
    return opened


async def resolve_recovered_eligibility_cases(
    conn, company_id: UUID, *, requirement_id: UUID | None = None,
    now: datetime | None = None, as_of: date | None = None,
) -> int:
    """Close expired-credential cases once a replacement has been verified.

    A food-handler event remains open after automatic shift removal because
    the underlying credential still needs remediation.  This is the single
    place that closes that case after the employee's renewed document is
    approved.
    """
    instant = now or datetime.combine(as_of or date.today(), datetime.min.time(), tzinfo=timezone.utc)
    rows = await conn.fetch(
        f"""
        SELECT c.id, ecr.id AS requirement_id, ecr.status, ecr.expires_at,
               ct.label, ct.has_expiration,
               COALESCE(case_location.timezone, primary_location.timezone) AS timezone,
               CASE WHEN c.job_id IS NOT NULL THEN EXISTS (
                   SELECT 1 FROM schedule_job_credential_requirements jr
                    WHERE jr.company_id=c.company_id AND jr.job_id=c.job_id
                      AND jr.credential_type_id=ecr.credential_type_id
                      AND jr.is_required AND jr.schedule_blocking
               ) ELSE {_BLOCKING_AUTHORITY_EXPR} END AS is_schedule_blocking
          FROM schedule_eligibility_cases c
          LEFT JOIN employees e ON e.id=c.employee_id AND e.org_id=c.company_id
          LEFT JOIN employee_credential_requirements ecr ON ecr.id = c.requirement_id
          LEFT JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
          LEFT JOIN credential_requirement_templates crt ON crt.id=ecr.template_id
          LEFT JOIN business_locations case_location ON case_location.id=c.location_id
          LEFT JOIN business_locations primary_location ON primary_location.id=e.work_location_id
         WHERE c.company_id=$1 AND c.requirement_type='credential'
           AND c.status = ANY($2::text[])
           AND ($3::uuid IS NULL OR c.requirement_id=$3)
        """,
        company_id, ["warning_open", "removal_requested", "keep_acknowledged"],
        requirement_id,
    )
    resolved = 0
    for row in rows:
        current_problem = _credential_problem(
            row, as_of=local_date_at(instant, row.get("timezone")),
        ) if row["requirement_id"] else None
        no_longer_blocking = not bool(row.get("is_schedule_blocking", True))
        if current_problem and not no_longer_blocking:
            continue
        reason = "credential_no_longer_schedule_blocking" if no_longer_blocking else "credential_renewed_or_cleared"
        await conn.execute(
            """UPDATE schedule_eligibility_cases
                  SET status='resolved', resolution_reason=$2,
                      resolved_at=NOW(), updated_at=NOW()
                WHERE id=$1 AND status = ANY($3::text[])""",
            row["id"], reason, ["warning_open", "removal_requested", "keep_acknowledged"],
        )
        resolved += 1
    return resolved


async def open_expired_eligibility_cases(
    conn, company_id: UUID, *, now: datetime | None = None, as_of: date | None = None,
) -> list[UUID]:
    """Create expiry cases and enforce type-specific automatic removals.

    Most schedule-blocking requirements stay manager-mediated.  A curated
    credential type may opt into the narrower ``auto_unassign_on_expiry``
    policy; food-handler cards use it so an expired card removes only future
    assignments while the credential remains blocked for new scheduling.
    """
    instant = now or datetime.combine(as_of or date.today(), datetime.min.time(), tzinfo=timezone.utc)
    rows = await conn.fetch(
        f"""
        SELECT ecr.id AS requirement_id, ecr.employee_id, ecr.status, ecr.expires_at, ct.label, ct.has_expiration,
               crt.legal_basis, e.work_location_id, primary_location.timezone AS primary_timezone,
               COALESCE(ct.auto_unassign_on_expiry, false) AS auto_unassign_on_expiry
        FROM employee_credential_requirements ecr JOIN employees e ON e.id = ecr.employee_id
        LEFT JOIN credential_requirement_templates crt ON crt.id = ecr.template_id
        LEFT JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
        LEFT JOIN business_locations primary_location ON primary_location.id=e.work_location_id
        WHERE e.org_id = $1 AND ecr.is_required = true AND ecr.applies_company_wide = true
          {_BLOCKING_AUTHORITY_SQL}
        """, company_id,
    )
    opened: list[UUID] = []
    for row in rows:
        assignments = await conn.fetch(
            """SELECT s.id AS shift_id, s.location_id, s.starts_at, s.ends_at, s.status, s.kind,
                      location.timezone
               FROM schedule_shifts s JOIN schedule_shift_assignments a ON a.shift_id=s.id
               LEFT JOIN business_locations location ON location.id=s.location_id
               WHERE s.company_id=$1 AND a.employee_id=$2 AND s.status <> 'cancelled'
                 AND s.location_id IS NOT NULL AND s.starts_at > NOW()""",
            company_id, row["employee_id"],
        )
        by_location: dict[UUID, list] = {}
        for assignment in assignments:
            by_location.setdefault(assignment["location_id"], []).append(assignment)

        primary_location = row["work_location_id"]
        if not by_location:
            primary_problem = _credential_problem(
                row, as_of=local_date_at(instant, row.get("primary_timezone")),
            )
            if not primary_problem:
                continue
            reason_code, _message = primary_problem
            auto_unassign = _requires_automatic_expiry_unassignment(
                row, as_of=local_date_at(instant, row.get("primary_timezone")),
            )
            if not auto_unassign:
                # Nothing upcoming to review — closing the stale warning beats
                # opening a manager case with zero assignments.
                await conn.execute(
                    """UPDATE schedule_eligibility_cases
                         SET status='resolved', resolution_reason='expired_no_assignments',
                             resolved_at=NOW(), updated_at=NOW()
                       WHERE company_id=$1 AND employee_id=$2 AND requirement_type='credential'
                         AND requirement_id=$3 AND expires_at=$4
                         AND status IN ('warning_open', 'keep_acknowledged')""",
                    company_id, row['employee_id'], row['requirement_id'], row['expires_at'],
                )
                continue
            by_location[primary_location] = []

        for location_id, location_assignments in by_location.items():
            timezone_name = location_assignments[0].get("timezone") if location_assignments else row.get("primary_timezone")
            problem = _credential_problem(row, as_of=local_date_at(instant, timezone_name))
            if not problem:
                continue
            reason_code, _message = problem
            local_as_of = local_date_at(instant, timezone_name)
            auto_unassign = _requires_automatic_expiry_unassignment(row, as_of=local_as_of)
            case_reason_code = "credential_expired_auto_unassigned" if auto_unassign else reason_code

            # A prior warning (or legacy acknowledgement) occupies the active
            # case key.  Expiry must always turn it into the enforceable case.
            case_id = await conn.fetchval(
                """
                UPDATE schedule_eligibility_cases
                   SET status='removal_requested', blocking_reason_code=$6,
                       manager_decision_by=NULL, manager_decision_at=NULL,
                       manager_acknowledged_by=NULL, manager_acknowledged_at=NULL,
                       acknowledgement_note=NULL, resolved_at=NULL, updated_at=NOW()
                 WHERE company_id=$1 AND employee_id=$2 AND requirement_type='credential'
                   AND requirement_id=$3 AND expires_at=$4
                   AND location_id IS NOT DISTINCT FROM $5
                   AND status IN ('warning_open', 'keep_acknowledged')
                RETURNING id
                """,
                company_id, row['employee_id'], row['requirement_id'], row['expires_at'],
                location_id, case_reason_code,
            )
            new_case = bool(case_id)
            if not case_id:
                case_id = await conn.fetchval(
                    """
                    INSERT INTO schedule_eligibility_cases
                        (company_id, employee_id, location_id, requirement_type, requirement_id, blocking_reason_code, status, expires_at, legal_basis)
                    VALUES ($1,$2,$3,'credential',$4,$5,'removal_requested',$6,$7::jsonb)
                    ON CONFLICT DO NOTHING RETURNING id
                    """,
                    company_id, row['employee_id'], location_id, row['requirement_id'], case_reason_code,
                    row['expires_at'], json.dumps(_basis(row['legal_basis'])),
                )
                new_case = bool(case_id)
            if not case_id and auto_unassign:
                case_id = await conn.fetchval(
                    """
                    UPDATE schedule_eligibility_cases
                       SET blocking_reason_code=$6, updated_at=NOW()
                     WHERE company_id=$1 AND employee_id=$2 AND requirement_type='credential'
                       AND requirement_id=$3 AND expires_at=$4
                       AND location_id IS NOT DISTINCT FROM $5
                       AND status='removal_requested'
                    RETURNING id
                    """,
                    company_id, row['employee_id'], row['requirement_id'], row['expires_at'],
                    location_id, case_reason_code,
                )
            if not case_id:
                continue
            if new_case:
                opened.append(case_id)
            for assignment in location_assignments:
                await _attach_case_assignment(
                    conn, case_id=case_id, company_id=company_id,
                    employee_id=row["employee_id"], assignment=assignment,
                    auto_unassign=auto_unassign,
                )
    return opened


async def open_expired_job_credential_cases(
    conn, company_id: UUID, *, now: datetime | None = None, as_of: date | None = None,
) -> list[UUID]:
    """Remove only the affected job's future assignments after expiry.

    The composite active-case index includes ``job_id``, so this can be run
    repeatedly without duplicating cases, events, or unassignment audit rows.
    """
    instant = now or datetime.combine(as_of or date.today(), datetime.min.time(), tzinfo=timezone.utc)
    rows = await conn.fetch(
        """SELECT jr.job_id, ecr.id AS requirement_id, ecr.employee_id, ecr.status, ecr.expires_at,
                  ct.label, ct.has_expiration, COALESCE(ct.auto_unassign_on_expiry,false) AS auto_unassign_on_expiry
             FROM schedule_job_credential_requirements jr
             JOIN employee_credential_requirements ecr ON ecr.credential_type_id=jr.credential_type_id
             JOIN scoped_credential_types ct ON ct.id=jr.credential_type_id
             JOIN employees e ON e.id=ecr.employee_id AND e.org_id=jr.company_id
             JOIN schedule_job_employees sje
               ON sje.job_id=jr.job_id AND sje.employee_id=ecr.employee_id AND sje.company_id=jr.company_id
            WHERE jr.company_id=$1 AND jr.is_required AND jr.schedule_blocking""",
        company_id,
    )
    opened: list[UUID] = []
    for row in rows:
        assignments = await conn.fetch(
            """SELECT s.id AS shift_id, s.location_id, s.starts_at, s.ends_at, s.status, s.kind, location.timezone
                 FROM schedule_shifts s
                 JOIN schedule_shift_assignments a ON a.shift_id=s.id
                 LEFT JOIN business_locations location ON location.id=s.location_id
                WHERE s.company_id=$1 AND s.job_id=$2 AND a.employee_id=$3
                  AND s.status <> 'cancelled' AND s.location_id IS NOT NULL AND s.starts_at > NOW()""",
            company_id, row["job_id"], row["employee_id"],
        )
        by_location: dict[UUID, list] = {}
        for assignment in assignments:
            by_location.setdefault(assignment["location_id"], []).append(assignment)
        for location_id, location_assignments in by_location.items():
            problem = _credential_problem(
                row, as_of=local_date_at(instant, location_assignments[0].get("timezone")),
            )
            if not problem:
                continue
            reason_code, _message = problem
            local_as_of = local_date_at(instant, location_assignments[0].get("timezone"))
            auto_unassign = _requires_automatic_expiry_unassignment(row, as_of=local_as_of)
            case_reason_code = "credential_expired_auto_unassigned" if auto_unassign else reason_code
            case_id = await conn.fetchval(
                """INSERT INTO schedule_eligibility_cases
                       (company_id, employee_id, location_id, job_id, requirement_type, requirement_id,
                        blocking_reason_code, status, expires_at, legal_basis)
                   VALUES ($1,$2,$3,$4,'credential',$5,$6,'removal_requested',$7,'{}'::jsonb)
                   ON CONFLICT DO NOTHING RETURNING id""",
                company_id, row["employee_id"], location_id, row["job_id"], row["requirement_id"],
                case_reason_code, row["expires_at"],
            )
            new_case = bool(case_id)
            if not case_id:
                case_id = await conn.fetchval(
                    """SELECT id FROM schedule_eligibility_cases
                         WHERE company_id=$1 AND employee_id=$2 AND location_id IS NOT DISTINCT FROM $3
                           AND job_id=$4 AND requirement_type='credential' AND requirement_id=$5
                           AND expires_at=$6 AND status IN ('warning_open','removal_requested',
                               'removal_confirmed','keep_acknowledged')""",
                    company_id, row["employee_id"], location_id, row["job_id"], row["requirement_id"], row["expires_at"],
                )
            if not case_id:
                continue
            if new_case:
                opened.append(case_id)
            for assignment in location_assignments:
                await _attach_case_assignment(
                    conn, case_id=case_id, company_id=company_id, employee_id=row["employee_id"],
                    assignment=assignment, auto_unassign=auto_unassign,
                )
    return opened
