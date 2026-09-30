"""Espresso's questions about a finished agent card, in the project chat.

When a run finishes, Espresso asks in the card's project discussion "want to
see what I found?". Yes posts a readable summary of the result (the full page
stays on the card). For a shopping result, and for a user allowed to buy, it
then asks "want to buy it?", then which saved card, and records a purchase
handoff: the exact item, retailer, checkout link and verified total the user
approved. Nothing real is charged: by default an approved purchase with a
verified total is charged in Stripe TEST mode (`test_charge.py`, test keys
only, no card number sent); otherwise the user finishes checkout at the link.

Every question is a `mw_agent_card_prompts` row. Answers are parsed
deterministically (no model call):
  * a threaded reply goes to the question it replies to — the only way to
    answer "buy it?" and "which card?", and only by the person who owns them;
  * a plain "yes" (a small, explicit set) with no reply target shows the
    channel's newest open result. Nothing else in ordinary chat is an answer,
    so "ok" to a colleague can never approve a purchase.
A question is claimed with one conditional UPDATE, under the same per-card
advisory lock `enqueue` takes, and only while its run is still the card's
current result; a newer run supersedes it.

Card numbers never travel through chat or the model: saved cards are added
through the payment-cards API, chat only ever shows the brand and last 4
digits, and a card number typed in reply to a question, or by someone with an
open purchase question in the channel, is removed before the message is
stored or broadcast (`redact_card_numbers`, used by the chat socket and the
message-edit endpoint).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.core.services import card_vault
from app.database import connection_or_direct, decode_jsonb

from ..project_agent.chat import ESPRESSO_MENTION, broadcast_espresso_message, persist_espresso_message
from . import test_charge

logger = logging.getLogger(__name__)

PROMPT_METADATA_KIND = "agent_card_prompt"
RESULT_METADATA_KIND = "agent_card_result"
RECEIPT_METADATA_KIND = "agent_card_receipt"
# Socket event when a question closes (answered / superseded), so every open
# chat drops its buttons without a reload. Expiry needs no event: questions
# carry `expires_at`.
PROMPT_UPDATED_EVENT = "agent_card_prompt_updated"
OFFER_TTL = timedelta(days=7)
PURCHASE_TTL = timedelta(days=2)
PICK_CARD_TTL = timedelta(hours=2)
MAX_MESSAGE_CHARS = 3500
PURCHASE_KINDS = ("purchase", "pick_card")
# Questions the Espresso assistant asks (agent_runtime/prompts.py). They share
# this table and this message card, and are answered over there.
ASSISTANT_KINDS = ("ask_user", "confirm_action")

ADD_CARD_HINT = "Add one in Espresso under Settings → Payment cards"
STALE_REPLY = "That result was replaced by a newer run on the card, so I've closed this question."

# Threaded replies: a generous vocabulary, because the reply target already
# says which question is being answered.
_YES = {
    "y", "yes", "yeah", "yea", "yep", "yup", "sure", "ok", "okay", "k", "please",
    "yes please", "show me", "show it", "go ahead", "do it", "buy it", "purchase",
    "purchase it", "sounds good", "absolutely", "definitely", "lets do it", "let s do it",
    "yes buy it", "yes show me",
}
_NO = {
    "n", "no", "nope", "nah", "not now", "later", "skip", "cancel", "no thanks",
    "no thank you", "dont", "don t", "do not", "stop", "never mind", "nevermind",
}
# Plain messages (no reply target): only an explicit request to see a result.
_PLAIN_YES = {"yes", "yes please", "show me", "show it", "yes show me"}
_LAST4 = re.compile(r"^(?:use\s+)?(?:the\s+)?(?:card\s+)?(?:ending\s+)?(?:in\s+)?(\d{4})$")
_CHOICE = re.compile(r"^(?:use\s+)?(?:card\s+|number\s+|option\s+)?([1-9])$")


@dataclass(frozen=True)
class Answer:
    kind: str  # "yes" | "no" | "last4" | "choice"
    value: str | None = None


def _normalize(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", ESPRESSO_MENTION.sub("", text).lower())
    return " ".join(normalized.split())


def parse_answer(text: str) -> Answer | None:
    """A threaded reply's answer: yes / no / last 4 digits / a numbered choice.
    Every buy command that answers a plain message ("buy", "order it") is a
    yes here too: a threaded reply is never stricter than a plain one."""
    if not isinstance(text, str) or len(text) > 60:
        return None
    normalized = _normalize(text)
    if not normalized:
        return None
    if normalized in _YES or is_buy_intent(normalized):
        return Answer("yes")
    if normalized in _NO:
        return Answer("no")
    match = _LAST4.match(normalized)
    if match:
        return Answer("last4", match.group(1))
    match = _CHOICE.match(normalized)
    if match:
        return Answer("choice", match.group(1))
    return None


def is_plain_yes(text: str) -> bool:
    """Whether a plain (unthreaded) message is an explicit yes. Synchronous
    and allocation-light: it runs on the chat socket's hot path."""
    return isinstance(text, str) and len(text) <= 30 and _normalize(text) in _PLAIN_YES


_NEGATION = re.compile(r"\b(don t|dont|do not|not|no|never|cancel|stop|wait|hold|later)\b")


# A buy phrase answers a question only when the WHOLE message is a short
# command aimed back at the offered pick ("buy it", "yes, buy the best one",
# "go ahead and order it, please") or a bare "buy" / "place the order". A buy
# word inside an ordinary sentence ("find me a rain jacket to buy that is
# waterproof", "I want to buy a desk, is it worth it") is new business, never
# a yes to whatever buy question happens to be open.
_BUY_LEAD = (
    r"(?:(?:yes|yeah|yep|ok|okay|sure|please|pls|go ahead and|let s|lets|then|just|"
    r"i ll|i will|i want to|i d like to|id like to|can you|could you|you can)\s+)*"
)
_BUY_TARGET = (
    r"(?:it|this|that|this one|that one|the pick|your pick|the top pick|top pick|"
    r"the (?:best|top|first|recommended|cheapest) (?:one|pick|option))"
)
_BUY_TAIL = r"(?:\s+(?:please|pls|now|then|for me|thanks|thank you))*"
_BUY_COMMAND = re.compile(rf"^{_BUY_LEAD}(?:buy|purchase|order)\s+{_BUY_TARGET}{_BUY_TAIL}$")
_BARE_BUY = {"buy", "purchase", "order", "buy now", "purchase now", "order now", "checkout", "check out",
             "place the order", "place order", "yes buy", "yes purchase"}


