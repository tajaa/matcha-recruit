"""Actions on findings: the registry, Buy, and propose -> confirm -> carry out once."""
import json
from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

import pytest

from app.core.models.auth import CurrentUser
from app.core.services.safe_fetch import FetchedResponse, UnsafeURL
from app.matcha.services.matcha_work.agent_tasks import actions, playbooks
from app.matcha.services.matcha_work.agent_tasks.actions import buy, service
from app.matcha.services.matcha_work.agent_tasks.actions.base import ActionContext, ActionError, Line, Proposal
from app.matcha.services.matcha_work.agent_tasks.service import AgentTaskError
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import ITEM, NOW, TASK, USER, item_row, task_row

PERSON = CurrentUser(id=USER, email="tess@example.test", role="individual")
STORE = "https://www.drbronner.com/products/peppermint-organic-lip-balms?variant=36027946893476&utm_source=goog"
PRODUCT = {"handle": "peppermint-organic-lip-balms", "variants": [
    {"id": 11, "title": "Default Title", "price": 450, "available": False},
    {"id": 36027946893476, "title": ".15 oz", "price": 399, "available": True},
]}
ADDRESS = {"name": "Tess Alex", "line1": "1 Main St", "line2": "", "city": "Oakland", "region": "CA",
           "postal_code": "94607", "country": "US", "phone": ""}


def _product_row(**over):
    fields = {"price": {"value": 3.99, "currency": "USD", "status": "verified",
                        "evidence": {"quote": "Google Shopping: $3.99", "url": STORE, "origin": "provider"}}}
    return item_row(**{"kind": "product", "title": "Dr Bronner's Organic Lip Balm", "subtitle": "Dr. Bronner's",
                       "url": STORE, "fields": json.dumps(fields), **over})


def _ctx(**over):
    return ActionContext(user=PERSON, task=task_row(), item=_product_row(**over))


def _fetched(body, status=200, ctype="application/json", truncated=False, final="u"):
    data = json.dumps(body).encode() if not isinstance(body, bytes) else body
    return FetchedResponse(url="u", final_url=final, status=status, content_type=ctype, body=data, truncated=truncated)


SHOP = "dr-bronners-us.myshopify.com"
META = {"myshopify_domain": SHOP, "currency": "USD", "name": "Dr. Bronner's"}


def _store(meta=META, product=PRODUCT, home="https://www.drbronner.com"):
    """A Shopify store: its meta.json, and its product fetched through the
    shop's myshopify address, which Shopify sends to `home`."""
    seen = []

    async def fetch(url, **_kwargs):
        seen.append(url)
        if url.endswith("/meta.json"):
            return _fetched(meta) if meta is not None else _fetched({}, status=404)
        return _fetched(product, final=f"{home}/products/peppermint-organic-lip-balms.js")

    fetch.seen = seen
    return fetch


# ── the registry ─────────────────────────────────────────────────────────────

def test_every_action_and_playbook_checks_out():
    assert actions.get("buy") is buy.ACTION and actions.get(None) is None
    assert playbooks.get("research").actions == ("buy",)
    bad = [
        replace(buy.ACTION, key="Buy"), replace(buy.ACTION, label=" "), replace(buy.ACTION, icon="rocket"),
        replace(buy.ACTION, item_kinds=()), replace(buy.ACTION, item_kinds=("boat",)),
        replace(buy.ACTION, per_day=0), replace(buy.ACTION, proposal_minutes=0),
        replace(buy.ACTION, params=(replace(buy.QUANTITY, type="file"),)),
    ]
    for action in bad:
        with pytest.raises(ValueError):
            actions.validate(action)
    research = playbooks.get("research")
    with pytest.raises(ValueError, match="unknown action"):
        replace(research, actions=("teleport",)).validate()
    with pytest.raises(ValueError, match="fits none"):
        replace(research, item_kinds=("place",), actions=("buy",)).validate()
    assert research.view()["actions"] == ["buy"]
    # A switch that starts on says so.
    assert buy.FILL_IN.view()["value"] == "yes" and "value" not in buy.QUANTITY.view()


# ── Buy ──────────────────────────────────────────────────────────────────────

