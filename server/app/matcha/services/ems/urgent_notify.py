"""Urgent-event fan-out: in-app notification to every reviewing admin +
email to the protocol-designated contacts (falling back to all admins).

Called fire-and-forget from channels_ws (_bg_ems_urgent_notify) AFTER the
pill broadcasts — a notify failure must never cost the confirmation.
Email carries title/category/channel/link only, NEVER the narrative
(at-rest in third-party inboxes — escalation_service precedent); the OSHA
variant adds the statutory window + hotline so the email alone is
actionable at 2am.
"""

import asyncio
import logging
from html import escape
from uuid import UUID

from app.config import get_settings
from app.database import get_connection
from app.matcha.services.ems import categories
from app.matcha.services.ir.ir_cards import OSHA_EMERGENCY_HOTLINE

logger = logging.getLogger(__name__)

NOTIFICATION_TYPE = "ems_urgent_event"

_OSHA_EMAIL_CLAUSE = (
    "<p>A fatality must be reported to OSHA within 8 hours; an in-patient "
    "hospitalization, amputation, or loss of an eye within 24 hours "
    f"(29 CFR 1904.39). OSHA hotline: <strong>{OSHA_EMERGENCY_HOTLINE}</strong>.</p>"
)

_ADMIN_CONTACTS_SQL = """
    SELECT DISTINCT u.id, u.email,
           COALESCE(NULLIF(c.name, ''), split_part(u.email, '@', 1)) AS name
    FROM clients c
    JOIN users u ON u.id = c.user_id
    WHERE c.company_id = $1 AND u.is_active = true AND u.email IS NOT NULL
    ORDER BY u.email
"""


def resolve_email_recipients(protocol_row, admin_contacts: list[dict]) -> list[dict]:
    """Pure. Explicit protocol notify_emails are designated contacts;
    notify_all_admins (default True — also the no-protocol-row default)
    unions in every active client contact. Case-insensitive dedupe. Never
    empty while admin_contacts is non-empty."""
    recipients: dict[str, dict] = {}
    if protocol_row:
        for email in protocol_row.get("notify_emails") or []:
            e = (email or "").strip()
            if e:
                recipients[e.lower()] = {"email": e, "name": e.split("@")[0]}
    include_admins = True if protocol_row is None else bool(protocol_row.get("notify_all_admins"))
    if include_admins or not recipients:
        for c in admin_contacts:
            recipients.setdefault((c["email"] or "").lower(), {"email": c["email"], "name": c["name"]})
    return list(recipients.values())


def build_urgent_email(*, urgency: str, company_name: str, title: str,
                       category_label: str, channel_name: str, link: str) -> tuple[str, str]:
    """(subject, html). No narrative — see module docstring."""
    kind = "possible OSHA-reportable event" if urgency == "osha" else "severe event reported"
    # title/channel_name/company_name trace back to user-typed channel
    # content (the model's own title, or a channel/company name) — escape
    # everything interpolated into the HTML body. `link` must be the
    # absolute app_base_url form here — a relative href is dead in an email
    # client — but escape it too on principle. The SUBJECT is plain text
    # (a mail header, not HTML), so it must NOT be escape()'d — the send
    # path already MIME-encodes the header, and escaping here double-
    # encodes entities (`Bob & Sons` -> `Bob &amp; Sons` in every inbox).
    subject = f"[{company_name}] URGENT: {kind}"
    osha_clause = _OSHA_EMAIL_CLAUSE if urgency == "osha" else ""
    html = (
        f"<h2>\U0001F6A8 Urgent event flagged by Huume</h2>"
        f"<p><strong>{escape(title)}</strong></p>"
        f"<p>Category: {escape(category_label)} · Channel: #{escape(channel_name)}</p>"
        f"{osha_clause}"
        f'<p><a href="{escape(link, quote=True)}">Review the event</a></p>'
    )
    return subject, html


async def send_urgent_event_notifications(*, company_id: UUID, event_row: dict) -> None:
    """Best-effort; never raises (caller logs via its own wrapper)."""
    from app.core.services.email import get_email_service
    from app.matcha.services import notification_service as notif_svc

    async with get_connection() as conn:
        company_row = await conn.fetchrow(
            "SELECT name, enabled_features, signup_source FROM companies WHERE id = $1", company_id,
        )
        channel_name = await conn.fetchval(
            "SELECT name FROM channels WHERE id = $1", event_row.get("channel_id"),
        ) or "channel"
        protocol_row = await conn.fetchrow(
            "SELECT notify_emails, notify_all_admins FROM company_event_protocols WHERE company_id = $1",
            company_id,
        )
        protocol_row = dict(protocol_row) if protocol_row else None
        admin_contacts = [dict(r) for r in await conn.fetch(_ADMIN_CONTACTS_SQL, company_id)]
    # -- conn released; notification + email fan-out open their own --

    company_name = (company_row and company_row["name"]) or "Your company"
    # Werk-Lite tenants live at /werk-lite, not /work — same merge werk
    # itself uses (channels_ws.py:_ems_company_gate) so the link lands the
    # admin in the shell they actually have.
    from app.core.feature_flags import merge_company_features
    merged = merge_company_features(
        (company_row and company_row["enabled_features"]) or {},
        company_row and company_row["signup_source"],
    )
    base_path = "/werk-lite" if merged.get("werk_lite") else "/work"

    urgency = event_row["urgency"]
    title = event_row.get("title") or categories.category_label(event_row["category"])
    label = categories.category_label(event_row["category"])
    link = f"{base_path}/events/{event_row['id']}"
    email_link = f"{get_settings().app_base_url.rstrip('/')}{link}"
    body = (
        "Possibly OSHA-reportable — a fatality must be reported within 8 hours; "
        "hospitalization/amputation/eye loss within 24 hours."
        if urgency == "osha" else "Flagged severe by Huume — review now."
    )

    for contact in admin_contacts:
        try:
            await notif_svc.create_notification(
                user_id=contact["id"], company_id=company_id,
                type=NOTIFICATION_TYPE, title=f"\U0001F6A8 Urgent event: {title}",
                body=body, link=link,
                metadata={"event_id": str(event_row["id"]), "urgency": urgency},
            )
        except Exception:
            logger.warning("urgent notify: in-app failed for %s", contact["id"], exc_info=True)

    email_service = get_email_service()
    if not email_service.is_configured():
        return
    recipients = resolve_email_recipients(protocol_row, admin_contacts)
    subject, html = build_urgent_email(
        urgency=urgency, company_name=company_name, title=title,
        category_label=label, channel_name=channel_name, link=email_link,
    )
    await asyncio.gather(
        *[
            email_service.send_email_with_fallback(
                to_email=r["email"], to_name=r["name"], subject=subject, html_content=html,
            )
            for r in recipients
        ],
        return_exceptions=True,
    )
