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

``aggregate_company_coordinates`` and ``cell_coverage`` are pure (no DB, no AI)
so they unit-test without fixtures.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Pure aggregation ────────────────────────────────────────────────────────


def aggregate_company_coordinates(coords: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Union per-location ``resolve_scope`` results into one company verdict. Pure.

    ``coords`` items (from :func:`resolve_company_scope`):
      ``{state, city, resolved, engine_definitive, codified_keys, uncodified,
         counts, unmodeled}``.

    ``coverage_source`` is ``"engine"`` only when there is at least one resolved
    coordinate, EVERY resolved coordinate is engine-definitive, and none degraded
    (an unmodeled state/city makes coverage uncertain — fall back conservatively).
    ``coverage_pct`` uses the same ``covered / (covered + gaps)`` formula the bank
    path uses, so the two numbers are comparable.
    """
    resolved = [c for c in coords if c.get("resolved")]

    codified_keys = set()
    for c in resolved:
        codified_keys |= {k for k in (c.get("codified_keys") or []) if k}

    # Dedupe uncodified on (regulation_key, citation); a key codified in ANY
    # location counts as codified for the company, so drop it from the queue.
    seen = set()
    uncodified: List[Dict[str, Any]] = []
    for c in resolved:
        for u in (c.get("uncodified") or []):
            k = u.get("regulation_key")
            sig = (k, u.get("citation"))
            if sig in seen:
                continue
            seen.add(sig)
            if k and k in codified_keys:
                continue
            uncodified.append(u)

    degraded = any(c.get("unmodeled") for c in resolved)
    engine = bool(resolved) and all(c.get("engine_definitive") for c in resolved) and not degraded

    codified_n = len(codified_keys)
    uncodified_n = len(uncodified)
    denom = codified_n + uncodified_n
    provisional = sum(int((c.get("counts") or {}).get("provisional", 0)) for c in resolved)
    unmodeled = [u for c in resolved for u in (c.get("unmodeled") or [])]

    return {
        "coverage_source": "engine" if engine else "bank",
        "codified_keys": sorted(codified_keys),
        "uncodified": uncodified,
        "counts": {
            "locations": len(resolved),
            "codified": codified_n,
            "uncodified": uncodified_n,
            "provisional": provisional,
        },
        "coverage_pct": round(100 * codified_n / denom) if denom else 100,
        "gate": {
            "total": len(resolved),
            "engine": sum(1 for c in resolved if c.get("engine_definitive")),
            "fallback": sum(1 for c in resolved if not c.get("engine_definitive")),
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


async def resolve_company_scope(
    conn,
    company_id,
    *,
    industry: Optional[str],
    specialty: Optional[str] = None,
    employee_count: Optional[int] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Resolve the registry scope for every one of a company's business locations
    and union the result (via :func:`aggregate_company_coordinates`).

    Reuses the per-location loop that ``shadow.record_shadow`` runs: only
    stateful, active, non-company-wide locations (so ``resolve_scope``'s
    "requires a state" guard is never hit). ``employee_count`` is injected into
    ``facility_attributes`` when absent so conditional labor strata (e.g. FMLA
    ≥ 50) resolve. Each coordinate is gated independently by
    ``registry_expected_keys`` — non-None ⇒ that coordinate is engine-definitive.
    """
    from .resolve import parse_jsonb, resolve_scope

    category = specialty or industry
    if not company_id or not category:
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
    for loc in locations:
        attrs = parse_jsonb(loc["facility_attributes"]) or {}
        if employee_count is not None and "employee_count" not in attrs:
            attrs = {**attrs, "employee_count": employee_count}
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
            coords.append({
                "state": loc["state"], "city": loc["city"], "resolved": False,
                "engine_definitive": False, "codified_keys": [], "uncodified": [],
                "counts": {}, "unmodeled": [],
            })
            continue

        definitive = False
        try:
            from app.core.services.compliance_evals.completeness import registry_expected_keys
            expected = await registry_expected_keys(
                conn, res["coordinate"]["jurisdiction_ids"], category,
            )
            definitive = expected is not None
        except Exception:
            logger.exception("gap_surfaces: gate check failed for company %s", company_id)

        coords.append({
            "state": loc["state"],
            "city": loc["city"],
            "resolved": True,
            "engine_definitive": definitive,
            "codified_keys": [c["regulation_key"] for c in res["codified"] if c.get("regulation_key")],
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
    """
    from app.core.services.compliance_evals.completeness import registry_expected_keys

    expected = await registry_expected_keys(conn, list(chain_ids), industry)
    if expected is None:
        return {"registry_definitive": False, "by_category": {}}

    rows = await conn.fetch(
        """
        SELECT category, regulation_key
        FROM jurisdiction_requirements
        WHERE jurisdiction_id = ANY($1::uuid[])
          AND regulation_key IS NOT NULL
          AND COALESCE(status, 'active') = 'active'
        """,
        list(chain_ids),
    )
    present: Dict[str, set] = {}
    for r in rows:
        present.setdefault(r["category"], set()).add(r["regulation_key"])

    by_category = {
        slug: cell_coverage(keys, present.get(slug, set()))
        for slug, keys in expected.items()
    }
    return {"registry_definitive": True, "by_category": by_category}
