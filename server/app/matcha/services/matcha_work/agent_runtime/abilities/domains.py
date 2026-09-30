"""Checking and registering domains through our Porkbun account.

Two tools:

  check_domains    (read) availability and Porkbun's live first-year price
                   for up to four names. What it finds is kept in the run.
  register_domain  (commit) registers one name `check_domains` found free.
                   `resolve` freezes the name and the checked price.

What keeps this safe:

  * It always asks. `always_confirm` holds every registration on a card with
    the name, the price, who holds it and that it renews; the yes registers
    exactly that.
  * Real money. Registration draws on our funded Porkbun balance (no Stripe,
    no test mode). So: the purchase allowlist only, private conversation
    only, switched on by the person, `ASSISTANT_COMMIT_MODE=live`, at most
    two a day, and nothing above `ASSISTANT_DOMAIN_MAX_CENTS` (default $50;
    premium names can cost thousands).
  * The price is Porkbun's, never the model's. The model names a domain; the
    cost comes from the check in this run, and Porkbun itself refuses a
    registration whose `cost` doesn't match its live price.
  * Once per approval. The row is UNIQUE on the confirmation, `registering`
    until Porkbun's answer is written, and the Porkbun idempotency key is
    the row id, so a repeat of the same yes never registers twice.
  * Registered under our account's WHOIS-private contact, like Cappe's
    resold domains; it can be transferred out after the 60-day lock.

The Porkbun client is shared with Cappe (`core/services/porkbun.py`).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from app.database import connection_or_direct

from .. import consent, policy
from ..context import RunContext, RunState
from ..registry import Ability, AgentTool, Target, ToolOutput

logger = logging.getLogger(__name__)

KEY = "domains"
ALLOWANCE = "purchases"
MAX_PER_CHECK = 4
MAX_CENTS_ENV = "ASSISTANT_DOMAIN_MAX_CENTS"
DEFAULT_MAX_CENTS = 5000
REGISTRAR_HOST = "porkbun.com"


def max_cents() -> int:
    try:
        return max(0, int(os.getenv(MAX_CENTS_ENV, str(DEFAULT_MAX_CENTS))))
    except ValueError:
        return DEFAULT_MAX_CENTS


def porkbun_configured() -> bool:
    """Both Porkbun keys are set. Read from settings when they are loaded and
    from the environment they come from otherwise (catalog listings in tests
    and scripts run without `load_settings`)."""
    from app.config import get_settings

    try:
        settings = get_settings()
        key, secret = settings.porkbun_api_key, settings.porkbun_secret_key
    except RuntimeError:
        key, secret = os.getenv("PORKBUN_API_KEY"), os.getenv("PORKBUN_SECRET_KEY")
    return bool(key and secret)


def normalize_domain(raw: Any) -> str | None:
    """A registrable name ("matcha.dev", "shop.co.uk"), lowercased and IDNA
    encoded; None for anything else (a subdomain, a URL, a bare word)."""
    text = str(raw or "").strip().lower()
    for prefix in ("https://", "http://"):
        text = text.removeprefix(prefix)
    text = text.split("/", 1)[0].removeprefix("www.")
    host = policy.encode_host(text)
    if host is None:
        return None
    labels = host.split(".")
    suffix = ".".join(labels[-2:])
    wanted = 3 if suffix in policy._MULTI_LABEL_SUFFIXES else 2
    return host if len(labels) == wanted else None


def _money(cents: int | None) -> str:
    return f"${cents / 100:,.2f}" if cents is not None else "unknown"


def _session(state: RunState) -> dict:
    return state.sessions[KEY]


# ── tools ────────────────────────────────────────────────────────────────────

async def _check(ctx: RunContext, state: RunState, args: dict, left: float) -> ToolOutput:
    from app.core.services.porkbun import PorkbunError, get_porkbun

    names = args.get("domains") if isinstance(args.get("domains"), list) else []
    results, refused = [], []
    for raw in names[:MAX_PER_CHECK]:
        domain = normalize_domain(raw)
        if domain is None:
            refused.append(str(raw)[:80])
            continue
        try:
            found = await get_porkbun().check_domain(domain)
        except PorkbunError as exc:
            results.append({"domain": domain, "error": str(exc)[:200]})
            continue
        cost = found.get("wholesale_cents")
        entry = {"domain": domain, "available": bool(found.get("available")), "first_year_price": _money(cost)}
        if entry["available"] and cost is not None and cost > max_cents():
            entry["note"] = f"Above the {_money(max_cents())} limit; can't be registered here."
        _session(state)["checked"][domain] = {"available": entry["available"], "cost_cents": cost}
        results.append(entry)
    payload: dict[str, Any] = {"results": results}
    if refused:
        payload["not_domains"] = refused
    if len(names) > MAX_PER_CHECK:
        payload["note"] = f"Only the first {MAX_PER_CHECK} were checked."
    return ToolOutput(payload=payload, label=f"Checked {len(results)} domain{'s' if len(results) != 1 else ''}",
                      audit={"checked": [r["domain"] for r in results], "refused": refused})


def resolve_registration(args: dict, state: RunState) -> dict:
    domain = normalize_domain(args.get("domain"))
    if domain is None:
        raise ValueError("that isn't a registrable domain name")
    checked = _session(state)["checked"].get(domain)
    if checked is None:
        raise ValueError(f"check {domain} with check_domains first")
    if not checked["available"]:
        raise ValueError(f"{domain} is taken")
    cost = checked["cost_cents"]
    if cost is None:
        raise ValueError(f"Porkbun gave no price for {domain}")
    if cost > max_cents():
        raise ValueError(f"{domain} costs {_money(cost)}, above the {_money(max_cents())} limit")
    return {"domain": domain, "cost_cents": int(cost)}


def _targets(args: dict, state: RunState) -> tuple[Target, ...]:
    return (Target("domain", REGISTRAR_HOST),)


def _lines(args: dict) -> list[dict]:
    return [
        {"label": "Domain", "value": args["domain"], "mono": True},
        {"label": "First year", "value": _money(args["cost_cents"])},
        {"label": "Registrar", "value": "Porkbun, in Matcha's account (WHOIS private)"},
        {"label": "Renews", "value": "Yearly at Porkbun's renewal price, until turned off"},
        {"label": "Payment", "value": "Real money, from Matcha's Porkbun balance"},
    ]


def _preview(args: dict, state: RunState) -> dict:
    return {"title": f"Register {args['domain']} for {_money(args['cost_cents'])}", "lines": _lines(args)}


async def _register(ctx: RunContext, state: RunState, args: dict, left: float) -> ToolOutput:
    """Register once per approval (see the module docstring)."""
    import httpx

    from app.core.services.porkbun import PorkbunError, get_porkbun

    from ..runner import TransportUncertain

    domain, cost = args["domain"], int(args["cost_cents"])
    await ctx.progress.note(f"Registering {domain}…", force=True)
    async with connection_or_direct() as conn:
        row = await conn.fetchrow(
            """INSERT INTO mw_agent_domain_registrations
                   (company_id, user_id, run_id, prompt_id, channel_id, domain, cost_cents)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               ON CONFLICT (prompt_id) DO UPDATE SET updated_at = NOW()
               RETURNING id, status, error, (xmax = 0) AS inserted""",
            ctx.company_id, ctx.user_id, ctx.run_id, ctx.resume_prompt_id, ctx.channel_id, domain, cost,
        )
    lines = _lines(args)
    if not row["inserted"] and row["status"] == "registered":
        return ToolOutput(
            payload={"status": "registered", "domain": domain, "already": True},
            receipt={"title": f"Registered {domain}", "lines": lines,
                     "note": "Already registered with this approval; nothing was bought again."},
            audit={"status": "registered", "registration_id": str(row["id"]), "again": True},
        )
    if not row["inserted"] and row["status"] == "failed":
        return ToolOutput(payload={"error": f"Registration failed earlier: {row['error']}"})
    try:
        await get_porkbun().register(domain, cost_cents=cost, idempotency_key=f"espresso-domain-{row['id']}")
    except PorkbunError as exc:
        if isinstance(exc.__cause__, httpx.HTTPError):
            # The request may have reached Porkbun: the row stays
            # `registering`, and the next attempt replays the same key.
            raise TransportUncertain(f"domain registration {row['id']}") from exc
        message = str(exc)[:300]
        async with connection_or_direct() as conn:
            await conn.execute(
                """UPDATE mw_agent_domain_registrations
                   SET status = 'failed', error = $2, updated_at = NOW() WHERE id = $1""",
                row["id"], message,
            )
        return ToolOutput(payload={"error": f"Porkbun refused it: {message}"},
                          audit={"status": "failed", "registration_id": str(row["id"])})
    try:
        async with connection_or_direct() as conn:
            await conn.execute(
                """UPDATE mw_agent_domain_registrations
                   SET status = 'registered', error = NULL, updated_at = NOW() WHERE id = $1""",
                row["id"],
            )
    except Exception as exc:
        # Registered, but not written down: say "unknown", never "failed".
        raise TransportUncertain(f"domain registration {row['id']} not recorded") from exc
    return ToolOutput(
        payload={"status": "registered", "domain": domain,
                 "note": "Registered in Matcha's Porkbun account. DNS is Porkbun's default until someone points it."},
        receipt={"title": f"Registered {domain}", "lines": lines,
                 "note": "Registered in Matcha's Porkbun account. Point its DNS at Porkbun when you're ready."},
        audit={"status": "registered", "registration_id": str(row["id"])},
    )


CHECK_TOOL = AgentTool(
    name="check_domains", effect="read", step_kind="read", handler=_check,
    description=(
        f"Check whether domain names are free to register, with Porkbun's first-year price. Up to "
        f"{MAX_PER_CHECK} full names per call (\"matcha.dev\", not \"matcha\"). Try a few spellings and "
        "extensions when the first choice is taken."
    ),
    parameters={"type": "object", "properties": {
        "domains": {"type": "array", "items": {"type": "string"}, "description": "Full domain names"},
    }, "required": ["domains"]},
    max_calls=3, timeout_seconds=60,
)

REGISTER_TOOL = AgentTool(
    name="register_domain", effect="commit", step_kind="commit", handler=_register,
    description=(
        "Register one domain that check_domains found available, for one year, in Matcha's Porkbun "
        "account. The person is always shown the name and price and asked to confirm first."
    ),
    parameters={"type": "object", "properties": {
        "domain": {"type": "string", "description": "A name check_domains reported available"},
    }, "required": ["domain"]},
    timeout_seconds=45, min_seconds_left=45,
    too_late_message="Not enough time left to register it; tell the person to ask again.",
    resolve=resolve_registration, targets=_targets, preview=_preview,
    ceilings=((2, 86400),),
    always_confirm=True,
)

def _prompt(_ctx: RunContext) -> str:
    return f"""Domains:
- To see whether a name is free, call check_domains with full names ("matcha.dev"). If it's taken, check a few close alternatives (other extensions, a short prefix or suffix) and say which are free and what they cost.
- Only register when the person asks you to. Call register_domain with a name check_domains found available; it always asks them to confirm first, so stop there.
- Registration uses real money from Matcha's Porkbun account, and nothing above {_money(max_cents())}. Say the price plainly.
- Report exactly what register_domain returned. Setting up DNS or a website is not part of this."""


def build() -> Ability:
    return Ability(
        key=KEY,
        label="Domains",
        tools=(CHECK_TOOL, REGISTER_TOOL),
        prompt_block=_prompt,
        env_ready=porkbun_configured,
        private_only=True,
        consent_version=consent.current_version(KEY),
        allowance=ALLOWANCE,
        session_factory=lambda _ctx: {"checked": {}},
    )
