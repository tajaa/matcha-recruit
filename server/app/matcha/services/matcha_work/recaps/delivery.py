"""One durable completion sender per logical request, with an honest grace link."""
from __future__ import annotations

import html
import json
import re
from uuid import uuid4

from app.config import get_settings
from app.database import connection_or_direct, decode_jsonb

from . import settings, transport
from .service import VALID

# Under the column's 64 KiB CHECK, with room for jsonb's own spacing.
PAYLOAD_BYTES = 60_000
# How long a handed-over email waits for its recap to be ready to link.
GRACE = "120 seconds"
_BODY = re.compile(r"<body[^>]*>(.*)</body>", re.S | re.I)
_WRAP = ("<div style=\"max-width:600px;margin:0 auto;padding:0 24px 24px;font-family:-apple-system,"
         "BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.5;color:#1c1917\">")


def _payload(message: dict) -> str:
    """The legacy email as stored for the combined send. Too large whole, it
    keeps its words: a handed-over email is never dropped for its size."""
    subject, text = str(message.get("subject") or "")[:200], str(message.get("text") or "")
    for candidate in (message, {"subject": subject, "text": text}, {"subject": subject, "text": text[:20_000]}):
        raw = json.dumps(candidate)
        if len(raw.encode()) <= PAYLOAD_BYTES:
            return raw
    return json.dumps({"subject": subject, "text": text[:6_000]})


async def own_mail(conn, *, kind, source_id, message):
    """Hand a finished source's completion email to its recap's one sender.

    False, so the caller sends it itself as always, unless that sender is
    certain to send it: a recap deleted or expired, a delivery suppressed or
    already sent, or a recap sweep an admin switched off never takes one.
    Taking it starts the grace period now, whatever the recap's other sources
    are still doing."""
    if not settings.enabled() and not await conn.fetchval("SELECT to_regclass('mw_agent_recaps')"):
        return False
    if kind == "research":
        source = await conn.fetchrow(
            """SELECT s.* FROM mw_agent_recap_sources s JOIN mw_agent_task_rounds q ON q.id=s.task_round_id
               JOIN mw_agent_tasks t ON t.id=q.task_id AND t.current_round=q.n
               WHERE t.id=$1 AND s.kind='research'""", source_id,
        )
    else:
        source = await conn.fetchrow(
            """SELECT s.* FROM mw_agent_recap_sources s JOIN mw_job_searches j
               ON j.id=s.job_search_id AND j.recap_generation=s.generation WHERE j.id=$1 AND s.kind='jobs'""", source_id,
        )
    if not source or source["completion_mail_owner"] != "recap":
        return False
    # One statement: the delivery row lock orders this hand-over against a
    # send claiming it and against a tombstone suppressing it.
    return bool(await conn.fetchval(
        f"""WITH handed AS (
               UPDATE mw_agent_recap_deliveries d SET
                   not_before=CASE WHEN d.deadline_at IS NULL THEN NOW()+INTERVAL '{GRACE}' ELSE d.not_before END,
                   deadline_at=COALESCE(d.deadline_at, NOW()+INTERVAL '{GRACE}')
               FROM mw_agent_recaps r
               WHERE d.recap_id=$2 AND r.id=d.recap_id AND d.state IN ('pending','retry_wait')
                 AND r.state NOT IN ('deleted','expired')
                 AND NOT EXISTS (SELECT 1 FROM scheduler_settings x WHERE x.task_key='espresso_recaps' AND NOT x.enabled)
               RETURNING d.id)
           UPDATE mw_agent_recap_sources SET mail_payload=$3::jsonb
           WHERE id=$1 AND EXISTS (SELECT 1 FROM handed) RETURNING TRUE""",
        source["id"], source["recap_id"], _payload(message),
    ))


def _body(message: dict) -> str:
    """A stored message's body: its composer's HTML (which escaped its own
    inputs), else its text. Never a nested document."""
    found = _BODY.search(str(message.get("html") or ""))
    if found:
        return found.group(1)
    content = html.escape(str(message.get("text") or "")[:6000])
    return f"{_WRAP}<p style='white-space:pre-wrap'>{content}</p></div>"


