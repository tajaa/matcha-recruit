"""Cappe token helpers.

Mirrors `core.services.auth` JWT creation/decoding but issues *Cappe-scoped*
tokens: the subject is a `cappe_accounts.id` and every token carries
`"scope": "cappe"`. `decode_cappe_token` enforces that scope, so a matcha
access token can never satisfy a Cappe endpoint (and vice-versa) even though
both are signed with the same `settings.jwt_secret_key`.

Password hashing/verification is reused verbatim from core — there is exactly
one bcrypt implementation in the codebase.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from jose import jwt, JWTError

from ...config import get_settings

# Re-export the single bcrypt implementation so Cappe code imports from one place.
from ...core.services.auth import hash_password, verify_password_async  # noqa: F401

CAPPE_SCOPE = "cappe"


def create_cappe_access_token(
    account_id: UUID,
    email: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a Cappe-scoped JWT access token."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload = {
        "sub": str(account_id),
        "email": email,
        "scope": CAPPE_SCOPE,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_cappe_refresh_token(account_id: UUID, email: str) -> str:
    """Create a Cappe-scoped JWT refresh token."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": str(account_id),
        "email": email,
        "scope": CAPPE_SCOPE,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def is_cappe_token_revoked(iat, tokens_valid_after) -> bool:
    """True if a token (by its `iat` epoch) predates the account's revocation
    watermark. Tokens minted before the feature shipped (no iat) or accounts
    that never revoked (NULL watermark) are never revoked."""
    if tokens_valid_after is None or iat is None:
        return False
    try:
        return float(iat) < tokens_valid_after.timestamp()
    except (TypeError, ValueError, AttributeError):
        return False


def decode_cappe_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """Decode and validate a Cappe token.

    Returns the raw payload dict on success, or None if invalid/expired, the
    wrong type, or NOT Cappe-scoped (rejecting matcha tokens reused here).
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require_exp": True},
        )
    except (JWTError, KeyError, TypeError):
        return None

    if payload.get("scope") != CAPPE_SCOPE:
        return None
    if expected_type and payload.get("type") != expected_type:
        return None
    if "sub" not in payload:
        return None
    return payload
