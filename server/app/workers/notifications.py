"""Redis pub/sub notifications for worker task completion."""

import json
import os
from typing import Any

import redis
from dotenv import load_dotenv

load_dotenv()


def get_redis_client() -> redis.Redis:
    """Get a synchronous Redis client for worker processes."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(redis_url)


def publish_task_complete(
    channel: str,
    task_type: str,
    entity_id: str,
    result: dict[str, Any] | None = None,
) -> None:
    """
    Publish task completion to Redis pub/sub for WebSocket forwarding.

    Args:
        channel: The Redis channel to publish to (e.g., "company:{company_id}")
        task_type: The type of task that completed (e.g., "interview_analysis")
        entity_id: The ID of the entity that was processed (e.g., interview_id)
        result: Optional result data to include in the notification
    """
    client = get_redis_client()
    message = json.dumps({
        "type": "task_complete",
        "task_type": task_type,
        "entity_id": entity_id,
        "result": result or {},
    })
    client.publish(channel, message)
    client.close()


def publish_task_progress(
    channel: str,
    task_type: str,
    entity_id: str,
    progress: int,
    total: int,
    message: str | None = None,
) -> None:
    """
    Publish task progress update to Redis pub/sub.

    Args:
        channel: The Redis channel to publish to
        task_type: The type of task in progress
        entity_id: The ID of the entity being processed
        progress: Current progress count
        total: Total items to process
        message: Optional status message
    """
    client = get_redis_client()
    data = json.dumps({
        "type": "task_progress",
        "task_type": task_type,
        "entity_id": entity_id,
        "progress": progress,
        "total": total,
        "message": message,
    })
    client.publish(channel, data)
    client.close()


def publish_task_error(
    channel: str,
    task_type: str,
    entity_id: str,
    error: str,
) -> None:
    """
    Publish task error to Redis pub/sub.

    Args:
        channel: The Redis channel to publish to
        task_type: The type of task that failed
        entity_id: The ID of the entity being processed
        error: Error message
    """
    client = get_redis_client()
    data = json.dumps({
        "type": "task_error",
        "task_type": task_type,
        "entity_id": entity_id,
        "error": error,
    })
    client.publish(channel, data)
    client.close()
