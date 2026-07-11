"""Bridge the scope-registry engine into the admin gap-analysis surfaces.

Two admin surfaces historically computed "coverage / gaps" without the engine:
the per-company Gap Analysis dashboard (``map_to_bank`` category-grab) and the
industry-requirements matrix (raw ``GROUP BY category`` counts). This module lets
them read the engine's grounded verdict **where the registry is definitively
classified**, falling back to the old count otherwise — the same conservative
gate ``compliance_evals.completeness.registry_expected_keys`` already uses
(``unclassified_count == 0`` on every covering index, else ``None``).

Design rules that callers rely on:
  * The engine verdict is **additive** — callers keep their bank arrays (the
    frontend's "Research a gap" actions consume the bank item shape, which the
    engine's ``{regulation_key, citation}`` items can't drop into).
  * The gate is applied **per coordinate / per cell**, never once for the whole
    company/chain: a coordinate covered only by fully-classified labor indexes
    passes a chain-level gate but has zero classifications for, say, healthcare —
    so a chain-level gate would zero out real bank data. See
    ``resolve_chain_category_coverage`` and ``aggregate_company_coordinates``.
  * Gaps are **per-jurisdiction facts**. ``resolve_scope``'s "uncodified" means
    "no catalog row in THIS chain", so a key codified in one location's chain is
    still a real gap for another location whose chain lacks it — the aggregate
    never drops a gap because a different chain covers the same key.
  * Any location that could not be resolved (resolve error) makes the company
    verdict non-engine: a "grounded" verdict must never silently omit part of
    the footprint.

``aggregate_company_coordinates`` and ``cell_coverage`` are pure (no DB, no AI)
so they unit-test without fixtures.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Pure aggregation ────────────────────────────────────────────────────────


def aggregate_company_coordinates(coords: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Union per-coordinate ``resolve_scope`` results into one company verdict. Pure.

    ``coords`` items (from :func:`resolve_company_scope`, one per **unique**
    coordinate): ``{state, city, resolved, engine_definitive, codified,
    uncodified, counts, unmodeled}`` where ``codified``/``uncodified`` are
    resolve_scope's item lists for that coordinate's chain.

    Counting is per (coordinate × classified item) on BOTH sides — the same
    units ``resolve_scope`` itself reports — so ``coverage_pct`` never mixes a
    key-union numerator with a per-citation denominator, and a key uncodified
    in one chain stays a gap even when another chain codifies it.

    ``coverage_source`` is ``"engine"`` only when at least one coordinate
    resolved, EVERY coordinate resolved (a failed resolve = unknown footprint),
    every resolved coordinate is engine-definitive, and none degraded (an
    unmodeled state/city makes coverage uncertain — fall back conservatively).
    """
    resolved = [c for c in coords if c.get("resolved")]
    failed = len(coords) - len(resolved)

    codified_keys = set()
    codified_n = 0
    uncodified: List[Dict[str, Any]] = []
    provisional = 0
    unmodeled: List[Dict[str, Any]] = []
    for c in resolved:
        cod = c.get("codified") or []
        codified_n += len(cod)
        codified_keys |= {e.get("regulation_key") for e in cod if e.get("regulation_key")}
        # Annotate each gap with the chain it belongs to — a per-jurisdiction
        # fact, deliberately NOT deduped against other chains' codified keys.
        for u in (c.get("uncodified") or []):
            uncodified.append({**u, "state": c.get("state"), "city": c.get("city")})
        # Chain-wide per coordinate (resolve_scope documents it that way); can
        # overlap across chains sharing the federal index — treat as indicative.
        provisional += int((c.get("counts") or {}).get("provisional", 0))
        unmodeled.extend(c.get("unmodeled") or [])

    uncodified_n = len(uncodified)
    degraded = bool(unmodeled) or failed > 0
    engine_n = sum(1 for c in resolved if c.get("engine_definitive"))
    n = len(resolved)
    engine = n > 0 and engine_n == n and not degraded
    denom = codified_n + uncodified_n

    return {
        "coverage_source": "engine" if engine else "bank",
        "codified_keys": sorted(codified_keys),
        "uncodified": uncodified,
        "counts": {
            "locations": n,
            "locations_failed": failed,
            "codified": codified_n,
            "uncodified": uncodified_n,
            "provisional": provisional,
        },
        "coverage_pct": round(100 * codified_n / denom) if denom else 100,
        "gate": {
            "total": len(coords),
            "engine": engine_n,
            "fallback": len(coords) - engine_n,
        },
        "unmodeled_coordinates": unmodeled,
        "degraded": degraded,
        "coordinates": [
            {
                "state": c.get("state"),
                "city": c.get("city"),
                "coverage_source": "engine" if c.get("engine_definitive") else "bank",
                "counts": c.get("counts") or {},
                "unmodeled": c.get("unmodeled") or [],
            }
            for c in resolved
        ],
    }


