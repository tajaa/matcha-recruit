"""Cappe social — the chat composer.

The owner drops photos and videos into a chat and says what to post, where
and when ("post these everywhere at 2pm tomorrow and link the oat latte").
Each turn is one Claude call that writes the copy for every network; the
plan comes back as a card the owner can edit, and nothing is posted until
they confirm it (`…/plans/{id}/confirm`), which makes the same posts the form
composer does, and for videos the files to download for TikTok and YouTube
(exports — "prepare this for all platforms" makes only those). Planning and
confirming: `services/social/chat/`. The owner's chats are listed, renamed
and deleted here too.

Gates: `social` for the chat, `social_video` for any video in it. No pooled
connection is held while the model is called.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeSocialChat,
    CappeSocialChatMessage,
    CappeSocialChatRename,
    CappeSocialChatSummary,
    CappeSocialChatTurn,
    CappeSocialChatTurnInput,
    CappeSocialPlanCard,
    CappeSocialPlanConfirm,
    CappeSocialPlanConfirmed,
    CappeSocialPost,
)
from ..services.common import loads_list, site_public_origin
from ..services.entitlements import resolve_entitlements
from ..services.merlin import store as convo_store
from ..services.social import ai as social_ai
from ..services.social import assets as asset_store
from ..services.social import connections as conn_store
from ..services.social import inbox as inbox_store
from ..services.social import posts as post_store
from ..services.social.chat import confirm as confirmer
from ..services.social.chat import plan as planner
from ..services.social.chat import turn as chat
from ._shared import get_owned_site
from . import social_exports
from .social import _social_gate, _video_gate, site_zone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sites/{site_id}/social/chat")

_TURNS_PER_HOUR = 60
_MAX_PRODUCTS = 60


async def _conversation(conn, conversation_id: UUID, site_id: UUID, account_id: UUID) -> dict:
    convo = await convo_store.get_owned_conversation(conn, conversation_id, account_id)
    if convo["kind"] != chat.KIND or convo["site_id"] != site_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return convo


def _message(m: dict) -> CappeSocialChatMessage:
    return CappeSocialChatMessage(id=m["id"], role=m["role"], content=m["content"] or "",
                                  attachments=m.get("attachments") or [], created_at=m["created_at"])


def _card(action: Optional[dict]) -> Optional[CappeSocialPlanCard]:
    return CappeSocialPlanCard(**action) if action else None


async def _products(conn, site_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """SELECT id, name, slug, price_cents, currency FROM cappe_products
           WHERE site_id = $1 AND status = 'active' ORDER BY updated_at DESC LIMIT $2""",
        site_id, _MAX_PRODUCTS,
    )
    return [dict(r) for r in rows]


def _summary(row) -> CappeSocialChatSummary:
    d = dict(row)
    plan = chat.latest(loads_list(d.get("staged_actions")) or [])
    last = " ".join(str(d.get("last") or "").split())
    return CappeSocialChatSummary(id=d["id"], title=d["title"], created_at=d.get("created_at"),
                                  updated_at=d["updated_at"], last=last[:120] or None,
                                  plan_status=plan.get("status") if plan else None)


@router.get("/conversations", response_model=list[CappeSocialChatSummary])
async def list_chats(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """The owner's chats for this site, newest first, with the last thing
    said and whether a plan is waiting on them."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            """SELECT c.id, c.title, c.created_at, c.updated_at, c.staged_actions,
                      (SELECT m.content FROM cappe_merlin_messages m WHERE m.conversation_id = c.id
                        ORDER BY m.created_at DESC LIMIT 1) AS last
               FROM cappe_merlin_conversations c
               WHERE c.site_id = $1 AND c.account_id = $2 AND c.kind = $3 ORDER BY c.updated_at DESC LIMIT 30""",
            site_id, account.id, chat.KIND,
        )
    return [_summary(r) for r in rows]


@router.patch("/conversations/{conversation_id}", response_model=CappeSocialChatSummary)
async def rename_chat(site_id: UUID, conversation_id: UUID, body: CappeSocialChatRename,
                      account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        convo = await _conversation(conn, conversation_id, site_id, account.id)
        title = " ".join(body.title.split())[:120] or convo["title"]
        await convo_store.rename_conversation(conn, conversation_id, title)
    plan = chat.latest(convo["staged_actions"] or [])
    return CappeSocialChatSummary(id=convo["id"], title=title, created_at=convo.get("created_at"),
                                  updated_at=convo["updated_at"], plan_status=plan.get("status") if plan else None)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(site_id: UUID, conversation_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Forget a chat. Posts and files it made stay."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _conversation(conn, conversation_id, site_id, account.id)
        await convo_store.delete_conversation(conn, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}", response_model=CappeSocialChat)
async def get_chat(site_id: UUID, conversation_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        convo = await _conversation(conn, conversation_id, site_id, account.id)
        messages = await convo_store.get_messages(conn, conversation_id)
    return CappeSocialChat(id=convo["id"], title=convo["title"], messages=[_message(m) for m in messages],
                           plan=_card(chat.latest(convo["staged_actions"] or [])))


async def _checked_attachments(conn, site_id: UUID, body: CappeSocialChatTurnInput, ent) -> list[dict]:
    out = []
    videos = [str(a.asset_id) for a in body.attachments if a.kind == "video"]
    if videos:
        _video_gate(ent)
    found = await asset_store.load_many(conn, videos) if videos else {}
    for att in body.attachments:
        if att.kind == "video":
            asset = found.get(str(att.asset_id))
            if asset is None or asset["site_id"] != site_id or asset["status"] in ("uploading", "failed", "deleted"):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail=(asset or {}).get("error") or "That video isn't ready to use")
            out.append({"kind": "video", "asset_id": str(att.asset_id), "name": att.name})
        else:
            if not chat.own_image(att.url):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail="Upload photos through the Social page first")
            out.append({"kind": "image", "url": att.url, "name": att.name})
    return out


@router.post("/turns", response_model=CappeSocialChatTurn)
async def chat_turn(site_id: UUID, body: CappeSocialChatTurnInput, account: CappeAccount = Depends(require_cappe_account)):
    """One message → one plan. The owner's message is saved first, so a
    failed model call doesn't lose what they wrote."""
    message = body.message.strip()
    if not message and not body.attachments:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Say what to post, or drop something in")
    await check_rate_limit(str(account.id), "cappe_social_chat", _TURNS_PER_HOUR, 3600)
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        _social_gate(ent)
        attachments = await _checked_attachments(conn, site_id, body, ent)
        if body.conversation_id:
            convo = await _conversation(conn, body.conversation_id, site_id, account.id)
        else:
            convo = await convo_store.create_conversation(
                conn, account_id=account.id, site_id=site_id, page_id=None, kind=chat.KIND,
                title=convo_store.title_from_message(message or "Photos and videos"),
            )
            convo["staged_actions"] = []
        history = await convo_store.load_history(conn, convo["id"])
        await convo_store.add_message(conn, convo["id"], role="user", content=message, attachments=attachments)
        messages = await convo_store.get_messages(conn, convo["id"])
        video_ids = [a["asset_id"] for m in messages if m["role"] == "user"
                     for a in (m.get("attachments") or []) if a.get("kind") == "video"]
        items = chat.items_from(messages, await asset_store.load_many(conn, video_ids),
                                exclude=chat.posted_keys(convo["staged_actions"] or [])
                                | await confirmer.posted_from_chat(conn, site_id, convo["id"]))
        settings = await inbox_store.get_settings(conn, site_id)
        accounts = await conn_store.list_connections(conn, site_id)
        products = await _products(conn, site_id)
    current = chat.proposed(convo["staged_actions"] or [])
    tz = site_zone(site)
    try:
        reply, plan, model = await chat.think(
            site=dict(site), settings=settings, accounts=accounts, products=products, items=items, history=history,
            current_plan=current["plan"] if current else None, message=message or "(dropped without a message)",
            now_local=datetime.now(tz), tz_name=str(tz), origin=site_public_origin(site),
        )
    except social_ai.AiUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except (RuntimeError, ValueError) as exc:
        logger.warning("cappe social chat turn failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Couldn't plan that just now — try again in a moment.")
    async with get_connection() as conn:
        summary = planner.summary(plan)
        saved = await convo_store.add_message(conn, convo["id"], role="assistant", content=reply,
                                              results=[{"summary": summary}] if summary else None)
        card = None
        if plan is not None:
            card = chat.staged(plan, revision=chat.next_revision(convo["staged_actions"] or []), model=model)
            await convo_store.mutate_staged_actions(conn, convo["id"], chat.replace_proposed(card))
    return CappeSocialChatTurn(conversation_id=convo["id"], message=_message(saved), plan=_card(card))