def test_buy_reads_a_store_link():
    assert buy.product_handle(STORE) == "peppermint-organic-lip-balms"
    assert buy.product_handle("https://shop.test/collections/lips/products/balm.json") == "balm"
    assert buy.product_handle("https://shop.test/p/balm") is None
    assert buy.wanted_variant(STORE) == 36027946893476 and buy.wanted_variant("https://shop.test/x?variant=a") is None
    assert buy.pick_variant(PRODUCT, 36027946893476)["id"] == 36027946893476
    assert buy.pick_variant(PRODUCT, None)["id"] == 36027946893476  # the first in stock
    assert buy.pick_variant({"variants": [{"id": 1, "available": False}]}, None)["id"] == 1
    assert buy.pick_variant({"variants": ["x"]}, None) is None
    assert buy.split_name("Tess Alex Smith") == ("Tess Alex", "Smith")
    assert buy.split_name("Cher") == ("Cher", "") and buy.split_name("") == ("", "")
    assert buy.checkout_link("shop.test", 5, 2, address=None, email="") == "https://shop.test/cart/5:2"
    link = buy.checkout_link("shop.test", 5, 1, address=ADDRESS, email="tess@example.test")
    params = dict(parse_qsl(urlsplit(link).query))
    assert urlsplit(link).path == "/cart/5:1"
    assert params["checkout[email]"] == "tess@example.test"
    assert params["checkout[shipping_address][first_name]"] == "Tess"
    assert params["checkout[shipping_address][zip]"] == "94607"
    assert "checkout[shipping_address][address2]" not in params


def test_buy_is_for_products_at_a_store():
    assert buy.available(_ctx()) is None
    assert "Only products" in buy.available(_ctx(kind="listing"))
    google = "https://www.google.com/search?ibp=oshop&q=balm"
    assert "Google's page" in buy.available(_ctx(url=google))
    assert "unavailable" in buy.available(_ctx(status="unavailable"))
    assert buy.ACTION.view(_ctx(url=google))["available"] is False


@pytest.mark.asyncio
async def test_buy_at_a_shopify_store_opens_checkout_with_it_in_the_cart(monkeypatch):
    monkeypatch.setattr(buy, "_saved_address", AsyncMock(return_value=ADDRESS))
    fetch = _store()
    proposal = await buy.prepare(_ctx(), {"quantity": 2.0, "fill_in": True}, fetch=fetch)
    assert fetch.seen == ["https://www.drbronner.com/meta.json",
                          f"https://{SHOP}/products/peppermint-organic-lip-balms.js"]
    frozen = proposal.frozen
    assert frozen["kind"] == "checkout" and frozen["variant_id"] == 36027946893476 and frozen["quantity"] == 2
    assert frozen["url"].startswith("https://www.drbronner.com/cart/36027946893476:2?")
    assert frozen["plain_url"] == "https://www.drbronner.com/cart/36027946893476:2" and frozen["currency"] == "USD"
    shown = {line.label: line.value for line in proposal.lines}
    assert shown["Price now"] == "$3.99" and shown["Ship to"].startswith("Tess Alex, 1 Main St")
    assert shown["Item"] == "Dr Bronner's Organic Lip Balm (.15 oz)" and shown["Email"] == "tess@example.test"
    assert "your address and email filled in" in proposal.note and "doesn't pay" in proposal.note
    assert "when found" not in proposal.note
    # The store's price moved since it was found: said so.
    moved = {"variants": [{"id": 36027946893476, "price": 499, "available": True, "title": "Default Title"}]}
    proposal = await buy.prepare(_ctx(), {}, fetch=_store(product=moved))
    assert "It was $3.99 when found." in proposal.note
    assert {line.label: line.value for line in proposal.lines}["Item"] == "Dr Bronner's Organic Lip Balm"
    # Fill-in turned off: nothing of theirs goes in the link, and the address isn't read.
    reads = AsyncMock(return_value=ADDRESS)
    monkeypatch.setattr(buy, "_saved_address", reads)
    proposal = await buy.prepare(_ctx(), {"fill_in": False}, fetch=_store())
    assert "?" not in proposal.frozen["url"] and "Email" not in {line.label for line in proposal.lines}
    reads.assert_not_awaited()
    # No saved address, no email: nothing filled in.
    monkeypatch.setattr(buy, "_saved_address", AsyncMock(return_value=None))
    bare = replace(_ctx(), user=CurrentUser(id=USER, email="", role="individual"))
    proposal = await buy.prepare(bare, {}, fetch=_store())
    assert "?" not in proposal.frozen["url"] and proposal.note.startswith(
        "Opens checkout at drbronner.com with this in the cart. ")
    # Only email: said so.
    proposal = await buy.prepare(_ctx(), {}, fetch=_store())
    assert ", email filled in." in proposal.note
    out = await buy.perform(_ctx(), proposal.frozen)
    assert out["headline"] == "Checkout opened at drbronner.com" and out["url"] == proposal.frozen["url"]
    assert out["stored_url"] == "https://www.drbronner.com/cart/36027946893476:1"