def is_buy_intent(text: str) -> bool:
    """An explicit, un-negated "buy it" aimed at the offered pick. Only ever
    applied to the sender's OWN open purchase question, so "ok" or "sure" to a
    colleague, or a new "find me … to buy", never buys anything."""
    if not isinstance(text, str) or len(text) > 80:
        return False
    normalized = _normalize(text)
    if _NEGATION.search(normalized):
        return False
    return normalized in _BARE_BUY or bool(_BUY_COMMAND.match(normalized))


def plain_card_choice(text: str) -> Answer | None:
    """A bare card number ("1") or last 4 ("4242") typed as a plain message."""
    if not isinstance(text, str) or len(text) > 30:
        return None
    answer = parse_answer(text)
    return answer if answer and answer.kind in ("choice", "last4") else None


def might_answer_plain(text: str) -> bool:
    """Hot-path guard for a plain message: could it answer an agent-card question?"""
    return is_plain_yes(text) or is_buy_intent(text) or plain_card_choice(text) is not None


# A plain "yes" answers the sender's own buy / card question only right after
# it was asked; after that it takes a threaded reply or an explicit "buy it".
FRESH_PURCHASE_QUESTION = timedelta(minutes=10)


PURCHASE_ALLOWLIST_ENV = "AGENT_PURCHASE_ALLOWED_EMAILS"


def purchases_allowed(user) -> bool:
    """Buying through chat is internal-only in v1: platform admins, plus the
    accounts listed (comma-separated emails) in `AGENT_PURCHASE_ALLOWED_EMAILS`."""
    if user is None:
        return False
    if (getattr(user, "role", "") or "").lower() == "admin":
        return True
    email = (getattr(user, "email", "") or "").strip().lower()
    allowed = {e.strip().lower() for e in (os.getenv(PURCHASE_ALLOWLIST_ENV) or "").split(",") if e.strip()}
    return bool(email) and email in allowed


# ── formatting ────────────────────────────────────────────────────────────────

def _ticket_token(task_id, title: str, column: str | None) -> str:
    safe = " ".join((title or "Agent card").split())
    safe = safe.replace("⟦", "").replace("⟧", "").replace("|", "/")[:200]
    label = (column or "review").replace("_", " ").title()
    return f"⟦ticket:{task_id}|{safe}|{label}⟧"


def format_money(amount, currency: str | None) -> str | None:
    if amount is None:
        return None
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return None
    code = (currency or "USD").upper()
    if code == "USD":
        return f"${value:,.2f}"
    return f"{value:,.2f} {code}"


def _pick_price(pick: dict) -> str | None:
    price = pick.get("price") or {}
    return format_money(price.get("amount"), price.get("currency"))


def _rating_line(pick: dict) -> str | None:
    rating = pick.get("rating") or {}
    if rating.get("value") is None:
        return None
    scale = rating.get("scale") or 5
    line = f"{rating['value']:g}/{scale:g}"
    if rating.get("count"):
        line += f" from {rating['count']:,} ratings"
    return line


