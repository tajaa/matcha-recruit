"""A store's policies — refund, shipping, terms, privacy (`cappe_site_policies`).

One plain-text body per kind, written by the owner (from a starter we offer),
served at `/policies/<kind>` on the store and linked from its footer, its
sitemap, the bag ("By placing your order you agree to…") and Stripe's payment
page. No row = no page and no link.

Plain text on purpose: the body is the owner's words, rendered escaped, with a
blank line between paragraphs. The starters are prompts to edit, not legal
advice, and say so.

Checkout points at the policies instead of asking Stripe to collect consent:
Stripe's `consent_collection.terms_of_service` refuses to open a payment page
unless the CONNECTED account has its own terms URL set in its own Stripe
settings, which a seller may never have done — it would break their checkout.
"""
from __future__ import annotations

from html import escape
from typing import Optional

KINDS = ("refund", "shipping", "terms", "privacy")
TITLES = {
    "refund": "Refund policy",
    "shipping": "Shipping policy",
    "terms": "Terms of service",
    "privacy": "Privacy policy",
}
MAX_BODY = 20_000

# What a store must publish before it can go live selling physical goods
# (services/readiness.py): a buyer of a parcel is owed both.
REQUIRED_FOR_PHYSICAL = ("refund", "shipping")

_STARTERS = {
    "refund": (
        "Returns\n"
        "You can return most items within 30 days of delivery for a full refund. Items must be unused "
        "and in their original packaging.\n\n"
        "How to return\n"
        "Reply to your order email or contact us, and we'll tell you where to send it. Return postage is "
        "paid by you unless the item arrived damaged or wrong.\n\n"
        "Refunds\n"
        "We refund to your original payment method within 5 business days of receiving the return.\n\n"
        "Exceptions\n"
        "Personalised and perishable items can't be returned unless they arrive damaged."
    ),
    "shipping": (
        "Processing\n"
        "Orders leave us within the handling time shown at checkout.\n\n"
        "Delivery\n"
        "Delivery times and prices for each option are shown in your bag before you pay. You'll get an "
        "email with tracking when your order ships.\n\n"
        "Lost or damaged parcels\n"
        "Contact us within 14 days of the expected delivery date and we'll replace or refund it."
    ),
    "terms": (
        "These terms apply when you buy from us.\n\n"
        "Orders\n"
        "Placing an order is an offer to buy. We confirm it by email; we may cancel and refund an order "
        "we can't fulfil.\n\n"
        "Prices\n"
        "Prices are shown in the store's currency. Tax and delivery are shown before you pay.\n\n"
        "Returns\n"
        "See our refund policy.\n\n"
        "Contact\n"
        "Questions about an order? Reply to your order email."
    ),
    "privacy": (
        "What we collect\n"
        "Your name, email, delivery address and order details, so we can fulfil and support your order.\n\n"
        "Payments\n"
        "Card payments are handled by Stripe; we never see or store your card number.\n\n"
        "Who we share it with\n"
        "Only the services that deliver your order (payment, shipping and email). We don't sell your data.\n\n"
        "Your rights\n"
        "Contact us to see, correct or delete what we hold about you."
    ),
}


def starter(kind: str) -> str:
    """A starting point the owner edits — not legal advice."""
    return _STARTERS[kind]


def policy_path(kind: str) -> str:
    return f"/policies/{kind}"


async def policy_kinds(conn, site_id) -> list[str]:
    """The kinds this store has published, in the fixed order."""
    rows = await conn.fetch("SELECT kind FROM cappe_site_policies WHERE site_id = $1", site_id)
    have = {r["kind"] for r in rows}
    return [k for k in KINDS if k in have]


def links(kinds) -> list[dict]:
    """[{kind, title, url}] for the footer, the bag and the sitemap."""
    return [{"kind": k, "title": TITLES[k], "url": policy_path(k)} for k in KINDS if k in set(kinds or ())]


def body_html(body: str) -> str:
    """The owner's text, escaped: a blank line starts a paragraph, a single
    line break stays one, and a short first line of a paragraph (no full stop)
    reads as its heading."""
    out = []
    for block in (body or "").replace("\r\n", "\n").split("\n\n"):
        lines = [line.rstrip() for line in block.strip().split("\n") if line.strip()]
        if not lines:
            continue
        if len(lines) > 1 and len(lines[0]) <= 60 and not lines[0].endswith((".", ":", "?", "!")):
            out.append(f"<h2>{escape(lines[0])}</h2>")
            lines = lines[1:]
        out.append("<p>" + "<br>".join(escape(line) for line in lines) + "</p>")
    return "".join(out)


def checkout_note(site_name: Optional[str], origin: Optional[str], kinds) -> Optional[str]:
    """The line Stripe's payment page shows above the pay button: what the
    buyer agrees to by paying, with where to read it. None without terms or a
    refund policy, or without an address to point at."""
    named = [(TITLES[k].lower() if k != "terms" else "terms", k) for k in ("terms", "refund") if k in set(kinds or ())]
    if not named or not origin:
        return None
    store = (site_name or "the store").strip()
    parts = " and ".join(f"{label} ({origin.rstrip('/')}{policy_path(k)})" for label, k in named)
    return f"By paying you agree to {store}'s {parts}."[:1200]
