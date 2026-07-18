"""Unit tests for Broker Pilot codified-jurisdiction grounding — pure, no DB.

`_jurisdiction_records` reshapes `er_compliance_grounding`'s flat index into the
corpus record shape every other source uses; the reshaped `jur:` cids must flow
through the flat corpus index so the shared `validate_citations` gate keeps the
real ones and drops invented ones.
"""

from app.matcha.services import broker_pilot as bp
from app.matcha.services.legal_defense import validate_citations


def _sample_index() -> dict:
    """Two rows in the shape `er_compliance_grounding.build_jurisdiction_corpus`
    returns as its flat index: one with a statute citation, one without."""
    return {
        "jur:11111111-1111-1111-1111-111111111111": {
            "cid": "jur:11111111-1111-1111-1111-111111111111",
            "requirement_id": "11111111-1111-1111-1111-111111111111",
            "state": "ca",
            "category": "final_pay",
            "title": "Final wages due at termination",
            "statute_citation": "Cal. Lab. Code §§ 201-203",
            "source_url": "https://example.test/ca-final-pay",
        },
        "jur:22222222-2222-2222-2222-222222222222": {
            "cid": "jur:22222222-2222-2222-2222-222222222222",
            "requirement_id": "22222222-2222-2222-2222-222222222222",
            "state": "US",
            "category": "anti_discrimination",
            "title": "Title VII protections",
            "statute_citation": None,
            "source_url": None,
        },
    }


def test_jurisdiction_records_reshapes_fields():
    recs = bp._jurisdiction_records(_sample_index())
    assert len(recs) == 2
    by_cid = {r["cid"]: r for r in recs}

    cited = by_cid["jur:11111111-1111-1111-1111-111111111111"]
    assert cited["ref"] == "CA — Final wages due at termination"
    assert cited["summary"] == (
        "(final_pay) Final wages due at termination. "
        "Citation: Cal. Lab. Code §§ 201-203"
    )
    assert cited["when"] == "current"
    # Only the four corpus-record keys — no requirement_id / source_url leak.
    assert set(cited.keys()) == {"cid", "ref", "summary", "when"}


def test_jurisdiction_records_uncited_row():
    recs = bp._jurisdiction_records(_sample_index())
    uncited = next(r for r in recs if r["cid"].startswith("jur:2222"))
    assert uncited["ref"] == "US — Title VII protections"
    assert uncited["summary"] == "(anti_discrimination) Title VII protections. Citation: uncited"


def test_jurisdiction_records_empty_index():
    assert bp._jurisdiction_records({}) == []
    assert bp._jurisdiction_records(None) == []


def test_build_corpus_indexes_jurisdiction_cids():
    jurisdiction = bp._jurisdiction_records(_sample_index())
    corpus = bp.build_corpus("Acme Co", {}, [], native=None, jurisdiction=jurisdiction)
    # jur: cids land in the flat index like every other source.
    for cid in _sample_index():
        assert cid in corpus["index"]
        assert corpus["index"][cid]["source"] == "jurisdiction"
    # Empty jurisdiction → no source registered.
    bare = bp.build_corpus("Acme Co", {}, [], native=None, jurisdiction=[])
    assert "jurisdiction" not in bare["sources"]


def test_validate_citations_drops_fake_jur_cid():
    """A real jur: cid survives the gate; an invented one is dropped — the whole
    point of routing jurisdiction records through the flat index."""
    jurisdiction = bp._jurisdiction_records(_sample_index())
    corpus = bp.build_corpus("Acme Co", {}, [], native=None, jurisdiction=jurisdiction)
    real = "jur:11111111-1111-1111-1111-111111111111"
    fake = "jur:99999999-9999-9999-9999-999999999999"
    evidence_map = [{"point": "Final pay is statutorily timed", "cited_ids": [real, fake]}]
    clean, dropped = validate_citations(evidence_map, corpus["index"])
    assert clean[0]["cited_ids"] == [real]
    assert dropped == [fake]
