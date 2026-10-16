"""An apartment building's homes one by one (`research/units.py`) and how
they reach ranking, the item views, the model and the enrich phase."""
import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.services.safe_fetch import FetchedResponse
from app.matcha.services.matcha_work.agent_runtime import chain
from app.matcha.services.matcha_work.agent_runtime.chain import Budget, Guard
from app.matcha.services.matcha_work.agent_tasks import items as items_mod, orchestrator
from app.matcha.services.matcha_work.agent_tasks.research import phases, prompts, ranking
from app.matcha.services.matcha_work.agent_tasks.research import units as U
from tests.agent_runtime.helpers import FakeConn, connection

from ._fixtures import TASK, TODAY, TOKEN, item_row, task_row

SITE = "https://www.parkwest.test/"
EMBED = "https://sightmap.com/embed/my8px6mqp19"
API = "https://sightmap.com/app/api/v1/05eve421wqo/sightmaps/19025"
PLAN_A = "https://cdn.sightmap.com/assets/a.png"
PLAN_B = "https://cdn.sightmap.com/assets/b.jpg"
TOUR = "https://my.matterport.com/show/?m=jMZHWUcMjzt"


def _sightmap(**over) -> dict:
    """A SightMap API answer, shaped as SightMap sends it."""
    unit = {"id": "1000752", "floor_id": "18907", "floor_plan_id": "55943", "unit_number": "A107", "label": "A107",
            "area": 644, "display_price": "$4,177.00", "price": 4177, "specials_description": None,
            "display_available_on": "Available Nov 4th", "display_lease_term": "12 Months",
            "available_on": "2026-11-04",
            "outbound_links": [{"url": TOUR, "label": "View Virtual Tour", "icon_type": "360_tour"}]}
    data = {
        "floors": [{"id": "18907", "filter_label": "Floor 1", "filter_short_label": "1"},
                   {"id": "18908", "filter_label": "Floor 2", "filter_short_label": "2"}],
        "floor_plans": [
            {"id": "55943", "name": json.dumps({"name": "1 Bed 1 Bath", "provider_id": "2229211"}),
             "bedroom_count": 1, "bathroom_count": 1, "image_url": PLAN_A},
            {"id": "55942", "name": "2 Bed 1 Bath", "bedroom_count": 2, "bathroom_count": 1, "image_url": PLAN_B},
        ],
        "units": [
            unit,
            {**unit, "id": "1000753", "unit_number": "B201", "floor_id": "18908", "floor_plan_id": "55942",
             "area": 910, "price": 3300, "available_on": "2026-09-01", "display_lease_term": "13 Months",
             "specials_description": "6 weeks free on a 13-month lease", "outbound_links": []},
            {**unit, "id": "1000754", "unit_number": "B202", "price": None, "display_price": None},
        ],
        **over,
    }
    return {"data": data}


def _avalon(**over) -> dict:
    home = {"unitKey": "CA100-CA100-001-1215", "apartmentNumber": "1215", "floor": 12, "beds": 1, "baths": 1.0,
            "apartmentSize": 716, "promotions": [],
            "pricing": {"amenitizedRent": 4125, "effectiveRent": 4125, "netEffectiveRent": None, "term": 18,
                        "availableDate": "2027-01-25", "showAsAvailable": True}}
    plan = {"floorPlanName": "A2", "floorPlanImage": "https://resource.avalonbay.com/floorplans/CA100/CA100-A2.png",
            "apartments": [home, {**home, "unitKey": "CA100-CA100-001-0319", "apartmentNumber": "319", "floor": 3,
                                  "pricing": {**home["pricing"], "effectiveRent": 3970, "netEffectiveRent": 3640,
                                              "availableDate": "2026-12-04"},
                                  "promotions": [{"promotionTitle": "1 month free"}]}],
            "finishPackages": [{"apartments": [home, {**home, "unitKey": "CA100-CA100-001-0900",
                                                      "pricing": {**home["pricing"], "showAsAvailable": False}}]}]}
    results = {"communityPromotions": [{"promotionTitle": "$250 deposit when you apply by 10-31!"}],
               "availableFloorPlanTypes": [{"availableFloorPlans": [plan]}], **over}
    return {"results": results}


def _loads(answers: dict):
    calls = []

    async def load(url, is_json):
        calls.append((url, is_json))
        answer = answers.get(url)
        return json.dumps(answer).encode() if isinstance(answer, dict) else answer

    return load, calls


# ── finding a building's leasing system ──────────────────────────────────────

def test_a_unit_map_is_found_in_a_page_even_inside_json():
    assert U.sightmap_embed(b'<iframe src="https://sightmap.com/embed/l8xvr1ompjk"></iframe>') == "l8xvr1ompjk"
    assert U.sightmap_embed(b'{"src": "https:\\/\\/sightmap.com\\/embed\\/x1p8dnmrvd6?x=1"}') == "x1p8dnmrvd6"
    assert U.sightmap_embed(b"<p>no map</p>") is None
    assert U.sightmap_embed(b"https://sightmap.com/embed/api") is None


