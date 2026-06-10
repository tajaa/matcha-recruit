"""Productivity routes — personal kanban boards + cards.

Mounted under matcha_work_router so they inherit `require_feature("matcha_work")`.
Everything is user-scoped (the personal productivity hub), so endpoints key off
`current_user.id`; `company_id` is stored opportunistically but not required
(personal Werk users have no company).
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.models.auth import CurrentUser
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import productivity_service

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────────────


class BoardCreate(BaseModel):
    title: str


class BoardPatch(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None      # active | archived


class CardCreate(BaseModel):
    title: str
    notes: Optional[str] = None
    board_column: Optional[str] = None    # todo | in_progress | done
    due_date: Optional[date] = None       # calendar placement
    source_journal_id: Optional[UUID] = None
    source_excerpt: Optional[str] = None


class CardPatch(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    board_column: Optional[str] = None
    position: Optional[int] = None
    # due_date is sent via model_dump(exclude_unset=True): an explicit null
    # clears the date (removes from calendar); absent leaves it untouched.
    due_date: Optional[date] = None


class QuickTodo(BaseModel):
    title: str
    due_date: Optional[date] = None
    source_journal_id: Optional[UUID] = None
    source_excerpt: Optional[str] = None


# ── Boards ───────────────────────────────────────────────────────────────


@router.get("/productivity/boards")
async def list_boards_endpoint(current_user: CurrentUser = Depends(require_admin_or_client)):
    return await productivity_service.list_boards(current_user.id)


@router.post("/productivity/boards", status_code=201)
async def create_board_endpoint(
    body: BoardCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    return await productivity_service.create_board(current_user.id, company_id, title=body.title)


@router.patch("/productivity/boards/{board_id}")
async def update_board_endpoint(
    board_id: UUID,
    body: BoardPatch,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    board = await productivity_service.update_board(board_id, current_user.id, body.model_dump(exclude_unset=True))
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


@router.delete("/productivity/boards/{board_id}", status_code=204)
async def delete_board_endpoint(
    board_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await productivity_service.delete_board(board_id, current_user.id)


# ── Cards ────────────────────────────────────────────────────────────────


@router.get("/productivity/boards/{board_id}/cards")
async def list_cards_endpoint(
    board_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    return await productivity_service.list_cards(board_id, current_user.id)


@router.post("/productivity/boards/{board_id}/cards", status_code=201)
async def create_card_endpoint(
    board_id: UUID,
    body: CardCreate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    card = await productivity_service.create_card(
        board_id, current_user.id,
        title=body.title, notes=body.notes, board_column=body.board_column,
        due_date=body.due_date,
        source_journal_id=body.source_journal_id, source_excerpt=body.source_excerpt,
    )
    if card is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return card


@router.patch("/productivity/cards/{card_id}")
async def update_card_endpoint(
    card_id: UUID,
    body: CardPatch,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    card = await productivity_service.update_card(card_id, current_user.id, body.model_dump(exclude_unset=True))
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.delete("/productivity/cards/{card_id}", status_code=204)
async def delete_card_endpoint(
    card_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    await productivity_service.delete_card(card_id, current_user.id)


# ── Quick capture (journal selection → to-do) ────────────────────────────


@router.post("/productivity/quick-todo", status_code=201)
async def quick_todo_endpoint(
    body: QuickTodo,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    return await productivity_service.quick_todo(
        current_user.id, company_id,
        title=body.title, due_date=body.due_date,
        source_journal_id=body.source_journal_id, source_excerpt=body.source_excerpt,
    )
