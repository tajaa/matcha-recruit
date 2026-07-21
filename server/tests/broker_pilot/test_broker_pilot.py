"""Unit tests for the Broker Pilot service — pure helpers, no DB / no app boot.

The cid scheme is the contract: every record the corpus emits must land in the
flat index (the citation gate and memo renderer key on it), and the imported
`validate_citations` gate must keep real broker-pilot cids while dropping
invented ones.
"""

from app.matcha.services import broker_pilot as bp
from app.matcha.services.legal_defense import validate_citations


# --- extraction coercion ----------------------------------------------------

def test_coerce_extraction_whitelists_doc_type():
    assert bp._coerce_extraction({"doc_type": "loss_run"})["doc_type"] == "loss_run"
    assert bp._coerce_extraction({"doc_type": "ransom_note"})["doc_type"] == "other"
    assert bp._coerce_extraction({})["doc_type"] == "other"


def test_coerce_extraction_caps_and_cleans():
    payload = {
        "doc_type": "quote",
        "summary": "x" * 1000,
        "key_figures": [{"label": "L" * 200, "value": "V" * 200, "context": "C" * 500}] * 40
                       + [{"label": "", "value": "orphan"}, "junk", None],
        "notable": ["n" * 500] * 30 + ["", None],
        "line": "warp-core",
        "carrier": "  Acme Mutual  ",
    }
    out = bp._coerce_extraction(payload)
    assert len(out["summary"]) == 600
    assert len(out["key_figures"]) <= bp._MAX_KEY_FIGURES
    for f in out["key_figures"]:
        assert len(f["label"]) <= 80 and len(f["value"]) <= 60 and len(f["context"]) <= 160
    assert len(out["notable"]) <= bp._MAX_NOTABLE
    assert all(len(n) <= 200 for n in out["notable"])
    assert out["line"] is None            # not in the line whitelist
    assert out["carrier"] == "Acme Mutual"


def test_coerce_extraction_never_raises_on_junk():
    for junk in (None, [], "string", 42, {"key_figures": "nope", "notable": 3}):
        out = bp._coerce_extraction(junk)  # type: ignore[arg-type]
        assert out["doc_type"] == "other"
        assert out["key_figures"] == []


# --- corpus build: cid/index integrity ---------------------------------------

_CTX = {
    "name": "Hillcrest Senior Living",
    "industry": "healthcare",
    "headcount": 180,
    "state": "CA",
    "wc": {"trir": 4.2, "dart_rate": 2.1, "current_emr": 1.18,
           "recordable_cases": 7, "lost_days": 44, "severity_band": "elevated"},
    "epl": {"score": 61, "band": "moderate",
            "factors": [{"key": "anti_harassment_policy", "status": "met"},
                        {"key": "pay_transparency", "status": "attested_no", "note": "broker note"}]},
    "controls": {"controls": [{"status": "verified"}, {"status": "unverified"}]},
    "readiness": {"score": 72, "band": "near_ready", "items": [{"complete": False}, {"complete": True}]},
    "venue": {"locations": [{"tier": "severe"}, {"tier": "moderate"}]},
    # Shapes mirror limit_adequacy.build_review lines_out / loss_development
    # build_triangle periods — the corpus builder keys on these exact names.
    "limits": {"lines": [
        {"key": "gl", "label": "General Liability",
         "carried": {"per_occurrence": 1_000_000, "aggregate": 2_000_000,
                     "carrier": "Hartford", "expiry_date": "2026-10-01"},
         "contract_required": {"per_occurrence": 2_000_000},
         "gap": "Carry $1.0M — contracts require $2.0M",
         "endorsement_gaps": [{"key": "additional_insured", "label": "Additional insured"}]},
        {"key": "auto", "label": "Commercial Auto", "carried": None,
         "contract_required": None},   # no data → skipped
    ]},
    "exclusions": {"exclusions": [{"name": "abuse_molestation", "why": "senior-living exposure"}]},
    "loss_development": {"lines": [
        {"line": "wc", "periods": [
            {"period_label": "2024-2025",
             "points": [{"paid": 180_000, "reserved": 60_000, "incurred": 240_000,
                         "claim_count": 9, "open_count": 2, "maturity": 12,
                         "valuation_date": "2026-03-31"}],
             "latest_incurred": 240_000, "ultimate": 260_000}]}]},
    "property": {"rollup": {"building_count": 3, "total_tiv": 12_500_000,
                            "worst_cope_grade": "C", "insured_to_value_pct": 84}},
}


