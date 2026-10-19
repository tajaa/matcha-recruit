"""Paid search APIs and Claude's hosted searches in the AI usage ledger, and
the quota Brave reports. No DB: `_insert_row` and `_save_quota` are patched.

Run from server/:  ./venv/bin/python -m pytest tests/core/test_api_usage.py -q
"""
from datetime import datetime

import httpx
import pytest

from app.core.services import ai_usage
from app.matcha.services.matcha_work import brave_search, search_apis

from .test_ai_usage import _call_feature_label_from


@pytest.fixture
def rows(monkeypatch):
    got = []

    async def fake_insert(row, *, direct=False):
        got.append(row)

    monkeypatch.setattr(ai_usage, "_insert_row", fake_insert)
    return got


@pytest.fixture
def quotas(monkeypatch):
    got = []

    async def fake_save(key, value):
        got.append((key, value))

    monkeypatch.setattr(ai_usage, "_save_quota", fake_save)
    return got


async def _no_sleep(_seconds):
    return None


# --- pricing ------------------------------------------------------------------

def test_a_request_is_priced_when_it_answered_and_free_when_it_failed():
    assert ai_usage.api_cost("brave", "web_search", "ok") == pytest.approx(0.005)
    assert ai_usage.api_cost("brave", "web_search", "error") == 0.0
    assert ai_usage.api_cost("google_places", "text_search_enterprise", "ok") == pytest.approx(0.035)
    assert ai_usage.api_cost("google_places", "text_search_pro", "ok") == pytest.approx(0.032)
    # Monthly plans have no per-request price: unknown, never a made-up rate.
    assert ai_usage.api_cost("serpapi", "google_jobs", "ok") is None
    assert ai_usage.api_cost("searchapi", "google_shopping", "error") is None


@pytest.mark.parametrize("given,each", [("0", 0.0), ("3", 0.003), (" 5.5 ", 0.0055), ("", 0.005),
                                         ("cheap", 0.005), ("-1", 0.005)])
def test_brave_is_priced_for_the_accounts_plan(monkeypatch, given, each):
    monkeypatch.setenv(ai_usage.BRAVE_PRICE_ENV, given)
    assert ai_usage.api_price("brave", "web_search") == pytest.approx(each)
    assert ai_usage.api_cost("brave", "web_search", "ok") == pytest.approx(each)
    # Only Brave's price moves.
    assert ai_usage.api_price("google_places", "text_search_pro") == pytest.approx(0.032)


def test_a_transport_module_is_not_the_feature():
    for module in ("app.matcha.services.matcha_work.search_apis",
                   "app.matcha.services.matcha_work.brave_search"):
        assert _call_feature_label_from(module) == "unknown"
    assert _call_feature_label_from("app.matcha.services.matcha_work.job_search.boards") == "matcha.job_search"


@pytest.mark.asyncio
async def test_record_api_call_writes_one_priced_row(rows):
    with ai_usage.feature_scope("matcha.espresso.assistant"):
        await ai_usage.record_api_call(provider="brave", model="web_search", method="search",
                                       latency_ms=812, status="ok")
        await ai_usage.record_api_call(provider="serpapi", model="google_jobs", method="search",
                                       latency_ms=90, status="weird", error="x" * 900)
    brave, serp = rows
    assert brave["provider"] == "brave" and brave["model"] == "web_search" and brave["method"] == "search"
    assert brave["feature"] == "matcha.espresso.assistant" and brave["latency_ms"] == 812
    assert brave["status"] == "ok" and brave["cost_usd"] == pytest.approx(0.005)
    assert brave["input_tokens"] is None and brave["output_tokens"] is None
    # An unknown status is an error; the error text is capped like any row's.
    assert serp["status"] == "error" and serp["cost_usd"] is None and len(serp["error"]) == 500


@pytest.mark.asyncio
async def test_nothing_is_recorded_when_logging_is_off(rows, quotas, monkeypatch):
    monkeypatch.setattr(ai_usage, "LOGGING_ENABLED", False)
    await ai_usage.record_api_call(provider="brave", model="web_search", method="search",
                                   latency_ms=1, status="ok")
    await ai_usage.save_api_quota("brave", limit=1, remaining=1, reset_seconds=1)
    assert rows == [] and quotas == []


# --- Claude's hosted searches -------------------------------------------------

