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
        "court_id": "ca9",
        "dateFiled": "2020-01-01",
        "opinions": [{"snippet": "the court held..."}],
        "meta": {"score": {"bm25": 33.5}},
    }]}
    out = lr._parse_search_results(payload)
    assert len(out) == 1
    c = out[0]
    assert c["id"] == "12345"
    assert c["case_name"] == "Doe v. Acme"
    assert c["citation"] == "123 F.3d 456"
    assert c["court"] == "9th Cir."
    assert c["court_id"] == "ca9"
    assert c["date_filed"] == "2020-01-01"
    assert c["url"] == "https://www.courtlistener.com/opinion/12345/doe-v-acme/"
    assert c["snippet"] == "the court held..."
    assert c["score"] == 33.5


def test_parse_search_results_tolerates_missing_keys():
    assert lr._parse_search_results({"results": [{}]}) == []
    assert lr._parse_search_results({}) == []
    assert lr._parse_search_results(None) == []
    # missing case name / cluster id individually
    assert lr._parse_search_results({"results": [{"cluster_id": 1}]}) == []
    assert lr._parse_search_results({"results": [{"caseName": "X"}]}) == []


def test_parse_search_results_parses_whole_page_not_just_max_cases():
    # the relevance floor + cap run afterwards in _filter_rank; truncating here
    # would discard candidates that outrank the ones kept
    payload = {"results": [
        {"cluster_id": i, "caseName": f"Case {i}"} for i in range(1, 21)
    ]}
    assert len(lr._parse_search_results(payload)) == 20
    assert len(lr._parse_search_results(payload, limit=3)) == 3


def test_bm25_extracts_score_and_tolerates_junk():
    assert lr._bm25({"meta": {"score": {"bm25": 12.5}}}) == 12.5
    assert lr._bm25({"meta": {"score": {"bm25": 7}}}) == 7.0
    # absent / malformed at each level -> unscored, never a crash
    assert lr._bm25({}) is None
    assert lr._bm25({"meta": None}) is None
    assert lr._bm25({"meta": {"score": None}}) is None
    assert lr._bm25({"meta": {"score": {"bm25": "high"}}}) is None
    # bool is an int subclass — must not read as a score
    assert lr._bm25({"meta": {"score": {"bm25": True}}}) is None


# --- relevance floor + dedupe -------------------------------------------------

def _case(cid, score=None, name=None, date=None):
    return {"id": str(cid), "case_name": name or f"Case {cid}",
            "date_filed": date, "score": score}


def test_filter_rank_drops_hits_below_relative_floor():
    # reference = median(100, 90, 80) = 90 -> floor 31.5; the 5.0 tail is cut
    out = lr._filter_rank([_case(1, 100.0), _case(2, 90.0), _case(3, 80.0), _case(4, 5.0)])
    assert [c["id"] for c in out] == ["1", "2", "3"]


def test_filter_rank_floor_is_relative_not_absolute():
    # same shape at a totally different BM25 scale must keep the same rows —
    # scores are query-scale dependent (live probe: top 40.7 vs top 7.5)
    out = lr._filter_rank([_case(1, 10.0), _case(2, 9.0), _case(3, 8.0), _case(4, 0.5)])
    assert [c["id"] for c in out] == ["1", "2", "3"]


def test_filter_rank_reference_survives_a_caption_match_outlier():
    # live probe: '"class action" ...' scored "In re NJOY Consumer Class Action
    # Litigation" at 192.9 against a ~30 field because the query terms sit in
    # the caption. A top-anchored floor (0.35*192.9=67.5) discarded all seven
    # genuine hits; the median of the top 3 ignores the spike.
    out = lr._filter_rank([
        _case(1, 192.9), _case(2, 30.0), _case(3, 29.0), _case(4, 28.0), _case(5, 27.0),
    ])
    assert [c["id"] for c in out] == ["1", "2", "3", "4", "5"]


def test_filter_rank_uses_top_score_when_sample_too_small_to_spot_an_outlier():
    # fewer than 3 scores: a spike is indistinguishable from a strong field,
    # so the top score stays the reference and the weak row is still cut
    out = lr._filter_rank([_case(1, 100.0), _case(2, 1.0)])
    assert [c["id"] for c in out] == ["1"]
    assert [c["id"] for c in lr._filter_rank([_case(1, 100.0)])] == ["1"]