def cell_coverage(expected: Any, present: Any) -> Dict[str, Any]:
    """Per-category codified/to-codify from the registry's expected keys vs the
    keys actually present in the catalog for a jurisdiction chain. Pure."""
    exp = set(expected or ())
    pres = set(present or ())
    to_codify = exp - pres
    return {
        "expected": len(exp),
        "codified": len(exp & pres),
        "to_codify": len(to_codify),
        "to_codify_keys": sorted(to_codify),
    }


# ── Engine-backed resolution (DB) ───────────────────────────────────────────


def _attrs_signature(attrs: Dict[str, Any]) -> tuple:
    """Stable identity for a facility_attributes dict (memo key component)."""
    try:
        return tuple(sorted((str(k), repr(v)) for k, v in attrs.items()))
    except Exception:
        return (repr(attrs),)


async def resolve_company_scope(
    conn,
    company_id,
    *,
    industry: Optional[str],
    specialty: Optional[str] = None,
    employee_count: Optional[int] = None,
    use_cache: bool = True,
    gate: bool = True,
) -> Dict[str, Any]:
    """Resolve the registry scope for every one of a company's business locations
    and union the result (via :func:`aggregate_company_coordinates`).

    Reuses the per-location loop that ``shadow.record_shadow`` ran inline: only
    stateful, active, non-company-wide locations (so ``resolve_scope``'s
    "requires a state" guard is never hit). Locations sharing an identical
    (state, city, attributes) coordinate are resolved **once** — memoized —
    so a 10-warehouse single-city company costs one resolution, not ten.

    ``category`` may be None (industry-less session): resolve_scope still
    matches ``universal_in_domain`` rows and reports an unmodeled-category
    finding, which degrades the verdict to bank — it must NOT short-circuit,
    or the shadow log records fake total-divergence for industry-less
    companies. ``employee_count`` is injected into ``facility_attributes``
    when absent so conditional labor strata (e.g. FMLA ≥ 50) resolve.

    ``gate=False`` skips the per-chain definitiveness check (2 queries per
    unique chain) for callers that never read the engine verdict — the shadow
    path only consumes ``codified_keys`` + ``unmodeled_coordinates``.
    """
    from .resolve import parse_jsonb, resolve_scope

    category = specialty or industry
    if not company_id:
        return aggregate_company_coordinates([])

    locations = await conn.fetch(
        """
        SELECT state, city, facility_attributes
        FROM business_locations
        WHERE company_id = $1 AND COALESCE(is_active, true)
          AND state IS NOT NULL AND NOT COALESCE(is_company_wide, false)
        """,
        company_id,
    )

    coords: List[Dict[str, Any]] = []
    seen_coordinates: set = set()
    gate_by_chain: Dict[tuple, bool] = {}
    for loc in locations:
        attrs = parse_jsonb(loc["facility_attributes"]) or {}
        if employee_count is not None and "employee_count" not in attrs:
            attrs = {**attrs, "employee_count": employee_count}

        memo_key = (loc["state"], loc["city"], _attrs_signature(attrs))
        if memo_key in seen_coordinates:
            continue  # identical coordinate — already resolved this pass
        seen_coordinates.add(memo_key)

        try:
            res = await resolve_scope(
                conn,
                category=category,
                state=loc["state"],
                city=loc["city"],
                facility_attributes=attrs,
                use_cache=use_cache,
            )
        except Exception:
            logger.exception(
                "gap_surfaces: resolve_scope failed for company %s loc %s/%s",
                company_id, loc["state"], loc["city"],
            )
            # A coordinate we couldn't evaluate: recorded so the aggregate
            # degrades the verdict to bank instead of pretending it isn't there.
            coords.append({
                "state": loc["state"], "city": loc["city"], "resolved": False,
                "engine_definitive": False, "codified": [], "uncodified": [],
                "counts": {}, "unmodeled": [],
            })
            continue

        definitive = False
        if gate:
            chain_key = tuple(res["coordinate"]["jurisdiction_ids"])
            if chain_key in gate_by_chain:
                definitive = gate_by_chain[chain_key]
            else:
                try:
                    from app.core.services.compliance_evals.completeness import (
                        registry_expected_keys,
                    )
                    expected = await registry_expected_keys(
                        conn, list(chain_key), category,
                    )
                    definitive = expected is not None
                except Exception:
                    logger.exception(
                        "gap_surfaces: gate check failed for company %s", company_id,
                    )
                gate_by_chain[chain_key] = definitive

        coords.append({
            "state": loc["state"],
            "city": loc["city"],
            "resolved": True,
            "engine_definitive": definitive,
            "codified": res["codified"],
            "uncodified": res["uncodified"],
            "counts": res["counts"],
            "unmodeled": res["unmodeled_coordinates"],
        })

    return aggregate_company_coordinates(coords)


