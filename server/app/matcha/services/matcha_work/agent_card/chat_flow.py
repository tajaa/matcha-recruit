"""Espresso's questions about a finished agent card, in the project chat.

When a run finishes, Espresso asks in the card's project discussion "want to
see what I found?". Yes posts a readable summary of the result (the full page
stays on the card). For a shopping result, and for a user allowed to buy, it
then asks "want to buy it?", then which saved card, and records a purchase
handoff: the exact item, retailer, checkout link and total the user approved.
v1 never charges anything; the user finishes checkout at the link.

Every question is a `mw_agent_card_prompts` row. Answers are parsed
deterministically (no model call): a threaded reply goes to that question; a
plain "yes" / "no" / last-4 goes to the channel's newest open question. A
question is claimed with one conditional UPDATE, so it is answered once.

Card numbers never travel through chat or the model: saved cards are added
through the payment-cards API, chat only ever shows the brand and last 4
digits, and a card number typed at an open question is removed before the
message is stored (see `channels_ws`).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.core.services import card_vault
from app.database import connection_or_direct

from ..project_agent.chat import broadcast_espresso_message, persist_espresso_message

PROMPT_METADATA_KIND = "agent_card_prompt"
OFFER_TTL = timedelta(days=7)
PURCHASE_TTL = timedelta(days=2)
PICK_CARD_TTL = timedelta(hours=2)
MAX_MESSAGE_CHARS = 3500

ADD_CARD_HINT = "Add one in Espresso under Settings → Payment cards"

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
_LAST4 = re.compile(r"^(?:use\s+)?(?:the\s+)?(?:card\s+)?(?:ending\s+)?(?:in\s+)?(\d{4})$")
_ESPRESSO_MENTION = re.compile(r"(?i)(?:(?<=^)|(?<=\s))@espresso\b")


@dataclass(frozen=True)
class Answer:
    kind: str  # "yes" | "no" | "last4"
    last4: str | None = None


def parse_answer(text: str) -> Answer | None:
    """A yes / no / "the one ending 4242", or None when it's something else."""
    if not isinstance(text, str) or len(text) > 60:
        return None
    normalized = re.sub(r"[^a-z0-9 ]+", " ", _ESPRESSO_MENTION.sub("", text).lower())
    normalized = " ".join(normalized.split())
    if not normalized:
        return None
    if normalized in _YES:
        return Answer("yes")
    if normalized in _NO:
        return Answer("no")
    match = _LAST4.match(normalized)
    if match:
        return Answer("last4", match.group(1))
    return None


def might_answer(text: str) -> bool:
    """Cheap, synchronous hot-path guard: could this plain message be an answer?"""
    return parse_answer(text) is not None


def purchases_allowed(role: str | None) -> bool:
    """Buying through chat is internal-only in v1: platform admins."""
    return (role or "").lower() == "admin"


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


def format_result(result: dict, *, task_id, title: str, column: str | None) -> str:
    """The result as a chat message. The full page (photos, every review and
    source) stays on the card; this is the short read."""
    lines = [_ticket_token(task_id, title, column), result.get("headline") or title, ""]
    lines.append(result.get("summary") or "")
    pick = result.get("top_pick")
    if pick:
        facts = [f for f in (_pick_price(pick), _rating_line(pick)) if f]
        name = pick["name"] + (f" by {pick['brand']}" if pick.get("brand") else "")
        lines += ["", "Top pick: " + " · ".join([name, *facts])]
        lines += [f"• {why}" for why in (pick.get("why") or [])[:3]]
        buy = (pick.get("buy_links") or [None])[0]
        if buy:
            lines.append(f"Buy at {buy.get('retailer') or 'the store'}: {buy['url']}")
    alternatives = result.get("alternatives") or []
    if alternatives:
        lines += ["", "Also worth a look:"]
        for alt in alternatives[:3]:
            price = _pick_price(alt)
            lines.append(f"• {alt['name']}" + (f", {price}" if price else ""))
    if not pick and result.get("sections"):
        lines += ["", "Covers: " + ", ".join(s["heading"] for s in result["sections"][:6] if s.get("heading"))]
    lines += ["", "The full page, with photos, reviews and sources, is on the card."]
    text = "\n".join(lines).strip()
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 1].rstrip() + "…"
    return text


