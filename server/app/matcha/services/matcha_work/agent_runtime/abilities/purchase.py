"""Buying something the assistant found, with the person's saved card.

Two tools:

  prepare_purchase  (read) loads what could be bought and what it would be
                    bought with: the picks from this person's recent results
                    in this conversation, their saved cards and their shipping
                    addresses. Nothing here comes from the model.
  buy_item          (commit) names one of those by id. `resolve` freezes the
                    item, card, shipping and billing address into a
                    self-contained action.

What keeps this safe:

  * It always asks. `always_confirm` holds every purchase for the person's
    yes, on a card that shows the item, price, store, card and address; the
    yes carries out exactly that frozen action.
  * The item is the provenance-gated pick a previous run stored: its name,
    buy link and source-checked price. The model picks an id; it cannot write
    a price or a link.
  * The card number never leaves the vault. Card numbers and addresses are
    never asked for in chat: a missing card or address ends the run with a
    `purchase_setup` block that points at Settings.
  * No real money moves. With a Stripe test key and a verified price the
    purchase is a Stripe test-mode charge (`agent_card/test_charge.py`, the
    same path agent-card purchases use); otherwise it is a handoff: the order
    is recorded and the person finishes checkout at the store's link.
  * Private conversation only, switched on by the person (disclosure
    `purchase-1`), and only for accounts allowed to buy
    (`chat_flow.purchases_allowed`): admins and `AGENT_PURCHASE_ALLOWED_EMAILS`.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from app.core.services import card_vault
from app.database import connection_or_direct, decode_jsonb

from .. import consent, policy
from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, Target, ToolOutput

logger = logging.getLogger(__name__)

KEY = "purchase"
ALLOWANCE = "purchases"
RECENT_RESULTS = 3
TEST_MODE_NOTE = "Test purchase: no real money moves."

SETUP_STEPS = {
    "payment_card": {
        "label": "Add a payment card",
        "where": "Settings → Payment cards",
        "detail": "Stored encrypted. Never paste a card number in chat.",
    },
    "shipping_address": {
        "label": "Add a shipping address",
        "where": "Settings → Shipping addresses",
        "detail": "Billing uses the same address unless you give the card its own.",
    },
}


def _session(state: RunState) -> dict:
    return state.sessions[KEY]


def _new_session(_ctx: RunContext) -> dict:
    return {"loaded": False, "items": {}, "cards": {}, "addresses": {}, "default_address": None,
            "setup": None}


# ── loading ──────────────────────────────────────────────────────────────────

def offers_from_result(result: Any) -> list[dict]:
    """Every buyable pick in one stored result (v1 or v2), top pick first."""
    from app.matcha.services.matcha_work.agent_card.chat_flow import pick_offer

    from ..result import picks_block, read_result

    v2 = read_result(result)
    block = picks_block(v2) if v2 else None
    if not block:
        return []
    picks = [block.get("top_pick"), *(block.get("alternatives") or [])]
    offers = []
    for pick in picks:
        offer = pick_offer(pick) if isinstance(pick, dict) else None
        if offer:
            offers.append(offer)
    return offers


def _card_view(row) -> dict:
    from app.matcha.services.matcha_work import shipping_addresses as addresses

    return {
        "card_id": str(row["id"]),
        "brand": row["brand"],
        "last4": row["last4"],
        "label": card_vault.redact_pans(row["label"] or ""),
        "exp_month": row["exp_month"],
        "exp_year": row["exp_year"],
        "billing": addresses.billing_of(row),
    }


async def load_session(conn, ctx: RunContext, session: dict) -> None:
    from app.matcha.services.matcha_work import shipping_addresses as addresses

    rows = await conn.fetch(
        """SELECT id, result FROM mw_project_agent_runs
           WHERE channel_id = $1 AND requested_by = $2 AND kind = 'assistant' AND status = 'done'
             AND id <> $3
           ORDER BY created_at DESC LIMIT $4""",
        ctx.channel_id, ctx.user_id, ctx.run_id, RECENT_RESULTS * 3,
    )
    items: dict[str, dict] = {}
    results = 0
    for row in rows:
        offers = offers_from_result(decode_jsonb(row["result"], None))
        if not offers:
            continue
        results += 1
        for offer in offers:
            items[f"item-{len(items) + 1}"] = {**offer, "source_run_id": str(row["id"])}
        if results >= RECENT_RESULTS:
            break
    cards = await conn.fetch(
        """SELECT id, label, brand, last4, exp_month, exp_year, billing_address
           FROM mw_payment_cards WHERE user_id = $1 ORDER BY created_at""",
        ctx.user_id,
    )
    live = [c for c in cards if card_vault.expiry_ok(c["exp_month"], c["exp_year"])]
    saved = await addresses.list_addresses(conn, ctx.user_id)
    session["items"] = items
    session["cards"] = {f"card-{i + 1}": _card_view(c) for i, c in enumerate(live)}
    session["addresses"] = {f"address-{i + 1}": a for i, a in enumerate(saved)}
    session["default_address"] = next(
        (key for key, a in session["addresses"].items() if a.get("is_default")),
        next(iter(session["addresses"]), None),
    )
    missing = [k for k, have in (("payment_card", live), ("shipping_address", saved)) if not have]
    session["setup"] = {"missing": missing} if missing else None
    session["loaded"] = True


# ── formatting ───────────────────────────────────────────────────────────────

def _money(offer: dict) -> str | None:
    from app.matcha.services.matcha_work.agent_card.chat_flow import format_money

    return format_money(offer.get("amount"), offer.get("currency"))


def _card_text(card: dict) -> str:
    from app.matcha.services.matcha_work.agent_card.chat_flow import _card_label

    return _card_label({"brand": card.get("brand"), "last4": card.get("last4"), "label": card.get("label")})


def _host(url: str) -> str | None:
    try:
        return policy.encode_host(urlsplit(url).hostname or "")
    except ValueError:
        return None


def _address_hint(address: dict) -> str:
    """Enough to tell addresses apart ("Haley Smith, Oakland CA"); the street
    and phone stay out of the model's context."""
    place = " ".join(p for p in (address.get("city"), address.get("region")) if p)
    return ", ".join(p for p in (address.get("name"), place) if p)


