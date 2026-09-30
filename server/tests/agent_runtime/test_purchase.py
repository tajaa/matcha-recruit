"""The assistant's purchase ability: what it loads, what it freezes, and what
a yes does. Nothing here opens a connection or calls Stripe."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_runtime import (
    catalog,
    consent,
    policy,
    prompt,
    result,
    runner,
)
from app.matcha.services.matcha_work.agent_runtime.abilities import purchase
from app.matcha.services.matcha_work.agent_runtime.context import FrozenAction, RunState
from app.matcha.services.matcha_work.agent_runtime.policy import (
    Grounding,
    PolicyContext,
)
from app.matcha.services.matcha_work.agent_runtime.registry import (
    AgentTool,
    CatalogError,
    Target,
    validate_tool,
)

from .helpers import (
    FakeClient,
    FakeConn,
    call,
    connection,
    context,
    response,
    wire_store,
)

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def _pick(name, *, amount=65.0, url="https://vandre.example.com/hat", retailer="Vandre"):
    return {
        "name": name, "brand": "Vandre", "why": ["Organic"], "reviews": [], "images": [],
        "price": {"amount": amount, "currency": "USD", "source_url": url} if amount is not None else None,
        "rating": None,
        "buy_links": [{"retailer": retailer, "url": url, "price": 1.0}] if url else [],
    }


STORED = {
    "schema": "agent_result.v2", "headline": "Best pick: Vandre hat", "summary": "Organic.",
    "blocks": [{
        "type": "picks", "criteria": [],
        "top_pick": _pick("Organic Cotton Baseball Hat"),
        "alternatives": [
            _pick("Core Casual Cap", amount=35.0, url="https://organicbasics.example.com/cap",
                  retailer="Organic Basics"),
            _pick("No Link Hat", url=None),
        ],
    }],
}

CARD = {"id": uuid4(), "label": "Personal", "brand": "visa", "last4": "4242", "exp_month": 12,
        "exp_year": 2031, "billing_address": None}
HOME = {"id": uuid4(), "name": "Haley Smith", "line1": "1 Main St", "line2": "", "city": "Oakland",
        "region": "CA", "postal_code": "94607", "country": "US", "phone": "510 555 0100",
        "is_default": True, "created_at": NOW}


def _conn(*, results=(STORED,), cards=(CARD,), addresses=(HOME,)):
    runs = [{"id": uuid4(), "result": json.dumps(r)} for r in results]
    return (FakeConn()
            .on("FROM mw_project_agent_runs", runs)
            .on("FROM mw_payment_cards", [dict(c) for c in cards])
            .on("FROM mw_shipping_addresses", [dict(a) for a in addresses]))


def _ctx(**over):
    base = {
        "channel_id": uuid4(), "commit_mode": "live",
        "policy": PolicyContext(surface="assistant", private_conversation=True,
                                grounding=Grounding(user_texts=("buy it from vandre.example.com",))),
    }
    base.update(over)
    return context(**base)


async def _prepared(monkeypatch, conn, ctx=None):
    monkeypatch.setattr(purchase, "connection_or_direct", connection(conn))
    state = RunState(started=0.0, sessions={purchase.KEY: purchase._new_session(None)})
    out = await purchase._prepare(ctx or _ctx(), state, {}, 60.0)
    return state, out


# ── loading ───────────────────────────────────────────────────────────────────

def test_offers_are_every_buyable_pick_top_first_with_the_gated_price():
    offers = purchase.offers_from_result(STORED)
    assert [o["item_name"] for o in offers] == ["Organic Cotton Baseball Hat", "Core Casual Cap"]
    # The source-checked price, never the buy link's own claim.
    assert offers[0]["amount"] == 65.0 and offers[0]["currency"] == "USD"
    assert offers[0]["checkout_url"] == "https://vandre.example.com/hat"


def test_a_card_result_v1_is_buyable_too():
    v1 = {"schema": "agent_result.v1", "answer_type": "recommendation", "top_pick": _pick("Hat"),
          "alternatives": []}
    assert [o["item_name"] for o in purchase.offers_from_result(v1)] == ["Hat"]
    assert purchase.offers_from_result({"schema": "agent_result.v2", "blocks": []}) == []
    assert purchase.offers_from_result(None) == []


@pytest.mark.asyncio
async def test_prepare_lists_ids_and_keeps_numbers_streets_and_phones_from_the_model(monkeypatch):
    state, out = await _prepared(monkeypatch, _conn())
    payload = out.payload
    assert payload["ready"] is True
    assert [i["item_id"] for i in payload["items"]] == ["item-1", "item-2"]
    assert payload["items"][0]["price"] == "$65.00"
    assert payload["cards"] == [{"card_id": "card-1", "card": "Visa ending 4242 (Personal)"}]
    assert payload["addresses"] == [{"address_id": "address-1", "ships_to": "Haley Smith, Oakland CA",
                                     "default": True}]
    text = json.dumps(payload)
    assert "1 Main St" not in text and "555" not in text and "94607" not in text
    assert state.sessions[purchase.KEY]["setup"] is None


@pytest.mark.asyncio
async def test_prepare_leaves_out_the_current_run_and_other_peoples_runs(monkeypatch):
    ctx = _ctx()
    conn = _conn()
    await _prepared(monkeypatch, conn, ctx)
    query, args = conn.ran("FROM mw_project_agent_runs")[0][1:]
    assert "requested_by = $2" in query and "id <> $3" in query and "kind = 'assistant'" in query
    assert args[:3] == (ctx.channel_id, ctx.user_id, ctx.run_id)


@pytest.mark.asyncio
async def test_expired_cards_do_not_count(monkeypatch):
    expired = {**CARD, "exp_year": 2020}
    _, out = await _prepared(monkeypatch, _conn(cards=(expired,)))
    assert out.payload["ready"] is False and out.payload["missing"] == ["payment_card"]


@pytest.mark.asyncio
async def test_missing_card_and_address_become_a_server_written_setup_block(monkeypatch):
    state, out = await _prepared(monkeypatch, _conn(cards=(), addresses=()))
    assert out.payload["missing"] == ["payment_card", "shipping_address"]
    assert "Never ask for a card number" in out.payload["next"]
    ability = purchase.build()
    # The model left the block out; it is added anyway, from the session.
    finished, _ = result.normalize({"headline": "Add a card first", "summary": "Then I can buy it."},
                                   state, [ability])
    setup = finished["blocks"][0]
    assert setup["type"] == "purchase_setup"
    assert [s["key"] for s in setup["steps"]] == ["payment_card", "shipping_address"]
    assert setup["steps"][0]["where"] == "Settings → Payment cards"
    # What the model writes in the block is ignored; only one block is kept.
    again, _ = result.normalize({"headline": "h", "summary": "s",
                                 "blocks": [{"type": "purchase_setup", "steps": [{"label": "evil"}]}]},
                                state, [ability])
    assert again["blocks"] == [setup]


@pytest.mark.asyncio
async def test_nothing_to_buy_says_so(monkeypatch):
    _, out = await _prepared(monkeypatch, _conn(results=()))
    assert out.payload["ready"] is False and out.payload["missing"] == ["item"]


def test_no_setup_block_when_nothing_is_missing():
    state = RunState(started=0.0, sessions={purchase.KEY: purchase._new_session(None)})
    assert purchase.auto_blocks(state) == []
    assert purchase.gate_block("purchase_setup", {}, state)[0] is None


# ── resolving and holding ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_freezes_the_stored_item_card_and_address(monkeypatch):
    state, _ = await _prepared(monkeypatch, _conn())
    frozen = purchase.resolve_purchase({"item_id": "item-1"}, state)
    assert frozen["item"]["item_name"] == "Organic Cotton Baseball Hat"
    assert frozen["item"]["amount"] == 65.0 and frozen["host"] == "vandre.example.com"
    assert frozen["card"] == {"card_id": str(CARD["id"]), "brand": "visa", "last4": "4242", "label": "Personal"}
    assert frozen["shipping"]["line1"] == "1 Main St" and frozen["billing"] is None
    preview = purchase._preview(frozen, state)
    assert preview["title"] == "Buy Organic Cotton Baseball Hat for $65.00"
    lines = {line["label"]: line["value"] for line in preview["lines"]}
    assert lines["Ship to"] == "Haley Smith, 1 Main St, Oakland, CA 94607, US"
    assert lines["Bill to"] == "Same as shipping"
    assert lines["Card"] == "Visa ending 4242 (Personal)"
    assert "no real money" in lines["Payment"]


@pytest.mark.asyncio
async def test_a_card_with_its_own_billing_address_bills_there(monkeypatch):
    billing = {k: HOME[k] for k in ("name", "line1", "line2", "city", "region", "postal_code", "country", "phone")}
    billing["line1"] = "9 Bank St"
    state, _ = await _prepared(monkeypatch, _conn(cards=({**CARD, "billing_address": json.dumps(billing)},)))
    frozen = purchase.resolve_purchase({"item_id": "item-2"}, state)
    assert frozen["billing"]["line1"] == "9 Bank St"
    assert frozen["item"]["item_name"] == "Core Casual Cap"


@pytest.mark.asyncio
@pytest.mark.parametrize("args, cards, why", [
    ({"item_id": "item-9"}, (CARD,), "no item"),
    ({"item_id": "item-1", "card_id": "card-7"}, (CARD,), "no card"),
    ({"item_id": "item-1", "address_id": "address-3"}, (CARD,), "no address"),
    ({"item_id": "item-1"}, (CARD, {**CARD, "id": uuid4(), "last4": "1881"}), "ask which one"),
])
async def test_resolve_refuses_ids_it_did_not_load(monkeypatch, args, cards, why):
    state, _ = await _prepared(monkeypatch, _conn(cards=cards))
    with pytest.raises(ValueError, match=why):
        purchase.resolve_purchase(args, state)


def test_resolve_needs_prepare_first():
    state = RunState(started=0.0, sessions={purchase.KEY: purchase._new_session(None)})
    with pytest.raises(ValueError, match="prepare_purchase first"):
        purchase.resolve_purchase({"item_id": "item-1"}, state)


@pytest.mark.asyncio
async def test_a_purchase_is_always_held_even_when_the_store_was_named(monkeypatch):
    wire_store(monkeypatch)
    monkeypatch.setattr(purchase, "connection_or_direct", connection(_conn()))
    charged = AsyncMock()
    monkeypatch.setattr(purchase, "_buy", charged)
    client = FakeClient([
        response(call("prepare_purchase")),
        response(call("buy_item", {"item_id": "item-1"})),
    ])
    out = await runner.run_agent(
        _ctx(), client=client, abilities=[purchase.build()],
        contract=runner.ResultContract(finish=result.finish_tool([purchase.build()]),
                                       normalize=lambda a, s: result.normalize(a, s, [purchase.build()])),
        instructions="sys", first_input=[],
    )
    assert out.kind == "confirmation" and out.decision.reason == "always_confirm"
    assert out.pending.tool == "buy_item"
    assert out.pending.args["item"]["checkout_url"] == "https://vandre.example.com/hat"
    assert charged.await_count == 0
    # What gets frozen needs nothing from this run.
    assert FrozenAction.from_payload(json.loads(json.dumps(out.pending.to_payload()))) == out.pending


def test_always_confirm_is_a_policy_decision_and_a_yes_goes_through():
    tool = purchase.BUY_TOOL
    grounded = PolicyContext(surface="assistant", private_conversation=True,
                             grounding=Grounding(user_texts=("vandre.example.com",)))
    target = (Target("domain", "vandre.example.com"),)
    held = policy.evaluate_commit(grounded, tool, {}, targets=target, private_only=True)
    assert held.verdict == "confirm" and held.reason == "always_confirm"
    approved = policy.evaluate_commit(
        PolicyContext(surface="assistant", private_conversation=True, grounding=Grounding(), approved=True),
        tool, {}, targets=target, private_only=True,
    )
    assert approved.verdict == "allow"
    outside = policy.evaluate_commit(
        PolicyContext(surface="project_chat", private_conversation=False, grounding=Grounding(), approved=True),
        tool, {}, targets=target, private_only=True,
    )
    assert outside.verdict == "deny"


def test_only_a_commit_tool_can_always_confirm():
    with pytest.raises(CatalogError, match="always confirm"):
        validate_tool(AgentTool(name="x", effect="read", description="", parameters={}, step_kind="read",
                                handler=AsyncMock(), always_confirm=True))


# ── carrying out a yes ────────────────────────────────────────────────────────

def _frozen(**over):
    args = {
        "item": {"item_name": "Organic Cotton Baseball Hat", "brand": "Vandre", "retailer": "Vandre",
                 "checkout_url": "https://vandre.example.com/hat", "amount": 65.0, "currency": "USD",
                 "image_url": None, "source_run_id": str(uuid4())},
        "host": "vandre.example.com",
        "card": {"card_id": str(CARD["id"]), "brand": "visa", "last4": "4242", "label": "Personal"},
        "shipping": {k: HOME[k] for k in ("name", "line1", "line2", "city", "region", "postal_code",
                                           "country", "phone")},
        "billing": None,
    }
    args.update(over)
    state = RunState(started=0.0, sessions={purchase.KEY: purchase._new_session(None)})
    return FrozenAction(tool="buy_item", args=args, targets=purchase._targets(args, state),
                        preview=purchase._preview(args, state))


PROMPT_ID = uuid4()


async def _approve(monkeypatch, conn, frozen=None, commit_mode="live"):
    wire_store(monkeypatch)
    monkeypatch.setattr(purchase, "connection_or_direct", connection(conn))
    receipts = []

    async def on_receipt(receipt):
        receipts.append(receipt)

    client = FakeClient([response(call("finish", {"headline": "Bought it", "summary": "Test purchase."}))])
    abilities = [purchase.build()]
    out = await runner.run_agent(
        _ctx(resume=frozen or _frozen(), resume_prompt_id=PROMPT_ID, commit_mode=commit_mode,
             on_receipt=on_receipt),
        client=client, abilities=abilities,
        contract=runner.ResultContract(finish=result.finish_tool(abilities),
                                       normalize=lambda a, s: result.normalize(a, s, abilities)),
        instructions="sys", first_input=[],
    )
    return out, receipts, client


def _buy_conn(purchase_id, *, status=None, inserted=True, payment_intent_id=None, error=None):
    def row(*args):
        return {"id": purchase_id, "status": status or args[-1], "stripe_payment_intent_id": payment_intent_id,
                "charge_error": error, "inserted": inserted}

    return (FakeConn()
            .on("FROM mw_payment_cards", dict(CARD))
            .on("INSERT INTO mw_agent_purchase_requests", row))


@pytest.mark.asyncio
async def test_a_yes_records_the_purchase_and_charges_stripe_test_mode(monkeypatch):
    purchase_id = uuid4()
    conn = _buy_conn(purchase_id)
    from app.matcha.services.matcha_work.agent_card import test_charge

    monkeypatch.setattr(test_charge, "test_key", lambda: "sk_test_x")
    charge = AsyncMock(return_value={"status": "test_charged", "payment_intent_id": "pi_1", "error": None})
    monkeypatch.setattr(test_charge, "charge", charge)
    out, receipts, _ = await _approve(monkeypatch, conn)
    query, insert = conn.ran("INSERT INTO mw_agent_purchase_requests")[0][1:]
    # Keyed on the approval: a second run of the same yes finds this row.
    assert "ON CONFLICT (prompt_id)" in query and insert[2] == PROMPT_ID
    assert insert[5] == "4242" and insert[6] == "Organic Cotton Baseball Hat"
    assert insert[9] == 65.0 and insert[10] == "USD"
    assert json.loads(insert[12])["line1"] == "1 Main St" and insert[13] is None
    assert insert[14] == "charging"  # until Stripe's answer is written
    assert charge.await_args.kwargs["amount"] == 65.0 and charge.await_args.kwargs["brand"] == "visa"
    assert conn.ran("UPDATE mw_agent_purchase_requests")[0][2][1] == "test_charged"
    receipt = receipts[0]
    assert receipt["status"] == "done" and receipt["title"] == "Bought Organic Cotton Baseball Hat"
    assert "TEST mode" in receipt["note"]
    assert receipt["link"] == {"label": "View at store", "url": "https://vandre.example.com/hat"}
    assert any(line["label"] == "Order ref" and line["value"] == str(purchase_id)[:8].upper()
               for line in receipt["lines"])
    assert out.kind == "result"


@pytest.mark.asyncio
async def test_without_a_test_key_it_is_a_handoff_to_the_store(monkeypatch):
    conn = _buy_conn(uuid4())
    from app.matcha.services.matcha_work.agent_card import test_charge

    monkeypatch.setattr(test_charge, "test_key", lambda: None)
    charge = AsyncMock()
    monkeypatch.setattr(test_charge, "charge", charge)
    _, receipts, _ = await _approve(monkeypatch, conn)
    assert charge.await_count == 0
    assert conn.ran("INSERT INTO mw_agent_purchase_requests")[0][2][14] == "handoff"
    assert receipts[0]["status"] == "handoff"
    assert receipts[0]["link"] == {"label": "Finish checkout", "url": "https://vandre.example.com/hat"}


@pytest.mark.asyncio
async def test_no_verified_price_is_never_charged(monkeypatch):
    conn = _buy_conn(uuid4())
    from app.matcha.services.matcha_work.agent_card import test_charge

    monkeypatch.setattr(test_charge, "test_key", lambda: "sk_test_x")
    charge = AsyncMock()
    monkeypatch.setattr(test_charge, "charge", charge)
    item = {**_frozen().args["item"], "amount": None, "currency": None}
    _, receipts, _ = await _approve(monkeypatch, conn, _frozen(item=item))
    assert charge.await_count == 0 and receipts[0]["status"] == "handoff"
    assert "No verified price" in receipts[0]["note"]


@pytest.mark.asyncio
async def test_a_failed_test_charge_is_a_failed_receipt(monkeypatch):
    conn = _buy_conn(uuid4())
    from app.matcha.services.matcha_work.agent_card import test_charge

    monkeypatch.setattr(test_charge, "test_key", lambda: "sk_test_x")
    monkeypatch.setattr(test_charge, "charge", AsyncMock(
        return_value={"status": "test_failed", "payment_intent_id": None, "error": "Declined."}))
    _, receipts, _ = await _approve(monkeypatch, conn)
    assert receipts[0]["status"] == "failed" and "Declined." in receipts[0]["note"]


@pytest.mark.asyncio
async def test_a_card_removed_since_the_yes_buys_nothing(monkeypatch):
    conn = FakeConn().on("FROM mw_payment_cards", None)
    _, receipts, _ = await _approve(monkeypatch, conn)
    assert conn.ran("INSERT INTO") == []
    assert receipts[0]["status"] == "failed" and "removed or has expired" in receipts[0]["note"]


@pytest.mark.asyncio
async def test_a_dry_run_buys_nothing(monkeypatch):
    conn = _buy_conn(uuid4())
    _, receipts, _ = await _approve(monkeypatch, conn, commit_mode="dry_run")
    assert conn.calls == [] and receipts[0]["status"] == "dry_run"


# ── who gets it ───────────────────────────────────────────────────────────────

async def _no_fetch(_url):
    return {}, set()


def _grant():
    return {purchase.KEY: {}}


def test_buying_needs_the_allowance_the_switch_and_the_private_conversation():
    everything = catalog.build_catalog(fetch_page=_no_fetch)
    buy = next(a for a in everything if a.key == purchase.KEY)
    allowed = frozenset({purchase.ALLOWANCE})
    assert catalog.availability(buy, catalog.Situation(private=True, grants=_grant(), allowed=allowed)).available
    assert not catalog.availability(buy, catalog.Situation(private=True, grants=_grant())).available
    assert catalog.availability(buy, catalog.Situation(private=True, allowed=allowed)).needs_consent
    assert not catalog.availability(buy, catalog.Situation(private=False, grants=_grant(),
                                                           allowed=allowed)).available
    assert buy.consent_version == consent.current_version(purchase.KEY)


def test_the_allowance_is_the_purchase_allowlist(monkeypatch):
    monkeypatch.setenv("AGENT_PURCHASE_ALLOWED_EMAILS", "haley@example.com")
    assert catalog.allowances_for(SimpleNamespace(role="individual", email="haley@example.com")) == {"purchases"}
    assert catalog.allowances_for(SimpleNamespace(role="admin", email="a@example.com")) == {"purchases"}
    assert catalog.allowances_for(SimpleNamespace(role="individual", email="x@example.com")) == frozenset()


def test_the_model_is_told_what_would_switch_buying_on_but_only_for_allowed_accounts():
    everything = catalog.build_catalog(fetch_page=_no_fetch)
    hints = dict(catalog.switch_on_hints(everything, catalog.Situation(
        private=True, allowed=frozenset({purchase.ALLOWANCE}))))
    assert hints["Buying"] == "Switch it on in Espresso's settings first."
    assert "Buying" not in dict(catalog.switch_on_hints(everything, catalog.Situation(private=True)))
    text = prompt.build_system_prompt(context(), [], unavailable=[("Buying", "Switch it on.")])
    assert "- Buying: Switch it on." in text
    assert "Not available in this run" not in prompt.build_system_prompt(context(), [])


# ── once per approval ─────────────────────────────────────────────────────────

def _stripe(monkeypatch, **result):
    from app.matcha.services.matcha_work.agent_card import test_charge

    monkeypatch.setattr(test_charge, "test_key", lambda: "sk_test_x")
    charge = AsyncMock(return_value={"status": "test_charged", "payment_intent_id": "pi_1", "error": None, **result})
    monkeypatch.setattr(test_charge, "charge", charge)
    return charge


@pytest.mark.asyncio
async def test_a_second_run_of_a_charged_yes_charges_nothing(monkeypatch):
    charge = _stripe(monkeypatch)
    conn = _buy_conn(uuid4(), status="test_charged", inserted=False, payment_intent_id="pi_first")
    _, receipts, _ = await _approve(monkeypatch, conn)
    assert charge.await_count == 0 and conn.ran("UPDATE mw_agent_purchase_requests") == []
    assert receipts[0]["status"] == "done" and "nothing was charged again" in receipts[0]["note"]
    assert any("pi_first" in line["value"] for line in receipts[0]["lines"])


@pytest.mark.asyncio
async def test_a_second_run_of_a_failed_or_handed_off_yes_reports_it_again(monkeypatch):
    charge = _stripe(monkeypatch)
    _, receipts, _ = await _approve(monkeypatch, _buy_conn(uuid4(), status="test_failed", inserted=False,
                                                           error="Declined."))
    assert receipts[0]["status"] == "failed" and "Declined." in receipts[0]["note"]
    _, receipts, _ = await _approve(monkeypatch, _buy_conn(uuid4(), status="handoff", inserted=False))
    assert receipts[0]["status"] == "handoff"
    assert charge.await_count == 0


@pytest.mark.asyncio
async def test_a_charge_left_unsettled_is_retried_under_the_same_idempotency_key(monkeypatch):
    charge = _stripe(monkeypatch)
    purchase_id = uuid4()
    conn = _buy_conn(purchase_id, status="charging", inserted=False)
    _, receipts, _ = await _approve(monkeypatch, conn)
    assert charge.await_args.kwargs["purchase_id"] == purchase_id  # Stripe key agent-purchase-<id>
    assert conn.ran("UPDATE mw_agent_purchase_requests")[0][2][1] == "test_charged"
    assert receipts[0]["status"] == "done"


@pytest.mark.asyncio
async def test_an_unsettled_charge_without_a_key_is_unknown_not_failed(monkeypatch):
    from app.matcha.services.matcha_work.agent_card import test_charge

    monkeypatch.setattr(test_charge, "test_key", lambda: None)
    _, receipts, _ = await _approve(monkeypatch, _buy_conn(uuid4(), status="charging", inserted=False))
    assert receipts[0]["status"] == "unknown"


@pytest.mark.asyncio
async def test_a_crash_after_the_charge_is_an_unknown_outcome_and_the_row_stays_charging(monkeypatch):
    from app.matcha.services.matcha_work.agent_card import test_charge

    monkeypatch.setattr(test_charge, "test_key", lambda: "sk_test_x")
    monkeypatch.setattr(test_charge, "charge", AsyncMock(side_effect=RuntimeError("socket closed")))
    conn = _buy_conn(uuid4())
    _, receipts, _ = await _approve(monkeypatch, conn)
    assert conn.ran("UPDATE mw_agent_purchase_requests") == []
    assert receipts[0]["status"] == "unknown" and "Check before retrying" in receipts[0]["note"]


# ── what counts as buyable, and what "it" is ──────────────────────────────────

def test_an_http_buy_link_is_not_buyable():
    plain = {**STORED, "blocks": [{**STORED["blocks"][0], "top_pick": _pick("Hat", url="http://shop.example.com/hat"),
                                   "alternatives": []}]}
    assert purchase.offers_from_result(plain) == []


def _answer(headline, blocks):
    return {"schema": "agent_result.v2", "headline": headline, "summary": "s", "blocks": blocks}


@pytest.mark.asyncio
async def test_it_is_the_latest_answer_not_an_older_product(monkeypatch):
    newer = _answer("Your calendar is free", [])
    question = {"schema": "agent_result.v2", "question": {"question": "Which size?"}}
    _, out = await _prepared(monkeypatch, _conn(results=(question, newer, STORED)))
    assert out.payload["ready"] is True
    assert all(not item["from_latest_answer"] for item in out.payload["items"])
    assert "ask which one" in out.payload["next"]


@pytest.mark.asyncio
async def test_a_question_run_does_not_hide_the_latest_answer(monkeypatch):
    question = {"schema": "agent_result.v2", "question": {"question": "Which card?"}}
    older = _answer("Best cap", [{"type": "picks", "criteria": [], "top_pick": _pick("Old Cap"), "alternatives": []}])
    _, out = await _prepared(monkeypatch, _conn(results=(question, STORED, older)))
    items = out.payload["items"]
    assert items[0]["name"] == "Organic Cotton Baseball Hat" and items[0]["from_latest_answer"]
    assert items[-1]["name"] == "Old Cap" and not items[-1]["from_latest_answer"]
    assert "is the top pick of their latest answer, item-1" in out.payload["next"]


def test_offered_is_the_one_allowance_rule():
    buy = purchase.build()
    assert not catalog.offered(buy, catalog.Situation(private=True))
    assert catalog.offered(buy, catalog.Situation(private=True, allowed=frozenset({purchase.ALLOWANCE})))
    assert catalog.offered(catalog.build_catalog(fetch_page=_no_fetch)[0], catalog.Situation(private=True))
