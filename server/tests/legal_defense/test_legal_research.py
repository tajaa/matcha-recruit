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
                "status": "complete", "cases": args[0], "guidance": args[1], "error": args[2],
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
