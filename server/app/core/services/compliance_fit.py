"""Per-business compliance fit map: what this company HAS vs what it NEEDS.

The demand signal on the codify worklist answers "who is waiting on what we
have". This answers the other half, and the constraint that shapes it is that
**"missing" has to fit the business**. A dental office must never be handed a
factory's confined-space rule as a gap — flooding a tenant with law it doesn't
need is worse than saying nothing, because it destroys the signal that the tab
is a real list of what you are responsible for.

Three buckets, all deterministic:

    visible  — projected AND codified. What the tenant sees today.
    gated    — projected, NOT codified. The tenant is waiting on us (this is the
               same set the Command Center's tenant-blocking count ranks).
    missing  — in the business's core checklist and NOT projected. Each carries a
               `reason`, because "missing" is four different problems with four
               different fixes (below).

Plus `beyond_core`: projected rows outside the core set. Reported as breadth,
never as excess — core is a floor, not a cap, and a real obligation that isn't
on the checklist is still a real obligation.

**Why `missing` must carry a reason.** The first live run of this map called
`state_minimum_wage` missing for a Los Angeles dental office. It isn't: the
California state row is in its chain and active, and the projection dropped it
because LA's *city* minimum wage preempts it. Reporting that as a gap is the
exact flooding this module exists to prevent. The same run called
`hipaa_privacy_rule` missing — and that one is real, but not because nobody
researched it: the federal row sits `pending`, and the only active copies are
misparented onto Idaho, Colorado, Texas, AZ and San Diego, none of which are in
an LA business's chain. Same word, opposite meanings. So:

    covered_by_stricter — the key IS in this location's chain, active, and older
        than the location's last sync, so the projection saw it and dropped it on
        purpose (preemption by a stricter local rule, an unmet facility trigger).
        Not a gap. Do nothing.
    stale_projection — in the chain and active, but written AFTER this location
        last synced. The tenant simply hasn't been re-projected yet. Fix: run a
        compliance check. (This is the 7-day-pull latency in the audit doc's
        finding 1, seen from the tenant's side: a CA breach-notification rule
        added on the 15th is invisible to a location last synced on the 14th.)
    staged — in the chain, but only as `status='pending'`. Researched, awaiting
        approval. Fix: approve it.
    researched_elsewhere — the key exists in the catalog for OTHER jurisdictions
        but not this chain. Either it needs researching here, or (for a federal
        statute) it is misparented onto states. Fix: research this chain, or
        re-parent.
    never_researched — the key appears nowhere in the catalog. Fix: research it.

Only the first is benign. `stale_projection` is a DELIVERY failure, not a data
one — the row exists and the tenant still can't see it — so it must not sit in
the same bucket as "working as designed".

Two deliberate choices:

**Core depth, not full.** `expected_keys` runs 180–237 keys per industry — too
many to hand-audit, so a wrong expectation hides in the pile. `core_keys` is the
curated ≤30-key must-have list where every miss is critical by construction.
Full depth is a later flag, not a default; defaulting to it would be the exact
flooding this module exists to prevent.

**No industry ⇒ the labor floor, and say so.** 23 of 43 dev companies have no
industry, and the column is free text ("Technology", "retail", "test"). Guessing
an industry keyset from that would invent obligations. An unresolvable industry
gets CORE_LABOR_KEYS only and `keyset: labor_floor_only` in the payload — the
evals' "unmeasured is null, never 100" rule, applied to a tenant.

Key matching mirrors the completeness eval exactly (`_bare_key` + `normalize_key`,
matched category-scoped on the normalized key). It has to: minimum-wage rows are
keyed on `rate_type` and `general` is level-sensitive, so a naive
`regulation_key` compare would report a company missing a minimum wage it
demonstrably has, on the same rows the eval calls present.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from .compliance_evals.industry_keysets import CORE_LABOR_KEYS, core_keys, has_core
from .compliance_evals.keys import normalize_key
from .compliance_evals.completeness import _bare_key

logger = logging.getLogger(__name__)


def labor_floor() -> Dict[str, Set[str]]:
    """The 12-key universal labor core, as a plain mutable mapping.

    Every employer owes these regardless of industry, so they are the honest
    fallback when the industry is unknown — and the floor `core_keys` merges
    into every curated industry set.
    """
    return {cat: set(keys) for cat, keys in CORE_LABOR_KEYS.items()}


def expected_for_industry(industry: Optional[str]) -> tuple[Dict[str, Set[str]], str]:
    """(expected {category: {key}}, provenance label) for a canonical industry.

    Provenance is returned, not inferred by the caller, because "we checked a
    dental office against the healthcare checklist" and "we only checked the
    labor floor because we don't know what this business is" are different
    claims, and the UI must not present the second as the first.
    """
    if industry and has_core(industry):
        return core_keys(industry), f"core:{industry}"
    return labor_floor(), "labor_floor_only"


def is_codified(row: Any) -> bool:
    """The codified trio, on a joined catalog row.

    Local rather than importing `compliance_service.is_codified_row` — that
    module imports heavily and this one is deliberately DB-free and cheap to
    unit-test. Same predicate; `scope_registry.codify.codified_sql` is the SQL
    twin and the three must not drift.
    """
    return bool(
        row.get("statute_citation")
        and row.get("citation_verified_at")
        and row.get("citation_item_id")
    )


def normalized_key_of(row: Any) -> Optional[str]:
    """This row's key in the registry vocabulary, or None if it has no key."""
    bare = _bare_key(row.get("regulation_key"), row.get("requirement_key"))
    if not bare:
        return None
    return normalize_key(
        row.get("category"),
        bare,
        row.get("jurisdiction_level"),
        row.get("country_code") or "US",
    )


