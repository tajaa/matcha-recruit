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
    recs = asyncio.run(ld._src_compliance_alerts(_FakeAlertConn(), "cid", None, None))
    assert len(recs) == 1
    r = recs[0]
    assert r["cid"] == "compliance_alert:a1"
    assert r["ref"] == "Minimum Wage"
    assert r["summary"] == "New law effective — Critical, Unread @ HQ"


def test_matter_type_categories_are_registry_keys():
    for cats in ld._MATTER_TYPE_CATEGORIES.values():
        if not cats:
            continue
        for c in cats:
            assert c in CATEGORY_KEYS


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