def _docs():
    return [
        {"id": "11111111-1111-1111-1111-111111111111", "filename": "loss-run.pdf",
         "status": "ready", "created_at": None,
         "extraction": {"doc_type": "loss_run", "title": "Travelers WC loss run",
                        "carrier": "Travelers", "period_label": "2025-2026",
                        "summary": "WC loss run valued 2026-03-31.",
                        "key_figures": [{"label": "Total paid", "value": "$210,000", "context": "2024 PY"},
                                        {"label": "Open claims", "value": "2", "context": ""}],
                        "notable": ["Two open lost-time claims"]},
         "extracted_text": "CLAIM 001 ..."},
        {"id": "22222222-2222-2222-2222-222222222222", "filename": "dec-page.pdf",
         "status": "text_only", "created_at": None, "extraction": None,
         "extracted_text": "DECLARATIONS ..."},
        {"id": "33333333-3333-3333-3333-333333333333", "filename": "broken.pdf",
         "status": "failed", "created_at": None, "extraction": None, "extracted_text": ""},
        {"id": "44444444-4444-4444-4444-444444444444", "filename": "uploading.pdf",
         "status": "processing", "created_at": None, "extraction": None, "extracted_text": ""},
    ]


def test_build_corpus_every_record_is_indexed():
    corpus = bp.build_corpus("Hillcrest", _CTX, _docs())
    for key, s in corpus["sources"].items():
        for r in s["records"]:
            assert r["cid"] in corpus["index"], f"{key} record {r['cid']} missing from index"
            assert corpus["index"][r["cid"]]["source"] == key


_NATIVE = {
    "sources": {
        "incidents": {"label": "Safety incidents (IR / OSHA)", "records": [
            {"cid": "incident:aaaa", "ref": "IR-2024-003", "summary": "Slip in kitchen", "when": "2024-03-01"},
        ]},
        "er_cases": {"label": "Employee-relations cases", "records": [
            {"cid": "er_case:bbbb", "ref": "ER-12", "summary": "Wage complaint", "when": "2024-05-10"},
        ]},
    },
    "notes": ["Safety incidents (IR / OSHA): showing 50 most recent of 61"],
}


def test_build_corpus_merges_native_sources_and_indexes_them():
    corpus = bp.build_corpus("Hillcrest", _CTX, _docs(), native=_NATIVE)
    assert "incidents" in corpus["sources"] and "er_cases" in corpus["sources"]
    assert corpus["index"]["incident:aaaa"]["source"] == "incidents"
    assert corpus["index"]["er_case:bbbb"]["source_label"] == "Employee-relations cases"
    # native truncation notes carry through
    assert any("showing 50 most recent" in n for n in corpus["notes"])
    # on-platform sessions must NOT get the off-platform upsell note
    assert not any("Off-platform client" in n for n in corpus["notes"])
    # source ordering: native sits between platform and documents
    keys = list(corpus["sources"])
    assert keys.index("platform") < keys.index("incidents") < keys.index("documents")


def test_build_corpus_external_gets_upsell_note():
    corpus = bp.build_corpus("Hillcrest", _CTX, _docs(), native=None)
    assert any("Off-platform client" in n for n in corpus["notes"])
    assert "incidents" not in corpus["sources"]


def test_platform_records_expected_cids():
    cids = {r["cid"] for r in bp._platform_records(_CTX)}
    assert "platform:profile" in cids
    assert "platform:wc" in cids
    assert "platform:epl" in cids
    assert "platform:epl.pay_transparency" in cids
    assert "platform:controls" in cids
    assert "platform:readiness" in cids
    assert "platform:venue" in cids
    assert "platform:limits.gl" in cids
    assert "platform:limits.auto" not in cids          # empty line skipped
    assert "platform:exclusions.0" in cids
    assert "platform:lossdev.wc.2024-2025" in cids
    assert "platform:property" in cids