def test_an_avalon_community_is_named_only_on_avalons_own_site():
    page = b"<script>window.x = {communityId: 'AVB-CA104', y: 1}</script>"
    avalon = "https://www.avaloncommunities.com/california/san-francisco-apartments/avalon-hayes-valley/"
    assert U.avalon_code(page, avalon) == "CA104"
    assert U.avalon_code(b'<a href="/x/apartment/CA090-CA090-001-0101/">', avalon) == "CA090"
    assert U.avalon_code(page, "https://www.not-avalon.test/") is None
    assert U.avalon_code(b"<p>nothing</p>", avalon) is None


# ── reading them ─────────────────────────────────────────────────────────────

def test_a_unit_maps_homes_are_read_with_their_rent_floor_plan_and_tour():
    homes = U.sightmap_units(_sightmap(), today=TODAY)
    assert [h["number"] for h in homes] == ["A107", "B201"]  # B202 has no rent: says nothing
    a107, b201 = homes
    assert a107 == {
        "id": "sightmap:1000752", "number": "A107", "floor": "1", "plan": "1 Bed 1 Bath", "beds": 1.0, "baths": 1.0,
        "sqft": 644.0, "rent": 4177.0, "currency": "USD", "available": "2026-11-04", "lease_months": 12,
        "special": None, "plan_image": None, "plan_source": PLAN_A, "tour_url": TOUR, "url": None,
        "source": "sightmap",
    }  # a unit map's homes have no page of their own; the plan waits to be copied to our CDN
    # A move-in date already past is now; the special's free weeks give a net rent on its own lease.
    assert b201["available"] == TODAY.isoformat() and b201["beds"] == 2.0 and b201["lease_months"] == 13
    assert b201["net_rent"] == 2949.0 and b201["net_note"] == "6 weeks free on a 13-month lease"
    # A map with no rents (Avalon's own) lists nothing.
    assert U.sightmap_units({"units": [{"id": 1, "price": None}]}, today=TODAY) == []


def test_avalons_homes_are_read_once_each_with_their_promotions():
    avalon = "https://www.avaloncommunities.com:443/california/x/ava-55-ninth/?utm_source=vurl"
    homes, promotions = U.avalon_units(_avalon(), url=U._page(avalon), today=TODAY)
    assert promotions == ["$250 deposit when you apply by 10-31!"]
    assert [h["number"] for h in homes] == ["1215", "319"]  # 0900 isn't shown as available
    h1215, h319 = homes
    assert h1215["url"] == "https://www.avaloncommunities.com/california/x/ava-55-ninth/apartment/CA100-CA100-001-1215/"
    assert h1215["floor"] == "12" and h1215["lease_months"] == 18 and h1215["available"] == "2027-01-25"
    assert h1215["plan"] == "A2" and h1215["plan_source"].endswith("CA100-A2.png") and "net_rent" not in h1215
    # "1 month free" on an 18-month lease, worked out by code (Avalon's own net is only used when there is none).
    assert h319["special"] == "1 month free" and h319["net_rent"] == round(3970 * 17 / 18)
    plain = _avalon()
    plain["results"]["availableFloorPlanTypes"][0]["availableFloorPlans"][0]["apartments"][1]["promotions"] = []
    homes, _ = U.avalon_units(plain, url=SITE, today=TODAY)
    assert homes[1]["net_rent"] == 3640 and homes[1]["net_note"] == "Avalon's net effective rent"


def test_avalon_homes_without_a_key_are_known_by_their_number():
    keyless = _avalon()
    plan = keyless["results"]["availableFloorPlanTypes"][0]["availableFloorPlans"][0]
    for home in plan["apartments"]:
        home["unitKey"] = None
    plan["apartments"].append({**plan["apartments"][0], "apartmentNumber": None})  # no key, no number: skipped
    plan["finishPackages"] = []
    homes, _ = U.avalon_units(keyless, url=SITE, today=TODAY)
    assert [(h["id"], h["url"]) for h in homes] == [("avalon:A2#1215", None), ("avalon:A2#319", None)]


@pytest.mark.parametrize("special,lease,expected", [
    ("6 weeks free", 12, (round(3000 * (12 - 6 / (52 / 12)) / 12), "6 weeks free on a 12-month lease")),
    ("Two months free on a 14 month lease", None, (round(3000 * 12 / 14), "Two months free on a 14-month lease")),
    ("First month free!", None, (2750, "First month free on a 12-month lease (lease length assumed)")),
    ("free month's rent", 12, (2750, "free month's rent on a 12-month lease")),
    ("Up to 8 weeks free", 12, None),  # a ceiling, not a promise
    ("$500 off move-in", 12, None),
    ("", 12, None),
    ("12 months free", 12, None),  # nothing left to pay is no rent
])
def test_net_rent_comes_only_from_free_time_a_special_states(special, lease, expected):
    assert U.net_rent(3000, special, lease) == (None if expected is None else (float(expected[0]), expected[1]))


