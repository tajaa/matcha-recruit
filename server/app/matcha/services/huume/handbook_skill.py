"""Huume skill #3 — Handbook Pilot in chat.

Thin agent-facing wrappers over `services/pilots/handbook_pilot`, writing to
the SAME tables the `/handbook-pilot` UI uses (`handbook_pilot_sessions` /
`_messages` / `_drafts` / `_audit_log`). Each huume thread lazily owns ONE
pilot session (its id rides `current_state.huume_handbook`), so drafts
proposed in chat are reviewable/editable on the Handbook Pilot page and
drafts promoted from either surface stay consistent.

The route-level gates are re-applied here, not bypassed: the unpaid-Matcha-X
check (`hp.unpaid_x_reason`) and the same per-company rate-limit key
(`handbook_pilot_chat`, 40/hr — chat-mode drafting shares the UI's quota
rather than doubling it). `actions.evaluate_pilot_tool` owns role/feature
authz; the two-turn promote guard is `actions.filter_promotable_drafts` plus
this module's `exclude_ids` handling.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_PENDING_CAP = 20


async def _audit(conn, session_id, user_id, action: str, details: Optional[dict[str, Any]] = None) -> None:
    await conn.execute(
        """INSERT INTO handbook_pilot_audit_log (session_id, user_id, action, details, ip_address)
           VALUES ($1, $2, $3, $4, NULL)""",
        session_id, user_id, action, json.dumps(details or {}),
    )


def _parse_jsonb(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return None
    return v


async def _load_session(conn, session_id, company_id) -> Optional[dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM handbook_pilot_sessions WHERE id = $1 AND company_id = $2",
        session_id, company_id,
    )
    if not row:
        return None
    out = dict(row)
    out["scopes"] = _parse_jsonb(out.get("scopes")) or []
    return out


async def _pending_drafts(conn, session_id) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT id, kind, title FROM handbook_pilot_drafts "
        "WHERE session_id = $1 AND status = 'pending' ORDER BY created_at LIMIT $2",
        session_id, _PENDING_CAP,
    )
    return [{"draft_id": str(r["id"]), "kind": r["kind"], "title": r["title"]} for r in rows]


async def ensure_session(
    *, company_id: UUID, actor_user_id: Optional[UUID], thread_id: UUID,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Reuse the thread's pilot session if it still exists and is active, else
    create one (mirroring the route's create: scopes seeded from the roster,
    industry from the company row). Never raises — a bad stored id just means
    a fresh session."""
    from app.database import get_connection

    async with get_connection() as conn:
        if session_id:
            try:
                UUID(str(session_id))
            except ValueError:
                session_id = None
        if session_id:
            session = await _load_session(conn, str(session_id), company_id)
            if session and session.get("status") == "active":
                return session

        try:
            from app.core.services.handbook_service import derive_handbook_scopes_from_employees
            scopes = await derive_handbook_scopes_from_employees(conn, str(company_id))
        except Exception:  # noqa: BLE001
            logger.warning("huume handbook_skill: scope seed failed for %s", company_id)
            scopes = []
        industry = await conn.fetchval("SELECT industry FROM companies WHERE id = $1", company_id)
        if industry:
            # companies.industry is VARCHAR(100) free text; the session column
            # is VARCHAR(60) — truncate so the fallback can't 500.
            industry = industry[:60]
        title = f"Huume chat — {date.today().isoformat()}"
        row = await conn.fetchrow(
            """INSERT INTO handbook_pilot_sessions
                   (company_id, title, goal, industry, scopes, created_by)
               VALUES ($1, $2, NULL, $3, $4, $5) RETURNING *""",
            company_id, title, industry,
            json.dumps([{**s, "location_id": str(s["location_id"]) if s.get("location_id") else None}
                        for s in scopes]),
            actor_user_id,
        )
        await _audit(conn, row["id"], actor_user_id, "create",
                     {"title": title, "via": "huume", "thread_id": str(thread_id)})
        session = dict(row)
        session["scopes"] = _parse_jsonb(session.get("scopes")) or []
        return session


