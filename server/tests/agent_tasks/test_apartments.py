"""Apartments: a rent range, move-in specials, distance from a named place, and Apply."""
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.core.models.auth import CurrentUser
from app.core.services.safe_fetch import FetchedResponse, UnsafeURL
from app.matcha.services.matcha_work.agent_card.page_extract import extract_page
from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import Budget, Guard
from app.matcha.services.matcha_work.agent_tasks import actions, items as items_mod, orchestrator, playbooks
from app.matcha.services.matcha_work.agent_tasks.actions import apply
from app.matcha.services.matcha_work.agent_tasks.actions.base import ActionContext, ActionError
from app.matcha.services.matcha_work.agent_tasks.research import (
    contracts, fields as F, geo, kinds, phases, prompts, providers, ranking,
)
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import TASK, TODAY, TOKEN, USER, item_row, task_row

LAKE = (30.2626, -97.7470)  # Lady Bird Lake
ROUND_ROCK = (30.5083, -97.6789)  # ~17 mi north
MANOR = (30.3408, -97.5569)  # ~12 mi east
KYLE = (29.9891, -97.8772)  # ~20 mi south
ANCHOR = {"name": "Lady Bird Lake", "lat": LAKE[0], "lng": LAKE[1], "source": "google_maps", "label": "Lady Bird Lake"}
BRIEF = {"location": "Austin, TX", "budget_min": 1600, "budget_max": 2000, "near": "Lady Bird Lake",
         "min_miles": 10, "directions": ["north", "south"]}
PERSON = CurrentUser(id=USER, email="tess@example.test", role="individual")


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    for module in (phases, chain):
        monkeypatch.setattr(module, "connection_or_direct", connection(c))
    c.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", lambda row_id, want, limit: want)
    return c


def _guard():
    return Guard(orchestrator.TASK_CHAIN, TASK, TOKEN)


def _deps(**over):
    return replace(phases.Deps(), **{"today": lambda: TODAY, "browser_ready": lambda: False, **over})


def _fetched(body=b"", status=200, ctype="text/html", final="https://thedomain.test/"):
    return FetchedResponse(url=final, final_url=final, status=status, content_type=ctype, body=body, truncated=False)


# ── the brief and the plan ───────────────────────────────────────────────────

def test_the_brief_takes_a_rent_range_and_a_distance():
    check = playbooks.get("apartments").validate_brief
    kept = check(BRIEF)
    assert (kept["budget_min"], kept["budget_max"], kept["near"], kept["min_miles"], kept["directions"]) == (
        1600.0, 2000.0, "Lady Bird Lake", 10.0, ["north", "south"])
    assert check({**BRIEF, "directions": ["north", "east", "south", "west"]})["directions"] == []  # no limit
    for bad in ({"budget_min": 2500, "budget_max": 2000}, {"min_miles": 10}, {"directions": ["north"]},
                {**BRIEF, "min_miles": 20, "max_miles": 5}, {**BRIEF, "directions": ["up"]}):
        with pytest.raises(ValueError):
            check(bad)
    assert len(playbooks.get("apartments").intake) <= 14


