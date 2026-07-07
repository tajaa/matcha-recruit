"""Regression tests pinning the fixes from the 2026-07-07 review of the Risk
Pilot engine — each test reproduces a bug that was CONFIRMED by execution
during review and asserts the corrected behavior.

Pure engine only (no DB / no Gemini / no app boot), like test_risk_analyzers.
"""

import math

from app.matcha.services import risk_analyzers as R
from app.matcha.services.risk_analyzers import base as B
from app.matcha.services.risk_analyzers import corpus as C


def _norm(csv: bytes, filename: str = "x.csv", **kw):
    return R.normalize(R.parse_tabular(csv, "csv", kw.pop("force_orientation", None)),
                       source_kind="csv", filename=filename, **kw)


# --- comparison: column alignment + % sign ----------------------------------

def test_comparison_values_align_to_present_datasets():
    # Dataset A lacks the pack entirely — B and C must keep THEIR OWN values.
    a = {"id": "a", "label": "A", "metrics": {}}
    b = {"id": "b", "label": "B", "metrics": {"financial_ratios":
         {"label": "FR", "values": {"net_margin": 0.10}}}}
    c = {"id": "c", "label": "C", "metrics": {"financial_ratios":
         {"label": "FR", "values": {"net_margin": 0.20}}}}
    cmp = R.build_comparison("c1", [a, b, c])
    table = cmp["tables"][0]
    assert table["columns"][:3] == ["Metric", "B", "C"]
    row = table["rows"][0]
    # B's column shows B's value, C's column shows C's value — nothing shifted.
    assert row[1] == "0.1" and row[2] == "0.2"


def test_comparison_pct_change_positive_for_loss_to_profit():
    d1 = {"id": "a", "label": "FY22", "metrics": {"financial_ratios":
          {"label": "FR", "values": {"net_income": -100.0}}}}
    d2 = {"id": "b", "label": "FY23", "metrics": {"financial_ratios":
          {"label": "FR", "values": {"net_income": 50.0}}}}
    cmp = R.build_comparison("c1", [d1, d2])
    row = cmp["tables"][0]["rows"][0]
    assert row[-2] == "150.0%"  # improvement reads positive, not -150%


# --- insurance: per-period alignment ----------------------------------------

def test_insurance_skips_misaligned_periods():
    # Asymmetric gaps: only 2023 has BOTH incurred and premium.
    ins = (b"metric,2021,2022,2023\n"
           b"Earned Premium,,1000000,1200000\n"
           b"Incurred Losses,600000,,900000\n"
           b"Claim Count,120,140,160\n")
    norm = _norm(ins, "lr.csv")
    m = R.run_analyzers(norm, {}, "d")
    ins_block = m["insurance_loss"]
    by_title = {t["title"]: t for t in ins_block["tables"]}
    lr_table = by_title.get("Loss ratio by period")
    assert lr_table is not None and len(lr_table["rows"]) == 1
    assert lr_table["rows"][0][0] == "2023" and lr_table["rows"][0][1] == "75.0%"
    # A single aligned point can't produce a citable loss-ratio-volatility.
    assert not any("loss_ratio_volatility" in r["cid"] for r in ins_block["records"])


# --- financial ratios: quick ratio needs inventory ---------------------------

def test_quick_ratio_unknown_without_inventory():
    fin = (b"line,FY23\nRevenue,1500\nNet Income,180\nCurrent Assets,950\n"
           b"Current Liabilities,500\nTotal Equity,1200\nTotal Liabilities,1300\n")
    m = R.run_analyzers(_norm(fin, "p.csv"), {}, "d")
    vals = m["financial_ratios"]["values"]
    assert "quick_ratio" not in vals              # unknown, not == current ratio
    assert abs(vals["current_ratio"] - 1.9) < 1e-9


# --- parse: header / period-index heuristics ---------------------------------

def test_headerless_date_csv_keeps_first_row():
    csv = b"2021-01-01,100\n2021-02-01,110\n2021-03-01,99\n"
    parsed = R.parse_tabular(csv, "csv")
    assert parsed["periods"] == ["2021-01-01", "2021-02-01", "2021-03-01"]
    (only_series,) = parsed["series"].values()
    assert only_series == [100.0, 110.0, 99.0]    # first observation intact


def test_cumulative_int_column_stays_a_series():
    csv = b"cumulative_claims,paid\n3,100\n7,200\n12,350\n20,500\n"
    parsed = R.parse_tabular(csv, "csv")
    assert "cumulative_claims" in parsed["series"]
    assert parsed["periods"] is None


def test_year_column_is_still_a_period_axis():
    csv = b"year,price\n2021,100\n2022,110\n2023,120\n2024,130\n"
    parsed = R.parse_tabular(csv, "csv")
    assert parsed["periods"] == ["2021", "2022", "2023", "2024"]
    assert "year" not in parsed["series"]


def test_force_orientation_rows():
    # Row labels match <2 roles, so auto-detect keeps columns; force 'rows'.
    csv = b"line,FY21,FY22\nWidgets,10,20\nGadgets,30,40\n"
    auto = R.parse_tabular(csv, "csv")
    assert "Widgets" not in auto["series"]
    forced = R.parse_tabular(csv, "csv", "rows")
    assert forced["series"]["Widgets"] == [10.0, 20.0]
    assert forced["periods"] == ["FY21", "FY22"]


