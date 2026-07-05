"""Unit tests for external legal research — CourtListener result parsing +
run_research orchestration. Fast, no network / no DB (fake conn + monkeypatched
network calls)."""
import asyncio
import json
from contextlib import asynccontextmanager

from app.matcha.services import legal_research as lr


# --- CourtListener v4 result parsing ---------------------------------------

def test_parse_search_results_maps_v4_fields():
    payload = {"results": [{
        "cluster_id": 12345,
        "caseName": "Doe v. Acme",
        "absolute_url": "/opinion/12345/doe-v-acme/",
        "citation": ["123 F.3d 456"],
        "court": "9th Cir.",
        "dateFiled": "2020-01-01",
        "opinions": [{"snippet": "the court held..."}],
    }]}
    out = lr._parse_search_results(payload)
    assert len(out) == 1
    c = out[0]
    assert c["id"] == "12345"
    assert c["case_name"] == "Doe v. Acme"
    assert c["citation"] == "123 F.3d 456"
    assert c["court"] == "9th Cir."
    assert c["date_filed"] == "2020-01-01"
    assert c["url"] == "https://www.courtlistener.com/opinion/12345/doe-v-acme/"
    assert c["snippet"] == "the court held..."


def test_parse_search_results_tolerates_missing_keys():
    assert lr._parse_search_results({"results": [{}]}) == []
    assert lr._parse_search_results({}) == []
    assert lr._parse_search_results(None) == []
    # missing case name / cluster id individually
    assert lr._parse_search_results({"results": [{"cluster_id": 1}]}) == []
    assert lr._parse_search_results({"results": [{"caseName": "X"}]}) == []


# --- query sanitization (CourtListener 500s on reserved chars) -------------

def test_sanitize_query_strips_confirmed_crash_chars():
    for ch in "/:[]{}~^":
        assert ch not in lr._sanitize_query(f"foo{ch}bar")


def test_sanitize_query_strips_operator_chars():
    for ch in '()"&|':
        assert ch not in lr._sanitize_query(f"foo{ch}bar")


def test_sanitize_query_preserves_low_risk_chars():
    out = lr._sanitize_query("at-will e-verify? really! co+op x\\y overtime*")
    for ch in "-?!+\\*":
        assert ch in out


def test_sanitize_query_collapses_whitespace():
    assert lr._sanitize_query("  meal   /  rest  ") == "meal rest"


def test_sanitize_query_handles_empty():
    assert lr._sanitize_query("") == ""
    assert lr._sanitize_query(None) == ""


