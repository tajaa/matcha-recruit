"""Weekly replay must not resurrect tickets deleted before the week."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_deleted_and_older_done_tasks_are_not_seeded():
    from app.matcha.routes.matcha_work import task_history

    conn = AsyncMock()
    conn.fetch.side_effect = [
        [
            {"task_key": "active", "last_event": "column_change", "column_key": "review",
             "title": "Current", "assignee_name": None, "assignee_avatar_url": None},
            {"task_key": "deleted", "last_event": "deleted", "column_key": None,
             "title": "Removed", "assignee_name": None, "assignee_avatar_url": None},
            {"task_key": "done", "last_event": "column_change", "column_key": "done",
             "title": "Earlier", "assignee_name": None, "assignee_avatar_url": None},
        ],
        [],
    ]
    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=conn)
    connection.__aexit__ = AsyncMock(return_value=False)

    with patch.object(task_history, "get_connection", return_value=connection), \
         patch.object(task_history, "_verify_project_access", new=AsyncMock()):
        result = await task_history.get_project_history_replay_endpoint(
            uuid4(), datetime(2026, 9, 21, 7, tzinfo=timezone.utc),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert [task["task_id"] for task in result["starting_state"]] == ["active"]
    snapshot_sql = conn.fetch.call_args_list[0].args[0]
    assert "h.event_type IN ('created', 'column_change', 'review_rejected', 'review_approved', 'deleted')" in snapshot_sql
    assert "COALESCE(h.task_id_text, h.task_id::text) IS NOT NULL" in snapshot_sql
