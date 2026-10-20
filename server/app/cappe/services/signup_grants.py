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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from ..models.auth import GRANT_TOKEN_PATTERN
from . import billing
from .email import dashboard_url

logger = logging.getLogger(__name__)

TOKEN_PATTERN = GRANT_TOKEN_PATTERN


def new_token() -> str:
    return secrets.token_urlsafe(24)


def signup_url(token: str) -> str:
    return dashboard_url(f"/signup?grant={token}")


def unusable_reason(grant: Any, *, now: datetime, email: Optional[str] = None) -> Optional[str]:
    """Why this grant can't start an account, as a sentence for the person
    holding the link, or None when it can. `email` is checked only when given:
    the signup page asks before anyone has typed an address.

    The one check for every path (the signup page's lookup, signup, the
    redemption at confirmation), so a rule added here holds everywhere."""
    if grant is None or grant["revoked_at"] is not None or grant["plan_status"] != "active":
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
           g.email, g.note, g.expires_at, g.revoked_at,
           p.name AS plan_name, p.status AS plan_status
      FROM cappe_signup_grants g
      JOIN cappe_billing_products p ON p.code = g.plan_code
"""


async def find(conn, token: str):
    return await conn.fetchrow(f"{_GRANT_SELECT} WHERE g.token = $1", token)


@dataclass(frozen=True)
class Redemption:
    """What confirming an account did with its grant: the plan given, free
    until `until`, or `refused` with the reason the person is told."""
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    until: Optional[datetime] = None
    refused: Optional[str] = None


ALREADY_ON_A_PLAN = "Your account already has a plan, so the invite's free plan wasn't added."


async def redeem(conn, *, account_id: UUID) -> Optional[Redemption]:
    """Give a just-confirmed account the plan its signup grant promised.

    None when the account has no grant or it was already dealt with. Otherwise
    a `Redemption`: the plan given, or why not — the grant can no longer be
    used (revoked, its plan withdrawn, every use taken by people who confirmed
    first), or the account already holds a plan (an admin gave it one while
    the email was unconfirmed; replacing that would undo the admin's choice).
    The outcome is written on the account either way, which is what makes this
    run once and lets the admin page say what happened.

    One transaction (a savepoint inside the caller's). The account row is
    locked first, so two confirmations of one account give the plan once; the
    grant row next, so two accounts racing for its last use can't both get it.
    Expiry is judged at signup time, when the link was used: a confirmation
    email opened the day after the link expired still gets the plan.
    """
    now = datetime.now(timezone.utc)
    async with conn.transaction():
        account = await conn.fetchrow(
            "SELECT email, created_at, signup_grant_id, signup_grant_redeemed_at, "
            "signup_grant_refused FROM cappe_accounts WHERE id = $1 FOR UPDATE",
            account_id,
        )
        if account is None or account["signup_grant_id"] is None:
            return None
        if account["signup_grant_redeemed_at"] is not None or account["signup_grant_refused"]:
            return None
        grant = await conn.fetchrow(
            f"{_GRANT_SELECT} WHERE g.id = $1 FOR UPDATE OF g", account["signup_grant_id"]
        )
        reason = unusable_reason(grant, now=account["created_at"] or now, email=account["email"])
        if reason is None and await conn.fetchval(
            "SELECT 1 FROM cappe_subscriptions WHERE account_id = $1 "
            "AND status IN ('trialing','active','past_due','incomplete','unpaid','paused')",
            account_id,
        ):
            reason = ALREADY_ON_A_PLAN
        if reason is not None:
            logger.info(
                "cappe: signup grant %s not given to account %s: %s",
                account["signup_grant_id"], account_id, reason,
            )
            await conn.execute(
                "UPDATE cappe_accounts SET signup_grant_refused = $2, updated_at = NOW() "
                "WHERE id = $1",
                account_id, reason,
            )
            return Redemption(refused=reason)

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
    return Redemption(plan_code=grant["plan_code"], plan_name=grant["plan_name"], until=until)
