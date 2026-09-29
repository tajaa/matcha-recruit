"""Payment-card numbers at rest, plus the card-number checks chat needs.

Only the card number (PAN) is encrypted and stored. Expiry, brand and last 4
digits are plain columns; the CVV is never accepted or stored.

Key handling is deliberately separate from `secret_crypto` (which derives its
key from the JWT secret): card numbers use their own AES-256-GCM keys from
`PAYMENT_CARD_KEYS`, and storing a card fails closed when that is unset.
Format: `PAYMENT_CARD_KEYS="k2:<base64 32 bytes>,k1:<base64 32 bytes>"`. The
first key encrypts, every listed key decrypts, so rotation is "prepend a new
key, re-encrypt, drop the old one".

Each ciphertext is bound (AES-GCM associated data) to its row id and owner, so
a blob copied onto another user's row does not decrypt.
"""
from __future__ import annotations

import base64
import binascii
import os
import re
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEYS_ENV = "PAYMENT_CARD_KEYS"
_NONCE_BYTES = 12


class VaultUnavailable(RuntimeError):
    """No usable encryption key is configured."""


@dataclass(frozen=True)
class _Key:
    key_id: str
    aead: AESGCM


def _keys() -> list[_Key]:
    raw = (os.getenv(KEYS_ENV) or "").strip()
    keys: list[_Key] = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        key_id, sep, encoded = entry.partition(":")
        if not sep or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", key_id):
            raise VaultUnavailable(f"{KEYS_ENV} entries must look like id:base64key")
        try:
            secret = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise VaultUnavailable(f"{KEYS_ENV} key {key_id} is not valid base64") from exc
        if len(secret) != 32:
            raise VaultUnavailable(f"{KEYS_ENV} key {key_id} must be 32 bytes")
        keys.append(_Key(key_id, AESGCM(secret)))
    return keys


def vault_configured() -> bool:
    try:
        return bool(_keys())
    except VaultUnavailable:
        return False


def _aad(card_id: UUID, user_id: UUID) -> bytes:
    return f"mw_payment_cards:{card_id}:{user_id}".encode()


def encrypt_pan(pan: str, *, card_id: UUID, user_id: UUID) -> tuple[bytes, str]:
    """Encrypt a normalized card number. Returns (nonce + ciphertext, key id)."""
    keys = _keys()
    if not keys:
        raise VaultUnavailable(f"{KEYS_ENV} is not set")
    key = keys[0]
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + key.aead.encrypt(nonce, pan.encode(), _aad(card_id, user_id)), key.key_id


def decrypt_pan(blob: bytes, key_id: str, *, card_id: UUID, user_id: UUID) -> str:
    for key in _keys():
        if key.key_id != key_id:
            continue
        try:
            plain = key.aead.decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], _aad(card_id, user_id))
        except InvalidTag as exc:
            raise ValueError("Stored card does not decrypt for this row") from exc
        return plain.decode()
    raise VaultUnavailable(f"Key {key_id} is not configured")


# ── card-number checks ────────────────────────────────────────────────────────

def normalize_pan(raw: str) -> str | None:
    """Digits only, or None when it can't be a card number (12-19 digits,
    Luhn-valid). Spaces and dashes are allowed between digit groups."""
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not re.fullmatch(r"[0-9][0-9 -]{10,30}[0-9]", candidate):
        return None
    digits = re.sub(r"[ -]", "", candidate)
    if not 12 <= len(digits) <= 19 or not luhn_ok(digits):
        return None
    return digits


def luhn_ok(digits: str) -> bool:
    if not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def card_brand(pan: str) -> str:
    if pan.startswith("4"):
        return "visa"
    two, four = int(pan[:2]), int(pan[:4])
    if 51 <= two <= 55 or 2221 <= four <= 2720:
        return "mastercard"
    if two in (34, 37):
        return "amex"
    if pan.startswith("6011") or pan.startswith("65") or 644 <= int(pan[:3]) <= 649:
        return "discover"
    return "card"


def expiry_ok(month: int, year: int, *, today: date | None = None) -> bool:
    """True while the card is usable: it expires at the END of its month."""
    today = today or date.today()
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        return False
    return (year, month) >= (today.year, today.month)


# Runs of digit groups separated by single spaces or dashes. A card number is
# the longest whole-group window of 12-19 digits that passes Luhn, so "4242
# 4242 4242 4242 123" (number then CVV) still finds the whole number.
_DIGIT_RUN = re.compile(r"(?<![0-9])[0-9]+(?:[ -][0-9]+)*(?![0-9])")
_GROUP = re.compile(r"[0-9]+")
REDACTED = "[card number removed]"


def _pan_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for run in _DIGIT_RUN.finditer(text or ""):
        groups = [(m.start() + run.start(), m.end() + run.start(), m.group(0)) for m in _GROUP.finditer(run.group(0))]
        i = 0
        while i < len(groups):
            digits, found = "", None
            for j in range(i, len(groups)):
                digits += groups[j][2]
                if len(digits) > 19:
                    break
                if len(digits) >= 12 and luhn_ok(digits):
                    found = j  # keep going: the longest valid window wins
            if found is None:
                i += 1
                continue
            spans.append((groups[i][0], groups[found][1]))
            i = found + 1
    return spans


def contains_pan(text: str) -> bool:
    return bool(_pan_spans(text))


def redact_pans(text: str) -> str:
    out, last = [], 0
    for start, end in _pan_spans(text):
        out += [text[last:start], REDACTED]
        last = end
    return "".join(out) + (text or "")[last:]