def _short(text: str, limit: int) -> str:
    """Clip to `limit` chars, preferring a sentence end, else a word."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= limit // 2:
        return cut[: end + 1]
    if text[limit] != " ":  # mid-word: drop the partial word
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def _http_url(url) -> str | None:
    url = str(url or "").strip()
    return url if url.startswith(("https://", "http://")) else None


def _image_url(pick: dict) -> str | None:
    """The first rehosted photo. Only https (our CDN) ever reaches a client."""
    for image in pick.get("images") or []:
        url = str((image or {}).get("url") or "")
        if url.startswith("https://"):
            return url
    return None


def _pick_view(pick: dict, *, full: bool) -> dict:
    buy = next((b for b in (pick.get("buy_links") or []) if _http_url(b.get("url"))), None)
    view = {
        "name": pick["name"],
        "brand": pick.get("brand") or None,
        "image_url": _image_url(pick),
        "price_text": _pick_price(pick),
        "buy_url": buy["url"] if buy else None,
        "retailer": (buy.get("retailer") or None) if buy else None,
    }
    if full:
        rating = pick.get("rating") or {}
        view["rating"] = (
            {"value": rating["value"], "scale": rating.get("scale") or 5, "count": rating.get("count")}
            if rating.get("value") is not None else None
        )
        view["why"] = [w for w in (pick.get("why") or []) if w][:3]
    return view


def _clock(iso: str | None) -> str:
    """"2026-11-12T07:05:00" → "7:05am" (the airport's local time)."""
    try:
        hour, minute = int(iso[11:13]), int(iso[14:16])
    except (TypeError, ValueError, IndexError):
        return ""
    return f"{(hour % 12) or 12}:{minute:02d}{'am' if hour < 12 else 'pm'}"


def _flight_option_view(option: dict) -> dict:
    return {
        "label": option.get("label"),
        "price_text": format_money(option.get("total_amount"), option.get("currency")),
        "total_with_bags_text": (
            format_money(option.get("true_total_amount"), option.get("currency"))
            if option.get("true_total_amount") and option.get("true_total_amount") != option.get("total_amount")
            else None
        ),
        "bag_note": option.get("bag_note"),
        "carriers": list(option.get("carriers") or [])[:3],
        "ticketing": option.get("ticketing") or "single",
        "slices": [
            {
                "origin": sl.get("origin"), "destination": sl.get("destination"),
                "departing_at": sl.get("departing_at"), "arriving_at": sl.get("arriving_at"),
                "stops": sl.get("stops"), "duration_minutes": sl.get("duration_minutes"),
                "flight_numbers": [s.get("flight_number") for s in sl.get("segments") or []][:4],
            }
            for sl in option.get("slices") or []
        ],
        "warning": (option.get("warnings") or [None])[0],
    }


def flights_view(flights: dict | None) -> dict | None:
    """The chat card's flight rows: the top 3 chosen offers, compact."""
    if not isinstance(flights, dict) or not flights.get("options"):
        return None
    return {
        "query_summary": flights.get("query_summary") or "",
        "test_data": bool(flights.get("test_data")),
        "searched_at": flights.get("searched_at"),
        "options": [_flight_option_view(o) for o in flights["options"][:3] if isinstance(o, dict)],
    }


def _flight_line(option: dict) -> str:
    view = _flight_option_view(option)
    price = view["price_text"] or ""
    if view["total_with_bags_text"]:
        price += f" ({view['total_with_bags_text']} with bags)"
    legs = [
        f"{sl['origin']} {_clock(sl['departing_at'])} → {sl['destination']} {_clock(sl['arriving_at'])}, "
        + ("nonstop" if not sl["stops"] else f"{sl['stops']} stop{'s' if sl['stops'] != 1 else ''}")
        for sl in view["slices"]
    ]
    parts = [price, ", ".join(view["carriers"]), " / ".join(legs)]
    if view["ticketing"] == "separate":
        parts.append("separate tickets")
    return f"{view['label'] or 'Option'}: " + " · ".join(p for p in parts if p)


def result_view(result: dict) -> dict:
    """What the chat card renders: headline, a short summary, the top pick
    (photo, price, rating, reasons, buy link) and up to 3 alternatives, or,
    for a flight search, the top 3 chosen offers."""
    pick = result.get("top_pick") if isinstance(result.get("top_pick"), dict) else None
    flights = flights_view(result.get("flights"))
    return {
        "headline": result.get("headline") or "",
        "summary": _short(result.get("summary") or "", 420),
        "answer_type": result.get("answer_type") or ("recommendation" if pick else "answer"),
        "top_pick": _pick_view(pick, full=True) if pick else None,
        "alternatives": [
            _pick_view(a, full=False) for a in (result.get("alternatives") or [])[:3] if isinstance(a, dict)
        ],
        "sections": [] if pick or flights else [
            s["heading"] for s in (result.get("sections") or [])[:6] if isinstance(s, dict) and s.get("heading")
        ],
        "flights": flights,
        "source_count": len(result.get("sources") or []),
        "confidence": result.get("confidence"),
    }


def format_result(result: dict, *, task_id, title: str, column: str | None) -> str:
    """Plain-text fallback for the result card (notifications, older apps):
    short, no raw URLs. The card itself renders `result_view`."""
    lines = [_ticket_token(task_id, title, column), result.get("headline") or title]
    summary = _short(result.get("summary") or "", 280)
    if summary:
        lines += ["", summary]
    pick = result.get("top_pick")
    if pick:
        facts = [f for f in (_pick_price(pick), _rating_line(pick)) if f]
        name = pick["name"] + (f" by {pick['brand']}" if pick.get("brand") else "")
        lines += ["", "Top pick: " + " · ".join([name, *facts])]
    alternatives = [a["name"] for a in (result.get("alternatives") or [])[:3]]
    if alternatives:
        lines.append("Also compared: " + ", ".join(alternatives))
    flights = result.get("flights") if isinstance(result.get("flights"), dict) else None
    if flights and flights.get("options"):
        lines.append("")
        if flights.get("test_data"):
            lines.append("TEST DATA: sandbox fares, not real prices.")
        lines += [_flight_line(o) for o in flights["options"][:3] if isinstance(o, dict)]
    elif not pick and result.get("sections"):
        lines += ["", "Covers: " + ", ".join(s["heading"] for s in result["sections"][:6] if s.get("heading"))]
    lines += ["", "The full page, with photos, reviews and sources, is on the card."]
    text = "\n".join(lines).strip()
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 1].rstrip() + "…"
    return text


def _button(label: str, reply: str | None = None, *, primary: bool = False, detail: str | None = None) -> dict:
    """A quick-reply button: the app sends `reply` as a threaded reply to the
    question, so it goes through exactly the same path as typing it."""
    return {"label": label, "reply": reply or label, "style": "primary" if primary else "secondary",
            "detail": detail}


def _show_view(*, reworked: bool) -> dict:
    # The card's heading. Fixed text: the task title (user-written) stays in the
    # message's ticket marker and is never parsed back out.
    question = ("I reworked it. Want to see the new result?" if reworked
                else "I finished it. Want to see what I found?")
    return {"question": question, "buttons": [_button("Show me", primary=True), _button("Not now")]}


def _purchase_view(offer: dict) -> dict:
    return {
        "question": "Want me to buy it?",
        "offer": {
            "item_name": offer["item_name"],
            "brand": offer.get("brand"),
            "retailer": offer.get("retailer"),
            "price_text": format_money(offer.get("amount"), offer.get("currency")),
            "image_url": offer.get("image_url"),
        },
        "buttons": [_button("Buy it", primary=True), _button("No thanks")],
    }


def _pick_card_view(options: list[dict]) -> dict:
    buttons = []
    for o in options:
        detail = ", ".join(
            d for d in (
                card_vault.redact_pans(o.get("label") or ""),
                f"expires {int(o['exp_month']):02d}/{int(o['exp_year']) % 100:02d}" if o.get("exp_month") else "",
            ) if d
        )
        buttons.append(_button(
            f"{_BRANDS.get(o.get('brand') or '', 'Card')} •••• {o['last4']}",
            f"Use card {o['n']}", primary=len(options) == 1, detail=detail or None,
        ))
    buttons.append(_button("Cancel"))
    return {"question": "Use this card?" if len(options) == 1 else "Which card should I use?", "buttons": buttons}


def receipt_view(payload: dict, *, card: dict, purchase_id, status: str,
                 payment_intent_id: str | None = None, error: str | None = None) -> dict:
    """The receipt card. `status`: paid_test (Stripe test charge succeeded),
    failed, approved (handoff: nothing charged) or no_price."""
    from datetime import datetime, timezone

    return {
        "status": status,
        "test_mode": True,
        "item_name": payload["item_name"],
        "brand": payload.get("brand"),
        "image_url": payload.get("image_url"),
        "retailer": payload.get("retailer"),
        "total_text": format_money(payload.get("amount"), payload.get("currency")),
        "currency": (payload.get("currency") or "").upper() or None,
        "card_text": _card_label(card),
        "payment_intent_id": payment_intent_id,
        "order_ref": str(purchase_id)[:8].upper(),
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product_url": _http_url(payload.get("checkout_url")),
        "error": error,
    }


