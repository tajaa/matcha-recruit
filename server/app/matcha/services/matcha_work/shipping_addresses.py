"""Shipping (and billing) addresses for assistant purchases.

A person keeps up to five shipping addresses, one of them the default. A saved
card may carry its own billing address; when it has none, billing is the same
as shipping. Addresses are plain text (they are shown back in chat on the
confirmation card), so no field may hold a card number.

Pure helpers plus two small reads, shared by the REST routes
(`routes/matcha_work/payment_cards.py`) and the purchase ability
(`agent_runtime/abilities/purchase.py`).
"""
from __future__ import annotations

import re
from typing import Any

from app.core.services import card_vault
from app.database import decode_jsonb

MAX_ADDRESSES_PER_USER = 5

_LIMITS = {
    "name": 80, "line1": 120, "line2": 120, "city": 80, "region": 80,
    "postal_code": 20, "country": 10, "phone": 30,  # country: checked as a 2-letter code below
}
REQUIRED = ("name", "line1", "city", "postal_code", "country")
FIELDS = tuple(_LIMITS)
_US_ZIP = re.compile(r"^\d{5}(?:-\d{4})?$")
_PHONE = re.compile(r"^[0-9+()\-. ]*$")

ADDRESS_COLUMNS = "id, name, line1, line2, city, region, postal_code, country, phone, is_default, created_at"


class AddressError(ValueError):
    """User-facing: what is wrong with the address."""


def normalize(raw: Any) -> dict:
    """A clean address dict, or AddressError. Whitespace is collapsed, the
    country upper-cased, and a US address must have a state and a ZIP."""
    if not isinstance(raw, dict):
        raise AddressError("An address is required.")
    out: dict[str, str] = {}
    for key, limit in _LIMITS.items():
        value = " ".join(str(raw.get(key) or "").split())
        if len(value) > limit:
            raise AddressError(f"{key.replace('_', ' ').capitalize()} is too long.")
        if card_vault.contains_pan(value):
            raise AddressError("Addresses can't contain card numbers.")
        out[key] = value
    out["country"] = (out["country"] or "US").upper()
    if not re.fullmatch(r"[A-Z]{2}", out["country"]):
        raise AddressError("Country must be a two-letter code, like US.")
    missing = [k for k in REQUIRED if not out[k]]
    if missing:
        raise AddressError("Missing " + ", ".join(k.replace("_", " ") for k in missing) + ".")
    if out["country"] == "US":
        if not out["region"]:
            raise AddressError("Missing state.")
        if not _US_ZIP.match(out["postal_code"]):
            raise AddressError("That isn't a valid ZIP code.")
    if not _PHONE.match(out["phone"]):
        raise AddressError("That isn't a valid phone number.")
    return out


def one_line(address: dict | None) -> str:
    """"Haley Smith, 1 Main St, Apt 2, Oakland, CA 94607, US"."""
    if not isinstance(address, dict):
        return ""
    locality = " ".join(p for p in (address.get("region"), address.get("postal_code")) if p)
    parts = [
        address.get("name"), address.get("line1"), address.get("line2"), address.get("city"),
        locality, address.get("country"),
    ]
    return ", ".join(p for p in parts if p)


def snapshot(address: dict) -> dict:
    """Just the address fields, for freezing into a purchase."""
    return {key: str(address.get(key) or "") for key in FIELDS}


def address_out(row) -> dict:
    return {
        "id": str(row["id"]),
        **{key: row[key] for key in FIELDS},
        "is_default": bool(row["is_default"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def billing_of(card_row) -> dict | None:
    """The card's own billing address, or None for "same as shipping"."""
    getter = getattr(card_row, "get", None)
    raw = getter("billing_address") if getter else None
    value = decode_jsonb(raw, None) if raw is not None else None
    return value if isinstance(value, dict) and value else None


async def list_addresses(conn, user_id) -> list[dict]:
    """Default first, then oldest first."""
    rows = await conn.fetch(
        f"""SELECT {ADDRESS_COLUMNS} FROM mw_shipping_addresses
            WHERE user_id = $1 ORDER BY is_default DESC, created_at""",
        user_id,
    )
    return [address_out(r) for r in rows]