async def draft_content(
    *, company_id: UUID, actor_user_id: Optional[UUID], thread_id: UUID,
    session: dict[str, Any], request_text: str,
) -> dict[str, Any]:
    """One grounded drafting turn from chat — the same pipeline as the route's
    chat endpoint (grounding → compliance floor OUTSIDE the conn block →
    full-text corpus → citation-gated generation → persisted turn + draft
    rows), returning the proposed drafts with their new row ids."""
    from fastapi import HTTPException

    from app.core.services.redis_cache import check_rate_limit
    from app.database import get_connection
    from app.matcha.services.pilots import handbook_pilot as hp

    request_text = (request_text or "").strip()
    if not request_text:
        return {"status": "error", "message": "Say what you'd like drafted."}

    async with get_connection() as conn:
        reason = await hp.unpaid_x_reason(conn, company_id)
        if reason:
            return {"status": "refused", "message": reason}
        try:
            await check_rate_limit(str(company_id), "handbook_pilot_chat", 40, 3600)
        except HTTPException:
            return {"status": "refused",
                    "message": "Handbook drafting rate limit reached — try again in an hour."}
        history = await conn.fetch(
            "SELECT role, content, metadata, created_at FROM handbook_pilot_messages "
            "WHERE session_id = $1 ORDER BY created_at",
            session["id"],
        )
        history = [dict(r) for r in history]
        grounding = await hp.gather_grounding(conn, company_id, session)
        await conn.execute(
            "INSERT INTO handbook_pilot_messages (session_id, role, content) VALUES ($1, 'user', $2)",
            session["id"], request_text,
        )
        await _audit(conn, session["id"], actor_user_id, "message",
                     {"role": "user", "via": "huume", "thread_id": str(thread_id)})

    # Must run OUTSIDE the connection block — attach_compliance_floor acquires
    # its own pool connection and nesting two acquisitions deadlocks under load.
    grounding = await hp.attach_compliance_floor(grounding, company_id)
    corpus = hp.build_corpus(grounding, with_full_text=True)

    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    async for ev in hp.run_chat_turn(session, history, corpus, request_text):
        if ev.get("type") == "result":
            result = ev.get("data")
        elif ev.get("type") == "error":
            error_message = ev.get("message")
    if not result:
        return {"status": "error", "message": error_message or "Drafting failed — please try again."}

    draft_ids = await hp.persist_turn(session["id"], company_id, result, actor_user_id)

    proposed = result.get("proposed_drafts") or []
    index = corpus.get("index") or {}
    drafts_out = []
    for did, d in zip(draft_ids, proposed):
        cids = d.get("cited_ids") or []
        drafts_out.append({
            "draft_id": did,
            "kind": d.get("kind"),
            "title": d.get("title"),
            "cited_ids": cids,
            "grounded": any(c.startswith("law:") or c.startswith("floor:") for c in cids),
        })

    async with get_connection() as conn:
        pending = await _pending_drafts(conn, session["id"])

    cited = [c for d in proposed for c in (d.get("cited_ids") or [])]
    return {
        "status": "ok",
        "session_id": str(session["id"]),
        "assistant_text": result.get("assistant_text") or "",
        "drafts": drafts_out,
        "open_questions": result.get("open_questions") or [],
        "dropped_citations": result.get("dropped_citations") or [],
        "pending_drafts": pending,
        "citation_records": hp.resolve_citations(cited, index),
        "message": "Drafts are proposals — review/edit them on the Handbook Pilot page or promote them here.",
    }


