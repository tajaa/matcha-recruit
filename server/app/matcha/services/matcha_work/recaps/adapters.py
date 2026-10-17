"""All display snapshots are allowlisted; no raw tool payload reaches media."""
from datetime import datetime, timezone

from app.database import decode_jsonb

from app.matcha.models.matcha_work.recaps import Event, Fact, clip

TOOLS = {
    "read_email": "Read selected email", "search_email": "Searched email",
    "draft_email": "Prepared an email draft", "send_email": "Sent email",
    "reply_email": "Replied to email", "archive_email": "Archived selected email",
    "archive_emails": "Archived selected emails", "label_email": "Labeled selected email",
    "list_events": "Checked calendar", "create_event": "Created calendar event",
    "update_event": "Updated calendar event", "delete_event": "Deleted calendar event",
    "create_calendar_event": "Created calendar event", "update_calendar_event": "Updated calendar event",
    "delete_calendar_event": "Deleted calendar event", "view_page": "Viewed a public page",
    "fetch_page": "Read a public page", "web_search": "Searched the web",
    "start_task": "Started background research", "follow_up_task": "Continued research",
    "create_email_label": "Created an email label",
    "list_espresso_events": "Checked Espresso calendar", "add_espresso_event": "Saved Espresso calendar event",
    "update_espresso_event": "Updated Espresso calendar event", "delete_espresso_event": "Removed Espresso calendar event",
    "list_apple_events": "Checked Apple calendar", "create_apple_event": "Created Apple calendar event",
    "update_apple_event": "Updated Apple calendar event", "delete_apple_event": "Removed Apple calendar event",
    "add_reminder": "Saved a reminder",
}


def step_event(step: dict) -> Event | None:
    tool, status, kind = step["tool"], step["status"], step["kind"]
    if tool not in TOOLS:
        return None
    value = decode_jsonb(step.get("result"), {}) or {}
    title = TOOLS[tool]
    if status in ("claimed", "unknown"):
        outcome = "unknown"
    elif status in ("error", "denied", "skipped"):
        outcome = "failed"
    elif status == "held":
        outcome = "held"
    elif kind == "commit" and value.get("mode") != "live":
        outcome = "dry_run"
    elif tool == "send_email" and value.get("sent") is False:
        outcome = "cancelled"
        title = "Email was not sent"
    elif tool.endswith("_apple_event") and value.get("queued"):
        outcome = "handoff"
    elif kind == "commit":
        outcome = "confirmed"
    elif tool in ("add_espresso_event", "update_espresso_event", "delete_espresso_event", "add_reminder"):
        outcome = "confirmed"
    elif kind == "draft":
        outcome = "drafted"
    else:
        outcome = "observed"
    facts = [Fact(label="Outcome", value=outcome.replace("_", " "))]
    if tool == "send_email" and value.get("sent") is False:
        facts.append(Fact(label="Delivery", value="Nothing was sent"))
    if tool in ("add_espresso_event", "update_espresso_event", "delete_espresso_event", "add_reminder"):
        safe = value.get("recap") if isinstance(value.get("recap"), dict) else {}
        for key, label in (("title", "Event"), ("date", "Due date")):
            if safe.get(key):
                facts.append(Fact(label=label, value=clip(safe[key], 160)))
        if safe.get("start"):
            facts.append(Fact(label="When", value=clip(f"{safe['start']} to {safe.get('end') or ''}", 300)))
        if safe.get("timezone"):
            facts.append(Fact(label="Timezone", value=clip(safe["timezone"], 80)))
        previous = safe.get("previous") if isinstance(safe.get("previous"), dict) else {}
        if previous.get("title") and previous["title"] != safe.get("title"):
            facts.append(Fact(label="Previous title", value=clip(previous["title"], 160)))
        if previous.get("start") and (previous["start"], previous.get("end")) != (safe.get("start"), safe.get("end")):
            facts.append(Fact(label="Previous time", value=clip(f"{previous['start']} to {previous.get('end') or ''}", 300)))
    preview = value.get("preview") if isinstance(value.get("preview"), dict) else {}
    if tool in ("create_event", "update_event", "delete_event"):
        for line in preview.get("lines") or []:
            if isinstance(line, dict) and line.get("label") in ("Event", "When", "New title", "New time"):
                facts.append(Fact(label=line["label"], value=clip(line.get("value"), 300)))
    if tool == "send_email":
        for line in preview.get("lines") or []:
            if isinstance(line, dict) and line.get("label") == "Subject":
                facts.append(Fact(label="Subject", value=clip(line.get("value"), 160)))
    if tool == "read_email" and value.get("subject"):
        facts.append(Fact(label="Selected subject", value=clip(value["subject"], 160)))
    if tool in ("archive_email", "label_email") and isinstance(value.get("weight"), int) and 0 < value["weight"] <= 200:
        facts.append(Fact(label="Selected messages", value=str(value["weight"])))
    # Never use args, unapproved preview fields, result bodies or audit labels.
    return Event(kind="action_resolved", title=title, outcome=outcome,
                 occurred_at=step.get("resolved_at") or step["created_at"],
                 facts=facts[:6])


