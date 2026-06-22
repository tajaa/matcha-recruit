"""Workers' Comp depth helpers — NCCI state-rate overlay + experience-mod trajectory.

Backs the deepened broker WC surface (migration ``wcdeep01``). Three concerns:

- Resolve a company's operating state(s) so we can hang a per-jurisdiction NCCI
  loss-cost trend on each client (the report's "WC Risk Index" jurisdiction lens).
- Look up the latest ``wc_state_rates`` row per state.
- Read/serialize the ``company_wc_mods`` experience-mod (EMR) trajectory — the
  number carriers actually price WC on.

All functions take an open asyncpg connection (caller owns the pool checkout).
"""

from typing import Iterable, Optional
from uuid import UUID

# Full state name → USPS abbreviation, to normalize the free-text
# ``companies.headquarters_state`` (VARCHAR(50)) fallback. business_locations.state
# is already a 2-letter code so it needs no mapping.
STATE_NAME_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "washington dc": "DC", "washington d.c.": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def _normalize_state(raw: Optional[str]) -> Optional[str]:
    """Coerce a state string to a 2-letter USPS code, else None."""
    if not raw:
        return None
    s = raw.strip()
    if len(s) == 2 and s.isalpha():
        return s.upper()
    return STATE_NAME_TO_ABBR.get(s.lower())


async def resolve_company_states(conn, company_id: UUID) -> list[str]:
    """Distinct operating states for a company, primary-ish first.

    Prefers ``business_locations`` (active first, then by employee/location
    density via row count). Falls back to the company's free-text HQ state.
    """
    rows = await conn.fetch(
        """
        SELECT state, COUNT(*) AS n
        FROM business_locations
        WHERE company_id = $1 AND state IS NOT NULL AND state <> ''
          AND COALESCE(is_active, true) = true
        GROUP BY state
        ORDER BY n DESC, state ASC
        """,
        company_id,
    )
    states = [r["state"].upper() for r in rows if r["state"]]
    if states:
        return states

    hq = await conn.fetchval(
        "SELECT headquarters_state FROM companies WHERE id = $1", company_id
    )
    norm = _normalize_state(hq)
    return [norm] if norm else []


def _serialize_state_rate(r) -> dict:
    return {
        "state": r["state"],
        "loss_cost_change_pct": float(r["loss_cost_change_pct"]),
        "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
        "trend": r["trend"],
        "source": r["source"],
        "note": r["note"],
    }


async def get_state_rates(conn, states: Iterable[str]) -> dict[str, dict]:
    """Latest NCCI rate row per requested state → {state: serialized_row}.

    "Latest" = most recent ``effective_date`` per state. Unknown states are
    simply absent from the result.
    """
    wanted = sorted({s.upper() for s in states if s})
    if not wanted:
        return {}
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (state) state, loss_cost_change_pct, effective_date, trend, source, note
        FROM wc_state_rates
        WHERE state = ANY($1::text[])
        ORDER BY state, effective_date DESC
        """,
        wanted,
    )
    return {r["state"]: _serialize_state_rate(r) for r in rows}


async def list_state_rates(conn) -> list[dict]:
    """All current (latest-per-state) NCCI rate rows for the reference panel."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (state) state, loss_cost_change_pct, effective_date, trend, source, note
        FROM wc_state_rates
        ORDER BY state, effective_date DESC
        """
    )
    out = [_serialize_state_rate(r) for r in rows]
    # National row ('US') last; otherwise increases first (worst), then by name.
    out.sort(key=lambda r: (r["state"] == "US", -r["loss_cost_change_pct"], r["state"]))
    return out


def _serialize_mod(r) -> dict:
    d = dict(r)
    return {
        "id": str(r["id"]),
        "company_id": str(r["company_id"]),
        "policy_period_start": r["policy_period_start"].isoformat() if r["policy_period_start"] else None,
        "policy_period_end": r["policy_period_end"].isoformat() if r["policy_period_end"] else None,
        "experience_mod": float(r["experience_mod"]),
        "carrier": r["carrier"],
        "annual_premium": float(r["annual_premium"]) if r["annual_premium"] is not None else None,
        "note": r["note"],
        "source": d.get("source") or "manual",  # 'manual' | 'worksheet'
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


async def mod_trajectory(conn, company_id: UUID) -> list[dict]:
    """Full experience-mod history for a company, oldest period first."""
    rows = await conn.fetch(
        """
        SELECT id, company_id, policy_period_start, policy_period_end,
               experience_mod, carrier, annual_premium, note, source, created_at
        FROM company_wc_mods
        WHERE company_id = $1
        ORDER BY policy_period_start ASC
        """,
        company_id,
    )
    return [_serialize_mod(r) for r in rows]


async def latest_mods(conn, company_ids: Iterable[UUID]) -> dict[str, dict]:
    """Most recent mod per company → {company_id_str: serialized_mod}.

    Batched for the portfolio rollup so one query covers the whole book.
    """
    ids = list({c for c in company_ids})
    if not ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (company_id)
               id, company_id, policy_period_start, policy_period_end,
               experience_mod, carrier, annual_premium, note, source, created_at
        FROM company_wc_mods
        WHERE company_id = ANY($1::uuid[])
        ORDER BY company_id, policy_period_start DESC
        """,
        ids,
    )
    return {str(r["company_id"]): _serialize_mod(r) for r in rows}