async def resolve_chain_category_coverage(
    conn, *, chain_ids, industry: Optional[str],
) -> Dict[str, Any]:
    """Per-category codified/to-codify for a jurisdiction chain, from the engine.

    Returns ``{"registry_definitive": bool, "by_category": {slug: cell_coverage}}``.
    ``registry_definitive`` is False (and ``by_category`` empty) unless the
    registry definitively covers the coordinate — the matrix then leaves those
    cells on their bank counts. Buckets are RKD ``category_slug``, which
    ``codify.py`` documents equals ``jurisdiction_requirements.category`` — the
    vocabulary the matrix groups by.

    The present set mirrors the completeness eval's presence union exactly
    (``load_jurisdiction_graph`` lines 49-54): ``_bare_key`` tolerates legacy
    rows that only carry the composite ``requirement_key``, and ``normalize_key``
    maps the catalog's minimum-wage rate_type dialect ('general'/'tipped') onto
    the registry vocabulary — without it, a chain with its minimum wage plainly
    codified would show phantom ``state_minimum_wage`` gaps.
    """
    from app.core.services.compliance_evals.completeness import (
        _bare_key,
        registry_expected_keys,
    )
    from app.core.services.compliance_evals.keys import normalize_key

    expected = await registry_expected_keys(conn, list(chain_ids), industry)
    if expected is None:
        return {"registry_definitive": False, "by_category": {}}

    # Unlike the eval's graph query this keeps the active-status filter — a
    # retired catalog row must not count as codified for the research worklist.
    rows = await conn.fetch(
        """
        SELECT jr.category, jr.regulation_key, jr.requirement_key,
               j.level::text AS level, COALESCE(j.country_code, 'US') AS country_code
        FROM jurisdiction_requirements jr
        JOIN jurisdictions j ON j.id = jr.jurisdiction_id
        WHERE jr.jurisdiction_id = ANY($1::uuid[])
          AND COALESCE(jr.status, 'active') = 'active'
        """,
        list(chain_ids),
    )
    present: Dict[str, set] = {}
    for r in rows:
        key = _bare_key(r["regulation_key"], r["requirement_key"])
        if not key or not r["category"]:
            continue
        key = normalize_key(r["category"], key, r["level"], r["country_code"])
        present.setdefault(r["category"], set()).add(key)

    by_category = {
        slug: cell_coverage(keys, present.get(slug, set()))
        for slug, keys in expected.items()
    }
    return {"registry_definitive": True, "by_category": by_category}
