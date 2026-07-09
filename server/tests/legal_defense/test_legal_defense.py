"""Unit tests for the Legal Defense service — pure helpers + gather isolation.

Fast, no DB / no app boot (a fake connection drives gather_evidence). The
citation gate is the security-critical bit: hallucinated IDs must never survive
into a packet.
"""
import asyncio
import io
import zipfile

from app.core.compliance_registry import CATEGORY_KEYS
from app.matcha.services import legal_defense as ld


# --- citation gate (anti-hallucination) ------------------------------------

def test_validate_citations_drops_unknown_ids():
    index = {"incident:a": {}, "er_case:b": {}}
    emap = [
        {"point": "p1", "cited_ids": ["incident:a", "ghost:zzz"]},
        {"point": "p2", "cited_ids": ["er_case:b"]},
    ]
    clean, dropped = ld.validate_citations(emap, index)
    assert dropped == ["ghost:zzz"]
    assert clean[0]["cited_ids"] == ["incident:a"]   # hallucinated id stripped
    assert clean[1]["cited_ids"] == ["er_case:b"]


def test_validate_citations_accepts_new_cid_kinds():
    index = {"law:x": {}, "case:123": {}, "bill:y": {}}
    emap = [{"point": "p", "cited_ids": ["law:x", "case:123", "bill:y", "case:999"]}]
    clean, dropped = ld.validate_citations(emap, index)
    assert dropped == ["case:999"]
    assert clean[0]["cited_ids"] == ["law:x", "case:123", "bill:y"]


def test_validate_citations_tolerates_garbage():
    clean, dropped = ld.validate_citations(["not-a-dict", {"cited_ids": "x"}, {}], {"a": {}})
    # never raises; non-dict skipped, bad shapes coerced
    assert isinstance(clean, list)
    assert dropped == []


def test_cited_ids_dedupes_in_order():
    memo = {"evidence_map": [{"cited_ids": ["x", "y"]}, {"cited_ids": ["x", "z"]}]}
    assert ld._cited_ids(memo) == ["x", "y", "z"]


# --- JSON parse tolerance --------------------------------------------------

def test_parse_json_strips_fences_and_prose():
    assert ld._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ld._parse_json('here you go: {"a": 2} thanks') == {"a": 2}
    assert ld._parse_json("not json at all") == {}
    assert ld._parse_json("") == {}


# --- ZIP bundle ------------------------------------------------------------