def test_filter_rank_dedupes_by_cluster_id_and_by_name_date():
    out = lr._filter_rank([
        _case(1, 10.0, name="Martel v. HG Staffing", date="2022-09-08"),
        _case(1, 10.0, name="Martel v. HG Staffing", date="2022-09-08"),   # same cluster id
        _case(2, 9.0, name="Martel v. HG Staffing", date="2022-09-08"),    # sibling cluster, same opinion
        _case(3, 9.0, name="Boucher v. Shaw", date="2008-11-26"),
    ])
    assert [c["id"] for c in out] == ["1", "3"]


def test_filter_rank_keeps_unscored_rows_and_sorts_them_last():
    out = lr._filter_rank([_case(1, None), _case(2, 100.0), _case(3, 90.0)])
    assert [c["id"] for c in out] == ["2", "3", "1"]


def test_filter_rank_all_unscored_preserves_api_order():
    out = lr._filter_rank([_case(3), _case(1), _case(2)])
    assert [c["id"] for c in out] == ["3", "1", "2"]


def test_filter_rank_caps_at_max_cases():
    out = lr._filter_rank([_case(i, 100.0) for i in range(20)])
    assert len(out) == lr._MAX_CASES


def test_filter_rank_empty():
    assert lr._filter_rank([]) == []


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


def _capture_search(monkeypatch, payload=None):
    """Run search_case_law against a fake httpx client; return the captured
    request params."""
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return payload or {}

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
    return captured


def test_search_case_law_sanitizes_query_before_request(monkeypatch):
    captured = _capture_search(monkeypatch)
    asyncio.run(lr.search_case_law("meal/rest breaks"))
    assert captured["params"]["q"] == "meal rest breaks"


def test_search_case_law_trusted_query_keeps_operators(monkeypatch):
    # curated _MATTER_TYPE_TERMS rely on quotes, parens and OR/AND reaching the
    # parser intact — _sanitize_query would strip every one of them
    term = lr._MATTER_TYPE_TERMS["class_action"]
    captured = _capture_search(monkeypatch)
    asyncio.run(lr.search_case_law(term, sanitize=False))
    assert captured["params"]["q"] == term
    assert lr._sanitize_query(term) != term  # ...which is why sanitize=False matters


def test_search_case_law_filters_by_court_and_omits_state_name(monkeypatch):
    # the bug: "Nevada" as a free-text AND term matched party names, returning
    # a Texas case captioned "Nevada v. U.S. Dep't of Labor"
    captured = _capture_search(monkeypatch)
    asyncio.run(lr.search_case_law("overtime wages", state="NV"))
    assert captured["params"]["court"] == "nev nevapp nvd ca9"
    assert "Nevada" not in captured["params"]["q"]
    assert captured["params"]["q"] == "overtime wages"


def test_search_case_law_accepts_lowercase_state(monkeypatch):
    captured = _capture_search(monkeypatch)
    asyncio.run(lr.search_case_law("overtime", state="nv"))
    assert captured["params"]["court"] == "nev nevapp nvd ca9"


def test_search_case_law_no_state_sends_no_court_filter(monkeypatch):
    captured = _capture_search(monkeypatch)
    asyncio.run(lr.search_case_law("overtime"))
    assert "court" not in captured["params"]


def test_search_case_law_unmapped_state_falls_back_to_state_name(monkeypatch):
    # territories / bad data: better to bias the free text than search the
    # entire country with no filter at all
    captured = _capture_search(monkeypatch)
    asyncio.run(lr.search_case_law("overtime", state="PR"))
    assert "court" not in captured["params"]
    assert captured["params"]["q"] == "overtime"


def test_search_case_law_applies_filter_rank(monkeypatch):
    payload = {"results": [
        {"cluster_id": 1, "caseName": "Strong", "meta": {"score": {"bm25": 100.0}}},
        {"cluster_id": 2, "caseName": "Weak", "meta": {"score": {"bm25": 1.0}}},
        {"cluster_id": 1, "caseName": "Strong", "meta": {"score": {"bm25": 100.0}}},
    ]}
    _capture_search(monkeypatch, payload)
    out = asyncio.run(lr.search_case_law("overtime", state="NV"))
    assert [c["case_name"] for c in out] == ["Strong"]


# --- state -> CourtListener court IDs ----------------------------------------

def test_state_courts_covers_every_state_and_dc():
    assert set(lr._STATE_COURTS) == set(lr._STATE_NAMES)
    assert len(lr._STATE_COURTS) == 51