#: Why an expected key isn't on the tenant's tab. Ordered most-benign first;
#: `classify_missing` returns the first that applies, so a key that is both in
#: the chain and elsewhere reports the chain answer — the nearer fact wins.
REASON_COVERED_BY_STRICTER = "covered_by_stricter"
REASON_STALE_PROJECTION = "stale_projection"
REASON_STAGED = "staged"
REASON_RESEARCHED_ELSEWHERE = "researched_elsewhere"
REASON_NEVER_RESEARCHED = "never_researched"

#: The one reason that is NOT somebody's problem — the obligation is handled, or
#: handled by something stricter. Counted separately so the headline gap number
#: can't be inflated by rules working as designed. `stale_projection` is
#: deliberately NOT here: the tenant can't see the rule, and "it'll sync within
#: 7 days" is a delivery failure, not a design.
BENIGN_REASONS = frozenset([REASON_COVERED_BY_STRICTER])


def classify_missing(
    category: str,
    key: str,
    chain_active: Dict[str, Set[str]],
    chain_pending: Dict[str, Set[str]],
    catalog_anywhere: Dict[str, Set[str]],
    chain_unsynced: Optional[Dict[str, Set[str]]] = None,
) -> str:
    """Why is this expected key not on the tenant's tab? Pure.

    `chain_unsynced`: keys in the chain written since the location last synced.
    Checked BEFORE `covered_by_stricter` — a row the projection has never run
    against wasn't filtered, it was never considered, and calling that
    "preempted" would file a delivery bug under "working as designed".
    """
    chain_unsynced = chain_unsynced or {}
    if key in chain_unsynced.get(category, set()):
        return REASON_STALE_PROJECTION
    if key in chain_active.get(category, set()):
        # In their chain, live, and the projection saw it and dropped it — a
        # stricter local rule preempts it, or a facility trigger didn't fire.
        return REASON_COVERED_BY_STRICTER
    if key in chain_pending.get(category, set()):
        return REASON_STAGED
    if key in catalog_anywhere.get(category, set()):
        return REASON_RESEARCHED_ELSEWHERE
    return REASON_NEVER_RESEARCHED


