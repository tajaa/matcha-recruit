"""The scope→fetch-queue→research→reconcile wire — the corpus-building and
body-prefetch subroutines are shared by the admin SSE endpoint (``POST
/admin/scope-registry/fetch-queue/research``, ``routes/scope_registry.py``)
and the headless scheduled task (``workers/tasks/scope_registry.py``).

``run_research_cycle`` is the task's own full chain (chain_uncodified →
group → prefetch → research → reconcile); the SSE route keeps its own
per-unit loop (a generator can't cleanly delegate its yield points to a
shared awaited callback) but calls the same ``bodies_for_unit`` /
``prefetch_bodies`` this module exports, so both callers fetch grounding
corpora identically.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def bodies_for_unit(conn, unit) -> tuple:
    """Fetch the unit items' statute bodies and render the grounded corpus."""
    from .grounded import build_grounded_corpus

    item_ids = [it["item_id"] for it in unit["items"] if it.get("item_id")]
    if not item_ids:
        return "", {}
    rows = await conn.fetch(
        "SELECT id AS item_id, citation, heading, body_text "
        "FROM authority_index_items WHERE id = ANY($1::uuid[])",
        item_ids,
    )
    return build_grounded_corpus([dict(r) for r in rows])


async def prefetch_bodies(conn, units: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Best-effort statute-text prefetch for any worklist index whose items
    don't have bodies yet, so research extracts values from the source
    instead of model recall. A fetch failure just falls back to ungrounded
    research for that unit — never raises.
    """
    from .body_fetch import fetch_bodies_for_index

    bodyless_slugs = sorted({
        it["index_slug"] for u in units for it in u["items"]
        if it.get("index_slug") and not it.get("has_body")
    })
    fetched = 0
    for slug in bodyless_slugs:
        try:
            res = await fetch_bodies_for_index(conn, slug)
            fetched += (res or {}).get("fetched", 0) if isinstance(res, dict) else 0
        except Exception as exc:
            logger.warning("body prefetch failed for %s: %s", slug, exc)
    return {"slugs": bodyless_slugs, "fetched": fetched}


async def corpus_for_jurisdiction(
    conn, jurisdiction_id, categories: List[str],
) -> tuple:
    """Grounded corpus for a jurisdiction + category set, for callers that
    research a jurisdiction directly rather than a pre-grouped research unit
    (the legacy specialty-research path, admin.py). Best-effort: returns
    ``("", {})`` when the registry has no classified authority covering this
    chain, which degrades that caller to ungrounded research — exactly what it
    did before, never worse.
    """
    from .codify import chain_uncodified

    try:
        jur = await conn.fetchrow(
            "SELECT state, city FROM jurisdictions WHERE id = $1", jurisdiction_id
        )
        if not jur or not jur["state"]:
            return "", {}

        work = await chain_uncodified(conn, state=jur["state"], city=jur["city"] or None)
        wanted = set(categories or ())
        items = [
            it for it in work["keyed"]
            if not wanted or it.get("category_slug") in wanted
        ]
        if not items:
            return "", {}

        await prefetch_bodies(conn, [{"items": items}])
        return await bodies_for_unit(conn, {"items": items})
    except Exception as exc:
        logger.warning("corpus_for_jurisdiction failed for %s: %s", jurisdiction_id, exc)
        return "", {}


async def run_research_units(
    conn,
    units: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Research every unit against its grounded corpus.

    Returns ``{"total_new": int, "results": [...]}``, one result dict per unit
    with ``jurisdiction_id``, ``new``, ``failed``, ``grounded``,
    ``penalties_stripped`` (and ``error`` on a per-unit failure — a unit
    failing never aborts the rest of the run).
    """
    from app.core.services.compliance_service import research_specialization_for_jurisdiction

    total_new = 0
    results: List[Dict[str, Any]] = []
    for unit in units:
        try:
            corpus, citation_index = await bodies_for_unit(conn, unit)
            res = await research_specialization_for_jurisdiction(
                conn, unit["jurisdiction_id"], unit["categories"],
                industry_tag="", industry_context=unit["context"],
                skip_existing=False,
                grounded_corpus=corpus, citation_index=citation_index,
            )
            new = res.get("new", 0)
            total_new += new
            entry = {"jurisdiction_id": unit["jurisdiction_id"], "new": new,
                      "failed": res.get("failed", []), "grounded": bool(corpus),
                      "penalties_stripped": res.get("penalties_stripped", 0)}
        except Exception as exc:  # a unit failing must not kill the run
            logger.warning("research unit failed for jurisdiction %s: %s",
                            unit["jurisdiction_id"], exc)
            entry = {"jurisdiction_id": unit["jurisdiction_id"], "new": 0, "error": str(exc)}
        results.append(entry)
    return {"total_new": total_new, "results": results}


async def run_research_cycle(
    conn,
    *,
    state: Optional[str] = None,
    city: Optional[str] = None,
    max_units: Optional[int] = None,
) -> Dict[str, Any]:
    """The full headless chain: chain_uncodified → group into units →
    prefetch bodies → research each (grounded) → reconcile.

    ``max_units`` caps the per-cycle work (a scheduled task's max_per_cycle
    knob) — units are already severity-ordered by ``group_research_units``,
    so a cap researches the highest-severity gaps first.

    Returns a summary dict: ``units``, ``unkeyed``, ``bodies_fetched``,
    ``total_new``, ``linked``, ``still_uncodified``, ``still_unkeyed``.
    """
    from .codify import chain_uncodified, group_research_units, reconcile_codifications

    work = await chain_uncodified(conn, state=state, city=city)
    units = group_research_units(
        work["keyed"],
        federal_id=work["chain"]["federal_id"],
        state_id=work["chain"]["state_id"],
        city_id=work["chain"]["city_id"],
    )
    if max_units is not None:
        units = units[:max_units]

    if not units:
        return {"units": 0, "unkeyed": len(work["unkeyed"]), "bodies_fetched": 0,
                "total_new": 0, "linked": 0, "still_uncodified": 0,
                "still_unkeyed": len(work["unkeyed"])}

    prefetch = await prefetch_bodies(conn, units)
    ran = await run_research_units(conn, units)

    recon = await reconcile_codifications(
        conn, state=state, city=city, source="scheduled_research",
        run_info={"task": "scope_registry_research", "units": len(units),
                  "new_requirements": ran["total_new"]},
    )
    after = await chain_uncodified(conn, state=state, city=city)
    return {
        "units": len(units),
        "unkeyed": len(work["unkeyed"]),
        "bodies_fetched": prefetch["fetched"],
        "total_new": ran["total_new"],
        "linked": recon["inserted"] + recon["updated"],
        "still_uncodified": len(after["keyed"]),
        "still_unkeyed": len(after["unkeyed"]),
    }