@pytest.mark.asyncio
async def test_find_units_tries_avalon_then_the_unit_map():
    avalon = "https://www.avaloncommunities.com/ca/x/"
    load, calls = _loads({U.AVALON_API.format(code="CA100"): _avalon()})
    found = await U.find_units(b"communityId: 'AVB-CA100'", avalon, load, today=TODAY)
    assert found.source == "avalon" and found.promotions and calls == [(U.AVALON_API.format(code="CA100"), True)]
    # The unit map: its embed page names its API.
    embed_page = f'<script>var api = "{API}";</script>'.encode()
    load, calls = _loads({EMBED: embed_page, API: _sightmap()})
    found = await U.find_units(f'<iframe src="{EMBED}">'.encode(), SITE, load, today=TODAY)
    assert found.source == "sightmap" and [u["number"] for u in found.units] == ["B201", "A107"]  # cheapest first
    assert calls == [(EMBED, False), (API, True)]
    # Nothing named, an embed page without its API, an answer that can't be read, or no homes: None.
    # A system already asked for this building is never asked again.
    load, calls = _loads({EMBED: embed_page, API: _sightmap()})
    assert await U.find_units(f'"{EMBED}"'.encode(), SITE, load, today=TODAY,
                              tried={"sightmap:my8px6mqp19"}) is None and calls == []
    for page, answers in ((b"<p>x</p>", {}), (f'"{EMBED}"'.encode(), {EMBED: b"<p>no api</p>"}),
                          (f'"{EMBED}"'.encode(), {EMBED: embed_page, API: b"not json"}),
                          (f'"{EMBED}"'.encode(), {EMBED: embed_page, API: b"[1, 2]"}),
                          (f'"{EMBED}"'.encode(), {EMBED: embed_page, API: {"data": {"units": []}}}),
                          (f'"{EMBED}"'.encode(), {EMBED: None})):
        load, _ = _loads(answers)
        assert await U.find_units(page, SITE, load, today=TODAY) is None


def test_a_buildings_fields_come_from_its_homes():
    found = U.Found(U._cheapest(U.sightmap_units(_sightmap(), today=TODAY)), [], "sightmap", SITE)
    fields = U.building_fields(found, today=TODAY)
    price = fields["price"]
    assert price["display"] == "$3,300–$4,177/mo" and price["spans"] == [[2949.0, 3300.0], [4177.0, 4177.0]]
    assert price["evidence"]["origin"] == "leasing" and price["evidence"]["quote"].startswith("#B201, floor 2")
    assert fields["available_date"]["value"] == TODAY.isoformat()
    assert fields["specials"]["value"] == "6 weeks free on a 13-month lease"
    # One rent: no range. A building-wide promotion is its special.
    one = U.Found(found.units[:1], ["$250 deposit when you apply by 10-31!"], "avalon", SITE)
    fields = U.building_fields(one, today=TODAY)
    assert fields["price"]["display"] == "$3,300/mo" and "high" not in fields["price"]
    assert fields["specials"]["value"] == "$250 deposit when you apply by 10-31!"


def test_a_home_as_a_line():
    home = U.sightmap_units(_sightmap(), today=TODAY)[1]
    assert U.unit_line(home) == ("#B201, floor 2, 2 bd, 1 ba, 910 sq ft, $3,300/mo, $2,949/mo net "
                                 "(6 weeks free on a 13-month lease), available 2026-10-14, "
                                 "special: 6 weeks free on a 13-month lease")
    assert U.unit_line({"rent": 2000.0, "beds": 0.0}) == "a home, studio, $2,000/mo"


# ── ranking a building on its homes ──────────────────────────────────────────

HOMES = [
    {"id": "a", "rent": 3300.0, "net_rent": 2949.0, "beds": 2.0, "baths": 1.0, "available": "2026-10-14"},
    {"id": "b", "rent": 3000.0, "beds": 0.0, "baths": 1.0, "available": "2026-12-01"},
    {"id": "c", "rent": 4177.0, "beds": None, "baths": 1.0},
]
UNDER_3100 = {"field": "price", "op": "lte", "value": 3100}
TWO_BEDS = {"field": "beds", "op": "gte", "value": 2}


