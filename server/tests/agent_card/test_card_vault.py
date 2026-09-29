import base64
import os
from datetime import date
from uuid import uuid4

import pytest

from app.core.services import card_vault

VISA = "4242424242424242"  # standard test number (Luhn-valid)


def _key(key_id: str = "k1") -> str:
    return f"{key_id}:{base64.b64encode(os.urandom(32)).decode()}"


@pytest.fixture
def keys(monkeypatch):
    first, second = _key("k2"), _key("k1")
    monkeypatch.setenv(card_vault.KEYS_ENV, f"{first},{second}")
    return first, second


def test_round_trip_is_bound_to_row_and_owner(keys):
    card_id, user_id = uuid4(), uuid4()
    blob, key_id = card_vault.encrypt_pan(VISA, card_id=card_id, user_id=user_id)
    assert key_id == "k2"  # the first key encrypts
    assert VISA.encode() not in blob
    assert card_vault.decrypt_pan(blob, key_id, card_id=card_id, user_id=user_id) == VISA
    with pytest.raises(ValueError):
        card_vault.decrypt_pan(blob, key_id, card_id=uuid4(), user_id=user_id)
    with pytest.raises(ValueError):
        card_vault.decrypt_pan(blob, key_id, card_id=card_id, user_id=uuid4())


def test_older_keys_still_decrypt_after_rotation(monkeypatch):
    old = _key("k1")
    monkeypatch.setenv(card_vault.KEYS_ENV, old)
    card_id, user_id = uuid4(), uuid4()
    blob, key_id = card_vault.encrypt_pan(VISA, card_id=card_id, user_id=user_id)
    monkeypatch.setenv(card_vault.KEYS_ENV, f"{_key('k2')},{old}")
    assert card_vault.decrypt_pan(blob, key_id, card_id=card_id, user_id=user_id) == VISA
    monkeypatch.setenv(card_vault.KEYS_ENV, _key("k2"))
    with pytest.raises(card_vault.VaultUnavailable):
        card_vault.decrypt_pan(blob, key_id, card_id=card_id, user_id=user_id)


@pytest.mark.parametrize("value", ["", "k1", "k1:not-base64!!", f"k1:{base64.b64encode(b'short').decode()}", "bad id:AAAA"])
def test_storing_fails_closed_without_a_valid_key(monkeypatch, value):
    monkeypatch.setenv(card_vault.KEYS_ENV, value)
    assert card_vault.vault_configured() is False
    with pytest.raises(card_vault.VaultUnavailable):
        card_vault.encrypt_pan(VISA, card_id=uuid4(), user_id=uuid4())


def test_unset_key_is_not_configured(monkeypatch):
    monkeypatch.delenv(card_vault.KEYS_ENV, raising=False)
    assert card_vault.vault_configured() is False


@pytest.mark.parametrize("raw, expected", [
    ("4242 4242 4242 4242", VISA),
    ("4242-4242-4242-4242", VISA),
    ("  4242424242424242 ", VISA),
    ("4242424242424241", None),  # fails Luhn
    ("4242", None),
    ("4242 4242 abcd 4242", None),
    (None, None),
])
def test_normalize_pan(raw, expected):
    assert card_vault.normalize_pan(raw) == expected


@pytest.mark.parametrize("pan, brand", [
    (VISA, "visa"), ("5555555555554444", "mastercard"), ("2223003122003222", "mastercard"),
    ("378282246310005", "amex"), ("6011111111111117", "discover"), ("3530111333300000", "card"),
])
def test_card_brand(pan, brand):
    assert card_vault.card_brand(pan) == brand


def test_expiry_counts_through_the_end_of_the_month():
    today = date(2026, 9, 28)
    assert card_vault.expiry_ok(9, 2026, today=today)
    assert not card_vault.expiry_ok(8, 2026, today=today)
    assert card_vault.expiry_ok(1, 2030, today=today)
    assert not card_vault.expiry_ok(13, 2030, today=today)


def test_card_numbers_in_chat_are_found_and_redacted_but_other_numbers_are_not():
    text = "use 4242 4242 4242 4242 exp 12/30, order 1234567890123 thanks"
    assert card_vault.contains_pan(text)
    redacted = card_vault.redact_pans(text)
    assert "4242 4242" not in redacted and card_vault.REDACTED in redacted
    assert "12/30" in redacted
    # A non-Luhn digit run (order number) is left alone.
    assert "1234567890123" in redacted
    assert not card_vault.contains_pan("call me at 415 555 0100")


def test_a_card_number_followed_by_its_cvv_is_still_redacted():
    redacted = card_vault.redact_pans("card 4242 4242 4242 4242 123 exp 1230")
    assert redacted == f"card {card_vault.REDACTED} 123 exp 1230"
    assert card_vault.redact_pans("no digits here") == "no digits here"
    assert card_vault.redact_pans("") == ""
