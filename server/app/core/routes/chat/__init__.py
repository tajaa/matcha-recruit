"""Chat routes aggregation."""

from fastapi import APIRouter

from .ai import router as ai_router
from .auth import router as auth_router
from .rooms import router as rooms_router
from .messages import router as messages_router
from .websocket import router as websocket_router

# Create main chat router
router = APIRouter()

# Mount sub-routers
router.include_router(ai_router, prefix="/ai", tags=["chat-ai"])
router.include_router(auth_router, prefix="/auth", tags=["chat-auth"])
router.include_router(rooms_router, prefix="/rooms", tags=["chat-rooms"])
router.include_router(messages_router, prefix="/rooms", tags=["chat-messages"])

# WebSocket router is separate (mounted at different path)
ws_router = websocket_router