def test_platform_records_empty_ctx_emits_nothing():
    assert bp._platform_records({}) == []
    assert bp._platform_records(None) == []
    # external-style ctx: no controls/readiness/limits sections at all
    ext_ctx = {"name": "OffPlat Co", "state": "TX",
               "wc": {"trir": 3.0}, "epl": {"score": 50, "band": "low", "factors": []}}
    cids = {r["cid"] for r in bp._platform_records(ext_ctx)}
    assert "platform:controls" not in cids
    assert "platform:readiness" not in cids
    assert not any(c.startswith("platform:limits.") for c in cids)


# Property sub-structures + composite index, as `_tenant_context` builds them
# (property_cat.summarize / property_exposure.portfolio_exposure /
# property_recommendations.build_plan / property_risk.portfolio_risk /
# risk_index.compute_risk_index). Off-platform clients have none of these.
_PROP_CTX = {
    **_CTX,
    "property": {
        "rollup": {"building_count": 3, "total_tiv": 12_500_000,
                   "worst_cope_grade": "C", "insured_to_value_pct": 84},
        "cat": {"worst_tier": "high", "worst_peril": "wildfire",
                "worst_peril_documented": False,
                "by_peril": {"flood": "moderate", "wildfire": "high"},
                "by_peril_detail": {}, "documented_probability_perils": ["flood", "quake"],
                "severe_high_count": 1, "buildings_total": 3, "buildings_geocoded": 2},
        "exposure": {"total_aal": 41_000, "worst_pml": 3_100_000,
                     "worst_pml_peril": "wildfire", "coinsurance_shortfall": 900_000,
                     "by_peril": {}, "buildings": {"b1": {"aal": 1}}, "basis": "directional"},
        "plan": {"fixes": [
            {"key": "sprinkler", "label": "Add sprinklers — Building A", "severity": "high",
             "detail": "Un-sprinklered frame.", "impact": "COPE +12",
             "building_id": "b1", "building_name": "Building A"},
            {"key": "itv", "label": "Raise insured value", "severity": "medium",
             "detail": "ITV 84%.", "impact": "$900,000 shortfall"},
        ], "summary": {"total": 2, "by_severity": {"high": 1, "medium": 1}, "shown": 2}},
        "risk": {"score": 58, "grade": "C", "risk_level": "elevated", "rated": 3,
                 "by_building": {"b1": {"score": 41}},
                 "top_risks": [{"building_id": "b1", "name": "Building A", "tiv": 5_000_000,
                                "score": 41, "grade": "D", "risk_level": "high"}]},
    },
    "risk_index": {
        "company_id": "c1", "index": 64, "band": "adequate",
        "components": [
            {"key": "wc", "label": "Workers' Comp", "weight": 0.35, "score": 70,
             "detail": "TRIR 4.2 vs benchmark", "confidence": "high"},
            {"key": "property", "label": "Commercial Property", "weight": 0.15, "score": 58,
             "detail": "COPE C", "confidence": "low"},
            {"key": "epl", "label": "EPL", "weight": 0.3, "score": None,
             "detail": "unscored", "confidence": "low"},
        ],
        "top_fixes": [], "coverage": 0.85,
        "components_missing": [{"key": "compliance", "label": "Compliance", "weight": 0.2}],
        "index_confidence": "low", "index_low": 55, "index_high": 73, "index_sigma": 4.6,
    },
}