async def search_event(conn, source, *, terminal=False, phase="") -> Event:
    research = source["kind"] == "research"
    if research:
        row = await conn.fetchrow(
            """SELECT t.*, q.n AS recap_round, q.status AS recap_status, q.completed_at AS recap_completed_at
               FROM mw_agent_task_rounds q JOIN mw_agent_tasks t ON t.id=q.task_id WHERE q.id=$1""",
            source["task_round_id"],
        )
        items = await conn.fetch(
            """SELECT title,subtitle,fields,fit_score,fit_reasons FROM mw_agent_task_items WHERE task_id=$1
               AND rank_band < 9 ORDER BY rank NULLS LAST, id LIMIT 3""", row["id"],
        )
        status = row["status"] if terminal and row["recap_status"] in ("queued", "running") else row["recap_status"] if terminal else row["status"]
        plan = decode_jsonb(row.get("plan"), {}) or {}
        from ..agent_tasks.research.ranking import describe
        constraints = [describe(item) for item in plan.get("constraints") or [] if isinstance(item, dict)]
        criteria = "; ".join(constraints[:4])
    else:
        row = await conn.fetchrow("SELECT * FROM mw_job_searches WHERE id=$1", source["job_search_id"])
        items = await conn.fetch(
            """SELECT title,company,comp,comp_status,comp_currency,fit_score,fit_reasons,approach_status
               FROM mw_job_leads WHERE search_id=$1 AND screen_status <> 'irrelevant'
               ORDER BY rank NULLS LAST, id LIMIT 3""", row["id"],
        )
        status = row["status"]
        wanted = decode_jsonb(row.get("criteria"), {}) or {}
        criteria = "; ".join([", ".join(wanted.get("titles") or []), ", ".join(wanted.get("locations") or []),
                              str(wanted.get("remote") or ""),
                              f"Base floor {wanted.get('base_floor')} {wanted.get('currency') or 'USD'}" if wanted.get("base_floor") is not None else ""])
    progress = decode_jsonb(row.get("progress"), {}) or {}
    outcome = "observed"
    if status in ("failed", "cancelled"):
        outcome = status
    elif str(progress.get("note") or "").startswith("Stopped early"):
        outcome = "partial"
    facts = [Fact(label="Status", value=clip(status, 80))]
    if criteria.strip("; "):
        facts.append(Fact(label="Criteria", value=clip(criteria, 300)))
    if terminal:
        for item in items:
            parts = []
            if research:
                parts.append(str(item.get("subtitle") or ""))
                fields = decode_jsonb(item.get("fields"), {}) or {}
                for key, value in list(fields.items())[:3]:
                    if not isinstance(value, dict) or not value.get("display"):
                        continue
                    evidence = "verified" if value.get("status") == "verified" else "unconfirmed"
                    parts.append(f"{key}: {value['display']} ({evidence})")
            else:
                from ..job_search.ranking import comp_line
                comp = decode_jsonb(item.get("comp"), {}) or {}
                parts.append(str(item.get("company") or ""))
                pay_status = item.get("comp_status") or "not_disclosed"
                parts.append(f"{comp_line(comp)} (posting pay)" if pay_status == "posted" else
                             "Pay mentioned, unverified" if pay_status == "mentioned" else "Pay not disclosed")
                parts.append(f"Approach: {item.get('approach_status') or 'none'}")
            if item.get("fit_score") is not None:
                parts.append(f"Fit: {item['fit_score']}/5")
            reasons = decode_jsonb(item.get("fit_reasons"), []) or []
            if reasons:
                parts.append(clip(reasons[0], 100))
            facts.append(Fact(label=clip(item["title"], 80), value=clip("; ".join(p for p in parts if p), 300) or "See source for evidence"))
    else:
        for key in ("found", "screened", "enriched", "ranked", "checked"):
            count = progress.get(key)
            if type(count) is int and 0 <= count <= 1_000_000 and len(facts) < 6:
                facts.append(Fact(label=key.capitalize(), value=str(count)))
    occurred = (row.get("recap_completed_at") or row.get("completed_at")) if terminal else row.get("updated_at")
    return Event(kind="result" if terminal else "phase_completed",
                 title=clip((row["title"] or "Research results") if terminal else f"{phase}: {row['title'] or 'Research'}"),
                 outcome=outcome, occurred_at=occurred or datetime.now(timezone.utc), facts=facts[:6])
