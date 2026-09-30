"""Shipping addresses and card billing addresses: validation and the routes.
No database: a scripted fake connection stands in."""
import base64
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.services import card_vault
from app.matcha.routes.matcha_work import payment_cards
from app.matcha.services.matcha_work import shipping_addresses as addresses
from tests.agent_runtime.helpers import FakeConn, connection

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
HOME = {"name": "Haley  Smith", "line1": "1 Main St", "line2": "", "city": "Oakland", "region": "CA",
        "postal_code": "94607", "country": "us", "phone": "(510) 555-0100"}


def _user(role="admin"):
    return SimpleNamespace(id=uuid4(), role=role, email=f"{role}@example.com")


def _row(**over):
    clean = addresses.normalize(HOME)
    return {"id": uuid4(), **clean, "is_default": True, "created_at": NOW, **over}


# ── validation ────────────────────────────────────────────────────────────────

def test_normalize_cleans_whitespace_and_the_country():
    clean = addresses.normalize(HOME)
    assert clean["name"] == "Haley Smith" and clean["country"] == "US"
    assert addresses.one_line(clean) == "Haley Smith, 1 Main St, Oakland, CA 94607, US"


@pytest.mark.parametrize("over, message", [
    ({"line1": ""}, "Missing line1"),
    ({"region": ""}, "Missing state"),
    ({"postal_code": "9460"}, "valid ZIP"),
    ({"country": "USA"}, "two-letter"),
    ({"line2": "4242 4242 4242 4242"}, "card numbers"),
    ({"phone": "call me"}, "phone"),
    ({"city": "x" * 81}, "too long"),
])
def test_normalize_refuses_bad_addresses(over, message):
    with pytest.raises(addresses.AddressError, match=message):
        addresses.normalize({**HOME, **over})


def test_a_non_us_address_needs_no_state_or_zip_shape():
    clean = addresses.normalize({**HOME, "country": "GB", "region": "", "postal_code": "SW1A 1AA"})
    assert clean["postal_code"] == "SW1A 1AA"


def test_billing_of_reads_jsonb_or_means_same_as_shipping():
    assert addresses.billing_of({"billing_address": None}) is None
    assert addresses.billing_of({"billing_address": json.dumps({"line1": "9 Bank St"})}) == {"line1": "9 Bank St"}
    assert addresses.billing_of({}) is None


# ── routes ────────────────────────────────────────────────────────────────────

@pytest.fixture
def db(monkeypatch):
    holder = {"conn": FakeConn()}

    def factory():
        return connection(holder["conn"])()

    monkeypatch.setattr(payment_cards, "get_connection", factory)
    monkeypatch.setenv(card_vault.KEYS_ENV, f"k1:{base64.b64encode(os.urandom(32)).decode()}")
    return holder


def _body(**over):
    return payment_cards.ShippingAddressIn(**{**HOME, **over})


@pytest.mark.asyncio
async def test_the_first_address_is_the_default_whatever_was_asked(db):
    db["conn"] = (FakeConn().on("COUNT(*)", 0)
                  .on("INSERT INTO mw_shipping_addresses", lambda *a: _row(is_default=a[-1])))
    out = await payment_cards.add_shipping_address(_body(is_default=False), _user())
    insert = db["conn"].ran("INSERT INTO mw_shipping_addresses")[0][2]
    assert insert[-1] is True and out["is_default"] is True
    assert insert[1] == "Haley Smith" and insert[7] == "US"
    assert db["conn"].ran("pg_advisory_xact_lock")[0][2][0].endswith(":shipping_addresses")


@pytest.mark.asyncio
async def test_a_new_default_unsets_the_old_one(db):
    db["conn"] = (FakeConn().on("COUNT(*)", 2)
                  .on("INSERT INTO mw_shipping_addresses", lambda *a: _row(is_default=a[-1])))
    await payment_cards.add_shipping_address(_body(is_default=True), _user())
    assert db["conn"].ran("SET is_default = FALSE")
    db["conn"] = (FakeConn().on("COUNT(*)", 2)
                  .on("INSERT INTO mw_shipping_addresses", lambda *a: _row(is_default=a[-1])))
    out = await payment_cards.add_shipping_address(_body(), _user())
    assert out["is_default"] is False and not db["conn"].ran("SET is_default = FALSE")


@pytest.mark.asyncio
async def test_addresses_are_capped_allowlisted_and_validated(db):
    db["conn"] = FakeConn().on("COUNT(*)", addresses.MAX_ADDRESSES_PER_USER)
    with pytest.raises(HTTPException) as exc:
        await payment_cards.add_shipping_address(_body(), _user())
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        await payment_cards.add_shipping_address(_body(), _user("client"))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await payment_cards.add_shipping_address(_body(postal_code="nope"), _user())
    assert exc.value.status_code == 400 and "ZIP" in exc.value.detail


