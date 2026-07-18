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
            "description": "Involuntary termination: all wages due immediately.",
            "statute_citation": "Cal. Lab. Code §§ 201-203",
            "source_url": "https://example.test/ca-final-pay",
        },
        "jur:22222222-2222-2222-2222-222222222222": {
            "cid": "jur:22222222-2222-2222-2222-222222222222",
            "requirement_id": "22222222-2222-2222-2222-222222222222",
            "state": "US",
            "category": "anti_discrimination",
            "title": "Title VII protections",
            "description": "",
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
        "(CA — final_pay) Final wages due at termination: "
        "Involuntary termination: all wages due immediately. "
        "Citation: Cal. Lab. Code §§ 201-203"
    )
    assert cited["when"] == "current"
    assert cited["source_url"] == "https://example.test/ca-final-pay"
    # requirement_id stays internal — it is not a citable corpus field.
    assert "requirement_id" not in cited


def test_summary_carries_state_and_description():
    """`_corpus_text` renders ONLY `summary`, so both must live there: without
    the state a multi-state client's rows are identical to the model; without
    the description it has a real cid and no statement of the rule."""
    prompt_lines = [r["summary"] for r in bp._jurisdiction_records(_sample_index())]
    assert all("CA" in ln or "US" in ln for ln in prompt_lines)
    ca = next(ln for ln in prompt_lines if ln.startswith("(CA"))
    assert "all wages due immediately" in ca
    # The two rows must not be indistinguishable in the prompt.
    assert len(set(prompt_lines)) == 2


def test_jurisdiction_records_uncited_row():
    recs = bp._jurisdiction_records(_sample_index())
    uncited = next(r for r in recs if r["cid"].startswith("jur:2222"))
    assert uncited["ref"] == "US — Title VII protections"
    # No description → title only, no dangling colon.
    assert uncited["summary"] == "(US — anti_discrimination) Title VII protections Citation: uncited"
    assert uncited["source_url"] is None


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


def test_missing_jurisdiction_grounding_is_announced():
    """An on-platform client (native is not None) whose codified grounding came
    back empty gets a scope note — the system prompt promises `jur:` records for
    on-platform clients, so silence reads as 'grounded' when it isn't."""
    native = {"sources": {}, "notes": []}
    bare = bp.build_corpus("Acme Co", {}, [], native=native, jurisdiction=[])
    assert any("jur:" in n and "unavailable" in n for n in bare["notes"])

    grounded = bp.build_corpus("Acme Co", {}, [], native=native,
                               jurisdiction=bp._jurisdiction_records(_sample_index()))
    assert not any("unavailable" in n for n in grounded["notes"])

    # Off-platform clients already carry their own note; don't double up.
    off = bp.build_corpus("Acme Co", {}, [], native=None, jurisdiction=[])
    assert not any("jur:" in n for n in off["notes"])


def test_jurisdiction_appendix_is_not_labelled_a_platform_record():
    """Statutes render under their own heading — `_native_appendix_html` would
    call them 'Platform records', misstating provenance in the exported memo."""
    jurisdiction = bp._jurisdiction_records(_sample_index())
    corpus = bp.build_corpus("Acme Co", {}, [], native=None, jurisdiction=jurisdiction)
    real = "jur:11111111-1111-1111-1111-111111111111"
    html = bp._jurisdiction_appendix_html([real], corpus)

    assert "Codified statutory obligations" in html
    assert "Platform records" not in html
    assert "all wages due immediately" in html
    assert 'href="https://example.test/ca-final-pay"' in html
    # Only the cited row renders.
    assert "Title VII" not in html


def test_appendix_source_link_rejects_non_http_scheme():
    assert bp._link_or_dash(None) == "—"
    assert bp._link_or_dash("javascript:alert(1)") == "—"
    assert bp._link_or_dash("https://example.test/x").startswith('<a href="https://example.test/x"')