def test_a_building_fits_only_when_one_home_meets_every_limit():
    # A home under budget once its special is counted, with two beds: it fits.
    assert ranking.unit_verdict(HOMES, [UNDER_3100, TWO_BEDS]) == (["a"], [], [])
    # One home has the rent, another the beds, none both: no fit, and it says so.
    fits, violations, unsure = ranking.unit_verdict(HOMES[1:2] + [{**HOMES[0], "net_rent": None}],
                                                    [UNDER_3100, TWO_BEDS])
    assert fits == [] and unsure == [] and violations[0]["field"] == "units"
    assert violations[0]["rule"].startswith("No home here meets every limit at once")
    # Every home breaks the same limit: that limit is named, with the cheapest rent.
    fits, violations, _ = ranking.unit_verdict(HOMES, [{"field": "price", "op": "lte", "value": 2500}])
    assert violations == [{"field": "price", "rule": ranking.describe({"field": "price", "op": "lte", "value": 2500}),
                           "value": "From $2,949/mo (3 homes)"}]
    _, violations, _ = ranking.unit_verdict(HOMES[:2], [{"field": "baths", "op": "gte", "value": 2}])
    assert violations[0]["value"] == "None of 2 homes"
    # A home not ruled out but missing a figure: unconfirmed, not hidden.
    assert ranking.unit_verdict(HOMES[2:], [{"field": "beds", "op": "gte", "value": 1}]) == ([], [], ["beds"])


def test_a_building_ranks_on_its_homes_and_says_which_fit():
    plan = {"constraints": [UNDER_3100, TWO_BEDS], "preferences": [], "fit_weight": 0.3}
    fields = {"price": {"value": 3000, "status": "verified", "spans": [[2995, 4177]]}}
    found = [{"id": "x", "fields": fields, "units": HOMES, "fit_score": 3},
             {"id": "y", "fields": fields, "units": HOMES[1:2], "fit_score": 5},
             {"id": "z", "fields": {"price": {"value": 3000, "status": "verified"}}, "fit_score": 3}]
    ranked = {r.item_id: r for r in ranking.rank(found, plan)}
    assert ranked["x"].band == ranking.OK and ranked["x"].explain["units_fit"] == ["a"]
    assert ranked["y"].band == ranking.HIDDEN and ranked["y"].explain["units_fit"] == []
    assert "units_fit" not in ranked["z"].explain  # no homes listed: judged on its own fields
    assert ranking.assess(found[0], plan["constraints"]) == (ranking.OK, [], [])


def test_no_home_fits_a_building_that_breaks_a_limit_of_its_own():
    plan = {"constraints": [UNDER_3100, {"field": "pets", "op": "includes", "value": "dogs"}], "preferences": []}
    no_pets = {"pets": {"value": ["none"], "status": "verified"}}
    [ranked] = ranking.rank([{"id": "x", "fields": no_pets, "units": HOMES}], plan)
    assert ranked.band == ranking.HIDDEN and ranked.explain["units_fit"] == []
    # Pets unconfirmed: the homes that fit still do, and the building says what it couldn't confirm.
    [ranked] = ranking.rank([{"id": "x", "fields": {}, "units": HOMES}], plan)
    assert ranked.explain["units_fit"] == ["a", "b"] and ranked.explain["flags"] == ["unconfirmed:pets"]


def test_a_homes_lowest_rent_is_its_net_rent():
    assert U.lowest_rent({"rent": 3300.0, "net_rent": 2949.0}) == 2949.0
    assert U.lowest_rent({"rent": 3300.0}) == 3300.0
    assert U.lowest_rent({"rent": 3300.0, "net_rent": 3500.0}) == 3300.0


# ── what the app and the model see ───────────────────────────────────────────

def _row(**over):
    return item_row(units=json.dumps(HOMES), rank_explain=json.dumps({"flags": [], "units_fit": ["a"]}), **over)


def test_the_app_sees_how_many_homes_fit_and_each_ones_verdict():
    assert items_mod.item_summary(_row())["homes"] == {"count": 3, "fit": 1, "from": 2949.0}
    assert [u["fits"] for u in items_mod.item_detail(_row())["units"]] == [True, False, False]
    # Before ranking: every home, none judged.
    unranked = item_row(units=json.dumps(HOMES))
    assert items_mod.item_summary(unranked)["homes"] == {"count": 3, "fit": None, "from": 2949.0}
    assert {u["fits"] for u in items_mod.units_view(unranked)} == {None}
    assert items_mod.item_summary(item_row())["homes"] is None and items_mod.units_view(item_row()) == []


def test_the_app_never_sees_a_floor_plans_source():
    homes = [{**HOMES[0], "plan_source": PLAN_A, "plan_image": "https://cdn.test/a.webp"}]
    [unit] = items_mod.units_view(item_row(units=json.dumps(homes)))
    assert "plan_source" not in unit and unit["plan_image"] == "https://cdn.test/a.webp"


