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


# --------------------------------------------------------------------------- #
# Per-turn cost: the corpus is cached per company (route-level)
# --------------------------------------------------------------------------- #

import asyncio

import pytest

from app.matcha.routes import broker_pilot as bpr


class _CountingConn:
    """Stands in for the asyncpg conn; counts how often the corpus is built."""

    def __init__(self):
        self.builds = 0


def _patch_corpus(monkeypatch, conn):
    async def _fake_build(_conn, _company_id, _ids):
        conn.builds += 1
        return "text", _sample_index()

    monkeypatch.setattr(bpr.ecg, "build_jurisdiction_corpus", _fake_build)


def _session(subject_id="c0000000-0000-0000-0000-000000000001", kind="company"):
    return {"id": "s1", "subject_kind": kind, "subject_id": subject_id}


@pytest.fixture(autouse=True)
def _clear_jur_cache():
    bpr._JUR_CACHE.clear()
    yield
    bpr._JUR_CACHE.clear()


def test_jurisdiction_corpus_is_built_once_per_company(monkeypatch):
    """A multi-turn session must not pay ~4 sequential round-trips per turn for
    rows that cannot change mid-conversation."""
    conn = _CountingConn()
    _patch_corpus(monkeypatch, conn)

    first = asyncio.run(bpr._jurisdiction_for(conn, _session()))
    for _ in range(19):
        again = asyncio.run(bpr._jurisdiction_for(conn, _session()))

    assert conn.builds == 1          # 20 turns, one build
    assert again == first
    assert len(first) == 2


def test_jurisdiction_cache_is_per_company(monkeypatch):
    conn = _CountingConn()
    _patch_corpus(monkeypatch, conn)

    asyncio.run(bpr._jurisdiction_for(conn, _session("c0000000-0000-0000-0000-00000000000a")))
    asyncio.run(bpr._jurisdiction_for(conn, _session("c0000000-0000-0000-0000-00000000000b")))
    assert conn.builds == 2          # no cross-client bleed


def test_jurisdiction_cache_expires(monkeypatch):
    conn = _CountingConn()
    _patch_corpus(monkeypatch, conn)

    clock = {"t": 1000.0}
    monkeypatch.setattr(bpr.time, "monotonic", lambda: clock["t"])

    asyncio.run(bpr._jurisdiction_for(conn, _session()))
    clock["t"] += bpr._JUR_CACHE_TTL_SECONDS + 1
    asyncio.run(bpr._jurisdiction_for(conn, _session()))
    assert conn.builds == 2


def test_empty_and_failed_grounding_are_not_cached(monkeypatch):
    """Pinning an empty result for the TTL would outlast the fix — a client
    whose states resolve a minute later would stay ungrounded for 15 minutes."""
    conn = _CountingConn()

    async def _empty(_c, _id, _ids):
        conn.builds += 1
        return "", {}

    monkeypatch.setattr(bpr.ecg, "build_jurisdiction_corpus", _empty)
    assert asyncio.run(bpr._jurisdiction_for(conn, _session())) == []
    assert asyncio.run(bpr._jurisdiction_for(conn, _session())) == []
    assert conn.builds == 2

    async def _boom(_c, _id, _ids):
        conn.builds += 1
        raise RuntimeError("catalog down")

    monkeypatch.setattr(bpr.ecg, "build_jurisdiction_corpus", _boom)
    assert asyncio.run(bpr._jurisdiction_for(conn, _session())) == []
    assert conn.builds == 3          # failure retried, not pinned


def test_external_subject_never_touches_the_catalog(monkeypatch):
    conn = _CountingConn()
    _patch_corpus(monkeypatch, conn)
    assert asyncio.run(bpr._jurisdiction_for(conn, _session(kind="external"))) == []
    assert conn.builds == 0


def test_jurisdiction_cache_is_size_capped(monkeypatch):
    conn = _CountingConn()
    _patch_corpus(monkeypatch, conn)
    for i in range(bpr._JUR_CACHE_MAX + 10):
        asyncio.run(bpr._jurisdiction_for(conn, _session(f"c{i:08d}-0000-0000-0000-000000000000")))
    assert len(bpr._JUR_CACHE) <= bpr._JUR_CACHE_MAX
