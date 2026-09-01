from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.werk.routes import channels_ws


def test_autopr_context_reference_is_exact_and_decision_bound():
    valid = channels_ws._autopr_context_reference({
        "kind": "autopr_context_request",
        "project_id": "11111111-0000-4000-8000-000000000001",
        "task_id": "22222222-0000-4000-8000-000000000002",
        "expected_progress_note": "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS",
    })
    assert str(valid["task_id"]).startswith("22222222")
    assert valid["expected_progress_note"].startswith("🤖 AUTO SETUP")

    assert channels_ws._autopr_context_reference({"kind": "other"}) is None
    assert channels_ws._autopr_context_reference(
        {"kind": "autopr_context_request", "project_id": "bad"}
    ) is None


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        return False


class _ProjectConnection:
    def __init__(self, company_id):
        self.company_id = company_id

    async def fetchrow(self, _query, *_args):
        return {
            "company_id": self.company_id,
            "is_collaborator": True,
            "is_same_company": False,
        }


@pytest.mark.asyncio
async def test_direct_espresso_reply_becomes_escalated_card_context(monkeypatch):
    from app.matcha.services.matcha_work import project_task_service
    from app.matcha.services.matcha_work.project_agent import chat

    company_id = uuid4()
    project_id = uuid4()
    task_id = uuid4()
    user_id = uuid4()
    channel_id = uuid4()
    request = AsyncMock(return_value={"ok": True})
    post = AsyncMock()
    monkeypatch.setattr(
        channels_ws,
        "get_connection",
        lambda: _ConnectionContext(_ProjectConnection(company_id)),
    )
    monkeypatch.setattr(project_task_service, "request_autopr_reconsideration", request)
    monkeypatch.setattr(chat, "post_as_espresso", post)

    await channels_ws._bg_apply_autopr_context_reply(
        str(channel_id),
        SimpleNamespace(id=user_id, role="client"),
        "@espresso The jobs editor is still missing credential rows.",
        {
            "project_id": project_id,
            "task_id": task_id,
            "expected_progress_note": "exact decision",
        },
    )

    request.assert_awaited_once_with(
        project_id=project_id,
        task_id=task_id,
        actor_user_id=user_id,
        expected_progress_note="exact decision",
        body="The jobs editor is still missing credential rows.",
    )
    post.assert_awaited_once()
    assert post.await_args.args[0] == company_id
    assert post.await_args.args[1] == UUID(str(channel_id))
    assert "escalated AutoPR context" in post.await_args.args[2]
