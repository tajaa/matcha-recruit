"""A reader's shelf: every magazine one Gummfit login holds (cappemag06).

On each magazine a reader is that site's `cappe_shoppers` row. The row is
made when they sign in there with an emailed code, subscribe from their
dashboard, or are given free months by the writer. A reader account
(`account_type='reader'`) is a gummfit.com login, and its confirmed email is
matched to those rows. So a subscription started on the magazine's own site
shows up on the dashboard, and one started on the dashboard works on the
magazine's site.

Only a confirmed email is matched. Signing in already requires one, and the
check is repeated here, so an address that was never confirmed holds nothing.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status

from ..common import site_public_origin
from .access import PAYING_STATUSES
from .figures import card_image
from .magazines import live_magazine
from .reader import covers, live_stories

SHELF_LIMIT = 50

_SUB_COLS = "id, status, current_period_end, cancel_at_period_end, total_cents, currency"


async def confirmed_email(conn, account_id: UUID) -> str:
    """The account's email, lower-cased, once it is confirmed."""
    row = await conn.fetchrow("SELECT email, email_verified_at FROM cappe_accounts WHERE id = $1", account_id)
    if not row or not row["email_verified_at"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "code": "email_unverified", "message": "Confirm your email to see your magazines."})
    return row["email"].strip().lower()


async def held(conn, email: str) -> list[dict[str, Any]]:
    """The magazines this email subscribes to or was given, newest first: the
    latest paying subscription and the live comp on each."""
    rows = await conn.fetch(
        f"""SELECT s.id AS site_id, s.slug, s.subdomain, s.custom_domain, s.status AS site_status, s.account_id,
                   s.name AS site_name, m.name, m.tagline, m.accent,
                   sub.id AS sub_id, sub.status, sub.current_period_end, sub.cancel_at_period_end,
                   sub.total_cents, sub.currency, comp.id AS comp_id, comp.expires_at AS comp_expires_at
              FROM cappe_shoppers sh
              JOIN cappe_sites s ON s.id = sh.site_id
              LEFT JOIN cappe_magazines m ON m.site_id = s.id
              LEFT JOIN LATERAL (
                   SELECT {_SUB_COLS}, created_at FROM cappe_shopper_subscriptions
                    WHERE site_id = sh.site_id AND shopper_id = sh.id AND kind = 'magazine'
                      AND status = ANY($2::text[])
                    ORDER BY created_at DESC LIMIT 1) sub ON TRUE
              LEFT JOIN LATERAL (
                   SELECT id, expires_at, created_at FROM cappe_magazine_comps
                    WHERE site_id = sh.site_id AND shopper_id = sh.id AND revoked_at IS NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                    LIMIT 1) comp ON TRUE
             WHERE sh.email = $1 AND NOT sh.deleting AND (sub.id IS NOT NULL OR comp.id IS NOT NULL)
             ORDER BY GREATEST(sub.created_at, comp.created_at) DESC NULLS LAST
             LIMIT $3""",
        email, list(PAYING_STATUSES), SHELF_LIMIT,
    )
    return [dict(r) for r in rows]


def subscription_view(row: dict) -> Optional[dict[str, Any]]:
    if not row.get("sub_id"):
        return None
    return {"id": row["sub_id"], "status": row["status"], "current_period_end": row["current_period_end"],
            "cancel_at_period_end": bool(row["cancel_at_period_end"]), "total_cents": row["total_cents"],
            "currency": row["currency"]}


def story_card(post: dict, cover: Optional[dict]) -> dict[str, Any]:
    return {"slug": post["slug"], "title": post.get("title") or "", "kicker": post.get("kicker"),
            "excerpt": post.get("excerpt"), "topic": post.get("topic"), "access": post.get("access") or "free",
            "published_at": post.get("published_at"), "reading_minutes": post.get("reading_minutes"),
            "cover": card_image(cover)}


async def shelf(conn, email: str) -> list[dict[str, Any]]:
    """The dashboard's list. A magazine that is down still appears (`live`
    false) so its reader can stop paying for it."""
    out = []
    for row in await held(conn, email):
        site = {"id": row["site_id"], "account_id": row["account_id"], "subdomain": row["subdomain"],
                "custom_domain": row["custom_domain"]}
        mag = await live_magazine(conn, site) if row["site_status"] == "published" else None
        latest = None
        if mag:
            posts = await live_stories(conn, row["site_id"], limit=1)
            if posts:
                latest = story_card(posts[0], (await covers(conn, row["site_id"], posts)).get(str(posts[0]["id"])))
        out.append({
            "site_id": row["site_id"], "slug": row["slug"], "name": row["name"] or row["site_name"],
            "tagline": row["tagline"], "accent": row["accent"], "origin": site_public_origin(site),
            "live": bool(mag), "subscription": subscription_view(row),
            "comp": {"expires_at": row["comp_expires_at"]} if row["comp_id"] else None,
            "latest": latest,
        })
    return out


async def published_magazine(conn, slug: str) -> tuple[dict, dict]:
    """(site, magazine) for a magazine a reader can open, or a 404."""
    site = await conn.fetchrow("SELECT * FROM cappe_sites WHERE slug = $1 AND status = 'published'", slug)
    mag = await live_magazine(conn, site) if site else None
    if not mag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Magazine not found")
    return dict(site), mag


async def shopper_for(conn, site_id: UUID, email: str) -> Optional[dict]:
    row = await conn.fetchrow("SELECT * FROM cappe_shoppers WHERE site_id = $1 AND email = $2", site_id, email)
    return dict(row) if row else None


async def ensure_shopper(conn, site_id: UUID, email: str) -> dict:
    """The reader's row on this magazine, made if they never signed in there."""
    row = await conn.fetchrow(
        "INSERT INTO cappe_shoppers (site_id, email) VALUES ($1, $2) "
        "ON CONFLICT (site_id, email) DO UPDATE SET updated_at = NOW() RETURNING *",
        site_id, email,
    )
    if row["deleting"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account deletion is in progress")
    return dict(row)


async def own_subscription(conn, subscription_id: UUID, email: str) -> dict:
    """A magazine subscription held by this email, or a 404."""
    row = await conn.fetchrow(
        "SELECT sub.* FROM cappe_shopper_subscriptions sub "
        "JOIN cappe_shoppers sh ON sh.id = sub.shopper_id AND sh.site_id = sub.site_id "
        "WHERE sub.id = $1 AND sh.email = $2 AND sub.kind = 'magazine'",
        subscription_id, email,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return row