def _model_view(session: dict) -> dict:
    """What the model is shown: ids to choose by, never a card number, a street or a phone."""
    return {
        "items": [
            {"item_id": key, "name": o["item_name"], "brand": o.get("brand"), "store": o.get("retailer"),
             "price": _money(o) or "not confirmed"}
            for key, o in session["items"].items()
        ],
        "cards": [{"card_id": key, "card": _card_text(c)} for key, c in session["cards"].items()],
        "addresses": [
            {"address_id": key, "ships_to": _address_hint(a), "default": bool(a.get("is_default"))}
            for key, a in session["addresses"].items()
        ],
    }


# ── tools ────────────────────────────────────────────────────────────────────

async def _prepare(ctx: RunContext, state: RunState, args: dict, left: float) -> ToolOutput:
    session = _session(state)
    async with connection_or_direct() as conn:
        await load_session(conn, ctx, session)
    view = _model_view(session)
    if session["setup"]:
        missing = session["setup"]["missing"]
        payload = {
            **view, "ready": False, "missing": missing,
            "next": ("The person has to add this in Settings before anything can be bought. "
                     "Finish now with a `purchase_setup` block and tell them what to add. Never ask "
                     "for a card number or an address in chat."),
        }
    elif not session["items"]:
        payload = {
            **view, "ready": False, "missing": ["item"],
            "next": ("Nothing to buy yet: none of their recent results in this conversation has a buyable "
                     "pick. Research it first (the result becomes buyable), or ask what they want."),
        }
    else:
        payload = {
            **view, "ready": True,
            "next": ("Call buy_item with the item_id they meant (\"it\" or \"the best pick\" is the top "
                     "pick of the latest result, item-1). If they have several cards and did not say "
                     "which, ask. The address defaults to their default address."),
        }
    return ToolOutput(
        payload=payload,
        audit={"items": len(session["items"]), "cards": len(session["cards"]),
               "addresses": len(session["addresses"]), "missing": payload.get("missing") or []},
        label="Checked your cards and addresses",
    )


def resolve_purchase(args: dict, state: RunState) -> dict:
    """The complete, frozen purchase. Raises ValueError (sent back to the
    model) when the ids do not name something prepare_purchase loaded."""
    from app.matcha.services.matcha_work import shipping_addresses as addresses

    session = _session(state)
    if not session["loaded"]:
        raise ValueError("call prepare_purchase first")
    if session["setup"]:
        raise ValueError("the person has to add a card and address in Settings first")
    item = session["items"].get(str(args.get("item_id") or ""))
    if item is None:
        raise ValueError(f"no item {args.get('item_id')!r}; use an item_id from prepare_purchase")
    cards = session["cards"]
    card_key = str(args.get("card_id") or "")
    if not card_key:
        if len(cards) != 1:
            raise ValueError("they have more than one card: ask which one (ask_user) and pass its card_id")
        card_key = next(iter(cards))
    card = cards.get(card_key)
    if card is None:
        raise ValueError(f"no card {card_key!r}; use a card_id from prepare_purchase")
    address_key = str(args.get("address_id") or "") or session["default_address"]
    address = session["addresses"].get(address_key or "")
    if address is None:
        raise ValueError(f"no address {address_key!r}; use an address_id from prepare_purchase")
    host = _host(item["checkout_url"])
    if host is None:
        raise ValueError("that item has no usable store link")
    return {
        "item": {k: item.get(k) for k in (
            "item_name", "brand", "retailer", "checkout_url", "amount", "currency", "image_url",
            "source_run_id",
        )},
        "host": host,
        "card": {k: card.get(k) for k in ("card_id", "brand", "last4", "label")},
        "shipping": addresses.snapshot(address),
        "billing": addresses.snapshot(card["billing"]) if card.get("billing") else None,
    }


