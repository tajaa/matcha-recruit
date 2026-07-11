"""Total Cost of Risk (TCOR) + aggregate retention/SIR optimization.

TCOR = premiums + retained losses + fees + risk-mitigation spend — the number a
broker actually manages down. The retention optimizer answers "should we take a
higher self-insured retention?" by pricing each candidate aggregate retention
against the SAME Monte-Carlo aggregate loss distribution the risk assessment
already produces (``monte_carlo_service.run_monte_carlo``): expected retained
loss ``E[min(total_loss, retention)]`` + its volatility, net of a premium credit.

Directional: the premium-credit curve is an explicitly-labeled heuristic (we have
no carrier rate/elasticity data), and the loss distribution inherits the cost-of-
risk model's assumptions. Aggregate retention only (the sim models the annual
aggregate, not per-occurrence severities). Reuses the existing engine — no new
simulation math.
"""

import asyncio
import math
from uuid import UUID

from .monte_carlo_service import run_monte_carlo, extract_cost_of_risk_items

# Premium-credit heuristic: raising the retention by a factor earns a premium
# credit that grows with the log of the ratio, capped. NOT an actuarial rate.
_CREDIT_K = 0.15          # credit sensitivity per e-fold of retention
_CREDIT_CAP = 0.45        # max fractional premium credit
_SURCHARGE_CAP = 0.30     # max fractional load for LOWERING retention below base
# Risk aversion: the recommended retention minimizes expected total cost PLUS
# this multiple of the retained-loss volatility (so a volatile retention isn't
# chosen purely on its lower mean).
_RISK_LAMBDA = 0.25


def assemble_tcor(premiums: float, retained_losses: float, fees: float,
                  mitigation: float) -> dict:
    """Assemble the four TCOR components into a total + percentage shares. Pure."""
    comps = {
        "premiums": max(0.0, float(premiums or 0)),
        "retained_losses": max(0.0, float(retained_losses or 0)),
        "fees": max(0.0, float(fees or 0)),
        "risk_mitigation": max(0.0, float(mitigation or 0)),
    }
    total = sum(comps.values())
    shares = {k: round(100 * v / total, 1) if total else 0.0 for k, v in comps.items()}
    return {
        "components": [
            {"key": k, "amount": round(v, 2), "share_pct": shares[k]}
            for k, v in comps.items()
        ],
        "total": round(total, 2),
    }


def retained_loss_at_layer(samples: list[float], retention: float) -> dict:
    """Expected retained loss + volatility + expected transfer at an AGGREGATE
    retention, from simulated annual-aggregate loss samples. Pure.

    retained_i = min(loss_i, retention); transferred_i = max(loss_i - retention, 0).
    """
    if not samples:
        return {"retention": round(retention, 2), "expected_retained": 0.0,
                "volatility": 0.0, "expected_transferred": 0.0}
    retained = [min(s, retention) for s in samples]
    n = len(retained)
    mean_ret = sum(retained) / n
    var = sum((r - mean_ret) ** 2 for r in retained) / n
    mean_transfer = sum(max(s - retention, 0.0) for s in samples) / n
    return {
        "retention": round(retention, 2),
        "expected_retained": round(mean_ret, 2),
        "volatility": round(math.sqrt(var), 2),
        "expected_transferred": round(mean_transfer, 2),
    }


def premium_credit(base_premium: float, base_retention: float, retention: float) -> float:
    """Heuristic premium at a candidate retention (higher retention → credit,
    lower → surcharge). Directional, not a quote. Pure.
    """
    if base_premium <= 0 or base_retention <= 0 or retention <= 0:
        return round(max(0.0, base_premium), 2)
    frac = _CREDIT_K * math.log(retention / base_retention)
    frac = max(-_SURCHARGE_CAP, min(_CREDIT_CAP, frac))
    return round(base_premium * (1.0 - frac), 2)