def test_the_model_sees_the_homes_that_fit_not_their_ids():
    seen = items_mod.view_for_model(_row())
    assert "units_fit" not in seen["rank_explain"]
    assert seen["homes"] == {"listed": 3, "meet_every_limit": 1, "homes_that_fit": [U.unit_line(HOMES[0])]}
    assert "homes" not in items_mod.view_for_model(item_row())
    # None fit: the cheapest are shown as not fitting, never as examples of a fit.
    none_fit = items_mod.view_for_model(item_row(units=json.dumps(HOMES), rank_explain='{"units_fit": []}'))
    assert none_fit["homes"] == {"listed": 3, "meet_every_limit": 0, "homes_that_fit": [],
                                 "cheapest_not_fitting": [U.unit_line(h) for h in HOMES]}
    # Not ranked yet (screening): examples, none judged.
    unranked = items_mod.view_for_model(item_row(units=json.dumps(HOMES)))
    assert unranked["homes"] == {"listed": 3, "examples": [U.unit_line(h) for h in HOMES]}
    assert "never call one a fit" in prompts.SUMMARIZE
    turn = prompts.screen_turn("a 2bd", {}, [("i1", seen)])
    assert '"meet_every_limit": 1' in turn
    assert '"homes"' in prompts.summary_turn("a 2bd", {}, [("i1", seen)], total=1, hidden=0, note=None)
    assert '"homes"' not in prompts.screen_turn("a 2bd", {}, [("i1", items_mod.view_for_model(item_row()))])


# ── the enrich phase ─────────────────────────────────────────────────────────

def _deps(**over):
    return replace(phases.Deps(), **{"today": lambda: TODAY, "browser_ready": lambda: False, **over})


def _fetched(body=b"", status=200, ctype="text/html", final=SITE, truncated=False):
    return FetchedResponse(url=final, final_url=final, status=status, content_type=ctype, body=body,
                           truncated=truncated)


def _web(pages: dict):
    """page_fetch over a fixed set of URLs, recording each call's arguments."""
    calls = []

    async def fetch(url, **kw):
        calls.append((url, kw))
        answer = pages.get(url)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            return _fetched(status=404, final=url)
        if isinstance(answer, dict):
            return _fetched(json.dumps(answer).encode(), ctype="application/json", final=url)
        return _fetched(answer, final=url)

    return AsyncMock(side_effect=fetch), calls


EMBED_PAGE = f'<script>var api = "{API}";</script>'.encode()
BUILDING = dict(item_row(fields="{}", origin="provider", url=SITE, title="Park West"))


@pytest.mark.asyncio
async def test_a_building_naming_its_unit_map_keeps_every_home():
    home = f'<html><body><a href="/floorplans/">Floor Plans</a> Starting at $2,900 <iframe src="{EMBED}">'.encode()
    fetch, calls = _web({SITE: home, EMBED: EMBED_PAGE, API: _sightmap()})
    fetches = Budget(left=4)
    update = await phases.enrich_one(BUILDING, _deps(page_fetch=fetch), fetches, Budget(left=0), prefix="p")
    assert [u["number"] for u in update["units"]] == ["B201", "A107"]
    assert update["fields"]["price"]["display"] == "$3,300–$4,177/mo"  # the leasing system's, not "starting at"
    assert update["fields"]["price"]["evidence"]["origin"] == "leasing"
    # Its site, the map's embed page and its API; no floor plans page needed.
    assert [url for url, _ in calls] == [SITE, EMBED, API] and fetches.left == 1
    assert calls[2][1]["gzip"] is True and calls[2][1]["accept"] == "application/json"


@pytest.mark.asyncio
async def test_a_unit_map_on_the_floor_plans_page_is_found_there():
    home = b"<html><body><a href='/availability'>Availability</a> Resort-style living</body></html>"
    plans = f'<html><body><div data-src="{EMBED}"></div></body></html>'.encode()
    fetch, calls = _web({SITE: home, SITE + "availability": plans, EMBED: EMBED_PAGE, API: _sightmap()})
    update = await phases.enrich_one(BUILDING, _deps(page_fetch=fetch), Budget(left=4), Budget(left=0), prefix="p")
    assert len(update["units"]) == 2 and [u for u, _ in calls][1] == SITE + "availability"


@pytest.mark.asyncio
async def test_a_leasing_system_that_fails_leaves_the_floor_plans_as_before():
    home = f'<html><body><a href="/floorplans/">Floor Plans</a> <iframe src="{EMBED}"></body></html>'.encode()
    plans = b"<html><body><p>A1 $1,449 - $1,464 /mo*</p></body></html>"
    for broken in (OSError("down"), None):
        fetch, _ = _web({SITE: home, EMBED: broken, SITE + "floorplans/": plans})
        update = await phases.enrich_one(BUILDING, _deps(page_fetch=fetch), Budget(left=4), Budget(left=0),
                                         prefix="p")
        assert "units" not in update and update["fields"]["price"]["spans"] == [[1449, 1464]]
    # No page loads left for the map: it is never asked.
    fetch, calls = _web({SITE: home})
    update = await phases.enrich_one(BUILDING, _deps(page_fetch=fetch), Budget(left=1), Budget(left=0), prefix="p")
    assert [u for u, _ in calls] == [SITE] and "units" not in update
    # A cut-off answer is not read.
    load = phases.leasing_loader(_deps(page_fetch=AsyncMock(return_value=_fetched(b"{", truncated=True))),
                                 Budget(left=1), Budget(left=1))
    assert await load(API, True) is None


