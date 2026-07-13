"""Broker Pilot document requirements — pure rules, no DB / no app boot.

Covers the three ways a requirement gets satisfied (upload / unclassified /
platform), the two that deliberately DON'T (a loss-run deep dive can't be
satisfied by platform triangles; a processing or failed upload never counts),
and the 409 body the chat gate raises.
"""

from app.matcha.services import broker_pilot as bp
from app.matcha.services import broker_pilot_requirements as bpr


# --------------------------------------------------------------------------- #
# Fixtures (hand-built — same style as test_broker_pilot.py)
# --------------------------------------------------------------------------- #

def _doc(doc_id: str, doc_type: str | None, status: str = "ready") -> dict:
    return {"id": doc_id, "doc_type": doc_type, "status": status}


def _corpus(platform_cids: list[str] | None = None, clauses: bool = False) -> dict:
    sources = {
        "platform": {
            "label": "Platform data on file",
            "records": [{"cid": c} for c in platform_cids or []],
        },
    }
    if clauses:
        sources["clauses"] = {"label": "Contract indemnity clauses",
                              "records": [{"cid": "clause:abc"}]}
    return {"sources": sources, "index": {}, "notes": []}


_CONTRACT_REVIEW = bp.get_template("contract_review")
_LOSS_RUN = bp.get_template("loss_run")
_MID_YEAR = bp.get_template("mid_year")
_QUOTES = bp.get_template("quote_comparison")


# --------------------------------------------------------------------------- #
# platform_flags
# --------------------------------------------------------------------------- #

def test_platform_flags_empty_corpus():
    flags = bpr.platform_flags({})
    assert flags == {"clauses": False, "lossdev": False, "limits": False}


def test_platform_flags_none_corpus_does_not_raise():
    assert bpr.platform_flags(None)["clauses"] is False


def test_platform_flags_detects_lossdev_and_limits_cids():
    corpus = _corpus(["platform:wc", "platform:lossdev.wc.2025", "platform:limits.gl"])
    flags = bpr.platform_flags(corpus)
    assert flags["lossdev"] is True
    assert flags["limits"] is True
    assert flags["clauses"] is False


def test_platform_flags_lossdev_not_triggered_by_unrelated_platform_records():
    # A bare `platform:wc` is not loss development — the prefix match must be exact.
    assert bpr.platform_flags(_corpus(["platform:wc", "platform:property"]))["lossdev"] is False


def test_platform_flags_clauses_source():
    assert bpr.platform_flags(_corpus([], clauses=True))["clauses"] is True


# --------------------------------------------------------------------------- #
# doc_requirements — no mode
# --------------------------------------------------------------------------- #

def test_no_template_has_no_requirements():
    assert bpr.doc_requirements(None, [_doc("d1", "loss_run")], {}) == []


def test_template_without_required_docs_has_no_requirements():
    assert bpr.doc_requirements({"key": "x"}, [], {}) == []


# --------------------------------------------------------------------------- #
# doc_requirements — satisfaction by upload
# --------------------------------------------------------------------------- #

def test_matching_upload_satisfies():
    rows = bpr.doc_requirements(_LOSS_RUN, [_doc("d1", "loss_run")], {})
    assert len(rows) == 1
    assert rows[0]["satisfied"] is True
    assert rows[0]["satisfied_by"] == "upload"
    assert rows[0]["doc_ids"] == ["d1"]


def test_all_matching_uploads_are_collected():
    rows = bpr.doc_requirements(_QUOTES, [_doc("q1", "quote"), _doc("q2", "quote")], {})
    quote_row = next(r for r in rows if r["doc_type"] == "quote")
    assert quote_row["doc_ids"] == ["q1", "q2"]


def test_processing_upload_does_not_satisfy():
    rows = bpr.doc_requirements(_LOSS_RUN, [_doc("d1", "loss_run", status="processing")], {})
    assert rows[0]["satisfied"] is False
    assert rows[0]["satisfied_by"] is None


def test_failed_upload_does_not_satisfy():
    rows = bpr.doc_requirements(_LOSS_RUN, [_doc("d1", "loss_run", status="failed")], {})
    assert rows[0]["satisfied"] is False


