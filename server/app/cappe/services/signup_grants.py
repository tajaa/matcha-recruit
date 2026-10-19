"""Signup grants: a link that starts a new account on a paid plan for a while.

A Matcha admin makes one at /admin/cappe ("30 days of Business", optionally
for one address only) and sends its link. Signing up through it records the
grant on the new account; confirming the email gives the plan as a comp that
ends `days` later. No card is taken. When the comp runs out
`cappe_comp_expiry` drops the account to free, and from then on it pays like
any other account.

The comp is the same `billing.grant_comp` an admin uses by hand, so a grant
shows up wherever comps do (the billing page's "free until", the admin roster)
and is never mistaken for a paying subscriber.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from . import billing
from .email import dashboard_url

logger = logging.getLogger(__name__)

# What a token in a link may look like; `new_token` makes 32 of these.
TOKEN_PATTERN = r"^[A-Za-z0-9_-]{16,64}$"


def new_token() -> str:
    return secrets.token_urlsafe(24)


def signup_url(token: str) -> str:
    return dashboard_url(f"/signup?grant={token}")


def unusable_reason(grant: Any, *, now: datetime, email: Optional[str] = None) -> Optional[str]:
    """Why this grant can't start an account, as a sentence for the person
    holding the link, or None when it can. `email` is checked only when given:
    the signup page asks before anyone has typed an address."""
    if grant is None or grant["revoked_at"] is not None:
        return "This invite link is no longer valid."
    if grant["expires_at"] is not None and grant["expires_at"] <= now:
        return "This invite link has expired."
    if grant["redeemed_count"] >= grant["max_redemptions"]:
        return "This invite link has already been used."
    if email is not None and grant["email"] and grant["email"].lower() != email.lower():
        return "This invite link is for a different email address."
    return None


_GRANT_SELECT = """
    SELECT g.id, g.token, g.plan_code, g.days, g.max_redemptions, g.redeemed_count,
           g.email, g.note, g.expires_at, g.revoked_at, p.name AS plan_name
      FROM cappe_signup_grants g
      JOIN cappe_billing_products p ON p.code = g.plan_code
"""


async def find(conn, token: str):
    return await conn.fetchrow(f"{_GRANT_SELECT} WHERE g.token = $1", token)


async def redeem(conn, *, account_id: UUID) -> Optional[dict]:
    """Give a just-confirmed account the plan its signup grant promised.

    Returns `{plan_code, plan_name, until}`, or None when the account has no
    grant, already got it, or the grant can no longer be used (revoked, or
    every use went to someone who confirmed first).

    One transaction. The account row is locked first, so two confirmations of
    the same account racing each other give the plan once; the grant row is
    locked next, so two accounts racing for its last use can't both get it.
    Expiry is judged at signup time, when the link was used: a confirmation
    email opened the day after the link expired still gets the plan.
    """
    now = datetime.now(timezone.utc)
    async with conn.transaction():
        account = await conn.fetchrow(
            "SELECT email, created_at, signup_grant_id, signup_grant_redeemed_at "
            "FROM cappe_accounts WHERE id = $1 FOR UPDATE",
            account_id,
        )
        if account is None or account["signup_grant_id"] is None:
            return None
        if account["signup_grant_redeemed_at"] is not None:
            return None
        grant = await conn.fetchrow(
            f"{_GRANT_SELECT} WHERE g.id = $1 FOR UPDATE OF g", account["signup_grant_id"]
        )
        reason = unusable_reason(grant, now=account["created_at"] or now, email=account["email"])
        if reason is not None:
            logger.info(
                "cappe: signup grant %s not given to account %s: %s",
                account["signup_grant_id"], account_id, reason,
            )
            return None

        until = now + timedelta(days=grant["days"])
        await billing.grant_comp(
            conn, account_id=account_id, plan_code=grant["plan_code"], until=until,
            reason=f"Signup grant: {grant['note']}" if grant["note"] else "Signup grant",
        )
        await conn.execute(
            "UPDATE cappe_signup_grants SET redeemed_count = redeemed_count + 1 WHERE id = $1",
            grant["id"],
        )
        await conn.execute(
            "UPDATE cappe_accounts SET signup_grant_redeemed_at = $2, updated_at = NOW() "
            "WHERE id = $1",
            account_id, now,
        )
    return {"plan_code": grant["plan_code"], "plan_name": grant["plan_name"], "until": until}