@pytest.mark.asyncio
async def test_each_hosted_search_claude_reports_is_its_own_priced_row(rows):
    with ai_usage.feature_scope("matcha.espresso.tasks.research"):
        await ai_usage.record_anthropic_response(
            model="claude-haiku-5-5", latency_ms=900,
            message={"id": "msg_1", "model": "claude-haiku-5-5", "stop_reason": "end_turn",
                     "usage": {"input_tokens": 100, "output_tokens": 20,
                               "server_tool_use": {"web_search_requests": 2}}},
        )
    message, *searches = rows
    assert message["model"] == "claude-haiku-5-5" and message["method"] == "messages.create"
    assert len(searches) == 2
    for row in searches:
        assert (row["provider"], row["model"], row["method"]) == ("anthropic", "web_search", "server_tool_use")
        assert row["feature"] == "matcha.espresso.tasks.research"
        assert row["cost_usd"] == pytest.approx(0.01) and row["latency_ms"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("server_tool_use", [None, {}, {"web_search_requests": 0}, {"web_search_requests": "3"}])
async def test_a_message_without_hosted_searches_is_one_row(rows, server_tool_use):
    usage = {"input_tokens": 1, "output_tokens": 1}
    if server_tool_use is not None:
        usage["server_tool_use"] = server_tool_use
    await ai_usage.record_anthropic_response(model="claude-haiku-5-5", latency_ms=1, message={"usage": usage})
    assert len(rows) == 1


# --- the saved quota ----------------------------------------------------------

@pytest.mark.asyncio
async def test_save_api_quota_keeps_the_latest_snapshot(quotas):
    await ai_usage.save_api_quota("brave", limit=2000, remaining=1500, reset_seconds=3600, window_seconds=2678400)
    await ai_usage.save_api_quota("brave", limit=None, remaining=None, reset_seconds=None)
    (key, value), (_, empty) = quotas
    assert key == "api_quota.brave"
    assert value["limit"] == 2000 and value["remaining"] == 1500 and value["window_seconds"] == 2678400
    observed = datetime.fromisoformat(value["observed_at"])
    resets = datetime.fromisoformat(value["resets_at"])
    assert 3599 <= (resets - observed).total_seconds() <= 3601
    assert empty["resets_at"] is None and empty["observed_at"]


@pytest.mark.asyncio
async def test_a_failed_quota_save_never_raises(monkeypatch):
    monkeypatch.undo()  # the real _save_quota, over a database that fails

    class Broken:
        async def __aenter__(self):
            raise OSError("no database")

        async def __aexit__(self, *exc):
            return False

    import app.database as database

    monkeypatch.setattr(database, "connection_or_direct", lambda **_k: Broken())
    await ai_usage._save_quota("api_quota.brave", {"limit": 1})


@pytest.mark.asyncio
async def test_save_quota_upserts_the_key(monkeypatch):
    monkeypatch.undo()
    ran = []

    class Conn:
        async def execute(self, query, *args):
            ran.append((" ".join(query.split()), args))

    class Ctx:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *exc):
            return False

    import app.database as database

    monkeypatch.setattr(database, "connection_or_direct", lambda **_k: Ctx())
    await ai_usage._save_quota("api_quota.brave", {"limit": 1})
    [(query, args)] = ran
    assert query.startswith("INSERT INTO platform_settings") and "ON CONFLICT (key) DO UPDATE" in query
    assert args == ("api_quota.brave", '{"limit": 1}')


# --- search_apis.answer meters every call ------------------------------------