def purchase_offer(result: dict) -> dict | None:
    """The one thing a yes would buy: the top pick at its first verified buy link.

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
    amount = link.get("price") if link.get("price") is not None else price.get("amount")
    return {
        "item_name": pick["name"],
        "brand": pick.get("brand") or None,
        "retailer": link.get("retailer") or None,
        "checkout_url": link["url"],
        "amount": amount,
        "currency": (price.get("currency") or "USD") if amount is not None else None,
    }


def _offer_line(offer: dict) -> str:
    parts = [offer["item_name"]]
    if offer.get("retailer"):
        parts.append(f"at {offer['retailer']}")
    money = format_money(offer.get("amount"), offer.get("currency"))
    parts.append(f"for {money}" if money else "(price not confirmed)")
    return " ".join(parts)


_BRANDS = {"visa": "Visa", "mastercard": "Mastercard", "amex": "Amex", "discover": "Discover"}


def _card_label(card: dict) -> str:
    brand = _BRANDS.get(card.get("brand") or "", "card")
    label = f"{brand} ending {card['last4']}"
    if card.get("label"):
        label += f" ({card['label']})"
    return label


# ── storage helpers ───────────────────────────────────────────────────────────

def _jsonb(value) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


async def channel_has_open_prompt(conn, channel_id: UUID) -> bool:
    return bool(await conn.fetchval(
        """SELECT EXISTS(
               SELECT 1 FROM mw_agent_card_prompts
               WHERE channel_id = $1 AND status = 'open' AND expires_at > NOW()
           )""",
        channel_id,
    ))


async def _ask(conn, *, prompt: dict, kind: str, owner_user_id, payload: dict, ttl: timedelta,
               content: str) -> dict | None:
    """Insert a follow-up question and its Espresso message on the caller's
    transaction. Returns the message payload to broadcast after commit."""
    prompt_id = await conn.fetchval(
        """INSERT INTO mw_agent_card_prompts
               (company_id, project_id, task_id, run_id, channel_id, kind,
                owner_user_id, payload, expires_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW() + $9::interval)
           RETURNING id""",
        prompt["company_id"], prompt["project_id"], prompt["task_id"], prompt["run_id"],
        prompt["channel_id"], kind, owner_user_id, json.dumps(payload), ttl,
    )
    message = await persist_espresso_message(
        conn, prompt["company_id"], prompt["channel_id"], content,
        metadata=_prompt_metadata(prompt_id, prompt["project_id"], prompt["task_id"], kind),
    )
    if message:
        await conn.execute(
            "UPDATE mw_agent_card_prompts SET message_id = $2 WHERE id = $1",
            prompt_id, UUID(message["id"]),
        )
    return message


def _prompt_metadata(prompt_id, project_id, task_id, kind: str) -> dict:
    return {
        "kind": PROMPT_METADATA_KIND,
        "prompt_id": str(prompt_id),
        "prompt_kind": kind,
        "project_id": str(project_id),
        "task_id": str(task_id),
    }


def prompt_reference(raw_metadata) -> UUID | None:
    """The question a threaded reply answers, from the replied-to message's metadata."""
    raw_metadata = _jsonb(raw_metadata)
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
    discussion chat. Idempotent per run; a newer offer closes the card's older
    open questions so nobody buys from a superseded result.
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
        verb = "reworked" if (row["round"] or 1) > 1 else "finished"
        content = (
            f"{_ticket_token(row['task_id'], title, row['board_column'])}\n"
            f"I {verb} \"{title}\". Want to see what I found? Reply yes or no."
        )
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"{row['task_id']}:agent_prompts",
            )
            prompt_id = await conn.fetchval(
                """INSERT INTO mw_agent_card_prompts
                       (company_id, project_id, task_id, run_id, channel_id, kind, expires_at)
                   VALUES ($1, $2, $3, $4, $5, 'show_result', NOW() + $6::interval)
                   ON CONFLICT (run_id) WHERE kind = 'show_result' DO NOTHING
                   RETURNING id""",
                row["company_id"], row["project_id"], row["task_id"], run_id, channel_id, OFFER_TTL,
            )
            if prompt_id is None:
                return True
            await conn.execute(
                """UPDATE mw_agent_card_prompts SET status = 'superseded'
                   WHERE task_id = $1 AND status = 'open' AND id <> $2""",
                row["task_id"], prompt_id,
            )
            payload = await persist_espresso_message(
                conn, row["company_id"], channel_id, content,
                metadata=_prompt_metadata(prompt_id, row["project_id"], row["task_id"], "show_result"),
            )
            if payload:
                await conn.execute(
                    "UPDATE mw_agent_card_prompts SET message_id = $2 WHERE id = $1",
                    prompt_id, UUID(payload["id"]),
                )
    await broadcast_espresso_message(payload)
    return True