AVALON_SITE = "https://www.avaloncommunities.com/ca/sf/ava-x/"
AVALON_PLANS = AVALON_SITE + "floor-plans/"


@pytest.mark.asyncio
async def test_a_building_spends_only_its_own_page_loads():
    # An AVA-style building: Avalon answers with no homes to let, its unit map has no rents,
    # and its floor plans page names both again.
    names = f"communityId: 'AVB-CA100' <iframe src='{EMBED}'>".encode()
    home = b"<html><body><a href='/ca/sf/ava-x/floor-plans/'>Floor Plans</a>" + names + b"</body></html>"
    no_homes = _avalon(availableFloorPlanTypes=[])
    fetch, calls = _web({AVALON_SITE: home, AVALON_PLANS: home, U.AVALON_API.format(code="CA100"): no_homes,
                         EMBED: EMBED_PAGE, API: _sightmap(units=[])})
    fetches = Budget(left=phases.BUILDING_LOADS * 3)  # the round has loads for other buildings too
    row = {**BUILDING, "url": AVALON_SITE}
    update = await phases.enrich_one(row, _deps(page_fetch=fetch), fetches, Budget(left=0), prefix="p")
    asked = [url for url, _ in calls]
    # Its site, Avalon, the map's embed page (its API would be a third leasing load), its floor plans page;
    # nothing on the floor plans page is asked again.
    assert asked == [AVALON_SITE, U.AVALON_API.format(code="CA100"), EMBED, AVALON_PLANS]
    assert fetches.used == phases.BUILDING_LOADS and not fetches.exhausted and "units" not in update


@pytest.mark.asyncio
async def test_the_leasing_systems_figures_beat_the_pages_structured_data():
    offer = (b"<script type='application/ld+json'>{\"@type\": \"ApartmentComplex\", \"name\": \"Park West\", "
             b"\"offers\": {\"@type\": \"Offer\", \"price\": 2800, \"priceCurrency\": \"USD\"}}</script>")
    home = b"<html><head>" + offer + b"</head><body>" + f'<iframe src="{EMBED}">'.encode() + b"</body></html>"
    fetch, _ = _web({SITE: home, EMBED: EMBED_PAGE, API: _sightmap()})
    stored = {"price": {"value": 2700.0, "status": "verified", "display": "$2,700/mo",
                        "evidence": {"origin": "provider"}}}
    row = {**BUILDING, "fields": json.dumps(stored)}
    update = await phases.enrich_one(row, _deps(page_fetch=fetch), Budget(left=4), Budget(left=0), prefix="p")
    price = update["fields"]["price"]
    assert price["display"] == "$3,300–$4,177/mo" and price["evidence"]["origin"] == "leasing"
    assert update["fields"]["available_date"]["evidence"]["origin"] == "leasing"


@pytest.fixture
def conn(monkeypatch):
    c = FakeConn()
    for module in (phases, chain):
        monkeypatch.setattr(module, "connection_or_direct", connection(c))
    c.on("RETURNING GREATEST(LEAST($2, $3 - cur.before), 0)", lambda row_id, want, limit: want)
    return c


def _guard():
    return Guard(orchestrator.TASK_CHAIN, TASK, TOKEN)


@pytest.mark.asyncio
async def test_a_batch_saves_the_homes_with_their_floor_plans_on_our_cdn(conn, monkeypatch):
    row = item_row(id=uuid4(), origin="provider", url=SITE, fields="{}", status="candidate", images="[]")
    conn.on("WHERE task_id = $1 AND enriched_at IS NULL AND status IN", [row])
    conn.on("COALESCE(SUM(jsonb_array_length(images)), 0)", 0)
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND enriched_at IS NULL", 0)
    home = f'<html><body><iframe src="{EMBED}"></body></html>'.encode()
    fetch, _ = _web({SITE: home, EMBED: EMBED_PAGE, API: _sightmap()})

    async def rehost(images, **kw):
        source = images[0]["source_url"]
        assert kw["prefix"].endswith("/plans") and kw["limit"] == 1
        return ([{"url": "https://cdn.test/b.webp"}] if source == PLAN_B else []), []

    rehost = AsyncMock(side_effect=rehost)
    plan = {"constraints": [UNDER_3100, TWO_BEDS], "preferences": []}
    monkeypatch.setattr(phases, "PLAN_IMAGE_CONCURRENCY", 1)
    await phases.enrich(task_row(plan=json.dumps(plan)), _deps(page_fetch=fetch, rehost=rehost), _guard())
    # Its fetch grant covers its site, its floor plans page and its leasing system.
    assert conn.ran("fetch_calls AS before")[0][2][1] == phases.BUILDING_LOADS
    # The plan of the home that fits (B201) first; the one that failed is never shown from SightMap,
    # but its source is kept for a later pass.
    assert [c.args[0][0]["source_url"] for c in rehost.await_args_list] == [PLAN_B, PLAN_A]
    [save] = conn.ran("enriched_at = NOW(), updated_at = NOW()")
    saved = json.loads(save[2][7])
    assert [(u["number"], u["plan_image"], u["plan_source"]) for u in saved] == [
        ("B201", "https://cdn.test/b.webp", PLAN_B), ("A107", None, PLAN_A)]
    # Read again later: the plan already on our CDN is reused, not copied again.
    conn.on("WHERE task_id = $1 AND enriched_at IS NULL AND status IN", [{**row, "units": save[2][7]}])
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND enriched_at IS NULL", 0)
    rehost.reset_mock()
    await phases.enrich(task_row(plan=json.dumps(plan)), _deps(page_fetch=_web(
        {SITE: home, EMBED: EMBED_PAGE, API: _sightmap()})[0], rehost=rehost), _guard())
    assert [c.args[0][0]["source_url"] for c in rehost.await_args_list] == [PLAN_A]
    saved = json.loads(conn.ran("enriched_at = NOW(), updated_at = NOW()")[-1][2][7])
    assert saved[0]["plan_image"] == "https://cdn.test/b.webp"


