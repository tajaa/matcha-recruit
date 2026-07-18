"""Pure-logic tests for ER compliance grounding (no DB, no network).

Covers the citation-record builder and the end-to-end anti-hallucination gate
(`legal_defense.validate_citations` over a corpus index). The DB-backed
`build_jurisdiction_corpus` query is exercised manually on dev-remote — see the
plan's verification section — not here.
"""

from app.matcha.services import er_compliance_grounding as g
from app.matcha.services.legal_defense import validate_citations


def _index():
    return {
        "jur:1": {"cid": "jur:1", "requirement_id": "1", "state": "CA",
                  "category": "final_pay", "title": "Final pay timing",
                  "statute_citation": "Cal. Lab. Code § 201", "source_url": None},
        "jur:2": {"cid": "jur:2", "requirement_id": "2", "state": "CA",
                  "category": "retaliation", "title": "Anti-retaliation",
                  "statute_citation": None, "source_url": "https://ex.example.com"},
    }


def test_build_citation_records_dedup_and_order():
    idx = _index()
    clean_map = [
        {"point": "a", "cited_ids": ["jur:2", "jur:1"]},
        {"point": "b", "cited_ids": ["jur:1"]},  # dup, dropped
    ]
    recs = g.build_citation_records(clean_map, idx)
    assert [r["cid"] for r in recs] == ["jur:2", "jur:1"]  # first-cited order, deduped
    assert recs[0]["statute_citation"] is None
    assert recs[1]["statute_citation"] == "Cal. Lab. Code § 201"


def test_build_citation_records_drops_unknown_cid():
    idx = _index()
    recs = g.build_citation_records([{"point": "x", "cited_ids": ["jur:999"]}], idx)
    assert recs == []


def test_build_citation_records_empty():
    assert g.build_citation_records([], _index()) == []
    assert g.build_citation_records(None, _index()) == []


def test_gate_drops_hallucinated_citation():
    idx = _index()
    # Model cited one real requirement and one it invented.
    model_map = [{"point": "Final pay due immediately", "cited_ids": ["jur:1", "jur:HALLUCINATED"]}]
    clean, dropped = validate_citations(model_map, idx)
    assert dropped == ["jur:HALLUCINATED"]
    assert clean[0]["cited_ids"] == ["jur:1"]
    recs = g.build_citation_records(clean, idx)
    assert len(recs) == 1 and recs[0]["cid"] == "jur:1"


def test_gate_handles_missing_evidence_map():
    clean, dropped = validate_citations(None, _index())
    assert clean == [] and dropped == []
    assert g.build_citation_records(clean, _index()) == []


# --------------------------------------------------------------------------- #
# Truncation signal — the LIMIT must not be silent
# --------------------------------------------------------------------------- #

import asyncio


class _FakeConn:
    """Returns `n` catalog rows; records the LIMIT the query asked for."""

    def __init__(self, n):
        self.n = n
        self.limit_requested = None

    async def fetch(self, _query, *args):
        # (states, categories, limit) — the corpus query; anything else is a
        # state-resolution query, which we answer with one work_state.
        if len(args) == 3:
            self.limit_requested = args[2]
            return [
                {"id": f"{i}", "state": "CA", "category": "final_pay",
                 "title": f"Requirement {i}", "description": "Body.",
                 "current_value": None, "statute_citation": "Cal. Lab. Code § 201",
                 "source_url": None, "effective_date": None}
                for i in range(self.n)
            ][: args[2]]
        return [{"work_state": "CA", "state": "CA"}]


def _run_corpus(conn, monkeypatch):
    async def _gate(_alias, *, conn=None):
        return ""

    monkeypatch.setattr("app.core.services.compliance_service.codified_gate_sql", _gate)
    return asyncio.run(g.build_jurisdiction_corpus(conn, "c1", ["e1"]))


def test_truncation_flag_set_when_catalog_exceeds_cap(monkeypatch):
    conn = _FakeConn(g._MAX_ROWS + 5)
    text, index, truncated = _run_corpus(conn, monkeypatch)
    assert truncated is True
    # Probes one past the cap to detect the overflow, but never shows it.
    assert conn.limit_requested == g._MAX_ROWS + 1
    assert len(index) == g._MAX_ROWS
    # The model reading the text is told, without each caller wiring it up.
    assert "truncated" in text


def test_no_truncation_at_exactly_the_cap(monkeypatch):
    """`len(index) == _MAX_ROWS` is the false positive the probe row exists to
    avoid — a full page is not a cut one."""
    conn = _FakeConn(g._MAX_ROWS)
    text, index, truncated = _run_corpus(conn, monkeypatch)
    assert truncated is False
    assert len(index) == g._MAX_ROWS
    assert "truncated" not in text