# --- parse: full-resolution compute, capped persistence ----------------------

def test_metrics_full_resolution_then_downsample_for_storage():
    rows = "\n".join(str(100 + (i % 7)) for i in range(20_000))
    parsed = R.parse_tabular(f"px\n{rows}\n".encode(), "csv")
    (series,) = parsed["series"].values()
    assert len(series) == 20_000                  # parse keeps full resolution
    norm = R.normalize(parsed, source_kind="csv", filename="big.csv")
    stored = R.downsample_for_storage(norm)
    (stored_series,) = stored["series"].values()
    assert len(stored_series) <= 5_000
    assert stored["meta"]["truncated"] is True
    assert any("downsampled" in w for w in stored["meta"]["warnings"])


def test_no_truncation_flag_at_exactly_the_cap():
    rows = "\n".join(str(100 + (i % 7)) for i in range(5_000))
    norm = R.normalize(R.parse_tabular(f"px\n{rows}\n".encode(), "csv"),
                       source_kind="csv", filename="x.csv")
    stored = R.downsample_for_storage(norm)
    (stored_series,) = stored["series"].values()
    assert len(stored_series) == 5_000
    assert not stored["meta"].get("truncated")    # nothing was dropped


# --- base: non-finite coercion (NaN would break the ::jsonb cast) ------------

def test_to_float_drops_non_finite():
    assert B.to_float(float("nan")) is None
    assert B.to_float(float("inf")) is None or math.isfinite(B.to_float(float("inf")) or 0.0)
    assert B.to_float("NaN") is None
    assert B.to_float("1,234.5") == 1234.5


# --- volatility: corr cap + domain-role exclusion ----------------------------

def test_correlation_records_capped():
    cols = [f"s{i}" for i in range(12)]           # 66 pairs > cap of 40
    header = ",".join(cols)
    body = "\n".join(",".join(str(100 + ((i * (j + 3)) % 11)) for j in range(12)) for i in range(30))
    m = R.run_analyzers(_norm(f"{header}\n{body}\n".encode()), {}, "d")
    corr = [r for r in m["volatility_risk"]["records"] if r["cid"].startswith("corr:")]
    assert len(corr) <= 40
    assert any("strongest" in n for n in m["volatility_risk"].get("notes", []))


def test_volatility_skips_tail_metrics_for_domain_roles():
    fin = (b"line,FY21,FY22,FY23,FY24\nRevenue,1000,1200,1500,1400\n"
           b"COGS,600,700,850,800\nNet Income,80,120,180,150\n")
    m = R.run_analyzers(_norm(fin, "pnl.csv"), {}, "d")
    vol_records = m["volatility_risk"]["records"]
    # Revenue is role-mapped: descriptive stats yes, VaR/Sharpe no.
    assert any(r["cid"] == "series:d:revenue" for r in vol_records)
    assert not any(r["cid"].startswith("metric:d:revenue:var95") for r in vol_records)
    assert not any(":revenue:sharpe_like" in r["cid"] for r in vol_records)


# --- corpus: review gate + per-source cap ------------------------------------

def _doc_dataset(status: str) -> dict:
    extraction = {
        "kind": "financial_statement", "periods": ["FY22", "FY23"],
        "line_items": [
            {"label": "Revenue", "values": [1200, 1500], "unit": None, "page": 12},
            {"label": "Net Income", "values": [120, 180], "unit": None, "page": 12},
            {"label": "Current Assets", "values": [850, 950], "unit": None, "page": 30},
            {"label": "Current Liabilities", "values": [420, 500], "unit": None, "page": 30},
        ],
        "notes": [],
    }
    norm = R.normalize(R.parsed_from_extraction(extraction), source_kind="pdf", filename="10k.pdf")
    metrics = R.run_analyzers(norm, {}, "doc1")
    return {"id": "doc1", "filename": "10k.pdf", "source_kind": "pdf", "status": status,
            "normalized": norm, "metrics": metrics, "created_at": "2026-07-07"}


def test_needs_review_excludes_computed_metrics_from_corpus():
    corpus = R.build_corpus([_doc_dataset("needs_review")], [])
    cids = list(corpus["index"].keys())
    assert any(c.startswith("figure:doc1:") for c in cids)         # figures citable
    assert not any(c.startswith(("metric:", "ratio:", "corr:")) for c in cids)
    figs = [r for r in corpus["index"].values() if r["cid"].startswith("figure:")]
    assert all(r["summary"].startswith("[unverified]") for r in figs)
    assert any("excluded from analysis until" in n for n in corpus["notes"])
    # Once confirmed (ready), metrics become citable.
    ready = R.build_corpus([_doc_dataset("ready")], [])
    assert any(c.startswith("ratio:") for c in ready["index"])


def test_per_source_record_cap(monkeypatch):
    monkeypatch.setattr(C, "_PER_SOURCE_CAP", 5)
    csv = b"a,b,c\n1,2,3\n2,4,6\n3,6,9\n4,8,12\n"
    norm = _norm(csv)
    ds = {"id": "d1", "filename": "x.csv", "source_kind": "csv", "status": "ready",
          "normalized": norm, "metrics": R.run_analyzers(norm, {}, "d1"),
          "created_at": "2026-07-07"}
    corpus = R.build_corpus([ds], [])
    assert len(corpus["sources"]["ds:d1"]["records"]) == 5
    assert any("showing 5 of" in n for n in corpus["notes"])