def purchase_offer(result: dict) -> dict | None:
    """The one thing a yes would buy: the top pick at its first verified buy link.

    The total is the pick's source-checked price (`price`, gated on its source
    URL, with its currency) or nothing: a buy link's own `price` is only the
    model's claim and has no currency, so it is never offered as the total.
    Frozen into the question's payload so the purchase that gets approved is
    exactly the item, store, link and total the user was shown.
    """
    if not isinstance(result, dict) or result.get("answer_type") != "recommendation":
        return None
    pick = result.get("top_pick")
    if not isinstance(pick, dict):
        return None
    link = next(
        (b for b in (pick.get("buy_links") or []) if str(b.get("url") or "").startswith(("https://", "http://"))),
        None,
    )
    if not link:
        return None
    price = pick.get("price") or {}
    verified = price.get("amount") is not None and price.get("currency")
    return {
        "item_name": pick["name"],
        "brand": pick.get("brand") or None,
        "retailer": link.get("retailer") or None,
        "checkout_url": link["url"],
        "amount": price["amount"] if verified else None,
        "currency": price["currency"] if verified else None,
        "image_url": _image_url(pick),
    }


def _offer_line(offer: dict) -> str:
    parts = [offer["item_name"]]
    if offer.get("retailer"):
        parts.append(f"at {offer['retailer']}")
    money = format_money(offer.get("amount"), offer.get("currency"))
    parts.append(f"for {money}" if money else "(price not confirmed)")
    return " ".join(parts)


def format_receipt(payload: dict, *, card: dict, purchase_id, payment_intent_id: str, task_id) -> str:
    """The "all done" message after a successful Stripe test charge."""
    from datetime import datetime, timezone

    item = payload["item_name"] + (f" ({payload['brand']})" if payload.get("brand") else "")
    code = (payload.get("currency") or "USD").upper()
    lines = [
        "All done. Here's your receipt.",
        "",
        "Receipt (Stripe TEST mode, no real money moved)",
        f"Item: {item}",
    ]
    if payload.get("retailer"):
        lines.append(f"Store: {payload['retailer']}")
    lines += [
        f"Total: {format_money(payload['amount'], code)} {code}",
        f"Paid with: {_card_label(card)}",
        f"Payment: {payment_intent_id} (succeeded)",
        f"Order ref: {str(purchase_id)[:8].upper()}",
        f"Date: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        "",
        f"It's saved on ⟦ticket:{task_id}|the card|Review⟧ under Purchases.",
    ]
    return "\n".join(lines)


_BRANDS = {"visa": "Visa", "mastercard": "Mastercard", "amex": "Amex", "discover": "Discover"}


def _card_label(card: dict, *, with_expiry: bool = False) -> str:
    brand = _BRANDS.get(card.get("brand") or "", "card")
    text = f"{brand} ending {card['last4']}"
    details = []
    if card.get("label"):
        # Labels are validated on save; redact again in case an older row slipped through.
        details.append(card_vault.redact_pans(card["label"]))
    if with_expiry and card.get("exp_month") and card.get("exp_year"):
        details.append(f"expires {int(card['exp_month']):02d}/{int(card['exp_year']) % 100:02d}")
    if details:
        text += f" ({', '.join(details)})"
    return text


# ── storage helpers ───────────────────────────────────────────────────────────

# Is there a run on this card newer than the question's own run that still
# counts (queued, running or done)? A failed or never-dispatched newer run does
# not replace the result the question is about.
_NEWER_RUN_SQL = """SELECT EXISTS(
    SELECT 1 FROM mw_project_agent_runs n
    JOIN mw_project_agent_runs r ON r.id = $2
    WHERE n.task_id = $1 AND n.kind = 'card_agent' AND n.id <> r.id
      AND n.created_at > r.created_at
      AND n.status IN ('queued', 'running', 'done')
)"""


async def _lock_card(conn, task_id) -> None:
    """The per-card lock `enqueue` takes (caller's transaction), so a question
    and a new run on the same card are strictly ordered."""
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{task_id}:card_agent")


async def _superseded(conn, task_id, run_id) -> bool:
    return bool(await conn.fetchval(_NEWER_RUN_SQL, task_id, run_id))


async def close_open_prompts(conn, task_id: UUID) -> list[dict]:
    """Close a card's open questions (a new run started). Returns the socket
    events to send once the caller's transaction commits
    (`broadcast_prompt_updates`)."""
    rows = await conn.fetch(
        """UPDATE mw_agent_card_prompts SET status = 'superseded'
           WHERE task_id = $1 AND status = 'open'
           RETURNING id, channel_id, kind""",
        task_id,
    )
    return [prompt_update(row, "superseded") for row in rows]


def public_answer(answer: str | None) -> str | None:
    """A closed question's answer as every channel member may see it. The
    stored card answer carries the buyer's last 4 (`card:4242`); the chat
    history and socket events only ever say a card was chosen."""
    if answer and answer.startswith("card:"):
        return "card"
    return answer


def answer_text(kind: str, answer: str | None) -> str | None:
    """How a closed question's answer reads on its card, for everyone in the
    channel. Never the buyer's card details: those stay on their receipt."""
    if not answer:
        return None
    if answer == "card" or answer.startswith("card:"):
        return "Card chosen"
    if kind == "show_result":
        return "Showed the result" if answer == "yes" else "Skipped for now"
    if kind == "purchase":
        return "Going ahead with the purchase" if answer == "yes" else "Not buying it"
    return "Cancelled" if answer == "no" else "Answered"


def prompt_update(row, status: str, answer: str | None = None) -> dict:
    """The `agent_card_prompt_updated` socket event for one closed question."""
    return {
        "type": PROMPT_UPDATED_EVENT,
        "channel_id": str(row["channel_id"]),
        "prompt_id": str(row["id"]),
        "status": status,
        "answer": public_answer(answer),
        "answer_text": answer_text(row["kind"], answer),
    }


async def _publish_prompt_update(update: dict) -> None:
    from ..project_task_notifications import broadcast_channel_event

    await broadcast_channel_event(UUID(update["channel_id"]), update)


