"""IR incident creation — the shared INSERT + post-insert mechanics.

Moved from routes/ir_incidents/_shared.py (refactor round 2, stage 3).
"""
import json
import logging
from typing import Optional

from .ir_notifications import send_ir_notifications_task
from .ir_osha_cases import _persist_osha_emergency_alert
from .ir_people_index import _gather_incident_people, _sync_incident_people

logger = logging.getLogger(__name__)


async def create_incident_core(
    conn,
    *,
    company_id: Optional[str],
    description: Optional[str],
    occurred_at,
    reported_by_name: str,
    title: Optional[str] = None,
    incident_type: Optional[str] = None,
    severity: Optional[str] = None,
    location: Optional[str] = None,
    location_id: Optional[str] = None,
    reported_by_email: Optional[str] = None,
    witnesses: Optional[list] = None,
    category_data: Optional[dict] = None,
    involved_employee_ids: Optional[list[str]] = None,
    corrective_actions: Optional[str] = None,
    created_by: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    actor_ip: Optional[str] = None,
    current_user=None,
    index_people: bool = True,
) -> tuple[dict, list]:
    """Insert an incident + run the shared post-insert mechanics.

    Shared by the authenticated create route (`crud.create_incident`), the
    public location magic-link intake (`inbound_email.submit_location_report`),
    and the truly-anonymous `/report` intake (`inbound_email.submit_anonymous_report`)
    so every path produces an incident of the same quality: real `location_id`
    (where applicable), witnesses, the per-person identity index, OSHA
    emergency detection, and the same AI auto-classify + policy-map +
    notification background jobs.

    ``index_people=False`` skips the per-person identity index — required for
    the anonymous `/report` intake, which per design must NOT mint `ir_people`
    rows (there's no reporter name or roster to attach them to; see
    `ir_incidents/CLAUDE.md`). In practice the anonymous form's "Anonymous"
    reporter name and lack of an `involved_parties` category key already make
    `_gather_incident_people` a no-op there, but the explicit flag makes that
    guaranteed rather than incidental, so it can't silently start indexing
    people if either of those inputs changes later.

    The CALLER owns the connection and its tenant scoping — the authed path uses
    `get_connection()`; the public token path uses
    `get_connection(tenant_id=company_id)` so the INSERT clears RLS — as well as
    transaction boundaries. This function never opens its own connection.

    Returns `(response_row, bg_tasks)` where `response_row` is a dict augmented
    with company/location names (ready for `row_to_response`) and `bg_tasks` is a
    list of `(fn, args, kwargs)` tuples the caller schedules on its own
    `BackgroundTasks` (or awaits). Deferring them lets the caller commit the
    transaction first and keeps this function connection-agnostic.
    """
    # Lazy: these stay in routes/ir_incidents/_shared.py (used widely by
    # other route submodules too) — a module-level import here would pull
    # services back into routes.
    from app.matcha.routes.ir_incidents._shared import (
        _auto_classify_incident_task,
        _detect_osha_reportable_keywords,
        _parse_occurred_at,
        generate_incident_number,
        log_audit,
    )

    witnesses = witnesses or []
    incident_number = generate_incident_number()
    occurred_at_dt = _parse_occurred_at(occurred_at)

    # Track whether the caller explicitly set type/severity so the background
    # classifier knows whether to override the system defaults.
    user_passed_type = incident_type is not None
    user_passed_severity = severity is not None and severity != "medium"
    effective_type = incident_type or "other"
    effective_severity = severity or "medium"

    # Title derives from the description's first line when not supplied (the
    # slim + public forms drop the Title field entirely).
    raw_title = (title or "").strip()
    if not raw_title:
        body = (description or "Incident").strip()
        first_line = body.splitlines()[0] if body else "Incident"
        raw_title = first_line[:80].strip() or "Incident"
    effective_title = raw_title

    row = await conn.fetchrow(
        """
        INSERT INTO ir_incidents (
            incident_number, title, description, incident_type, severity,
            occurred_at, location, reported_by_name, reported_by_email,
            witnesses, category_data, involved_employee_ids,
            company_id, location_id, created_by, corrective_actions
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        RETURNING *
        """,
        incident_number,
        effective_title,
        description,
        effective_type,
        effective_severity,
        occurred_at_dt,
        location,
        reported_by_name,
        reported_by_email,
        json.dumps([w.model_dump() if hasattr(w, "model_dump") else w for w in witnesses]),
        json.dumps(category_data or {}),
        involved_employee_ids,
        company_id,
        (str(location_id) if location_id else None),
        created_by,
        (corrective_actions or None),
    )

    # Resolve company / location names for the response payload.
    company_name = None
    location_name = None
    location_city = None
    location_state = None
    if company_id:
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        if company:
            company_name = company["name"]
    if row.get("location_id"):
        loc = await conn.fetchrow(
            "SELECT name, city, state FROM business_locations WHERE id = $1",
            row["location_id"],
        )
        if loc:
            location_name = loc["name"]
            location_city = loc["city"]
            location_state = loc["state"]

    # Audit — only when there's an actor (public intake has no user).
    if actor_user_id:
        await log_audit(
            conn,
            str(row["id"]),
            actor_user_id,
            "incident_created",
            "incident",
            str(row["id"]),
            {"title": effective_title, "type": effective_type},
            actor_ip,
        )

    # Per-person identity index (best-effort; never blocks submit).
    if company_id and index_people:
        try:
            people = _gather_incident_people(
                reported_by_name=row.get("reported_by_name"),
                reported_by_email=row.get("reported_by_email"),
                witnesses=witnesses,
                category_data=category_data,
            )
            await _sync_incident_people(conn, str(company_id), str(row["id"]), people)
        except Exception:
            logger.exception("[IR] people sync failed for incident %s", row.get("id"))

    # OSHA reportable-event (29 CFR 1904.39) emergency detection — flips
    # severity to critical and drops the alert card into the Copilot transcript.
    if _detect_osha_reportable_keywords(f"{effective_title}\n{description or ''}"):
        await _persist_osha_emergency_alert(conn, str(row["id"]), current_user)
        row = await conn.fetchrow("SELECT * FROM ir_incidents WHERE id = $1", row["id"])

    response_row = dict(row)
    response_row["company_name"] = company_name
    response_row["location_name"] = location_name
    response_row["location_city"] = location_city
    response_row["location_state"] = location_state

    # Post-commit background work — assembled here, scheduled by the caller.
    bg_tasks: list = []
    if company_id:
        bg_tasks.append((
            send_ir_notifications_task,
            (),
            dict(
                company_id=str(company_id),
                incident_id=str(row["id"]),
                incident_number=row["incident_number"],
                incident_title=row["title"],
                event_type="created",
                current_status=row["status"],
                changed_by_email=actor_email,
                previous_status=None,
                location_name=location_name or row.get("location"),
                occurred_at=row.get("occurred_at"),
            ),
        ))
        bg_tasks.append((
            _auto_classify_incident_task,
            (str(row["id"]),),
            dict(user_passed_type=user_passed_type, user_passed_severity=user_passed_severity),
        ))
        # Lazy import: ai_analysis imports from _shared, so a module-level import
        # here would be circular (same pattern crud.create_incident used).
        from app.matcha.routes.ir_incidents.ai_analysis import _auto_map_policy_violations
        bg_tasks.append((
            _auto_map_policy_violations,
            (str(row["id"]), str(company_id)),
            {},
        ))

    return response_row, bg_tasks