# --- WC class codes (wcclass01) --------------------------------------------

async def list_class_codes(conn) -> list[dict]:
    """Reference NCCI class codes (illustrative seed pending a licensed feed)."""
    rows = await conn.fetch(
        "SELECT state, class_code, description, base_rate, source FROM wc_class_codes ORDER BY class_code"
    )
    return [{
        "state": r["state"], "class_code": r["class_code"], "description": r["description"],
        "base_rate": float(r["base_rate"]) if r["base_rate"] is not None else None,
        "source": r["source"],
    } for r in rows]


async def class_exposures(conn, company_id: UUID) -> list[dict]:
    """A client's class-code exposures, joined to the best-matching reference rate
    (state-specific if present, else the national 'US' row) + an estimated manual
    premium (payroll / 100 × rate)."""
    rows = await conn.fetch(
        """
        SELECT e.id, e.class_code, e.state, e.payroll, e.headcount, e.note, e.created_at,
               c.description, c.base_rate
        FROM company_wc_class_exposures e
        LEFT JOIN LATERAL (
            SELECT description, base_rate FROM wc_class_codes wc
            WHERE wc.class_code = e.class_code AND wc.state IN (e.state, 'US')
            ORDER BY (wc.state = e.state) DESC LIMIT 1
        ) c ON true
        WHERE e.company_id = $1
        ORDER BY e.payroll DESC NULLS LAST, e.class_code
        """,
        company_id,
    )
    out: list[dict] = []
    for r in rows:
        payroll = float(r["payroll"]) if r["payroll"] is not None else None
        rate = float(r["base_rate"]) if r["base_rate"] is not None else None
        est = round(payroll / 100 * rate) if (payroll and rate) else None
        out.append({
            "id": str(r["id"]), "class_code": r["class_code"], "state": r["state"],
            "description": r["description"], "payroll": payroll, "headcount": r["headcount"],
            "base_rate": rate, "est_manual_premium": est, "note": r["note"],
        })
    return out


# --- experience-mod proxy (directional, auto from loss-runs + class payroll) ----

def proxy_mod(actual_losses: float, expected_losses: float) -> Optional[float]:
    """Directional experience proxy = actual incurred ÷ expected losses (~1.0 = on
    plan, >1 adverse). None when there's no expected-loss base. Pure (unit-tested)."""
    if not expected_losses or expected_losses <= 0:
        return None
    return round(actual_losses / expected_losses, 3)


async def expected_annual_losses(conn, company_id: UUID) -> float:
    """One policy year's expected losses at current exposure: Σ(payroll/100 × base_rate)
    across the client's class exposures. WCIRB/NCCI pure-premium rates ARE expected
    losses per $100 payroll, so this is an expected-loss base (not premium). 0 if none."""
    exposures = await class_exposures(conn, company_id)
    return float(sum(e["est_manual_premium"] for e in exposures if e.get("est_manual_premium")))


async def mod_proxy_trajectory(conn, company_id: UUID) -> dict:
    """Directional experience-mod proxy per loss-run valuation date — automatic, no
    manual entry, no licensed bureau parameters.

    Per valuation: actual = total WC incurred (paid+reserved) across the policy
    periods reported as of that date; expected = one year's expected losses × the
    number of policy periods in that valuation (so multi-year actuals meet multi-year
    expected). Reuses ``wc_loss_runs`` + class payroll already on file. Directional —
    NOT the bureau's published mod."""
    expected_annual = await expected_annual_losses(conn, company_id)
    if expected_annual <= 0:
        return {"points": [], "expected_annual_losses": 0.0,
                "basis": "Add WC class payroll exposures to enable the proxy trajectory."}
    rows = await conn.fetch(
        """
        SELECT valuation_date,
               COUNT(DISTINCT policy_period_label) AS periods,
               SUM(COALESCE(paid, 0) + COALESCE(reserved, 0)) AS incurred
        FROM wc_loss_runs
        WHERE subject_kind = 'company' AND subject_id = $1 AND line = 'wc'
        GROUP BY valuation_date
        ORDER BY valuation_date ASC
        """,
        company_id,
    )
    points: list[dict] = []
    for r in rows:
        periods = int(r["periods"]) or 1
        actual = float(r["incurred"] or 0)
        expected = expected_annual * periods
        pm = proxy_mod(actual, expected)
        if pm is None:
            continue
        points.append({
            "valuation_date": r["valuation_date"].isoformat() if r["valuation_date"] else None,
            "experience_mod": pm, "actual_losses": round(actual), "expected_losses": round(expected),
            "periods": periods, "source": "proxy",
        })
    return {
        "points": points,
        "expected_annual_losses": round(expected_annual),
        "basis": "actual incurred ÷ expected losses (pure-premium rate × payroll); directional, not the bureau mod.",
    }