@pytest.mark.asyncio
async def test_a_batchs_photos_and_floor_plans_are_copied_at_the_same_time(conn):
    rows = [item_row(id=uuid4(), origin="provider", url=SITE, fields="{}", status="candidate", images="[]")]
    conn.on("WHERE task_id = $1 AND enriched_at IS NULL AND status IN", rows)
    conn.on("COALESCE(SUM(jsonb_array_length(images)), 0)", 0)
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND enriched_at IS NULL", 0)
    home = (f'<html><head><meta property="og:image" content="https://www.parkwest.test/p.jpg"></head>'
            f'<body><iframe src="{EMBED}"></body></html>').encode()
    fetch, _ = _web({SITE: home, EMBED: EMBED_PAGE, API: _sightmap()})
    started, both = [], asyncio.Event()

    async def rehost(images, **kw):
        started.append(kw["prefix"].rsplit("/", 1)[1])
        if len(started) == 2:
            both.set()
        await asyncio.wait_for(both.wait(), 2)  # each finishes only once the other has started
        return [{"url": "https://cdn.test/x.webp"}], []

    await phases.enrich(task_row(), _deps(page_fetch=fetch, rehost=AsyncMock(side_effect=rehost)), _guard())
    assert {"photos", "plans"} <= set(started)


@pytest.mark.asyncio
async def test_photos_stop_when_the_batchs_time_for_them_is_up(conn, monkeypatch):
    rows = [item_row(id=uuid4(), url=f"https://apts.test/{n}", fields="{}", status="candidate", images="[]")
            for n in range(2)]
    conn.on("WHERE task_id = $1 AND enriched_at IS NULL AND status IN", rows)
    conn.on("COALESCE(SUM(jsonb_array_length(images)), 0)", 0)
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND enriched_at IS NULL", 0)
    monkeypatch.setattr(phases, "IMAGE_SECONDS", 0)
    page = b'<html><head><meta property="og:image" content="https://apts.test/p.jpg"></head><body>1 bd</body></html>'
    rehost = AsyncMock(return_value=([], []))
    await phases.enrich(task_row(), _deps(page_fetch=AsyncMock(side_effect=lambda url, **_: _fetched(page, final=url)),
                                          rehost=rehost), _guard())
    rehost.assert_not_awaited()


def test_floor_plans_are_ordered_by_fit_then_rent_and_kept_once():
    homes = [{"id": "1", "rent": 2000.0, "beds": 1.0, "plan_source": "p1"},
             {"id": "2", "rent": 2500.0, "beds": 2.0, "plan_source": "p2"},
             {"id": "3", "rent": 2600.0, "beds": 2.0, "plan_source": "p2"},
             {"id": "4", "rent": 2700.0, "beds": 1.0, "plan_source": None}]
    assert phases.plan_order(homes, {"constraints": [TWO_BEDS]}) == ["p2", "p1"]
    assert phases.plan_order(homes, {}) == ["p1", "p2"]


@pytest.mark.asyncio
async def test_rehosting_floor_plans_stops_in_time_and_survives_a_failure(monkeypatch):
    units = [{"id": "1", "rent": 1.0, "plan_source": PLAN_A}, {"id": "2", "rent": 2.0, "plan_source": PLAN_B}]
    rehost = AsyncMock(side_effect=[RuntimeError("s3 down"), ([{"url": "https://cdn.test/b.webp"}], [])])
    monkeypatch.setattr(phases, "PLAN_IMAGE_CONCURRENCY", 1)
    [copied] = await phases.rehost_plans([units], {}, _deps(rehost=rehost), prefix="p", seconds=10)
    assert [u["plan_image"] for u in copied] == [None, "https://cdn.test/b.webp"]
    rehost = AsyncMock()
    [late] = await phases.rehost_plans([units], {}, _deps(rehost=rehost), prefix="p", seconds=0)
    rehost.assert_not_awaited()
    assert late[0]["plan_image"] is None and late[0]["plan_source"] == PLAN_A
    # PLAN_IMAGES new ones a building a pass; ones already copied are reused.
    monkeypatch.setattr(phases, "PLAN_IMAGES", 1)
    rehost = AsyncMock(return_value=([{"url": "https://cdn.test/new.webp"}], []))
    [some] = await phases.rehost_plans([units], {}, _deps(rehost=rehost), prefix="p", seconds=10,
                                       copies={PLAN_A: "https://cdn.test/a.webp"})
    assert [u["plan_image"] for u in some] == ["https://cdn.test/a.webp", "https://cdn.test/new.webp"]


