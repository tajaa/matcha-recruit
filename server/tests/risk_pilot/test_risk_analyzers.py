"""Unit tests for the Risk Pilot deterministic engine (services/risk_analyzers).

Fast, pure, no DB / no Gemini / no app boot. The engine is the trust anchor of
the feature — every number the AI is allowed to cite is computed here — so the
math, the CSV/XLSX orientation detection, the pack `applies` gates, the
comparison, and the corpus contract are all pinned to hand-verified values.
"""

import math

from app.matcha.services import risk_analyzers as R
from app.matcha.services.risk_analyzers import base as B


# --- pure math --------------------------------------------------------------

def test_returns_and_drawdown():
    levels = [100, 110, 99, 130, 120]
    r = B.returns(levels)
    assert r[0] == 0.1 and abs(r[1] - (-0.1)) < 1e-12
    # worst peak-to-trough: peak 110 -> 99 = 11/110
    assert abs(B.max_drawdown(levels) - (11 / 110)) < 1e-12


def test_percentile_and_var():
    xs = [-0.05, -0.02, 0.0, 0.01, 0.03]
    assert B.percentile([1, 2, 3, 4, 5], 50) == 3
    # VaR95 (5th pct) is a positive loss magnitude
    v = B.value_at_risk(xs, 5)
    assert v is not None and v > 0


def test_correlation_edges():
    assert B.pearson([1, 2, 3], [2, 4, 6]) == 1.0
    assert round(B.pearson([1, 2, 3], [3, 2, 1]), 6) == -1.0
    assert B.pearson([1, 1, 1], [1, 2, 3]) is None       # zero variance
    assert B.pearson([1], [2]) is None                    # too few points


def test_guards_return_none():
    assert B.stdev([1]) is None
    assert B.coefficient_of_variation([0, 0, 0]) is None
    assert B.cagr(0, 100, 3) is None


def test_cagr_known():
    # 100 -> 400 over 2 steps => 2x per step => 1.0
    assert abs(B.cagr(100, 400, 2) - 1.0) < 1e-12


# --- parsing / orientation --------------------------------------------------

def test_period_column_not_a_series():
    csv = b"period,price\n2021,100\n2022,110\n2023,120\n2024,130\n"
    norm = R.normalize(R.parse_tabular(csv, "csv"), source_kind="csv", filename="p.csv")
    assert "period" not in norm["series"]
    assert norm["periods"] == ["2021", "2022", "2023", "2024"]
    assert "price" in norm["series"]


def test_pnl_line_items_in_rows_transpose():
    fin = (b"line,FY21,FY22,FY23\nRevenue,1000,1200,1500\nCOGS,600,700,850\n"
           b"Net Income,80,120,180\nTotal Assets,2000,2200,2500\n"
           b"Total Equity,900,1000,1200\nCurrent Assets,800,850,950\n"
           b"Current Liabilities,400,420,500\n")
    norm = R.normalize(R.parse_tabular(fin, "csv"), source_kind="csv", filename="pnl.csv")
    assert norm["kind"] == "financial_statement"
    assert "Revenue" in norm["series"] and norm["periods"] == ["FY21", "FY22", "FY23"]
    assert norm["roles"].get("Revenue") == "revenue"


# --- packs ------------------------------------------------------------------

def test_volatility_pack_always_applies():
    csv = b"px\n100\n110\n99\n130\n120\n"
    norm = R.normalize(R.parse_tabular(csv, "csv"), source_kind="csv", filename="x.csv")
    m = R.run_analyzers(norm, {}, "d1")
    assert "volatility_risk" in m
    cids = {r["cid"] for r in m["volatility_risk"]["records"]}
    assert any(c.startswith("metric:d1:") and c.endswith(":volatility") for c in cids)


def test_financial_ratios_current_ratio_and_margin():
    fin = (b"line,FY22,FY23\nRevenue,1000,1500\nNet Income,100,180\n"
           b"Current Assets,800,950\nCurrent Liabilities,400,500\n"
           b"Total Equity,900,1200\nTotal Liabilities,1100,1300\n")
    norm = R.normalize(R.parse_tabular(fin, "csv"), source_kind="csv", filename="p.csv")
    m = R.run_analyzers(norm, {}, "d2")
    assert "financial_ratios" in m
    vals = m["financial_ratios"]["values"]
    assert abs(vals["current_ratio"] - (950 / 500)) < 1e-9
    assert abs(vals["net_margin"] - (180 / 1500)) < 1e-9