@pytest.mark.asyncio
async def test_the_price_is_in_the_stores_own_currency(monkeypatch):
    monkeypatch.setattr(buy, "_saved_address", AsyncMock(return_value=None))
    moved = {"variants": [{"id": 36027946893476, "price": 2400, "available": True}]}
    # A UK shop: its own currency, and no comparison with a dollar price found on Google.
    proposal = await buy.prepare(_ctx(), {}, fetch=_store(meta={**META, "currency": "GBP"}, product=moved))
    assert {line.label: line.value for line in proposal.lines}["Price now"] == "24.00 GBP"
    assert "when found" not in proposal.note
    # No currency from the shop: the bare amount, never a guessed "$".
    proposal = await buy.prepare(_ctx(), {}, fetch=_store(meta={"myshopify_domain": SHOP}, product=moved))
    assert {line.label: line.value for line in proposal.lines}["Price now"] == "24.00"
    assert buy.money(None, "USD") == ""


@pytest.mark.asyncio
async def test_only_a_shop_shopify_vouches_for_gets_a_checkout(monkeypatch):
    """A site that looks like Shopify, or names someone else's shop, gets the
    product page: nothing of the person's goes to it."""
    monkeypatch.setattr(buy, "_saved_address", AsyncMock(return_value=ADDRESS))
    page = {"kind": "product_page", "url": STORE, "store": "drbronner.com", "title": "Dr Bronner's Organic Lip Balm"}
    for fetch in (
        _store(meta=None),                                              # no meta.json
        _store(meta={"myshopify_domain": "evil.example.com"}),          # not a myshopify shop
        _store(home="https://real-brand.test"),                          # Shopify sends the shop elsewhere
        _store(product={"variants": [{"id": "x"}]}),                    # not Shopify's product shape
        AsyncMock(return_value=_fetched(b"<html>", ctype="text/html")),
        AsyncMock(return_value=_fetched(META, truncated=True)),
        AsyncMock(side_effect=UnsafeURL("private")), AsyncMock(side_effect=RuntimeError("x")),
    ):
        proposal = await buy.prepare(_ctx(), {}, fetch=fetch)
        assert proposal.frozen == page and proposal.confirm == "Open drbronner.com"
    # A shop with no domain of its own is its myshopify address.
    shop_only = _ctx(url=f"https://{SHOP}/products/peppermint-organic-lip-balms")
    proposal = await buy.prepare(shop_only, {}, fetch=_store(home=f"https://{SHOP}"))
    assert proposal.frozen["kind"] == "checkout"
    no_products_path = _ctx(url="https://shop.test/p/balm")
    proposal = await buy.prepare(no_products_path, {}, fetch=AsyncMock())
    assert proposal.frozen["kind"] == "product_page"
    assert {line.label for line in proposal.lines} == {"Item", "Store", "Price when found"}
    out = await buy.perform(no_products_path, proposal.frozen)
    assert out["headline"] == "Opened the product at shop.test" and out["url"] == "https://shop.test/p/balm"
    assert "stored_url" not in out


@pytest.mark.asyncio
async def test_buy_refuses_what_cant_be_bought(monkeypatch):
    monkeypatch.setattr(buy, "_saved_address", AsyncMock(return_value=None))
    sold_out = {"variants": [{"id": 36027946893476, "price": 399, "available": False}]}
    with pytest.raises(ActionError, match="out of stock at drbronner.com"):
        await buy.prepare(_ctx(), {}, fetch=_store(product=sold_out))
    for bad in (0.0, 11.0, 2.5, True, "2"):
        with pytest.raises(ActionError) as exc:
            await buy.prepare(_ctx(), {"quantity": bad}, fetch=AsyncMock())
        assert exc.value.code == 422 and str(exc.value) == "Quantity must be 1 to 10."
    assert buy.quantity_of({}) == 1 and buy.quantity_of({"quantity": 3.0}) == 3
    with pytest.raises(ActionError):
        await buy.prepare(_ctx(url="https://www.google.com/shopping/product/1"), {}, fetch=AsyncMock())