def _api(*responses):
    queue = list(responses)

    def handler(request):
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_an_answered_search_is_one_ok_row(rows):
    transport = _api(httpx.Response(200, json={"jobs": []}))
    with ai_usage.feature_scope("matcha.espresso.job_search"):
        body = await search_apis.answer(
            "SearchAPI", lambda client: client.get("https://api.example/search"),
            transport=transport, sleep=_no_sleep, sku="google_jobs",
        )
    assert body == {"jobs": []}
    [row] = rows
    assert (row["provider"], row["model"], row["method"]) == ("searchapi", "google_jobs", "search")
    assert row["status"] == "ok" and row["error"] is None and row["cost_usd"] is None
    assert row["feature"] == "matcha.espresso.job_search" and row["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_a_retried_then_answered_search_is_still_one_row(rows):
    transport = _api(httpx.Response(503), httpx.Response(200, json={}))
    await search_apis.answer("Google Places", lambda client: client.get("https://api.example/p"),
                             transport=transport, sleep=_no_sleep, sku="text_search_enterprise")
    [row] = rows
    assert row["provider"] == "google_places" and row["cost_usd"] == pytest.approx(0.035)


@pytest.mark.asyncio
async def test_a_refused_search_is_an_error_row_with_why(rows):
    transport = _api(httpx.Response(401, json={"error": "Invalid API key"}))
    with pytest.raises(search_apis.ProviderError):
        await search_apis.answer("SerpApi", lambda client: client.get("https://api.example/s"),
                                 transport=transport, sleep=_no_sleep, sku="google_shopping")
    [row] = rows
    assert row["status"] == "error" and "refused the API key" in row["error"]
    assert row["provider"] == "serpapi" and row["model"] == "google_shopping"


@pytest.mark.asyncio
async def test_a_send_that_stops_is_an_error_row_and_no_sku_is_a_request(rows):
    class Stop(Exception):
        pass

    async def send(_client):
        raise Stop()

    with pytest.raises(Stop):
        await search_apis.answer("Brave", send, transport=_api(), sleep=_no_sleep)
    [row] = rows
    assert row["status"] == "error" and row["error"] == "Stop" and row["model"] == "request"


@pytest.mark.asyncio
async def test_a_cancelled_search_is_a_timeout_row(rows):
    import asyncio

    async def send(_client):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await search_apis.answer("Brave", send, transport=_api(), sleep=_no_sleep, sku="web_search")
    [row] = rows
    assert row["status"] == "timeout" and row["cost_usd"] == 0.0


def test_provider_ids():
    assert search_apis.provider_id("Google Places") == "google_places"
    assert search_apis.provider_id("SerpApi") == "serpapi"


# --- Brave's quota ------------------------------------------------------------

def _headers(**values):
    return httpx.Headers({f"x-ratelimit-{k}": v for k, v in values.items()})


def test_quota_is_the_longest_day_or_longer_window():
    found = brave_search.quota(_headers(
        policy="1;w=1, 2000;w=2678400", limit="1, 2000", remaining="0, 1834", reset="1, 86400",
    ))
    assert found == {"limit": 2000, "remaining": 1834, "window_seconds": 2678400, "reset_seconds": 86400}
    # Two long windows: the month, not the day.
    found = brave_search.quota(_headers(
        policy="1;w=1, 500;w=86400, 9000;w=2592000", limit="1, 500, 9000", remaining="1, 20, 8000",
        reset="1, 10, 99",
    ))
    assert found["limit"] == 9000 and found["remaining"] == 8000 and found["reset_seconds"] == 99


@pytest.mark.parametrize("headers", [
    {},
    {"policy": "1;w=1", "limit": "1", "remaining": "0", "reset": "1"},
    {"policy": "garbage"},
])
def test_no_quota_without_a_long_window(headers):
    assert brave_search.quota(_headers(**headers)) is None


def test_a_missing_part_is_unknown_not_shifted():
    found = brave_search.quota(_headers(policy="1;w=1, 2000;w=2678400", limit="1, 2000", remaining="1"))
    assert found == {"limit": 2000, "remaining": None, "window_seconds": 2678400, "reset_seconds": None}


@pytest.fixture
def keyed_brave(monkeypatch):
    monkeypatch.setattr(brave_search, "_key", lambda: "brave-key")
    brave_search.reset()
    yield
    brave_search.reset()


MONTH = {"x-ratelimit-policy": "1;w=1, 2000;w=2678400", "x-ratelimit-limit": "1, 2000",
         "x-ratelimit-remaining": "0, 1999", "x-ratelimit-reset": "1, 3600"}


@pytest.mark.asyncio
async def test_a_brave_search_saves_its_quota_and_meters_the_request(keyed_brave, rows, quotas):
    transport = _api(httpx.Response(200, json={"web": {"results": []}}, headers=MONTH))
    assert await brave_search.search("q", transport=transport, sleep=_no_sleep) == []
    [row] = rows
    assert (row["provider"], row["model"], row["cost_usd"]) == ("brave", "web_search", pytest.approx(0.005))
    [(key, value)] = quotas
    assert key == "api_quota.brave" and value["limit"] == 2000 and value["remaining"] == 1999


@pytest.mark.asyncio
async def test_a_spent_brave_quota_is_saved_too(keyed_brave, rows, quotas):
    spent = {**MONTH, "x-ratelimit-remaining": "1, 0"}
    transport = _api(httpx.Response(429, json={}, headers=spent))
    out = None
    try:
        await brave_search.search("q", transport=transport, sleep=_no_sleep)
    except brave_search.Unavailable as exc:
        out = exc
    assert out is not None and out.out
    [(_, value)] = quotas
    assert value["remaining"] == 0
    assert rows[0]["status"] == "error" and rows[0]["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_a_brave_answer_without_a_monthly_window_saves_nothing(keyed_brave, rows, quotas):
    transport = _api(httpx.Response(200, json={"web": {"results": []}}, headers={"x-ratelimit-policy": "1;w=1"}))
    await brave_search.search("q", transport=transport, sleep=_no_sleep)
    assert quotas == [] and len(rows) == 1