async def broadcast_prompt_updates(updates: list[dict]) -> None:
    """Tell every open chat these questions closed. Best-effort: a reload
    reads the same state (`overlay_prompt_statuses`), and a late button press
    is refused by the claim anyway."""
    for update in updates:
        try:
            await _publish_prompt_update(update)
        except Exception:
            logger.warning("agent-card question update broadcast failed", exc_info=True)


async def user_has_open_purchase_question(conn, channel_id: UUID, user_id) -> bool:
    return bool(await conn.fetchval(
        """SELECT EXISTS(
               SELECT 1 FROM mw_agent_card_prompts
               WHERE channel_id = $1 AND owner_user_id = $2
                 AND kind IN ('purchase', 'pick_card')
                 AND status = 'open' AND expires_at > NOW()
           )""",
        channel_id, user_id,
    ))


async def redact_card_numbers(
    conn, *, channel_id: UUID, user_id, replied_prompt_id: UUID | None, content: str | None,
) -> tuple[str | None, bool]:
    """(content to store, whether a card number was removed).

    Applies to a reply to one of Espresso's questions, or to a message from
    someone who has an open "buy it?" / "which card?" question in this
    channel. Ordinary chat is never rewritten. The lookup runs only for text
    that holds a card-shaped, Luhn-valid number, and fails closed.
    """
    if not content or not card_vault.contains_pan(content):
        return content, False
    if replied_prompt_id is None:
        try:
            applies = await user_has_open_purchase_question(conn, channel_id, user_id)
        except Exception:
            logger.warning("agent-card question lookup failed; redacting", exc_info=True)
            applies = True
        if not applies:
            return content, False
    return card_vault.redact_pans(content), True


async def _ask(conn, *, prompt: dict, kind: str, owner_user_id, payload: dict, ttl: timedelta,
               content: str, view: dict | None = None) -> dict | None:
    """Insert a follow-up question and its Espresso message on the caller's
    transaction. Returns the message payload to broadcast after commit."""
    row = await conn.fetchrow(
        """INSERT INTO mw_agent_card_prompts
               (company_id, project_id, task_id, run_id, channel_id, kind,
                owner_user_id, payload, expires_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW() + $9::interval)
           RETURNING id, expires_at""",
        prompt["company_id"], prompt["project_id"], prompt["task_id"], prompt["run_id"],
        prompt["channel_id"], kind, owner_user_id, json.dumps(payload), ttl,
    )
    prompt_id = row["id"]
    message = await persist_espresso_message(
        conn, prompt["company_id"], prompt["channel_id"], content,
        metadata=_prompt_metadata(
            prompt_id, prompt["project_id"], prompt["task_id"], kind, view=view,
            owner_user_id=owner_user_id, expires_at=row["expires_at"],
        ),
    )
    if message:
        await conn.execute(
            "UPDATE mw_agent_card_prompts SET message_id = $2 WHERE id = $1",
            prompt_id, UUID(message["id"]),
        )
    return message


def _prompt_metadata(prompt_id, project_id, task_id, kind: str, *, view: dict | None = None,
                     owner_user_id=None, expires_at=None) -> dict:
    """`owner_user_id` (buy / card questions) lets the apps show the buttons
    only to the buyer; `expires_at` lets them retire the buttons on time."""
    metadata = {
        "kind": PROMPT_METADATA_KIND,
        "prompt_id": str(prompt_id),
        "prompt_kind": kind,
        "project_id": str(project_id),
        "task_id": str(task_id),
    }
    if owner_user_id is not None:
        metadata["owner_user_id"] = str(owner_user_id)
    if expires_at is not None:
        metadata["expires_at"] = expires_at.isoformat()
    if view:
        metadata["view"] = view
    return metadata


async def overlay_prompt_statuses(conn, messages, *, channel_id: UUID) -> list:
    """Stamp each question message with its live state (`prompt_status`:
    open / answered / superseded / expired, and `answer`) so a reloaded chat
    shows answered questions as answered instead of offering stale buttons.
    One indexed query per history page; other messages pass through."""
    ids: set[UUID] = set()
    for message in messages:
        prompt_id = prompt_reference(message.get("metadata"))
        if prompt_id is not None:
            ids.add(prompt_id)
    if not ids:
        return list(messages)
    rows = await conn.fetch(
        """SELECT id, kind, status, answer, (status = 'open' AND expires_at <= NOW()) AS expired
           FROM mw_agent_card_prompts WHERE id = ANY($1::uuid[]) AND channel_id = $2""",
        sorted(ids, key=str), channel_id,
    )
    states = {row["id"]: row for row in rows}
    out = []
    for message in messages:
        prompt_id = prompt_reference(message.get("metadata"))
        row = states.get(prompt_id)
        if row is not None:
            message = dict(message)
            message["metadata"] = {
                **(decode_jsonb(message.get("metadata"), {}) or {}),
                "prompt_status": "expired" if row["expired"] else row["status"],
                "answer": public_answer(row["answer"]),
                "answer_text": answer_text(row["kind"], row["answer"]),
            }
        out.append(message)
    return out


def prompt_reference(raw_metadata) -> UUID | None:
    """The question a threaded reply answers, from the replied-to message's metadata."""
    raw_metadata = decode_jsonb(raw_metadata)
    if not isinstance(raw_metadata, dict) or raw_metadata.get("kind") != PROMPT_METADATA_KIND:
        return None
    try:
        return UUID(str(raw_metadata.get("prompt_id")))
    except (TypeError, ValueError):
        return None


# ── the offer, posted by the worker ───────────────────────────────────────────

