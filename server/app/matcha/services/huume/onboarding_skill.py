"""Huume skill #1 — end-to-end new-hire onboarding.

Two halves, same split as the rest of the codebase's confirm-first
subsystems (`hr_pilot_actions`, `discipline_compliance`): a PURE plan
builder (`build_onboarding_plan`) that is unit-testable against plain
dicts, and DB-bound tool handlers / step executors that do the actual
reads and writes. `actions.py` owns the safety envelope that gates when
these executors are allowed to run — nothing here re-checks authz itself.
"""

from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from app.matcha.services.employees.invitations import _send_invitation_with_conn
from app.matcha.services.offer_letters.document import _send_candidate_range_email

logger = logging.getLogger(__name__)

# The full v1 onboarding plan, in execution order. `create_employee` always
# runs first (actions.execute_plan_steps re-sorts on top of this anyway).
PLAN_STEP_ORDER: tuple[tuple[str, str], ...] = (
    ("create_employee", "Create employee record"),
    ("portal_invitation", "Send employee portal invitation"),
    ("onboarding_tasks", "Assign onboarding task checklist"),
    ("credential_requirements", "Assign credential requirements"),
    ("training_assignment", "Assign new-hire training"),
    ("google_workspace", "Provision Google Workspace account"),
    ("slack", "Provision Slack account"),
    ("schedule_note", "Note upcoming shift coverage"),
    ("benefits_note", "Note benefits eligibility window"),
    ("jurisdiction_packet_note", "Note new-hire jurisdiction notices"),
)


# ---------------------------------------------------------------------------
# Pure: plan builder
# ---------------------------------------------------------------------------

