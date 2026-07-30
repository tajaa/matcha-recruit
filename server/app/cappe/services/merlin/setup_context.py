"""Site/account context for the dashboard setup concierge.

The page editor's Merlin gets a page snapshot (blocks + theme) as its
context. The dashboard concierge has no open page — the SITE is the
context: what's built, what's missing (readiness), what plan allows
(entitlements), and what's already been proposed this conversation (staged
actions). `build_setup_context` reads that; `build_setup_prompt` turns it
into the system instruction, alongside the registry-generated action
vocabulary from `setup_actions.SETUP_ACTIONS` — the same anti-drift shape
`services/merlin/turn.py` uses for the page editor's op vocabulary, so the
prompt can never describe an action the validator doesn't actually enforce.
"""
import json
from typing import Any, Optional

from ..common import loads
from ..entitlements import Entitlements, resolve_entitlements
from ..readiness import compute_readiness
from .setup_actions import SETUP_ACTIONS, SETUP_PAGE_PRESETS

_MAX_PRODUCTS_LISTED = 10


async def build_setup_context(conn, site: dict[str, Any], account: Any) -> dict[str, Any]:
    """Everything the concierge's prompt needs, read fresh every turn — this
    surface has no client-resent snapshot to fall back on, so a DB read here
    is the only way it ever sees what changed since the last message."""
    site_id = site["id"]
    entitlements = await resolve_entitlements(account.plan, conn=conn)
    readiness = await compute_readiness(conn, site_id, site)

    page_rows = await conn.fetch(
        "SELECT id, title, slug, content FROM cappe_pages WHERE site_id = $1 ORDER BY sort_order, created_at",
        site_id,
    )
    pages = []
    for r in page_rows:
        content = loads(r["content"])
        block_types = [
            b.get("type") for b in (content.get("blocks") or [])
            if isinstance(b, dict) and b.get("type")
        ]
        pages.append({
            "id": str(r["id"]), "title": r["title"], "slug": r["slug"], "block_types": block_types,
        })

    product_rows = await conn.fetch(
        """SELECT name, price_cents, fulfillment, status FROM cappe_products
           WHERE site_id = $1 ORDER BY created_at DESC LIMIT $2""",
        site_id, _MAX_PRODUCTS_LISTED,
    )
    product_count = await conn.fetchval(
        "SELECT COUNT(*) FROM cappe_products WHERE site_id = $1", site_id
    )
    booking_type_count = await conn.fetchval(
        "SELECT COUNT(*) FROM cappe_booking_types WHERE site_id = $1 AND status = 'active'", site_id
    )
    subscriber_count = await conn.fetchval(
        "SELECT COUNT(*) FROM cappe_subscribers WHERE site_id = $1 AND status = 'subscribed'", site_id
    )

    meta = loads(site.get("meta_config"))
    promos = meta.get("promos") if isinstance(meta.get("promos"), dict) else {}

    return {
        "site_name": site.get("name"),
        "account_name": account.name,
        "account_type": account.account_type,
        "plan": account.plan,
        "plan_name": entitlements.plan_name,
        "allowed_fulfillment": sorted(entitlements.allowed_fulfillment),
        "is_premium": entitlements.plan_code in ("pro", "business", "creator"),
        "readiness": readiness,
        "pages": pages,
        "products": [dict(r) for r in product_rows],
        "product_count": product_count or 0,
        "booking_type_count": booking_type_count or 0,
        "subscriber_count": subscriber_count or 0,
        "promo_bar_enabled": bool((promos.get("bar") or {}).get("enabled")),
        "promo_popup_enabled": bool((promos.get("popup") or {}).get("enabled")),
    }


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SETUP_INSTRUCTIONS = """You are Merlin, helping {account_name} set up their website conversationally.

You do NOT edit pages directly. Every change you propose is STAGED via stage_action and only \
takes effect after the user confirms — either by saying so in chat (then call \
execute_staged_action with its id) or by clicking Approve in the UI. NEVER claim you created, \
added, or turned on something before it has actually been executed — say "I've staged that, \
want me to go ahead?" instead of "Done!".

One action per stage_action call. After an action executes, look at what's still missing \
from readiness (below) and suggest the next thing rather than waiting to be asked.

If what the user wants isn't allowed on their plan, say so plainly and offer the closest thing \
that IS allowed — never stage something you already know will be blocked. The plan/entitlement \
facts below are authoritative; don't guess at what a plan can or can't do."""