def compose(row, messages: list[dict], *, recap_email: bool) -> dict:
    messages = messages[:5]
    if messages:
        # The task's own email, as it would have gone, with the recap link added.
        subject = str(messages[0].get("subject") or f"Finished: {row['title']}")
        if len(messages) > 1:
            subject += f" and {len(messages) - 1} more"
        parts = [_body(message) for message in messages]
        text = [str(message.get("text") or "")[:20_000] for message in messages]
    else:
        subject = f"Finished: {row['title']}"
        line = "Your task has finished. Open Espresso to review its results and action outcomes."
        parts = [f"{_WRAP}<h2>{html.escape(subject)}</h2><p>{line}</p></div>"]
        text = [subject, line]
    if recap_email and row["state"] in ("ready", "queued", "rendering"):
        base = get_settings().app_base_url.rstrip("/")
        link = f"{base}/espresso/recaps/{row['id']}"
        label = "Watch recap" if row["state"] == "ready" else "View recap (preparing)"
        text.append(f"{label}: {link}")
        parts.append(f'{_WRAP}<p><a href="{html.escape(link, quote=True)}">{label}</a></p></div>')
    divider = '<hr style="border:none;border-top:1px solid #e7e5e4;margin:8px auto;max-width:600px">'
    document = ('<!DOCTYPE html><html><body style="margin:0;padding:0">'
                + divider.join(parts) + "</body></html>")
    return {"subject": subject[:200], "html": document, "text": "\n\n".join(text)}


async def deliver(delivery_id):
    token = uuid4()
    async with connection_or_direct() as conn, conn.transaction():
        delivery = await conn.fetchrow(
            """UPDATE mw_agent_recap_deliveries SET state='sending',claim_token=$2,dispatched_at=NULL,
               lease_until=NOW()+INTERVAL '90 seconds',attempts=attempts+1
               WHERE id=$1 AND state IN ('pending','retry_wait') AND not_before<=NOW() AND attempts<3
               AND deadline_at IS NOT NULL RETURNING *""", delivery_id, token,
        )
        if not delivery:
            return
        # A recap the person deleted still sends the task email it was handed
        # (without a link); a revoked source or owner fails VALID instead.
        row = await conn.fetchrow(
            f"""SELECT r.*,u.email,p.email_enabled FROM mw_agent_recaps r JOIN users u ON u.id=r.owner_user_id
                LEFT JOIN mw_agent_recap_preferences p ON p.user_id=r.owner_user_id AND p.company_id=r.company_id
                WHERE r.id=$1 AND r.state<>'expired' AND {VALID}""", delivery["recap_id"],
        )
        sources = await conn.fetch("SELECT kind,mail_payload FROM mw_agent_recap_sources WHERE recap_id=$1 AND completion_mail_owner='recap'", delivery["recap_id"])
        messages = [decode_jsonb(s["mail_payload"], {}) for s in sources if s["mail_payload"]]
        # Ordinary search email eligibility remains intact when recap email is
        # off. A quick round without a legacy payload never gains a new email.
        standalone = bool(row and row["email_enabled"] and row["state"] != "deleted"
                          and row["last_error_code"] != "no_useful_evidence")
        should_send = bool(row and (messages or standalone))
        if not should_send:
            await conn.execute("UPDATE mw_agent_recap_deliveries SET state='suppressed' WHERE id=$1 AND claim_token=$2", delivery_id, token)
            await conn.execute("UPDATE mw_agent_recap_sources SET mail_payload=NULL WHERE recap_id=$1", delivery["recap_id"])
            return
        message = compose(dict(row), messages, recap_email=bool(row["email_enabled"] and settings.enabled()))
        recipient = row["email"]
    # No database transaction spans provider I/O.
    result = await transport.send(recipient, message)
    state = result.state
    if state == "retry_wait" and delivery["attempts"] >= 3:
        state = "failed"
    async with connection_or_direct() as conn, conn.transaction():
        updated = await conn.fetchval(
            """UPDATE mw_agent_recap_deliveries SET state=$3,provider=$4,provider_message_id=$5,
               sent_at=CASE WHEN $3='sent' THEN NOW() ELSE NULL END,
               not_before=NOW()+make_interval(secs=>$6),lease_until=NULL
               WHERE id=$1 AND claim_token=$2 AND state='sending' RETURNING TRUE""",
            delivery_id, token, state, result.provider, result.message_id, 30.0 if delivery["attempts"] == 1 else 120.0,
        )
        if updated and state != "retry_wait":
            # Settled: the stored task emails have no further use.
            await conn.execute("UPDATE mw_agent_recap_sources SET mail_payload=NULL WHERE recap_id=$1", delivery["recap_id"])
