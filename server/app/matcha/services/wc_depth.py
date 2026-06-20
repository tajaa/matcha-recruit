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
    return {
        "id": str(r["id"]),
        "company_id": str(r["company_id"]),
        "policy_period_start": r["policy_period_start"].isoformat() if r["policy_period_start"] else None,
        "policy_period_end": r["policy_period_end"].isoformat() if r["policy_period_end"] else None,
        "experience_mod": float(r["experience_mod"]),
        "carrier": r["carrier"],
        "annual_premium": float(r["annual_premium"]) if r["annual_premium"] is not None else None,
        "note": r["note"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


async def mod_trajectory(conn, company_id: UUID) -> list[dict]:
    """Full experience-mod history for a company, oldest period first."""
    rows = await conn.fetch(
        """
        SELECT id, company_id, policy_period_start, policy_period_end,
               experience_mod, carrier, annual_premium, note, created_at
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
               experience_mod, carrier, annual_premium, note, created_at
        FROM company_wc_mods
        WHERE company_id = ANY($1::uuid[])
        ORDER BY company_id, policy_period_start DESC
        """,
        ids,
    )
    return {str(r["company_id"]): _serialize_mod(r) for r in rows}
