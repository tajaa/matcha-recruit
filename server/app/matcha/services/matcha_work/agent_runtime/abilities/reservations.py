"""Booking a table or an appointment by driving the booking site.

The agent finds the venue and its booking page with the web ability, then
calls `book_reservation`, which opens that page in the guarded browser
(`matcha_work/browser/`) and lets a computer-use model work the form.

What keeps this safe:

  * It is a commit. The booking site's host is the target, so a site the
    person never named, and that is not a booking platform we know, holds the
    booking for their yes.
  * The browser stays on that one site (navigation allowlist) and can only
    reach public addresses (egress proxy).
  * The person's contact details come from their saved settings. The model
    types placeholders; the real values are swapped in as the keys are pressed.
  * Card details are never entered, by construction: a payment field, or any
    text that holds a card number, stops the booking and hands back a link.
  * A captcha or a login wall stops it the same way. Nothing here tries to get
    past either.
  * "Booked" is only reported when the page itself says so.

It runs on its own worker queue (`AGENT_BROWSER_QUEUE`): Chromium does not fit
in the main worker. Without that queue the ability is not offered at all.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from app.core.services import card_vault

from .. import consent, policy
from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, Target, ToolOutput

logger = logging.getLogger(__name__)

KEY = "reservations"
BROWSER_QUEUE_ENV = "AGENT_BROWSER_QUEUE"
BOOKING_SECONDS = 170.0
MAX_TURNS = 18

# Booking platforms a person expects a table to be booked through. A venue's
# own site is not on this list, so booking there asks first.
TRUSTED_BOOKING_DOMAINS = frozenset({
    "opentable.com", "resy.com", "exploretock.com", "sevenrooms.com", "yelp.com",
    "tablein.com", "quandoo.com", "thefork.com", "bookatable.com",
})

Booker = Callable[[RunContext, dict], Awaitable[dict]]


def browser_ready() -> bool:
    return bool(os.getenv(BROWSER_QUEUE_ENV))


def _host(url: Any) -> str:
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError as exc:
        raise ValueError("that is not a web address") from exc
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ValueError("the booking page must be an https address")
    host = policy.encode_host(parts.hostname)
    if host is None:
        raise ValueError("that is not a web address")
    return host


def _details(args: dict) -> dict:
    try:
        party = int(args.get("party_size"))
    except (TypeError, ValueError) as exc:
        raise ValueError("party_size must be a number") from exc
    if not 1 <= party <= 20:
        raise ValueError("party_size must be between 1 and 20")
    day = str(args.get("date") or "")
    try:
        date.fromisoformat(day)
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc
    at = str(args.get("time") or "")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at):
        raise ValueError("time must be HH:MM, 24 hour")
    venue = " ".join(str(args.get("venue_name") or "").split())[:120]
    if not venue:
        raise ValueError("venue_name is required")
    requests = " ".join(str(args.get("special_requests") or "").split())[:300]
    if card_vault.contains_pan(requests):
        raise ValueError("special requests cannot hold a card number")
    return {"venue": venue, "party_size": party, "date": day, "time": at, "special_requests": requests}


def resolve_booking(args: dict, state: RunState) -> dict:
    from app.matcha.services.matcha_work.agent_card.schema import normalize_url

    details = _details(args)
    url = str(args.get("url") or "").strip()
    host = _host(url)
    seen = {normalize_url(u) for u in state.provenance}
    if normalize_url(url) not in seen:
        # The model may not mint the address of a booking page any more than
        # it may mint a buy link.
        raise ValueError("the booking page must be one web_search returned or fetch_page loaded")
    return {**details, "url": url, "host": host}


def _targets(args: dict, state: RunState) -> tuple[Target, ...]:
    return (Target("domain", args["host"]),)


def _preview(args: dict, state: RunState) -> dict:
    lines = [
        {"label": "Where", "value": args["venue"]},
        {"label": "When", "value": f"{args['date']} at {args['time']}"},
        {"label": "Party", "value": str(args["party_size"])},
        {"label": "Booked on", "value": args["host"]},
    ]
    if args.get("special_requests"):
        lines.append({"label": "Requests", "value": args["special_requests"]})
    return {"title": "Book a reservation", "lines": lines}


def contact_of(ctx: RunContext) -> dict:
    contact = (ctx.grants.get(KEY) or {}).get("contact") or {}
    if not contact.get("name") or not (contact.get("phone") or contact.get("email")):
        raise ValueError("no booking contact details are saved")
    return contact


_STATUS_TEXT = {
    "booked": "Booked.",
    "unverified": "The form was submitted, but the site did not show a confirmation. Check before relying on it.",
    "unavailable": "That time was not available.",
    "handoff": "The site asks for payment details, which Espresso never enters. Finish it at the link.",
    "blocked": "The site asked for a login or a human check. Finish it at the link.",
    "failed": "The booking could not be completed.",
}


def reservation_block(details: dict, outcome: dict) -> dict:
    status = outcome.get("status") if outcome.get("status") in _STATUS_TEXT else "failed"
    link = outcome.get("url") if status in ("handoff", "blocked", "unverified", "failed") else None
    return {
        "type": "reservation",
        "venue": details["venue"],
        "when": f"{details['date']} {details['time']}",
        "party_size": details["party_size"],
        "status": status,
        "confirmation": outcome.get("confirmation") if status == "booked" else None,
        "handoff_url": link,
    }


def _tools(booker: Booker) -> tuple[AgentTool, ...]:
    async def book(ctx: RunContext, state: RunState, args: dict, left: float) -> ToolOutput:
        await ctx.progress.note(f"Booking {args['venue']}…", force=True)
        outcome = await booker(ctx, {**args, "contact": contact_of(ctx)})
        block = reservation_block(args, outcome)
        state.sessions[KEY]["blocks"].append(block)
        status = block["status"]
        payload = {"status": status, "note": _STATUS_TEXT[status]}
        if block["confirmation"]:
            payload["confirmation"] = block["confirmation"]
        if block["handoff_url"]:
            payload["finish_at"] = block["handoff_url"]
        receipt: dict = {"note": _STATUS_TEXT[status]}
        if status != "booked":
            receipt["status"] = (
                "handoff" if status in ("handoff", "blocked")
                else "unknown" if status == "unverified" else "failed"
            )
        if block["confirmation"]:
            receipt["lines"] = [*_preview(args, state)["lines"],
                                {"label": "Confirmation", "value": block["confirmation"], "mono": True}]
        if block["handoff_url"]:
            receipt["link"] = {"label": "Finish booking", "url": block["handoff_url"]}
        return ToolOutput(
            payload=payload, receipt=receipt,
            audit={"status": status, "host": args["host"], "turns": outcome.get("turns")},
        )

    return (
        AgentTool(
            name="book_reservation", effect="commit", step_kind="browse", handler=book,
            description=(
                "Book a table or appointment on the venue's booking page. Give the exact booking "
                "page address you found with web_search or fetch_page. The person's contact details "
                "are filled in for you. If the site needs payment, a login or a human check, you get "
                "a link back to pass on instead."
            ),
            parameters={"type": "object", "properties": {
                "url": {"type": "string", "description": "The https booking page, exactly as found"},
                "venue_name": {"type": "string"},
                "party_size": {"type": "integer"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM, 24 hour, venue local time"},
                "special_requests": {"type": "string"},
            }, "required": ["url", "venue_name", "party_size", "date", "time"]},
            # Never start a booking the run could cut off halfway: the whole
            # budget has to be there before the first click.
            timeout_seconds=BOOKING_SECONDS + 20, min_seconds_left=BOOKING_SECONDS + 20,
            too_late_message="Not enough time left to book; give the person the booking link instead.",
            resolve=resolve_booking, targets=_targets, preview=_preview,
            ceilings=((5, 3600), (15, 86400)),
        ),
    )


_RESERVATION_BLOCK: dict[str, Any] = {
    "type": "object",
    "description": "The booking you made or handed back. Filled in by the system; send it empty.",
    "properties": {},
}

_PROMPT = """Booking a table or appointment:
- Find the venue and its own booking page first (web_search, then fetch_page to confirm it is the right place).
- Then call book_reservation with that exact page address, the date, the time and the party size.
- If the person did not give a date, a time or how many people, ask them. Do not guess.
- You never see or type their name, phone or email: they are filled in for you.
- You never pay and never enter card details. If a booking needs a card you get a link back; give it to the person.
- Report exactly what book_reservation returned. Only say it is booked when the status is "booked".
- Add one `reservation` block to your answer after booking."""


def gate_block(block_type: str, raw: Any, state: RunState) -> tuple[dict | None, list[str]]:
    blocks = state.sessions[KEY]["blocks"]
    if not blocks:
        return None, ["Dropped a reservation block: nothing was booked in this run"]
    # Server-authored: what the model wrote in the block is ignored.
    return dict(blocks[-1]), []


async def _book_in_browser(ctx: RunContext, job: dict) -> dict:
    from app.matcha.services.matcha_work.browser.booking import book

    return await book(job, on_status=lambda text: ctx.progress.note(text))


def build(*, booker: Booker | None = None,
          env_ready: Callable[[], bool] = browser_ready) -> Ability:
    return Ability(
        key=KEY,
        label="Reservations",
        tools=_tools(booker or _book_in_browser),
        prompt_block=lambda _ctx: _PROMPT,
        entitlement="assistant",
        env_ready=env_ready,
        private_only=True,
        consent_version=consent.current_version(KEY),
        session_factory=lambda _ctx: {"blocks": []},
        block_schemas={"reservation": _RESERVATION_BLOCK},
        gate=gate_block,
        trusted_domains=TRUSTED_BOOKING_DOMAINS,
    )
