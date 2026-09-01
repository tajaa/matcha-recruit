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
        attachment_ids=None,
    )
    post.assert_awaited_once()
    assert post.await_args.args[0] == company_id
    assert post.await_args.args[1] == UUID(str(channel_id))
    assert "escalated AutoPR context" in post.await_args.args[2]


@pytest.mark.asyncio
async def test_screenshot_only_espresso_reply_is_attached_to_ticket(monkeypatch):
    from app.matcha.services.matcha_work import project_file_service, project_task_service
    from app.matcha.services.matcha_work.project_agent import chat

    company_id = uuid4()
    project_id = uuid4()
    task_id = uuid4()
    user_id = uuid4()
    channel_id = uuid4()
    file_id = uuid4()
    request = AsyncMock(return_value={"ok": True, "autopr_directives": []})
    sync = AsyncMock(return_value=[file_id])
    post = AsyncMock()
    monkeypatch.setattr(
        channels_ws,
        "get_connection",
        lambda: _ConnectionContext(_ProjectConnection(company_id)),
    )
    monkeypatch.setattr(project_task_service, "request_autopr_reconsideration", request)
    monkeypatch.setattr(project_file_service, "sync_channel_attachments_to_task", sync)
    monkeypatch.setattr(chat, "post_as_espresso", post)

    attachment = {
        "url": "https://files.hey-matcha.com/screenshot.png",
        "filename": "screenshot.png",
        "content_type": "image/png",
        "size": 123,
    }
    await channels_ws._bg_apply_autopr_context_reply(
        str(channel_id),
        SimpleNamespace(id=user_id, role="client"),
        "",
        {
            "project_id": project_id,
            "task_id": task_id,
            "expected_progress_note": "exact decision",
        },
        [attachment],
    )

    sync.assert_awaited_once()
    request.assert_awaited_once_with(
        project_id=project_id,
        task_id=task_id,
        actor_user_id=user_id,
        expected_progress_note="exact decision",
        body=None,
        attachment_ids=[file_id],
    )
    assert "screenshots" in post.await_args.args[2]


@pytest.mark.asyncio
async def test_chat_image_reference_becomes_bounded_task_file(monkeypatch):
    from app.matcha.services.matcha_work import project_file_service

    class _Storage:
        @staticmethod
        def is_supported_storage_path(path):
            return path.startswith("https://cdn.example.cloudfront.net/")

    class _Conn:
        def __init__(self):
            self.insert_args = None

        async def fetchval(self, query, *_args):
            if "SELECT EXISTS" in query:
                return True
            return None

        async def fetchrow(self, query, *args):
            assert "INSERT INTO mw_project_files" in query
            self.insert_args = args
            return {"id": file_id}

    project_id = uuid4()
    task_id = uuid4()
    user_id = uuid4()
    file_id = uuid4()
    conn = _Conn()
    monkeypatch.setattr(project_file_service, "get_storage", lambda: _Storage())

    ids = await project_file_service.sync_channel_attachments_to_task(
        conn,
        project_id,
        task_id,
        user_id,
        [{
            "url": "https://cdn.example.cloudfront.net/chat/shot",
            "kind": "image",
            "size": 321,
        }],
    )

    assert ids == [file_id]
    assert conn.insert_args[3] == "shot.png"
    assert conn.insert_args[6] == 321
