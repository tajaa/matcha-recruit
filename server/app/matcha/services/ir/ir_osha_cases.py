"""Per-injured-employee OSHA case records (ir_osha_case_details) + the
OSHA emergency-alert persistence.

Moved from routes/ir_incidents/_shared.py (refactor round 2, stage 3).

One row per injured employee on a recordable incident: each person's own OSHA
case (classification, days away/restricted, M-column injury type) + Privacy
Case answer. case_key = str(employee_id) for a roster employee, else
'reporter'. These rows are the authoritative source for the 300/301/300A
reads; the incident-level columns remain a fallback for un-captured rows.
"""
import json
from datetime import datetime, timezone

from app.core.services.osha_privacy import determine_privacy_case

from .ir_cards import (
    OSHA_EMERGENCY_ALERT_CARD_ID,
    build_osha_days_type_query_card,
    build_osha_emergency_alert_card,
    build_osha_injury_type_query_card,
    build_privacy_case_query_card,
)


async def next_case_step(conn, incident_id):
    """Drive the per-injured-employee OSHA case-capture chain.

    Returns the next card for the first INCOMPLETE ``ir_osha_case_details`` row,
    in ``case_seq`` order: days-type (→ days-count) until ``classification`` is
    set, then injury-type, then the Privacy Case prompt. Returns ``None`` when
    every case is fully captured (chain complete). Called after recordable=yes
    and after each capture step. Each card carries ``case_key`` so the handler
    writes the right case row.
    """
    # Lazy: these stay in routes/ir_incidents/_shared.py (used widely by
    # other route submodules too) — a module-level import here would pull
    # services back into routes.
    from app.matcha.routes.ir_incidents._shared import _hydrate_involved_employees, _safe_json_loads

    case_rows = await conn.fetch(
        "SELECT * FROM ir_osha_case_details WHERE incident_id = $1 ORDER BY case_seq, case_key",
        incident_id,
    )
    if not case_rows:
        return None
    inc = await conn.fetchrow(
        "SELECT company_id, category_data, osha_form_301_data, reported_by_name "
        "FROM ir_incidents WHERE id = $1",
        incident_id,
    )
    cd = (_safe_json_loads(inc["category_data"], {}) if inc else {}) or {}
    form_301 = (_safe_json_loads(inc["osha_form_301_data"], {}) if inc else {}) or {}
    _is_priv, suggested = determine_privacy_case(
        cd, form_301.get("injury_type"), bool(cd.get("employee_privacy_requested")),
    )
    emp_ids = [str(r["employee_id"]) for r in case_rows if r["employee_id"]]
    by_id = {}
    if emp_ids and inc:
        hydrated = await _hydrate_involved_employees(conn, inc["company_id"], emp_ids)
        by_id = {str(e["id"]): e for e in hydrated}

    def _name(cr):
        if cr["case_key"] == "reporter":
            return (inc["reported_by_name"] if inc else None) or "this employee"
        emp = by_id.get(cr["case_key"])
        if emp:
            return f"{emp.get('first_name') or ''} {emp.get('last_name') or ''}".strip() or "this employee"
        return "this employee"

    for cr in case_rows:
        name = _name(cr)
        if cr["classification"] is None:
            return build_osha_days_type_query_card(case_key=cr["case_key"], employee_name=name)
        if cr["injury_type"] is None:
            return build_osha_injury_type_query_card(case_key=cr["case_key"], employee_name=name)
        if cr["privacy_case_reason"] is None:
            return build_privacy_case_query_card(
                employee_key=cr["case_key"], employee_name=name, suggested_reason=suggested,
            )
    return None


