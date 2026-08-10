from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.matcha.services.huume_code import store
from app.matcha.services.matcha_work import element_repo_service, task_events


class _GroundingConnection:
    async def fetch(self, query, *_args):
        if "regexp_replace" in query:
            return [{"path": "CLAUDE.md", "content": "Follow repository rules."}]
        return [{"path": "server/app/main.py", "content": "app = FastAPI()"}]


class _TaskConnection:
    def __init__(self, task_id, project_id):
        self.task_id = task_id
        self.project_id = project_id
        self.history = []

    async def fetchrow(self, query, *_args):
        if query.lstrip().startswith("SELECT"):
            return {"board_column": "todo"}
        return {
            "id": self.task_id, "project_id": self.project_id, "created_by": None,
            "title": "Ship it", "description": None, "board_column": "in_progress",
            "priority": "medium", "status": "pending", "assigned_to": None,
            "due_date": None, "completed_at": None, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc), "progress_note": None, "category": None,
            "element_id": None, "review_note": None,
        }

    async def execute(self, query, *args):
        self.history.append((query, args))


@pytest.mark.asyncio
async def test_grounding_uses_worker_safe_connection(monkeypatch):
    conn = _GroundingConnection()

    @asynccontextmanager
    async def direct_connection():
        yield conn

    monkeypatch.setattr(element_repo_service, "connection_or_direct", direct_connection)
    result = await store.grounding(uuid4(), None)
    assert "CLAUDE.md" in result
    assert "server/app/main.py" in result


@pytest.mark.asyncio
async def test_silent_move_still_broadcasts_a_complete_task_update(monkeypatch):
    task_id, project_id, actor_id = uuid4(), uuid4(), uuid4()
    conn = _TaskConnection(task_id, project_id)
    received = []

    @asynccontextmanager
    async def direct_connection():
        yield conn

    async def record_event(project, event, payload):
        received.append((project, event, payload))

    monkeypatch.setattr(store, "connection_or_direct", direct_connection)
    monkeypatch.setattr(task_events, "broadcast_task_event", record_event)
    payload = await store.move_ticket_silently(project_id, task_id, "in_progress", actor_id)

    assert payload and payload["board_column"] == "in_progress"
    assert received == [(project_id, "task.updated", payload)]
    assert payload["actor_id"] == str(actor_id)
