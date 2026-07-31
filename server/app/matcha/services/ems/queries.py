"""Shared EMS event SELECT.

Lifted out of routes/ems.py (2026-07-31) so services/huume/ems_skill.py can
load a promote-ready event row without a services -> routes import — same
lift pattern as services/er/er_case_context.py. routes/ems.py re-imports
these under their old local names, so its route bodies and their tests are
unchanged.

Neither `channel_name` nor `reporter_name` is a column on ems_events —
both are resolved here via the joins below. Loading an event any other
way and handing it to promote.promote_event files the incident with
`#unknown channel` / `reported_by_name="Unknown"`.
"""

_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"

EVENT_SELECT = f"""
    SELECT ev.id, ev.company_id, ev.channel_id, ch.name AS channel_name,
           ev.message_id, ev.reporter_user_id, {_NAME_EXPR} AS reporter_name,
           ev.title, ev.category, ev.severity_hint, ev.doc, ev.narrative,
           ev.incident_recommendation, ev.incident_reasoning,
           ev.suggested_incident_type, ev.suggested_severity,
           ev.status, ev.incident_id,
           (ev.clarify_message_id IS NOT NULL AND ev.status = 'logged') AS awaiting_reply,
           ev.clarification_rounds,
           ev.created_at, ev.updated_at
    FROM ems_events ev
    LEFT JOIN channels ch ON ch.id = ev.channel_id
    LEFT JOIN users u ON u.id = ev.reporter_user_id
    LEFT JOIN clients c ON c.user_id = u.id
    LEFT JOIN employees e ON e.user_id = u.id
    LEFT JOIN admins a ON a.user_id = u.id
"""
