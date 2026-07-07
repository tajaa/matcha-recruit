"""Tests for the Analysis Pilot general descriptive pack and the chat
edit-proposal gate (highlight-to-chat discrepancy corrections).

Pure engine only (no DB / no Gemini / no app boot), like test_analysis_packs.
"""

from app.matcha.services import analysis_packs as P
from app.matcha.services.analysis_packs.corpus import build_corpus, validate_edit_proposals


def _norm(csv: bytes, filename: str = "x.csv"):
    return P.normalize(P.parse_tabular(csv, "csv"), source_kind="csv", filename=filename)


_CSV = b"period,Revenue,Expenses\n2021,1000,700\n2022,1200,760\n2023,1500,900\n"


# --- general descriptive pack ------------------------------------------------

def test_general_pack_applies_to_any_numeric_dataset():
    m = P.run_analyzers(_norm(_CSV), {}, "d1")
    assert "general_stats" in m
    # registered FIRST so its records survive the corpus cap preferentially
    assert list(k for k in m if k != "_warnings")[0] == "general_stats"


def test_general_pack_latest_trend_extremes_hand_verified():
    g = P.run_analyzers(_norm(_CSV), {}, "d1")["general_stats"]
    summaries = [r["summary"] for r in g["records"]]
    # latest: 1500 in 2023, +25% vs 2022 (300/1200)
    assert any("latest (2023): 1,500 (+25.0% vs 2022)" in s for s in summaries)
    # trend: 1000→1500 = +50%; CAGR over 2 steps = sqrt(1.5)-1 ≈ 22.5%
    assert any("+50.0% 2021→2023" in s and "rising" in s and "CAGR +22.5%" in s for s in summaries)
    # extremes carry period labels
    assert any("peak: 1,500 in 2023" in s for s in summaries)
    assert any("low: 1,000 in 2021" in s for s in summaries)
    # totals + share (all-positive series)
    assert any("total across 3 points: 3,700" in s for s in summaries)
    assert any("Revenue — share of combined total: 61.1%" in s for s in summaries)


def test_general_pack_share_skipped_for_negative_totals():
    # PnL total is negative — shares of a mixed-sign combined total are
    # meaningless and must not become citable records.
    csv = b"period,PnL,Other\n2021,-100,50\n2022,20,60\n"
    g = P.run_analyzers(_norm(csv), {}, "d2")["general_stats"]
    assert not any(":share" in r["cid"] for r in g["records"])


def test_named_period_column_is_index_even_with_two_rows():
    # 2 rows is below the unnamed-integer-run threshold, but the column is
    # literally NAMED "period" — it must never be analyzed as a data series.
    csv = b"period,PnL\n2021,-100\n2022,20\n"
    norm = _norm(csv)
    assert "period" not in norm["series"]
    assert norm["periods"] == ["2021", "2022"]


def test_general_pack_cids_disjoint_from_other_packs():
    fin = (b"line,FY22,FY23\nRevenue,1000,1500\nNet Income,100,180\n"
           b"Current Assets,800,950\nCurrent Liabilities,400,500\n")
    m = P.run_analyzers(_norm(fin), {}, "d3")
    seen: set[str] = set()
    for pk, block in m.items():
        if pk == "_warnings":
            continue
        for r in block.get("records") or []:
            assert r["cid"] not in seen, f"cid collision: {r['cid']}"
            seen.add(r["cid"])


def test_general_pack_values_feed_comparisons():
    a = {"id": "a", "label": "FY22", "metrics": P.run_analyzers(
        _norm(b"period,Revenue\n2021,900\n2022,1000\n"), {}, "a")}
    b = {"id": "b", "label": "FY23", "metrics": P.run_analyzers(
        _norm(b"period,Revenue\n2022,1000\n2023,1500\n"), {}, "b")}
    cmp = P.build_comparison("c1", [a, b])
    # revenue_latest is a shared machine-readable key → comparable
    assert any("revenue latest" in r["summary"].lower().replace("_", " ")
               for r in cmp["records"])


# --- edit-proposal gate ------------------------------------------------------

_DATASETS = [
    {"id": "d1", "source_kind": "pdf", "extraction": {
        "periods": ["FY22", "FY23"],
        "line_items": [{"label": "Revenue", "values": [12000, 1500]}],
    }},
    {"id": "d2", "source_kind": "csv", "extraction": None},
]


def test_edit_gate_keeps_valid_proposal_with_current_value():
    clean, dropped = validate_edit_proposals([
        {"dataset_id": "d1", "label": "Revenue", "period": "FY22",
         "proposed_value": 1200, "reason": "unit misread"},
    ], _DATASETS)
    assert len(clean) == 1 and not dropped
    assert clean[0]["current_value"] == 12000 and clean[0]["proposed_value"] == 1200.0


def test_edit_gate_drops_every_invalid_shape():
    clean, dropped = validate_edit_proposals([
        {"dataset_id": "d1", "label": "Revenue", "period": "FY99", "proposed_value": 1},   # bad period
        {"dataset_id": "d1", "label": "Ghost", "period": "FY22", "proposed_value": 1},     # bad label
        {"dataset_id": "d2", "label": "Revenue", "period": "FY22", "proposed_value": 1},   # csv dataset
        {"dataset_id": "zz", "label": "Revenue", "period": "FY22", "proposed_value": 1},   # unknown dataset
        {"dataset_id": "d1", "label": "Revenue", "period": "FY23", "proposed_value": float("nan")},
        {"dataset_id": "d1", "label": "Revenue", "period": "FY23", "proposed_value": float("inf")},
        "not-a-dict",
    ], _DATASETS)
    assert clean == []
    assert len(dropped) == 6  # the non-dict is skipped entirely


def test_edit_gate_empty_inputs():
    assert validate_edit_proposals(None, _DATASETS) == ([], [])
    assert validate_edit_proposals([], []) == ([], [])


# --- focus cids resolve through the corpus index -----------------------------

def test_focus_cids_resolve_in_corpus_index():
    norm = _norm(_CSV)
    metrics = P.run_analyzers(norm, {}, "ds")
    ds = {"id": "ds", "filename": "x.csv", "source_kind": "csv", "status": "ready",
          "normalized": norm, "metrics": metrics, "created_at": "2026-07-07"}
    corpus = build_corpus([ds], [])
    # the route resolves focus cids against this index — a general-pack record
    # must be focusable, an unknown cid must not
    assert "metric:ds:revenue:trend" in corpus["index"]
    assert "metric:ds:ghost:trend" not in corpus["index"]