def test_wrong_type_upload_does_not_satisfy():
    rows = bpr.doc_requirements(_LOSS_RUN, [_doc("d1", "dec_page")], {})
    assert rows[0]["satisfied"] is False


# --------------------------------------------------------------------------- #
# doc_requirements — the unclassified grace (Gemini down)
# --------------------------------------------------------------------------- #

def test_unclassified_upload_satisfies():
    rows = bpr.doc_requirements(_LOSS_RUN, [_doc("d1", None, status="text_only")], {})
    assert rows[0]["satisfied"] is True
    assert rows[0]["satisfied_by"] == "unclassified"
    assert rows[0]["doc_ids"] == ["d1"]


def test_one_unclassified_doc_satisfies_only_one_requirement():
    # contract_review declares contract (required) + dec_page (optional). A single
    # unreadable PDF must not stand in for both.
    rows = bpr.doc_requirements(_CONTRACT_REVIEW, [_doc("d1", None, status="text_only")], {})
    satisfied = [r for r in rows if r["satisfied_by"] == "unclassified"]
    assert len(satisfied) == 1
    assert satisfied[0]["doc_type"] == "contract"  # first declared wins


def test_classified_match_preferred_over_spending_an_unclassified_doc():
    docs = [_doc("u1", None, status="text_only"), _doc("c1", "contract")]
    rows = bpr.doc_requirements(_CONTRACT_REVIEW, docs, {})
    contract = next(r for r in rows if r["doc_type"] == "contract")
    dec = next(r for r in rows if r["doc_type"] == "dec_page")
    assert contract["satisfied_by"] == "upload"
    # The unclassified doc is still unspent, so it falls to the next open row.
    assert dec["satisfied_by"] == "unclassified"


# --------------------------------------------------------------------------- #
# doc_requirements — satisfaction by platform data (the dynamic part)
# --------------------------------------------------------------------------- #

def test_contract_review_satisfied_by_clauses_on_file():
    flags = bpr.platform_flags(_corpus([], clauses=True))
    rows = bpr.doc_requirements(_CONTRACT_REVIEW, [], flags)
    contract = next(r for r in rows if r["doc_type"] == "contract")
    assert contract["satisfied"] is True
    assert contract["satisfied_by"] == "platform"


def test_contract_review_unsatisfied_without_clauses():
    rows = bpr.doc_requirements(_CONTRACT_REVIEW, [], bpr.platform_flags(_corpus([])))
    contract = next(r for r in rows if r["doc_type"] == "contract")
    assert contract["satisfied"] is False


def test_mid_year_loss_run_satisfied_by_platform_lossdev():
    flags = bpr.platform_flags(_corpus(["platform:lossdev.wc.2025"]))
    rows = bpr.doc_requirements(_MID_YEAR, [], flags)
    assert rows[0]["satisfied_by"] == "platform"


def test_loss_run_deep_dive_is_NOT_satisfied_by_platform_lossdev():
    """The locked product decision: the deep-dive mode reconciles the carrier
    document against the platform triangles, so the triangles alone can't stand
    in for the document — otherwise the mode silently loses its subject."""
    flags = bpr.platform_flags(_corpus(["platform:lossdev.wc.2025"]))
    rows = bpr.doc_requirements(_LOSS_RUN, [], flags)
    assert rows[0]["satisfied"] is False
    assert bpr.missing_required(rows)


# --------------------------------------------------------------------------- #
# missing_required
# --------------------------------------------------------------------------- #

def test_optional_rows_never_block():
    rows = bpr.doc_requirements(_CONTRACT_REVIEW, [_doc("c1", "contract")], {})
    dec = next(r for r in rows if r["doc_type"] == "dec_page")
    assert dec["required"] is False and dec["satisfied"] is False
    assert bpr.missing_required(rows) == []


def test_missing_required_lists_unsatisfied_required_rows():
    rows = bpr.doc_requirements(_CONTRACT_REVIEW, [], {})
    missing = bpr.missing_required(rows)
    assert [m["doc_type"] for m in missing] == ["contract"]


def test_missing_required_of_none_is_empty():
    assert bpr.missing_required(None) == []