def bucket_fit(
    projected_rows: List[Dict[str, Any]],
    expected: Dict[str, Set[str]],
    chain_active: Optional[Dict[str, Set[str]]] = None,
    chain_pending: Optional[Dict[str, Set[str]]] = None,
    catalog_anywhere: Optional[Dict[str, Set[str]]] = None,
    chain_unsynced: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, Any]:
    """Split a company's projected rows against its expected checklist.

    Pure — no DB, no I/O — so the bucketing rules are unit-testable and the
    numbers in the UI can be reproduced from a fixture.

    `projected_rows` carry: category, regulation_key, requirement_key,
    jurisdiction_level, country_code, title, statute_citation,
    citation_verified_at, citation_item_id.

    The three catalog maps are what let `missing` say WHY (see module docstring).
    Omitting them degrades every miss to `never_researched`, which is the honest
    default for a caller that can't see the catalog — it never invents a benign
    reason it hasn't checked.
    """
    chain_active = chain_active or {}
    chain_pending = chain_pending or {}
    catalog_anywhere = catalog_anywhere or {}
    visible: List[Dict[str, Any]] = []
    gated: List[Dict[str, Any]] = []
    beyond_core: List[Dict[str, Any]] = []

    # category -> normalized keys actually present, regardless of codification.
    # `missing` means "we never researched this for them"; a gated row was
    # researched and is merely withheld, so counting it missing would double-bill
    # the same obligation as two different failures with two different fixes.
    present: Dict[str, Set[str]] = {}

    for row in projected_rows:
        cat = row.get("category")
        key = normalized_key_of(row)
        if cat and key:
            present.setdefault(cat, set()).add(key)

        entry = {
            "id": str(row["id"]) if row.get("id") else None,
            "category": cat,
            "regulation_key": key,
            "title": row.get("title"),
            "jurisdiction_name": row.get("jurisdiction_name"),
            "jurisdiction_level": row.get("jurisdiction_level"),
            "statute_citation": row.get("statute_citation"),
        }
        (visible if is_codified(row) else gated).append(entry)

        if not (cat and key and key in expected.get(cat, set())):
            beyond_core.append(entry)

    missing: List[Dict[str, str]] = []
    for cat in sorted(expected):
        for key in sorted(expected[cat] - present.get(cat, set())):
            missing.append({
                "category": cat,
                "regulation_key": key,
                "reason": classify_missing(
                    cat, key, chain_active, chain_pending, catalog_anywhere, chain_unsynced,
                ),
            })

    gaps = [m for m in missing if m["reason"] not in BENIGN_REASONS]
    return {
        "visible": visible,
        "gated": gated,
        "missing": missing,
        "beyond_core": beyond_core,
        "counts": {
            "visible": len(visible),
            "gated": len(gated),
            # `missing` is every expected key off the tab; `gaps` is the subset
            # that is actually somebody's problem. Headline the second — the
            # first includes preempted rules that are working as designed.
            "missing": len(missing),
            "gaps": len(gaps),
            "covered_by_stricter": len(missing) - len(gaps),
            "beyond_core": len(beyond_core),
            "expected": sum(len(v) for v in expected.values()),
            "projected": len(projected_rows),
        },
    }


# One query for every projected row across a company's active locations, with
# the catalog fields the buckets need. Deliberately NOT gated by
# `codified_gate_sql`: the gate's job is to hide uncodified rows from tenants,
# and this map's job is to count exactly what it hides. Applying it here would
# make `gated` structurally always 0.
_PROJECTED_SQL = """
    SELECT r.id, r.location_id,
           bl.city AS location_city, bl.state AS location_state,
           r.category, r.requirement_key, r.jurisdiction_name, r.jurisdiction_level,
           r.title,
           cat.regulation_key, cat.statute_citation,
           cat.citation_verified_at, cat.citation_item_id,
           j.country_code
    FROM compliance_requirements r
    JOIN business_locations bl ON bl.id = r.location_id
                              AND COALESCE(bl.is_active, true) = true
    LEFT JOIN jurisdiction_requirements cat ON cat.id = r.jurisdiction_requirement_id
    LEFT JOIN jurisdictions j ON j.id = cat.jurisdiction_id
    WHERE bl.company_id = $1
    ORDER BY r.location_id, r.category, r.title
"""


# Every catalog row on a location's jurisdiction chain (leaf → … → federal),
# with its status. Same recursive walk + depth cap as
# `_load_chain_requirements`, for the same reason: a parent_id cycle from a bad
# merge would otherwise spin forever. This is what separates "preempted" from
# "never researched" — without it every filtered row looks like a hole.
_CHAIN_KEYS_SQL = """
    WITH RECURSIVE chain AS (
        SELECT bl.id AS location_id, j.id, j.parent_id, 0 AS depth
        FROM business_locations bl
        JOIN jurisdictions j ON j.id = bl.jurisdiction_id
        WHERE bl.company_id = $1 AND COALESCE(bl.is_active, true) = true
        UNION ALL
        SELECT c.location_id, j.id, j.parent_id, c.depth + 1
        FROM jurisdictions j
        JOIN chain c ON j.id = c.parent_id
        WHERE c.depth < 8
    )
    SELECT DISTINCT chain.location_id, jr.category, jr.regulation_key,
           jr.requirement_key, jr.jurisdiction_level, jr.status::text AS status,
           j2.country_code,
           -- Written since this location last synced ⇒ the projection has never
           -- run against it. COALESCE: a location that has NEVER been checked
           -- can't have filtered anything, so everything in its chain is
           -- unsynced rather than "preempted".
           (jr.created_at > COALESCE(bl.last_compliance_check, '-infinity'::timestamp))
               AS unsynced
    FROM chain
    JOIN business_locations bl ON bl.id = chain.location_id
    JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = chain.id
    LEFT JOIN jurisdictions j2 ON j2.id = jr.jurisdiction_id
    WHERE jr.status IN ('active', 'pending')
"""

