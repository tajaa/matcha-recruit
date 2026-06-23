"""Directional $ exposure for the Statement of Values — turns TIV + catastrophe tier
+ the insurance-to-value gap into dollar figures a business can act on:

  - **AAL** (average annual loss) — expected $ lost per year to catastrophe, per peril,
  - **PML** (probable maximum loss) — the $ damage of a benchmark severe event, per peril,
    aggregated across buildings exposed to the same peril (accumulation),
  - **coinsurance shortfall** — additional insured value needed to satisfy a 90%
    coinsurance clause (the under-insurance the ITV check flags).

All **directional / illustrative**, NOT actuarial: the damage ratios are coarse
benchmarks keyed by the shared severe…low tier vocabulary, not a cat model. Pure
helpers (unit-tested, no DB) + a thin async wrapper. Everything is clearly labeled
"directional estimate" wherever it surfaces.
"""

from typing import Optional
from uuid import UUID

from app.matcha.services.property_sov import building_tiv, itv_ratio

# Benchmark severe-event PML as a fraction of TIV, per peril (illustrative).
_PML_SEVERE = {"quake": 0.50, "flood": 0.45, "wildfire": 0.60, "wind": 0.35}
# Scale the severe-event PML down by hazard tier.
_TIER_PML_SCALE = {"severe": 1.0, "high": 0.6, "elevated": 0.3, "moderate": 0.12, "low": 0.03}
# Annual probability of the benchmark event by tier — AAL ≈ PML × this (crude, directional).
_TIER_ANNUAL_PROB = {"severe": 0.04, "high": 0.02, "elevated": 0.008, "moderate": 0.003, "low": 0.0005}
_COINSURANCE_PCT = 0.90
BASIS = "directional estimate"


def peril_pml(tiv: float, peril: str, tier: Optional[str]) -> float:
    """Probable maximum loss $ for one peril at one building (benchmark severe event
    scaled by hazard tier). Pure."""
    if not tier or tier not in _TIER_PML_SCALE:
        return 0.0
    return float(tiv) * _PML_SEVERE.get(peril, 0.35) * _TIER_PML_SCALE[tier]


def peril_aal(tiv: float, peril: str, tier: Optional[str]) -> float:
    """Average annual loss $ for one peril ≈ PML × annual event probability. Pure."""
    if not tier or tier not in _TIER_ANNUAL_PROB:
        return 0.0
    return peril_pml(tiv, peril, tier) * _TIER_ANNUAL_PROB[tier]


def coinsurance_shortfall(insured_value, replacement_cost, coinsurance_pct: float = _COINSURANCE_PCT) -> float:
    """Additional insured value needed to satisfy a coinsurance clause = the
    under-insurance $ the ITV check flags. 0 when compliant or no replacement cost. Pure."""
    rc = float(replacement_cost) if replacement_cost else 0.0
    if rc <= 0:
        return 0.0
    required = coinsurance_pct * rc
    carried = float(insured_value or 0)
    return round(max(0.0, required - carried), 2)


def _tier_of(perils: list[dict], peril: str) -> Optional[str]:
    for p in perils:
        if p.get("peril") == peril and p.get("tier"):
            return p["tier"]
    return None


def building_exposure(b: dict) -> dict:
    """Per-building exposure from a serialized SOV building (carries ``tiv``, ``perils``,
    ``insured_value``, ``replacement_cost``). Pure.

    AAL sums across perils (independent); worst_pml is the single worst peril event
    (you don't lose to a flood and a quake the same instant)."""
    tiv = b.get("tiv")
    if tiv is None:
        tiv = building_tiv(b)
    perils = b.get("perils") or []
    by_peril: dict[str, dict] = {}
    for peril in _PML_SEVERE:
        tier = _tier_of(perils, peril)
        if not tier:
            continue
        by_peril[peril] = {"aal": round(peril_aal(tiv, peril, tier)), "pml": round(peril_pml(tiv, peril, tier)), "tier": tier}
    aal = round(sum(v["aal"] for v in by_peril.values()))
    worst_pml = max((v["pml"] for v in by_peril.values()), default=0)
    return {
        "aal": aal,
        "worst_pml": worst_pml,
        "coinsurance_shortfall": coinsurance_shortfall(b.get("insured_value"), b.get("replacement_cost")),
        "itv_ratio": itv_ratio(b.get("insured_value"), b.get("replacement_cost")),
        "by_peril": by_peril,
    }


def portfolio_exposure(buildings: list[dict]) -> dict:
    """Roll per-building exposure into a portfolio view. Pure.

    Portfolio PML aggregates by peril ACROSS buildings (one event hits every building
    exposed to that peril — the accumulation a property underwriter prices), then the
    worst peril total is the headline PML."""
    per_building: dict[str, dict] = {}
    by_peril_aal: dict[str, float] = {}
    by_peril_pml: dict[str, float] = {}
    total_shortfall = 0.0
    for b in buildings:
        ex = building_exposure(b)
        per_building[b["id"]] = {
            "aal": ex["aal"], "worst_pml": ex["worst_pml"],
            "coinsurance_shortfall": ex["coinsurance_shortfall"], "by_peril": ex["by_peril"],
        }
        total_shortfall += ex["coinsurance_shortfall"]
        for peril, v in ex["by_peril"].items():
            by_peril_aal[peril] = by_peril_aal.get(peril, 0) + v["aal"]
            by_peril_pml[peril] = by_peril_pml.get(peril, 0) + v["pml"]
    total_aal = round(sum(by_peril_aal.values()))
    worst_peril = max(by_peril_pml, key=lambda p: by_peril_pml[p]) if by_peril_pml else None
    worst_pml = round(by_peril_pml[worst_peril]) if worst_peril else 0
    return {
        "total_aal": total_aal,
        "worst_pml": worst_pml,
        "worst_pml_peril": worst_peril,
        "coinsurance_shortfall": round(total_shortfall),
        "by_peril": {p: {"aal": round(by_peril_aal[p]), "pml": round(by_peril_pml[p])} for p in by_peril_pml},
        "buildings": per_building,
        "basis": BASIS,
    }


async def build_exposure(conn, company_id: UUID, *, buildings: Optional[list[dict]] = None) -> dict:
    """Portfolio exposure for a company. Reuses already-serialized buildings when the
    caller has them (the /sov route does), else fetches via build_sov. Never raises."""
    try:
        if buildings is None:
            from app.matcha.services import property_sov as sov
            buildings = (await sov.build_sov(conn, company_id)).get("buildings") or []
        return portfolio_exposure(buildings)
    except Exception:  # noqa: BLE001 — best-effort, mirror the property service contract
        return portfolio_exposure([])