async def offer_result(run_id: UUID) -> bool:
    """Ask "want to see what I found?" in the card's project chat.

    Pool-free (runs in the Celery worker). No-op when the project has no
    discussion chat, or when a newer run has already started on the card (the
    card was sent back between finishing and this offer). Idempotent per run;
    a newer offer closes the card's older open questions.
    """
    payload = None
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """SELECT r.company_id, r.project_id, r.task_id, r.round, r.status,
                      t.title, t.board_column,
                      p.project_data->>'discussion_channel_id' AS channel_id
               FROM mw_project_agent_runs r
               JOIN mw_tasks t ON t.id = r.task_id
               JOIN mw_projects p ON p.id = r.project_id
               WHERE r.id = $1 AND r.kind = 'card_agent'""",
            run_id,
        )
        if not row or row["status"] != "done" or not row["channel_id"]:
            return False
        try:
            channel_id = UUID(str(row["channel_id"]))
        except ValueError:
            return False
        title = row["title"] or "your agent card"
        reworked = (row["round"] or 1) > 1
        content = (
            f"{_ticket_token(row['task_id'], title, row['board_column'])}\n"
            f"I {'reworked' if reworked else 'finished'} \"{title}\". Want to see what I found? Reply yes or no."
        )
        async with conn.transaction():
            await _lock_card(conn, row["task_id"])
            if await _superseded(conn, row["task_id"], run_id):
                return False
            inserted = await conn.fetchrow(
                """INSERT INTO mw_agent_card_prompts
                       (company_id, project_id, task_id, run_id, channel_id, kind, expires_at)
                   VALUES ($1, $2, $3, $4, $5, 'show_result', NOW() + $6::interval)
                   ON CONFLICT (run_id) WHERE kind = 'show_result' DO NOTHING
                   RETURNING id, expires_at""",
                row["company_id"], row["project_id"], row["task_id"], run_id, channel_id, OFFER_TTL,
            )
            if inserted is None:
                return True
            prompt_id = inserted["id"]
            closed = await conn.fetch(
                """UPDATE mw_agent_card_prompts SET status = 'superseded'
                   WHERE task_id = $1 AND status = 'open' AND id <> $2
                   RETURNING id, channel_id, kind""",
                row["task_id"], prompt_id,
            )
            payload = await persist_espresso_message(
                conn, row["company_id"], channel_id, content,
                metadata=_prompt_metadata(
                    prompt_id, row["project_id"], row["task_id"], "show_result",
                    view=_show_view(reworked=reworked), expires_at=inserted["expires_at"],
                ),
            )
            if payload:
                await conn.execute(
                    "UPDATE mw_agent_card_prompts SET message_id = $2 WHERE id = $1",
                    prompt_id, UUID(payload["id"]),
                )
    await broadcast_espresso_message(payload)
    await broadcast_prompt_updates([prompt_update(r, "superseded") for r in closed])
    return True


# ── answers, from the chat socket ─────────────────────────────────────────────

async def _can_access_project(prompt: dict, user) -> bool:
    """The REST API's own rule (`project_service.resolve_project_access`, behind
    `_verify_project_access`): collaborators, the company's own users except
    employees on discipline/recruiting boards, and admins only as collaborators."""
    from app.core.models.auth import CurrentUser
    from app.matcha.dependencies import get_client_company_id

    from ..project_service import resolve_project_access

    actor = user if isinstance(user, CurrentUser) else CurrentUser(
        id=user.id, email=getattr(user, "email", None) or "", role=user.role,
    )
    company_id = None if actor.role == "admin" else await get_client_company_id(actor)
    return await resolve_project_access(prompt["project_id"], actor, company_id=company_id) is not None


async def _load_prompt(
    conn, channel_id: UUID, *, prompt_id: UUID | None, purchase_owner=None,
    kinds: tuple[str, ...] = PURCHASE_KINDS, max_age: timedelta | None = None,
) -> dict | None:
    if prompt_id is not None:
        row = await conn.fetchrow(
            """SELECT *, (status = 'open' AND expires_at > NOW()) AS live
               FROM mw_agent_card_prompts WHERE id = $1 AND channel_id = $2""",
            prompt_id, channel_id,
        )
    elif purchase_owner is not None:
        row = await conn.fetchrow(
            """SELECT *, TRUE AS live
               FROM mw_agent_card_prompts
               WHERE channel_id = $1 AND owner_user_id = $2 AND kind = ANY($3::text[])
                 AND status = 'open' AND expires_at > NOW()
                 AND ($4::interval IS NULL OR created_at > NOW() - $4::interval)
               ORDER BY created_at DESC LIMIT 1""",
            channel_id, purchase_owner, list(kinds), max_age,
        )
    else:
        row = await conn.fetchrow(
            """SELECT *, TRUE AS live
               FROM mw_agent_card_prompts
               WHERE channel_id = $1 AND kind = 'show_result'
                 AND status = 'open' AND expires_at > NOW()
               ORDER BY created_at DESC LIMIT 1""",
            channel_id,
        )
    if not row:
        return None
    prompt = dict(row)
    prompt["payload"] = decode_jsonb(prompt.get("payload"), {}) or {}
    return prompt


class _Outbox:
    """What to broadcast once the answer's transaction has committed:
    Espresso's new messages, and the questions that closed (so every open
    chat drops their buttons)."""

    def __init__(self) -> None:
        self.messages: list[dict | None] = []
        self.prompt_updates: list[dict] = []

    async def flush(self) -> None:
        for message in self.messages:
            await broadcast_espresso_message(message)
        await broadcast_prompt_updates(self.prompt_updates)


async def _claimed(conn, prompt, user, answer: str, *, say, outbox: _Outbox) -> bool:
    """Claim the question for this answer. False when someone else answered
    it first, or when a newer run replaced its result (the card's open
    questions are then closed and the user is told). Must run in the
    caller's transaction."""
    await _lock_card(conn, prompt["task_id"])
    if await _superseded(conn, prompt["task_id"], prompt["run_id"]):
        outbox.prompt_updates += await close_open_prompts(conn, prompt["task_id"])
        await say(STALE_REPLY)
        return False
    claimed = await conn.fetchval(
        """UPDATE mw_agent_card_prompts
           SET status = 'answered', answer = $2, answered_by = $3, answered_at = NOW()
           WHERE id = $1 AND status = 'open' AND expires_at > NOW()
           RETURNING TRUE""",
        prompt["id"], answer, user.id,
    )
    if claimed:
        outbox.prompt_updates.append(prompt_update(prompt, "answered", answer))
    return bool(claimed)


async def _saved_cards(conn, user_id) -> list[dict]:
    rows = await conn.fetch(
        """SELECT id, label, brand, last4, exp_month, exp_year
           FROM mw_payment_cards WHERE user_id = $1 ORDER BY created_at""",
        user_id,
    )
    today = date.today()
    return [
        dict(r) for r in rows
        if card_vault.expiry_ok(r["exp_month"], r["exp_year"], today=today)
    ]


