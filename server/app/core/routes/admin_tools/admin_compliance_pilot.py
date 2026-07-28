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

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.services import compliance_pilot as cp
from app.core.services.compliance_pilot import agent as agent_mod
from app.core.services.compliance_pilot.approve import _embed_bg, _snapshot_bg
from app.core.services.compliance_pilot.confirm import ActionConflict, cancel_proposed, confirm_and_launch
from app.core.services.rate_limiter import RateLimitExceeded
from app.core.services.redis_cache import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Reclaim horizon + concurrency ceiling now live in compliance_pilot.core
# (cp.STALE_RECLAIM_HOURS / cp.MAX_CONCURRENT_RESEARCH) — shared with the
# agentic loop's confirm.py so the two paths can't drift apart. The detached-
# task strong-ref registry lives there too (cp.launch_action_task).


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
        session["actions"] = await cp.load_actions(conn, session_id)
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

async def _stream_agent_turn(session_id: str, actor_id, history: list[dict]):
    """Agent-mode chat stream: pass `agent.run_pilot_turn`'s frames straight
    through, then persist the assistant summary. `citation_records` (not
    `citations` — the legacy single-shot mode already owns that key for a
    DIFFERENT shape, `{point, cited_ids}`; reusing it here would have the
    frontend render agent-mode's flat `{cid, summary, ...}` records as if they
    were that shape) carries the resolved citation records, and
    `proposal_action_ids` the ids any stage_* tool call inserted this turn.

    The persist runs under `asyncio.shield` — a client that aborts the SSE
    connection cancels this generator, but by the time we're here the turn's
    tool calls have already written real `compliance_pilot_actions` rows; losing
    the assistant message that explains them would leave the session's history
    silently out of sync with what's actually staged.
    """
    result_data = None
    try:
        async for ev in agent_mod.run_pilot_turn(session_id=session_id, actor_id=actor_id, history=history):
            if ev.get("type") == "agent_result":
                result_data = ev.get("data") or {}
            yield f"data: {json.dumps(ev)}\n\n"
    except RateLimitExceeded:
        logger.warning("compliance_pilot: agent turn rate-limited for session %s", session_id)
        yield f"data: {json.dumps({'type': 'error', 'message': 'Gemini rate limit reached — please try again shortly.'})}\n\n"
    except Exception:
        logger.exception("compliance_pilot: agent stream error")
        yield f"data: {json.dumps({'type': 'error', 'message': 'The Pilot hit a problem.'})}\n\n"

    if result_data:
        async def _persist():
            async with get_connection() as c2:
                await c2.execute(
                    "INSERT INTO compliance_pilot_messages (session_id, role, content, metadata) "
                    "VALUES ($1, 'assistant', $2, $3)",
                    session_id, result_data.get("message", ""),
                    json.dumps({
                        "steps": result_data.get("steps"),
                        "citation_records": result_data.get("citations"),
                        "proposal_action_ids": result_data.get("proposal_action_ids"),
                    }),
                )
                await c2.execute(
                    "UPDATE compliance_pilot_sessions SET updated_at = NOW() WHERE id = $1",
                    session_id,
                )
        try:
            await asyncio.shield(_persist())
        except Exception:
            logger.exception("compliance_pilot: failed to persist agent assistant message")
    yield "data: [DONE]\n\n"


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatIn, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        session = await _load_session(conn, session_id)
        await check_rate_limit(str(getattr(current_user, "id", "admin")), "compliance_pilot_chat", 40, 3600)
        mode = session.get("mode") or "research"
        history = await _load_messages(conn, session_id)

        if mode == "agent":
            await conn.execute(
                "INSERT INTO compliance_pilot_messages (session_id, role, content) VALUES ($1, 'user', $2)",
                session_id, body.message,
            )
            actor_id = getattr(current_user, "id", None)
            # run_pilot_turn expects the full turn history INCLUDING the latest
            # user message as its last entry (same convention as Huume) — no
            # second round trip needed, the row we just inserted is this dict.
            agent_history = history + [{"role": "user", "content": body.message}]
            return StreamingResponse(
                _stream_agent_turn(session_id, actor_id, agent_history),
                media_type="text/event-stream", headers={"X-Accel-Buffering": "no"},
            )

        actions = await cp.load_actions(conn, session_id)
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
    from app.core.services.compliance_service import _resolve_industry

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
            f"  AND started_at < NOW() - interval '{cp.STALE_RECLAIM_HOURS} hours'",
            session_id,
        )
        if body.kind == "research":
            running = await conn.fetchval(
                "SELECT COUNT(*) FROM compliance_pilot_actions WHERE kind='research' AND status='running'"
            ) or 0
            if running >= cp.MAX_CONCURRENT_RESEARCH:
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
    # Detached runner — owns its own connections; never the request's.
    # launch_action_task holds the strong ref (see its docstring for why).
    cp.launch_action_task(action_id, actor_id)
    return {"action_id": str(action_id)}


@router.get("/actions/{action_id}")
async def get_action(action_id: str, current_user=Depends(require_admin)):
    async with get_connection() as conn:
        row = await cp.load_action(conn, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")
    return row


@router.post("/actions/{action_id}/confirm")
async def confirm_action_route(action_id: str, current_user=Depends(require_admin)):
    """Execute a proposed action — the REST twin of the agentic loop's
    `confirm_action` tool. Both funnel through `confirm.confirm_and_launch`, so
    a chat-driven confirm and a button-driven confirm for the same action can't
    diverge. No two-turn check here: a REST call is definitionally a separate
    request from whatever staged the action, so the structural same-turn risk
    `actions.evaluate_confirm` guards against in the loop doesn't apply — the
    CAS `WHERE status='proposed'` in `confirm_and_launch` is the whole gate.
    """
    actor_id = getattr(current_user, "id", None)
    try:
        return await confirm_and_launch(action_id, actor_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Action not found")
    except ActionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/actions/{action_id}/cancel")
async def cancel_action_route(action_id: str, current_user=Depends(require_admin)):
    """Void a proposed action — the REST twin of the agentic loop's
    `cancel_action` tool, same executor (`confirm.cancel_proposed`)."""
    try:
        return await cancel_proposed(action_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Action not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, body: ApproveBody, background_tasks: BackgroundTasks,
                         current_user=Depends(require_admin)):
    """Commit SELECTED staged policies: activate them, then make each AUTHORITATIVE
    via codify_from_requirement — but only when it passes the deterministic
    provenance gate (regulation_key + a statute citation from research + a live
    PRIMARY .gov source). Gate failures stay live-but-uncodified with the reason.

    The work lives in `compliance_pilot.approve.approve_from_action` — shared
    with the agentic loop's `stage_approve` -> `confirm_action` path so there is
    exactly one commit implementation.
    """
    from app.core.services.compliance_pilot.approve import approve_from_action

    actor_id = getattr(current_user, "id", None)
    try:
        out = await approve_from_action(action_id, body.ids or [], actor_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Action not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if out["jurisdiction_ids"]:
        background_tasks.add_task(_embed_bg, out["jurisdiction_ids"])
    if out["snap_targets"]:
        background_tasks.add_task(_snapshot_bg, out["snap_targets"])

    return {k: v for k, v in out.items() if k not in ("jurisdiction_ids", "snap_targets")}
