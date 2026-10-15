"""The research phases that use no model."""
import json
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services.safe_fetch import FetchedResponse, UnsafeURL
from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import Budget, Guard
from app.matcha.services.matcha_work.agent_tasks import items as items_mod, orchestrator
from app.matcha.services.matcha_work.agent_tasks.research import phases, providers
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import ITEM, PLAN, TASK, TODAY, TOKEN, item_row, task_row


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    for module in (phases, chain):
        monkeypatch.setattr(module, "connection_or_direct", connection(c))
    # Every grant is given in full; refunds are recorded.
    c.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", lambda row_id, want, limit: want)
    return c


def _guard():
    return Guard(orchestrator.TASK_CHAIN, TASK, TOKEN)


def _html(ld=None, body="<p>Sunny 1 bed / 1 ba. $3,200/mo. Dogs welcome!</p>"):
    script = f'<script type="application/ld+json">{json.dumps(ld)}</script>' if ld else ""
    return f"<html><head><title>x</title><meta property='og:image' content='https://img.test/og.jpg'>{script}</head><body>{body}</body></html>".encode()


def _fetched(body=b"", status=200, ctype="text/html", final="https://apts.test/1"):
    return FetchedResponse(url=final, final_url=final, status=status, content_type=ctype, body=body, truncated=False)


def _deps(**over):
    return replace(phases.Deps(), **{"today": lambda: TODAY, "browser_ready": lambda: False, **over})


def test_helpers():
    assert phases.own_page("https://apts.test/1") and not phases.own_page("https://www.google.com/maps/x")
    assert not phases.own_page("https://shopping.google.co.uk/p") and not phases.own_page(None)
    page = {"og_image": "https://img.test/og.jpg", "products": [{"images": ["https://img.test/p.jpg", 7]}]}
    assert [i["source_url"] for i in phases.page_images(page, "t", "u")] == ["https://img.test/p.jpg", "https://img.test/og.jpg"]
    assert phases.provider_record(providers.ProviderItem(kind="product", title="Balm", url="https://s.test", image_url="https://i.test/a"))["image_candidates"][0]["page_url"] == "https://s.test"
    assert phases.cursor_of({"phase_cursor": "[1]"}) == {} and phases.plan_of({}) == {}


@pytest.mark.asyncio
async def test_item_room_grows_after_search_more():
    c = FakeConn().on("COUNT(*) FROM mw_agent_task_items", 70)
    assert await phases.item_room(c, TASK) == 10
    c.on("kind = 'more'", True)
    assert await phases.item_room(c, TASK) == 50


@pytest.mark.asyncio
async def test_providers_add_findings_then_hand_to_the_web(conn, monkeypatch):
    provider = AsyncMock()
    provider.search = AsyncMock(side_effect=[
        [providers.ProviderItem(kind="product", title="Balm", url="https://shop.test/b", provider="google_shopping")],
        providers.ProviderError("rate limited"),
    ])
    insert = AsyncMock(return_value=1)
    monkeypatch.setattr(items_mod, "insert_items", insert)
    conn.on("COUNT(*) FROM mw_agent_task_items", 0)
    task = task_row(plan=json.dumps({**PLAN, "source": "shopping", "queries": ["balm", "lip balm"]}),
                    phase_cursor=json.dumps({"provider_page": 2}))
    out = await phases.run_providers(task, _deps(provider=lambda: provider), _guard())
    assert out.phase == phases.DISCOVER and out.cursor["provider_added"] == 1 and "Google Shopping" in out.progress["note"]
    assert provider.search.await_args_list[0].kwargs == {"page": 2}
    assert insert.await_args.args[4][0]["origin"] == "provider"
    # The web: no provider to ask.
    out = await phases.run_providers(task_row(), _deps(provider=lambda: provider), _guard())
    assert out.phase == phases.DISCOVER and out.progress["note"] == "Searching the web…"


