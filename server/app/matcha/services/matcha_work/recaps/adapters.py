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
    if status in ("claimed", "unknown"):
        outcome = "unknown"
    elif status in ("error", "denied", "skipped"):
        outcome = "failed"
    elif status == "held":
        outcome = "held"
    elif kind == "commit" and value.get("mode") != "live":
        outcome = "dry_run"
    elif kind == "commit":
        outcome = "confirmed"
    elif kind == "draft":
        outcome = "drafted"
    else:
        outcome = "observed"
    facts = [Fact(label="Outcome", value=outcome.replace("_", " "))]
    if tool in ("archive_email", "label_email") and isinstance(value.get("weight"), int) and 0 < value["weight"] <= 200:
        facts.append(Fact(label="Selected messages", value=str(value["weight"])))
    # Never use args, preview lines, result bodies or free-form audit labels.
    return Event(kind="action_resolved", title=TOOLS.get(tool, "Agent action"), outcome=outcome,
                 occurred_at=step.get("resolved_at") or step["created_at"],
                 facts=facts)


async def search_event(conn, source, *, terminal=False, phase="") -> Event:
    research = source["kind"] == "research"
    if research:
        row = await conn.fetchrow(
            """SELECT t.*, q.n AS recap_round, q.status AS recap_status FROM mw_agent_task_rounds q
               JOIN mw_agent_tasks t ON t.id=q.task_id WHERE q.id=$1""", source["task_round_id"],
        )
        items = await conn.fetch(
            """SELECT title,subtitle,status FROM mw_agent_task_items WHERE task_id=$1
               AND rank_band < 9 ORDER BY rank NULLS LAST, id LIMIT 3""", row["id"],
        )
        status = row["status"] if terminal and row["recap_status"] in ("queued", "running") else row["recap_status"] if terminal else row["status"]
    else:
        row = await conn.fetchrow("SELECT * FROM mw_job_searches WHERE id=$1", source["job_search_id"])
        items = await conn.fetch(
            """SELECT title,company AS subtitle,comp_status AS status FROM mw_job_leads WHERE search_id=$1
               AND screen_status <> 'irrelevant' ORDER BY rank NULLS LAST, id LIMIT 3""", row["id"],
        )
        status = row["status"]
    progress = decode_jsonb(row.get("progress"), {}) or {}
    outcome = "observed"
    if status in ("failed", "cancelled"):
        outcome = status
    elif str(progress.get("note") or "").startswith("Stopped early"):
        outcome = "partial"
    facts = [Fact(label="Status", value=clip(status, 80))]
    if terminal:
        for item in items:
            facts.append(Fact(label=clip(item["title"], 80), value=clip(item["subtitle"], 240) or "See source for evidence"))
    return Event(kind="result" if terminal else "phase_completed",
                 title=clip((row["title"] or "Research results") if terminal else f"Stage: {phase}"),
                 outcome=outcome, occurred_at=datetime.now(timezone.utc), facts=facts)
