"""Sym-chat routes — /matcha-work/sym-chats/*.

Business `/work` only: every handler resolves the caller's company through
`_business_scope`, which refuses personal (Espresso) workspaces and the
`individual` role that `require_admin_or_client` would otherwise admit. The
`sym_chat` flag gates the whole router on top of the package's `matcha_work`
gate. All logic lives in `services/sym_chat/service.py`.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.core.services.redis_cache import check_rate_limit
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_feature, resolve_accessible_company_scope
from app.matcha.models.sym_chat import SymChatCreate, SymChatMessageCreate
from app.matcha.services.sym_chat import service
from app.matcha.services.sym_chat.kinds import KINDS

router = APIRouter(prefix="/sym-chats", dependencies=[Depends(require_feature("sym_chat"))])

# (limit, window seconds). Turns are the Gemini spend; creates send emails.
TURN_LIMIT_PER_CHAT = (200, 3600)
TURN_LIMIT_PER_COMPANY = (1000, 3600)
CREATE_LIMIT_PER_USER = (30, 3600)


async def _business_scope(current_user: CurrentUser) -> UUID:
    if current_user.role not in ("admin", "client"):
        raise HTTPException(status_code=403, detail="Sym-chat is only available in business workspaces")
    scope = await resolve_accessible_company_scope(current_user)
    company_id = scope.get("company_id")
    if not company_id:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    async with get_connection() as conn:
        is_personal = await conn.fetchval(
            "SELECT COALESCE(is_personal, false) FROM companies WHERE id = $1",
            company_id,
        )
    if is_personal:
        raise HTTPException(status_code=403, detail="Sym-chat is only available in business workspaces")
    return company_id


def _raise(exc: service.SymChatError):
    raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/kinds")
async def list_kinds(current_user: CurrentUser = Depends(require_admin_or_client)):
    await _business_scope(current_user)
    return {"kinds": [{"kind": k, **v} for k, v in KINDS.items()]}


@router.get("")
async def list_sym_chats(current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_scope(current_user)
    return {"sym_chats": await service.list_for_user(company_id, current_user.id)}


@router.post("")
async def create_sym_chat(body: SymChatCreate, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_scope(current_user)
    await check_rate_limit(str(current_user.id), "sym_chat_create", *CREATE_LIMIT_PER_USER)
    try:
        return await service.create_sym_chat(
            company_id=company_id,
            user_id=current_user.id,
            kind=body.kind,
            title=body.title,
            objective=body.objective,
            participant_ids=body.participant_ids,
            raw_config=body.config,
        )
    except service.SymChatError as exc:
        _raise(exc)


# Declared before /{chat_id} so "people" is never read as a chat id.
@router.get("/people")
async def search_people(
    q: str | None = Query(default=None, max_length=100),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _business_scope(current_user)
    return {"people": await service.search_people(company_id, current_user.id, q)}


@router.get("/{chat_id}")
async def get_sym_chat(chat_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_scope(current_user)
    try:
        return await service.get_detail(chat_id, company_id, current_user.id)
    except service.SymChatError as exc:
        _raise(exc)


@router.post("/{chat_id}/messages")
async def send_sym_chat_message(
    chat_id: UUID,
    body: SymChatMessageCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await _business_scope(current_user)
    await check_rate_limit(str(chat_id), "sym_chat_turn", *TURN_LIMIT_PER_CHAT)
    await check_rate_limit(str(company_id), "sym_chat_turn_company", *TURN_LIMIT_PER_COMPANY)
    try:
        return await service.run_turn(chat_id, company_id, current_user.id, body.content)
    except service.SymChatError as exc:
        _raise(exc)


@router.post("/{chat_id}/cancel")
async def cancel_sym_chat(chat_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await _business_scope(current_user)
    try:
        return await service.cancel(chat_id, company_id, current_user.id)
    except service.SymChatError as exc:
        _raise(exc)
