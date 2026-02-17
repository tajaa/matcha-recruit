"""Helpers for encrypting/decrypting integration secrets at rest."""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from ...config import get_settings

SECRET_PREFIX = "enc:v1:"


def _resolve_seed(override_seed: Optional[str] = None) -> str:
    if override_seed:
        return override_seed

    try:
        return get_settings().jwt_secret_key
    except RuntimeError:
        env_seed = os.getenv("JWT_SECRET_KEY")
        if env_seed:
            return env_seed
        # Test/dev fallback when settings are not initialized.
        return "matcha-dev-secret"


def _fernet_for_seed(seed: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest())
    return Fernet(key)


def is_encrypted_secret(value: Optional[str]) -> bool:
    return isinstance(value, str) and value.startswith(SECRET_PREFIX)


def encrypt_secret(value: Optional[str], *, seed: Optional[str] = None) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return ""
    if is_encrypted_secret(normalized):
        return normalized

    cipher = _fernet_for_seed(_resolve_seed(seed))
    token = cipher.encrypt(normalized.encode("utf-8")).decode("utf-8")
    return f"{SECRET_PREFIX}{token}"


def decrypt_secret(value: Optional[str], *, seed: Optional[str] = None) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return ""
    if not is_encrypted_secret(normalized):
        return normalized

    token = normalized[len(SECRET_PREFIX):]
    cipher = _fernet_for_seed(_resolve_seed(seed))
    try:
        decrypted = cipher.decrypt(token.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt stored secret") from exc