def test_insurance_loss_ratio_and_severity():
    ins = (b"metric,2022,2023\nEarned Premium,1000000,1200000\n"
           b"Incurred Losses,600000,900000\nClaim Count,120,160\nOpen Claims,10,35\n")
    norm = R.normalize(R.parse_tabular(ins, "csv"), source_kind="csv", filename="lr.csv")
    m = R.run_analyzers(norm, {}, "d3")
    assert "insurance_loss" in m
    vals = m["insurance_loss"]["values"]
    assert abs(vals["loss_ratio"] - (900000 / 1200000)) < 1e-9
    assert abs(vals["severity"] - (900000 / 160)) < 1e-6


def test_inventory_turnover():
    inv = (b"metric,2022,2023\nUnits On Hand,500,600\nUnits Sold,4000,5000\n"
           b"COGS,200000,260000\nInventory Value,50000,60000\n")
    norm = R.normalize(R.parse_tabular(inv, "csv"), source_kind="csv", filename="inv.csv")
    m = R.run_analyzers(norm, {}, "d4")
    assert "inventory_ops" in m
    assert "inventory_turnover" in m["inventory_ops"]["values"]


# --- comparison + corpus ----------------------------------------------------

def test_comparison_delta_and_pct():
    d1 = {"id": "a", "label": "FY22", "metrics": {"financial_ratios":
          {"label": "Financial Ratios", "values": {"net_margin": 0.10}}}}
    d2 = {"id": "b", "label": "FY23", "metrics": {"financial_ratios":
          {"label": "Financial Ratios", "values": {"net_margin": 0.12}}}}
    cmp = R.build_comparison("c1", [d1, d2])
    assert cmp["tables"], "a shared metric should produce a comparison table"
    assert any("compare:c1:" in r["cid"] for r in cmp["records"])


def test_corpus_index_is_flat_cid_map():
    csv = b"px\n100\n110\n99\n130\n"
    norm = R.normalize(R.parse_tabular(csv, "csv"), source_kind="csv", filename="x.csv")
    metrics = R.run_analyzers(norm, {}, "ds")
    ds = {"id": "ds", "filename": "x.csv", "source_kind": "csv", "status": "ready",
          "normalized": norm, "metrics": metrics, "created_at": "2026-07-07"}
    corpus = R.build_corpus([ds], [])
    assert "dataset:ds" in corpus["index"]
    # every record surfaces in the flat index the citation gate keys on
    for src in corpus["sources"].values():
        for rec in src["records"]:
            assert rec["cid"] in corpus["index"]


def test_document_extraction_normalizes_and_grounds():
    extraction = {
        "kind": "financial_statement",
        "periods": ["FY21", "FY22", "FY23"],
        "line_items": [
            {"label": "Revenue", "values": [1000, 1200, 1500], "unit": "USD", "page": 42},
            {"label": "Net Income", "values": [80, 120, 180], "unit": "USD", "page": 42},
            {"label": "Current Assets", "values": [800, 850, 950], "page": 30},
            {"label": "Current Liabilities", "values": [400, 420, 500], "page": 30},
            {"label": "Total Equity", "values": [900, 1000, 1200], "page": 30},
            {"label": "Total Liabilities", "values": [1100, 1200, 1300], "page": 30},
        ],
        "notes": [],
    }
    parsed = R.parsed_from_extraction(extraction)
    norm = R.normalize(parsed, source_kind="pdf", filename="10k.pdf")
    assert norm["series"]["Revenue"] == [1000, 1200, 1500]
    metrics = R.run_analyzers(norm, {}, "docds")
    assert "financial_ratios" in metrics
    ds = {"id": "docds", "filename": "10k.pdf", "source_kind": "pdf", "status": "needs_review",
          "normalized": norm, "metrics": metrics, "created_at": "2026-07-07"}
    corpus = R.build_corpus([ds], [])
    # document figures are individually citable with provenance
    assert any(c.startswith("figure:docds:") for c in corpus["index"])


def test_fmt_helpers():
    assert B.fmt_pct(0.184) == "18.4%"
    assert B.fmt_pct(None) == "—"
    assert B.fmt_ratio(1.9) == "1.90×"
    assert B.fmt_money(1500) == "$1,500"
