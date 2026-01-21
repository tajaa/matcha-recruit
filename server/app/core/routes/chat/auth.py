"""Chat authentication routes."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from ....config import get_settings
from ....database import get_connection
from ...services.auth import hash_password, verify_password
from ...models.chat import (
    ChatUserRegister,
    ChatUserLogin,
    ChatTokenResponse,
    ChatTokenPayload,
    ChatUserPublic,
    ChatRefreshRequest,
)

router = APIRouter()
security = HTTPBearer(auto_error=False)


def create_chat_access_token(user_id: UUID, email: str) -> str:
    """Create a JWT access token for chat."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.chat_jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "type": "chat_access"
    }
    return jwt.encode(payload, settings.chat_jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_chat_refresh_token(user_id: UUID, email: str) -> str:
    """Create a JWT refresh token for chat."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.chat_jwt_refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "type": "chat_refresh"
    }
    return jwt.encode(payload, settings.chat_jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_chat_token(token: str) -> ChatTokenPayload | None:
    """Decode and validate a chat JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.chat_jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        # Verify this is a chat token
        if not payload.get("type", "").startswith("chat"):
            return None
        return ChatTokenPayload(
            sub=payload["sub"],
            email=payload["email"],
            exp=payload["exp"],
            type=payload["type"]
        )
    except JWTError:
        return None


async def get_current_chat_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> ChatUserPublic:
    """Dependency to get current authenticated chat user."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    payload = decode_chat_token(token)
    if not payload or payload.type != "chat_access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    async with get_connection() as conn:
        user = await conn.fetchrow(
            """
            SELECT id, email, first_name, last_name, avatar_url, bio, last_seen
            FROM chat_users WHERE id = $1 AND is_active = TRUE
            """,
            UUID(payload.sub)
        )
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # Update last_seen
        await conn.execute(
            "UPDATE chat_users SET last_seen = CURRENT_TIMESTAMP WHERE id = $1",
            UUID(payload.sub)
        )

        return ChatUserPublic(
            id=user["id"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            avatar_url=user["avatar_url"],
            bio=user["bio"],
            last_seen=user["last_seen"]
        )


async def get_optional_chat_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> ChatUserPublic | None:
    """Dependency to get current chat user if authenticated (optional)."""
    if not credentials:
        return None

    try:
        return await get_current_chat_user(credentials)
    except HTTPException:
        return None


@router.post("/register", response_model=ChatTokenResponse)
async def register(data: ChatUserRegister):
    """Register a new chat user."""
    async with get_connection() as conn:
        # Check if email already exists
        existing = await conn.fetchval(
            "SELECT id FROM chat_users WHERE email = $1",
            data.email.lower()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        password_hash = hash_password(data.password)
        user = await conn.fetchrow(
            """
            INSERT INTO chat_users (email, first_name, last_name, password_hash)
            VALUES ($1, $2, $3, $4)
            RETURNING id, email, first_name, last_name, avatar_url, bio, last_seen
            """,
            data.email.lower(),
            data.first_name,
            data.last_name,
            password_hash
        )

        user_public = ChatUserPublic(
            id=user["id"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            avatar_url=user["avatar_url"],
            bio=user["bio"],
            last_seen=user["last_seen"]
        )

        # Auto-join default rooms
        default_rooms = await conn.fetch(
            "SELECT id FROM chat_rooms WHERE is_default = TRUE"
        )
        for room in default_rooms:
            await conn.execute(
                """
                INSERT INTO chat_room_members (room_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                room["id"],
                user["id"]
            )

        return ChatTokenResponse(
            access_token=create_chat_access_token(user["id"], user["email"]),
            refresh_token=create_chat_refresh_token(user["id"], user["email"]),
            user=user_public
        )


@router.post("/login", response_model=ChatTokenResponse)
async def login(data: ChatUserLogin):
    """Login a chat user."""
    async with get_connection() as conn:
        user = await conn.fetchrow(
            """
            SELECT id, email, first_name, last_name, password_hash, avatar_url, bio, last_seen
            FROM chat_users WHERE email = $1 AND is_active = TRUE
            """,
            data.email.lower()
        )

        if not user or not verify_password(data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Update last_seen
        await conn.execute(
            "UPDATE chat_users SET last_seen = CURRENT_TIMESTAMP WHERE id = $1",
            user["id"]
        )

        user_public = ChatUserPublic(
            id=user["id"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            avatar_url=user["avatar_url"],
            bio=user["bio"],
            last_seen=user["last_seen"]
        )

        return ChatTokenResponse(
            access_token=create_chat_access_token(user["id"], user["email"]),
            refresh_token=create_chat_refresh_token(user["id"], user["email"]),
            user=user_public
        )


@router.post("/refresh", response_model=ChatTokenResponse)
async def refresh_token(data: ChatRefreshRequest):
    """Refresh access token."""
    payload = decode_chat_token(data.refresh_token)
    if not payload or payload.type != "chat_refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    async with get_connection() as conn:
        user = await conn.fetchrow(
            """
            SELECT id, email, first_name, last_name, avatar_url, bio, last_seen
            FROM chat_users WHERE id = $1 AND is_active = TRUE
            """,
            UUID(payload.sub)
        )
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        user_public = ChatUserPublic(
            id=user["id"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            avatar_url=user["avatar_url"],
            bio=user["bio"],
            last_seen=user["last_seen"]
        )

        return ChatTokenResponse(
            access_token=create_chat_access_token(user["id"], user["email"]),
            refresh_token=create_chat_refresh_token(user["id"], user["email"]),
            user=user_public
        )


@router.get("/me", response_model=ChatUserPublic)
async def get_me(current_user: ChatUserPublic = Depends(get_current_chat_user)):
    """Get current user profile."""
    return current_user