def test_search_case_law_sanitizes_query_before_request(monkeypatch):
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {}

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            captured["params"] = params
            return _FakeResponse()

    class _FakeSettings:
        courtlistener_api_token = None

    monkeypatch.setattr(lr, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(lr.httpx, "AsyncClient", _FakeAsyncClient)
    asyncio.run(lr.search_case_law("meal/rest breaks"))
    assert captured["params"]["q"] == "meal rest breaks"


# --- run_research orchestration ---------------------------------------------

class _FakeResearchConn:
    """Captures the INSERT/UPDATE args and round-trips jsonb the way asyncpg
    actually does (str in, str back out) — proves run_research's final read
    matches what real persistence would return."""
    def __init__(self):
        self.updates = []
        self.insert_args = None

    async def fetchrow(self, sql, *args):
        if "INSERT INTO legal_matter_research" in sql:
            self.insert_args = args
            return {"id": "r1"}
        if "SELECT state FROM business_locations" in sql:
            return None
        if "SELECT * FROM legal_matter_research WHERE id" in sql:
            last = self.updates[-1]
            return {
                "id": "r1", "matter_id": "m1", "company_id": "cid",
                "status": last["status"], "query": "q",
                "jurisdiction_state": self.insert_args[4] if self.insert_args else None,
                "cases": last.get("cases"), "guidance": last.get("guidance"),
                "error": last.get("error"), "created_by": None,
                "created_at": None, "completed_at": None,
            }
        return None

    async def execute(self, sql, *args):
        if "status='failed'" in sql:
            self.updates.append({"status": "failed", "error": args[0]})
        elif "status='complete'" in sql:
            self.updates.append({
                "status": "complete", "cases": args[0], "guidance": args[1],
                "error": args[2], "query": args[3],
            })


def _patch_conn(monkeypatch, conn):
    """run_research acquires its own short-lived connections (so the pool is
    never held across the external calls) — route both acquisitions to the
    same fake."""
    @asynccontextmanager
    async def fake_get_connection(tenant_id=None):
        yield conn

    monkeypatch.setattr(lr, "get_connection", fake_get_connection)


_MATTER = {
    "id": "m1", "company_id": "cid", "matter_type": "class_action",
    "allegation": "Workers allege unpaid overtime.", "jurisdiction_state": "CA",
    "location_id": None,
}
_CASES = [{
    "id": "c1", "case_name": "Doe v. Acme", "citation": None,
    "court": "Ct", "date_filed": None, "url": "https://x", "snippet": None,
}]
_GUIDANCE = {"summary": "sum", "key_authorities": []}


def test_run_research_persists_only_api_rows(monkeypatch):
    async def fake_search(query, state=None, limit=8):
        return _CASES

    async def fake_guidance(matter, juris_display, cases):
        return _GUIDANCE

    monkeypatch.setattr(lr, "search_case_law", fake_search)
    monkeypatch.setattr(lr, "synthesize_guidance", fake_guidance)

    conn = _FakeResearchConn()
    _patch_conn(monkeypatch, conn)
    result = asyncio.run(lr.run_research(_MATTER, created_by=None))

    assert result["status"] == "complete"
    assert result["cases"] == _CASES
    assert result["guidance"] == _GUIDANCE
    # the state the run was grounded in is persisted with the row
    assert conn.insert_args[4] == "CA"
    # persisted cases are exactly the API rows — no fabricated entries mixed in
    complete_update = conn.updates[-1]
    assert json.loads(complete_update["cases"]) == _CASES


def test_run_research_partial_failure_completes(monkeypatch):
    async def failing_search(query, state=None, limit=8):
        raise RuntimeError("courtlistener down")

    async def fake_guidance(matter, juris_display, cases):
        return _GUIDANCE

    monkeypatch.setattr(lr, "search_case_law", failing_search)
    monkeypatch.setattr(lr, "synthesize_guidance", fake_guidance)

    conn = _FakeResearchConn()
    _patch_conn(monkeypatch, conn)
    result = asyncio.run(lr.run_research(_MATTER, created_by=None))

    assert result["status"] == "complete"
    assert result["cases"] == []
    assert result["guidance"] == _GUIDANCE
    assert "unavailable" in (result["error"] or "").lower()


def test_run_research_total_failure_marks_failed(monkeypatch):
    async def failing_search(query, state=None, limit=8):
        raise RuntimeError("courtlistener down")

    async def failing_guidance(matter, juris_display, cases):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(lr, "search_case_law", failing_search)
    monkeypatch.setattr(lr, "synthesize_guidance", failing_guidance)

    conn = _FakeResearchConn()
    _patch_conn(monkeypatch, conn)
    result = asyncio.run(lr.run_research(_MATTER, created_by=None))

    assert result["status"] == "failed"
    assert result["error"]


def test_run_research_skips_guidance_when_disabled(monkeypatch):
    called = {"guidance": False}

    async def fake_search(query, state=None, limit=8):
        return _CASES

    async def fake_guidance(matter, juris_display, cases):
        called["guidance"] = True
        return _GUIDANCE

    monkeypatch.setattr(lr, "search_case_law", fake_search)
    monkeypatch.setattr(lr, "synthesize_guidance", fake_guidance)

    conn = _FakeResearchConn()
    _patch_conn(monkeypatch, conn)
    result = asyncio.run(lr.run_research(_MATTER, created_by=None, include_guidance=False))

    assert called["guidance"] is False
    assert result["status"] == "complete"
    assert result["cases"] == _CASES
    assert result["guidance"] is None
    assert result["error"] is None


def test_run_research_case_failure_marks_failed_when_guidance_skipped(monkeypatch):
    async def failing_search(query, state=None, limit=8):
        raise RuntimeError("courtlistener down")

    async def fake_guidance(matter, juris_display, cases):
        raise AssertionError("guidance must not be attempted when include_guidance=False")

    monkeypatch.setattr(lr, "search_case_law", failing_search)
    monkeypatch.setattr(lr, "synthesize_guidance", fake_guidance)

    conn = _FakeResearchConn()
    _patch_conn(monkeypatch, conn)
    result = asyncio.run(lr.run_research(_MATTER, created_by=None, include_guidance=False))

    # case search is the only thing attempted — its failure is total failure
    assert result["status"] == "failed"
    assert "courtlistener down" in result["error"]


# --- query ladder (empty-result fix) -----------------------------------------

def test_keywords_drop_stopwords_and_digits():
    kws = lr._keywords(
        "our employees were required to work off the clock during 2025 at the facility", 10)
    assert "our" not in kws and "the" not in kws and "were" not in kws
    assert "2025" not in " ".join(kws)  # digit tokens never match opinions
    assert "employees" in kws and "clock" in kws


def test_build_query_ladder_narrow_to_broad_distinct():
    ladder = lr.build_query_ladder(
        "class_action",
        "employees were required to work off the clock during meal breaks and were not paid overtime wages",
    )
    assert len(ladder) == 3
    assert ladder[-1] == "Class Action"                 # broadest = type label alone
    assert all(q.startswith("Class Action") for q in ladder)
    assert len(ladder) == len(set(ladder))              # distinct tiers
    # tiers strictly shrink
    assert len(ladder[0].split()) > len(ladder[1].split()) > len(ladder[2].split())


def test_build_query_ladder_empty_allegation_single_tier():
    assert lr.build_query_ladder("eeoc_charge", "") == ["Eeoc Charge"]
    assert lr.build_query_ladder(None, None) == ["Employment matter"]


def test_run_research_broadens_until_cases_found(monkeypatch):
    calls: list[str] = []

    async def fake_search(query, state=None, limit=8):
        calls.append(query)
        return _CASES if len(calls) == 3 else []   # only the broadest tier hits

    monkeypatch.setattr(lr, "search_case_law", fake_search)

    conn = _FakeResearchConn()
    _patch_conn(monkeypatch, conn)
    result = asyncio.run(lr.run_research(
        {**_MATTER, "allegation": "employees required to work off the clock during meal breaks unpaid overtime"},
        created_by=None, include_guidance=False,
    ))

    assert len(calls) == 3
    assert calls == lr.build_query_ladder("class_action",
        "employees required to work off the clock during meal breaks unpaid overtime")
    assert result["status"] == "complete"
    assert result["cases"] == _CASES
    # the tier that actually matched is persisted with the row
    assert conn.updates[-1]["query"] == calls[-1]


def test_run_research_all_tiers_empty_completes_with_empty_cases(monkeypatch):
    calls: list[str] = []

    async def fake_search(query, state=None, limit=8):
        calls.append(query)
        return []

    monkeypatch.setattr(lr, "search_case_law", fake_search)

    conn = _FakeResearchConn()
    _patch_conn(monkeypatch, conn)
    result = asyncio.run(lr.run_research(_MATTER, created_by=None, include_guidance=False))

    assert len(calls) == len(lr.build_query_ladder("class_action", _MATTER["allegation"]))
    assert result["status"] == "complete"       # ran fine, genuinely nothing matched
    assert result["cases"] == []
    assert result["error"] is None


# --- state precedence --------------------------------------------------------

class _LocStateConn:
    """Location lookup returns a state — and the SQL must be company-scoped."""
    def __init__(self, state):
        self.state = state
        self.seen_sql = None

    async def fetchrow(self, sql, *args):
        self.seen_sql = sql
        return {"state": self.state}


def test_resolve_state_location_wins_over_override():
    # Same precedence as legal_defense.resolve_matter_jurisdiction: the
    # location governs when set, so the CourtListener search can never target
    # a different state than the governing-law chain.
    conn = _LocStateConn("ny")
    matter = {**_MATTER, "location_id": "loc1", "jurisdiction_state": "CA"}
    state = asyncio.run(lr._resolve_state(conn, matter))
    assert state == "NY"
    assert "company_id" in conn.seen_sql  # tenant-scoped lookup


def test_resolve_state_falls_back_to_override():
    conn = _FakeResearchConn()  # business_locations lookup returns None
    matter = {**_MATTER, "location_id": "loc1", "jurisdiction_state": "CA"}
    assert asyncio.run(lr._resolve_state(conn, matter)) == "CA"
