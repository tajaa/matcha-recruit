"""Cappe newsletter-campaign helpers, and the send budget newsletters and
magazine issues share.

Campaigns go out through the platform's shared transactional sender, the same
one every other product's mail uses. A compromised or malicious tenant with an
uploaded address list is therefore a spam relay on OUR sending reputation, so a
send is bounded twice: how often an account may send at all
(`SENDS_PER_DAY`, the `cappe_campaign_send` rate-limit bucket), and how many
addresses it may reach in a day across all of its sites (`send_cap_problem`).
A magazine issue is a campaign (`kind='issue'`) and counts against both.
"""
from html import escape
from typing import Optional

from ...core.services.email._shared import _is_reserved_test_domain


def deliverable_recipients(rows) -> list[dict]:
    """Filter subscriber rows to actually-deliverable recipients: a real email,
    not a reserved/test domain, de-duplicated. Each row may be an asyncpg Record
    or a dict with email/name/unsubscribe_token."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        email = (r["email"] or "").strip().lower()
        if not email or email in seen or _is_reserved_test_domain(email):
            continue
        seen.add(email)
        out.append({
            "email": email,
            "name": (r["name"] if "name" in r else None),
            "unsubscribe_token": (r["unsubscribe_token"] if "unsubscribe_token" in r else None),
        })
    return out


def personalize_unsubscribe(body_html: str, unsubscribe_url: str) -> str:
    """Append a one-click unsubscribe footer to a campaign's HTML body. CAN-SPAM
    / deliverability basics: every bulk email needs a working opt-out."""
    safe = escape(unsubscribe_url or "", quote=True)
    footer = (
        '<p style="margin:28px 0 0;font-size:12px;color:#9aa0a6;line-height:1.6;">'
        "You're receiving this because you subscribed. "
        f'<a href="{safe}" style="color:#9aa0a6;">Unsubscribe</a>.</p>'
    )
    return f"{body_html or ''}{footer}"


SENDS_PER_DAY = 3
RECIPIENTS_PER_DAY = 5000


async def send_cap_problem(conn, account_id, site_id) -> Optional[str]:
    """Why sending to this site's subscribers now would break the daily
    recipient ceiling, or None.

    A campaign still `sending` has recipient_count 0 until the worker finalizes
    it, so counting finished ones alone let three back-to-back sends (3 × 5k)
    all clear a 5k cap. An in-flight campaign is charged its site's current
    subscriber count — the audience the worker is about to mail."""
    already_sent = await conn.fetchval(
        """SELECT COALESCE(SUM(
                    CASE WHEN c.status = 'sending'
                         THEN (SELECT COUNT(*) FROM cappe_subscribers sub
                                WHERE sub.site_id = c.site_id AND sub.status = 'subscribed')
                         ELSE c.recipient_count END), 0)
             FROM cappe_campaigns c
             JOIN cappe_sites s ON s.id = c.site_id
            WHERE s.account_id = $1
              AND (c.status = 'sending' OR c.sent_at > NOW() - INTERVAL '24 hours')""",
        account_id,
    )
    pending = await conn.fetchval(
        "SELECT COUNT(*) FROM cappe_subscribers WHERE site_id = $1 AND status = 'subscribed'",
        site_id,
    )
    if int(already_sent or 0) + int(pending or 0) > RECIPIENTS_PER_DAY:
        return (f"That would reach more than {RECIPIENTS_PER_DAY:,} people in 24 hours "
                f"(already sent to {int(already_sent or 0):,}). Try again tomorrow, or split the list.")
    return None