def test_the_plan_measures_from_the_named_place():
    plan = contracts.plan_from_brief("apartments with specials", BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    typed = {(c["field"], c["op"]): c for c in plan["constraints"]}
    assert typed[("price", "between")]["value"] == [1600, 2000] and typed[("price", "between")]["unit"] == "month"
    assert ("price", "lte") not in typed and ("price", "gte") not in typed
    only_low = contracts.brief_constraints({"budget_min": 1600}, item_kind="listing", today=TODAY)
    assert [(c["op"], c["value"]) for c in only_low] == [("gte", 1600.0)]
    assert typed[("distance", "gte")]["value"] == 10 and typed[("direction", "any_of")]["value"] == ["north", "south"]
    assert plan["fields"][:4] == ["price", "specials", "distance", "beds"] and "direction" in plan["fields"]
    assert plan["source"] == "places"
    # A model's distance limit means nothing without a place: it is dropped, and so are the columns.
    model = {**plan, "constraints": [{"field": "distance", "op": "lte", "value": 5}],
             "preferences": [{"field": "distance", "weight": 0.5}], "fields": ["distance"]}
    bare = contracts.finalize_plan(model, {"location": "Austin"}, today=TODAY, kind=kinds.APARTMENTS)
    assert not any(c["field"] in F.COMPUTED for c in bare["constraints"])
    assert not bare["preferences"] and not set(bare["fields"]) & F.COMPUTED
    assert kinds.apartment_limits({"min_miles": 3}) == []  # no place, no distance
    assert {"field": "distance", "op": "lte", "value": 8} in kinds.apartment_limits({"near": "x", "max_miles": 8})


def test_a_refine_may_change_the_rent_floor_and_the_miles():
    plan = contracts.plan_from_brief("apartments", BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    args = {"result": {"constraints": [{"field": "price", "op": "between", "value": ["1500", 2200], "unit": "month"},
                                       {"field": "distance", "op": "gte", "value": 15}],
                       "preferences": [], "fields_add": [], "queries": [], "search_again": False, "note": "x"}}
    out, _ = contracts.normalize_refine(args, plan=plan, brief=BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    typed = {(c["field"], c["op"]): c["value"] for c in out["plan"]["constraints"]}
    assert typed[("price", "between")] == [1500, 2200] and typed[("distance", "gte")] == 15
    assert typed[("direction", "any_of")] == ["north", "south"]  # left out by the model, so it stays


def test_a_model_never_states_a_distance():
    assert "distance" not in contracts.DISCOVER_SCHEMA["properties"]["candidates"]["items"]["properties"]["facts"]["items"]["properties"]["field"]["enum"]
    made, why = contracts._fact({"field": "distance", "value": 3, "quote": "only 3 miles from downtown",
                                 "source_url": "https://a.test/1"},
                                item_key="a.test/1", page_text={"a.test/1": "only 3 miles from downtown"},
                                allowed={"a.test/1": "https://a.test/1"}, today=TODAY)
    assert made is None and "unknown field" in why


def test_prompts_name_the_place_and_ask_for_addresses():
    plan = {**contracts.plan_from_brief("apts", BRIEF, today=TODAY, kind=kinds.APARTMENTS), "anchor": ANCHOR}
    assert "Distances are measured from Lady Bird Lake" in prompts.plan_lines(plan)
    lost = {**plan, "anchor": {"name": "Atlantis", "error": "Couldn't find Atlantis on a map."}}
    assert "Distances: unknown. Couldn't find Atlantis on a map." in prompts.plan_lines(lost)
    text = prompts.discover_instructions(plan, browser=False)
    assert "Specials" in text and "street address" in text and "Distance," not in text
    assert "Budget (min): 1600" in prompts.plan_turn("apts", {"budget_min": 1600.0}, None)


# ── facts ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,want", [
    ("Specials: receive up to 8 weeks free on select homes!", "Up to 8 weeks free"),
    ("Get $1,000 off your first month rent when you lease by Friday", "$1,000 off your first month rent"),
    ("Enjoy one month free. Also no application fee.", "One month free"),
    ("Look & Lease: waived application fee today", "Look & Lease"),
    ("$0 deposit for qualified applicants", "$0 deposit"),
    ("We charge a $50 application fee.", None),
])
def test_move_in_specials_are_read_from_the_page(text, want):
    found = F.scan_listing_text(text, url="https://a.test/1", today=TODAY).get("specials")
    assert (found or {}).get("value") == want
    if found:
        assert found["status"] == "verified" and F.verify_quote(found["evidence"]["quote"], text)


def test_any_of_is_one_of_them():
    rule = {"field": "direction", "op": "any_of", "value": ["north", "south"]}
    north = {"value": ["north"], "status": "verified"}
    assert ranking.check(rule, north) == "ok"
    assert ranking.check(rule, {"value": ["east"], "status": "verified"}) == "violates"
    assert ranking.check(rule, {"value": [], "status": "verified"}) == "unknown"
    assert ranking.check(rule, {**north, "status": "claimed"}) == "unknown"
    assert ranking.describe(rule) == "Direction is North or South"
    assert ranking.describe({"field": "distance", "op": "gte", "value": 10}) == "Distance at least 10 mi"
    assert contracts.clean_constraint(rule, today=TODAY) == rule


# ── where things are ─────────────────────────────────────────────────────────

def test_distance_and_direction_are_arithmetic():
    assert 16 < geo.miles(LAKE, ROUND_ROCK) < 18 and geo.quarter(geo.bearing(LAKE, ROUND_ROCK)) == "north"
    assert geo.quarter(geo.bearing(LAKE, MANOR)) == "east" and geo.quarter(geo.bearing(LAKE, KYLE)) == "south"
    assert geo.quarter(300) == "west" and geo.quarter(315) == "north" and geo.quarter(44.9) == "north"
    made = geo.distance_fields(ROUND_ROCK, ANCHOR, status="verified", origin="provider", url="https://r.test",
                               how="where Google Maps puts it")
    assert made["distance"]["display"].endswith("mi north") and made["direction"]["value"] == ["north"]
    assert "of Lady Bird Lake (where Google Maps puts it)" in made["distance"]["evidence"]["quote"]
    assert geo.point_of({"latitude": "30.5", "longitude": -97.6}) == (30.5, -97.6)
    for bad in (None, {"lat": 0, "lng": 0}, {"lat": 95, "lng": 1}, {"lat": "x", "lng": 1}):
        assert geo.point_of(bad) is None
    assert geo.anchor_query("Lady Bird Lake", "Austin, TX") == "Lady Bird Lake, Austin, TX"
    assert geo.anchor_query("Lady Bird Lake Austin", "Austin") == "Lady Bird Lake Austin"


@pytest.mark.asyncio
async def test_the_anchor_is_found_on_google_maps_else_by_address():
    provider = AsyncMock()
    provider.locate = AsyncMock(return_value=("Lady Bird Lake", LAKE))
    census = AsyncMock(return_value=(1.0, 2.0))
    found = await geo.resolve_anchor("Lady Bird Lake", "Austin", provider=provider, geocode=census)
    assert found["lat"] == LAKE[0] and found["source"] == "google_maps"
    provider.locate.assert_awaited_once_with("Lady Bird Lake, Austin")
    census.assert_not_awaited()
    provider.locate = AsyncMock(side_effect=providers.ProviderError("down"))
    assert (await geo.resolve_anchor("100 Congress Ave", "Austin", provider=provider, geocode=census))["source"] == "census"
    lost = await geo.resolve_anchor("Atlantis", None, provider=None, geocode=AsyncMock(side_effect=RuntimeError()))
    assert "lat" not in lost and "Atlantis" in lost["error"]


@pytest.mark.asyncio
async def test_a_finding_is_placed_by_its_address():
    address = {"value": "301 W 2nd St, Austin, TX 78701", "status": "claimed",
               "evidence": {"url": "https://other.test/a", "origin": "model"}}
    census = AsyncMock(return_value=KYLE)
    made = await geo.from_address({"address": address}, ANCHOR, geocode=census)
    assert made["distance"]["status"] == "claimed" and made["direction"]["value"] == ["south"]
    assert made["distance"]["evidence"]["origin"] == "geocode"
    for fields in ({}, {"address": {**address, "value": "Downtown"}}, {"address": {**address, "status": "unknown"}}):
        assert await geo.from_address(fields, ANCHOR, geocode=census) == {}
    assert await geo.from_address({"address": address}, ANCHOR, geocode=AsyncMock(return_value=None)) == {}
    assert await geo.from_address({"address": address}, ANCHOR, geocode=AsyncMock(side_effect=OSError())) == {}


def test_a_page_says_where_it_is():
    ld = {"@context": "https://schema.org", "@type": "ApartmentComplex", "name": "The Domain Lofts",
          "geo": {"@type": "GeoCoordinates", "latitude": 30.4021, "longitude": -97.7253}}
    html = f'<html><script type="application/ld+json">{json.dumps(ld)}</script><body>x</body></html>'.encode()
    page = extract_page(html, "https://thedomain.test/")
    assert page["listings"][0]["geo"] == {"lat": 30.4021, "lng": -97.7253}
    assert geo.page_point(page, "The Domain Lofts") == (30.4021, -97.7253)
    plain = extract_page(html.replace(b'"geo"', b'"nope"'), "https://thedomain.test/")
    assert "geo" not in plain["listings"][0] and geo.page_point(plain, "x") is None


def test_google_maps_results_carry_their_point():
    raw = {"title": "The Domain", "place_id": "p1", "website": "https://thedomain.test/", "address": "11400 Domain Dr",
           "gps_coordinates": {"latitude": 30.4021, "longitude": -97.7253}, "type": "Apartment complex",
           "price": "$$", "rating": 4.4, "reviews": 210}
    item = providers.place_item(raw, today=TODAY)
    assert item.point == (30.4021, -97.7253)
    home = phases.as_kind(item, {"item_kind": "listing"}, ANCHOR)
    assert home.kind == "listing" and "cuisine" not in home.fields and "price_level" not in home.fields
    assert home.fields["distance"]["evidence"]["origin"] == "provider" and home.fields["rating"]["value"] == 4.4
    place = phases.as_kind(item, {"item_kind": "place"}, None)
    assert place.kind == "place" and "cuisine" in place.fields and "distance" not in place.fields


@pytest.mark.asyncio
async def test_locate_asks_google_maps_for_one_place():
    api = providers.SearchApi("key")
    api._get = AsyncMock(return_value={"place_result": {"title": "Lady Bird Lake",
                                                        "gps_coordinates": {"latitude": LAKE[0], "longitude": LAKE[1]}}})
    assert await api.locate("Lady Bird Lake, Austin") == ("Lady Bird Lake", LAKE)
    api._get = AsyncMock(return_value={"local_results": [{"title": "Lake", "gps_coordinates": {"latitude": 1, "longitude": 2}}]})
    assert await api.locate("x") == ("Lake", (1.0, 2.0))
    api._get = AsyncMock(return_value={"local_results": [{"title": "Lake"}]})
    assert await api.locate("x") is None


@pytest.mark.asyncio
async def test_the_anchor_is_found_once_and_kept_in_the_plan(conn):
    provider = AsyncMock()
    provider.locate = AsyncMock(return_value=("Lady Bird Lake", LAKE))
    task = task_row(playbook="apartments", brief=json.dumps(BRIEF))
    anchor = await phases.ensure_anchor(task, _deps(provider=lambda: provider), _guard())
    assert anchor["lat"] == LAKE[0]
    saved = conn.ran("jsonb_build_object('anchor'")
    assert saved and json.loads(saved[0][2][2])["name"] == "Lady Bird Lake" and saved[0][2][1] == TOKEN
    # Kept: no second lookup.
    assert (await phases.ensure_anchor(task, _deps(provider=lambda: provider), _guard()))["lat"] == LAKE[0]
    provider.locate.assert_awaited_once()
    # Not found: kept as not found, distances stay unknown.
    lost = task_row(playbook="apartments", brief=json.dumps(BRIEF))
    deps = _deps(provider=lambda: None, geocode=AsyncMock(return_value=None))
    assert await phases.ensure_anchor(lost, deps, _guard()) is None
    assert "error" in phases.plan_of(lost)["anchor"]
    assert await phases.ensure_anchor(task_row(), _deps(), _guard()) is None  # nothing named


@pytest.mark.asyncio
async def test_google_maps_buildings_become_listings_with_distance(conn, monkeypatch):
    provider = AsyncMock()
    provider.locate = AsyncMock(return_value=("Lady Bird Lake", LAKE))
    provider.search = AsyncMock(return_value=[
        providers.ProviderItem(kind="place", title="North Lofts", url="https://north.test/", provider="google_maps",
                               point=ROUND_ROCK),
        providers.ProviderItem(kind="place", title="East Flats", url="https://east.test/", provider="google_maps",
                               point=MANOR),
    ])
    insert = AsyncMock(return_value=2)
    monkeypatch.setattr(items_mod, "insert_items", insert)
    conn.on("COUNT(*) FROM mw_agent_task_items", 0)
    plan = contracts.plan_from_brief("apartments", BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    task = task_row(playbook="apartments", brief=json.dumps(BRIEF), plan=json.dumps(plan))
    out = await phases.run_providers(task, _deps(provider=lambda: provider), _guard())
    assert "Google Maps" in out.progress["note"]
    records = insert.await_args.args[4]
    # Each search finds both (the store keeps one of each): east breaks a limit, so it is last.
    assert list(dict.fromkeys(r["title"] for r in records)) == ["North Lofts", "East Flats"]
    assert all(r["kind"] == "listing" for r in records)
    assert insert.await_args.kwargs["room"] == phases.PROVIDER_BUILDINGS  # page loads for each one's floor plans
    assert records[0]["fields"]["direction"]["value"] == ["north"]
    # The map is searched around each direction asked first, then the plan's own queries.
    calls = provider.search.await_args_list
    assert [c.args[1] for c in calls[:2]] == ["apartments", "apartments"]
    north, south = (float(c.kwargs["ll"][1:].split(",")[0]) for c in calls[:2])
    assert north > LAKE[0] + 0.1 and south < LAKE[0] - 0.1
    assert all("ll" not in c.kwargs for c in calls[2:]) and len(calls) == 2 + len(plan["queries"][:6])


def test_the_map_is_searched_in_every_direction_asked():
    north, south = geo.areas(ANCHOR, BRIEF)
    assert north.endswith(",13z") and south.endswith(",13z")
    for spot, way in ((north, "north"), (south, "south")):
        point = tuple(float(x) for x in spot[1:-4].split(","))
        assert round(geo.miles(LAKE, point)) == 15 and geo.quarter(geo.bearing(LAKE, point)) == way
    between = geo.areas(ANCHOR, {"min_miles": 10, "max_miles": 20})  # no direction: all four
    assert len(between) == 4 and round(geo.miles(LAKE, tuple(float(x) for x in between[1][1:-4].split(",")))) == 15
    assert geo.areas(ANCHOR, {"max_miles": 5}) == [f"@{LAKE[0]:.5f},{LAKE[1]:.5f},13z"]
    assert geo.areas(ANCHOR, {"max_miles": 10})[0].endswith(",12z")
    out_to = geo.areas(ANCHOR, {"max_miles": 10, "directions": ["east"]})[0]
    assert round(geo.miles(LAKE, tuple(float(x) for x in out_to[1:-4].split(",")))) == 5
    assert geo.areas(ANCHOR, {}) == []
    west = geo.areas(ANCHOR, {"directions": ["west"]})[0]
    assert round(geo.miles(LAKE, tuple(float(x) for x in west[1:-4].split(",")))) == geo.DIRECTION_MILES


@pytest.mark.asyncio
async def test_a_map_search_is_centred_where_asked():
    for api in (providers.SearchApi("key"), providers.SerpApi("key")):
        api._get = AsyncMock(return_value={"local_results": []})
        await api.search("places", "apartments", ll="@30.4,-97.7,12z")
        assert api._get.await_args.args[0]["ll"] == "@30.4,-97.7,12z"
        await api.search("places", "apartments")
        assert "ll" not in api._get.await_args.args[0]
        await api.search("shopping", "lip balm", ll="@30.4,-97.7,12z")
        assert "ll" not in api._get.await_args.args[0]


@pytest.mark.asyncio
async def test_nothing_measured_searches_only_the_plans_queries(conn, monkeypatch):
    provider = AsyncMock()
    provider.search = AsyncMock(return_value=[])
    monkeypatch.setattr(items_mod, "insert_items", AsyncMock(return_value=0))
    conn.on("COUNT(*) FROM mw_agent_task_items", 0)
    brief = {"location": "Austin, TX", "budget_max": 2000}
    plan = contracts.plan_from_brief("apartments", brief, today=TODAY, kind=kinds.APARTMENTS)
    task = task_row(playbook="apartments", brief=json.dumps(brief), plan=json.dumps(plan))
    await phases.run_providers(task, _deps(provider=lambda: provider), _guard())
    assert provider.search.await_args_list and all("ll" not in c.kwargs for c in provider.search.await_args_list)


@pytest.mark.asyncio
async def test_enrich_places_a_finding_from_its_page_or_address(conn, monkeypatch):
    plan = {**contracts.plan_from_brief("apartments", BRIEF, today=TODAY, kind=kinds.APARTMENTS), "anchor": ANCHOR}
    task = task_row(playbook="apartments", brief=json.dumps(BRIEF), plan=json.dumps(plan))
    ld = {"@context": "https://schema.org", "@type": "ApartmentComplex", "name": "Sunny 1BR",
          "address": {"streetAddress": "1 Main St", "addressLocality": "Kyle", "addressRegion": "TX"},
          "geo": {"latitude": KYLE[0], "longitude": KYLE[1]}}
    page = f'<html><script type="application/ld+json">{json.dumps(ld)}</script><body>Up to 6 weeks free!</body></html>'
    census = AsyncMock(return_value=ROUND_ROCK)
    rows = [item_row(fields="{}", images="[]")]
    conn.on("WHERE task_id = $1 AND enriched_at IS NULL AND status IN", rows)
    conn.on("COALESCE(SUM(jsonb_array_length(images)), 0)", 0)
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND enriched_at IS NULL", 0)
    fetch = AsyncMock(return_value=_fetched(page.encode(), final="https://apts.test/1"))
    deps = _deps(page_fetch=fetch, geocode=census, rehost=AsyncMock(return_value=([], [])))
    await phases.enrich(task, deps, _guard())
    saved = json.loads(conn.ran("enriched_at = NOW(), updated_at = NOW()")[0][2][3])
    assert saved["direction"]["value"] == ["south"] and saved["distance"]["evidence"]["origin"] == "jsonld"
    assert saved["specials"]["value"] == "Up to 6 weeks free"
    census.assert_not_awaited()  # the page said where it is

    update = {"fields": {"address": {"value": "1 Main St, Round Rock, TX", "status": "verified",
                                     "evidence": {"url": "https://apts.test/2", "origin": "jsonld"}}},
              "status": "verified"}
    await phases.locate(update, ANCHOR, deps)
    assert update["fields"]["distance"]["evidence"]["origin"] == "geocode"
    census.assert_awaited_once_with("1 Main St, Round Rock, TX")
    await phases.locate(update, ANCHOR, deps)  # already verified: no second lookup
    census.assert_awaited_once()


# ── Apply ────────────────────────────────────────────────────────────────────

LISTING = "https://www.thedomain.test/floorplans/a1"
PAGE = b"""<html><body>
<header><a href="/apply-now">Apply Now</a></header>
<a href="https://domain.securecafe.com/onlineleasing/domain/oleapplication.aspx">Start your application</a>
<a href="/careers/apply">Apply for a job</a>
<a href="http://elsewhere.test/apply">apply</a>
<a href="/floorplans">Floor plans</a>
</body></html>"""


def _listing(**over):
    fields = {"price": {"value": 1850, "display": "$1,850/mo", "status": "verified"},
              "specials": {"value": "Up to 6 weeks free", "display": "Up to 6 weeks free", "status": "verified"},
              "phone": {"value": "(512) 555-0100", "display": "(512) 555-0100", "status": "verified"}}
    return item_row(**{"kind": "listing", "title": "The Domain Lofts", "url": LISTING, "fields": json.dumps(fields), **over})


def _ctx(**over):
    return ActionContext(user=PERSON, task=task_row(playbook="apartments"), item=_listing(**over))


def test_apply_is_the_apartments_action():
    assert "apply" in actions.ACTIONS and playbooks.get("apartments").actions == ("apply",)
    assert apply.available(_ctx()) is None
    assert "Only homes" in apply.available(_ctx(kind="product"))
    assert "Google's page" in apply.available(_ctx(url="https://www.google.com/maps/search/?api=1&query=x"))
    assert "off the market" in apply.available(_ctx(status="unavailable"))


def test_application_links_best_first():
    links = apply.apply_links(PAGE, LISTING)
    assert [link["url"] for link in links] == [
        "https://www.thedomain.test/apply-now",
        "https://domain.securecafe.com/onlineleasing/domain/oleapplication.aspx",
    ]
    by_path = apply.apply_links(b'<a href="https://x.rentcafe.com/apply/x">Go</a><a href="/a">Apply</a>', LISTING)
    assert by_path[0]["url"] == "https://www.thedomain.test/a"  # its words beat a path


@pytest.mark.asyncio
async def test_apply_opens_the_application_its_page_links_to():
    proposal = await apply.prepare(_ctx(), {}, fetch=AsyncMock(return_value=_fetched(PAGE, final=LISTING)))
    assert proposal.frozen == {"kind": "application", "url": "https://www.thedomain.test/apply-now",
                               "title": "The Domain Lofts", "site": "thedomain.test", "listing": LISTING}
    lines = {line.label: line.value for line in proposal.lines}
    assert lines["Rent"] == "$1,850/mo" and lines["Specials"] == "Up to 6 weeks free"
    assert lines["Leasing office"] == "(512) 555-0100" and "doesn't apply, pay or sign" in proposal.note
    done = await apply.perform(_ctx(), proposal.frozen)
    assert done["url"] == "https://www.thedomain.test/apply-now" and "application" in done["headline"]


@pytest.mark.asyncio
async def test_apply_without_a_link_opens_the_listing():
    for fetch in (AsyncMock(return_value=_fetched(b"<p>Call us</p>", final=LISTING)),
                  AsyncMock(side_effect=UnsafeURL("private")), AsyncMock(side_effect=RuntimeError()),
                  AsyncMock(return_value=_fetched(b"%PDF", ctype="application/pdf"))):
        proposal = await apply.prepare(_ctx(), {}, fetch=fetch)
        assert proposal.frozen["kind"] == "listing" and proposal.frozen["url"] == LISTING
        assert proposal.confirm == "Open thedomain.test"
    done = await apply.perform(_ctx(), proposal.frozen)
    assert done["headline"] == "Opened the listing at thedomain.test"
    with pytest.raises(ActionError, match="off the market"):
        await apply.prepare(_ctx(), {}, fetch=AsyncMock(return_value=_fetched(status=410)))
    with pytest.raises(ActionError):
        await apply.prepare(_ctx(url="https://www.google.com/maps/x"), {}, fetch=AsyncMock())


@pytest.mark.asyncio
async def test_apply_survives_a_page_it_cannot_read(monkeypatch):
    monkeypatch.setattr(apply, "apply_links", lambda *_: (_ for _ in ()).throw(RecursionError()))
    proposal = await apply.prepare(_ctx(), {}, fetch=AsyncMock(return_value=_fetched(PAGE, final=LISTING)))
    assert proposal.frozen["kind"] == "listing"


def test_the_apartments_card_says_what_it_does():
    described = playbooks.get("apartments").description
    assert "specials" in described and "applied to" in described


# ── a building's rents ───────────────────────────────────────────────────────

FLOOR_PLANS = ("Floor Plan A1 1 bed 1 bath 701 sq. ft. $1,449.38 - $1,464.38 /mo* 12 months $1,415 - $1,430 "
               "Base Rent * Total Monthly Leasing Price. Plan A2 1 bed 1 bath $1,554.38 /mo* 12 months. "
               "Plan B1 2 bed 2 bath $2,648 - $2,753 /mo* Up to 6 weeks free!")


def test_a_buildings_rent_is_every_span_its_floor_plans_state():
    found = F.scan_listing_text(FLOOR_PLANS, url="https://b.test/fp", today=TODAY, building=True)
    price = found["price"]
    assert price["value"] == 1449 and price["high"] == 2753 and price["display"] == "$1,449–$2,753/mo"
    assert price["spans"] == [[1449, 1464], [1554, 1554], [2648, 2753]] and price["unit"] == "month"
    assert F.verify_quote(price["evidence"]["quote"], " ".join(FLOOR_PLANS.split()))
    assert found["specials"]["value"] == "Up to 6 weeks free"
    starting = F.scan_listing_text("Find your floor plan. Starting at $1125. See availability", url="u",
                                   today=TODAY, building=True)["price"]
    assert starting["display"] == "From $1,125/mo" and starting["spans"] == [[1125, None]]
    several = F.scan_listing_text("Studio starting at $1,123. 2 bed starting at $1,939", url="u", today=TODAY,
                                  building=True)["price"]
    assert several["display"] == "$1,123–$1,939+/mo" and several["high"] == 1939
    mixed = F.scan_listing_text("A1 $1,449 - $1,464/mo. B2 starting at $2,900", url="u", today=TODAY,
                                building=True)["price"]
    assert mixed["display"] == "$1,449–$2,900+/mo"
    one = F.scan_listing_text("Only one left: $1,700/mo", url="u", today=TODAY, building=True)["price"]
    assert one["display"] == "$1,700/mo" and "high" not in one
    assert "price" not in F.scan_listing_text("Call for pricing", url="u", today=TODAY, building=True)
    # A single home's page with two figures still says nothing.
    assert "price" not in F.scan_listing_text("$2,100/mo or $1,950/mo", url="u", today=TODAY)


@pytest.mark.parametrize("spans,want", [
    ([[1449, 1464], [1554, 1554], [2648, 2753]], "violates"),  # nothing between 1,600 and 2,000
    ([[1449, 1464], [1554, 1900]], "ok"),  # a plan's range reaches into it
    ([[1700, None]], "ok"),  # starting at 1,700: the cheapest is in it
    ([[1125, None]], "unknown"),  # starting at 1,125: dearer homes may be in it
    ([[2100, None]], "violates"),  # starting above it
])
def test_a_budget_is_met_when_any_rent_overlaps_it(spans, want):
    rule = {"field": "price", "op": "between", "value": [1600, 2000], "unit": "month", "currency": "USD"}
    entry = {"value": spans[0][0], "status": "verified", "unit": "month", "currency": "USD", "spans": spans}
    assert ranking.check(rule, entry) == want


def test_between_and_the_other_limits_on_spans():
    entry = {"value": 1449, "status": "verified", "unit": "month", "currency": "USD", "spans": [[1449, 1464], [2648, 2753]]}
    assert ranking.check({"field": "price", "op": "lte", "value": 1500}, entry) == "ok"
    assert ranking.check({"field": "price", "op": "gte", "value": 2700}, entry) == "ok"
    assert ranking.check({"field": "price", "op": "gte", "value": 3000}, entry) == "violates"
    assert ranking.check({"field": "price", "op": "eq", "value": 1449}, entry) == "unknown"
    assert ranking.check({"field": "price", "op": "eq", "value": 1449}, {**entry, "spans": [[1449, 1449]]}) == "ok"
    assert ranking.check({"field": "price", "op": "eq", "value": 9}, {**entry, "spans": [[1449, 1449]]}) == "violates"
    assert ranking.check({"field": "price", "op": "gte", "value": 1600}, {**entry, "spans": [[1125, None]]}) == "unknown"
    assert ranking.check({"field": "beds", "op": "between", "value": [1, 2]}, {"value": 2, "status": "verified"}) == "ok"
    assert ranking.describe({"field": "price", "op": "between", "value": [1600, 2000], "unit": "month",
                             "currency": "USD"}) == "Price between $1,600 and $2,000/mo"
    assert ranking.describe({"field": "beds", "op": "between", "value": [1, 2]}) == "Beds between 1 and 2"
    assert contracts.clean_constraint({"field": "price", "op": "between", "value": ["2,000", 1600]},
                                      today=TODAY)["value"] == [1600, 2000]
    for bad in ([1600], "1600", [1600, "lots"]):
        assert contracts.clean_constraint({"field": "price", "op": "between", "value": bad}, today=TODAY) is None


HOME = b"""<html><body><nav><a href="/floorplans/">Floor Plans</a></nav>
<a href="https://other.test/floorplans">Floor plans elsewhere</a><a href="/">Home</a></body></html>"""


def test_a_buildings_floor_plans_link():
    assert phases.plans_link(HOME, "https://www.bldg.test/") == "https://www.bldg.test/floorplans/"
    assert phases.plans_link(b'<a href="/plans-availability/">Check Availability</a>', "https://bldg.test/") == \
        "https://bldg.test/plans-availability/"
    assert phases.plans_link(b'<a href="/amenities">Amenities</a>', "https://bldg.test/") is None
    assert phases._no_rent({}) and phases._no_rent({"price": {"spans": [[1125, None]]}})
    assert not phases._no_rent({"price": {"value": 1500}})


@pytest.mark.asyncio
async def test_floor_plans_are_read_or_viewed(monkeypatch):
    plans = f"<html><body><p>{FLOOR_PLANS}</p></body></html>".encode()
    fetch = AsyncMock(return_value=_fetched(plans, final="https://www.bldg.test/floorplans/"))
    found = await phases.floor_plans(HOME, "https://www.bldg.test/", _deps(page_fetch=fetch), Budget(left=1),
                                     Budget(left=0), prefix="p", today=TODAY)
    assert found["price"]["display"] == "$1,449–$2,753/mo"
    # Drawn by JavaScript: viewed in the browser.
    blank = AsyncMock(return_value=_fetched(b"<html><body><div id=app>Loading</div></body></html>"))
    view = AsyncMock(return_value={"url": "https://www.bldg.test/floorplans/", "text": "A1 $1,800 - $1,900 /mo"})
    found = await phases.floor_plans(HOME, "https://www.bldg.test/", _deps(page_fetch=blank, view=view,
                                     browser_ready=lambda: True), Budget(left=1), Budget(left=1), prefix="p", today=TODAY)
    assert found["price"]["spans"] == [[1800, 1900]] and found["price"]["evidence"]["origin"] == "browser"
    # No link, no page loads left, or a page that won't load: nothing.
    for html, fetches, fetcher in ((b"<a href='/x'>x</a>", 1, fetch), (HOME, 0, fetch),
                                   (HOME, 1, AsyncMock(side_effect=OSError())),
                                   (HOME, 1, AsyncMock(return_value=_fetched(status=404)))):
        assert await phases.floor_plans(html, "https://www.bldg.test/", _deps(page_fetch=fetcher), Budget(left=fetches),
                                        Budget(left=0), prefix="p", today=TODAY) == {}


@pytest.mark.asyncio
async def test_a_building_from_google_maps_reads_its_floor_plans():
    home = b"<html><body><a href='/floorplans/'>View Floor Plans</a> Starting at $1125</body></html>"
    plans = f"<html><body><p>{FLOOR_PLANS}</p></body></html>".encode()
    fetch = AsyncMock(side_effect=[_fetched(home, final="https://www.bldg.test/"),
                                   _fetched(plans, final="https://www.bldg.test/floorplans/")])
    row = dict(item_row(fields="{}", origin="provider", url="https://www.bldg.test/", title="Bldg"))
    update = await phases.enrich_one(row, _deps(page_fetch=fetch), Budget(left=2), Budget(left=0), prefix="p")
    assert update["fields"]["price"]["display"] == "$1,449–$2,753/mo"  # beats the home page's "starting at"
    assert update["fields"]["specials"]["value"] == "Up to 6 weeks free"


@pytest.mark.asyncio
async def test_a_buildings_one_price_is_where_its_rents_start():
    # Its page gives one figure (schema.org), and there are no floor plans to read.
    home = (b"<html><head><script type='application/ld+json'>{\"@type\": \"ApartmentComplex\", "
            b"\"name\": \"Bldg\", \"offers\": {\"@type\": \"Offer\", \"price\": 1500, "
            b"\"priceCurrency\": \"USD\"}}</script></head><body>Bldg</body></html>")
    fetch = AsyncMock(return_value=_fetched(home, final="https://www.bldg.test/"))
    row = dict(item_row(fields="{}", origin="provider", url="https://www.bldg.test/", title="Bldg"))
    update = await phases.enrich_one(row, _deps(page_fetch=fetch), Budget(left=2), Budget(left=0), prefix="p")
    price = update["fields"].get("price")
    if price is not None:
        assert price["spans"] == [[price["value"], None]] and price["display"].startswith("From ")
        assert ranking.check({"field": "price", "op": "between", "value": [1600, 2000]}, price) == "unknown"
    assert F.starting_at({"value": 1500, "display": "$1,500/mo"}) == {
        "value": 1500, "display": "From $1,500/mo", "spans": [[1500, None]]}


def test_a_finding_with_specials_ranks_higher():
    assert contracts.clean_preference({"field": "specials", "weight": 0.5}) == {"field": "specials", "weight": 0.5}
    assert contracts.clean_preference({"field": "neighborhood", "weight": 0.5}) is None
    plan = {"constraints": [], "preferences": [{"field": "specials", "weight": 1}], "fit_weight": 0}
    special = {"value": "6 weeks free", "status": "verified", "display": "6 weeks free"}
    found = [{"id": "a", "fields": {}, "fit_score": 3}, {"id": "b", "fields": {"specials": special}, "fit_score": 3}]
    assert [r.item_id for r in ranking.rank(found, plan)] == ["b", "a"]


def test_a_result_sent_as_json_text_is_read():
    answer = {"headline": "Five buildings", "summary": "", "sections": [], "top": []}
    out, _ = contracts.normalize_summary({"result": json.dumps(answer)}, batch={}, item_texts={}, citable=set())
    assert out["headline"] == "Five buildings"
    # The finish tool's fields are the answer's own, no `result` wrapper to send as text.
    assert contracts.SUMMARY_FINISH.parameters is contracts.SUMMARY_SCHEMA
    assert contracts.normalize_summary(answer, batch={}, item_texts={}, citable=set())[0]["headline"] == "Five buildings"
    with pytest.raises(ValueError):
        contracts.normalize_summary(None, batch={}, item_texts={}, citable=set())
    # A list sent as JSON text is the list; text that only looks like one stays text.
    sections = [{"heading": "South", "body_md": "Kyle and Buda."}]
    out, _ = contracts.normalize_summary({**answer, "sections": json.dumps(sections), "summary": "[not json"},
                                         batch={}, item_texts={}, citable=set())
    assert out["sections"][0]["heading"] == "South" and out["summary"] == "[not json"
    assert contracts._unquoted('"just text"') == '"just text"' and contracts._unquoted("[1, 2]") == [1, 2]
    assert contracts._unquoted("{1}") == "{1}" and contracts._unquoted(" 7") == " 7"
    with pytest.raises(ValueError, match="not as a string"):
        contracts.normalize_summary({"result": '{"headline": "x", "sections": [{"a": "b"]}'}, batch={},
                                    item_texts={}, citable=set())
    with pytest.raises(ValueError):
        contracts.normalize_summary({"result": "[1, 2]"}, batch={}, item_texts={}, citable=set())


def test_screening_leaves_the_limits_to_code():
    text = " ".join(prompts.SCREEN.split())
    assert "a must have that only restates one" in text and "not a reason to score lower" in text
    assert "a finding that doesn't show it isn't failing" in text
    assert "it never makes a finding irrelevant" in text
    assert "a finding without it doesn't fail" in " ".join(prompts.SUMMARIZE.split())
    assert "any part of it is inside" in " ".join(prompts.SUMMARIZE.split())


def test_nearer_is_better_whatever_the_planner_says():
    pref = contracts.clean_preference({"field": "distance", "weight": 0.4, "higher_is_better": True})
    assert pref == {"field": "distance", "weight": 0.4}
    far = {"value": 33.2, "status": "verified"}
    near = {"value": 17.0, "status": "verified"}
    found = [{"id": "far", "fields": {"distance": far}}, {"id": "near", "fields": {"distance": near}}]
    assert [r.item_id for r in ranking.rank(found, {"preferences": [pref], "fit_weight": 0})] == ["near", "far"]
    assert contracts.clean_preference({"field": "rating", "weight": 1, "higher_is_better": False})["higher_is_better"] is False


def _building(title, miles, way):
    point = geo.offset(LAKE, miles, geo.BEARINGS[way])
    return phases.as_kind(providers.ProviderItem(kind="place", title=title, url=f"https://{title}.test/",
                                                 provider="google_maps", point=point),
                          {"item_kind": "listing"}, ANCHOR)


def test_every_direction_asked_gets_room():
    plan = contracts.plan_from_brief("apartments", BRIEF, today=TODAY, kind=kinds.APARTMENTS)
    norths = [_building(f"n{i}", 12 + i, "north") for i in range(4)]
    found = [*norths, _building("s0", 15, "south"), _building("close", 3, "south"), _building("s1", 16, "south")]
    titles = [i.title for i in phases.prerank(found, plan)]
    assert titles[:4] == ["n0", "s0", "n1", "s1"] and titles[-1] == "close"  # too close: last
    assert phases.asked_directions(plan) == ["north", "south"]
    one_way = {**BRIEF, "directions": ["north"]}
    plan = contracts.plan_from_brief("apartments", one_way, today=TODAY, kind=kinds.APARTMENTS)
    assert [i.title for i in phases.prerank(norths, plan)] == ["n0", "n1", "n2", "n3"]
    unplaced = providers.ProviderItem(kind="listing", title="u", url="https://u.test/", provider="google_maps")
    assert phases.by_direction([unplaced, norths[0]], ["north", "south"])[-1] is unplaced


def test_espresso_reads_a_multi_choice_field_as_a_list():
    from app.matcha.services.matcha_work.agent_runtime.abilities import tasks as tasks_ability

    text = tasks_ability._prompt(None)
    assert "directions (In these directions from it: a list of any of north | east | south | west)" in text
    assert "goes there, not in must_haves" in " ".join(text.split())
    assert "Something they want to find out about each one" in " ".join(text.split())