# Every key the catalog knows anywhere, at any jurisdiction. Distinguishes "we
# have never researched this" from "we researched it, but onto jurisdictions
# this business isn't in" — which is what a misparented federal statute looks
# like from a tenant's chain.
_CATALOG_KEYS_SQL = """
    SELECT DISTINCT jr.category, jr.regulation_key, jr.requirement_key,
           jr.jurisdiction_level, j.country_code
    FROM jurisdiction_requirements jr
    LEFT JOIN jurisdictions j ON j.id = jr.jurisdiction_id
    WHERE jr.status = 'active'
"""


def _index_keys(rows) -> Dict[str, Set[str]]:
    """{category: {normalized key}} from catalog rows."""
    out: Dict[str, Set[str]] = {}
    for r in rows:
        cat = r.get("category")
        key = normalized_key_of(r)
        if cat and key:
            out.setdefault(cat, set()).add(key)
    return out


async def company_fit_map(conn, company_id: UUID) -> Dict[str, Any]:
    """The fit map for one company: rollup + per-location buckets."""
    from .compliance_service import _get_company_canonical_industry

    industry = await _get_company_canonical_industry(conn, company_id)
    expected, provenance = expected_for_industry(industry)

    rows = [dict(r) for r in await conn.fetch(_PROJECTED_SQL, company_id)]
    chain_rows = [dict(r) for r in await conn.fetch(_CHAIN_KEYS_SQL, company_id)]
    catalog_anywhere = _index_keys(await conn.fetch(_CATALOG_KEYS_SQL))

    chain_active_by_loc: Dict[Any, List[Dict[str, Any]]] = {}
    chain_pending_by_loc: Dict[Any, List[Dict[str, Any]]] = {}
    chain_unsynced_by_loc: Dict[Any, List[Dict[str, Any]]] = {}
    for r in chain_rows:
        target = chain_active_by_loc if r["status"] == "active" else chain_pending_by_loc
        target.setdefault(r["location_id"], []).append(r)
        if r["status"] == "active" and r["unsynced"]:
            chain_unsynced_by_loc.setdefault(r["location_id"], []).append(r)

    chain_active_all = _index_keys([r for r in chain_rows if r["status"] == "active"])
    chain_pending_all = _index_keys([r for r in chain_rows if r["status"] == "pending"])
    # Company rollup: a key is stale if EVERY location holding it is unsynced for
    # it. If one location already has it projected, the company has it — so the
    # per-location detail, not this, is where a single stale site shows up.
    chain_unsynced_all = _index_keys(
        [r for r in chain_rows if r["status"] == "active" and r["unsynced"]]
    )

    by_location: Dict[Any, List[Dict[str, Any]]] = {}
    for r in rows:
        by_location.setdefault(r["location_id"], []).append(r)

    locations = []
    for loc_id, loc_rows in by_location.items():
        fit = bucket_fit(
            loc_rows, expected,
            chain_active=_index_keys(chain_active_by_loc.get(loc_id, [])),
            chain_pending=_index_keys(chain_pending_by_loc.get(loc_id, [])),
            catalog_anywhere=catalog_anywhere,
            chain_unsynced=_index_keys(chain_unsynced_by_loc.get(loc_id, [])),
        )
        locations.append({
            "location_id": str(loc_id),
            "city": loc_rows[0].get("location_city"),
            "state": loc_rows[0].get("location_state"),
            **fit,
        })
    locations.sort(key=lambda x: (x["state"] or "", x["city"] or ""))

    # The rollup buckets the company's whole projection at once rather than
    # summing per-location counts: an obligation researched for one location and
    # not another is present for the COMPANY, and summing would report it both
    # missing and present. Per-location detail below is where that distinction
    # lives.
    rollup = bucket_fit(
        rows, expected,
        chain_active=chain_active_all,
        chain_pending=chain_pending_all,
        catalog_anywhere=catalog_anywhere,
        chain_unsynced=chain_unsynced_all,
    )

    return {
        "company_id": str(company_id),
        "industry": industry,
        "keyset": provenance,
        "keyset_note": (
            None if provenance != "labor_floor_only" else
            "No curated core checklist for this industry — measured against the "
            "12-key universal labor floor only. Industry-specific obligations "
            "are NOT assessed."
        ),
        "counts": rollup["counts"],
        "missing": rollup["missing"],
        "locations": locations,
    }