async def close_open_prompts(conn, task_id: UUID) -> None:
    """A new run on the card makes its open questions stale (caller's transaction)."""
    await conn.execute(
        """UPDATE mw_agent_card_prompts SET status = 'superseded'
           WHERE task_id = $1 AND status = 'open'""",
        task_id,
    )


# ── answers, from the chat socket ─────────────────────────────────────────────

async def _can_access_project(conn, prompt: dict, user) -> bool:
    if (getattr(user, "role", "") or "").lower() == "admin":
        return True
    return bool(await conn.fetchval(
        """SELECT EXISTS(
               SELECT 1 FROM mw_project_collaborators
               WHERE project_id = $1 AND user_id = $3 AND status = 'active'
           ) OR EXISTS(
               SELECT 1 FROM clients WHERE user_id = $3 AND company_id = $2
           ) OR EXISTS(
               SELECT 1 FROM employees WHERE user_id = $3 AND org_id = $2
           )""",
        prompt["project_id"], prompt["company_id"], user.id,
    ))


async def _load_prompt(conn, channel_id: UUID, prompt_id: UUID | None) -> dict | None:
    if prompt_id is not None:
        row = await conn.fetchrow(
            """SELECT *, (status = 'open' AND expires_at > NOW()) AS live
               FROM mw_agent_card_prompts WHERE id = $1 AND channel_id = $2""",
            prompt_id, channel_id,
        )
    else:
        row = await conn.fetchrow(
            """SELECT *, TRUE AS live
               FROM mw_agent_card_prompts
               WHERE channel_id = $1 AND status = 'open' AND expires_at > NOW()
               ORDER BY created_at DESC LIMIT 1""",
            channel_id,
        )
    if not row:
        return None
    prompt = dict(row)
    prompt["payload"] = _jsonb(prompt.get("payload")) or {}
    return prompt


