"""Eval orchestration: run suites, persist runs/results/findings, publish progress.

The runner is the only thing here that writes. It writes to the three eval tables
and nowhere else — in particular it never touches ``jurisdiction_requirements``,
so a bad eval can corrupt a scorecard but can never corrupt the catalog.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

from app.database import get_connection

from . import authority as authority_suite
from . import baseline as baseline_suite
from . import completeness as completeness_suite
from . import golden as golden_suite
from . import grounding as grounding_suite
from . import scope as scope_suite
from . import industry_keysets as iks
from . import tagging as tagging_suite
from .scoring import Subscores, composite_score, evaluate_readiness

logger = logging.getLogger(__name__)

ALL_SUITES = ("completeness", "authority", "tagging", "golden", "scope", "grounding", "baseline")
DEFAULT_STALENESS_DAYS = 90

# Suites that reach the network. Routed to Celery rather than BackgroundTasks so a
# slow regulator host cannot occupy a uvicorn worker for minutes. `authority` is
# always network; `grounding` is network ONLY when its LLM verifier (tier-2b) is
# enabled — otherwise it's pure tier-1 + golden and stays inline. Use
# network_suites() (not this base set) to decide routing.
NETWORK_SUITES = frozenset({"authority"})


def network_suites() -> frozenset:
    """Suites that reach the network for the CURRENT config. Adds `grounding` when
    the tier-2b LLM verifier flag is on (that's the only thing that makes grounding
    do I/O)."""
    from app.config import get_settings

    extra = {"grounding"} if get_settings().grounding_llm_verifier_enabled else set()
    return NETWORK_SUITES | extra


def _progress(run_id: UUID, message: str, pct: int) -> None:
    try:
        from app.workers.notifications import publish_task_progress

        publish_task_progress(
            "admin:compliance_evals",
            "compliance_evals",
            str(run_id),
            pct,
            100,
            message,
        )
    except Exception:  # progress is best-effort; never fail a run over it
        logger.debug("progress publish failed", exc_info=True)


async def _freshness_by_jurisdiction(conn, jurisdiction_ids: Optional[List] = None) -> Dict:
    """Fraction of each jurisdiction's rows re-verified inside their key's SLA.

    Reuses the staleness SLA already declared per regulation key
    (``regulation_key_definitions.staleness_warning_days``), defaulting to 90 days
    for keys with no definition row.
    """
    sql = """
        SELECT jr.jurisdiction_id,
               COUNT(*) AS total,
               COUNT(*) FILTER (
                   WHERE jr.last_verified_at >= NOW() - (
                       COALESCE(rkd.staleness_warning_days, $1) || ' days'
                   )::interval
               ) AS within_sla
        FROM jurisdiction_requirements jr
        LEFT JOIN regulation_key_definitions rkd ON rkd.key = jr.regulation_key
    """
    params: List[Any] = [DEFAULT_STALENESS_DAYS]
    if jurisdiction_ids:
        sql += " WHERE jr.jurisdiction_id = ANY($2::uuid[])"
        params.append(jurisdiction_ids)
    sql += " GROUP BY jr.jurisdiction_id"

    try:
        rows = await conn.fetch(sql, *params)
    except Exception:
        logger.warning("freshness query failed", exc_info=True)
        return {}

    from .scoring import freshness_score

    return {
        r["jurisdiction_id"]: {
            "score": freshness_score(r["within_sla"], r["total"]),
            "detail": {"within_sla": r["within_sla"], "total": r["total"]},
        }
        for r in rows
    }


async def _resolve_jurisdiction_ids(conn, jurisdiction_ids: Optional[List[str]]) -> List:
    if jurisdiction_ids:
        return [UUID(str(j)) for j in jurisdiction_ids]
    rows = await conn.fetch(
        "SELECT id FROM jurisdictions WHERE level::text NOT IN ('federal','national')"
    )
    return [r["id"] for r in rows]


async def _insert_findings(conn, run_id: UUID, findings: List[Dict]) -> None:
    if not findings:
        return
    await conn.executemany(
        """
        INSERT INTO compliance_eval_findings (
            run_id, suite, finding_type, severity, jurisdiction_id, requirement_id,
            requirement_key, category, industry, expected, observed
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        [
            (
                run_id,
                f["suite"],
                f["finding_type"],
                f.get("severity", "warn"),
                f.get("jurisdiction_id"),
                f.get("requirement_id"),
                f.get("requirement_key"),
                f.get("category"),
                f.get("industry"),
                json.dumps(f["expected"]) if f.get("expected") is not None else None,
                json.dumps(f["observed"]) if f.get("observed") is not None else None,
            )
            for f in findings
        ],
    )


