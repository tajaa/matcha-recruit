"""Cappe newsletter-campaign helpers (pure — unit-tested without DB/SMTP)."""
from html import escape

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