@pytest.mark.asyncio
async def test_a_saved_address_is_the_default_one(monkeypatch):
    c = FakeConn().on("FROM mw_shipping_addresses", [
        {"id": uuid4(), **ADDRESS, "is_default": True, "created_at": NOW}])
    monkeypatch.setattr(buy, "connection_or_direct", connection(c))
    assert (await buy._saved_address(USER))["postal_code"] == "94607"
    c.on("FROM mw_shipping_addresses", [])
    assert await buy._saved_address(USER) is None


# ── propose -> confirm -> carry out ──────────────────────────────────────────

ACTION_ID = uuid4()


def action_row(**over):
    return {"id": ACTION_ID, "task_id": TASK, "item_id": ITEM, "user_id": USER, "action": "buy",
            "status": "proposed", "params": "{}", "frozen": json.dumps({"kind": "checkout", "url": "https://s.test/cart/1:1",
                                                                          "store": "s.test", "title": "Balm", "quantity": 1}),
            "preview": json.dumps({"title": "Buy Balm", "lines": [], "note": ""}), "result": None, "error": None,
            "created_at": NOW, "expires_at": NOW + timedelta(minutes=30), "decided_at": None, "finished_at": None,
            **over}


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    monkeypatch.setattr(service, "connection_or_direct", connection(c))
    c.on("FROM mw_agent_tasks", task_row())
    c.on("SELECT * FROM mw_agent_task_items", _product_row())
    return c


@pytest.mark.asyncio
async def test_propose_freezes_what_would_happen(conn, monkeypatch):
    prepared = Proposal(frozen={"kind": "checkout", "url": "https://s.test/cart/1:1"}, title="Buy Balm",
                        lines=(Line("Store", "s.test"),), note="You pay there.")
    monkeypatch.setitem(actions.ACTIONS, "buy", replace(buy.ACTION, prepare=AsyncMock(return_value=prepared)))
    conn.on("INSERT INTO mw_agent_task_actions", lambda *args: action_row(preview=args[6], frozen=args[5]))
    view = await service.propose(PERSON, TASK, ITEM, "buy", {"quantity": "2"})
    assert view["status"] == "proposed" and view["preview"]["lines"] == [{"label": "Store", "value": "s.test"}]
    assert view["confirm_label"] == "Go to checkout" and view["label"] == "Buy"
    assert conn.ran("SET status = 'expired'")  # an earlier proposal for it is gone
    insert = conn.ran("INSERT INTO mw_agent_task_actions")[0][2]
    assert json.loads(insert[4]) == {"quantity": 2} and insert[7] == timedelta(minutes=30)
    # A proposal can say what its button reads.
    prepared = replace(prepared, confirm="Open s.test")
    monkeypatch.setitem(actions.ACTIONS, "buy", replace(buy.ACTION, prepare=AsyncMock(return_value=prepared)))
    assert (await service.propose(PERSON, TASK, ITEM, "buy", {}))["confirm_label"] == "Open s.test"


@pytest.mark.asyncio
async def test_propose_refuses(conn, monkeypatch):
    async def code(call):
        with pytest.raises(AgentTaskError) as exc:
            await call
        return exc.value.code

    assert await code(service.propose(PERSON, TASK, ITEM, "teleport", {})) == 404
    assert await code(service.propose(PERSON, TASK, ITEM, "buy", {"quantity": "lots"})) == 422
    conn.on("decided_at > NOW() - INTERVAL '1 day'", 30)  # the day's limit
    with pytest.raises(AgentTaskError, match="the most for a day"):
        await service.propose(PERSON, TASK, ITEM, "buy", {})
    conn.on("decided_at > NOW() - INTERVAL '1 day'", 0)
    gone = replace(buy.ACTION, prepare=AsyncMock(side_effect=ActionError("Out of stock.")))
    monkeypatch.setitem(actions.ACTIONS, "buy", gone)
    assert await code(service.propose(PERSON, TASK, ITEM, "buy", {})) == 409
    conn.on("SELECT * FROM mw_agent_task_items", _product_row(url="https://www.google.com/shopping/product/1"))
    assert await code(service.propose(PERSON, TASK, ITEM, "buy", {})) == 409
    conn.on("SELECT * FROM mw_agent_task_items", None)
    assert await code(service.propose(PERSON, TASK, ITEM, "buy", {})) == 404
    # A job search's jobs take no actions here; nor does a finding of another kind.
    assert service.for_item(task_row(engine="job_search"), _product_row()) == []
    assert service.for_item(task_row(), item_row()) == []
    assert service.for_item(task_row(playbook="gone"), _product_row()) == []