def test_platform_records_property_substructures():
    recs = {r["cid"]: r for r in bp._platform_records(_PROP_CTX)}
    assert "platform:property" in recs                      # rollup still emitted
    assert "platform:property.cat" in recs
    assert "platform:property.exposure" in recs
    assert "platform:property.plan.0" in recs
    assert "platform:property.plan.1" in recs
    assert "platform:property.risk" in recs

    cat = recs["platform:property.cat"]["summary"].lower()
    assert "high" in cat and "wildfire" in cat
    assert "1 of 3" in cat and "2/3 geocoded" in cat
    # a directional tier must not read as a documented probability
    assert "directional baseline" in cat

    exposure = recs["platform:property.exposure"]["summary"]
    assert "41,000" in exposure and "3,100,000" in exposure and "900,000" in exposure

    assert "Add sprinklers" in recs["platform:property.plan.0"]["summary"]
    assert "high" in recs["platform:property.plan.0"]["summary"].lower()
    risk = recs["platform:property.risk"]["summary"]
    assert "58" in risk and "Building A" in risk


def test_platform_records_risk_index():
    recs = {r["cid"]: r for r in bp._platform_records(_PROP_CTX)}
    head = recs["platform:risk"]["summary"]
    assert "64/100" in head and "adequate" in head.lower()
    assert "55–73" in head                       # uncertainty band carried
    assert "85%" in head                         # coverage
    assert "Compliance" in head                  # unscored component named
    assert "platform:risk.wc" in recs and "platform:risk.property" in recs
    assert "platform:risk.epl" not in recs       # score None → no record
    assert "70/100" in recs["platform:risk.wc"]["summary"]


def test_platform_records_property_partials_emit_nothing():
    # None scores / missing sections must emit no half-filled record.
    ctx = {"property": {"cat": {"worst_tier": None, "by_peril": {}},
                        "risk": {"score": None, "top_risks": []},
                        "exposure": {"total_aal": 0, "worst_pml": 0,
                                     "coinsurance_shortfall": 0},
                        "plan": {"fixes": []}},
           "risk_index": {"index": None, "components": []}}
    cids = {r["cid"] for r in bp._platform_records(ctx)}
    assert not any(c.startswith("platform:property") for c in cids)
    assert not any(c.startswith("platform:risk") for c in cids)


def test_platform_records_external_property_shape_is_inert():
    # `_external_context` puts a flat broker-entered snapshot under `property`
    # (no cat/exposure/plan/risk keys) — it must degrade, never raise.
    ext_ctx = {"name": "OffPlat Co", "state": "TX",
               "wc": {"trir": 3.0}, "epl": {"score": 50, "band": "low", "factors": []},
               "property": {"building_count": 2, "total_tiv": 4_000_000,
                            "cat": "not-a-dict", "plan": ["junk"], "risk": None,
                            "exposure": 7}}
    cids = {r["cid"] for r in bp._platform_records(ext_ctx)}
    assert not any(c.startswith("platform:property.") for c in cids)
    assert not any(c.startswith("platform:risk") for c in cids)
    # junk in every optional slot still never raises
    for junk in ({"property": "string"}, {"property": ["list"]}, {"risk_index": "nope"},
                 {"property": {"plan": {"fixes": ["str", None, 3]}}}):
        bp._platform_records(junk)


def test_build_corpus_indexes_property_and_risk_records():
    corpus = bp.build_corpus("Hillcrest", _PROP_CTX, _docs())
    for cid in ("platform:property.cat", "platform:property.plan.0", "platform:risk",
                "platform:risk.property"):
        assert cid in corpus["index"], cid
        assert corpus["index"][cid]["source"] == "platform"


def test_doc_records_statuses():
    doc_recs, fig_recs, notes = bp._doc_records(_docs())
    cids = {r["cid"] for r in doc_recs}
    assert "doc:11111111-1111-1111-1111-111111111111" in cids
    assert "doc:22222222-2222-2222-2222-222222222222" in cids   # text_only still citable
    assert "doc:33333333-3333-3333-3333-333333333333" not in cids  # failed → note
    assert "doc:44444444-4444-4444-4444-444444444444" not in cids  # processing → note
    assert len(notes) == 2
    # docfig cids: deterministic parent.uuid.position
    fig_cids = [r["cid"] for r in fig_recs]
    assert fig_cids == ["docfig:11111111-1111-1111-1111-111111111111.0",
                        "docfig:11111111-1111-1111-1111-111111111111.1"]