# --------------------------------------------------------------------------- #
# missing_docs_detail — the 409 body (mirrors schedule_rules.conflict_detail)
# --------------------------------------------------------------------------- #

def test_missing_docs_detail_shape():
    rows = bpr.doc_requirements(_CONTRACT_REVIEW, [], {})
    detail = bpr.missing_docs_detail(bpr.missing_required(rows))
    assert detail["code"] == "missing_required_documents"
    assert "Client contract" in detail["message"]
    assert [m["doc_type"] for m in detail["missing"]] == ["contract"]
    assert detail["missing"][0]["label"] and detail["missing"][0]["hint"]


def test_missing_docs_detail_empty_still_well_formed():
    detail = bpr.missing_docs_detail([])
    assert detail["code"] == "missing_required_documents"
    assert detail["missing"] == []


# --------------------------------------------------------------------------- #
# scope_notes + single_quote_note — what the analyst is told
# --------------------------------------------------------------------------- #

def test_scope_notes_name_the_missing_document():
    rows = bpr.doc_requirements(_LOSS_RUN, [], {})
    notes = bpr.scope_notes(_LOSS_RUN, [], rows)
    assert len(notes) == 1
    assert "Carrier loss run" in notes[0]
    assert "NOT been provided" in notes[0]


def test_scope_notes_silent_when_satisfied():
    docs = [_doc("d1", "loss_run")]
    rows = bpr.doc_requirements(_LOSS_RUN, docs, {})
    assert bpr.scope_notes(_LOSS_RUN, docs, rows) == []


def test_single_quote_note_fires_on_exactly_one_quote():
    docs = [_doc("q1", "quote")]
    note = bpr.single_quote_note(_QUOTES, docs)
    assert note and "ONE carrier quote" in note


def test_single_quote_note_silent_on_two_quotes():
    docs = [_doc("q1", "quote"), _doc("q2", "quote")]
    assert bpr.single_quote_note(_QUOTES, docs) is None


def test_single_quote_note_silent_on_zero_quotes():
    assert bpr.single_quote_note(_QUOTES, []) is None


def test_single_quote_note_only_applies_to_the_quote_mode():
    assert bpr.single_quote_note(_LOSS_RUN, [_doc("q1", "quote")]) is None


def test_scope_notes_carry_the_single_quote_note():
    docs = [_doc("q1", "quote")]
    rows = bpr.doc_requirements(_QUOTES, docs, {})
    notes = bpr.scope_notes(_QUOTES, docs, rows)
    assert any("ONE carrier quote" in n for n in notes)


# --------------------------------------------------------------------------- #
# Catalog integrity — a typo in a template spec must fail here, not silently
# never match at runtime.
# --------------------------------------------------------------------------- #

def test_every_required_doc_type_is_a_real_doc_type():
    for t in bp.PILOT_TEMPLATES:
        for spec in t.get("required_docs") or ():
            assert spec["doc_type"] in bp.DOC_TYPES, (t["key"], spec["doc_type"])


def test_every_platform_source_is_a_known_flag():
    known = bpr.platform_flags({}).keys()
    for t in bp.PILOT_TEMPLATES:
        for spec in t.get("required_docs") or ():
            source = spec.get("platform_source")
            assert source is None or source in known, (t["key"], source)
            assert source is None or source in bpr.PLATFORM_SOURCES


def test_every_required_doc_spec_is_complete():
    for t in bp.PILOT_TEMPLATES:
        for spec in t.get("required_docs") or ():
            assert spec["label"] and spec["hint"]
            assert isinstance(spec["required"], bool)


def test_public_template_exposes_required_docs():
    tmpl = bp.get_template("contract_review")
    assert [r["doc_type"] for r in tmpl["required_docs"]] == ["contract", "dec_page"]


def test_public_template_required_docs_are_copies():
    a = bp.get_template("contract_review")
    a["required_docs"][0]["label"] = "mutated"
    assert bp.get_template("contract_review")["required_docs"][0]["label"] == "Client contract"


def test_catalog_entries_all_carry_required_docs_key():
    for t in bp.template_catalog():
        assert isinstance(t["required_docs"], list)