@pytest.mark.asyncio
async def test_confirm_carries_it_out_once(conn, monkeypatch):
    perform = AsyncMock(return_value={"headline": "Checkout opened at s.test", "lines": [], "url": "https://s.test/cart/1:1"})
    monkeypatch.setitem(actions.ACTIONS, "buy", replace(buy.ACTION, perform=perform))
    conn.on("SET status = 'running'", action_row(status="running"))
    conn.on("SET status = $2, result", lambda *args: action_row(status=args[1], result=args[2], error=args[3]))
    done = await service.confirm(PERSON, ACTION_ID)
    assert done["status"] == "done" and done["result"]["url"] == "https://s.test/cart/1:1"
    assert perform.await_args.args[1]["url"] == "https://s.test/cart/1:1"  # the frozen proposal, nothing else
    # A retry gets what came of it, and nothing runs again.
    conn.on("SET status = 'running'", None)
    conn.on("SELECT * FROM mw_agent_task_actions WHERE id", action_row(status="done", result='{"url": "u"}'))
    perform.reset_mock()
    assert (await service.confirm(PERSON, ACTION_ID))["result"] == {"url": "u"}
    perform.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_link_kept_carries_none_of_the_persons_details(conn, monkeypatch):
    full = "https://s.test/cart/1:1?checkout%5Bemail%5D=tess%40example.test"
    perform = AsyncMock(return_value={"headline": "Checkout opened at s.test", "lines": [], "url": full,
                                      "stored_url": "https://s.test/cart/1:1"})
    monkeypatch.setitem(actions.ACTIONS, "buy", replace(buy.ACTION, perform=perform))
    conn.on("SET status = 'running'", action_row(status="running"))
    conn.on("SET status = $2, result", lambda *args: action_row(status=args[1], result=args[2], error=args[3]))
    done = await service.confirm(PERSON, ACTION_ID)
    assert done["result"]["url"] == full  # this once, to open
    stored = json.loads(conn.ran("SET status = $2, result")[0][2][2])
    assert stored["url"] == "https://s.test/cart/1:1" and "stored_url" not in stored


@pytest.mark.asyncio
async def test_proposing_is_bounded_and_serialized(conn, monkeypatch):
    prepared = Proposal(frozen={"kind": "checkout", "url": "https://s.test/cart/1:1"}, title="Buy Balm")
    monkeypatch.setitem(actions.ACTIONS, "buy", replace(buy.ACTION, prepare=AsyncMock(return_value=prepared)))
    conn.on("INSERT INTO mw_agent_task_actions", lambda *args: action_row())
    await service.propose(PERSON, TASK, ITEM, "buy", {})
    # One live proposal per finding and action, even when two arrive at once.
    [lock] = conn.ran("pg_advisory_xact_lock")
    assert lock[2] == (f"task_action:{ITEM}:buy",)
    # An action whose process died is settled, not left running for good.
    [stale] = conn.ran("status = 'running' AND decided_at < NOW()")
    assert stale[2] == (USER, service.UNFINISHED) and "INTERVAL '10 minutes'" in stale[1]
    # The day's limit counts what the person said yes to.
    assert conn.ran("AND decided_at > NOW() - INTERVAL '1 day'")
    # Many proposals in a minute: refused before anything is fetched.
    conn.on("created_at > NOW() - INTERVAL '1 minute'", service.PROPOSALS_PER_MINUTE)
    with pytest.raises(AgentTaskError) as exc:
        await service.propose(PERSON, TASK, ITEM, "buy", {})
    assert exc.value.code == 429 and "in a minute" in str(exc.value)
    # History settles them too.
    conn.calls.clear()
    await service.history(conn, ITEM, USER)
    assert conn.ran("status = 'running' AND decided_at < NOW()")