async def promote(
    *, company_id: UUID, actor_user_id: Optional[UUID], thread_id: UUID,
    session_id: str, draft_ids: Optional[list[str]] = None,
    exclude_ids: Optional[set[str]] = None, handbook_title: Optional[str] = None,
    target_handbook_id: Optional[str] = None,
) -> dict[str, Any]:
    """Promote pending drafts into the real handbook/policy tables via the
    shared `hp.promote_drafts`. `draft_ids` empty/None means "all pending",
    minus `exclude_ids` (drafts created THIS turn — the agent's two-turn
    guard); if the exclusion leaves nothing, refuse with the review-first
    message instead of silently promoting what was just proposed."""
    from app.database import get_connection
    from app.matcha.services.pilots import handbook_pilot as hp

    exclude_ids = exclude_ids or set()

    async with get_connection() as conn:
        session = await _load_session(conn, session_id, company_id)
        if not session:
            return {"status": "error", "message": "No handbook session for this thread yet — draft something first."}
        reason = await hp.unpaid_x_reason(conn, company_id)
        if reason:
            return {"status": "refused", "message": reason}

        target_uuid: Optional[UUID] = None
        if target_handbook_id:
            try:
                target_uuid = UUID(str(target_handbook_id))
            except ValueError:
                return {"status": "error",
                        "message": "That doesn't look like a handbook id."}
            hb = await conn.fetchrow(
                "SELECT id, status FROM handbooks WHERE id = $1 AND company_id = $2",
                target_uuid, company_id,
            )
            if not hb:
                return {"status": "error",
                        "message": "No handbook with that id belongs to this company."}
            if hb["status"] == "archived":
                return {"status": "refused",
                        "message": "That handbook is archived — unarchive it or promote to a new handbook."}

        # Re-derive live scopes (not the session snapshot) so a promoted
        # handbook is scoped to the company's current work locations.
        try:
            from app.core.services.handbook_service import derive_handbook_scopes_from_employees
            scopes = await derive_handbook_scopes_from_employees(conn, str(company_id))
        except Exception:  # noqa: BLE001
            logger.warning("huume handbook_skill: scope derivation failed for promote %s", company_id)
            scopes = session.get("scopes") or []

        if draft_ids:
            valid: list[UUID] = []
            for d in draft_ids:
                try:
                    valid.append(UUID(str(d)))
                except ValueError:
                    continue
            if not valid:
                return {"status": "error", "message": "None of those look like draft ids — see the pending drafts list."}
            rows = await conn.fetch(
                """SELECT * FROM handbook_pilot_drafts
                   WHERE session_id = $1 AND company_id = $2 AND id = ANY($3::uuid[])
                     AND status = 'pending'""",
                session["id"], company_id, valid,
            )
        else:
            rows = await conn.fetch(
                """SELECT * FROM handbook_pilot_drafts
                   WHERE session_id = $1 AND company_id = $2 AND status = 'pending'
                   ORDER BY created_at""",
                session["id"], company_id,
            )

    drafts = [dict(r) for r in rows if str(r["id"]) not in exclude_ids]
    held_back = [dict(r) for r in rows if str(r["id"]) in exclude_ids]
    if not drafts:
        if held_back:
            return {"status": "refused", "message": (
                "Those drafts were just proposed this turn — review them and promote on your next message."
            )}
        return {"status": "error", "message": "No promotable pending drafts found."}

    result = await hp.promote_drafts(
        company_id, session, drafts, scopes=scopes,
        handbook_title=handbook_title,
        target_handbook_id=str(target_uuid) if target_uuid else None,
        user_id=actor_user_id,
    )

    async with get_connection() as conn:
        await _audit(conn, session["id"], actor_user_id, "promote",
                     {"promoted": list(result["promoted_refs"].keys()),
                      "failed": [f["draft_id"] for f in result["failed"]],
                      "target_handbook_id": str(target_uuid) if target_uuid else None,
                      "resolved_change_requests": [
                          c["change_request_id"]
                          for c in result["resolved_change_requests"]],
                      "via": "huume", "thread_id": str(thread_id)})
        pending = await _pending_drafts(conn, session["id"])

    out: dict[str, Any] = {
        "status": "ok",
        "session_id": str(session["id"]),
        "promoted": len(result["promoted_refs"]),
        "handbook": result["handbook"],
        "policies": result["policies"],
        "failed": result["failed"],
        "resolved_change_requests": result["resolved_change_requests"],
        "pending_drafts": pending,
    }
    if held_back:
        out["held_back"] = [{"draft_id": str(d["id"]), "title": d["title"]} for d in held_back]
        out["message"] = ("Some drafts were proposed this turn and were NOT promoted — "
                          "review them and promote on a later message.")
    return out
