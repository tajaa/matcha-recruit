"""Handbook Pilot routes (`/handbook-pilot/*`, Pro + Matcha-X).

Grounded conversational handbook/policy generation: a business admin opens a
session, converses with an AI grounded in the company's handbook profile +
applicable jurisdiction requirements + existing handbooks/policies + the
industry playbook (service: `services/handbook_pilot.py`), and the model
proposes citation-validated candidate handbook sections and policies. Each
proposal persists as a reviewable `draft` row the admin edits and PROMOTES into
the real handbooks / policies tables (drafts to edit/publish normally).

Every endpoint is `require_admin_or_client`-gated and tenant-scoped by
`company_id`; the router is mounted behind `require_feature("handbook_pilot")`.
Every session mutation, chat turn, draft edit, and promotion is audit-logged.
"""

import asyncio
import json
import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from app.core.services.redis_cache import check_rate_limit, client_ip
from ..services import handbook_pilot as hp

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class SessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    goal: Optional[str] = Field(None, max_length=4_000)
    industry: Optional[str] = Field(None, max_length=60)


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    goal: Optional[str] = Field(None, max_length=4_000)
    industry: Optional[str] = Field(None, max_length=60)
    status: Optional[Literal["active", "closed"]] = None


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=5_000)


class DraftUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    content: Optional[str] = Field(None, max_length=20_000)
    section_key: Optional[str] = Field(None, max_length=120)


class PromoteIn(BaseModel):
    draft_ids: list[UUID] = Field(..., min_length=1)
    handbook_title: Optional[str] = Field(None, max_length=300)


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


async def _audit(conn, session_id, current_user, request: Request, action: str,
                 details: dict | None = None):
    await conn.execute(
        """INSERT INTO handbook_pilot_audit_log (session_id, user_id, action, details, ip_address)
           VALUES ($1, $2, $3, $4, $5)""",
        session_id, getattr(current_user, "id", None), action,
        json.dumps(details or {}), client_ip(request),
    )


async def _load_session(conn, session_id, company_id) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM handbook_pilot_sessions WHERE id = $1 AND company_id = $2",
        session_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    out = dict(row)
    out["scopes"] = _parse_jsonb(out.get("scopes"))
    return out