GOOGLE = "https://www.google.com/search?ibp=oshop&q={q}&prds=productid:{n}"


def _shop(title, seller, *, n=1, q="balm", token="tok"):
    return providers.ProviderItem(kind="product", title=title, subtitle=seller, url=GOOGLE.format(q=q, n=n),
                                  provider="google_shopping", offers_token=token)


def test_the_best_of_each_query_first_and_which_to_look_up():
    assert phases.interleave([[1, 2, 3], [], [4]]) == [1, 4, 2, 3] and phases.interleave([]) == []
    found = [
        _shop("Balm", "Acme"),
        _shop("Balm", "Acme", q="lip balm"),           # the same listing from another query
        _shop("Old", "Shop"),                           # the task has it
        _shop("No token", "Shop", token=None),
        providers.ProviderItem(kind="product", title="Own page", subtitle="Shop", url="https://shop.test/x",
                               offers_token="tok"),
        _shop("", "Shop"),
        _shop("Wax", "Bee Co"),
        _shop("Tin", "Bee Co"),
    ]
    assert phases.store_lookups(found, {("old", "shop")}, limit=5) == [0, 6, 7]
    assert phases.store_lookups(found, set(), limit=2) == [0, 2]


@pytest.mark.asyncio
async def test_shopping_findings_are_kept_at_their_stores_page(conn, monkeypatch):
    provider = AsyncMock()
    provider.search = AsyncMock(side_effect=[
        [_shop("Balm", "Acme", n=1), _shop("Wax", "Bee Co", n=2)],
        [_shop("Balm", "Acme", n=1, q="lip balm"), _shop("Tin", "Tin Co", n=3, q="lip balm")],
    ])

    async def stores(token):
        if token == "fail":
            raise providers.ProviderError("SerpApi answered 500")
        return [providers.Store(name="Acme", link="https://acme.test/balm", price=4.0)]

    provider.stores = AsyncMock(side_effect=stores)
    insert = AsyncMock(return_value=3)
    monkeypatch.setattr(items_mod, "insert_items", insert)
    conn.on("COUNT(*) FROM mw_agent_task_items", 0)
    conn.on("SELECT title, subtitle FROM mw_agent_task_items", [{"title": "Tin", "subtitle": "Tin Co"}])
    task = task_row(plan=json.dumps({**PLAN, "source": "shopping", "queries": ["balm", "lip balm"]}))
    out = await phases.run_providers(task, _deps(provider=lambda: provider), _guard())
    assert out.cursor["provider_added"] == 3
    records = insert.await_args.args[4]
    # Each query's best first; the repeat and the one the task has aren't looked up.
    assert [r["title"] for r in records] == ["Balm", "Balm", "Wax", "Tin"]
    assert provider.stores.await_count == 2
    assert records[0]["url"] == "https://acme.test/balm" and records[0]["subtitle"] == "Acme"
    # Wax's seller isn't among the stores: the first store's page, name and price.
    assert records[2]["url"] == "https://acme.test/balm" and records[2]["fields"]["price"]["value"] == 4.0
    assert records[3]["url"].startswith("https://www.google.com/")

    # A failed lookup keeps Google's link; with no budget left nothing is asked.
    provider.search = AsyncMock(return_value=[_shop("Balm", "Acme", token="fail")])
    provider.stores.reset_mock()
    await phases.run_providers(task, _deps(provider=lambda: provider), _guard())
    assert insert.await_args.args[4][0]["url"].startswith("https://www.google.com/")
    conn.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", lambda row_id, want, limit: 0)
    provider.search = AsyncMock(return_value=[_shop("Balm", "Acme")])
    provider.stores.reset_mock()
    assert (await phases.with_stores(task, provider, [_shop("Balm", "Acme")], set(), TODAY))[0].url.startswith(
        "https://www.google.com/")
    provider.stores.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_lookups_are_only_paid_for_findings_there_is_room_for(conn, monkeypatch):
    provider = AsyncMock()
    provider.stores = AsyncMock(return_value=[providers.Store(name="Acme", link="https://acme.test/balm")])
    monkeypatch.setattr(items_mod, "insert_items", AsyncMock(return_value=0))
    task = task_row(plan=json.dumps({**PLAN, "source": "shopping", "queries": ["balm"]}))
    three = [_shop("Balm", "Acme"), _shop("Wax", "Bee Co", n=2), _shop("Tin", "Tin Co", n=3)]
    # Room for one more finding: one lookup.
    provider.search = AsyncMock(return_value=three)
    conn.on("COUNT(*) FROM mw_agent_task_items", phases.BUDGETS.items - 1)
    await phases.run_providers(task, _deps(provider=lambda: provider), _guard())
    assert provider.stores.await_count == 1
    # Full: nothing is looked up, and nothing is asked about what it has.
    provider.stores.reset_mock()
    conn.calls.clear()
    conn.on("COUNT(*) FROM mw_agent_task_items", phases.BUDGETS.items)
    await phases.run_providers(task, _deps(provider=lambda: provider), _guard())
    provider.stores.assert_not_awaited()
    assert not conn.ran("SELECT title, subtitle FROM mw_agent_task_items")


