"""What each search API has left (core/services/api_quotas.py). No network:
the account APIs answer through MockTransport; no database: Brave's saved
snapshot comes from a fake connection."""
import json

import httpx
import pytest

from app.core.services import api_quotas


@pytest.fixture
def keys(monkeypatch):
    given = {"brave_search_api_key": "brave-key", "serp_api_key": "serp-secret",
             "search_api_key": "search-secret", "google_maps_api_key": "maps-key"}
    monkeypatch.setattr(api_quotas, "_key", lambda name: given.get(name))
    return given


class Conn:
    def __init__(self, value):
        self.value = value
        self.asked = []

    async def fetchval(self, query, *args):
        self.asked.append((query, args))
        return self.value


def _transport(routes):
    seen = []

    def handler(request):
        seen.append(request)
        answer = routes[request.url.host]
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.MockTransport(handler), seen


@pytest.mark.asyncio
async def test_brave_reads_the_latest_snapshot(keys):
    conn = Conn(json.dumps({"limit": 2000, "remaining": 1500, "resets_at": "2026-11-01T00:00:00+00:00",
                            "observed_at": "2026-10-16T12:00:00+00:00", "window_seconds": 2678400}))
    card = await api_quotas.brave(conn)
    assert conn.asked[0][1] == ("api_quota.brave",)
    assert card["configured"] and card["source"] == "headers"
    assert (card["limit"], card["remaining"], card["used"]) == (2000, 1500, 500)
    assert card["resets_at"].startswith("2026-11-01") and card["observed_at"].startswith("2026-10-16")
    assert "$5 per 1,000" in card["note"] and "BRAVE_SEARCH_USD_PER_1000" in card["note"]


@pytest.mark.asyncio
async def test_brave_on_the_free_plan_is_counted_at_nothing(keys, monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_USD_PER_1000", "0")
    card = await api_quotas.brave(Conn(None))
    assert "$0 a search" in card["note"]


@pytest.mark.asyncio
async def test_brave_before_any_search_says_so(keys):
    card = await api_quotas.brave(Conn(None))
    assert card["remaining"] is None and "after the next search" in card["note"]
    # asyncpg hands jsonb back as text unless a codec is set; a dict works too.
    card = await api_quotas.brave(Conn({"limit": 10, "remaining": 10.0, "resets_at": 5}))
    assert card["limit"] == 10 and card["remaining"] == 10 and card["resets_at"] is None


@pytest.mark.asyncio
async def test_serpapi_from_its_account_api(keys):
    transport, seen = _transport({"serpapi.com": httpx.Response(200, json={
        "api_key": "serp-secret", "account_email": "someone@example.com", "plan_name": "Developer Plan",
        "plan_monthly_price": 75.0, "searches_per_month": 5000, "plan_searches_left": 4000,
        "extra_credits": 20, "total_searches_left": 4020, "this_month_usage": 1000,
        "plan_renewal_date": "2026-11-16",
    })})
    card = await api_quotas.serpapi(transport=transport)
    assert seen[0].url.params["api_key"] == "serp-secret"
    assert card["plan"] == "Developer Plan" and card["monthly_price"] == 75.0
    assert (card["limit"], card["remaining"], card["used"], card["extra_credits"]) == (5000, 4020, 1000, 20)
    assert card["resets_at"] == "2026-11-16" and card["error"] is None
    # Nothing about the account but its quota is passed on.
    assert "serp-secret" not in json.dumps(card) and "someone@example.com" not in json.dumps(card)


@pytest.mark.asyncio
async def test_serpapi_without_a_total_uses_the_plans_left(keys):
    transport, _ = _transport({"serpapi.com": httpx.Response(200, json={"plan_searches_left": 7})})
    assert (await api_quotas.serpapi(transport=transport))["remaining"] == 7


@pytest.mark.asyncio
async def test_searchapi_from_its_me_endpoint(keys):
    transport, seen = _transport({"www.searchapi.io": httpx.Response(200, json={
        "account": {"current_month_usage": 60, "monthly_allowance": 100, "remaining_credits": 40},
        "api_usage": {"searches_this_hour": 1, "hourly_rate_limit": 100},
        "subscription": {"period_start": "2026-10-01", "period_end": "2026-11-01"},
    })})
    card = await api_quotas.searchapi(transport=transport)
    assert seen[0].url.path == "/api/v1/me" and seen[0].headers["Authorization"] == "Bearer search-secret"
    assert (card["limit"], card["remaining"], card["used"]) == (100, 40, 60)
    assert card["resets_at"] == "2026-11-01" and card["note"] is None


@pytest.mark.asyncio
async def test_searchapi_with_no_subscription_notes_it(keys):
    transport, _ = _transport({"www.searchapi.io": httpx.Response(200, json={
        "account": {"current_month_usage": 100, "monthly_allowance": 100, "remaining_credits": 0}})})
    card = await api_quotas.searchapi(transport=transport)
    assert card["remaining"] == 0 and card["note"] == "No active subscription reported."


@pytest.mark.asyncio
@pytest.mark.parametrize("answer,why", [
    (httpx.Response(401, json={"error": "Invalid API key serp-secret"}), "answered 401"),
    (httpx.Response(200, text="<html>"), "something other than JSON"),
    (httpx.Response(200, json=[1, 2]), "unexpected shape"),
    (httpx.ConnectError("https://serpapi.com/account.json?api_key=serp-secret"), "ConnectError"),
])
async def test_a_failed_account_call_says_why_without_the_key(keys, answer, why):
    transport, _ = _transport({"serpapi.com": answer, "www.searchapi.io": answer})
    for ask in (api_quotas.serpapi, api_quotas.searchapi):
        card = await ask(transport=transport)
        assert card["configured"] and why in card["error"] and card["remaining"] is None
        assert "secret" not in json.dumps(card)


@pytest.mark.asyncio
async def test_unconfigured_apis_are_not_asked(monkeypatch):
    monkeypatch.setattr(api_quotas, "_key", lambda name: None)
    transport, seen = _transport({})
    cards = await api_quotas.all_quotas(await api_quotas.brave(Conn(None)), transport=transport)
    assert seen == []
    assert [c["provider"] for c in cards] == ["brave", "searchapi", "serpapi", "google_places"]
    assert not any(c["configured"] for c in cards)
    assert "Enterprise" in cards[3]["note"] and "$35" in cards[3]["note"]


def test_key_reads_settings(monkeypatch):
    class Settings:
        serp_api_key = "k"
        search_api_key = ""

    monkeypatch.setattr(api_quotas, "_settings", lambda: Settings())
    assert api_quotas._key("serp_api_key") == "k"
    assert api_quotas._key("search_api_key") is None and api_quotas._key("missing") is None
    monkeypatch.setattr(api_quotas, "_settings", lambda: None)
    assert api_quotas._key("serp_api_key") is None


def test_settings_not_loaded_is_none(monkeypatch):
    import app.config as config

    def boom():
        raise RuntimeError("not loaded")

    monkeypatch.setattr(config, "get_settings", boom)
    assert api_quotas._settings() is None


def test_numbers_are_checked():
    assert api_quotas._int(True) is None and api_quotas._int(3.0) == 3 and api_quotas._int(3.5) is None
    assert api_quotas._number(False) is None and api_quotas._number(2) == 2.0
    assert api_quotas._text("") is None and api_quotas._text("x" * 200) == "x" * 100
