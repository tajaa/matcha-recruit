"""Saved payment cards and shipping addresses for agent purchases (per user;
admins plus the `AGENT_PURCHASE_ALLOWED_EMAILS` allowlist in v1).

The card number is validated, encrypted with the vault key and stored; only
brand, last 4 digits, expiry, a label and an optional billing address ever come
back out. There is no CVV field and no endpoint that returns the number. Cards
are never read from chat.

A card with no billing address bills to the shipping address. Shipping
addresses (up to five, one default) are where the assistant ships a purchase.
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.models.auth import CurrentUser
from app.core.services import card_vault
from app.database import get_connection
from app.matcha.dependencies import require_company_member
from app.matcha.models.matcha_work.purchases import (
    AddressIn,
    BillingAddressUpdate,
    PaymentCardCreate,
    ShippingAddressIn,
)
from app.matcha.services.matcha_work import shipping_addresses as addresses
from app.matcha.services.matcha_work.agent_card.chat_flow import purchases_allowed

router = APIRouter()

MAX_CARDS_PER_USER = 5
MAX_LABEL_DIGITS = 4


_CARD_COLUMNS = "id, label, brand, last4, exp_month, exp_year, billing_address, created_at"


def _card_out(row) -> dict:
    return {
        "id": str(row["id"]),
        "label": row["label"],
        "brand": row["brand"],
        "last4": row["last4"],
        "exp_month": row["exp_month"],
        "exp_year": row["exp_year"],
        "billing_address": addresses.billing_of(row),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def _clean_address(body: AddressIn | None) -> dict | None:
    if body is None:
        return None
    try:
        return addresses.normalize(body.model_dump())
    except addresses.AddressError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
            f"""SELECT {_CARD_COLUMNS}
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
    billing = _clean_address(body.billing_address)
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
                f"""INSERT INTO mw_payment_cards
                       (id, user_id, label, brand, last4, exp_month, exp_year, pan_ciphertext, key_id,
                        billing_address)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                    RETURNING {_CARD_COLUMNS}""",
                card_id, current_user.id, label, card_vault.card_brand(pan), pan[-4:],
                body.exp_month, body.exp_year, ciphertext, key_id,
                json.dumps(billing) if billing else None,
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


@router.put("/payment-cards/{card_id}/billing-address")
async def set_card_billing_address(
    card_id: UUID,
    body: BillingAddressUpdate,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Set the card's own billing address, or clear it (null) to bill to the
    shipping address."""
    _require_purchases(current_user)
    billing = _clean_address(body.billing_address)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""UPDATE mw_payment_cards SET billing_address = $3::jsonb
                WHERE id = $1 AND user_id = $2
                RETURNING {_CARD_COLUMNS}""",
            card_id, current_user.id, json.dumps(billing) if billing else None,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return _card_out(row)


# ── shipping addresses ───────────────────────────────────────────────────────

@router.get("/shipping-addresses")
async def list_shipping_addresses(current_user: CurrentUser = Depends(require_company_member)):
    async with get_connection() as conn:
        rows = await addresses.list_addresses(conn, current_user.id)
    return {"enabled": purchases_allowed(current_user), "addresses": rows}


async def _lock_addresses(conn, user_id) -> None:
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{user_id}:shipping_addresses")


@router.post("/shipping-addresses", status_code=status.HTTP_201_CREATED)
async def add_shipping_address(
    body: ShippingAddressIn,
    current_user: CurrentUser = Depends(require_company_member),
):
    _require_purchases(current_user)
    clean = _clean_address(body)
    async with get_connection() as conn:
        async with conn.transaction():
            await _lock_addresses(conn, current_user.id)
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mw_shipping_addresses WHERE user_id = $1", current_user.id,
            )
            if count >= addresses.MAX_ADDRESSES_PER_USER:
                raise HTTPException(
                    status_code=409,
                    detail=f"You can save up to {addresses.MAX_ADDRESSES_PER_USER} addresses. Remove one first.",
                )
            # The first address is the default whatever was asked.
            make_default = body.is_default or count == 0
            if make_default:
                await conn.execute(
                    "UPDATE mw_shipping_addresses SET is_default = FALSE WHERE user_id = $1 AND is_default",
                    current_user.id,
                )
            row = await conn.fetchrow(
                f"""INSERT INTO mw_shipping_addresses
                        (user_id, name, line1, line2, city, region, postal_code, country, phone, is_default)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING {addresses.ADDRESS_COLUMNS}""",
                current_user.id, *(clean[k] for k in addresses.FIELDS), make_default,
            )
    return addresses.address_out(row)


@router.put("/shipping-addresses/{address_id}")
async def update_shipping_address(
    address_id: UUID,
    body: ShippingAddressIn,
    current_user: CurrentUser = Depends(require_company_member),
):
    _require_purchases(current_user)
    clean = _clean_address(body)
    async with get_connection() as conn:
        async with conn.transaction():
            await _lock_addresses(conn, current_user.id)
            if body.is_default:
                await conn.execute(
                    """UPDATE mw_shipping_addresses SET is_default = FALSE
                       WHERE user_id = $1 AND is_default AND id <> $2""",
                    current_user.id, address_id,
                )
            # Unticking "default" never leaves the person without one: only
            # making another address the default moves it.
            row = await conn.fetchrow(
                f"""UPDATE mw_shipping_addresses
                    SET name = $3, line1 = $4, line2 = $5, city = $6, region = $7, postal_code = $8,
                        country = $9, phone = $10, is_default = is_default OR $11, updated_at = NOW()
                    WHERE id = $1 AND user_id = $2
                    RETURNING {addresses.ADDRESS_COLUMNS}""",
                address_id, current_user.id, *(clean[k] for k in addresses.FIELDS), body.is_default,
            )
            if row is None:
                # Inside the transaction, so the defaults cleared above roll
                # back: a PUT on a missing or foreign id never strips the
                # person's default.
                raise HTTPException(status_code=404, detail="Address not found")
    return addresses.address_out(row)


@router.delete("/shipping-addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shipping_address(
    address_id: UUID,
    current_user: CurrentUser = Depends(require_company_member),
):
    """Past purchases keep the address they shipped to (a snapshot). Deleting
    the default makes the oldest remaining address the default."""
    async with get_connection() as conn:
        async with conn.transaction():
            await _lock_addresses(conn, current_user.id)
            was_default = await conn.fetchval(
                "DELETE FROM mw_shipping_addresses WHERE id = $1 AND user_id = $2 RETURNING is_default",
                address_id, current_user.id,
            )
            if was_default is None:
                raise HTTPException(status_code=404, detail="Address not found")
            if was_default:
                await conn.execute(
                    """UPDATE mw_shipping_addresses SET is_default = TRUE
                       WHERE id = (SELECT id FROM mw_shipping_addresses WHERE user_id = $1
                                   ORDER BY created_at, id LIMIT 1)""",
                    current_user.id,
                )