@pytest.mark.asyncio
async def test_confirm_when_it_cant(conn, monkeypatch):
    conn.on("SET status = 'running'", None)
    conn.on("SELECT * FROM mw_agent_task_actions WHERE id", action_row())  # proposed, but no longer fresh
    with pytest.raises(AgentTaskError) as exc:
        await service.confirm(PERSON, ACTION_ID)
    assert exc.value.code == 409 and conn.ran("SET status = 'expired' WHERE id")
    conn.on("SELECT * FROM mw_agent_task_actions WHERE id", action_row(status="cancelled"))
    with pytest.raises(AgentTaskError):
        await service.confirm(PERSON, ACTION_ID)
    conn.on("SELECT * FROM mw_agent_task_actions WHERE id", None)
    with pytest.raises(AgentTaskError) as exc:
        await service.confirm(PERSON, ACTION_ID)
    assert exc.value.code == 404

    # Claimed, but the task was deleted meanwhile: cancelled, not carried out.
    conn.on("SET status = 'running'", action_row(status="running"))
    conn.on("FROM mw_agent_tasks", None)
    with pytest.raises(AgentTaskError):
        await service.confirm(PERSON, ACTION_ID)
    assert conn.ran("SET status = 'cancelled', finished_at")
    conn.on("FROM mw_agent_tasks", task_row())

    # It fails: the reason when it gave one, a plain one when it didn't.
    conn.on("SET status = $2, result", lambda *args: action_row(status=args[1], result=args[2], error=args[3]))
    for raised, said in ((ActionError("The store said no."), "The store said no."),
                         (RuntimeError("boom"), service.FAILED)):
        monkeypatch.setitem(actions.ACTIONS, "buy", replace(buy.ACTION, perform=AsyncMock(side_effect=raised)))
        failed = await service.confirm(PERSON, ACTION_ID)
        assert failed["status"] == "failed" and failed["error"] == said and failed["result"] is None
    monkeypatch.delitem(actions.ACTIONS, "buy")
    assert (await service.confirm(PERSON, ACTION_ID))["status"] == "failed"


@pytest.mark.asyncio
async def test_cancel_views_and_history(conn):
    conn.on("SET status = 'cancelled', decided_at", action_row(status="cancelled"))
    assert (await service.cancel(PERSON, ACTION_ID))["status"] == "cancelled"
    conn.on("SET status = 'cancelled', decided_at", None)
    conn.on("SELECT * FROM mw_agent_task_actions WHERE id", action_row(status="done"))
    assert (await service.cancel(PERSON, ACTION_ID))["status"] == "done"
    conn.on("SELECT * FROM mw_agent_task_actions WHERE id", None)
    with pytest.raises(AgentTaskError):
        await service.cancel(PERSON, ACTION_ID)
    conn.on("FROM mw_agent_task_actions\n", [action_row(status="done")])
    conn.on("WHERE item_id = $1 AND user_id = $2 AND status NOT IN", [action_row(status="done")])
    assert [h["status"] for h in await service.history(conn, ITEM, USER)] == ["done"]
    [view] = service.views(PERSON, task_row(), _product_row())
    assert view["key"] == "buy" and view["available"] is True and view["params"][0]["key"] == "quantity"
    unknown = service.action_view(action_row(action="gone"))
    assert unknown["label"] == "gone" and unknown["confirm_label"] == "Go ahead"


@pytest.mark.asyncio
async def test_adding_an_action_needs_nothing_else(conn, monkeypatch):
    """A new action is a module with an `ACTION` and a key in a playbook: the
    finding offers it, and propose and confirm carry it out, with no change to
    the service, the routes or the app."""
    from app.matcha.services.matcha_work.agent_tasks.actions.base import ItemAction, outcome

    async def prepare(ctx, params):
        return Proposal(frozen={"to": ctx.item["title"]}, title="Write to the store")

    async def perform(ctx, frozen):
        return outcome(f"Wrote about {frozen['to']}")

    ask = ItemAction(key="ask_store", label="Ask the store", icon="envelope", description="Writes to the store.",
                     item_kinds=("product",), available=lambda ctx: None, prepare=prepare, perform=perform)
    actions.validate(ask)
    monkeypatch.setitem(actions.ACTIONS, "ask_store", ask)
    research = playbooks.get("research")
    monkeypatch.setitem(playbooks.PLAYBOOKS, "research", replace(research, actions=("buy", "ask_store")))
    playbooks.get("research").validate()
    assert [v["key"] for v in service.views(PERSON, task_row(), _product_row())] == ["buy", "ask_store"]
    conn.on("INSERT INTO mw_agent_task_actions", lambda *args: action_row(action="ask_store", frozen=args[5],
                                                                         preview=args[6]))
    assert (await service.propose(PERSON, TASK, ITEM, "ask_store", {}))["label"] == "Ask the store"
    conn.on("SET status = 'running'", action_row(action="ask_store", status="running",
                                                 frozen='{"to": "Balm"}'))
    conn.on("SET status = $2, result", lambda *args: action_row(action="ask_store", status=args[1], result=args[2]))
    assert (await service.confirm(PERSON, ACTION_ID))["result"]["headline"] == "Wrote about Balm"
