"""Pydantic models for the Chat system."""

from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List


# ====================
# Auth Models
# ====================

class ChatUserRegister(BaseModel):
    """Registration request for chat users."""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6)


class ChatUserLogin(BaseModel):
    """Login request for chat users."""
    email: EmailStr
    password: str


class ChatTokenPayload(BaseModel):
    """JWT token payload for chat auth."""
    sub: str  # user_id
    email: str
    exp: int
    type: str = "chat"  # Distinguishes from main app tokens


# ====================
# User Models
# ====================

class ChatUserPublic(BaseModel):
    """Public representation of a chat user."""
    id: UUID
    email: str
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    last_seen: datetime

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class ChatUserUpdate(BaseModel):
    """Update request for user profile."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None


class ChatTokenResponse(BaseModel):
    """Auth token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: ChatUserPublic


class ChatRefreshRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str


# ====================
# Room Models
# ====================

class ChatRoom(BaseModel):
    """Chat room representation."""
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_default: bool = False
    member_count: int = 0
    created_at: datetime


class ChatRoomWithUnread(ChatRoom):
    """Chat room with unread count for current user."""
    unread_count: int = 0
    is_member: bool = False


class ChatRoomMember(BaseModel):
    """Room member representation."""
    user: ChatUserPublic
    joined_at: datetime


# ====================
# Message Models
# ====================

class ChatMessage(BaseModel):
    """Chat message representation."""
    id: UUID
    room_id: UUID
    user_id: Optional[UUID] = None
    content: str
    created_at: datetime
    edited_at: Optional[datetime] = None
    user: Optional[ChatUserPublic] = None


class ChatMessageCreate(BaseModel):
    """Create message request."""
    content: str = Field(..., min_length=1, max_length=2000)


class ChatMessageUpdate(BaseModel):
    """Update message request."""
    content: str = Field(..., min_length=1, max_length=2000)


# ====================
# Pagination Models
# ====================

class MessagePage(BaseModel):
    """Paginated message response."""
    messages: List[ChatMessage]
    next_cursor: Optional[str] = None
    has_more: bool = False


# ====================
# WebSocket Models
# ====================

class WSClientMessage(BaseModel):
    """WebSocket message from client."""
    type: str  # join_room, leave_room, message, typing, ping
    room: Optional[str] = None  # room slug
    content: Optional[str] = None


class WSServerMessage(BaseModel):
    """WebSocket message to client."""
    type: str  # message, user_joined, user_left, typing, online_users, pong, error
    room: Optional[str] = None
    message: Optional[ChatMessage] = None
    user: Optional[ChatUserPublic] = None
    users: Optional[List[ChatUserPublic]] = None
    error: Optional[str] = None
