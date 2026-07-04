"""Unit tests for external legal research — CourtListener result parsing +
run_research orchestration. Fast, no network / no DB (fake conn + monkeypatched
network calls)."""
import asyncio
import json

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
    """Captures UPDATE args and round-trips them through json like asyncpg's
    jsonb columns actually do (str in, str back out) — proves run_research's
    final read matches what real persistence would return."""
    def __init__(self):
        self.updates = []

    async def fetchrow(self, sql, *args):
        if "INSERT INTO legal_matter_research" in sql:
            return {"id": "r1"}
        if "SELECT * FROM legal_matter_research WHERE id" in sql:
            last = self.updates[-1]
            return {
                "id": "r1", "matter_id": "m1", "company_id": "cid",
                "status": last["status"], "query": "q",
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
    result = asyncio.run(lr.run_research(conn, _MATTER, created_by=None))

    assert result["status"] == "complete"
    assert result["cases"] == _CASES
    assert result["guidance"] == _GUIDANCE
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
    result = asyncio.run(lr.run_research(conn, _MATTER, created_by=None))

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
    result = asyncio.run(lr.run_research(conn, _MATTER, created_by=None))

    assert result["status"] == "failed"
    assert result["error"]
