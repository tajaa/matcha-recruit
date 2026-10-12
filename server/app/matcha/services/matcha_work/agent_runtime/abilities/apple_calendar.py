"""Tools for calendars explicitly shared by the person's Mac via EventKit."""
from app.matcha.services.matcha_work import apple_calendar_service as apple, calendar_service as cal
from ..registry import AgentTool, ToolOutput


def _session(state):
    return state.sessions["calendar"]


def _fields(args, event=None):
    old = event or {}
    fields = cal.event_fields(title=args.get("title", old.get("title")),
        start=args.get("start", old.get("start")), end=args.get("end", old.get("end")),
        notes=args.get("notes", old.get("notes")), location=args.get("location", old.get("location")))
    begin = fields["start_date"] if fields["all_day"] else fields["starts_at"]
    end = fields["end_date"] if fields["all_day"] else fields["ends_at"]
    return {"title": fields["title"], "start": cal.render_when(begin, None),
            "end": cal.render_when(end, None), "all_day": fields["all_day"],
            "notes": fields["notes"], "location": fields["location"]}


def _resolve(operation, args, state):
    session = _session(state)
    if session.apple_connection is None:
        raise ValueError("List Apple Calendar first to choose the connected calendar.")
    event = None
    if operation != "create":
        event = session.apple_events.get(str(args.get("event_id") or ""))
        if not event or not event["editable"]:
            raise ValueError("List an editable event first. Existing invitations open in Apple Calendar.")
    return {"connection_id": session.apple_connection, "operation": operation,
            "payload": {"event": event, "fields": _fields(args, event) if operation != "delete" else {}}}


def _preview(args, state):
    event = args["payload"].get("event") or args["payload"]["fields"]
    return {"title": f"{args['operation'].capitalize()} Apple Calendar event: {event['title']}",
            "details": "Your connected Mac applies this change. Existing invitations are read-only."}


async def _list(ctx, state, args, remaining):
    begin, finish = cal.window(args.get("time_min"), args.get("time_max"))
    row = await apple.connection(ctx.user_id)
    feed = apple.events_in(row, begin, finish, args.get("query"))
    if row:
        _session(state).apple_connection = str(row["connection_id"])
        _session(state).apple_events.update({e["id"]: e for e in feed["events"]})
    return ToolOutput(payload=feed, label=f"Read {len(feed['events'])} Apple Calendar events")


async def _write(ctx, state, args, remaining):
    try:
        action_id = await apple.enqueue(ctx.user_id, args["connection_id"], args["operation"], args["payload"])
    except ValueError as exc:
        return ToolOutput(payload={"error": str(exc)})
    return ToolOutput(payload={"queued": True, "action_id": action_id,
                              "note": "Queued for the connected Mac, not yet confirmed. Check Calendar settings for its status."},
                      receipt={"status": "handoff", "note": "Queued for your Mac. Calendar settings shows when it finishes."})


def tools():
    fields = {k: {"type": "string"} for k in ("title", "start", "end", "notes", "location")}
    writes = []
    for operation in ("create", "update", "delete"):
        properties = fields if operation == "create" else {"event_id": {"type": "string"}, **(fields if operation == "update" else {})}
        writes.append(AgentTool(name=f"{operation}_apple_event", effect="commit", step_kind="commit", handler=_write,
            description=f"{operation.capitalize()} a personal Apple Calendar event through the connected Mac. Queued, not immediate. Invitations are read-only.",
            parameters={"type": "object", "properties": properties,
                        "required": ["title", "start", "end"] if operation == "create" else ["event_id"]},
            required_scopes=(apple.SCOPE,), timeout_seconds=20, ceilings=((30, 3600),),
            resolve=lambda args, state, op=operation: _resolve(op, args, state),
            targets=lambda args, state: (), preview=_preview))
    return (AgentTool(name="list_apple_events", effect="read", step_kind="read", handler=_list,
        description="Read the Apple Calendar snapshot shared by the person's Mac. Only status ok is complete, current availability; partial, stale and out_of_range data cannot prove that a time is free.",
        parameters={"type": "object", "properties": {k: {"type": "string"} for k in ("time_min", "time_max", "query")},
                    "required": ["time_min", "time_max"]},
        required_scopes=(apple.SCOPE,), max_calls=6, timeout_seconds=20, untrusted_output=True), *writes)
