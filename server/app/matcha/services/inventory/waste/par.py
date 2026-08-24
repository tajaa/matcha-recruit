"""Pure deterministic par recommendation and safety gates."""

from decimal import Decimal
from typing import Optional


def recommend_par(*, lead_demand: Decimal, safety_demand: Decimal, daily_demand: list[Decimal], lead_time_days: int, shelf_life_days: Optional[int] = None, status: str = "ready") -> dict:
    demand_par = Decimal(str(lead_demand)) + Decimal(str(safety_demand))
    if status != "ready":
        return {"recommended_par": None, "par_basis": "no_demand" if status == "no_demand" else "insufficient",
                "demand_par": demand_par, "shelf_cap": None, "structural_deficit": False}
    shelf_cap = None
    if shelf_life_days:
        days = max(1, int(shelf_life_days))
        values = [Decimal(str(value)) for value in daily_demand]
        shelf_cap = sum(values[lead_time_days:lead_time_days + days], Decimal("0")) or sum(values[:days], Decimal("0"))
        if shelf_cap < demand_par:
            structural = shelf_cap < Decimal(str(lead_demand))
            return {"recommended_par": shelf_cap, "par_basis": "structural_deficit" if structural else "shelf_life",
                    "demand_par": demand_par, "shelf_cap": shelf_cap, "structural_deficit": structural}
    return {"recommended_par": demand_par, "par_basis": "demand", "demand_par": demand_par,
            "shelf_cap": shelf_cap, "structural_deficit": False}


def par_drift_pct(current_par: Optional[Decimal], recommended_par: Optional[Decimal]) -> Optional[Decimal]:
    if current_par is None or recommended_par is None or not Decimal(str(current_par)):
        return None
    return abs(Decimal(str(recommended_par)) - Decimal(str(current_par))) / Decimal(str(current_par))


def should_auto_apply(*, current_par: Optional[Decimal], recommended_par: Optional[Decimal], par_source: str, status: str, confidence: str, max_drift_pct: Decimal) -> tuple[bool, str]:
    if recommended_par is None:
        return False, "no_recommendation"
    if status != "ready":
        return False, "status_not_ready"
    if confidence == "low":
        return False, "low_confidence"
    if par_source != "auto":
        return False, "manual_par_pinned"
    if current_par is None:
        return True, "first_par"
    if (par_drift_pct(current_par, recommended_par) or Decimal("0")) > Decimal(str(max_drift_pct)):
        return False, "drift_exceeds_bound"
    return True, "within_bound"


def par_exceeds_shelf_capacity(par: Decimal, shelf_cap: Optional[Decimal]) -> bool:
    return shelf_cap is not None and Decimal(str(par)) > Decimal(str(shelf_cap))


# Refusal reasons a manager's EXPLICIT apply (mode in {manual,huume} + named
# item_ids) may override, upgrading the refusal to "manager_override". Kept
# separate from NEVER_OVERRIDABLE so a preview can tell a manager "you could
# override this" apart from "no override will ever apply here" — a UI must
# never re-derive this set itself, since drift here silently breaks that
# promise for callers still trusting the old boundary.
OVERRIDABLE = frozenset({"manual_par_pinned", "drift_exceeds_bound"})
NEVER_OVERRIDABLE = frozenset({
    "no_recommendation", "status_not_ready", "low_confidence", "par_exceeds_shelf_capacity",
})


def decide_par_line(*, current_par: Optional[Decimal], recommended_par: Optional[Decimal],
                     par_source: str, status: str, confidence: str,
                     shelf_cap_quantity: Optional[Decimal], max_drift_pct: Decimal,
                     explicit: bool) -> dict:
    """Single source of truth for the par gate — same order of operations
    apply_par_recommendations has always used: should_auto_apply, then an
    explicit-apply override upgrade, then the shelf-capacity check AFTER the
    allow (a par can only exceed shelf capacity once it would otherwise be
    applied). `explicit` = mode in {manual,huume} and item_ids is not None.
    Returns {allowed, reason, drift_pct, overridable} — pure, no I/O, shared
    by the writer (apply_par_recommendations) and the read-only preview
    (plan_par_recommendations) so the two can never drift apart."""
    if explicit:
        allowed, reason = should_auto_apply(
            current_par=current_par, recommended_par=recommended_par, par_source="auto",
            status=status, confidence=confidence, max_drift_pct=max_drift_pct,
        )
        if not allowed and reason in OVERRIDABLE:
            allowed, reason = True, "manager_override"
    else:
        allowed, reason = should_auto_apply(
            current_par=current_par, recommended_par=recommended_par, par_source=par_source,
            status=status, confidence=confidence, max_drift_pct=max_drift_pct,
        )
    if allowed and recommended_par is not None and par_exceeds_shelf_capacity(recommended_par, shelf_cap_quantity):
        allowed, reason = False, "par_exceeds_shelf_capacity"
    drift = par_drift_pct(current_par, recommended_par)
    overridable = (not allowed) and reason in OVERRIDABLE
    return {"allowed": allowed, "reason": reason, "drift_pct": drift, "overridable": overridable}
