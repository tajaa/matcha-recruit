"""BLS-enriched WC benchmark lookup (gap-analysis #22)."""

from app.matcha.services import wc_benchmarks as wb


def test_bls_module_loaded():
    assert wb.BLS_META["year"] == 2024
    assert wb.BLS_META["count"] > 500
    # 2-digit ranges expanded so a plain sector code resolves
    for sector in ("11", "23", "31", "44", "48", "62", "72"):
        assert sector in wb.BLS_INJURY_RATES


def test_bls_rate_walks_up_to_sector():
    # exact detailed code
    r = wb.bls_rate("6231")
    assert r and r["naics"] == "6231"
    # an over-specified 6-digit code with no row walks up to its parent
    r2 = wb.bls_rate("623199")
    assert r2 and r2["naics"] in ("6231", "623", "62")
    # nonsense → None
    assert wb.bls_rate("99") is None
    assert wb.bls_rate(None) is None


def test_detailed_naics_beats_sector():
    # nursing care (6231) is materially worse than the health-care sector (62)
    nursing = wb.lookup_benchmark("nursing")
    sector = wb.lookup_benchmark("healthcare")
    assert nursing["naics"] == "6231"
    assert nursing["trir"] > sector["trir"]  # detail captures the real exposure
    assert nursing["source"].startswith("BLS")


def test_sector_stays_two_digit_for_premium():
    # premium estimator keys on 2-digit sector — must remain 2 digits even when
    # the rate came from a detailed NAICS
    b = wb.lookup_benchmark("nursing")
    assert b["sector"] == "62"
    impact = wb.estimate_premium_impact(8.0, b["trir"], 100, b["sector"])
    assert impact is not None and impact["direction"] == "increase"


def test_explicit_naics_arg():
    b = wb.lookup_benchmark("ignored text", naics="622")
    assert b["naics"] == "622" and b["label"].lower().startswith("hospital")


def test_backward_compatible_keys():
    b = wb.lookup_benchmark("construction")
    assert {"sector", "trir", "dart"} <= set(b)  # callers rely on these


def test_unknown_industry_none():
    assert wb.lookup_benchmark("teleportation services") is None
    assert wb.lookup_benchmark(None) is None