def _op_shapes_text() -> str:
    lines = [f'- {a.name}: {a.prompt_shape}' for a in SETUP_ACTIONS]
    return "Available actions (call stage_action with one of these types + a matching payload):\n" + "\n".join(lines)


def _rules_text() -> str:
    lines = []
    for a in SETUP_ACTIONS:
        for rule in a.prompt_rules:
            lines.append(f"[{a.name}] {rule}")
    if not lines:
        return ""
    return "Action-specific guidance:\n" + "\n".join(lines)


def _presets_text() -> str:
    lines = [f'- {key}: {", ".join(b["type"] for b in p["blocks"])}' for key, p in SETUP_PAGE_PRESETS.items()]
    return "create_page presets and the sections each contains:\n" + "\n".join(lines)


def _readiness_text(readiness: dict[str, Any]) -> str:
    if readiness.get("ready"):
        return "Readiness: this site has everything required to publish."
    items = readiness.get("items") or []
    missing = [i.get("label") or i.get("key") for i in items if not i.get("done")]
    if not missing:
        return "Readiness: unknown."
    return "Readiness — still missing: " + "; ".join(str(m) for m in missing)


def _account_type_guidance(account_type: str) -> str:
    if account_type == "personal":
        return (
            "This is a SOLO CREATOR (not a business) — lean toward selling sessions/bookings and "
            "digital downloads, and an about-ME page rather than an about-the-company one."
        )
    return (
        "This is a BUSINESS account — lean toward physical/digital products, a newsletter signup, "
        "and an about-the-company page."
    )


def build_setup_prompt(context: dict[str, Any]) -> str:
    """Pure — takes the dict `build_setup_context` returns, no DB access.
    Kept separate so prompt assembly is unit-testable from a canned context."""
    parts = [
        _SETUP_INSTRUCTIONS.format(account_name=context.get("account_name") or "there"),
        _op_shapes_text(),
        _rules_text(),
        _presets_text(),
        f"Site: {context.get('site_name') or 'Untitled site'}",
        _account_type_guidance(context.get("account_type") or "business"),
        (
            f"Plan: {context.get('plan_name')} — may sell: "
            f"{', '.join(context.get('allowed_fulfillment') or []) or 'nothing'}. "
            f"Promo banners {'are' if context.get('is_premium') else 'are NOT'} available on this plan."
        ),
        _readiness_text(context.get("readiness") or {}),
    ]

    pages = context.get("pages") or []
    if pages:
        page_lines = [
            f'- id={p["id"]} "{p["title"]}" (/{p["slug"]}) sections: {", ".join(p["block_types"]) or "empty"}'
            for p in pages
        ]
        parts.append("Existing pages (use these ids for add_blocks):\n" + "\n".join(page_lines))
    else:
        parts.append("Existing pages: none yet — the first ask is usually create_page.")

    parts.append(
        f"Commerce so far: {context.get('product_count', 0)} product(s), "
        f"{context.get('booking_type_count', 0)} active booking type(s), "
        f"{context.get('subscriber_count', 0)} newsletter subscriber(s). "
        f"Promo bar {'ON' if context.get('promo_bar_enabled') else 'off'}, "
        f"promo pop-up {'ON' if context.get('promo_popup_enabled') else 'off'}."
    )

    products = context.get("products") or []
    if products:
        lines = [
            f'- "{p["name"]}" {p["fulfillment"]} ${(p["price_cents"] or 0) / 100:.2f} ({p["status"]})'
            for p in products
        ]
        parts.append("Recent products:\n" + "\n".join(lines))

    return "\n\n".join(p for p in parts if p)
