"""Commit staged research: activate + codify, lifted out of the route.

This is the exact body of the legacy `POST /actions/{id}/approve` route
(`core/routes/admin_tools/admin_compliance_pilot.py`, previously :405-553),
extracted so BOTH the legacy REST endpoint and the agentic loop's
`stage_approve` → `confirm_action` path share one implementation. The route
still owns the HTTP shape (404/400 mapping, `BackgroundTasks`); this module
owns the work.

Two-phase commit, same as before:

1. `research_review.approve_staged` — the shared core: activates `pending`
   rows, then reconciles against the Gen-2 registry (only fires when a
   confirmed classification already carries this `regulation_key` — most
   research-staged rows have no such classification yet, since the registry
   corpus is federal + California only).
2. Per-row MINT via `codify_from_requirement`, using the citation the
   RESEARCH RUN ITSELF returned (`metadata.research_citation` /
   `grounded_citations`) — this is what actually codifies most Gen-1 rows,
   independent of whether Gen-2 has scoped the same obligation. Gated by the
   deterministic `_codify_gate`; a gate failure leaves the row live but
   uncodified with the reason recorded, never blocking the activation.

Each mint runs in its own transaction, so a mid-mint failure can't leave a
half-written classification a later reconcile silently stamps authoritative.
Reconcile then runs ONCE per distinct (state, city) among the rows actually
minted — never once per row.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from app.database import get_connection
from app.core.services.change_context import set_change_context
from app.core.services.compliance_pilot.core import _codify_gate

logger = logging.getLogger(__name__)


async def _embed_bg(jurisdiction_ids: list) -> None:
    from app.core.services.compliance_embedding_pipeline import embed_updated_requirements
    try:
        async with get_connection() as conn:
            for jid in jurisdiction_ids:
                await embed_updated_requirements(conn, jid)
    except Exception:
        logger.exception("compliance_pilot: post-approve embed failed")


async def _snapshot_bg(snap_targets: list) -> None:
    """Freeze each newly-committed row's cited page — a pilot commit is a
    tenant-visibility moment, same as the admin approve (which snapshots too)."""
    import httpx
    from app.core.services.source_snapshot import snapshot_source
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for req_id, url in snap_targets:
                async with get_connection() as conn:
                    await snapshot_source(conn, req_id, url, "approve", client=client)
    except Exception:
        logger.exception("compliance_pilot: post-approve snapshot failed")


async def approve_from_action(
    from_action_id: str,
    ids: list[str],
    actor_id: Optional[UUID],
    *,
    existing_action_id: Optional[str] = None,
) -> dict[str, Any]:
    """Commit the selected staged requirement ids from `from_action_id`'s
    research run.

    `existing_action_id` is None for the legacy REST route (which INSERTs a
    fresh 'approve' action row for the audit trail) and set for the agentic
    confirm path (which instead UPDATEs the already-inserted 'approve'
    proposal row from running -> done, so confirming never creates a second
    action row for the same commit).

    Returns `{action_id, jurisdiction_ids, snap_targets, activated, codified,
    uncodified, already_live, results}` — the caller schedules `_embed_bg`
    (jurisdiction_ids) and `_snapshot_bg` (snap_targets) as background tasks;
    this function does no scheduling of its own so it stays awaitable from
    both a FastAPI route (`BackgroundTasks`) and a detached asyncio task
    (`asyncio.create_task`).
    """
    from app.core.services.research_review import approve_staged
    from app.core.services.scope_registry.codify import codify_from_requirement, reconcile_codifications

    async with get_connection() as conn:
        act = await conn.fetchrow(
            "SELECT session_id, kind, staged_ids, status FROM compliance_pilot_actions WHERE id = $1",
            from_action_id,
        )
        if not act:
            raise LookupError("Action not found")
        if act["kind"] != "research":
            raise ValueError("Only research actions can be codified")
        staged = [str(s) for s in (act["staged_ids"] or [])]
        if ids:
            want = set(ids)
            staged = [s for s in staged if s in want]
        if not staged:
            raise ValueError("Nothing selected to commit")
        rows = await conn.fetch(
            "SELECT r.id, r.jurisdiction_id, r.title, r.regulation_key, r.source_url, "
            "       r.source_url_status, r.metadata, j.state, j.city "
            "FROM jurisdiction_requirements r JOIN jurisdictions j ON j.id = r.jurisdiction_id "
            "WHERE r.id = ANY($1::uuid[]) AND r.status='pending'",
            [UUID(s) for s in staged],
        )
    pending_ids = [r["id"] for r in rows]
    jurisdiction_ids = list({r["jurisdiction_id"] for r in rows})
    already_live = len(staged) - len(pending_ids)

    # 1. Activate (shared core; also reconciles keys the Gen-2 registry already
    #    has a confirmed classification for).
    core = await approve_staged(pending_ids, actor_id, source="pilot_commit")
    activated_ids = {o["id"] for o in core["results"]}

    # 2. Per-row: gate -> MINT the codify trio off the research run's OWN
    #    citation (no reconcile yet — batched below).
    outcomes_by_id: dict = {}
    minted: list = []
    reconcile_pairs: set = set()
    async with get_connection() as conn:
        await set_change_context(conn, "pilot_commit", actor_id)
        for r in rows:
            rid = str(r["id"])
            o = {"id": rid, "title": r["title"], "state": r["state"], "city": r["city"],
                 "activated": rid in activated_ids, "codified": False,
                 "statute_citation": None, "citation_url": None, "gate_reason": None}
            outcomes_by_id[rid] = o
            if not o["activated"]:
                o["gate_reason"] = "no longer pending (handled elsewhere)"
                continue
            meta = r["metadata"]
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            meta = meta or {}
            citation = meta.get("research_citation") or (meta.get("grounded_citations") or [None])[0]
            ok, reason, _cls = _codify_gate(
                r["regulation_key"], citation, r["source_url"], r["source_url_status"])
            if not ok:
                o["gate_reason"] = reason
                continue
            try:
                async with conn.transaction():
                    await codify_from_requirement(
                        conn, r["id"], citation=citation, source_url=r["source_url"],
                        admin_id=actor_id, run_reconcile=False)
                minted.append(r)
                st = (r["state"] or "").upper() or None
                reconcile_pairs.add((st, (r["city"] or "").lower() or None))
            except Exception as exc:  # noqa: BLE001 — row is already live; never fail approve
                logger.warning("compliance_pilot: codify mint failed for %s: %s", r["id"], exc)
                o["gate_reason"] = f"codify error: {str(exc)[:120]}"

        # 3. ONE reconcile per distinct (state, city) for all minted rows.
        for st, ci in sorted(reconcile_pairs, key=lambda p: (p[0] or "", p[1] or "")):
            if st:
                try:
                    await reconcile_codifications(conn, state=st, city=ci, source="pilot_commit")
                except Exception as exc:
                    logger.warning("compliance_pilot: reconcile failed for %s/%s: %s", st, ci, exc)

        # 4. Batch-read the stamped state for minted rows -> final verdict.
        if minted:
            stamped = await conn.fetch(
                "SELECT r.id, r.statute_citation, r.citation_verified_at IS NOT NULL AS authoritative, "
                "       ai.source_url AS citation_url "
                "FROM jurisdiction_requirements r "
                "LEFT JOIN authority_index_items ai ON ai.id = r.citation_item_id "
                "WHERE r.id = ANY($1::uuid[])",
                [r["id"] for r in minted],
            )
            for s in stamped:
                o = outcomes_by_id[str(s["id"])]
                o["codified"] = s["authoritative"]
                o["statute_citation"] = s["statute_citation"]
                o["citation_url"] = s["citation_url"]
                if not s["authoritative"]:
                    o["gate_reason"] = "codify ran but the citation wasn't stamped"

    outcomes = [outcomes_by_id[str(r["id"])] for r in rows]
    codified_n = sum(1 for o in outcomes if o["codified"])

    snap_map = {rid: url for rid, url in core["snap_targets"]}
    for r in minted:
        o = outcomes_by_id[str(r["id"])]
        if o["codified"]:
            snap_map[r["id"]] = o["citation_url"] or r["source_url"]
    snap_targets = [(k, v) for k, v in snap_map.items() if v]

    result = {
        "activated": core["activated"], "codified": codified_n,
        "uncodified": len(outcomes) - codified_n, "already_live": already_live,
        "results": outcomes,
    }

    async with get_connection() as conn:
        if existing_action_id is None:
            arow = await conn.fetchrow(
                "INSERT INTO compliance_pilot_actions "
                "(session_id, kind, params, status, result, actor_id, finished_at) "
                "VALUES ($1, 'approve', $2::jsonb, 'done', $3::jsonb, $4, NOW()) RETURNING id",
                act["session_id"], json.dumps({"from_action": from_action_id}),
                json.dumps(result), actor_id,
            )
            action_id = str(arow["id"])
        else:
            await conn.execute(
                "UPDATE compliance_pilot_actions SET status='done', result=$2::jsonb, "
                "finished_at=NOW() WHERE id = $1",
                UUID(existing_action_id), json.dumps(result),
            )
            action_id = str(existing_action_id)

    return {
        "action_id": action_id,
        "jurisdiction_ids": jurisdiction_ids,
        "snap_targets": snap_targets,
        **result,
    }
