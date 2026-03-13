"""Encrypt/decrypt sensitive medical credential fields at rest.

Reuses the Fernet scheme from secret_crypto.py. Fields that are already
encrypted (have the ``enc:v1:`` prefix) are left untouched, so this is
safe to call repeatedly on the same data.
"""

from __future__ import annotations

from typing import Any

from .secret_crypto import decrypt_secret, encrypt_secret

ENCRYPTED_FIELDS = [
    "license_number",
    "npi_number",
    "dea_number",
    "malpractice_policy_number",
]


def encrypt_credential_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *data* with sensitive fields encrypted."""
    result = dict(data)
    for field in ENCRYPTED_FIELDS:
        val = result.get(field)
        if val:
            result[field] = encrypt_secret(val)
    return result


def decrypt_credential_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *data* with sensitive fields decrypted."""
    result = dict(data)
    for field in ENCRYPTED_FIELDS:
        val = result.get(field)
        if val:
            result[field] = decrypt_secret(val)
    return result
