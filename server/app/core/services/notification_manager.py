"""Server-side notification manager for forwarding Redis pub/sub to WebSocket clients."""

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class NotificationManager:
    """
    Manages WebSocket connections and forwards Redis pub/sub messages to clients.

    The server subscribes to Redis channels and forwards notifications to connected
    WebSocket clients. This allows Celery workers to notify the frontend when
    async tasks complete.
    """

    def __init__(self):
        # Map of channel -> list of connected WebSockets
        self._connections: dict[str, list[WebSocket]] = {}
        self._redis = None
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    async def connect(self, redis_url: str) -> None:
        """Initialize Redis connection for pub/sub."""
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url)
        self._pubsub = self._redis.pubsub()
        print("[NotificationManager] Connected to Redis for pub/sub")

    async def subscribe(self, websocket: WebSocket, channel: str) -> None:
        """Subscribe a WebSocket client to a channel."""
        if channel not in self._connections:
            self._connections[channel] = []
            # Subscribe to the Redis channel
            await self._pubsub.subscribe(channel)
            print(f"[NotificationManager] Subscribed to Redis channel: {channel}")

        self._connections[channel].append(websocket)
        print(f"[NotificationManager] WebSocket subscribed to {channel}")

    async def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        """Unsubscribe a WebSocket client from a channel."""
        if channel in self._connections:
            if websocket in self._connections[channel]:
                self._connections[channel].remove(websocket)
                print(f"[NotificationManager] WebSocket unsubscribed from {channel}")

            # If no more clients on this channel, unsubscribe from Redis
            if not self._connections[channel]:
                await self._pubsub.unsubscribe(channel)
                del self._connections[channel]
                print(f"[NotificationManager] Unsubscribed from Redis channel: {channel}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from all channels."""
        channels_to_remove = []
        for channel, sockets in self._connections.items():
            if websocket in sockets:
                sockets.remove(websocket)
                if not sockets:
                    channels_to_remove.append(channel)

        for channel in channels_to_remove:
            await self._pubsub.unsubscribe(channel)
            del self._connections[channel]
            print(f"[NotificationManager] Unsubscribed from Redis channel: {channel}")

    async def start_listener(self) -> None:
        """Start the background task to listen for Redis messages."""
        self._listener_task = asyncio.create_task(self._listen())
        print("[NotificationManager] Started Redis listener")

    async def stop_listener(self) -> None:
        """Stop the background listener task."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
            print("[NotificationManager] Stopped Redis listener")

    async def _listen(self) -> None:
        """Background task to listen for Redis messages and forward to WebSockets."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()

                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()

                    # Forward to all connected WebSockets on this channel
                    await self._broadcast(channel, data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[NotificationManager] Listener error: {e}")

    async def _broadcast(self, channel: str, data: str) -> None:
        """Broadcast a message to all WebSockets subscribed to a channel."""
        if channel not in self._connections:
            return

        dead_sockets = []
        for ws in self._connections[channel]:
            try:
                await ws.send_text(data)
            except Exception:
                dead_sockets.append(ws)

        # Remove dead connections
        for ws in dead_sockets:
            self._connections[channel].remove(ws)

    async def close(self) -> None:
        """Clean up Redis connection."""
        await self.stop_listener()
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        print("[NotificationManager] Closed Redis connection")

    async def broadcast_to_channel(self, channel: str, message: dict[str, Any]) -> None:
        """Directly broadcast a message to a channel (without Redis)."""
        data = json.dumps(message)
        await self._broadcast(channel, data)


# Global instance
notification_manager: NotificationManager | None = None


def get_notification_manager() -> NotificationManager:
    """Get the global notification manager instance."""
    global notification_manager
    if notification_manager is None:
        raise RuntimeError("NotificationManager not initialized")
    return notification_manager


async def init_notification_manager(redis_url: str) -> NotificationManager:
    """Initialize the global notification manager."""
    global notification_manager
    notification_manager = NotificationManager()
    await notification_manager.connect(redis_url)
    await notification_manager.start_listener()
    return notification_manager


async def close_notification_manager() -> None:
    """Close the global notification manager."""
    global notification_manager
    if notification_manager:
        await notification_manager.close()
        notification_manager = None