def _targets(args: dict, state: RunState) -> tuple[Target, ...]:
    return (Target("domain", args["host"]),)


def _lines(args: dict) -> list[dict]:
    from app.matcha.services.matcha_work import shipping_addresses as addresses

    item = args["item"]
    lines = [{"label": "Item", "value": item["item_name"] + (f" ({item['brand']})" if item.get("brand") else "")}]
    lines.append({"label": "Price", "value": _money(item) or "Not confirmed (you'll see it at checkout)"})
    if item.get("retailer"):
        lines.append({"label": "Store", "value": item["retailer"]})
    lines.append({"label": "Card", "value": _card_text(args["card"])})
    lines.append({"label": "Ship to", "value": addresses.one_line(args["shipping"])})
    lines.append({
        "label": "Bill to",
        "value": addresses.one_line(args["billing"]) if args.get("billing") else "Same as shipping",
    })
    return lines


def _preview(args: dict, state: RunState) -> dict:
    money = _money(args["item"])
    title = f"Buy {args['item']['item_name']}" + (f" for {money}" if money else "")
    return {"title": title[:160], "lines": [*_lines(args), {"label": "Payment", "value": TEST_MODE_NOTE}]}


async def _buy(ctx: RunContext, state: RunState, args: dict, left: float) -> ToolOutput:
    from app.matcha.services.matcha_work.agent_card import test_charge

    item, frozen_card = args["item"], args["card"]
    await ctx.progress.note(f"Buying {item['item_name']}…", force=True)
    async with connection_or_direct() as conn:
        card = await conn.fetchrow(
            """SELECT id, brand, last4, exp_month, exp_year FROM mw_payment_cards
               WHERE id = $1 AND user_id = $2""",
            UUID(frozen_card["card_id"]), ctx.user_id,
        )
        if card is None or not card_vault.expiry_ok(card["exp_month"], card["exp_year"]):
            return ToolOutput(payload={
                "error": f"The card ending {frozen_card['last4']} was removed or has expired. Nothing was bought.",
            })
        purchase_id = await conn.fetchval(
            """INSERT INTO mw_agent_purchase_requests
                   (company_id, project_id, task_id, run_id, prompt_id, user_id, card_id, card_last4,
                    item_name, retailer, checkout_url, amount, currency, channel_id,
                    shipping_address, billing_address)
               VALUES ($1, NULL, NULL, $2, NULL, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                       $12::jsonb, $13::jsonb)
               RETURNING id""",
            ctx.company_id, ctx.run_id, ctx.user_id, card["id"], card["last4"], item["item_name"],
            item.get("retailer"), item["checkout_url"], item.get("amount"), item.get("currency"),
            ctx.channel_id, json.dumps(args["shipping"]),
            json.dumps(args["billing"]) if args.get("billing") else None,
        )
    order_ref = str(purchase_id)[:8].upper()
    lines = [*_lines(args), {"label": "Order ref", "value": order_ref, "mono": True}]
    link_url = item["checkout_url"] if str(item["checkout_url"]).startswith("https://") else None
    key = test_charge.test_key()
    if key is None or item.get("amount") is None or not item.get("currency"):
        why = "No verified price, so nothing was charged." if key else "Nothing was charged."
        return ToolOutput(
            payload={"status": "handoff", "order_ref": order_ref,
                     "note": f"{why} The person finishes checkout at the store's link."},
            receipt={
                "status": "handoff", "title": f"Ready to check out: {item['item_name']}"[:160],
                "lines": lines, "note": f"{why} Finish checkout at the store.",
                "link": {"label": "Finish checkout", "url": link_url} if link_url else None,
            },
            audit={"status": "handoff", "purchase_id": str(purchase_id)},
        )
    outcome = await test_charge.charge(
        key, purchase_id=purchase_id, amount=item["amount"], currency=item["currency"],
        brand=card["brand"], description=f"Espresso assistant test purchase: {item['item_name']}",
        metadata={"purchase_id": purchase_id, "run_id": ctx.run_id, "card_last4": card["last4"]},
    )
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE mw_agent_purchase_requests
               SET status = $2, stripe_payment_intent_id = $3, charge_error = $4
               WHERE id = $1""",
            purchase_id, outcome["status"], outcome["payment_intent_id"], outcome["error"],
        )
    if outcome["status"] != "test_charged":
        return ToolOutput(
            payload={"error": f"The test charge failed: {outcome['error']}", "order_ref": order_ref},
            receipt={"lines": lines, "note": f"The Stripe test charge failed: {outcome['error']}"},
            audit={"status": "test_failed", "purchase_id": str(purchase_id)},
        )
    lines.append({"label": "Payment", "value": f"{outcome['payment_intent_id']} (succeeded)", "mono": True})
    return ToolOutput(
        payload={"status": "test_charged", "order_ref": order_ref,
                 "note": "Charged in Stripe test mode. No real money moved and no real order was placed."},
        receipt={
            "title": f"Bought {item['item_name']}"[:160], "lines": lines,
            "note": "Stripe TEST mode: no real money moved and no real order was placed.",
            "link": {"label": "View at store", "url": link_url} if link_url else None,
        },
        audit={"status": "test_charged", "purchase_id": str(purchase_id),
               "payment_intent_id": outcome["payment_intent_id"]},
    )


PREPARE_TOOL = AgentTool(
    name="prepare_purchase", effect="read", step_kind="read", handler=_prepare,
    description=(
        "Before buying anything: loads what can be bought (the picks from the person's recent results "
        "in this conversation, each with an item_id), their saved cards and their shipping addresses, "
        "and says what is missing."
    ),
    parameters={"type": "object", "properties": {}},
    max_calls=2,
    timeout_seconds=20,
)

BUY_TOOL = AgentTool(
    name="buy_item", effect="commit", step_kind="commit", handler=_buy,
    description=(
        "Buy one item with a saved card, shipped to a saved address. Use ids from prepare_purchase. "
        "The person is always shown the purchase and asked to confirm first."
    ),
    parameters={"type": "object", "properties": {
        "item_id": {"type": "string", "description": "item-N from prepare_purchase"},
        "card_id": {"type": "string", "description": "card-N; may be left out when they have one card"},
        "address_id": {"type": "string", "description": "address-N; left out means their default"},
    }, "required": ["item_id"]},
    timeout_seconds=40, min_seconds_left=40,
    too_late_message="Not enough time left to buy it; tell the person to ask again.",
    resolve=resolve_purchase, targets=_targets, preview=_preview,
    ceilings=((3, 3600), (10, 86400)),
    always_confirm=True,
)


_SETUP_BLOCK: dict[str, Any] = {
    "type": "object",
    "description": "What the person must add in Settings before buying. Filled in by the system; send it empty.",
    "properties": {},
}

_PROMPT = """Buying:
- When the person asks to buy something ("buy it", "purchase the best pick", "order the second one"), call prepare_purchase, then buy_item. "It" or "the best pick" means the top pick of the latest result (item-1).
- If prepare_purchase says a card or address is missing, finish with a `purchase_setup` block and tell them what to add. Never ask for card numbers or addresses in chat.
- buy_item always asks the person to confirm first. That is expected: stop there.
- Purchases are test purchases: no real money moves. Report exactly what buy_item returned."""


def setup_block(state: RunState) -> dict | None:
    session = state.sessions.get(KEY) or {}
    setup = session.get("setup")
    if not setup:
        return None
    return {
        "type": "purchase_setup",
        "missing": list(setup["missing"]),
        "steps": [{"key": key, **SETUP_STEPS[key]} for key in setup["missing"]],
    }


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    block = setup_block(state)
    if block is None:
        return None, ["Dropped a purchase_setup block: nothing is missing"]
    # Server-authored: what the model wrote in the block is ignored.
    return block, []


def auto_blocks(state: RunState) -> list[dict]:
    block = setup_block(state)
    return [block] if block else []


def build() -> Ability:
    return Ability(
        key=KEY,
        label="Buying",
        tools=(PREPARE_TOOL, BUY_TOOL),
        prompt_block=lambda _ctx: _PROMPT,
        private_only=True,
        consent_version=consent.current_version(KEY),
        allowance=ALLOWANCE,
        session_factory=_new_session,
        block_schemas={"purchase_setup": _SETUP_BLOCK},
        gate=gate_block,
        auto_blocks=auto_blocks,
    )