async def _load_messages(conn, session_id) -> list[dict]:
    rows = await conn.fetch(
        "SELECT role, content, metadata, created_at FROM handbook_pilot_messages "
        "WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    return [{**dict(r), "metadata": _parse_jsonb(r["metadata"])} for r in rows]


async def _load_drafts(conn, session_id) -> list[dict]:
    rows = await conn.fetch(
        """SELECT id, kind, title, section_key, content, jurisdiction_scope,
                  citations, status, promoted_ref, created_at, updated_at
           FROM handbook_pilot_drafts WHERE session_id = $1 ORDER BY created_at""",
        session_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["jurisdiction_scope"] = _parse_jsonb(d.get("jurisdiction_scope"))
        d["citations"] = _parse_jsonb(d.get("citations"))
        d["promoted_ref"] = _parse_jsonb(d.get("promoted_ref"))
        out.append(d)
    return out


async def _load_draft(conn, draft_id, company_id) -> dict:
    row = await conn.fetchrow(
        "SELECT * FROM handbook_pilot_drafts WHERE id = $1 AND company_id = $2",
        draft_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    return dict(row)


async def _assert_paid(conn, company_id) -> None:
    """Block the token-burning / write endpoints for a self-serve Matcha-X
    company that hasn't paid yet. handbook_pilot is granted to Matcha-X via the
    tier overlay *before* checkout, and the Stripe webhook flips `incidents` on
    payment (the X paid gate) — so an abandoned-checkout X company can reach the
    page (FeatureGate passes) but must not run Gemini generation or promote until
    paid. Pro/bespoke (contract-billed) has no such gate."""
    from app.core.feature_flags import merge_company_features

    row = await conn.fetchrow(
        "SELECT signup_source, enabled_features FROM companies WHERE id = $1", company_id
    )
    if not row:
        return
    if row["signup_source"] == "matcha_x":
        features = merge_company_features(row["enabled_features"], row["signup_source"])
        if not features.get("incidents"):
            raise HTTPException(
                status_code=402,
                detail="Subscribe to Matcha-X to use Handbook Pilot drafting.",
            )


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions")
async def create_session(body: SessionCreate, request: Request,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")
    async with get_connection() as conn:
        # Seed scopes from the employee roster so the very first turn already
        # grounds on the applicable jurisdiction requirements.
        try:
            from app.core.services.handbook_service import derive_handbook_scopes_from_employees
            scopes = await derive_handbook_scopes_from_employees(conn, str(company_id))
        except Exception:  # noqa: BLE001
            logger.warning("handbook_pilot: scope seed failed for %s", company_id)
            scopes = []
        industry = body.industry
        if not industry:
            industry = await conn.fetchval("SELECT industry FROM companies WHERE id = $1", company_id)
        if industry:
            # companies.industry is VARCHAR(100) (unvalidated free text); the
            # session column is VARCHAR(60) — truncate so the fallback can't 500.
            industry = industry[:60]
        row = await conn.fetchrow(
            """INSERT INTO handbook_pilot_sessions
                   (company_id, title, goal, industry, scopes, created_by)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            company_id, body.title, body.goal, industry,
            json.dumps([{**s, "location_id": str(s["location_id"]) if s.get("location_id") else None}
                        for s in scopes]),
            getattr(current_user, "id", None),
        )
        await _audit(conn, row["id"], current_user, request, "create", {"title": body.title})
    out = dict(row)
    out["scopes"] = _parse_jsonb(out.get("scopes"))
    return out


@router.get("/pilot/sessions")
async def list_sessions(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.title, s.goal, s.industry, s.status, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM handbook_pilot_messages m WHERE m.session_id = s.id) AS message_count,
                   (SELECT COUNT(*) FROM handbook_pilot_drafts d WHERE d.session_id = s.id) AS draft_count,
                   (SELECT COUNT(*) FROM handbook_pilot_drafts d
                      WHERE d.session_id = s.id AND d.status = 'promoted') AS promoted_count
            FROM handbook_pilot_sessions s
            WHERE s.company_id = $1
            ORDER BY s.updated_at DESC
            """,
            company_id,
        )
    return [dict(r) for r in rows]


@router.get("/pilot/sessions/{session_id}")
async def get_session(session_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        session = await _load_session(conn, session_id, company_id)
        session["messages"] = await _load_messages(conn, session_id)
        session["drafts"] = await _load_drafts(conn, session_id)
    return session


@router.patch("/pilot/sessions/{session_id}")
async def update_session(session_id: UUID, body: SessionUpdate, request: Request,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    async with get_connection() as conn:
        await _load_session(conn, session_id, company_id)
        sets, vals = [], []
        for i, (k, v) in enumerate(fields.items(), start=1):
            sets.append(f"{k} = ${i}")
            vals.append(v)
        vals.extend([session_id, company_id])
        if fields.get("status") == "closed":
            closed = ", closed_at = NOW()"
        elif fields.get("status") == "active":
            closed = ", closed_at = NULL"   # reopening clears the stale timestamp
        else:
            closed = ""
        row = await conn.fetchrow(
            f"UPDATE handbook_pilot_sessions SET {', '.join(sets)}, updated_at = NOW(){closed} "
            f"WHERE id = ${len(vals) - 1} AND company_id = ${len(vals)} RETURNING *",
            *vals,
        )
        await _audit(conn, session_id, current_user, request, "update", {"fields": list(fields.keys())})
    out = dict(row)
    out["scopes"] = _parse_jsonb(out.get("scopes"))
    return out


# --------------------------------------------------------------------------- #
# Context preview + grounded chat
# --------------------------------------------------------------------------- #

@router.get("/pilot/sessions/{session_id}/context")
async def get_context(session_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        session = await _load_session(conn, session_id, company_id)
        grounding = await hp.gather_grounding(conn, company_id, session)
    corpus = hp.build_corpus(grounding)
    return {
        "sources": {k: {"label": s["label"], "count": len(s["records"])}
                    for k, s in corpus["sources"].items()},
        "notes": corpus["notes"],
        "scopes": grounding.get("scopes") or [],
        "total": sum(len(s["records"]) for s in corpus["sources"].values()),
    }


@router.post("/pilot/sessions/{session_id}/chat")
async def chat(session_id: UUID, body: ChatIn, request: Request,
               current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    # Pre-work in one connection; release it before the long Gemini call.
    async with get_connection() as conn:
        session = await _load_session(conn, session_id, company_id)
        await _assert_paid(conn, company_id)
        await check_rate_limit(str(company_id), "handbook_pilot_chat", 40, 3600)
        history = await _load_messages(conn, session_id)
        grounding = await hp.gather_grounding(conn, company_id, session)
        await conn.execute(
            "INSERT INTO handbook_pilot_messages (session_id, role, content) VALUES ($1, 'user', $2)",
            session_id, body.message,
        )
        await _audit(conn, session_id, current_user, request, "message", {"role": "user"})

    corpus = hp.build_corpus(grounding)
    user_id = getattr(current_user, "id", None)

    async def _persist(result_payload: dict):
        """Persist the assistant turn + proposed drafts. Wrapped in
        asyncio.shield by the caller so a client disconnect right after the
        result is produced doesn't drop the (already-generated) turn."""
        drafts = result_payload.get("proposed_drafts") or []
        async with get_connection() as c2:
            async with c2.transaction():
                draft_ids = []
                for d in drafts:
                    new_id = await c2.fetchval(
                        """INSERT INTO handbook_pilot_drafts
                               (session_id, company_id, kind, title, section_key,
                                content, citations, created_by)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
                        session_id, company_id, d["kind"], d["title"],
                        d.get("section_key"), d["content"],
                        json.dumps(d.get("cited_ids") or []), user_id,
                    )
                    draft_ids.append(str(new_id))
                await c2.execute(
                    "INSERT INTO handbook_pilot_messages (session_id, role, content, metadata) "
                    "VALUES ($1, 'assistant', $2, $3)",
                    session_id, result_payload.get("assistant_text", ""),
                    json.dumps({
                        "open_questions": result_payload.get("open_questions"),
                        "dropped_citations": result_payload.get("dropped_citations"),
                        "draft_ids": draft_ids,
                    }),
                )
                await c2.execute(
                    "UPDATE handbook_pilot_sessions SET updated_at = NOW() WHERE id = $1",
                    session_id,
                )

    async def event_stream():
        result_payload = None
        try:
            async for ev in hp.run_chat_turn(session, history, corpus, body.message):
                if ev.get("type") == "result":
                    result_payload = ev.get("data")
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception:
            logger.exception("handbook_pilot: chat stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Drafting failed.'})}\n\n"
        # Persist after streaming. shield() so a disconnect at this point still
        # commits the completed turn (the Gemini tokens were already spent).
        if result_payload:
            try:
                await asyncio.shield(_persist(result_payload))
            except Exception:
                logger.exception("handbook_pilot: failed to persist assistant turn")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


# --------------------------------------------------------------------------- #
# Drafts
# --------------------------------------------------------------------------- #

@router.patch("/pilot/drafts/{draft_id}")
async def update_draft(draft_id: UUID, body: DraftUpdate, request: Request,
                       current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    async with get_connection() as conn:
        draft = await _load_draft(conn, draft_id, company_id)
        if draft["status"] == "promoted":
            raise HTTPException(status_code=400, detail="Promoted drafts can't be edited")
        sets, vals = [], []
        for i, (k, v) in enumerate(fields.items(), start=1):
            sets.append(f"{k} = ${i}")
            vals.append(v)
        vals.extend([draft_id, company_id])
        row = await conn.fetchrow(
            f"UPDATE handbook_pilot_drafts SET {', '.join(sets)}, updated_at = NOW() "
            f"WHERE id = ${len(vals) - 1} AND company_id = ${len(vals)} RETURNING *",
            *vals,
        )
        await _audit(conn, draft["session_id"], current_user, request, "edit_draft",
                     {"draft_id": str(draft_id), "fields": list(fields.keys())})
    out = dict(row)
    out["citations"] = _parse_jsonb(out.get("citations"))
    out["jurisdiction_scope"] = _parse_jsonb(out.get("jurisdiction_scope"))
    out["promoted_ref"] = _parse_jsonb(out.get("promoted_ref"))
    return out


@router.delete("/pilot/drafts/{draft_id}")
async def delete_draft(draft_id: UUID, request: Request,
                       current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        draft = await _load_draft(conn, draft_id, company_id)
        await conn.execute("DELETE FROM handbook_pilot_drafts WHERE id = $1 AND company_id = $2",
                           draft_id, company_id)
        await _audit(conn, draft["session_id"], current_user, request, "delete_draft",
                     {"draft_id": str(draft_id)})
    return {"deleted": True}


# --------------------------------------------------------------------------- #
# Promotion — push reviewed drafts into the real handbooks / policies tables.
# --------------------------------------------------------------------------- #

@router.post("/pilot/sessions/{session_id}/promote")
async def promote(session_id: UUID, body: PromoteIn, request: Request,
                  current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    user_id = getattr(current_user, "id", None)

    # Pre-work: gate, load the requested pending drafts, and re-derive the
    # current work locations (not the possibly-stale session snapshot) so a
    # promoted handbook is scoped to the company's live jurisdictions.
    async with get_connection() as conn:
        session = await _load_session(conn, session_id, company_id)
        await _assert_paid(conn, company_id)
        try:
            from app.core.services.handbook_service import derive_handbook_scopes_from_employees
            scopes = await derive_handbook_scopes_from_employees(conn, str(company_id))
        except Exception:  # noqa: BLE001
            logger.warning("handbook_pilot: scope derivation failed for promote %s", company_id)
            scopes = session.get("scopes") or []
        rows = await conn.fetch(
            """SELECT * FROM handbook_pilot_drafts
               WHERE session_id = $1 AND company_id = $2 AND id = ANY($3::uuid[])
                 AND status = 'pending'""",
            session_id, company_id, list(body.draft_ids),
        )
    drafts = [dict(r) for r in rows]
    if not drafts:
        raise HTTPException(status_code=400, detail="No promotable drafts found")

    section_drafts = [d for d in drafts if d["kind"] == "handbook_section"]
    policy_drafts = [d for d in drafts if d["kind"] == "policy"]

    promoted: dict[str, dict] = {}      # draft_id -> promoted_ref
    handbook_result: dict | None = None
    policy_results: list[dict] = []
    failed: list[dict] = []             # {draft_id, title, error}

    # Handbook sections → one new draft handbook (the section group is atomic:
    # create_handbook_from_sections runs in a single transaction).
    if section_drafts:
        from app.core.services.handbook_service import HandbookService
        sections = [{
            "section_key": d.get("section_key"),
            "title": d["title"],
            "content": d["content"],
            "section_type": "custom",
        } for d in section_drafts]
        title = (body.handbook_title or session.get("title") or "Handbook Pilot draft")[:300]
        try:
            handbook = await HandbookService.create_handbook_from_sections(
                str(company_id), title, scopes, sections, str(user_id) if user_id else None,
            )
            hb_id = str(handbook.id)
            handbook_result = {"id": hb_id, "title": title}
            for d in section_drafts:
                promoted[str(d["id"])] = {"kind": "handbook", "handbook_id": hb_id}
        except Exception as exc:  # noqa: BLE001 - surface as a per-draft failure, not a 500
            logger.exception("handbook_pilot: handbook promotion failed")
            for d in section_drafts:
                failed.append({"draft_id": str(d["id"]), "title": d["title"], "error": str(exc)})

    # Policies → one draft policy each (independent; a failure doesn't block the rest).
    if policy_drafts:
        from app.core.services.policy_service import PolicyService
        from app.core.models.policy import PolicyCreate
        for d in policy_drafts:
            try:
                policy = await PolicyService.create_policy(
                    str(company_id),
                    PolicyCreate(title=d["title"], content=d["content"], status="draft",
                                 source_type="manual"),
                    str(user_id) if user_id else None,
                )
                pid = str(policy.id)
                policy_results.append({"id": pid, "title": d["title"]})
                promoted[str(d["id"])] = {"kind": "policy", "policy_id": pid}
            except Exception as exc:  # noqa: BLE001
                logger.exception("handbook_pilot: policy promotion failed for draft %s", d["id"])
                failed.append({"draft_id": str(d["id"]), "title": d["title"], "error": str(exc)})

    # Mark whatever succeeded as promoted (each ref points at the real record so
    # a re-promote of the rest never re-creates the succeeded ones) + audit.
    async with get_connection() as conn:
        for draft_id, ref in promoted.items():
            await conn.execute(
                "UPDATE handbook_pilot_drafts SET status = 'promoted', promoted_ref = $2::jsonb, "
                "updated_at = NOW() WHERE id = $1",
                UUID(draft_id), json.dumps(ref),
            )
        await conn.execute("UPDATE handbook_pilot_sessions SET updated_at = NOW() WHERE id = $1", session_id)
        await _audit(conn, session_id, current_user, request, "promote",
                     {"promoted": list(promoted.keys()),
                      "failed": [f["draft_id"] for f in failed]})
    return {
        "promoted": len(promoted),
        "handbook": handbook_result,
        "policies": policy_results,
        "failed": failed,
    }