_HINTS = {
    "show_result": "Reply yes to see what I found, or no to skip.",
    "purchase": "Reply yes to buy it, or no to skip.",
    "pick_card": "Reply with the number of the card to use, or no to cancel.",
}
_CARD_NUMBER_WARNING = (
    "I removed a card number from that message. Please never paste card numbers in chat. "
    f"{ADD_CARD_HINT}, where they're stored encrypted."
)


async def handle_chat_answer(
    *,
    channel_id: UUID,
    user,
    content: str,
    prompt_id: UUID | None = None,
    has_attachments: bool = False,
    card_number_removed: bool = False,
) -> bool:
    """Apply one chat message as an answer. Returns whether it was one of ours.

    `prompt_id` is set for a threaded reply to a question. Without it, only a
    plain "yes" is considered (it shows the channel's newest open result), or a
    removed card number (warned about against the sender's own open purchase
    question). Everything else is ordinary chat.
    """
    targeted = prompt_id is not None
    plain_answer: Answer | None = None
    async with connection_or_direct() as conn:
        if targeted:
            prompt = await _load_prompt(conn, channel_id, prompt_id=prompt_id)
        elif card_number_removed:
            prompt = await _load_prompt(conn, channel_id, prompt_id=None, purchase_owner=user.id)
        else:
            prompt, plain_answer = await _plain_target(conn, channel_id, user, content)
    if prompt is None:
        return False
    if prompt["kind"] in ASSISTANT_KINDS:
        # A question the assistant asked is answered by the assistant's own
        # rules (only its owner, any text for `ask_user`), not the card's.
        from ..agent_runtime import chat_entry

        return await chat_entry.answer_loaded_prompt(
            prompt=prompt, channel_id=channel_id, user=user, content=content,
        )
    allowed = await _can_access_project(prompt, user)
    if not allowed and not targeted:
        return False

    outbox = _Outbox()
    async with connection_or_direct() as conn:

        async def say(text: str, metadata: dict | None = None) -> None:
            outbox.messages.append(await persist_espresso_message(
                conn, prompt["company_id"], channel_id, text, metadata=metadata,
            ))

        if not allowed:
            await say("I can only take answers from people on this project.")
        elif card_number_removed:
            await say(_CARD_NUMBER_WARNING)
        elif has_attachments and targeted and prompt["kind"] in PURCHASE_KINDS:
            await say(
                "I don't read card photos. Please delete that image from the chat. "
                f"{ADD_CARD_HINT} instead."
            )
        else:
            await _answer(conn, prompt, user, content, targeted=targeted, plain_answer=plain_answer,
                          say=say, outbox=outbox)
    await outbox.flush()
    return True


async def _plain_target(conn, channel_id: UUID, user, content: str) -> tuple[dict | None, Answer | None]:
    """Which question a plain (unthreaded) message answers, if any:
      * an explicit "buy it" → the sender's own open buy / card question;
      * "1" / "4242" → the sender's own open card question;
      * "yes" → the sender's own buy / card question if it was just asked,
        else the channel's newest "want to see it?" question.
    """
    buy, choice, yes = is_buy_intent(content), plain_card_choice(content), is_plain_yes(content)
    if buy or yes:
        prompt = await _load_prompt(
            conn, channel_id, prompt_id=None, purchase_owner=user.id,
            max_age=None if buy else FRESH_PURCHASE_QUESTION,
        )
        if prompt:
            return prompt, Answer("yes")
    if choice:
        prompt = await _load_prompt(conn, channel_id, prompt_id=None, purchase_owner=user.id, kinds=("pick_card",))
        if prompt:
            return prompt, choice
    if yes:
        return await _load_prompt(conn, channel_id, prompt_id=None), Answer("yes")
    return None, None


async def _answer(conn, prompt: dict, user, content: str, *, targeted: bool, say, outbox,
                  plain_answer: Answer | None = None) -> None:
    answer = parse_answer(content) if targeted else plain_answer
    kind = prompt["kind"]
    owner = prompt.get("owner_user_id")
    if owner is not None and owner != user.id:
        await say("Only the person who asked to buy this can answer that.")
        return
    if answer is None or (answer.kind in ("last4", "choice") and kind != "pick_card"):
        # Chatter in reply to a closed question is just chat.
        if prompt["live"]:
            await say(_HINTS[kind])
        return
    if not prompt["live"]:
        await say("That question has closed. The latest result is on the card.")
        return

    if kind == "show_result":
        await _answer_show_result(conn, prompt, user, answer, say=say, outbox=outbox)
    elif kind == "purchase":
        await _answer_purchase(conn, prompt, user, answer, say=say, outbox=outbox)
    else:
        await _answer_pick_card(conn, prompt, user, answer, say=say, outbox=outbox)


async def _answer_show_result(conn, prompt, user, answer: Answer, *, say, outbox) -> None:
    if answer.kind == "no":
        async with conn.transaction():
            if await _claimed(conn, prompt, user, "no", say=say, outbox=outbox):
                await say("No problem. It's on the card whenever you want it.")
        return
    row = await conn.fetchrow(
        """SELECT r.result, t.title, t.board_column
           FROM mw_project_agent_runs r JOIN mw_tasks t ON t.id = r.task_id
           WHERE r.id = $1""",
        prompt["run_id"],
    )
    result = decode_jsonb(row["result"]) if row else None
    async with conn.transaction():
        if not await _claimed(conn, prompt, user, "yes", say=say, outbox=outbox):
            return
        if not isinstance(result, dict):
            await say("I couldn't load that result any more. Open the card to see its latest run.")
            return
        await say(
            format_result(result, task_id=prompt["task_id"], title=row["title"], column=row["board_column"]),
            metadata={
                "kind": RESULT_METADATA_KIND,
                "task_id": str(prompt["task_id"]),
                "project_id": str(prompt["project_id"]),
                "run_id": str(prompt["run_id"]),
                "result": result_view(result),
            },
        )
        offer = purchase_offer(result)
        if offer and purchases_allowed(user):
            outbox.messages.append(await _ask(
                conn, prompt=prompt, kind="purchase", owner_user_id=user.id, payload=offer,
                ttl=PURCHASE_TTL,
                content=(
                    f"Want me to buy it? {_offer_line(offer)}. "
                    "Reply yes (or \"buy it\") to buy, or no to skip."
                ),
                view=_purchase_view(offer),
            ))


