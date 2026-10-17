"""Deterministic ranking of a search's leads. Pure: no I/O, no model.

The person weighs four things: base pay, bonus, equity and fit. Each lead gets
a 0..1 score per component; the rank is the weighted sum, inside a band:

  0  base pay posted, in the search's currency
  1  base pay posted in another currency (amounts are never compared across
     currencies: base is scored within that currency)
  2  base pay not posted: base drops out and the other weights are
     renormalized. Undisclosed pay is unknown, never $0.
  8  screened a weaker fit than the search's fit floor (`fit_floor`): a
     search shows its strong matches first (`FIT_FLOOR`, 4/5) and adds the
     3/5 ones only when the person asks (`WIDER_FIT_FLOOR`). Not drafted for.
  9  marked irrelevant by screening, or dismissed by the person

A bonus is scored against the base it is paid on: its score is scaled by the
job's base score, so "30% bonus" on $237K counts for less than "30% bonus" on
$500K. Without that, a high bonus weight lifted a smaller package over a much
larger one (seen on dev: $200-275K + 25-35% above $500K).

Ties break on fit, then the newest posting, then id, so a re-rank of the same
data gives the same order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import comp as comp_mod

DEFAULT_WEIGHTS = {"base": 0.45, "bonus": 0.2, "equity": 0.2, "fit": 0.15}
# A search's first pass reads, ranks and drafts for its 4/5 and 5/5 matches;
# the person can widen it once to 3/5. Jobs under the floor rank in
# `BELOW_FLOOR_BAND`, after every match and before the screened-out ones.
FIT_FLOOR = 4
WIDER_FIT_FLOOR = 3
BELOW_FLOOR_BAND = 8
COMPONENTS = ("base", "bonus", "equity", "fit")
BONUS_CAP_PCT = 50.0
EQUITY_CAP_PCT = 2.0


@dataclass(frozen=True)
class Ranked:
    lead_id: str
    score: float
    rank: int
    band: int
    explain: dict


def clean_weights(weights: dict | None) -> dict[str, float]:
    out = {}
    for key in COMPONENTS:
        try:
            value = float((weights or {}).get(key, DEFAULT_WEIGHTS[key]))
        except (TypeError, ValueError):
            value = DEFAULT_WEIGHTS[key]
        out[key] = min(1.0, max(0.0, value))
    if sum(out.values()) <= 0:
        return dict(DEFAULT_WEIGHTS)
    return out


def _relative_to_best(values: dict[str, float]) -> dict[str, float]:
    """id -> each value as a share of the best one (0..1).

    Not a percentile: two jobs $10K apart should score 1.0 and 0.96, not 1 and 0,
    or a small base difference outweighs a large bonus and equity difference.
    """
    best = max(values.values(), default=0.0)
    if best <= 0:
        return {key: 0.0 for key in values}
    return {key: value / best for key, value in values.items()}


def _bonus_score(comp: dict) -> float:
    pct = comp_mod.bonus_pct(comp)
    if pct is not None:
        return min(pct, BONUS_CAP_PCT) / BONUS_CAP_PCT
    bonus = comp.get("bonus") or {}
    if bonus.get("status") == "posted" and bonus.get("kind") != "signing":
        return 0.5  # a stated amount we could not put against base
    if bonus:
        return 0.3
    return 0.0


def _equity_score(comp: dict) -> float:
    pct = comp_mod.equity_pct(comp)
    if pct is not None:
        return min(pct, EQUITY_CAP_PCT) / EQUITY_CAP_PCT
    equity = comp.get("equity") or {}
    if equity.get("status") == "posted":
        return 0.7  # a stated cash value
    if equity:
        return 0.4
    return 0.0


def _posted_key(lead: dict) -> float:
    posted = lead.get("posted_order")
    return float(posted) if isinstance(posted, (int, float)) else float("-inf")


def rank(leads: list[dict], weights: dict | None, *, floor: float | None = None,
         currency: str = "USD", fit_floor: int | None = None) -> list[Ranked]:
    """Rank `leads` (dicts with id, comp, fit_score, screen_status, user_state).

    `posted_order` (optional, larger = newer) breaks ties after fit. With a
    `fit_floor`, a lead screened below it ranks in `BELOW_FLOOR_BAND`; one
    with no fit score (its screening batch failed) is not held below it.
    """
    weights = clean_weights(weights)
    currency = (currency or "USD").upper()
    by_currency: dict[str, dict[str, float]] = {}
    for lead in leads:
        lo, hi, cur = comp_mod.annual_range(lead.get("comp") or {})
        if lo is not None and hi is not None and cur:
            by_currency.setdefault(cur, {})[str(lead["id"])] = (float(lo) + float(hi)) / 2
    base_pct: dict[str, float] = {}
    for values in by_currency.values():
        base_pct.update(_relative_to_best(values))

    scored: list[tuple[tuple, str, float, int, dict]] = []
    for lead in leads:
        lead_id = str(lead["id"])
        comp = lead.get("comp") or {}
        lo, hi, cur = comp_mod.annual_range(comp)
        flags: list[str] = []
        fit = lead.get("fit_score")
        components: dict[str, float] = {
            "bonus": _bonus_score(comp),
            "equity": _equity_score(comp),
            "fit": (float(fit) / 5.0) if isinstance(fit, (int, float)) else 0.5,
        }
        if lead.get("screen_status") == "irrelevant" or lead.get("user_state") == "dismissed":
            band = 9
        elif fit_floor is not None and isinstance(fit, (int, float)) and fit < fit_floor:
            band = BELOW_FLOOR_BAND
        elif lo is None:
            band = 2
        else:
            band = 0 if cur == currency else 1
        if lo is not None:
            components["base"] = base_pct.get(lead_id, 0.0)
            # A bonus is a share of THIS base: worth what the base is worth.
            components["bonus"] *= base_pct.get(lead_id, 0.0)
            if band == 0 and floor and hi is not None and float(hi) < float(floor):
                components["base"] = 0.0
                flags.append("below_floor")
        used = {key: weights[key] for key in components if key in weights}
        total = sum(used.values()) or 1.0
        score = sum(components[key] * used[key] for key in used) / total
        explain = {
            "components": {key: round(value, 4) for key, value in components.items()},
            "weights": {key: round(value / total, 4) for key, value in used.items()},
            "flags": flags,
        }
        sort_key = (band, -score, -(fit if isinstance(fit, (int, float)) else -1),
                    -_posted_key(lead), lead_id)
        scored.append((sort_key, lead_id, round(score, 6), band, explain))
    scored.sort(key=lambda item: item[0])
    return [
        Ranked(lead_id=lead_id, score=score, rank=i + 1, band=band, explain=explain)
        for i, (_key, lead_id, score, band, explain) in enumerate(scored)
    ]


def comp_line(comp: dict[str, Any]) -> str:
    """A one-line pay summary for lists: "$250K–$300K · 30% bonus · equity"."""
    parts = []
    lo, hi, cur = comp_mod.annual_range(comp)
    if lo is not None:
        symbol = "$" if cur == "USD" else f"{cur} "
        parts.append(f"{symbol}{_short(lo)}" + (f"–{symbol}{_short(hi)}" if hi and hi != lo else ""))
    pct = comp_mod.bonus_pct(comp)
    if pct is not None:
        parts.append(f"{pct:g}% bonus")
    elif comp.get("bonus"):
        parts.append("bonus")
    epct = comp_mod.equity_pct(comp)
    if epct is not None:
        parts.append(f"{epct:g}% equity")
    elif comp.get("equity"):
        parts.append("equity")
    return " · ".join(parts) or "Pay not posted"


def _short(value: float) -> str:
    value = float(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1_000:
        return f"{round(value / 1_000):,}K"
    return f"{value:,.0f}"