async def _claim(conn, prompt: dict, user, answer: str) -> bool:
    return await conn.fetchval(
        """UPDATE mw_agent_card_prompts
           SET status = 'answered', answer = $2, answered_by = $3, answered_at = NOW()
           WHERE id = $1 AND status = 'open' AND expires_at > NOW()
           RETURNING TRUE""",
        prompt["id"], answer, user.id,
    ) is not None


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
    "pick_card": "Reply with the last 4 digits of the card to use, or no to cancel.",
}


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

    `prompt_id` is set for a threaded reply to a question; otherwise the
    channel's newest open question is the target, and anything that isn't a
    clear answer from someone who may give it is left as ordinary chat.
    """
    targeted = prompt_id is not None
    outbox: list[dict | None] = []
    handled = False
    async with connection_or_direct() as conn:

        async def say(text: str) -> None:
            outbox.append(await persist_espresso_message(conn, prompt["company_id"], channel_id, text))

        prompt = await _load_prompt(conn, channel_id, prompt_id)
        if prompt is None:
            return False
        if not await _can_access_project(conn, prompt, user):
            if targeted:
                await say("I can only take answers from people on this project.")
            handled = targeted
        elif card_number_removed:
            await say(
                "I removed a card number from that message. Please never paste card numbers in chat. "
                f"{ADD_CARD_HINT}, where they're stored encrypted."
            )
            handled = True
        elif has_attachments and targeted and prompt["kind"] in ("purchase", "pick_card"):
            await say(
                "I don't read card photos. Please delete that image from the chat. "
                f"{ADD_CARD_HINT} instead."
            )
            handled = True
        else:
            handled = await _answer(conn, prompt, user, content, targeted=targeted, say=say, outbox=outbox)
    for message in outbox:
        await broadcast_espresso_message(message)
    return handled


async def _answer(conn, prompt: dict, user, content: str, *, targeted: bool, say, outbox) -> bool:
    answer = parse_answer(content)
    kind = prompt["kind"]
    owner = prompt.get("owner_user_id")
    if owner is not None and owner != user.id:
        if targeted:
            await say("Only the person who asked to buy this can answer that.")
        return targeted
    if answer is None or (answer.kind == "last4" and kind != "pick_card"):
        # Chatter in reply to a closed question is just chat.
        if targeted and prompt["live"]:
            await say(_HINTS[kind])
        return targeted
    if not prompt["live"]:
        await say("That question has closed. The latest result is on the card.")
        return True

    if kind == "show_result":
        return await _answer_show_result(conn, prompt, user, answer, say=say, outbox=outbox)
    if kind == "purchase":
        return await _answer_purchase(conn, prompt, user, answer, say=say, outbox=outbox)
    return await _answer_pick_card(conn, prompt, user, answer, say=say)


async def _answer_show_result(conn, prompt, user, answer: Answer, *, say, outbox) -> bool:
    if answer.kind == "no":
        if await _claim(conn, prompt, user, "no"):
            await say("No problem. It's on the card whenever you want it.")
        return True
    row = await conn.fetchrow(
        """SELECT r.result, t.title, t.board_column
           FROM mw_project_agent_runs r JOIN mw_tasks t ON t.id = r.task_id
           WHERE r.id = $1""",
        prompt["run_id"],
    )
    result = _jsonb(row["result"]) if row else None
    if not isinstance(result, dict):
        if await _claim(conn, prompt, user, "yes"):
            await say("I couldn't load that result any more. Open the card to see its latest run.")
        return True
    async with conn.transaction():
        if not await _claim(conn, prompt, user, "yes"):
            return True
        await say(format_result(result, task_id=prompt["task_id"], title=row["title"], column=row["board_column"]))
        offer = purchase_offer(result)
        if offer and purchases_allowed(getattr(user, "role", None)):
            outbox.append(await _ask(
                conn, prompt=prompt, kind="purchase", owner_user_id=user.id, payload=offer,
                ttl=PURCHASE_TTL,
                content=f"Want me to buy it? {_offer_line(offer)}. Reply yes or no.",
            ))
    return True


async def _answer_purchase(conn, prompt, user, answer: Answer, *, say, outbox) -> bool:
    if answer.kind == "no":
        if await _claim(conn, prompt, user, "no"):
            await say("Okay, I won't buy it.")
        return True
    cards = await _saved_cards(conn, user.id)
    if not cards:
        # Leave the question open so "yes" works again once a card is saved.
        await say(
            f"You don't have a saved card yet. {ADD_CARD_HINT} (never paste card numbers in chat), "
            "then reply yes here again."
        )
        return True
    options = [
        {"card_id": str(c["id"]), "last4": c["last4"], "brand": c["brand"], "label": c["label"]}
        for c in cards
    ]
    if len(options) == 1:
        question = f"Use your {_card_label(options[0])}? Reply yes, or no to cancel."
    else:
        question = "Which card? Reply with the last 4 digits: " + "; ".join(
            _card_label(o) for o in options
        ) + ". Or reply no to cancel."
    async with conn.transaction():
        if not await _claim(conn, prompt, user, "yes"):
            return True
        outbox.append(await _ask(
            conn, prompt=prompt, kind="pick_card", owner_user_id=user.id,
            payload={**prompt["payload"], "options": options}, ttl=PICK_CARD_TTL, content=question,
        ))
    return True


async def _answer_pick_card(conn, prompt, user, answer: Answer, *, say) -> bool:
    payload = prompt["payload"]
    options = payload.get("options") or []
    if answer.kind == "no":
        if await _claim(conn, prompt, user, "no"):
            await say("Okay, cancelled. Nothing was bought.")
        return True
    if answer.kind == "yes":
        if len(options) != 1:
            await say(_HINTS["pick_card"])
            return True
        chosen = options[0]
    else:
        chosen = next((o for o in options if o["last4"] == answer.last4), None)
        if chosen is None:
            await say(
                f"I don't see a saved card ending {answer.last4}. Reply with one of: "
                + ", ".join(o["last4"] for o in options) + "."
            )
            return True
    card = await conn.fetchrow(
        """SELECT id, last4, brand, label, exp_month, exp_year
           FROM mw_payment_cards WHERE id = $1 AND user_id = $2""",
        UUID(chosen["card_id"]), user.id,
    )
    if not card or not card_vault.expiry_ok(card["exp_month"], card["exp_year"]):
        await say(f"The card ending {chosen['last4']} was removed or has expired. Pick another, or reply no.")
        return True
    async with conn.transaction():
        if not await _claim(conn, prompt, user, f"card:{card['last4']}"):
            return True
        await conn.execute(
            """INSERT INTO mw_agent_purchase_requests
                   (company_id, project_id, task_id, run_id, prompt_id, user_id, card_id,
                    card_last4, item_name, retailer, checkout_url, amount, currency)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)""",
            prompt["company_id"], prompt["project_id"], prompt["task_id"], prompt["run_id"],
            prompt["id"], user.id, card["id"], card["last4"], payload["item_name"],
            payload.get("retailer"), payload["checkout_url"], payload.get("amount"),
            payload.get("currency"),
        )
        await say(
            f"Approved: {_offer_line(payload)}, on your {_card_label(dict(card))}. "
            "I haven't charged anything. Finish checkout here: "
            f"{payload['checkout_url']}\nIt's saved on the card under Purchases."
        )
    return True