async def _answer_purchase(conn, prompt, user, answer: Answer, *, say, outbox) -> None:
    if answer.kind == "no":
        async with conn.transaction():
            if await _claimed(conn, prompt, user, "no", say=say, outbox=outbox):
                await say("Okay, I won't buy it.")
        return
    cards = await _saved_cards(conn, user.id)
    if not cards:
        # Leave the question open so "yes" works again once a card is saved.
        await say(
            f"You don't have a saved card yet. {ADD_CARD_HINT} (never paste card numbers in chat), "
            "then reply yes to that question again."
        )
        return
    options = [
        {
            "n": i + 1, "card_id": str(c["id"]), "last4": c["last4"], "brand": c["brand"],
            "label": c["label"], "exp_month": c["exp_month"], "exp_year": c["exp_year"],
        }
        for i, c in enumerate(cards)
    ]
    if len(options) == 1:
        question = (
            f"Use your {_card_label(options[0], with_expiry=True)}? "
            "Reply yes (or 1) to confirm, or no to cancel."
        )
    else:
        question = (
            "Which card? Reply with its number: "
            + "; ".join(f"{o['n']}. {_card_label(o, with_expiry=True)}" for o in options)
            + ". Or reply no to cancel."
        )
    async with conn.transaction():
        if not await _claimed(conn, prompt, user, "yes", say=say, outbox=outbox):
            return
        outbox.messages.append(await _ask(
            conn, prompt=prompt, kind="pick_card", owner_user_id=user.id,
            payload={**prompt["payload"], "options": options}, ttl=PICK_CARD_TTL, content=question,
            view=_pick_card_view(options),
        ))


def _choose(options: list[dict], answer: Answer) -> tuple[dict | None, str | None]:
    """(chosen option, or a reply explaining why none was chosen)."""
    if answer.kind == "yes":
        if len(options) == 1:
            return options[0], None
        return None, _HINTS["pick_card"]
    if answer.kind == "choice":
        n = int(answer.value)
        chosen = next((o for o in options if o.get("n") == n), None)
        if chosen is None:
            return None, f"There's no card {n}. Reply with a number from 1 to {len(options)}."
        return chosen, None
    matches = [o for o in options if o["last4"] == answer.value]
    if len(matches) == 1:
        return matches[0], None
    if matches:
        return None, (
            f"More than one saved card ends in {answer.value}. Reply with its number: "
            + ", ".join(str(o["n"]) for o in matches) + "."
        )
    return None, f"I don't see a saved card ending {answer.value}. Reply with the card's number."


async def _answer_pick_card(conn, prompt, user, answer: Answer, *, say, outbox) -> None:
    payload = prompt["payload"]
    if answer.kind == "no":
        async with conn.transaction():
            if await _claimed(conn, prompt, user, "no", say=say, outbox=outbox):
                await say("Okay, cancelled. Nothing was bought.")
        return
    chosen, problem = _choose(payload.get("options") or [], answer)
    if problem:
        await say(problem)
        return
    card = await conn.fetchrow(
        """SELECT id, last4, brand, label, exp_month, exp_year
           FROM mw_payment_cards WHERE id = $1 AND user_id = $2""",
        UUID(chosen["card_id"]), user.id,
    )
    if not card or not card_vault.expiry_ok(card["exp_month"], card["exp_year"]):
        await say(f"The card ending {chosen['last4']} was removed or has expired. Pick another, or reply no.")
        return
    async with conn.transaction():
        if not await _claimed(conn, prompt, user, f"card:{card['last4']}", say=say, outbox=outbox):
            return
        purchase_id = await conn.fetchval(
            """INSERT INTO mw_agent_purchase_requests
                   (company_id, project_id, task_id, run_id, prompt_id, user_id, card_id,
                    card_last4, item_name, retailer, checkout_url, amount, currency)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
               RETURNING id""",
            prompt["company_id"], prompt["project_id"], prompt["task_id"], prompt["run_id"],
            prompt["id"], user.id, card["id"], card["last4"], payload["item_name"],
            payload.get("retailer"), payload["checkout_url"], payload.get("amount"),
            payload.get("currency"),
        )
    # The Stripe call happens after commit (never inside a transaction); the
    # approval is recorded either way.
    approved = f"Approved: {_offer_line(payload)}, on your {_card_label(dict(card))}."
    link = "The product link is on the card under Purchases."
    # The receipt card renders the link as a button; this plain text is what
    # notifications and older apps show, so a handoff carries the URL itself.
    checkout = f"Finish checkout here: {payload['checkout_url']}"

    def receipt(status: str, **extra) -> dict:
        return {
            "kind": RECEIPT_METADATA_KIND,
            "task_id": str(prompt["task_id"]),
            "project_id": str(prompt["project_id"]),
            "receipt": receipt_view(payload, card=dict(card), purchase_id=purchase_id, status=status, **extra),
        }

    key = test_charge.test_key()
    if key is None:
        await say(f"{approved} I haven't charged anything. {checkout}", receipt("approved"))
        return
    if payload.get("amount") is None or not payload.get("currency"):
        await say(f"{approved} No verified price, so I didn't make a test charge. {checkout}",
                  receipt("no_price"))
        return
    outcome = await test_charge.charge(
        key, purchase_id=purchase_id, amount=payload["amount"], currency=payload["currency"],
        brand=card["brand"], description=f"Agent card test purchase: {payload['item_name']}",
        metadata={"purchase_id": purchase_id, "task_id": prompt["task_id"], "card_last4": card["last4"]},
    )
    await conn.execute(
        """UPDATE mw_agent_purchase_requests
           SET status = $2, stripe_payment_intent_id = $3, charge_error = $4
           WHERE id = $1""",
        purchase_id, outcome["status"], outcome["payment_intent_id"], outcome["error"],
    )
    if outcome["status"] == "test_charged":
        await say(
            format_receipt(
                payload, card=dict(card), purchase_id=purchase_id,
                payment_intent_id=outcome["payment_intent_id"], task_id=prompt["task_id"],
            ),
            receipt("paid_test", payment_intent_id=outcome["payment_intent_id"]),
        )
    else:
        await say(f"{approved} The Stripe test charge failed: {outcome['error']} {link}",
                  receipt("failed", payment_intent_id=outcome["payment_intent_id"], error=outcome["error"]))