def test_doc_records_extraction_as_json_string():
    doc = {"id": "55555555-5555-5555-5555-555555555555", "filename": "x.pdf",
           "status": "ready", "created_at": None,
           "extraction": '{"summary": "S.", "key_figures": [{"label": "P", "value": "1"}]}',
           "extracted_text": "t"}
    doc_recs, fig_recs, _ = bp._doc_records([doc])
    assert doc_recs[0]["summary"].startswith("S.")
    assert fig_recs[0]["cid"].endswith(".0")


# --- citation gate over the combined index -----------------------------------

def test_validate_citations_over_pilot_index():
    corpus = bp.build_corpus("Hillcrest", _CTX, _docs())
    emap = [
        {"point": "real", "cited_ids": [
            "platform:wc", "platform:epl.pay_transparency",
            "doc:11111111-1111-1111-1111-111111111111",
            "docfig:11111111-1111-1111-1111-111111111111.1"]},
        {"point": "mixed", "cited_ids": [
            "doc:deadbeef-dead-dead-dead-deaddeadbeef", "platform:nope", "platform:wc"]},
    ]
    clean, dropped = validate_citations(emap, corpus["index"])
    assert clean[0]["cited_ids"] == emap[0]["cited_ids"]
    assert clean[1]["cited_ids"] == ["platform:wc"]
    assert set(dropped) == {"doc:deadbeef-dead-dead-dead-deaddeadbeef", "platform:nope"}


# --- corpus text caps ---------------------------------------------------------

def test_corpus_text_caps_doc_text():
    docs = [
        {"id": f"00000000-0000-0000-0000-00000000000{i}", "filename": f"d{i}.pdf",
         "status": "ready", "created_at": None,
         "extraction": {"summary": f"Doc {i}.", "key_figures": [], "notable": []},
         "extracted_text": "A" * (bp._DOC_TEXT_CAP + 5_000)}
        for i in range(8)
    ]
    corpus = bp.build_corpus("X", {}, docs)
    text = bp._corpus_text(corpus, docs)
    # only the most recent _MAX_DOC_TEXT_BLOCKS docs get raw-text blocks
    assert text.count("### DOCUMENT TEXT") == bp._MAX_DOC_TEXT_BLOCKS
    # each block clipped + truncation note
    assert "…(truncated)" in text
    longest_run = max(len(s) for s in text.split("\n"))
    assert longest_run <= bp._DOC_TEXT_CAP + len(" …(truncated)")


def test_corpus_text_empty():
    corpus = bp.build_corpus("X", {}, [])
    assert "(no records or documents in scope)" in bp._corpus_text(corpus, [])


# --- memo helpers -------------------------------------------------------------

# --- starter templates ("modes") ---------------------------------------------

def test_template_catalog_shape_and_unique_keys():
    cat = bp.template_catalog()
    assert cat, "catalog must not be empty"
    keys = [t["key"] for t in cat]
    assert len(keys) == len(set(keys)), "template keys must be unique"
    for t in cat:
        for field in ("key", "label", "description", "title"):
            assert isinstance(t[field], str) and t[field].strip(), f"{t.get('key')}.{field} empty"
        assert t["starters"] and all(isinstance(s, str) and s.strip() for s in t["starters"])
        # the public catalog never leaks the internal system-prompt directive
        assert "focus" not in t


def test_get_template_and_validity():
    known = bp.PILOT_TEMPLATES[0]["key"]
    tmpl = bp.get_template(known)
    assert tmpl is not None and tmpl["key"] == known
    assert "focus" not in tmpl                       # public shape only
    assert bp.get_template("nope") is None
    assert bp.get_template(None) is None
    assert bp.get_template("") is None               # blank → open analysis


def test_get_template_starters_are_copies():
    # the public projection must not alias the module catalog's list
    known = bp.PILOT_TEMPLATES[0]["key"]
    a = bp.get_template(known)
    a["starters"].append("mutation")
    b = bp.get_template(known)
    assert "mutation" not in b["starters"]