def test_state_courts_every_entry_has_a_federal_circuit():
    circuits = {f"ca{n}" for n in range(1, 12)} | {"cadc"}
    for state, courts in lr._STATE_COURTS.items():
        assert circuits & set(courts), f"{state} has no binding federal circuit"
        assert len(courts) == len(set(courts)), f"{state} has duplicate court ids"


def test_state_courts_never_includes_scotus():
    # binding everywhere, so never jurisdictionally wrong — but it outscores
    # local precedent on generic employment terms and would eat the 8-case cap
    for courts in lr._STATE_COURTS.values():
        assert "scotus" not in courts


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
    async def fake_search(query, state=None, limit=8, sanitize=True):
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
    async def failing_search(query, state=None, limit=8, sanitize=True):
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
    async def failing_search(query, state=None, limit=8, sanitize=True):
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

    async def fake_search(query, state=None, limit=8, sanitize=True):
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
    async def failing_search(query, state=None, limit=8, sanitize=True):
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
    assert ladder[0] == "employees required work off clock meal"   # 6 keywords
    assert ladder[1] == "employees required work"                  # 3 keywords
    assert ladder[2] == lr._MATTER_TYPE_TERMS["class_action"]      # curated concepts
    assert len(ladder) == len(set(ladder))                         # distinct tiers


def test_build_query_ladder_never_emits_the_humanized_enum_label():
    # regression: the old broadest tier was _hum(matter_type), so matter_type
    # 'other' searched q="Other" -> 84,621 hits, top hit a death-penalty case
    for mt in lr._MATTER_TYPE_TERMS:
        ladder = lr.build_query_ladder(mt, "")
        assert ladder == [lr._MATTER_TYPE_TERMS[mt]]
        assert lr._hum(mt) not in ladder
    assert "Other" not in lr.build_query_ladder("other", "")
    assert "Employment matter" not in lr.build_query_ladder(None, None)


def test_build_query_ladder_empty_allegation_is_curated_tier_only():
    assert lr.build_query_ladder("eeoc_charge", "") == [lr._MATTER_TYPE_TERMS["eeoc_charge"]]
    assert lr.build_query_ladder(None, None) == [lr._DEFAULT_MATTER_TERMS]
    # unknown / stale matter_type falls back rather than searching its label
    assert lr.build_query_ladder("bankruptcy", "") == [lr._DEFAULT_MATTER_TERMS]


def test_build_query_ladder_short_allegation_collapses_duplicate_tiers():
    # <=3 keywords: the 6-keyword and 3-keyword tiers are the same string
    ladder = lr.build_query_ladder("audit", "unpaid overtime")
    assert ladder == ["unpaid overtime", lr._MATTER_TYPE_TERMS["audit"]]


def test_matter_type_terms_cover_every_schema_matter_type():
    # legal_matters.matter_type CHECK constraint (migration legaldef01)
    assert set(lr._MATTER_TYPE_TERMS) == {
        "subpoena", "class_action", "eeoc_charge", "single_plaintiff", "audit", "other",
    }


def test_matter_type_terms_are_all_anchored_to_employment():
    # a procedural posture is not a subject: unanchored, the class_action tier
    # returned a consumer vape class action, and subpoena reaches grand-jury
    # practice. Every tier must AND in the employment anchor.
    for mt, term in lr._MATTER_TYPE_TERMS.items():
        assert term.endswith(f"AND {lr._EMPLOYMENT_ANCHOR}"), mt


def test_run_research_broadens_until_cases_found(monkeypatch):
    calls: list[str] = []

    async def fake_search(query, state=None, limit=8, sanitize=True):
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


def test_run_research_sends_ladder_queries_unsanitized(monkeypatch):
    # the curated tier's quotes/OR must survive to CourtListener's parser;
    # ladder tiers are alphabetic keywords or code-authored constants, never
    # raw user text, so sanitizing them is both unnecessary and destructive
    seen = []

    async def fake_search(query, state=None, limit=8, sanitize=True):
        seen.append(sanitize)
        return []

    monkeypatch.setattr(lr, "search_case_law", fake_search)
    conn = _FakeResearchConn()
    _patch_conn(monkeypatch, conn)
    asyncio.run(lr.run_research(_MATTER, created_by=None, include_guidance=False))

    assert seen and all(s is False for s in seen)


def test_run_research_all_tiers_empty_completes_with_empty_cases(monkeypatch):
    calls: list[str] = []

    async def fake_search(query, state=None, limit=8, sanitize=True):
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
