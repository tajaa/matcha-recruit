"""One durable completion sender per logical request, with an honest grace link."""
from __future__ import annotations

import html
import json
import os
from uuid import uuid4

from app.database import connection_or_direct, decode_jsonb

from . import settings, transport
from .service import VALID


async def own_mail(conn, *, kind, source_id, message):
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
    # Registration already assigned ownership before legacy mail was suppressed.
    # A payload failure must not activate a second sender; recovery uses evidence.
    if len(json.dumps(message).encode()) <= 65_536:
        await conn.execute("UPDATE mw_agent_recap_sources SET mail_payload=$2::jsonb WHERE id=$1", source["id"], json.dumps(message))
    return True


def compose(row, messages: list[dict], *, recap_email: bool) -> dict:
    subject = f"Finished: {row['title']}"
    parts = [f"<h2>{html.escape(subject)}</h2>"]
    text = [subject]
    for message in messages[:5]:
        # Stored composers already escape their inputs; use their text as plain
        # content here so the combined root never nests arbitrary HTML documents.
        content = str(message.get("text") or "")[:6000]
        text.append(content)
        parts.append(f"<p style='white-space:pre-wrap'>{html.escape(content)}</p>")
    if not messages:
        text.append("Your task has finished. Open Espresso to review its results and action outcomes.")
        parts.append(f"<p>{text[-1]}</p>")
    if recap_email and row["state"] in ("ready", "queued", "rendering"):
        base = os.getenv("FRONTEND_URL", "https://hey-matcha.com").rstrip("/")
        link = f"{base}/espresso/recaps/{row['id']}"
        label = "Watch recap" if row["state"] == "ready" else "View recap (preparing)"
        text.append(f"{label}: {link}")
        parts.append(f'<p><a href="{html.escape(link, quote=True)}">{label}</a></p>')
    return {"subject": subject[:200], "html": "".join(parts), "text": "\n\n".join(text)}


async def deliver(delivery_id):
    token = uuid4()
    async with connection_or_direct() as conn, conn.transaction():
        delivery = await conn.fetchrow(
            """UPDATE mw_agent_recap_deliveries SET state='sending',claim_token=$2,
               lease_until=NOW()+INTERVAL '90 seconds',attempts=attempts+1
               WHERE id=$1 AND state IN ('pending','retry_wait') AND not_before<=NOW() AND attempts<3
               AND deadline_at IS NOT NULL RETURNING *""", delivery_id, token,
        )
        if not delivery:
            return
        row = await conn.fetchrow(
            f"""SELECT r.*,u.email,p.email_enabled FROM mw_agent_recaps r JOIN users u ON u.id=r.owner_user_id
                LEFT JOIN mw_agent_recap_preferences p ON p.user_id=r.owner_user_id AND p.company_id=r.company_id
                WHERE r.id=$1 AND r.state NOT IN ('deleted','expired') AND {VALID}""", delivery["recap_id"],
        )
        sources = await conn.fetch("SELECT kind,mail_payload FROM mw_agent_recap_sources WHERE recap_id=$1 AND completion_mail_owner='recap'", delivery["recap_id"])
        messages = [decode_jsonb(s["mail_payload"], {}) for s in sources if s["mail_payload"]]
        # Ordinary search email eligibility remains intact when recap email is
        # off. A quick round without a legacy payload never gains a new email.
        standalone = bool(row and row["email_enabled"] and row["last_error_code"] != "no_useful_evidence")
        should_send = bool(row and (messages or standalone))
        if not should_send:
            await conn.execute("UPDATE mw_agent_recap_deliveries SET state='suppressed' WHERE id=$1 AND claim_token=$2", delivery_id, token)
            return
        message = compose(dict(row), messages, recap_email=bool(row["email_enabled"] and settings.enabled()))
        recipient = row["email"]
    # No database transaction spans provider I/O.
    result = await transport.send(recipient, message)
    state = result.state
    if state == "retry_wait" and delivery["attempts"] >= 3:
        state = "failed"
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_agent_recap_deliveries SET state=$3,provider=$4,provider_message_id=$5,
               sent_at=CASE WHEN $3='sent' THEN NOW() ELSE NULL END,
               not_before=NOW()+make_interval(secs=>$6),lease_until=NULL
               WHERE id=$1 AND claim_token=$2 AND state='sending'""",
            delivery_id, token, state, result.provider, result.message_id, 30.0 if delivery["attempts"] == 1 else 120.0,
        )
