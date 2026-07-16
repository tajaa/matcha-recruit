"""Compliance Pilot routes (`/admin/pilot/*`, admin-only).

Chat-driven compliance-library building for the admin Compliance Studio. A session
runs in a mode (research / ask / check_sources / scope); a chat turn may emit an
action PROPOSAL which the admin confirms into a background RUN (research staging /
source-link check), and a staged research run is committed via `approve` (the same
`research_review.approve_staged` core the admin queue uses).

Actions run as detached background tasks that own their own connections
(`compliance_pilot.run_action`), so a browser tab close mid-run can't orphan a
research pass on a request-scoped connection. The frontend polls `GET /actions/{id}`.
"""
import asyncio
import json
import logging
from typing import List, Literal, Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import get_connection
from ..dependencies import require_admin
from ..services import compliance_pilot as cp
from ..services.change_context import set_change_context
from ..services.redis_cache import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Strong refs to detached runner tasks — without this the event loop keeps only a
# weak ref and the GC can collect a task mid-run (documented CPython pitfall),
# leaving the action stuck 'running' and the per-session unique index 409-ing
# forever. Discarded on completion.
_BG_TASKS: set = set()

# A runner that dies (GC, deploy swap, crash) before its terminal UPDATE leaves the
# row 'running'. Reclaim rows older than this so the session isn't locked forever —
# same 2h horizon as vertical_coverage_sweep.
_STALE_RECLAIM_HOURS = 2
# Global ceiling on concurrent research runs — each pins a pooled connection for the
# full multi-minute Gemini pass (pool max_size=10), and the running-guard is only
# per-session. (Celery is the real fix — fast-follow.)
_MAX_CONCURRENT_RESEARCH = 2


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class SessionCreate(BaseModel):
    mode: str = Field("research", max_length=40)
    title: Optional[str] = Field(None, min_length=1, max_length=300)


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    status: Optional[Literal["active", "closed"]] = None


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=5_000)


class ActionCreate(BaseModel):
    kind: Literal["research", "check_sources"]
    state: str = Field(..., min_length=2, max_length=2)
    city: Optional[str] = Field(None, max_length=120)
    industry_tag: Optional[str] = Field(None, max_length=80)
    categories: Optional[List[str]] = None


