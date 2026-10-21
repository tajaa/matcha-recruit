"""A site's magazine (`cappe_magazines`, one per site) and whether it is live.

A magazine is live — its pages render — when the owner has turned it on AND
the owner's plan includes `magazine`. The plan is checked when a page is
rendered, not when the owner saves, so losing the plan takes the pages down
without touching anything the owner wrote, and the iOS app's post editing
never meets a 402.

One exception: a magazine whose readers were paying stays up for
`GRACE_DAYS` after its paid subscriptions stopped (`lapsed_at`, set by
`services/magazine/lapse.py`), and while that sweep hasn't run yet. Readers
keep what they paid for; their subscriptions end with the month they paid.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from ..entitlements import resolve_entitlements

MAG_COLS = (
    "site_id, enabled, name, tagline, about, masthead_style, accent, topics, front_at_root, nav_label, "
    "cover_post_id, follow_enabled, paid_enabled, price_cents, paid_pitch, preview_blocks, lapsed_at, "
    "created_at, updated_at"
)

GRACE_DAYS = 31
DEFAULT_PREVIEW_BLOCKS = 3

# Masthead style → (masthead and headline font, body font). Google Fonts, all
# serif-forward except `modern`; loaded on magazine pages only.
MASTHEADS: dict[str, tuple[str, str]] = {
    "classic": ("Bodoni Moda", "Spectral"),
    "literary": ("Newsreader", "Newsreader"),
    "modern": ("Archivo Black", "Libre Franklin"),
    "elegant": ("Cormorant Garamond", "EB Garamond"),
    "display": ("Playfair Display", "Lora"),
}

EDITABLE = ("enabled", "name", "tagline", "about", "masthead_style", "accent", "topics", "front_at_root",
            "nav_label", "cover_post_id", "follow_enabled", "paid_enabled", "price_cents", "paid_pitch",
            "preview_blocks", "lapsed_at")


async def get_magazine(conn, site_id: UUID) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(f"SELECT {MAG_COLS} FROM cappe_magazines WHERE site_id = $1", site_id)
    return dict(row) if row else None


async def save_magazine(conn, site_id: UUID, fields: dict[str, Any], *, default_name: str) -> dict[str, Any]:
    """Create or update the site's magazine with already-validated fields."""
    unknown = set(fields) - set(EDITABLE)
    if unknown:  # names go into the SQL
        raise ValueError(f"not editable: {sorted(unknown)}")
    # A first save needs a name; a later one changes only what was sent.
    names = list(fields) + ([] if "name" in fields else ["name"])
    values = [fields[n] for n in fields] + ([] if "name" in fields else [default_name])
    params = ", ".join(f"${i + 2}" for i in range(len(names)))
    updates = ", ".join([f"{n} = EXCLUDED.{n}" for n in fields] + ["updated_at = NOW()"])
    row = await conn.fetchrow(
        f"INSERT INTO cappe_magazines (site_id, {', '.join(names)}) VALUES ($1, {params}) "
        f"ON CONFLICT (site_id) DO UPDATE SET {updates} RETURNING {MAG_COLS}",
        site_id, *values,
    )
    return dict(row)


async def live_magazine(conn, site) -> Optional[dict[str, Any]]:
    """The site's magazine if its pages should render, else None."""
    mag = await get_magazine(conn, site["id"])
    if not mag or not mag["enabled"]:
        return None
    plan = await conn.fetchval("SELECT plan FROM cappe_accounts WHERE id = $1", site["account_id"])
    ent = await resolve_entitlements(plan, conn=conn)
    return mag if ent.has("magazine") or in_grace(mag) else None


def in_grace(mag: dict, *, now: Optional[datetime] = None) -> bool:
    """Whether a magazine stays up without the plan: its paid subscriptions
    stopped less than `GRACE_DAYS` ago, or are still on (the plan was lost and
    the lapse sweep hasn't stopped them yet)."""
    lapsed = mag.get("lapsed_at")
    if lapsed:
        return lapsed > (now or datetime.now(timezone.utc)) - timedelta(days=GRACE_DAYS)
    return bool(mag.get("paid_enabled"))


def preview_blocks(mag: Optional[dict]) -> int:
    """How many blocks a paid story without a paywall marker shows free."""
    return int((mag or {}).get("preview_blocks") or DEFAULT_PREVIEW_BLOCKS)


def nav_entry(mag: Optional[dict]) -> Optional[dict]:
    """The header link to the magazine, or None (no magazine, or it is the
    home page already)."""
    if not mag or mag.get("front_at_root"):
        return None
    return {"title": mag.get("nav_label") or "Magazine", "href": "/magazine"}


def masthead_fonts(mag: dict) -> tuple[str, str]:
    return MASTHEADS.get(mag.get("masthead_style") or "", MASTHEADS["classic"])