@pytest.mark.asyncio
async def test_enrich_one_reads_the_items_own_page(monkeypatch):
    row = dict(item_row(fields=json.dumps({}), kind="listing", image_candidates="[]"))
    fetch = AsyncMock(return_value=_fetched(_html()))
    update = await phases.enrich_one(row, _deps(page_fetch=fetch), Budget(left=1), Budget(left=0), prefix="p")
    assert update["status"] == "verified" and update["fields"]["price"]["value"] == 3200
    assert update["fields"]["pets"]["value"] == ["dogs"] and update["image_candidates"][0]["source_url"] == "https://img.test/og.jpg"
    # Out of page loads: not tried, so it stays unread for a later batch.
    assert await phases.enrich_one(row, _deps(page_fetch=fetch), Budget(left=0), Budget(left=0), prefix="p") is phases.NOT_TRIED
    # No page of its own: nothing to read.
    maps = {**row, "url": "https://www.google.com/maps/search/x"}
    assert (await phases.enrich_one(maps, _deps(), Budget(left=1), Budget(left=0), prefix="p"))["status"] == "verified"
    gone = AsyncMock(return_value=_fetched(status=410))
    assert (await phases.enrich_one(row, _deps(page_fetch=gone), Budget(left=1), Budget(left=0), prefix="p"))["status"] == "unavailable"
    removed = AsyncMock(return_value=_fetched(_html(body="<p>This listing has been removed.</p>")))
    assert (await phases.enrich_one(row, _deps(page_fetch=removed), Budget(left=1), Budget(left=0), prefix="p"))["status"] == "unavailable"
    for broken in (AsyncMock(side_effect=UnsafeURL("private")), AsyncMock(side_effect=RuntimeError("x")),
                   AsyncMock(return_value=_fetched(status=500)), AsyncMock(return_value=_fetched(ctype="application/pdf"))):
        out = await phases.enrich_one(row, _deps(page_fetch=broken), Budget(left=1), Budget(left=0), prefix="p")
        assert out["status"] == "verified" and out["fields"] == {}
    monkeypatch.setattr(phases, "extract_page", lambda *_: (_ for _ in ()).throw(RecursionError()))
    out = await phases.enrich_one(row, _deps(page_fetch=fetch), Budget(left=1), Budget(left=0), prefix="p")
    assert out["fields"] == {}