@pytest.fixture
def items_conn(monkeypatch):
    c = FakeConn()
    monkeypatch.setattr(phases, "connection_or_direct", connection(c))
    return c


@pytest.mark.asyncio
async def test_a_refine_copies_the_floor_plans_of_homes_that_fit_only_now(items_conn):
    copied = {**HOMES[0], "plan_source": PLAN_A, "plan_image": "https://cdn.test/a.webp"}
    waiting = {**HOMES[1], "plan_source": PLAN_B, "plan_image": None}
    item_id = uuid4()
    items_conn.on("SELECT id, units FROM mw_agent_task_items", [{"id": item_id, "units": json.dumps([copied, waiting])}])
    rehost = AsyncMock(return_value=([{"url": "https://cdn.test/b.webp"}], []))
    plan = {"constraints": [{"field": "beds", "op": "lte", "value": 0}]}  # a studio now: home b fits
    await phases.fill_plans(task_row(), plan, _deps(rehost=rehost), _guard())
    assert [c.args[0][0]["source_url"] for c in rehost.await_args_list] == [PLAN_B]
    [write] = items_conn.ran("SET units = $3::jsonb")
    assert [u["plan_image"] for u in json.loads(write[2][2])] == ["https://cdn.test/a.webp", "https://cdn.test/b.webp"]
    # Every plan copied already: nothing to do.
    items_conn.on("SELECT id, units FROM mw_agent_task_items", [{"id": item_id, "units": json.dumps([copied])}])
    rehost.reset_mock()
    await phases.fill_plans(task_row(), plan, _deps(rehost=rehost), _guard())
    rehost.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_viewed_pages_screenshot_is_kept_apart_from_the_photos(conn):
    row = item_row(id=uuid4(), origin="provider", url=SITE, fields="{}", status="candidate",
                   images=json.dumps([{"url": "https://cdn.test/old.webp"}]))
    conn.on("WHERE task_id = $1 AND enriched_at IS NULL AND status IN", [row])
    conn.on("COALESCE(SUM(jsonb_array_length(images)), 0)", 1)
    conn.on("COUNT(*) FROM mw_agent_task_items WHERE task_id = $1 AND enriched_at IS NULL", 0)
    thin = b"<html><body>Loading</body></html>"
    fetch, _ = _web({SITE: thin})
    view = AsyncMock(return_value={"url": SITE, "text": "A1 $1,800 - $1,900 /mo",
                                   "screenshot_url": "https://cdn.test/shot.webp"})
    deps = _deps(page_fetch=fetch, view=view, browser_ready=lambda: True, rehost=AsyncMock(return_value=([], [])))
    await phases.enrich(task_row(), deps, _guard())
    [save] = conn.ran("enriched_at = NOW(), updated_at = NOW()")
    assert save[2][6] is None  # its photos are untouched: a screenshot never counts as one
    assert json.loads(save[2][8]) == [{"url": "https://cdn.test/shot.webp", "page_url": SITE,
                                       "alt": "Its page as it looked"}]
    assert save[2][7] is None  # no homes found: the stored ones are left as they are
    assert items_mod.item_summary(item_row(screenshots=save[2][8]))["screenshots"][0]["url"] == \
        "https://cdn.test/shot.webp"


def test_a_document_lists_a_buildings_homes_that_fit_first():
    from app.matcha.services.matcha_work.agent_tasks import document

    homes = [{**HOMES[1], "number": "B1", "url": "https://bldg.test/apartment/B1/"},
             {**HOMES[0], "number": "A1", "tour_url": TOUR, "url": None}]
    row = item_row(url=SITE, units=json.dumps(homes), rank_explain=json.dumps({"units_fit": ["a"]}))
    _, md = document.render(task_row(), [row], today=TODAY)
    assert "- Homes to let: 2 listed, 1 meet every limit" in md
    first, second = [line for line in md.splitlines() if line.startswith("  - ")]
    assert first.startswith("  - \\#A1") and f"[tour]({TOUR})" in first and "its page" not in first
    assert "[its page](https://bldg.test/apartment/B1/)" in second
    # Not ranked yet: no count of what fits.
    _, md = document.render(task_row(), [item_row(units=json.dumps(homes))], today=TODAY)
    assert "- Homes to let: 2 listed\n" in md
