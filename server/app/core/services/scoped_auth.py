"""Scoped-JWT helper factory for the side products (Cappe, Tell-Us).

`tellus/services/auth.py` and `cappe/services/auth.py` were near-verbatim twins:
identical token minting, identical revocation check, identical decode-and-
validate — differing only in the scope string baked into the payload.

That duplication is a security-drift hazard rather than merely verbose. The
decode path is what stops a matcha token satisfying a Cappe endpoint (and vice
versa); with two copies, a fix to one — tightening `options`, adding a claim
check, handling a new failure mode — silently leaves the other product exposed.
One implementation, parameterized by scope, cannot drift.

Both side apps may import from `app/core` (the documented cross-product rule in
the root CLAUDE.md), so core is the right home.

Usage:

    _h = make_token_helpers("cappe")
    create_cappe_access_token = _h.create_access_token
    decode_cappe_token = _h.decode_token
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from uuid import UUID

from jose import JWTError, jwt

from app.config import get_settings

__all__ = ["ScopedTokenHelpers", "make_token_helpers", "is_token_revoked"]


def is_token_revoked(iat, tokens_valid_after) -> bool:
    """True if a token (by its ``iat`` epoch) predates the account's revocation
    watermark. Tokens minted before the feature shipped (no iat) or accounts
    that never revoked (NULL watermark) are never revoked.

    Scope-independent, so it is a plain function rather than a bound helper.
    """
    if tokens_valid_after is None or iat is None:
        return False
    try:
        return float(iat) < tokens_valid_after.timestamp()
    except (TypeError, ValueError, AttributeError):
        return False


@dataclass(frozen=True)
class ScopedTokenHelpers:
    scope: str
    create_access_token: Callable[..., str]
    create_refresh_token: Callable[[UUID, str], str]
    decode_token: Callable[..., Optional[dict]]


def make_token_helpers(scope: str) -> ScopedTokenHelpers:
    """Build the create/decode trio for one product scope."""

    def create_access_token(
        account_id: UUID,
        email: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        settings = get_settings()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
        )
        payload = {
            "sub": str(account_id),
            "email": email,
            "scope": scope,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access",
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def create_refresh_token(account_id: UUID, email: str) -> str:
        settings = get_settings()
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        payload = {
            "sub": str(account_id),
            "email": email,
            "scope": scope,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "refresh",
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def decode_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
        """Decode and validate a token for this scope.

        Returns the raw payload dict on success, or None if invalid/expired, the
        wrong type, or not scoped to this product — which is what stops a token
        from one product being replayed against another, since every product
        signs with the same ``settings.jwt_secret_key``.
        """
        settings = get_settings()
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
                options={"require_exp": True},
            )
        except (JWTError, KeyError, TypeError, AttributeError, ValueError):
            # AttributeError is not hypothetical: python-jose does
            # `token.rsplit(...)` without a type check, so a None token raises
            # rather than returning None. Both original per-product copies had
            # this same gap. No caller passes None today (all three sites hand in
            # a string), but a function documented to return None for anything
            # invalid must not raise for ANY input — otherwise the first caller
            # that forwards a missing header turns a 401 into a 500.
            return None

        if payload.get("scope") != scope:
            return None
        if expected_type and payload.get("type") != expected_type:
            return None
        if "sub" not in payload:
            return None
        return payload

    return ScopedTokenHelpers(
        scope=scope,
        create_access_token=create_access_token,
        create_refresh_token=create_refresh_token,
        decode_token=decode_token,
    )
