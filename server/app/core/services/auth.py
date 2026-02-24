import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from jose import jwt, JWTError

from ...config import get_settings
from ..models.auth import TokenPayload, UserRole


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode('utf-8')
    # Truncate to 72 bytes if needed (bcrypt limit)
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    salt = bcrypt.gensalt(rounds=10)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash (blocking — use verify_password_async in async routes)."""
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Non-blocking bcrypt verify — runs in a thread so the event loop stays free."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


def create_access_token(
    user_id: UUID,
    email: str,
    role: UserRole,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token."""
    settings = get_settings()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expire,
        "type": "access"
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID, email: str, role: UserRole) -> str:
    """Create a JWT refresh token."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)

    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expire,
        "type": "refresh"
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_interview_ws_token(
    interview_id: UUID,
    expires_delta: Optional[timedelta] = None,
    is_practice: bool = False,
) -> str:
    """Create a short-lived JWT token scoped to a specific interview websocket."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=2))
    payload = {
        "sub": str(interview_id),
        "exp": expire,
        "type": "interview_ws",
        "is_practice": is_practice,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_interview_ws_token(token: str) -> tuple[Optional[UUID], bool]:
    """Decode an interview websocket token and return the interview ID and practice flag."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "interview_ws":
            return None, False
        return UUID(payload["sub"]), payload.get("is_practice", False)
    except (JWTError, ValueError, TypeError):
        return None, False


def decode_token(token: str) -> Optional[TokenPayload]:
    """Decode and validate a JWT token."""
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return TokenPayload(
            sub=payload["sub"],
            email=payload["email"],
            role=payload["role"],
            exp=payload["exp"]
        )
    except (JWTError, KeyError, TypeError):
        return None
