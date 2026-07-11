"""Resolve a (state, city) coordinate to its jurisdiction inheritance chain.

Moved verbatim from ``core/routes/admin.py`` (PR #25's matrix endpoint) so the
scope-registry resolver and the admin routes share one implementation — services
must not import from routes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID


async def resolve_jurisdiction_chain(
    conn, state: str, city: Optional[str]
) -> Dict[str, Any]:
    """The jurisdictions whose requirements an establishment here inherits.

    city ∪ county ∪ state ∪ federal — the same union `compliance_evals` uses for
    presence (`completeness.present_keys_for`). A requirement held at the state
    level covers a business in the city; asking only about the city row would
    report nearly everything as missing.

    `federal` and `national` are not the same bucket: `national` rows are country
    roots (UK, Mexico, Singapore), so only the US `federal` row is chained here.

    Reports `state_found`/`city_found` separately from the id list, because the
    federal row always resolves — a caller checking only `ids` would treat a
    nonexistent state as a valid one-link chain.
    """
    ids: List[UUID] = []

    federal = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE level::text = 'federal' LIMIT 1"
    )
    if federal:
        ids.append(federal)

    state_id = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE level::text = 'state' AND state = $1 "
        "AND COALESCE(country_code,'US') = 'US' LIMIT 1",
        state,
    )
    if state_id:
        ids.append(state_id)

    city_id = None
    city_found = False
    city_name = None
    county_name = None
    if city:
        city_row = await conn.fetchrow(
            "SELECT id, city, county FROM jurisdictions WHERE LOWER(city) = LOWER($1) AND state = $2 "
            "AND COALESCE(country_code,'US') = 'US' LIMIT 1",
            city, state,
        )
        if city_row:
            city_found = True
            city_id = city_row["id"]
            city_name = city_row["city"]   # canonical stored casing
            ids.append(city_row["id"])
            if city_row["county"]:
                county_name = city_row["county"]
                county_id = await conn.fetchval(
                    "SELECT id FROM jurisdictions WHERE level::text = 'county' "
                    "AND LOWER(county) = LOWER($1) AND state = $2 LIMIT 1",
                    city_row["county"], state,
                )
                if county_id:
                    ids.append(county_id)

    return {
        "ids": ids,
        "state_found": state_id is not None,
        "city_found": city_found,
        # Per-level ids for research targeting (additive; existing callers read
        # ids/state_found/city_found only).
        "federal_id": federal,
        "state_id": state_id,
        "city_id": city_id,
        # Canonical names for sub-index jurisdiction_scope matching (additive).
        "city_name": city_name,
        "county_name": county_name,
    }