def test_mode_focus_lookup():
    known = bp.PILOT_TEMPLATES[0]["key"]
    focus = bp._mode_focus(known)
    assert "SESSION MODE" in focus
    assert bp._mode_focus("nope") == ""
    assert bp._mode_focus(None) == ""


def test_build_prompt_injects_mode_focus_only_when_set():
    corpus = bp.build_corpus("X", {}, [])
    known = bp.PILOT_TEMPLATES[0]
    moded = {"title": "T", "subject_kind": "company", "template_key": known["key"]}
    open_ = {"title": "T", "subject_kind": "company"}
    p_moded = bp._build_prompt(moded, "Acme", [], corpus, [], "hi")
    p_open = bp._build_prompt(open_, "Acme", [], corpus, [], "hi")
    assert known["focus"] in p_moded
    assert "SESSION MODE" in p_moded
    assert "SESSION MODE" not in p_open


def test_build_prompt_renders_scope_notes():
    """Corpus notes are the ONLY channel that tells the analyst what it was not
    given — an absent record is otherwise indistinguishable from one that doesn't
    exist. They used to reach the memo but never the model."""
    corpus = bp.build_corpus("X", {}, [])
    corpus["notes"].append("The loss run has NOT been provided.")
    prompt = bp._build_prompt({"title": "T", "subject_kind": "company"},
                              "Acme", [], corpus, [], "hi")
    assert "SCOPE NOTES" in prompt
    assert "The loss run has NOT been provided." in prompt


def test_build_prompt_omits_scope_block_when_no_notes():
    corpus = {"sources": {}, "index": {}, "notes": []}
    prompt = bp._build_prompt({"title": "T", "subject_kind": "company"},
                              "Acme", [], corpus, [], "hi")
    assert "SCOPE NOTES" not in prompt


def test_memo_html_shows_mode_label():
    corpus = bp.build_corpus("Hillcrest", _CTX, _docs())
    memo = {"assistant_text": "x", "evidence_map": [], "open_questions": []}
    known = bp.PILOT_TEMPLATES[0]
    session = {"title": "Contract review — Hillcrest", "subject_kind": "company",
               "template_key": known["key"]}
    html = bp._memo_html(session, "Hillcrest Senior Living", corpus, memo, _docs())
    assert known["label"] in html


def test_memo_html_renders_without_error():
    corpus = bp.build_corpus("Hillcrest", _CTX, _docs())
    memo = {
        "assistant_text": "Premium on the dec page exceeds the loss-supported level.",
        "evidence_map": [{"point": "EMR is 1.18",
                          "cited_ids": ["platform:wc",
                                        "docfig:11111111-1111-1111-1111-111111111111.0",
                                        "platform:gone.away"]}],
        "open_questions": ["Obtain the 2023 valuation."],
    }
    session = {"title": "Renewal review — 2026", "subject_kind": "company"}
    html = bp._memo_html(session, "Hillcrest Senior Living", corpus, memo, _docs(),
                         broker_name="Acme Insurance Partners")
    assert "Client Risk Analysis Memo" in html
    assert "Hillcrest Senior Living" in html
    assert bp._GONE in html                       # stale cid rendered explicitly
    assert "Travelers WC loss run" in html        # doc appendix from stored extraction
    assert "Appendix — Platform data: Wc" in html # cited platform section appendix
    assert "ATTORNEY WORK PRODUCT" not in html    # legal-pilot watermark not inherited


# --- structured answer: coercion, citation gate, memo layout ------------------