@pytest.mark.asyncio
async def test_a_page_drawn_by_javascript_is_viewed_in_the_browser():
    row = dict(item_row(fields="{}", kind="listing"))
    thin = AsyncMock(return_value=_fetched(_html(body="<div id=app></div>")))
    view = AsyncMock(return_value={"url": "https://apts.test/1", "text": "Studio. $2,950/mo. Cats OK."})
    out = await phases.enrich_one(row, _deps(page_fetch=thin, view=view, browser_ready=lambda: True),
                                  Budget(left=1), Budget(left=1), prefix="p")
    assert out["fields"]["price"]["value"] == 2950 and out["fields"]["price"]["evidence"]["origin"] == "browser"
    view.assert_awaited_once_with("https://apts.test/1", "p/views")
    failed = AsyncMock(return_value={"error": "busy"})
    out = await phases.enrich_one(row, _deps(page_fetch=thin, view=failed, browser_ready=lambda: True),
                                  Budget(left=1), Budget(left=1), prefix="p")
    assert out["fields"] == {}


@pytest.mark.asyncio
async def test_enrich_batches_saves_and_moves_on(conn, monkeypatch):
    rows = [item_row(id=ITEM, kind="listing", fields="{}", images="[]"),
            item_row(id=uuid4(), url="https://www.google.com/maps/x", fields="{}", images="[]"),
            item_row(id=uuid4(), url="https://apts.test/9", fields="{}", images="[]")]
    conn.on("WHERE task_id = $1 AND enriched_at IS NULL AND status IN", rows)
    conn.on("COALESCE(SUM(jsonb_array_length(images)), 0)", 0)
    fetch = AsyncMock(side_effect=[_fetched(_html()), RuntimeError("boom")])
    rehost = AsyncMock(return_value=([{"url": "https://cdn.test/a.webp", "page_url": "p", "alt": ""}], []))
    monkeypatch.setattr(phases, "enrich_one", AsyncMock(side_effect=[
        await phases.enrich_one(dict(rows[0]), _deps(page_fetch=fetch), Budget(left=1), Budget(left=0), prefix="p"),
        {"fields": {}, "status": "verified", "image_candidates": []},
        RuntimeError("boom"),
    ]))
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND enriched_at IS NULL", 0)
    out = await phases.enrich(task_row(), _deps(rehost=rehost), _guard())
    assert out.phase == phases.SCREEN
    saves = conn.ran("enriched_at = NOW(), updated_at = NOW()")
    assert len(saves) == 3
    first = saves[0][2]
    assert json.loads(first[3])["price"]["value"] == 3200 and json.loads(first[6])[0]["url"] == "https://cdn.test/a.webp"
    assert saves[2][2][3:] == (None, None, None, None)  # failed: marked read, nothing changed
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND enriched_at IS NULL", 5)
    monkeypatch.setattr(phases, "enrich_one", AsyncMock(return_value=phases.NOT_TRIED))
    out = await phases.enrich(task_row(), _deps(rehost=rehost), _guard())
    assert out.phase == phases.ENRICH and not conn.ran("enriched_at = NOW(), updated_at = NOW()")[3:]


@pytest.mark.asyncio
async def test_rerank_and_rank_phase(conn):
    conn.on("SELECT id, fields, status, fit_score, user_state", [
        item_row(id=ITEM), item_row(id=uuid4(), fields=json.dumps({"pets": {"value": ["none"], "status": "verified"}}))])
    assert await phases.rerank(conn, task_row()) == 2
    [update] = conn.ran("SET rank = v.rank")
    assert update[2][3] == [1, 9] or update[2][3] == [9, 1]
    assert await phases.rerank(FakeConn(), task_row()) == 0
    conn.on("WHERE id = $1 AND dispatch_token = $2", 1)
    conn.on("SELECT * FROM mw_agent_tasks WHERE id = $1", task_row())
    assert (await phases.rank_phase(task_row(), _deps(), _guard())).phase == phases.SUMMARIZE
    conn.on("WHERE id = $1 AND dispatch_token = $2", None)
    assert (await phases.rank_phase(task_row(), _deps(), _guard())).phase is None