async def _insert_result(
    conn,
    run_id: UUID,
    jurisdiction_id,
    industry: Optional[str],
    suite: str,
    score: Optional[float],
    detail: Optional[Dict],
    onboarding_ready: Optional[bool] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO compliance_eval_results (
            run_id, jurisdiction_id, industry, suite, score, detail, onboarding_ready
        ) VALUES ($1,$2,$3,$4,$5,$6,$7)
        ON CONFLICT (run_id, jurisdiction_id, COALESCE(industry, ''), suite) DO NOTHING
        """,
        run_id, jurisdiction_id, industry, suite,
        score, json.dumps(detail or {}), onboarding_ready,
    )


async def run_evals(
    *,
    suites: Optional[List[str]] = None,
    jurisdiction_ids: Optional[List[str]] = None,
    industries: Optional[List[str]] = None,
    triggered_by: Optional[UUID] = None,
    trigger_source: str = "manual",
    run_id: Optional[UUID] = None,
) -> UUID:
    """Execute the requested suites and persist a scorecard. Returns the run id."""
    suites = [s for s in (suites or list(ALL_SUITES)) if s in ALL_SUITES]
    if not suites:
        raise ValueError("no valid suites requested")
    industries = industries or iks.SUPPORTED_INDUSTRIES

    async with get_connection() as conn:
        if run_id is None:
            row = await conn.fetchrow(
                """
                INSERT INTO compliance_eval_runs (suites, trigger_source, triggered_by, params)
                VALUES ($1,$2,$3,$4) RETURNING id
                """,
                suites, trigger_source, triggered_by,
                json.dumps({"jurisdiction_ids": jurisdiction_ids, "industries": industries}),
            )
            run_id = row["id"]

        try:
            jur_ids = await _resolve_jurisdiction_ids(conn, jurisdiction_ids)
            totals: Dict[str, Any] = {}
            all_findings: List[Dict] = []

            completeness_results: Dict = {}
            authority_results: Dict = {}
            tagging_results: Dict = {}
            golden_results: Dict = {}
            golden_counts: Dict = {}
            grounding_results: Dict = {}
            baseline_results: Dict = {}
            scope_results: Dict = {}

            if "completeness" in suites:
                _progress(run_id, "Building jurisdiction graph", 5)
                graph = await completeness_suite.load_jurisdiction_graph(conn)
                _progress(run_id, "Scoring completeness", 15)
                out = await completeness_suite.run_completeness(
                    conn, graph, jur_ids, industries
                )
                completeness_results = out["results"]
                all_findings.extend(out["findings"])
                totals["completeness_cells"] = len(completeness_results)

            if "tagging" in suites:
                _progress(run_id, "Auditing tags and key integrity", 40)
                out = await tagging_suite.run_tagging(conn, jur_ids)
                tagging_results = out["results"]
                all_findings.extend(out["findings"])

            if "golden" in suites:
                _progress(run_id, "Comparing against golden facts", 55)
                out = await golden_suite.run_golden(conn)
                golden_results = out["results"]
                golden_counts = out["fact_counts"]
                all_findings.extend(out["findings"])
                totals["golden_facts_asserted"] = sum(golden_counts.values())

            if "authority" in suites:
                _progress(run_id, "Checking citations (network)", 70)
                out = await authority_suite.run_authority(conn, jur_ids)
                authority_results = out["results"]
                all_findings.extend(out["findings"])
                totals["urls_checked"] = len(out["url_liveness"])

            if "scope" in suites:
                _progress(run_id, "Auditing scope-registry coverage", 80)
                out = await scope_suite.run_scope(conn, jur_ids)
                # Indexes attributed to a jurisdiction now carry a subscore
                # (confirmed-classified + codified fraction). Federal indexes
                # attribute to NULL and can't ride the per-jurisdiction
                # scorecard — their criticals gate readiness instead, via the
                # federal_criticals bucket below.
                scope_results = {
                    jid: cell for jid, cell in (out.get("results") or {}).items()
                    if jid is not None
                }
                all_findings.extend(out["findings"])
                totals.update(out["totals"])

            if "grounding" in suites:
                _progress(run_id, "Verifying grounded values against cited text", 83)
                out = await grounding_suite.run_grounding(conn, jur_ids)
                grounding_results = out["results"]
                all_findings.extend(out["findings"])
                totals.update({f"grounding_{k}": v for k, v in out["totals"].items()})

            if "baseline" in suites:
                _progress(run_id, "Scoring federal + CA labor baseline", 84)
                # Resolves its OWN base jurisdictions (federal + CA-state) — does
                # NOT use jur_ids, which excludes federal by default.
                out = await baseline_suite.run_baseline(conn)
                baseline_results = out["results"]
                all_findings.extend(out["findings"])
                totals.update({f"baseline_{k}": v for k, v in out["totals"].items()})

            _progress(run_id, "Computing freshness", 85)
            freshness_results = await _freshness_by_jurisdiction(conn, jur_ids)

            _progress(run_id, "Persisting findings", 90)
            await _insert_findings(conn, run_id, all_findings)

            # Per-jurisdiction critical counts, so the readiness gate can block on them.
            critical_by_jur: Dict = {}
            critical_by_pair: Dict = {}
            federal_criticals = 0
            for f in all_findings:
                if f.get("severity") != "critical":
                    continue
                # Baseline scores the federal + CA-state BASE layer; its criticals
                # are a data-side signal on those jurisdictions, not a per-company
                # gate. Folding them into critical_by_jur would (a) block CA-state's
                # every-industry composite the moment a base-layer key is missing and
                # (b) do nothing for federal (excluded from jur_ids). Keep baseline
                # out of the onboarding-readiness gate — it has its own scorecard.
                if f.get("suite") == "baseline":
                    continue
                jid = f.get("jurisdiction_id")
                if jid is None:
                    # Federal-attributed criticals (scope emits jurisdiction_id
                    # NULL for the federal index). These were dropped entirely,
                    # so a jurisdiction could read READY sitting on top of a
                    # broken federal baseline that applies to every US employer
                    # (COMPLIANCE_SYSTEM_GAP_REVIEW.md §5). Federal law applies
                    # everywhere: block every jurisdiction on them.
                    federal_criticals += 1
                    continue
                if f.get("industry"):
                    critical_by_pair[(jid, f["industry"])] = (
                        critical_by_pair.get((jid, f["industry"]), 0) + 1
                    )
                else:
                    critical_by_jur[jid] = critical_by_jur.get(jid, 0) + 1

            _progress(run_id, "Writing scorecard", 95)
            for jid in jur_ids:
                for suite_name, res in (
                    ("authority", authority_results),
                    ("tagging", tagging_results),
                    ("golden", golden_results),
                    ("freshness", freshness_results),
                    ("grounding", grounding_results),
                    ("scope", scope_results),
                ):
                    cell = res.get(jid)
                    if cell:
                        await _insert_result(
                            conn, run_id, jid, None, suite_name,
                            cell["score"], cell["detail"],
                        )

                for industry in industries:
                    comp = completeness_results.get((jid, industry))
                    if comp:
                        await _insert_result(
                            conn, run_id, jid, industry, "completeness",
                            comp["score"], comp["detail"],
                        )

                    subs = Subscores(
                        completeness=comp["score"] if comp else None,
                        accuracy=(golden_results.get(jid) or {}).get("score"),
                        authority=(authority_results.get(jid) or {}).get("score"),
                        freshness=(freshness_results.get(jid) or {}).get("score"),
                        tagging=(tagging_results.get(jid) or {}).get("score"),
                        scope=(scope_results.get(jid) or {}).get("score"),
                    )
                    readiness = evaluate_readiness(
                        subs,
                        focused_keys_complete=bool(
                            comp and comp["detail"].get("focused_keys_complete")
                        ),
                        open_critical_findings=(
                            critical_by_jur.get(jid, 0)
                            + critical_by_pair.get((jid, industry), 0)
                            + federal_criticals
                        ),
                        golden_fact_count=golden_counts.get(jid, 0),
                    )
                    await _insert_result(
                        conn, run_id, jid, industry, "composite",
                        composite_score(subs),
                        {
                            "subscores": subs.as_dict(),
                            "status": readiness.status,
                            "blocking": readiness.blocking,
                        },
                        readiness.ready,
                    )

            # Baseline persists on its own jurisdictions (federal + CA-state), which
            # are not in jur_ids — so it can't ride the per-jur scorecard loop above.
            for jid, cell in baseline_results.items():
                await _insert_result(
                    conn, run_id, jid, None, "baseline",
                    cell["score"], cell["detail"],
                )

            # Same problem for golden: _resolve_jurisdiction_ids excludes federal,
            # so the 13 US-federal golden facts were asserted (and emitted findings)
            # every run but their score was never stored — the federal baseline had
            # no accuracy cell at all (COMPLIANCE_SYSTEM_GAP_REVIEW.md §5).
            jur_id_set = set(jur_ids)
            for jid, cell in golden_results.items():
                if jid not in jur_id_set:
                    await _insert_result(
                        conn, run_id, jid, None, "golden",
                        cell["score"], cell["detail"],
                    )

            totals["findings"] = len(all_findings)
            await conn.execute(
                "UPDATE compliance_eval_runs SET status='completed', finished_at=NOW(), "
                "totals=$2 WHERE id=$1",
                run_id, json.dumps(totals),
            )
            _progress(run_id, "Complete", 100)

        except Exception as exc:
            logger.exception("compliance eval run %s failed", run_id)
            await conn.execute(
                "UPDATE compliance_eval_runs SET status='failed', finished_at=NOW(), "
                "error_text=$2 WHERE id=$1",
                run_id, str(exc)[:2000],
            )
            raise

    return run_id


def _missing_from_checklist(core: Dict) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for item in core["items"]:
        if not item["present"]:
            out.setdefault(item["category"], []).append(item["key"])
    return out


async def onboarding_readiness(
    conn,
    *,
    industry: str,
    state: Optional[str],
    city: Optional[str],
    country_code: str = "US",
    depth: str = "full",
) -> Dict:
    """The headline question, answerable without a stored run.

    Completeness is deterministic, so it is computed live. Accuracy / authority /
    freshness / tagging are merged from the most recent run that measured them —
    absent entirely if the suites have never been run, which correctly yields
    NOT_READY rather than a flattering silence.
    """
    canonical = iks.resolve_industry(industry) or industry
    if city:
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE LOWER(city)=LOWER($1) AND state=$2 "
            "AND COALESCE(country_code,'US')=$3 LIMIT 1",
            city, state, country_code,
        )
    else:
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE level::text='state' AND state=$1 "
            "AND COALESCE(country_code,'US')=$2 LIMIT 1",
            state, country_code,
        )
    if not row:
        return {
            "found": False,
            "status": "NOT_READY",
            "blocking": ["no jurisdiction record for this location"],
            "industry": canonical,
        }

    jid = row["id"]
    graph = await completeness_suite.load_jurisdiction_graph(conn)

    # `core` scores the ≤30-key must-have checklist; `full` scores the whole
    # registry sweep (201 keys for manufacturing). The gate reads whichever the
    # caller asked for, and the response always carries the core checklist when
    # one exists so the verdict can be audited key by key.
    core = None
    if iks.has_core(canonical):
        core = completeness_suite.core_checklist(graph, jid, canonical)

    if depth == "core":
        if core is None:
            raise ValueError(f"no core keyset curated for industry {canonical!r}")
        cell = {
            "score": core["score"],
            "detail": {
                "missing_keys": _missing_from_checklist(core),
                "focused_keys_complete": core["complete"],
                "focused_categories": sorted({i["category"] for i in core["items"]}),
            },
        }
        findings = []
    else:
        cell, findings = await completeness_suite.evaluate_pair(
            conn, graph, jid, canonical, {}
        )

    # The eval tables may not exist yet (migration jureval01 unapplied) or may
    # simply hold no run for this jurisdiction. Both mean "never measured", which
    # the readiness gate already handles as NOT_READY — so degrade, don't 500.
    try:
        latest = await conn.fetch(
            """
            SELECT DISTINCT ON (suite) suite, score, detail
            FROM compliance_eval_results
            WHERE jurisdiction_id = $1 AND industry IS NULL
            ORDER BY suite, created_at DESC
            """,
            jid,
        )
    except asyncpg.UndefinedTableError:
        logger.warning("compliance_eval_results missing; migration jureval01 not applied")
        latest = []
    by_suite = {r["suite"]: r for r in latest}

    def _score(name: str) -> Optional[float]:
        r = by_suite.get(name)
        return float(r["score"]) if r and r["score"] is not None else None

    golden_detail = by_suite.get("golden")
    golden_count = 0
    if golden_detail and golden_detail["detail"]:
        d = golden_detail["detail"]
        if isinstance(d, str):
            d = json.loads(d)
        golden_count = (d.get("passed", 0) or 0) + (d.get("failed", 0) or 0)

    try:
        open_critical = await conn.fetchval(
            """
            SELECT COUNT(*) FROM compliance_eval_findings
            WHERE status = 'open' AND severity = 'critical'
              AND suite <> 'baseline'
              AND (
                  (jurisdiction_id = $1 AND (industry IS NULL OR industry = $2))
                  -- Federal-attributed criticals (scope emits jurisdiction_id
                  -- NULL for the federal index) bind every US jurisdiction, so
                  -- they gate everyone — mirroring run_evals' federal_criticals
                  -- bucket. Without this the live endpoint and the stored run
                  -- disagree: the run says NOT_READY, this says READY, on the
                  -- same broken federal baseline.
                  OR jurisdiction_id IS NULL
              )
            """,
            jid, canonical,
        )
    except asyncpg.UndefinedTableError:
        open_critical = 0

    subs = Subscores(
        completeness=cell["score"],
        accuracy=_score("golden"),
        authority=_score("authority"),
        freshness=_score("freshness"),
        tagging=_score("tagging"),
        scope=_score("scope"),
    )
    readiness = evaluate_readiness(
        subs,
        focused_keys_complete=bool(cell["detail"].get("focused_keys_complete")),
        open_critical_findings=int(open_critical or 0),
        golden_fact_count=golden_count,
    )

    return {
        "found": True,
        "jurisdiction_id": str(jid),
        "industry": canonical,
        "depth": depth,
        "status": readiness.status,
        "ready": readiness.ready,
        "subscores": subs.as_dict(),
        "composite": composite_score(subs),
        "blocking": readiness.blocking,
        "missing_keys": cell["detail"]["missing_keys"],
        "focused_categories": cell["detail"]["focused_categories"],
        "golden_fact_count": golden_count,
        "open_critical_findings": int(open_critical or 0),
        "live_missing_key_findings": len(findings),
        # Always present when the industry has one, whatever `depth` scored the
        # gate — it is the artifact a human can actually check line by line.
        "core_checklist": core,
    }