def test_build_zip_contains_memo_manifest_and_sources():
    blob = ld._build_zip(
        b"%PDF-1.4 fake",
        [("incidents/1/photo.png", b"img-bytes")],
        ["er-cases/2/doc.pdf (download failed)"],
        {"title": "Doe v. Acme"},
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = set(z.namelist())
        assert "defense-memo.pdf" in names
        assert "manifest.txt" in names
        assert "source-documents/incidents/1/photo.png" in names
        manifest = z.read("manifest.txt").decode()
        assert "COULD NOT BE INCLUDED" in manifest
        assert "er-cases/2/doc.pdf" in manifest


# --- gather_evidence isolation ---------------------------------------------

class _FakeConn:
    """Minimal asyncpg-conn stand-in: raises for one table, returns a row for ER."""
    def __init__(self, fail_substr=None):
        self.fail = fail_substr

    async def fetch(self, sql, *args):
        if self.fail and self.fail in sql:
            raise RuntimeError("simulated source failure")
        if "er_cases" in sql:
            return [{
                "id": "11111111-1111-1111-1111-111111111111",
                "case_number": "ER-1", "title": "Complaint", "category": "harassment",
                "status": "open", "outcome": None, "created_at": None,
            }]
        return []

    async def fetchrow(self, sql, *args):
        if self.fail and self.fail in sql:
            raise RuntimeError("simulated jurisdiction failure")
        return None


_ALL_FEATURES = {
    "incidents": True, "compliance": True, "discipline": True,
    "training": True, "handbooks": True, "accommodations": True,
}


def test_gather_evidence_isolates_a_failing_source():
    corpus = asyncio.run(ld.gather_evidence(
        _FakeConn(fail_substr="ir_incidents"), "cid", None, None, _ALL_FEATURES,
    ))
    # ER survived; incidents degraded to a note, not a crash.
    assert "er_cases" in corpus["sources"]
    assert "incidents" not in corpus["sources"]
    assert any("Safety incidents" in n for n in corpus["notes"])
    # index is flat cid -> record and only holds surfaced sources
    assert "er_case:11111111-1111-1111-1111-111111111111" in corpus["index"]


def test_gather_evidence_respects_disabled_features():
    corpus = asyncio.run(ld.gather_evidence(
        _FakeConn(), "cid", None, None, {"incidents": False},
    ))
    # ER has no feature gate (always attempted); incidents off → never queried.
    assert "incidents" not in corpus["sources"]


def test_gather_evidence_without_matter_adds_no_law_source():
    # matter=None (default) — proves the new keyword stays back-compat with
    # every pre-existing 3-positional-arg caller.
    corpus = asyncio.run(ld.gather_evidence(_FakeConn(), "cid", None, None, {}))
    assert "law" not in corpus["sources"]
    assert "legislation" not in corpus["sources"]
    assert "case_law" not in corpus["sources"]
    assert corpus["legal_context"] is None


def test_gather_evidence_jurisdiction_failure_degrades():
    matter = {"id": "m1", "company_id": "cid", "matter_type": "class_action",
              "location_id": None, "jurisdiction_state": "CA"}
    corpus = asyncio.run(ld.gather_evidence(
        _FakeConn(fail_substr="jurisdictions"), "cid", None, None, {}, matter=matter,
    ))
    assert corpus["legal_context"] is None
    assert any("Jurisdiction" in n for n in corpus["notes"])
    assert "law" not in corpus["sources"]


class _FakeAlertConn:
    async def fetch(self, sql, *args):
        return [{
            "id": "a1", "title": "New law effective", "severity": "critical",
            "status": "unread", "category": "minimum_wage", "deadline": None,
            "created_at": None, "location_name": "HQ",
        }]


def test_src_compliance_alerts_shape():
    recs = asyncio.run(ld._src_compliance_alerts(_FakeAlertConn(), "cid", None, None, None, None))
    assert len(recs) == 1
    r = recs[0]
    assert r["cid"] == "compliance_alert:a1"
    assert r["ref"] == "Minimum Wage"
    assert r["summary"] == "New law effective — Critical, Unread @ HQ"


# --- matter scoping ----------------------------------------------------------

def test_scope_fragments_use_expected_placeholders():
    import re
    frag = ld._scope_direct("t.location_id", "bl.state", 4)
    assert set(re.findall(r"\$(\d+)", frag)) == {"4", "5"}
    frag2 = ld._scope_direct("cr.location_id", "bl.state", 2)
    assert set(re.findall(r"\$(\d+)", frag2)) == {"2", "3"}
    emp = ld._scope_employee(4)
    assert set(re.findall(r"\$(\d+)", emp)) == {"4", "5"}
    assert "e.work_location_id" in emp and "e.work_state" in emp
    er = ld._scope_er_involved(4)
    assert set(re.findall(r"\$(\d+)", er)) == {"4", "5"}
    # no-employees ER cases stay IN scope; malformed ids can't crash the cast
    assert "jsonb_array_length" in er
    assert "~" in er and "::uuid" in er


def test_chronology_rows_sorted_and_filtered():
    index = {
        "incident:a": {"cid": "incident:a", "summary": "s1", "when_iso": "2025-06-01"},
        "discipline:b": {"cid": "discipline:b", "summary": "s2", "when_iso": "2025-01-15T10:00:00"},
        "er_case:c": {"cid": "er_case:c", "summary": "s3", "when_iso": None},
        "compliance_req:d": {"cid": "compliance_req:d", "summary": "posture", "when_iso": "2020-01-01"},
        "law:e": {"cid": "law:e", "summary": "law", "when_iso": "2019-01-01"},
    }
    rows = ld._chronology_rows(index)
    # posture + jurisdiction context excluded; dated events oldest first; undated last
    assert [r["cid"] for r in rows] == ["discipline:b", "incident:a", "er_case:c"]


def test_chronology_html_renders_dates_and_escapes():
    index = {"incident:a": {"cid": "incident:a", "summary": "<b>x</b>", "when_iso": "2025-06-01",
                            "source_label": "Safety incidents (IR / OSHA)"}}
    html = ld._chronology_html(index)
    assert "Chronology of records" in html
    assert "2025-06-01" in html
    assert "&lt;b&gt;" in html          # summaries are escaped
    assert ld._chronology_html({}) == ""  # empty corpus renders nothing


class _ArgCountConn:
    """Records the positional-arg count of every fetch so scoping params are
    provably threaded through each source query."""
    def __init__(self):
        self.arg_counts: dict[str, int] = {}

    async def fetch(self, sql, *args):
        for tbl in ("ir_incidents", "er_cases", "compliance_requirements",
                    "progressive_discipline", "training_records",
                    "policy_signatures", "accommodation_cases", "compliance_alerts"):
            if tbl in sql:
                self.arg_counts[tbl] = len(args)
        return []

    async def fetchrow(self, sql, *args):
        return None  # jurisdiction unresolvable — state fallback path


def test_gather_evidence_scopes_sources_to_matter_location():
    conn = _ArgCountConn()
    matter = {"id": "m1", "company_id": "cid", "matter_type": "class_action",
              "location_id": "22222222-2222-2222-2222-222222222222",
              "jurisdiction_state": None}
    corpus = asyncio.run(ld.gather_evidence(
        conn, "cid", None, None, _ALL_FEATURES, matter=matter,
    ))
    # every source got the two scope params on top of company/start/end;
    # subject-bearing sources carry the topic allowlist (+ known vocabulary)
    assert conn.arg_counts["ir_incidents"] == 7
    assert conn.arg_counts["compliance_requirements"] == 4  # no date filter there
    assert conn.arg_counts["progressive_discipline"] == 7
    assert conn.arg_counts["training_records"] == 5         # unfiltered by design
    assert conn.arg_counts["accommodation_cases"] == 5      # unfiltered by design
    assert conn.arg_counts["compliance_alerts"] == 6        # registry categories, no passthrough
    assert any(n.startswith("Evidence scoped to") for n in corpus["notes"])


def test_gather_evidence_state_only_scope_notes():
    class _Conn(_ArgCountConn):
        async def fetchrow(self, sql, *args):
            return None  # no jurisdiction row for the state — raw override used

    corpus = asyncio.run(ld.gather_evidence(
        _Conn(), "cid", None, None, {},
        matter={"id": "m1", "company_id": "cid", "matter_type": "audit",
                "location_id": None, "jurisdiction_state": "CA"},
    ))
    assert any(n == "Evidence scoped to CA." for n in corpus["notes"])


def test_gather_evidence_unscoped_matter_has_no_scope_note():
    corpus = asyncio.run(ld.gather_evidence(
        _ArgCountConn(), "cid", None, None, {},
        matter={"id": "m1", "company_id": "cid", "matter_type": "other",
                "location_id": None, "jurisdiction_state": None},
    ))
    assert not any("Evidence scoped" in n for n in corpus["notes"])


def test_matter_type_categories_are_registry_keys():
    for cats in ld._MATTER_TYPE_CATEGORIES.values():
        if not cats:
            continue
        for c in cats:
            assert c in CATEGORY_KEYS


# --- matter theory (subject-matter scoping) ----------------------------------

def test_theory_compliance_categories_are_registry_keys():
    for topic in ld._THEORIES.values():
        for c in topic.compliance or []:
            assert c in CATEGORY_KEYS


def test_resolve_theory_reads_the_allegation_over_the_matter_type():
    # the reported bug: a wage-and-hour class action was pulling slip-and-falls
    slug, topic = ld.resolve_matter_theory({
        "matter_type": "class_action", "title": "Jones vs 720 Behavioral",
        "allegation": "Nurses were required to work through meal breaks off the clock.",
    })
    assert slug == "wage_hour"
    assert topic.incidents == []               # no IR incident type is about pay
    assert "meal_breaks" in topic.compliance

    # a safety class action must NOT inherit the matter_type's wage-hour default
    slug, topic = ld.resolve_matter_theory({
        "matter_type": "class_action", "title": "Slip and fall",
        "allegation": "Employees were injured by an unmarked wet floor hazard.",
    })
    assert slug == "safety"
    assert "safety" in topic.incidents


def test_broad_matter_types_ignore_allegation_keywords():
    """The escape hatch the UI promises. A subject-less matter_type must stay
    broad even when the allegation is full of theory keywords — otherwise
    'set the type to Other to see every record' is a lie, and a records
    subpoena mentioning wages silently loses its safety incidents."""
    for mt in ("other", "subpoena", "audit"):
        slug, topic = ld.resolve_matter_theory({
            "matter_type": mt, "title": "Jones",
            "allegation": "missed meal breaks, unpaid overtime, wage theft",
        })
        assert slug is None, mt
        assert topic is ld._BROAD, mt


def test_theory_keywords_match_at_the_very_end_of_the_text():
    # a probe carrying a trailing space ("ada ") must still hit a term that
    # lands last — the scan text is padded for exactly this
    slug, _ = ld.resolve_matter_theory({
        "matter_type": "single_plaintiff", "title": "",
        "allegation": "Claim brought under the ADA",
    })
    assert slug == "eeo"


def test_compliance_alerts_keep_uncategorized_rows():
    # ca.category is nullable; an uncategorized alert must survive the filter
    frag_seen = {}

    class _Conn:
        async def fetch(self, sql, *args):
            frag_seen["sql"] = sql
            return []

    asyncio.run(ld._src_compliance_alerts(
        _Conn(), "cid", None, None, None, None, ld._THEORIES["wage_hour"]))
    assert "ca.category IS NULL" in frag_seen["sql"]


def test_resolve_theory_falls_back_to_matter_type_when_text_is_silent():
    assert ld.resolve_matter_theory({"matter_type": "eeoc_charge"})[0] == "eeo"
    assert ld.resolve_matter_theory({"matter_type": "class_action"})[0] == "wage_hour"
    # types carrying no subject signal stay broad — the escape hatch
    for mt in ("subpoena", "audit", "other"):
        slug, topic = ld.resolve_matter_theory({"matter_type": mt})
        assert slug is None
        assert topic is ld._BROAD
    assert ld.resolve_matter_theory(None) == (None, ld._BROAD)


def test_resolve_theory_declines_to_guess_on_a_tie():
    # one hit each ("discriminat" / "injur") — no winner, so the matter_type
    # decides rather than a coin flip on keyword ordering.
    slug, _ = ld.resolve_matter_theory({
        "matter_type": "eeoc_charge", "title": "",
        "allegation": "Discrimination claim following an injury.",
    })
    assert slug == "eeo"
    slug, _ = ld.resolve_matter_theory({
        "matter_type": "class_action", "title": "",
        "allegation": "Discrimination claim following an injury.",
    })
    assert slug == "wage_hour"


def test_topic_filter_passes_unknown_slugs_and_nulls():
    frag = ld._topic_filter("pd.infraction_type", 6)
    import re
    assert set(re.findall(r"\$(\d+)", frag)) == {"6", "7"}
    assert "IS NULL" in frag                        # unattributable rows stay in
    assert "NOT (pd.infraction_type = ANY($7))" in frag   # company-defined slugs stay in


def test_gather_evidence_filters_sources_to_the_theory():
    class _CapturingConn(_ArgCountConn):
        def __init__(self):
            super().__init__()
            self.topic_args: dict[str, object] = {}

        async def fetch(self, sql, *args):
            if "ir_incidents" in sql:
                self.topic_args["incidents"] = args[5]
            if "progressive_discipline" in sql:
                self.topic_args["discipline"] = args[5]
            if "compliance_requirements" in sql:
                self.topic_args["compliance"] = args[3]
            return await super().fetch(sql, *args)

    conn = _CapturingConn()
    corpus = asyncio.run(ld.gather_evidence(
        conn, "cid", None, None, _ALL_FEATURES,
        matter={"id": "m1", "company_id": "cid", "matter_type": "class_action",
                "title": "Jones", "allegation": "unpaid overtime and missed meal breaks",
                "location_id": None, "jurisdiction_state": None},
    ))
    assert conn.topic_args["incidents"] == []      # IR/OSHA drops out entirely
    assert "attendance" in conn.topic_args["discipline"]
    assert "meal_breaks" in conn.topic_args["compliance"]
    assert corpus["theory"] == {"slug": "wage_hour", "label": "wage-and-hour"}
    assert any("wage-and-hour theory" in n for n in corpus["notes"])


def test_gather_evidence_broad_theory_passes_null_allowlists():
    class _CapturingConn(_ArgCountConn):
        def __init__(self):
            super().__init__()
            self.incident_topic = "unset"

        async def fetch(self, sql, *args):
            if "ir_incidents" in sql:
                self.incident_topic = args[5]
            return await super().fetch(sql, *args)

    conn = _CapturingConn()
    corpus = asyncio.run(ld.gather_evidence(
        conn, "cid", None, None, _ALL_FEATURES,
        matter={"id": "m1", "company_id": "cid", "matter_type": "subpoena",
                "title": "Records subpoena", "allegation": None,
                "location_id": None, "jurisdiction_state": None},
    ))
    assert conn.incident_topic is None            # NULL allowlist = no filter
    assert corpus["theory"] is None
    assert not any("theory" in n for n in corpus["notes"])


# --- packet rendering guards -------------------------------------------------

def test_research_html_surfaces_partial_error():
    # A partial run (CourtListener down) persists status='complete' with an
    # error note and cases=[] — the PDF must not render that as a genuine
    # zero-result search.
    html = ld._research_html({
        "cases": [], "guidance": {"summary": "s", "key_authorities": []},
        "error": "Case search unavailable: courtlistener down",
    })
    assert "Partial run" in html
    assert "courtlistener down" in html
    # clean run renders no partial-run banner
    clean = ld._research_html({"cases": [], "guidance": {}, "error": None})
    assert "Partial run" not in clean


def test_memo_html_marks_out_of_scope_citations():
    # A cid validated at chat time but absent from the packet-time re-gather
    # must render an explicit marker, not silently-blank index cells.
    memo = {"assistant_text": "x", "open_questions": [],
            "evidence_map": [{"point": "p", "cited_ids": ["law:gone"]}]}
    corpus = {"index": {}, "sources": {}, "notes": []}
    html = ld._memo_html({}, corpus, memo, details={}, cited=["law:gone"])
    assert "no longer in evidence scope" in html


def test_dt_date_normalizes_str_and_date():
    # The RAG path pre-isoformats dates to str; the SQL path returns date
    # objects — both must render identically, date-only.
    import datetime
    assert ld._dt_date("2024-01-15") == "2024-01-15"
    assert ld._dt_date(datetime.date(2024, 1, 15)) == "2024-01-15"
    assert ld._dt_date(None) == "—"


# --- intake parser coercion ---------------------------------------------------

def test_coerce_draft_clamps_garbage():
    from app.matcha.services.legal_intake_parser import coerce_draft
    d = coerce_draft({
        "matter_type": "lawsuit-of-doom", "title": "  T  " + "x" * 300,
        "allegation": None, "jurisdiction_state": "Nevada",
        "evidence_start": "not-a-date", "evidence_end": "2025-12-31",
        "response_deadline": "2026-02-30",  # invalid calendar date
    })
    assert d["matter_type"] == "other"          # unknown type → other
    assert len(d["title"]) <= 120
    assert d["jurisdiction_state"] is None      # "Nevada" is not a 2-letter code
    assert d["evidence_start"] is None
    assert d["evidence_end"] == "2025-12-31"
    assert d["response_deadline"] is None       # Feb 30 rejected
    assert coerce_draft("not-a-dict")["matter_type"] == "other"


def test_coerce_draft_swaps_inverted_window_and_uppercases_state():
    from app.matcha.services.legal_intake_parser import coerce_draft
    d = coerce_draft({
        "matter_type": "eeoc_charge", "jurisdiction_state": "nv",
        "evidence_start": "2025-12-01", "evidence_end": "2025-01-01",
    })
    assert d["matter_type"] == "eeoc_charge"
    assert d["jurisdiction_state"] == "NV"
    assert d["evidence_start"] == "2025-01-01" and d["evidence_end"] == "2025-12-01"


# --- deadline reminder buckets -------------------------------------------------

def test_deadline_bucket_boundaries():
    from app.workers.tasks.legal_deadline_reminders import bucket_for
    assert bucket_for(0) == 1
    assert bucket_for(1) == 1
    assert bucket_for(2) == 3
    assert bucket_for(6) == 7      # worker down on day 7 still catches day 6
    assert bucket_for(14) == 14
    assert bucket_for(15) is None  # beyond lookahead
    assert bucket_for(-1) is None  # overdue — no nag, UI shows red
