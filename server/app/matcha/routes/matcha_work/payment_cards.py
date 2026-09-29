"""Saved payment cards for agent-card purchases (per user; admins plus the
`AGENT_PURCHASE_ALLOWED_EMAILS` allowlist in v1).

The card number is validated, encrypted with the vault key and stored; only
brand, last 4 digits, expiry and a label ever come back out. There is no CVV
field and no endpoint that returns the number. Cards are never read from chat.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.core.services import card_vault
from app.database import get_connection
from app.matcha.dependencies import require_company_member
from app.matcha.services.matcha_work.agent_card.chat_flow import purchases_allowed

router = APIRouter()

MAX_CARDS_PER_USER = 5
MAX_LABEL_DIGITS = 4


class PaymentCardCreate(BaseModel):
    number: str
    exp_month: int
    exp_year: int
    label: str = ""


def _card_out(row) -> dict:
    return {
        "id": str(row["id"]),
        "label": row["label"],
        "brand": row["brand"],
        "last4": row["last4"],
        "exp_month": row["exp_month"],
        "exp_year": row["exp_year"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def _require_purchases(user: CurrentUser) -> None:
    if not purchases_allowed(user):
        raise HTTPException(
            status_code=403,
            detail={"code": "purchases_unavailable", "message": "Agent purchases aren't available on this account."},
        )


@router.get("/payment-cards")
async def list_payment_cards(current_user: CurrentUser = Depends(require_company_member)):
    enabled = purchases_allowed(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, label, brand, last4, exp_month, exp_year, created_at
               FROM mw_payment_cards WHERE user_id = $1 ORDER BY created_at""",
            current_user.id,
        )
    return {
        "enabled": enabled,
        "configured": card_vault.vault_configured(),
        "cards": [_card_out(r) for r in rows],
    }


@router.post("/payment-cards", status_code=status.HTTP_201_CREATED)
async def add_payment_card(
    body: PaymentCardCreate,
    current_user: CurrentUser = Depends(require_company_member),
):
    _require_purchases(current_user)
    if not card_vault.vault_configured():
        raise HTTPException(status_code=503, detail="Card storage isn't set up on this server.")
    pan = card_vault.normalize_pan(body.number)
    if pan is None:
        raise HTTPException(status_code=400, detail="That isn't a valid card number.")
    if not card_vault.expiry_ok(body.exp_month, body.exp_year):
        raise HTTPException(status_code=400, detail="That card has expired or the expiry date is invalid.")
    label = " ".join((body.label or "").split())[:40]
    # The label is stored in plain text and shown in project chat ("Visa ending
    # 4242 (label)"), so it must never carry a card number — or any piece of
    # one: more than 4 digits is refused outright.
    if sum(ch.isdigit() for ch in label) > MAX_LABEL_DIGITS:
        raise HTTPException(status_code=400, detail="Card labels can't contain card numbers.")
    card_id = uuid4()
    ciphertext, key_id = card_vault.encrypt_pan(pan, card_id=card_id, user_id=current_user.id)
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"{current_user.id}:payment_cards",
            )
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mw_payment_cards WHERE user_id = $1", current_user.id,
            )
            if count >= MAX_CARDS_PER_USER:
                raise HTTPException(
                    status_code=409, detail=f"You can save up to {MAX_CARDS_PER_USER} cards. Remove one first.",
                )
            row = await conn.fetchrow(
                """INSERT INTO mw_payment_cards
                       (id, user_id, label, brand, last4, exp_month, exp_year, pan_ciphertext, key_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   RETURNING id, label, brand, last4, exp_month, exp_year, created_at""",
                card_id, current_user.id, label, card_vault.card_brand(pan), pan[-4:],
                body.exp_month, body.exp_year, ciphertext, key_id,
            )
    return _card_out(row)


@router.delete("/payment-cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_card(
    card_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Deletes the row, ciphertext included. Past purchase handoffs keep the
    last 4 digits they were approved with."""
    async with get_connection() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM mw_payment_cards WHERE id = $1 AND user_id = $2 RETURNING id",
            card_id, current_user.id,
        )
    if deleted is None:
        raise HTTPException(status_code=404, detail="Card not found")