@pytest.mark.asyncio
async def test_update_is_scoped_to_the_owner_and_never_drops_the_default(db):
    db["conn"] = FakeConn()  # no row updated
    with pytest.raises(HTTPException) as exc:
        await payment_cards.update_shipping_address(uuid4(), _body(), _user())
    assert exc.value.status_code == 404
    query = db["conn"].ran("UPDATE mw_shipping_addresses")[-1][1]
    assert "user_id = $2" in query and "is_default = is_default OR $11" in query


class _TxConn(FakeConn):
    """Records whether an exception left each transaction (i.e. rolled it back)."""

    def __init__(self):
        super().__init__()
        self.rolled_back = []

    @asynccontextmanager
    async def transaction(self):
        try:
            yield
        except BaseException:
            self.rolled_back.append(True)
            raise
        self.rolled_back.append(False)


@pytest.mark.asyncio
async def test_a_default_put_on_a_missing_id_rolls_back_the_cleared_default(db):
    db["conn"] = _TxConn()
    with pytest.raises(HTTPException) as exc:
        await payment_cards.update_shipping_address(uuid4(), _body(is_default=True), _user())
    assert exc.value.status_code == 404
    assert db["conn"].ran("SET is_default = FALSE")  # cleared inside the transaction…
    assert db["conn"].rolled_back == [True]           # …and rolled back with it


@pytest.mark.asyncio
async def test_deleting_the_default_promotes_the_oldest(db):
    db["conn"] = FakeConn().on("DELETE FROM mw_shipping_addresses", True)
    await payment_cards.delete_shipping_address(uuid4(), _user("client"))
    assert db["conn"].ran("SET is_default = TRUE")
    db["conn"] = FakeConn().on("DELETE FROM mw_shipping_addresses", False)
    await payment_cards.delete_shipping_address(uuid4(), _user())
    assert not db["conn"].ran("SET is_default = TRUE")
    db["conn"] = FakeConn()
    with pytest.raises(HTTPException) as exc:
        await payment_cards.delete_shipping_address(uuid4(), _user())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_addresses_default_first(db):
    db["conn"] = FakeConn().on("FROM mw_shipping_addresses", [_row()])
    out = await payment_cards.list_shipping_addresses(_user("client"))
    assert out["enabled"] is False and out["addresses"][0]["city"] == "Oakland"
    assert "ORDER BY is_default DESC" in db["conn"].calls[0][1]


def _card_row(billing=None):
    return {"id": uuid4(), "label": "", "brand": "visa", "last4": "4242", "exp_month": 12,
            "exp_year": 2031, "billing_address": json.dumps(billing) if billing else None, "created_at": NOW}


@pytest.mark.asyncio
async def test_a_card_can_carry_its_own_billing_address(db):
    db["conn"] = FakeConn().on("COUNT(*)", 0).on("INSERT INTO mw_payment_cards",
                                                  lambda *a: _card_row(json.loads(a[9]) if a[9] else None))
    body = payment_cards.PaymentCardCreate(number="4242 4242 4242 4242", exp_month=12, exp_year=2031,
                                           billing_address=payment_cards.AddressIn(**{**HOME, "line1": "9 Bank St"}))
    out = await payment_cards.add_payment_card(body, _user())
    assert out["billing_address"]["line1"] == "9 Bank St"
    plain = payment_cards.PaymentCardCreate(number="4242 4242 4242 4242", exp_month=12, exp_year=2031)
    out = await payment_cards.add_payment_card(plain, _user())
    assert out["billing_address"] is None  # same as shipping


@pytest.mark.asyncio
async def test_set_and_clear_a_cards_billing_address(db):
    db["conn"] = FakeConn().on("UPDATE mw_payment_cards", lambda *a: _card_row(json.loads(a[2]) if a[2] else None))
    out = await payment_cards.set_card_billing_address(
        uuid4(), payment_cards.BillingAddressUpdate(billing_address=payment_cards.AddressIn(**HOME)), _user())
    assert out["billing_address"]["city"] == "Oakland"
    out = await payment_cards.set_card_billing_address(uuid4(), payment_cards.BillingAddressUpdate(), _user())
    assert out["billing_address"] is None
    assert "user_id = $2" in db["conn"].calls[-1][1]
    db["conn"] = FakeConn()
    with pytest.raises(HTTPException) as exc:
        await payment_cards.set_card_billing_address(uuid4(), payment_cards.BillingAddressUpdate(), _user())
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        await payment_cards.set_card_billing_address(uuid4(), payment_cards.BillingAddressUpdate(), _user("client"))
    assert exc.value.status_code == 403