async def ensure_osha_case_rows(conn, incident_id) -> None:
    """Create one ir_osha_case_details row per injured employee for a recordable
    incident — roster employees from ``involved_employee_ids`` (in order), else a
    single ``'reporter'`` row. Seeds from the incident-level values + any prior
    ``category_data.privacy_cases`` answer. Idempotent (``ON CONFLICT DO
    NOTHING``) — safe to call whenever recordability is set, by any path.

    Mirrors the migration backfill, scoped to one incident.
    """
    await conn.execute(
        """
        INSERT INTO ir_osha_case_details
            (incident_id, case_key, employee_id, case_seq,
             classification, days_away, days_restricted, injury_type, privacy_case_reason)
        SELECT i.id, emp.eid::text, emp.eid, emp.ord::int,
               i.osha_classification, COALESCE(i.days_away_from_work, 0),
               COALESCE(i.days_restricted_duty, 0), i.osha_form_301_data->>'injury_type',
               NULLIF(i.category_data->'privacy_cases'->>(emp.eid::text), '')
        FROM ir_incidents i
        CROSS JOIN LATERAL unnest(i.involved_employee_ids) WITH ORDINALITY AS emp(eid, ord)
        WHERE i.id = $1 AND i.osha_recordable = true
          AND array_length(i.involved_employee_ids, 1) > 0
        ON CONFLICT (incident_id, case_key) DO NOTHING
        """,
        incident_id,
    )
    await conn.execute(
        """
        INSERT INTO ir_osha_case_details
            (incident_id, case_key, employee_id, case_seq,
             classification, days_away, days_restricted, injury_type, privacy_case_reason)
        SELECT i.id, 'reporter', NULL, 1,
               i.osha_classification, COALESCE(i.days_away_from_work, 0),
               COALESCE(i.days_restricted_duty, 0), i.osha_form_301_data->>'injury_type',
               NULLIF(i.category_data->'privacy_cases'->>'reporter', '')
        FROM ir_incidents i
        WHERE i.id = $1 AND i.osha_recordable = true
          AND array_length(i.involved_employee_ids, 1) IS NULL
        ON CONFLICT (incident_id, case_key) DO NOTHING
        """,
        incident_id,
    )


async def fetch_osha_case_rows(conn, incident_id) -> list[dict]:
    """All case rows for one incident, ordered by case_seq."""
    rows = await conn.fetch(
        "SELECT * FROM ir_osha_case_details WHERE incident_id = $1 ORDER BY case_seq, case_key",
        incident_id,
    )
    return [dict(r) for r in rows]


async def fetch_osha_case_rows_for(conn, incident_ids) -> dict:
    """Batch: ``{str(incident_id): [case rows]}`` for the 300-log (avoids N+1)."""
    if not incident_ids:
        return {}
    rows = await conn.fetch(
        "SELECT * FROM ir_osha_case_details WHERE incident_id = ANY($1::uuid[]) "
        "ORDER BY case_seq, case_key",
        [str(i) for i in incident_ids],
    )
    out: dict = {}
    for r in rows:
        out.setdefault(str(r["incident_id"]), []).append(dict(r))
    return out


async def _persist_osha_emergency_alert(conn, incident_id: str, current_user) -> None:
    """Flip severity to critical, mark the alert active in category_data,
    and persist the emergency card to the Copilot transcript.

    Idempotent: a second call on the same incident skips re-persisting the
    card if one already exists (e.g. background classifier re-triggered).
    """
    await conn.execute(
        """
        UPDATE ir_incidents
        SET severity = 'critical',
            category_data = jsonb_set(
                COALESCE(category_data, '{}'::jsonb),
                '{osha_emergency_alert_active}',
                'true'::jsonb,
                true
            )
        WHERE id = $1
        """,
        incident_id,
    )

    existing = await conn.fetchval(
        """
        SELECT 1 FROM ir_incident_ai_messages
        WHERE incident_id = $1
          AND message_type = 'card'
          AND metadata->'card'->>'id' = $2
        LIMIT 1
        """,
        incident_id,
        OSHA_EMERGENCY_ALERT_CARD_ID,
    )
    if existing:
        return

    # Inline assistant directive — must precede the card insert so
    # _extract_current_cards in copilot.py treats the alert as part of
    # the current round (it walks messages and only includes assistant
    # cards after the most recent assistant text marker). Without this
    # text the panel sees a transcript with no active round and renders
    # the alert card with no guidance copy above it — looks inert.
    user_id_str = (
        str(current_user.id) if current_user and getattr(current_user, "id", None) else None
    )
    directive_text = (
        "Severity flipped to critical because the report describes a "
        "potential OSHA reportable event (29 CFR 1904.39). Acknowledge "
        "the alert below with your reporting notes, then we'll capture "
        "the OSHA recordable details for the 300 log."
    )
    directive_metadata = {
        "open_questions": [],
        "model": "osha_emergency_inline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await conn.execute(
        """
        INSERT INTO ir_incident_ai_messages
          (incident_id, role, message_type, content, metadata, created_by)
        VALUES ($1, 'assistant', 'text', $2, $3::jsonb, $4)
        """,
        incident_id,
        directive_text,
        json.dumps(directive_metadata),
        user_id_str,
    )

    card = build_osha_emergency_alert_card()
    metadata = {"card": card, "accepted": False}
    await conn.execute(
        """
        INSERT INTO ir_incident_ai_messages
          (incident_id, role, message_type, content, metadata, created_by)
        VALUES ($1, 'assistant', 'card', $2, $3::jsonb, $4)
        """,
        incident_id,
        card["title"],
        json.dumps(metadata),
        user_id_str,
    )