class ApproveBody(BaseModel):
    # Specific staged requirement ids to commit; omit/empty = all staged.
    ids: Optional[List[str]] = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _parse_jsonb(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


async def _load_session(conn, session_id: str) -> dict:
    row = await conn.fetchrow("SELECT * FROM compliance_pilot_sessions WHERE id = $1", session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return dict(row)


async def _load_messages(conn, session_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT role, content, metadata, created_at FROM compliance_pilot_messages "
        "WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    return [{**dict(r), "metadata": _parse_jsonb(r["metadata"])} for r in rows]


def _action_out(row) -> dict:
    d = dict(row)
    for k in ("params", "progress", "result"):
        if k in d:
            d[k] = _parse_jsonb(d[k])
    d["staged_ids"] = [str(x) for x in (d.get("staged_ids") or [])]
    return d


async def _load_actions(conn, session_id: str) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, kind, params, status, progress, result, staged_ids, started_at, finished_at "
        "FROM compliance_pilot_actions WHERE session_id = $1 ORDER BY started_at",
        session_id,
    )
    return [_action_out(r) for r in rows]


def _latest_coordinate(history: list[dict], actions: list[dict]) -> Optional[dict]:
    """The session's current (state, city, industry_tag) — the latest resolved
    proposal in an assistant turn, else the latest action's params. None on turn 1."""
    for m in reversed(history):
        prop = (m.get("metadata") or {}).get("proposal")
        if isinstance(prop, dict) and prop.get("state"):
            return {"state": prop["state"], "city": prop.get("city"),
                    "industry_tag": prop.get("industry_tag")}
    for a in reversed(actions):
        p = a.get("params") or {}
        if isinstance(p, dict) and p.get("state"):
            return {"state": p["state"], "city": p.get("city"),
                    "industry_tag": p.get("industry_tag")}
    return None


# --------------------------------------------------------------------------- #
# Templates + sessions
# --------------------------------------------------------------------------- #

@router.get("/templates")
async def list_templates(current_user=Depends(require_admin)):
    return cp.template_catalog()


@router.post("/sessions")
async def create_session(body: SessionCreate, current_user=Depends(require_admin)):
    tmpl = cp.get_template(body.mode)
    if tmpl is None:
        raise HTTPException(status_code=400, detail="Unknown mode")
    title = (body.title or "").strip() or tmpl["title"]
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "INSERT INTO compliance_pilot_sessions (admin_id, title, mode) "
            "VALUES ($1, $2, $3) RETURNING *",
            getattr(current_user, "id", None), title[:300], body.mode,
        )
    return {**dict(row), "template": tmpl}


@router.get("/sessions")
async def list_sessions(current_user=Depends(require_admin)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT s.*, "
            "(SELECT COUNT(*) FROM compliance_pilot_messages m WHERE m.session_id = s.id) AS message_count "
            "FROM compliance_pilot_sessions s ORDER BY s.updated_at DESC LIMIT 200"
        )
    return [{**dict(r), "template": cp.get_template(r["mode"])} for r in rows]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        session = await _load_session(conn, session_id)
        session["template"] = cp.get_template(session.get("mode"))
        session["messages"] = await _load_messages(conn, session_id)
        session["actions"] = await _load_actions(conn, session_id)
    return session


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: SessionUpdate, current_user=Depends(require_admin)):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets, vals = [], []
    for i, (k, v) in enumerate(fields.items(), start=1):
        sets.append(f"{k} = ${i}")
        vals.append(v)
    vals.append(session_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE compliance_pilot_sessions SET {', '.join(sets)}, updated_at = NOW() "
            f"WHERE id = ${len(vals)} RETURNING *",
            *vals,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
    return {**dict(row), "template": cp.get_template(row.get("mode"))}


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #

@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatIn, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        session = await _load_session(conn, session_id)
        await check_rate_limit(str(getattr(current_user, "id", "admin")), "compliance_pilot_chat", 40, 3600)
        mode = session.get("mode") or "research"
        history = await _load_messages(conn, session_id)
        actions = await _load_actions(conn, session_id)
        corpus = {"records": [], "index": {}}
        snapshot = None
        if mode == "ask":
            corpus = await cp.build_ask_corpus(conn, body.message)
        else:
            # Ground research/scope/check_sources on the session's current coordinate
            # (latest resolved proposal, else latest action params) so scope mode can
            # narrate real coverage. First turn (no coordinate yet) has no snapshot —
            # the focus text tells the model to name an industry + place.
            coord = _latest_coordinate(history, actions)
            if coord:
                snapshot = await cp.build_scope_snapshot(
                    conn, coord["state"], coord.get("city"), coord.get("industry_tag"))
        # Persist the user turn before streaming (a refused turn leaves no orphan —
        # there is no gate here, so this is unconditional).
        await conn.execute(
            "INSERT INTO compliance_pilot_messages (session_id, role, content) VALUES ($1, 'user', $2)",
            session_id, body.message,
        )

    async def event_stream():
        result_payload = None
        try:
            async for ev in cp.run_chat_turn(mode, corpus, snapshot, history, body.message):
                if ev.get("type") == "result":
                    data = ev.get("data") or {}
                    # Resolve any proposal against the DB (read-only) before it
                    # reaches the client — attach the concrete coordinate + coverage
                    # preview, or demote to proposal_errors.
                    prop = data.get("proposal")
                    if prop:
                        try:
                            async with get_connection() as c:
                                resolved, errors = await cp.resolve_proposal(c, prop)
                            data["proposal"] = resolved
                            data["proposal_errors"] = errors
                        except Exception:
                            logger.exception("compliance_pilot: proposal resolve failed")
                            data["proposal"] = None
                            data["proposal_errors"] = ["Could not validate the proposal."]
                    result_payload = data
                    ev["data"] = data
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception:
            logger.exception("compliance_pilot: chat stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis failed.'})}\n\n"

        if result_payload:
            try:
                async with get_connection() as c2:
                    await c2.execute(
                        "INSERT INTO compliance_pilot_messages (session_id, role, content, metadata) "
                        "VALUES ($1, 'assistant', $2, $3)",
                        session_id, result_payload.get("assistant_text", ""),
                        json.dumps({
                            "citations": result_payload.get("citations"),
                            "proposal": result_payload.get("proposal"),
                            "proposal_errors": result_payload.get("proposal_errors"),
                            "dropped_citations": result_payload.get("dropped_citations"),
                        }),
                    )
                    await c2.execute(
                        "UPDATE compliance_pilot_sessions SET updated_at = NOW() WHERE id = $1",
                        session_id,
                    )
            except Exception:
                logger.exception("compliance_pilot: failed to persist assistant message")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


# --------------------------------------------------------------------------- #
# Actions — run + poll + approve
# --------------------------------------------------------------------------- #

@router.post("/sessions/{session_id}/actions")
async def create_action(session_id: str, body: ActionCreate, current_user=Depends(require_admin)):
    from ..services.compliance_service import _resolve_industry

    state = body.state.upper()
    if len(state) != 2 or not state.isalpha():
        raise HTTPException(status_code=400, detail="state must be a 2-letter code")

    params = {"kind": body.kind, "state": state, "city": (body.city or "").strip() or None}
    if body.kind == "research":
        # Canonicalize the industry tag — a non-canonical tag would force-tag shared
        # catalog rows with an applicable_industries value no tenant matches (the
        # blanket-tag poisoning invariant). Reject rather than research under it.
        industry_tag = _resolve_industry(body.industry_tag)
        if not industry_tag:
            raise HTTPException(status_code=400,
                                detail=f"Couldn't resolve the industry '{body.industry_tag}'")
        async with get_connection() as conn:
            cats = body.categories
            if cats:
                valid = {r["slug"] for r in await conn.fetch(
                    "SELECT slug FROM compliance_categories WHERE slug = ANY($1::text[])", cats)}
                cats = [c for c in cats if c in valid]
            else:
                cats = await cp.default_categories(conn, industry_tag)
        if not cats:
            raise HTTPException(status_code=400, detail="No valid categories resolved")
        params["industry_tag"] = industry_tag
        params["categories"] = cats

    actor_id = getattr(current_user, "id", None)
    async with get_connection() as conn:
        # Reclaim stale runners (dead task / deploy swap) so a lost run can't lock
        # the session's unique index forever.
        await conn.execute(
            "UPDATE compliance_pilot_actions "
            "SET status='failed', finished_at=NOW(), "
            "    result='{\"error\":\"reclaimed: runner lost\"}'::jsonb "
            "WHERE session_id=$1 AND status='running' "
            f"  AND started_at < NOW() - interval '{_STALE_RECLAIM_HOURS} hours'",
            session_id,
        )
        if body.kind == "research":
            running = await conn.fetchval(
                "SELECT COUNT(*) FROM compliance_pilot_actions WHERE kind='research' AND status='running'"
            ) or 0
            if running >= _MAX_CONCURRENT_RESEARCH:
                raise HTTPException(status_code=409,
                                    detail="Too many research runs in flight — try again shortly")
        try:
            row = await conn.fetchrow(
                "INSERT INTO compliance_pilot_actions (session_id, kind, params, actor_id) "
                "VALUES ($1, $2, $3::jsonb, $4) RETURNING id",
                session_id, body.kind, json.dumps(params), actor_id,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="An action is already running for this session")
        except asyncpg.ForeignKeyViolationError:
            raise HTTPException(status_code=404, detail="Session not found")
    action_id = row["id"]
    # Detached runner — owns its own connections; never the request's. Hold a strong
    # ref so the GC can't collect it mid-run.
    task = asyncio.create_task(cp.run_action(action_id, actor_id))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return {"action_id": str(action_id)}


@router.get("/actions/{action_id}")
async def get_action(action_id: str, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, session_id, kind, params, status, progress, result, staged_ids, "
            "started_at, finished_at FROM compliance_pilot_actions WHERE id = $1",
            action_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    return _action_out(row)


async def _embed_bg(jurisdiction_ids: list):
    from ..services.compliance_embedding_pipeline import embed_updated_requirements
    try:
        async with get_connection() as conn:
            for jid in jurisdiction_ids:
                await embed_updated_requirements(conn, jid)
    except Exception:
        logger.exception("compliance_pilot: post-approve embed failed")


async def _snapshot_bg(snap_targets: list):
    """Freeze each newly-committed row's cited page — pilot_commit is a tenant-
    visibility moment, same as the admin approve (which snapshots too)."""
    import httpx
    from ..services.source_snapshot import snapshot_source
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for req_id, url in snap_targets:
                async with get_connection() as conn:
                    await snapshot_source(conn, req_id, url, "approve", client=client)
    except Exception:
        logger.exception("compliance_pilot: post-approve snapshot failed")


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, body: ApproveBody, background_tasks: BackgroundTasks,
                         current_user=Depends(require_admin)):
    """Commit SELECTED staged policies: activate them, then make each AUTHORITATIVE
    via codify_from_requirement — but only when it passes the deterministic
    provenance gate (regulation_key + a statute citation from research + a live
    PRIMARY .gov source). Gate failures stay live-but-uncodified with the reason.
    """
    from ..services.research_review import approve_staged
    from ..services.scope_registry.codify import codify_from_requirement
    from ..services.compliance_pilot import _codify_gate

    actor_id = getattr(current_user, "id", None)
    async with get_connection() as conn:
        act = await conn.fetchrow(
            "SELECT session_id, kind, staged_ids, status FROM compliance_pilot_actions WHERE id = $1",
            action_id,
        )
        if not act:
            raise HTTPException(status_code=404, detail="Action not found")
        if act["kind"] != "research":
            raise HTTPException(status_code=400, detail="Only research actions can be codified")
        staged = [str(s) for s in (act["staged_ids"] or [])]
        if body.ids:
            want = set(body.ids)
            staged = [s for s in staged if s in want]
        if not staged:
            raise HTTPException(status_code=400, detail="Nothing selected to commit")
        # Still-pending rows among the selection (concurrent Pipeline approval is benign)
        # + the fields the codify gate needs.
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

    # 1. Activate (shared core; also reconciles keys that already had a confirmed
    #    classification). Rows are now 'active' — codify_from_requirement's guard.
    core = await approve_staged(pending_ids, actor_id, source="pilot_commit")

    # 2. Per-row: gate → codify_from_requirement (mints the confirmed classification
    #    for the admin-confirmed citation, then reconcile stamps citation_verified_at).
    outcomes = []
    snap_targets = []
    async with get_connection() as conn:
        await set_change_context(conn, "pilot_commit", actor_id)
        for r in rows:
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
            codified, statute_citation, citation_url = False, None, None
            if ok:
                try:
                    res = await codify_from_requirement(
                        conn, r["id"], citation=citation, source_url=r["source_url"], admin_id=actor_id)
                    codified = bool(res.get("codified"))
                    statute_citation = res.get("statute_citation")
                    citation_url = res.get("citation_url")
                    if not codified:
                        reason = "codify ran but the citation wasn't stamped"
                except Exception as exc:  # noqa: BLE001 — row is already live; never fail approve
                    logger.warning("compliance_pilot: codify failed for %s: %s", r["id"], exc)
                    reason = f"codify error: {str(exc)[:120]}"
            if codified and (citation_url or r["source_url"]):
                snap_targets.append((r["id"], citation_url or r["source_url"]))
            outcomes.append({
                "id": str(r["id"]), "title": r["title"], "activated": True,
                "codified": codified, "statute_citation": statute_citation,
                "citation_url": citation_url, "gate_reason": None if codified else reason,
                "state": r["state"], "city": r["city"],
            })

    codified_n = sum(1 for o in outcomes if o["codified"])
    result = {
        "activated": core["activated"], "codified": codified_n,
        "uncodified": len(outcomes) - codified_n, "already_live": already_live,
        "results": outcomes,
    }
    async with get_connection() as conn:
        arow = await conn.fetchrow(
            "INSERT INTO compliance_pilot_actions "
            "(session_id, kind, params, status, result, actor_id, finished_at) "
            "VALUES ($1, 'approve', $2::jsonb, 'done', $3::jsonb, $4, NOW()) RETURNING id",
            act["session_id"], json.dumps({"from_action": action_id}),
            json.dumps(result), actor_id,
        )

    if jurisdiction_ids:
        background_tasks.add_task(_embed_bg, jurisdiction_ids)
    if snap_targets:
        background_tasks.add_task(_snapshot_bg, snap_targets)

    return {"action_id": str(arow["id"]), **result}