def test_coerce_turn_clamps_every_bucket():
    out = bp._coerce_turn({
        "assistant_text": "  Limits trail the contract requirements.  ",
        "key_questions": ["q" * 500, "", None, "Which carrier wrote 2025?"] + ["extra"] * 20,
        "considerations": [{"point": "p" * 900, "cited_ids": ["platform:wc", 7]},
                           {"point": "", "cited_ids": []},   # pointless → dropped
                           "junk"],
        "gaps": [{"point": "GL sits below the MSA requirement",
                  "severity": "HIGH", "cited_ids": ["clause:1"]},
                 {"point": "No waiver of subrogation", "severity": "catastrophic",
                  "cited_ids": ["platform:limits.gl"]}],
    })
    assert out["assistant_text"] == "Limits trail the contract requirements."
    assert len(out["key_questions"]) <= bp._MAX_QUESTIONS
    assert all(q and len(q) <= bp._QUESTION_CAP for q in out["key_questions"])
    # one consideration survives; point capped; non-str cited id dropped
    assert len(out["considerations"]) == 1
    assert len(out["considerations"][0]["point"]) == bp._FINDING_POINT_CAP
    assert out["gaps"][0]["severity"] == "high"     # normalized
    assert out["gaps"][1]["severity"] is None       # off-whitelist → unranked, not guessed


def test_coerce_turn_falls_back_to_legacy_open_questions():
    out = bp._coerce_turn({"assistant_text": "x", "open_questions": ["Obtain the loss run."]})
    assert out["key_questions"] == ["Obtain the loss run."]
    assert out["considerations"] == [] and out["gaps"] == []


def test_coerce_turn_never_raises_on_junk():
    for junk in (None, [], "string", 42, {"gaps": "nope", "key_questions": 3}):
        out = bp._coerce_turn(junk)  # type: ignore[arg-type]
        assert out["gaps"] == [] and out["considerations"] == [] and out["key_questions"] == []


def test_gate_preserves_severity_and_drops_invented_ids():
    index = bp.build_corpus("Hillcrest", _CTX, _docs())["index"]
    real = next(iter(index))
    clean, dropped = bp._gate(
        [{"point": "gap", "severity": "high", "cited_ids": [real, "platform:invented"]}], index)
    assert clean[0]["severity"] == "high"          # key the shared gate doesn't know about
    assert clean[0]["cited_ids"] == [real]
    assert dropped == ["platform:invented"]


def test_cited_ids_spans_gaps_and_considerations():
    memo = {
        "evidence_map": [{"point": "a", "cited_ids": ["platform:wc"]}],
        "gaps": [{"point": "b", "cited_ids": ["clause:9", "platform:wc"]}],  # dupe collapses
        "considerations": [{"point": "c", "cited_ids": ["platform:epl"]}],
    }
    # a record cited ONLY by a gap must still reach the footnote/appendix set
    assert bp._cited_ids(memo) == ["platform:wc", "clause:9", "platform:epl"]


def test_memo_html_renders_structured_sections_in_order():
    corpus = bp.build_corpus("Hillcrest", _CTX, _docs())
    memo = {
        "assistant_text": "Carried GL trails what the MSA requires.",
        "key_questions": ["Which carrier wrote the 2025 policy?"],
        "considerations": [{"point": "The account markets better with the MSA cured",
                            "cited_ids": ["platform:wc"]}],
        "gaps": [{"point": "Low-ranked gap", "severity": "low", "cited_ids": ["platform:wc"]},
                 {"point": "Unranked gap", "severity": None, "cited_ids": ["platform:wc"]},
                 {"point": "Critical gap", "severity": "high", "cited_ids": ["platform:epl"]}],
        "evidence_map": [{"point": "EMR is 1.18", "cited_ids": ["platform:wc"]}],
    }
    html = bp._memo_html({"title": "Contract review", "subject_kind": "company"},
                         "Hillcrest Senior Living", corpus, memo, _docs())
    for heading in ("Key questions", "Strategic considerations",
                    "Gaps identified in the record", "Observations grounded in the material"):
        assert f"<h2>{heading}</h2>" in html
    # ticket order: questions → considerations → gaps
    assert (html.index("Key questions") < html.index("Strategic considerations")
            < html.index("Gaps identified in the record"))
    # severity ranks the gaps; the unranked one sorts last rather than vanishing
    assert html.index("Critical gap") < html.index("Low-ranked gap") < html.index("Unranked gap")
    assert "sev-high" in html and "sev-low" in html