def build_onboarding_plan(
    *,
    offer: dict[str, Any],
    features: dict[str, Any],
    integrations: dict[str, bool],
) -> dict[str, Any]:
    """Build the staged onboarding plan for an accepted offer. Pure — every
    feature-missing / integration-missing step is marked `skipped` up front
    with a reason so the admin sees why, and `actions.evaluate_plan_step`
    re-checks the same conditions at execute time (a flag can change between
    turns)."""
    features = features or {}
    integrations = integrations or {}

    steps: list[dict[str, Any]] = []
    for key, label in PLAN_STEP_ORDER:
        from app.matcha.services.huume.actions import evaluate_plan_step
        step = {
            "key": key, "label": label, "status": "proposed",
            "requires": None, "reason": None, "record_id": None, "error": None,
        }
        reason = evaluate_plan_step(step, features=features, integrations=integrations, employee_id=None)
        # create_employee has no employee_id dependency, so a reason here at
        # plan-build time reflects a real missing flag/integration, not the
        # employee-not-created-yet placeholder every other step would trip.
        if key != "create_employee" and reason == "waiting on create_employee to run first":
            reason = None
        if reason:
            step["status"] = "skipped"
            step["reason"] = reason
        steps.append(step)

    name = (offer.get("candidate_name") or "").strip()
    first_name, _, last_name = name.partition(" ")

    return {
        "status": "proposed",
        "offer_id": str(offer["id"]),
        "employee": {
            "first_name": first_name or name,
            "last_name": last_name or None,
            "email": offer.get("candidate_email"),
            "position_title": offer.get("position_title"),
            "start_date": offer.get("start_date").isoformat() if isinstance(offer.get("start_date"), (date, datetime)) else offer.get("start_date"),
            "location": offer.get("location"),
            "employment_type": offer.get("employment_type"),
        },
        "employee_id": None,
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# DB-bound: tool handlers (called from agent.py's function-calling loop)
# ---------------------------------------------------------------------------

async def lookup_context(
    *, company_id: UUID, topic: str, query: Optional[str] = None, features: Optional[dict[str, Any]] = None,
    days: Optional[int] = None,
) -> dict[str, Any]:
    """Agent-facing tool wrapper — opens its own connection."""
    from app.database import get_connection
    async with get_connection() as conn:
        return await _lookup_context_impl(conn, company_id=company_id, topic=topic, query=query, features=features, days=days)


# topic -> feature flag gating it. Absent from this dict = no extra gate
# (roster/templates/integrations/offers, which predate this and ride only
# `huume` + the mode's own gate).
_TOPIC_REQUIRED_FEATURE: dict[str, str] = {
    "training": "training",
    "training_status": "training",
    "credentials": "credential_templates",
    "employee": "employees",
    "schedule": "employee_schedule",
    "incidents": "incidents",
    "er_cases": "er_copilot",
    "pto_leave": "employees",
    "policies": "handbooks",
    "discipline": "discipline",
    "documents": "employees",
    "events": "ems",
}

# compliance is gated on either of two flags (Matcha-X's read-only taste or
# full Compliance) — handled separately from the single-flag dict above.
_COMPLIANCE_TOPIC_FLAGS = ("compliance", "compliance_lite")

# A leave that has already started is `active`, not `approved` — filtering on
# `approved` alone reports "nobody is out" for exactly the people who are out
# right now. Same pair `hr_proactive_push` and `discipline_compliance`'s
# PROTECTED_LEAVE_STATUSES use ('completed' is excluded here: this topic is
# about who is out NOW, not leave history).
_OPEN_LEAVE_STATUSES = ("approved", "active")

# `dismissed` is a closed alert (the admin looked and decided no action) —
# counting it as open overstates what's outstanding. `actioned` and
# `dismissed` are both terminal; `unread`/`read` are the open set.
_OPEN_ALERT_STATUSES = ("unread", "read")

# Mirrors `hr_proactive_push.SIGNATURE_STALE_DAYS` — the documents topic and
# the proactive digest must agree on what counts as overdue, or an admin gets
# two different answers to the same question. Duplicated rather than imported:
# this module must not pull in a Celery-worker module.
_SIGNATURE_STALE_DAYS = 7

_INCIDENT_LOOKBACK_DEFAULT_DAYS = 90
_INCIDENT_LOOKBACK_MAX_DAYS = 365


def _clamp_incident_days(days: Optional[int]) -> int:
    """Model-supplied window, clamped to a sane range. A bad/missing value
    (None, non-numeric, 0, negative, huge) degrades to the default rather
    than erroring — this backs a chat lookup, not a form field. The tool
    schema declares `days` as INTEGER, but a digit-string ("30") is coerced
    rather than silently defaulted — Gemini function-calling args have been
    observed to arrive JSON-decoded loosely typed."""
    if isinstance(days, str) and days.strip().lstrip("-").isdigit():
        days = int(days)
    if not isinstance(days, int) or isinstance(days, bool) or days <= 0:
        return _INCIDENT_LOOKBACK_DEFAULT_DAYS
    return min(days, _INCIDENT_LOOKBACK_MAX_DAYS)


async def _lookup_context_impl(
    conn, *, company_id: UUID, topic: str, query: Optional[str] = None, features: Optional[dict[str, Any]] = None,
    days: Optional[int] = None,
) -> dict[str, Any]:
    """Read-only grounding lookup for a handful of topics. Never raises —
    degrades to an empty/estimate result so a lookup failure doesn't kill
    the turn. Gate check runs BEFORE any SQL (three-state idiom from
    `hr_pilot_corpus`: flag off -> {"module": "off"}, distinct from
    on-but-empty -> an empty list)."""
    required = _TOPIC_REQUIRED_FEATURE.get(topic)
    if required and not (features or {}).get(required):
        return {"topic": topic, "module": "off", "note": f"'{required}' isn't enabled for this company."}
    if topic == "compliance" and not any((features or {}).get(f) for f in _COMPLIANCE_TOPIC_FLAGS):
        return {"topic": topic, "module": "off", "note": "Compliance isn't enabled for this company."}
    try:
        if topic == "roster":
            rows = await conn.fetch(
                """
                SELECT id, first_name, last_name, email, job_title
                FROM employees
                WHERE org_id = $1 AND (COALESCE(employment_status,'active') NOT IN ('terminated','offboarded'))
                  AND ($2::text IS NULL OR (first_name || ' ' || last_name) ILIKE '%' || $2 || '%' OR email ILIKE '%' || $2 || '%')
                ORDER BY first_name LIMIT 10
                """,
                company_id, query,
            )
            return {"topic": "roster", "matches": [dict(r) for r in rows]}
        if topic == "templates":
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM onboarding_tasks WHERE org_id = $1 AND is_active = TRUE",
                company_id,
            )
            return {"topic": "templates", "active_template_count": count or 0}
        if topic == "integrations":
            rows = await conn.fetch(
                "SELECT provider FROM integration_connections WHERE company_id = $1",
                company_id,
            )
            connected = {r["provider"] for r in rows}
            return {
                "topic": "integrations",
                "google_workspace_connected": "google_workspace" in connected,
                "slack_connected": "slack" in connected,
            }
        if topic == "training":
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM training_assignment_rules WHERE company_id = $1 AND trigger = 'new_hire' AND is_active = TRUE",
                company_id,
            )
            # The requirement catalog is what makes `assign_training` usable —
            # that tool takes a requirement_id and refuses a name, so the ids
            # have to be reachable from a lookup.
            requirements = await conn.fetch(
                """
                SELECT id, title, training_type, frequency_months
                FROM training_requirements
                WHERE company_id = $1 AND is_active = TRUE
                  AND ($2::text IS NULL OR title ILIKE '%' || $2 || '%')
                ORDER BY title LIMIT 20
                """,
                company_id, query,
            )
            return {
                "topic": "training",
                "new_hire_rule_count": count or 0,
                "active_requirements": [dict(r) for r in requirements],
            }
        if topic == "credentials":
            rows = await conn.fetch(
                """
                SELECT ecr.id, e.first_name, e.last_name, ct.label AS credential_label, ecr.status, ecr.due_date
                FROM employee_credential_requirements ecr
                JOIN employees e ON e.id = ecr.employee_id
                JOIN credential_types ct ON ct.id = ecr.credential_type_id
                WHERE e.org_id = $1 AND ecr.waived_at IS NULL
                  AND ecr.status != 'verified'
                  AND ecr.due_date IS NOT NULL AND ecr.due_date < CURRENT_DATE + INTERVAL '60 days'
                ORDER BY ecr.due_date LIMIT 10
                """,
                company_id,
            )
            return {"topic": "credentials", "expiring_or_overdue": [dict(r) for r in rows]}
        if topic == "employee":
            row = await conn.fetchrow(
                """
                SELECT id, first_name, last_name, email, job_title, employment_status, start_date, work_state
                FROM employees
                WHERE org_id = $1 AND (($2::text IS NOT NULL AND (
                    (first_name || ' ' || last_name) ILIKE '%' || $2 || '%' OR email ILIKE $2
                )))
                ORDER BY first_name LIMIT 1
                """,
                company_id, query,
            )
            if not row:
                return {"topic": "employee", "match": None, "note": "No employee matched that name/email."}
            return {"topic": "employee", "match": dict(row)}
        if topic == "training_status":
            counts = await conn.fetch(
                "SELECT status, COUNT(*) FROM training_records WHERE company_id = $1 GROUP BY status",
                company_id,
            )
            overdue = await conn.fetch(
                """
                SELECT e.first_name, e.last_name, tr.title, tr.due_date
                FROM training_records tr JOIN employees e ON e.id = tr.employee_id
                WHERE tr.company_id = $1 AND tr.status NOT IN ('completed', 'waived')
                  AND tr.due_date IS NOT NULL AND tr.due_date < CURRENT_DATE
                ORDER BY tr.due_date LIMIT 10
                """,
                company_id,
            )
            return {
                "topic": "training_status",
                "counts_by_status": {r["status"]: r["count"] for r in counts},
                "overdue": [dict(r) for r in overdue],
            }
        if topic == "schedule":
            rows = await conn.fetch(
                """
                SELECT s.id, s.role, s.starts_at, s.ends_at, s.required_staff,
                       COUNT(a.id) AS assigned_count
                FROM schedule_shifts s
                LEFT JOIN schedule_shift_assignments a ON a.shift_id = s.id AND a.status != 'declined'
                WHERE s.company_id = $1 AND s.status = 'published'
                  AND s.starts_at > NOW() AND s.starts_at < NOW() + INTERVAL '7 days'
                GROUP BY s.id ORDER BY s.starts_at LIMIT 20
                """,
                company_id,
            )
            return {"topic": "schedule", "upcoming_shifts": [dict(r) for r in rows]}
        if topic == "incidents":
            # Detail, but never named individuals or the free-text narrative
            # — no involved_employee_ids, witnesses, reporter identity, or
            # description (that's exactly where a legal record names people,
            # e.g. "Maria slipped near bay 3"), same rule as hr_pilot_corpus's
            # incident: group. `description` is still searchable server-side
            # below (query filter), it's just never returned to the model.
            # show_record (the side-panel tool) fetches the fuller record
            # separately, gated on the admin's own auth, not the model.
            window_days = _clamp_incident_days(days)
            counts = await conn.fetch(
                """
                SELECT incident_type, severity, COUNT(*) AS count
                FROM ir_incidents
                WHERE company_id = $1 AND occurred_at > NOW() - ($2 || ' days')::interval
                  AND ($3::text IS NULL
                       OR incident_number ILIKE '%' || $3 || '%'
                       OR title ILIKE '%' || $3 || '%'
                       OR description ILIKE '%' || $3 || '%'
                       OR incident_type ILIKE '%' || $3 || '%')
                GROUP BY incident_type, severity
                """,
                company_id, str(window_days), query,
            )
            detail_rows = await conn.fetch(
                """
                SELECT id, incident_number, title, incident_type, severity, status,
                       occurred_at, location
                FROM ir_incidents
                WHERE company_id = $1 AND occurred_at > NOW() - ($2 || ' days')::interval
                  AND ($3::text IS NULL
                       OR incident_number ILIKE '%' || $3 || '%'
                       OR title ILIKE '%' || $3 || '%'
                       OR description ILIKE '%' || $3 || '%'
                       OR incident_type ILIKE '%' || $3 || '%')
                ORDER BY occurred_at DESC LIMIT 21
                """,
                company_id, str(window_days), query,
            )
            truncated = len(detail_rows) > 20
            result: dict[str, Any] = {
                "topic": "incidents",
                "window_days": window_days,
                "counts_by_type_and_severity": [dict(r) for r in counts],
                "incidents": [dict(r) for r in detail_rows[:20]],
            }
            if truncated:
                result["note"] = "More incidents exist in this window than shown — narrow with query or a smaller days window."
            return result
        if topic == "er_cases":
            # Titles/status only — never description or involved_employees,
            # same legal-record rule as the incidents topic. show_record
            # ('er_case', id) is how the admin sees the fuller record, via
            # their own auth in the side panel.
            counts = await conn.fetch(
                "SELECT status, COUNT(*) FROM er_cases WHERE company_id = $1 GROUP BY status",
                company_id,
            )
            rows = await conn.fetch(
                """
                SELECT id, case_number, title, status, category, outcome, created_at
                FROM er_cases
                WHERE company_id = $1
                  AND ($2::text IS NULL OR case_number ILIKE '%' || $2 || '%' OR title ILIKE '%' || $2 || '%')
                ORDER BY created_at DESC LIMIT 20
                """,
                company_id, query,
            )
            return {
                "topic": "er_cases",
                "counts_by_status": {r["status"]: r["count"] for r in counts},
                "cases": [dict(r) for r in rows],
            }
        if topic == "events":
            # EMS channel-logged events. Narrative IS included (truncated) —
            # see record_view._model_ems_events_batch's note for why this
            # diverges from the incidents/er_cases no-narrative rule above:
            # this is pre-promotion documentation typed openly in a channel,
            # not yet a legal record. Ids included because promote_ems_event
            # and show_record both take them.
            window = _clamp_incident_days(days)
            counts = await conn.fetch(
                "SELECT status, COUNT(*) FROM ems_events WHERE company_id = $1 GROUP BY status",
                company_id,
            )
            rows = await conn.fetch(
                """
                SELECT ev.id, ev.title, ev.category, ev.severity_hint, ev.status,
                       ev.incident_recommendation, ev.incident_id,
                       LEFT(ev.narrative, 400) AS narrative, ch.name AS channel_name, ev.created_at
                FROM ems_events ev LEFT JOIN channels ch ON ch.id = ev.channel_id
                WHERE ev.company_id = $1 AND ev.created_at >= NOW() - ($2 || ' days')::interval
                  AND ($3::text IS NULL OR ev.title ILIKE '%' || $3 || '%' OR ev.narrative ILIKE '%' || $3 || '%')
                ORDER BY ev.created_at DESC LIMIT 20
                """,
                company_id, str(window), query,
            )
            return {
                "topic": "events",
                "window_days": window,
                "counts_by_status": {r["status"]: r["count"] for r in counts},
                "events": [dict(r) for r in rows],
                "note": "Promote one with promote_ems_event(event_id=...); open detail with show_record('ems_event', ...).",
            }
        if topic == "pto_leave":
            pto_rows = await conn.fetch(
                """
                SELECT e.first_name, e.last_name, pr.request_type, pr.start_date, pr.end_date
                FROM pto_requests pr JOIN employees e ON e.id = pr.employee_id
                WHERE e.org_id = $1 AND pr.status = 'approved' AND pr.end_date >= CURRENT_DATE
                ORDER BY pr.start_date LIMIT 10
                """,
                company_id,
            )
            leave_rows = await conn.fetch(
                """
                SELECT e.first_name, e.last_name, lr.leave_type, lr.start_date, lr.expected_return_date
                FROM leave_requests lr JOIN employees e ON e.id = lr.employee_id
                WHERE lr.org_id = $1 AND lr.status = ANY($2::text[])
                  AND (lr.actual_return_date IS NULL) AND (lr.expected_return_date IS NULL OR lr.expected_return_date >= CURRENT_DATE)
                ORDER BY lr.start_date LIMIT 10
                """,
                company_id, list(_OPEN_LEAVE_STATUSES),
            )
            # Pending requests carry their id because `decide_pto_request`
            # takes one — an approve/deny is unreachable without this.
            # `pto_requests` has no org_id of its own; tenant scope comes
            # through the employees join (same trap discipline_compliance
            # documents).
            pending_rows = await conn.fetch(
                """
                SELECT pr.id, e.first_name, e.last_name, pr.request_type,
                       pr.start_date, pr.end_date, pr.hours, pr.reason
                FROM pto_requests pr JOIN employees e ON e.id = pr.employee_id
                WHERE e.org_id = $1 AND pr.status = 'pending'
                ORDER BY pr.start_date LIMIT 10
                """,
                company_id,
            )
            return {
                "topic": "pto_leave",
                "upcoming_pto": [dict(r) for r in pto_rows],
                "active_leave": [dict(r) for r in leave_rows],
                "pending_requests": [dict(r) for r in pending_rows],
            }
        if topic == "documents":
            # Counts + document titles only, never employee names — same rule
            # as the incidents/discipline topics. "Stale" mirrors the
            # hr_proactive_push sweep's own threshold so chat and the
            # proactive digest can't disagree about what's overdue.
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS pending_total,
                       COUNT(*) FILTER (
                           WHERE ed.created_at < NOW() - ($2 || ' days')::interval
                       ) AS stale_total,
                       MIN(ed.created_at) AS oldest_pending_at
                FROM employee_documents ed
                JOIN employees e ON e.id = ed.employee_id
                WHERE ed.org_id = $1 AND ed.status = 'pending_signature'
                  AND e.termination_date IS NULL
                """,
                company_id, str(_SIGNATURE_STALE_DAYS),
            )
            by_document = await conn.fetch(
                """
                SELECT ed.title, COUNT(*) AS pending_count
                FROM employee_documents ed
                JOIN employees e ON e.id = ed.employee_id
                WHERE ed.org_id = $1 AND ed.status = 'pending_signature'
                  AND e.termination_date IS NULL
                GROUP BY ed.title
                ORDER BY COUNT(*) DESC, ed.title LIMIT 10
                """,
                company_id,
            )
            return {
                "topic": "documents",
                "pending_total": (row["pending_total"] if row else 0) or 0,
                "stale_total": (row["stale_total"] if row else 0) or 0,
                "stale_after_days": _SIGNATURE_STALE_DAYS,
                "oldest_pending_at": row["oldest_pending_at"] if row else None,
                "by_document": [dict(r) for r in by_document],
            }
        if topic == "policies":
            rows = await conn.fetch(
                """
                SELECT title, category FROM policies
                WHERE company_id = $1 AND status = 'active'
                  AND ($2::text IS NULL OR title ILIKE '%' || $2 || '%')
                ORDER BY title LIMIT 20
                """,
                company_id, query,
            )
            return {"topic": "policies", "active_policies": [dict(r) for r in rows]}
        if topic == "discipline":
            # Counts + review dates only — never description/outcome_notes,
            # same rule as the incidents topic: this grounds a status
            # question, it never surfaces a legal narrative.
            counts = await conn.fetch(
                "SELECT status, COUNT(*) FROM progressive_discipline WHERE company_id = $1 GROUP BY status",
                company_id,
            )
            upcoming_reviews = await conn.fetch(
                """
                SELECT discipline_type, review_date FROM progressive_discipline
                WHERE company_id = $1 AND status = 'active' AND review_date IS NOT NULL
                  AND review_date >= CURRENT_DATE
                ORDER BY review_date LIMIT 10
                """,
                company_id,
            )
            # Pending-approval records carry ids — decide_disciplinary_action
            # takes an id, never a name, so this is the lookup that feeds it.
            pending_approval = await conn.fetch(
                """
                SELECT id, discipline_type, infraction_type, approval_requested_at
                FROM progressive_discipline
                WHERE company_id = $1 AND approval_status = 'pending'
                ORDER BY approval_requested_at ASC LIMIT 20
                """,
                company_id,
            )
            return {
                "topic": "discipline",
                "counts_by_status": {r["status"]: r["count"] for r in counts},
                "upcoming_reviews": [dict(r) for r in upcoming_reviews],
                "pending_approval": [
                    {
                        "record_id": str(r["id"]),
                        "discipline_type": r["discipline_type"],
                        "infraction_type": r["infraction_type"],
                        "approval_requested_at": (
                            r["approval_requested_at"].isoformat() if r["approval_requested_at"] else None
                        ),
                    }
                    for r in pending_approval
                ],
            }
        if topic == "compliance":
            rows = await conn.fetch(
                """
                SELECT ca.category, COUNT(*) AS count
                FROM compliance_alerts ca
                WHERE ca.company_id = $1 AND ca.status = ANY($2::text[])
                GROUP BY ca.category
                ORDER BY count DESC
                """,
                company_id, list(_OPEN_ALERT_STATUSES),
            )
            # Named "alerts", not "requirements": these are the open compliance
            # ALERTS raised against this company's locations, which is what a
            # "what's outstanding?" question actually means here — the
            # jurisdiction requirement catalog itself is a different corpus.
            return {"topic": "compliance", "open_alerts_by_category": [dict(r) for r in rows]}
        if topic == "offers":
            rows = await conn.fetch(
                "SELECT id, candidate_name, candidate_email, position_title, status, created_at "
                "FROM offer_letters WHERE company_id = $1 AND ($2::text IS NULL OR candidate_email ILIKE $2) "
                "ORDER BY created_at DESC LIMIT 10",
                company_id, f"%{query}%" if query else None,
            )
            return {"topic": "offers", "matches": [dict(r) for r in rows]}
        return {"topic": topic, "error": "unknown topic"}
    except Exception:
        logger.exception("huume lookup_context failed topic=%s company=%s", topic, company_id)
        return {"topic": topic, "error": "lookup failed"}


async def draft_offer_letter(
    *, company_id: UUID, thread_id: UUID, offer_id: Optional[str] = None, **fields: Any,
) -> dict[str, Any]:
    """Create or update a `status='draft'` offer letter and link the
    thread to it via `mw_threads.linked_offer_letter_id` (the same column
    the classic offer_letter skill uses). Never sends anything — that's the
    separate staged `send_offer` action. Agent-facing tool wrapper — opens
    its own connection."""
    from app.database import get_connection
    async with get_connection() as conn:
        return await _draft_offer_letter_impl(conn, company_id=company_id, thread_id=thread_id, offer_id=offer_id, **fields)


async def _draft_offer_letter_impl(
    conn, *, company_id: UUID, thread_id: UUID, offer_id: Optional[str] = None, **fields: Any,
) -> dict[str, Any]:
    company_name = await conn.fetchval("SELECT name FROM companies WHERE id = $1", company_id)

    start_date = None
    if fields.get("start_date"):
        try:
            start_date = date.fromisoformat(str(fields["start_date"])[:10])
        except ValueError:
            pass

    if offer_id:
        row = await conn.fetchrow(
            """
            UPDATE offer_letters
            SET candidate_name = COALESCE($1, candidate_name),
                candidate_email = COALESCE($2, candidate_email),
                position_title = COALESCE($3, position_title),
                salary = COALESCE($4, salary),
                start_date = COALESCE($5, start_date),
                employment_type = COALESCE($6, employment_type),
                location = COALESCE($7, location),
                updated_at = NOW()
            WHERE id = $8 AND company_id = $9 AND status = 'draft'
            RETURNING *
            """,
            fields.get("candidate_name"), fields.get("candidate_email"),
            fields.get("position_title"), fields.get("salary"), start_date,
            fields.get("employment_type"), fields.get("location"),
            offer_id, company_id,
        )
        if not row:
            return {"status": "error", "message": "That offer isn't a draft (or doesn't exist), so it can't be edited here."}
    else:
        candidate_name = str(fields.get("candidate_name") or "").strip()
        position_title = str(fields.get("position_title") or "").strip()
        if not candidate_name or not position_title:
            return {"status": "error", "message": "Need at least a candidate name and position title to draft an offer."}
        row = await conn.fetchrow(
            """
            INSERT INTO offer_letters (
                candidate_name, position_title, company_name, company_id,
                salary, start_date, employment_type, location, candidate_email, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft')
            RETURNING *
            """,
            candidate_name, position_title, company_name, company_id,
            fields.get("salary"), start_date,
            fields.get("employment_type") or "Full-Time Exempt",
            fields.get("location") or "Remote",
            fields.get("candidate_email"),
        )
        await conn.execute(
            "UPDATE mw_threads SET linked_offer_letter_id = $1, updated_at = NOW() WHERE id = $2",
            row["id"], thread_id,
        )

    # Whitelisted view, not the whole row — the row also carries company_id,
    # candidate_token/expiry (NULL pre-send), and other internals the model
    # has no use for and shouldn't be re-echoing as context.
    _OFFER_FIELDS = (
        "candidate_name", "candidate_email", "position_title", "salary",
        "start_date", "employment_type", "location", "status",
    )
    offer_out = dict(row)
    return {
        "status": "ok",
        "offer_id": str(row["id"]),
        "offer": {k: offer_out.get(k) for k in _OFFER_FIELDS},
    }


async def check_offer_status(*, company_id: UUID, offer_id: str) -> dict[str, Any]:
    from app.database import get_connection
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT status, signed_name, signed_at, declined_at, candidate_email FROM offer_letters WHERE id = $1 AND company_id = $2",
            offer_id, company_id,
        )
    if not row:
        return {"status": "error", "message": "Offer not found."}
    return dict(row)


async def execute_send_offer(*, company_id: UUID, actor_user_id: Optional[UUID], offer_id: str) -> dict[str, Any]:
    """Send the candidate their sign link. Mirrors send_range_offer's token
    minting (offer_letters.py) but for the fixed-terms sign flow."""
    from app.database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM offer_letters WHERE id = $1 AND company_id = $2",
            offer_id, company_id,
        )
        if not row:
            return {"status": "error", "message": "Offer not found."}
        offer = dict(row)
        if offer["status"] != "draft":
            return {"status": "error", "message": f"Offer is already {offer['status']} — can't re-send from here."}
        if not offer.get("candidate_email"):
            return {"status": "error", "message": "This offer has no candidate email set — add one before sending."}

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        updated = await conn.fetchrow(
            """
            UPDATE offer_letters
            SET candidate_token = $1, candidate_token_expires_at = $2, status = 'sent', updated_at = NOW()
            WHERE id = $3
            RETURNING *
            """,
            token, expires_at, offer_id,
        )

    try:
        from app.config import get_settings
        from app.core.services.email import EmailService
        settings = get_settings()
        email_svc = EmailService()
        if email_svc.is_configured():
            frontend_url = getattr(settings, "app_base_url", "http://localhost:5174")
            offer_url = f"{frontend_url}/offer/{token}"
            subject = f"Offer of Employment — {updated['position_title']} at {updated['company_name']}"
            html_body = f"""
<html><body style="font-family: sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
<h2 style="color: #16a34a;">You have an offer from {updated['company_name']}</h2>
<p>You've been offered the position of <strong>{updated['position_title']}</strong> at <strong>{updated['company_name']}</strong>.</p>
<p style="margin: 24px 0;">
  <a href="{offer_url}" style="background: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
    View &amp; Sign Your Offer
  </a>
</p>
<p style="color: #666; font-size: 0.9em;">This link expires in 7 days.</p>
</body></html>"""
            await email_svc.send_email(to_email=updated["candidate_email"], to_name=None, subject=subject, html_content=html_body)
    except Exception:
        logger.exception("[Huume] failed to send offer email for %s", offer_id)

    return {
        "status": "created", "record_id": str(updated["id"]),
        "message": f"Sent the offer to {updated['candidate_email']}. I'll let you know here as soon as they respond.",
    }


# ---------------------------------------------------------------------------
# DB-bound: build_onboarding_plan tool wrapper + plan step executors
# ---------------------------------------------------------------------------

async def build_plan_for_offer(*, company_id: UUID, offer_id: str) -> dict[str, Any]:
    from app.database import get_connection
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM offer_letters WHERE id = $1 AND company_id = $2", offer_id, company_id,
        )
        if not row:
            return {"status": "error", "message": "Offer not found."}
        offer = dict(row)
        if offer["status"] != "accepted":
            return {"status": "error", "message": f"This offer is {offer['status']}, not accepted — the plan can only be built after acceptance."}

        from app.core.feature_flags import get_company_features
        features = await get_company_features(company_id, conn=conn)

        integ_rows = await conn.fetch("SELECT provider FROM integration_connections WHERE company_id = $1", company_id)
        integrations = {r["provider"]: True for r in integ_rows}

    plan = build_onboarding_plan(offer=offer, features=features, integrations=integrations)
    return {"status": "ok", "plan": plan}


async def execute_plan_step(
    *, key: str, company_id: UUID, actor_user_id: Optional[UUID], plan: dict[str, Any], employee_id: Optional[str],
) -> dict[str, Any]:
    from app.database import get_connection

    handler = _STEP_HANDLERS.get(key)
    if handler is None:
        return {"status": "failed", "message": f"Unknown step '{key}'."}
    async with get_connection() as conn:
        return await handler(conn, company_id=company_id, actor_user_id=actor_user_id, plan=plan, employee_id=employee_id)


async def _step_create_employee(conn, *, company_id, actor_user_id, plan, employee_id, **_) -> dict[str, Any]:
    from app.matcha.routes.employees._shared import (
        _employee_compensation_fields_available, _employee_org_fields_available,
        _sync_employee_location_for_compliance, _normalize_work_state,
    )

    emp = plan.get("employee") or {}
    email = (emp.get("email") or "").strip().lower()
    if not email:
        return {"status": "failed", "message": "No candidate email on file — can't create the employee record."}

    existing = await conn.fetchval("SELECT id FROM employees WHERE org_id = $1 AND email = $2", company_id, email)
    if existing:
        return {"status": "created", "record_id": str(existing), "message": "An employee with this email already existed — linked instead of duplicating."}

    start_date = None
    if emp.get("start_date"):
        try:
            start_date = date.fromisoformat(str(emp["start_date"])[:10])
        except ValueError:
            pass

    work_state = None
    location = (emp.get("location") or "").strip()
    if len(location) == 2:
        normalized, valid = _normalize_work_state(location)
        work_state = normalized if valid else None

    comp_available = await _employee_compensation_fields_available(conn)
    org_available = await _employee_org_fields_available(conn)

    cols = ["org_id", "email", "first_name", "last_name", "work_state", "employment_type", "start_date"]
    vals = [company_id, email, emp.get("first_name") or "New", emp.get("last_name") or "Hire",
            work_state, emp.get("employment_type") or "Full-Time Exempt", start_date]
    if org_available and emp.get("position_title"):
        cols.append("job_title")
        vals.append(emp["position_title"])
    placeholders = ", ".join(f"${i}" for i in range(1, len(vals) + 1))
    row = await conn.fetchrow(
        f"INSERT INTO employees ({', '.join(cols)}) VALUES ({placeholders}) RETURNING id",
        *vals,
    )
    new_id = row["id"]

    try:
        await _sync_employee_location_for_compliance(
            conn, company_id=company_id, employee_id=new_id, work_state=work_state,
            work_city=None, background_tasks=None,
        )
    except Exception:
        logger.warning("huume create_employee: location sync failed for %s", new_id, exc_info=True)

    offer_id = plan.get("offer_id")
    if offer_id:
        await conn.execute("UPDATE offer_letters SET employee_id = $1 WHERE id = $2", new_id, offer_id)

    return {"status": "created", "record_id": str(new_id), "message": f"Created the employee record for {emp.get('first_name') or 'the new hire'}."}


async def _step_portal_invitation(conn, *, company_id, actor_user_id, employee_id, **_) -> dict[str, Any]:
    try:
        result = await _send_invitation_with_conn(
            UUID(employee_id), company_id, actor_user_id, conn, raise_on_email_failure=False,
        )
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        return {"status": "skipped", "message": f"Invitation not sent: {detail}"}
    return {"status": "created", "record_id": str(result.get("invitation_id") or employee_id), "message": "Sent the employee portal invitation."}


async def _step_onboarding_tasks(conn, *, company_id, employee_id, **_) -> dict[str, Any]:
    template_rows = await conn.fetch(
        "SELECT id, title, description, category, is_employee_task, due_days, "
        "link_type, link_id, link_label, link_url "
        "FROM onboarding_tasks WHERE org_id = $1 AND is_active = TRUE ORDER BY sort_order",
        company_id,
    )
    if not template_rows:
        return {"status": "skipped", "message": "No active onboarding task templates to assign."}

    created = 0
    for tmpl in template_rows:
        exists = await conn.fetchval(
            "SELECT 1 FROM employee_onboarding_tasks WHERE employee_id = $1 AND task_id = $2",
            employee_id, tmpl["id"],
        )
        if exists:
            continue
        due = date.today() + timedelta(days=tmpl["due_days"] or 0)
        await conn.execute(
            "INSERT INTO employee_onboarding_tasks "
            "(id, employee_id, task_id, title, description, category, is_employee_task, due_date, status, "
            "link_type, link_id, link_label, link_url) "
            "VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, 'pending', $8, $9, $10, $11)",
            employee_id, tmpl["id"], tmpl["title"], tmpl["description"], tmpl["category"],
            tmpl["is_employee_task"], due, tmpl["link_type"], tmpl["link_id"], tmpl["link_label"], tmpl["link_url"],
        )
        created += 1
    return {"status": "created", "record_id": employee_id, "message": f"Assigned {created} onboarding task(s)."}


async def _step_credential_requirements(conn, *, company_id, employee_id, **_) -> dict[str, Any]:
    from app.core.services.credential_template_service import (
        resolve_credential_requirements, assign_credential_requirements_to_employee,
    )
    emp = await conn.fetchrow("SELECT work_state, job_title, start_date FROM employees WHERE id = $1", employee_id)
    if not emp or not emp["job_title"]:
        return {"status": "skipped", "message": "No job title on file — can't resolve credential requirements."}
    reqs = await resolve_credential_requirements(conn, company_id, emp["work_state"], None, emp["job_title"])
    if not reqs:
        return {"status": "skipped", "message": "No credential requirements apply to this role."}
    count = await assign_credential_requirements_to_employee(conn, employee_id, company_id, reqs, emp["start_date"])
    return {"status": "created", "record_id": employee_id, "message": f"Assigned {count} credential requirement(s)."}


async def _step_training_assignment(conn, *, company_id, employee_id, **_) -> dict[str, Any]:
    from app.matcha.services.training.training_assignment import evaluate_new_hire_rules
    result = await evaluate_new_hire_rules(conn, company_id, UUID(str(employee_id)))
    if not result.assigned and not result.accelerated:
        return {"status": "skipped", "message": "No new-hire training rules matched this employee."}
    return {"status": "created", "record_id": employee_id, "message": f"Assigned {result.assigned} training program(s)."}


async def _step_google_workspace(conn, *, company_id, actor_user_id, employee_id, **_) -> dict[str, Any]:
    from app.matcha.services.onboarding.onboarding_orchestrator import start_google_workspace_onboarding
    payload = await start_google_workspace_onboarding(
        company_id=company_id, employee_id=UUID(str(employee_id)),
        triggered_by=actor_user_id, trigger_source="huume",
    )
    if payload.get("status") == "completed":
        return {"status": "created", "record_id": payload.get("run_id"), "message": "Provisioned the Google Workspace account."}
    return {"status": "skipped", "message": payload.get("last_error") or "Google Workspace provisioning didn't complete."}


async def _step_slack(conn, *, company_id, actor_user_id, employee_id, **_) -> dict[str, Any]:
    from app.matcha.services.onboarding.onboarding_orchestrator import start_slack_onboarding
    payload = await start_slack_onboarding(
        company_id=company_id, employee_id=UUID(str(employee_id)),
        triggered_by=actor_user_id, trigger_source="huume",
    )
    if payload.get("status") == "completed":
        return {"status": "created", "record_id": payload.get("run_id"), "message": "Provisioned the Slack account."}
    return {"status": "skipped", "message": payload.get("last_error") or "Slack provisioning didn't complete."}


async def _step_schedule_note(conn, *, company_id, employee_id, **_) -> dict[str, Any]:
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM schedule_shifts WHERE company_id = $1 AND status = 'published' AND starts_at > NOW() AND starts_at < NOW() + INTERVAL '14 days'",
        company_id,
    )
    return {"status": "created", "record_id": employee_id, "message": f"{count or 0} shift(s) are published in the next two weeks at this company — assign this hire from Scheduling when ready."}


async def _step_benefits_note(conn, *, company_id, employee_id, **_) -> dict[str, Any]:
    return {"status": "created", "record_id": employee_id, "message": "New hire is eligible for the company's benefits enrollment window — review eligibility from Benefits."}


async def _step_jurisdiction_packet_note(conn, *, company_id, employee_id, **_) -> dict[str, Any]:
    from app.matcha.services.onboarding.new_hire_packet import build_packet
    packet = await build_packet(conn, company_id, UUID(str(employee_id)))
    count = packet.get("count") or 0
    if not count:
        return {"status": "skipped", "message": "No jurisdiction-specific new-hire notices found for this employee's work state."}
    return {"status": "created", "record_id": employee_id, "message": f"{count} new-hire notice(s) apply for {packet.get('state')} — see the jurisdiction packet on the employee record."}


_STEP_HANDLERS = {
    "create_employee": _step_create_employee,
    "portal_invitation": _step_portal_invitation,
    "onboarding_tasks": _step_onboarding_tasks,
    "credential_requirements": _step_credential_requirements,
    "training_assignment": _step_training_assignment,
    "google_workspace": _step_google_workspace,
    "slack": _step_slack,
    "schedule_note": _step_schedule_note,
    "benefits_note": _step_benefits_note,
    "jurisdiction_packet_note": _step_jurisdiction_packet_note,
}