def optimize_retention(samples: list[float], candidates: list[float],
                       base_premium: float, base_retention: float,
                       risk_lambda: float = _RISK_LAMBDA) -> dict:
    """Price each candidate aggregate retention and recommend the efficient one.

    expected_total_cost = premium_at_retention + expected_retained_loss.
    risk_adjusted_cost  = expected_total_cost + risk_lambda × retained volatility.
    The recommendation minimizes risk_adjusted_cost. Pure.
    """
    rows: list[dict] = []
    for ret in sorted({float(c) for c in candidates if c and c > 0}):
        layer = retained_loss_at_layer(samples, ret)
        prem = premium_credit(base_premium, base_retention, ret)
        expected_total = prem + layer["expected_retained"]
        risk_adjusted = expected_total + risk_lambda * layer["volatility"]
        rows.append({
            **layer,
            "premium": prem,
            "expected_total_cost": round(expected_total, 2),
            "risk_adjusted_cost": round(risk_adjusted, 2),
        })
    recommended = min(rows, key=lambda r: r["risk_adjusted_cost"])["retention"] if rows else None
    return {
        "candidates": rows,
        "recommended_retention": recommended,
        "basis": "expected retained loss from the simulated aggregate distribution + a "
                 "directional premium-credit heuristic; aggregate retention, not a quote.",
    }


def _default_candidates(base_retention: float, max_loss: float) -> list[float]:
    """A spread of candidate retentions around the current one, bounded by the
    worst simulated loss (no point testing a retention above max modeled loss)."""
    base = base_retention if base_retention and base_retention > 0 else 25_000.0
    raw = [base * m for m in (0.5, 1.0, 2.0, 4.0, 8.0)]
    cap = max_loss if max_loss and max_loss > 0 else base * 8
    return [round(r) for r in raw if r <= cap * 1.5] or [round(base)]


async def build_tcor(conn, company_id: UUID) -> dict:
    """DB wrapper: TCOR from stored inputs + retention optimization off the latest
    risk snapshot's cost-of-risk Monte-Carlo. Best-effort; never raises."""
    inputs = await conn.fetch(
        """SELECT line, annual_premium, fees, risk_mitigation_spend, current_retention, policy_year
           FROM company_tcor_inputs WHERE company_id = $1""",
        company_id,
    )
    premiums = sum(float(r["annual_premium"] or 0) for r in inputs)
    fees = sum(float(r["fees"] or 0) for r in inputs)
    mitigation = sum(float(r["risk_mitigation_spend"] or 0) for r in inputs)
    # Current aggregate retention = sum of per-line retentions on file (aggregate view).
    base_retention = sum(float(r["current_retention"] or 0) for r in inputs)

    # Modeled retained losses from the latest snapshot's cost-of-risk sim.
    snap = await conn.fetchrow(
        "SELECT dimensions FROM risk_assessment_snapshots WHERE company_id = $1", company_id,
    )
    modeled_loss = 0.0
    optimization = None
    dims = snap["dimensions"] if snap else None
    if dims:
        import json
        if isinstance(dims, str):
            dims = json.loads(dims)
        line_items = extract_cost_of_risk_items(dims) if isinstance(dims, dict) else []
        if line_items:
            # 10k-iteration sim — offload so it doesn't block the event loop
            # (mirrors the other run_monte_carlo callsites in the risk routes).
            mc = await asyncio.to_thread(run_monte_carlo, line_items, 10000, 42, True)
            modeled_loss = mc.aggregate.expected_annual_loss
            samples = mc.aggregate.samples or []
            candidates = _default_candidates(base_retention, mc.aggregate.max_simulated)
            optimization = optimize_retention(
                samples, candidates,
                base_premium=premiums or 0.0,
                base_retention=base_retention or (candidates[0] if candidates else 25_000.0),
            )

    tcor = assemble_tcor(premiums, modeled_loss, fees, mitigation)
    return {
        "company_id": str(company_id),
        "tcor": tcor,
        "retained_losses_basis": "modeled" if modeled_loss else "none",
        "current_retention": round(base_retention, 2),
        "optimization": optimization,
        "has_inputs": bool(inputs),
    }