@router.post("/conversations/{conversation_id}/plans/{plan_id}/confirm", response_model=CappeSocialPlanConfirmed)
async def confirm_plan(
    site_id: UUID, conversation_id: UUID, plan_id: str, body: CappeSocialPlanConfirm,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Make the posts (and the files to download, for its videos). The
    plan's row is locked for the whole write, so a second click finds it
    already `executed`. `export` mode makes only the files."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        ent = await resolve_entitlements(account.plan, conn=conn)
        _social_gate(ent)
        await _conversation(conn, conversation_id, site_id, account.id)
        live = {str(c["id"]): c for c in await conn_store.list_connections(conn, site_id) if c["status"] == "connected"}
        unknown = [c for c in body.connection_ids if str(c) not in live]
        if unknown:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
        accounts = [{"connection_id": str(c), "platform": live[str(c)]["platform"]} for c in body.connection_ids]
        async with conn.transaction():
            actions = await convo_store.lock_conversation_actions(conn, conversation_id)
            action = next((a for a in actions if a.get("id") == plan_id and a.get("kind") == chat.ACTION_KIND), None)
            if action is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
            if action.get("status") != "proposed":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"This plan was already {action['status']}")
            if int(action.get("revision") or 0) != body.revision:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The plan changed — check the new one")
            try:
                plan = confirmer.apply_edits(action["plan"], [p.model_dump() for p in body.posts] if body.posts else None,
                                             keep_link=body.keep_link,
                                             exports=body.exports.model_dump() if body.exports else None)
                confirmer.check(plan, [a["platform"] for a in accounts], mode=body.mode)
                first_at = confirmer.schedule(body.mode, body.when_local, site_zone(site))
            except confirmer.PlanError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
            if plan.get("exports") or any(m.get("kind") == "video" for p in plan["posts"] for m in p.get("media") or []):
                _video_gate(ent)
            # Files only post nothing, so there is nothing to have posted twice.
            if body.mode != "export":
                try:
                    await confirmer.check_media(conn, site_id, conversation_id, plan)
                except confirmer.AlreadyPosted as exc:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
                except confirmer.PlanError as exc:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
            provenance = {"conversation_id": str(conversation_id), "plan_id": plan_id, "revision": body.revision}
            created = [] if body.mode == "export" else await confirmer.create_posts(
                conn, site_id=site_id, plan=plan, accounts=accounts, first_at=first_at,
                publish_now=body.mode == "now", tz=site_zone(site), provenance=provenance,
            )
            made = await confirmer.create_exports(conn, site_id=site_id, account_id=account.id, plan=plan,
                                                  provenance=provenance)
            done = {**action, "status": "executed", "plan": plan, "post_ids": [str(c["id"]) for c in created],
                    "export_ids": [str(e["id"]) for e in made], "executed_at": datetime.now(timezone.utc).isoformat()}
            await convo_store.mutate_staged_actions(
                conn, conversation_id, lambda current: [done if a.get("id") == plan_id else a for a in current])
        posts = [await post_store.get_post(conn, site_id, c["id"]) for c in created]
        exports = await social_exports.views(conn, made)
    social_exports.queue([e["id"] for e in made])
    for c in created:
        if c["publish_now"]:
            try:
                from app.workers.tasks.cappe_social_publisher import run_cappe_social_publish_post

                run_cappe_social_publish_post.delay(str(c["id"]))
            except Exception:  # noqa: BLE001 — the minute sweep picks it up
                logger.warning("cappe social chat: could not dispatch publish for %s", c["id"], exc_info=True)
    return CappeSocialPlanConfirmed(plan=CappeSocialPlanCard(**done),
                                    posts=[CappeSocialPost(**p) for p in posts if p], exports=exports)


@router.post("/conversations/{conversation_id}/plans/{plan_id}/dismiss", response_model=CappeSocialPlanCard)
async def dismiss_plan(site_id: UUID, conversation_id: UUID, plan_id: str,
                       account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _conversation(conn, conversation_id, site_id, account.id)
        found: dict = {}

        def dismiss(current: list[dict]) -> list[dict]:
            out = []
            for a in current:
                if a.get("id") == plan_id and a.get("kind") == chat.ACTION_KIND:
                    a = {**a, "status": "dismissed"} if a.get("status") == "proposed" else a
                    found["action"] = a
                out.append(a)
            return out

        await convo_store.mutate_staged_actions(conn, conversation_id, dismiss)
    if "action" not in found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return CappeSocialPlanCard(**found["action"])


__all__ = ["router"]
